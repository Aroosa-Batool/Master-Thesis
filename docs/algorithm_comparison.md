# Algorithm Comparison: Camera and Voice Presence Detection

This document compares the detection algorithms used by the presence-sensing
layer of the thesis prototype against CPU-only, pip-installable alternatives. It
has two halves:

1. **Literature check** — does a head-to-head comparison of these algorithm
   families already exist, and on which factors? (Section 3.)
2. **Empirical benchmark** — where the published comparisons do not match this
   system's constraints, an own measurement of **latency, throughput, peak
   memory, model size, install/deploy friction**, and (with a recorded eval set)
   **accuracy and robustness**, run on the actual deployment hardware.
   (Sections 4–6.)

The reproducible harness lives in
[`robot/bench/`](../robot/bench/). Citation
conventions follow [`literature_review.md`](literature_review.md): every DOI /
arXiv id below was loaded from a real publisher, DOI resolver, or arXiv abstract
page during preparation; anything not verified to that standard is marked
**[needs verification]**.

---

## 1. What is being compared, and why

The robot decides "is a bystander present?" through two independent modalities,
each a small two-stage pipeline:

| Modality | Stage 1 — *presence* | Stage 2 — *identity (owner vs bystander)* |
| --- | --- | --- |
| **Camera** ([`face_id.py`](../robot/perception/face_id.py)) | Haar cascade (cheap per-frame count) + **YuNet** CNN for precise boxes | **SFace** 128-d embedding + cosine similarity |
| **Voice** ([`voice_id.py`](../robot/perception/voice_id.py)) | auto-calibrated **RMS energy gate** (VAD) | **Resemblyzer** GE2E d-vector (256-d) + cosine similarity |

These choices were made for defensible but largely *qualitative* reasons (they
ship with the libraries, run on CPU, avoid a `dlib` compile). A thesis that
*senses* in order to make a privacy decision should be able to say **why these
algorithms and not the alternatives**, in numbers, on the hardware it runs on.
That is what this document supplies.

The binding constraint is not raw accuracy but **deployability under a real-time
budget**: the laptop simultaneously holds a BLE link to the watch and a USB
serial link to the Ohbot, and the presence loop must stay responsive while doing
so. So the comparison weights **latency, memory, and install friction** as
first-class factors alongside accuracy — the opposite emphasis to most published
benchmarks, which optimise accuracy on a GPU.

### Candidate roster (all CPU-only, all pip-installable)

| Modality | Stage | In the demo | Challengers benchmarked |
| --- | --- | --- | --- |
| Camera | detection | Haar, YuNet | OpenCV-DNN SSD (ResNet-10), MediaPipe BlazeFace, HOG person detector, SCRFD (InsightFace) |
| Camera | recognition | SFace (128-d) | ArcFace / InsightFace `buffalo_l` (512-d) |
| Voice | VAD | RMS gate | WebRTC VAD, Silero VAD |
| Voice | speaker ID | Resemblyzer GE2E (256-d) | ECAPA-TDNN (192-d), x-vector (512-d), both SpeechBrain |

`dlib`'s HOG/CNN face detector and ResNet recogniser were intentionally excluded
because they require a compile step (CMake), which is precisely the deployment
friction the project avoids; their exclusion is itself a deployability finding.

---

## 2. The algorithms and their seminal references

All identifiers below were verified during preparation.

**Face detection**

- **Haar cascade** — Viola & Jones (2001). *Rapid Object Detection using a
  Boosted Cascade of Simple Features.* CVPR 2001, I-511–I-518.
  [doi:10.1109/CVPR.2001.990517](https://doi.org/10.1109/CVPR.2001.990517). The
  classic boosted-cascade detector; OpenCV ships its cascades.
- **MTCNN** — Zhang, Zhang, Li & Qiao (2016). *Joint Face Detection and
  Alignment using Multi-task Cascaded Convolutional Networks.* IEEE Signal
  Processing Letters. [arXiv:1604.02878](https://arxiv.org/abs/1604.02878).
- **YuNet** — Wu, Peng & Yu (2023). *YuNet: A Tiny Millisecond-level Face
  Detector.* Machine Intelligence Research, 20(5), 656–665.
  [doi:10.1007/s11633-023-1423-y](https://doi.org/10.1007/s11633-023-1423-y).
  Anchor-free, edge-targeted; the paper reports 1.6 ms/frame at 320×320 on an
  i7-12700K and 81.1% mAP on WIDER FACE hard. This is the demo's detector.
- **BlazeFace** — Bazarevsky, Kartynnik, Vakunov, Raveendran & Grundmann (2019).
  *BlazeFace: Sub-millisecond Neural Face Detection on Mobile GPUs.* CVPR
  Workshop. [arXiv:1907.05047](https://arxiv.org/abs/1907.05047). The detector
  inside MediaPipe.
- **RetinaFace** — Deng, Guo, Zhou, Yu, Kotsia & Zafeiriou (2019).
  *RetinaFace: Single-stage Dense Face Localisation in the Wild.*
  [arXiv:1905.00641](https://arxiv.org/abs/1905.00641).
- **SCRFD** — Guo, Deng, Lattas & Zafeiriou (2021). *Sample and Computation
  Redistribution for Efficient Face Detection.*
  [arXiv:2105.04714](https://arxiv.org/abs/2105.04714). The detector inside
  InsightFace `buffalo_l`.

**Face recognition / embedding**

- **FaceNet** — Schroff, Kalenichenko & Philbin (2015). *FaceNet: A Unified
  Embedding for Face Recognition and Clustering.* CVPR 2015.
  [arXiv:1503.03832](https://arxiv.org/abs/1503.03832). The deep-embedding +
  cosine/triplet family the whole stack belongs to.
- **ArcFace** — Deng, Guo, Yang, Xue, Kotsia & Zafeiriou (2018; CVPR 2019).
  *ArcFace: Additive Angular Margin Loss for Deep Face Recognition.*
  [arXiv:1801.07698](https://arxiv.org/abs/1801.07698). The challenger
  recogniser (512-d), via InsightFace.
- **SFace** — Zhong, Deng, et al. (2021). *SFace: Sigmoid-Constrained Hypersphere
  Loss for Robust Face Recognition.* IEEE Transactions on Image Processing, 30,
  2587–2598. [doi:10.1109/TIP.2020.3048632](https://doi.org/10.1109/TIP.2020.3048632).
  The demo's recogniser (128-d), via `cv2.FaceRecognizerSF`. *[Full author list
  beyond Zhong & Deng needs verification before final cite.]*

**Voice activity detection**

- **RMS energy gate** — classical short-term-energy VAD; no single canonical
  paper (the statistical-model lineage is Sohn, Kim & Sung, 1999, *A statistical
  model-based voice activity detection*, IEEE SPL 6(1) **[needs verification of
  exact pagination]**). The demo uses an auto-calibrated energy threshold.
- **WebRTC VAD** — the GMM-based detector from Google's open-source WebRTC
  project (`libwebrtc`), exposed in Python via `py-webrtcvad`. No peer-reviewed
  paper; cite the project/wrapper.
- **Silero VAD** — Silero Team (2021). *Silero VAD: pre-trained enterprise-grade
  Voice Activity Detector.* GitHub: `snakers4/silero-vad`. A small CNN; no
  peer-reviewed paper, cite the repository.

**Speaker recognition / embedding**

- **i-vector** — Dehak, Kenny, Dehak, Dumouchel & Ouellet (2011). *Front-End
  Factor Analysis for Speaker Verification.* IEEE TASLP, 19(4), 788–798.
  [doi:10.1109/TASL.2010.2064307](https://doi.org/10.1109/TASL.2010.2064307).
  The pre-deep baseline.
- **x-vector** — Snyder, Garcia-Romero, Sell, Povey & Khudanpur (2018).
  *X-Vectors: Robust DNN Embeddings for Speaker Recognition.* ICASSP 2018,
  5329–5333. [doi:10.1109/ICASSP.2018.8461375](https://doi.org/10.1109/ICASSP.2018.8461375).
  A challenger embedder (512-d), via SpeechBrain.
- **GE2E d-vector** — Wan, Wang, Papir & Lopez Moreno (2017; ICASSP 2018).
  *Generalized End-to-End Loss for Speaker Verification.*
  [arXiv:1710.10467](https://arxiv.org/abs/1710.10467). The loss behind
  Resemblyzer's encoder (256-d), the demo's embedder.
- **ECAPA-TDNN** — Desplanques, Thienpondt & Demuynck (2020). *ECAPA-TDNN:
  Emphasized Channel Attention, Propagation and Aggregation in TDNN Based
  Speaker Verification.* Interspeech 2020.
  [arXiv:2005.07143](https://arxiv.org/abs/2005.07143). Current SOTA family
  (192-d), via SpeechBrain.

---

## 3. Does the comparison already exist in the literature?

**Short answer: partially, and never in this system's framing.** Comparisons are
abundant *within* each sub-area, almost always optimising **accuracy on a GPU**
against a standard benchmark; they do not jointly cover both modalities, the
CPU-only real-time budget, or the deploy-friction dimension this prototype needs.

### 3a. Face detection — comparisons exist, mostly accuracy-first

- **Feng, Yu, Peng, Li & Zhang (2021).** *Detect Faces Efficiently: A Survey and
  Evaluations.* [arXiv:2112.01787](https://arxiv.org/abs/2112.01787). The closest
  existing comparison for this sub-area: it explicitly compares deep face
  detectors on **FLOPs and latency**, not only accuracy. Still a general survey,
  not CPU-laptop-in-a-robot-loop, and predates the 2023 YuNet paper's framing.
- The **WIDER FACE** benchmark is the common accuracy yardstick most detector
  papers above report on (MTCNN, RetinaFace, SCRFD, YuNet); it is an
  accuracy-in-the-wild benchmark, not a latency one.
- *Benchmark: Face Detection Using Deep Learning Models and Frameworks* (Springer,
  2025), [doi:10.1007/978-3-031-93103-1_11](https://doi.org/10.1007/978-3-031-93103-1_11),
  reports CPU per-face timings (≈0.03 s YuNet, ≈0.04 s MediaPipe, RetinaFace much
  slower) — the same ranking this benchmark finds. **[needs verification of
  author list and exact numbers — located via search; chapter page not loaded.]**

### 3b. Face recognition — comparisons exist, accuracy-first, GPU

- ArcFace, SFace, and FaceNet are routinely compared on **LFW / MegaFace / IJB-C**
  verification accuracy in their own papers and in survey literature. These are
  accuracy benchmarks; per-embedding **CPU latency** and **memory** are rarely
  the headline and rarely measured against the exact OpenCV-bundled SFace this
  project ships.

### 3c. VAD — comparisons exist, often vendor/grey-literature

- The **Silero VAD** repository publishes quality metrics versus WebRTC VAD, and
  third-party benchmarks (e.g. Picovoice) compare WebRTC / Silero / commercial
  VADs. Reported frame-level results put Silero far above WebRTC on speech-vs-
  noise F1 (~96% vs ~52% in one widely-cited comparison) while both are
  sub-millisecond per chunk. Useful, but largely **non-peer-reviewed**, and not
  measured inside a robot's live capture loop.

### 3d. Speaker recognition — comparisons exist, EER-first

- **VoxCeleb** and **NIST SRE** are the standard arenas; ECAPA-TDNN, x-vector,
  and d-vector/GE2E are compared there by **Equal Error Rate**. ECAPA-TDNN is the
  consensus modern winner on EER. Again: EER-first, GPU-trained, not CPU-latency-
  in-deployment, and Resemblyzer's specific GE2E encoder is rarely the comparison
  point.

### 3e. Both modalities together for real-time HRI presence — essentially absent

- **Aris & Grondin (2023).** *Efficient Face Detection with Audio-Based Region
  Proposals for Human-Robot Interactions.*
  [arXiv:2309.08005](https://arxiv.org/abs/2309.08005). The nearest cross-modal
  neighbour: it *uses* audio to make face detection cheaper for a robot. But it
  is a fusion method, not a head-to-head comparison of competing face- **and**
  voice-presence algorithms on a shared latency budget.
- Recent multi-party social-robot systems combine voice DoA + diarisation + face
  recognition (e.g. Frontiers / arXiv multi-party conversation work, 2025–2026
  **[needs verification of specific venues/authors]**), but they report
  task-level success, not a controlled per-algorithm latency/accuracy comparison
  for the *presence-gating* decision.

### Headline gap

No verified prior work compares, **head-to-head on a CPU-only laptop running a
co-located social robot in real time**, the camera *and* voice presence+identity
algorithm families together, weighting **latency, memory, and install/deploy
friction** alongside accuracy. Per-sub-area, accuracy-first, GPU benchmarks exist
and are cited above; this document's contribution is the **system-specific,
deployment-constrained, cross-modal** comparison — and the reproducible harness
that produces it. That is a legitimate, narrow engineering contribution and, more
practically, it lets the thesis justify each sensing choice with its own numbers
rather than by appeal to a benchmark run under different assumptions.

---

## 4. Empirical method

The harness ([`robot/bench/`](../robot/bench/)) measures
each candidate in its **own subprocess**, which (a) yields a clean per-candidate
**peak RSS** (`resource.getrusage`, normalised across macOS/Linux), (b) isolates
native-library crashes, and (c) prevents one loaded model from warming caches or
stealing memory from the next. Timing uses `time.perf_counter` after a warmup
phase; the **median** and **p95** are reported (per-call latency is right-skewed,
and the median is what the live loop feels).

Latency units match the live loops:

- **Detection** — one frame (default 640×480; configurable).
- **Recognition** — one aligned 112×112 face crop (cost is content-independent).
- **VAD** — one ~30 ms audio block (one live-callback decision).
- **Speaker embedding** — one ~6 s utterance (a representative single-utterance window).

**Accuracy and robustness need a labelled eval set** (real images/audio of the
people to be told apart), because each algorithm has its own embedding space and
pre-computed galleries do not transfer. The harness measures latency/memory/size
with no data; with `--data` it computes detection rate, false-positive rate, and
verification **EER / d-prime** from genuine-vs-impostor cosine pairs. A capture
helper (`capture_eval_set.py`) records that set from the same webcam/mic in ~10
minutes; collecting it and filling in Section 6 is the remaining step.

**Hardware caveat.** The numbers in Section 5 were collected on an **Apple M4
(10-core), macOS, Python 3.13** — the development laptop. The M4 is fast, so
absolute latencies are optimistic relative to a low-power edge board; the harness
is meant to be re-run on whatever hardware the study actually deploys on. The
*rankings* are expected to hold; the *margins* are hardware-dependent.

---

## 5. Results (latency, throughput, memory, size, deployability)

Apple M4, 640×480 frames, 16 kHz audio. Detection reps = 50; VAD reps = 200;
speaker reps measured on real speech tiled from `ohbotspeech.wav`. Raw output:
[`robot/bench/results/`](../robot/bench/results/).

### 5a. Camera — face detection (latency = 1 frame @ 640×480)

| Detector | Median ms | p95 ms | FPS | Peak RSS MB | Model MB | Init ms | Deploy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **MediaPipe BlazeFace** | **0.83** | 0.91 | ~1200 | 151 | 0.2 | 132 | pip; tflite (Tasks API) |
| **YuNet** *(in demo)* | 5.15 | 6.29 | ~194 | 102 | 0.2 | 18 | ships with opencv |
| OpenCV-DNN SSD (ResNet-10) | 9.47 | 12.71 | ~106 | 139 | 10.2 | 13 | cv2.dnn; ~10 MB download |
| HOG person detector | 10.99 | 12.40 | ~91 | 134 | — | 41 | builtin; detects *persons* |
| **Haar cascade** *(in demo)* | 18.01 | 18.76 | ~56 | 111 | 0.9 | 12 | ships with opencv |
| SCRFD (InsightFace) | 91.68 | 134.94 | ~11 | 787 | 16.1 | 402 | pip; `buffalo_l` ~300 MB |

### 5b. Camera — face recognition (latency = 1 crop 112×112)

| Recogniser | Dim | Median ms | p95 ms | FPS | Peak RSS MB | Model MB | Deploy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **SFace** *(in demo)* | 128 | 7.33 | 9.14 | ~136 | 229 | 36.9 | ships with opencv |
| ArcFace (InsightFace) | 512 | 81.01 | 89.38 | ~12 | 1136 | 166.3 | pip; `buffalo_l` ~300 MB |

### 5c. Voice — VAD (latency = 1 block ~30 ms)

| VAD | Median ms | FPS | RTF | Peak RSS MB | Model MB | Deploy |
| --- | --- | --- | --- | --- | --- | --- |
| **RMS gate** *(in demo)* | <0.01 | ~360k | ~0.0001 | 199 | — | builtin; zero deps |
| WebRTC VAD | <0.01 | ~270k | ~0.0001 | 201 | — | pip; already a dep |
| Silero VAD | 0.09 | ~11.6k | ~0.003 | 370 | 10.8 | pip; torch (already a dep) |

### 5d. Voice — speaker embedding (latency = 1 × 6 s utterance)

| Embedder | Dim | Median ms | p95 ms | RTF | Peak RSS MB | Model MB | Init ms | Deploy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Resemblyzer GE2E** *(in demo)* | 256 | 23.74 | 24.45 | 0.004 | 379 | 16.3 | 14 | weights bundled (no download) |
| ECAPA-TDNN (SpeechBrain) | 192 | 31.28 | 32.10 | 0.005 | 600 | 84.9 | 14334 | downloads from HF |
| x-vector (SpeechBrain) | 512 | 5.98 | 6.24 | 0.001 | 388 | 31.4 | 9465 | downloads from HF |

### 5e. Accuracy and robustness — pending eval set

Detection rate, false-positive rate, and verification EER / d-prime are computed
automatically once a labelled eval set exists
([`capture_eval_set.py`](../robot/bench/capture_eval_set.py); see
Section 6). The published rankings to expect: **ArcFace > SFace** on face
verification (ArcFace leads LFW/IJB-C), **ECAPA-TDNN > x-vector > GE2E/d-vector**
on speaker EER (VoxCeleb), and **Silero ≫ WebRTC ≫ RMS** on speech-vs-noise VAD.
The benchmark's job is to confirm whether those accuracy gains are large enough,
*on this system's own data and conditions*, to justify their latency/memory cost.

---

## 6. Discussion and recommendation

**1. On this hardware, latency is not the binding constraint for the lightweight
options — it is decisive only for the SOTA ones.** Every shipped choice (YuNet,
SFace, RMS, Resemblyzer) runs comfortably real-time: detection and recognition
each cost single-digit milliseconds, VAD is effectively free, and speaker
embedding is RTF ≈ 0.004 (a 6 s window embeds in ~24 ms). The heavyweight
challengers are where latency bites: SCRFD detection is **~18× slower** than
YuNet and ArcFace recognition **~11× slower** than SFace, each pushing peak RSS
toward **~0.8–1.1 GB** — material when the same laptop is also driving BLE + USB
serial.

**2. The "cheap" Haar presence path is, counter-intuitively, the slowest face
detector measured** (18 ms vs YuNet's 5 ms at VGA). Haar's cost scales with the
number of scanned windows, whereas YuNet's is a fixed, small forward pass. This
is a concrete, citable finding and suggests the demo could **drop Haar and use
YuNet for both the cheap per-frame count and the precise boxes**, simplifying the
pipeline with no latency penalty. (MediaPipe BlazeFace is faster still at 0.83 ms
but returns only boxes/keypoints, not the embedding-ready aligned crop YuNet+SFace
rely on, and adds a model download.)

**3. The current voice choices are well-justified on deployability.** Resemblyzer
ships its weights inside the pip package (zero download, ~14 ms init), whereas the
SpeechBrain models add a multi-second model load (ECAPA ~14 s init) and an
HF download. Interestingly **x-vector is the *fastest* embedder measured** (6 ms,
RTF 0.001) — if a labelled eval set shows it meaningfully beats GE2E on EER for
this mic/room, it is a cheap upgrade; ECAPA only earns its 31 ms + 14 s-init cost
if its accuracy advantage is real on this system's data.

**4. RMS vs WebRTC vs Silero is an accuracy question, not a latency one.** All
three are far below the live budget. The literature strongly favours Silero on
speech-vs-noise discrimination; since `webrtcvad` is *already an installed
dependency*, WebRTC VAD is a near-zero-cost robustness upgrade over the raw RMS
gate worth testing against the eval set, with Silero as the accuracy ceiling.

**Recommendation.** Keep **YuNet + SFace** (camera) and **RMS/Resemblyzer**
(voice) as the shipped stack — the benchmark confirms they are at or near the
Pareto front of latency × memory × deploy-friction. Then run the three concrete,
low-cost experiments the numbers surface: (i) **Haar → YuNet** for the cheap
count; (ii) **WebRTC or Silero VAD** in place of the raw RMS gate; (iii)
**x-vector** as a faster speaker embedder — each gated on the accuracy/robustness
numbers from Section 5e once the eval set is recorded. Report ArcFace and ECAPA
as the *accuracy ceiling* the lightweight stack is measured against, not as
deployment candidates.

---

## 7. Reproducing

```bash
pip install -r requirements.txt
pip install onnxruntime insightface mediapipe silero-vad speechbrain   # challengers

python robot/bench/bench_camera.py        # latency/memory/size
python robot/bench/bench_voice.py

# accuracy + robustness: record ~10 min of labelled data first, then --data
python robot/bench/capture_eval_set.py faces  --person alice --condition near --shots 5
python robot/bench/capture_eval_set.py voices --speaker alice --condition quiet --clips 3
python robot/bench/bench_camera.py --data robot/bench/eval_data
python robot/bench/bench_voice.py  --data robot/bench/eval_data
```

See [`robot/bench/README.md`](../robot/bench/README.md)
for the full candidate list and options.

---

## 8. Verified-citation summary

Loaded and verified during preparation (publisher / DOI resolver / arXiv):
Viola & Jones 2001 (10.1109/CVPR.2001.990517); MTCNN (arXiv:1604.02878);
RetinaFace (arXiv:1905.00641); BlazeFace (arXiv:1907.05047); SCRFD
(arXiv:2105.04714); YuNet (10.1007/s11633-023-1423-y); FaceNet (arXiv:1503.03832);
ArcFace (arXiv:1801.07698); SFace (10.1109/TIP.2020.3048632); Feng et al. survey
(arXiv:2112.01787); i-vector (10.1109/TASL.2010.2064307); x-vector
(10.1109/ICASSP.2018.8461375); GE2E (arXiv:1710.10467); ECAPA-TDNN
(arXiv:2005.07143); Silero VAD (github.com/snakers4/silero-vad); Aris & Grondin
2023 (arXiv:2309.08005).

Marked **[needs verification]**: SFace full author list; Springer 2025 CPU
benchmark author list/numbers; Sohn et al. 1999 VAD pagination; the 2025–2026
multi-party social-robot venues/authors.
