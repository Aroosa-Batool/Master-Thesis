"""Voice-modality algorithm comparison: VAD + speaker embedding.

Compares the demo's current voice stack against CPU-only, pip-installable
challengers, on the factors the thesis cares about: latency (the live loop must
keep up), real-time factor, peak memory, model size, and - when an eval set is
supplied - speaker-verification accuracy (EER / d-prime).

Stages
------
VAD (voice-activity detection, the "is anyone speaking?" gate):
  - rms     : the demo's current auto-calibrated energy gate  (voice_id.py)
  - webrtc  : Google WebRTC VAD (GMM-based, already a transitive dep)
  - silero  : Silero VAD (small CNN, torch)

SPEAKER embedding (the "owner vs bystander" re-ID):
  - resemblyzer : GE2E d-vector, 256-d  (the demo's current encoder)
  - ecapa       : SpeechBrain ECAPA-TDNN, 192-d  (current SOTA family)
  - xvector     : SpeechBrain x-vector TDNN, 512-d

Each candidate runs in its own subprocess (see _bench_util). Latency unit:
  - VAD    : classify ONE ~30 ms block (what the live callback does per block)
  - speaker: embed ONE ~6 s utterance (a representative single-utterance window)

Usage
-----
    python robot/bench/bench_voice.py            # latency + memory
    python robot/bench/bench_voice.py --data eval_data
    python robot/bench/bench_voice.py --repeats 50

With --data, expects eval_data/voices/<speaker_label>/*.wav (>=2 speakers,
>=2 clips each) and computes genuine/impostor cosine EER per speaker encoder.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))   # for the sibling _bench_util import

from _bench_util import (  # noqa: E402
    CandidateResult, TimingStats, cosine, equal_error_rate, file_size_mb,
    peak_rss_mb, render_markdown, render_table, run_worker, time_call, write_csv,
)

SR = 16000
BLOCK_MS = 30
BLOCK_N = int(SR * BLOCK_MS / 1000)        # 480 samples / 30 ms block
SILERO_BLOCK_N = 512                        # Silero v5 wants exactly 512 @ 16k
UTTER_S = 6.0                               # speaker-embedding utterance length
MODELS_DIR = _HERE / "models"
# Optional real-speech sample (the Ohbot TTS output, written to the repo root on
# each say()); if absent, a synthetic buffer is used instead - see load_sample().
SAMPLE_WAV = _HERE.parent.parent / "ohbotspeech.wav"

VAD_CANDIDATES = ["rms", "webrtc", "silero"]
SPEAKER_CANDIDATES = ["resemblyzer", "ecapa", "xvector"]
ALL = VAD_CANDIDATES + SPEAKER_CANDIDATES


# --- audio prep -------------------------------------------------------------

def load_sample_audio(target_s: float) -> np.ndarray:
    """A representative 16 kHz mono float32 buffer of length ~target_s.

    Built by tiling the demo's own ohbotspeech.wav (real speech) so latency is
    measured on speech, not noise. Falls back to band-limited noise if the wav
    is missing.
    """

    import soundfile as sf
    import librosa
    if SAMPLE_WAV.exists():
        wav, sr = sf.read(str(SAMPLE_WAV), dtype="float32")
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        if sr != SR:
            wav = librosa.resample(wav, orig_sr=sr, target_sr=SR)
    else:
        rng = np.random.default_rng(0)
        wav = rng.standard_normal(SR).astype("float32") * 0.1
    reps = int(np.ceil(target_s * SR / len(wav)))
    buf = np.tile(wav, reps)[: int(target_s * SR)]
    return buf.astype("float32")


# --- VAD candidate wrappers -------------------------------------------------
# Each returns (init_ms, classify_one_block_fn, model_paths, block_n, deploy).

def build_vad(name: str):
    if name == "rms":
        # A representative absolute voiced-RMS floor for an energy-gate VAD
        # baseline (the voice engine's live default gate is 0.02).
        t0 = time.perf_counter()
        gate = 0.012
        init_ms = (time.perf_counter() - t0) * 1000
        def classify(block: np.ndarray) -> bool:
            return float(np.sqrt(np.mean(block ** 2))) > gate
        return init_ms, classify, [], BLOCK_N, "builtin; zero deps"

    if name == "webrtc":
        import webrtcvad
        t0 = time.perf_counter()
        vad = webrtcvad.Vad(2)
        init_ms = (time.perf_counter() - t0) * 1000
        def classify(block: np.ndarray) -> bool:
            pcm = (np.clip(block, -1, 1) * 32767).astype("<i2").tobytes()
            return vad.is_speech(pcm, SR)
        return init_ms, classify, [], BLOCK_N, "pip; tiny (already a dep)"

    if name == "silero":
        import torch
        from silero_vad import load_silero_vad
        t0 = time.perf_counter()
        model = load_silero_vad()
        init_ms = (time.perf_counter() - t0) * 1000
        try:
            import silero_vad as _sv
            mp = [Path(_sv.__file__).resolve().parent]
        except Exception:
            mp = []
        def classify(block: np.ndarray) -> bool:
            with torch.no_grad():
                p = model(torch.from_numpy(block.astype("float32")), SR).item()
            return p >= 0.5
        return init_ms, classify, mp, SILERO_BLOCK_N, "pip; torch (already a dep)"

    raise ValueError(name)


# --- speaker candidate wrappers ---------------------------------------------
# Each returns (init_ms, embed_fn(wav_float32)->vec, model_paths, dim, deploy).

def build_speaker(name: str):
    if name == "resemblyzer":
        from resemblyzer import VoiceEncoder, preprocess_wav
        t0 = time.perf_counter()
        enc = VoiceEncoder(verbose=False)
        init_ms = (time.perf_counter() - t0) * 1000
        try:
            import resemblyzer as _rz
            mp = [Path(_rz.__file__).resolve().parent / "pretrained.pt"]
        except Exception:
            mp = []
        def embed(wav: np.ndarray) -> np.ndarray:
            w = preprocess_wav(wav, source_sr=SR)
            return np.asarray(enc.embed_utterance(w), dtype="float32")
        return init_ms, embed, mp, 256, "pip; weights bundled (no download)"

    if name in ("ecapa", "xvector"):
        import torch
        try:
            from speechbrain.inference.speaker import EncoderClassifier
        except Exception:
            from speechbrain.pretrained import EncoderClassifier  # older path
        source = ("speechbrain/spkrec-ecapa-voxceleb" if name == "ecapa"
                  else "speechbrain/spkrec-xvect-voxceleb")
        savedir = MODELS_DIR / name
        t0 = time.perf_counter()
        clf = EncoderClassifier.from_hparams(
            source=source, savedir=str(savedir), run_opts={"device": "cpu"}
        )
        init_ms = (time.perf_counter() - t0) * 1000
        dim = 192 if name == "ecapa" else 512
        def embed(wav: np.ndarray) -> np.ndarray:
            with torch.no_grad():
                t = torch.from_numpy(wav.astype("float32")).unsqueeze(0)
                out = clf.encode_batch(t)
            return out.squeeze().cpu().numpy().astype("float32")
        return init_ms, embed, [savedir], dim, "pip; downloads ~20-80MB from HF"

    raise ValueError(name)


# --- worker (one candidate, one subprocess) ---------------------------------

def run_one(name: str, repeats: int, data_dir: Path | None) -> CandidateResult:
    is_vad = name in VAD_CANDIDATES
    stage = "vad" if is_vad else "speaker"
    try:
        if is_vad:
            init_ms, classify, model_paths, block_n, deploy = build_vad(name)
            buf = load_sample_audio(UTTER_S)
            blocks = [buf[i:i + block_n] for i in range(0, len(buf) - block_n, block_n)]
            idx = {"i": 0}
            def call():
                b = blocks[idx["i"] % len(blocks)]
                idx["i"] += 1
                return classify(b)
            lat = time_call(call, repeats=repeats, warmup=5)
            block_audio_ms = block_n / SR * 1000.0
            rtf = lat.median_ms / block_audio_ms
            res = CandidateResult(
                name=name, stage=stage, ok=True, init_ms=init_ms,
                latency=lat.__dict__, rtf=rtf, peak_rss_mb=peak_rss_mb(),
                model_size_mb=file_size_mb(model_paths), deploy=deploy,
                extra={"block_ms": round(block_audio_ms, 1)},
            )
        else:
            init_ms, embed, model_paths, dim, deploy = build_speaker(name)
            buf = load_sample_audio(UTTER_S)
            lat = time_call(lambda: embed(buf), repeats=max(5, repeats // 4), warmup=2)
            rtf = lat.median_ms / (UTTER_S * 1000.0)
            res = CandidateResult(
                name=name, stage=stage, ok=True, init_ms=init_ms,
                latency=lat.__dict__, rtf=rtf, peak_rss_mb=peak_rss_mb(),
                model_size_mb=file_size_mb(model_paths), embedding_dim=dim,
                deploy=deploy,
            )
            if data_dir is not None:
                res.accuracy = speaker_accuracy(embed, data_dir)
        return res
    except Exception as exc:  # any candidate may fail to load on a given box
        import traceback
        return CandidateResult(name=name, stage=stage, ok=False,
                               error=f"{type(exc).__name__}: {exc}",
                               extra={"trace": traceback.format_exc()[-500:]})


def speaker_accuracy(embed, data_dir: Path) -> dict | None:
    """EER from genuine/impostor cosine pairs over eval_data/voices/<spk>/*.wav."""

    import soundfile as sf
    import librosa
    root = data_dir / "voices"
    if not root.is_dir():
        return None
    embs: dict[str, list[np.ndarray]] = {}
    for spk_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        vecs = []
        for wavf in sorted(spk_dir.glob("*.wav")):
            wav, sr = sf.read(str(wavf), dtype="float32")
            if wav.ndim > 1:
                wav = wav.mean(axis=1)
            if sr != SR:
                wav = librosa.resample(wav, orig_sr=sr, target_sr=SR)
            try:
                vecs.append(embed(wav.astype("float32")))
            except Exception:
                pass
        if len(vecs) >= 2:
            embs[spk_dir.name] = vecs
    if len(embs) < 2:
        return {"note": "need >=2 speakers with >=2 clips each"}
    genuine, impostor = [], []
    spk = list(embs)
    for s in spk:
        v = embs[s]
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                genuine.append(cosine(v[i], v[j]))
    for a in range(len(spk)):
        for b in range(a + 1, len(spk)):
            for va in embs[spk[a]]:
                for vb in embs[spk[b]]:
                    impostor.append(cosine(va, vb))
    return equal_error_rate(genuine, impostor)


# --- orchestrator -----------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker", metavar="NAME", help="(internal) run one candidate")
    ap.add_argument("--repeats", type=int, default=200,
                    help="timed reps (VAD blocks); speaker uses repeats//4")
    ap.add_argument("--data", type=str, default=None,
                    help="eval-set dir with voices/<speaker>/*.wav for EER")
    ap.add_argument("--only", type=str, default=None,
                    help="comma list to restrict candidates")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--out-dir", type=str, default=None,
                    help="write results here instead of bench/results")
    args = ap.parse_args()

    data_dir = Path(args.data).resolve() if args.data else None

    if args.worker:
        run_one(args.worker, args.repeats, data_dir).emit()
        return

    names = ALL if not args.only else [n.strip() for n in args.only.split(",")]
    extra = ["--repeats", str(args.repeats)]
    if data_dir:
        extra += ["--data", str(data_dir)]

    print(f"Voice benchmark - {len(names)} candidates, repeats={args.repeats}"
          + (f", eval={data_dir}" if data_dir else " (latency/memory only)"))
    results = []
    for n in names:
        print(f"  running {n} ...", flush=True)
        results.append(run_worker(_HERE / "bench_voice.py", n, extra, args.timeout))

    vad = [r for r in results if r.stage in ("vad", "?") and r.name in VAD_CANDIDATES]
    spk = [r for r in results if r.name in SPEAKER_CANDIDATES]
    print(render_table(vad, "VOICE - VAD (latency = 1 block ~30ms)"))
    print(render_table(spk, f"VOICE - speaker embedding (latency = 1 x {UTTER_S:.0f}s utterance)"))

    out_dir = Path(args.out_dir).resolve() if args.out_dir else _HERE / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, out_dir / "voice_results.csv")
    md = ["# Voice benchmark results", "",
          render_markdown(vad, f"VAD (latency = one ~{BLOCK_MS} ms block)"), "",
          render_markdown(spk, f"Speaker embedding (latency = one {UTTER_S:.0f} s utterance)")]
    for r in spk:
        if r.accuracy:
            md.append(f"\n- `{r.name}` accuracy: {r.accuracy}")
    (out_dir / "voice_results.md").write_text("\n".join(md))
    print(f"\nWrote {out_dir/'voice_results.csv'} and voice_results.md")


if __name__ == "__main__":
    main()
