"""
Read phase-0004 and phase-0005 results from all run archives in a scale folder
and print noise-sweep comparison tables (console + LaTeX fragments).

Usage:
    python3 analysis/noise_sweep_summary.py SCALE_DIR

SCALE_DIR is a path to a scale folder containing individual run archives, e.g.:
    project_SHA3-32bit/pipeline_runner/runs_archive/smoke_v3

Archives are auto-discovered by parsing mode and sigma from folder names:
    YYYY-MM-DD_{scale}_{mode}_sigma{X}p{Y}

If multiple archives exist for the same (mode, sigma), the latest is used.

Output:
  Section 1 — per-mode template SR tables (rows=sigma, cols=A/B/C/D + mean)
  Section 2 — per-mode SASCA tables (rows=sigma, cols=iter/rate metrics per depth)
  Section 3 — LaTeX fragments for tab:sr-sigma-sweep, tab:sr-a-sigma-sweep, tab:auc-sigma
"""

import sys
import re
import csv
import numpy as np
from pathlib import Path
from collections import defaultdict

FAMILIES  = ["A", "B", "C", "D"]
DEPTHS    = ["2R", "3R", "4R"]
MODES     = ["f9", "hw", "hd", "id"]
MODE_DISPLAY = {"f9": "F9", "hw": "HW", "hd": "HD", "id": "ID"}

# --------------------------------------------------------------------------
# Archive discovery
# --------------------------------------------------------------------------

def discover_archives(scale_dir: Path) -> dict:
    """Return {(mode, sigma_float): Path} using the latest archive per pair."""
    pattern = re.compile(r'_([a-z0-9]+)_sigma(\d+p\d+)$')
    found = defaultdict(list)
    for d in scale_dir.iterdir():
        if not d.is_dir():
            continue
        m = pattern.search(d.name)
        if not m:
            continue
        mode  = m.group(1)
        sigma = float(m.group(2).replace("p", "."))
        found[(mode, sigma)].append(d)
    # keep latest (folder names sort by date prefix)
    return {key: sorted(paths)[-1] for key, paths in found.items()}


# --------------------------------------------------------------------------
# Data loading (inlined from template_summary.py / sasca_summary.py)
# --------------------------------------------------------------------------

def load_family_stats(archive: Path):
    """Return {family: {sr_mean, ge_mean, sr_per_round}} or None."""
    csv_path = archive / "0004_validation" / "quality_report" / "summary_family_round.csv"
    if not csv_path.exists():
        return None
    by_family = defaultdict(list)
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            tag = row["family_round"]
            by_family[tag[0]].append(
                (float(row["sr_mean_avg"]), float(row["ge_mean_avg"]))
            )
    result = {}
    for fam, entries in by_family.items():
        srs = [e[0] for e in entries]
        ges = [e[1] for e in entries]
        result[fam] = dict(
            sr_mean=sum(srs) / len(srs),
            ge_mean=sum(ges) / len(ges),
            sr_per_round=srs,
        )
    return result


def read_n_traces(archive: Path):
    env_path = archive / "pipeline_runner" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("SHA3_SASCA_TRACE_COUNT="):
                return int(line.split("=", 1)[1].strip())
    return None


def load_arr(archive: Path, scan_type: str, depth: str):
    folder = "Iteration_Scan" if scan_type == "iter" else "Rate_Scan"
    prefix = "iteration_scan"  if scan_type == "iter" else "rate_scan"
    p = archive / "0005_SASCA" / folder / f"{prefix}_{depth}_B.npy"
    return np.load(p).astype(float) if p.exists() else None


def load_sasca(archive: Path):
    """Return (n_traces, {depth: {iter_final_sr, iter_mean_sr, rate_auc, ...}})."""
    n_traces = read_n_traces(archive)
    if n_traces is None:
        candidates = [
            int(load_arr(archive, "rate", d).max())
            for d in DEPTHS
            if load_arr(archive, "rate", d) is not None and load_arr(archive, "rate", d).max() > 0
        ]
        n_traces = max(candidates) if candidates else 50

    results = {}
    for depth in DEPTHS:
        iter_arr = load_arr(archive, "iter", depth)
        rate_arr = load_arr(archive, "rate", depth)

        if iter_arr is not None:
            mx = iter_arr.max()
            final_sr   = iter_arr[-1] / n_traces
            iter_mean  = iter_arr.mean() / n_traces
            conv_iter  = int(np.argmax(iter_arr >= mx)) if mx > 0 else None
        else:
            final_sr = iter_mean = conv_iter = None

        if rate_arr is not None:
            auc      = rate_arr.mean() / n_traces
            baseline = rate_arr[0]    / n_traces
        else:
            auc = baseline = None

        results[depth] = dict(
            iter_final_sr=final_sr,
            iter_mean_sr=iter_mean,
            iter_conv=conv_iter,
            rate_auc=auc,
            rate_baseline=baseline,
        )
    return n_traces, results


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

def fs(v, dec=1):
    """Format success rate as percentage string."""
    return f"{100*v:.{dec}f}\\%" if v is not None else "---"

def fa(v):
    """Format AUC to 3 decimal places."""
    return f"{v:.3f}" if v is not None else "---"

def snr(sigma):
    if sigma <= 0:
        return "---"
    v = 0.667 / sigma**2
    # use enough decimals so we never print "0.0" for valid values
    return f"{v:.3g}"


# --------------------------------------------------------------------------
# Console output helpers
# --------------------------------------------------------------------------

def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


# --------------------------------------------------------------------------
# Section 1: per-mode template SR tables
# --------------------------------------------------------------------------

def print_template_section(archives: dict, sigmas: list):
    print_section("TEMPLATE SUCCESS RATE  (per-family, per-mode)")

    for mode in MODES:
        print(f"\n--- Mode: {MODE_DISPLAY[mode]} ---\n")
        hdr = f"{'sigma':>6}  {'A':>8}  {'B':>8}  {'C':>8}  {'D':>8}  {'mean':>8}"
        print(hdr)
        print("-" * len(hdr))
        for sigma in sigmas:
            arch = archives.get((mode, sigma))
            if arch is None:
                print(f"{sigma:>6.1f}  {'---':>8}  {'---':>8}  {'---':>8}  {'---':>8}  {'---':>8}")
                continue
            stats = load_family_stats(arch)
            if stats is None:
                print(f"{sigma:>6.1f}  (no data)")
                continue
            fam_srs = [stats[f]["sr_mean"] if f in stats else None for f in FAMILIES]
            valid   = [v for v in fam_srs if v is not None]
            mean_sr = sum(valid) / len(valid) if valid else None
            cols = "  ".join(f"{fs(v):>8}" for v in fam_srs)
            print(f"{sigma:>6.1f}  {cols}  {fs(mean_sr):>8}")


# --------------------------------------------------------------------------
# Section 2: per-mode SASCA tables
# --------------------------------------------------------------------------

def print_sasca_section(archives: dict, sigmas: list):
    print_section("SASCA  (iteration scan + rate scan, per-mode)")

    for mode in MODES:
        print(f"\n--- Mode: {MODE_DISPLAY[mode]} ---\n")
        hdr = (
            f"{'sigma':>6}  "
            + "  ".join(
                f"{'IterFin'+d:>10}  {'ItMean'+d:>9}  {'AUC'+d:>7}"
                for d in DEPTHS
            )
        )
        print(hdr)
        print("-" * len(hdr))
        for sigma in sigmas:
            arch = archives.get((mode, sigma))
            if arch is None:
                print(f"{sigma:>6.1f}  (no archive)")
                continue
            _, res = load_sasca(arch)
            parts = []
            for depth in DEPTHS:
                r = res[depth]
                parts.append(
                    f"{fs(r['iter_final_sr']):>10}  "
                    f"{fs(r['iter_mean_sr']):>9}  "
                    f"{fa(r['rate_auc']):>7}"
                )
            print(f"{sigma:>6.1f}  " + "  ".join(parts))


# --------------------------------------------------------------------------
# Section 3: LaTeX fragments
# --------------------------------------------------------------------------

def print_latex_section(archives: dict, sigmas: list):
    print_section("LaTeX FRAGMENTS")

    # --- tab:sr-sigma-sweep (all-family mean SR) ---
    print("\n% --- tab:sr-sigma-sweep  (all-family mean SR) ---")
    print(r"% \sigma & SNR_var & HW & HD & ID & F9 \\")
    for sigma in sigmas:
        means = {}
        for mode in MODES:
            arch = archives.get((mode, sigma))
            if arch is None:
                means[mode] = None
                continue
            stats = load_family_stats(arch)
            if stats is None:
                means[mode] = None
                continue
            valid = [stats[f]["sr_mean"] for f in FAMILIES if f in stats]
            means[mode] = sum(valid) / len(valid) if valid else None
        cols = " & ".join(fs(means[m]) for m in ["hw", "hd", "id", "f9"])
        print(f"        {sigma:.1f} & {snr(sigma)} & {cols} \\\\")

    # --- tab:sr-a-sigma-sweep (Family A SR only) ---
    print("\n% --- tab:sr-a-sigma-sweep  (Family A SR) ---")
    print(r"% \sigma & HW (A) & HD (A) & ID (A) & F9 (A) \\")
    for sigma in sigmas:
        a_srs = {}
        for mode in MODES:
            arch = archives.get((mode, sigma))
            if arch is None:
                a_srs[mode] = None
                continue
            stats = load_family_stats(arch)
            a_srs[mode] = stats["A"]["sr_mean"] if (stats and "A" in stats) else None
        cols = " & ".join(fs(a_srs[m]) for m in ["hw", "hd", "id", "f9"])
        print(f"        {sigma:.1f} & {cols} \\\\")

    # --- tab:auc-sigma (RateAUC per mode × depth) ---
    print("\n% --- tab:auc-sigma  (RateAUC, 3 dp) ---")
    header_modes = " & ".join(
        " & ".join(f"{MODE_DISPLAY[m]} {d}" for d in DEPTHS)
        for m in ["hw", "hd", "id", "f9"]
    )
    print(f"% sigma & {header_modes} \\\\")
    for sigma in sigmas:
        aucs = {}
        for mode in MODES:
            arch = archives.get((mode, sigma))
            if arch is None:
                aucs[mode] = {d: None for d in DEPTHS}
                continue
            _, res = load_sasca(arch)
            aucs[mode] = {d: res[d]["rate_auc"] for d in DEPTHS}
        cols = " & ".join(
            " & ".join(fa(aucs[m][d]) for d in DEPTHS)
            for m in ["hw", "hd", "id", "f9"]
        )
        print(f"        {sigma:.1f} & {cols} \\\\")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 noise_sweep_summary.py SCALE_DIR", file=sys.stderr)
        sys.exit(1)

    scale_dir = Path(sys.argv[1])
    if not scale_dir.is_dir():
        print(f"[error] not a directory: {scale_dir}", file=sys.stderr)
        sys.exit(1)

    archives = discover_archives(scale_dir)
    if not archives:
        print(f"[error] no run archives found in {scale_dir}", file=sys.stderr)
        sys.exit(1)

    sigmas = sorted({sigma for _, sigma in archives})

    print(f"\nScale directory : {scale_dir}")
    print(f"Archives found  : {len(archives)}")
    print(f"Modes           : {sorted({mode for mode, _ in archives})}")
    print(f"Sigma values    : {sigmas}")

    print_template_section(archives, sigmas)
    print_sasca_section(archives, sigmas)
    print_latex_section(archives, sigmas)


if __name__ == "__main__":
    main()
