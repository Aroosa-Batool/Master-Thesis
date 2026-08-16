"""Camera-modality algorithm comparison: face detection + face recognition.

Compares the demo's current camera stack against CPU-only, pip-installable
challengers, on the thesis's factors: latency (the presence loop must stay
real-time), throughput (FPS), peak memory, model size, and - when an eval set
is supplied - detection rate and face-verification accuracy (EER / d-prime).

Stages
------
DETECTION (the "is anyone in view?" gate):
  - haar          : Viola-Jones Haar cascade        (the demo's cheap presence path)
  - yunet         : YuNet CNN, cv2.FaceDetectorYN   (the demo's precise detector)
  - opencv_dnn_ssd: ResNet-10 SSD face detector (cv2.dnn, auto-downloaded)
  - mediapipe     : BlazeFace short-range (MediaPipe)
  - hog_people    : HOG+SVM *person* detector (cv2) - presence without a face
  - scrfd         : SCRFD via InsightFace (buffalo_l) - optional, downloads once

RECOGNITION (the "owner vs bystander" re-ID):
  - sface         : SFace 128-d, cv2.FaceRecognizerSF   (the demo's current encoder)
  - arcface       : ArcFace 512-d via InsightFace (buffalo_l) - optional

Latency unit:
  - detection : detect on ONE frame (default 640x480; --res to change)
  - recognition: embed ONE aligned 112x112 face crop (content-independent cost)

Latency caveat (documented honestly): with no --data, detection runs on a
synthetic frame. For the CNN detectors (yunet/ssd/mediapipe/scrfd) the cost is
the fixed-resolution forward pass and is essentially content-independent; for
Haar/HOG the cost grows with the number of candidate windows, so their
synthetic-frame number is a *floor* - pass --data with real frames for a
content-realistic detection latency.

Usage
-----
    python robot/bench/bench_camera.py
    python robot/bench/bench_camera.py --res 1280x720 --repeats 50
    python robot/bench/bench_camera.py --data eval_data

With --data, expects eval_data/faces/<person_label>/*.jpg (>=2 persons, >=2
images each) for recognition EER, and optionally eval_data/faces/_negative/*.jpg
(frames with no face) for detector false-positive rate.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))   # for the sibling _bench_util import

from _bench_util import (  # noqa: E402
    CandidateResult, cosine, equal_error_rate, file_size_mb, peak_rss_mb,
    render_markdown, render_table, run_worker, time_call, write_csv,
)

MODELS_DIR = _HERE / "models"                        # challenger weights (bench-local)
# Reuse the package's YuNet/SFace ONNX weights (robot/state/models); _HERE is
# robot/bench, so _HERE.parent is the robot/ package root.
PRESENCE_MODELS = _HERE.parent / "state" / "models"
YUNET_ONNX = PRESENCE_MODELS / "face_detection_yunet_2023mar.onnx"
SFACE_ONNX = PRESENCE_MODELS / "face_recognition_sface_2021dec.onnx"

SSD_PROTO_URL = ("https://raw.githubusercontent.com/opencv/opencv/4.x/"
                 "samples/dnn/face_detector/deploy.prototxt")
SSD_MODEL_URL = ("https://raw.githubusercontent.com/opencv/opencv_3rdparty/"
                 "dnn_samples_face_detector_20170830/"
                 "res10_300x300_ssd_iter_140000.caffemodel")
BLAZE_URL = ("https://storage.googleapis.com/mediapipe-models/face_detector/"
             "blaze_face_short_range/float16/1/blaze_face_short_range.tflite")

DETECT_CANDIDATES = ["haar", "yunet", "opencv_dnn_ssd", "mediapipe", "hog_people", "scrfd"]
RECOGNIZE_CANDIDATES = ["sface", "arcface"]
ALL = DETECT_CANDIDATES + RECOGNIZE_CANDIDATES


def _synthetic_frame(w: int, h: int) -> np.ndarray:
    """A textured BGR frame. Not a real face - used for forward-pass latency."""
    rng = np.random.default_rng(0)
    return (rng.integers(0, 256, (h, w, 3))).astype("uint8")


def _synthetic_crop() -> np.ndarray:
    rng = np.random.default_rng(1)
    return (rng.integers(0, 256, (112, 112, 3))).astype("uint8")


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        f.write(r.read())
    os.replace(tmp, dest)


# --- detection candidate wrappers -------------------------------------------
# Each returns (init_ms, detect_fn(bgr_frame)->n_faces, model_paths, deploy).

def build_detector(name: str, res: tuple[int, int]):
    import cv2
    w, h = res

    if name == "haar":
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        t0 = time.perf_counter()
        clf = cv2.CascadeClassifier(str(path))
        init_ms = (time.perf_counter() - t0) * 1000
        def detect(frame):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return len(clf.detectMultiScale(gray, 1.1, 5))
        return init_ms, detect, [path], "builtin (ships with opencv)"

    if name == "yunet":
        t0 = time.perf_counter()
        det = cv2.FaceDetectorYN.create(str(YUNET_ONNX), "", (w, h), 0.9, 0.3, 5000)
        init_ms = (time.perf_counter() - t0) * 1000
        def detect(frame):
            det.setInputSize((frame.shape[1], frame.shape[0]))
            _, faces = det.detect(frame)
            return 0 if faces is None else len(faces)
        return init_ms, detect, [YUNET_ONNX], "0.2MB onnx (already shipped)"

    if name == "opencv_dnn_ssd":
        proto = MODELS_DIR / "deploy.prototxt"
        model = MODELS_DIR / "res10_300x300_ssd.caffemodel"
        _download(SSD_PROTO_URL, proto)
        _download(SSD_MODEL_URL, model)
        t0 = time.perf_counter()
        net = cv2.dnn.readNetFromCaffe(str(proto), str(model))
        init_ms = (time.perf_counter() - t0) * 1000
        def detect(frame):
            blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300),
                                         (104.0, 177.0, 123.0))
            net.setInput(blob)
            d = net.forward()
            return int((d[0, 0, :, 2] > 0.5).sum())
        return init_ms, detect, [proto, model], "cv2.dnn; ~10MB caffemodel download"

    if name == "mediapipe":
        # MediaPipe 0.10.x on Python 3.13 ships only the Tasks API (the legacy
        # mp.solutions.face_detection module is gone), so use vision.FaceDetector
        # with the downloadable BlazeFace short-range tflite.
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
        model_path = MODELS_DIR / "blaze_face_short_range.tflite"
        _download(BLAZE_URL, model_path)
        t0 = time.perf_counter()
        det = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
            min_detection_confidence=0.5,
            running_mode=vision.RunningMode.IMAGE,
        ))
        init_ms = (time.perf_counter() - t0) * 1000
        def detect(frame):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = det.detect(mp_img)
            return len(result.detections) if result.detections else 0
        return init_ms, detect, [model_path], "pip; BlazeFace tflite (Tasks API)"

    if name == "hog_people":
        t0 = time.perf_counter()
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        init_ms = (time.perf_counter() - t0) * 1000
        def detect(frame):
            rects, _ = hog.detectMultiScale(frame, winStride=(8, 8))
            return len(rects)
        return init_ms, detect, [], "builtin; detects PERSONS not faces"

    if name == "scrfd":
        from insightface.app import FaceAnalysis
        t0 = time.perf_counter()
        app = FaceAnalysis(name="buffalo_l", allowed_modules=["detection"],
                           providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        init_ms = (time.perf_counter() - t0) * 1000
        model_dir = Path.home() / ".insightface" / "models" / "buffalo_l"
        det_onnx = model_dir / "det_10g.onnx"
        def detect(frame):
            bboxes, _ = app.det_model.detect(frame, max_num=0, metric="default")
            return 0 if bboxes is None else len(bboxes)
        return init_ms, detect, [det_onnx if det_onnx.exists() else model_dir], \
            "pip; insightface buffalo_l (~300MB)"

    raise ValueError(name)


# --- recognition candidate wrappers -----------------------------------------
# Each returns (init_ms, embed_crop_fn(112x112 bgr)->vec, model_paths, dim, deploy,
#               embed_image_fn(full bgr)->vec|None for accuracy).

def build_recognizer(name: str):
    import cv2

    if name == "sface":
        t0 = time.perf_counter()
        rec = cv2.FaceRecognizerSF.create(str(SFACE_ONNX), "")
        det = cv2.FaceDetectorYN.create(str(YUNET_ONNX), "", (320, 320), 0.9, 0.3, 5000)
        init_ms = (time.perf_counter() - t0) * 1000
        def embed_crop(crop112):
            return np.asarray(rec.feature(crop112), dtype="float32").ravel()
        def embed_image(frame):
            det.setInputSize((frame.shape[1], frame.shape[0]))
            _, faces = det.detect(frame)
            if faces is None or len(faces) == 0:
                return None
            aligned = rec.alignCrop(frame, faces[0])
            return np.asarray(rec.feature(aligned), dtype="float32").ravel()
        return init_ms, embed_crop, [SFACE_ONNX], 128, \
            "38.7MB onnx (already shipped)", embed_image

    if name == "arcface":
        from insightface.app import FaceAnalysis
        t0 = time.perf_counter()
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        init_ms = (time.perf_counter() - t0) * 1000
        rec = app.models["recognition"]
        model_dir = Path.home() / ".insightface" / "models" / "buffalo_l"
        rec_onnx = model_dir / "w600k_r50.onnx"
        def embed_crop(crop112):
            return np.asarray(rec.get_feat(crop112), dtype="float32").ravel()
        def embed_image(frame):
            faces = app.get(frame)
            if not faces:
                return None
            return np.asarray(faces[0].embedding, dtype="float32").ravel()
        return init_ms, embed_crop, [rec_onnx if rec_onnx.exists() else model_dir], \
            512, "pip; insightface buffalo_l (~300MB)", embed_image

    raise ValueError(name)


# --- worker -----------------------------------------------------------------

def run_one(name: str, res: tuple[int, int], repeats: int,
            data_dir: Path | None) -> CandidateResult:
    is_det = name in DETECT_CANDIDATES
    stage = "detect" if is_det else "recognize"
    try:
        if is_det:
            init_ms, detect, model_paths, deploy = build_detector(name, res)
            frame = _frame_for_latency(res, data_dir)
            lat = time_call(lambda: detect(frame), repeats=repeats, warmup=3)
            res_obj = CandidateResult(
                name=name, stage=stage, ok=True, init_ms=init_ms,
                latency=lat.__dict__, peak_rss_mb=peak_rss_mb(),
                model_size_mb=file_size_mb(model_paths), deploy=deploy,
                extra={"res": f"{res[0]}x{res[1]}"},
            )
            if data_dir is not None:
                res_obj.accuracy = detection_accuracy(detect, data_dir)
        else:
            init_ms, embed_crop, model_paths, dim, deploy, embed_image = \
                build_recognizer(name)
            crop = _synthetic_crop()
            lat = time_call(lambda: embed_crop(crop), repeats=repeats, warmup=3)
            res_obj = CandidateResult(
                name=name, stage=stage, ok=True, init_ms=init_ms,
                latency=lat.__dict__, peak_rss_mb=peak_rss_mb(),
                model_size_mb=file_size_mb(model_paths), embedding_dim=dim,
                deploy=deploy,
            )
            if data_dir is not None:
                res_obj.accuracy = recognition_accuracy(embed_image, data_dir)
        return res_obj
    except Exception as exc:
        import traceback
        return CandidateResult(name=name, stage=stage, ok=False,
                               error=f"{type(exc).__name__}: {exc}",
                               extra={"trace": traceback.format_exc()[-500:]})


def _frame_for_latency(res, data_dir):
    """A real eval frame if available (content-realistic), else synthetic."""
    if data_dir is not None:
        import cv2
        faces = data_dir / "faces"
        if faces.is_dir():
            for p in sorted(faces.rglob("*.jpg")):
                img = cv2.imread(str(p))
                if img is not None:
                    return cv2.resize(img, res)
    return _synthetic_frame(*res)


def detection_accuracy(detect, data_dir: Path) -> dict | None:
    import cv2
    faces = data_dir / "faces"
    if not faces.is_dir():
        return None
    pos = [p for p in faces.rglob("*.jpg") if "_negative" not in p.parts]
    neg = [p for p in (faces / "_negative").glob("*.jpg")] if (faces / "_negative").is_dir() else []
    hits = 0
    for p in pos:
        img = cv2.imread(str(p))
        if img is not None and detect(img) >= 1:
            hits += 1
    fp = 0
    for p in neg:
        img = cv2.imread(str(p))
        if img is not None and detect(img) >= 1:
            fp += 1
    return {"detection_rate": round(hits / max(1, len(pos)), 4),
            "n_pos": len(pos),
            "false_positive_rate": round(fp / len(neg), 4) if neg else None,
            "n_neg": len(neg)}


def recognition_accuracy(embed_image, data_dir: Path) -> dict | None:
    import cv2
    root = data_dir / "faces"
    if not root.is_dir():
        return None
    embs: dict[str, list[np.ndarray]] = {}
    for pdir in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "_negative"):
        vecs = []
        for img_p in sorted(pdir.glob("*.jpg")):
            img = cv2.imread(str(img_p))
            if img is None:
                continue
            v = embed_image(img)
            if v is not None:
                vecs.append(v)
        if len(vecs) >= 2:
            embs[pdir.name] = vecs
    if len(embs) < 2:
        return {"note": "need >=2 persons with >=2 detected faces each"}
    genuine, impostor = [], []
    ppl = list(embs)
    for s in ppl:
        v = embs[s]
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                genuine.append(cosine(v[i], v[j]))
    for a in range(len(ppl)):
        for b in range(a + 1, len(ppl)):
            for va in embs[ppl[a]]:
                for vb in embs[ppl[b]]:
                    impostor.append(cosine(va, vb))
    return equal_error_rate(genuine, impostor)


# --- orchestrator -----------------------------------------------------------

def _parse_res(s: str) -> tuple[int, int]:
    w, h = s.lower().split("x")
    return int(w), int(h)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker", metavar="NAME")
    ap.add_argument("--res", type=str, default="640x480")
    ap.add_argument("--repeats", type=int, default=50)
    ap.add_argument("--data", type=str, default=None)
    ap.add_argument("--only", type=str, default=None)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--out-dir", type=str, default=None,
                    help="write results here instead of bench/results")
    args = ap.parse_args()

    res = _parse_res(args.res)
    data_dir = Path(args.data).resolve() if args.data else None

    if args.worker:
        run_one(args.worker, res, args.repeats, data_dir).emit()
        return

    names = ALL if not args.only else [n.strip() for n in args.only.split(",")]
    extra = ["--res", args.res, "--repeats", str(args.repeats)]
    if data_dir:
        extra += ["--data", str(data_dir)]

    print(f"Camera benchmark - {len(names)} candidates, res={args.res}, "
          f"repeats={args.repeats}"
          + (f", eval={data_dir}" if data_dir else " (latency/memory only)"))
    results = []
    for n in names:
        print(f"  running {n} ...", flush=True)
        results.append(run_worker(_HERE / "bench_camera.py", n, extra, args.timeout))

    det = [r for r in results if r.name in DETECT_CANDIDATES]
    rec = [r for r in results if r.name in RECOGNIZE_CANDIDATES]
    print(render_table(det, f"CAMERA - detection (latency = 1 frame @ {args.res})"))
    print(render_table(rec, "CAMERA - recognition (latency = 1 face crop 112x112)"))

    out_dir = Path(args.out_dir).resolve() if args.out_dir else _HERE / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, out_dir / "camera_results.csv")
    md = ["# Camera benchmark results", "",
          render_markdown(det, f"Detection (latency = one frame @ {args.res})"), "",
          render_markdown(rec, "Recognition (latency = one 112x112 crop)")]
    for r in results:
        if r.accuracy:
            md.append(f"\n- `{r.name}` accuracy: {r.accuracy}")
    (out_dir / "camera_results.md").write_text("\n".join(md))
    print(f"\nWrote {out_dir/'camera_results.csv'} and camera_results.md")


if __name__ == "__main__":
    main()
