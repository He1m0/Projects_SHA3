#!/usr/bin/env python3
"""Analyze Result_Tables.zip produced by template_validation_bytes.

This script parses SR/GE LaTeX-style table files from the ZIP archive,
computes quality metrics, and writes summary reports.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

TABLE_NAME_RE = re.compile(r"(SR|GE)_table_([ABCD]\d{2})_G(\d+)\.txt$")
ROW_RE = re.compile(r"^\((\d+),\s*(\d+)\)\s*&\s*(.+?)\\\\")
NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


@dataclass
class TableMetrics:
    family_round: str
    group: int
    nbytes: int
    sr_mean: float
    sr_median: float
    sr_min: float
    sr_max: float
    ge_mean: float
    ge_median: float
    ge_min: float
    ge_max: float
    combined_score: float
    quality_label: str


def parse_row(line: str) -> Tuple[int, int, List[float]] | None:
    m = ROW_RE.match(line.strip())
    if not m:
        return None
    i = int(m.group(1))
    j = int(m.group(2))
    payload = m.group(3)
    cells = [c.strip() for c in payload.split("&")]
    values: List[float] = []
    for c in cells:
        clean = c.replace("\\", "").strip()
        n = NUM_RE.search(clean)
        if n:
            values.append(float(n.group(0)))
    if len(values) != 8:
        return None
    return i, j, values


def parse_table_content(text: str) -> Dict[int, float]:
    """Return byte_index -> value from one SR/GE table text."""
    out: Dict[int, float] = {}
    for line in text.splitlines():
        parsed = parse_row(line)
        if not parsed:
            continue
        i, j, vals = parsed
        lane = j * 5 + i
        for k, v in enumerate(vals):
            byte_idx = lane * 8 + k
            out[byte_idx] = v
    return out


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def quality_label(sr_mean: float, ge_mean: float) -> str:
    if sr_mean >= 0.20 and ge_mean <= 20:
        return "excellent"
    if sr_mean >= 0.10 and ge_mean <= 40:
        return "good"
    if sr_mean >= 0.03 and ge_mean <= 80:
        return "fair"
    return "weak"


def combined_quality_score(sr_mean: float, ge_mean: float) -> float:
    # GE in [1,256], lower is better. Map to [0,1] where 1 is best.
    ge_norm = clamp01((256.0 - ge_mean) / 255.0)
    score = 0.7 * clamp01(sr_mean) + 0.3 * ge_norm
    return score


def analyze_zip(zip_path: str) -> Tuple[List[TableMetrics], List[dict], List[dict]]:
    """Parse ZIP and return per-table metrics, aggregate metrics, and weak-byte records."""
    per_table_raw = defaultdict(lambda: {"SR": {}, "GE": {}})

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if n.endswith(".txt")]
        for name in names:
            base = os.path.basename(name)
            m = TABLE_NAME_RE.search(base)
            if not m:
                continue
            metric = m.group(1)
            family_round = m.group(2)
            group = int(m.group(3))
            text = zf.read(name).decode("utf-8", errors="replace")
            byte_map = parse_table_content(text)
            per_table_raw[(family_round, group)][metric] = byte_map

    table_metrics: List[TableMetrics] = []
    weak_bytes: List[dict] = []

    for (family_round, group), data in sorted(per_table_raw.items()):
        sr = data["SR"]
        ge = data["GE"]
        common = sorted(set(sr.keys()) & set(ge.keys()))
        if not common:
            continue

        sr_vals = [sr[b] for b in common]
        ge_vals = [ge[b] for b in common]

        sr_mean = statistics.mean(sr_vals)
        ge_mean = statistics.mean(ge_vals)

        t = TableMetrics(
            family_round=family_round,
            group=group,
            nbytes=len(common),
            sr_mean=sr_mean,
            sr_median=statistics.median(sr_vals),
            sr_min=min(sr_vals),
            sr_max=max(sr_vals),
            ge_mean=ge_mean,
            ge_median=statistics.median(ge_vals),
            ge_min=min(ge_vals),
            ge_max=max(ge_vals),
            combined_score=combined_quality_score(sr_mean, ge_mean),
            quality_label=quality_label(sr_mean, ge_mean),
        )
        table_metrics.append(t)

        for b in common:
            weak_bytes.append(
                {
                    "family_round": family_round,
                    "group": group,
                    "byte": b,
                    "sr": sr[b],
                    "ge": ge[b],
                    "weakness": ge[b] - (255.0 * sr[b]),
                }
            )

    # Aggregate by family_round over all groups.
    bucket = defaultdict(lambda: {"sr": [], "ge": [], "scores": [], "labels": []})
    for t in table_metrics:
        b = bucket[t.family_round]
        b["sr"].append(t.sr_mean)
        b["ge"].append(t.ge_mean)
        b["scores"].append(t.combined_score)
        b["labels"].append(t.quality_label)

    aggregate: List[dict] = []
    for fr in sorted(bucket.keys()):
        b = bucket[fr]
        aggregate.append(
            {
                "family_round": fr,
                "groups": len(b["sr"]),
                "sr_mean_avg": statistics.mean(b["sr"]),
                "ge_mean_avg": statistics.mean(b["ge"]),
                "combined_score_avg": statistics.mean(b["scores"]),
                "best_label": sorted(b["labels"])[0],
                "worst_label": sorted(b["labels"])[-1],
            }
        )

    weak_bytes.sort(key=lambda x: (x["weakness"], x["ge"], -x["sr"]), reverse=True)
    return table_metrics, aggregate, weak_bytes


def write_csv(path: str, rows: List[dict], fieldnames: List[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_table_line(t: TableMetrics) -> str:
    return (
        f"{t.family_round} G{t.group}: "
        f"SR(mean={t.sr_mean:.4f}, min={t.sr_min:.4f}, max={t.sr_max:.4f}) | "
        f"GE(mean={t.ge_mean:.2f}, min={t.ge_min:.2f}, max={t.ge_max:.2f}) | "
        f"score={t.combined_score:.4f} -> {t.quality_label}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze Result_Tables.zip quality")
    ap.add_argument("zip_path", nargs="?", default="Result_Tables.zip", help="Path to Result_Tables.zip")
    ap.add_argument("--out", default="quality_report", help="Output directory for reports")
    ap.add_argument("--top", type=int, default=20, help="Top-N weakest bytes to include")
    args = ap.parse_args()

    if not os.path.isfile(args.zip_path):
        print(f"Error: cannot find ZIP file: {args.zip_path}")
        return 2

    os.makedirs(args.out, exist_ok=True)

    table_metrics, aggregate, weak_bytes = analyze_zip(args.zip_path)
    if not table_metrics:
        print("No SR/GE tables found in ZIP.")
        return 3

    # Per-table CSV.
    table_rows = [
        {
            "family_round": t.family_round,
            "group": t.group,
            "nbytes": t.nbytes,
            "sr_mean": f"{t.sr_mean:.6f}",
            "sr_median": f"{t.sr_median:.6f}",
            "sr_min": f"{t.sr_min:.6f}",
            "sr_max": f"{t.sr_max:.6f}",
            "ge_mean": f"{t.ge_mean:.6f}",
            "ge_median": f"{t.ge_median:.6f}",
            "ge_min": f"{t.ge_min:.6f}",
            "ge_max": f"{t.ge_max:.6f}",
            "combined_score": f"{t.combined_score:.6f}",
            "quality_label": t.quality_label,
        }
        for t in table_metrics
    ]
    write_csv(
        os.path.join(args.out, "summary_tables.csv"),
        table_rows,
        [
            "family_round",
            "group",
            "nbytes",
            "sr_mean",
            "sr_median",
            "sr_min",
            "sr_max",
            "ge_mean",
            "ge_median",
            "ge_min",
            "ge_max",
            "combined_score",
            "quality_label",
        ],
    )

    # Aggregate CSV.
    agg_rows = [
        {
            "family_round": r["family_round"],
            "groups": r["groups"],
            "sr_mean_avg": f"{r['sr_mean_avg']:.6f}",
            "ge_mean_avg": f"{r['ge_mean_avg']:.6f}",
            "combined_score_avg": f"{r['combined_score_avg']:.6f}",
            "best_label": r["best_label"],
            "worst_label": r["worst_label"],
        }
        for r in aggregate
    ]
    write_csv(
        os.path.join(args.out, "summary_family_round.csv"),
        agg_rows,
        [
            "family_round",
            "groups",
            "sr_mean_avg",
            "ge_mean_avg",
            "combined_score_avg",
            "best_label",
            "worst_label",
        ],
    )

    # Weakest bytes CSV.
    weak_top = weak_bytes[: max(1, args.top)]
    weak_rows = [
        {
            "family_round": r["family_round"],
            "group": r["group"],
            "byte": r["byte"],
            "sr": f"{r['sr']:.6f}",
            "ge": f"{r['ge']:.6f}",
            "weakness": f"{r['weakness']:.6f}",
        }
        for r in weak_top
    ]
    write_csv(
        os.path.join(args.out, "weakest_bytes_top.csv"),
        weak_rows,
        ["family_round", "group", "byte", "sr", "ge", "weakness"],
    )

    # Text report.
    report_path = os.path.join(args.out, "report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Template Quality Report\n")
        f.write("=======================\n\n")
        f.write(f"Input ZIP: {args.zip_path}\n")
        f.write(f"Parsed tables: {len(table_metrics)}\n\n")

        f.write("Per-table metrics\n")
        f.write("-----------------\n")
        for t in table_metrics:
            f.write(format_table_line(t) + "\n")

        f.write("\nAggregated by family+round\n")
        f.write("--------------------------\n")
        for r in aggregate:
            f.write(
                f"{r['family_round']}: groups={r['groups']} | "
                f"SR(avg)={r['sr_mean_avg']:.4f} | GE(avg)={r['ge_mean_avg']:.2f} | "
                f"score(avg)={r['combined_score_avg']:.4f}\n"
            )

        f.write("\nTop weakest bytes\n")
        f.write("-----------------\n")
        for r in weak_top:
            f.write(
                f"{r['family_round']} G{r['group']} byte={r['byte']}: "
                f"SR={r['sr']:.4f}, GE={r['ge']:.2f}, weakness={r['weakness']:.2f}\n"
            )

    print(f"Done. Reports written to: {args.out}")
    print(f"Main report: {report_path}")
    print(f"Best table: {max(table_metrics, key=lambda x: x.combined_score).family_round} "
          f"G{max(table_metrics, key=lambda x: x.combined_score).group}")
    print(f"Worst table: {min(table_metrics, key=lambda x: x.combined_score).family_round} "
          f"G{min(table_metrics, key=lambda x: x.combined_score).group}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
