#!/usr/bin/env python3
"""Sigma-sweep comparison for hw / hd / id / f9 leakage modes.

Produces two figures:
  1. Per-mode (2×2): template SR + SASCA 2R/3R/4R success at max rate vs sigma
  2. Cross-mode (2×2): one panel per metric, all modes overlaid

Usage:
    python tmp_sigma_sweep_compare.py [--out-prefix PREFIX] [--archive-root DIR]
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ARCHIVE_ROOT_DEFAULT = Path(__file__).parent / "runs_archive" / "smoke_v2"
SASCA_N_TRACES = 50   # SHA3_SASCA_TRACE_COUNT for smoke runs
RAND_SR_TEMPLATE = 1.0 / 256.0

SIGMAS = [0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]

# Archive name patterns for each mode (sigma label → archive dir prefix search)
# We pick the latest archive whose name contains the mode+sigma pattern.
MODE_PATTERNS = {
    "hw": "smoke_v2_hw_sigma",
    "hd": "smoke_v2_hd_sigma",
    "id": "smoke_v2_id_sigma",
    "f9": "smoke_v2_f9_sigma",
}

MODE_COLORS = {"hw": "#1f77b4", "hd": "#ff7f0e", "id": "#2ca02c", "f9": "#d62728"}
MODE_LABELS = {"hw": "HW", "hd": "HD", "id": "ID", "f9": "F9"}

DEPTH_STYLES = {"2R": "-", "3R": "--", "4R": ":"}
DEPTH_COLORS = {"2R": "#9467bd", "3R": "#8c564b", "4R": "#e377c2"}


def sigma_str(s: float) -> str:
    return f"{s:.1f}".replace(".", "p")


def find_archive(root: Path, pattern: str, sigma: float) -> Path | None:
    tag = pattern + sigma_str(sigma)
    candidates = sorted(root.glob(f"*_{tag}"))
    return candidates[-1] if candidates else None


def load_template_sr(archive: Path) -> float | None:
    """Average sr_mean_avg over all family/round rows."""
    p = archive / "0004_validation" / "quality_report" / "summary_family_round.csv"
    if not p.exists():
        return None
    vals = []
    with open(p) as f:
        for row in csv.DictReader(f):
            if row.get("family_round"):
                vals.append(float(row["sr_mean_avg"]))
    return float(np.mean(vals)) if vals else None


def load_template_ge(archive: Path) -> float | None:
    """Average ge_mean_avg over all family/round rows."""
    p = archive / "0004_validation" / "quality_report" / "summary_family_round.csv"
    if not p.exists():
        return None
    vals = []
    with open(p) as f:
        for row in csv.DictReader(f):
            if row.get("family_round"):
                vals.append(float(row["ge_mean_avg"]))
    return float(np.mean(vals)) if vals else None


def load_template_by_family(archive: Path) -> dict[str, float] | None:
    """SR per family (averaged over rounds)."""
    p = archive / "0004_validation" / "quality_report" / "summary_family_round.csv"
    if not p.exists():
        return None
    fam: dict[str, list[float]] = {}
    with open(p) as f:
        for row in csv.DictReader(f):
            fr = row.get("family_round", "")
            if not fr:
                continue
            letter = fr[0]
            fam.setdefault(letter, []).append(float(row["sr_mean_avg"]))
    return {k: float(np.mean(v)) for k, v in fam.items()}


def load_sasca_auc(archive: Path, depth: str) -> float | None:
    """Mean success fraction across the full rate scan (AUC proxy)."""
    p = archive / "0005_SASCA" / "Rate_Scan" / f"rate_scan_{depth}_B.npy"
    if not p.exists():
        return None
    b = np.load(p, allow_pickle=True)
    return float(b.mean()) / SASCA_N_TRACES


def load_sasca_curve(archive: Path, depth: str) -> np.ndarray | None:
    """Full rate-scan success curve (fraction), shape (21,)."""
    p = archive / "0005_SASCA" / "Rate_Scan" / f"rate_scan_{depth}_B.npy"
    if not p.exists():
        return None
    b = np.load(p, allow_pickle=True)
    return b.astype(float) / SASCA_N_TRACES


def collect_mode_data(root: Path, mode: str) -> dict:
    pattern = MODE_PATTERNS[mode]
    data = {
        "sigma": [], "template_sr": [], "template_ge": [],
        "sasca_2R": [], "sasca_3R": [], "sasca_4R": [],
        "template_sr_by_family": [],
    }
    for s in SIGMAS:
        arch = find_archive(root, pattern, s)
        if arch is None:
            print(f"  [MISSING] {mode} sigma={s}")
            continue
        tsr = load_template_sr(arch)
        tge = load_template_ge(arch)
        s2 = load_sasca_auc(arch, "2R")
        s3 = load_sasca_auc(arch, "3R")
        s4 = load_sasca_auc(arch, "4R")
        tf = load_template_by_family(arch)
        if tsr is None:
            print(f"  [NO DATA] {arch.name}")
            continue
        data["sigma"].append(s)
        data["template_sr"].append(tsr)
        data["template_ge"].append(tge)
        data["sasca_2R"].append(s2)
        data["sasca_3R"].append(s3)
        data["sasca_4R"].append(s4)
        data["template_sr_by_family"].append(tf)
        print(f"  {arch.name}  SR={tsr:.4f}  2R={s2:.2f}  3R={s3:.2f}  4R={s4:.2f}")
    for k in ("sigma", "template_sr", "template_ge", "sasca_2R", "sasca_3R", "sasca_4R"):
        data[k] = np.array(data[k], dtype=float)
    return data


def fig_per_mode(all_data: dict, out: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=False)
    fig.suptitle("Sigma sweep — per-mode: template SR & SASCA AUC (rate-scan mean)", fontsize=13, fontweight="bold")

    for ax, (mode, data) in zip(axes.flat, all_data.items()):
        sig = data["sigma"]
        ax.semilogy(sig, data["template_sr"], "k-o", lw=2, ms=5, label="Template SR (avg)", zorder=5)
        ax.axhline(RAND_SR_TEMPLATE, color="grey", ls=":", lw=1, label="Random (1/256)")

        # Per-family template SR
        families = sorted({k for d in data["template_sr_by_family"] for k in d.keys()})
        fam_colors = {"A": "#aec7e8", "B": "#ffbb78", "C": "#98df8a", "D": "#ff9896"}
        for fam in families:
            fsr = [d.get(fam, np.nan) for d in data["template_sr_by_family"]]
            ax.semilogy(sig, fsr, color=fam_colors.get(fam, "grey"),
                        ls="-", lw=1, ms=3, marker=".", alpha=0.7, label=f"Fam {fam}")

        ax2 = ax.twinx()
        for depth, ls in DEPTH_STYLES.items():
            col = DEPTH_COLORS[depth]
            sasca = data[f"sasca_{depth}"]
            mask = ~np.isnan(sasca)
            ax2.plot(sig[mask], sasca[mask], ls=ls, color=col, lw=1.8, ms=5, marker="s",
                     label=f"SASCA {depth}")
        ax2.set_ylim(-0.05, 1.05)
        ax2.set_ylabel("SASCA AUC (rate-scan mean)", fontsize=9)
        ax2.axhline(0.0, color="grey", ls=":", lw=0.8)

        ax.set_xlabel("Noise sigma σ")
        ax.set_ylabel("Template SR (log)", fontsize=9)
        ax.set_title(f"{MODE_LABELS[mode]} mode", fontweight="bold")
        ax.set_xticks(SIGMAS)
        ax.set_xticklabels([str(s) for s in SIGMAS], fontsize=8)

        # Combined legend
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="lower left")

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.close(fig)


def fig_cross_mode(all_data: dict, out: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    fig.suptitle("Sigma sweep — cross-mode comparison", fontsize=13, fontweight="bold")

    ax_tsr, ax_tge, ax_2r, ax_34r = axes.flat

    # --- Template SR ---
    for mode, data in all_data.items():
        ax_tsr.semilogy(data["sigma"], data["template_sr"],
                         color=MODE_COLORS[mode], lw=2, marker="o", ms=5, label=MODE_LABELS[mode])
    ax_tsr.axhline(RAND_SR_TEMPLATE, color="grey", ls=":", lw=1, label="Random")
    ax_tsr.set_ylabel("Template SR mean (log)")
    ax_tsr.set_title("Template success rate (avg over families/rounds)")
    ax_tsr.legend(fontsize=9)
    ax_tsr.set_xticks(SIGMAS)

    # --- Template GE ---
    for mode, data in all_data.items():
        ax_tge.plot(data["sigma"], data["template_ge"],
                    color=MODE_COLORS[mode], lw=2, marker="o", ms=5, label=MODE_LABELS[mode])
    ax_tge.axhline(128.0, color="grey", ls=":", lw=1, label="Random GE=128")
    ax_tge.set_ylabel("Template GE mean (lower = better)")
    ax_tge.set_title("Template guessing entropy (avg over families/rounds)")
    ax_tge.legend(fontsize=9)

    # --- SASCA 2R ---
    for mode, data in all_data.items():
        s2 = data["sasca_2R"]
        mask = ~np.isnan(s2)
        ax_2r.plot(data["sigma"][mask], s2[mask],
                   color=MODE_COLORS[mode], lw=2, marker="s", ms=5, label=MODE_LABELS[mode])
    ax_2r.set_ylabel("SASCA AUC (rate-scan mean SR)")
    ax_2r.set_title("SASCA 2R — AUC across data-rate sweep")
    ax_2r.set_ylim(-0.05, 1.05)
    ax_2r.axhline(0.0, color="grey", ls=":", lw=0.8)
    ax_2r.legend(fontsize=9)
    ax_2r.set_xlabel("Noise sigma σ")

    # --- SASCA 3R + 4R ---
    for mode, data in all_data.items():
        col = MODE_COLORS[mode]
        for depth, ls in [("3R", "-"), ("4R", "--")]:
            sarr = data[f"sasca_{depth}"]
            mask = ~np.isnan(sarr)
            ax_34r.plot(data["sigma"][mask], sarr[mask],
                        color=col, lw=1.8, ls=ls, marker="^", ms=4,
                        label=f"{MODE_LABELS[mode]} {depth}")
    ax_34r.set_ylabel("SASCA AUC (rate-scan mean SR)")
    ax_34r.set_title("SASCA 3R (solid) & 4R (dashed) — AUC across data-rate sweep")
    ax_34r.set_ylim(-0.05, 1.05)
    ax_34r.axhline(0.0, color="grey", ls=":", lw=0.8)
    ax_34r.legend(fontsize=7, ncol=2)
    ax_34r.set_xlabel("Noise sigma σ")

    for ax in axes.flat:
        ax.set_xticks(SIGMAS)
        ax.set_xticklabels([str(s) for s in SIGMAS], fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.close(fig)


def fig_rate_scan_grid(all_data: dict, root: Path, out: Path) -> None:
    """4×3 grid: mode (rows) × depth (cols), rate-scan curve per sigma."""
    modes = list(all_data.keys())
    depths = ["2R", "3R", "4R"]
    fig, axes = plt.subplots(len(modes), len(depths), figsize=(14, 11), sharex=True, sharey=True)
    fig.suptitle("Rate-scan curves — all modes × depths (coloured by sigma)", fontsize=12, fontweight="bold")

    cmap = plt.cm.plasma
    sigma_norm = plt.Normalize(vmin=min(SIGMAS), vmax=max(SIGMAS))
    x_pos = np.linspace(0, 1, 21)

    for row, mode in enumerate(modes):
        pattern = MODE_PATTERNS[mode]
        for col, depth in enumerate(depths):
            ax = axes[row][col]
            if row == 0:
                ax.set_title(f"SASCA {depth}", fontweight="bold")
            if col == 0:
                ax.set_ylabel(f"{MODE_LABELS[mode]}\nSR", fontsize=9)
            for s in SIGMAS:
                arch = find_archive(root, pattern, s)
                if arch is None:
                    continue
                curve = load_sasca_curve(arch, depth)
                if curve is None:
                    continue
                color = cmap(sigma_norm(s))
                ax.plot(x_pos, curve, color=color, lw=1.5, alpha=0.85)
            ax.set_ylim(-0.05, 1.05)
            ax.axhline(0.0, color="grey", ls=":", lw=0.7)
            ax.grid(True, alpha=0.25)
            if row == len(modes) - 1:
                ax.set_xlabel("Rate scan pos\n(0=max data)", fontsize=8)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=sigma_norm)
    sm.set_array([])
    fig.colorbar(sm, ax=axes, label="Noise sigma σ", shrink=0.6, pad=0.02)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-prefix", default="sigma_sweep", help="Output filename prefix")
    ap.add_argument("--archive-root", type=Path, default=ARCHIVE_ROOT_DEFAULT)
    args = ap.parse_args()

    root = args.archive_root
    prefix = args.out_prefix

    print("Collecting data...")
    all_data = {}
    for mode in ("hw", "hd", "id", "f9"):
        print(f"\n[{mode}]")
        all_data[mode] = collect_mode_data(root, mode)

    out_dir = root.parent
    print("\nPlotting figure 1: per-mode...")
    fig_per_mode(all_data, out_dir / f"{prefix}_per_mode.png")

    print("Plotting figure 2: cross-mode...")
    fig_cross_mode(all_data, out_dir / f"{prefix}_cross_mode.png")

    print("Plotting figure 3: rate-scan grid...")
    fig_rate_scan_grid(all_data, root, out_dir / f"{prefix}_rate_scan_grid.png")

    print("\nDone.")


if __name__ == "__main__":
    main()
