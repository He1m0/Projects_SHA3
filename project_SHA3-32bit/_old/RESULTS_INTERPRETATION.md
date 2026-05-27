# Interpreting 0004 and 0005 Results

## 0004 — Template Validation

**What it measures:** How well individual byte templates discriminate the correct byte from 255 alternatives, across `SHA3_VALIDATION_INPUTS` inputs.

**Key outputs** (in `quality_report/`):

| File | What's in it |
|---|---|
| `report.txt` | Human-readable summary |
| `summary_family_round.csv` | Per `family_round` (e.g. `A00`, `B01`) average SR, GE, combined score |
| `summary_tables.csv` | Per `(family_round, group)` breakdown |
| `weakest_bytes_top.csv` | Worst-performing individual bytes |

**Metrics:**

- **SR (Success Rate)** — fraction of test traces where the correct byte ranked 1st. Range `[0, 1]`. Random baseline = 1/256 ≈ 0.004.
- **GE (Guessing Entropy)** — expected rank of the correct byte. Range `[1, 256]`. Random baseline = 128.
- **combined_score** = `0.7 × SR + 0.3 × (256 − GE)/255`, range `[0, 1]`.
- **quality_label** thresholds:
  - `excellent`: SR ≥ 0.20 and GE ≤ 20
  - `good`: SR ≥ 0.10 and GE ≤ 40
  - `fair`: SR ≥ 0.03 and GE ≤ 80
  - `weak`: below all of the above (may still be useful for BP)

**What to look for:** Most bytes should land at "fair" or above for SASCA to converge. A few `weak` bytes are tolerable — BP can recover them from constraints if enough neighbors are strong. Systematic weakness across a whole `family_round` (e.g., all `B01`) is a sign of a training/ICS mismatch.

---

## 0005 — SASCA (Belief Propagation)

Two separate scans exist at each round depth (`2R`, `3R`, `4R`):

### Iteration_Scan

**What it measures:** How many BP iterations are needed for convergence, given full template observations (all bits unmasked).

**Success definition:** A trace "succeeds" at iteration `i` if total wrong bits in the 1600-bit state ≤ `SASCA_ALLOWED_WRONG_BITS` (default 0 = exact recovery).

**Output:** `iteration_scan_XR_B.npy` — shape `(n_iters,)`, each value = number of traces that succeeded at that iteration count.

**What to look for:**
- Does success rate plateau early (good — fast convergence) or keep climbing (more iterations help)?
- Does it reach a ceiling below 100 % at any iteration count? That ceiling is the achievable SR given current template quality.
- If it doesn't improve at all: templates are too weak to seed BP convergence.

### Rate_Scan

**What it measures:** How many of the 1600 input bits' template observations can be withheld (replaced with uniform 0.5 prior) before BP fails, at a fixed iteration count (`SASCA_RATE_BP_ITERATION_COUNT`).

**X-axis:** `unknown_bits` = `byte × RATE_STEP_BITS`, sweeping from 0 to `RATE_POINT_COUNT × RATE_STEP_BITS`.

**Three anchor points:**

| Point | `unknown_bits` | Meaning |
|---|---|---|
| **Baseline** (rate_point 0) | 0 | All template observations active. BP just propagates existing knowledge. |
| **Operating point** | `SASCA_KNOWN_RATE_BITS = 1600 − 2×SASCA_OUTPUT_BITS` | The bits the attack is actually trying to recover (default: 576 unknown bits for 512-bit output). |
| **Final** (last point) | max | BP must infer bits from constraints alone — theoretical stress test. |

**Output files:**

- `rate_scan_XR_B.npy` — aggregated success counts across traces at each rate point (length = `RATE_POINT_COUNT`)
- `Success/success_XXXX.npy` — per-trace bool array of length `RATE_POINT_COUNT`
- `Predictions/prediction_baseline_XXXX.npy` / `prediction_final_XXXX.npy` — 1600-bit predicted state at those two anchors (used by `analyze_per_bit_errors.py`)

**What to look for:**
- **Baseline SR >> 0004 byte-level SR?** Expected — BP propagates information across the state, so bit-level accuracy is higher than byte-level first-rank SR.
- **Baseline SR ≈ 0?** Template tables are not reaching BP correctly (ICS/template tag mismatch, wrong round depth, or all-zeros tables).
- **Curve drops sharply at operating point vs baseline?** BP can use constraints but struggles without enough priors.
- **Flat curve from 0 to operating point, then drops?** Known bits are redundant; loss comes purely from the unknown region.

---

## Connecting 0004 → 0005

The data flow is:

```
0004 SR/GE (byte level)
    ↓ template LDA files → bit tables → SASCA priors
0005 Rate_Scan baseline (bit-level BER with full priors)
    ↓ rate scan: withhold bits
0005 Rate_Scan @ operating point (actual attack success rate)
```

**Rules of thumb:**

1. If 0004 shows `fair`/`good` templates but 0005 baseline success is near 0 → check `SASCA_TEMPLATE_TAG` / `SASCA_ICS_TAG` match what 0004 produced; also check `SHA3_SASCA_OUTPUT_BITS` matches the expected unknown region.
2. If 0005 baseline is high but operating-point SR is low → BP needs more iterations or more rounds of leakage (`3R`/`4R` will outperform `2R`).
3. If `3R` >> `2R` but `4R` ≈ `3R` → diminishing returns from extra rounds; noise limits further gains.
4. `analyze_per_bit_errors.py ARCHIVE --depth 2R` breaks down which of the 1600 bits are systematically wrong (useful for diagnosing structural leakage gaps).
5. `compare_runs.py` overlays 0004 SR/GE and 0005 rate curves across multiple archived runs in one plot — use this to compare simulator variants or env configs.

---

## Quick Commands

```sh
# Analyze 0004 quality from an archive
python 0004_validation/template_validation_bytes/analyze_result_tables_zip.py \
    pipeline_runner/runs_archive/<label>/0004_validation/quality_report/../Result_Tables.zip

# 0005 rate scan summary (run from inside Rate_Scan_XR/)
python get_results.py 0 <N>

# Cross-run comparison plot
python pipeline_runner/compare_runs.py \
    pipeline_runner/runs_archive/<run1> pipeline_runner/runs_archive/<run2> \
    --rate-depth 2R

# Per-bit error breakdown
python pipeline_runner/analyze_per_bit_errors.py \
    pipeline_runner/runs_archive/<label> --depth 2R
```
