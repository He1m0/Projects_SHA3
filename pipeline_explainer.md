# SHA-3 Template-Attack Pipeline — Code, Math, Env Parameters, Fragment-Size

**Companion to `findings_2026-04-27.md`** (which records the simulator/sandbox tuning results). This file explains the system itself: what each phase does, the math behind it, how env parameters control behavior, and where the 8-bit byte-fragmentation is baked in.

Repo root: `/home/muri/Documents/Uni/IDP/Projects_SHA3/`. Active project: `project_SHA3-32bit/`. The reference paper attack targets a 32-bit ARM Cortex-M4 implementation of Keccak-f[1600] in **bit-interleaved** form. The "8-bit byte fragmentation" is the consequence of attacking each 32-bit word as **4 byte fragments × 256 classes** rather than the full 32-bit word at once (`2^32` classes is intractable).

---

## High-level flow

```
0001 reference  →  0002 detection  →  0003 training  →  0004 validation  →  0005 SASCA  →  0006-0011 per-algorithm attack
   (ref trace)     (find ICS)         (LDA templates)   (SR / GE / scores)   (BP scans)      (full SHA3-X recovery)
```

Three artifact types flow forward:

| From → To | Artifact | What |
|---|---|---|
| 0001 → 0002, 0003, 0004 | `ref_trace.npy` | Mean trace; correlation gating |
| 0002 → 0003, 0004, 0005, 0006 | `ics_original_NNN.zip` | Sample indices where R²(byte ⇒ trace) crosses threshold NNN/100 |
| 0003 → 0004, 0005, 0006 | `templateLDA_ONNN.zip` | Per-byte LDA (eigenvecs + class means + scov) |
| 0004 → diagnostics | `Result_Tables.zip`, `quality_report/` | Mean SR / GE per byte / score / label |
| 0005 / 0006 → diagnostics | `Iteration_Scan_*`, `Rate_Scan_*`, `Recovered_Data` | BP convergence + final recovery |

Every phase's behavior is parameterized through `project_SHA3-32bit/global_config.py`, with each constant overridable via `SHA3_*` env. `pipeline_runner/run_full_pipeline.sh` copies the chosen `.env_*` profile to `.env` so each phase's `script_all.sh` reads the same settings. Simulator profile knobs are `SIM_*` (read by `KeccakSim_BI_TA.py`).

---

## 0001_reference

### Substep — reference trace
- File: `0001_reference/Code_reference/get_reference.py:32-51`
- Inputs: raw `.bin` traces, `INPUTS × INVOCATIONS × REFERENCE_FOLDERS` of them (paperscale: 16 × 10 × 2 = 320)
- Outputs: `ref_trace.npy` shape `(REFERENCE_TRACE_LEN,)` = (55296,) at paperscale
- What it does: mean of all reference traces.
- Math: `Ref = (1/N) Σ trace_i`
- Env: `SHA3_INPUTS`, `SHA3_INVOCATIONS`, `SHA3_REFERENCE_FOLDERS`, `SHA3_REFERENCE_TRACE_LEN`
- Fragment-size: not used here.

### Substep — correlation filter
- File: `0001_reference/Code_reference/get_corr.py:30-76`
- Inputs: `ref_trace.npy` + the same raw set
- Outputs: `corrcoef.npy` (Pearson ρ per trace)
- Math: `ρ(T_i, Ref) = Cov / (σ_T σ_Ref)`. Outliers flagged outside `mean ± 4σ`.
- Env: same as above.

The point of 0001: define the canonical "good trace" so later phases can drop outliers and the simulator can be sanity-checked against this shape.

---

## 0002_detection

### Substep — preprocessing & QC
- File: `0002_detection/Code_preprocessing/pre_processing.py:27-81`
- Inputs: `Raw/Raw_DN_*.zip`, `data_in.npy`, `data_out.npy`, `ref_trace.npy`
- Outputs: `Processed_DN_*.hdf5`, shape `(INPUTS × INVOCATIONS, DETECTION_OUTPUT_SIZE)` = (160, 55296)
- What it does: validates I/O via SHA3-512 (lines 28-40), resamples each trace by aggregating `SAMPLE_WIDTH` consecutive samples spaced `DETECTION_PPC` apart (lines 69-73), correlates against ref.
- Math: `Sample[s] = Σ_k Trace[OFFSET + s·PPC + k]`. Reject if `ρ < CORR_BOUND`.
- Env: `SHA3_DETECTION_TRACE_LEN`, `_SET_COUNT`, `_SETS_PER_PART`, `_TRACE_OFFSET`, `_PPC`, `_OUTPUT_SIZE`, `_CORR_BOUND`, `_SAMPLE_SHIFT`, `_SAMPLE_WIDTH`.

### Substep — combine partitions
- File: `0002_detection/Code_preprocessing/combine.py:19-76`
- Stacks `Processed_DN_*` into `part_NN.hdf5` of `SETS_PER_PART × set_size` rows.

### Substep — intermediate values + bit-packing
- Files: `0002_detection/Code_intermediate_values/get_invoc_io.py`, `get_invoc_intermediate.py`, `intermediate_H2B.py`
- What it does:
  - `get_invoc_io.py:44-68` — runs Keccak-f[1600] sponge `INVOCATIONS` times; pulls state at each round boundary.
  - `get_invoc_intermediate.py:44-152` — extracts state at the θ "intermediate points" labelled A, B, C, D, E. Tags A/B/E → 200 bytes (25 lanes × 8 bytes per lane fragment); tags C/D → 40 bytes (parity columns × 8 bytes). For DETECTION_ROUNDS=4 we accumulate 4 sets of these.
  - `intermediate_H2B.py:16-42` — converts each hex byte → 8-bit float vector. **`Tr_Mat = [[128],[64],...,[1]]`** (line 16) and **`for bt in range(0, 8)`** (line 31) are the first hardcoded 8-bit assumptions.

### What the A/B/C/D families mean
Each Keccak-f[1600] round runs five transformations: **θ → ρ → π → χ → ι**. The pipeline taps four specific points along that chain and treats them as separate template targets (canonical reference: `Kec_f1600_inter()` in `get_invoc_intermediate.py:44-117` — look for the `Output point: X` comments).

| Family | Pipeline position | Bit width | Byte width | Role |
|---|---|---|---|---|
| **C** | inside θ, after column XOR | 320 | 40 | per-column parity vector `CB` (5 lanes × 64 b) |
| **D** | inside θ, after column rotation | 320 | 40 | diffused column `DB` used to update the state |
| **A** | after θ + ρ + π | 1600 | 200 | full state right *before* χ |
| **B** | after θ + ρ + π + χ | 1600 | 200 | full state right *after* χ (round output, before ι) |

(There is also an unused **E** = state right after θ alone; defined in code but not part of the active attack path.)

Tag naming: `<Letter><Round>` like `A00`, `B03`, etc. The two-digit suffix is the **round index** 0..3 (controlled by `SHA3_DETECTION_ROUNDS=4`).

The `i00`, `i01`, … suffix on `A00_i37`-style filenames is the **bit-interleaved 32-bit word index** within the family at that round:
- A and B: 1600 b ÷ 32 = **50 words** → indices i00…i49 (`SHA3_DETECTION_ICS_WORDS_AB=50`)
- C and D: 320 b ÷ 32 = **10 words** → i00…i09 (`SHA3_DETECTION_ICS_WORDS_CD=10`)

That's why the `validate_training_ics_archive` report shows `A: ?/50, B: ?/50, C: ?/10, D: ?/10` — those denominators are word counts, not arbitrary numbers.

**Why these four points specifically:**
- **C** and **D** are linear in θ (XOR-only). Templates here have very clean structure but a small target space (320 b) — useful sanity check, low absolute information yield.
- **A** is post-π = post-bit-permutation. Diffuses C/D's information across the full state — useful crossroads for SASCA's belief propagation.
- **B** is post-χ — the only **nonlinear** step in Keccak. Recovering B-bytes is the most valuable for SASCA because χ is what defeats algebraic attacks; if you can profile χ-output bytes you've got the bridge into the next round's input.

The headline numbers in the findings doc (`A=9.39%, B=3.4%, C=3.7%, D=2.0%` for smoke widerpbw) reflect this asymmetry: A SR is highest because A sits right after a permutation (state diffusion → leakage spread across many sample points). B is hardest because χ scrambles per-byte signal. D is the deep-round canary — small target space, smallest bit count, first to die when sim leakage doesn't make it through to the late rounds.

### Substep — R² detection
- File: `0002_detection/Code_detection_R2/get_corrcoef.py:24-67`
- For each output sample t in the resampled trace, fits a per-byte linear regression `Ŷ_t = β₀ + Σ β_i b_i(t)` (8 features, the 8 bits of the byte) and computes `R²(t) = 1 − SS_res/SS_tot`. Word-level R² = sum of 4 byte R²s.
- Outputs: `detect_results_08/TAG_r_squ_b{byte:03d}.npy` and `detect_results_32/TAG_r_squ_i{word:03d}.npy`.
- **Hardcoded:** line 54 `for byte in range(4*ints, 4*ints+4)` and line 64 `np.sum(Scores, axis=0)` over the 4-byte block.

### Substep — ICS extraction
- File: `0002_detection/Code_extract_ics/ics_detect.py:14-32`
- For each TAG, each word index, each threshold τ ∈ `SHA3_DETECTION_ICS_THRESHOLDS`, save `{t : R²(tag, word, t) > τ}` into `ics_TAG_iWWW.npy`. Thresholds get archived as `ics_original_010.zip`, `ics_original_020.zip`, …, `ics_original_090.zip`.
- The downstream `SHA3_TRAINING_ICS_LEVEL` knob picks which archive to consume — the **dominant tuning knob** in our experiments.

### What R² means here
For each sample point in the trace, R² is the fraction of variance explained by a *linear* function of the 8 target bits. High R² ⇒ that sample carries information about the byte under leakage assumptions consistent with HW/HD or per-bit linear leakage. ICS_LEVEL trades off recall vs. precision: lower threshold → more samples per byte (higher recall, more LDA features, easier to overfit); higher threshold → fewer, sharper samples.

---

## 0003_training

### Substep — preprocessing
- File: `0003_training/Code_preprocessing/`
- Same as 0002 but on TR (training) zips, output `Processed_HDF5/Processed_*.hdf5`.
- Total rows = `SET_COUNT × INPUTS × INVOCATIONS` = 400×16×10 = 64000 at paperscale.
- Env: `SHA3_TRAINING_SET_COUNT`, `_TRACE_OFFSET`, `_PPC`, `_OUTPUT_SIZE`, `_CORR_BOUND`.

### Substep — intermediate values
- Same `intermediate_H2B.py` machinery → `intermediate_values/intermediate_B_TAG/TAG_b{byte:03d}.npy`, shape `(64000, 8)`.

### Substep — IoP discovery (`get_IoPs.py`)
- File: `0003_training/Code_find_IoPs/get_IoPs.py:35-52`
- Args 0..3 = which byte block (the round/state slice).
- For each ICS index k, extract a window `[k·ICS_WINDOW : (k+1)·ICS_WINDOW]` from each processed trace, where `ICS_WINDOW = DETECTION_PPC // TRAINING_PPC`.
- Output: `IoPs/Ints_TAG_iNNN.hdf5`, shape `(64000, ICS_WINDOW × |ICs|)`.
- The "I" in IoP — Iso-Power-Curves / Interesting Points — names the per-trace projection onto the candidate sample set found in 0002.
- Env: `SHA3_TRAINING_ICS_LEVEL` (selects which `ics_original_NNN.zip` archive), implicit `ICS_WINDOW = DETECTION_PPC / TRAINING_PPC`.

### Substep — LDA template profiling (`Template_profiling_round.py`)
- File: `0003_training/template_profiling_bytes/Template_profiling_round.py:29-76`
- Iterates `for byte in range(4*word, 4*word+4)` (line 86) — **the 4-fragments-per-32-bit-word assumption**.
- Per byte:
  1. **Linear regression** over `(IoP_traces, InterBits)` to predict expected power per bit pattern (line 38).
  2. **Between-class scatter** `B = (E_full − E_½)ᵀ(E_full − E_½)` where E_½ is the prediction at "all-bits-0.5" (the centroid). (lines 42-43)
  3. **Within-class scatter** `W = (Re_Traces − E)ᵀ(Re_Traces − E)` (lines 45-46).
  4. **Generalized eigenvalue problem** `B v = λ W v` solved via `Target = W⁻¹ B`, eigendecomposition, keep eigenvectors with normalized eigenvalue > 1e-5 (lines 50-51).
  5. **Per-class means** projected: `Expects = predict(Bits) · A` for all 256 byte values (line 72).
  6. **Regularized covariance** in LDA subspace: `Σ̂ = AᵀWA / (N − DOF)` with `DOF = TEMPLATE_LDA_DOF = 9` (8 bits + intercept) (lines 64-65).
- Output per byte: `templateLDA_ONNN/template_TAG/template_TAG_avts_b{byte:03d}.npy` (eigenvectors, shape `(IoP_dim, k_lda)`), `..._scov_b...npy` (regularized cov, `(k_lda, k_lda)`), `..._expect_b...npy` (256-class projections, `(256, k_lda)`).
- Math summary: this is **Fisher LDA on a regression-derived class-mean estimator**, not a per-class empirical mean — that's the trick that lets it work at 256 classes with 64000/256 ≈ 250 traces each.

**Why LDA after a regression?**
A naive per-class empirical mean over 256 classes would need many traces per class. The linear-regression model under per-bit leakage `L = β₀ + Σ βᵢ bᵢ + ε` gives a closed-form prediction for any byte value from far fewer traces, then LDA finds the subspace where these 256 predicted means are most separable relative to the residual noise W. **This is also why our simulator's leakage model matters so much**: if the simulator's leakage isn't well approximated by a linear-in-bits function, the regression step is mis-specified and the resulting templates underperform vs. the linear-approximation real-data templates.

### 0003 env summary

| Env var                                   | What it controls                                                                            |
| ----------------------------------------- | ------------------------------------------------------------------------------------------- |
| `SHA3_TRAINING_SET_COUNT`                 | training data density (rows = SC×INPUTS×INVOC)                                              |
| `SHA3_TRAINING_TRACE_LEN`, `_OUTPUT_SIZE` | resampled trace dimension                                                                   |
| `SHA3_TRAINING_PPC`                       | sample resampling stride                                                                    |
| `SHA3_TRAINING_CORR_BOUND`                | reject low-correlation training traces                                                      |
| `SHA3_TRAINING_ICS_LEVEL`                 | which 0002 ICS archive flows in (the **dominant knob**)                                     |
| `SHA3_TEMPLATE_LDA_DOF`                   | DOF subtracted in `Σ̂` denominator (default 9)                                              |
| `SIM_*` (sim only)                        | influences what training traces look like; matched-to-real isn't always best (see findings) |

---

## 0004_validation

### Substep — preprocessing + intermediate values
- Same `pre_processing.py` and `intermediate_H2B.py` but applied to TS (test/validation) zips.
- Total rows = `VALIDATION_SET_COUNT × VALIDATION_INPUTS × INVOCATIONS` = 40×10×10 = 4000 at paperscale.

### Substep — template validation (`Template_validate_LDA.py`)
- File: `0004_validation/template_validation_bytes/Template_validate_LDA.py:69-95`
- Loads template (A, Σ̂, μ for all 256 classes) for each byte. For each validation trace:
  1. Build IoP from ICS indices (same as training).
  2. Project: `Xm = IoP · A`.
  3. Score every class via Mahalanobis: `ℓ(c) = exp(−½ (Xm − μ_c)ᵀ Σ̂⁻¹ (Xm − μ_c))` (line 84).
  4. Sort classes by ℓ; record rank of the *true* byte value into `Rank_ONNN/rank_TAG_b{byte:03d}.npy`.

### Substep — SR + GE tables
- Files: `draw_table_SR.py`, `draw_table_GE.py`
- **Success Rate**: fraction of traces where rank == 0 (line 43, draw_table_SR.py).
- **Guessing Entropy**: `GE = 1 + (Σ rank) / N` — average #guesses needed (line 43-44, draw_table_GE.py).
- A "score" (visible in `quality_report/report.txt`) is a derived per-byte composite (SR weighted by something) that the table sorts on; "weak/excellent" labels come from thresholding it.

### What 0004 tells you
SR_mean across all 200 bytes (A/B states) is the headline number. **Bimodality matters**: a few bytes hitting SR ≈ 1 (anchors) is more useful for SASCA than uniformly mediocre SR — anchor bytes pin down state, and BP propagates from there. We saw exactly this in the smoke-strict experiments: lower SR_mean but much better SASCA than realnoise.

### 0004 env summary

| Env var | Controls |
|---|---|
| `SHA3_VALIDATION_SET_COUNT`, `_INPUTS` | how many test traces |
| `SHA3_VALIDATION_TEMPLATE_TAG`, `_ICS_TAG` | which 0003/0002 archives to evaluate |
| `SHA3_VALIDATION_PPC`, `_OUTPUT_SIZE`, `_TRACE_OFFSET`, `_CORR_BOUND` | mirror training side |
| `SHA3_VALIDATION_ICS_WINDOW = DETECTION_PPC // VALIDATION_PPC` | derived |

---

## 0005_SASCA

### Subdirectory layout

```
0005_SASCA/
├── bit_table_generation/         # produces Bit_Tables/Tables_INP/, _A00..A03, _B00..B03, _C00..C03, _D00..D03
├── Iteration_Scan_2R/, _3R/, _4R/    # convergence vs. BP iterations
├── Rate_Scan_2R/, _3R/, _4R/         # SR vs. unknown-bit budget (data rate)
└── plot_scans/                       # final figures
```

Dependency: `bit_table_generation/` runs first (consumes 0004 + templates + ICS). Both scan families consume those tables in parallel (default — see `--serial-scans` flag).

### Substep — `bit_table_generation/get_tables.py`
- File: `0005_SASCA/bit_table_generation/get_tables.py:39-99`
- For each TAG (`A00..A03`, `B00..B03`, `C00..C03`, `D00..D03`, `INP`):
  - Load LDA template (covInv, A, μ, ICs) for each fragment of that block.
  - For each validation trace, compute byte-level posterior `P(byte | trace)` via Mahalanobis on Xm (line 81-94, `Guess(Trace)`), shape `(256, 1)` per byte.
  - **Marginalize 256-byte posterior → 8 bit-marginals** via precomputed `Bits_O / Bits_Z` matrices in `marginalization.py:2-14`. This is the bridge from "256-class softmax over a byte" to "two probabilities per bit". Output: `(2, 1600)` table per TAG (or per partial state for C/D).
- Saved as `Bit_Tables/Tables_TAG/table_{trace}.npy`.

### Substep — Iteration scan
- File: `0005_SASCA/Iteration_Scan_2R/Iteration_scan.py:26-36` (driver), `SASCA_2R.py` (factor graph), `SASCA_scan.py:11-56` (BP scheduler).
- Sweeps iteration count 0 → `SASCA_ITERATION_COUNT`. After each iteration count, reads marginals, hard-decides each bit at threshold 0.5, compares to ground truth.
- Output: success vector indexed by iteration. Used to pick a sensible `RATE_BP_ITERATION_COUNT`.

### Substep — Rate scan
- File: `0005_SASCA/Rate_Scan_2R/Rate_scan.py:35-117`
- For each rate point `r ∈ {0, 1, 2, …, RATE_POINT_COUNT-1}`:
  - `unknown_bits = min(r · RATE_STEP_BITS, 1600)`.
  - Reset INP block's leftmost `unknown_bits` to uniform `0.5` (the attacker's null prior).
  - Run BP for `RATE_BP_ITERATION_COUNT` iterations.
  - Check if recovered bits ≤ `ALLOWED_WRONG_BITS`. Save `success_RRRR.npy`.
- `RATE_POINT_COUNT × RATE_STEP_BITS` should bracket 1600 (the full state) — at `201 × 8 = 1608` we cover the whole range.

### The factor graph

Variable nodes: bit-level state at each round boundary post-θ.
- `A_variable` (1600 bits = full Keccak state)
- `B_variable` (1600 bits)
- `C_variable` (320 bits = column parities)
- `D_variable` (320 bits = parity differences)

Factor nodes:
- **θ factor** (`THETA_factor_first/second/third`, lines 256-275 of SASCA_XR.py): XOR-tree over column parities. The factor graph cuts θ into three sub-factors so the 5-input enumeration `Σ_{t1,t2,t3,t4} Q1·Q2·Q3·Q4·QC[parity]` stays tractable.
- **χ factor** (`CHI_factor`, lines 387-424): the only nonlinear step. 5-bit input enumeration `(x ⊕ ((¬y) ∧ z))` per row, runs over `2^5 = 32` hypotheses.
- **ι** (round constants): absorbed implicitly via input rotation in the factor initialization.
- **ρ/π**: deterministic permutations; just index manipulation, no explicit factor needed.

Belief Propagation = sum-product on this graph:

```
m_{F→V}(x_V) = Σ_{x_other} φ_F(x_V, x_other) · ∏_{V'∈N(F)\V} m_{V'→F}(x_{V'})
```

The graph has loops (BP on Keccak isn't tree-structured), so this is **loopy BP** — no convergence guarantee, but works well empirically on this graph. No explicit damping; messages are fully replaced each iteration.

### Bit-interleaved representation

Keccak-f[1600] has 25 lanes × 64 bits each. The 32-bit ARM port stores each 64-bit lane as **two 32-bit halves**: even-indexed bits in one word, odd-indexed bits in the other (`x_even = x[0,2,...,62]`, `x_odd = x[1,3,...,63]`). This is the standard bit-interleaving trick to avoid 64-bit shifts on a 32-bit MCU.

Why it matters for the attack: a leakage byte spans 8 bits of one 32-bit word, which corresponds to 4 even-indexed and 4 odd-indexed bits of two lanes (interleaved). Templates implicitly learn this mixing — and the simulator must produce traces with the same mixing pattern, otherwise templates trained on the simulator won't generalize.

### 4R / 3R / 2R

The leakage is observable for the first few Keccak-f rounds (post-θ, before χ destroys 1-bit information across the lane). 4R = leak 4 rounds → most info → fastest BP convergence. 2R = leak 2 → least info, hardest. Templates (0003) profile *all* leaking rounds; the SASCA scan picks how many to actually wire into the factor graph.

### 0005 env summary

| Env var | Default | Controls |
|---|---|---|
| `SHA3_SASCA_TRACE_COUNT` | 1000 | number of attack traces |
| `SHA3_SASCA_ITERATION_COUNT` | 40 | iteration scan cap |
| `SHA3_SASCA_RATE_BP_ITERATION_COUNT` | 200 | BP iterations per rate point |
| `SHA3_SASCA_RATE_POINT_COUNT` | 201 | resolution of rate sweep |
| `SHA3_SASCA_RATE_STEP_BITS` | 8 | step size in bits |
| `SHA3_SASCA_OUTPUT_BITS` | 512 | known output (sponge capacity) |
| `SHA3_SASCA_ALLOWED_WRONG_BITS` | 0 | success threshold (Hamming) |
| `SHA3_SASCA_TEMPLATE_TAG`, `_ICS_TAG`, `_PPC` | — | which archives to evaluate |

---

## 0006_test_SHA3_512 (and 0007–0011)

### Purpose

While 0005 is a *simulated* attack on training-style data (a feasibility scan over rounds and rates), **0006 is the actual end-to-end attack**: take the trained templates, point them at *new* traces from a real SHA3-512 invocation, recover the input plaintext.

### Layout

```
0006_test_SHA3_512/SHA3_512_I0X/
└── template_attack_SHA3_512_NR_I0X/       # N ∈ {1,2,3,4} rounds, X ∈ {1,2} instances
    ├── init.sh            # unzip ics_original_NNN, templateLDA_ONNN, raw I/O
    ├── pack.sh            # archive Recovered_Data, Iterations, Success
    ├── clean.sh
    ├── get_tables.py      # per-trace Mahalanobis → byte posterior  (modified in working tree)
    ├── marginalization.py # 256-byte → 8-bit marginal              (8-bit hardcoded)
    ├── SASCA_XR.py        # factor graph (same shape as 0005 SASCA_XR) for X = N rounds
    ├── SASCA_scan.py      # BP scheduler (200-iter cap)
    ├── SASCA_Procedure.py # the attack driver
    └── KECCAK.py          # reference Keccak-f for cross-check (Back_Theta, Back_RhoPi)
```

### Substep — `init.sh`
- Reads `SHA3_VALIDATION_ICS_TAG` (or fallback `SHA3_TRAINING_ICS_LEVEL`) and `SHA3_VALIDATION_TEMPLATE_TAG`, formats them as 3-digit zero-padded.
- Unzips: `ics_original_NNN.zip`, `templateLDA_ONNN.zip`, `data_raw_in/`, `data_raw_out/`.
- Creates `Recovered_Data/`, `Iterations/`, `Success/`.

### Substep — `SASCA_Procedure.py` (lines 1-199)
1. Initialize Template_A/B/C/D for each of the `ROUND` rounds (lines 31-46). `ROUND` is hardcoded per directory: `1R_I01` → ROUND=1, `4R_I02` → ROUND=4.
2. For each test input (1000 of them):
   - Pull the corresponding processed validation trace.
   - Per-byte template guess → 256-class posterior.
   - 8-bit marginalization → bit table.
   - Run loopy BP via `SASCA_scan.State_Scan` with up to 200 iterations.
   - Reconstruct full state, undo `θ`/`ρ`/`π` via `KECCAK.py:Back_Theta` / `Back_RhoPi`.
   - Compare recovered input bits to ground truth (`data_raw_in/`); strip Keccak padding bytes (`0x86`, `0x80`).
   - Save recovery outcome into `Recovered_Data/recovered_inputs_XXXX.npy`, BP iterations used into `Iterations/iteration_XXXX.npy`, hit/miss into `Success/success_XXXX.npy`.
3. Across multiple invocations (the `I01` vs `I02` directories represent linked invocations) the output state of one invocation is the input state of the next, allowing chained attacks.

### Math
- Per-byte likelihood: same Mahalanobis as 0004.
- Marginalization: same as 0005.
- BP: same loopy sum-product as 0005, but **rounds parameter** is now N (1..4) instead of fixed.
- Reconstruction: invert linear Keccak ops on the recovered state to back out the input.

### 0007–0011 differences

These attack alternative SHA-3 family members **using the same templates and same SASCA machinery as 0006**, since Keccak-f[1600] is identical for all family members. Differences are *only* sponge constants:

| Phase | Variant | Capacity c | Rate r | Output |
|---|---|---|---|---|
| 0006 | SHA3-512 | 1024 | 576 | 512 b |
| 0007 | SHA3-384 | 768 | 832 | 384 b |
| 0008 | SHA3-256 | 512 | 1088 | 256 b |
| 0009 | SHA3-224 | 448 | 1152 | 224 b |
| 0010 | SHAKE256 | 512 | 1088 | XOF |
| 0011 | SHAKE128 | 256 | 1344 | XOF |

The factor graphs are **bit-for-bit identical**; only the input "known capacity" portion and output reading length differ. Demonstrates template **transferability** across the SHA-3 family.

### 0006 env summary

| Env var | Controls |
|---|---|
| `SHA3_VALIDATION_ICS_TAG` (or `SHA3_TRAINING_ICS_LEVEL`) | which ICS archive to load |
| `SHA3_VALIDATION_TEMPLATE_TAG` | which template archive to load |
| `SHA3_SASCA_PPC` | derives `VALIDATION_ICS_WINDOW` |
| `ROUND` | **NOT env-driven** — hardcoded by directory name |
| `INVOC` | hardcoded by directory name |

---

## How env parameters cascade — running example

Using `.env_paperscale_best` (the running paperscale realnoise config):

```
SHA3_INPUTS=16, _INVOCATIONS=10, _REFERENCE_FOLDERS=2
  → 0001 averages 320 traces → ref_trace.npy

SHA3_DETECTION_SET_COUNT=10, _PPC=1, _OUTPUT_SIZE=55296, _ICS_THRESHOLDS=0.09..0.01
  → 0002 produces ics_original_010.zip ... _090.zip

SHA3_TRAINING_SET_COUNT=400, _PPC=1, _OUTPUT_SIZE=55296, _ICS_LEVEL=90
  → 0003 reads ics_original_090, builds templateLDA_O090.zip

SHA3_VALIDATION_SET_COUNT=40, _ICS_TAG=90, _TEMPLATE_TAG=90
  → 0004 reads templateLDA_O090, writes Result_Tables.zip + quality_report/

SHA3_SASCA_TRACE_COUNT=1000, _RATE_POINT_COUNT=201, _RATE_STEP_BITS=8, _RATE_BP_ITERATION_COUNT=200
  → 0005 produces 201 success_*.npy per round per scan; full sweep covers 1608 ≥ 1600 bits

SIM_NOISE_SIGMA=0.01, SIM_HW_RATIO=1.0, SIM_LEAKAGE_GRANULARITY=byte-bitweighted, SIM_SEED_PBW=2839
  → simulator generates "realnoise" traces; SIM_LEAKAGE_GRANULARITY chooses byte-level
    per-bit-weighted stochastic leakage (the regression model the templates expect)
```

---

## Where the 8-bit fragmentation is hardcoded

Comprehensive list, grouped by *what* the constant is doing.

### 1) Bit-packing: 8 bits per byte

| File | Line | What |
|---|---|---|
| `0002_detection/Code_intermediate_values/intermediate_H2B.py` | 16, 31-37 | `Tr_Mat=[[128],...,[1]]`, `for bt in range(0, 8)`, `bits = [-1.0]*8` |
| `0003_training/Code_intermediate_values/intermediate_H2B.py` | 16, 44-45 | same |
| `0004_validation/Code_intermediate_values/intermediate_H2B.py` | 16, 44-45 | same |

### 2) 4 fragments per 32-bit word

| File | Line | What |
|---|---|---|
| `0002_detection/Code_detection_R2/get_corrcoef.py` | 54, 64 | `for byte in range(4*ints, 4*ints+4)`, `np.sum(Scores, axis=0)` |
| `0003_training/template_profiling_bytes/Template_profiling_round.py` | 86 | `for byte in range(4*word, 4*word+4)` |
| `0004_validation/template_validation_bytes/Template_validate_LDA.py` | 51 | `ints = byte // 4` |
| `0005_SASCA/bit_table_generation/get_tables.py` | 66, 91 | `for frag in range(0, 4*self.Size)`, `range(4*ints, 4*ints+4)` |
| `0006_*/get_tables.py` | 46, 71 | same pattern |

### 3) 256-class enumeration

| File | Line | What |
|---|---|---|
| `0003_training/template_profiling_bytes/Template_profiling_round.py` | 27, 72 | `Bits.npy[:,0:8]`, `Expects = predict(Bits) · A` over 256 rows |
| `0004_validation/template_validation_bytes/Template_validate_LDA.py` | 83-92 | `np.ones((256, 1))`, ranking loop over 256 |
| `0005_SASCA/bit_table_generation/get_tables.py` | 94, 97 | `np.ones((256, 1))`, `np.arange(256.0)` |
| `0006_*/get_tables.py` | 71, 75 | same |
| `*/marginalization.py` | 3-8 | `Marginalization(bit_size=8)`, `for t in range(0, 8)` |
| `0004/draw_table_SR.py`, `_GE.py` | 41 | `byte = 8*lane + bt`, loops over 8 |
| `*/Bits.npy` | (data) | shape `(256, 8)` |

### 4) LDA degrees-of-freedom

| File | Line | What |
|---|---|---|
| `global_config.py` | (search) | `SHA3_TEMPLATE_LDA_DOF=9` (8 bits + intercept) |
| `Template_profiling_round.py` | 64-65 | `Scov = ... / (Total_Tnum - LDA_DOF)` |

### 5) Implicit (architecture-dependent, fixed by spec)

- Lane = 64 bits = 8 bytes (Keccak spec)
- State = 1600 bits = 200 bytes (Keccak spec)
- 32-bit word = 4 bytes (target architecture)
- Bit-interleaved layout: 64-bit lane → two 32-bit halves (target architecture)

The first three are *spec-fixed* and not changeable. The fragment-size knob really lives in **how we split the 32-bit word into target classes**: today 4 fragments × 8 bits × 256 classes; could be 2 × 16 × 65536 (likely intractable due to per-class data needs) or 8 × 4 × 16 (smaller targets, finer factor graph). The `frag-bits-env` branch implements an `SHA3_FRAGMENT_BITS` env knob that derives these constants centrally — see that branch's commit messages for the design and migration plan.

---

## What this means for the simulator

The big picture from `findings_2026-04-27.md` maps onto this pipeline as follows:

- **`SIM_LEAKAGE_GRANULARITY=byte-bitweighted`** + **`SIM_SEED_PBW`** → produces traces whose leakage is *exactly* the per-bit linear model `L = β₀ + Σ βᵢ bᵢ + ε` that 0003's regression step assumes. That's the headline reason this granularity outperforms the older HW-only / common-wave models. As of `sim-per-leakpoint-pbw` (Apr 29), each PoI now also draws its **own** `(c_0..c_7, c_8)` instead of reusing one shared 8-vector — the canonical F_9 form (You & Kuhn 2022 §2.1; orig. Schindler/Lemke/Paar 2005). Verified bit-exact correct.
- **`SIM_NOISE_SIGMA`** → controls residual `ε` magnitude, which feeds 0003's W (within-class scatter). Under F_9 with σ ∈ {0.0007, 0.01} the per-byte SR is bit-identical to 4 dp and per-bit BP errors correlate at 0.985 — i.e. **noise is no longer a bottleneck at the smoke noise levels we test**. The earlier "noise-axis inversion" (low-noise → 0004 worse / 0005 better; reversed at high noise) was a model-mismatch artefact under collapsed pbw and disappears under F_9.
- **`SIM_HW_RATIO`** → amplitude scale of the leakage signal vs. common-wave background. At 1.0 (no common wave) the signal is in the linear bit terms; at 0.82 the common wave eats 18 % of amplitude.
- **`SIM_COMMON_WAVE_SCOPE=invocation`** → variance structure across invocations (not bytes). Affects W in the same direction as σ but not the same way as the per-bit β.
- **`SHA3_TRAINING_ICS_LEVEL`** → the *non-simulator* dominant knob. Determines how many sample points per byte template get. ICS sweep (Apr 29 widerpbw_ics50/70/90) confirms ICS_LEVEL is **not** the bottleneck once any halfway-decent selection exists — null result across all 16 (family, round) cells.

### The real-vs-sim gap is *not* about coefficients any more

Until Apr 29 the sim story was "we need a better per-bit linear model." That's done. F_9 templates fit per-PoI 9-vec exactly, sim emits per-PoI 9-vec exactly. **Yet sim A SR ≈ 6 % vs real ≈ 36 %.** The remaining gap is therefore not in *what each leakage cycle says*; it's in **which cycles leak at all** and **how those cycles relate temporally**. Concrete missing physics our sim ignores:

1. **Hamming distance / transition power** — real CMOS gates dissipate proportionally to the number of bits that **flip** between cycles, not to the absolute bit-pattern. Our `_emit_sample_*` functions take only the current `value`; there is no `prev_value` reference anywhere (`grep prev_value KeccakSim_BI_TA.py` ⇒ nothing). `SIM_HD_RATIO` exists on `sim-hd-leakage` branch but only as a **replacement** for HW, not an additive component (`smoke_hd_ics40` test Apr 29 with HD=1.0 made A *worse*, but a fair test mixes HW + HD; that mixed run was killed before completion and has not been re-run on top of F_9).
2. **Multi-cycle per logical op** — a 32-bit ARM op runs through fetch / decode / execute / memory / writeback, each with its own pipeline-register leakage. Real captures sample several cycles per op. Our sim emits exactly one sample per `leak()` (4 per word in byte-bitweighted, 1 in word-bitweighted). The 55 k-sample budget per trace is filled by **many ops × few samples each** in sim vs **fewer ops × many samples each** in reality. This affects A most because θ + ρ + π is a long stretch of memory-shuffling per byte, where real silicon emits the most multi-stage leakage and sim emits the least relative density.
3. **Microarch fingerprints** — pipeline forwarding paths, register-file read-port leakage, cache line traffic, branch-history register state. Untested in any axis; probably 2nd-order to (1) and (2).

### What we've already ruled out as the bottleneck

- ICS_LEVEL (sweep null, Apr 29).
- Noise level (F_9 σ-axis bit-identical, Apr 30).
- Coefficient-distribution shape (F_9 implementation faithful; whether U(0,1) vs U(-1,+1) matters is the in-flight Apr 30 `signed` test, but the cap for any coefficient-only fix is bounded above by the collapsed-pbw run, which already runs the same pipeline at full per-PoI fit and gets A=9.4 % — still 4× short of real).
- Operand-fetch leakage (`leakops`, Apr 28 — null; the added samples carried bit-mixes too similar to result samples).
- Pure HD-only leakage (Apr 29 — strictly worse than HW; but mixed HW + HD on top of F_9 never tested).

**Bottom line**: the simulator interface to the pipeline is `0001/Raw/` zips + `data_in.npy` + `data_out.npy`. Improvements that change the *amplitude / shape* of each emitted sample (`SIM_*_PBW*`, `SIM_NOISE_*`, `SIM_HW_RATIO`) are now spent. The remaining lever is **how many samples per byte op are emitted, and what each sample depends on** — i.e. add multi-cycle per-instruction leakage and additive HD on top of HW, not yet-another-coefficient-distribution.

For the fragment-size sweep: the simulator's per-bit weights (`SIM_SEED_PBW`) need to **stay realistic** at 4-bit fragments: each 4-bit fragment uses 4 of the 8 bit-weights from a byte. Fragment size 4 should "just work" with current sim. Fragment size 16 (cross-byte) would require the simulator to model leakage *across* current byte boundaries, which it currently doesn't.
