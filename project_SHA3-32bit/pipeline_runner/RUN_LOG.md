# Pipeline Run Log

Tracks sigma sweep runs and notable smoke runs.
Update this file whenever a batch launches, finishes, or gets archived.

Log markers: `[MOVE : DN]` = detection done, `[MOVE : TR]` = training started,
`VALIDATION` = phase 0004, `SASCA` = phase 0005, `DONE` = complete.

---

## Status snapshot — 2026-05-25

| Batch | # Runs | State | Notes |
|-------|--------|-------|-------|
| Midscale v1 σ=0.1–2.5 | 24 | **COMPLETE** | All 4 modes, ICS level 90, archived pending |
| Midscale v1 σ=3.0–4.0 ICS fixes | 11 | **Training in progress** | --skip-detection; f9σ3p0→70, f9σ4p0→40, hd/hw/id→70/50/40 |
| Midscale v1 f9 σ=3.5 (original) | 1 | **SASCA in progress** | Already at correct ICS=50; no fix needed |
| Smoke v3 ICS sweep | 36 | **Simulation/R2 detection** | Fresh simulation; ICS scan pending after [MOVE:DN] |
| Paperscale v3 | 0 | **Not started** | Env files ready; await midscale + smoke v3 completion |

**R2 processes active** (as of ~12:15 2026-05-25): 7 (smoke v3 early R2 + midscale f9σ3p5)

---

## Midscale v1 Sigma Sweep — COMPLETE / FIXING (36 runs — 4 modes × 9 sigmas)

Scale: 30 det sets, 200 TR sets, 20 val sets, 300 SASCA traces.
Env dir: `envs/midscale_v1_sigma_sweep/sigma{X}/` (per-sigma-slice, 4 modes per slice).
Sandbox naming: `midscale_v1_{mode}_sigma{X}`.

Trace reuse:
- hd/hw/id all sigmas: `--skip-sim`, TRACES_DIR=`/storage/ge96pug/traces_paperscale_v2_{mode}_sigma{X}`
- f9 σ=3.0/3.5/4.0: `--skip-sim`, TRACES_DIR=`/storage/ge96pug/traces_paperscale_v2_f9_sigma{X}` (TR=400 ✓)
- f9 σ=0.1/0.5/1.0: simulate (TR killed at 4–6 sets in crash), TRACES_DIR=`/storage/ge96pug/traces_midscale_v1_f9_sigma{X}`
- f9 σ=1.5/2.0/2.5: simulate (no traces exist), TRACES_DIR=`/storage/ge96pug/traces_midscale_v1_f9_sigma{X}`

**NOTE:** `traces_paperscale_v2_*` dirs are now gone from IDP. Midscale sandboxes deployed those
traces into their own Raw/ subdirs before the paperscale dirs were deleted, so midscale pipeline
state is intact. However, any future run that needs hd/hw/id traces must simulate fresh.

Concurrency: safe cap ≤24 concurrent R2 (midscale ~10 GB commit/process vs paperscale ~33 GB).

Wave A launched 2026-05-22 ~10:57–11:05 (21 runs: hd/hw/id σ=0.1–2.5 + f9 σ=3.0–4.0, --skip-sim).
Wave Af9 batch 1 launched 2026-05-22 ~11:05 (f9 σ=0.1/0.5/1.0, simulate). [MOVE:DN] at ~11:39.
Wave Af9 batch 2 launched 2026-05-22 ~15:00 (f9 σ=1.5/2.0/2.5, simulate).
Wave B launched 2026-05-23 ~11:52 (hd/hw/id σ=3.0–4.0, --skip-sim). R2 count was 20 at launch.

**ICS level fix round 1 — f9 σ=3.0/3.5/4.0 (2026-05-23):**
High-noise f9 runs found no ICS at threshold 90 (ics_original_090.zip empty). Fixed in-place:
- Updated sandbox `.env` + local env files: SHA3_TRAINING_ICS_LEVEL=50, VALIDATION/SASCA tags=50.
- σ=3.0 and σ=4.0: pipeline died at ICS check → cleaned 0003 → restarted via `run_overnight_chain.sh --with-training`.
- σ=3.5: `.env` updated while in R2; pipeline died anyway (old env vars in shell) → same restart applied.
- ics_original_050.zip had 131–141 KB of content for all three runs.

**ICS level fix round 2 — per-sigma consistency (2026-05-25):**
Applied per-sigma ICS standard (highest level passing for all 4 modes = f9 bottleneck).
Used `--skip-detection` (reuse existing R2 archives, re-run 0003–0005 only).

| Run | Old level | New level | Log |
|-----|-----------|-----------|-----|
| f9 σ=4.0 | 50 (**BROKEN**: 9 empty arrays) | **40** | `fix_f9_sigma4p0.log` |
| f9 σ=3.0 | 50 (valid but suboptimal) | **70** | `fix_f9_sigma3p0.log` |
| hd σ=3.0 | 90 (mismatch) | **70** | `fix_hd_sigma3p0.log` |
| hw σ=3.0 | 90 (mismatch) | **70** | `fix_hw_sigma3p0.log` |
| id σ=3.0 | 90 (mismatch) | **70** | `fix_id_sigma3p0.log` |
| hd σ=3.5 | 90 (mismatch) | **50** | `fix_hd_sigma3p5.log` |
| hw σ=3.5 | 90 (mismatch) | **50** | `fix_hw_sigma3p5.log` |
| id σ=3.5 | 90 (mismatch) | **50** | `fix_id_sigma3p5.log` |
| hd σ=4.0 | 90 (mismatch) | **40** | `fix_hd_sigma4p0.log` |
| hw σ=4.0 | 90 (mismatch) | **40** | `fix_hw_sigma4p0.log` |
| id σ=4.0 | 90 (mismatch) | **40** | `fix_id_sigma4p0.log` |

Fix sessions launched 2026-05-25 ~11:26–11:34 (11 concurrent). Training in progress as of ~12:15.
f9 σ=3.5 already at level 50 (correct) — no fix needed; original session still running SASCA.

**Final ICS levels (midscale v1, per-sigma standard):**

| Sigma | hd | hw | id | f9 |
|-------|----|----|----|----|
| 0.1–2.5 | 90 | 90 | 90 | 90 |
| 3.0 | 70 | 70 | 70 | 70 |
| 3.5 | 50 | 50 | 50 | 50 |
| 4.0 | 40 | 40 | 40 | 40 |

**Status as of 2026-05-25 ~12:15:**

| Run | Status |
|-----|--------|
| σ=0.1–2.5, all 4 modes (24 runs) | **COMPLETE** |
| f9 σ=3.5 | **SASCA running** (original session, level 50 ✓) |
| All 11 fix sessions (σ=3.0/3.5/4.0 for modes w/ level change) | **Training in progress** |

**Archive:** pending all 11 fix sessions + f9σ3.5 completion.
Verify: `grep -c 'COMPLETE' /storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_*/project_SHA3-32bit/pipeline_runner/*.log`
Archive cmd: `for mode in hd hw id f9; do for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
  sb=/storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_${mode}_sigma${sig}/project_SHA3-32bit
  sh pipeline_runner/archive_run.sh --name midscale_v1_${mode}_sigma${sig} --env-file .env
done; done`

---

## Smoke v3 ICS Sensitivity Sweep — RUNNING (36 runs — 4 modes × 9 sigmas)

**Purpose:** Compare ICS level 10 (existing smoke v2 archives) vs per-sigma standard at smoke scale.
Scale: 10 det sets, 50 TR sets, 20 val sets, 50 SASCA traces.
Env dir: `envs/smoke_v3_ics_sweep/sigma{X}/`. Sandbox naming: `smoke_v3_{mode}_sigma{X}`.

**Trace situation:** All 36 runs simulate fresh.
- f9 σ=0.1–2.5 (6 runs): `--skip-sim`, TRACES_DIR=`/storage/ge96pug/traces_midscale_v1_f9_sigma{X}` (exists ✓)
- All other 30 runs: fresh simulation into `traces_smoke_v3_{mode}_sigma{X}`
  (paperscale_v2 hd/hw/id traces gone; midscale hd/hw/id Raw/ dirs have only 30 det sets,
   which is enough for smoke reuse but copying is not yet automated — --skip-deploy not wired up here)

All 36 sessions launched 2026-05-25 ~11:37–12:03.
As of ~12:15: 6 sessions at early R2 (Linear Regression), remaining in simulation.

**ICS boundary scan (required before training):**
After all 36 show `[MOVE:DN]`, run:
```sh
sh pipeline_runner/launch_smoke_v3.sh --ics-scan   # or manual loop below
ssh IDP "for mode in hd hw id f9; do for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
  sb=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v3_\${mode}_sigma\${sig}/project_SHA3-32bit
  printf \"\${mode}_sigma\${sig}: \"
  for level in 090 080 070 060 050 040 030 020 010; do
    ok=\$(python3 \"\$sb/pipeline_runner/check_ics_archive.py\" \
      --ics-zip \"\$sb/0002_detection/Code_extract_ics/ics_original_\${level}.zip\" \
      2>&1 | grep -c 'OK:')
    if [ \"\$ok\" -eq 1 ]; then echo \"max valid = \$level\"; break; fi
  done
done; done"
```
Then apply --skip-detection fix per run if level differs from env file placeholder (90).

---

## Paperscale v3 Sigma Sweep — NOT STARTED (36 runs — 4 modes × 9 sigmas)

Scale: 100 det sets, 400 TR sets, 40 val sets, 1000 SASCA traces. R2 commit ~33 GB/process.
Env dir: `envs/paperscale_v3_sigma_sweep/sigma{X}/`. Sandbox: `paperscale_v3_{mode}_sigma{X}`.
Launcher: `launch_paperscale_v3.sh`.

**All 36 runs need fresh simulation** (paperscale_v2 trace dirs gone from IDP).
TRACES_DIR: `/storage/ge96pug/traces_paperscale_v3_{mode}_sigma{X}` (fresh per run).

ICS levels (midscale-derived baselines; verify after detection for σ≥3.0):

| Sigma | Level | Notes |
|-------|-------|-------|
| 0.1–2.5 | 90 | All modes stable at this threshold |
| 3.0 | 70 | Placeholder — paperscale has 100 det sets; may support higher |
| 3.5 | 50 | Placeholder |
| 4.0 | 40 | Placeholder |

Wave structure (simulation cap: 3 concurrent; R2 cap: ≤18):
```sh
# Launch 3 waves simultaneously (= 9 concurrent sims, 3 per mode)
sh launch_paperscale_v3.sh --wave A1   # hd σ=0.1/0.5/1.0
sh launch_paperscale_v3.sh --wave B1   # hw σ=0.1/0.5/1.0
sh launch_paperscale_v3.sh --wave D1   # f9 σ=0.1/0.5/1.0
# After R2 count ≤ 15:
sh launch_paperscale_v3.sh --wave A2   # hd σ=1.5/2.0/2.5
# ... etc., check --status between waves
```

ICS verification command (before training for σ≥3.0):
```sh
sh launch_paperscale_v3.sh --ics-scan   # after [MOVE:DN] in σ≥3.0 runs
sh launch_paperscale_v3.sh --fix-ics MODE SIGMA LEVEL   # if level needs updating
```

---

## Paperscale Sigma Sweep — FROZEN (OOM crash 2026-05-21) (36 runs — 4 modes × 9 sigmas)

Sigmas: 0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0

**All processes killed by OOM at 2026-05-21 10:41–10:51.** Root cause: 28 concurrent R2
processes committed ~33 GB virtual each, exceeding ~940 GB overcommit limit. Nothing is
running. Frozen state preserved on IDP.

**Trace dirs status (as of 2026-05-25):** `traces_paperscale_v2_hd/hw/id_*` directories have
been deleted from IDP. Only the sandbox Raw/ dirs (which contain deployed trace zips) remain.
The frozen paperscale_v2 sandboxes themselves are still on IDP but will not be resumed
(superseded by paperscale v3).

### Batch 1 — hd (frozen state at OOM crash)

| Run | Sandbox | Started | Frozen Status |
|-----|---------|---------|--------------|
| hd σ=0.1 | paperscale_v2_hd_sigma0p1 | 2026-05-18 19:27 | **Partial R2** (detect_results_08 partially filled) |
| hd σ=0.5 | paperscale_v2_hd_sigma0p5 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=1.0 | paperscale_v2_hd_sigma1p0 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=1.5 | paperscale_v2_hd_sigma1p5 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=2.0 | paperscale_v2_hd_sigma2p0 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=2.5 | paperscale_v2_hd_sigma2p5 | 2026-05-18 19:27 | R2 DONE; **partial training** (IoP parts 00–02 done) |
| hd σ=3.0 | paperscale_v2_hd_sigma3p0 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=3.5 | paperscale_v2_hd_sigma3p5 | 2026-05-18 19:28 | R2 DONE; **partial training** (IoP part 00 done) |
| hd σ=4.0 | paperscale_v2_hd_sigma4p0 | 2026-05-18 19:28 | **Partial R2** |

### Batch 2+3 — hw + id (frozen state at OOM crash)

Launched 2026-05-21 09:13 — OOM hit ~90 min later. Zero R2 progress for both modes.

| Run | Sandbox | Frozen Status |
|-----|---------|--------------|
| hw σ=0.1–4.0 (×9) | paperscale_v2_hw_sigma* | **0 R2 progress** (preprocessing/deploy only) |
| id σ=0.1–4.0 (×9) | paperscale_v2_id_sigma* | **0 R2 progress** (preprocessing/deploy only) |

### Batch 4c — f9 high noise (frozen state at OOM crash)

| Run | Sandbox | Started | Frozen Status |
|-----|---------|---------|--------------|
| f9 σ=3.0 | paperscale_v2_f9_sigma3p0 | 2026-05-18 19:48 | **Partial R2** |
| f9 σ=3.5 | paperscale_v2_f9_sigma3p5 | 2026-05-18 19:48 | **Partial R2** |
| f9 σ=4.0 | paperscale_v2_f9_sigma4p0 | 2026-05-18 19:48 | **Partial R2** |

### Batch 4a — f9 low noise (frozen state at OOM crash)

| Run | Sandbox | Started | Frozen Status |
|-----|---------|---------|--------------|
| f9 σ=0.1 | paperscale_v2_f9_sigma0p1 | 2026-05-21 09:13 | **TR simulation killed** (DN=100, TR=6, TS=0) |
| f9 σ=0.5 | paperscale_v2_f9_sigma0p5 | 2026-05-21 09:13 | **TR simulation killed** (DN=100, TR=4, TS=0) |
| f9 σ=1.0 | paperscale_v2_f9_sigma1p0 | 2026-05-21 09:13 | **TR simulation killed** (DN=100, TR=5, TS=0) |

### Batch 4b — f9 mid noise (never launched)

| Run | Frozen Status |
|-----|--------------|
| f9 σ=1.5/2.0/2.5 | **Never launched** — no sandboxes, no traces |

---

## Smoke Sigma Sweep (completed pilot runs)

### smoke_v2_id — identity leakage mode, all 9 sigmas

| Run | Finished | Archive |
|-----|----------|---------|
| id σ=0.1 | 2026-05-19 04:51 | 2026-05-20_smoke_v2_id_sigma0p1 |
| id σ=0.5 | 2026-05-19 06:01 | 2026-05-20_smoke_v2_id_sigma0p5 |
| id σ=1.0 | 2026-05-19 07:29 | 2026-05-20_smoke_v2_id_sigma1p0 |
| id σ=1.5 | 2026-05-19 03:57 | 2026-05-20_smoke_v2_id_sigma1p5 |
| id σ=2.0 | 2026-05-19 05:04 | 2026-05-20_smoke_v2_id_sigma2p0 |
| id σ=2.5 | 2026-05-19 06:31 | 2026-05-20_smoke_v2_id_sigma2p5 |
| id σ=3.0 | 2026-05-19 05:10 | 2026-05-20_smoke_v2_id_sigma3p0 |
| id σ=3.5 | 2026-05-19 05:19 | 2026-05-20_smoke_v2_id_sigma3p5 |
| id σ=4.0 | 2026-05-19 04:07 | 2026-05-20_smoke_v2_id_sigma4p0 |

### smoke_v2_f9 high noise — f9 mode, σ=3.0/3.5/4.0 (env identical to paperscale)

| Run | Finished | Archive |
|-----|----------|---------|
| f9 σ=3.0 | 2026-05-19 20:00 | 2026-05-20_paperscale_v2_f9_sigma3p0 |
| f9 σ=3.5 | 2026-05-19 23:24 | 2026-05-20_paperscale_v2_f9_sigma3p5 |
| f9 σ=4.0 | 2026-05-19 20:55 | 2026-05-20_paperscale_v2_f9_sigma4p0 |

---

## Quick status check commands

```sh
# Midscale fix run completion
ssh IDP "grep -c 'COMPLETE' /storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_*/project_SHA3-32bit/pipeline_runner/fix_*.log 2>/dev/null | grep ':1'"

# Smoke v3 detection progress ([MOVE:DN] = R2 done, training started)
ssh IDP "grep -l 'MOVE.*DN' /storage/ge96pug/Projects_SHA3_sandbox_smoke_v3_*/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null | wc -l"

# R2 process count (global cap: ≤18 for paperscale)
ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0"

# Paperscale v3 overview
sh pipeline_runner/launch_paperscale_v3.sh --status
```

## Midscale v1 Sigma Sweep — ACTIVE (36 runs — 4 modes × 9 sigmas)

Scale: 30 det sets, 200 TR sets, 20 val sets, 300 SASCA traces.
Env dir: `envs/midscale_v1_sigma_sweep/sigma{X}/` (per-sigma-slice, 4 modes per slice).
Sandbox naming: `midscale_v1_{mode}_sigma{X}`.

Trace reuse:
- hd/hw/id all sigmas: `--skip-sim`, TRACES_DIR=`/storage/ge96pug/traces_paperscale_v2_{mode}_sigma{X}`
- f9 σ=3.0/3.5/4.0: `--skip-sim`, TRACES_DIR=`/storage/ge96pug/traces_paperscale_v2_f9_sigma{X}` (TR=400 ✓)
- f9 σ=0.1/0.5/1.0: simulate (TR killed at 4–6 sets in crash), TRACES_DIR=`/storage/ge96pug/traces_midscale_v1_f9_sigma{X}`
- f9 σ=1.5/2.0/2.5: simulate (no traces exist), TRACES_DIR=`/storage/ge96pug/traces_midscale_v1_f9_sigma{X}`

Concurrency: safe cap ≤24 concurrent R2 (midscale ~10 GB commit/process vs paperscale ~33 GB).
Before each wave: `ssh IDP "pgrep -c -f detect_script"` must be ≤ 20.

Wave A — hd/hw/id × 6 slices (σ=0.1–2.5) simultaneously; f9 σ=3.0/3.5/4.0 also --skip-sim.
Wave A-f9 — f9 simulations: 3 concurrent max (disk-write cap); σ=0.1/0.5/1.0 first, then σ=1.5/2.0/2.5.
Wave B — hd/hw/id × 3 slices (σ=3.0–4.0) when R2 count drops; f9 σ=0.1–2.5 after simulation done.

Actual R2 duration: ~22–24h (far longer than 2–4h estimate; likely BLAS contention at 20–25 concurrent).

Wave A launched 2026-05-22 ~10:57–11:05 (21 runs: hd/hw/id σ=0.1–2.5 + f9 σ=3.0–4.0, --skip-sim).
Wave Af9 batch 1 launched 2026-05-22 ~11:05 (f9 σ=0.1/0.5/1.0, simulate). [MOVE:DN] at ~11:39.
Wave Af9 batch 2 launched 2026-05-22 ~15:00 (f9 σ=1.5/2.0/2.5, simulate).
Wave B launched 2026-05-23 ~11:52 (hd/hw/id σ=3.0–4.0, --skip-sim). R2 count was 20 at launch.

**ICS level fix — f9 σ=3.0/3.5/4.0:**
High-noise f9 runs found no ICS at threshold 90 (ics_original_090.zip empty). Fixed in-place:
- Updated sandbox `.env` + local env files: SHA3_TRAINING_ICS_LEVEL=50, VALIDATION/SASCA tags=50.
- σ=3.0 and σ=4.0: pipeline died at ICS check → cleaned 0003 → restarted via `run_overnight_chain.sh --with-training`.
- σ=3.5: `.env` updated while in R2; pipeline died anyway (old env vars in shell) → same restart applied.
- ics_original_050.zip had 131–141 KB of content for all three runs.
- Env files committed: `envs/midscale_v1_sigma_sweep/sigma{3p0,3p5,4p0}/.env_midscale_v1_f9_sigma*`

**Status as of 2026-05-23 ~12:00 — all 36 runs active:**

| Run | Sandbox | Started | Status (2026-05-23 ~12:00) |
|-----|---------|---------|---------------------------|
| hd σ=0.1–2.5 (×6) | midscale_v1_hd_sigma* | 2026-05-22 10:57 | Mixed: some in training, some in R2 |
| hd σ=3.0–4.0 (×3) | midscale_v1_hd_sigma* | 2026-05-23 11:52 | Trace deploy / early R2 |
| hw σ=0.1–2.5 (×6) | midscale_v1_hw_sigma* | 2026-05-22 10:57 | Mixed: some in training, some in R2 |
| hw σ=3.0–4.0 (×3) | midscale_v1_hw_sigma* | 2026-05-23 11:52 | Trace deploy / early R2 |
| id σ=0.1–2.5 (×6) | midscale_v1_id_sigma* | 2026-05-22 10:57 | Mixed: some in SASCA, some in R2 |
| id σ=3.0–4.0 (×3) | midscale_v1_id_sigma* | 2026-05-23 11:52 | Trace deploy / early R2 |
| f9 σ=3.0–4.0 (×3) | midscale_v1_f9_sigma* | 2026-05-22 10:59 | Training (restarted with ICS=50) |
| f9 σ=0.1/0.5/1.0 | midscale_v1_f9_sigma* | 2026-05-22 11:05 | R2 detection |
| f9 σ=1.5/2.0/2.5 | midscale_v1_f9_sigma* | 2026-05-22 ~15:00 | R2 detection |

---

## Paperscale Sigma Sweep — FROZEN (OOM crash 2026-05-21) (36 runs — 4 modes × 9 sigmas)

Sigmas: 0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0

**All processes killed by OOM at 2026-05-21 10:41–10:51.** Root cause: 28 concurrent R2
processes committed ~33 GB virtual each, exceeding ~940 GB overcommit limit. Nothing is
running. Frozen state preserved on IDP. To resume paperscale, see PAPERSCALE_RELAUNCH_PLAN.md.

### Batch 1 — hd (frozen state at OOM crash)

| Run | Sandbox | Started | Frozen Status |
|-----|---------|---------|--------------|
| hd σ=0.1 | paperscale_v2_hd_sigma0p1 | 2026-05-18 19:27 | **Partial R2** (detect_results_08 partially filled) |
| hd σ=0.5 | paperscale_v2_hd_sigma0p5 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=1.0 | paperscale_v2_hd_sigma1p0 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=1.5 | paperscale_v2_hd_sigma1p5 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=2.0 | paperscale_v2_hd_sigma2p0 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=2.5 | paperscale_v2_hd_sigma2p5 | 2026-05-18 19:27 | R2 DONE; **partial training** (IoP parts 00–02 done) |
| hd σ=3.0 | paperscale_v2_hd_sigma3p0 | 2026-05-18 19:27 | **Partial R2** |
| hd σ=3.5 | paperscale_v2_hd_sigma3p5 | 2026-05-18 19:28 | R2 DONE; **partial training** (IoP part 00 done) |
| hd σ=4.0 | paperscale_v2_hd_sigma4p0 | 2026-05-18 19:28 | **Partial R2** |

### Batch 2+3 — hw + id (frozen state at OOM crash)

Launched 2026-05-21 09:13 — OOM hit ~90 min later. Zero R2 progress for both modes.

| Run | Sandbox | Frozen Status |
|-----|---------|--------------|
| hw σ=0.1–4.0 (×9) | paperscale_v2_hw_sigma* | **0 R2 progress** (preprocessing/deploy only) |
| id σ=0.1–4.0 (×9) | paperscale_v2_id_sigma* | **0 R2 progress** (preprocessing/deploy only) |

### Batch 4c — f9 high noise (frozen state at OOM crash)

| Run | Sandbox | Started | Frozen Status |
|-----|---------|---------|--------------|
| f9 σ=3.0 | paperscale_v2_f9_sigma3p0 | 2026-05-18 19:48 | **Partial R2** |
| f9 σ=3.5 | paperscale_v2_f9_sigma3p5 | 2026-05-18 19:48 | **Partial R2** |
| f9 σ=4.0 | paperscale_v2_f9_sigma4p0 | 2026-05-18 19:48 | **Partial R2** |

Trace dirs complete (DN=100, TR=400, TS=40 each) — resumable with smart R2 resume.

### Batch 4a — f9 low noise (frozen state at OOM crash)

| Run | Sandbox | Started | Frozen Status |
|-----|---------|---------|--------------|
| f9 σ=0.1 | paperscale_v2_f9_sigma0p1 | 2026-05-21 09:13 | **TR simulation killed** (DN=100, TR=6, TS=0) |
| f9 σ=0.5 | paperscale_v2_f9_sigma0p5 | 2026-05-21 09:13 | **TR simulation killed** (DN=100, TR=4, TS=0) |
| f9 σ=1.0 | paperscale_v2_f9_sigma1p0 | 2026-05-21 09:13 | **TR simulation killed** (DN=100, TR=5, TS=0) |

### Batch 4b — f9 mid noise (never launched)

| Run | Frozen Status |
|-----|--------------|
| f9 σ=1.5/2.0/2.5 | **Never launched** — no sandboxes, no traces |

---

## Smoke Sigma Sweep (completed pilot runs)

### smoke_v2_id — identity leakage mode, all 9 sigmas

| Run | Finished | Archive |
|-----|----------|---------|
| id σ=0.1 | 2026-05-19 04:51 | 2026-05-20_smoke_v2_id_sigma0p1 |
| id σ=0.5 | 2026-05-19 06:01 | 2026-05-20_smoke_v2_id_sigma0p5 |
| id σ=1.0 | 2026-05-19 07:29 | 2026-05-20_smoke_v2_id_sigma1p0 |
| id σ=1.5 | 2026-05-19 03:57 | 2026-05-20_smoke_v2_id_sigma1p5 |
| id σ=2.0 | 2026-05-19 05:04 | 2026-05-20_smoke_v2_id_sigma2p0 |
| id σ=2.5 | 2026-05-19 06:31 | 2026-05-20_smoke_v2_id_sigma2p5 |
| id σ=3.0 | 2026-05-19 05:10 | 2026-05-20_smoke_v2_id_sigma3p0 |
| id σ=3.5 | 2026-05-19 05:19 | 2026-05-20_smoke_v2_id_sigma3p5 |
| id σ=4.0 | 2026-05-19 04:07 | 2026-05-20_smoke_v2_id_sigma4p0 |

### smoke_v2_f9 high noise — f9 mode, σ=3.0/3.5/4.0 (env identical to paperscale)

| Run | Finished | Archive |
|-----|----------|---------|
| f9 σ=3.0 | 2026-05-19 20:00 | 2026-05-20_paperscale_v2_f9_sigma3p0 |
| f9 σ=3.5 | 2026-05-19 23:24 | 2026-05-20_paperscale_v2_f9_sigma3p5 |
| f9 σ=4.0 | 2026-05-19 20:55 | 2026-05-20_paperscale_v2_f9_sigma4p0 |

---

## Quick status check commands

```sh
# All running paperscale runs — last 2 log lines each
ssh IDP "for log in /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v2_*/project_SHA3-32bit/pipeline_runner/sandbox_*.log; do echo \"=== \$log ===\"; tail -2 \"\$log\" 2>/dev/null; done"

# Just the last marker line per run (phase transitions)
ssh IDP "tail -1 /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v2_*/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null"

# Check if all 9 hd runs have cleared R2 (trigger for hw+id+f9 launch)
ssh IDP "grep -c 'DONE.*0002 detection R2' /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v2_hd_sigma*/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null"
# → need 9 lines of ':1'
```
