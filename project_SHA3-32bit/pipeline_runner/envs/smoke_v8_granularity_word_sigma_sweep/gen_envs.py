#!/usr/bin/env python3
"""Generate smoke v8 word-granularity sigma sweep env files (36 total: 4 pure
modes x 9 sigmas).

Purpose: KeccakSim_v2/v3's --granularity flag (word vs. byte, default byte)
has never been tested -- every active sweep hardcodes SIM_GRANULARITY=byte.
Byte mode emits 4 samples per 32-bit leak() call (one per byte); word mode
emits 1 sample per leak() call for the whole word -- a uniform 4x factor
across the entire trace (KeccakSim_v2.py/_v3.py:_leak_signal). This sweep
clones the current canonical byte-mode source for each pure leakage model,
flips SIM_GRANULARITY to word, and divides the six trace-length-derived env
vars by 4 (55296 -> 13824, matching global_config.py's own word-mode default
of 13824) -- everything else (ICS thresholds, SASCA params, seeds, ICS level)
is carried over unchanged.

Sources (pure modes only -- no mixed HW+HD; see RUN_LOG_snr_equalized.md /
RUN_LOG_hd_promotion.md for why smoke_v4's F9/ID are NOT used -- they are
unnormalized, not SNR-equalized):
  hw -> smoke_v5_sigma_sweep      (pure HW, iter=200 canonical rerun, ICS 90)
  hd -> smoke_v7_hd_pure_sigma_sweep (KeccakSim_v3 mode=hd, ICS 40)
  f9 -> smoke_v6_sigma_sweep      (SNR-equalized, f9_scale=1.7321, ICS 90)
  id -> smoke_v6_sigma_sweep      (SNR-equalized, id_scale=0.01913, ICS 90)
"""
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENVS_DIR = os.path.dirname(SCRIPT_DIR)

SIGMAS = ["0p1", "0p5", "1p0", "1p5", "2p0", "2p5", "3p0", "3p5", "4p0"]

SOURCES = {
    "hw": os.path.join(ENVS_DIR, "smoke_v5_sigma_sweep", ".env_smoke_v5_hw_sigma{sigma}"),
    "hd": os.path.join(ENVS_DIR, "smoke_v7_hd_pure_sigma_sweep", ".env_smoke_v7_hd_pure_sigma{sigma}"),
    "f9": os.path.join(ENVS_DIR, "smoke_v6_sigma_sweep", ".env_smoke_v6_f9_sigma{sigma}"),
    "id": os.path.join(ENVS_DIR, "smoke_v6_sigma_sweep", ".env_smoke_v6_id_sigma{sigma}"),
}

HEADER = """\
# smoke_v8_granularity_word -- word-granularity clone of {src_name}.
# SIM_GRANULARITY=word (was byte); trace-length vars divided by 4 (55296 ->
# 13824) to match the simulator's actual word-mode sample count. All other
# params (ICS level, SASCA iterations, seeds) unchanged from the source.
"""

count = 0
for mode, path_tmpl in SOURCES.items():
    for sigma in SIGMAS:
        src_path = path_tmpl.format(sigma=sigma)
        with open(src_path) as f:
            content = f.read()

        content = content.replace("SIM_GRANULARITY=byte", "SIM_GRANULARITY=word")
        content, n = re.subn(r"=55296\b", "=13824", content)
        if n != 6:
            raise ValueError(
                f"{src_path}: expected 6 occurrences of '=55296', found {n}"
            )

        out_content = HEADER.format(src_name=os.path.basename(src_path)) + content
        out_name = f".env_smoke_v8_granularity_word_{mode}_sigma{sigma}"
        out_path = os.path.join(SCRIPT_DIR, out_name)
        with open(out_path, "w") as f:
            f.write(out_content)
        count += 1
        print(f"  wrote {out_name}  (from {os.path.basename(os.path.dirname(src_path))}/{os.path.basename(src_path)})")

print(f"\nGenerated {count} env files.")
