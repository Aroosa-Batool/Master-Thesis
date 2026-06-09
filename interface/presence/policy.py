"""Shared consent/policy machinery for the watch-mediated demos.

Provides:

- ``BangleClient``: BLE wrapper around the Bangle.js running
  ``bangle/consent_app.js``. Runs its own asyncio loop on a background
  thread, streams heart-rate samples, and exposes a thread-safe
  ``ask_consent(message, timeout)`` that round-trips a Yes/No question
  to the watch and blocks the caller until the user taps or the timeout
  elapses.

- ``ConsentStore``: small JSON-backed cache mapping
  ``(bystander_id, content_type)`` -> ``"YES" | "NO"``. This is what
  lets the robot remember a person's decision and skip re-asking the
  next time the same bystander appears.

Wire format (line-oriented Nordic UART, served by ``bangle/consent_app.js``):

- Watch -> laptop, line-oriented::

    BPM:<n>
    CONSENT:<id>:YES
    CONSENT:<id>:NO

- Laptop -> watch, line-oriented JS that the watch REPL evaluates::

    consent("p17", "Allow private reminder in front of bystander?")\\n

Strings are JSON-encoded so quotes/newlines/backslashes are escaped.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from bleak import BleakClient, BleakScanner
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: install with `pip install bleak`.") from exc


# Nordic UART:
#   RX (notify): watch -> laptop (we subscribe).
#   TX (write):  laptop -> watch (we send JS for the REPL to evaluate).
NUS_RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"


class _LineBuffer:
    def __init__(self) -> None:
        self._buf = ""

    def feed(self, data: bytes) -> list[str]:
        self._buf += data.decode("utf-8", errors="replace")
        lines: list[str] = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            lines.append(line.strip())
        return lines


class BangleClient:
    """Owns the BLE link to the watch on a background asyncio thread.

    Lifecycle:
        client = BangleClient()
        if client.start():
            ...                          # main loop reads latest_bpm(),
                                         # calls ask_consent(...)
        client.close()

    All public methods are safe to call from the main thread.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: BleakClient | None = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._bpm = 0
        self._bpm_ts = 0.0
        # _pending is only touched from the BLE loop thread.
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._next_id = 0

    # --- public, thread-safe -------------------------------------------------

    def start(self, timeout: float = 20.0) -> bool:
        """Connect to the watch. Returns True iff the link came up."""

        threading.Thread(target=self._run, daemon=True).start()
        if not self._ready.wait(timeout=timeout):
            return False
        return self._client is not None

    def close(self) -> None:
        self._stop.set()

    def latest_bpm(self) -> tuple[int, float]:
        with self._lock:
            return self._bpm, self._bpm_ts

    def is_connected(self) -> bool:
        """Best-effort 'is the watch in BLE range right now' check.

        The demos use this as the owner's presence signal: as long as
        the watch holds a GATT link to the laptop, the owner is taken
        to be in the room (Bangle.js BLE reaches roughly 10 m, which
        approximates 'same room'). Returns False if we never connected
        or if bleak reports the link has dropped.

        Reading ``self._client`` from the main thread is safe under
        the GIL: ``_main`` only ever assigns the attribute (set on
        connect, ``None`` in the finally on disconnect). The follow-up
        ``client.is_connected`` is bleak's sync property and may go
        False without us seeing the disconnect event yet, hence the
        try/except guard.
        """

        client = self._client
        if client is None:
            return False
        try:
            return bool(client.is_connected)
        except Exception:
            return False

    def ask_consent(self, message: str, timeout: float = 30.0) -> bool | None:
        """Send ``message`` to the watch and block until Yes/No or timeout.

        Returns True for Yes, False for No, None if the watch did not
        reply within ``timeout`` seconds (or the link is down). Callers
        should treat ``None`` as a privacy-safe "do not disclose".
        """

        if self._loop is None or self._client is None:
            return None
        prompt_id = self._fresh_id()
        future = asyncio.run_coroutine_threadsafe(
            self._ask(prompt_id, message, timeout), self._loop
        )
        try:
            return future.result(timeout=timeout + 5.0)
        except Exception as exc:
            print(f"[ble] ask_consent failed: {exc}")
            return None

    # --- private -------------------------------------------------------------

    def _fresh_id(self) -> str:
        with self._lock:
            self._next_id += 1
            return f"p{self._next_id}"

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception as exc:
            print(f"[ble] loop crashed: {exc}")
            self._ready.set()

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        print("[ble] scanning for Bangle.js...")
        device = await BleakScanner.find_device_by_filter(
            lambda d, adv: bool(d.name and "bangle" in d.name.lower()),
            timeout=15.0,
        )
        if device is None:
            print("[ble] watch not found. Demo will run without prompts.")
            self._ready.set()
            return

        print(f"[ble] connecting to {device.name} ({device.address})...")
        buffer = _LineBuffer()

        def on_uart(_sender: int, data: bytearray) -> None:
            for line in buffer.feed(bytes(data)):
                self._handle_line(line)

        try:
            async with BleakClient(device) as client:
                self._client = client
                await client.start_notify(NUS_RX_UUID, on_uart)
                print("[ble] subscribed; watch is online.")
                self._ready.set()
                while not self._stop.is_set():
                    await asyncio.sleep(0.5)
                try:
                    await client.stop_notify(NUS_RX_UUID)
                except Exception:
                    pass
        finally:
            # Fast-fail any consent prompts still waiting on a reply so the
            # worker thread that called ask_consent() isn't blocked on a
            # Future no one will resolve. We use CancelledError instead of
            # set_result(False) so the caller can distinguish "BLE link
            # dropped" from "user tapped No" - otherwise a mid-prompt
            # disconnect would silently cache a NO decision for the
            # bystander, polluting the cache with a non-decision.
            for pid, fut in list(self._pending.items()):
                if not fut.done():
                    try:
                        fut.set_exception(
                            asyncio.CancelledError("BLE link closed")
                        )
                    except Exception:
                        pass
            self._pending.clear()
            self._client = None

    def _handle_line(self, line: str) -> None:
        # Defensive: Espruino's REPL emits ">" prompts that can leak
        # onto the UART (especially during the brief window between BLE
        # connect and our echo(0) re-applying). The watch script also
        # avoids printing console.log to the UART for the same reason,
        # but defense-in-depth here means a leaked ">" prefix doesn't
        # cause us to silently drop a BPM/CONSENT frame.
        cleaned = line.lstrip(">").strip()
        # Drop pure REPL chatter outright - "=undefined" is what the
        # REPL prints after evaluating a void expression, and a bare
        # ">" prompt collapses to "" after the lstrip above.
        if not cleaned or cleaned == "=undefined":
            return

        if cleaned.startswith("BPM:"):
            try:
                bpm = int(cleaned[4:])
            except ValueError:
                return
            with self._lock:
                self._bpm = bpm
                self._bpm_ts = time.monotonic()
            return
        if cleaned.startswith("CONSENT:"):
            # "CONSENT:<id>:YES" or "CONSENT:<id>:NO"
            parts = cleaned.split(":", 2)
            if len(parts) != 3:
                return
            pid, answer = parts[1], parts[2].strip().upper()
            fut = self._pending.pop(pid, None)
            if fut is None or fut.done():
                return
            fut.set_result(answer == "YES")
            return
        # Anything else is probably a stray REPL message from the watch
        # - typically an "Uncaught SyntaxError: ..." caused by a stale
        # partial write. Surface it so the next time something breaks
        # on the watch side we have a chance to see it rather than
        # silently dropping the line.
        print(f"[ble] watch> {cleaned}", flush=True)

    async def _ask(self, prompt_id: str, message: str, timeout: float) -> bool | None:
        assert self._client is not None
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[prompt_id] = future

        # JSON-encoded strings are valid JS string literals, so this
        # round-trips quotes/newlines/backslashes correctly.
        #
        # Leading "\n" is defensive: if a previous _ask call failed
        # mid-payload, the watch may have a partial JS line buffered
        # without a terminating newline. The leading newline forces
        # Espruino to evaluate (and discard, as a SyntaxError logged
        # via _handle_line) that stale buffer before our new
        # consent(...) call starts arriving.
        payload = (
            f"\nconsent({json.dumps(prompt_id)},{json.dumps(message)});\n"
        )
        # Writing to Espruino's NUS RX from macOS CoreBluetooth has two
        # requirements that bleak does NOT handle for us:
        #   1. Chunk under the per-write cap. Espruino's BLE UART is
        #      documented to accept at most 20 bytes per GATT write on
        #      the NUS RX endpoint; a single 130-byte write returns
        #      CBATTErrorCode 130 (0x82, application-defined error per
        #      BT Core Spec Vol 3 Part F, application range 0x80-0x9F).
        #      20 bytes is the safe floor regardless of negotiated MTU.
        #   2. response=False routes via macOS's writeWithoutResponse
        #      path, which is what the Espruino Web IDE itself uses
        #      and avoids per-write ATT ACK round-trips. The NUS RX
        #      characteristic actually supports both write types per
        #      the Nordic NUS spec, so this is a perf/latency choice
        #      rather than a correctness one.
        # We also yield briefly between chunks so macOS's
        # writeWithoutResponse flow-control queue (which bleak does
        # not always surface, see bleak issue #1589) drains rather
        # than silently dropping a chunk.
        #
        # Espruino's REPL buffers incoming UART bytes until it sees a
        # newline, then evaluates the buffered line as JS - so the
        # chunked writes still land as one consent(...) call.
        data = payload.encode("utf-8")
        chunk_size = 20
        inter_chunk_delay_s = 0.005
        try:
            chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
            for i, chunk in enumerate(chunks):
                await self._client.write_gatt_char(
                    NUS_TX_UUID, chunk, response=False,
                )
                if i < len(chunks) - 1:
                    await asyncio.sleep(inter_chunk_delay_s)
        except Exception as exc:
            print(f"[ble] write failed: {exc}")
            self._pending.pop(prompt_id, None)
            return None

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(prompt_id, None)
            print(f"[ble] consent prompt {prompt_id} timed out.")
            return None
        except asyncio.CancelledError:
            # BLE link closed while the worker was waiting on this
            # prompt (see the cleanup path in _main()). Returning None
            # tells the caller "no decision" so they DON'T cache it as
            # a NO.
            self._pending.pop(prompt_id, None)
            print(
                f"[ble] consent prompt {prompt_id} cancelled - BLE link closed."
            )
            return None


# ---------------------------------------------------------------------------
# Consent store (Cache-Memory policy).


@dataclass(frozen=True)
class ConsentKey:
    bystander_id: str
    content_type: str


class ConsentStore:
    """JSON-backed lookup keyed by ``(bystander_id, content_type)``.

    Persists across runs so the Cache-Memory policy survives restarts
    of the demo script. The store is single-file and tiny; we rewrite
    the whole file on every ``put`` to keep the logic simple.

    Thread-safe: a single ``threading.Lock`` guards both the in-memory
    dict and the on-disk file. ``put`` writes through a same-directory
    temp file and atomically renames so a crash mid-write can't leave
    half a JSON file on disk.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, str]] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text())
            except Exception as exc:
                print(f"[cache] could not read {path}: {exc}; starting fresh.")
                self._data = {}

    def get(self, key: ConsentKey) -> bool | None:
        with self._lock:
            v = self._data.get(key.bystander_id, {}).get(key.content_type)
        if v == "YES":
            return True
        if v == "NO":
            return False
        return None

    def put(self, key: ConsentKey, value: bool) -> None:
        with self._lock:
            self._data.setdefault(key.bystander_id, {})[key.content_type] = (
                "YES" if value else "NO"
            )
            payload = json.dumps(self._data, indent=2)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: same-directory temp file then os.replace so
            # we never overwrite the live JSON with a half-written file.
            # The tmpfile MUST be in the same directory as the target,
            # otherwise os.replace across filesystems raises OSError(EXDEV)
            # (real risk on macOS where /tmp is a different volume).
            try:
                fd, tmp_name = tempfile.mkstemp(
                    prefix=self._path.name + ".",
                    suffix=".tmp",
                    dir=str(self._path.parent),
                )
                try:
                    with os.fdopen(fd, "w") as f:
                        f.write(payload)
                    os.replace(tmp_name, self._path)
                except Exception:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
                    raise
            except Exception as exc:
                print(f"[cache] could not write {self._path}: {exc}")

    def dump(self) -> dict[str, dict[str, str]]:
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}
