"""Download every model the apps need, so a session never waits on the network.

Run once after installing (``setup.command`` does this for you):

    uv run python -m robot.apps.download_models

Fetches the YuNet + SFace face models (~37 MB, into robot/state/models/), the
Whisper speech-to-text model (~140 MB for base.en, into ~/.cache/whisper) and
the MiniLM sensitivity classifier (~80 MB, into the HuggingFace cache). Models
that are already present are skipped. Silero VAD and Resemblyzer ship inside
their packages, so there is nothing to download for them.
"""

from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--whisper", default="base.en",
                    help="Whisper model to fetch (default base.en, the add_reminder default)")
    args = ap.parse_args()

    print("[models] face detection + recognition (YuNet, SFace)...", flush=True)
    from robot.perception.face_id import ensure_models
    ensure_models()

    print(f"[models] speech-to-text (Whisper {args.whisper})...", flush=True)
    import whisper
    whisper.load_model(args.whisper)

    print("[models] reminder sensitivity classifier (MiniLM)...", flush=True)
    from robot.core.sensitivity import MODEL_NAME
    from sentence_transformers import SentenceTransformer
    SentenceTransformer(MODEL_NAME)

    print("[models] all models ready.", flush=True)


if __name__ == "__main__":
    main()
