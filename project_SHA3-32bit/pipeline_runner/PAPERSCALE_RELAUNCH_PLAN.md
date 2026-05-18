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

Launch **one mode at a time**, in order: hd → hw → id → f9.
For hd/hw/id, use `--skip-sim` (traces already present).
For f9, no existing traces — simulate in **sub-batches of 3** to cap concurrent disk writes
and simulation RAM.

Wait for each batch to clear detection+training (phases 0002+0003) before launching the next.
Estimated time to clear detection+training at paperscale: ~3–6 hours per run.

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

### Batch 2 — hw (after hd clears detection+training)
- Env dir: `envs/paperscale_v2_hw_sigma_sweep/` (9 envs)
- Traces: present → `--skip-sim`
- Command:
  ```sh
  sh run_sandboxes.sh --envs-dir envs/paperscale_v2_hw_sigma_sweep --ssh IDP -- --skip-sim
  ```

### Batch 3 — id (after hw clears detection+training)
- Env dir: `envs/paperscale_v2_id_sigma_sweep/` (9 envs)
- Traces: present → `--skip-sim`
- Command:
  ```sh
  sh run_sandboxes.sh --envs-dir envs/paperscale_v2_id_sigma_sweep --ssh IDP -- --skip-sim
  ```

### Batch 4 — f9 (sub-batches, simulation required)
No existing traces. Launch 3 envs at a time; wait for each sub-batch simulation to complete
before launching the next (watch for `[MOVE : TR]` in logs).

**4a — low noise (sigma 0.1, 0.5, 1.0):**
```sh
for sigma in 0p1 0p5 1p0; do
  sh run_sandboxes.sh \
    --envs-dir /dev/stdin --ssh IDP <<< "" 2>/dev/null || true
done
# Or directly:
ssh IDP "cd /storage/ge96pug/Projects_SHA3/project_SHA3-32bit/pipeline_runner && \
  for sigma in 0p1 0p5 1p0; do \
    sh setup_sandbox.sh ... ; done"
```
Simpler: copy the 3 env files to a tmp dir and run run_sandboxes.sh against it:
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

**4c — high noise (sigma 3.0, 3.5, 4.0):**
```sh
mkdir -p /tmp/f9_batch_4c
cp envs/paperscale_v2_f9_sigma_sweep/.env_paperscale_v2_f9_sigma{3p0,3p5,4p0} /tmp/f9_batch_4c --ssh IDP
sh run_sandboxes.sh --envs-dir /tmp/f9_batch_4c --ssh IDP
```

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
- [ ] Batch 1 (hd): **launched**
- [ ] Batch 2 (hw): pending
- [ ] Batch 3 (id): pending
- [ ] Batch 4a (f9 low noise): pending
- [ ] Batch 4b (f9 mid noise): pending
- [ ] Batch 4c (f9 high noise): pending
