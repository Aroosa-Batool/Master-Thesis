"""Shared benchmark utilities for the camera/voice algorithm comparison.

Design notes
------------
Each candidate algorithm is measured in its **own subprocess** (the bench
scripts re-exec themselves in ``--worker NAME`` mode). This buys three things
that matter for a defensible thesis benchmark:

  1. A clean *peak-RSS* number per candidate. ``resource.getrusage`` reports the
     high-water mark for the whole process, so it is only meaningful if exactly
     one model lives in that process. One worker == one model.
  2. Crash isolation. A flaky native lib (a segfaulting ONNX op, a torch abort)
     takes down only its own worker; the orchestrator records it as FAILED and
     keeps going.
  3. No cross-contamination. One candidate's loaded weights cannot warm caches
     or steal memory from the next, so latency/memory are comparable.

The worker emits exactly one machine-readable line prefixed with ``@@RESULT@@``
(everything else it prints - model-download chatter, torch warnings - is
ignored by the parent). The parent collects those lines and renders tables.

Timing uses ``time.perf_counter`` with a warmup phase (first calls pay lazy
init / cache-fill costs that do not reflect steady-state latency). We report the
*median* and *p95* rather than the mean because per-call latency is right-skewed
(occasional GC / scheduler stalls) and the median is what the live loop feels.
"""

from __future__ import annotations

import csv
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

RESULT_PREFIX = "@@RESULT@@ "


# --- memory -----------------------------------------------------------------

def peak_rss_mb() -> float:
    """Peak resident set size of *this* process, in MB.

    ``ru_maxrss`` is bytes on macOS/BSD but kibibytes on Linux - normalise.
    """

    import resource

    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return raw / (1024 * 1024)
    return raw / 1024  # Linux: KiB -> MB


def file_size_mb(paths: list[Path]) -> float:
    """Total on-disk size of the given model files/dirs, in MB (0 if none)."""

    total = 0
    for p in paths:
        if p is None:
            continue
        p = Path(p)
        if p.is_dir():
            total += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        elif p.is_file():
            total += p.stat().st_size
    return total / (1024 * 1024)


# --- timing -----------------------------------------------------------------

@dataclass
class TimingStats:
    median_ms: float
    p95_ms: float
    mean_ms: float
    min_ms: float
    std_ms: float
    n: int

    @classmethod
    def from_samples(cls, samples_ms: list[float]) -> "TimingStats":
        s = sorted(samples_ms)
        p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
        return cls(
            median_ms=statistics.median(s),
            p95_ms=p95,
            mean_ms=statistics.fmean(s),
            min_ms=s[0],
            std_ms=statistics.pstdev(s) if len(s) > 1 else 0.0,
            n=len(s),
        )


def time_call(fn: Callable[[], object], repeats: int, warmup: int = 3) -> TimingStats:
    """Time ``fn()`` ``repeats`` times after ``warmup`` untimed calls."""

    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return TimingStats.from_samples(samples)


# --- worker result schema ---------------------------------------------------

@dataclass
class CandidateResult:
    """One row of the comparison table - the worker's full report."""

    name: str
    stage: str                       # e.g. "detect" / "recognize" / "vad" / "speaker"
    ok: bool
    init_ms: float = 0.0             # time to construct/load the model
    latency: dict | None = None      # TimingStats as dict, or None on failure
    rtf: float | None = None         # real-time factor (proc_time / audio_dur), audio only
    peak_rss_mb: float = 0.0
    model_size_mb: float = 0.0
    embedding_dim: int | None = None
    deploy: str = ""                 # short deployability note
    accuracy: dict | None = None     # filled only when an eval set is supplied
    error: str = ""
    extra: dict = field(default_factory=dict)

    def emit(self) -> None:
        sys.stdout.write(RESULT_PREFIX + json.dumps(asdict(self)) + "\n")
        sys.stdout.flush()


# --- orchestration ----------------------------------------------------------

def run_worker(script: Path, name: str, extra_args: list[str], timeout: float) -> CandidateResult:
    """Spawn ``python script --worker name [extra_args]`` and parse its result."""

    cmd = [sys.executable, str(script), "--worker", name, *extra_args]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return CandidateResult(name=name, stage="?", ok=False,
                               error=f"timeout after {timeout:.0f}s")
    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_PREFIX):
            data = json.loads(line[len(RESULT_PREFIX):])
            return CandidateResult(**data)
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    msg = tail[-1] if tail else f"exit {proc.returncode}, no result line"
    return CandidateResult(name=name, stage="?", ok=False, error=msg[:200])


# --- rendering --------------------------------------------------------------

def _fmt(v, nd=1):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def render_table(results: list[CandidateResult], title: str) -> str:
    """Return a plain-text table summarising the candidate results."""

    headers = ["candidate", "ok", "init_ms", "lat_med_ms", "lat_p95_ms",
               "fps", "rtf", "rss_mb", "model_mb", "dim", "deploy"]
    rows = []
    for r in results:
        lat = r.latency or {}
        med = lat.get("median_ms")
        fps = (1000.0 / med) if med else None
        rows.append([
            r.name,
            "yes" if r.ok else "FAIL",
            _fmt(r.init_ms, 0),
            _fmt(med, 2),
            _fmt(lat.get("p95_ms"), 2),
            _fmt(fps, 0),
            _fmt(r.rtf, 3) if r.rtf is not None else "-",
            _fmt(r.peak_rss_mb, 0),
            _fmt(r.model_size_mb, 1),
            _fmt(r.embedding_dim, 0) if r.embedding_dim else "-",
            (r.deploy or (r.error if not r.ok else ""))[:34],
        ])
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) if rows
              else len(headers[i]) for i in range(len(headers))]
    def line(cells):
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))
    out = [f"\n=== {title} ===", line(headers), line(["-" * w for w in widths])]
    out += [line(r) for r in rows]
    return "\n".join(out)


def render_markdown(results: list[CandidateResult], title: str) -> str:
    headers = ["Candidate", "OK", "Init ms", "Latency median ms", "Latency p95 ms",
               "FPS", "RTF", "Peak RSS MB", "Model MB", "Dim", "Notes"]
    lines = [f"### {title}", "", "| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in results:
        lat = r.latency or {}
        med = lat.get("median_ms")
        fps = (1000.0 / med) if med else None
        cells = [
            f"`{r.name}`", "yes" if r.ok else "**FAIL**", _fmt(r.init_ms, 0),
            _fmt(med, 2), _fmt(lat.get("p95_ms"), 2), _fmt(fps, 0),
            _fmt(r.rtf, 3) if r.rtf is not None else "-",
            _fmt(r.peak_rss_mb, 0), _fmt(r.model_size_mb, 1),
            _fmt(r.embedding_dim, 0) if r.embedding_dim else "-",
            (r.deploy or (r.error if not r.ok else "")),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_csv(results: list[CandidateResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "stage", "ok", "init_ms", "lat_median_ms", "lat_p95_ms",
                    "lat_mean_ms", "fps", "rtf", "peak_rss_mb", "model_size_mb",
                    "embedding_dim", "deploy", "accuracy", "error"])
        for r in results:
            lat = r.latency or {}
            med = lat.get("median_ms")
            w.writerow([
                r.name, r.stage, r.ok, f"{r.init_ms:.2f}",
                _fmt(med, 3), _fmt(lat.get("p95_ms"), 3), _fmt(lat.get("mean_ms"), 3),
                f"{1000.0/med:.2f}" if med else "", _fmt(r.rtf, 4) if r.rtf else "",
                f"{r.peak_rss_mb:.1f}", f"{r.model_size_mb:.2f}",
                r.embedding_dim or "", r.deploy,
                json.dumps(r.accuracy) if r.accuracy else "", r.error,
            ])


# --- accuracy helpers (used only when an eval set is supplied) ---------------

def cosine(a, b) -> float:
    import numpy as np
    a = np.asarray(a, dtype="float32").ravel()
    b = np.asarray(b, dtype="float32").ravel()
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / d) if d > 1e-12 else 0.0


def equal_error_rate(genuine: list[float], impostor: list[float]) -> dict:
    """EER from genuine/impostor cosine-similarity score lists.

    Sweeps the decision threshold over all observed scores and returns the
    operating point where false-accept rate ~= false-reject rate. Also returns
    d-prime (separation of the two score distributions in pooled-SD units), a
    threshold-free separability number that is robust to small samples.
    """

    import numpy as np
    if not genuine or not impostor:
        return {"eer": None, "eer_threshold": None, "dprime": None,
                "n_genuine": len(genuine), "n_impostor": len(impostor)}
    g = np.asarray(genuine); im = np.asarray(impostor)
    thresholds = np.unique(np.concatenate([g, im]))
    best = None
    for t in thresholds:
        far = float(np.mean(im >= t))    # impostors accepted
        frr = float(np.mean(g < t))      # genuines rejected
        gap = abs(far - frr)
        if best is None or gap < best[0]:
            best = (gap, float((far + frr) / 2), float(t))
    pooled_sd = float(np.sqrt((g.var() + im.var()) / 2)) or 1e-9
    dprime = float((g.mean() - im.mean()) / pooled_sd)
    return {"eer": round(best[1], 4), "eer_threshold": round(best[2], 4),
            "dprime": round(dprime, 3),
            "genuine_mean": round(float(g.mean()), 4),
            "impostor_mean": round(float(im.mean()), 4),
            "n_genuine": len(genuine), "n_impostor": len(impostor)}
