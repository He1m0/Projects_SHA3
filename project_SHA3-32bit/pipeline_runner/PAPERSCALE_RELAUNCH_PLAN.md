# Paperscale Sigma Sweep — Relaunch Plan (revised 2026-05-20)

## Context

36 paperscale runs across 4 leakage modes (hd, hw, id, f9) × 9 sigma values (0.1–4.0).

**Resource envelope:**
- Remote: 192 cores, ~940 GiB RAM (essentially idle), 3.5 TB free on /storage
- Each trace dir: ~36 GB. hd/hw/id traces already complete (27 × 36 GB = ~972 GB used).
- f9 traces deleted; need re-simulation (~9 × 36 GB = ~324 GB additional).
- Pipeline intermediates per run (HDF5 zips, templateLDA): ~10–30 GB each.

---

## Stage load analysis

**0002 R2 detection** is the dominant bottleneck. `detect_script.py` is a single Python
process that drives NumPy/BLAS matrix multiplies (LinearRegression fit over 16,000 traces ×
55,296 samples) sequentially — no joblib, no internal parallelism beyond BLAS threads.

Observed scaling from actual run data:
- 9 runs concurrent: ~65h wall-clock for R2 (7.2h/run)
- 18 runs concurrent: ~82h wall-clock for R2 (9.1h/run, ~1.27× slowdown per run)
- 24 runs concurrent (estimated): ~93h (~1.43×)
- 27 runs concurrent (estimated): ~98h (~1.51×)

RAM usage: ~1.7 GB per detection part × 4 parts/run × N runs. At 27 runs: ~183 GB — fine.

**f9 simulation** (single-threaded Python writing trace data) uses 1 CPU core per run and
is disk-write bound. Safe to run alongside R2 detection — entirely different resource. Limit
of 3 concurrent simulations is a disk-write bandwidth cap, not a CPU limit.

All other stages (preprocessing, intermediate values, IoPs, validation, SASCA) run fast
relative to R2 and template profiling. SASCA spawns 6 single-threaded processes per run;
27 runs × 6 = 162 cores used — not a bottleneck on a 192-core machine.

**Template profiling** (LDA via sklearn) also uses BLAS. With 27 concurrent runs this adds
contention, but since profiling runs after R2 and the training times of individual runs
naturally stagger (low-SNR runs train differently than high-SNR runs), peak overlap is low.

**Practical parallelism limits per stage:**

| Stage | Concurrent runs | Notes |
|-------|----------------|-------|
| f9 simulation | 3 | disk write cap |
| 0002 R2 detection | ≤24 | above 24 the per-run slowdown exceeds the parallelism gain |
| 0003 template profiling | ~18 | BLAS-bound; stagger naturally by sigma |
| 0005 SASCA | unlimited | 1 core/process × 6 processes/run |
| everything else | unlimited | fast stages, no meaningful contention |

---

## Strategy (revised)

**Key insight over the previous plan:** f9 simulation uses an entirely different resource
from R2 detection. There is no reason to wait for hw/id to finish training before simulating
f9. Overlapping simulation with detection costs nothing. Starting f9 4a+4b earlier saves
~5 days on total completion.

Revised trigger: instead of waiting for `DONE: 0003 training` (hd clears training), we
wait only for `DONE: 0002 detection R2` (hd clears R2). This avoids adding f9 runs to
the R2 pool while hd's 9 runs are still competing, keeping peak concurrent R2 ≤ 24.

**Wave structure (revised):**
1. hd R2 runs alone until done (ETA 2026-05-21 07:00).
2. Immediately after hd R2: launch hw + id (18 runs, --skip-sim).
   Simultaneously: start f9-4a simulation (3 runs).
3. ~5h later (f9-4a sim done): start f9-4b simulation (3 runs).
   Launch f9-4a into pipeline as soon as its simulation completes.
4. ~5h later (f9-4b sim done): launch f9-4b into pipeline.
5. Peak: hw(9) + id(9) + f9-4a(3) + f9-4b(3) = 24 concurrent R2 runs. (~93h for R2)
6. f9-4c is already running independently.

**Revised ETA (as of 2026-05-20):**
- hd R2 done:             ~2026-05-21 07:00 → trigger step 2
- hw+id+f9-4a+4b in R2:  ~2026-05-21 12:00 (after deploy ~2h + sim ~5h)
- All 24 R2 done:         ~2026-05-25 09:00 (+~93h from 2026-05-21 12:00)
- All 24 training done:   ~2026-05-25 22:00 (+6h approx; staggered by sigma)
- All 24 val+SASCA done:  ~2026-05-26 10:00 (+12h approx)
- f9-4c done:             ~2026-05-22 01:00 (already running, unaffected)
- **All 36 runs complete: ~2026-05-26** (vs ~2026-05-31 in previous plan — **5 days saved**)

hd training and val/SASCA run in the background while hw/id/f9 are in R2; hd completes
~2026-05-21 13:00 unaffected (hd R2 is already done before hw/id enter).

---

## Batches

### Batch 1 — hd ✅ RUNNING
- Env dir: `envs/paperscale_v2_hd_sigma_sweep/` (9 envs)
- Traces: present → `--skip-sim`
- Status: in detection R2 as of 2026-05-20 (~68% done, ETA 2026-05-21 07:00)
- **Trigger for next step:** when all 9 hd logs show `DONE : 0002 detection R2`

### Batch 2+3 — hw + id simultaneously
Trigger: all 9 hd sandboxes show `DONE : 0002 detection R2` (not full training done).
- Traces: present for both → `--skip-sim`
- Commands (run both back-to-back; they start near-simultaneously):
  ```sh
  sh run_sandboxes.sh --envs-dir envs/paperscale_v2_hw_sigma_sweep --ssh IDP -- --skip-sim
  sh run_sandboxes.sh --envs-dir envs/paperscale_v2_id_sigma_sweep --ssh IDP -- --skip-sim
  ```
- Monitor: confirm all 18 new sandboxes appear and show `[MOVE : DN]` in logs.

### Batch 4 — f9 (sub-batches, simulation required)
No existing traces. Launch 3 envs at a time to cap concurrent disk writes.

**4a — low noise (sigma 0.1, 0.5, 1.0):**
Start simulation at the same time as hw+id launch (simulation uses different resources).
```sh
mkdir -p /tmp/f9_batch_4a
cp envs/paperscale_v2_f9_sigma_sweep/.env_paperscale_v2_f9_sigma{0p1,0p5,1p0} /tmp/f9_batch_4a/
sh run_sandboxes.sh --envs-dir /tmp/f9_batch_4a --ssh IDP
```

**4b — mid noise (sigma 1.5, 2.0, 2.5):**
Launch when 4a simulation completes (watch for `[MOVE : DN]` in 4a logs — at that point
simulation+deploy is done and 4a is in detection; 4b simulation can then start).
```sh
mkdir -p /tmp/f9_batch_4b
cp envs/paperscale_v2_f9_sigma_sweep/.env_paperscale_v2_f9_sigma{1p5,2p0,2p5} /tmp/f9_batch_4b/
sh run_sandboxes.sh --envs-dir /tmp/f9_batch_4b --ssh IDP
```

**4c — high noise (sigma 3.0, 3.5, 4.0):** ✅ ALREADY RUNNING
Launched 2026-05-18 from `envs/smoke_v2_f9_missing/` — confirmed byte-for-byte identical
to `envs/paperscale_v2_f9_sigma_sweep/` for these three sigmas. Sandboxes:
`Projects_SHA3_sandbox_paperscale_v2_f9_sigma{3p0,3p5,4p0}`. Traces were re-simulated
as part of this launch (no pre-existing traces).
Archive with label `paperscale_v2_f9_sigma{3p0,3p5,4p0}` when complete.

---

## Progress Tracking

Check log tails on remote to gauge phase progress:
```sh
ssh IDP "for log in /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v2_*/project_SHA3-32bit/pipeline_runner/sandbox_*.log; do echo \"=== \$log ===\"; tail -2 \"\$log\" 2>/dev/null; done"
```

Or per-mode:
```sh
ssh IDP "tail -1 /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v2_hd_sigma*/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null"
```

Check if hd has cleared R2 (trigger for hw+id+f9 launch):
```sh
ssh IDP "grep -c 'DONE.*0002 detection R2' /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v2_hd_sigma*/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null"
# → 9 lines of ':1' means all 9 hd runs cleared R2
```

Key log markers:
- `[MOVE : DN]` — detection traces deployed, phase 0002 starting
- `[MOVE : TR]` — training traces deployed, phase 0003 starting
- `DONE : 0002 detection R2` — R2 phase complete (trigger for hw+id+f9 launch)
- `VALIDATION` — phase 0004 starting
- `SASCA` — phase 0005 starting
- `DONE` — run complete; archive with `archive_run.sh`

---

## Status

- [x] hd/hw/id traces present and correct (100 DN + 400 TR per run)
- [x] f9 traces deleted (incomplete TR from previous attempt)
- [x] All norm envs deleted
- [x] All 36 old sandbox dirs deleted
- [x] Batch 1 (hd): launched 2026-05-18, in detection R2 as of 2026-05-20 (~68% done, ETA R2 done 2026-05-21 07:00)
- [ ] Batch 2+3 (hw+id): pending — launch when hd clears R2 (~2026-05-21 07:00)
- [ ] Batch 4a (f9 low noise): pending — launch simultaneously with hw+id (sim runs alongside)
- [ ] Batch 4b (f9 mid noise): pending — launch when 4a simulation completes (~5h after 4a start)
- [x] Batch 4c (f9 high noise): running — launched 2026-05-18 via smoke_v2_f9_missing envs (identical to plan), ETA 2026-05-22 01:00
