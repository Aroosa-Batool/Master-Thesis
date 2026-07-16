# Camera benchmark results

### Detection (latency = one frame @ 640x480)

| Candidate | OK | Init ms | Latency median ms | Latency p95 ms | FPS | RTF | Peak RSS MB | Model MB | Dim | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `haar` | yes | 12 | 18.01 | 18.76 | 56 | - | 111 | 0.9 | - | builtin (ships with opencv) |
| `yunet` | yes | 18 | 5.15 | 6.29 | 194 | - | 102 | 0.2 | - | 0.2MB onnx (already shipped) |
| `opencv_dnn_ssd` | yes | 13 | 9.47 | 12.71 | 106 | - | 139 | 10.2 | - | cv2.dnn; ~10MB caffemodel download |
| `mediapipe` | yes | 132 | 0.83 | 0.91 | 1200 | - | 151 | 0.2 | - | pip; BlazeFace tflite (Tasks API) |
| `hog_people` | yes | 41 | 10.99 | 12.40 | 91 | - | 134 | 0.0 | - | builtin; detects PERSONS not faces |
| `scrfd` | yes | 402 | 91.68 | 134.94 | 11 | - | 787 | 16.1 | - | pip; insightface buffalo_l (~300MB) |

### Recognition (latency = one 112x112 crop)

| Candidate | OK | Init ms | Latency median ms | Latency p95 ms | FPS | RTF | Peak RSS MB | Model MB | Dim | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `sface` | yes | 35 | 7.33 | 9.14 | 136 | - | 229 | 36.9 | 128 | 38.7MB onnx (already shipped) |
| `arcface` | yes | 459 | 81.01 | 89.38 | 12 | - | 1136 | 166.3 | 512 | pip; insightface buffalo_l (~300MB) |