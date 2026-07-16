# Findings: get_IoPs.py performance fixes, resume support, and the icslow stall

Session date: 2026-07-16. Written as a handoff for a separate session — read
this first instead of re-deriving state.

## 1. What was committed (already done, verified)

Commit `c26cab6` on branch `sim-per-leakpoint-pbw`, pushed to origin, and
fast-forwarded into the IDP master copy (`/storage/ge96pug/Projects_SHA3/`):

- **BLAS/OMP thread cap** (`${SHA3_R2_THREADS:-4}`, was only in
  `Code_detection_R2/script_all.sh`) extended to every other numpy/BLAS-heavy
  `script_all.sh`: `Code_find_IoPs`, `template_profiling_bytes`,
  `template_validation_bytes`, `0005_SASCA/{Iteration,Rate}_Scan_{2,3,4}R`,
  `bit_table_generation`, `get_answers`, `plot_scans`. Guards against the
  2026-07-14 incident (~127 unbounded BLAS threads/process crashing the
  scheduler at 2-3 concurrent runs).
- **`get_IoPs.py` batched column reads** — replaced a per-selected-column
  `h5py` fancy-index loop (one Python-level call per index, each forcing a
  full gzip-9 chunk decompression) with one batched `np.unique`/fancy-index
  read per part. Distinct bug from the thread cap — single-threaded HDF5
  chunk decompression, not a BLAS thread-count issue.
- **`${WORKSPACE_DIR}` placeholder fix** in `run_sandboxes.sh`'s
  `deploy_env_file()` — resolves the placeholder in deployed `.env` files
  at deploy time (previously crashed 18 sandboxes with "unbound variable"
  in scripts that re-source `.env` fresh under `set -eu`).
- **`setup_sandbox.sh`** — added `KeccakSim_v4.py` to the simulator
  copy-list (was missing, caused a silent log-less crash on `--force`
  relaunch).
- **`ics_gate_lib.sh` / `auto_sweep_monitor.sh`** committed — the
  `r2_pressure()` admission-control gate (`--r2-cap`, default 20), separate
  concurrency knob from the thread cap.
- CLAUDE.md's "Remote host & concurrency" section documents all of the
  above in detail — read that for the full mental model of the two
  concurrency knobs.

En route, discovered and fixed an unrelated issue: `0005_SASCA/
{Iteration,Rate}_Scan_{2,3,4}R/` had every tracked file deleted from disk
(not by this session) — restored via `git checkout`, then the thread-cap
edit (which had only ever been manually applied on IDP, never committed)
had to be reapplied to those 6 files by hand, verified byte-identical
against the already-working IDP copies before recommitting.

## 2. New this session: resume/skip-existing support for `get_IoPs.py`

**Not a repeat of prior work** — checked git history, local tree, IDP
master copy, and `md5sum` across every `get_IoPs.py` on IDP (all
`smoke_v8`/`v9`/`v10` sandboxes): all identical, none had resume logic
before this session, despite a recollection that this had been done
before on another device. Built fresh.

### The change (`0003_training/Code_find_IoPs/get_IoPs.py`)
In `IOPS_Extractor.get_IoPs()`:
- Compute `name_output` first; if it exists, print "already exists,
  skipping" and return immediately — no ICS load, no
  `Processed_HDF5` reads.
- Atomic write: build the array as before, write to `name_output + '.tmp'`,
  close, then `os.replace(tmp, name_output)`. Without this, a process
  killed mid-write leaves a truncated file that the exists-check would
  treat as done, permanently poisoning that group on every future resume.

### Why this can't go through `run_full_pipeline.sh`
`run_stage()` in `run_full_pipeline.sh` runs `./clean.sh` unconditionally
before `./script_all.sh` for every stage. `Code_find_IoPs/clean.sh` is
`rm -rf ics_original_XXX/ IoPs/` — it deletes exactly the output the
resume logic exists to preserve. `Code_preprocessing/clean.sh` is worse
(`rm -r ../Processed_HDF5/`, the source data `get_IoPs.py` reads).
**Any restart through the normal pipeline runner negates this fix.**
Rescues must invoke a stage's `script_all.sh` directly, never through
`run_full_pipeline.sh`/`run_0003_chain.sh`, and never its own `clean.sh`.

### Verification performed
- Local synthetic test (throwaway script, not committed): built fake
  `Processed_HDF5` parts + a fake ICS `.npy` in a scratch dir, ran
  `get_IoPs()` twice — first call creates output with no `.tmp` left
  behind, second call is a no-op (mtime and data byte-identical). Passed.
- Live rescue on `smoke_v10_word_mix_id_sigma1p0` (had been stuck ~8h,
  only 50/480 groups done at ~6-7 min/group, projected ~46h total):
  1. Deployed patched `get_IoPs.py` + already-committed thread-capped
     `script_all.sh` to the sandbox.
  2. Killed the stuck process (pid 1818890).
  3. Restarted via `cd Code_find_IoPs && ./script_all.sh` directly in a
     new tmux session `rescue_id_sigma1p0_getiops` (bypassing
     `clean.sh`/`run_full_pipeline.sh` per above).
  4. Result: all 50 existing groups skipped instantly; new groups
     computed at a steady **~32-33s/group**, a **~12x speedup** over the
     pre-fix pace. Remaining ~420 groups now estimated at ~3.5-4h instead
     of ~46h.
  5. Integrity: re-hashed `Ints_A00_i00.hdf5` and `Ints_A00_i49.hdf5`
     after the resume — byte-identical to pre-kill hashes
     (`42abfb39fc2fd89f8d276ccda284fa25`, `aa2691de650f1382dccf9192eb9524f6`).
     Skip path confirmed non-destructive.

**Deployment status**: the resume patch exists in the local working tree
(`0003_training/Code_find_IoPs/get_IoPs.py`) and was manually copied only
to the `id_sigma1p0` sandbox. **Not yet committed**, not on the IDP master
copy, not in any other sandbox. If a future session wants this fix
elsewhere, commit it first (same pattern as `c26cab6`), then sync to IDP
master, then it only benefits sandboxes created afterward or manually
patched like `id_sigma1p0` was.

## 3. New discovery: the 12 `icslow` sandboxes are stuck far worse

While checking "are there more stuck runs," surveyed every live
`get_IoPs.py` process on IDP (23 total):

- **9 sandboxes fine, no action needed**: `f9`/`id` at sigmas other than
  1.0 (e.g. `f9_sigma1p5`, `id_sigma4p0`, `id_sigma2p5`, ...). Running the
  *old*, unpatched code, but at 9-17s/group — their ICS selection at these
  configs is small enough that the old per-column-read overhead barely
  matters. Already 250-440+ groups deep.
- **12 sandboxes badly stuck** — all of
  `smoke_v10_word_mix_icslow_{hw,hd,f9,id}_sigma{0.1,0.5,1.0}` (the
  low-ICS-threshold side test, forced to level `010` instead of each
  mode's auto-selected level). Checked `icslow_id_sigma1p0` concretely:
  - Level `010` selects **54,823 ICS indices per group**, vs. **1,927**
    for `id_sigma1p0`'s normal level-030 — ~28x more columns.
  - First output group (`Ints_A00_i00.hdf5`) took ~4 hours and is
    **3.2 GB** on disk.
  - Second group has been running ~4 more hours with nothing written yet.
  - All 12 icslow sandboxes show the identical pattern (single
    multi-GB output file, hours old, no second file yet).

**This is not purely the read-pattern bug** — it's a genuine data-volume
problem. The batching fix would still help a lot (turns ~54,823 separate
per-column chunk-decompressions into far fewer via `np.unique`), but won't
shrink the underlying multi-GB-per-group output. Extrapolated worst case
(3GB/group × up to 480 groups/sandbox × 12 sandboxes) could be tens of TB.
**Current disk: 3.5TB free of 14TB (74% used)** — this is a real risk, not
just a performance annoyance.

### Open, unresolved as of end of session
1. Is multi-GB-per-group output actually intended for the icslow side
   test, or does level-010 select far more indices than the test's design
   called for? (Needs a decision on the test's own design, not just a
   code fix.)
2. Should the resume+batching fix be applied to the 12 icslow sandboxes
   the same way it was to `id_sigma1p0`? It will speed up processing but
   won't address the disk-volume risk above.
3. Given disk headroom, should any of the 12 icslow sandboxes proceed at
   all before #1 is resolved, or should they be paused (same
   `paused_sandboxes/` mechanism already used for other stale sandboxes,
   see `RUN_LOG_word_mix_sweep.md`) pending a decision?

## 4. Quick reference for the next session

```sh
# Current state of the rescued sandbox:
ssh IDP 'S=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v10_word_mix_id_sigma1p0/project_SHA3-32bit/0003_training/Code_find_IoPs
ls "$S/IoPs" | wc -l; tmux has-session -t rescue_id_sigma1p0_getiops && echo alive || echo DEAD'

# icslow sandboxes' current output-file state (repeat the survey):
ssh IDP 'for s in hw hd f9 id; do for sig in 0p1 0p5 1p0; do
  D=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v10_word_mix_icslow_${s}_sigma${sig}/project_SHA3-32bit/0003_training/Code_find_IoPs/IoPs
  echo "icslow_${s}_sigma${sig}: $(ls "$D" 2>/dev/null | wc -l) files"
done; done'

# Disk headroom:
ssh IDP 'df -h /storage/ge96pug'
```

Relevant files: `0003_training/Code_find_IoPs/get_IoPs.py` (resume patch,
uncommitted), `project_SHA3-32bit/pipeline_runner/run_full_pipeline.sh`
(`run_stage()`, shows why clean.sh blocks resume), `CLAUDE.md` ("Remote
host & concurrency" section, committed).

## 5. Resolution (2026-07-16, later same day): icslow test aborted, kept as report evidence

The three open questions from §3 are answered. Decision: **abort the icslow
side test rather than resize and rerun it** — the disk/runtime numbers
gathered while investigating the stall already make the case the test set
out to make, more cheaply than actually completing any version of it would.
Summary of what was done and found, kept here so a report-writing session
doesn't have to re-derive it:

### Actions taken
1. Killed all 12 stuck `get_IoPs.py` processes on IDP. Verified safe first:
   `h5py.File(name, 'w')` only opens after all 4 `Processed_HDF5` parts are
   read into memory, so no partial/truncated file existed under any final
   name at kill time (confirmed on disk for all 12; one sandbox,
   `icslow_id_sigma1p0`, had in fact just finished writing its second group
   cleanly moments before the kill — verified readable, correct shape).
2. Committed the resume + atomic-write patch (`e3c8546` on
   `sim-per-leakpoint-pbw`, pushed to origin, fast-forwarded into the IDP
   master copy at `/storage/ge96pug/Projects_SHA3/`). Combined with the
   already-committed batching fix (`c26cab6`), master's `get_IoPs.py` now
   has both.
3. Deployed the fully-patched `get_IoPs.py` + thread-capped `script_all.sh`
   to the 4 `icslow_{hw,hd,f9,id}_sigma0p1` sandboxes (chosen over sigma1p0
   as the sigma to keep — see below). Then **stopped short of restarting
   them** once the round-count investigation (next section) showed the
   remaining work wasn't worth it.
4. The other 8 icslow sandboxes (sigma 0.5 and 1.0 per mode) were left
   killed but not deleted, pending a cleanup decision.

### Why sigma=0.1 over sigma=1.0, and why it turned out not to matter
Initially planned to keep sigma=1.0 (this project's common baseline sigma
across other smoke_v10 sweeps) as the one sigma-per-mode to carry forward.
Reconsidered: the original rationale for the default ICS-level rule (per
user) was specifically about **near-zero-noise runs and matrix inversion**
— sigma=0.1 is the closest-to-no-noise point in this sweep and more
directly tests that claim. Checked empirically whether this would cost more
disk: it doesn't. Level 010's selected column count is nearly sigma-
independent — σ=0.1: 54,808-54,907 columns across tags A-D; σ=1.0:
54,823-54,892 — under 0.2% difference. **Level 010 is already saturated
near the ceiling of what a widest-permissive threshold can select,
regardless of noise in the 0.1-1.0 range tested.** This alone is a useful
data point: forcing the threshold to its loosest setting doesn't behave
like a noise-tunable knob, it just blows up to (approximately) "keep nearly
everything" almost immediately.

### Why the round-0-only idea was dropped
Investigated whether running only round 0 (120 of 480 groups/sandbox,
~392 GB instead of ~1.5 TB per sandbox) could substitute for a full run.
Turns out there's no config-level way to do this: `range(0,4)` and explicit
`A00`-`A03`/`B00`-`B03` round tags are hard-coded (not gated by any env var
or config knob — `global_config.py`'s `SHA3_DETECTION_ROUNDS` exists but is
unused everywhere except its own definition) in at least 5 places:
`Code_find_IoPs/script_all.sh`'s 4x `get_IoPs.py {0,1,2,3}` invocation,
`template_profiling_bytes/Template_profiling_round.py`'s `profiling_round`
loop, `template_profiling_bytes/script_all.sh`'s equivalent loop,
`0004_validation/template_validation_bytes/Template_validate_LDA.py`'s
`for rd in range(0, 4)` (twice), and `0005_SASCA/bit_table_generation/
get_tables.py`'s explicit `Template('A00'..'A03')` instantiation. Doing a
"real" partial-pipeline run would mean patching all 5 for what's meant to
be a cheap confirmatory/negative-result side test — not worth the
engineering risk or time. Decided to abort rather than pursue it.

### The evidence gathered — arguments for the ICS-level rationale (for the report)
All of this is real, measured or directly-derived data, not
extrapolated-from-nothing:

1. **Measured feature-set size at the loosest threshold.** One fully
   materialized IoPs group at level 010 (smoke scale, `sigma=1.0` and
   `sigma=0.1` both measured): `shape (8000, 54823)` / `(8000, 54808)`
   `float64` — **3.51 GB uncompressed, 3.27 GB on disk even at gzip level
   9** (compression barely helps on noisy trace floats). Compare to the
   auto-selected default level's column count for the same setup
   (~1,927, per the original stall investigation in §3) — **level 010
   selects ~28x more columns than the default rule does.**
2. **Disk cost is prohibitive even at smoke scale.** `get_round()` produces
   480 groups/sandbox (A:50 + B:50 + C:10 + D:10, ×4 rounds). At ~3.27
   GB/group: **~1.57 TB for a single fully-run sandbox**. The original
   12-sandbox icslow sweep (4 modes × 3 sigmas) would have needed
   **~18.8 TB**, against 3.5 TB free of 14 TB total on the shared host.
3. **Paperscale would be categorically worse, not just larger.** Paperscale
   profiles use `SHA3_TRAINING_SET_COUNT=400` vs smoke's `50` (8x more
   training rows: 64,000 vs 8,000). Scaling the measured group size
   linearly with row count: **≈26.2 GB/group, ≈12.6 TB for a single
   sigma/mode's full sandbox** — bigger than the entire free disk on this
   host, for just one of what would need to be many sigma/mode
   combinations. This is a clean, citable number for arguing paperscale-
   scale runs at loose ICS thresholds are outright infeasible on available
   infrastructure, without needing to actually attempt one.
4. **The blowup isn't noise-tunable — it's a property of the threshold
   itself.** Column count at level 010 varies <0.2% between σ=0.1 and
   σ=1.0. Forcing the loosest threshold doesn't scale down at lower noise;
   it just selects nearly everything, independent of where in the tested
   noise range you are.
5. **Numerical-stability argument (not yet run, but implied by the
   dimensions already measured).** 54,823+ features from only 8,000
   (smoke) or 64,000 (paperscale) training rows is a small-n/large-p
   regime — the per-byte LDA covariance matrix is rank-deficient by
   construction (rank ≤ n ≪ p) independent of noise level. This lines up
   directly with the stated original concern behind the default rule
   ("problem with no noise runs and matrix inversion"). Note: this specific
   point is an implication of the measured dimensions, not something
   empirically confirmed by actually running LDA on the data — if the
   report wants to state it as a *demonstrated* failure rather than a
   dimensional argument, that would need the standalone LDA-fit diagnostic
   that was proposed but not run (load an existing `Ints_A00_i00.hdf5`,
   attempt the per-byte covariance fit directly, no pipeline changes
   needed — cheap, but out of scope for this session).
6. **Runtime, independently.** Even before considering disk, the 12
   sandboxes spent 7-8+ CPU-hours to produce only 1-2 groups each under the
   *old* per-column-read code (54,823 individual columns vs ~1,927 at the
   default level — each a separate gzip-9 chunk decompression). The
   batching fix would cut this substantially but wasn't given a chance to
   prove out at this scale before the test was aborted.

### Status of the 12 icslow sandboxes
All killed, none deleted yet. `icslow_{hw,hd,f9,id}_sigma0p1` have the
fixed `get_IoPs.py`/`script_all.sh` deployed but were never restarted. All
12 still hold their 1-2 completed groups (~13-14 GB each) and raw
`Processed_HDF5` data. Deletion needs an explicit decision/confirmation in
a future session (per this project's standing rule to never delete
sandboxes autonomously) — not done as part of this abort.
