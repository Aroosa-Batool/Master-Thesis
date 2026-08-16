"""Record a small *labelled* eval set so the benchmarks can report accuracy and
robustness - not just latency.

Latency, memory and model size are intrinsic to each algorithm and need no data
(``bench_camera.py`` / ``bench_voice.py`` measure them on synthetic inputs). But
*detection rate*, *speaker/face verification EER*, and *robustness across
conditions* need real, labelled examples of the people the system must tell
apart. This tool captures them from the same webcam and microphone the demos
use, in a layout the benchmarks read directly:

    eval_data/
      faces/
        <person_label>/<condition>_<i>.jpg     e.g. alice/near_01.jpg
        _negative/<i>.jpg                       frames with NO face (FP rate)
      voices/
        <speaker_label>/<condition>_<i>.wav    e.g. alice/quiet_01.wav

Encode the capture *condition* in the filename prefix (near/far/backlit/side for
faces; quiet/noisy/far for voice). The accuracy code globs every file per label;
the prefixes let a later analysis stratify EER by condition for the robustness
story without re-recording.

Recommended minimum for a defensible number: >=3 people, >=2 conditions, >=4
shots/clips each. ~10 minutes of recording.

Examples
--------
    # 5 face shots of one person in the "near" condition (SPACE=capture, q=done)
    python robot/bench/capture_eval_set.py faces \
        --person alice --condition near --shots 5

    # 10 background frames with nobody in view
    python robot/bench/capture_eval_set.py faces --negative --shots 10

    # 3 voice clips of one speaker, 4 s each, in a noisy room
    python robot/bench/capture_eval_set.py voices \
        --speaker alice --condition noisy --clips 3 --seconds 4
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = _HERE / "eval_data"


def _next_index(folder: Path, prefix: str, suffix: str) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    existing = list(folder.glob(f"{prefix}*{suffix}"))
    return len(existing) + 1


def capture_faces(args) -> None:
    import cv2

    # Repo root on sys.path so this stays runnable as a plain script
    # (`python robot/bench/capture_eval_set.py ...`), not only as a module.
    sys.path.insert(0, str(_HERE.parent.parent))
    from robot.perception.camera_device import open_camera  # noqa: E402

    root = Path(args.root) / "faces"
    if args.negative:
        out = root / "_negative"
        label, condition = "_negative", "bg"
    else:
        if not args.person:
            sys.exit("faces mode needs --person LABEL (or --negative)")
        out = root / args.person
        label, condition = args.person, args.condition
    out.mkdir(parents=True, exist_ok=True)

    # Capture the eval set through the same camera the demos sense with -
    # accuracy measured on a different lens does not transfer.
    cap = open_camera(args.camera)
    print(f"Capturing {args.shots} shot(s) for '{label}' [{condition}].")
    print("  SPACE = capture frame, q = quit early.")
    if not args.negative:
        print("  Vary pose/expression slightly between shots; keep the labelled "
              "condition (lighting/distance) fixed.")

    taken = 0
    while taken < args.shots:
        ok, frame = cap.read()
        if not ok:
            continue
        hud = frame.copy()
        cv2.putText(hud, f"{label} [{condition}]  {taken}/{args.shots}  SPACE=shot q=quit",
                    (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("capture_eval_set - faces", hud)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            idx = _next_index(out, f"{condition}_", ".jpg")
            path = out / f"{condition}_{idx:02d}.jpg"
            cv2.imwrite(str(path), frame)
            taken += 1
            print(f"  saved {path}")
    cap.release()
    cv2.destroyAllWindows()
    print(f"Done: {taken} image(s) in {out}")


def capture_voices(args) -> None:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    if not args.speaker:
        sys.exit("voices mode needs --speaker LABEL")
    out = Path(args.root) / "voices" / args.speaker
    out.mkdir(parents=True, exist_ok=True)
    sr = 16000
    print(f"Recording {args.clips} clip(s) of {args.seconds}s for "
          f"'{args.speaker}' [{args.condition}].")
    print("  Speak naturally for each clip (a sentence or two).")

    for c in range(args.clips):
        input(f"  [{c+1}/{args.clips}] press Enter, then talk for {args.seconds}s ...")
        rec = sd.rec(int(args.seconds * sr), samplerate=sr, channels=1, dtype="float32")
        for remaining in range(int(args.seconds), 0, -1):
            print(f"    recording... {remaining}s ", end="\r", flush=True)
            time.sleep(1)
        sd.wait()
        idx = _next_index(out, f"{args.condition}_", ".wav")
        path = out / f"{args.condition}_{idx:02d}.wav"
        sf.write(str(path), np.squeeze(rec), sr)
        print(f"\n    saved {path}")
    print(f"Done: {args.clips} clip(s) in {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    f = sub.add_parser("faces", help="capture labelled face images from the webcam")
    f.add_argument("--person", help="person label (folder name)")
    f.add_argument("--negative", action="store_true",
                   help="capture background frames with no face (for FP rate)")
    f.add_argument("--condition", default="default",
                   help="filename prefix encoding the condition (near/far/backlit/...)")
    f.add_argument("--shots", type=int, default=5)
    f.add_argument("--camera", default=None,
                   help="camera index or name substring "
                        "(default: CAMERA_DEVICE, else the external camera)")
    f.add_argument("--root", default=str(DEFAULT_ROOT))
    f.set_defaults(func=capture_faces)

    v = sub.add_parser("voices", help="record labelled voice clips from the mic")
    v.add_argument("--speaker", help="speaker label (folder name)")
    v.add_argument("--condition", default="default",
                   help="filename prefix encoding the condition (quiet/noisy/far/...)")
    v.add_argument("--clips", type=int, default=3)
    v.add_argument("--seconds", type=float, default=4.0)
    v.add_argument("--root", default=str(DEFAULT_ROOT))
    v.set_defaults(func=capture_voices)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
