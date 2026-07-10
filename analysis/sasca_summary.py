"""
Read SASCA iteration-scan and rate-scan _B.npy files from one or more
run archives and print a summary table (console + LaTeX fragment).

Usage:
    python3 tmp_sasca_summary.py ARCHIVE [ARCHIVE ...]

Each ARCHIVE is a path like:
    project_SHA3-32bit/pipeline_runner/runs_archive/smoke_v4/2026-05-28_smoke_v4_f9_sigma0p1

Multiple archives are printed as separate rows.
If no archives are given, defaults to all four smoke_v4 sigma=0.1 modes.

n_traces is read from ARCHIVE/pipeline_runner/.env (SHA3_SASCA_TRACE_COUNT).
Falls back to arr.max() over all loaded arrays if the env file is absent.
"""

import sys
import os
import glob
import numpy as np
from pathlib import Path

DEPTHS = ["2R", "3R", "4R"]
ARCHIVE_ROOT = Path("project_SHA3-32bit/pipeline_runner/runs_archive")
DEFAULT_SCALE = "smoke_v4"
DEFAULT_SIGMA = "sigma0p1"
DEFAULT_MODES = ["f9", "hd", "hw", "id"]


def read_n_traces(archive: Path) -> int:
    env_path = archive / "pipeline_runner" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("SHA3_SASCA_TRACE_COUNT="):
                return int(line.split("=", 1)[1].strip())
    return None


def load_arr(archive: Path, scan_type: str, depth: str):
    folder = "Iteration_Scan" if scan_type == "iter" else "Rate_Scan"
    prefix = "iteration_scan" if scan_type == "iter" else "rate_scan"
    p = archive / "0005_SASCA" / folder / f"{prefix}_{depth}_B.npy"
    if p.exists():
        return np.load(p).astype(float)
    return None


def summarise(archive: Path):
    n_traces = read_n_traces(archive)

    # Fallback: infer from the maximum value across all rate-scan arrays
    # (rate arr[0] = full template ≈ n_traces for low-noise runs; good enough as fallback)
    if n_traces is None:
        candidates = []
        for depth in DEPTHS:
            arr = load_arr(archive, "rate", depth)
            if arr is not None and arr.max() > 0:
                candidates.append(int(arr.max()))
        n_traces = max(candidates) if candidates else 50

    results = {}
    for depth in DEPTHS:
        iter_arr = load_arr(archive, "iter", depth)
        rate_arr = load_arr(archive, "rate", depth)

        if iter_arr is not None:
            final_sr = iter_arr[-1] / n_traces
            mx = iter_arr.max()
            conv_iter = int(np.argmax(iter_arr >= mx)) if mx > 0 else None
            iter_mean_sr = iter_arr.mean() / n_traces
        else:
            final_sr = conv_iter = iter_mean_sr = None

        if rate_arr is not None:
            auc = rate_arr.mean() / n_traces
            baseline_sr = rate_arr[0] / n_traces   # arr[0] = full template
            pure_sr = rate_arr[-1] / n_traces       # arr[-1] = all bits blanked
        else:
            auc = baseline_sr = pure_sr = None

        results[depth] = dict(
            iter_final_sr=final_sr,
            iter_conv=conv_iter,
            iter_mean_sr=iter_mean_sr,
            rate_auc=auc,
            rate_baseline=baseline_sr,
            rate_pure=pure_sr,
        )

    return n_traces, results


def fmt(v, pct=True, dec=1):
    if v is None:
        return "---"
    if pct:
        return f"{100*v:.{dec}f}\\%"
    return f"{v:.{dec+1}f}"


def fmt_iter(v):
    return "---" if v is None else str(v)


def print_archive(archive: Path):
    label = archive.name
    n_traces, res = summarise(archive)

    print(f"\n=== {label}  (n_traces={n_traces}) ===\n")

    hdr = f"{'Depth':<6} {'IterFinalSR':>11} {'IterConv':>8} {'IterMeanSR':>10} {'RateAUC':>8} {'RateBaseline':>13} {'RatePure':>9}"
    print(hdr)
    print("-" * len(hdr))
    for depth in DEPTHS:
        r = res[depth]
        print(
            f"{depth:<6} "
            f"{fmt(r['iter_final_sr']):>11} "
            f"{fmt_iter(r['iter_conv']):>8} "
            f"{fmt(r['iter_mean_sr']):>10} "
            f"{fmt(r['rate_auc'], dec=3):>8} "
            f"{fmt(r['rate_baseline']):>13} "
            f"{fmt(r['rate_pure']):>9}"
        )

    # LaTeX fragment — one row per depth
    print()
    print("% --- LaTeX rows (iter scan: final SR / conv iter, rate scan: AUC) ---")
    for depth in DEPTHS:
        r = res[depth]
        fs = fmt(r['iter_final_sr'])
        ci = fmt_iter(r['iter_conv'])
        auc_val = f"{r['rate_auc']:.3f}" if r['rate_auc'] is not None else "---"
        print(f"  {label} ({depth}) & {fs} / iter {ci} & {auc_val} \\\\")


def default_archives():
    archives = []
    for mode in DEFAULT_MODES:
        pattern = str(ARCHIVE_ROOT / DEFAULT_SCALE / f"*{mode}*{DEFAULT_SIGMA}")
        matches = sorted(glob.glob(pattern))
        if matches:
            archives.append(Path(matches[-1]))
        else:
            print(f"[warn] no archive found for mode={mode} sigma={DEFAULT_SIGMA}", file=sys.stderr)
    return archives


if __name__ == "__main__":
    if len(sys.argv) > 1:
        archives = [Path(a) for a in sys.argv[1:]]
    else:
        archives = default_archives()

    for arch in archives:
        if not arch.exists():
            print(f"[error] archive not found: {arch}", file=sys.stderr)
            continue
        print_archive(arch)
