"""Hardware workers used by the local thesis presentation console.

Each worker runs in its own process so cancellation reliably releases camera,
microphone, BLE, and robot resources.  Progress is best-effort presentation
telemetry and never participates in a research decision.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

from robot.core import presentation_telemetry as telemetry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = PROJECT_ROOT / "robot" / "bench" / "eval_data"


def _next_path(folder: Path, prefix: str, suffix: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    used = sorted(folder.glob(f"{prefix}_*{suffix}"))
    return folder / f"{prefix}_{len(used) + 1:02d}{suffix}"


def device_camera(_args: argparse.Namespace) -> None:
    import cv2
    from robot.perception.camera_device import open_camera
    from robot.perception.face_id import FaceIdentifier, ensure_models

    yunet, sface = ensure_models()
    identifier = FaceIdentifier(yunet, sface)
    cap = open_camera()
    telemetry.sensor("camera", True)
    started = time.monotonic()
    try:
        while time.monotonic() - started < 8.0:
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            for face in identifier.detect_and_embed(frame):
                x, y, w, h = face.bbox
                cv2.rectangle(frame, (x, y), (x + w, y + h), (45, 210, 90), 2)
                cv2.putText(frame, f"face {face.confidence:.2f}", (x, max(22, y - 7)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.58, (45, 210, 90), 2)
            telemetry.frame(frame)
            telemetry.emit("job_progress", progress=(time.monotonic() - started) / 8.0,
                           detail="External robot-camera preview")
    finally:
        cap.release()
        telemetry.sensor("camera", False)
        telemetry.clear_frame()
    telemetry.emit("job_result", result="Camera opened and delivered frames successfully")


def device_microphone(_args: argparse.Namespace) -> None:
    import sounddevice as sd
    from robot.perception.audio_device import pick_input_device

    level = 0.0

    def callback(indata, _frames, _time_info, _status) -> None:
        nonlocal level
        level = float(np.sqrt(np.mean(indata[:, 0] ** 2))) if len(indata) else 0.0

    sd.default.device = (pick_input_device(), sd.default.device[1])
    telemetry.sensor("microphone", True)
    started = time.monotonic()
    try:
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                            blocksize=1600, callback=callback):
            while time.monotonic() - started < 5.0:
                elapsed = time.monotonic() - started
                telemetry.metric("microphone_level", level, progress=elapsed / 5.0)
                time.sleep(0.1)
    finally:
        telemetry.sensor("microphone", False)
    telemetry.emit("job_result", result="Microphone opened and produced a live signal")


def device_watch(_args: argparse.Namespace) -> None:
    from robot.core.policy import BangleClient

    watch = BangleClient()
    try:
        deadline = time.monotonic() + 8.0
        connected = bool(watch.start(timeout=8.0))
        while not connected and time.monotonic() < deadline:
            connected = bool(watch.is_connected())
            telemetry.emit("job_progress", progress=1.0 - max(0.0, deadline - time.monotonic()) / 8.0,
                           detail="Scanning for the Bangle.js watch")
            time.sleep(0.25)
        if not connected:
            raise RuntimeError("Bangle.js watch was not found within 8 seconds")
        telemetry.emit("job_result", result="Bangle.js watch connected successfully")
    finally:
        watch.close()


def device_ohbot(_args: argparse.Namespace) -> None:
    from robot.core import voice_reminder
    from robot.core import robot_io

    voice_reminder.init_ohbot()
    try:
        robot_io.deliver_reminder_spoken("Ohbot presentation test successful")
        telemetry.emit("job_result", result="Ohbot initialized, moved, and spoke successfully")
    finally:
        voice_reminder.close_ohbot()


def _stdin_actions(target: queue.Queue[dict]) -> None:
    for line in sys.stdin:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            target.put(payload)


def eval_face(args: argparse.Namespace) -> None:
    import cv2
    from robot.perception.camera_device import open_camera
    from robot.perception.face_id import FaceIdentifier, ensure_models

    label = "_negative" if args.negative else args.label
    condition = "bg" if args.negative else args.condition
    folder = EVAL_ROOT / "faces" / label
    actions: queue.Queue[dict] = queue.Queue()
    threading.Thread(target=_stdin_actions, args=(actions,), daemon=True).start()
    yunet, sface = ensure_models()
    identifier = FaceIdentifier(yunet, sface)
    cap = open_camera()
    telemetry.sensor("camera", True)
    taken = 0
    try:
        while taken < args.count:
            ok, raw = cap.read()
            if not ok or raw is None:
                continue
            annotated = raw.copy()
            faces = identifier.detect_and_embed(raw)
            for face in faces:
                x, y, w, h = face.bbox
                cv2.rectangle(annotated, (x, y), (x + w, y + h), (45, 210, 90), 2)
                cv2.putText(annotated, f"face {face.confidence:.2f}", (x, max(22, y - 7)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.58, (45, 210, 90), 2)
            cv2.putText(annotated, f"{label} [{condition}] {taken}/{args.count}",
                        (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            telemetry.frame(annotated)
            try:
                action = actions.get_nowait()
            except queue.Empty:
                action = {}
            if action.get("action") == "capture":
                path = _next_path(folder, condition, ".jpg")
                if not cv2.imwrite(str(path), raw):
                    raise RuntimeError(f"could not write {path}")
                taken += 1
                telemetry.emit("job_progress", progress=taken / args.count,
                               detail=f"Saved {taken}/{args.count}: {path.name}")
            time.sleep(0.01)
    finally:
        cap.release()
        telemetry.sensor("camera", False)
        telemetry.clear_frame()
    telemetry.emit("job_result", result=f"Saved {taken} labelled face image(s) in {folder}")


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    pcm = np.clip(np.squeeze(audio), -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def eval_voice(args: argparse.Namespace) -> None:
    import sounddevice as sd
    from robot.perception.audio_device import pick_input_device

    sample_rate = 16000
    folder = EVAL_ROOT / "voices" / args.label
    sd.default.device = (pick_input_device(), sd.default.device[1])
    telemetry.sensor("microphone", True)
    try:
        for clip in range(args.count):
            telemetry.emit("job_progress", progress=clip / args.count,
                           detail=f"Clip {clip + 1}/{args.count}: recording starts now")
            audio = sd.rec(int(args.seconds * sample_rate), samplerate=sample_rate,
                           channels=1, dtype="float32")
            started = time.monotonic()
            while time.monotonic() - started < args.seconds:
                elapsed = min(args.seconds, time.monotonic() - started)
                filled = min(len(audio), int(elapsed * sample_rate))
                level = float(np.sqrt(np.mean(audio[max(0, filled - sample_rate // 4):filled, 0] ** 2))) if filled else 0.0
                telemetry.metric("microphone_level", level,
                                 progress=(clip + elapsed / args.seconds) / args.count,
                                 remaining_s=max(0.0, args.seconds - elapsed))
                time.sleep(0.1)
            sd.wait()
            path = _next_path(folder, args.condition, ".wav")
            _write_wav(path, audio, sample_rate)
            telemetry.emit("job_progress", progress=(clip + 1) / args.count,
                           detail=f"Saved clip {clip + 1}/{args.count}: {path.name}")
    finally:
        telemetry.sensor("microphone", False)
    telemetry.emit("job_result", result=f"Saved {args.count} labelled voice clip(s) in {folder}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=(
        "device-camera", "device-microphone", "device-watch", "device-ohbot",
        "eval-face", "eval-voice",
    ))
    parser.add_argument("--label", default="")
    parser.add_argument("--condition", default="default")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--negative", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    functions = {
        "device-camera": device_camera,
        "device-microphone": device_microphone,
        "device-watch": device_watch,
        "device-ohbot": device_ohbot,
        "eval-face": eval_face,
        "eval-voice": eval_voice,
    }
    functions[args.kind](args)
    telemetry.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
