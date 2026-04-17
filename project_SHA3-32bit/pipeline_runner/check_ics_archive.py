#!/usr/bin/env python3

import argparse
import io
import re
import sys
import zipfile
from collections import defaultdict

import numpy as np


ICS_NAME_RE = re.compile(r"ics_([ABCD]\d{2})_i(\d{2})\.npy$")


def expected_entries(round_count: int, ab_words: int, cd_words: int):
    entries = []
    for rd in range(round_count):
        tag_a = f"A{rd:02d}"
        tag_b = f"B{rd:02d}"
        tag_c = f"C{rd:02d}"
        tag_d = f"D{rd:02d}"
        entries.extend((tag_a, i) for i in range(ab_words))
        entries.extend((tag_b, i) for i in range(ab_words))
        entries.extend((tag_c, i) for i in range(cd_words))
        entries.extend((tag_d, i) for i in range(cd_words))
    return entries


def load_zip_arrays(ics_zip: str):
    arrays = {}
    with zipfile.ZipFile(ics_zip, "r") as zf:
        for name in zf.namelist():
            m = ICS_NAME_RE.search(name)
            if not m:
                continue
            tag = m.group(1)
            idx = int(m.group(2))
            with zf.open(name) as f:
                data = f.read()
            arr = np.load(io.BytesIO(data), allow_pickle=False)
            arr = np.asarray(arr).reshape(-1)
            arrays[(tag, idx)] = arr
    return arrays


def main():
    parser = argparse.ArgumentParser(
        description="Validate ICS archive contains expected non-empty arrays for training IoPs."
    )
    parser.add_argument("--ics-zip", required=True, help="Path to ics_original_XXX.zip")
    parser.add_argument("--round-count", type=int, default=4, help="Number of rounds expected")
    parser.add_argument("--ab-words", type=int, default=50, help="Word count for A/B tags")
    parser.add_argument("--cd-words", type=int, default=10, help="Word count for C/D tags")
    parser.add_argument("--max-empty", type=int, default=0, help="Allowed number of empty ICS arrays")
    parser.add_argument("--max-missing", type=int, default=0, help="Allowed number of missing ICS arrays")
    parser.add_argument("--report-limit", type=int, default=20, help="Max missing/empty entries to print")
    args = parser.parse_args()

    arrays = load_zip_arrays(args.ics_zip)
    expected = expected_entries(args.round_count, args.ab_words, args.cd_words)

    missing = []
    empty = []
    by_tag_counts = defaultdict(int)
    by_tag_empty = defaultdict(int)

    for key in expected:
        if key not in arrays:
            missing.append(key)
            continue
        tag, _ = key
        by_tag_counts[tag] += 1
        if arrays[key].size == 0:
            empty.append(key)
            by_tag_empty[tag] += 1

    print("ICS validation summary")
    print(f"  archive: {args.ics_zip}")
    print(f"  expected entries: {len(expected)}")
    print(f"  found entries:    {len(arrays)}")
    print(f"  missing entries:  {len(missing)}")
    print(f"  empty entries:    {len(empty)}")

    if by_tag_counts:
        print("  per-tag empty counts:")
        for tag in sorted(by_tag_counts.keys()):
            print(f"    {tag}: {by_tag_empty.get(tag, 0)}/{by_tag_counts[tag]}")

    if missing:
        print("Missing entries (sample):")
        for tag, idx in missing[: args.report_limit]:
            print(f"  {tag} i{idx:02d}")

    if empty:
        print("Empty entries (sample):")
        for tag, idx in empty[: args.report_limit]:
            print(f"  {tag} i{idx:02d}")

    if len(missing) > args.max_missing or len(empty) > args.max_empty:
        print("ERROR: ICS archive validation failed.")
        print(
            "Hint: lower SHA3_TRAINING_ICS_LEVEL (for example 10) or regenerate traces/detection with stronger signal."
        )
        return 1

    print("OK: ICS archive validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
