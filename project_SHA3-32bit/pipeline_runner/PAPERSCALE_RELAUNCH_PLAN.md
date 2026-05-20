# Paperscale Sigma Sweep — Gradual Relaunch Plan

## Context

36 paperscale runs across 4 leakage modes (hd, hw, id, f9) × 9 sigma values (0.1–4.0).
Previous attempts were killed (potential OOM / disk pressure) before producing any pipeline output.

**Resource envelope:**
- Remote: 192 cores, ~940 GiB RAM (essentially idle), 3.5 TB free on /storage
- Each trace dir: ~36 GB. hd/hw/id traces already complete (27 × 36 GB = ~972 GB used).
- f9 traces deleted; need re-simulation (~9 × 36 GB = ~324 GB additional).
- Pipeline intermediates per run (HDF5 zips, templateLDA): ~10–30 GB each.

**OOM risk:** Detection phase loads 25-set parts × 4,000 traces × 55,296 samples × 8 B
≈ 1.7 GB/part per run. With 9 runs in detection simultaneously that is ~15 GB peak.
Staggering modes ensures at most ~9 runs are in the heavy detection+training phase at once.

---

## Strategy

Launch in three waves: hd first, then hw+id simultaneously, then f9 sub-batches.
For hd/hw/id, use `--skip-sim` (traces already present).
For f9, no existing traces — simulate in **sub-batches of 3** to cap concurrent disk writes
and simulation RAM.

hw and id are safe to overlap: both use `--skip-sim` (no simulation disk contention) and
192 cores / 940 GiB RAM absorbs 18 concurrent detection runs comfortably. Measured OOM risk
with 18 runs in detection is ~30 GB peak — negligible on this machine.

Wait for hd to fully clear detection+training before launching hw+id (avoids 27-way CPU
contention in the R2 correlation sweep). Estimated slowdown from 18 concurrent runs vs 9:
~1.4×; R2 takes ~82h for hw+id vs ~40h for hd alone.

**Rough ETA (as of 2026-05-20):**
- Batch 1 (hd) done:       ~2026-05-21 13:00 → launch hw+id
- Batch 2+3 (hw+id) done:  ~2026-05-25 06:00 → launch f9 4a
- Batch 4a (f9 low) done:  ~2026-05-28 08:00 → launch f9 4b
- Batch 4b (f9 mid) done:  ~2026-05-31 10:00 ← **all 36 runs complete**
(f9 4c already running alongside hd; finishes ~2026-05-22 01:00)

---

## Batches

### Batch 1 — hd (launch now)
- Env dir: `envs/paperscale_v2_hd_sigma_sweep/` (9 envs)
- Traces: present → `--skip-sim`
- Command (from `project_SHA3-32bit/pipeline_runner/`):
  ```sh
  sh run_sandboxes.sh --envs-dir envs/paperscale_v2_hd_sigma_sweep --ssh IDP -- --skip-sim
  ```
- Monitor: check all 9 tmux sessions have progressed past `[MOVE : DN]` log entry.

### Batch 2+3 — hw + id simultaneously (after hd clears detection+training)
- Launch both immediately when all 9 hd sandboxes show `DONE : 0003 training` in their logs.
- Traces: present for both → `--skip-sim`
- Commands (run both, one after the other — they start near-simultaneously):
  ```sh
  sh run_sandboxes.sh --envs-dir envs/paperscale_v2_hw_sigma_sweep --ssh IDP -- --skip-sim
  sh run_sandboxes.sh --envs-dir envs/paperscale_v2_id_sigma_sweep --ssh IDP -- --skip-sim
  ```
- Monitor: confirm all 18 new sandboxes appear and show `[MOVE : DN]` in their logs.

### Batch 4 — f9 (sub-batches, simulation required)
No existing traces. Launch 3 envs at a time; wait for each sub-batch simulation to complete
before launching the next (watch for `[MOVE : TR]` in logs).

**4a — low noise (sigma 0.1, 0.5, 1.0):**
```sh
mkdir -p /tmp/f9_batch_4a
cp envs/paperscale_v2_f9_sigma_sweep/.env_paperscale_v2_f9_sigma{0p1,0p5,1p0} /tmp/f9_batch_4a/
sh run_sandboxes.sh --envs-dir /tmp/f9_batch_4a --ssh IDP
```

**4b — mid noise (sigma 1.5, 2.0, 2.5):**
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
ssh IDP "for log in /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v2_*/ \
  project_SHA3-32bit/pipeline_runner/sandbox_*.log; do \
  echo \"=== \$log ===\"; tail -2 \"\$log\" 2>/dev/null; done"
```

Or per-mode:
```sh
ssh IDP "tail -1 /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v2_hd_sigma*/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null"
```

Key log markers:
- `[MOVE : DN]` — detection traces deployed, phase 0002 starting
- `[MOVE : TR]` — training traces deployed, phase 0003 starting
- `VALIDATION` — phase 0004 starting
- `SASCA` — phase 0005 starting
- `DONE` — run complete; archive with `archive_run.sh`

---

## Status

- [x] hd/hw/id traces present and correct (100 DN + 400 TR per run)
- [x] f9 traces deleted (incomplete TR from previous attempt)
- [x] All norm envs deleted
- [x] All 36 old sandbox dirs deleted
- [x] hd/hw/id traces present and correct (100 DN + 400 TR per run)
- [x] f9 traces deleted (incomplete TR from previous attempt)
- [x] All norm envs deleted
- [x] All 36 old sandbox dirs deleted
- [x] Batch 1 (hd): launched 2026-05-18, in detection R2 as of 2026-05-20 (~68% done, ETA 2026-05-21 07:00)
- [ ] Batch 2+3 (hw+id): pending — launch simultaneously when hd clears training (~2026-05-21 13:00)
- [ ] Batch 4a (f9 low noise): pending — launch when hw+id clear training (~2026-05-25 06:00)
- [ ] Batch 4b (f9 mid noise): pending — launch when 4a clears training (~2026-05-28 08:00)
- [x] Batch 4c (f9 high noise): running — launched 2026-05-18 via smoke_v2_f9_missing envs (identical to plan), ETA 2026-05-22 01:00
