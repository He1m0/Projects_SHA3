# Pipeline Run Log

Tracks sigma sweep runs and notable smoke runs.
Update this file whenever a batch launches, finishes, or gets archived.

Log markers: `[MOVE : DN]` = detection done, `[MOVE : TR]` = training started,
`VALIDATION` = phase 0004, `SASCA` = phase 0005, `DONE` = complete.

---

## Status snapshot — 2026-06-02 ~09:10

| Batch | # Runs | State | Notes |
|-------|--------|-------|-------|
| Midscale v1 (all σ) | 36 | **ARCHIVED** | All 36 archived locally under `runs_archive/midscale_v1/`; f9 σ=4.0 completed 2026-05-31 18:04, archived 2026-06-01 |
| Smoke v3 ICS sweep | 36 | **ARCHIVED** | All 36 archived under `runs_archive/smoke_v3/` |
| Smoke v4 SASCA re-run | 36 | **ARCHIVED** | All 36 archived under `runs_archive/smoke_v4/` |
| Paperscale v3 σ=4.0 hd | 1 | **SASCA running** | Depths at traces 445/673/674; slowest (4R) 44.5%; ETA ~25h (~Jun 3 10:00) |
| Paperscale v3 σ=4.0 hw | 1 | **SASCA running** | Trace 741/1000 (74.1%); ETA ~31h (~Jun 3 16:00) |
| Paperscale v3 σ=4.0 id | 1 | **ARCHIVED** | COMPLETE 2026-06-01 08:58; archived locally |
| Paperscale v3 σ=4.0 f9 | 1 | **SASCA running** | fix run at trace 335/1000 (2R depth); ~9 tr/hr (same as sigma3p5); ETA ~Jun 5; fix log: `paperscale_v3_f9_sigma4p0.log`; ICS=30. Premature archive deleted (--status false-positive: detected 0004 COMPLETE, not full 0005). Re-archive with --force when done. |
| Paperscale v3 σ=3.5 hd | 1 | **SASCA running** | Trace 707/1000 (70.7%); ETA ~13h (~Jun 2 22:00) |
| Paperscale v3 σ=3.5 hw | 1 | **SASCA running** | Trace 715/1000 (71.5%); ETA ~34h (~Jun 3 19:00) |
| Paperscale v3 σ=3.5 id | 1 | **ARCHIVED** | COMPLETE 2026-06-01 09:09; archived locally |
| Paperscale v3 σ=3.5 f9 | 1 | **SASCA running** | fix run at trace 335/1000 (33.5%); ~9 tr/hr; ETA ~74h (~Jun 5 11:00); fix log: `paperscale_v3_f9_sigma3p5.log`; ICS=40 |
| Paperscale v3 σ=3.0 hd | 1 | **SASCA running** | Depths at traces 315/419/623; slowest (4R) 31.5%; long ETA (~Jun 5–6) |
| Paperscale v3 σ=3.0 hw | 1 | **SASCA running** | Depths at traces 336/451/673; slowest (4R) 33.6%; long ETA (~Jun 6) |
| Paperscale v3 σ=3.0 id | 1 | **ARCHIVED** | COMPLETE 2026-06-01 09:49; archived locally |
| Paperscale v3 σ=3.0 f9 | 1 | **SASCA running** | fix run at trace 195/1000 (19.5%); ~3 tr/hr (ICS=60 heavy); ETA 10+ days; fix log: `paperscale_v3_f9_sigma3p0.log` |
| Paperscale v3 σ=2.0–2.5 (all modes) | 8 | **R2 detection** | All 8 in linear regression as of 09:00 Jun 2; R2=8–9 (at cap); ETA ~1–2 more days |
| Paperscale v3 σ=0.1–1.5 | 16 | **Queued — auto-relaunch** | Monitor stuck at R2=8 since midnight; waiting for ≤6 to launch sigma1p5; hd/hw/id 0p1–1p5 sims done (SIM:DN May31), f9 0p1–1p5 need sandboxes |
| Reference (Cambridge) | 1 | **ARCHIVED** | `runs_archive/reference/2026-04-24_ref_original_paper/`; 50 PPC |

**In-flight safety cap:** `R2 + KeccakSim ≤ 6` before each 4-run batch launch guarantees peak R2 ≤ 10 (system limit). Monitor at `/tmp/paperscale_relaunch_monitor.sh`, log at `/tmp/paperscale_monitor.log`.

**Note on ETA estimates (2026-06-02):**
- Rate observations: hd high-sigma runs ~22 tr/hr (few ICS samples); hw all sigma and hd sigma3p0 ~8 tr/hr; f9 sigma3p5 fix ~9 tr/hr; f9 sigma3p0 fix ~3 tr/hr (ICS=60).
- 4R depth is always slowest and gates completion for multi-depth runs. Reported trace counts are the slowest depth unless labeled otherwise.
- f9 sigma3p0 fix is the long-tail bottleneck for paperscale v3 completion.

**ICS level rationale (clarified 2026-06-02):**
The level numbering maps directly to the R² threshold: level N = r² > N/1000.
Higher level = stricter threshold = FEWER ICS samples. The goal is the **highest** level
that passes `check_ics_archive.py` (no empty arrays). Lower level → more samples → slower SASCA.

| Scale | σ≤2.5 | σ=3.0 | σ=3.5 | σ=4.0 | Notes |
|-------|-------|-------|-------|-------|-------|
| Smoke v3 | 90 (all modes) | 90 (hd/hw/id), **70** (f9) | 90 (hd/hw/id), **60** (f9) | 90 (hd/hw/id), **50** (f9) | f9 bottleneck at smoke scale; env files fixed 2026-06-02 |
| Midscale v1 | 90 | 70 (all modes) | 50 | 40 | f9 was bottleneck; others matched |
| Paperscale v3 | 90 | **60** (all modes) | **40** | **30** | Single level per sigma = f9 bottleneck; hd/hw/id could support one step higher but id already archived at these levels — not restarted |

Paperscale uses one level lower than midscale at high sigma because fresh paperscale traces yield
slightly different R² boundaries. This is a minor cross-scale ICS discrepancy, not a design error.
Within each scale, all 4 modes use the same level per sigma for consistency.

**Log file note — ICS fix runs:** When `--fix-ics` is applied, the repair re-run logs to a separate file
`pipeline_runner/paperscale_v3_{mode}_sigma{X}.log` (without `sandbox_` prefix) rather than appending
to the original `sandbox_paperscale_v3_{mode}_sigma{X}.log`. The original sandbox log ends with the
ICS error from the initial (now-superseded) run — **this is expected and not a failure**. Use the fix log
for current status. `--status` now auto-detects and prefers the fix log when present.

**Tooling change 2026-05-27:** `sigma_sweep_compare.py` fixed — SASCA N_TRACES is now
auto-detected per archive (was hardcoded 50, giving 6× inflated AUC for midscale). Rate-scan
grid plot also fixed to use actual curve length instead of hardcoded 21 points. Archive-root
mode patterns now derived from root basename, so `--archive-root midscale_v1` works without
any edits.

**ICS fix 2026-05-31 — paperscale f9 σ=3.0/3.5/4.0:**
Post-detection ICS scan on paperscale sandboxes revealed different boundaries than midscale
(fresh traces, different noise draws → borderline words flip). Corrected levels (via
`launch_paperscale_v3.sh --fix-ics`):

| Run | Midscale level | Paperscale level | Notes |
|-----|----------------|------------------|-------|
| f9 σ=4.0 | 40 | **30** | Level 40 had 1 empty entry at paperscale |
| f9 σ=3.5 | 50 | **40** | Level 50 had 1 empty entry at paperscale |
| f9 σ=3.0 | 70 | **60** | Level 70 had 2 empty entries at paperscale |

hd/hw/id are unaffected (all levels pass for them). Note: hd/hw/id σ=4.0 used level 40,
σ=3.5 used level 50 — one step above the f9 bottleneck — accepted, not re-run.

Also fixed a pack.sh octal bug that caused `templateLDA_O030/040.zip` to be named `O024/O032.zip`
(leading-zero TEMPLATE_TAG values were interpreted as octal by printf). Re-packed correctly
using `launch_paperscale_v3.sh --fix-ics` (stores plain integers) + re-ran `sh pack.sh`.

---

## Midscale v1 Sigma Sweep — IN PROGRESS / COMPLETE (36 runs — 4 modes × 9 sigmas)

Scale: 30 det sets, 200 TR sets, 20 val sets, 300 SASCA traces.
Env dir: `envs/midscale_v1_sigma_sweep/sigma{X}/` (per-sigma-slice, 4 modes per slice).
Sandbox naming: `midscale_v1_{mode}_sigma{X}`.

Trace reuse:
- hd/hw/id all sigmas: `--skip-sim`, TRACES_DIR=`/storage/ge96pug/traces_paperscale_v2_{mode}_sigma{X}`
- f9 σ=3.0/3.5/4.0: `--skip-sim`, TRACES_DIR=`/storage/ge96pug/traces_paperscale_v2_f9_sigma{X}` (TR=400 ✓)
- f9 σ=0.1/0.5/1.0: simulate (TR killed at 4–6 sets in crash), TRACES_DIR=`/storage/ge96pug/traces_midscale_v1_f9_sigma{X}`
- f9 σ=1.5/2.0/2.5: simulate (no traces exist), TRACES_DIR=`/storage/ge96pug/traces_midscale_v1_f9_sigma{X}`

**NOTE:** `traces_paperscale_v2_*` dirs are now gone from IDP. Midscale sandboxes deployed those
traces into their own Raw/ subdirs before deletion, so midscale pipeline state is intact.

Concurrency: safe cap ≤24 concurrent R2 (midscale ~10 GB commit/process vs paperscale ~33 GB).

**ICS level fix round 1 — f9 σ=3.0/3.5/4.0 (2026-05-23):**
High-noise f9 runs found no ICS at threshold 90. Fixed to ICS=50 and restarted.

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

Fix sessions launched 2026-05-25 ~11:26–11:34. f9 σ=3.5 at level 50 already correct — no fix; ran SASCA in original session.

**Also discovered (2026-05-26): pack.sh octal bug.**
`printf '%03d' "070"` interprets `070` as octal 56, creating wrong zip names (O056 / O032).
Affected f9 σ=3.0 and σ=4.0. Fix: `$((10#${var}))` forces decimal interpretation.
All ICS tag env vars now stored as plain integers (no leading zeros). Committed e7b1e67.

**Final ICS levels (midscale v1, per-sigma standard):**

| Sigma | hd | hw | id | f9 |
|-------|----|----|----|----|
| 0.1–2.5 | 90 | 90 | 90 | 90 |
| 3.0 | 70 | 70 | 70 | 70 |
| 3.5 | 50 | 50 | 50 | 50 |
| 4.0 | 40 | 40 | 40 | 40 |

**Status as of 2026-05-26 ~16:20:**

| Run | Status |
|-----|--------|
| σ=0.1–2.5, all 4 modes (24 runs) | **COMPLETE** |
| f9 σ=3.5 (original session, ICS=50) | **COMPLETE** |
| id σ=3.0, id σ=3.5, id σ=4.0 | **COMPLETE** (2026-05-24 20:03, 22:25, RECOVERY) |
| hd σ=3.0, hd σ=3.5, hd σ=4.0 | **SASCA running** (fix_hd_sigma*.log, last ~16:19) |
| hw σ=3.0, hw σ=3.5, hw σ=4.0 | **SASCA running** (fix_hw_sigma*.log, last ~16:20) |
| f9 σ=3.0, f9 σ=3.5, f9 σ=4.0 | **SASCA running** (fix_f9_sigma*.log, last ~16:20) |

Expected COMPLETE: ~2026-05-27 morning.

**Archive:** pending all 9 remaining SASCA sessions completing.
```sh
# Verify all 36 complete
ssh IDP "for mode in hd hw id f9; do for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
  sb=/storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_\${mode}_sigma\${sig}/project_SHA3-32bit
  log=\$(ls \"\$sb/pipeline_runner/fix_\${mode}_sigma\${sig}.log\" 2>/dev/null || \
         ls \"\$sb/pipeline_runner/sandbox_midscale_v1_\${mode}_sigma\${sig}.log\" 2>/dev/null)
  complete=\$(grep -c 'COMPLETE\|overnight chain finished' \"\$log\" 2>/dev/null || echo 0)
  echo \"\${mode}_sigma\${sig}: \$complete\"
done; done"
```

---

## Smoke v4 SASCA Re-Run — IN PROGRESS (36 runs — SASCA phase only)

**Purpose:** Achieve cross-scale AUC comparability. Smoke v3 used 21 rate-scan points × 64
bits = max 1280 oracle bits, while midscale/paperscale/reference use 201 × 8 = max 1600 bits.
The near-zero-oracle cliff (≈1400–1600 bits) is not sampled by smoke v3, causing its AUC to
systematically overestimate vs all other scales. Smoke v4 re-uses the same trained templates
from smoke v3 sandboxes and only re-runs phase 0005 with the corrected rate-scan parameters.

Scale: identical to smoke v3 (10 det sets, 50 TR sets, 20 val sets, 50 SASCA traces).
Rate-scan params: **SHA3_SASCA_RATE_POINT_COUNT=201, SHA3_SASCA_RATE_STEP_BITS=8** (matching midscale / paperscale / reference).
Sandbox naming: reuses `smoke_v3_{mode}_sigma{X}` sandboxes on IDP (sandboxes intact).
Env files: `envs/smoke_v4_201pt/.env_smoke_v4_{mode}_sigma{X}` (36 files; local only, for reference).

**How it was launched (2026-05-27 ~16:13):**
1. Verified all 36 smoke_v3 sandbox `0004_validation/` directories still exist on IDP.
2. Updated `.env` in all 36 sandboxes in-place: `SHA3_SASCA_RATE_POINT_COUNT=201` and `SHA3_SASCA_RATE_STEP_BITS=8`.
3. Launched `run_0005_chain.sh` in all 36 sandboxes in parallel via `nohup ... &`.
4. Logs writing to `pipeline_runner/sasca_v4_rerun.log` per sandbox.

**Archived 2026-05-28** — all 36 archived on IDP and synced to `runs_archive/smoke_v4/` (~168 MB, 36 dirs).
Archive names: `2026-05-28_smoke_v4_{mode}_sigma{X}`.

**Completion check:**
```sh
ssh IDP "for mode in hd hw id f9; do for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
  log=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v3_\${mode}_sigma\${sig}/project_SHA3-32bit/pipeline_runner/sasca_v4_rerun.log
  done=\$(grep -c 'SASCA.*done\|Step 5.*complete\|run_0005.*finished\|COMPLETE' \"\$log\" 2>/dev/null || echo 0)
  echo \"\${mode}_sigma\${sig}: \$done\"
done; done"
```

---

## Smoke v3 ICS Sensitivity Sweep — COMPLETE (36 runs — 4 modes × 9 sigmas)

**Purpose:** Compare ICS level 10 (existing smoke v2 archives) vs per-sigma standard at smoke scale.
Scale: 10 det sets, 50 TR sets, 20 val sets, 50 SASCA traces.
Env dir: `envs/smoke_v3_ics_sweep/sigma{X}/`. Sandbox naming: `smoke_v3_{mode}_sigma{X}`.

All 36 sessions launched 2026-05-25 ~11:37–12:03. All simulate fresh into `traces_smoke_v3_{mode}_sigma{X}/`.

**Completion status:** All 36 complete and archived 2026-05-26.
- 33/36: `COMPLETE: run_full_pipeline finished` (hd/hw/id all 9σ + f9 σ=0.1–2.5)
- 3/36: `overnight chain finished` — f9 σ=3.0, σ=3.5, σ=4.0 (completed ~14:11–14:13 2026-05-26)
- **All 36 archived locally**: `runs_archive/2026-05-26_smoke_v3_*` (~238 MB, 36 dirs)

**Why f9 high-sigma were via overnight chain:**
Env files had placeholder ICS level 90, but smoke scale (10 det sets) can't support level 90 for
high-noise f9. Pipeline exited at check_ics_archive.py validation. After finding correct levels:

| Run | Max valid ICS level (smoke scale) | Midscale reference |
|-----|-----------------------------------|--------------------|
| f9 σ=3.0 | **70** | 70 (same) |
| f9 σ=3.5 | **60** | 50 (smoke higher — noisy R²) |
| f9 σ=4.0 | **50** | 40 (smoke higher — noisy R²) |

Smoke scale (10 det sets) → noisy R² estimates → inflated apparent max valid level vs midscale.
Smoke results at σ=3.5/4.0 trained at different ICS level than midscale — not directly comparable.
See `findings_2026-05-26.md` for full analysis.

**Archive:** Ready to archive all 36. Run after midscale is also archived.
```sh
# Overnight chain runs also archivable — key outputs (0004 quality_report, 0005 SASCA) are complete
for mode in hd hw id f9; do for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
  sb=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v3_${mode}_sigma${sig}/project_SHA3-32bit
  sh pipeline_runner/archive_run.sh \
    --name smoke_v3_${mode}_sigma${sig} \
    --env-file .env
done; done
```

---

## Paperscale v3 Sigma Sweep — IN PROGRESS (36 runs — 4 modes × 9 sigmas)

Scale: 100 det sets, 400 TR sets, 40 val sets, 1000 SASCA traces. R2 commit ~33 GB/process.
Env dir: `envs/paperscale_v3_sigma_sweep/sigma{X}/`. Sandbox: `paperscale_v3_{mode}_sigma{X}`.
Launcher: `launch_paperscale_v3.sh`.

**All 36 runs need fresh simulation** (paperscale_v2 trace dirs gone from IDP).
TRACES_DIR: `/storage/ge96pug/traces_paperscale_v3_{mode}_sigma{X}` (fresh per run).
ICS tags in env files stored as plain integers (no leading zeros) to avoid octal printf bug.

ICS levels (verified on paperscale sandboxes 2026-05-31):

| Sigma | hd/hw/id level | f9 level | Notes |
|-------|----------------|----------|-------|
| 0.1–2.5 | 90 | 90 | All modes stable |
| 3.0 | 70 | **60** | f9 bottleneck; 70 fails (2 empty) at paperscale |
| 3.5 | 50 | **40** | f9 bottleneck; 50 fails (1 empty) at paperscale |
| 4.0 | 40 | **30** | f9 bottleneck; 40 fails (1 empty) at paperscale |

Note: hd/hw/id σ=4.0/3.5 already ran at their levels (40/50) and are in SASCA.
Levels are one step above the f9 bottleneck — accepted inconsistency, no re-run.

**Sigma-first launch order** (high-to-low: high sigma = primary scientific question = scale effect on noise):

| Priority | Sigma dir | Command | Pre-check |
|----------|-----------|---------|-----------|
| 1 | sigma4p0 | `run_sandboxes.sh --envs-dir sigma4p0/ --ssh IDP` | none |
| 2 | sigma3p5 | same with sigma3p5 | ✅ Launched 2026-05-26 ~22:00 (R2=4 at launch) |
| 3 | sigma3p0 | same with sigma3p0 | ✅ Launched 2026-05-27 (time unknown) |
| 4 | sigma2p5 | same | **≤6** |
| 5 | sigma2p0 | same | **≤6** |
| 6 | sigma1p5 | same | **≤6** |
| 7–9 | sigma1p0/0p5/0p1 | as slots free | **≤6** each |

**Post-detection ICS check (σ≥3.0, mandatory before training starts):**
The midscale and smoke ICS scans are already done (those established the per-sigma standard).
This is a different check: verifying whether paperscale's 100 det sets support a *higher* level
than the midscale-derived placeholder. Stronger R² signal at paperscale may unlock level 50+ for
σ=4.0 (vs placeholder 40). Run after each σ≥3.0 batch hits [MOVE:DN]:
```sh
sh launch_paperscale_v3.sh --ics-scan          # after [MOVE:DN] in σ≥3.0 runs (~2026-05-27 12:00–20:00 for sigma4p0)
sh launch_paperscale_v3.sh --fix-ics f9 4p0 50 # example: if level 50 passes at paperscale
```

**R2 cap: ≤10 concurrent** (~33 GB commit/process; CommitLimit=511 GB with overcommit_ratio=50,
overhead ~59 GB → safe at 80%: floor((511×0.80−59)/33)=10. Old cap of ≤18 was based on
CommitLimit~940 GB and is now dangerously wrong — 18×33+59=653 GB > 511 GB would OOM.)
Check before each sigma batch: `ssh IDP 'pgrep -c -f detect_script'` must be **≤6**
(so that adding 4 new runs peaks at ≤10).

**CRITICAL — simulation stagger is NOT a safe assumption:** All runs launched simultaneously
simulate the same amount of data and complete at the same time → all hit R2 simultaneously.
Launch at most one sigma batch (4 runs) at a time. Wait for R2 count ≤6 before next batch.

**Run status:**

| Sigma | hd | hw | id | f9 | Launched |
|-------|----|----|----|----|----------|
| 4p0 | R2 (LR-3 @ 17:35) | R2 (LR-2 @ 17:35) | R2 (LR-0 @ 17:36) | R2 (LR-3 @ 17:36) | 2026-05-26 |
| 3p5 | R2 (LR-2 @ 17:35) | R2 (LR-2 @ 17:36) | R2 (LR-3 @ 17:35) | R2 (LR-0 @ 17:35) | 2026-05-26 ~22:00 |
| 3p0 | R2 (LR-2 @ 17:36) | R2 (LR-0 @ 17:36) | R2 (LR-2 @ 17:36) | Simulating TR (log stale @ 12:28) | 2026-05-27 (time unknown) |
| 2p5–0p1 | not started | — | — | — | — |

---

## Paperscale v2 Sigma Sweep — FROZEN (OOM crash 2026-05-21)

**All processes killed by OOM at 2026-05-21 10:41–10:51.** Root cause: 28 concurrent R2
processes committed ~33 GB virtual each, exceeding ~940 GB overcommit limit.
Frozen state preserved on IDP but superseded by paperscale v3.

`traces_paperscale_v2_hd/hw/id_*` trace dirs have been deleted from IDP (only sandbox Raw/ remains).
Frozen paperscale_v2 sandboxes are still on IDP but will NOT be resumed.

---

## Smoke v2 (completed pilot runs, archived)

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

### smoke_v2_f9 high noise — f9 mode, σ=3.0/3.5/4.0

| Run | Finished | Archive |
|-----|----------|---------|
| f9 σ=3.0 | 2026-05-19 20:00 | 2026-05-20_paperscale_v2_f9_sigma3p0 |
| f9 σ=3.5 | 2026-05-19 23:24 | 2026-05-20_paperscale_v2_f9_sigma3p5 |
| f9 σ=4.0 | 2026-05-19 20:55 | 2026-05-20_paperscale_v2_f9_sigma4p0 |

---

## Quick status check commands

```sh
# Midscale fix run completion (check fix logs first, fall back to orig)
ssh IDP "for mode in hd hw id f9; do for sig in 3p0 3p5 4p0; do
  sb=/storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_\${mode}_sigma\${sig}/project_SHA3-32bit
  log=\"\$sb/pipeline_runner/fix_\${mode}_sigma\${sig}.log\"
  [ -f \"\$log\" ] || log=\"\$sb/pipeline_runner/sandbox_midscale_v1_\${mode}_sigma\${sig}.log\"
  complete=\$(grep -c 'COMPLETE\|overnight chain finished' \"\$log\" 2>/dev/null | tr -d ' ')
  echo \"\${mode}_sigma\${sig}: \$complete\"
done; done"

# Smoke v3 — all 36 done check
ssh IDP "grep -l 'COMPLETE\|overnight chain finished' \
  /storage/ge96pug/Projects_SHA3_sandbox_smoke_v3_*/project_SHA3-32bit/pipeline_runner/sandbox_*.log \
  2>/dev/null | wc -l"

# Paperscale v3 overview
sh pipeline_runner/launch_paperscale_v3.sh --status

# R2 process count (cap: ≤10 for paperscale; launch only if ≤6)
ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0"
```
