# Proposal: multi-sample "emission kernel" for word-level leakage

Written 2026-07-15. Follow-up to `ANALYSIS_granularity_mechanism.md` and
`INVESTIGATION_word_granularity_anomalies.md`. This is a design proposal for
a **separate planning/implementation session** — nothing here has been
implemented, and the parameter choices below are placeholders, not
recommendations. Read the two companion docs first; this one assumes their
conclusions (byte/word mode as bracketing idealizations, confound-variance
explanation for word-mode degradation, unresolved F9 13x gap).

## 1. The idea

Goal restated: the simulator should keep leaking at **word granularity**
(a real 32-bit system leaks the whole word, not byte-isolated fragments —
byte mode is an optimistic idealization, not a target to reproduce), but
should be made more realistic in a way that moves pipeline outputs
(R²/ICS detection -> LDA templating -> SASCA) closer to results on real
hardware.

Current mechanism gap: in `KeccakSim_v3.py:_leak_signal`, every leak event
(byte or word) emits **exactly one sample** (`self._emit(sig)` called
once). Real acquisition (Fig. 3 of the You & Kuhn CARDIS 2021 paper, p.13,
2.5 GS/s / 500 samples per clock cycle) never does this — one logical leak
event produces *many* correlated raw samples, each a different linear
mixture of the leaking bits, because each byte's physical contribution
peaks at a different time offset within the cycle. The pipeline's own
ICS-selection stage exists specifically to handle "many correlated samples
per event," and the paper's fragment-template LDA operates on the
resulting multi-sample feature vector, not on a single scalar. So the
one-sample-per-event assumption is a simplification that exists in the sim
today for *both* granularity modes; word mode just suffers from it more
visibly because there's no per-byte fallback to compensate (see
`ANALYSIS_granularity_mechanism.md` §3 for why word mode's single mixed
sample carries ~3x confound variance relative to byte mode).

Proposed fix: for word-granularity leak events, emit **N samples** across a
small window instead of one, where each sample's per-byte weight follows
an envelope `e_b(t)`, e.g. a shared kernel shape with a distinct peak
offset per byte (4 staggered peaks across the window, mirroring the 4
staggered curves in Fig. 3):

```
signal(t_i) = Σ_b  e_b(t_i) · leak_fn(byte_b bits)  +  noise(t_i)     for i in 1..N
```

`leak_fn` is unchanged — still whichever leakage model is active (HW, F9,
ID, HD). The kernel is a new, orthogonal mechanism layered on top.

### Why this is different from (and better motivated than) the earlier "decaying kernel" idea

An earlier version of this idea proposed spreading a single word-leak
event's signal over ~1000 samples, scaled down over time (pure amplitude
decay, same mixing weights at every offset). That version was **rejected**:
repeating an *identical* linear combination of all 32 bits at multiple
offsets (just attenuated) gives the pipeline only redundant noisy copies of
one number. R²-based ICS selection would gravitate to the few near-peak
samples and discard the shallow tail, so the decay shape would end up
mostly irrelevant to outcomes — and even if it didn't, averaging identical
copies only improves SNR by sqrt(N), it can never separate byte 0's
contribution from byte 1's, because every sample has the same mixing
vector (rank-1 across the window).

The per-byte-offset kernel proposed here is qualitatively different: each
sample is a **different** mixture of the 4 bytes (different weight
vector), which is what actually allows a linear projection (LDA) to
(partially) invert the mixing and recover byte-specific information — the
same statistical-separation mechanism the paper's fragment templates rely
on for real, physically-mixed hardware traces. This also directly answers
the "give the pipeline more information about *when* whole words leak"
framing: staggered per-byte peaks are literally timing information about
sub-word structure, encoded the same way Fig. 3's real curves encode it.

## 2. Where this fits in the model taxonomy

This is **not** a fifth leakage model alongside HW/F9/ID/HD. Those describe
the *value -> signal* function (what property of the bits is leaked).
This proposal describes a different axis: how one logical leak event maps
onto the *number and temporal-mixing structure* of emitted trace samples.
Proposed framing:

- **Leakage model** (`--leakage-profile`: HW/F9/ID/HD) — the data
  dependency of a single sample.
- **Granularity** (`byte`/`word`) — which bits get pooled into a sample.
- **Emission kernel** (new axis, e.g. `--emission-kernel {single,word-mix}`)
  — how many samples one leak event produces, and how per-byte weights
  vary across them. `single` = current behavior (one sample, equal
  implicit weight to all bits). `word-mix` = the N-sample staggered-kernel
  behavior proposed above.

This keeps the three axes composable and independently testable, rather
than conflating "how the leak value is computed" with "how it gets
smeared across the trace."

## 3. Is this realistic, or just engineered to fix word-mode's bad numbers?

Worth stating both sides plainly for whoever picks this up:

**In favor of "real gap, not a rescue":** the one-sample-per-event
assumption is a pre-existing simplification independent of the word-mode
degradation problem — it exists in byte mode too, it's just less costly
there because byte mode already gives each byte's classifier a clean,
unconfounded sample. Fixing it addresses a documented mismatch between the
sim's acquisition model and the paper's actual acquisition model (500
samples/cycle, multi-sample fragment templates), not a symptom that only
shows up when word-mode numbers look bad.

**Risk to guard against:** the specific kernel shape, window length, and
per-byte offset spacing are currently based on eyeballing a single figure
(Fig. 3) with no extracted coordinates. There's a real risk of tuning these
free parameters until the F9/word gap "looks fixed," which would be
circular (see the open, still-unconfirmed F9 13x-vs-HW 2.5-3.9x gap in
`ANALYSIS_granularity_mechanism.md` §3-4 — this proposal does not resolve
that anomaly and shouldn't be treated as if it does until checked).
Mitigating this requires picking parameters *before* looking at pipeline
outcomes (see open questions below), and treating "did the F9 gap change"
as a result to explain, not a target to hit.

## 4. Open questions for the planning session

1. **Parameter source.** Can actual (x, y) coordinates be extracted from
   Fig. 3 (digitizing the plot) to fit `e_b(t)` and offsets empirically,
   rather than guessing? If not, what's the fallback for picking N, kernel
   width, and offset spacing without implicitly reverse-engineering them
   from desired pipeline outcomes?
2. **Kernel shape.** Gaussian vs. triangular vs. something paper-derived —
   does the choice materially change downstream results, or is only the
   "distinct offsets per byte" property load-bearing? (If the latter, favor
   the simplest shape — fewer free parameters, easier to reason about.)
3. **Noise model across the N samples.** Independent per-sample noise (as
   assumed above) vs. correlated/shared noise across the window — real
   scope noise at 2.5 GS/s is not independent sample-to-sample. Does
   independence change ICS behavior in a way that matters here?
4. **Interaction with ICS selection.** With N samples per event and 4
   staggered peaks, how many of those N samples are expected to clear the
   R² threshold in practice, and does that count give LDA enough
   dimensionality to actually separate bytes, or does it still collapse to
   a small number of near-peak samples? This should be checked with a
   small-N smoke test before committing to a larger sweep.
5. **Compute/storage cost.** N samples per word-leak event multiplies trace
   width for the affected operations — what's an acceptable N given
   existing pipeline runtime/storage budgets (see `smoke_v8`
   byte-vs-word precedent for scale)?
6. **Scope of application.** Does `word-mix` apply to every word-level leak
   primitive (`leak_xor`, `leak_and`, `leak_ROL32`, etc. — see
   `KeccakSim_v3.py:304-339`) uniformly, or only specific ones first for a
   smoke test?
7. **Relationship to the open F9 anomaly.** Should this be sequenced
   before or after resolving the F9 13x-gap investigation
   (`ANALYSIS_granularity_mechanism.md` §4, ICS-threshold-cliff
   hypothesis)? Implementing a new mechanism on top of an unexplained
   anomaly makes it harder to attribute any change in results to either
   cause.

## 5. Non-goals

- Not aiming for 100% physical realism — the goal is "closer to reference
  pipeline outcomes than flat word mode," not a faithful EM/power model.
- Not replacing byte mode or word (`single` kernel) — this is an additional
  mode/axis for comparison, per the project's existing pattern of keeping
  bracketing idealizations (byte, word) alongside more realistic
  intermediate variants (see `smoke_v8` granularity precedent).
- Not intended to resolve the F9-vs-HW word-mode degradation-gap anomaly by
  construction; any effect on that gap should be treated as a result to
  investigate, not a success criterion.
