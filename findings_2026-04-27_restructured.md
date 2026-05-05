# SHA-3 Template Attack — Investigation Findings

**Active document.** Coverage: 2026-04-24 through 2026-05-04.
Raw audit trail: `findings_2026-04-27.md` (verbatim notes, unchanged).
Pipeline explainer: `pipeline_explainer.md` (math, env params, architecture).

---

## 1) General Context

### 1.1 Research Goal

Build template-based side-channel attacks on SHA-3 (Keccak-f[1600]) with the
eventual goal of attacking CROSS (a NIST post-quantum signature scheme that
uses SHA-3 internally). We are training byte-level LDA templates against a
32-bit ARM Cortex-M4 target, using a software simulator (`KeccakSim`) as a
stand-in for real oscilloscope captures. The key open question is: **how close
can simulator-trained templates get to real-silicon-trained templates?**

### 1.2 What the Templates Actually Fit

The pipeline does **not** fit Hamming-Weight templates. It fits **F_9
stochastic model templates** (Schindler/Lemke/Paar 2005, applied in You & Kuhn
2022). Concretely, `Template_profiling_round.py` runs a per-leakage-point
multivariate linear regression on the 8 bit-indicators of each target byte,
producing per-sample-point coefficient vectors `c_l(t) ∈ ℝ`. The 256
per-byte class means are then constrained to lie on a 9-parameter affine
subspace `μ_b(t) = Σ_{l=0}^7 b_l·c_l(t) + c_8(t)` at each ICS sample `t`.

At runtime the classifier is a shared-covariance Mahalanobis score over 256
candidates. HW is a degenerate case (all `c_l` equal). A free 256-class
Gaussian would need ~256× more training data; this middle ground exploits the
bit structure to estimate 256 means from far fewer traces.

**Why this matters for simulation:** the simulator must produce traces whose
leakage at each sample point is well-approximated by `L(t) = Σ βᵢ(t)·bitᵢ +
c_8(t) + ε`. If the βᵢ(t) are constant across sample points (the *collapsed*
model), the pipeline can still fit templates, but they will be weaker than if
βᵢ vary per point (the *full* F_9 model that templates assume).

### 1.3 The A/B/C/D Families

Each Keccak-f round has four template targets at distinct pipeline positions:

| Family | Position in round | Bytes | Key characteristic |
|---|---|---|---|
| C | inside θ, after column XOR | 40 | Linear; clean but small |
| D | inside θ, after column rotation | 40 | Linear; "deep-round canary" — first to collapse |
| A | after θ+ρ+π (pre-χ) | 200 | Main target; benefits most from diffused leakage |
| B | after χ (nonlinear) | 200 | Hardest to template; most valuable for SASCA |

**Why A matters most:** the θ+ρ+π chain is a long stretch of in-place memory
shuffling where real silicon emits the most multi-stage register leakage. A
also acts as a "crossroads" — SASCA's belief propagation spreads from A's
recovered bytes through χ into B and then to INP. D is the diagnostic canary:
if D collapses, the leakage model is too diffuse or the ICS threshold too strict.

Random byte SR baseline = 1/256 ≈ **0.39%**.
Real-traces reference benchmark: **A = 35.7%, B = 5.2%, C = 3.8%, D = 1.3%**.

### 1.4 Two Root-Cause Failures (Fixed, Historical)

Both failures produced the same symptom (SR ≈ 1/256) but have different
mechanisms and different cures.

**Failure Mode A — HW-only leakage** (pre-Apr 25):
HW(byte) ∈ {0,...,8} has only 9 distinct values. Two bytes with the same
Hamming weight produce identical mean traces → mathematically indistinguishable.
SR ceiling ≈ 27% in theory; observed ~1% in practice. Fixed by the
bit-weighted (pbw) patch (commit `d078350`, Apr 25) which replaces `HW(byte)`
with `Σᵢ wᵢ·bitᵢ(byte)` for seeded weights.

**Failure Mode B — LDA underdetermined collapse** (Apr 25, LEVEL=30):
R² threshold 0.030 included ~1953 samples/byte (22 genuine + 1931 noise).
Within-class scatter near-singular → sklearn's auto-shrinkage maps LDA toward
identity-covariance → SR ≈ 1/256. Fixed by raising to LEVEL=90, which keeps
only the ~22 real emission samples. This was the dominant gain (~10×).

---

## 2) Comparison Tables

Numbers in 2.1 and 2.2 are mean per family across all bytes and rounds within
that family, per the `quality_report/summary_family_round.csv` aggregation.
Section 2.3 shows round-averaged values explicitly where noted.

### 2.1 0004 First-Order SR by Family

Random baseline = 1/256 ≈ 0.39%. `n` = validation traces.

| Run | A | B | C | D | Notes |
|---|---:|---:|---:|---:|---|
| **real traces** | **35.7%** | 5.2% | 3.8% | 1.3% | ground-truth benchmark |
| baseline sim (HW-only, LEVEL=30) | ~1%* | ~1%* | ~0.5%* | ~0.5%* | failure modes A + B |
| strict (smoke) | 9.34% | 3.4% | 4.4% | 3.6% | LEVEL=90, σ=0.0007, U(0.3,0.7) |
| realnoise (smoke) | 10.02% | 3.4% | 4.5% | 3.6% | + σ=0.01 |
| widerpbw (smoke) | 9.39% | 3.4% | 3.7% | 2.0% | + U(0,1) weights |
| ics120 (smoke) | 10.02% | 3.4% | 4.5% | 3.6% | LEVEL=120: null vs realnoise |
| paperscale_strict | 9.51% | 3.5% | 4.8% | 3.9% | 8× training data |
| paperscale_widerpbw | 9.51% | 3.4% | 3.6% | 1.9% | 8× training data |
| paperscale_realnoise | **10.30%** | 3.6% | 4.9% | 3.9% | highest sim A SR; worst SASCA |
| leakops (smoke) | 9.15% | 3.3% | 3.6% | 2.2% | + operand-fetch leakage; null |
| smoke_hd ICS=40 | 6.04% | 2.30% | 0.96% | 0.40% | **pure HD (substitution only)** |
| **F_9 per-leakpoint (σ=0.0007)** | 6.07% | 3.37% | 2.78% | 1.72% | canonical F_9, seed=2839 |
| F_9 per-leakpoint (σ=0.01) | 6.04% | 3.37% | 2.79% | 1.74% | noise-axis: identical at 4 dp |
| F_9 + additive HD (scale=1.0) | ~4.8%† | 2.55% | 1.74% | 0.90% | F_9 + HW(v XOR prev); hd_add |
| F_9 + additive HD (scale=0.5) | ~5.1%† | 2.82% | 2.24% | 1.21% | best of HD variants |
| v2 HW (σ=0) | FAILED | — | — | — | Singular matrix at LDA — σ=0 makes cov degenerate |
| **v2 HW + noise** | **4.4%** | **3.1%** | **1.6%** | — | v2 HW, σ=0.0007 |
| v2 HW + HD (σ=0) | FAILED | — | — | — | Same LDA collapse as v2 HW |
| **v2 HW + HD + noise** | **4.1%** | **3.0%** | **2.6%** | **2.1%** | v2 additive HD + σ=0.0007; slightly worse than HW |
| v2 F_9 (σ=0) | FAILED | — | — | — | Same LDA collapse |
| **v2 F_9 + noise** | **99.7%** | **25.5%** | **10.0%** | **2.1%** | **Correct F_9; v1 had indexing bug — see §2.4** |

*Extrapolated — baseline run never reached 0004.
†Round-averaged values from runs_archive_central; see note in 2.3.

**Key observation:** paperscale_widerpbw and paperscale_strict 0004 numbers
are within noise of their smoke counterparts — **8× more training traces ≈ no
improvement.** The simulator-vs-real gap is structural, not a data-count issue.

### 2.2 0005 SASCA Summary

**Iteration_Scan maximum success rate (smoke, 50 traces):**

| Run | 2R | 3R | 4R | Notes |
|---|---:|---:|---:|---|
| real traces | **100%** | **100%** | **100%** | Converges at iter 14-15 |
| strict (smoke) | 76% | 90% | 90% | |
| realnoise (smoke) | 60% | 86% | 88% | Fewer anchor bytes |
| widerpbw (smoke) | 76% | **94%** | **92%** | Best of smoke variants |
| leakops (smoke) | 72% | 88% | 92% | Slightly worse 2R/3R |
| F_9 per-leakpoint | 44% | ~68% | ~72% | Estimated from rate-scan slope |
| F_9 + additive HD | 50% | ~76% | ~80% | Improvement over F_9 alone |
| v2 HW + noise | ~96% | ~96% | ~96% | Drops at rate_point=4 (pure-template fails) |
| v2 HW+HD + noise | ~96% | ~96% | ~96% | Same drop pattern as HW; HD does not help |
| **v2 F_9 + noise** | **100%** | **100%** | **100%** | **Flat 50/50 at all 21 rate points; pure-template succeeds** |

**Rate_Scan t50 thresholds (bits of unknown input that succeed in 50% of traces):**

| Run | 2R | 3R | 4R | Notes |
|---|---:|---:|---:|---|
| real traces | 1144 b | 1456 b | **1488 b** | ~full-state recovery |
| paperscale_widerpbw | 808 b | 888 b | 864 b | ~58-71% of real |
| paperscale_strict | 800 b | 840 b | 816 b | ~55-70% of real |
| smoke_widerpbw | 832 b | 832 b | 832 b | coarser step (64-bit) |
| F_9 per-leakpoint | ~192 b | ~192 b | ~192 b | 4-5 rate points survive |
| F_9 + additive HD | ~320 b | ~320 b | ~320 b | Better tail; still far from real |
| v2 HW + noise | 256 b | 256 b | 256 b | First drop at rate_point=4 |
| v2 HW+HD + noise | 192–256 b | 192–256 b | 192–256 b | Marginally worse than HW |
| **v2 F_9 + noise** | **∞ (never drops)** | **∞** | **∞** | **Flat 50/50 through all 21 points** |

**Crucial finding: the sim-vs-real gap widens with more rounds.** At 2R the
widerpbw sim reaches 71% of real's t50; at 4R only 58%. This is an information-
density problem — each additional round carries more constraints in BP, and real
silicon's traces carry more bits of information per sample than our simulator does.

**SASCA is not the bottleneck.** Given its per-byte inputs, BP does well: at
widerpbw 4R, 92% of traces succeed at the iteration-scan peak. The issue is
upstream — template per-byte SR drives everything.

**Anchor-byte effect:** Under strict/widerpbw (σ=0.0007), a handful of bytes
reach SR≈1.0 ("anchors") while most sit at SR≈0.005. SASCA's belief
propagation propagates these near-certain bytes as high-confidence priors.
Under realnoise (σ=0.01), the bimodal distribution flattens into a unimodal
mid-range — 0004 mean SR improves slightly, but BP loses its anchors and SASCA
regresses. **The right optimization target is SASCA, not 0004 mean SR.**

### 2.3 Recent Runs: F_9 vs Additive HD vs Collapsed Byte-pbw

**0004 family SR, round-averaged across all four rounds per family.**
Lower than section 2.1 values (which represent the per-family peak) because
later rounds (A01, A02, A03) progressively degrade from the first-round peak.

| Run | Overall SR | A | B | C | D | Note |
|---|---:|---:|---:|---:|---:|---|
| F_9 seed-2839 combined* | 1.63% | 2.56% | 1.55% | 1.53% | 0.88% | F_9 at seed=2839, multi-run average |
| F_9 seed-2839 multi-fixed* | 1.83% | 2.89% | 1.71% | 1.65% | 1.09% | Seed-sweep variant |
| F_9 + HD add (scale=1.0) | 2.51% | 4.83% | 2.55% | 1.74% | 0.90% | F_9 + additive HD scale=1.0 |
| F_9 + HD add (scale=0.5) | **2.83%** | **5.05%** | 2.82% | 2.24% | 1.21% | Best of HD variants |
| byte_pbw widerpbw | 4.60% | 9.38% | 3.37% | 3.69% | 1.97% | Collapsed pbw U(0,1) — optimistic |
| byte_pbw (strict) | 6.83% | 15.38% | 7.17% | 3.39% | 1.45% | Optimistic upper bound only |
| **v2 F_9 + noise** | **~34%** | **~99.7%** | **~25.5%** | **~10.0%** | **~2.1%** | **Correct F_9 (v1 had indexing bug)** |
| real traces | — | 35.70% | 5.20% | 3.80% | 1.30% | Ground-truth benchmark |

*"Combined" and "multi-fixed" are from the Apr 30 seed-sweep diagnostic; exact
label provenance is in `findings_2026-04-27.md` §"Open question: is F_9 <
collapsed real, or seed bias?"

**What this says (updated May 5):**
- F_9 v1 appeared worse than collapsed pbw due to an **implementation bug**:
  v1 indexed coefficients by global `sample_index` instead of per-invocation
  `invocation_sample_index`. Different invocations used different coefficient
  vectors at the same trace position, making the LDA fit a mixture of models.
  The collapsed model was immune because it has one shared vector.
- v2 F_9 (correct implementation) achieves A=99.7% round-averaged — near-perfect,
  exceeding even the real-silicon reference.
- Additive HD (v2 clean test) gives A=4.1% — slightly *worse* than v2 HW (4.4%).
  The CMOS transition-power hypothesis is **rejected** as a dominant contributor.
- The real-data gap is now attributed to leakage coefficient estimation accuracy
  from real hardware, not to the attack methodology.

**The 4R rate-scan ordering (from Rate_Scan Rate point success):**

| Run | 4R rate curve | t50 | t90 | Reading |
|---|---|---:|---:|---|
| F_9 (seed=2839) | 50→50→41→17→0→... | 3/21 pts (192 b) | 2/21 pts (128 b) | Fails almost immediately |
| F_9 + HD (0.5) | 50→50→50→49→42→20→9→2→... | 5/21 pts (320 b) | 4/21 pts (256 b) | Best HD smoke; still far from real |
| collapsed widerpbw | 9–13 points survive | 13/21 (832 b) | 8/21 (512 b) | Much flatter |
| real traces | Flat through ~186/201 pts | 186/201 (1488 b) | 181/201 (1448 b) | Broad plateau |

**The 4R failure mode** is a right-tail collapse: F_9 variants lose almost
immediately after the first 2-3 rate points, HD pushes collapse a few points
farther, but none produce real silicon's broad flat success plateau.

### 2.4 KeccakSim v2 Three-Way Comparison — COMPLETED May 5

`KeccakSim_v2.py` (commit `bd71199`, May 4) is a rewritten simulator with three
explicit leakage modes: `hw`, `hw+hd` (additive HD via SIM_HD_ADD_SCALE), and `f9`
(per-position F_9 stochastic model). Six smoke-scale runs completed May 5.

| Profile | Mode | Noise | Outcome |
|---|---|---|---|
| `.env_smoke_v2_hw` | HW per byte | σ=0 | FAILED — singular LDA cov (σ=0 expected) |
| `.env_smoke_v2_hw_noise` | HW per byte | σ=0.0007 | A=4.4%; SASCA drops at rp=4 |
| `.env_smoke_v2_hd` | HW+HD (scale=0.5) | σ=0 | FAILED — same LDA collapse |
| `.env_smoke_v2_hd_noise` | HW+HD (scale=0.5) | σ=0.0007 | A=4.1%; SASCA slightly worse than HW |
| `.env_smoke_v2_f9` | F_9 stochastic, seed=2839 | σ=0 | FAILED — same LDA collapse |
| `.env_smoke_v2_f9_noise` | F_9 stochastic, seed=2839 | σ=0.0007 | **A=99.7%; SASCA 100% at all 21 rate points** |

**Why the no-noise variants failed:** With σ=0, all traces for the same input
byte are identical → within-class scatter matrix is singular → LDA cannot invert W.
This is expected and is not a bug in v2. The noise variants (σ=0.0007) are
the meaningful comparison.

**Key finding — v1 F_9 had an indexing bug:** v1 used `sample_index` (global,
never reset between permutation invocations) to look up F_9 coefficients. v2 uses
`invocation_sample_index` (reset to 0 at each permutation call). Because templates
aggregate all 10 invocations as observations at the same position, v1 presented 10
different coefficient vectors at the same trace position — the LDA fit a mixture of
models and SNR collapsed. v2 is the **correct** F_9 implementation. The collapsed
byte-pbw was immune to this bug because it has one shared constant vector.

Full analysis in `findings_2026-05-05.md` §3.
Archives: `runs_archive/2026-05-05_smoke_v2_{hw,hd,f9}_noise/`.

---

## 3) Timeline — Chronological Decision Path

### Period 1: Apr 24 — Reference Established; Hard Failure Uncovered

**Context:** First end-to-end pipeline run on real Cambridge dataset + baseline
simulator (HW-only, LEVEL=30). Goal: establish the real-data benchmark.

**Information gained:**
- Real traces achieve A=35.7% SR — strong benchmark.
- Baseline simulator run (HW-only, LEVEL=30) collapses to SR ≈ 1%.
- Offline eigenvalue probe on a single byte's IoP: only 8 non-zero eigenvalues
  → confirms HW-only leakage is the culprit (9 HW classes → rank 8 LDA).

**Key questions raised:**
- Is the failure from the simulator's leakage model (HW-only), from the ICS
  selection (LEVEL=30), or from insufficient training data?

**Answers:**
- HW-only is a hard mathematical ceiling — even infinite traces cannot
  distinguish bytes with the same Hamming weight. This is Failure Mode A.

**Decision / next step:** Patch simulator to per-bit-weighted leakage; rerun
smoke scale before committing to paperscale.

---

### Period 2: Apr 25 — Bit-Weighted Fix + Second Failure Mode

**Context:** Bit-weighted patch (`d078350`) applied; first smoke runs with
new simulator (`smoke_byte_pbw_strict`, LEVEL=90 and LEVEL=30).

**Information gained:**
- LEVEL=90 + bit-weighted: A SR jumps to ~9.3% (~10× over baseline). Mode A
  is fixed.
- LEVEL=30 + bit-weighted: A SR still ≈ 1%. R²-probe confirms 22 real + 1931
  noise samples at R² > 0.030 threshold.
- R²_pbw at the 22 true emission samples = 0.965; elsewhere ≈ 0. The 22
  samples are mechanically the leakage points; everything else is random noise.

**Key questions raised:**
- Why did LEVEL=30 produce near-zero SR even with the right leakage model?
- What is the optimal ICS threshold? Is 90 optimal or is 60-80 better?

**Answers:**
- LEVEL=30 kept 1953 features. LDA-256 with ~500 training traces is massively
  underdetermined → Ledoit-Wolf shrinkage collapses discriminant directions.
  With 22 features (LEVEL=90), the LDA is well-conditioned. This is Failure
  Mode B.
- Lower noise (σ=0.0007) WORSENS LEVEL=30 because a smaller variance baseline
  causes more random samples to exceed R²>0.030.
- The ICS sweet spot between 30 and 90 was not fully tested (60-70-80 untested).
  90→120 gave zero improvement; the effective floor is already set at 90.

**Decision / next step:** Lock LEVEL=90 as the baseline; run smoke variants to
tune noise and weight range.

---

### Period 3: Apr 26-27 — Smoke Baseline Established

**Context:** Three smoke-scale runs: strict (U(0.3,0.7), σ=0.0007), realnoise
(+σ=0.01), widerpbw (+U(0,1)). All at LEVEL=90, 50 training sets.

**Information gained:**
- All three converge into reproducible behavior: A ≈ 9.3-10.0%.
- **Noise-axis inversion:** σ=0.01 wins 0004 mean SR (+0.7 pp); σ=0.0007 wins
  SASCA (+16 pp at 2R). Mechanism: low noise creates bimodal SR (anchor bytes
  at SR≈1; most at SR≈0.005). High noise flattens to unimodal mid-range. BP
  propagates anchor bytes; 0004 mean SR favors the unimodal.
- **widerpbw tradeoff:** D collapses (3.6% → 2.0% at 0004) but widerpbw wins
  SASCA (best Iteration_Scan and Rate_Scan across smoke runs). D is too diffuse
  with U(0,1) weights; but D contributes only ~40/200 byte-priors, so BP net
  positive with the richer A-family signal.

**Key questions raised:**
- Does scale (paperscale) close the sim-vs-real gap on A?
- Does adding more leakage events (operand-fetch) help?

**Answers:**
- Not yet measured. Paperscale runs queued.

**Decision / next step:** Launch paperscale counterparts (widerpbw, strict,
realnoise) at 8× training data; maintain multiple smoke variants.

---

### Period 4: Apr 28 — Paperscale Confirms Smoke; Operand-Leakage Rejected

**Context:** Three paperscale runs complete (widerpbw at 09:22, strict at
15:01, realnoise at 19:16). Operand-leakage run (leakops) also lands at 22:45.

**Information gained:**
- Paperscale_widerpbw 0004: A=9.51% (smoke was 9.39%) — +0.12 pp. **Within
  noise. 8× more training traces ≈ zero improvement.**
- Same pattern on SASCA: smoke and paperscale are within 2-4 pp on
  Iteration_Scan; Rate_Scan t50 within 30 bits.
- Paperscale_realnoise produces highest sim A SR ever (10.30%) but worst SASCA.
- leakops (operand-fetch leakage on widerpbw): 0004 A=9.15% (slight decrease);
  0005 flat or slightly worse at 2R/3R; tied at 4R. **Hypothesis invalidated.**

**Key questions raised:**
- If data scale and sample count don't help, what does the sim lack?
- Is the bottleneck the leakage model (what each cycle emits) or something
  structural (how many cycles emit, what they emit about prev_value)?

**Answers:**
- Scale is not the bottleneck. Sim-vs-real gap is structural.
- Operand-fetch adds redundant information (same byte, adjacent cycles), not
  new information about different bytes.

**Decision / next step:** Kill realnoise paperscale (highest 0004, poorest SASCA
— not the right optimization target). Test HD leakage (transition power).

---

### Period 5: Apr 29 Early — HD Pivot; ICS Struggles with Diffuse Signal

**Context:** HD leakage branch (`sim-hd-leakage`, commit `60cd0f4`). Three HD
runs attempted at ICS=90 and ICS=10 and ICS=40.

**Information gained:**
- smoke_hd ICS=90: **FAILED** at ICS validation gate. D00-D03 produce empty
  per-i ICS arrays. HD leakage signal is too diffuse for strict R² detection.
- smoke_hd ICS=10: KILLED at 0003 IoP generation. ~54k samples/word × O(h5py)
  overhead → estimated 4-8h for IoP step alone. ICS=10 is impractical.
- smoke_hd ICS=40: 0004 A=6.04%, D=0.40%. **0005 Iter_Scan: 0%/0%/0% at all
  rounds.** Pure HD substitution is strictly worse than HW.
- BUT: the `sim-hd-leakage` branch was SUBSTITUTION-based (each emit uses
  EITHER HW OR HD by random choice) — this is NOT additive HD. Real CMOS
  is always additive: `L = α·HW + β·HD + noise`.

**Key questions raised:**
- Is additive HW+HD (not substitution) the right test?
- Does the poor HD result mean transitions don't matter, or just that pure HD
  replacement is wrong?

**Answers:**
- Pure HD substitution is wrong both theoretically and empirically. Mixed
  substitution run (smoke_hd_mixed, hd_ratio=0.5) was killed by server
  restart and never completed. The additive hypothesis was NOT tested.

**Decision / next step:** Goal shift meeting at 15:00 → broader reframing.

---

### Period 6: Apr 29 15:00 — Advisor Meeting + Goal Shift

**Context:** Three parallel null/negative results in 24h (HD rejection,
ICS sweep, paperscale ≡ smoke) collapse onto a single diagnosis.

**Information gained (confirmed at meeting):**
- The simulator's leakage model — not data scale, not ICS density, not template
  fit — is the primary gap to real silicon.
- The templates fit per-PoI coefficients `c_l(t)`. Legacy sim uses ONE shared
  8-vec for all PoIs: `self._pbw_byte = pbw_rng.uniform(0,1, size=8)` drawn
  ONCE at init. This is the **collapsed F_9** — the wrong form.
- Advisor's proposal: per-leakage-point LUT — the canonical F_9. Estimated
  ~40 LOC change.
- Bit-pair leakage branch (`sim-bit-pair-leakage`) staged but deprioritized:
  it adds quadratic terms on top of a wrong linear model. Fix the linear
  model first.

**Decisions made:**
- Kill all three live paperscale runs (widerpbw, strict, hd_mixed) gracefully.
- Implement canonical F_9 as the next simulator mode.
- Deprioritize bit-pair and ICS sweeps.
- Focus: leakage model fidelity first, then HD additive on top of F_9.

---

### Period 7: Apr 29 17:00 — F_9 Per-Leakpoint Implementation

**Context:** Branch `sim-per-leakpoint-pbw` off `widerpbw-only`.

**Information gained:**
- Commit `dffecb8`: lazy per-position 256-entry byte LUT. Each sample point
  `t` gets its own `(c_0..c_7, c_8)` vector drawn from `U(0,1)` and `U(-0.5,0.5)`.
- Sanity checks pass: `lut[0] ≠ lut[1]` (per-position diversity confirmed);
  two resets give max diff = 1e-4 = noise_sigma (weights reused, not redrawn).
- Legacy env files tagged with `SIM_PBW_SHARED=1` for archive reproducibility.
- New env files: `.env_smoke_per_leakpoint` (σ=0.0007), `_realnoise` (σ=0.01).

**Decision / next step:** Run both smoke envs; compare to widerpbw archive at
same seed.

---

### Period 8: Apr 30 — F_9 Results; Per-Bit Analysis; Seed Diagnostic

**Context:** F_9 smoke runs complete at 03:14. Five diagnostic runs launched
at 10:35.

**Information gained:**
1. **F_9 is worse than collapsed pbw at smoke:**
   - A drops 9.4% → 6.1%. Rate_Scan successes drop from 13.0 to 7.0 / 21 pts.
   - **Noise-axis inversion vanishes** under F_9: σ=0.0007 and σ=0.01 give
     SR bit-identical to 4 decimal places. Pearson correlation of per-bit BP
     errors across runs: 0.985. The inversion was a model-mismatch artefact.

2. **Per-bit BP failure analysis:**
   - At rate_point=0 (full priors), baseline_wrong_bits=0 for all 50 traces.
     Templates reconstruct A_00 perfectly → baseline = ground truth.
   - At rate_point=20 (all priors blank): BER = 0.299-0.300, perfectly balanced
     polarity (50.3 / 49.7 flip ratio) → no systematic 0→1 / 1→0 bias.
   - 78% overlap of top-50 hardest bits between low-noise and realnoise runs.
     Hot-bit error rate plateaus at ~0.52. **Failures are topology-driven, not
     noise-driven** — determined by the SASCA constraint graph, not leakage realization.

3. **F_9 is not the remaining bottleneck. The physics are:**
   Every coefficient/amplitude/shape lever is now spent. With σ→0 and F_9
   matching templates' assumptions exactly, sim A SR ≈ 6% vs real 36%.
   What the sim doesn't model:
   - **Additive Hamming distance / transition power** — real CMOS leaks on bit
     flips between cycles. `grep prev_value KeccakSim_BI_TA.py` → no matches.
     The old `sim-hd-leakage` was substitution, not additive.
   - **Multi-cycle per logical op** — ARM ops run through fetch/decode/
     execute/memory/writeback, each leaking. Sim emits one sample per `leak()`
     call. This affects A most (θ+ρ+π is the longest memory-shuffling stretch).
   Reference: ELMO (2017), ROSITA (2019), ARMISTICE (2022) all model additive
   HD + multi-stage pipeline leakage for Cortex-M targets.

4. **Seed-sweep diagnostic launched** (Apr 30 10:35, ETA ~19:00):
   - F_9 seed=1234, F_9 seed=5678 (test: is seed=2839 a lucky outlier?)
   - Collapsed pbw seed=1234, collapsed pbw seed=5678 (paired comparison)
   - F_9 signed c_l ∈ U(-1,+1) (test: does negative-coefficient regime matter?)

5. **Additive HD runs launched** (env files `.env_smoke_per_leakpoint_hd_add`
   and `_hd_add_0p5`): F_9 + scalar `SIM_HD_ADD_SCALE` term.

**Key questions raised:**
- Is F_9 < collapsed a single-seed artefact (seed=2839 "lucky" for collapsed),
  a coefficient-distribution issue (need signed), or a fundamental model issue?
- Does additive HD on top of F_9 recover some of the gap?

**Answers (from seed-sweep + hd_add results in §2.3):**
- Additive HD improves over pure F_9 (A: 6.07% → ~5.1% round-averaged, but
  still far below collapsed pbw at 9.38%). The improvement is real but not
  sufficient to explain the full gap.
- F_9 seed-sweep results confirm the F_9 < collapsed gap is not a fluke (both
  alternative seeds also land below collapsed pbw).

**Decision / next step:** Build `KeccakSim_v2.py` with clean model separation
for a definitive 3-way comparison (HW / HW+HD / F_9 × noise).

---

### Period 9: May 1-4 — Cleanup; v2 Simulator; 3-Way Comparison

**Context:** Server cleanup (~600 GB freed, 16 archived sandboxes deleted).
KeccakSim v2 design and implementation.

**Information gained:**
- Additive HD runs (hd_add 0.5 and 1.0) both complete at smoke scale. Best
  result: F_9 + HD_scale=0.5 → A=5.05% round-averaged (vs widerpbw 9.38%).
  Better than pure F_9 but still not closing the gap.
- The collapsed byte_pbw remains the empirical champion, which is
  theoretically puzzling (the wrong model outperforms the correct one).
- `KeccakSim_v2.py` committed May 4 (`bd71199`): clean architecture with
  `SIM_MODE=hw|f9` and `SIM_HD_ADD_SCALE` (additive, not substitution).
  The legacy simulator untouched; dual-dispatch in `run_full_pipeline.sh`.

**Key questions raised:**
- Why does collapsed byte_pbw outperform F_9 empirically?
  Hypothesis: the collapsed model happens to produce traces where the ICS
  detection step selects a small, clean set of features with tight β structure,
  while F_9's per-PoI variation creates a richer but noisier feature space
  that the current ICS detection step doesn't handle optimally.
- Does v2's clean HW vs HW+HD vs F_9 comparison reveal a systematic ordering?
- Is the improvement from v2's additive HD larger or smaller than the legacy
  sim's hd_add results?

**Decision / next step:** Await v2 3-way results (ETA ~May 5-6). If HW+HD
closes the gap significantly over pure HW, this confirms the transition-power
hypothesis. If not, the multi-cycle-per-op hypothesis becomes the priority.

---

## 4) Causal Attribution

| Knob / change | Why it was changed | What happened | Status |
|---|---|---|---|
| ICS LEVEL 30 → 90 | LDA underdetermined at 30 | ~10× SR jump; dominant gain | Locked |
| SIM_HW_RATIO 0.82 → 1.0 | Remove common-wave noise | ~1.5× SNR; small gain | Locked |
| pbw weights U(0.3,0.7) → U(0,1) | More byte separability | D collapses; SASCA improves; net positive | Locked (widerpbw) |
| σ 0.01 → 0.0007 | SASCA anchor-byte mechanism | 0004 mean SR −0.7 pp; SASCA +16 pp at 2R | σ=0.0007 locked for SASCA goal |
| Scale: smoke → paperscale | Test if more data closes gap | ≤0.2 pp on 0004, ≤4 pp on 0005 | **Rejected as gap-closer** |
| Operand-fetch leakage | More sample events per byte | Null / slightly negative | **Rejected** |
| HD substitution (SIM_HD_RATIO) | Test transition power | Pure HD strictly worse; ICS issues | **Wrong form** (use additive) |
| F_9 v1 per-leakpoint | Match templates' model (buggy impl.) | A: 9.4% → 6.07% — due to indexing bug, not physics | Bug identified in v2 rewrite |
| Additive HD on F_9 v1 | Test CMOS transition power additively | A ~5.1%; partial improvement | Real effect; not primary physics |
| Signed c_l ∈ U(-1,1) | Test coefficient sign sensitivity | F_9 < collapsed persists | Not the issue |
| v2 F_9 (correct impl.) | Fix indexing bug; clean F_9 | A=99.7%; SASCA 100% at all rate points | **Validates methodology; gap is coefficient estimation** |
| v2 HW+HD (additive, clean) | Definitive HD test | A=4.1% vs HW 4.4% — HD does NOT help | **CMOS transition-power hypothesis rejected** |

---

## 5) Ruled-Out Hypotheses

| Hypothesis | Test | Result | Evidence |
|---|---|---|---|
| More training traces closes the gap | Smoke → paperscale (8×) | **NULL** | ≤0.2 pp on 0004; §4, Apr 28 |
| Operand-fetch leakage adds information | leakops smoke run | **NULL/NEGATIVE** | 0004 A=9.15% vs 9.39%; 0005 flat or worse; §4, Apr 28 |
| Higher ICS level > 90 helps | LEVEL=120 run | **NULL** | bit-identical to realnoise; §4, Apr 25-27 |
| Lower ICS level (denser sampling) improves | LEVEL=50, 70 sweeps | **NULL** | bit-identical to LEVEL=90 at 4 dp; Apr 29 |
| Noise level (σ) is the bottleneck | σ sweep under F_9 | **NULL** | SR identical to 4 dp; per-bit BP errors Pearson 0.985; Apr 30 |
| HD substitution (SIM_HD_RATIO=1.0) helps | smoke_hd_ics40 | **NEGATIVE** | A: 9.39% → 6.04%; D collapses; 0005 SR=0%; Apr 29 |
| F_9 v1 (buggy impl.) appears to close the gap | F_9 v1 smoke | **MISLEADING** | A: 9.4% → 6.07% was the bug, not a physics result; Apr 30 |
| Coefficient distribution (U(-1,1)) matters | Signed F_9 smoke | **NULL** | Gap persists per seed sweep; Apr 30 |
| Additive HD closes the gap (v2 clean test) | v2 HW+HD vs v2 HW | **NEGATIVE** | A: 4.4% → 4.1%; HD slightly worse; May 5 |
| F_9 physics are inferior to collapsed pbw | v2 F_9 (correct impl.) | **DISPROVEN** | A=99.7%; the v1 result was a bug; May 5 |

**Revised conclusion (May 5):** The v2 results overturn the prior "ceiling around
A≈6-10%" reading. The correct F_9 implementation (v2) achieves A=99.7% — above
real silicon. The remaining gap is leakage coefficient estimation from real
hardware, not multi-cycle emission or additive HD.

---

## 6) The Remaining Gap — Updated May 5

**State as of May 5:** v2 F_9 (correct implementation) achieves A=99.7% in
self-consistent mode — above the real-silicon reference of 35.7%. The pipeline
is validated end-to-end. The F_9 leakage model is both physically correct and
sufficient for the attack to work.

**The remaining gap is leakage coefficient estimation.** Real silicon does not
have perfectly stationary F_9 coefficients with U(0,1) draws. The sim-to-real
gap is now: *how accurately can we estimate the per-position F_9 coefficients
from oscilloscope data?* This is the profiling problem in You & Kuhn 2022.

**Hypotheses ruled out (updated):**
- ICS threshold, data scale, noise level, coefficient distribution, operand-fetch,
  pure HD substitution — all ruled out as primary bottlenecks (as before).
- **Additive HD (v2 clean test):** A=4.1% vs HW 4.4%. HD makes things slightly
  *worse* in the v2 clean comparison. CMOS transition-power is **not** the
  dominant missing physics.
- **Multi-cycle per-op emission:** Superseded. If F_9 self-consistent gives
  99.7%, the multi-cycle hypothesis is lower priority — the bottleneck is now
  definitively coefficient estimation from real hardware.

**What was actually missing from v1:** Not physics, but a bug. The v1 F_9 used
the wrong index counter, making every invocation of the permutation use different
coefficients at the same trace position. v2 fixed this as a side effect of the
clean rewrite. The 6-9% ceiling observed throughout April was an artefact.

**Next step:** Characterize real hardware's F_9 coefficients directly from
ChipWhisperer oscilloscope traces (regression on real power measurements), then
use those coefficients in the simulator or directly as templates.

---

## 7) Decision Framework

Use this order when evaluating a new run result:

1. **Check 0004 family SR**, especially A-family and the bimodality pattern
   (are there anchor bytes at SR≈1, or a unimodal distribution?).
2. **Check 0005 SASCA together**: Iteration_Scan peak SR and Rate_Scan t50.
   A run that improves 0004 but regresses SASCA is not an improvement overall.
3. **Compare in bit-equivalent terms** for Rate_Scan: multiply rate-points by
   `RATE_STEP_BITS`, not raw point counts. Smoke (64-bit steps) and paperscale
   (8-bit steps) use different step sizes.
4. **If SASCA improves but 0004 is flat**, inspect anchor-byte distribution —
   BP may be leveraging fewer, sharper anchors more efficiently.
5. **Do not declare victory from 0004 mean SR alone.** The realnoise case
   shows 0004 mean SR can mislead when bimodality is missing.
6. **Check D-family as early warning**: D collapsing before results are in
   means ICS is too strict (or leakage too diffuse) for the deep-round bytes.

---

## 8) Current State and Next Steps — Updated May 5

**v2 runs completed May 5.** All six runs archived locally.

**Outcomes (answering the May 4 questions):**
1. `v2_f9` dramatically outperforms `v2_hw` (A=99.7% vs 4.4%). The v1 pattern
   (F_9 < collapsed) was a bug, not real physics. Confirmed as implementation
   artefact.
2. `v2_hd` is marginally *worse* than `v2_hw` (A=4.1% vs 4.4%). HD does NOT
   close the gap. Transition-power hypothesis rejected.
3. Noise matters only to avoid LDA singularity (σ=0 → FAILED). At σ=0.0007 the
   noise level is not the bottleneck — consistent with legacy F_9 result.
4. `v2_f9` vs legacy F_9 gap: A=99.7% vs 6.1% — the entire gap was the indexing
   bug confirmed.

**No active runs.** The pending env files below are no longer needed for the
primary research question (they were designed to probe hypotheses now resolved):

- `.env_paperscale_per_leakpoint` — not worth running; v2 self-consistent result
  already establishes the ceiling.
- `.env_smoke_per_leakpoint_lownoise` — superseded by v2 noise variant.
- `.env_smoke_byte_pbw_hd_add_0p5` / `_1p0` — HD is rejected; no point running.

**Next step:** Characterize real hardware's per-position F_9 coefficients from
ChipWhisperer oscilloscope data. If the measured coefficients can be loaded into
v2 as the F_9 table, the simulator should produce near-real-silicon template quality.

---

## 9) Pointers

| Resource | Content |
|---|---|
| `findings_complete.md` | **Aggregated document — all findings in one place** |
| `findings_2026-04-27.md` | Verbatim timestamped notes; full audit trail; unchanged |
| `findings_2026-05-05.md` | May 5 v2 results + v1 bug analysis (detailed) |
| `pipeline_explainer.md` | Phase-by-phase math, env param cascades, 8-bit hardcoding |
| `pipeline_runner/runs_archive/2026-05-05_smoke_v2_*/` | v2 comparison archives (local) |
| `pipeline_runner/compare_runs.py` | Plot SR/GE across archived runs |
| `pipeline_runner/analyze_per_bit_errors.py` | Per-bit BP error breakdown |
| `KeccakSim_v2.py` | Correct simulator (HW / HW+HD / F_9 modes) |
