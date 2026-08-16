"""Measure speaker-embedding separability - calibrate the voice re-ID threshold.

The bystander gallery (``voice_db.json``) calls two utterances the SAME person
when their Resemblyzer d-vector cosine similarity is ``>= VOICE_SAME_SPEAKER``
(``robot/perception/voice_id.py``). If DIFFERENT people score above that bar,
new bystanders get merged into an existing id ("it always matches someone").

This tool prints the pairwise cosine matrix for several clips so you can SEE the
same-vs-different gap on YOUR microphone/room and pick a threshold - instead of
guessing. It embeds each clip with the exact pipeline embedder
(``VoiceIdentifier.embed`` -> Resemblyzer, VAD-trimmed, whole-utterance).

Two modes
---------
FILES (isolates the EMBEDDER - no microphone, no loudspeaker):
    python -m robot.bench.voice_similarity --files alice1.wav alice2.wav bob.mp3
    python -m robot.bench.voice_similarity --files a1.wav a2.wav b.wav \
        --labels alice alice bob
  Embeds the audio files DIRECTLY. This is the clean test: if different speakers
  still score high here, it is the embedder/threshold. If they separate here but
  NOT when recorded live, the loudspeaker + room + mic CHANNEL is inflating the
  similarity - the usual cause when you play YouTube voices through speakers into
  the mic. Download a couple of YouTube clips (e.g. with yt-dlp) and point this
  at them, or use any two-per-speaker voice files you have.

RECORD (tests the FULL live channel: mic + room + whatever is playing):
    python -m robot.bench.voice_similarity --record 3 --seconds 6
    python -m robot.bench.voice_similarity --record 4 --seconds 6 \
        --labels youtubeA youtubeA youtubeB youtubeB
  Records N clips (press Enter before each), embeds them, prints the matrix.

With ``--labels`` it also reports the worst DIFFERENT-speaker pair and the worst
SAME-speaker pair and suggests a threshold between them (if one exists).

Run from the repo root so ``robot`` is importable.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from robot.perception.voice_id import (
    VoiceIdentifier,
    VOICE_SAME_SPEAKER,
    VOICE_SR,
    load_voice_mean,
    center_embedding,
)
from robot.paths import VOICE_MEAN_PATH

try:
    import sounddevice as sd
except (ModuleNotFoundError, OSError):
    sd = None  # only needed for --record


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 1e-12 else 0.0


def _load_file(path: str) -> tuple[np.ndarray, int]:
    """Load any audio file (wav/mp3/m4a/...) as float32 mono + its sample rate."""

    try:
        import librosa  # pulled in by resemblyzer
    except ModuleNotFoundError as exc:
        raise SystemExit("Need librosa to read files: pip install librosa.") from exc
    audio, sr = librosa.load(path, sr=None, mono=True)
    return np.asarray(audio, dtype=np.float32), int(sr)


def _record_clip(seconds: float, sr: int) -> np.ndarray:
    if sd is None:
        raise SystemExit("sounddevice not available; --record needs a working mic.")
    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    return audio[:, 0].copy()


def _collect_embeddings(args, identifier: VoiceIdentifier):
    """Return (labels, embeddings, names) for the chosen mode; drops empties."""

    names: list[str] = []
    raw: list[tuple[str, np.ndarray, int]] = []   # (name, audio, sr)
    if args.files:
        for path in args.files:
            audio, sr = _load_file(path)
            raw.append((path, audio, sr))
    else:
        print(f"[record] {args.record} clips, {args.seconds:.0f}s each at {VOICE_SR} Hz.")
        for i in range(args.record):
            try:
                input(f"  -> ready clip #{i + 1}? play the voice, then press Enter... ")
            except EOFError:
                pass
            print("     recording...", flush=True)
            audio = _record_clip(args.seconds, VOICE_SR)
            print("     done.", flush=True)
            raw.append((f"clip{i + 1}", audio, VOICE_SR))

    embeddings: list[np.ndarray] = []
    for name, audio, sr in raw:
        emb = identifier.embed(audio, source_sr=sr)
        if emb is None:
            print(f"  ! {name}: too little voiced audio to embed - skipped.")
            continue
        embeddings.append(emb)
        names.append(name)

    labels = args.labels if args.labels else names
    if args.labels and len(labels) != len(raw):
        raise SystemExit(
            f"--labels count ({len(labels)}) must match the number of clips ({len(raw)})."
        )
    # If some clips were skipped, keep labels aligned to the kept ones.
    if args.labels:
        labels = [args.labels[i] for i, (name, *_1) in enumerate(raw)
                  if name in names][:len(names)]
    return labels, embeddings, names


def _print_matrix(names, labels, embeddings) -> None:
    n = len(embeddings)
    if n < 2:
        raise SystemExit("Need at least 2 embeddable clips to compare.")
    width = max(len(x) for x in names) + 2
    print("\nPairwise cosine similarity (>= threshold marked with *, which the "
          "gallery would call the SAME person):\n")
    header = " " * width + "".join(f"{i + 1:>7}" for i in range(n))
    print(header)
    for i in range(n):
        row = f"{names[i]:<{width}}"
        for j in range(n):
            if j == i:
                row += "   -   "
            else:
                sim = _cosine(embeddings[i], embeddings[j])
                mark = "*" if sim >= VOICE_SAME_SPEAKER else " "
                row += f"{sim:6.2f}{mark}"
        print(row)
    print(f"\nCurrent VOICE_SAME_SPEAKER threshold = {VOICE_SAME_SPEAKER:.2f}")


def _report_gap(labels, embeddings) -> None:
    """If labels are given, contrast same-speaker vs different-speaker pairs."""

    same: list[float] = []
    diff: list[float] = []
    n = len(embeddings)
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine(embeddings[i], embeddings[j])
            (same if labels[i] == labels[j] else diff).append(sim)

    print("\n--- separability (from --labels) ---")
    if same:
        print(f"  SAME-speaker cosine : min {min(same):.2f}, mean "
              f"{sum(same) / len(same):.2f}, max {max(same):.2f}  ({len(same)} pairs)")
    else:
        print("  SAME-speaker cosine : (no same-speaker pairs given)")
    if diff:
        print(f"  DIFF-speaker cosine : min {min(diff):.2f}, mean "
              f"{sum(diff) / len(diff):.2f}, max {max(diff):.2f}  ({len(diff)} pairs)")
    else:
        print("  DIFF-speaker cosine : (no different-speaker pairs given)")

    if same and diff:
        worst_same, worst_diff = min(same), max(diff)
        gap = worst_same - worst_diff
        print(f"\n  Worst same-speaker pair = {worst_same:.2f}; "
              f"worst different-speaker pair = {worst_diff:.2f}.")
        if gap > 0:
            suggested = round((worst_same + worst_diff) / 2, 2)
            print(f"  They SEPARATE (gap {gap:+.2f}). A threshold of ~{suggested:.2f} "
                  f"would keep same-speaker together and different speakers apart.")
            print(f"  -> set VOICE_SAME_SPEAKER = {suggested:.2f} in "
                  "robot/perception/voice_id.py")
        else:
            print(f"  They OVERLAP (gap {gap:+.2f}): no single cosine threshold can "
                  "separate them on this audio.\n"
                  "  This is the tell-tale sign of channel inflation - most likely "
                  "because the voices were played through speakers into the mic.\n"
                  "  Try FILE mode (--files) on the raw audio to confirm, and/or test "
                  "with real people speaking live, or upgrade the embedder (ECAPA).")


def _save_mean(embeddings, names) -> None:
    """Average the clips' RAW embeddings into the cohort mean -> voice_mean.json."""

    if len(embeddings) < 2:
        raise SystemExit("Need >= 2 embeddable clips to build a mean "
                         "(>= 5 DIFFERENT voices is ideal).")
    if len(embeddings) < 5:
        print(f"[warn] only {len(embeddings)} clips - a cohort mean works best from "
              ">= 5 DIFFERENT voices (more diversity = better centering).")
    mean = np.mean(np.stack(embeddings, axis=0), axis=0).astype(np.float32)
    VOICE_MEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOICE_MEAN_PATH.write_text(json.dumps(
        {"mean": [float(x) for x in mean], "n_clips": len(embeddings),
         "sources": names}, indent=2))
    print(f"\n[saved] cohort mean of {len(embeddings)} clips -> {VOICE_MEAN_PATH}")
    print("Centering is now ENABLED for the voice pipeline. Stored voice prints must "
          "be centered too, so next:")
    print("   1) delete the old gallery:  rm robot/state/voice_db.json")
    print("   2) re-enroll the owner:     python -m robot.apps.enroll_voice")
    print("Then re-run this tool to confirm the same-vs-different gap widened, and "
          "re-tune VOICE_SAME_SPEAKER in robot/perception/voice_id.py to sit in it.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Measure speaker-embedding cosine similarity to calibrate the "
                    "voice re-ID threshold, and build the centering mean."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--files", nargs="+", metavar="PATH",
                     help="audio files to embed directly (no mic) - the clean test")
    src.add_argument("--record", type=int, metavar="N",
                     help="record N clips from the mic instead")
    ap.add_argument("--seconds", type=float, default=6.0,
                    help="seconds per recorded clip (record mode; default 6)")
    ap.add_argument("--labels", nargs="+", metavar="LABEL",
                    help="one label per clip (e.g. 'alice alice bob'); same label = "
                         "same speaker, used to report the same-vs-different gap")
    ap.add_argument("--save-mean", action="store_true",
                    help="average the clips into the cohort mean (voice_mean.json) "
                         "to ENABLE d-vector centering; use >= 5 DIFFERENT voices")
    args = ap.parse_args()

    print("[startup] loading the voice encoder (Resemblyzer GE2E)...", flush=True)
    identifier = VoiceIdentifier(center=False)   # measure RAW separability
    labels, embeddings, names = _collect_embeddings(args, identifier)

    if args.save_mean:
        _save_mean(embeddings, names)
        return

    print("\n===== RAW d-vectors (pipeline default when un-calibrated) =====")
    _print_matrix(names, labels, embeddings)
    if args.labels:
        _report_gap(labels, embeddings)

    mean = load_voice_mean()
    if mean is not None:
        centered = [center_embedding(e, mean) for e in embeddings]
        print(f"\n===== CENTERED d-vectors (using {VOICE_MEAN_PATH.name}) =====")
        _print_matrix(names, labels, centered)
        if args.labels:
            _report_gap(labels, centered)
    else:
        print(f"\n[hint] No {VOICE_MEAN_PATH.name} yet - centering is OFF. Build one "
              "from several DIFFERENT voices to enable it:\n"
              "   python -m robot.bench.voice_similarity --files v1.wav v2.wav "
              "v3.wav v4.wav v5.wav --save-mean")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[voice-sim] interrupted.", file=sys.stderr)
