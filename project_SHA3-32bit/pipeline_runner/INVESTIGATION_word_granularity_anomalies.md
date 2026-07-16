# Investigation: word-granularity (`smoke_v8`) anomalies

Written 2026-07-15. Triggered by the thesis fragment
(`student_thesis/th_fragment-template_on_CROSS_latest.tex`) reporting
word-granularity results that look far worse than the byte-granularity
baselines even at low noise, plus a non-monotonic ID outlier at σ=2.5 that the
author flagged as unresolved. This doc re-derives the numbers directly from
`quality_report` CSVs and live remote pipeline logs — **do not reuse the
numbers currently in the `.tex`**, several of them are stale or based on
partial runs (see below). See `ANALYSIS_granularity_mechanism.md` for the
mechanistic analysis of what byte/word granularity represent and why the §3
"F9 is place-value-like" explanation below is now considered unconfirmed /
likely wrong — that doc supersedes §3's F9 reasoning pending the
verification steps in its §4 / this doc's planned follow-up sweeps.

## 1. Sweep status (as of 2026-07-15 16:32 CEST)

`smoke_v8_granularity_word` = 4 modes (hw, hd, f9, id) × 9 σ values, first-ever
test of the simulator's `--granularity word` mode (1 sample/leak) against the
established `--granularity byte` baselines (4 samples/leak): `smoke_v5` (hw),
`smoke_v7_hd_pure` (hd), `smoke_v6` (f9, id).

| mode | done | still running |
|---|---|---|
| hw | 9/9 | — |
| hd | 9/9 | — |
| f9 | 9/9 | — |
| **id** | **2/9** (σ=0.1, σ=1.0) | σ=0.5, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0 (actively progressing on `IDP`, SASCA rate-scan stage) |

Two of the four id runs present in the local archive (σ=0.5, σ=2.5) were
snapshotted **mid-run** — their `Rate_Scan` prediction counts are 16/100 and
36/100 of target (vs. 100/100 for the two genuinely complete runs) — so their
SR/GE numbers are noisy small-sample estimates, not final results. The
remaining 5 σ values aren't archived at all yet; they don't exist as numbers,
only as in-progress sandboxes.

## 2. Corrected numbers (family A00, byte vs. word)

Pulled directly from each run's `0004_validation/quality_report/summary_family_round.csv`
(row `A00`), not from README "best/worst by score" summaries (family/round
ordering there is inconsistent between runs) and not from the `.tex` draft.

**HW** (byte: `smoke_v5`, ICS 90 / word: `smoke_v8`, ICS 90)

| σ | byte SR | byte GE | word SR | word GE |
|---|---|---|---|---|
| 0.1 | 5.68% | 30.0 | 1.46% | 84.3 |
| 0.5 | 4.56% | 36.8 | 1.37% | 85.4 |
| 1.0 | 3.32% | 46.9 | 1.22% | 88.3 |
| 1.5 | 2.65% | 55.2 | 1.15% | 91.0 |
| 2.0 | 2.24% | 62.3 | 1.08% | 93.2 |
| 2.5 | 1.89% | 69.3 | 1.02% | 95.0 |
| 3.0 | 1.62% | 75.4 | 0.99% | 96.5 |
| 3.5 | 1.42% | 80.6 | 0.95% | 98.1 |
| 4.0 | 1.25% | 85.5 | 0.92% | 99.5 |

**HD** (byte: `smoke_v7_hd_pure`, ICS 40 / word: `smoke_v8`, ICS 40)

| σ | byte SR | byte GE | word SR | word GE |
|---|---|---|---|---|
| 0.1 | 3.70% | 48.4 | 1.49% | 83.3 |
| 0.5 | 2.95% | 52.8 | 1.35% | 85.6 |
| 1.0 | 2.32% | 60.4 | 1.19% | 89.3 |
| 1.5 | 1.94% | 67.7 | 1.09% | 92.3 |
| 2.0 | 1.67% | 74.5 | 1.02% | 94.8 |
| 2.5 | 1.45% | 80.7 | 0.96% | 97.1 |
| 3.0 | 1.27% | 86.1 | 0.92% | 99.1 |
| 3.5 | 1.14% | 90.9 | 0.89% | 101.0 |
| 4.0 | 1.01% | 95.4 | 0.85% | 102.7 |

**F9** (byte: `smoke_v6`, ICS 90 / word: `smoke_v8`, ICS 90)

| σ | byte SR | byte GE | word SR | word GE |
|---|---|---|---|---|
| 0.1 | 86.33% | 1.2 | 6.59% | 37.8 |
| 0.5 | 29.29% | 7.0 | 5.09% | 42.9 |
| 1.0 | 11.04% | 22.2 | 3.64% | 53.0 |
| 1.5 | 6.07% | 36.6 | 2.71% | 62.5 |
| 2.0 | 3.95% | 48.8 | 2.15% | 70.5 |
| 2.5 | 2.80% | 59.4 | 1.76% | 77.1 |
| 3.0 | 2.16% | 68.1 | 1.51% | 82.4 |
| 3.5 | 1.76% | 75.6 | 1.32% | 86.6 |
| 4.0 | 1.48% | 82.1 | 1.19% | 90.1 |

**ID** (byte: `smoke_v6`, ICS 90 / word: `smoke_v8`, ICS 90 — see §4)

| σ | byte SR | byte GE | word SR | word GE | word status |
|---|---|---|---|---|---|
| 0.1 | 50.07% | 29.9 | 2.07% | 115.7 | complete |
| 0.5 | 20.09% | 33.8 | 1.15% | 116.1 | **partial, 16/100 traces** |
| 1.0 | 8.12% | 42.7 | 9.20% | 100.7 | complete |
| 1.5 | 4.42% | 52.3 | — | — | running, not archived |
| 2.0 | 2.95% | 61.1 | — | — | running, not archived |
| 2.5 | 2.09% | 69.4 | 12.31% | 98.7 | **partial, 36/100 traces** |
| 3.0 | 1.63% | 76.4 | — | — | running, not archived |
| 3.5 | 1.38% | 82.1 | — | — | running, not archived |
| 4.0 | 1.21% | 87.1 | — | — | running, not archived |

Note the ID numbers here (word σ=0.1: 2.07%/115.7) differ from the `.tex`
draft's (3.1%/118.9) — the archive was apparently re-captured after the draft
was written. Treat this doc's numbers, pulled fresh from the CSVs just now, as
current ground truth; re-pull again before final write-up since 7 of 9 id
sigmas are still moving.

## 2.5. SASCA comparison, and the real-hardware reference

Triggered by a follow-up question: how do these numbers compare against the
**real-hardware reference** (`runs_archive/reference/2026-06-03_ref_cambridge_downloaded`,
the Cambridge/CARDIS-2021 dataset — the only non-simulated data point we
have)? That archive reports family SR≈35.8%/GE≈9.1 (best, family A) down to
SR≈1.3%/GE≈86 (worst, family D), and SASCA Rate_Scan AUC (`rate_scan_{depth}_B.npy`,
mean/max, same metric `compare_runs.py` uses) of **2R=0.726, 3R=0.900,
4R=0.923**.

Pulling the same AUC metric for every archived σ point, byte vs word, all
four modes (2R/3R/4R; `—` = not yet archived, see §1):

**SASCA Rate_Scan AUC, F9** (byte: `smoke_v6` / word: `smoke_v8`)

| σ | byte 2R | byte 3R | byte 4R | word 2R | word 3R | word 4R |
|---|---|---|---|---|---|---|
| 0.1 | 0.940 | 0.944 | 0.944 | 0.291 | 0.297 | 0.293 |
| 0.5 | 0.821 | 0.945 | 0.936 | 0.219 | 0.220 | 0.218 |
| 1.0 | 0.527 | 0.589 | 0.617 | 0.154 | 0.154 | 0.153 |
| 1.5 | 0.299 | 0.301 | 0.296 | 0.105 | 0.105 | 0.104 |
| 2.0 | 0.185 | 0.183 | 0.183 | 0.075 | 0.075 | 0.075 |
| 2.5 | 0.142 | 0.141 | 0.141 | 0.059 | 0.059 | 0.059 |
| 3.0 | 0.109 | 0.111 | 0.110 | 0.050 | 0.051 | 0.051 |
| 3.5 | 0.080 | 0.080 | 0.080 | 0.044 | 0.044 | 0.044 |
| 4.0 | 0.059 | 0.059 | 0.059 | 0.039 | 0.038 | 0.039 |

At σ=0.1, **byte-granularity F9 exceeds the reference at every depth**
(0.940 vs 0.726, 0.944 vs 0.900, 0.944 vs 0.923) — consistent with the thesis
(`th_fragment-template_on_CROSS_latest.tex:1465`): "F9 achieves near-perfect
AUC at low noise". Byte-granularity F9's 2R AUC drops below the reference's
2R value (0.726) somewhere between σ=0.5 (0.821) and σ=1.0 (0.527) —
consistent with the thesis's "collapses rapidly above σ≈1.0" characterization.
**Word-granularity F9 sits below the reference at every σ, starting at
σ=0.1** (0.291 vs 0.726) — this is the number that prompted the "F9 performs
far worse than the reference" question; see the resolution at the end of §3.

**SASCA Rate_Scan AUC at σ=0.1, all four modes** (byte / word / reference,
2R only shown for brevity — 3R/4R follow the same pattern):

| mode | byte | word | reference (2R) |
|---|---|---|---|
| HW | 0.346 | 0.057 | 0.726 |
| HD | 0.162 | 0.048 | 0.726 |
| F9 | 0.940 | 0.291 | 0.726 |
| ID | 0.718 | 0.026 (partial/unreliable — only 2 σ points archived, see §1) | 0.726 |

Byte-granularity HW/HD sit below the reference even at σ=0.1 — already the
documented, expected outcome (`th_fragment-template_on_CROSS_latest.tex:868`:
"F9 and ID achieving high SASCA success, HW and HD failing"); word
granularity pushes them lower still, but this doesn't change their
qualitative story the way it does for F9/ID.

## 3. Root cause — HW/HD/F9/ID all weaker under word granularity

All four models lose accuracy going from byte to word granularity at every σ,
but by very different factors (byte SR / word SR at σ=0.1):

| mode | byte→word SR ratio at σ=0.1 | byte→word SASCA-AUC ratio at σ=0.1 (2R) |
|---|---|---|
| HD | 2.5× | 3.4× |
| HW | 3.9× | 6.1× |
| F9 | 13.1× | 3.2× |
| ID | 24.2× | 27.6× (partial word data, see §2.5) |

The SASCA-AUC ratio for F9 (3.2×) is much smaller than its SR-based ratio
(13.1×), even though both are measuring the same byte→word degradation. This
is expected: SR/GE average uniformly over every templated intermediate value,
including the many diluted, low-R² ones that word packing produces, so the
metric is dragged down by weak templates in proportion to how many there are.
SASCA/BP instead marginalizes over the whole factor graph — the smaller set
of strong, undiluted templates that do survive the ICS gate can still carry
enough signal to drive successful belief propagation, so the aggregate attack
outcome degrades less sharply than the underlying template-quality average
would suggest. HW/HD don't show this compression (their ratios are *larger*
under AUC than under SR), consistent with them not having a "few strong
templates carry the graph" mechanism — sum-of-bits models don't have the
extreme per-template quality skew that lets a handful of survivors dominate.

**HW/HD's ~3–4× drop is roughly what a 4× reduction in samples/leak point
(byte = 4 samples, word = 1 sample) would predict on its own** — consistent
with a simple information-loss floor, not a bug. Both are sum-of-bits leakage
models (Hamming weight / Hamming distance), where the total leaked information
about a value doesn't depend much on *how* the bits are split across samples.

**F9 and ID lose far more than 4×.** Both are place-value-sensitive models:
F9 assigns each bit a random-but-fixed coefficient (roughly place-value-like
in aggregate), and ID leaks the literal integer value, whose per-bit variance
contribution scales as 2^(2i) (bit i dominates variance by orders of
magnitude over bit 0). `RUN_LOG_granularity_word.md` already documents this:
byte packing (8-bit chunks) has a 128:1 MSB:LSB variance ratio; word packing
(32-bit chunks) has ~2×10⁹:1. At that skew, most bits' individual R² contribution
falls below even the most permissive ICS threshold (level 10, R²>0.01), so a
much larger fraction of the templated intermediate values carry near-zero
signal under word granularity than byte — a genuine, mechanism-explained
degradation, not just sample-count dilution. This is confirmed by the actual
scale of the drop (13×/24× vs. the ~4× baseline HW/HD sets).

**Conclusion**: the "way worse than expected" word-mode results are not a bug
for HW/HD (expected ~4× floor, observed 2.5–3.9×) but are a real, disproportionate
effect for F9/ID tied to place-value leakage packing, as already hypothesized
in the RUN_LOG. Worth stating in the thesis as a genuine, explained finding
rather than an anomaly to fix.

**Resolution of the "F9 performs far worse than the real-hardware reference"
question**: this was a byte/word mix-up, not a new finding about F9's
fidelity. F9 at **byte granularity** — the pipeline's actual default and the
setting used everywhere except this one ablation sweep — *exceeds* the
real-hardware reference at low σ on every metric checked (§2.5), matching the
thesis's existing "near-perfect AUC at low noise" characterization. F9 at
**word granularity** does fall well below the reference starting at σ=0.1,
but word granularity is a deliberately extreme, first-ever ablation (1 leak
sample per 32-bit register write, vs the default 4) introduced specifically
to probe simulator sensitivity — it was never meant to be read as a claim
about how well the F9 model matches real hardware. Comparing the word-mode
numbers against the reference line answers "how sensitive is F9 to this
synthetic packing choice" (answer: very), not "does F9 approximate real
leakage" (the byte-mode comparison already answers that, favorably, at low
noise). See §5 for the corresponding thesis-writeup caution.

## 4. Root cause — ID's non-monotonic σ behavior (the σ=2.5 "outlier")

**The ICS-level-mismatch hypothesis is ruled out.** Live remote logs show
every word-mode ID sigma actually trains against ICS level 30 (the
level 90 threshold fails ICS validation for word-mode ID — confirmed in
`RUN_LOG_granularity_word.md` — and `auto_sweep_monitor.sh`'s unattended
gate-fix corrects each sigma to level 30 independently before training,
regardless of what the sigma's static `.env` file on disk says). The stale
`.env` copies embedded in some local archive snapshots (showing level 90 for
σ=0.1/0.5/2.5) are leftover launcher-template copies, not what was actually
trained on — confirmed by grepping each sandbox's live log for `CHECK:
validating training ICS archive (level=0XX)`, which shows `030` for every
sigma checked. **So level is held constant (30) across the sweep — it is not
the source of the σ=2.5 spike.**

The real pattern, from §2's numbers, using only the two fully-complete runs
(σ=0.1: SR=2.07%; σ=1.0: SR=9.20%) plus the two partial ones (σ=0.5: 1.15%
on 16 traces; σ=2.5: 12.31% on 36 traces): SR is *not* monotonically
decreasing in σ, the opposite of every other mode and of ID under byte
granularity. This is a genuine effect, not (solely) a config artifact — though
the two partial points should be treated cautiously given their small trace
counts (16 and 36 traces produce high-variance SR estimates).

**Leading hypothesis, not yet confirmed**: a structural leak-density
inhomogeneity in the simulator's rotation instrumentation, `leak_ROL32`
(`KeccakSim_v3.py:331-339`, same in `KeccakSim_v2.py:311-319`):

```python
def leak_ROL32(self, a, offset):
    if offset != 0:
        a = int(a)
        res = self.leak_xor(self.leak(a << offset) & 0xFFFFFFFF,
                            self.leak(a >> (32 - offset)) & 0xFFFFFFFF)
    else:
        res = self.leak(a)
    ...
```

For `offset != 0`, a rotation costs **3** `leak()` calls (shifted-left,
shifted-right, xor result) each carrying only part of the value's bits. For
`offset == 0` (a real case in Keccak's rho step — several lanes rotate by 0),
it costs exactly **1** `leak()` call that emits the *entire* 32-bit value
undiluted. This is functionally correct (ROL by 0 is the identity), but for
a literal-value leakage model like ID, an offset-0 lane's single leak point
carries far more information (about the whole word at once) than an
offset-nonzero lane's three diluted leak points. Combined with ICS-threshold
selection at level 30 (only R²>0.03 clock samples survive into templates):
as σ increases, the diluted offset-nonzero features' already-low R² is the
first to drop below threshold, so the *surviving* ICS feature set shrinks
toward being dominated by the strong, undiluted offset-0 features. That
would produce exactly the observed pattern — apparent SR *improving* with
more noise, because the ICS gate is silently curating an increasingly
clean (if smaller) feature set as noise grows, rather than because more
noise genuinely helps the attack.

**Not yet verified. Next steps to confirm/refute:**
1. For the id σ=0.1 and σ=1.0 sandboxes (both complete), pull the actual
   selected ICS clock-sample list at level 30 and cross-reference each
   selected intermediate value against Keccak's rho-offset table — check
   whether the fraction of selected samples coming from offset-0 lanes rises
   from σ=0.1 to σ=1.0.
2. Once σ=1.5/2.0/3.0/3.5/4.0 finish, check whether SR keeps rising
   (consistent with an ICS-curation effect that saturates once only offset-0
   lanes remain) or eventually falls again (would argue against this
   hypothesis, or for a bounded version of it).
3. If confirmed, this is a simulator-instrumentation caveat worth stating
   explicitly in the thesis (ID/F9 place-value models interact with ICS
   thresholding at word granularity in a way that byte granularity mostly
   avoids), not a claim that the identity model becomes more attackable
   under noise.

## 5. Recommendation for the thesis rewrite

- Do not present final HW/HD/F9 word-granularity numbers as final — they are
  already final (9/9 done) — but do present the byte→word ratio finding from
  §3 as an explained result, not an open anomaly.
- Do **not** write up final ID σ-sweep numbers yet: 7 of 9 points are
  incomplete or entirely missing. Either wait for the remaining runs (actively
  progressing; re-run `sh auto_sweep_monitor.sh --family smoke_v8 --modes id
  --status --detailed` on `IDP` to check progress) and re-archive, or if
  writing now, label the table "preliminary, ID sweep 2/9 complete" and drop
  the two partial (16/100, 36/100 trace) points rather than presenting them
  as done.
- Replace the "differing ICS levels" explanation for the σ=2.5 anomaly in the
  draft — that's now ruled out (§4) — with the ICS-curation-of-offset-0-lanes
  hypothesis, clearly marked unconfirmed pending the verification steps above.
- Do not plot or table word-granularity numbers against the real-hardware
  reference line without an explicit "ablation" label. Byte-granularity F9
  already exceeds the reference at low σ (§2.5) — that's the real
  reference-comparison result. Word-granularity numbers falling below the
  reference is a sensitivity-to-packing finding, not a fidelity-to-hardware
  finding; conflating the two is exactly the confusion this investigation
  was triggered by (§3, "Resolution" paragraph).
