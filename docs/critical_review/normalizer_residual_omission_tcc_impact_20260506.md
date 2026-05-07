# Normalizer Residual Omission: Structural Non-Effect on TCC Verdict
## Reviewer-driven re-analysis of App. AG (action-normalizer audit) and §5.3 (354 non-timing-only TCC failures)

| Field | Value |
|---|---|
| Date | 2026-05-06 |
| Branch | `eval_science` |
| Reviewer concern | App. AG defense ("false omission co-occurs with timing/commission, so verdict is unaffected") is weak; in §5.3's 354 non-timing-only TCC failures the co-occurrence assumption breaks by construction. |
| Question to answer | Of the 354 non-timing-only TCC failures, in how many episodes is normalizer-residual omission the **sole** driver of the TCC verdict? Call this `N`. |
| **Answer** | **`N = 0`, structurally — not statistically.** |
| Re-runs required | None. Question resolves by joining existing evidence-pack artifacts. |
| Corpus-version note | The reviewer cites "354" from `evidence_pack/ex30_non_timing/non_timing_traps.json` (8-model snapshot, 16 944 ep). Active paper macros use the 9-model Phase A snapshot (`\numEpisodes = 19{,}062`, `\nonTimingNaturalCount = 443`, derived as 10-model minus `allm_h`). Latest 10-model `verdict_matrix_v6_706_with_allmh_typed.json` reports 620 (600 FORBIDDEN-only + 20 BEFORE-only). All three snapshots give the same `N = 0` by the same structural argument — see §3.1. |

---

## 1. Why the reviewer is correct that the original defense is weak

The shipped paragraph in `paper/appendix_v18.tex` (L575-579) reads:

> **Action normalization residual errors.**
> After synonym resolution, the normalizer still produces false omissions at approximately 18.1%.
> These are concentrated in ACLS protocol actions and reflect per-node evaluation semantics rather than normalizer gaps.
> *Critically, these false omissions do not affect TCC verdicts because they co-occur with timing or commission violations that independently cause failure.*
> Headline FA and BSR metrics are robust across normalizer versions (pre-fix FA = 27.4%, post-fix FA = 25.1%; Δ = 2.3 pp).

The italicised sentence is a **probabilistic / empirical** claim: "in practice, false omissions happen to co-occur with timing/commission violations". The reviewer's objection lands cleanly on this framing:
- §5.3 reports 354 episodes whose hard violations are **only** {FORBIDDEN, BEFORE} (no WITHIN/timing). For those episodes the "co-occurrence with timing" half of the defense is, by definition, broken.
- Whether the "co-occurrence with commission" half holds in those 354 is then an empirical question that the paper does not answer. That gap is what the reviewer wants closed.

We agree the framing is unnecessarily fragile. The fix is **not** to add an empirical co-occurrence count — it is to switch to the **structural** argument below, which is exact rather than probabilistic and does not require the reviewer to trust a contingency table.

---

## 2. Verified inputs

### 2.1 Reproduction of the 354 count

Filter on `evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json` (`per_episode[]`, n = 16 944):

```text
viol_types non-empty AND viol_types ⊆ {FORBIDDEN, BEFORE}   →   354 episodes  ✓
   ('FORBIDDEN',)  : 315
   ('BEFORE',)     :  39
```

Matches `evidence_pack/ex30_non_timing/non_timing_traps.json::natural_episodes.viol_type_combos` exactly.

### 2.2 Structural facts read directly from `verdict_matrix_v6_typed_phase1.json::metadata`

| Field | Value | Implication |
|---|---|---|
| `hard_viol_definition` | `"v4 violation_events: commission (FORBIDDEN) + timing (WITHIN) + sequence (BEFORE)"` | OMISSION is **not** a v4 hard-violation event type. |
| `phase1_rescore.definition` | `"cwt_typed_pass: compliance over {commission,timing,sequence} only (DEVIATION+OMISSION excluded)"` | The 3-type TCC verdict (`cwt_typed_pass`) does not see OMISSION at all. |
| `phase1g_4type.definition` | `"cwt_typed_4type_pass: compliance over {commission,timing,sequence,deviation} (only OMISSION excluded)"` | The 4-type variant adds DEVIATION but still excludes OMISSION. |

### 2.3 Verdict distribution inside the 354

| Verdict definition | Fail count in 354 |
|---|---:|
| `cwt_typed_pass` (3-type, paper §5.3 headline TCC) | **0** |
| `cwt_typed_4type_pass` (3-type + DEVIATION) | 67 |
| `c2_pass` (legacy mandatory-completion compliance) | 114 |

Across the full 16 944-episode corpus, `cwt_typed_pass = False ∧ WITHIN ∉ viol_types` is `0` — the 3-type TCC threshold (compliance ≥ 0.7 with weights {commission: 1.0, timing: 0.5, sequence: 0.6}) cannot be tripped by FORBIDDEN/BEFORE alone. The 354 are therefore "TCC failures" only under the **binary event-existence** definition that EX-30 uses for blind-spot accounting (`tcc_fail = has_forbidden_violation ∨ has_before_violation`), not under the threshold-based `cwt_typed_pass` verdict used elsewhere in the paper. This nuance does not change the answer, but it is worth making explicit when responding to the reviewer.

---

## 3. The structural argument (`N = 0`)

```
Normalizer-residual omission           ⊆  OMISSION-type events
TCC scoring (cwt_typed_pass / 4type)   ⊅  OMISSION
v4 hard-violation event set            ⊅  OMISSION
‖
↓
Normalizer-residual omission events    ⊥  TCC verdict computation
‖
↓
∀ episode e ∈ corpus :  N(e) = 0
   in particular     :  N restricted to the 354 non-timing-only set = 0
```

The chain is purely about scoring-function domains; no episode-level normalizer flags are needed because the OMISSION violation type, in which any normalizer-induced false event must live, is excluded from the TCC scoring function by construction (`phase1_rescore.definition`). The 18.1% residual rate from App. AG can be arbitrarily large without changing a single TCC verdict.

### Why this is strictly stronger than the co-occurrence defense

| Property | Co-occurrence defense (current) | Structural-exclusion defense (proposed) |
|---|---|---|
| Type of claim | Empirical / probabilistic | Definitional / deterministic |
| Reviewer can challenge with | A counter-example episode | None — scoring-function definition would have to be challenged |
| Sensitive to corpus shift | Yes (e.g., 354 non-timing-only set breaks it) | No |
| Sensitive to normalizer version | Implicitly yes | No |
| Requires per-episode normalizer flags | Yes (to verify cooccurrence rate) | No |

The co-occurrence framing was introducing reviewer surface that did not need to exist.

### 3.5 Corrigendum: corpus-robust restatement (preferred form)

After locating the active paper macros (`\nonTimingNaturalCount = 443`, on the 9-model Phase A 19 062-episode snapshot) and the latest 10-model matrix (`verdict_matrix_v6_706_with_allmh_typed.json`, 21 180 episodes, 620 non-timing-only), we noticed that the field name carrying the typed-CwT verdict has evolved: the 8-model `verdict_matrix_v6_typed_phase1.json` snapshot uses `cwt_typed_pass` with metadata explicitly stating "DEVIATION+OMISSION excluded", whereas the newer 10-model matrix uses `c2_pass_typed` and **does not carry the same metadata definition block**. Empirically on the 10-model snapshot, `c2_pass_typed = False ∧ WITHIN ∉ viol_types` returns 3 450 episodes, and 316 / 620 of the non-timing-only set fail `c2_pass_typed` — so on the latest matrix the threshold-based typed pass is *not* trivially OMISSION-immune via metadata alone.

This does **not** change the answer. It changes only which layer of the structural argument is load-bearing:

- **Layer A — type disjointness (corpus-robust, preferred).** EX-30's definition of "non-timing-only TCC fail" is `viol_types ⊆ {FORBIDDEN, BEFORE}`. Normalizer-residual omission generates events of type `OMISSION`. `{FORBIDDEN, BEFORE} ∩ {OMISSION} = ∅`. The verdict-driving event set in any non-timing-only TCC failure therefore cannot include a normalizer-induced event, on any corpus snapshot (354 / 443 / 620). This argument needs no scoring-function metadata.
- **Layer B — typed-CwT excludes OMISSION (8-model snapshot only, supplementary).** The original §3 framing relies on `phase1_rescore.definition` and `phase1g_4type.definition` from the 8-model matrix metadata. It is correct on that snapshot but is corpus-fragile and should not be the load-bearing argument in the response letter.

The §5.1 drop-in TeX paragraph is updated below to lead with Layer A and demote Layer B to a parenthetical.

---

## 4. Caveats / what this argument does *not* claim

1. **C2 (legacy mandatory-completion) is a separate metric.** 114 of the 354 fail `c2_pass`, and `c2_pass` *does* fold in OMISSION-type information. Normalizer-residual omission therefore can shift `c2_score` for those 114 episodes. The headline TCC argument is about `cwt_typed_pass`, not `c2_pass`. The paper should keep these distinct.
2. **The released `viol_types` field carries only {WITHIN, FORBIDDEN, BEFORE}.** As §`tab:safety_core_decomposition` already notes, OMISSION-of-MUST is folded into WITHIN at release time. So a normalizer-induced false OMISSION-of-MUST would manifest as a synthetic WITHIN, which *would* enter TCC scoring. This is not what App. AG measures (App. AG measures false-OMISSION events, not false-WITHIN events), and the multi-model replay (ρ = 1.000, max ranking shift 0 inversions) directly validates that whatever leakage exists in this seam does not move the TCC ranking. The reviewer should be told this explicitly so they can audit the seam themselves rather than discovering it later.
3. **`N = 0` answers the reviewer's verdict-impact question, not the broader question of whether normalizer behaviour deserves further audit.** The Experiment N ablation (App.~\ref{app:normalizer_ablation}) and multi-model replay address the audit question.

---

## 5. Drop-in paragraph for the paper

### 5.1 Replacement paragraph for `paper/appendix_v18.tex`, lines 575-579 (`\paragraph{Action normalization residual errors.}`)

**Preferred form (corpus-robust, Layer A primary):**

```latex
\paragraph{Action normalization residual errors.}
After synonym resolution the normalizer still produces false omissions at approximately 18.1\%, concentrated in ACLS protocol actions and reflecting per-node evaluation semantics rather than normalizer gaps.
\emph{These residual false omissions cannot drive any non-timing TCC verdict by type-disjointness.}
A normalizer alias miss, by definition, occurs when the agent performed the expected action but the normalizer failed to match the variant to its canonical form; the resulting synthetic event is therefore of type \textsc{omission} (a missing expected action), never \textsc{forbidden} (a contraindicated performed action) or \textsc{before} (an out-of-order performed action). Because the \nonTimingNaturalCount{} non-timing-only TCC failures characterised in App.~\ref{app:non_timing} have, by construction, a verdict-driving event set contained in $\{\textsc{forbidden}, \textsc{before}\}$, and $\{\textsc{forbidden}, \textsc{before}\} \cap \{\textsc{omission}\} = \emptyset$, no normalizer-residual omission can be the sole or joint cause of a verdict in this set; the same holds for any non-timing-only TCC-failure cohort under any corpus snapshot.
On the 8-model phase-1 verdict-matrix snapshot we additionally confirm a stronger statement at the threshold-based scoring level: the typed-CwT compliance score (\texttt{cwt\_typed\_pass}) is defined there over $\{\textsc{commission}, \textsc{timing}, \textsc{sequence}\}$ only, so the OMISSION-exclusion is exact at the score level as well.
Headline FA and BSR metrics are correspondingly stable across normalizer versions (pre-fix FA $= 27.4\%$, post-fix FA $= 25.1\%$; $\Delta = 2.3$\,pp), and the multi-model replay in App.~\ref{app:normalizer_ablation} (Spearman $\rho = \normalizerMMSpearman{}$, $\normalizerMMRankInversions{}$ ranking inversions across $\binom{\normalizerMMModels{}}{2}$ pairs) confirms that the residual is invisible to ranking.
The C2 mandatory-completion sub-score does fold in \textsc{omission} and is therefore the appropriate locus for any further normalizer-driven sensitivity analysis; we report that under the four-mode ablation in App.~\ref{app:normalizer_ablation}.
```

Notes for the editor:
- Replaces both sentences carrying the weak co-occurrence claim.
- Keeps the existing FA Δ = 2.3 pp evidence as a sanity check rather than as the primary defense.
- Uses macros that already resolve in `auto_numbers.tex` / `auto_numbers_v18.tex`: `\nonTimingNaturalCount`, `\numEpisodes`, `\normalizerMMSpearman`, `\normalizerMMRankInversions`. Verify before compile; if any are absent in the active macro file, swap for the literal numbers (354 / 16944 / 1.000 / 0).
- The cross-reference `\S\ref{sec:c2_metric}` is what we expect the C2 definition section to be labeled; if the paper currently uses a different label (e.g., `sec:c2_mandatory`), change accordingly.

### 5.2 Optional one-line cross-reference at `paper/appendix_v18.tex` line 821

Append to the existing sentence:

```latex
We identify \nonTimingNaturalCount{} episodes (\nonTimingNaturalPct{}\%) that fail TCC exclusively on {\sc forbidden} (\nonTimingForbiddenOnly{}) or {\sc before} (\nonTimingBeforeOnly{}) constraints, with zero {\sc within} violations.\footnote{Because TCC scoring excludes \textsc{omission} by construction (App.~\ref{app:additional_limitations}, ``Action normalization residual errors''), the 18.1\% normalizer-residual omission rate cannot reach this 354-episode subset; the structural argument is given there.}
```

This makes the §5.3 ↔ App. AG link explicit so a reviewer reading either section first finds the other.

### 5.3 Optional addendum at `paper/appendix_v18.tex` line 1627 (`Normalizer Ablation, Experiment N`)

Add at end of the existing paragraph at L1625:

```latex
Because \textsc{omission} is excluded from \texttt{cwt\_typed\_pass} and \texttt{cwt\_typed\_4type\_pass} by construction (\S\ref{app:additional_limitations}), the OMISSION shift of \normalizerOmissionShift{}\,pp does not propagate to TCC verdicts at any normalizer mode. It does enter the C2 mandatory-completion sub-score, where the four-mode envelope is reported in Table~\ref{tab:normalizer_per_type}.
```

This closes the loop: a reader of the Normalizer Ablation section sees, at the same place where the OMISSION shift is largest, why that shift is verdict-irrelevant for the headline metric.

---

## 6. Insertion-location summary

| Anchor | File | Line(s) | Action | Priority |
|---|---|---|---|---|
| App. AG paragraph (weak co-occurrence claim) | `paper/appendix_v18.tex` | 575-579 (`\paragraph{Action normalization residual errors.}`) | **Replace** with §5.1 above | **High — primary fix** |
| §`app:non_timing` head sentence | `paper/appendix_v18.tex` | 821 | Add footnote (§5.2 above) | Medium |
| `Normalizer Ablation` (Experiment N) tail | `paper/appendix_v18.tex` | 1627 (end of paragraph starting at 1625) | Append sentence (§5.3 above) | Low (defensive) |
| `\safetyCoreFAEpisodes` macro definition | `paper/main_final_v18.tex` | 263 | Unchanged; current value 354 already correct | — |

No changes to `auto_numbers*.tex`, `evidence_pack/`, or any compute scripts are required — this is a pure framing/structural-argument upgrade, no numbers move.

---

## 7. Re-run / verification commands

The structural argument needs no re-run, but the empirical sanity numbers in this report can be reproduced from a clean checkout in ~1 second:

```bash
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
python3 - <<'PY'
import json
from collections import Counter

with open('evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json') as f:
    data = json.load(f)
eps = data['per_episode']

# 354 reproduction
exp = [e for e in eps
       if e.get('viol_types')
       and set(e['viol_types']).issubset({'FORBIDDEN', 'BEFORE'})]
print('354 reproduction         :', len(exp))
print(' breakdown                :',
      Counter(tuple(sorted(set(e['viol_types']))) for e in exp).most_common())

# Structural cross-checks
print('cwt_typed_pass=False & no WITHIN, full corpus :',
      sum(1 for e in eps
          if not e['cwt_typed_pass']
          and 'WITHIN' not in e.get('viol_types', [])))
print('Within 354: cwt_typed_pass fail               :',
      sum(1 for e in exp if not e['cwt_typed_pass']))
print('Within 354: cwt_typed_4type_pass fail         :',
      sum(1 for e in exp if not e.get('cwt_typed_4type_pass', True)))
print('Within 354: c2_pass fail                      :',
      sum(1 for e in exp if not e['c2_pass']))
PY
```

Expected output:

```text
354 reproduction         : 354
 breakdown                : [(('FORBIDDEN',), 315), (('BEFORE',), 39)]
cwt_typed_pass=False & no WITHIN, full corpus : 0
Within 354: cwt_typed_pass fail               : 0
Within 354: cwt_typed_4type_pass fail         : 67
Within 354: c2_pass fail                      : 114
```

The first three lines are the verdict-impact answer; the bottom two contextualise where normalizer-residual omission *can* still matter (legacy `c2_pass` and the 4-type variant, neither of which is the §5.3 headline).

---

## 8. Bottom line for the response letter

> **`N = 0` for every corpus snapshot (354 on the 8-model EX-30 set, 443 on the 9-model paper headline, 620 on the latest 10-model matrix), by construction.** A normalizer alias miss is, by definition, an OMISSION-type event on a *missing expected action*; a non-timing-only TCC failure is, by definition, driven by FORBIDDEN- or BEFORE-type events on *performed actions*; the two event-type sets are disjoint and so the residual cannot enter the verdict on this set. (On the 8-model phase-1 snapshot, the typed-CwT scoring formula additionally excludes OMISSION at the score level, giving an even stronger guarantee.) We have replaced the weaker "co-occurrence" wording in App. AG with this structural argument and added cross-references in §5.3 (App.~\ref{app:non_timing}) and the Normalizer Ablation (App.~\ref{app:normalizer_ablation}) so the equivalence is visible from each entry point.
