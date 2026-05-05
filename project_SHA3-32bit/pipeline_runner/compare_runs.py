#!/usr/bin/env python3
"""Compare N archived runs (produced by archive_run.sh) and render a plot.

Reads each archive's 0004_validation/quality_report/summary_family_round.csv
and any 0005_SASCA/Rate_Scan/{2,3,4}R_Success/ partials present.

Usage:
    python compare_runs.py <archive_dir> [<archive_dir> ...]
                           [--out PATH] [--title TEXT] [--rate-depth 2R|3R|4R]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as e:
    sys.exit(f"matplotlib is required: {e}")

RAND_SR = 1.0 / 256.0
RAND_GE = 128.0
FAM_LETTERS = ("A", "B", "C", "D")


def load_family_csv(archive: Path):
    p = archive / "0004_validation" / "quality_report" / "summary_family_round.csv"
    if not p.exists():
        return None
    rows = []
    with open(p) as f:
        for r in csv.DictReader(f):
            if not r.get("family_round"):
                continue
            rows.append({
                "family_round": r["family_round"],
                "sr": float(r["sr_mean_avg"]),
                "ge": float(r["ge_mean_avg"]),
                "score": float(r["combined_score_avg"]),
            })
    return rows


def load_success_curves(archive: Path, depth: str):
    d = archive / "0005_SASCA" / "Rate_Scan" / f"{depth}_Success"
    if not d.is_dir():
        return []
    curves = []
    for p in sorted(d.glob("success_*.npy")):
        try:
            a = np.load(p, allow_pickle=True).astype(bool)
        except Exception:
            continue
        curves.append((p.stem, a))
    return curves


def load_rate_scan_npy(archive: Path, depth: str):
    """Load the newer rate_scan_{depth}_B.npy summary format.

    Returns (counts, n_total) where counts[k] = number of successful attacks
    at scan point k (out of n_total), or None if not present.
    """
    p = archive / "0005_SASCA" / "Rate_Scan" / f"rate_scan_{depth}_B.npy"
    if not p.exists():
        return None
    arr = np.load(p).astype(float)
    n_total = int(arr.max()) if arr.max() > 0 else 1
    return arr, n_total


def family_aggregate(rows):
    agg = {"sr": {}, "ge": {}}
    for letter in FAM_LETTERS:
        matches = [r for r in rows if r["family_round"].startswith(letter)]
        if matches:
            agg["sr"][letter] = float(np.mean([r["sr"] for r in matches]))
            agg["ge"][letter] = float(np.mean([r["ge"] for r in matches]))
    return agg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archives", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=None,
                    help="Output PNG path (default: comparison_<labels>.png "
                         "next to the first archive)")
    ap.add_argument("--title", type=str, default=None)
    ap.add_argument("--rate-depth", choices=["2R", "3R", "4R"], default="2R",
                    help="Which Rate_Scan depth to overlay success curves for")
    ap.add_argument("--max-curves", type=int, default=40,
                    help="Max success curves to plot per archive (subsampled evenly)")
    args = ap.parse_args()

    runs = []
    for arch in args.archives:
        arch = arch.resolve()
        if not arch.is_dir():
            sys.exit(f"not a directory: {arch}")
        rows = load_family_csv(arch)
        if rows is None:
            sys.exit(f"missing summary_family_round.csv in {arch}")
        curves = load_success_curves(arch, args.rate_depth)
        rate_summary = load_rate_scan_npy(arch, args.rate_depth)
        runs.append({
            "path": arch,
            "name": arch.name,
            "rows": rows,
            "agg": family_aggregate(rows),
            "curves": curves,
            "rate_summary": rate_summary,
        })

    labels = [r["family_round"] for r in runs[0]["rows"]]
    for r in runs[1:]:
        if [x["family_round"] for x in r["rows"]] != labels:
            sys.exit("archives have mismatched family_round rows — aborting")

    # --- figure layout: 3 rows
    # Row 0: SR per family+round (log) | GE per family+round (linear)
    # Row 1: SR per family (linear)    | SR ratio (if N==2)
    # Row 2: Rate_Scan success curves (spanning both columns)

    fig = plt.figure(figsize=(14, 10))
    gs = fig.add_gridspec(3, 2, hspace=0.42, wspace=0.28)
    title = args.title or (
        "Run comparison — " + " vs ".join(r["name"] for r in runs))
    fig.suptitle(title, fontsize=12, fontweight="bold")

    n = len(runs)
    colors = plt.cm.tab10(np.linspace(0, 1, max(n, 3)))
    x = np.arange(len(labels))
    width = 0.8 / n

    # SR per family+round (log)
    ax = fig.add_subplot(gs[0, 0])
    for i, r in enumerate(runs):
        sr = np.array([row["sr"] for row in r["rows"]])
        ax.bar(x + (i - (n - 1) / 2) * width, sr, width,
               color=colors[i], edgecolor="k", linewidth=0.3, label=r["name"])
    ax.axhline(RAND_SR, color="red", ls="--", lw=1, label="random=1/256")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=60, fontsize=8)
    ax.set_ylabel("SR mean (log)")
    ax.set_yscale("log")
    ax.set_ylim(1e-3, 1.0)
    ax.set_title("1st-order success rate per family/round")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(True, which="both", alpha=0.3)

    # GE per family+round (linear)
    ax = fig.add_subplot(gs[0, 1])
    for i, r in enumerate(runs):
        ge = np.array([row["ge"] for row in r["rows"]])
        ax.bar(x + (i - (n - 1) / 2) * width, ge, width,
               color=colors[i], edgecolor="k", linewidth=0.3, label=r["name"])
    ax.axhline(RAND_GE, color="red", ls="--", lw=1, label="random=128")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=60, fontsize=8)
    ax.set_ylabel("GE mean (lower=better)")
    ax.set_ylim(0, 140)
    ax.set_title("Guessing entropy per family/round")
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(True, alpha=0.3)

    # SR per family (linear, aggregated) — shape view
    ax = fig.add_subplot(gs[1, 0])
    xf = np.arange(4)
    for i, r in enumerate(runs):
        sr = [r["agg"]["sr"].get(L, 0.0) for L in FAM_LETTERS]
        ax.bar(xf + (i - (n - 1) / 2) * width, sr, width,
               color=colors[i], edgecolor="k", linewidth=0.3, label=r["name"])
    ax.axhline(RAND_SR, color="red", ls="--", lw=1, label="random")
    ax.set_xticks(xf)
    ax.set_xticklabels([f"family {L}" for L in FAM_LETTERS])
    ax.set_ylabel("SR mean (linear)")
    ax.set_title("Per-family SR shape")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # Ratio panel (if exactly 2 archives, treat first as baseline)
    ax = fig.add_subplot(gs[1, 1])
    if n == 2:
        base = runs[0]["agg"]["sr"]
        other = runs[1]["agg"]["sr"]
        ratios = [(other.get(L, 0.0) / base[L]) if base.get(L, 0.0) > 0 else 0.0
                  for L in FAM_LETTERS]
        bar_colors = ["#c45" if r < 0.5 else "#f93" if r < 0.9
                      else "#2b8" if r < 1.5 else "#28c" for r in ratios]
        bars = ax.bar(FAM_LETTERS, ratios, color=bar_colors,
                      edgecolor="k", linewidth=0.4)
        for b, v in zip(bars, ratios):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02,
                    f"{v:.2f}×", ha="center", fontsize=9)
        ax.axhline(1.0, color="k", lw=1)
        ax.set_ylabel(f"SR ratio ({runs[1]['name']} / {runs[0]['name']})")
        ax.set_title("Leakage strength ratio (second / first)")
        ax.grid(True, alpha=0.3)
    else:
        ax.axis("off")
        ax.text(0.5, 0.5,
                "SR ratio panel is only shown for N=2 archives.\n"
                f"(this comparison has N={n}.)",
                ha="center", va="center", fontsize=10)

    # Rate_Scan success curves — both per-trace (old) and summary-npy (new) formats.
    # x-axis is normalised to [0, 1]: 0 = max data rate (easiest), 1 = min (hardest).
    # y-axis is success fraction [0, 1].
    ax = fig.add_subplot(gs[2, :])
    has_any = False
    for i, r in enumerate(runs):
        curves = r["curves"]
        rate_summary = r["rate_summary"]

        # Old per-trace format: plot faint individual lines + a thick mean aggregate.
        if curves:
            has_any = True
            max_len = max(len(c) for _, c in curves)
            xs_norm = np.linspace(0, 1, max_len)

            plot_curves = curves
            if len(plot_curves) > args.max_curves:
                step = max(1, len(plot_curves) // args.max_curves)
                plot_curves = plot_curves[::step][:args.max_curves]
            for j, (_, curve) in enumerate(plot_curves):
                ax.plot(np.linspace(0, 1, len(curve)), curve.astype(float),
                        color=colors[i], alpha=0.25, lw=0.8,
                        label=(f"{r['name']} (n={len(curves)}, per-trace)"
                               if j == 0 else None))

            # Mean aggregate across all curves (pad shorter ones with NaN).
            mat = np.full((len(curves), max_len), np.nan)
            for k, (_, c) in enumerate(curves):
                mat[k, :len(c)] = c.astype(float)
            ax.plot(xs_norm, np.nanmean(mat, axis=0),
                    color=colors[i], lw=2.2, ls="--", alpha=0.9)

        # New summary-npy format: single aggregate fraction line.
        if rate_summary is not None:
            has_any = True
            arr, n_total = rate_summary
            xs_norm = np.linspace(0, 1, len(arr))
            ax.plot(xs_norm, arr / n_total,
                    color=colors[i], lw=2.2,
                    label=f"{r['name']} (n={n_total}, summary)")

    if has_any:
        ax.set_xlabel("rate scan position  (0 = max data rate / easiest → 1 = min / hardest)")
        ax.set_ylabel(f"success fraction — {args.rate_depth}")
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_ylim(-0.05, 1.05)
        ax.set_title(f"Rate_Scan_{args.rate_depth} aggregate success "
                     "(solid = summary npy; dashed = mean of per-trace curves)")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)
    else:
        ax.axis("off")
        ax.text(0.5, 0.5,
                f"No Rate_Scan_{args.rate_depth} data in any archive",
                ha="center", va="center", fontsize=10)

    out = args.out or (runs[0]["path"].parent / f"comparison_{'_vs_'.join(r['name'] for r in runs)}.png")
    out = Path(out)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(out, dpi=140, bbox_inches="tight")
    print(f"saved {out}")

    # Text summary
    txt = out.with_suffix(".txt")
    with open(txt, "w") as f:
        f.write(f"Comparison of {n} archive(s):\n")
        for r in runs:
            f.write(f"  - {r['name']}  ({r['path']})\n")
        f.write("\nPer-family SR / GE (avg across rounds):\n")
        f.write(f"{'family':<8}")
        for r in runs:
            f.write(f"{r['name'][:18]:>20}")
        f.write("\n")
        for L in FAM_LETTERS:
            f.write(f"{L:<8}")
            for r in runs:
                sr = r["agg"]["sr"].get(L, 0.0)
                ge = r["agg"]["ge"].get(L, 0.0)
                f.write(f"{'SR=' + f'{sr:.4f}' + ' GE=' + f'{ge:.1f}':>20}")
            f.write("\n")
        f.write(f"\nRate_Scan_{args.rate_depth} success summary:\n")
        for r in runs:
            if r["curves"]:
                counts = np.array([int(c.sum()) for _, c in r["curves"]])
                f.write(f"  {r['name']} [per-trace]: n={len(counts)}  "
                        f"min={counts.min()}  median={int(np.median(counts))}  "
                        f"max={counts.max()}  mean={counts.mean():.1f}\n")
            elif r["rate_summary"] is not None:
                arr, n_total = r["rate_summary"]
                frac = arr / n_total
                # find the last scan point where ≥50% of attacks succeed
                above_half = np.where(frac >= 0.5)[0]
                half_pt = int(above_half[-1]) if len(above_half) else -1
                f.write(f"  {r['name']} [summary npy]: n={n_total}  "
                        f"SR@0={frac[0]:.2f}  SR@mid={frac[len(frac)//2]:.2f}  "
                        f"SR@end={frac[-1]:.2f}  "
                        f"last≥50%=pt{half_pt}/{len(arr)-1}\n")
            else:
                f.write(f"  {r['name']}: (no rate scan data)\n")
    print(f"saved {txt}")


if __name__ == "__main__":
    main()
