"""
Back-of-envelope sizing for the Dual-Camera Traffic-Intersection Monitor.

Every number in the design PDF comes from this script, so the reasoning can be
re-checked or re-run with different assumptions (edit the ASSUMPTIONS block).

Run:  python3 analysis/calc.py
"""

MB = 1e6
GB = 1e9

# ----------------------------------------------------------------------------
# ASSUMPTIONS (all stated in the PDF, section 0)
# ----------------------------------------------------------------------------
W, H, FPS, STREAMS = 5120, 4096, 30, 2
NV12_BPP = 1.5                    # bytes / pixel
OUT_W, OUT_H = 1280, 1024         # undistorted display / encode resolution (5:4, /4)
MODEL = 640                       # detector input
GFLOP_PER_INF = 8.5               # given (assumed = 2 x MACs)
PARAMS = 7e6                      # given -> 7 MB INT8 weights
NPU_PEAK_TOPS = 8.0
NPU_UTIL = 0.35                   # realistic utilisation for a YOLO-class net
NPU_ACT_TRAFFIC_MB = 40           # activation spill per inference (1 MB SRAM << tensors)
GPU_FP16_TFLOPS = 1.0
GPU_CNN_UTIL = 0.30
REMAP_OVERFETCH = 1.2             # gather on a distorted grid fetches extra lines
DDR_SUSTAINED = 18 * GB
DDR_PEAK = 25.6 * GB
ISP_CAP_PX_S = 2 * 1920 * 1080 * 60      # 2 inputs x 1080p60
ENC_CAP_PX_S = 3840 * 2160 * 30          # 4K30 (== 2 x 1080p60 ~ same px/s)
CPU_REMAP_MPX_S_PER_A78 = 250e6          # OpenCV remap bilinear, 1 A78 core, NEON (assumed)
CPU_CVT_MPX_S_PER_A78 = 800e6            # NV12->RGB, 1 A78 core (assumed)

px = W * H
frame_nv12 = px * NV12_BPP
fr_total = FPS * STREAMS


def line(name, v, unit=""):
    print(f"  {name:<52s} {v:>12,.2f} {unit}")


print("== 1. Raw input ==")
line("pixels / frame (MP)", px / 1e6, "MP")
line("NV12 frame size", frame_nv12 / MB, "MB")
line("pixel rate, both streams", px * fr_total / 1e6, "MP/s")
line("raw capture write bandwidth, both streams", frame_nv12 * fr_total / GB, "GB/s")
line("ISP output capacity (2 x 1080p60)", ISP_CAP_PX_S / 1e6, "MP/s")
line("-> demand / ISP capacity", px * fr_total / ISP_CAP_PX_S, "x")
line("Encoder capacity (4K30)", ENC_CAP_PX_S / 1e6, "MP/s")
line("-> full-res encode demand / encoder capacity", px * fr_total / ENC_CAP_PX_S, "x")

print("\n== 2. Naive pipeline DDR traffic (CPU/OpenCV, full resolution) ==")
map_bytes = px * 8                     # CV_32FC2 float map at full res
naive = {
    "1 capture write": frame_nv12,
    "2 remap: read src (x overfetch)": frame_nv12 * REMAP_OVERFETCH,
    "2 remap: read float map (8 B/px)": map_bytes,
    "2 remap: write undistorted NV12": frame_nv12,
    "3 cvtColor: read NV12": frame_nv12,
    "3 cvtColor: write RGB888": px * 3,
    "4 resize: read RGB888": px * 3,
    "4 resize: write 640x640x3": MODEL * MODEL * 3,
    "8 overlay (touch boxes, ~1%)": frame_nv12 * 0.01,
    "9 encoder read + refs (x3)": frame_nv12 * 3,
}
tot = 0
for k, v in naive.items():
    line(k, v / MB, "MB/frame")
    tot += v
line("TOTAL per frame (excl. NN)", tot / MB, "MB")
naive_bw = tot * fr_total
line("TOTAL both streams", naive_bw / GB, "GB/s")
line("-> % of sustained DDR (18 GB/s)", 100 * naive_bw / DDR_SUSTAINED, "%")

print("\n== 3. Naive CPU compute for stages 2-3 ==")
remap_cores = px * NV12_BPP * fr_total / CPU_REMAP_MPX_S_PER_A78
cvt_cores = px * fr_total / CPU_CVT_MPX_S_PER_A78
line("A78 cores needed for remap", remap_cores, "cores")
line("A78 cores needed for NV12->RGB", cvt_cores, "cores")
line("available big cores", 4, "cores")

print("\n== 4. Detector compute ==")
gops = GFLOP_PER_INF * fr_total
line("required (both streams)", gops, "GOPS")
line("NPU INT8 peak utilisation needed", 100 * gops / (NPU_PEAK_TOPS * 1e3), "%")
t_npu_compute = GFLOP_PER_INF / (NPU_PEAK_TOPS * 1e3 * NPU_UTIL) * 1e3
npu_bytes = PARAMS + NPU_ACT_TRAFFIC_MB * MB + MODEL * MODEL * 3
t_npu_mem = npu_bytes / (8 * GB) * 1e3   # NPU's achievable share of DDR
line("NPU compute time @35% util", t_npu_compute, "ms")
line("NPU memory time (weights+acts @ 8 GB/s)", t_npu_mem, "ms")
line("NPU DDR traffic per inference", npu_bytes / MB, "MB")
t_npu = max(t_npu_compute, t_npu_mem) + 1.5   # + setup/sync
line("NPU latency estimate (max + 1.5 ms setup)", t_npu, "ms")
line("NPU busy (60 inf/s)", 100 * t_npu * fr_total / 1e3, "%")
t_gpu = GFLOP_PER_INF / (GPU_FP16_TFLOPS * 1e3 * GPU_CNN_UTIL) * 1e3
line("GPU FP16 per inference @30% util", t_gpu, "ms")
line("GPU busy if it ran detection (60 inf/s)", 100 * t_gpu * fr_total / 1e3, "%")
cpu_peak_gops = 4 * 2.0e9 * 64 / 1e9     # 4 x A78, 2x SDOT/cycle (16 MAC each) = 64 ops/cyc
line("4xA78 INT8 SDOT peak", cpu_peak_gops, "GOPS")
line("-> CPU utilisation needed", 100 * gops / cpu_peak_gops, "%")

# SiLU fallback cost
n_silu = 57                  # YOLO-s style backbone+neck activations (approx.)
silu_elems = 22e6            # sum of activation tensor sizes across SiLU layers (approx.)
t_part = 0.3                 # ms per NPU<->CPU partition switch (sync + cache maint.)
t_silu_cpu = silu_elems / 1.0e9 * 1e3   # 1 Gelem/s LUT on one A78
line("SiLU fallback: partition overhead", n_silu * 2 * t_part, "ms/inf")
line("SiLU fallback: CPU elementwise", t_silu_cpu, "ms/inf")
line("SiLU fallback total per inference", n_silu * 2 * t_part + t_silu_cpu, "ms")

print("\n== 5. Optimised pipeline DDR traffic ==")
out_nv12 = OUT_W * OUT_H * NV12_BPP
opt = {
    "1 capture write (full res)": frame_nv12,
    "A GPU undistort+2x2avg+downscale: read src": frame_nv12 * REMAP_OVERFETCH,
    "A sparse map (16px grid, FP32x2)": (OUT_W // 16 + 1) * (OUT_H // 16 + 1) * 8,
    "A write 1280x1024 NV12": out_nv12,
    "B GPU letterbox+RGB: read 1280x1024": out_nv12,
    "B write 640x640x3 uint8 tensor": MODEL * MODEL * 3,
    "5 NPU weights + activations": npu_bytes - MODEL * MODEL * 3,
    "6 head outputs (INT8, 8400 x 84)": 8400 * 84,
    "8 overlay RMW (~5% of frame)": out_nv12 * 0.05 * 2,
    "9 encoder read + refs (x3)": out_nv12 * 3,
}
tot2 = 0
for k, v in opt.items():
    line(k, v / MB, "MB/frame")
    tot2 += v
line("TOTAL per frame", tot2 / MB, "MB")
opt_bw = tot2 * fr_total
line("TOTAL both streams", opt_bw / GB, "GB/s")
line("-> % of sustained DDR", 100 * opt_bw / DDR_SUSTAINED, "%")
# variant: camera / ISP delivers 2560x2048 (binning) -> capture+read 4x smaller
cut = (frame_nv12 + frame_nv12 * REMAP_OVERFETCH) * 0.75
line("variant: sensor 2x2 binning -> both streams", (tot2 - cut) * fr_total / GB, "GB/s")

t_passA = frame_nv12 * REMAP_OVERFETCH / (8 * GB) * 1e3
line("Pass A time (bandwidth bound @ 8 GB/s)", t_passA, "ms")
line("encode px/s (2 x 1280x1024@30) vs cap", 100 * 2 * OUT_W * OUT_H * 30 / ENC_CAP_PX_S, "% of enc")

print("\n== 6. NMS ==")
line("worst-case IoU pairs, 8400 boxes", 8400 ** 2 / 2 / 1e6, "M")
line("  @ ~1 ns/IoU NEON-ish (ms)", 8400 ** 2 / 2 * 1e-6, "ms")
line("with top-K=1000 cap", 1000 ** 2 / 2 / 1e6, "M pairs")
line("  (ms)", 1000 ** 2 / 2 * 1e-6, "ms")
line("class-score scan 8400 x 80 (INT8 compares)", 8400 * 80 / 1e6, "M ops")

print("\n== 7. Memory footprint (CMA) ==")
cma = (STREAMS * 4 * frame_nv12 + STREAMS * 6 * out_nv12 +
       STREAMS * 3 * MODEL * MODEL * 3 + PARAMS + 2 * 8 * MB)
line("capture 4/stream + display 6/stream + tensors 3/stream + model", cma / MB, "MB")
