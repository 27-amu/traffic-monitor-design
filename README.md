# Dual-Camera Traffic-Intersection Monitor — Design Assessment

Embedded Platform Intern design exercise: size the compute, design the pipeline, and define a benchmark plan for a 2-camera vehicle/pedestrian monitor on an Arm SoC (4×A78 + 4×A55, mobile GPU, 8 TOPS NPU, HW H.264, 4 GB LPDDR4X).

**Deliverable:** [`docs/Design_Embedded_Platform_Intern.pdf`](docs/Design_Embedded_Platform_Intern.pdf) (4 pages, including diagrams).

## How I approached it

The assessment is about problem-solving strategy, so here is the reasoning path in plain steps:

1. **Turn the spec into rates.** For every stage, compute pixels/s, bytes/s of DDR traffic, and ops/s. Then compare each rate with the block that would run that stage (ISP, GPU, NPU, CPU, encoder, DDR).
2. **Flag anything above ~70 % of capacity as a bottleneck.** That threshold leaves room for p99 tails, thermal throttling and contention on shared DDR.
3. **Fix bottlenecks by doing less work first, then by doing it faster.** Lower the resolution early, fuse passes, and reshape the model to fit the NPU before tuning kernels.
4. **Map each stage to the cheapest unit that meets its p99 latency slice.** Then pipeline the two streams across GPU / NPU / CPU / VPU so the units work in parallel.
5. **Write a benchmark plan that can prove every assumed number wrong.** Estimates are only a starting point; measurements decide.

## Key findings (details in the PDF)

| Finding | Number |
|---|---|
| Input pixel rate vs ISP/encoder capacity | 1,258 MP/s vs 249 MP/s → **5.1× over**, so the output must be downscaled (1280×1024 chosen) |
| Naive full-res CPU/OpenCV chain | **31.3 GB/s** DDR (174 % of sustained) and ~9 big cores → infeasible |
| Optimised design DDR traffic | **7.7 GB/s** (43 % of sustained) |
| Detector load | 510 GOPS → NPU 6 % of peak, ~7.5 ms/inference (memory-bound), 45 % busy |
| SiLU on NPU | Unsupported → CPU fallback ≈ 56 ms/inference → replace with ReLU + distillation |
| NMS worst case | 8,400 boxes ≈ 35 ms → top-K 1,000 bounds it to < 1 ms |
| Latency budget | **60 ms mean / 92 ms p99** (target 100 / 150), measured from start of sensor readout |

### Pipeline in one line

`Capture (CSI DMA) → GPU Pass A: undistort + downscale to 1280×1024 → GPU Pass B: letterbox 640×640, NV12→RGB (uint8 = INT8 input) → NPU: ReLU-YOLO INT8 → A78: decode + NMS + Kalman tracker + overlay → VPU: H.264 → RTP/RTSP`

All hand-offs are zero-copy DMA-BUF. Camera B is phase-shifted by half a frame so the shared GPU and NPU never queue.

## Repository layout

```
docs/Design_Embedded_Platform_Intern.pdf   the submission
analysis/calc.py                           every number in the PDF (edit assumptions at the top and re-run)
analysis/calc_output.txt                   output of calc.py
analysis/figures.py                        generates the three diagrams (incl. the pipeline schedule simulation)
analysis/build_pdf.py                      builds the PDF from text + figures
figures/                                   fig1 data flow, fig2 timeline, fig3 benchmark flow
```

## Reproduce

```bash
pip install matplotlib reportlab pypdf
python3 analysis/calc.py          # sizing numbers
python3 analysis/figures.py       # diagrams
python3 analysis/build_pdf.py     # PDF
```

## Main assumptions

The full list is in section 0 of the PDF. The ones that matter most:

- The cameras deliver processed NV12, and the SoC ISP acts only as the capture/DMA path. Its 1080p60 limit cannot process 5120×4096@30.
- The encoded output is the undistorted frame at 1280×1024@30 per stream. Full-resolution encode exceeds the encoder 5×.
- Latency is measured from the start of sensor readout to the last encoded NAL unit. Network transit is excluded.
- NPU utilisation (~35 %), per-core CPU rates and DDR share per engine are estimates. The Task 3 benchmarks replace them.
