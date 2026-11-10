"""
Generates the three diagrams used in the design PDF.
  fig1_pipeline.png  - data flow + workload mapping (one stream; x2 in the system)
  fig2_timeline.png  - pipelined schedule of both streams (mean stage times)
  fig3_benchmark.png - benchmark methodology flow
Run:  python3 analysis/figures.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = "figures/"
UNIT_COL = {
    "ISP/CSI": "#d9e8f5", "GPU": "#dff0d8", "NPU": "#fde2c8",
    "CPU A78": "#ece0f5", "CPU A55": "#f3eadb", "VPU": "#f9d9d9",
}
EDGE = "#333333"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})


def box(ax, x, y, w, h, text, unit, fs=7.2, bold_first=True):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=UNIT_COL[unit], ec=EDGE, lw=0.9))
    lines = text.split("\n")
    if bold_first:
        ax.text(x + w / 2, y + h - 0.17, lines[0], ha="center", va="top", fontsize=fs + 0.6,
                weight="bold")
        ax.text(x + w / 2, y + h - 0.45, "\n".join(lines[1:]), ha="center", va="top",
                fontsize=fs, linespacing=1.25)
    else:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)


def arrow(ax, p, q, label=None, style="-|>", ls="-", color=EDGE, lpos=0.5, dy=0.12, rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=9, lw=1.0,
                                 color=color, linestyle=ls,
                                 connectionstyle=f"arc3,rad={rad}"))
    if label:
        mx = p[0] + (q[0] - p[0]) * lpos
        my = p[1] + (q[1] - p[1]) * lpos
        ax.text(mx, my + dy, label, ha="center", va="bottom", fontsize=6.0, color="#222",
                bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.9))


# ---------------------------------------------------------------- Figure 1
def fig1():
    fig, ax = plt.subplots(figsize=(10.4, 3.5))
    ax.set_xlim(0, 20.8); ax.set_ylim(1.3, 7.75); ax.axis("off")
    # lane labels
    lanes = [("ISP/CSI", 6.3), ("GPU", 6.3), ("NPU", 6.3), ("CPU A78", 6.3), ("VPU", 1.4), ("CPU A55", 1.4)]
    W, Hh = 2.6, 1.65
    B = {}
    S = 3.5
    B["cap"] = (0.2, 4.9);  box(ax, *B["cap"], W, Hh, "1  Capture\nCSI/ISP -> DMA-BUF\nNV12 5120x4096\n31.5 MB, 30 fps", "ISP/CSI")
    B["A"] = (0.2 + S, 4.9);   box(ax, *B["A"], W, Hh, "Pass A  (2)\nundistort, sparse map\n+ 2x2 avg, /4 scale\n-> NV12 1280x1024", "GPU")
    B["Bp"] = (0.2 + 2*S, 4.9);   box(ax, *B["Bp"], W, Hh, "Pass B  (3+4)\n640x512 + 64 px pad\nNV12 -> RGB uint8\n(= INT8 input)", "GPU")
    B["npu"] = (0.2 + 3*S, 4.9); box(ax, *B["npu"], W, Hh, "5  Detector INT8\nReLU-YOLO, graph\ncut before decode\n~7.5 ms", "NPU")
    B["nms"] = (0.2 + 4*S, 4.9); box(ax, *B["nms"], W, Hh, "6  Decode + NMS\nlogit threshold,\ntop-K 1000, NMS\n~1 ms", "CPU A78")
    B["trk"] = (0.2 + 5*S, 4.9); box(ax, *B["trk"], W, Hh, "7  Tracker\nKalman + IoU /\nHungarian, <=100 obj\n~0.8 ms", "CPU A78")
    B["ovl"] = (0.2 + 5*S, 1.5); box(ax, *B["ovl"], W, Hh, "8  Overlay\nboxes + IDs on held\n1280x1024 NV12\n~1 ms", "CPU A78")
    B["enc"] = (0.2 + 4*S, 1.5); box(ax, *B["enc"], W, Hh, "9  H.264 encode\nlow-delay P, no B,\nintra-refresh, CBR\n~8 ms", "VPU")
    B["net"] = (0.2 + 3*S, 1.5);  box(ax, *B["net"], W, Hh, "Stream out\nRTP/RTSP + JSON\ncounts / tracks\nover Ethernet", "CPU A55")
    box(ax, 0.2, 1.5, 2*S + W - 0.6, Hh,
        "Buffer pools: pre-allocated CMA, 64-B aligned (~310 MB)\nper stream: capture 4 x 31.5 MB | display 6 x 2 MB | tensor 3 x 1.2 MB\n"
        "every edge = DMA-BUF fd + frame-ID/timestamp, no CPU memcpy\n"
        "bounded SPSC queues (depth 2); NPU input: drop-oldest", "CPU A55", fs=6.9)

    def R(k, dx=W, dy=Hh / 2): return (B[k][0] + dx, B[k][1] + dy)
    def L(k, dy=Hh / 2): return (B[k][0], B[k][1] + dy)
    arrow(ax, R("cap"), L("A"), "31.5 MB")
    arrow(ax, R("A"), L("Bp"), "2 MB")
    arrow(ax, R("Bp"), L("npu"), "1.2 MB")
    arrow(ax, R("npu"), L("nms"), "0.7 MB")
    arrow(ax, R("nms"), L("trk"), "boxes")
    arrow(ax, (B["trk"][0] + W/2, B["trk"][1]), (B["ovl"][0] + W/2, B["ovl"][1] + Hh), "tracks", lpos=0.5, dy=-0.05)
    arrow(ax, L("ovl"), R("enc"), "2 MB")
    arrow(ax, L("enc"), R("net"), "H.264")
    # display buffer held from Pass A to overlay
    arrow(ax, (B["A"][0] + 1.4, B["A"][1]), (B["ovl"][0] + 0.4, B["ovl"][1] + Hh),
          "display buffer held (same frame ID) until tracks arrive", ls="--", color="#2a6a2a",
          lpos=0.45, dy=-0.05, rad=0.08)
    # legend
    x = 0.25
    for u, c in UNIT_COL.items():
        ax.add_patch(FancyBboxPatch((x, 7.2), 0.35, 0.3, boxstyle="round,pad=0.01", fc=c, ec=EDGE, lw=0.6))
        ax.text(x + 0.45, 7.35, u, va="center", fontsize=7.2)
        x += 1.75
    ax.text(20.6, 7.35, "One stream shown; stream B is identical and shares GPU, NPU, VPU",
            ha="right", va="center", fontsize=7.2, style="italic")
    fig.tight_layout(pad=0.1)
    fig.savefig(OUT + "fig1_pipeline.png", dpi=220)
    plt.close(fig)


# ---------------------------------------------------------------- Figure 2
def simulate(n_frames=4):
    T = 1000 / 30
    d = dict(deq=0.5, A=5.0, B=0.7, npu=7.5, post=2.8, enc=8.0)
    free = {"GPU": 0.0, "NPU": 0.0, "VPU": 0.0, "postA": 0.0, "postB": 0.0}
    events, lat = [], {}
    frames = []
    for k in range(n_frames):
        frames.append(("A", k, T * k, T * (k + 1)))
        frames.append(("B", k, T * k + T / 2, T * (k + 1) + T / 2))
    frames.sort(key=lambda f: f[3])
    # stage-by-stage greedy list scheduling in frame-arrival order
    st = {}
    for s, k, r0, r1 in frames:
        events.append(("Sensor " + s, r0, r1, s, k, "readout"))
        t = r1 + d["deq"]
        a0 = max(t, free["GPU"]); a1 = a0 + d["A"] + d["B"]; free["GPU"] = a1
        events.append(("GPU", a0, a1, s, k, "A+B"))
        n0 = max(a1, free["NPU"]); n1 = n0 + d["npu"]; free["NPU"] = n1
        events.append(("NPU", n0, n1, s, k, "det"))
        pk = "post" + s
        p0 = max(n1, free[pk]); p1 = p0 + d["post"]; free[pk] = p1
        events.append(("CPU A78 (" + s + ")", p0, p1, s, k, "post"))
        e0 = max(p1, free["VPU"]); e1 = e0 + d["enc"]; free["VPU"] = e1
        events.append(("VPU", e0, e1, s, k, "enc"))
        lat[(s, k)] = (r0, e1)
    return events, lat


def fig2():
    events, lat = simulate(4)
    rows = ["Sensor A", "Sensor B", "GPU", "NPU", "CPU A78 (A)", "CPU A78 (B)", "VPU"]
    col = {"A": "#4c78a8", "B": "#f58518"}
    fig, ax = plt.subplots(figsize=(10.4, 2.75))
    for (r, t0, t1, s, k, lab) in events:
        y = len(rows) - 1 - rows.index(r)
        alpha = 0.35 if lab == "readout" else 0.9
        ax.barh(y, t1 - t0, left=t0, height=0.62, color=col[s], alpha=alpha, ec="white", lw=0.5)
        if t1 - t0 > 4:
            ax.text((t0 + t1) / 2, y, f"{s}{k}", ha="center", va="center", fontsize=6.3,
                    color="black" if lab == "readout" else "white")
    ax.set_yticks(range(len(rows))); ax.set_yticklabels(rows[::-1], fontsize=7.5)
    ax.set_xlim(0, 175); ax.set_xlabel("time (ms) - mean stage durations, stream B phase-shifted by T/2 = 16.7 ms", fontsize=7.5)
    ax.tick_params(axis="x", labelsize=7)
    for x in range(0, 176, 33):
        pass
    # annotate latency of A1
    r0, e1 = lat[("A", 1)]
    y = len(rows) - 0.25
    ax.annotate("", xy=(e1, y), xytext=(r0, y), arrowprops=dict(arrowstyle="<->", lw=0.9))
    ax.text((r0 + e1) / 2, y + 0.12, f"A1, ideal schedule (no queueing/slack): start-of-readout -> encoded = {e1 - r0:.1f} ms "
            f"(capture-complete -> encoded = {e1 - r0 - 33.3:.1f} ms)", ha="center", va="bottom", fontsize=7)
    ax.set_ylim(-0.6, len(rows) + 0.5)
    ax.grid(axis="x", ls=":", lw=0.5)
    for sp in ["top", "right"]: ax.spines[sp].set_visible(False)
    fig.tight_layout(pad=0.2)
    fig.savefig(OUT + "fig2_timeline.png", dpi=220)
    plt.close(fig)
    return lat


# ---------------------------------------------------------------- Figure 3
def fig3():
    fig, ax = plt.subplots(figsize=(10.4, 1.15))
    ax.set_xlim(0, 20.8); ax.set_ylim(0, 2.2); ax.axis("off")
    steps = [
        ("L0 Micro-bench", "each stage x each\ncandidate unit, isolated,\nfixed clocks, real shapes"),
        ("L1 Contention", "same stage while other\nunits load DDR/L3\n(stress kernels, 2nd stream)"),
        ("L2 System soak", "2 live/replayed streams,\n>=1 h, thermal steady,\nper-stage timestamps"),
        ("L3 Quality", "mAP@0.5 vs FP32 ref,\nMOTA/IDF1, count error,\nencode PSNR/bitrate"),
        ("Decide", "gate: p99 budget + accuracy;\nthen rank: energy/frame,\nDDR GB/s, headroom"),
        ("Regress (CI)", "nightly replay on target;\nalert on >5% p99 or\n>0.2 mAP change"),
    ]
    w, gap = 3.05, 0.42
    for i, (h, t) in enumerate(steps):
        x = 0.1 + i * (w + gap)
        ax.add_patch(FancyBboxPatch((x, 0.05), w, 2.1, boxstyle="round,pad=0.02,rounding_size=0.1",
                                    fc="#eef3f8" if i < 4 else "#fdf1e3", ec=EDGE, lw=0.9))
        ax.text(x + w / 2, 2.05, h, ha="center", va="top", fontsize=8.2, weight="bold")
        ax.text(x + w / 2, 1.55, t, ha="center", va="top", fontsize=7.0, linespacing=1.3)
        if i < len(steps) - 1:
            arrow(ax, (x + w, 1.1), (x + w + gap, 1.1))
    fig.tight_layout(pad=0.05)
    fig.savefig(OUT + "fig3_benchmark.png", dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    fig1()
    lat = fig2()
    fig3()
    for k, (r0, e1) in sorted(lat.items(), key=lambda x: x[1][0]):
        print(k, f"readout-start->enc {e1 - r0:.1f} ms, capture-complete->enc {e1 - r0 - 33.3:.1f} ms")
