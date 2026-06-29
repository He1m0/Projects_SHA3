# SNR-Equalized Sigma Sweep Run Log

Tracks smoke_v6 and paperscale_v5 — the corrected reruns of F9 and Identity models
with SNR-equalized signal scales, making results directly comparable to HW/HD.

**Why these runs exist:** Previous sweeps (smoke_v2/v3/v4, paperscale_v3) ran all
models at identical sigma values but different signal variances, making cross-model
comparison scientifically invalid. Fixed by setting model-specific scales so all
models share SNR_var = 2/σ² (matching HW at hw_scale=1.0).

**Scale values:**
- F9:       `SIM_F9_SCALE=1.7321` (=√3, with bcs=1.0,  → Var_signal=2.0)
- Identity: `SIM_ID_SCALE=0.01913` (=√(2/5461.25),     → Var_signal=2.0)
- HW/HD:    scale=1.0 (unchanged, already Var_signal=2.0) ← **no rerun needed**

**ICS level:** 90 uniformly across all sigmas and models (previously varied because
F9/ID had lower SNR — now fixed).

**Comparable to:** smoke_v5 (HW/HD), paperscale_v4 (HW/HD)

---

## Pre-launch checklist — 2026-06-29

- [x] SNR math verified, scale values derived
- [x] KeccakSim_v2.py already has `--f9-scale` / `--id-scale` flags (no code changes needed)
- [x] 36 env files generated (smoke_v6: flat 18-file layout; paperscale_v5: sigma subdirs)
- [x] launch_smoke_v6.sh written and tested (--dry-run)
- [x] launch_paperscale_v5.sh written and tested (--dry-run, waves A1–A3/B1–B3)
- [x] Stale v4iter_* tmux sessions killed (6 sessions)
- [x] IDP disk cleanup (paperscale_v3 + smoke_v5 + older remnants)
- [x] monitor_snr_sweep.sh + deploy_monitor.sh written, deployed, monitor started
- [x] Smoke_v6 sanity run (f9+id σ=0.1) — launched 2026-06-29 22:27
- [x] ICS level 90 confirmed viable — PASSED immediately for both f9+id σ=0.1
- [x] Smoke_v6 remaining (16 runs) + Paperscale_v5 wave A1 — auto-launched by monitor
- [x] Monitor bug fixed (B1-B3 missing in main path); restarted --start-wave B1 at 22:40
- [x] Three deeper bugs fixed (KeccakSim path, R2-only gate, smoke batching); committed b8b4db7
- [x] Race condition on restart fixed: cleanup must complete before monitor starts
- [x] Monitor restarted clean at 00:36 (2026-06-30); ICS gate polling
- [ ] Paperscale_v5 full sweep complete

---

## IDP cleanup — 2026-06-29

**Pre-cleanup disk:** 2.8 TB free / 14 TB (80% full). Target: ≥4 TB free before paperscale launch.

**Local archives confirmed intact before deleting:**
- `runs_archive/smoke_v5/`: 18/18 entries ✓
- `runs_archive/paperscale_v3/`: 36 run dirs ✓
- `runs_archive/paperscale_v4/`: 6 run dirs ✓

Post-cleanup disk: **5.4 TB free / 14 TB (60% full)** — cleaned 2026-06-29.
Freed ~2.6 TB: 42 paperscale_v3 dirs + 36 smoke_v5 dirs + 16 smoke_v3/v4+orphan dirs.

---

## smoke_v6 — sanity check runs

| Mode | σ   | Launched        | ICS OK? | DONE | Archived |
|------|-----|-----------------|---------|------|----------|
| f9   | 0.1 | 2026-06-30 00:36 | pending    |      |          |
| id   | 0.1 | 2026-06-30 00:36 | pending    |      |          |

**Gate condition before paperscale_v5:** ICS level 90 non-empty for both sanity runs.
**Result: Pending** — ICS gate polling as of 00:36. Previous attempts (22:28, 23:35) failed due to monitor bugs and cleanup race condition.

### smoke_v6 full sweep

All 18 runs to be launched by monitor (Phase S + SR). Monitor: `snr_monitor` tmux on IDP.
Active monitor log: `/storage/ge96pug/monitor_snr_sweep_20260630_003610.log`

| Mode | σ   | Launched        | DONE | Archived |
|------|-----|-----------------|------|----------|
| f9   | 0.1 | 2026-06-30 00:36  |      |          |
| f9   | 0.5 | pending           |      |          |
| f9   | 1.0 | 2026-06-29 ~22:30 |    |          |
| f9   | 1.5 | 2026-06-29 ~22:30 |    |          |
| f9   | 2.0 | 2026-06-29 ~22:31 |    |          |
| f9   | 2.5 | 2026-06-29 ~22:31 |    |          |
| f9   | 3.0 | 2026-06-29 ~22:32 |    |          |
| f9   | 3.5 | 2026-06-29 ~22:32 |    |          |
| f9   | 4.0 | 2026-06-29 ~22:33 |    |          |
| id   | 0.1 | 2026-06-30 00:36  |      |          |
| id   | 0.5 | pending           |      |          |
| id   | 1.0 | 2026-06-29 ~22:30 |    |          |
| id   | 1.5 | 2026-06-29 ~22:30 |    |          |
| id   | 2.0 | 2026-06-29 ~22:31 |    |          |
| id   | 2.5 | 2026-06-29 ~22:31 |    |          |
| id   | 3.0 | 2026-06-29 ~22:32 |    |          |
| id   | 3.5 | 2026-06-29 ~22:32 |    |          |
| id   | 4.0 | 2026-06-29 ~22:33 |    |          |

---

## paperscale_v5 — primary dataset

SASCA: 200 iter, 201 rate points, 8-bit step.
Trace counts: 100 det, 400 training, 40 val, 1000 SASCA.

### Wave status

Waves launched by `snr_monitor` tmux session on IDP. Monitor gates R2 ≤ 6 between waves.

| Wave | Mode | σ         | Launched          | R2 peak | SASCA | DONE | Archived |
|------|------|-----------|-------------------|---------|-------|------|----------|
| A1   | f9   | 0.1       | pending           |         |       |      |          |
| A1   | f9   | 0.5       | pending           |         |       |      |          |
| A1   | f9   | 1.0       | pending           |         |       |      |          |
| B1   | id   | 0.1       | pending           |         |       |      |          |
| B1   | id   | 0.5       | pending           |         |       |      |          |
| B1   | id   | 1.0       | pending           |         |       |      |          |
| A2   | f9   | 1.5       | pending           |         |       |      |          |
| A2   | f9   | 2.0       |          |         |       |      |          |
| A2   | f9   | 2.5       |          |         |       |      |          |
| B2   | id   | 1.5       |          |         |       |      |          |
| B2   | id   | 2.0       |          |         |       |      |          |
| B2   | id   | 2.5       |          |         |       |      |          |
| A3   | f9   | 3.0       |          |         |       |      |          |
| A3   | f9   | 3.5       |          |         |       |      |          |
| A3   | f9   | 4.0       |          |         |       |      |          |
| B3   | id   | 3.0       |          |         |       |      |          |
| B3   | id   | 3.5       |          |         |       |      |          |
| B3   | id   | 4.0       |          |         |       |      |          |

### ICS deviations (if any σ≥3.0 runs needed level < 90)

*Expected: none — SNR matching should make level 90 viable for all runs.*
*Document here if --fix-ics was applied to any run.*

| Mode | σ   | ICS level used | Reason |
|------|-----|----------------|--------|
|      |     |                |        |

### Final completion table

| Mode | σ=0.1 | σ=0.5 | σ=1.0 | σ=1.5 | σ=2.0 | σ=2.5 | σ=3.0 | σ=3.5 | σ=4.0 |
|------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| f9   |       |       |       |       |       |       |       |       |       |
| id   |       |       |       |       |       |       |       |       |       |

---

## midscale_v6 (nice-to-have, after paperscale_v5 complete)

To be planned once paperscale_v5 is fully archived.
Comparable to: midscale_v2.

---

## Archive naming convention

```
runs_archive/smoke_v6/   YYYY-MM-DD_smoke_v6_{mode}_sigma{X}
runs_archive/paperscale_v5/   YYYY-MM-DD_paperscale_v5_{mode}_sigma{X}
```

After archiving each run: immediately delete sandbox and TRACES_DIR on IDP to free disk.
Monitor: `ssh IDP 'df -h /storage/'` — keep ≥1 TB free.
