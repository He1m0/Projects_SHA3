"""
Read phase-0004 validation results from one or more run archives and print
mean SR and GE per family (A/B/C/D), averaged over rounds.

Usage:
    python3 tmp_template_summary.py ARCHIVE [ARCHIVE ...]

Each ARCHIVE is a path like:
    project_SHA3-32bit/pipeline_runner/runs_archive/smoke_v4/2026-05-28_smoke_v4_f9_sigma0p1

If no archives are given, defaults to all four smoke_v4 sigma=0.1 modes.
"""

import sys
import csv
import glob
from pathlib import Path
from collections import defaultdict

ARCHIVE_ROOT = Path("project_SHA3-32bit/pipeline_runner/runs_archive")
DEFAULT_SCALE = "smoke_v4"
DEFAULT_SIGMA = "sigma0p1"
DEFAULT_MODES = ["f9", "hd", "hw", "id"]
FAMILIES = ["A", "B", "C", "D"]


def load_family_stats(archive: Path):
    """Return {family: {round_idx: (sr, ge)}} from summary_family_round.csv."""
    csv_path = archive / "0004_validation" / "quality_report" / "summary_family_round.csv"
    if not csv_path.exists():
        return None

    by_family = defaultdict(list)
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            tag = row["family_round"]          # e.g. "A03"
            fam = tag[0]                       # "A"
            by_family[fam].append((float(row["sr_mean_avg"]), float(row["ge_mean_avg"])))

    result = {}
    for fam, entries in by_family.items():
        srs = [e[0] for e in entries]
        ges = [e[1] for e in entries]
        result[fam] = dict(
            sr_mean=sum(srs) / len(srs),
            ge_mean=sum(ges) / len(ges),
            sr_per_round=srs,
            ge_per_round=ges,
            n_rounds=len(srs),
        )
    return result


def fmt_sr(v):
    return f"{100*v:.2f}\\%" if v is not None else "---"


def fmt_ge(v):
    return f"{v:.2f}" if v is not None else "---"


def print_archive(archive: Path):
    label = archive.name
    stats = load_family_stats(archive)
    if stats is None:
        print(f"[error] summary_family_round.csv not found in {archive}", file=sys.stderr)
        return

    print(f"\n=== {label} ===\n")

    # Console table
    hdr = f"{'Fam':<5} {'SR_mean':>9} {'GE_mean':>8}   per-round SR"
    print(hdr)
    print("-" * 60)
    for fam in FAMILIES:
        if fam not in stats:
            print(f"{fam:<5} {'---':>9} {'---':>8}")
            continue
        s = stats[fam]
        per_round = "  ".join(f"R{i}={100*sr:.1f}%" for i, sr in enumerate(s["sr_per_round"]))
        print(f"{fam:<5} {fmt_sr(s['sr_mean']):>9} {fmt_ge(s['ge_mean']):>8}   {per_round}")

    # LaTeX row — SR per family, then GE per family
    sr_cols = " & ".join(fmt_sr(stats[f]["sr_mean"]) if f in stats else "---" for f in FAMILIES)
    ge_cols = " & ".join(fmt_ge(stats[f]["ge_mean"]) if f in stats else "---" for f in FAMILIES)
    print()
    print("% --- LaTeX row (SR: A B C D | GE: A B C D) ---")
    print(f"  {label} & {sr_cols} & {ge_cols} \\\\")


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
