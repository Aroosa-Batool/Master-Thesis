"""Voice modality of the Cache-Memory consent demo.

The audio twin of ``demo_cache_memory.py``. Everything downstream of
"is a bystander present?" is identical - the heart-rate gate, the watch
consent prompt, the Ohbot disclose/withhold behaviours, and the per-person
consent memory - but presence is sensed by **microphone** instead of
webcam:

  - The mic is monitored continuously. A cheap RMS gate (auto-calibrated to
    the room at startup) decides per 100 ms block whether someone is
    *speaking*, and a sliding window votes "voice present" vs "silence"
    (the audio analog of the camera's "face in view" vote).
  - When the owner's heart rate is elevated AND voice is present AND the
    watch is connected, a trial fires: the last few seconds of audio are
    run through Resemblyzer (``voice_id.py``). Each ~1.6 s voiced window
    becomes a speaker embedding; windows matching the enrolled owner are
    filtered out, and any *other* speaker is a bystander.
  - With a bystander present, the watch is asked for consent (or the cached
    answer is reused). Yes -> Ohbot suggests deep breaths; No -> "Hello
    there." The decision is remembered keyed by the bystander voice ID.

Owner presence in the room is still established by the watch's BLE link
(same as the camera demo), so the owner need not be the one talking. The
owner's *voice* is only used to subtract the owner from whoever is heard.

Identity stores are separate from the camera demo's (a voice ``person_001``
is a different namespace from a face ``person_001``):
  - owner voice print : ``owner_voice.json``      (enroll_owner_voice.py)
  - bystander gallery : ``voice_db.json``
  - consent memory    : ``consent_cache_voice.json``

Inherent limitation (documented, like the camera trade-offs): voice can
only notice a bystander who actually *speaks*. A silent third party is
invisible to this modality - that is what the camera demo is for.

Run:
    python interface/presence/demo_voice_cache_memory.py
Set NO_OHBOT=1 to run without the robot (decisions spoken via the OS voice).
Press 'q' in the status window to quit.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path

import cv2
import numpy as np

try:
    import sounddevice as sd
except (ModuleNotFoundError, OSError) as exc:
    raise SystemExit(
        "Missing dependency: install with `pip install sounddevice` "
        "(needs the PortAudio library; on Linux: `apt install libportaudio2`)."
    ) from exc

try:
    from ohbot import ohbot
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: install with `pip install ohbot`.") from exc

from face_db import FaceDB
from owner import OwnerStore
from policy import BangleClient, ConsentKey, ConsentStore
from voice_id import (
    VOICE_OWNER_THRESHOLD,
    VOICE_SAME_SPEAKER,
    VOICE_SR,
    VoiceIdentifier,
)


OHBOT_PORT_HINT = os.environ.get("OHBOT_PORT", "Pico")
# Set NO_OHBOT=1 to skip Ohbot init/use entirely - the consent flow on the
# watch still runs and disclose/withhold are spoken via the OS voice.
NO_OHBOT = os.environ.get("NO_OHBOT") == "1"

# macOS shim for the ohbot SDK (it shells out to `aplay`, absent on Darwin).
if sys.platform == "darwin":
    _silence_wav = os.path.join(os.path.dirname(ohbot.__file__), "Silence1.wav")

    def _say_speech_macos(addSilence):
        try:
            if addSilence:
                subprocess.run(["afplay", _silence_wav], timeout=5, check=False)
            subprocess.run(["afplay", "ohbotspeech.wav"], timeout=30, check=False)
        except subprocess.TimeoutExpired:
            print("[ohbot] afplay timed out; continuing.")
        except FileNotFoundError:
            print("[ohbot] afplay not found; skipping audio.")

    ohbot.saySpeech = _say_speech_macos


# Shared state for thread-safe Ohbot access and shutdown coordination.
# See demo_cache_memory.py for the full rationale.
shutting_down = threading.Event()
ohbot_lock = threading.Lock()


def _speak_fallback(text: str) -> None:
    """OS-native TTS fallback when NO_OHBOT=1. See demo_cache_memory.py."""

    if not text:
        return
    cmd: list[str] | None = None
    if sys.platform == "darwin":
        cmd = ["say", text]
    elif sys.platform.startswith("linux"):
        cmd = ["espeak", text]
    if cmd is None:
        print(f"[tts] no TTS available on {sys.platform}; would say: {text!r}")
        return
    try:
        subprocess.run(cmd, timeout=30, check=False)
    except FileNotFoundError:
        print(f"[tts] {cmd[0]} not found; would say: {text!r}")
    except subprocess.TimeoutExpired:
        print("[tts] TTS timed out.")


# --- audio / presence tuning -------------------------------------------------

BLOCK_FRAMES = int(VOICE_SR * 0.1)  # 100 ms mic callback blocks
OBSERVATION_WINDOW_S = 6.0          # presence sliding window
# Fraction of the window that must be "voiced" for a verdict. Lower than the
# camera's because speech is bursty (pauses between sentences).
#   >= VOICE_FRACTION_HIGH -> "VOICE_PRESENT"
#   <= VOICE_FRACTION_LOW  -> "SILENCE"
VOICE_FRACTION_HIGH = 0.25
VOICE_FRACTION_LOW = 0.05
TRIAL_AUDIO_S = 6.0                 # how much recent audio a trial embeds
# Absolute floor so a near-silent room still requires real speech even if
# ambient calibration measures ~0. The gate is max(this, calibrated).
RMS_GATE_FLOOR = 0.012

ELEVATED_BPM = 100
MIN_ELEVATED_DWELL_S = 5.0
HR_STALE_S = 10.0
CONSENT_TIMEOUT_S = 30.0

CONTENT_TYPE = "elevated_hr"
_HERE = Path(__file__).resolve().parent
CACHE_PATH = _HERE / "consent_cache_voice.json"
VOICE_DB_PATH = _HERE / "voice_db.json"
OWNER_VOICE_PATH = _HERE / "owner_voice.json"

PROMPT_MESSAGE = (
    "I have noticed that someone is present with you. "
    "Do you want me to send private reminders in front of them?"
)

DISCLOSE_TEMPLATE = (
    "I noticed your heart rate has been a bit elevated, around {bpm}. "
    "Would you like to take a few deep breaths together?"
)
WITHHOLD_LINE = "Hello there."


def behavior_disclose(bpm: int) -> None:
    """User consented - speak the wellbeing suggestion out loud."""

    msg = DISCLOSE_TEMPLATE.format(bpm=bpm)
    print(f">>> disclose ({bpm} bpm) -> {msg!r}")
    if NO_OHBOT:
        print("[ohbot] NO_OHBOT=1; speaking via OS TTS instead.")
        _speak_fallback(msg)
        return
    with ohbot_lock:
        if shutting_down.is_set():
            return
        try:
            ohbot.move(ohbot.HEADTURN, 5)
            ohbot.move(ohbot.HEADNOD, 5)
            ohbot.say(msg, untilDone=True, lipSync=True)
        except Exception as exc:
            print(f"[ohbot] disclose failed: {exc}")


def behavior_withhold() -> None:
    """User declined - Ohbot stays neutral."""

    print(f">>> withhold -> {WITHHOLD_LINE!r}")
    if NO_OHBOT:
        print("[ohbot] NO_OHBOT=1; speaking via OS TTS instead.")
        _speak_fallback(WITHHOLD_LINE)
        return
    with ohbot_lock:
        if shutting_down.is_set():
            return
        try:
            ohbot.move(ohbot.HEADTURN, 5)
            ohbot.say(WITHHOLD_LINE, untilDone=True, lipSync=True)
        except Exception as exc:
            print(f"[ohbot] withhold failed: {exc}")


class AudioMonitor:
    """Background mic capture feeding the presence window + trial buffer.

    The PortAudio callback runs on its own thread and only appends to two
    deques under a lock; the main loop reads ``presence()`` and, at trial
    time, ``snapshot_audio()``. This keeps the main loop (cv2 HUD + policy)
    free of blocking audio I/O, the same split the camera demo uses for the
    capture buffer vs. the trial worker.
    """

    def __init__(self, gate: float) -> None:
        self.gate = gate
        self._lock = threading.Lock()
        self._voiced: deque[tuple[float, bool]] = deque()
        self._raw: deque[tuple[float, np.ndarray]] = deque()
        self.cur_rms = 0.0

    def callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        x = indata[:, 0].copy()
        now = time.monotonic()
        rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
        voiced = rms > self.gate
        with self._lock:
            self.cur_rms = rms
            self._voiced.append((now, voiced))
            while self._voiced and self._voiced[0][0] < now - OBSERVATION_WINDOW_S:
                self._voiced.popleft()
            self._raw.append((now, x))
            while self._raw and self._raw[0][0] < now - TRIAL_AUDIO_S:
                self._raw.popleft()

    def presence(self) -> tuple[float, float, float]:
        """Return ``(window_duration_s, fraction_voiced, current_rms)``."""

        with self._lock:
            if not self._voiced:
                return 0.0, 0.0, self.cur_rms
            duration = self._voiced[-1][0] - self._voiced[0][0]
            fraction = sum(1 for _, v in self._voiced if v) / len(self._voiced)
            return duration, fraction, self.cur_rms

    def snapshot_audio(self) -> np.ndarray:
        """Concatenate the last ``TRIAL_AUDIO_S`` of raw audio for a trial."""

        with self._lock:
            if not self._raw:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate([b for _, b in self._raw])


def calibrate_gate(mic_rms_samples: list[float]) -> float:
    """Pick a voiced-RMS gate from a short ambient sample of the room."""

    if not mic_rms_samples:
        return RMS_GATE_FLOOR
    noise = float(np.median(mic_rms_samples))
    return max(RMS_GATE_FLOOR, noise * 3.0)


def identify_speakers_in_buffer(
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_store: OwnerStore,
    audio: np.ndarray,
) -> tuple[str, list[tuple[str, float, bool, bool]], bool]:
    """Audio twin of ``identify_people_in_frame``.

    Returns ``(bystander_id, per_window_info, owner_detected)``:
      - ``bystander_id``     : ':'-joined sorted set of non-owner speaker IDs
      - ``per_window_info``  : one ``(id, similarity, is_new, is_owner)`` per
                               voiced window, in time order
      - ``owner_detected``   : True iff some window matched the owner print

    Windows matching the owner voice-print (>= ``VOICE_OWNER_THRESHOLD``) are
    filtered out; every other window is identified against the bystander
    gallery, so the same person speaking across several windows collapses to
    one ID and the sorted set dedups them.
    """

    windows = voice_identifier.segment_and_embed(audio)
    if not windows:
        return "", [], False

    per_window: list[tuple[str, float, bool, bool]] = []
    bystanders: list[str] = []
    owner_detected = False
    for win in windows:
        is_owner, owner_sim = owner_store.matches(
            win.embedding, threshold=VOICE_OWNER_THRESHOLD
        )
        if is_owner:
            owner_detected = True
            per_window.append(("owner", owner_sim, False, True))
            continue
        pid, sim, is_new = voice_db.identify(win.embedding)
        per_window.append((pid, sim, is_new, False))
        bystanders.append(pid)

    bystander_id = ":".join(sorted(set(bystanders)))
    return bystander_id, per_window, owner_detected


def run_policy(
    watch: BangleClient,
    store: ConsentStore,
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_store: OwnerStore,
    bpm: int,
    audio: np.ndarray,
) -> str:
    """Run one Cache-Memory trial on an audio snapshot. Returns a HUD string."""

    bystander_id, per_window, owner_detected = identify_speakers_in_buffer(
        voice_identifier, voice_db, owner_store, audio
    )
    if not per_window:
        print("[policy] trial aborted (no usable speech in buffer).")
        return "aborted (no speech)"
    if owner_store.has_owner() and not owner_detected:
        sims = ", ".join(f"sim={sim:.2f}" for _, sim, _, _ in per_window)
        print(
            f"[policy] owner not heard in buffer (BLE confirms in-room). "
            f"Treating all voiced windows as bystanders. "
            f"owner-sim per window = [{sims}], "
            f"threshold = {VOICE_OWNER_THRESHOLD:.2f}."
        )
    if not bystander_id:
        print("[policy] trial aborted (only the owner was heard; no bystanders).")
        return "aborted (only owner)"

    def _fmt(entry):
        pid, sim, is_new, is_owner = entry
        tag = "[OWNER] " if is_owner else ("*" if is_new else "")
        return f"{tag}{pid} (sim={sim:.2f})"

    pretty = ", ".join(_fmt(e) for e in per_window)
    print(f"[policy] voices in buffer: {pretty}  -> bystander key '{bystander_id}'")
    print("  (* = newly minted ID; [OWNER] = enrolled watch-wearer)")

    key = ConsentKey(bystander_id=bystander_id, content_type=CONTENT_TYPE)
    cached = store.get(key)
    if cached is True:
        print(f"[policy] cache hit for {bystander_id}: YES -> disclose without prompt")
        behavior_disclose(bpm)
        return f"cache-hit YES ({bystander_id})"
    if cached is False:
        print(f"[policy] cache hit for {bystander_id}: NO -> withhold without prompt")
        behavior_withhold()
        return f"cache-hit NO ({bystander_id})"

    print(f"[policy] cache miss for {bystander_id}: asking the watch...")
    answer = watch.ask_consent(PROMPT_MESSAGE, timeout=CONSENT_TIMEOUT_S)
    if answer is None:
        print("[policy] no answer from watch; withholding (safe default).")
        behavior_withhold()
        return f"no-reply -> withhold ({bystander_id})"

    store.put(key, answer)
    if answer:
        print(f"[policy] watch -> YES; stored for {bystander_id} and disclosing.")
        behavior_disclose(bpm)
        return f"asked YES ({bystander_id})"
    print(f"[policy] watch -> NO; stored for {bystander_id} and withholding.")
    behavior_withhold()
    return f"asked NO ({bystander_id})"


def _make_hud(lines: list[str], rms: float, gate: float):
    """Render the level meter + 3 status lines, mirroring the camera HUD."""

    img = np.zeros((180, 720, 3), dtype=np.uint8)
    level = min(1.0, rms / max(gate * 4.0, 1e-4))
    cv2.rectangle(img, (20, 16), (700, 40), (70, 70, 70), 1)
    cv2.rectangle(img, (20, 16), (20 + int(680 * level), 40), (0, 220, 0), -1)
    for i, line in enumerate(lines):
        cv2.putText(
            img, line, (20, 78 + i * 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1,
        )
    return img


def main() -> None:
    if NO_OHBOT:
        print("[startup] NO_OHBOT=1 set; skipping Ohbot.", flush=True)
    else:
        print(
            f"[startup] initialising Ohbot (port hint='{OHBOT_PORT_HINT}'). "
            "If this hangs, the robot is likely not plugged in - rerun with "
            "NO_OHBOT=1 to skip it.",
            flush=True,
        )
        with ohbot_lock:
            ohbot.setSynthesizer("espeak")
            ohbot.init(OHBOT_PORT_HINT)
            ohbot.reset()
            ohbot.setVoice("-v en-gb+f3")
        print("[startup] Ohbot ready.", flush=True)

    store = ConsentStore(CACHE_PATH)
    print(
        f"[cache] loaded {len(store.dump())} bystander record(s) from {CACHE_PATH}",
        flush=True,
    )

    print("[startup] loading speaker encoder (first load takes a moment)...", flush=True)
    voice_identifier = VoiceIdentifier()
    voice_db = FaceDB(VOICE_DB_PATH, match_threshold=VOICE_SAME_SPEAKER)
    print(
        f"[voice] gallery has {voice_db.count()} known speaker(s); "
        f"new voices auto-IDed at cosine sim < {VOICE_SAME_SPEAKER:.3f}.",
        flush=True,
    )

    owner_store = OwnerStore(OWNER_VOICE_PATH)
    if not owner_store.has_owner():
        raise SystemExit(
            "[startup] No voice owner enrolled. Run this first:\n"
            "    python interface/presence/enroll_owner_voice.py\n"
            "Then re-run this demo. The owner's voice print lets the system "
            "subtract the watch-wearer from whoever it hears, so the consent "
            "cache is keyed by bystander voices only."
        )
    print(
        f"[owner] voice enrolled at {owner_store.enrolled_at()} "
        f"({owner_store.samples()} sample(s)).",
        flush=True,
    )

    # Ambient calibration: sample the room for ~1.5 s to set the voiced gate.
    print("[startup] calibrating mic - stay quiet for ~1.5s...", flush=True)
    cal_rms: list[float] = []

    def _cal_cb(indata, frames, time_info, status):  # noqa: ARG001
        x = indata[:, 0]
        if len(x):
            cal_rms.append(float(np.sqrt(np.mean(x ** 2))))

    with sd.InputStream(
        samplerate=VOICE_SR, channels=1, dtype="float32",
        blocksize=BLOCK_FRAMES, callback=_cal_cb,
    ):
        time.sleep(1.5)
    gate = calibrate_gate(cal_rms)
    print(f"[startup] voiced-RMS gate set to {gate:.4f}.", flush=True)

    print("[startup] starting watch BLE link...", flush=True)
    watch = BangleClient()
    if not watch.start():
        print("[ble] proceeding without watch link; cache-miss trials will withhold.")

    monitor = AudioMonitor(gate)

    print(
        f"Voice Cache-Memory demo running. Observing for ~{int(OBSERVATION_WINDOW_S)}s "
        "before reacting. Press 'q' in the status window to quit."
    )

    armed_for_trial = True
    ABORT_RE_ARM_S = 3.0
    last_abort_re_arm_at = 0.0
    RETRYABLE_ABORT_STATUSES = {"aborted (no speech)"}

    trial_lock = threading.Lock()
    trial_state: dict[str, object] = {"in_trial": False, "last_status": "(none)"}

    def fire_trial_async(bpm_snapshot: int, audio_snapshot: np.ndarray) -> bool:
        def worker() -> None:
            try:
                status = run_policy(
                    watch, store, voice_identifier, voice_db, owner_store,
                    bpm_snapshot, audio_snapshot,
                )
            except Exception as exc:
                traceback.print_exc()
                status = f"error: {exc}"
            finally:
                with trial_lock:
                    trial_state["last_status"] = status
                    trial_state["in_trial"] = False

        with trial_lock:
            if trial_state["in_trial"]:
                return False
            trial_state["in_trial"] = True
            trial_state["last_status"] = "identifying voices..."
            threading.Thread(target=worker, daemon=True, name="trial-worker").start()
            return True

    try:
        with sd.InputStream(
            samplerate=VOICE_SR, channels=1, dtype="float32",
            blocksize=BLOCK_FRAMES, callback=monitor.callback,
        ):
            while True:
                now = time.monotonic()
                duration, fraction_voiced, cur_rms = monitor.presence()
                have_full_window = duration >= OBSERVATION_WINDOW_S * 0.9

                bpm, last_hr_ts = watch.latest_bpm()
                fresh = (now - last_hr_ts) < HR_STALE_S
                # elevated_since is tracked across iterations via closure-free
                # locals below; recompute the stable flag each tick.
                # (kept structurally identical to the camera demo)
                elevated_stable = _update_elevated(now, bpm, fresh)
                # TEST-ONLY: forces trials to fire without a real elevated
                # reading (mirrors the knob used in the camera demos).
                elevated_stable = True

                presence_verdict: str | None = None
                if have_full_window:
                    if fraction_voiced >= VOICE_FRACTION_HIGH:
                        presence_verdict = "VOICE_PRESENT"
                    elif fraction_voiced <= VOICE_FRACTION_LOW:
                        presence_verdict = "SILENCE"

                ble_up = watch.is_connected()
                # Re-arm on any gap: silence, HR settles, or the watch drops -
                # each marks the boundary of a new encounter.
                if (
                    presence_verdict == "SILENCE"
                    or not elevated_stable
                    or not ble_up
                ):
                    armed_for_trial = True

                with trial_lock:
                    in_trial = bool(trial_state["in_trial"])
                    last_trial_status = str(trial_state["last_status"])

                if (
                    not in_trial
                    and not armed_for_trial
                    and last_trial_status in RETRYABLE_ABORT_STATUSES
                    and (now - last_abort_re_arm_at) >= ABORT_RE_ARM_S
                ):
                    armed_for_trial = True
                    last_abort_re_arm_at = now
                    print(
                        f"[trial] re-arming after abort ('{last_trial_status}')",
                        flush=True,
                    )

                should_trial = (
                    armed_for_trial
                    and not in_trial
                    and have_full_window
                    and presence_verdict == "VOICE_PRESENT"
                    and elevated_stable
                    and ble_up
                )
                if should_trial:
                    armed_for_trial = False
                    print(
                        "[trial] starting on worker thread. Speaker IDs will be "
                        "auto-assigned from the recent audio; the status window "
                        "stays open and quittable with 'q'.",
                        flush=True,
                    )
                    fire_trial_async(bpm, monitor.snapshot_audio())

                raw_label = "voice" if cur_rms > gate else "quiet"
                line1 = (
                    f"raw: {raw_label}  rms={cur_rms:.3f}/{gate:.3f}  "
                    f"bpm={bpm if fresh else '--'}  "
                    f"watch={'OK' if ble_up else 'OFFLINE'}"
                )
                if have_full_window:
                    line2 = (
                        f"window {duration:.0f}s  {fraction_voiced:.0%} voiced  "
                        f"verdict={presence_verdict or 'ambiguous'}  "
                        f"elevated={elevated_stable}"
                    )
                else:
                    line2 = f"observing... {duration:.0f}/{int(OBSERVATION_WINDOW_S)}s"
                trial_tag = "[TRIAL IN PROGRESS] " if in_trial else ""
                line3 = f"{trial_tag}last trial: {last_trial_status}"

                cv2.imshow(
                    "Voice Cache-Memory demo",
                    _make_hud([line1, line2, line3], cur_rms, gate),
                )
                if cv2.waitKey(30) & 0xFF == ord("q"):
                    shutting_down.set()
                    break
    finally:
        shutting_down.set()
        cv2.destroyAllWindows()
        watch.close()
        if not NO_OHBOT:
            acquired = ohbot_lock.acquire(timeout=10.0)
            if not acquired:
                print(
                    "[shutdown] ohbot_lock busy after 10s; skipping reset/close. "
                    "The serial port will be released by process exit."
                )
            try:
                if acquired:
                    try:
                        ohbot.reset()
                    finally:
                        ohbot.close()
            finally:
                if acquired:
                    ohbot_lock.release()


# Heart-rate "elevated and sustained" gate, factored out so the main loop
# stays readable. Uses a module-level cell instead of a nonlocal because the
# main loop is not a closure over it.
_elevated_since: float | None = None


def _update_elevated(now: float, bpm: int, fresh: bool) -> bool:
    global _elevated_since
    if fresh and bpm > ELEVATED_BPM:
        if _elevated_since is None:
            _elevated_since = now
    else:
        _elevated_since = None
    return (
        _elevated_since is not None
        and (now - _elevated_since) >= MIN_ELEVATED_DWELL_S
    )


if __name__ == "__main__":
    main()
