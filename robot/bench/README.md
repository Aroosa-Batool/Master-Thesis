# Algorithm comparison benchmark

Head-to-head comparison of the demo's **camera** and **voice** presence-sensing
algorithms against CPU-only, pip-installable challengers, on the factors the
thesis cares about: **latency, throughput, peak memory, model size, install/
deploy friction**, and — with a recorded eval set — **accuracy (EER) and
robustness**.

The narrative write-up (literature review + results + the gap argument) lives in
[`../../docs/algorithm_comparison.md`](../../docs/algorithm_comparison.md).
This folder is the reproducible measurement harness behind it.

## What it compares

| Modality | Stage | Current (in the demo) | Challengers |
|---|---|---|---|
| Camera | detection | Haar cascade, YuNet | OpenCV-DNN SSD, MediaPipe BlazeFace, HOG person, SCRFD |
| Camera | recognition | SFace (128-d) | ArcFace / InsightFace (512-d) |
| Voice | VAD | RMS energy gate | WebRTC VAD, Silero VAD |
| Voice | speaker ID | Resemblyzer GE2E (256-d) | ECAPA-TDNN (192-d), x-vector (512-d) |

All challengers are CPU-only and pip-installable. Each candidate is measured in
its **own subprocess** so its peak-RSS is clean, a flaky native lib can't crash
the whole run, and no model pollutes another's memory/latency.

## Running it

```bash
# latency + memory + model size (no data needed; safe to run anywhere)
python robot/bench/bench_camera.py
python robot/bench/bench_voice.py

# more reps / a higher camera resolution
python robot/bench/bench_camera.py --res 1280x720 --repeats 100
python robot/bench/bench_voice.py  --repeats 500

# restrict to specific candidates
python robot/bench/bench_camera.py --only yunet,mediapipe,sface
```

First run downloads a few challenger models (SSD caffemodel ~10 MB, BlazeFace
tflite ~0.2 MB, InsightFace `buffalo_l` ~300 MB, SpeechBrain ECAPA/x-vector
~20–80 MB each). They cache under `bench/models/` and `~/.insightface/`.

Results are printed as tables and written to `bench/results/*.csv` and
`*.md`.

## Accuracy + robustness (needs a labelled eval set)

Latency/memory are intrinsic to each algorithm; accuracy and robustness need
real labelled examples of the people the system must tell apart. Record a small
set (~10 min) with the capture helper, then pass `--data`:

```bash
# faces: SPACE captures, q quits. Repeat per person and per condition.
python robot/bench/capture_eval_set.py faces --person alice --condition near  --shots 5
python robot/bench/capture_eval_set.py faces --person alice --condition far   --shots 5
python robot/bench/capture_eval_set.py faces --person bob   --condition near  --shots 5
python robot/bench/capture_eval_set.py faces --negative --shots 10   # no-face frames

# voices: one folder per speaker, condition in the filename prefix
python robot/bench/capture_eval_set.py voices --speaker alice --condition quiet --clips 3 --seconds 4
python robot/bench/capture_eval_set.py voices --speaker bob   --condition quiet --clips 3 --seconds 4

# now the benchmarks also report detection rate + verification EER / d-prime
python robot/bench/bench_camera.py --data robot/bench/eval_data
python robot/bench/bench_voice.py  --data robot/bench/eval_data
```

Minimum for a defensible number: **≥3 people, ≥2 conditions, ≥4 shots/clips
each**. The condition prefix (`near_01.jpg`, `noisy_02.wav`) lets you stratify
EER by condition for the robustness story.

The recorded `eval_data/` is git-ignored (personal data), as are the downloaded
challenger weights.

## Files

- `bench_camera.py` — face detection + recognition comparison
- `bench_voice.py` — VAD + speaker-embedding comparison
- `capture_eval_set.py` — record the labelled faces/voices eval set
- `_bench_util.py` — subprocess-isolated timing, peak-RSS, EER, table/CSV output
- `results/` — generated `camera_results.{csv,md}`, `voice_results.{csv,md}`
