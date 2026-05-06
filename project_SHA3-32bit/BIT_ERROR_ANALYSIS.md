# Per-Bit Error Analysis of 0005 SASCA Rate_Scan Outputs

This document explains how to diagnose *why* a pipeline run failed to achieve
100 % success rate in the 0005 SASCA stage.  It covers three layers of
increasing resolution, and gives step-by-step instructions for each.

---

## Quick orientation: what "success" means in Rate_Scan

`Rate_scan.py` sweeps `RATE_POINT_COUNT` steps.  At each step it blanks an
additional `RATE_STEP_BITS` template priors (replacing them with 0.5) and runs
BP.  It then compares the BP-decoded 1600-bit Keccak state against the ground
truth.  A trace "succeeds" at a given rate point if the number of wrong bits is
≤ `ALLOWED_WRONG_BITS` (default 0 = exact recovery).

Two anchor points matter most:

| Anchor | rate_point | template priors blanked |
|---|---|---|
| **Baseline** | 0 | none — full template info fed to BP |
| **Final** | RATE_POINT_COUNT−1 | all — BP works from constraints alone |

If baseline already has many wrong bits, the templates themselves are the
bottleneck.  If baseline is near 0 but final is high, BP cannot propagate
information far enough without prior support.

---

## Layer 1 — Rate-scan staircase (`rate_scan_*R_B.npy`)

**What it is:** A 1-D integer array of length `RATE_POINT_COUNT + 1`.
Element `k` is the number of traces (out of `n`) that succeeded at rate
point `k`.

**Where to find it:** In every archived run at
`0005_SASCA/Rate_Scan/rate_scan_{2R,3R,4R}_B.npy`.

**How to read it manually:**

```python
import numpy as np

B = np.load("runs_archive/<label>/0005_SASCA/Rate_Scan/rate_scan_2R_B.npy")
# e.g. hw_noise: [50 50 50 50 48 45 44 42 36  5  1  0  0  0  0  0  0  0  0  0  0]
# e.g. f9_noise: [50 50 50 50 50 50 50 50 50 50 50 50 50 50 50 50 50 50 50 50 50]

n = B[0]          # total traces (all succeed at rate_point=0 when baseline is good)
sr_baseline = B[0] / n      # should be 1.0 if templates are not catastrophically weak
sr_final    = B[-1] / n     # SR at the hardest point
print(f"baseline SR={sr_baseline:.2f}  final SR={sr_final:.2f}")

# Find the rate point where SR first drops below 50 %
drop_pt = next((i for i, v in enumerate(B) if v / n < 0.5), len(B))
print(f"SR drops below 50% at rate_point {drop_pt} "
      f"(= {drop_pt * <RATE_STEP_BITS>} bits blanked)")
```

**What to look for:**

- `B[0] < n`: even at rate_point=0 (full priors) some traces already have
  wrong bits.  This means **the templates themselves are weak** — the fault
  is in 0003 training or the ICS level, not in BP.
- The array stays flat at `n` across all rate points → 100 % SR regardless
  of how many priors are withheld: BP is extremely robust for this run.
- The array drops sharply around the operating point
  (`SASCA_KNOWN_RATE_BITS / RATE_STEP_BITS`): BP works well up to the
  intended attack scenario but fails under heavier withholding.

**From `compare_runs.py`** these staircase values are what get plotted as the
rate-scan curve.  The columns `SR@0`, `SR@mid`, `SR@end` and `last≥50%=ptK/20`
in the comparison `.txt` files correspond to `B[0]/n`, `B[mid]/n`, `B[-1]/n`,
and `drop_pt`.

---

## Layer 2 — Per-trace summaries in the run log

**What it is:** One line per trace emitted by `Rate_scan.py` to stdout,
capturing the key statistics at the best and final rate points.

**Where to find it:** In archived logs at `log/<label>.log.gz`.

```sh
# Extract all per-trace summary lines from an archived log:
zcat runs_archive/2026-05-05_smoke_v2_hw_noise/log/smoke_v2_hw_noise.log.gz \
  | grep "Trace.*summary"
```

Example output line:

```
Trace 0007 summary: baseline_wrong_bits=523, best_wrong_bits=7@pt38,
  final_wrong_bits=8, best_ber=0.0044, final_ber=0.0050,
  delta_best_vs_baseline=-516, delta_final_vs_baseline=-515,
  final_unknown_wrong=2/576, final_known_wrong=6/1024, success_count=0/41
```

**Field-by-field explanation:**

| Field | Meaning |
|---|---|
| `baseline_wrong_bits` | Wrong bits at rate_point=0 (full priors).  For a strong run this is near 0; for `hw_noise` it is ~530/1600 = 33 % — templates alone are poor. |
| `best_wrong_bits@ptN` | Fewest wrong bits BP ever achieved; `N` is the rate_point index.  If `N > 0`, BP actively improved things beyond the template baseline. |
| `final_wrong_bits` | Wrong bits at the last rate_point (maximum blanking). |
| `best_ber` / `final_ber` | Bit error rate = wrong_bits / 1600. |
| `delta_best_vs_baseline` | `best − baseline`: negative means BP improved on raw templates, positive means BP made things worse (rare, signals divergence). |
| `delta_final_vs_baseline` | Same but for the final rate_point. |
| `final_unknown_wrong=168/576` | Of the 576 bits whose priors were withheld at the final point, 168 remain wrong.  This is the "hard core" BP could not recover from constraints. |
| `final_known_wrong=296/1024` | Of the 1024 bits that still had live priors at the final point, 296 are wrong — errors propagated *into* the known region. |
| `success_count=0/41` | How many of the 41 rate points scored ≤ `ALLOWED_WRONG_BITS` (0 = exact). |

**Quick aggregate from the log:**

```sh
# Average baseline_wrong_bits and final_wrong_bits across traces
zcat runs_archive/<label>/log/*.log.gz | grep "Trace.*summary" | \
  awk '{
    for(i=1;i<=NF;i++){
      if($i~/^baseline_wrong_bits=/) {split($i,a,"="); base+=a[2]; n++}
      if($i~/^final_wrong_bits=/)    {split($i,a,"="); fin+=a[2]}
    }
  } END {printf "n=%d  avg_baseline_wrong=%.1f  avg_final_wrong=%.1f\n", n, base/n, fin/n}'
```

---

## Layer 3 — Per-bit heatmap via `analyze_per_bit_errors.py`

This tool produces a PNG heatmap of which of the 1600 Keccak bits are
systematically wrong, broken down by lane (0–24) and bit-within-lane (0–63).
It also reports polarity imbalance (does BP systematically prefer 0 or 1 for
certain bits?) and a histogram of per-trace wrong-bit counts.

### Prerequisites

The tool needs two sets of files inside the archive:

1. **Predictions** — the 1600-bit BP output at the baseline and final rate
   points, one file per trace:
   ```
   0005_SASCA/Rate_Scan/{depth}_Predictions/prediction_baseline_XXXX.npy
   0005_SASCA/Rate_Scan/{depth}_Predictions/prediction_final_XXXX.npy
   ```

2. **Ground truth** — the actual Keccak state bits for each trace:
   ```
   0005_SASCA/answers_A00/ans_bit_XXXX.npy
   ```

As of the updated `archive_run.sh`, both are captured automatically.  If
you are working with an older archive that is missing them, see
**"Re-generating Predictions for an old run"** below.

### Step-by-step: running the analysis

```sh
cd project_SHA3-32bit/pipeline_runner

# Basic usage — analysis at 2R depth, output to /tmp/per_bit_analysis/
python analyze_per_bit_errors.py \
  runs_archive/2026-05-05_smoke_v2_hw_noise \
  --depth 2R

# Multiple runs side by side (produces one PNG per run):
python analyze_per_bit_errors.py \
  runs_archive/2026-05-05_smoke_v2_hw_noise \
  runs_archive/2026-05-05_smoke_v2_hd_noise \
  --depth 2R \
  --out-dir /tmp/bit_errors_hw_vs_hd

# Explicit answers path (if answers_A00 is not in the archive but is in the
# live pipeline directory — e.g. after a fresh run before archiving):
python analyze_per_bit_errors.py \
  runs_archive/<label> \
  --depth 2R \
  --answers ../0005_SASCA/Rate_Scan_2R/answer_bit/answers_A00
```

All outputs go to `--out-dir` (default `/tmp/per_bit_analysis/`):

| File | Contents |
|---|---|
| `per_bit_<label>_<depth>.png` | 6-panel figure (see below) |
| `per_bit_summary_<depth>.md` | Text summary with BER, flip counts, top-10 worst bits |

### Understanding the output figure

The PNG has 3 rows × 2 columns:

**Row 0 — Per-bit error rate heatmap (lane × bit-in-lane)**

Each cell is the fraction of traces for which that specific bit position was
wrong.  X-axis = bit 0–63 within the lane; Y-axis = lane 0–24 (the 5×5
Keccak state, row-major).

- Pure black = that bit is never wrong.
- Bright / white = that bit is almost always wrong.
- A horizontal stripe on lane `k` → all bits in that lane are systematically
  wrong — likely a missing or badly trained round-`k` leakage source.
- A vertical stripe at bit position `b` across multiple lanes → bit position
  `b` within the lane word is systematically mispredicted — may indicate a
  structural property of the leakage model.

The left panel is the **baseline** (rate_point=0, full priors); the right
panel is the **final** (all priors blanked, BP from constraints only).
Compare them: bits that are wrong at baseline are template-quality failures;
bits that go wrong only in the final panel are BP-propagation failures.

**Row 1 — Per-trace wrong-bit count histogram**

How many bits were wrong per trace.  A good run has a spike near 0.  A run
with weak templates has a broad distribution centred around 400–600 (roughly
random for a 33 % BER).  Trace 0007 in the `hw_noise` run shows
`best_wrong_bits=7` but still counts as failure because `ALLOWED_WRONG_BITS=0`.

**Row 2 left — Polarity imbalance bar chart**

Four bars: baseline/final × (1→0 flip rate, 0→1 flip rate), each normalised
by the number of true 1-bits or true 0-bits respectively.

- Balanced bars: BP has no directional bias.
- `1→0` much taller than `0→1`: BP systematically predicts 0 for bits that
  are truly 1 (under-estimation of HW? missing positive-leakage component).
- `0→1` much taller: BP over-estimates HW / over-confident positive prior.

**Row 2 right — Distribution of per-bit error rates**

Histogram over the 1600 bit positions of their individual error rate.
Ideally a spike at 0 (all bits nearly always correct).  A bimodal distribution
(spike at 0 and spike at 0.5 or 1.0) means some bits are structurally
unrecoverable and others are fine — look at the heatmap for their lane/bit
positions.

---

## Re-generating Predictions for an old run

If an archive is missing `{depth}_Predictions/`, you need to re-run just the
0005 Rate_Scan stage with the original env.

```sh
cd project_SHA3-32bit

# 1. Restore the env from the archive (the run you want to re-analyse):
cp pipeline_runner/runs_archive/2026-05-05_smoke_v2_hw_noise/pipeline_runner/.env_smoke_v2_hw_noise .env

# 2. Make sure templates are still on disk (0003_training/ must be present
#    and match the run).  If you still have them from the original run, skip
#    steps 3–4.  Otherwise re-run training:
#      cd pipeline_runner && ./run_overnight_chain.sh --with-training

# 3. Re-run only the Rate_Scan stages (fast — no simulation needed):
cd 0005_SASCA/Rate_Scan_2R && ./clean.sh && ./script_all.sh && cd ../..
cd 0005_SASCA/Rate_Scan_3R && ./clean.sh && ./script_all.sh && cd ../..
cd 0005_SASCA/Rate_Scan_4R && ./clean.sh && ./script_all.sh && cd ../..

# 4. Check that Predictions were written:
ls 0005_SASCA/Rate_Scan_2R/Predictions/ | head -5

# 5. Run the analysis (pass live answers since pack.sh has not run yet):
cd pipeline_runner
python analyze_per_bit_errors.py \
  runs_archive/2026-05-05_smoke_v2_hw_noise \
  --depth 2R \
  --answers ../0005_SASCA/Rate_Scan_2R/answer_bit/answers_A00
```

> **Note:** `pack.sh` removes `answer_bit/` and `Success/` but leaves
> `Predictions/` intact.  If you want to archive the predictions together with
> the existing archive, run:
> ```sh
> sh pipeline_runner/archive_run.sh --name smoke_v2_hw_noise_with_preds --force
> ```
> (This will overwrite the archive — use a different `--name` to keep both.)

---

## Which runs are worth analysing

Not every run is informative for per-bit analysis.  Use these heuristics:

| Condition | What to do |
|---|---|
| `rate_scan_2R_B.npy` is all-equal (100 % at every rate point) | No failure to diagnose at 2R; check 3R/4R or 0004 template quality instead. |
| `B[0] < n` (failures even at baseline) | Start with Layer 2 log grep to check `baseline_wrong_bits`; templates are the bottleneck, not BP. |
| `B[0] = n` but curve drops off quickly | BP propagation is limited; per-bit heatmap helps identify which lanes BP cannot propagate through. |
| Very noisy run (e.g. HW-only or HD-only without F9) | `baseline_wrong_bits` ≈ 500 / 1600 (≈ random); heatmap will be uniformly grey; not informative — compare against a stronger-leakage run. |

As of the May 2026 runs, the most informative failing runs are:

- `2026-05-05_smoke_v2_hw_noise` — HW-only leakage, essentially no BP convergence.
  `baseline_wrong_bits` ≈ 530 even at rate_point=0 → template failure.
- `2026-05-05_smoke_v2_hd_noise` — HD-only, same situation.
- `2026-05-06_smoke_v2_hd_f9_noise` — mixed HD+F9; 2R succeeds 100 %, 3R/4R
  may show partial failure (use `--depth 3R`).

The pure-F9, HW+F9, and HD+F9 runs at 2R all hit 100 % and are not useful for
failure diagnosis.
