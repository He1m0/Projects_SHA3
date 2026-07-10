#!/usr/bin/env python3
"""Generate smoke v6 F9+HW mixed-leakage sigma sweep env files (9 total).

Motivation: the smoke_v6_f9mixed diagnostic (sec:eval-f9-mixed) found F9+HW is the
only mixed-leakage configuration that beats pure F9, but only at a single sigma (1.0).
This sweep extends that comparison across the full 9-point noise range to see whether
the advantage holds, narrows, or reverses with noise. Paperscale-scale would take too
long for a diagnostic sweep, so this stays at smoke scale like the rest of the
f9mixed diagnostics.

SNR-equalized convention (matches smoke_v6 pure-F9/ID sweep and the existing
smoke_v6_f9mixed_hw_sigma1p0 diagnostic): SIM_F9_SCALE=1.7321=sqrt(3) so F9's
Var_signal=2.0, matching HW at hw_scale=1.0. SIM_HD_SCALE=0.0 (no HD component
in this mode -- F9+HW only).

ICS level 90 uniformly, same as smoke_v6.

sigma=1.0 was already run and archived as smoke_v6_f9mixed_hw_sigma1p0
(runs_archive/smoke_v6/2026-07-03_smoke_v6_f9mixed_hw_sigma1p0) -- this script
regenerates it too for a single source of truth, but the launcher skips relaunching it.
"""
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SIGMAS = [
    ("0p1", 0.1, 1), ("0p5", 0.5, 2), ("1p0", 1.0, 3),
    ("1p5", 1.5, 4), ("2p0", 2.0, 5), ("2p5", 2.5, 6),
    ("3p0", 3.0, 7), ("3p5", 3.5, 8), ("4p0", 4.0, 9),
]

TEMPLATE = """\
# KeccakSim_v2 -- mixed (F9 + HW, no HD), SNR-equalized (f9_scale=1.7321=sqrt(3), hw_scale=1.0), sigma={sigma_f}.
# F9 component: SNR_var=2/sigma^2. HW component: SNR_var=2/sigma^2 (scale=1.0, unchanged).
# Extends the smoke_v6_f9mixed_hw_sigma1p0 diagnostic (tab:f9-mixed-equalized) into a
# full 9-point noise sweep: F9+HW was the only mixed mode beating pure F9, at sigma=1.0 only.
# Smoke: 10 ref, 10 det, 50 training, 20 validation sets, 50 SASCA traces. ICS level 90.
# Sweep step {step}/9.
SHA3_INPUTS=16
SHA3_INVOCATIONS=10

SHA3_REFERENCE_FOLDERS=10
SHA3_REFERENCE_TRACE_LEN=55296

SHA3_DETECTION_TRACE_LEN=55296
SHA3_DETECTION_SET_COUNT=10
SHA3_DETECTION_SETS_PER_PART=10
SHA3_DETECTION_CORR_BOUND=0.0
SHA3_DETECTION_TRACE_OFFSET=0
SHA3_DETECTION_PPC=1
SHA3_DETECTION_OUTPUT_SIZE=55296
SHA3_DETECTION_ROUNDS=4
SHA3_DETECTION_ICS_WORDS_AB=50
SHA3_DETECTION_ICS_WORDS_CD=10
SHA3_DETECTION_ICS_THRESHOLDS=0.09,0.08,0.07,0.06,0.05,0.04,0.03,0.02,0.01
SHA3_DETECTION_SAMPLE_SHIFT=0
SHA3_DETECTION_SAMPLE_WIDTH=1

SHA3_TRAINING_SET_COUNT=50
SHA3_TRAINING_TRACE_LEN=55296
SHA3_TRAINING_TRACE_OFFSET=0
SHA3_TRAINING_PPC=1
SHA3_TRAINING_OUTPUT_SIZE=55296
SHA3_TRAINING_SETS_PER_PART=25
SHA3_TRAINING_CORR_BOUND=0.0
SHA3_TRAINING_ICS_LEVEL=90

SHA3_VALIDATION_INPUTS=10
SHA3_VALIDATION_SET_COUNT=20
SHA3_VALIDATION_TRACE_OFFSET=0
SHA3_VALIDATION_PPC=1
SHA3_VALIDATION_OUTPUT_SIZE=55296
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
SIM_GRANULARITY=byte
SIM_NOISE_SIGMA={sigma_f}
SIM_MODE=mixed
SIM_HW_SCALE=1.0
SIM_HD_SCALE=0.0
SIM_F9_SEED=2839
SIM_F9_C8_RANGE=0.5
SIM_F9_SCALE=1.7321
SIM_SEED_RE=128
SIM_SEED_DN=256
SIM_SEED_TR=512
SIM_SEED_TS=1024
"""

count = 0
for sigma_s, sigma_f, step in SIGMAS:
    content = TEMPLATE.format(sigma_f=sigma_f, step=step)
    fname = os.path.join(SCRIPT_DIR, f".env_smoke_v6_f9mixed_hw_sigma{sigma_s}")
    with open(fname, "w") as f:
        f.write(content)
    count += 1
    print(f"  wrote {fname}")

print(f"\nGenerated {count} env files.")
