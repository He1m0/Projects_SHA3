# Template attacks on SHA-3 (Keccak)

IDP research project: template side-channel attacks on SHA-3 / Keccak-f[1600]
using synthetic power traces from a software simulator.

## Active project

**`project_SHA3-32bit/`** — 32-bit ARM Cortex-M4 (STM32F303RCT7, ChipWhisperer-Lite).
Pipeline phases 0001–0011 cover reference generation, R² detection, LDA template profiling,
validation, SASCA belief-propagation attack, and per-algorithm tests
(SHA3-512/384/256/224, SHAKE256/128).

**`KeccakSim_v2.py`** (repo root) — active simulator. Generates synthetic HW/HD/ID/F9 power
traces for Keccak-f[1600]; invoked by `project_SHA3-32bit/pipeline_runner/run_full_pipeline.sh`.

**`Bit_Tables/`** — precomputed bit-to-byte lookup tables for SASCA.

## Running the pipeline

See `project_SHA3-32bit/pipeline_runner/EVALUATION_GUIDE.md` for the full evaluation workflow
and `CLAUDE.md` for developer guidance.

Quick start:
```sh
cd project_SHA3-32bit/pipeline_runner
./run_full_pipeline.sh --env-file envs/.env_smoke_v3_f9_sigma1p0
```

## Status docs (active)

| File | Contents |
|------|----------|
| `findings_2026-05-21.md` | Full 4-mode sigma sweep analysis (smoke scale) |
| `findings_2026-05-25.md` | ICS mechanics, cross-scale comparability |
| `findings_2026-05-26.md` | Smoke v3 run status, ICS boundaries, midscale fix timing |
| `pipeline_explainer.md` | Full technical breakdown of all pipeline phases |

## Repo structure

```
Projects_SHA3/
├── project_SHA3-32bit/    active pipeline + phases 0001-0011
├── project_SHA3-XMEGA/    legacy 8-bit XMEGA project (static)
├── KeccakSim_v2.py        active simulator
├── Bit_Tables/            precomputed SASCA tables
├── student_thesis/        LaTeX thesis
├── _legacy/               superseded code (KeccakSim_BI_TA.py)
├── _old/                  historical findings and planning docs
├── findings_2026-*.md     active status/findings docs
├── CLAUDE.md              developer guidance for Claude Code
└── GEMINI.md              architecture overview
```

`project_SHA3-32bit/pipeline_runner/runs_archive/` (gitignored, local only) holds
snapshots of completed pipeline runs organised by scale:
`smoke_v3/`, `midscale_v1/`, `paperscale_v3/`, `smoke_v2/`, `_legacy/`.

## Reference

S.-C. You, M. G. Kuhn: *Single-trace fragment template attack on a 32-bit implementation
of Keccak*, CARDIS 2021, LNCS 13173.
