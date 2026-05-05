# SHA-3 Template Attack — Complete Findings

**Coverage:** 2026-04-24 (reference run) through 2026-05-05 (v2 results).
**Source documents** (kept separately, unchanged):
- `findings_2026-04-27.md` — verbatim timestamped raw notes
- `findings_2026-04-27_restructured.md` — restructured Apr 24 – May 4 findings
- `findings_2026-05-05.md` — May 5 v2 results + v1 bug analysis
- `pipeline_explainer.md` — pipeline architecture, math, env parameters

---

## 1) Research Goal

Build template-based side-channel attacks on SHA-3 (Keccak-f[1600]) targeting a
32-bit ARM Cortex-M4 implementation on a ChipWhisperer-Lite. The eventual goal is
attacking CROSS (a NIST post-quantum signature scheme). We train byte-level LDA
templates against a software simulator (`KeccakSim`) as a stand-in for real
oscilloscope captures. The key question: **how close can simulator-trained templates
get to real-silicon-trained templates?**

Random-byte SR baseline = 1/256 ≈ **0.39%**.
Real-traces reference benchmark: **A=35.7%, B=5.2%, C=3.8%, D=1.3%**.

---

## 2) What the Templates Actually Fit

The pipeline does **not** fit Hamming-Weight templates. It fits **F_9 stochastic
model templates** (Schindler/Lemke/Paar 2005, applied in You & Kuhn 2022).
`Template_profiling_round.py` runs a per-leakage-point multivariate linear
regression on the 8 bit-indicators of each target byte, producing per-sample-point
coefficient vectors `c_l(t) ∈ ℝ`. The 256 per-byte class means are constrained to
lie on a 9-parameter affine subspace `μ_b(t) = Σ_{l=0}^7 b_l·c_l(t) + c_8(t)`.

At runtime the classifier is a shared-covariance Mahalanobis score over 256
candidates. HW is the degenerate case (all `c_l` equal).

---

## 3) Pipeline Architecture

### Phases

```
0001 reference → 0002 detection → 0003 training → 0004 validation → 0005 SASCA → 0006–0011 per-algorithm
```

| From → To | Artifact |
|---|---|
| 0001 → 0002/0003/0004 | `ref_trace.npy` — mean trace for correlation gating |
| 0002 → 0003/0004/0005 | `ics_original_NNN.zip` — sample indices where R²(byte⇒trace) > τ |
| 0003 → 0004/0005 | `templateLDA_ONNN.zip` — per-byte LDA (eigenvecs + class means + shared cov) |
| 0004 → diagnostics | `Result_Tables.zip`, `quality_report/` — SR / GE / score / label |
| 0005 → diagnostics | `Iteration_Scan_*`, `Rate_Scan_*` — BP convergence + rate sweep |

### The A/B/C/D Families

Each Keccak-f round taps four intermediate states as template targets:

| Family | Pipeline position | Bytes | Key characteristic |
|---|---|---|---|
| C | inside θ, after column XOR | 40 | Linear; clean but small |
| D | inside θ, after column rotation | 40 | "Deep-round canary" — first to collapse |
| A | after θ+ρ+π (pre-χ) | 200 | **Main target**; benefits most from diffused leakage |
| B | after χ (nonlinear) | 200 | Hardest; most valuable for SASCA |

**Why A matters most:** θ+ρ+π is a long in-place memory-shuffling stretch where real
silicon emits the most multi-stage register leakage. A also acts as a crossroads —
SASCA's BP spreads from A's recovered bytes through χ into B and then to the input.

### 0003 Template Training (LDA detail)

Per byte:
1. Linear regression `Ŷ = β₀ + Σ βᵢ bᵢ` on 8 bit-indicators across training traces.
2. Between-class scatter B, within-class scatter W.
3. Generalized eigenvalue `B v = λ W v` → LDA subspace.
4. 256 per-class means projected: `μ_c = predict(bits_c) · A`.
5. Regularized shared covariance `Σ̂ = AᵀWA / (N − 9)` (DOF=9: 8 bits + intercept).

The regression-derived mean estimator is what makes this work at 256 classes with
~250 traces/class rather than needing thousands.

### 0005 SASCA Factor Graph

Variable nodes: A (1600 b), B (1600 b), C (320 b), D (320 b) at each round boundary.

Factor nodes:
- **θ factor**: XOR-tree over column parities; cut into sub-factors to stay tractable.
- **χ factor**: nonlinear step, 5-bit enumeration (2⁵ = 32 hypotheses per row).
- **ρ/π**: deterministic permutations; index manipulation only, no explicit factor.

Loopy belief propagation (sum-product on a graph with cycles). No convergence
guarantee but converges well empirically on this graph.

**Rate_Scan axis:** rate point r = attacker "reveals" the leftmost `r × RATE_STEP_BITS`
bits of the input to BP as oracle. Rate point 0 = pure template attack, no oracle.
Rate point max = nearly the whole state handed to BP. Success count plotted vs r.

---

## 4) Root-Cause Failures (Fixed, Historical)

**Failure Mode A — HW-only leakage** (pre-Apr 25):
HW(byte) ∈ {0,...,8} → only 9 distinct values → mathematically indistinguishable
bytes at SR ceiling ~27%, observed ~1%. Fixed by per-bit-weighted (pbw) patch
(commit `d078350`, Apr 25).

**Failure Mode B — LDA underdetermined collapse** (Apr 25, ICS LEVEL=30):
R²>0.030 included ~1953 samples/byte (22 genuine + 1931 noise). Within-class
scatter near-singular → Ledoit-Wolf shrinkage → SR ≈ 1/256. Fixed by raising to
LEVEL=90, keeping only ~22 real emission samples. Dominant gain (~10×).

---

## 5) Experimental Chronology

### Apr 24 — Reference Established

- Real traces: A=35.7%, B=5.2%, C=3.8%, D=1.3%.
- Baseline sim (HW-only, LEVEL=30): SR ≈ 1% — Failure Modes A+B both active.
- Eigenvalue probe: 8 non-zero eigenvalues for one byte → confirms HW-only ceiling.

### Apr 25 — Bit-Weighted Fix

- pbw patch + LEVEL=90: A jumps to ~9.3% (~10× over baseline). Mode A fixed.
- LEVEL=30 + pbw: still ≈ 1% (Mode B unresolved until threshold raised).

### Apr 26–27 — Smoke Baseline Established

Three smoke-scale runs (strict U(0.3,0.7) σ=0.0007; realnoise +σ=0.01;
widerpbw +U(0,1)). All at LEVEL=90.

- All converge: A ≈ 9.3–10.0%.
- **Noise-axis inversion discovered:** low noise → bimodal SR distribution (anchor
  bytes at SR≈1, most at ≈0.005). High noise → unimodal mid-range. BP propagates
  anchor bytes → SASCA wins at low noise; 0004 mean SR favors high noise.
- **widerpbw tradeoff:** D collapses (3.6%→2.0%) but SASCA improves (anchor bytes
  richer). Net positive for SASCA.

### Apr 28 — Paperscale Confirms Smoke; Operand-Leakage Rejected

- Paperscale_widerpbw 0004: A=9.51% (smoke was 9.39%). **8× more training ≈ zero.**
- leakops (operand-fetch leakage): A=9.15%, 0005 flat. **Hypothesis rejected.**
- Conclusion: scale and operand-fetch are not the bottleneck.

### Apr 29 Early — Pure HD Rejected

- Pure HD substitution (ICS=40): A=6.04%, SASCA Iter_Scan 0%/0%/0%.
- The `sim-hd-leakage` branch was substitution-based, not additive — wrong form.

### Apr 29 15:00 — Advisor Meeting + Goal Shift

Three parallel null results in 24h (HD rejection, ICS sweep, paperscale≡smoke)
converge on: **leakage model fidelity is the bottleneck, not data or ICS tuning.**

Decisions:
- Kill all live paperscale runs.
- Implement canonical F_9 per-leakage-point (advisor's proposal).
- Deprioritize bit-pair; fix the linear model before adding quadratic terms.

### Apr 29 17:00 — F_9 v1 Implemented

Commit `dffecb8`: lazy per-position 256-entry byte LUT. Each sample point t gets
its own `(c_0..c_7, c_8)` drawn from `U(0,1)` and `U(-0.5,0.5)`.

### Apr 30 — F_9 v1 Results; Seed Diagnostic

- **F_9 v1 results:** A drops 9.4% → 6.1%. Rate_Scan successes 13.0 → 7.0/21 pts.
- **Noise-axis inversion vanishes** under F_9: σ=0.0007 vs σ=0.01 SR identical at
  4 dp; per-bit BP errors Pearson 0.985. Inversion was a model-mismatch artefact.
- F_9 implementation **verified numerically correct** (LUT matches analytic formula
  `Σ b_i·c_l[i] − ½Σ c_l + c_8` to 0 abs diff at multiple PoIs).
- **Puzzling: theoretically correct F_9 is worse than the wrong collapsed model.**
  This turns out to be a bug (§6 below).
- **Seed sweep launched** (Apr 30 10:35): F_9 seeds 1234/5678, collapsed seeds
  1234/5678, signed F_9 c_l ∈ U(-1,+1). Goal: rule out seed bias and sign effects.
- **Per-bit BP failure analysis:** Failures are topology-driven, not noise-driven.
  Top-50 hardest bits 78% overlap between low/high noise; hot-bit BER plateaus at
  ~0.52. No systematic 0→1/1→0 imbalance.
- **600 GB freed** on remote host (16 archived sandboxes deleted).

**Seed-sweep result (Apr 30 ~19:00):** F_9 < collapsed confirmed across multiple
seeds. Both signed and alternative seeds also land below collapsed pbw.

### May 1–3 — Additive HD Experiments

- F_9 + additive HD scale=0.5: A ~5.1% round-averaged (vs F_9-only 2.9%).
- F_9 + additive HD scale=1.0: A ~4.8% (slightly worse than scale=0.5).
- Improvement is real but does not close the gap to collapsed pbw (9.38%).
- CMOS transition-power hypothesis: **partially confirmed, insufficient** as
  a primary explanation of the gap.
- Two multicycle implementations attempted (May 2), both FAILED at pipeline.

### May 4 — KeccakSim v2 Design and Launch

Commit `bd71199`: clean rewrite with three modes: `hw`, `hw+hd`, `f9`.
Six smoke-scale runs launched on remote host for definitive 3-way comparison.

### May 5 — v2 Results Arrive (Major Finding)

See §7 below for complete results.

---

## 6) The v1 F_9 Bug — Root Cause Analysis

### Was it a bug or a deliberate modeling choice?

**It was a bug.** Three reasons:

1. The F_9 model requires coefficients `c_l(t)` to be **fixed** per circuit position.
   A chip's transistor characteristics don't change between evaluations of the algorithm.

2. The variable `invocation_sample_index` already existed in v1 and was already being
   reset to 0 correctly at every `KeccakP1600_leak_PermutationOnWords` call. The counter
   was there *for exactly this purpose*. Using `sample_index` instead was an oversight.

3. The v2 code comment makes the original intent explicit:
   > `# Use invocation_sample_index for F9 so all permutation invocations share`
   > `# the same per-position coefficients (modular over the table size).`

**v2 is the correct implementation of F_9.**

### Code evidence

**v1 (`KeccakSim_BI_TA.py`, `_emit_sample_byte_pbw`):**
```python
contrib = self._pbw_byte_lut_at(self.sample_index)[int(byte_value) & 0xFF]
#                               ^^^^^^^^^^^^^^^^ global, never reset per invocation
```

If each permutation is L samples long, invocation j at within-permutation position t
uses coefficient row `table[j·L + t]` — a different regression model per invocation.

**v2 (`KeccakSim_v2.py`, `_leak_signal`):**
```python
row = self.f9_table[self.invocation_sample_index % len(self.f9_table)]
#                   ^^^^^^^^^^^^^^^^^^^^^^^^^ reset to 0 at each permutation call
```

Every invocation at position t uses `table[t % T]`. Same model, every time.

### Why this kills template quality

Templates aggregate `SHA3_INVOCATIONS=10` invocations per trace as independent
observations at the same trace position t. Template fitting assumes
`trace[t] = f(byte_value)` is stationary across observations.

Under v1: invocation j uses coefficient row `table[j·L + t]` — 10 different linear
models at the same position. The LDA fits a mixture → signal averages out → SNR
collapses to near-HW levels.

Under v2: all invocations use `table[t % T]` — same model everywhere. Clean fit.
Templates become near-perfect (A-family SR 99.7%).

### Why collapsed byte-pbw was immune

The collapsed model draws one shared 8-vector at init time. With no per-PoI table,
`sample_index` vs `invocation_sample_index` makes no difference — both return the
same constant vector. The collapsed model had the correct invocation-invariant property
*accidentally*. This fully explains why the theoretically weaker model outperformed
the theoretically correct but buggy v1 F_9 in all Apr/May runs.

### What test would have caught this

A unit test in noise-free mode: assert that `trace[t]` is approximately equal for the
same byte value at the same within-permutation position across two different invocations.
v1 would have failed immediately; v2 passes. Adding this invariant to the simulator
test suite is recommended before any future model comparisons.

---

## 7) v2 3-Way Comparison — Complete Results

All three runs: smoke scale, σ=0.0007, SHA3_INPUTS=16, SHA3_INVOCATIONS=10,
SHA3_TRAINING_SET_COUNT=50, SHA3_VALIDATION_INPUTS=10.

### Template Quality (0004)

Mean SR and GE by family, averaged across all rounds and groups.

| Model | A SR | A GE | B SR | B GE | C SR | C GE | D SR | D GE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **real silicon** | **35.7%** | 9.1 | 5.2% | 45.6 | 3.8% | — | 1.3% | — |
| v2 HW | 4.4% | 32.7 | 3.1% | 49.0 | 1.6% | 58.6 | — | — |
| v2 HW+HD (0.5) | 4.1% | 36.9 | 3.0% | 50.6 | 2.6% | 52.5 | 2.1% | 55.2 |
| **v2 F_9** | **99.7%** | **1.00** | **25.5%** | **9.9** | **10.0%** | **15.4** | **2.1%** | **55.2** |

D-family (Chi) is weak even under F_9 at 2.1% / GE 55.2. SASCA recovers D through
constraint propagation from the excellent A/B/C priors — BP does not need a strong D
prior if A is near-certain.

### SASCA End-to-End (0005 Rate_Scan)

21 rate points, step=64 bits, max=50 test traces per point.
Rate point 0 = max data (easiest for SASCA); rate point 20 = min data (hardest).

| Model | 2R Rate_Scan (counts/50) | 3R | 4R |
|---|---|---|---|
| v2 HW | 50→50→50→50→48→45→44→42→36→5→1→0… | same shape | same shape |
| v2 HW+HD | 50→50→50→50→46→45→45→28→5→0… | faster drop | faster drop |
| **v2 F_9** | **50 at every one of 21 points** | **flat 50** | **flat 50** |

F_9: 100% key recovery on all 50 test traces, at all round depths, at all rate points
including rate_point=20 (pure template attack, no oracle assistance).
HW/HD: degrade to 0/50 by rate_point ~9.

### Cross-Run Summary

| Model | A SR (0004) | SASCA 2R pure-template |
|---|---:|---:|
| Real silicon | 35.7% | 100% |
| Collapsed pbw (v1 best) | 9.4% | ~76% |
| F_9 v1 | 6.1% | ~44% |
| F_9 + additive HD v1 | ~5.1% | ~50% |
| v2 HW | 4.4% | drops at rp=4 |
| v2 HW+HD | 4.1% | drops at rp=4 |
| **v2 F_9** | **99.7%** | **100% (all 21 rp)** |

---

## 8) What These Results Mean

### The attack pipeline is validated

v2 F_9 (self-consistent: simulate with F_9, fit with LDA → LDA learns the F_9
structure perfectly) gives A=99.7% and 100% SASCA at all operating points. The
methodology is sound. Given a leakage model that matches the hardware, the attack
succeeds completely.

### HD is not the missing piece

v2 HW+HD (scale=0.5) scores A=4.1% — slightly *worse* than v2 HW at 4.4%. The CMOS
transition-power hypothesis is rejected as the dominant missing physics. The F_9
coefficient structure (per-bit, per-position) is the dominant signal.

### The v1 F_9 anomaly is fully resolved

The counter-intuitive result (theoretically correct F_9 < theoretically wrong collapsed
pbw) was an implementation bug, not a statement about F_9 physics.

### The remaining gap is leakage coefficient estimation

Real silicon A=35.7% is well above HW (4.4%) and well below the self-consistent F_9
ceiling (99.7%). The gap is now characterized as: how accurately can we estimate
the real hardware's per-position F_9 coefficients from oscilloscope data? This is
exactly the profiling problem in You & Kuhn 2022.

---

## 9) All Findings Tables

### 9.1 First-Order SR by Family (0004)

Random baseline = 1/256 ≈ 0.39%.

| Run | A | B | C | D | Notes |
|---|---:|---:|---:|---:|---|
| **real traces** | **35.7%** | 5.2% | 3.8% | 1.3% | ground-truth benchmark |
| baseline HW-only LEVEL=30 | ~1% | ~1% | ~0.5% | ~0.5% | failure modes A+B |
| smoke strict | 9.34% | 3.4% | 4.4% | 3.6% | LEVEL=90, σ=0.0007, U(0.3,0.7) |
| smoke realnoise | 10.02% | 3.4% | 4.5% | 3.6% | + σ=0.01 |
| smoke widerpbw | 9.39% | 3.4% | 3.7% | 2.0% | + U(0,1) weights |
| paperscale strict | 9.51% | 3.5% | 4.8% | 3.9% | 8× training data |
| paperscale widerpbw | 9.51% | 3.4% | 3.6% | 1.9% | 8× training data |
| paperscale realnoise | **10.30%** | 3.6% | 4.9% | 3.9% | highest sim A; worst SASCA |
| smoke leakops | 9.15% | 3.3% | 3.6% | 2.2% | + operand-fetch; null |
| smoke HD ICS=40 | 6.04% | 2.30% | 0.96% | 0.40% | pure HD substitution |
| F_9 v1 (σ=0.0007) | 6.07% | 3.37% | 2.78% | 1.72% | per-leakpoint, seed=2839 |
| F_9 v1 (σ=0.01) | 6.04% | 3.37% | 2.79% | 1.74% | noise-axis: identical at 4 dp |
| F_9 v1 + additive HD 1.0 | ~4.8% | 2.55% | 1.74% | 0.90% | F_9 + HW(v XOR prev) |
| F_9 v1 + additive HD 0.5 | ~5.1% | 2.82% | 2.24% | 1.21% | best of HD variants |
| v2 HW | 4.4% | 3.1% | 1.6% | — | KeccakSim v2, pure HW |
| v2 HW+HD (scale=0.5) | 4.1% | 3.0% | 2.6% | 2.1% | v2 additive HD |
| **v2 F_9** | **99.7%** | **25.5%** | **10.0%** | **2.1%** | **v2 correct F_9** |

**Key observation:** paperscale_widerpbw ≡ smoke_widerpbw at 0004 (within noise).
8× more training traces ≈ zero improvement. Scale is not the bottleneck.

### 9.2 SASCA Summary (0005)

Iteration_Scan maximum success rate (smoke, 50 traces):

| Run | 2R | 3R | 4R |
|---|---:|---:|---:|
| real traces | 100% | 100% | 100% |
| smoke strict | 76% | 90% | 90% |
| smoke realnoise | 60% | 86% | 88% |
| smoke widerpbw | 76% | **94%** | **92%** |
| F_9 v1 | 44% | ~68% | ~72% |
| F_9 v1 + additive HD | 50% | ~76% | ~80% |
| v2 HW | ~96% | ~96% | ~96% |
| v2 HW+HD | ~96% | ~96% | ~96% |
| **v2 F_9** | **100%** | **100%** | **100%** |

Rate_Scan: first rate point where success drops below 100%:

| Run | First drop at rp | Bits revealed at drop |
|---|---:|---:|
| v2 HW | 4 | 256 b |
| v2 HW+HD | 3–4 | 192–256 b |
| **v2 F_9** | **never** | **0 (pure template)** |

### 9.3 Round-Averaged 0004 (recent runs)

Values are round-averaged across all four rounds per family (A00–A03 etc.).

| Run | Overall SR | A | B | C | D |
|---|---:|---:|---:|---:|---:|
| F_9 v1 seed=2839 | 1.63% | 2.56% | 1.55% | 1.53% | 0.88% |
| F_9 v1 + HD 1.0 | 2.51% | 4.83% | 2.55% | 1.74% | 0.90% |
| F_9 v1 + HD 0.5 | **2.83%** | **5.05%** | 2.82% | 2.24% | 1.21% |
| byte_pbw widerpbw | 4.60% | 9.38% | 3.37% | 3.69% | 1.97% |
| **v2 F_9** | **~34%** | **~99.7%** | **~25.5%** | **~10%** | **~2.1%** |
| real traces | — | 35.70% | 5.20% | 3.80% | 1.30% |

---

## 10) Causal Attribution

| Knob / change | Why changed | Result | Status |
|---|---|---|---|
| ICS LEVEL 30 → 90 | LDA underdetermined | ~10× SR jump | Locked |
| SIM_HW_RATIO 0.82 → 1.0 | Remove common-wave noise | ~1.5× SNR | Locked |
| pbw U(0.3,0.7) → U(0,1) | More byte separability | D collapses; SASCA improves | Locked (widerpbw) |
| σ 0.01 → 0.0007 | SASCA anchor-byte mechanism | 0004 mean −0.7 pp; SASCA +16 pp | Locked for SASCA |
| Scale: smoke → paperscale | Test if data closes gap | ≤0.2 pp; ≤4 pp SASCA | **Rejected** |
| Operand-fetch leakage | More events per byte | Null / slightly negative | **Rejected** |
| HD substitution | Test transition power | Pure HD worse; ICS issues | **Wrong form** |
| F_9 v1 per-leakpoint | Match templates' model | A: 9.4% → 6.07% (bug-degraded) | Bug identified |
| Additive HD on F_9 v1 | Additive transition power | A ~5.1%; partial improvement | Real effect; not primary |
| Signed c_l ∈ U(-1,1) | Coefficient sign sensitivity | F_9 < collapsed persists | Not the issue |
| **v2 F_9 (correct)** | **Bug-free implementation** | **A=99.7%; SASCA 100%** | **Validates methodology** |

---

## 11) Ruled-Out Hypotheses

| Hypothesis | Test | Result | Evidence |
|---|---|---|---|
| More training traces closes the gap | Smoke → paperscale (8×) | **NULL** | ≤0.2 pp on 0004; Apr 28 |
| Operand-fetch leakage adds info | leakops smoke | **NULL/NEGATIVE** | A=9.15% vs 9.39%; Apr 28 |
| Higher ICS level > 90 helps | LEVEL=120 run | **NULL** | Identical to realnoise; Apr 25–27 |
| Lower ICS level (denser sampling) | LEVEL=50/70 sweeps | **NULL** | Identical to LEVEL=90 at 4 dp |
| Noise level (σ) is the bottleneck | σ sweep under F_9 | **NULL** | SR identical at 4 dp; Pearson 0.985 per-bit |
| HD substitution helps | smoke_hd_ics40 | **NEGATIVE** | A: 9.39%→6.04%; SASCA SR=0%; Apr 29 |
| Additive HD (v2 clean test) | v2 HW+HD vs v2 HW | **NEGATIVE** | A: 4.4%→4.1% (slightly worse); May 5 |
| F_9 model physics are inferior | v2 F_9 (correct impl.) | **DISPROVEN** | A=99.7%; was a bug in v1 |

---

## 12) What Remains Open

| Question | Status |
|---|---|
| Can F_9 coefficients be estimated from real traces? | Next step: profiling on ChipWhisperer hardware |
| Does v2 F_9 hold at paperscale? | Not run; not necessary for current goal |
| Why is D weak (2.1%) even under F_9? | Chi step inherently hardest; SASCA tolerates it |
| No-noise v2 variants crashed at LDA | Singular matrix with σ=0; expected, not a bug |
| Does multi-cycle per-op emission help? | Superseded by F_9 result; lower priority now |

---

## 13) Numbers at a Glance

| Metric | HW-only baseline | Best pre-v2 | v2 F_9 | Real silicon |
|---|---:|---:|---:|---:|
| A-family SR | ~1% | 9.4% | **99.7%** | 35.7% |
| B-family SR | ~1% | 3.4% | **25.5%** | 5.2% |
| C-family SR | ~1% | 3.7% | **10.0%** | 3.8% |
| D-family SR | ~1% | 2.0% | 2.1% | 1.3% |
| SASCA 2R pure-template | 0% | 76% | **100%** | 100% |
| SASCA 4R pure-template | 0% | 92% | **100%** | 100% |
| SASCA Rate_Scan rp=10 | 0% | ~10% | **100%** | ~100% |

Random baseline = 1/256 ≈ 0.39%. "Pure template" = no oracle-revealed bits.

---

## 14) Decision Framework for New Results

1. Check 0004 family SR, especially A-family and the bimodality pattern (anchor bytes
   at SR≈1 vs unimodal distribution?).
2. Check 0005 SASCA together: Iteration_Scan peak SR and Rate_Scan t50. A run that
   improves 0004 but regresses SASCA is not an improvement.
3. Compare Rate_Scan in bit-equivalent terms (multiply rate points by RATE_STEP_BITS).
4. If SASCA improves but 0004 is flat, inspect anchor-byte distribution.
5. Do not declare victory from 0004 mean SR alone (realnoise shows this misleads).
6. Check D-family as early warning: D collapsing first means ICS too strict or leakage
   too diffuse for deep-round bytes.

---

## 15) Archived Runs (local)

| Archive | Date | Notes |
|---|---|---|
| `2026-04-24_ref_original_paper` | Apr 24 | Real-silicon reference; 2R only |
| `2026-04-27_smoke_byte_pbw_realnoise` | Apr 27 | σ=0.01 baseline |
| `2026-05-02_smoke_per_leakpoint_hd_add` | May 2 | F_9 v1 + HD scale=1.0 |
| `2026-05-02_smoke_per_leakpoint_hd_add_0p5` | May 2 | F_9 v1 + HD scale=0.5 (best HD) |
| `2026-05-04_f9_combined_fixed` | May 4 | F_9 v1 seed sweep combined; SR=2.59% |
| `2026-05-04_f9_multi_fixed` | May 4 | F_9 v1 multi-seed; SR=1.83% |
| `2026-05-04_legacy_hd_0p5` / `_1p0` | May 4 | Legacy HD runs |
| `2026-05-05_smoke_v2_hw_noise` | May 5 | **v2 HW, σ=0.0007** |
| `2026-05-05_smoke_v2_hd_noise` | May 5 | **v2 HW+HD, σ=0.0007** |
| `2026-05-05_smoke_v2_f9_noise` | May 5 | **v2 F_9, σ=0.0007 — primary result** |
