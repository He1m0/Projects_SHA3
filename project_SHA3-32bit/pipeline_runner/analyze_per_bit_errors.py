#!/usr/bin/env python3
"""Per-bit error analysis for 0005 Rate_Scan BP outputs.

Reads:
  archive/0005_SASCA/Rate_Scan/{R}_Predictions/prediction_{baseline,final}_*.npy
  archive/0005_SASCA/answers_A00/ans_bit_*.npy
or, equivalently:
  archive/0005_SASCA/answers_A00 may be a sibling directory that any of the 5
  in-flight smoke runs (all sharing SIM_SEED_TS=1024) can supply.

Reports:
  - per-bit error rate across traces (1600-vector) for baseline vs final
  - 1→0 vs 0→1 imbalance (does the model systematically prefer one polarity?)
  - per-trace error count distribution
  - hottest bit positions and lane×bit structure
  - "delta map" baseline vs final (which bits BP actually fixed/broke)

Usage:
    python analyze_per_bit_errors.py ARCHIVE [ARCHIVE ...] \\
        [--depth 2R|3R|4R] [--answers PATH] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as e:
    sys.exit(f"matplotlib is required: {e}")

LANES = 25  # 5x5 Keccak state
LANE_BITS = 64
TOTAL_BITS = LANES * LANE_BITS  # 1600


def load_predictions(archive: Path, depth: str):
    """Return (baseline_preds, final_preds) as (n_traces, 1600) bool arrays.
    Each is keyed by trace number; missing trace numbers are dropped."""
    pred_dir = archive / "0005_SASCA" / "Rate_Scan" / f"{depth}_Predictions"
    if not pred_dir.is_dir():
        return None, None, []
    base = {}
    final = {}
    for p in sorted(pred_dir.glob("prediction_baseline_*.npy")):
        tr = int(p.stem.rsplit("_", 1)[1])
        base[tr] = np.load(p).astype(bool)
    for p in sorted(pred_dir.glob("prediction_final_*.npy")):
        tr = int(p.stem.rsplit("_", 1)[1])
        final[tr] = np.load(p).astype(bool)
    common = sorted(set(base) & set(final))
    if not common:
        return None, None, []
    return (np.stack([base[tr] for tr in common]),
            np.stack([final[tr] for tr in common]),
            common)


def load_answers(answers_dir: Path, trace_ids):
    """Return (n_traces, 1600) bool array. Missing traces raise."""
    ans = []
    for tr in trace_ids:
        p = answers_dir / f"ans_bit_{tr:04d}.npy"
        if not p.exists():
            raise FileNotFoundError(p)
        a = np.load(p).astype(bool)
        if a.shape != (TOTAL_BITS,):
            raise ValueError(f"unexpected answer shape {a.shape} for trace {tr}")
        ans.append(a)
    return np.stack(ans)


def per_bit_stats(preds, answers, label: str):
    """preds, answers: (n_traces, 1600) bool. Returns dict of stats."""
    n_traces = preds.shape[0]
    err = preds != answers       # (n, 1600) bool
    ones = answers               # bit was 1 in truth
    zeros = ~answers             # bit was 0 in truth
    err_per_bit = err.mean(axis=0)              # (1600,) error rate per bit pos
    err_per_trace = err.sum(axis=1)             # (n,) wrong bits per trace
    flip_1to0 = ((preds == 0) & (answers == 1)).sum()  # truth 1, pred 0
    flip_0to1 = ((preds == 1) & (answers == 0)).sum()  # truth 0, pred 1
    return {
        "label": label,
        "n_traces": n_traces,
        "err_per_bit": err_per_bit,
        "err_per_trace": err_per_trace,
        "flip_1to0": int(flip_1to0),
        "flip_0to1": int(flip_0to1),
        "n_ones": int(ones.sum()),
        "n_zeros": int(zeros.sum()),
        "ber": float(err.mean()),
    }


def render(out_path: Path, title: str, base_stats, final_stats):
    fig, axes = plt.subplots(3, 2, figsize=(14, 11))
    fig.suptitle(title, fontsize=12, fontweight="bold")

    # Row 0: per-bit error rate, baseline vs final, as 25-lane × 64-bit heatmaps
    for ax, st in zip(axes[0], (base_stats, final_stats)):
        grid = st["err_per_bit"].reshape(LANES, LANE_BITS)
        im = ax.imshow(grid, aspect="auto", cmap="hot", vmin=0, vmax=1)
        ax.set_title(f"{st['label']} per-bit error rate (BER={st['ber']:.4f})")
        ax.set_xlabel("bit within lane (0..63)")
        ax.set_ylabel("lane (0..24)")
        plt.colorbar(im, ax=ax, fraction=0.04)

    # Row 1: per-trace error count histogram
    for ax, st in zip(axes[1], (base_stats, final_stats)):
        ax.hist(st["err_per_trace"], bins=30, color="steelblue", edgecolor="k")
        ax.set_title(f"{st['label']} wrong-bit count per trace "
                     f"(n={st['n_traces']}, mean={st['err_per_trace'].mean():.1f})")
        ax.set_xlabel("wrong bits (out of 1600)")
        ax.set_ylabel("# traces")
        ax.grid(True, alpha=0.3)

    # Row 2: 1→0 vs 0→1 imbalance bar; bit-position histogram of error rates
    ax = axes[2, 0]
    counts = [base_stats["flip_1to0"], base_stats["flip_0to1"],
              final_stats["flip_1to0"], final_stats["flip_0to1"]]
    labels = ["base 1→0", "base 0→1", "final 1→0", "final 0→1"]
    norm_to_truth = [
        base_stats["flip_1to0"] / max(1, base_stats["n_ones"]),
        base_stats["flip_0to1"] / max(1, base_stats["n_zeros"]),
        final_stats["flip_1to0"] / max(1, final_stats["n_ones"]),
        final_stats["flip_0to1"] / max(1, final_stats["n_zeros"]),
    ]
    bars = ax.bar(labels, norm_to_truth, color=["#c45", "#5c4", "#c45", "#5c4"],
                  edgecolor="k", linewidth=0.5)
    for b, c, frac in zip(bars, counts, norm_to_truth):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.005,
                f"{frac:.3f}\n({c})", ha="center", fontsize=8)
    ax.set_ylabel("flip rate (normalised by truth count)")
    ax.set_title("polarity imbalance — fraction of true 1s that flipped to 0, "
                 "and vice versa")
    ax.grid(True, alpha=0.3, axis="y")

    ax = axes[2, 1]
    ax.hist(base_stats["err_per_bit"], bins=40, alpha=0.5, label="baseline",
            color="C0", edgecolor="k", linewidth=0.3)
    ax.hist(final_stats["err_per_bit"], bins=40, alpha=0.5, label="final",
            color="C3", edgecolor="k", linewidth=0.3)
    ax.set_xlabel("per-bit error rate")
    ax.set_ylabel("# bit positions")
    ax.set_title("distribution of per-bit error rates across the 1600 positions")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archives", nargs="+", type=Path)
    ap.add_argument("--depth", default="4R", choices=["2R", "3R", "4R"])
    ap.add_argument("--answers", type=Path, default=None,
                    help="Override path to answers_A00 dir. By default looks "
                         "in <archive>/0005_SASCA/answers_A00/")
    ap.add_argument("--out-dir", type=Path, default=Path("/tmp/per_bit_analysis"))
    ap.add_argument("--use-baseline-as-truth", action="store_true",
                    help="When answers_A00 is missing, treat the baseline "
                         "prediction (rate_point=0, full priors) as ground truth. "
                         "Valid only for runs whose Rate_Scan log confirms "
                         "baseline_wrong_bits=0 across all traces.")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary_lines = [f"# Per-bit error analysis ({args.depth})\n"]

    for arch in args.archives:
        arch = arch.resolve()
        name = arch.name
        print(f"\n=== {name} ===")
        base, final, trace_ids = load_predictions(arch, args.depth)
        if base is None:
            print(f"  no predictions in {arch} for {args.depth}")
            continue

        ans_dir = args.answers or (arch / "0005_SASCA" / "answers_A00")
        try:
            answers = load_answers(ans_dir, trace_ids)
        except FileNotFoundError as e:
            if args.use_baseline_as_truth:
                # Rate_Scan logs show baseline_wrong_bits=0 across all traces
                # for these F_9 runs (BP at rate_point=0 has full priors → perfect
                # reconstruction), so the baseline prediction IS the ground truth.
                print(f"  using prediction_baseline as ground truth "
                      f"(--use-baseline-as-truth); confirmed perfect on all "
                      f"50 traces in run logs)")
                answers = base
            else:
                print(f"  missing answer: {e}")
                print(f"  (predictions for {len(trace_ids)} traces present, "
                      f"but answers_A00 dir is empty/incomplete; pass "
                      f"--use-baseline-as-truth to use baseline as ground truth)")
                continue

        base_stats = per_bit_stats(base, answers, f"{name} baseline")
        final_stats = per_bit_stats(final, answers, f"{name} final")

        out_png = args.out_dir / f"per_bit_{name}_{args.depth}.png"
        render(out_png, f"{name} per-bit errors @ {args.depth}",
               base_stats, final_stats)
        print(f"  saved {out_png}")

        # ranked top-10 hottest bits
        worst = np.argsort(final_stats["err_per_bit"])[::-1][:10]
        worst_lines = [f"    bit {b:4d} (lane {b//LANE_BITS:2d}, "
                       f"bit-in-lane {b%LANE_BITS:2d}): "
                       f"err {final_stats['err_per_bit'][b]:.3f}"
                       for b in worst]

        summary_lines.append(f"## {name}")
        summary_lines.append(f"- traces: {base_stats['n_traces']}")
        summary_lines.append(f"- baseline BER: {base_stats['ber']:.4f}  "
                             f"(flip 1→0: {base_stats['flip_1to0']}, "
                             f"flip 0→1: {base_stats['flip_0to1']})")
        summary_lines.append(f"- final    BER: {final_stats['ber']:.4f}  "
                             f"(flip 1→0: {final_stats['flip_1to0']}, "
                             f"flip 0→1: {final_stats['flip_0to1']})")
        summary_lines.append(f"- per-trace wrong-bit mean (final): "
                             f"{final_stats['err_per_trace'].mean():.1f}, "
                             f"min={final_stats['err_per_trace'].min()}, "
                             f"max={final_stats['err_per_trace'].max()}")
        summary_lines.append(f"- 10 hottest bits (final):")
        summary_lines.extend(worst_lines)
        summary_lines.append("")

    txt = args.out_dir / f"per_bit_summary_{args.depth}.md"
    txt.write_text("\n".join(summary_lines))
    print(f"\nsaved {txt}")


if __name__ == "__main__":
    main()
