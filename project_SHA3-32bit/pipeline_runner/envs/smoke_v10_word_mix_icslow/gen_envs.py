#!/usr/bin/env python3
"""Generate the smoke v10 low-ICS-level side test (12 files: 4 modes x
sigma in {0.1, 0.5, 1.0}).

Clones of the matching smoke_v10_word_mix sigma files, with
SHA3_TRAINING_ICS_LEVEL/_VALIDATION_TEMPLATE_TAG/_VALIDATION_ICS_TAG/
_SASCA_TEMPLATE_TAG/_SASCA_ICS_TAG forced to 10 (the lowest/most permissive
threshold, ics_original_010.zip) instead of each mode's normal
auto-selected level -- to see how a looser/larger ICS feature set changes
LDA/SASCA outcomes. Distinct sandbox label (`_icslow_`) so these don't
collide with the main sweep's sandboxes at the same sigma.
"""
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENVS_DIR = os.path.dirname(SCRIPT_DIR)
SOURCE_DIR = os.path.join(ENVS_DIR, "smoke_v10_word_mix")

SIGMAS = ["0p1", "0p5", "1p0"]
MODES = ("hw", "hd", "f9", "id")

FORCED_ICS_VARS = (
    "SHA3_TRAINING_ICS_LEVEL",
    "SHA3_VALIDATION_TEMPLATE_TAG",
    "SHA3_VALIDATION_ICS_TAG",
    "SHA3_SASCA_TEMPLATE_TAG",
    "SHA3_SASCA_ICS_TAG",
)

HEADER_TMPL = """\
# smoke_v10_word_mix_icslow -- {src_name}, with ICS level forced to the
# lowest threshold (010, the most permissive -- widest surviving point set)
# instead of the auto-selected level, to see how a looser/larger ICS
# feature set changes LDA/SASCA outcomes. Deliberately forced, not
# auto-selected -- not directly comparable to the main sweep's per-sigma-
# optimal levels.
"""

count = 0
for mode in MODES:
    for sigma in SIGMAS:
        src_name = f".env_smoke_v10_word_mix_{mode}_sigma{sigma}"
        src_path = os.path.join(SOURCE_DIR, src_name)
        with open(src_path) as f:
            content = f.read()

        content, n_header = re.subn(r"^(#.*\n)+", "", content)
        if n_header != 1:
            raise ValueError(f"{src_path}: expected a leading '#' comment block to strip, found none")

        for var in FORCED_ICS_VARS:
            content, n = re.subn(rf"^{var}=\d+$", f"{var}=10", content, count=1, flags=re.M)
            if n != 1:
                raise ValueError(f"{src_path}: expected exactly one {var}=<N> line, found {n}")

        header = HEADER_TMPL.format(src_name=src_name)
        out_name = f".env_smoke_v10_word_mix_icslow_{mode}_sigma{sigma}"
        out_path = os.path.join(SCRIPT_DIR, out_name)
        with open(out_path, "w") as f:
            f.write(header + content)
        count += 1
        print(f"  wrote {out_name}  (from {src_name})")

print(f"\nGenerated {count} env files.")
