# Fast Calibration Matrix (M0-M3)

This matrix isolates the dominant cause of poor simulated-data recovery with reduced runtime but realistic geometry.

## Profiles

- M0 baseline fast: `.env_cal_m0_fast`
- M1 ICS strictness test: `.env_cal_m1_fast_ics_strict`
- M2 correlation strictness test: `.env_cal_m2_fast_corr_strict`
- M3 simulator reference knobs test: `.env_cal_m3_fast_sim_ref`

## What changes across runs

- M0 -> M1: only ICS policy changes.
  - training ICS level/tag and validation/SASCA ICS tags from 0 to 10
  - removes 0.00 from detection thresholds
- M0 -> M2: only correlation gates change.
  - detection/training/validation corr bounds from 0.8 to 0.98
- M0 -> M3: only simulator noise/jitter/hw ratio changes.
  - uses reference-like simulator values

## Runtime minimization strategy

- Run M0 with simulation once.
- Run M1 and M2 with `--skip-sim` to reuse M0 traces.
- Run M3 with simulation because simulator parameters changed.

This avoids 2 extra simulation passes.

## Local execution (from `project_SHA3-32bit/pipeline_runner`)

Set trace root once:

```sh
export TRACES_DIR=/home/muri/Documents/Uni/IDP/Projects_SHA3/project_SHA3-32bit/pipeline_runner/_cal_traces
mkdir -p "$TRACES_DIR"
```

Run M0 (simulate + full chain):

```sh
./run_full_pipeline.sh --env-file ./.env_cal_m0_fast --traces-dir "$TRACES_DIR/m0"
```

Run M1 (reuse traces):

```sh
./run_full_pipeline.sh --env-file ./.env_cal_m1_fast_ics_strict --traces-dir "$TRACES_DIR/m0" --skip-sim
```

Run M2 (reuse traces):

```sh
./run_full_pipeline.sh --env-file ./.env_cal_m2_fast_corr_strict --traces-dir "$TRACES_DIR/m0" --skip-sim
```

Run M3 (new simulation):

```sh
./run_full_pipeline.sh --env-file ./.env_cal_m3_fast_sim_ref --traces-dir "$TRACES_DIR/m3"
```

## Remote execution template

Do this only when ready to move runs to the remote host.

```sh
ssh IDP
cd /storage/ge96pug/Projects_SHA3/project_SHA3-32bit/pipeline_runner
export TRACES_DIR=/storage/ge96pug/traces/cal_matrix_fast
mkdir -p "$TRACES_DIR"

./run_full_pipeline.sh --env-file ./envs/.env_cal_m0_fast --traces-dir "$TRACES_DIR/m0"
./run_full_pipeline.sh --env-file ./envs/.env_cal_m1_fast_ics_strict --traces-dir "$TRACES_DIR/m0" --skip-sim
./run_full_pipeline.sh --env-file ./envs/.env_cal_m2_fast_corr_strict --traces-dir "$TRACES_DIR/m0" --skip-sim
./run_full_pipeline.sh --env-file ./envs/.env_cal_m3_fast_sim_ref --traces-dir "$TRACES_DIR/m3"
```

## Compare outcomes

For each run, capture:

- ICS validation pass/fail and missing/empty counts
- template validation quality report presence
- final scan summaries from:
  - iteration scan get_results
  - rate scan get_results

Interpretation:

- M1 fails or degrades strongly: ICS strictness is the bottleneck.
- M2 improves over M0: loose corr gates were admitting harmful traces.
- M3 improves over M0: simulator knobs are a major contributor.
- All runs weak: likely deeper feature-model mismatch.
