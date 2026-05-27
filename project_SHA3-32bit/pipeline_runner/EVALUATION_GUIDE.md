# Evaluation Guide

How to work with archived pipeline runs and the comparison/analysis scripts
to evaluate template quality and SASCA performance.

## What we're evaluating

Two outputs per run:

1. **Template quality** (phase 0004) — per-byte template success rate (SR) and guessing
   entropy (GE), summarised by family (A/B/C/D) and round. Lives in
   `0004_validation/quality_report/`.

2. **SASCA attack success** (phase 0005) — belief-propagation success curves over a
   data-rate scan (how many measured traces needed to break the full Keccak state) at
   2R / 3R / 4R rounds of leakage. Lives in `0005_SASCA/Rate_Scan_{2,3,4}R_Success/`.

Both are captured by `archive_run.sh` into `runs_archive/<scale>/<date>_<label>/`.

## Active run sets (focus here)

| Set | Location | Status |
|-----|----------|--------|
| `smoke_v3` | `runs_archive/smoke_v3/` | 36/36 archived (2026-05-26) |
| `midscale_v1` | `runs_archive/midscale_v1/` | 34/36; f9 σ=3.0/4.0 still running |
| `paperscale_v3` | `runs_archive/paperscale_v3/` | in progress on IDP remote |

Parameters across scales:

| | Smoke v3 | Midscale v1 | Paperscale v3 |
|-|----------|-------------|---------------|
| Training sets | 50 | 200 | 500 |
| SASCA traces | 50 | 300 | 300 |
| Detection sets | 10 | 30 | 100 |
| Rate-scan points | 21 | 101 | 101 |

Each set has 36 runs: 4 modes (f9, hw, hd, id) × 9 σ values (0.1, 0.5, 1.0, 1.5, 2.0,
2.5, 3.0, 3.5, 4.0).

## Step 1 — archive a completed run

From the repo root after a run finishes on the IDP remote:

```sh
# sync logs from remote (adjust sandbox label and sigma)
scp IDP:/storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_f9_sigma3p0/project_SHA3-32bit/pipeline_runner/pipeline_midscale_v1_f9_sigma3p0.log /tmp/

# archive into the right subdir
sh project_SHA3-32bit/pipeline_runner/archive_run.sh \
    --name midscale_v1_f9_sigma3p0 \
    --env-file project_SHA3-32bit/pipeline_runner/envs/.env_midscale_v1_f9_sigma3p0 \
    --log /tmp/pipeline_midscale_v1_f9_sigma3p0.log \
    --note "midscale fix run after octal bug; ICS level 70"

# then move to the correct subdir
mv runs_archive/2026-*_midscale_v1_f9_sigma3p0 runs_archive/midscale_v1/
```

`archive_run.sh` always writes to `runs_archive/` flat; move into the subdir after.

## Step 2 — inspect a single run

```
runs_archive/<scale>/<date>_<label>/
├── README.md                          # one-line verdict, Rate_Scan progress
├── 0004_validation/quality_report/
│   ├── report.txt                     # human-readable SR/GE summary
│   ├── summary_family_round.csv       # machine-readable SR/GE per family×round
│   └── summary_word_round.csv         # per-word SR/GE
└── 0005_SASCA/Rate_Scan/
    ├── 2R_Success/success_????.npy    # one file per rate point
    ├── 3R_Success/...
    └── 4R_Success/...
```

Quick read:

```sh
cat runs_archive/smoke_v3/2026-05-26_smoke_v3_f9_sigma1p0/README.md
cat runs_archive/smoke_v3/2026-05-26_smoke_v3_f9_sigma1p0/0004_validation/quality_report/report.txt
```

## Step 3 — compare two or more runs

### Pairwise / multi-run comparison

```sh
python project_SHA3-32bit/pipeline_runner/compare_runs.py \
    runs_archive/smoke_v3/2026-05-26_smoke_v3_f9_sigma1p0 \
    runs_archive/midscale_v1/2026-05-27_midscale_v1_f9_sigma1p0 \
    --out runs_archive/_compare_plots/cross_scale/f9_sigma1p0_smoke_vs_midscale_2R.png \
    --rate-depth 2R
```

Flags:
- `--rate-depth 2R|3R|4R` — which SASCA round depth to plot rate-scan curves for.
- `--out PATH` — output PNG path; a `.txt` summary is written alongside automatically.
- `--title TEXT` — figure title.

### Sigma-sweep overview (all modes, one scale)

`sigma_sweep_compare.py` reads an entire scale's archive root and plots SR and SASCA
success vs σ for all four modes at once:

```sh
# smoke_v3 sigma sweep
python project_SHA3-32bit/pipeline_runner/sigma_sweep_compare.py \
    --archive-root runs_archive/smoke_v3 \
    --out-prefix runs_archive/_compare_plots/smoke_v3/sigma_sweep

# midscale_v1 sigma sweep
python project_SHA3-32bit/pipeline_runner/sigma_sweep_compare.py \
    --archive-root runs_archive/midscale_v1 \
    --out-prefix runs_archive/_compare_plots/midscale_v1/sigma_sweep
```

Produces three PNGs per run: `*_per_mode.png`, `*_cross_mode.png`, `*_rate_scan_grid.png`.

### Per-bit error breakdown

```sh
python project_SHA3-32bit/pipeline_runner/analyze_per_bit_errors.py \
    runs_archive/smoke_v3/2026-05-26_smoke_v3_f9_sigma1p0 \
    --depth 2R \
    --out-dir runs_archive/_compare_plots/smoke_v3/
```

Outputs per-bit error rate, 1→0/0→1 imbalance, lane×bit heatmap, and a delta map
showing which bits BP fixed vs. broke.

## Step 4 — re-run quality analysis without re-archiving

If `quality_report/` is missing or stale, regenerate it in-place:

```sh
cd project_SHA3-32bit/0004_validation/template_validation_bytes
python analyze_result_tables_zip.py \
    ../../pipeline_runner/runs_archive/smoke_v3/2026-05-26_smoke_v3_f9_sigma1p0/0004_validation/Result_Tables.zip \
    --out-dir ../../pipeline_runner/runs_archive/smoke_v3/2026-05-26_smoke_v3_f9_sigma1p0/0004_validation/quality_report/
```

`archive_run.sh` calls this automatically if the dir is absent; run it manually when you
want to refresh an existing archive (e.g., after the analysis script is updated).

## Where comparison outputs go

Save all comparison outputs under `runs_archive/_compare_plots/<subdir>/`:

| Subdir | Contents |
|--------|----------|
| `smoke_v2/` | historical comparisons from the smoke_v2 era (reference only) |
| `smoke_v3/` | smoke_v3 sigma-sweep plots and per-run comparisons |
| `midscale_v1/` | midscale_v1 plots |
| `cross_scale/` | comparisons spanning two or more scales |

See `runs_archive/_compare_plots/README.md` for naming conventions.

## Typical evaluation workflow

For a new scale that just finished all 36 runs:

```sh
# 1. archive all 36 runs into the right subdir (one archive_run.sh call per run)

# 2. generate sigma-sweep overview
python pipeline_runner/sigma_sweep_compare.py \
    --archive-root runs_archive/<scale> \
    --out-prefix runs_archive/_compare_plots/<scale>/sigma_sweep

# 3. compare same sigma across scales (e.g., f9 σ=1.0 smoke vs midscale)
python pipeline_runner/compare_runs.py \
    runs_archive/smoke_v3/<date>_smoke_v3_f9_sigma1p0 \
    runs_archive/midscale_v1/<date>_midscale_v1_f9_sigma1p0 \
    runs_archive/paperscale_v3/<date>_paperscale_v3_f9_sigma1p0 \
    --out runs_archive/_compare_plots/cross_scale/f9_sigma1p0_all_scales_2R.png \
    --rate-depth 2R

# 4. investigate per-bit errors for key runs (e.g., borderline SASCA success)
python pipeline_runner/analyze_per_bit_errors.py \
    runs_archive/<scale>/<date>_<label> \
    --depth 2R
```

## Key metrics to report

| Metric | Where | Good threshold |
|--------|-------|----------------|
| Template SR (family A) | `summary_family_round.csv`, family A | > 0.5 at σ ≤ 1.0 |
| Template GE (family A) | same | < 20 at σ ≤ 1.0 |
| SASCA 2R SR@mid | `Rate_Scan_2R_Success/` | > 0.5 at moderate rate |
| SASCA 2R last≥50% | compare_runs.py `.txt` | pt15/20+ for smoke |
| σ crossover (f9 vs hw/hd) | sigma_sweep_cross_mode.png | ~σ=1.5–2.0 |
