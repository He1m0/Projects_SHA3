# HD promotion to main comparison — run log

Tracks the work to switch the thesis's leakage-model comparison from combined
HW+HD additive to **pure HD**, and the supporting `KeccakSim_v3` simulator
refactor. Unlike `RUN_LOG*.md` (gitignored, untracked), this file IS tracked
in git so a different session/device can pick up where this one left off.
Keep it updated as status changes; move to `_old/` once this workstream is
fully wrapped (paperscale pure-HD sweep archived and thesis updated).

## Objective

The thesis's main-sweep tables/figures label a column "HD" that is actually
**combined HW+HD additive** leakage (`SIM_MODE=hw`, `hw_scale=1`,
`hd_add_scale≈0.5–1.0` depending on the run), not pure Hamming Distance. The
real pure-HD-only condition existed as exactly one archived data point
(smoke scale, σ=1.0). Decision: promote **pure HD** to the main comparison
(alongside F9/HW/ID), and move the additive-combination results into the
mixed-mode diagnostics section instead (reusing the already-archived combined
sweeps as-is — no new compute needed there). See
`/home/muri/.claude/plans/check-out-home-muri-documents-uni-idp-pr-agile-cupcake.md`
for the full plan and rationale (DPA-literature framing, why additive
combination isn't standard, etc.).

## Status (updated 2026-07-10 ~13:05)

### Done, committed, pushed (origin/sim-per-leakpoint-pbw)
- `KeccakSim_v3.py` created: adds `hd_scale` as a first-class scale + `mode="hd"`,
  following the same per-component pattern as hw/f9/id (each mode defaults its
  own scale to 1.0, others 0.0, all overridable — combined leakage is just
  passing >1 nonzero scale). `KeccakSim_v2.py` is untouched, still the exact
  reproduction path for any pre-v3 archived run (`SIM_SCRIPT_OVERRIDE=<path>/KeccakSim_v2.py`).
  Verified byte-identical output to v2 for hw/id/hd/combined modes (Python-level
  and CLI-subprocess level).
- `run_full_pipeline.sh`: defaults to v3, canonicalized on one env var
  `SIM_HD_SCALE` (translated to `--hd-scale` for v3 or `--hd-add-scale` for v2
  internally, so env files don't need to know which script runs them).
- `setup_sandbox.sh` / `sync_sandbox.sh`: updated to also deploy `KeccakSim_v3.py`
  to sandboxes (previously only knew about v2/legacy — would have silently
  failed to deploy v3 without this fix).
- `SIM_HD_ADD_SCALE` renamed to `SIM_HD_SCALE` across all env files (~352 files).
  `RUN_LOG_snr_equalized.md` deliberately left with the old name (historical record).
- New `envs/smoke_v7_hd_pure_sigma_sweep/` — 9 env files, σ∈{0.1..4.0}, `mode=hd`.
  ICS level 40 (not the main sweep's 90) carried forward from the original
  σ=1.0 pilot finding — **still needs re-verification per sigma, see below.**
- Env comparability confirmed against current main-sweep HW (`smoke_v4_201pt`)
  and F9 (`smoke_v6_sigma_sweep`): identical trace counts, SASCA iteration
  count (200), rate-scan resolution (201 points, 8-bit step) — only difference
  is the (deliberate) ICS level and mode/scale.
- Noted for later (Part 5, thesis rewrite): the existing "combined HW+HD" data
  (`smoke_v4_201pt/.env_smoke_v4_hd_sigma*`) actually uses `SIM_HD_SCALE=0.5`,
  not `1.0` as the thesis text currently claims — needs correcting when that
  section is rewritten.
- Git housekeeping: found ~317 pre-existing uncommitted files in the working
  tree (unrelated prior-session WIP, including a real `get_corrcoef.py`
  checkpoint/resume fix). Split into two commits (prior-session WIP vs. this
  session's HD/v3 work), rebased onto `origin` after a genuine divergence
  (another commit `6fb3a20` had already landed the same `get_corrcoef.py` fix
  from a different session — rebase resolved cleanly, verified no duplicate
  content). Both commits pushed.

### In progress — smoke_v7 pure-HD sweep, ICS-level verification (Task #6)

**Rationale for checking ICS level per sigma** (user instruction, not yet
resolved): "highest ICS level with non-empty sets" — at low noise (σ=0.1) the
R² statistics may support a much higher ICS level than 40 (maybe close to the
main sweep's 90); at high noise it may need to go lower. The σ=1.0 pilot only
established that level 40 works at σ=1.0 specifically — it was never verified
per-sigma, and hardcoding 40 everywhere would understate pure HD's true
performance at low noise (throwing away usable features) or could fail
outright at high noise if 40 turns out too high there.

**Plan**: detection produces ICS archives at ALL 9 threshold levels
(`SHA3_DETECTION_ICS_THRESHOLDS=0.09,...,0.01` → levels 90..10) in one run,
regardless of what `SHA3_TRAINING_ICS_LEVEL` the env file specifies. So:
1. Phase 1 (DONE): `run_sandboxes.sh --envs-dir envs/smoke_v7_hd_pure_sigma_sweep
   --ssh IDP -- --skip-chain` — creates the 9 sandboxes, sim+deploys traces only.
   Completed ~11:50.
2. Phase 2 (IN PROGRESS): reference + detection only (`run_0001_chain.sh &&
   run_0002_chain.sh`) per sandbox, via manually-launched tmux sessions
   (`sandbox_smoke_v7_hd_pure_sigma<X>_detect`), **not** via `run_sandboxes.sh`
   (which only knows how to run the full `run_full_pipeline.sh`).
   - **Gotcha already hit and fixed**: `run_0001_chain.sh`/`run_0002_chain.sh`
     do NOT activate the sandbox's `.venv` (unlike `run_full_pipeline.sh`,
     which prepends `.venv/bin` to `PATH`). First launch attempt (~11:51)
     crashed all 9 within seconds (`ModuleNotFoundError: No module named
     'sklearn'`) and sat silently dead — the monitor loop only checked for
     the success string, not failure, so this wasn't caught for ~20 min.
     Relaunched at 12:11 with `PATH=<sandbox>/.venv/bin:$PATH` prepended
     explicitly. Confirmed working (R2 regressions progressing) as of 13:05.
   - Smoke-scale R2 detection is much slower than smoke-scale simulation
     (~45-50s per regression group, ~120 groups per sigma → roughly 1.5-2h
     per sigma, sigmas run in parallel so ~1.5-2h wall clock total, not ×9).
     Don't assume "smoke = fast" applies uniformly — it does for simulation,
     not for R2.
   - R2 concurrency: 11 processes observed (9 mine + 2 leftover paperscale_v5),
     within the documented safe cap (~10, derived from a prior OOM crash at
     28 concurrent *paperscale-scale* R2 processes — smoke-scale regressions
     are much smaller so this headroom is fine).
3. **NOT YET DONE**: once all 9 detection chains complete, inspect
   `0002_detection/Code_extract_ics/ics_original_0XX.zip` (X = 90,80,...,10)
   per sigma with `check_ics_archive.py --ics-zip <path> --round-count 4
   --ab-words 50 --cd-words 10 --max-empty 0 --max-missing 0` (exits nonzero
   if any array is empty/missing). Find the highest level that passes, per
   sigma — may differ from 40, may differ across sigmas.
4. **NOT YET DONE**: update each of the 9 env files' `SHA3_TRAINING_ICS_LEVEL`
   (+ cascading `SHA3_VALIDATION_TEMPLATE_TAG`/`_ICS_TAG`,
   `SHA3_SASCA_TEMPLATE_TAG`/`_ICS_TAG`) to the determined per-sigma level.
   Re-deploy the updated env file to each sandbox (`scp`) — detection output
   already sits in the sandbox, doesn't need to be regenerated.
5. **NOT YET DONE**: resume with `run_full_pipeline.sh --skip-detection
   --env-file envs/<updated>.env` per sandbox (training → validation → SASCA),
   in new tmux sessions (`sandbox_smoke_v7_hd_pure_sigma<X>`, reusing the
   original label so it points at the same sandbox/traces dir).
6. Extract Family-A/B/C/D SR, GE, 2R/3R/4R SASCA AUC per σ.

### How to check current status (from any session)
```sh
ssh IDP 'for s in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
  log=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v7_hd_pure_sigma${s}/project_SHA3-32bit/pipeline_runner/detect_only_sigma${s}.log
  grep -q "COMPLETE: 0002 detection chain finished" "$log" 2>/dev/null && echo "DONE  sigma${s}" || echo "----  sigma${s}: $(tail -1 "$log" 2>/dev/null)"
done'
ssh IDP 'echo "R2=$(pgrep -cf detect_script)  KeccakSim=$(pgrep -cf KeccakSim)"'
```

## Not started (Part 5 — thesis rewrite)
- Rewrite HD model description, main tables/figures (smoke rows → pure HD),
  restructure `sec:eval-mixed` (combined HW+HD becomes the primary mixed-mode
  diagnostic, full 9σ sweep — already archived, no new compute), fix the
  hd_scale=0.5-vs-1.0 discrepancy noted above, update disc-model-assessment
  and disc-limitations. Recompile with latexmk.

## Not started (Part 8 — paperscale pure-HD sweep, last, deferred)
- Do not start until: smoke_v7 fully validated AND `paperscale_v5` (F9/ID
  SNR-equalized rerun, currently ~5-9/18 done — check
  `RUN_LOG_snr_equalized.md`, local-only) finishes and is archived.
- Same two-phase approach (detection-only first to determine per-sigma ICS
  level, THEN training onward) applies at paperscale too, likely more
  important there since paperscale R2 is the ~64h/run bottleneck stage —
  getting the ICS level wrong the first time is much more costly to redo
  than at smoke scale.
