#!/usr/bin/env python3
"""Generate paperscale v5 sigma sweep env files (18 total: 2 modes × 9 sigmas).

SNR-equalized: f9_scale=√3≈1.7321, id_scale≈0.01913 so that all models share
SNR_var = 2/sigma² (matching HW at hw_scale=1.0, Var[HW(byte)]=2.0).

ICS level 90 is used uniformly across all sigmas. This is valid because SNR-
matching eliminates the asymmetry that forced F9/ID to lower ICS levels at high
sigmas in paperscale-v3.

Comparable to paperscale-v4 (same scale params, same SASCA setup, corrected
leakage scales).
"""
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SIGMAS = [
    ("0p1", 0.1, 1), ("0p5", 0.5, 2), ("1p0", 1.0, 3),
    ("1p5", 1.5, 4), ("2p0", 2.0, 5), ("2p5", 2.5, 6),
    ("3p0", 3.0, 7), ("3p5", 3.5, 8), ("4p0", 4.0, 9),
]

ICS_LEVEL = 90  # uniform — valid because SNR is now matched to HW

MODES = {
    "f9": {
        "desc": "pure F9 (SNR-equalized, f9_scale=1.7321=√3, bcs=1.0)",
        "snr": "2",
        "sim_mode": "f9",
        "hd_add_scale": "0.0",
        "extra": "SIM_F9_SEED=2839\nSIM_F9_C8_RANGE=0.5\nSIM_F9_SCALE=1.7321\n",
    },
    "id": {
        "desc": "identity mode (SNR-equalized, id_scale=0.01913=√(2/5461.25))",
        "snr": "2",
        "sim_mode": "id",
        "hd_add_scale": "0.0",
        "extra": "SIM_ID_SCALE=0.01913\n",
    },
}

TEMPLATE = """\
# KeccakSim_v2 — {mode_desc}, paperscale-v5 noise sweep: sigma={sigma_f}.
# SNR_var={snr}/sigma^2~{snr_val:.4g}. Scale chosen to match HW SNR (Var_signal=2.0).
# Paperscale-v5: 10 ref, 100 det, 400 training, 40 val sets, 1000 SASCA traces (iter=200).
# Comparable to paperscale-v4 (HW/HD). Sweep step {step}/9.
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
SHA3_TRAINING_ICS_LEVEL={ics}

SHA3_VALIDATION_INPUTS=10
SHA3_VALIDATION_SET_COUNT=40
SHA3_VALIDATION_TRACE_OFFSET=0
SHA3_VALIDATION_PPC=1
SHA3_VALIDATION_OUTPUT_SIZE=55296
SHA3_VALIDATION_CORR_BOUND=0.0
SHA3_VALIDATION_SETS_PER_PART=10
SHA3_VALIDATION_TEMPLATE_TAG={ics}
SHA3_VALIDATION_ICS_TAG={ics}

SHA3_SASCA_TRACE_COUNT=1000
SHA3_SASCA_TEMPLATE_TAG={ics}
SHA3_SASCA_ICS_TAG={ics}
SHA3_SASCA_PPC=1
SHA3_SASCA_ITERATION_COUNT=200
SHA3_SASCA_RATE_BP_ITERATION_COUNT=200
SHA3_SASCA_RATE_POINT_COUNT=201
SHA3_SASCA_RATE_STEP_BITS=8
SHA3_SASCA_ALLOWED_WRONG_BITS=0
SHA3_SASCA_OUTPUT_BITS=512

TRACES_DIR=/storage/ge96pug/traces_paperscale_v5_{mode}_sigma{sigma_s}

SIM_ALGORITHM=sha3-512
SIM_TRACE_FORMAT=bin
SIM_TRACE_DTYPE=float64
SIM_BULK_DATA_FORMAT=hex
SIM_GRANULARITY=byte
SIM_NOISE_SIGMA={sigma_f}
SIM_MODE={sim_mode}
SIM_HD_SCALE={hd_add_scale}
{extra_sim}\
SIM_SEED_RE=128
SIM_SEED_DN=256
SIM_SEED_TR=512
SIM_SEED_TS=1024
"""

count = 0
for sigma_s, sigma_f, step in SIGMAS:
    sigma_dir = os.path.join(SCRIPT_DIR, f"sigma{sigma_s}")
    os.makedirs(sigma_dir, exist_ok=True)
    for mode, m in MODES.items():
        snr_val = float(m["snr"]) / sigma_f ** 2
        content = TEMPLATE.format(
            mode_desc=m["desc"],
            sigma_f=sigma_f,
            snr=m["snr"],
            snr_val=snr_val,
            step=step,
            ics=ICS_LEVEL,
            mode=mode,
            sigma_s=sigma_s,
            sim_mode=m["sim_mode"],
            hd_add_scale=m["hd_add_scale"],
            extra_sim=m["extra"],
        )
        fname = os.path.join(sigma_dir, f".env_paperscale_v5_{mode}_sigma{sigma_s}")
        with open(fname, "w") as f:
            f.write(content)
        count += 1
        print(f"  wrote {fname}")

print(f"\nGenerated {count} env files.")
