# Sigma Sweep Plan — 2026-05-25

Covers: midscale v1 ICS fix + archive, smoke v3 ICS sensitivity sweep, and paperscale v3.
See `findings_2026-05-25.md` (repo root) for the ICS mechanics analysis that motivates this.

---

## ICS Level Rationale

All 9 ICS archives (levels 010–090, R² thresholds 0.01–0.09) are always generated during
detection. `SHA3_TRAINING_ICS_LEVEL` selects which one flows into training. Higher level =
stricter threshold = fewer but higher-quality ICS samples = faster (but potentially weaker)
training.

**Per-sigma standard:** use the highest level that passes `check_ics_archive.py` for ALL
four leakage modes at that sigma (f9 is always the bottleneck). This maximises template
selectivity while ensuring no intermediate value word has empty ICS.

Validation command per sandbox:
```sh
python3 pipeline_runner/check_ics_archive.py \
  --ics-zip 0002_detection/Code_extract_ics/ics_original_{LEVEL:03d}.zip
# OK = passes; ERROR = empty arrays present
```

**CRITICAL:** `run_overnight_chain.sh --with-training` bypasses this check. Always verify
manually before restarting training at a new level, especially for high-sigma f9 runs.

---

## Step 1: Midscale v1 ICS Fix (before archiving)

All 36 midscale detections are done — only training+val+SASCA need to be re-run where
levels are wrong. Can run all in parallel on IDP (~3h wall-clock).

### Mandatory (broken data):

**f9 σ=4.0** — ran at level 50 with ICS check bypassed (9 empty arrays → corrupted templates):
```sh
# IDP: update .env
sed -i \
  -e 's/SHA3_TRAINING_ICS_LEVEL=.*/SHA3_TRAINING_ICS_LEVEL=40/' \
  -e 's/SHA3_VALIDATION_TEMPLATE_TAG=.*/SHA3_VALIDATION_TEMPLATE_TAG=040/' \
  -e 's/SHA3_VALIDATION_ICS_TAG=.*/SHA3_VALIDATION_ICS_TAG=040/' \
  -e 's/SHA3_SASCA_TEMPLATE_TAG=.*/SHA3_SASCA_TEMPLATE_TAG=040/' \
  -e 's/SHA3_SASCA_ICS_TAG=.*/SHA3_SASCA_ICS_TAG=040/' \
  /storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_f9_sigma4p0/project_SHA3-32bit/.env

# IDP: clean + restart training
cd /storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_f9_sigma4p0/project_SHA3-32bit
for d in 0003_training/Code_preprocessing 0003_training/Code_intermediate_values \
          0003_training/Code_find_IoPs 0003_training/template_profiling_bytes; do
  [ -f "$d/clean.sh" ] && sh "$d/clean.sh"
done
tmux new-session -d -s sandbox_midscale_v1_f9_sigma4p0_fix \
  'sh pipeline_runner/run_overnight_chain.sh --with-training \
   2>&1 | tee pipeline_runner/sandbox_midscale_v1_f9_sigma4p0_fix.log'
```

### Recommended (cross-mode consistency, σ=3.0–4.0 slices):

These runs used level 90 (hd/hw/id) or suboptimal 50 (f9 σ=3.0), but should match the
per-sigma standard to make mode comparisons valid within each sigma slice:

| Run | Current level | Target level | Action |
|-----|--------------|--------------|--------|
| f9 σ=3.0 | 50 | **70** | re-run (level 70 passes, 50 is valid but not optimal) |
| hd σ=3.0, hw σ=3.0, id σ=3.0 | 90 | **70** | re-run (level 90 passes for these modes, but must match f9) |
| hd σ=3.5, hw σ=3.5, id σ=3.5 | 90 | **50** | re-run |
| hd σ=4.0, hw σ=4.0, id σ=4.0 | 90 | **40** | re-run |

Same procedure as mandatory fix: update `.env` (5 fields), clean 0003_training subdirs,
restart via `run_overnight_chain.sh --with-training`.

Also update local env files in `envs/midscale_v1_sigma_sweep/sigma{3p0,3p5,4p0}/` to match
and commit (git add -f, same pattern as before).

---

## Step 2: Archive Midscale v1

After all fixes complete (confirm with `grep -c 'COMPLETE' sandbox_*.log`):

```sh
# On IDP: archive each run
for mode in hd hw id f9; do
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_${mode}_sigma${sig}
    cd "$sb/project_SHA3-32bit" && \
    sh pipeline_runner/archive_run.sh \
      --name midscale_v1_${mode}_sigma${sig} \
      --env-file .env \
      --log pipeline_runner/sandbox_midscale_v1_${mode}_sigma${sig}.log
  done
done

# Local: rsync archives back
rsync -av IDP:/storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_*/project_SHA3-32bit/pipeline_runner/runs_archive/ \
  /path/to/local/pipeline_runner/runs_archive/
```

Archive naming: `YYYY-MM-DD_midscale_v1_{mode}_sigma{X}` (date auto-prefixed by archive_run.sh).

Update `RUN_LOG.md` with archive dates and ICS levels used.

---

## Step 3: Smoke v3 ICS Sensitivity Sweep

**Purpose:** Compare attack quality at level 10 (existing smoke v2 archives) vs the
per-sigma maximum valid level (to be found empirically). Reveals whether ICS level
meaningfully affects SR/SASCA AUC at smoke scale.

**Scale:** Same as smoke v2 (DETECTION_SET_COUNT=10, TRAINING_SET_COUNT=50, SASCA_TRACE_COUNT=50).
All traces available via `--skip-sim` — smoke v3 will be very fast (~2–4h total).

### 3a. Env file setup

Create `envs/smoke_v3_ics_sweep/sigma{X}/` with 36 env files (4 modes × 9 sigmas).
Base: copy midscale v1 env files, replace scale parameters:
- DETECTION_SET_COUNT=10, DETECTION_SETS_PER_PART=10
- TRAINING_SET_COUNT=50, TRAINING_SETS_PER_PART=25
- SASCA_TRACE_COUNT=50, SASCA_RATE_POINT_COUNT=21, SASCA_RATE_STEP_BITS=64
- SHA3_TRAINING_ICS_LEVEL=90 (placeholder; will be updated after detection)

TRACES_DIR assignments:
- hd/hw/id all σ: `TRACES_DIR=/storage/ge96pug/traces_paperscale_v2_{mode}_sigma{X}`
- f9 σ=0.1–2.5: `TRACES_DIR=/storage/ge96pug/traces_midscale_v1_f9_sigma{X}`
- f9 σ=3.0–4.0: `TRACES_DIR=/storage/ge96pug/traces_paperscale_v2_f9_sigma{X}`

Sandbox naming: `smoke_v3_{mode}_sigma{X}`

### 3b. Launch (all 36, --skip-sim, all simultaneously)

Smoke R2 commit ~3 GB/process → safe for all 36 concurrent.

```sh
sh run_sandboxes.sh --envs-dir envs/smoke_v3_ics_sweep/sigma0p1 --ssh IDP -- --skip-sim
# ... repeat for all 9 sigma dirs (or use launch script)
```

### 3c. ICS boundary scan (after detection, before training)

After all 36 sandboxes show `[MOVE:DN]` in logs:

```sh
ssh IDP "
for mode in hd hw id f9; do
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v3_\${mode}_sigma\${sig}/project_SHA3-32bit
    echo -n \"\${mode}_sigma\${sig}: \"
    for level in 090 080 070 060 050 040 030 020 010; do
      ok=\$(python3 \"\$sb/pipeline_runner/check_ics_archive.py\" \
        --ics-zip \"\$sb/0002_detection/Code_extract_ics/ics_original_\${level}.zip\" \
        2>&1 | grep -c 'OK:')
      if [ \"\$ok\" -eq 1 ]; then
        echo \"max valid level = \$level\"
        break
      fi
    done
  done
done"
```

For each sigma: note the **highest level that passes for all 4 modes** (f9 bottleneck).
Update `.env` in each sandbox to the standardized level for that sigma. Restart training:
```sh
ssh IDP "tmux send-keys -t sandbox_smoke_v3_{mode}_sigma{X}:0.0 \
  'sh pipeline_runner/run_overnight_chain.sh --with-training' Enter"
```

### 3d. Archive and compare

Archive naming: `smoke_v3_{mode}_sigma{X}`.
Compare:
```sh
python3 compare_runs.py \
  runs_archive/*_smoke_v2_{hd,hw,id,f9}_sigma* \
  runs_archive/*_smoke_v3_{hd,hw,id,f9}_sigma*
```

---

## Step 4: Paperscale v3 Sigma Sweep

Scale: 100 det sets, 400 TR sets, 1000 SASCA traces. R2 commit ~33 GB/process.
**Safe concurrent R2: ≤18** (confirmed limit; 28 killed machine in OOM crash 2026-05-21).

### ICS levels
Start with smoke v3 boundaries as a reference, but **verify after detection**.
Paperscale (100 det sets) has stronger R² signal → may support higher levels than smoke or midscale.
After R2 detection completes for each run, run the ICS boundary scan before starting training.

### Env file setup
`envs/paperscale_v3_sigma_sweep/sigma{X}/` (36 env files, same sigma slices as midscale).
Sandbox naming: `paperscale_v3_{mode}_sigma{X}`.
ICS level in env files: placeholder 90 initially, updated after detection (same as smoke v3).

Paperscale parameters (same as frozen v2):
- DETECTION_SET_COUNT=100, DETECTION_SETS_PER_PART=25
- TRAINING_SET_COUNT=400, TRAINING_SETS_PER_PART=25
- VALIDATION_SET_COUNT=40, SASCA_TRACE_COUNT=1000
- SASCA_RATE_POINT_COUNT=201, SASCA_RATE_STEP_BITS=8

### Trace reuse
- hd/hw/id all σ: `--skip-sim`, `TRACES_DIR=/storage/ge96pug/traces_paperscale_v2_{mode}_sigma{X}`
  (frozen paperscale v2 traces intact on IDP)
- f9 all σ: simulate (`traces_paperscale_v3_f9_sigma{X}` — v2 f9 traces in partial/deleted state)

### Wave structure (R2 concurrency ≤18)

**Wave A:** hd + hw, all 9 sigmas (18 runs, --skip-sim).
Check before launch: `ssh IDP "pgrep -c -f detect_script"` = 0.

**Wave B trigger:** `pgrep -c -f detect_script` ≤ 9.
Launch id, all 9 sigmas (9 runs, --skip-sim).

**f9 simulation:** 3 concurrent max (disk-write cap). Start alongside Wave A.
- Batch 1: σ=0.1/0.5/1.0 → launch into R2 when simulation completes + R2 slots free
- Batch 2: σ=1.5/2.0/2.5 → when batch 1 shows [MOVE:DN]
- Batch 3: σ=3.0/3.5/4.0 → same

f9 R2 trigger: `pgrep -c -f detect_script` ≤ 15 before adding each batch of 3.

### Post-detection ICS check (mandatory)
After detection for each sigma slice, run check before training. For σ≥3.0 slices, scan
all levels to find max valid (same script as smoke v3 §3c). Update env files and confirm
before allowing training to proceed.

### Timing estimate
- R2 at 18 concurrent: ~70–80h (3.3× midscale data × contention factor)
- Training: ~12–15h per run
- Val+SASCA: ~6–8h
- Total: ~4–5 days for R2 + 2 days for training/SASCA

---

## Progress Checklist

- [ ] Midscale f9 σ=4.0: fix at level 40 (mandatory)
- [ ] Midscale f9 σ=3.0: fix at level 70 (recommended)
- [ ] Midscale hd/hw/id σ=3.0: fix at level 70 (recommended)
- [ ] Midscale hd/hw/id σ=3.5: fix at level 50 (recommended)
- [ ] Midscale hd/hw/id σ=4.0: fix at level 40 (recommended)
- [ ] Midscale local env files updated + committed
- [ ] All 36 midscale runs archived
- [ ] RUN_LOG.md updated with midscale archive info
- [ ] Smoke v3 env files created
- [ ] Smoke v3 launched (all 36, --skip-sim)
- [ ] Smoke v3 ICS boundary scan done
- [ ] Smoke v3 training levels updated + training restarted
- [ ] Smoke v3 archived + compare_runs.py comparison done
- [ ] Paperscale v3 env files created
- [ ] Paperscale v3 Wave A launched (hd+hw, 18 runs)
- [ ] Paperscale v3 Wave B triggered (id, 9 runs)
- [ ] Paperscale v3 f9 simulation + R2 batches managed
- [ ] Paperscale v3 ICS check done per sigma slice before training
- [ ] Paperscale v3 archived + final comparison
