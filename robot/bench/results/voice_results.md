# Voice benchmark results

### VAD (latency = one ~30 ms block)

| Candidate | OK | Init ms | Latency median ms | Latency p95 ms | FPS | RTF | Peak RSS MB | Model MB | Dim | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `rms` | yes | 0 | 0.00 | 0.00 | 363634 | 0.000 | 199 | 0.0 | - | builtin; zero deps |
| `webrtc` | yes | 0 | 0.00 | 0.00 | 266667 | 0.000 | 201 | 0.0 | - | pip; tiny (already a dep) |
| `silero` | yes | 31 | 0.09 | 0.09 | 11572 | 0.003 | 370 | 10.8 | - | pip; torch (already a dep) |

### Speaker embedding (latency = one 6 s utterance)

| Candidate | OK | Init ms | Latency median ms | Latency p95 ms | FPS | RTF | Peak RSS MB | Model MB | Dim | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `resemblyzer` | yes | 14 | 23.74 | 24.45 | 42 | 0.004 | 379 | 16.3 | 256 | pip; weights bundled (no download) |
| `ecapa` | yes | 14334 | 31.28 | 32.10 | 32 | 0.005 | 600 | 84.9 | 192 | pip; downloads ~20-80MB from HF |
| `xvector` | yes | 9465 | 5.98 | 6.24 | 167 | 0.001 | 388 | 31.4 | 512 | pip; downloads ~20-80MB from HF |