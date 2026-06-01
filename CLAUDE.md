# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

Research code for template side-channel attacks on SHA-3 (Keccak). Two projects:

- `project_SHA3-XMEGA/` — 8-bit XMEGA target (SHA3-512), legacy / mostly static.
- `project_SHA3-32bit/` — 32-bit ARM Cortex-M4 (STM32F303RCT7 on ChipWhisperer-Lite) target. **This is the active project** — almost all work happens here.

`KeccakSim_v2.py` (repo root) is the **active simulator** — a Keccak-f[1600] synthetic HW trace generator with a stochastic F9 leakage model. It is what `pipeline_runner/run_full_pipeline.sh` invokes. The older `_legacy/KeccakSim_BI_TA.py` (original bit-interleaved HW model) is preserved for reference but not used by the pipeline.

`Bit_Tables/` holds precomputed bit-to-byte tables consumed by the SASCA (belief propagation) stages.

## Repository layout conventions

- `_legacy/` (repo root) — superseded code kept for reference (not used by the active pipeline).
- `_old/` (repo root and per-subdir) — historical docs and planning artefacts moved out of the active workspace. Still in git; just out of the way.
- `pipeline_runner/runs_archive/` — local-only (gitignored) snapshots of completed runs, organised by scale (`smoke_v3/`, `midscale_v1/`, `paperscale_v3/`, `smoke_v2/`, `_legacy/`).
- `pipeline_runner/_old/` — executed planning docs (sweep plans, relaunch plans) moved here once completed.

## Python environment

Two interchangeable venvs exist at the repo root (historical). Scripts auto-detect in this order: `.venv/bin/python`, then `venv/bin/python`, then `python3`. Stay consistent with whichever one is active; both have `numpy`, `scipy`, `h5py`, `scikit-learn`, `joblib`.

## Pipeline structure (project_SHA3-32bit)

The workflow is a linear pipeline of numbered phase directories. Each phase has subdirectories (e.g. `Code_preprocessing/`, `Code_intermediate_values/`) where the convention is:

- `script_all.sh` — runs the full stage end-to-end.
- `clean.sh` — wipes generated artifacts for a fresh re-run.
- `download.sh` / `serv_manager.py` — fetch/stage raw data.
- Output is typically a zipped HDF5 archive consumed by the next phase.

Phases:

1. **0001_reference** — generate `ref_trace.npy` for trace-quality gating.
2. **0002_detection** — preprocess → intermediate values → R² detection → ICS (Interesting Clock Samples) extraction. Produces `ics_original_{level:03d}.zip` archives, one per correlation-threshold level.
3. **0003_training** — preprocessing → intermediate values → IoP discovery → LDA template profiling. Produces `templateLDA_OXXX/`.
4. **0004_validation** — evaluate templates (first-order success rate, guessing entropy). Produces `Result_Tables.zip` and `quality_report/`.
5. **0005_SASCA** — factor-graph belief propagation across a Keccak-f[1600] permutation. Contains `Iteration_Scan_{2,3,4}R/` and `Rate_Scan_{2,3,4}R/` subdirs (scans over BP iteration count and data rate, at 2/3/4 rounds of leakage). `bit_table_generation/` builds the per-step bit tables; `plot_scans/` renders the final figures.
6. **0006–0011** — per-algorithm attacks (SHA3-512/384/256/224, SHAKE256/128).

## Configuration

All numeric parameters flow through `project_SHA3-32bit/global_config.py`. Every constant is overridable via an `SHA3_*` environment variable. A `.env` (or `.env_*` profile) at the project root is auto-loaded. `pipeline_runner/run_full_pipeline.sh --env-file <path>` copies the chosen profile to `.env` so every downstream `script_all.sh` picks up the same settings.

When changing pipeline behavior, prefer editing `global_config.py` or an env profile over hard-coding in individual scripts — the shell scripts read values via `python3 -c "import global_config as cfg; print(cfg.X)"`.

Key parameters (with env-var name):
- `SHA3_INPUTS` (16), `SHA3_INVOCATIONS` (10), `SHA3_VALIDATION_INPUTS` (10)
- `SHA3_{DETECTION,TRAINING,VALIDATION}_SET_COUNT`, `_CORR_BOUND`, `_PPC`
- `SHA3_TRAINING_ICS_LEVEL` — picks which `ics_original_XXX.zip` flows into training
- `SHA3_SASCA_*` — BP iterations, rate-scan resolution, output bits, damping

## Running the pipeline

From `project_SHA3-32bit/pipeline_runner/`:

```sh
export TRACES_DIR=/some/scratch/dir       # required if simulating
./run_full_pipeline.sh --env-file ./envs/<profile>.env
```

Useful flags:
- `--skip-sim` — reuse previously simulated traces in `TRACES_DIR` (common when sweeping non-simulator parameters — see `CALIBRATION_MATRIX_FAST.md`).
- `--skip-chain` — only (re)generate + deploy traces.
- `--traces-dir PATH` — override `TRACES_DIR` for this run.
- `--serial-scans` — default is parallel 0005 scans; serialize for low-memory hosts.
- `--keep-local-zips` — retain generated zip copies in `TRACES_DIR` after deployment.

The default `--env-file` if omitted is `../.env_debug` (the project-root debug profile).

Partial chains (skip simulation, assume `Raw/*.zip` already present):
- `sh run_0001_chain.sh` — reference only
- `sh run_0002_chain.sh` — detection only
- `sh run_0003_chain.sh` — training only (includes ICS validation guard — fails fast if the configured ICS level has empty arrays)
- `sh run_0004_chain.sh` — validation only
- `sh run_0005_chain.sh` — SASCA only

Run these from `pipeline_runner/`; they resolve `project_SHA3-32bit/` as `../`. To rerun 0003→0005 in sequence: run them one after another. Note: `run_overnight_chain.sh` no longer exists — it bypassed the ICS check and allowed silent template corruption.

A single stage can be rerun directly: `cd 0003_training/Code_preprocessing && ./clean.sh && ./script_all.sh`.

## Run archiving and comparison

`pipeline_runner/` contains tooling to snapshot and compare runs:

- `archive_run.sh --name LABEL [--env-file PATH] [--log PATH] [--note TEXT]` — captures the env, `0004_validation/quality_report/`, and `0005_SASCA/` partials into `runs_archive/<date>_<label>/`. After archiving, move the directory into the appropriate subdir (`smoke_v3/`, `midscale_v1/`, `paperscale_v3/`).
- `compare_runs.py <archive_dir> [<archive_dir> ...]` — plots success-rate / guessing-entropy across archived runs; supports `--rate-depth 2R|3R|4R` to focus on a specific SASCA round depth. Archive paths must include the subdir, e.g. `runs_archive/smoke_v3/2026-05-26_smoke_v3_f9_sigma1p0`.
- `sigma_sweep_compare.py --archive-root runs_archive/<scale>` — sigma-sweep overview for all 4 modes at once; produces `*_per_mode.png`, `*_cross_mode.png`, `*_rate_scan_grid.png`.
- `analyze_per_bit_errors.py ARCHIVE [ARCHIVE ...] [--depth 2R|3R|4R]` — per-bit error-rate breakdown of `Rate_Scan` BP outputs (baseline vs. final, 1→0/0→1 imbalance, lane×bit heatmap).
- `check_ics_archive.py` — sanity-checks an ICS zip; called automatically by `run_full_pipeline.sh` (after detection) and `run_0003_chain.sh` (before training). Fails if any ICS array is empty.

`runs_archive/` is structured into subdirs by scale; comparison plots go under `runs_archive/_compare_plots/<scale>/`. See `pipeline_runner/EVALUATION_GUIDE.md` for the full evaluation workflow.

## Simulator

`KeccakSim_v2.py` (active simulator) supports `--noise-sigma`, `--gain-jitter-sigma`, `--offset-jitter-sigma`, `--smooth-window`, `--hw-ratio`, `--leakage-profile`, `--common-wave-scope`. The `simulate_group` function in `run_full_pipeline.sh` is the canonical invocation — mirror its flags when running standalone. The older `_legacy/KeccakSim_BI_TA.py` (original HW-only model) is not used by the pipeline.

`KeccakSim_v2.py` key F9 parameters:
- `SIM_F9_SEED` — RNG seed for the per-position coefficient table (default: 2839).
- `SIM_F9_C8_RANGE` — half-width of U(−r,+r) for the **intercept** column only (default: 0.5).
- `SIM_F9_BIT_COEFF_SCALE` — upper bound of U(0,s) for **bit coefficients** (default: 1.0).

**F9 coefficient normalization:** The bit_coeff_scale determines the SNR formula:
- Default `1.0` (unnormalized): E[Var_signal] = 2/3 ≈ 0.667, so **SNR_var = 0.667/σ²** (SNR=1 at σ≈0.816).
  **All sigma-sweep runs (smoke v2, smoke v3, midscale, paperscale) use this default.** The normalization was considered but discarded to avoid extra complexity — do not set `SIM_F9_BIT_COEFF_SCALE=1.2247` for new runs.
- Normalized `sqrt(3/2) ≈ 1.2247`: E[Var_signal] = 1.0, so **SNR_var = 1/σ²** (SNR=1 at σ=1.0 exactly).
  Not used in any active sweep runs. Kept here for reference only.

The pipeline encodes `bcs{value}` in the F9 table filename (e.g. `f9_table_byte_seed2839_bcs1p0.npy`) so tables from different normalizations never collide in TRACES_DIR.

## Conventions

- `tmp_*.py` / `tmp_*.sh` at the project root are ad-hoc diagnostic scripts (kept out of git via `.gitignore`: `tmp_*`). They are not part of the pipeline; don't take their presence as a contract.
- Large `.npy`, `.hdf5`, `.zip`, and `Raw/` data are gitignored. Don't commit regenerated artifacts.
- ICS archive filenames encode the threshold: `ics_original_010.zip` corresponds to `SHA3_DETECTION_ICS_THRESHOLDS` index / `SHA3_TRAINING_ICS_LEVEL=10`.
- Template tags (`VALIDATION_TEMPLATE_TAG`, `SASCA_TEMPLATE_TAG`) are zero-padded 3-digit strings derived from integer env vars — keep that format when producing new archives.
