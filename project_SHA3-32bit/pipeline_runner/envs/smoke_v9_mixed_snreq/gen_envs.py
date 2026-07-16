#!/usr/bin/env python3
"""Generate smoke v9 mixed-mode total-variance-equalized env files.

Motivation: every existing mixed-mode leakage config (HW+HD combined,
F9+HD, F9+HW, F9+HW+HD) sums components at their *single-mode-equalized*
scales, so total raw signal variance scales with the number of active
components instead of holding at the fixed reference (Var=2.0, matching
Pure HW/HD/F9 at their own equalized scales):

  - HW+HD combined (smoke_v5_sigma_sweep, .env_smoke_v5_hd_sigma*):
    hw_scale=1.0 (Var 2.0) + hd_scale=0.5 (Var 0.5) = Var 2.5
  - F9+HD (smoke_v6_f9mixed_sigma_sweep, sigma=1.0 only):
    f9_scale=1.7321 (Var 2.0) + hd_scale=1.0 (Var 2.0) = Var 4.0
  - F9+HW (smoke_v6_f9mixed_hw_sigma_sweep, 9-pt + sigma=1.0 diagnostic):
    f9_scale=1.7321 (Var 2.0) + hw_scale=1.0 (Var 2.0) = Var 4.0
  - F9+HW+HD (smoke_v6_f9mixed_sigma_sweep, sigma=1.0 only):
    f9_scale=1.7321 (Var 2.0) + hw_scale=1.0 (Var 2.0) + hd_scale=1.0 (Var 2.0) = Var 6.0

This sweep supersedes all four with an equal-split convention: for a config
with N active components, each component is scaled so its own contribution
is 2.0/N, i.e. scale_i = sqrt((2.0/N) / raw_var_i), where raw_var at scale=1.0
is HW=2.0, HD=2.0, F9=0.667 (KeccakSim_v3 constants). This holds every
config's total at SNR_var=2.0/sigma^2, matching every single-mode baseline.

Resulting scales (see ~/.claude/plans/prepare-a-plan-run-log-for-jiggly-grove.md
for the full derivation):
  - hwhd:   hw_scale=0.7071, hd_scale=0.7071            (N=2, target 1.0 each)
  - f9hw:   f9_scale=1.2247, hw_scale=0.7071             (N=2, target 1.0 each)
  - f9hd:   f9_scale=1.2247, hd_scale=0.7071             (N=2, target 1.0 each)
  - f9hwhd: f9_scale=1.0000, hw_scale=0.5774, hd_scale=0.5774  (N=3, target 0.6667 each)

Scope: hwhd and f9hw get the full 9-point sigma sweep (they already had one,
just at the wrong total variance). f9hd and f9hwhd stay sigma=1.0 only,
matching what's actually cited in thesis tab:f9-mixed-equalized -- no full
sweep existed for these two before either.

ICS level is left at 90 for all four here as a starting point, matching the
pre-existing mixed-mode convention -- but per the run log, this is NOT
assumed to hold for the HD-containing configs (hwhd, f9hd, f9hwhd), since
diluting HD's own scale plausibly weakens its already-fragile per-byte
discriminability (pure HD needed level 40, a structural gap -- see
sec:disc-limitations). The launcher's sanity wave + check_ics_archive.py
scan (RUN_LOG_mixed_snreq.md) determines the real level per config before
the full sweep is committed; this script only writes the starting-point 90.

Word granularity (2026-07-14): switched from SIM_GRANULARITY=byte to word
and halved-then-halved-again the four trace-length vars (55296 -> 13824,
same /4 substitution as envs/smoke_v8_granularity_word_sigma_sweep/gen_envs.py)
before this family was ever launched -- the byte-granularity mismatch
between the 8-bit-packed simulator default and the 32-bit target/SASCA
model was identified as a correctness issue for the whole thesis, so every
new sweep (this one included) now defaults to word granularity. ICS level
is even less certain under word granularity than the byte-era starting
guess of 90 above -- do not assume it holds for ANY of the four configs,
not just the HD-containing ones; auto_sweep_monitor.sh's gate-sigma step
resolves this automatically per config.
"""
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SIGMAS = [
    ("0p1", 0.1, 1), ("0p5", 0.5, 2), ("1p0", 1.0, 3),
    ("1p5", 1.5, 4), ("2p0", 2.0, 5), ("2p5", 2.5, 6),
    ("3p0", 3.0, 7), ("3p5", 3.5, 8), ("4p0", 4.0, 9),
]

COMMON = """\
SHA3_INPUTS=16
SHA3_INVOCATIONS=10

SHA3_REFERENCE_FOLDERS=10
SHA3_REFERENCE_TRACE_LEN=13824

SHA3_DETECTION_TRACE_LEN=13824
SHA3_DETECTION_SET_COUNT=10
SHA3_DETECTION_SETS_PER_PART=10
SHA3_DETECTION_CORR_BOUND=0.0
SHA3_DETECTION_TRACE_OFFSET=0
SHA3_DETECTION_PPC=1
SHA3_DETECTION_OUTPUT_SIZE=13824
SHA3_DETECTION_ROUNDS=4
SHA3_DETECTION_ICS_WORDS_AB=50
SHA3_DETECTION_ICS_WORDS_CD=10
SHA3_DETECTION_ICS_THRESHOLDS=0.09,0.08,0.07,0.06,0.05,0.04,0.03,0.02,0.01
SHA3_DETECTION_SAMPLE_SHIFT=0
SHA3_DETECTION_SAMPLE_WIDTH=1

SHA3_TRAINING_SET_COUNT=50
SHA3_TRAINING_TRACE_LEN=13824
SHA3_TRAINING_TRACE_OFFSET=0
SHA3_TRAINING_PPC=1
SHA3_TRAINING_OUTPUT_SIZE=13824
SHA3_TRAINING_SETS_PER_PART=25
SHA3_TRAINING_CORR_BOUND=0.0
SHA3_TRAINING_ICS_LEVEL=90

SHA3_VALIDATION_INPUTS=10
SHA3_VALIDATION_SET_COUNT=20
SHA3_VALIDATION_TRACE_OFFSET=0
SHA3_VALIDATION_PPC=1
SHA3_VALIDATION_OUTPUT_SIZE=13824
SHA3_VALIDATION_CORR_BOUND=0.0
SHA3_VALIDATION_SETS_PER_PART=10
SHA3_VALIDATION_TEMPLATE_TAG=90
SHA3_VALIDATION_ICS_TAG=90

SHA3_SASCA_TRACE_COUNT=50
SHA3_SASCA_TEMPLATE_TAG=90
SHA3_SASCA_ICS_TAG=90
SHA3_SASCA_PPC=1
SHA3_SASCA_ITERATION_COUNT=200
SHA3_SASCA_RATE_BP_ITERATION_COUNT=200
SHA3_SASCA_RATE_POINT_COUNT=201
SHA3_SASCA_RATE_STEP_BITS=8
SHA3_SASCA_ALLOWED_WRONG_BITS=0
SHA3_SASCA_OUTPUT_BITS=512


SIM_ALGORITHM=sha3-512
SIM_TRACE_FORMAT=bin
SIM_TRACE_DTYPE=float64
SIM_BULK_DATA_FORMAT=hex
SIM_GRANULARITY=word
SIM_NOISE_SIGMA={sigma_f}
"""

SIM_FOOTER = """\
SIM_F9_SEED=2839
SIM_F9_C8_RANGE=0.5
SIM_SEED_RE=128
SIM_SEED_DN=256
SIM_SEED_TR=512
SIM_SEED_TS=1024
"""

# Each config: (header comment, sim-mode block, full sigma sweep?)
CONFIGS = {
    "hwhd": {
        "comment": (
            "# KeccakSim_v3 -- HW+HD combined, total-variance-equalized (hw_scale=0.7071,\n"
            "# hd_scale=0.7071, each contributing Var=1.0 -> total Var=2.0), sigma={sigma_f}.\n"
            "# Supersedes smoke_v5_sigma_sweep .env_smoke_v5_hd_sigma{sigma_s} (hw=1.0/hd=0.5,\n"
            "# total Var=2.5 -- not equalized against the single-mode Var=2.0 reference).\n"
            "# Sweep step {step}/9.\n"
        ),
        "sim_mode": "SIM_MODE=hw\nSIM_HW_SCALE=0.7071\nSIM_HD_SCALE=0.7071\n",
        "full_sweep": True,
    },
    "f9hw": {
        "comment": (
            "# KeccakSim_v3 -- F9+HW, total-variance-equalized (f9_scale=1.2247, hw_scale=0.7071,\n"
            "# each contributing Var=1.0 -> total Var=2.0), sigma={sigma_f}.\n"
            "# Supersedes smoke_v6_f9mixed_hw_sigma_sweep (f9=1.7321/hw=1.0, total Var=4.0 --\n"
            "# each component individually equalized but summed, not jointly equalized).\n"
            "# Sweep step {step}/9.\n"
        ),
        "sim_mode": "SIM_MODE=mixed\nSIM_HW_SCALE=0.7071\nSIM_HD_SCALE=0.0\nSIM_F9_SCALE=1.2247\n",
        "full_sweep": True,
    },
    "f9hd": {
        "comment": (
            "# KeccakSim_v3 -- F9+HD, total-variance-equalized (f9_scale=1.2247, hd_scale=0.7071,\n"
            "# each contributing Var=1.0 -> total Var=2.0), sigma={sigma_f}.\n"
            "# Supersedes smoke_v6_f9mixed_sigma_sweep .env_smoke_v6_f9mixed_hd_sigma1p0\n"
            "# (f9=1.7321/hd=1.0, total Var=4.0). sigma=1.0 only -- matches tab:f9-mixed-equalized,\n"
            "# no full sweep exists for this config.\n"
        ),
        "sim_mode": "SIM_MODE=f9\nSIM_HD_SCALE=0.7071\nSIM_F9_SCALE=1.2247\n",
        "full_sweep": False,
    },
    "f9hwhd": {
        "comment": (
            "# KeccakSim_v3 -- F9+HW+HD, total-variance-equalized (f9_scale=1.0000, hw_scale=0.5774,\n"
            "# hd_scale=0.5774, each contributing Var=0.6667 -> total Var=2.0), sigma={sigma_f}.\n"
            "# Supersedes smoke_v6_f9mixed_sigma_sweep .env_smoke_v6_f9mixed_hwhd_sigma1p0\n"
            "# (f9=1.7321/hw=1.0/hd=1.0, total Var=6.0). sigma=1.0 only -- matches\n"
            "# tab:f9-mixed-equalized, no full sweep exists for this config.\n"
        ),
        "sim_mode": "SIM_MODE=mixed\nSIM_HW_SCALE=0.5774\nSIM_HD_SCALE=0.5774\nSIM_F9_SCALE=1.0000\n",
        "full_sweep": False,
    },
}

count = 0
for cfg_name, cfg in CONFIGS.items():
    sigmas = SIGMAS if cfg["full_sweep"] else [("1p0", 1.0, 3)]
    for sigma_s, sigma_f, step in sigmas:
        content = (
            cfg["comment"].format(sigma_f=sigma_f, sigma_s=sigma_s, step=step)
            + COMMON.format(sigma_f=sigma_f)
            + cfg["sim_mode"]
            + SIM_FOOTER
        )
        fname = os.path.join(SCRIPT_DIR, f".env_smoke_v9_mixed_snreq_{cfg_name}_sigma{sigma_s}")
        with open(fname, "w") as f:
            f.write(content)
        count += 1
        print(f"  wrote {fname}")

print(f"\nGenerated {count} env files.")
