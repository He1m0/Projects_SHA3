#!/usr/bin/env python3
"""Generate paperscale v6 pure-HD sigma sweep env files (9 total).

Promotes pure HD (mode=hd, no HW/F9/ID component) from the smoke-scale sweep
(smoke_v7_hd_pure_sigma*, done and archived) to paperscale scale, alongside
the F9/ID SNR-equalized paperscale_v5 sweep. Trace counts / SASCA params
copied from paperscale_v5 (100 det, 400 training, 40 val, 1000 SASCA;
iter=200, 201 rate points, 8-bit step) for direct comparability.

ICS level 40 carried forward from smoke_v7 as a *starting* value only --
Part 8 of RUN_LOG_hd_promotion.md explicitly calls for re-verifying this at
paperscale scale via a detection-only phase before committing to training
(paperscale's 100 detection sets vs. smoke's 10 could shift the level).
"""
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SIGMAS = [
    ("0p1", 0.1, 1), ("0p5", 0.5, 2), ("1p0", 1.0, 3),
    ("1p5", 1.5, 4), ("2p0", 2.0, 5), ("2p5", 2.5, 6),
    ("3p0", 3.0, 7), ("3p5", 3.5, 8), ("4p0", 4.0, 9),
]

TEMPLATE = """\
# KeccakSim_v3 -- pure HD (mode=hd, hd_scale=1.0 default), paperscale-v6 noise sweep: sigma={sigma_f}.
# Promotes pure HD from the smoke-scale sweep (smoke_v7_hd_pure_sigma{sigma_s}) to
# paperscale scale, alongside the F9/ID SNR-equalized paperscale_v5 sweep.
# ICS level 40 is a STARTING value carried from smoke_v7 -- Part 8 of
# RUN_LOG_hd_promotion.md requires re-verifying per sigma at paperscale scale
# (detection-only phase first) before training onward -- do not assume it holds.
# Paperscale-v6: 10 ref, 100 det, 400 training, 40 val sets, 1000 SASCA traces (iter=200).
# Comparable to paperscale-v5 (F9/ID). Sweep step {step}/9.
SHA3_INPUTS=16
SHA3_INVOCATIONS=10

SHA3_REFERENCE_FOLDERS=10
SHA3_REFERENCE_TRACE_LEN=55296

SHA3_DETECTION_TRACE_LEN=55296
SHA3_DETECTION_SET_COUNT=100
SHA3_DETECTION_SETS_PER_PART=25
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

SHA3_TRAINING_SET_COUNT=400
SHA3_TRAINING_TRACE_LEN=55296
SHA3_TRAINING_TRACE_OFFSET=0
SHA3_TRAINING_PPC=1
SHA3_TRAINING_OUTPUT_SIZE=55296
SHA3_TRAINING_SETS_PER_PART=25
SHA3_TRAINING_CORR_BOUND=0.0
SHA3_TRAINING_ICS_LEVEL=40

SHA3_VALIDATION_INPUTS=10
SHA3_VALIDATION_SET_COUNT=40
SHA3_VALIDATION_TRACE_OFFSET=0
SHA3_VALIDATION_PPC=1
SHA3_VALIDATION_OUTPUT_SIZE=55296
SHA3_VALIDATION_CORR_BOUND=0.0
SHA3_VALIDATION_SETS_PER_PART=10
SHA3_VALIDATION_TEMPLATE_TAG=40
SHA3_VALIDATION_ICS_TAG=40

SHA3_SASCA_TRACE_COUNT=1000
SHA3_SASCA_TEMPLATE_TAG=40
SHA3_SASCA_ICS_TAG=40
SHA3_SASCA_PPC=1
SHA3_SASCA_ITERATION_COUNT=200
SHA3_SASCA_RATE_BP_ITERATION_COUNT=200
SHA3_SASCA_RATE_POINT_COUNT=201
SHA3_SASCA_RATE_STEP_BITS=8
SHA3_SASCA_ALLOWED_WRONG_BITS=0
SHA3_SASCA_OUTPUT_BITS=512

TRACES_DIR=/storage/ge96pug/traces_paperscale_v6_hd_pure_sigma{sigma_s}

SIM_ALGORITHM=sha3-512
SIM_TRACE_FORMAT=bin
SIM_TRACE_DTYPE=float64
SIM_BULK_DATA_FORMAT=hex
SIM_GRANULARITY=byte
SIM_NOISE_SIGMA={sigma_f}
SIM_MODE=hd
SIM_HD_SCALE=1.0
SIM_SEED_RE=128
SIM_SEED_DN=256
SIM_SEED_TR=512
SIM_SEED_TS=1024
"""

count = 0
for sigma_s, sigma_f, step in SIGMAS:
    content = TEMPLATE.format(sigma_f=sigma_f, sigma_s=sigma_s, step=step)
    subdir = os.path.join(SCRIPT_DIR, f"sigma{sigma_s}")
    os.makedirs(subdir, exist_ok=True)
    fname = os.path.join(subdir, f".env_paperscale_v6_hd_pure_sigma{sigma_s}")
    with open(fname, "w") as f:
        f.write(content)
    count += 1
    print(f"  wrote {fname}")

print(f"\nGenerated {count} env files.")
