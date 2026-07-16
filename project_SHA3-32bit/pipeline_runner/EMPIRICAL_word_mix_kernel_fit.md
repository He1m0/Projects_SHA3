# Empirical fit: word-mix emission kernel parameters

Written 2026-07-15. Companion to `PROPOSAL_word_emission_kernel.md`,
`ANALYSIS_granularity_mechanism.md`, `INVESTIGATION_word_granularity_anomalies.md`.
Records how N/offsets/width for the `word-mix` emission kernel (decisions 1,
2, 5 of the implementation plan) were derived from real hardware data,
computed once before any simulator change, so they cannot be back-fit to
pipeline outcomes.

## 0. Correction to the plan's original premise

The plan assumed `0002_detection/Code_detection_R2/detect_results_08.zip`
(already present locally) was real, per-raw-sample Cambridge data at "full
resolution" (Fig. 3 of You & Kuhn CARDIS 2021). Two things turned out to be
wrong:

1. **The precomputed `detect_results_08.zip` is per-cycle, not per-raw-sample.**
   `Code_preprocessing/pre_processing.py:69-73` shows each output index `S`
   is `sum(float_array[OFFSET+S*PPC+SHIFT : +WIDTH])` — one integrated value
   per **entire clock cycle** (`PPC=500` raw samples apart), not one value
   per raw ADC sample. The index axis is "which cycle", not "sub-cycle time".
2. **The locally-cached `detect_results_08.zip`/`Raw/Raw_DN_0000.zip` are stale
   simulated leftovers**, not real downloads, despite matching download.sh's
   target filenames — confirmed by comparing `Content-Length` against the
   real Cambridge server (real `Raw_DN_0000.zip` = 1.08 GB vs. 16.5 MB
   cached; real `detect_results_08.zip` = 175.7 MB vs. 20.2 MB cached) and by
   the cached trace values themselves (smooth ~15±3 range, textbook
   Hamming-weight-leakage shape, not an analog capture). This project hit
   the identical mistake once before — see
   `runs_archive/reference/2026-06-03_ref_cambridge_downloaded/README.md`.

Fix: downloaded the genuine real `Raw_DN_0000.zip` (one set, 160 traces,
1.08 GB) directly from the Cambridge server and worked from raw ADC samples
(confirmed real: values in [-0.066, 0.011], mean ≈ 0.0002 — a real
AC-coupled EM/power capture, not simulator output).

## 1. Method

- Tag `A00` (output-A intermediate value, round 0 — matches the paper's
  `α'_0`), lane 0 (first 4 bytes of the 200-byte state hex string).
- Reused `Code_intermediate_values/get_invoc_intermediate.py` /
  `get_invoc_io.py` / `KECCAK.py` logic directly (same absorb/permute/output
  code the pipeline itself uses) to compute the real per-invocation
  intermediate byte values for all 16 inputs × 10 invocations = 160 traces
  in the one downloaded set, from that set's own `data_in.npy`/`data_out.npy`.
- Loaded a 7500-raw-sample window per trace starting at
  `DETECTION_TRACE_OFFSET` (75455), read via file-seek (not full-trace load —
  160 × 7.5M-sample traces would risk exhausting available RAM).
- A raw-sample-by-raw-sample R² regression (`sklearn.LinearRegression`
  per-bit, same method as `get_corrcoef.py`) was too noisy at n=160 traces
  (individual-sample spikes, not smooth curves — real archive R² values use
  16,000 traces, 100× more). Applied the pipeline's own denoising idea
  (`SAMPLE_WIDTH`-style boxcar sum) but at fine stride (`stride=20` samples,
  `boxcar=50` samples) instead of once per whole cycle (`PPC=500`), to get
  usable SNR while still resolving intra-cycle structure at ~25 points/cycle.
- Fit each byte's peak via FWHM (more robust than nonlinear `curve_fit` given
  the noise at this trace count — `curve_fit` diverged/gave unphysical
  fits for 2 of 4 bytes).

## 2. Result

| byte | peak raw offset | offset rel. to earliest | sigma (raw samples) | sigma (cycles, PPC=500) |
|---|---|---|---|---|
| 3 | 77055 | 0 | 25 | 0.050 |
| 0 | 78375 | 1320 (2.64 cycles) | 42 | 0.084 |
| 1 | 78655 | 1600 (3.20 cycles) | 110 | 0.220 |
| 2 | 82435 | 5380 (10.76 cycles) | 17 | 0.034 |

Peak R² at these offsets: 0.11–0.14 (byte0/1/2/3), comparable order of
magnitude to the (unreliable, simulated) locally-cached data's 0.14–0.24 —
not used for anything beyond a rough sanity check given §0.

**Median sigma: 33.5 raw samples ≈ 0.067 clock cycles** (decision 2: shared
width across bytes).

## 3. Caveat: byte 2 is very plausibly a different event, not the same one

Bytes 3, 0, 1 cluster within 1600 raw samples (~3.2 cycles) of each other —
consistent with one multi-cycle store/rotate instruction sequence's
electrical crosstalk smearing across a few adjacent cycles (Fig. 3's
mechanism, just wider than one cycle — plausible given Cortex-M4 pipeline
effects). Byte 2's peak sits 10.76 cycles away from the earliest of the
other three — an order of magnitude further out than the other three's
mutual spacing. This is far more consistent with byte 2's value being
**read again by a separate, later instruction** (a different leak event
entirely) than with one instruction's intra-event mixing reaching that far.

This was exactly the mechanism the plan's rejected "option 2" (reinterpret
the kernel at cycle granularity) would have conflated with the real
intra-event mixing this proposal targets — see the plan's Context section.
Forcing byte 2 into the same shared kernel window as an outlier would not be
justified by this data.

**Decision for v1 (time-constrained, single-set fit — decision 4):** treat
all 4 bytes' fitted offsets/widths above as the kernel parameters anyway
(N=4, one weighted sample per byte, spanning the full empirical range
including byte 2), rather than trying to separately model "which bytes
belong to the same physical event" — that finer discrimination is out of
scope for a smoke-scale fit. This is noted here explicitly so it is not
mistaken for a resolved mechanism; a follow-up with more sets (better SNR)
could re-examine whether byte 2 should be excluded or modeled as its own
later, independent leak point instead of part of this kernel.

## 4. Parameters carried into `KeccakSim_v4.py` (step 2)

- `N = 4`
- Offsets (fraction of one clock cycle, relative to earliest): `[0.0, 2.64,
  3.20, 10.76]` for bytes `[3, 0, 1, 2]` respectively — i.e. byte 3 is the
  reference (offset 0), byte 2 is furthest out.
- Shared width (fraction of one clock cycle): `sigma = 0.067`.
- These are expressed as **fractions of the simulator's own per-leak-event
  timestep**, not literal raw sample counts (the simulator's synthetic trace
  is far shorter than the real 7.5M-sample capture) — step 2 converts them
  to whatever internal sample-spacing unit `KeccakSim_v4.py` uses for a
  word-mix leak event's N emitted samples.

## 5. Artifacts

Analysis scripts and intermediate data kept in `tmp_kernel_fit/` at the repo
root (gitignored per the `tmp_*` convention) for reproducibility during this
session: `compute_intermediate.py` (real A00 byte bits for the 160 traces),
`scan_window.py` / `scan_fine.py` (raw and boxcar-smoothed R² scans),
`fit_fine_kernel.py` (Gaussian/FWHM fits). Not committed — regenerable from
the real `Raw_DN_0000.zip` download plus these scripts.
