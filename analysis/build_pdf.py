"""Builds docs/Design_Embedded_Platform_Intern.pdf (<= 5 pages). Run from repo root."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                Image, KeepTogether, CondPageBreak)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

FD = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", FD + "DejaVuSansCondensed.ttf"))
pdfmetrics.registerFont(TTFont("DV-B", FD + "DejaVuSansCondensed-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DV-I", FD + "DejaVuSansCondensed-Oblique.ttf"))
pdfmetrics.registerFont(TTFont("DV-BI", FD + "DejaVuSansCondensed-BoldOblique.ttf"))
addMapping("DV", 0, 0, "DV"); addMapping("DV", 1, 0, "DV-B")
addMapping("DV", 0, 1, "DV-I"); addMapping("DV", 1, 1, "DV-BI")

ACC = colors.HexColor("#1f4e79")
body = ParagraphStyle("b", fontName="DV", fontSize=8.8, leading=11.0, spaceAfter=2.5)
small = ParagraphStyle("s", parent=body, fontSize=7.8, leading=9.5, spaceAfter=0)
cell = ParagraphStyle("c", parent=body, fontSize=7.6, leading=9.2, spaceAfter=0)
cellb = ParagraphStyle("cb", parent=cell, fontName="DV-B")
h1 = ParagraphStyle("h1", fontName="DV-B", fontSize=11.5, leading=14, textColor=ACC,
                    spaceBefore=5, spaceAfter=3, keepWithNext=1)
h2 = ParagraphStyle("h2", fontName="DV-B", fontSize=9.2, leading=11.5, textColor=ACC,
                    spaceBefore=4, spaceAfter=2, keepWithNext=1)
title = ParagraphStyle("t", fontName="DV-B", fontSize=14.5, leading=17, textColor=ACC)
cap = ParagraphStyle("cap", parent=small, fontName="DV-I", textColor=colors.HexColor("#444"),
                     spaceAfter=3, spaceBefore=1)
bul = ParagraphStyle("bul", parent=body, leftIndent=9, bulletIndent=0, spaceAfter=1.2)

W = A4[0] - 2 * 1.35 * cm


def P(t, s=body): return Paragraph(t, s)
def B(t): return Paragraph(t, bul, bulletText="•")


def T(rows, widths, head=True, fs=None, zebra=True):
    data = [[c if not isinstance(c, str) else Paragraph(c, cellb if (head and i == 0) else cell)
             for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * W for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9aa7b4")),
          ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 2.6), ("RIGHTPADDING", (0, 0), (-1, -1), 2.6),
          ("TOPPADDING", (0, 0), (-1, -1), 1.3), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce6f0")))
    if zebra:
        for i in range(2 if head else 1, len(rows), 2):
            st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f7fa")))
    t.setStyle(TableStyle(st))
    return t


def fig(path, ratio, caption, scale=1.0):
    im = Image(path, width=W * scale, height=W * scale * ratio)
    return KeepTogether([im, P(caption, cap)])


def footer(c, d):
    c.saveState()
    c.setFont("DV", 7)
    c.setFillColor(colors.HexColor("#666"))
    c.drawString(1.35 * cm, 0.8 * cm, "Dual-Camera Traffic-Intersection Monitor - design assessment (Embedded Platform Intern)")
    c.drawRightString(A4[0] - 1.35 * cm, 0.8 * cm, f"page {d.page}")
    c.restoreState()


S = []
# ============================================================== header
S += [P("Dual-Camera Traffic-Intersection Monitor: Sizing, Pipeline Design and Benchmark Plan", title),
      Spacer(1, 2),
      P("<b>Approach.</b> (1) Turn the spec into rates: pixels/s, bytes/s and ops/s for every stage, and "
        "compare each against the block that would run it. (2) Anything above ~70 % of a block's capacity is a "
        "bottleneck; fix it by <i>doing less work</i> (lower resolution, fused passes, model surgery) before "
        "<i>doing it faster</i>. (3) Map each stage to the cheapest unit that meets its p99 slice of the latency "
        "budget, then pipeline the two streams across GPU/NPU/CPU/VPU. (4) Define benchmarks that confirm or "
        "overturn every assumed number. All arithmetic is in <font face='DV-B'>analysis/calc.py</font> of the "
        "accompanying repository, so each figure can be re-derived.", body)]

S += [P("0. Assumptions", h1)]
assume = [
    ["#", "Assumption (and why it is needed)"],
    ["A1", "Cameras deliver <b>processed</b> NV12 5120x4096@30 over MIPI-CSI; the SoC ISP is used as a capture/DMA "
           "path in bypass. Its 1920x1080@60 processing limit is ~5x below the input rate, so it cannot process these frames."],
    ["A2", "The encoded output is the <b>undistorted 1280x1024@30</b> frame per stream (5:4, /4 per axis). Full-resolution "
           "encode is impossible: 1258 MP/s vs 249 MP/s VPU capacity, and 81,920 macroblocks exceeds H.264 level 5.2."],
    ["A3", "Latency starts at <b>start of sensor readout</b> (conservative: includes 33.3 ms frame transfer) and ends when the "
           "last NAL unit of that frame leaves the encoder. Network transit is excluded."],
    ["A4", "8.5 GFLOPs = 2 x MACs. 8,400 candidates = 80<super>2</super>+40<super>2</super>+20<super>2</super> (anchor-free, "
           "strides 8/16/32). 80 COCO classes in the head; the product uses 6 (person, bicycle, car, motorbike, bus, truck)."],
    ["A5", "NPU sustains ~35 % of peak on a YOLO-class net. 7 MB INT8 weights and ~40 MB of activations spill to DDR per "
           "inference (1 MB SRAM is far smaller than the tensors). One engine gets ~8 GB/s of the 18 GB/s sustained DDR."],
    ["A6", "OpenCL can import DMA-BUF (e.g. cl_arm_import_memory); V4L2 capture and the V4L2-M2M encoder take DMA-BUF. "
           "The NPU SDK allows cutting the graph at named tensors. PTQ runs in the SDK; fine-tuning runs offline in PyTorch."],
    ["A7", "CPU rates (OpenCV remap ~250 MP/s per A78 core, NV12->RGB ~800 MP/s per core) are estimates; Task 3 L0 "
           "benchmarks replace them. Lens maps are static (from calibration). cpu0-3 = A55, cpu4-7 = A78; kernel built with PREEMPT_RT."],
]
S += [T(assume, [0.04, 0.96])]

# ============================================================== TASK 1
S += [P("Task 1. Compute demand, latency, bottlenecks and remedies", h1),
      P("1.1 Demand vs capacity (both streams, 60 frames/s total)", h2)]
dem = [
    ["Quantity", "Demand", "Capacity / verdict"],
    ["Input pixel rate", "2 x 20.97 MP x 30 = <b>1,258 MP/s</b>; NV12 frame 31.5 MB",
     "ISP out 249 MP/s, VPU 249 MP/s: <b>5.1x over</b> both -> must downscale (A1, A2)"],
    ["Capture write to DDR", "31.5 MB x 60 = 1.89 GB/s", "10 % of 18 GB/s sustained: OK, but unavoidable"],
    ["Naive chain DDR (CPU/OpenCV at full res: remap with float map, cvtColor, resize, full-res encode)",
     "522 MB/frame -> <b>31.3 GB/s</b> (the float remap map alone is 168 MB/frame)",
     "<b>174 % of sustained, 122 % of peak</b>: infeasible"],
    ["Naive CPU for undistort + CSC", "7.6 + 1.6 = <b>9.1 A78 cores</b>", "4 A78 available: infeasible"],
    ["Detector compute", "8.5 GOP x 60 = <b>510 GOPS</b>",
     "NPU: 6.4 % of 8 TOPS (OK). GPU FP16 at 30 % util: 28 ms/inf = 170 % busy. 4xA78 SDOT: 100 % of peak. Only the NPU fits"],
    ["NPU per inference", "compute 3.0 ms; memory 48 MB -> 6.0 ms",
     "<b>memory-bound</b>, ~7.5 ms incl. setup -> 45 % busy at 60 inf/s"],
    ["SiLU + decode on NPU", "SiLU, Sigmoid, box math unsupported -> CPU fallback",
     "~57 SiLU = ~114 NPU<->CPU switches (~34 ms) + 22 ms CPU math = <b>~56 ms/inference</b>: breaks latency and fps"],
    ["NMS worst case", "8,400 boxes -> 35 M IoU pairs (~35 ms)", "p99 hazard; with top-K 1,000: 0.5 M pairs, ~0.5 ms"],
    ["Tracking", "100 objects: Kalman 8-state + Hungarian (100<super>3</super> = 1 M ops)", "<1 ms on one A78: not a concern"],
]
S += [T(dem, [0.2, 0.36, 0.44])]
S += [P("<b>First-cut latency of the naive design</b> (A78s, OpenCV, NPU with fallback): readout 33 + remap 31 + "
        "CSC/resize 12 + NPU with SiLU fallback 56 + NMS worst case 35 + encode (not possible at 5120x4096) "
        "= <b>&gt;167 ms, and it cannot sustain 30 fps</b>. The requirement (100 ms mean / 150 ms p99) needs "
        "structural changes, not tuning.", body)]

S += [P("1.2 Bottlenecks, ranked by impact", h2)]
bn = [
    ["#", "Bottleneck", "Root cause"],
    ["B1", "Resolution mismatch with ISP and VPU", "2 x 21 MP @ 30 is 5x the ISP and encoder pixel rate. The spec as written cannot be met at full resolution."],
    ["B2", "DDR bandwidth", "Full-resolution intermediates (undistorted NV12, RGB888) plus an 8 B/px float map. Remap is a gather, so cache lines are over-fetched."],
    ["B3", "NPU operator coverage", "SiLU, Sigmoid, decode arithmetic (and Split/Softmax in C2f/DFL variants) fall back to CPU. Each switch costs sync + cache maintenance."],
    ["B4", "CPU pixel processing", "Undistort and colour conversion at 1.26 GP/s need ~9 big cores. They also thrash the shared 2 MB L3 that post-processing needs."],
    ["B5", "NPU memory traffic", "1 MB SRAM vs 7 MB weights: weights and activations stream from DDR each inference, so the NPU is memory-bound."],
    ["B6", "Tail latency (p99)", "Data-dependent NMS, both streams arriving at the NPU together, DVFS/thermal throttling, I-frame size spikes."],
]
S += [T(bn, [0.04, 0.22, 0.74])]

S += [P("1.3 Remedies to raise throughput and cut latency", h2)]
rem = [
    ["Remedy", "Fixes", "Effect (from calc.py)"],
    ["<b>Downscale early.</b> Undistort once, straight to 1280x1024 (2x2 average + bilinear on a sparse 16-px map grid). "
     "Derive the 640x640 tensor from that buffer, not from the full frame.", "B1 B2 B4",
     "DDR 31.3 -> <b>7.7 GB/s</b> (43 % of sustained). Map 168 MB -> 42 KB. If the camera supports 2x2 binning: 4.6 GB/s"],
    ["<b>Fuse stages 2-4 on the GPU</b> (2 kernels, DMA-BUF in/out, zero CPU copies). Fold normalisation into input "
     "quantisation: scale 1/255, zero-point 0, so raw uint8 RGB <i>is</i> the INT8 tensor.", "B2 B4",
     "~5.7 ms GPU per frame, 34 % GPU busy. No full-res RGB is ever written"],
    ["<b>Make the model NPU-native.</b> SiLU->ReLU with distillation from the FP32 SiLU teacher. Split->1x1 conv/Concat. "
     "Cut the graph before Sigmoid/decode. Keep box and class outputs separate (own quant scales).", "B3",
     "One NPU partition: ~56 ms -> <b>~7.5 ms</b>. Accuracy managed in 2.3"],
    ["<b>Cheap decode and bounded NMS.</b> Threshold on raw logits (sigmoid is monotonic, so compare against "
     "logit(0.25) = -1.1). Top-K 1,000 via nth_element. Class-offset NMS.", "B6", "Worst case 35 ms -> &lt;1 ms; sigmoid only on survivors"],
    ["<b>Pipeline across units and phase-shift the cameras</b> by T/2 = 16.7 ms (trigger/frame-sync). The two streams "
     "never queue on the NPU/GPU at the same time.", "B6", "No NPU queueing in the mean case (Fig. 2)"],
    ["<b>Determinism.</b> Pre-allocated CMA pools, PREEMPT_RT, isolated cores, fixed clocks/DDR devfreq floor, "
     "encoder intra-refresh instead of periodic I-frames.", "B6", "Removes allocation, migration and DVFS jitter from p99"],
]
S += [T(rem, [0.58, 0.08, 0.34])]

# ============================================================== TASK 2
S += [CondPageBreak(9 * cm), P("Task 2. Workload mapping and pipeline design", h1),
      P("2.1 Data flow", h2),
      fig("figures/fig1_pipeline.png", 770 / 2288,
          "Figure 1 - Per-stream data flow, compute-unit mapping and buffer sizes. Only DMA-BUF handles move between "
          "blocks. The undistorted display buffer from Pass A is held (by frame ID) until tracks arrive, so the overlay "
          "is drawn on the frame the detections came from."),
      P("<b>Key data-flow choices.</b> (i) Undistort <i>once</i>, at output resolution. The detector input is a 2x "
        "downscale of the same buffer, so box coordinates map back with one scale and a 64-px offset. "
        "(ii) 5:4 frames letterbox to 640x512 + 64 px pad top and bottom (pad value 114, as in YOLO training). "
        "(iii) <i>Rejected:</i> detecting on the distorted image and undistorting only the boxes. That is cheaper, "
        "but the wide-angle edges hurt a rectilinear-trained detector, and the overlay needs an undistorted frame anyway.")]

S += [P("2.2 Compute-unit allocation and justification", h2)]
mp = [
    ["Stage", "Unit", "Alternatives and why rejected", "Selection criteria met"],
    ["1 Capture", "CSI/ISP DMA", "-", "Hardware DMA into DMA-BUF; zero CPU load"],
    ["2 Undistort (+ downscale)", "GPU (Pass A)", "ISP: no LDC. NPU: no gather op. CPU: 7.6 cores, L3 thrash",
     "Texture sampler does bilinear gathers in hardware; bandwidth-bound ~4.7 ms"],
    ["3-4 CSC, letterbox, normalise", "GPU (Pass B)", "NPU 1x1-conv CSC needs chroma upsampling first. CPU: extra copy",
     "Fused into one kernel on a 2 MB input, &lt;1 ms. Output is NPU-ready (64-B aligned, contiguous)"],
    ["5 Detection", "NPU INT8", "GPU FP16: 170 % busy. CPU: 100 % of peak",
     "Only unit with &gt;2x headroom (45 % busy); lowest energy per inference"],
    ["6 Decode + NMS", "CPU A78", "NPU: no sigmoid/sort. GPU: launch overhead is larger than the work",
     "Branchy, data-dependent, &lt;1 MB: ideal for a big core plus NEON"],
    ["7 Tracking", "CPU A78", "-", "Sequential, tiny (100 objects), needs cache-resident state"],
    ["8 Overlay", "CPU A78 (post thread)", "GPU: an extra kernel launch and sync for ~100 boxes",
     "~1 ms; same thread as tracking (data already in cache); DMA_BUF_IOCTL_SYNC brackets the writes"],
    ["9 Encode + stream", "VPU + A55", "Software x264: several cores", "2 x 1280x1024@30 = 32 % of VPU capacity; GStreamer rtph264pay on A55"],
]
S += [T(mp, [0.15, 0.11, 0.37, 0.37])]

S += [P("2.3 Detector adaptation (needed to make the NPU mapping work) and accuracy plan", h2),
      B("<b>Graph surgery:</b> SiLU->ReLU (ReLU6 if range clipping helps INT8). Split->two 1x1 convs (or C3-style Concat). "
        "Upsample stays Resize-nearest (supported). Cut after the last head convs and export 6 tensors (box and class, x3 scales). "
        "Result: the whole backbone, neck and head run in a single NPU partition."),
      B("<b>Accuracy budget (&le;1.0 mAP@0.5 vs FP32 reference):</b> &le;0.5 for the activation swap (recover with "
        "fine-tuning and distillation from the FP32 SiLU teacher on COCO plus site data), &le;0.5 for INT8. "
        "PTQ calibration uses 500-1,000 <i>undistorted, letterboxed site frames</i> (day/night/rain), with per-channel weights."),
      B("<b>Fallbacks if over budget:</b> run the 2-3 most sensitive layers (stem, final head convs) in FP16 on the NPU "
        "(2 TOPS FP16 supported; ~+1 ms); then QAT in PyTorch exported with Q/DQ nodes, if the SDK accepts them.")]

S += [P("2.4 Thread structure and scheduling policy", h2)]
th = [
    ["Thread", "Core", "Policy / prio", "Work per frame", "Wakes on"],
    ["T_cap (both cams)", "cpu1 (A55)", "FIFO 80", "VIDIOC_DQBUF, timestamp, frame ID, push fd", "V4L2 poll()"],
    ["T_gpu", "cpu4 (A78)", "FIFO 70", "Enqueue Pass A+B on an in-order OpenCL queue; wait on cl_event", "capture queue"],
    ["T_npu (single owner)", "cpu5 (A78)", "FIFO 70", "EDF across both streams by capture timestamp; run inference", "tensor queue"],
    ["T_post_A / T_post_B", "cpu6 / cpu7", "FIFO 60", "Decode, NMS, track, overlay; push display fd to encoder", "NPU done fence"],
    ["T_enc + T_net", "cpu2 (A55)", "FIFO 65 / 50", "V4L2-M2M QBUF/DQBUF; RTP/RTSP send; JSON counts", "overlay queue"],
    ["T_mon, logging, OTA", "cpu3 (A55)", "SCHED_OTHER", "Telemetry, health, watchdog kick, trace flush", "1 Hz timer"],
    ["IRQs, kernel work", "cpu0 (A55)", "irq affinity", "CSI, GPU, NPU, VPU, Ethernet interrupts", "-"],
]
S += [T(th, [0.17, 0.11, 0.11, 0.43, 0.18])]
S += [B("<b>Why this shape:</b> one RT thread per isolated big core (isolcpus=4-7, nohz_full, rcu_nocbs), so stages never "
        "preempt each other. Priorities only protect against background work. Accelerators run asynchronously; "
        "threads block on fences, not busy-polls. The A78 L2s stay warm for the post-processing threads."),
      B("<b>Hand-off:</b> lock-free SPSC rings of depth 2 carrying {dma-buf fd, frame ID, timestamps}. If the NPU input ring "
        "is full, <i>drop the oldest</i> inference request: video is still encoded, using Kalman-predicted tracks. "
        "Throughput holds and latency stays bounded under overload."),
      B("<b>Policy:</b> SCHED_FIFO on PREEMPT_RT with mlockall and no allocation after start-up. "
        "SCHED_DEADLINE (runtime 10 ms / period 33.3 ms) is a drop-in alternative for T_npu if a third workload ever "
        "shares the core. Performance governor on A78, DDR devfreq floor, thermal headroom monitored by T_mon.")]

S += [P("2.5 Latency budget and throughput justification", h2)]
lb = [
    ["Stage (unit)", "Mean ms", "p99 ms", "Basis"],
    ["Sensor readout / CSI transfer", "33.3", "33.3", "1/30 s, fixed (A3)"],
    ["DQBUF + hand-off (A55)", "0.5", "2.0", "RT thread, IRQ on cpu0"],
    ["GPU Pass A + B", "5.7", "9.5", "~43 MB moved at ~8 GB/s; p99 under DDR contention (+65 %)"],
    ["NPU queue wait", "2.0", "8.0", "Phase-shifted streams: ~0 nominal; p99 = one full inference of the other stream"],
    ["NPU inference", "7.5", "11.0", "Memory-bound estimate (1.1)"],
    ["Decode + NMS / track / overlay (A78)", "2.8", "6.5", "Top-K bounded; 100 objects; dma-buf sync"],
    ["H.264 encode (VPU)", "8.0", "12.0", "1.3 MP frame, low-delay P, intra-refresh (no I-frame spikes)"],
    ["OS / scheduling slack", "0.3", "10.0", "Reserve for preemption, cache maintenance, thermal"],
    ["<b>Total (start of readout -> encoded)</b>", "<b>60.1</b>", "<b>92.3</b>", "<b>Target 100 / 150 ms: 40 % and 38 % margin</b>"],
]
S += [T(lb, [0.31, 0.08, 0.08, 0.53])]
S += [fig("figures/fig2_timeline.png", 605 / 2288,
          "Figure 2 - Pipelined schedule (mean times) for 4 frames of each stream. Stream B is phase-shifted by 16.7 ms, so "
          "GPU, NPU and VPU serve the two streams alternately without queueing. Each stage is much shorter than "
          "the 33.3 ms frame period, so throughput is set by the busiest unit, not by the sum of the stages."),
      P("<b>Throughput.</b> Unit loads at 60 frames/s: NPU 45 %, GPU 34 %, VPU 32 % of pixel rate, each post "
        "core ~8 %, DDR 43 % of sustained (7.7 GB/s). The busiest unit (NPU) leaves ~2.2x headroom, so 30 fps per stream "
        "is sustainable. The p99 column is a sum of per-stage p99s, which is pessimistic because tails rarely coincide. "
        "Even so, it stays under 150 ms. Latency measured from capture-complete is ~27 ms mean.", body)]

# ============================================================== TASK 3
S += [CondPageBreak(6 * cm), P("Task 3. Benchmark methodology", h1),
      P("<b>Goal:</b> replace every assumed number in Tasks 1-2 with a measured one, choose the compute unit "
        "for each stage on evidence, and prove the product requirements on the target board. "
        "The plan runs in four levels, from isolated to whole-system (Fig. 3). A candidate that fails a level does not move on.", body),
      fig("figures/fig3_benchmark.png", 253 / 2288,
          "Figure 3 - Benchmark levels. L0 picks candidates; L1 removes those that only win in isolation; L2 proves "
          "the requirements; L3 proves accuracy; CI guards against regressions."),
      P("3.1 Variables: what we vary, what we hold fixed (dependencies), what we measure", h2)]
var = [
    ["Type", "Items"],
    ["Independent (varied)", "Compute unit (A78 x1/x4, A55, GPU, NPU, VPU); implementation (OpenCV vs OpenCL image vs buffer; full vs sparse map; "
     "kernel work-group size); model variant (FP32-SiLU ref, FP32-ReLU, INT8 PTQ, INT8+FP16 mixed); stream count (1, 2); "
     "scene load (0 / 30 / 100 / 150 objects; synthetic 8,400 candidates); clocks (fixed vs production DVFS)"],
    ["Controlled dependencies (pinned and recorded with every result)", "Kernel/RT config, NPU SDK, OpenCL driver, GStreamer and firmware versions; CPU/GPU/NPU/DDR "
     "frequencies and governors; thermal state (enclosure fitted, 25 &deg;C and 45 &deg;C ambient, start after steady state); "
     "core affinity, IRQ affinity; identical input bytes (recorded sequences replayed through the same DMA-BUF path); background load"],
    ["Dependent (metrics)", "See 3.2"],
]
S += [T(var, [0.2, 0.8])]

S += [P("3.2 Metrics", h2)]
met = [
    ["Metric", "Definition / tool", "Pass criterion"],
    ["E2E latency", "Capture timestamp carried as frame ID in an H.264 SEI message; delta to encoder output. Mean, p50, p99, p99.9, max", "&le;100 mean, &le;150 p99"],
    ["Per-stage latency", "CLOCK_MONOTONIC at each hand-off; OpenCL event profiling; NPU SDK profiler; ftrace/Perfetto", "Within its 2.5 slice at p99"],
    ["Throughput, drops", "Output fps per stream over a 1 h soak; dropped inference/video frames; inter-frame jitter (std)", "30.0 fps, 0 video drops"],
    ["Utilisation", "Per-core CPU (/proc/stat, perf); GPU/NPU busy (vendor counters, devfreq); VPU load", "&le;70 % each unit"],
    ["DDR bandwidth", "Memory-controller PMU (perf uncore / devfreq-event), per master where available", "&le;60 % of 18 GB/s"],
    ["Power, thermal", "Board rail shunt (INA2xx) -> mJ/frame; SoC temperatures; throttle events", "0 throttle events at 45 &deg;C"],
    ["Memory", "CMA used, RSS, fd count over the soak (leak check)", "Flat after warm-up"],
    ["Accuracy", "mAP@0.5 on held-out site set vs FP32 reference (same pre-processing); per class; MOTA/IDF1; count error", "Drop &le;1.0 mAP"],
    ["Video quality", "PSNR/SSIM vs the uncompressed overlay frame at the chosen bitrate", "Fit for operators (&ge;36 dB)"],
]
S += [T(met, [0.14, 0.64, 0.22])]

S += [P("3.3 Hardware-selection benchmarks per stage", h2)]
sel = [
    ["Stage", "Candidates benchmarked", "Inputs / sweep", "Deciding measurements"],
    ["Undistort + scale", "CPU OpenCV remap (fixed-point maps, 1/4 thr); GPU image-sampler vs buffer; full vs sparse map",
     "5120x4096 -> 1280x1024, 1 and 2 streams", "p99 ms under L1 load; DDR GB/s; mJ/frame; L3 miss rate"],
    ["CSC + letterbox", "CPU NEON; GPU fused; NPU 1x1-conv", "1280x1024 NV12 -> 640x640", "ms, extra copies, NPU time stolen"],
    ["Detector", "NPU INT8; NPU mixed; GPU FP16; CPU INT8 (Arm NN)", "4 model variants", "ms, #partitions, fallback ops, mAP, mJ/inference"],
    ["Decode + NMS", "A78 1 thread; A55; GPU", "100 / 1,000 / 8,400 candidates", "p99.9 ms (worst case matters)"],
    ["Tracker, overlay", "A78; A55", "0-150 objects", "p99 ms, cache misses"],
    ["Encode", "VPU settings: GOP, intra-refresh, slices, rate control", "Static and busy scenes", "p99 encode ms, bitrate, PSNR"],
]
S += [T(sel, [0.12, 0.38, 0.2, 0.3])]

S += [P("3.4 Procedure and decision rule", h2),
      B("<b>Statistical hygiene:</b> discard 300 warm-up frames. Use &ge;10,000 frames per point, so at least 100 samples lie "
        "beyond p99, and a 1 h soak (108k frames/stream) for p99.9. Run 5 repetitions and report the median with a 95 % CI. "
        "Tracing must add &lt;1 % overhead (ring-buffer tracing, no printf in the hot path)."),
      B("<b>Inputs:</b> recorded site sequences (day, night, rain, glare, rush hour with &ge;100 objects, empty road) replayed "
        "byte-identically for A/B comparisons, plus synthetic stress (8,400 candidates, max motion). "
        "Final sign-off uses live cameras."),
      B("<b>Contention is mandatory (L1):</b> each candidate is re-measured while the other units run their real workload "
        "or a DDR stress kernel. Shared DDR and L3 are this SoC's main coupling, and isolated numbers overstate the headroom."),
      B("<b>Decision:</b> (1) hard gates: meets its p99 latency slice under contention, meets the accuracy budget, no "
        "hidden CPU fallback. (2) Rank survivors by a weighted score: 0.4 headroom (1 - utilisation), "
        "0.3 energy per frame, 0.2 DDR traffic, 0.1 implementation risk. Keep the runner-up as the documented fallback. "
        "(3) Re-run the L2 soak with the chosen mapping, then add it to nightly CI (alert on &gt;5 % p99 or &gt;0.2 mAP change).")]

doc = SimpleDocTemplate("docs/Design_Embedded_Platform_Intern.pdf", pagesize=A4,
                        leftMargin=1.35 * cm, rightMargin=1.35 * cm, topMargin=1.1 * cm, bottomMargin=1.25 * cm,
                        title="Dual-Camera Traffic-Intersection Monitor - Design", author="Candidate")
doc.build(S, onFirstPage=footer, onLaterPages=footer)
print("built")
