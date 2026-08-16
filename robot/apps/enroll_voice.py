"""One-shot owner *voice* enrollment - the audio analog of ``enroll_face.py``.

Records the owner speaking alone, turns the speech into Resemblyzer
d-vector embeddings, averages them, and writes the result to
``owner_voice.json`` via the same ``OwnerStore`` the camera pipeline uses.
After this runs once, the voice apps (``mic_remember`` / ``mic_reask``) can
tell the owner's voice apart from any other speaker it hears, so the consent
cache is keyed by bystander voices only.

Procedure:
  - Opens the default microphone.
  - Asks you to speak continuously and **alone** (read a few sentences)
    while it captures ``TARGET_SAMPLES`` voiced-window embeddings.
  - Averages them into one owner voice-print and saves it.
  - Runs a short verify loop showing the live similarity of whatever it
    hears to the saved owner print, so you can sanity-check it.

A small status window (level meter + sample count) stands in for the
camera preview; press 'q' there to abort. The laptop terminal is not used
for any consent decision - only the one-time "overwrite?" guard at the
very start reads a keystroke, exactly like ``enroll_face.py``.

Run:
    python -m robot.apps.enroll_voice
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
import threading
import time
from collections import deque

import cv2
import numpy as np

try:
    import sounddevice as sd
except (ModuleNotFoundError, OSError) as exc:
    raise SystemExit(
        "Missing dependency: install with `pip install sounddevice` "
        "(needs the PortAudio library; on Linux: `apt install libportaudio2`)."
    ) from exc

from robot.perception.audio_device import pick_input_device
from robot.core.owner import OwnerStore
from robot.perception.voice_id import VOICE_OWNER_THRESHOLD, VOICE_SR, VoiceIdentifier
from robot.core.logsetup import setup_logging, logcall, get_logger
from robot.core import presentation_telemetry as telemetry


from robot.paths import OWNER_VOICE_PATH

log = get_logger(__name__)

TARGET_SAMPLES = 20
# Run the encoder on disjoint chunks of this length so we don't double-
# count overlapping windows. ~2 s of continuous speech yields one or two
# voiced-window embeddings.
PROCESS_CHUNK_S = 2.0
BLOCK_FRAMES = int(VOICE_SR * 0.1)  # 100 ms mic callback blocks
UI_JOB = os.environ.get("THESIS_UI_JOB") == "1"


@logcall(level=logging.DEBUG)
def _make_hud(rms: float, gate: float, lines: list[tuple[str, tuple[int, int, int]]]):
    """Render the level meter + status lines into a small BGR image."""

    img = np.zeros((220, 660, 3), dtype=np.uint8)
    # Level bar, scaled so normal speech fills most of the width.
    level = min(1.0, rms / max(gate * 4.0, 1e-4))
    cv2.rectangle(img, (20, 24), (640, 54), (70, 70, 70), 1)
    cv2.rectangle(img, (20, 24), (20 + int(620 * level), 54), (0, 220, 0), -1)
    for i, (text, color) in enumerate(lines):
        cv2.putText(
            img, text, (20, 96 + i * 32),
            cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 1,
        )
    return img


class _Mic:
    """Background mic capture into a thread-safe block queue."""

    @logcall
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blocks: deque[np.ndarray] = deque()
        self.cur_rms = 0.0

    @logcall(level=logging.DEBUG)
    def callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        x = indata[:, 0].copy()
        rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
        with self._lock:
            self.cur_rms = rms
            self._blocks.append(x)

    @logcall(level=logging.DEBUG)
    def drain(self) -> np.ndarray:
        with self._lock:
            if not self._blocks:
                return np.zeros(0, dtype=np.float32)
            chunk = np.concatenate(list(self._blocks))
            self._blocks.clear()
            return chunk


@logcall
def capture_owner_samples(
    identifier: VoiceIdentifier, mic: _Mic
) -> list[np.ndarray]:
    """Capture loop. Returns embeddings, or [] if the user aborts with 'q'."""

    samples: list[np.ndarray] = []
    pending = np.zeros(0, dtype=np.float32)
    chunk_target = int(PROCESS_CHUNK_S * VOICE_SR)

    print(
        "[enroll] speak now - alone, in full sentences. Keep going until "
        f"{TARGET_SAMPLES} samples are captured.",
        flush=True,
    )
    log.info("owner voice capture started (target %d samples)", TARGET_SAMPLES,
             extra={"event": "capture_started"})
    while len(samples) < TARGET_SAMPLES:
        new = mic.drain()
        if len(new):
            pending = np.concatenate([pending, new])
        if len(pending) >= chunk_target:
            for seg in identifier.segment_and_embed(pending):
                samples.append(seg.embedding)
                print(
                    f"[enroll] captured sample {len(samples)}/{TARGET_SAMPLES}",
                    flush=True,
                )
                log.info("captured sample %d/%d", len(samples), TARGET_SAMPLES,
                         extra={"event": "sample_captured"})
                if len(samples) >= TARGET_SAMPLES:
                    break
            pending = np.zeros(0, dtype=np.float32)

        hud = _make_hud(
            mic.cur_rms, gate=0.02,
            lines=[
                (f"Owner VOICE enrollment - {len(samples)}/{TARGET_SAMPLES} samples",
                 (255, 255, 255)),
                ("Speak now, ALONE, in full sentences.", (0, 220, 0)),
                ("'q' to abort", (200, 200, 200)),
            ],
        )
        telemetry.metric("microphone_level", mic.cur_rms)
        telemetry.emit(
            "job_progress", progress=len(samples) / TARGET_SAMPLES,
            detail=f"Voice samples: {len(samples)}/{TARGET_SAMPLES}",
        )
        if not UI_JOB:
            cv2.imshow("Owner voice enrollment", hud)
            if cv2.waitKey(20) & 0xFF == ord("q"):
                return []
        else:
            time.sleep(0.02)

    print(f"[enroll] captured {len(samples)} samples.", flush=True)
    return samples


@logcall
def verify_loop(identifier: VoiceIdentifier, mic: _Mic, store: OwnerStore) -> None:
    """Show live similarity of whatever is heard to the saved owner print."""

    print(
        "[enroll] verify loop: keep talking (and have someone else speak) to "
        "see OWNER vs other. 'q' to exit.",
        flush=True,
    )
    pending = np.zeros(0, dtype=np.float32)
    chunk_target = int(PROCESS_CHUNK_S * VOICE_SR)
    last_label = "(listening...)"
    last_color = (200, 200, 200)
    verify_started = time.monotonic()
    while True:
        new = mic.drain()
        if len(new):
            pending = np.concatenate([pending, new])
        if len(pending) >= chunk_target:
            emb = identifier.embed(pending)
            pending = np.zeros(0, dtype=np.float32)
            if emb is not None:
                is_owner, sim = store.matches(emb, threshold=VOICE_OWNER_THRESHOLD)
                last_label = f"{'OWNER' if is_owner else 'other'}  sim={sim:.2f}"
                last_color = (0, 220, 0) if is_owner else (0, 0, 255)

        hud = _make_hud(
            mic.cur_rms, gate=0.02,
            lines=[
                (f"Verify - sim >= {VOICE_OWNER_THRESHOLD:.2f} = OWNER",
                 (255, 255, 255)),
                (last_label, last_color),
                ("'q' to exit", (200, 200, 200)),
            ],
        )
        telemetry.metric("microphone_level", mic.cur_rms, label=last_label)
        if UI_JOB and time.monotonic() - verify_started >= 8.0:
            return
        if not UI_JOB:
            cv2.imshow("Owner voice enrollment", hud)
            if cv2.waitKey(20) & 0xFF == ord("q"):
                return
        else:
            time.sleep(0.02)


@logcall
def main() -> None:
    setup_logging(run_name="enroll_voice")
    store = OwnerStore(OWNER_VOICE_PATH)
    if store.has_owner():
        print(
            f"[enroll] A voice owner is already enrolled "
            f"(samples={store.samples()}, at={store.enrolled_at()}).",
            flush=True,
        )
        if UI_JOB:
            reply = "yes" if os.environ.get("THESIS_UI_OVERWRITE") == "1" else ""
        else:
            try:
                reply = input(
                    "Type 'yes' to OVERWRITE the existing enrollment, "
                    "anything else to cancel: "
                ).strip().lower()
            except EOFError:
                reply = ""
        if reply != "yes":
            print("[enroll] cancelled; existing enrollment kept.", flush=True)
            return

    print("[enroll] loading speaker encoder (first load takes a moment)...", flush=True)
    identifier = VoiceIdentifier()
    mic = _Mic()
    # Pin an explicit input device (PortAudio's default can be -1 on macOS
    # even with a working mic). See pick_input_device().
    sd.default.device = (pick_input_device(), sd.default.device[1])

    try:
        with sd.InputStream(
            samplerate=VOICE_SR,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_FRAMES,
            callback=mic.callback,
        ):
            telemetry.sensor("microphone", True)
            samples = capture_owner_samples(identifier, mic)
            if not samples:
                print("[enroll] aborted; no enrollment written.", flush=True)
                return

            mean = np.mean(np.stack(samples, axis=0), axis=0)
            enrolled_at = datetime.datetime.now().isoformat(timespec="seconds")
            store.save(mean, samples=len(samples), enrolled_at=enrolled_at)
            print(
                f"[enroll] wrote {OWNER_VOICE_PATH} ({len(samples)} samples).",
                flush=True,
            )
            log.info("owner enrolled with %d samples", len(samples),
                     extra={"event": "owner_enrolled"})

            verify_loop(identifier, mic, store)
            telemetry.emit("job_result", result="Voice enrollment and verification complete")
    finally:
        telemetry.sensor("microphone", False)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[enroll] interrupted.", file=sys.stderr)
