# Pipeline Run Log

Tracks sigma sweep runs and notable smoke runs.
Update this file whenever a batch launches, finishes, or gets archived.

Log markers: `[MOVE : DN]` = detection done, `[MOVE : TR]` = training started,
`VALIDATION` = phase 0004, `SASCA` = phase 0005, `DONE` = complete.

---

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

Est. completion: ~12–14h after launch (hd/hw/id slices done ~8–10h).

Wave A launched 2026-05-22 ~10:57–11:05 (21 runs: hd/hw/id σ=0.1–2.5 + f9 σ=3.0–4.0, --skip-sim).
Wave Af9 batch 1 launched 2026-05-22 ~11:05 (f9 σ=0.1/0.5/1.0, simulate). [MOVE:DN] at ~11:39.
Wave Af9 batch 2 launched 2026-05-22 ~15:00 (f9 σ=1.5/2.0/2.5, simulate). [MOVE:DN] expected ~19:00.
Wave B PENDING — launch `sh launch_midscale_v1.sh B` when `pgrep -c -f detect_script` ≤ 20.

**Status as of 2026-05-22 18:45:**
- 25 concurrent R2 processes. All 27 launched runs are active.
- R2 is taking longer than the 2–4h estimate (~6.5h so far for Wave A runs). Still progressing.
- Wave B not yet launched — R2 count must drop to ≤20 first.
- Wave B launch command (from local pipeline_runner/):
  ```sh
  ssh IDP "pgrep -c -f detect_script"   # must be ≤ 20 before running
  sh launch_midscale_v1.sh B
  ```

| Run | Sandbox | Started | Status (2026-05-22 18:45) | Finished | Archive |
|-----|---------|---------|--------------------------|----------|---------|
| hd σ=0.1–2.5 (×6) | midscale_v1_hd_sigma* | 2026-05-22 10:57 | R2 detection (6.5h in) | — | — |
| hd σ=3.0–4.0 (×3) | midscale_v1_hd_sigma* | — | PENDING (Wave B) | — | — |
| hw σ=0.1–2.5 (×6) | midscale_v1_hw_sigma* | 2026-05-22 10:57 | R2 detection (6.5h in) | — | — |
| hw σ=3.0–4.0 (×3) | midscale_v1_hw_sigma* | — | PENDING (Wave B) | — | — |
| id σ=0.1–2.5 (×6) | midscale_v1_id_sigma* | 2026-05-22 10:57 | R2 detection (6.5h in) | — | — |
| id σ=3.0–4.0 (×3) | midscale_v1_id_sigma* | — | PENDING (Wave B) | — | — |
| f9 σ=3.0–4.0 (×3) | midscale_v1_f9_sigma* | 2026-05-22 10:59 | R2 detection (6.5h in) | — | — |
| f9 σ=0.1/0.5/1.0 | midscale_v1_f9_sigma* | 2026-05-22 11:05 | R2 detection (4h in) | — | — |
| f9 σ=1.5/2.0/2.5 | midscale_v1_f9_sigma* | 2026-05-22 ~15:00 | R2 detection (just entered) | — | — |

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
