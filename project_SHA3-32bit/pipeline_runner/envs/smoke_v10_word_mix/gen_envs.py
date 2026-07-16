#!/usr/bin/env python3
"""Generate smoke v10 word-mix sigma sweep env files (36 total: 4 pure
modes x 9 sigmas).

Word-mix clone of smoke_v8_granularity_word_sigma_sweep, with two
corrections beyond the mechanical SIM_MODE->SIM_*_SCALE swap (verified by
diffing the output against the 4 hand-written v10 sigma1p0 files):

1. Trace-length vars: smoke_v8's word mode emits 1 sample/leak() call, so
   its gen_envs.py divided them by 4 (55296 -> 13824). Word-mix emits 4
   samples/leak() call, same as byte mode, so those vars need to go back to
   the byte-mode value (55296) -- multiply smoke_v8's word-mode value by 4
   rather than carrying it over unchanged.
2. `hw` mode's source file has no explicit `SIM_HW_SCALE` line (the old
   mode-selection code derived it as an implicit default); KeccakSim_v4 has
   no such default, so `SIM_HW_SCALE=1.0` must be added explicitly wherever
   a mode's source file doesn't already set its own scale var.

ICS level/tags are carried over unchanged -- each sigma already has its own
correct, previously-scanned level in the source file.
"""
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENVS_DIR = os.path.dirname(SCRIPT_DIR)
SOURCE_DIR = os.path.join(ENVS_DIR, "smoke_v8_granularity_word_sigma_sweep")

SIGMAS = ["0p1", "0p5", "1p0", "1p5", "2p0", "2p5", "3p0", "3p5", "4p0"]
SIGMA_DISPLAY = {s: s.replace("p", ".") for s in SIGMAS}

MODE_LABEL = {
    "hw": "HW mode",
    "hd": "Pure HD (hd_scale=1.0)",
    "f9": "F9 mode (SNR-equalized, f9_scale=1.7321)",
    "id": "Identity mode (SNR-equalized, id_scale=0.01913)",
}

# Only hw's source lacks its own explicit scale line (see module docstring).
MISSING_SCALE_LINE = {
    "hw": "SIM_HW_SCALE=1.0\n",
}

TRACE_LEN_VARS = (
    "SHA3_REFERENCE_TRACE_LEN",
    "SHA3_DETECTION_TRACE_LEN",
    "SHA3_DETECTION_OUTPUT_SIZE",
    "SHA3_TRAINING_TRACE_LEN",
    "SHA3_TRAINING_OUTPUT_SIZE",
    "SHA3_VALIDATION_OUTPUT_SIZE",
)

HEADER_TMPL = """\
# smoke_v10_word_mix -- word-mix-kernel clone of {src_name}.
# SIM_SCRIPT=KeccakSim_v4.py, SIM_EMISSION_KERNEL=word-mix (4 samples/leak
# event instead of 1); SIM_MODE dropped (v4 has no mode -- see
# KeccakSim_v4.py's docstring), replaced by the explicit SIM_*_SCALE vars
# already present in the source file. Kernel offsets/sigma default to the
# empirical fit in EMPIRICAL_word_mix_kernel_fit.md (not overridden here).
# {mode_label}, sigma={sigma_display}.
"""

count = 0
for mode, mode_label in MODE_LABEL.items():
    for sigma in SIGMAS:
        src_name = f".env_smoke_v8_granularity_word_{mode}_sigma{sigma}"
        src_path = os.path.join(SOURCE_DIR, src_name)
        with open(src_path) as f:
            content = f.read()

        content, n_header = re.subn(r"^(#.*\n)+", "", content)
        if n_header != 1:
            raise ValueError(f"{src_path}: expected a leading '#' comment block to strip, found none")

        content, n_mode = re.subn(
            r"^SIM_MODE=\w+\n", MISSING_SCALE_LINE.get(mode, ""), content, flags=re.M
        )
        if n_mode != 1:
            raise ValueError(f"{src_path}: expected exactly one SIM_MODE= line, found {n_mode}")

        for var in TRACE_LEN_VARS:
            content, n = re.subn(
                rf"^{var}=13824$",
                f"{var}=55296",
                content,
                count=1,
                flags=re.M,
            )
            if n != 1:
                raise ValueError(f"{src_path}: expected exactly one {var}=13824 line, found {n}")

        content, n_seed = re.subn(
            r"^SIM_SEED_RE=",
            "SIM_SCRIPT_OVERRIDE=${WORKSPACE_DIR}/KeccakSim_v4.py\n"
            "SIM_EMISSION_KERNEL=word-mix\n"
            "SIM_SEED_RE=",
            content,
            count=1,
            flags=re.M,
        )
        if n_seed != 1:
            raise ValueError(f"{src_path}: expected exactly one SIM_SEED_RE= line, found {n_seed}")

        header = HEADER_TMPL.format(
            src_name=src_name, mode_label=mode_label, sigma_display=SIGMA_DISPLAY[sigma]
        )
        out_name = f".env_smoke_v10_word_mix_{mode}_sigma{sigma}"
        out_path = os.path.join(SCRIPT_DIR, out_name)
        with open(out_path, "w") as f:
            f.write(header + content)
        count += 1
        print(f"  wrote {out_name}  (from {src_name})")

print(f"\nGenerated {count} env files.")
