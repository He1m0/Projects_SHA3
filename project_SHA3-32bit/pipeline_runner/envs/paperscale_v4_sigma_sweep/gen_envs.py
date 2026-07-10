#!/usr/bin/env python3
"""Generate paperscale v4 sigma sweep env files (6 total: 2 modes × 3 sigmas).

paperscale-v4 reruns the Iteration Scan for HW and HD at low sigma (0.1, 0.5, 1.0)
with SHA3_SASCA_ITERATION_COUNT=200 instead of the 40 used in paperscale-v3.

The TRACES_DIR intentionally points at the paperscale-v3 trace directories — the
simulation data and trained templates are reused; only the Iteration Scan stages are
re-executed with the higher iteration cap.
"""
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SIGMAS = [
    ("0p1", 0.1, 1), ("0p5", 0.5, 2), ("1p0", 1.0, 3),
]

ICS_LEVELS = {
    "0p1": 90, "0p5": 90, "1p0": 90,
}

MODES = {
    "hd": {
        "desc": "HW+HD mode (HD_ADD_SCALE=0.5)",
        "snr": "~2.5",
        "sim_mode": "hw",
        "hd_add_scale": "0.5",
        "extra": "",
    },
    "hw": {
        "desc": "HW mode",
        "snr": "2",
        "sim_mode": "hw",
        "hd_add_scale": "0.0",
        "extra": "",
    },
}

TEMPLATE = """\
# KeccakSim_v2 — {mode_desc}, paperscale-v4 noise sweep: sigma={sigma_f}.
# SNR_var={snr}/sigma^2~{snr_val:.4g}.
# Paperscale-v4: rerun of Iteration Scan at 200 iters (was 40 in paperscale-v3).
# Reuses paperscale-v3 traces and templates; only Iteration_Scan_*R stages are rerun.
# Sweep step {step}/3.
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

# Reuse paperscale-v3 traces (same simulation data, only Iteration Scan is rerun).
TRACES_DIR=/storage/ge96pug/traces_paperscale_v3_{mode}_sigma{sigma_s}

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
    ics = ICS_LEVELS[sigma_s]
    for mode, m in MODES.items():
        snr_val = float(m["snr"].lstrip("~")) / sigma_f**2
        content = TEMPLATE.format(
            mode_desc=m["desc"],
            sigma_f=sigma_f,
            snr=m["snr"],
            snr_val=snr_val,
            step=step,
            ics=ics,
            mode=mode,
            sigma_s=sigma_s,
            sim_mode=m["sim_mode"],
            hd_add_scale=m["hd_add_scale"],
            extra_sim=m["extra"],
        )
        fname = os.path.join(sigma_dir, f".env_paperscale_v4_{mode}_sigma{sigma_s}")
        with open(fname, "w") as f:
            f.write(content)
        count += 1
        print(f"  wrote {fname}")

print(f"\nGenerated {count} env files.")
