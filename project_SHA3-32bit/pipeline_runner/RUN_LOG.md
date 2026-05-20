# Pipeline Run Log

Tracks paperscale sigma sweep runs and notable smoke runs.
Update this file whenever a batch launches, finishes, or gets archived.

Log markers: `[MOVE : DN]` = detection done, `[MOVE : TR]` = training started,
`VALIDATION` = phase 0004, `SASCA` = phase 0005, `DONE` = complete.

---

## Paperscale Sigma Sweep (36 runs — 4 modes × 9 sigmas)

Sigmas: 0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0

### Batch 1 — hd (--skip-sim)

| Run | Sandbox | Started | Status | Finished | Archive |
|-----|---------|---------|--------|----------|---------|
| hd σ=0.1 | paperscale_v2_hd_sigma0p1 | 2026-05-18 19:27 | RUNNING (training) | — | — |
| hd σ=0.5 | paperscale_v2_hd_sigma0p5 | 2026-05-18 19:27 | RUNNING (training) | — | — |
| hd σ=1.0 | paperscale_v2_hd_sigma1p0 | 2026-05-18 19:27 | RUNNING (training) | — | — |
| hd σ=1.5 | paperscale_v2_hd_sigma1p5 | 2026-05-18 19:27 | RUNNING (training) | — | — |
| hd σ=2.0 | paperscale_v2_hd_sigma2p0 | 2026-05-18 19:27 | RUNNING (training) | — | — |
| hd σ=2.5 | paperscale_v2_hd_sigma2p5 | 2026-05-18 19:27 | RUNNING (training) | — | — |
| hd σ=3.0 | paperscale_v2_hd_sigma3p0 | 2026-05-18 19:27 | RUNNING (training) | — | — |
| hd σ=3.5 | paperscale_v2_hd_sigma3p5 | 2026-05-18 19:28 | RUNNING (training) | — | — |
| hd σ=4.0 | paperscale_v2_hd_sigma4p0 | 2026-05-18 19:28 | RUNNING (training) | — | — |

### Batch 2+3 — hw + id simultaneously (--skip-sim)

Launch both immediately when hd clears training (~2026-05-21 13:00). Safe to overlap:
no simulation contention, 192 cores handles 18 concurrent R2 runs (~1.4× slowdown vs 9).

| Run | Sandbox | Started | Status | Finished | Archive |
|-----|---------|---------|--------|----------|---------|
| hw σ=0.1–4.0 (×9) | paperscale_v2_hw_sigma* | — | PENDING (~2026-05-25 06:00) | — | — |
| id σ=0.1–4.0 (×9) | paperscale_v2_id_sigma* | — | PENDING (~2026-05-25 06:00) | — | — |

### Batch 4c — f9 high noise (simulate; launched with Batch 1)

| Run | Sandbox | Started | Status | Finished | Archive |
|-----|---------|---------|--------|----------|---------|
| f9 σ=3.0 | paperscale_v2_f9_sigma3p0 | 2026-05-18 19:48 | RUNNING (training) | — | — |
| f9 σ=3.5 | paperscale_v2_f9_sigma3p5 | 2026-05-18 19:48 | RUNNING (training) | — | — |
| f9 σ=4.0 | paperscale_v2_f9_sigma4p0 | 2026-05-18 19:48 | RUNNING (training) | — | — |

### Batch 4a — f9 low noise (simulate; σ=0.1, 0.5, 1.0)

| Run | Sandbox | Started | Status | Finished | Archive |
|-----|---------|---------|--------|----------|---------|
| f9 σ=0.1–1.0 (×3) | paperscale_v2_f9_sigma{0p1,0p5,1p0} | — | PENDING (~2026-05-28 08:00) | — | — |

### Batch 4b — f9 mid noise (simulate; σ=1.5, 2.0, 2.5)

| Run | Sandbox | Started | Status | Finished | Archive |
|-----|---------|---------|--------|----------|---------|
| f9 σ=1.5–2.5 (×3) | paperscale_v2_f9_sigma{1p5,2p0,2p5} | — | PENDING (~2026-05-31 10:00) | — | — |

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

# Check if any hd runs have cleared training (look for VALIDATION marker)
ssh IDP "grep -l VALIDATION /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v2_hd_sigma*/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null || echo 'none yet'"
```
