# Analysis: what "byte vs. word granularity" actually models

Written 2026-07-15. Companion to `INVESTIGATION_word_granularity_anomalies.md`
(which documents the *numbers* and flags the open F9/ID anomaly) — this doc
works out the *mechanism*, derived in conversation while tracing through
`KeccakSim_v3.py` and the You & Kuhn CARDIS 2021 paper
(https://www.cl.cam.ac.uk/~mgk25/cardis2021-sha3.pdf, the basis of this
project's whole methodology, cited in both project READMEs). Do not merge
this into the investigation doc — that doc is about resolving a specific
numeric anomaly; this one is about what the granularity knob represents,
which is a prerequisite for interpreting those numbers correctly.

## 1. Real hardware leaks as a continuum, not discrete word/byte/bit samples

Fig. 3 of the paper (p.13) plots real measured R² curves for the four bytes
of one 32-bit lane (`α'_0[0,0,0..3]`), captured on the actual
STM32F303RCT7/Cortex-M4 target at 2.5 GS/s (500 points per clock cycle).
The four curves are continuous, overlap substantially, and each peaks at a
*different* time offset within the same clock cycle — but none of them is
zero elsewhere in that window. In other words: at any single real time
sample, the raw voltage/EM signal almost certainly carries information about
more than one byte simultaneously, just in different proportions depending
on the time offset. Fine oscilloscope resolution doesn't hand you a sample
that is purely "byte 0" — it hands you many correlated samples, each a
different mixture of all 32 bits, some of which happen to be byte-0-dominant.

The paper's fragment-template method (LDA projecting onto the top
eigenvectors of Σ⁻¹B, restricted to one byte's inter-class scatter) is the
machinery that hunts across those overlapping real samples for a projection
that best isolates one fragment's signal. It is a *statistical* separation
performed on physically-mixed data, not a *physical* separation that exists
for free in the trace.

## 2. What the simulator's granularity modes actually are

Contrast the above with `KeccakSim_v3.py:_leak_signal` (lines 264–302).
Byte mode:

```python
cur = [((value >> s) & 0xFF) for s in (0, 8, 16, 24)]
for i, b in enumerate(cur):
    sig = ...   # function of b (8 bits) ONLY
    self._emit(sig)   # + one independent Gaussian noise draw
```

Each of the four emitted samples is a pure function of *one byte's 8 bits*.
The other 24 bits of `value` are never read when constructing that sample.
There is no "compute the full leak, then discard 24 bits as noise" step —
those 24 bits were never combined into the sample in the first place.

Word mode combines all 32 bits' contributions into a single scalar before
emitting one sample.

So the two modes are **not** literally "how real 32-bit hardware leaks."
They are two idealized bracketing approximations of the real continuum
described in §1:

- **Byte mode** ≈ the optimistic limit where LDA/dimensionality-reduction has
  already achieved *perfect* per-byte separation, as if there really were
  four physically disjoint sample points, each carrying exactly one byte's
  bits and nothing else.
- **Word mode** ≈ the pessimistic limit where *zero* separation is
  achievable — as if the scope had only one sample per cycle, forced to mix
  all 32 bits into one scalar.

Real hardware + real LDA processing sits strictly between these two
extremes (which is why the paper's own measured success rates in Tables 2–5
are well below 100%, not near it, even with byte fragment templates on real
traces). The pipeline's real-world performance on physical traces should be
expected to fall somewhere between the byte-mode and word-mode simulated
numbers — neither bound is "the realistic one" on its own.

## 3. Why word mode is worse: confound variance, not information deletion

For a linear/weighted-sum leakage model (`sig = Σ c_l·bit_l + intercept`,
which covers HW with `c_l=1` and F9 with `c_l ~ U(0, bit_coeff_scale)` i.i.d.
per bit — confirmed in `generate_f9_table`, `KeccakSim_v3.py:57–89`, no
place-value scaling by bit index in either mode):

- **Byte mode**: the sample used to template byte *i* is a function of
  exactly that byte's 8 bits + measurement noise σ². Intra-class scatter
  Σ_f = σ² only.
- **Word mode**: the same sample also contains the other 24 bits' random
  coefficient-weighted contributions. Those contribute extra *within-class*
  variance for whatever byte you're trying to classify — the paper calls
  this "switching noise" (p.9) in the context of real hardware, but the
  identical algebraic structure appears here for a different reason (the
  simulator chooses to combine 32 bits into 1 sample, rather than physics
  forcing it). Σ_f = σ² + Var(other 24 bits' contribution).

With coefficients of comparable expected magnitude at every bit position (no
place-value skew), the other-byte contribution is a fixed variance ratio —
roughly 24:8 = 3:1 relative to the target byte's own signal variance,
**structurally the same for HW and F9**, since both are unweighted-in-position
sums. This predicts HW and F9 should degrade by similar factors under word
granularity. The observed sigma-sweep data instead show HW/HD at 2.5–3.9×
(matching a simple 4× sample-count floor reasonably well) but F9 at 13× and
ID at 24× — a gap this confound-variance argument alone does not explain.
ID's 24× has a confirmed, different mechanism (literal place-value leak,
`RUN_LOG_granularity_word.md:89-98`). **F9's 13× currently has no confirmed
mechanism** — the investigation doc's "F9 is roughly place-value-like"
explanation is contradicted by the coefficient-generation code (i.i.d. per
bit) and by the run log's own explicit statement that F9 is not subject to
the place-value dilution mechanism. This is the open question the plan in
§4 below is designed to resolve.

## 4. Leading unconfirmed hypothesis for the F9 gap

A nonlinear **ICS-threshold cliff**: if F9's byte-mode per-bit R² values
happen to sit closer to the selection threshold than HW's do, an equal
~3× confound-driven SNR reduction could tip a much larger fraction of F9's
features below threshold — dropping them from the template set entirely
(binary exclusion) rather than degrading them gracefully — while HW's
per-bit R² values (already either comfortably high or low) rarely cross
that boundary. Unconfirmed; see the verification plan below.
