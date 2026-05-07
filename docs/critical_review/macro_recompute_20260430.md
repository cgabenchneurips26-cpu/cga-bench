# Macro Recompute — 2026-04-30

## Source data

| File | Role | Key fields used |
|---|---|---|
| `evidence_pack/analysis/verdict_matrix_v6.json` | Phase A 9m episode-level matrix | `v4_hard`, `v4_crit`, `ac_proxy`, `mab_proxy`, `c2_pass`, `viol_types`, `model_dir` |
| `evidence_pack/analysis/verdict_matrix_v6_full.json` | Phase B 8m episode-level matrix | same fields |
| `evidence_pack/analysis/v6_full_macros.json` | Pre-computed FA aggregates (all corpora) | `fa.*`, `bsr_conditional.*`, `per_model_fa.*` |
| `evidence_pack/analysis/exp_e9_safety_core.json` | Safety-core decomposition | `n_strict_fa_S1`, `safety_core_S1`, `must_only_S1`, `family_breakdown_S1` |
| `paper/auto_numbers.tex.v6_phaseA_backup_20260428` | Pre-Llama4Scout Phase A 8m macro snapshot | `\nonTimingNaturalCount{354}`, `\nonTimingForbiddenOnly{315}`, `\nonTimingBeforeOnly{39}` |
| `evidence_pack/analysis/full_706_v6_summary.json` | Phase A 8m model-level summary | confirms 8-model corpus = 16,944 |

All computations performed directly on per-episode arrays. No intermediary scripts were re-run.

---

## Corpus inventory

| Corpus | Formula | N_total (computed) | Matches expected? |
|---|---|---|---|
| Phase A 9m | 706 scenarios × 9 models × 3 runs | 19,062 | **Yes — 19,062** |
| Phase A 8m | 706 × 8 × 3 (exclude llama4scout from Phase A 9m matrix) | 16,944 | **Yes — 16,944** |
| Phase B 8m | 3,186 × 8 × 3 (706 manual + 2,480 auto_v2) | 76,464 | **Yes — 76,464** |

Models in Phase A 9m matrix: deepseek_r1_7b, gemma31b, llama4scout, nemotron30b, oss120b, qwen27b, qwen35b, qwen397b, qwen4b.

Phase A 8m = Phase A 9m minus llama4scout (2,118 episodes).

Evaluator mapping (from `verdict_matrix_v6.json` metadata):

| Matrix field | Evaluator name | Paper abbreviation |
|---|---|---|
| `ac_proxy` | Action-Coverage Proxy | ASC |
| `mab_proxy` | MAB F1 Proxy | PAF |
| `c2_pass` | C2 compliance threshold | CwT |
| `v4_hard` | Hard violation present (TCC fail) | TCC fail |
| `v4_crit` | Any violation severity = CRITICAL | catalogue-critical flag |
| `dxem` | DxEM outcome metric | TOM (always True in Phase A matrix) |

Hard violation definition (from metadata): FORBIDDEN (commission) + WITHIN (timing) + BEFORE (sequence). **OMISSION is not a hard violation type in the released matrix.** The "MUST-only" cell in the safety-core decomposition is operationally WITHIN-only episodes.

---

## Per-corpus FA table

All computations performed on raw `per_episode` arrays from the respective matrices. See computation source at end of each sub-section.

### Step 2 items (1)–(8) × 3 corpora

| Metric | Phase A 9m (n=19,062) | Phase A 8m (n=16,944) | Phase B 8m (n=76,464) |
|---|---|---|---|
| **(1) N_total** | 19,062 | 16,944 | 76,464 |
| **(2) Strict-3way FA** (TCC∧ASC∧PAF∧CwT) — count | 1,124 | 912 | 2,974 |
| **(2) Strict-3way FA** — pct of N | 5.90% | 5.38% | 3.89% |
| **(3) Strict-critical FA** (strict3 ∧ v4_crit) — count | 22 | 14 | 56 |
| **(3) Strict-critical FA** — pct of strict3 | 1.96% | 1.54% | 1.88% |
| **(3) Strict-critical FA** — pct of N | 0.12% | 0.08% | 0.07% |
| **(4) Loose-2way FA** (TCC∧ASC∧CwT) — count | 2,106 | 1,858 | 4,405 |
| **(4) Loose-2way FA** — pct of N | 11.05% | 10.97% | 5.76% |
| **(5) Loose-critical FA** (loose ∧ v4_crit) — count | 139 | 126 | 170 |
| **(5) Loose-critical FA** — pct of loose FA | 6.60% | 6.78% | 3.86% |
| **(5) Loose-critical FA** — pct of N | 0.73% | 0.74% | 0.22% |
| **(6) Safety-core FA** (strict3 excl. WITHIN-only) — count | 144 | 123 | 1,280 |
| **(6) Safety-core FA** — pct of N | 0.76% | 0.73% | 1.67% |
| **(6) MUST-only (WITHIN-only) excluded** — count | 980 | 789 | 1,694 |
| **(7) Non-timing TCC-fail** (FORBIDDEN∣BEFORE, no WITHIN) — count | 443 | 390 | 2,564 |
| **(7) Non-timing TCC-fail** — pct of N | 2.32% | 2.30% | 3.35% |
| **(8) Non-timing: FORBIDDEN-only** | 423 | 370 | 370 |
| **(8) Non-timing: BEFORE-only** | 20 | 20 | 2,194 |
| **(8) Non-timing: pass ASC** (ac_proxy=T) | 306 (69.1%) | 279 (71.5%) | 2,429 (94.7%) |
| **(8) Non-timing: pass PAF** (mab_proxy=T) | 201 (45.4%) | 177 (45.4%) | 1,902 (74.2%) |

**Note on TOM:** `dxem` is uniformly True across all Phase A 9m episodes, making TOM∩ASC∩CwT = ASC∩CwT. The `\consensusFATotal` = loose-2way FA = 2,106 for Phase A 9m.

---

## Safety-core decomposition (the X1 fix)

Source: computed from `verdict_matrix_v6.json` per-episode array (Phase A 9m, n=19,062); cross-checked against `exp_e9_safety_core.json` (match = exact).

Strict-3way FA total (Phase A 9m): **1,124 episodes**

| Violation-family cell | Episodes | % of strict3-FA |
|---|---|---|
| WITHIN-only (MUST-omission timing) | 980 | 87.2% |
| FORBIDDEN-only | 139 | 12.4% |
| BEFORE-only | 0 | 0.0% |
| FORBIDDEN + WITHIN (mixed) | 5 | 0.4% |
| BEFORE + WITHIN (mixed) | 0 | 0.0% |
| FORBIDDEN + BEFORE | 0 | 0.0% |
| FORBIDDEN + BEFORE + WITHIN | 0 | 0.0% |
| **Safety-core subtotal (non-WITHIN-only)** | **144** | **12.8%** |

Safety-core pct of N (19,062): **0.76%**

Cross-check: `exp_e9_safety_core.json` reports `safety_core_S1=144`, `must_only_S1=980`, `forbid_only=139`, `forbid_within=5` — **exact match**.

**Critical finding for `\safetyCoreFAEpisodes`:** The current macro value of 354 is the pre-Llama4Scout Phase A 8m non-timing TCC-fail total (315 FORBIDDEN-only + 39 BEFORE-only, confirmed in backup file `auto_numbers.tex.v6_phaseA_backup_20260428` at L538-539). This is a completely different concept from safety-core-FA. The correct value for safety-core-FA (strict-3way FA minus WITHIN-only, Phase A 9m) is **144**.

### Three-corpus safety-core comparison

| Corpus | Strict-3way FA | Safety-core (non-WITHIN-only) | WITHIN-only excluded |
|---|---|---|---|
| Phase A 9m (n=19,062) | 1,124 | **144** | 980 |
| Phase A 8m (n=16,944) | 912 | **123** | 789 |
| Phase B 8m (n=76,464) | 2,974 | **1,280** | 1,694 |

---

## Macro reconciliation table

| Macro | Line | Current value | Current comment | Verified value | Verified corpus | Verdict |
|---|---|---|---|---|---|---|
| `\safetyCoreFAEpisodes` | L215 | 354 | "EX-30 non-timing natural failures" | **144** | Phase A 9m | **REPLACE** — 354 is pre-Llama4Scout Phase A 8m non-timing TCC-fail count (=315+39); correct concept is strict-3way-FA minus WITHIN-only = 144 |
| `\safetyCoreFAPct` | L216 | 1.86 | "354/19062" | **0.76** | Phase A 9m | **REPLACE** — 354/19062=1.86% uses wrong numerator (non-timing count not safety-core count); correct 144/19062=0.76% |
| `\nonTimingNaturalCount` | L420 | 443 | (none) | **443** | Phase A 9m | **KEEP** — correct; matches Phase A 9m non-timing TCC-fail (FORBIDDEN∣BEFORE, no WITHIN) |
| `\nonTimingNaturalPct` | L421 | 2.09 | (none) | **2.32** | Phase A 9m | **REPLACE** — 2.09 is stale value from backup (354/16,944=2.089%); count was updated 354→443 but pct not recalculated; correct 443/19,062=2.32% |
| `\nonTimingACBlindPct` | L422 | 72.0 | (none) | **69.1** | Phase A 9m | **REPLACE** — 72.0 comes from old Phase A 8m corpus (255/354=72.0%); current Phase A 9m: 306/443=69.1% |
| `\nonTimingMABBlindPct` | L537 | 52.0 | "MAB blind among non-timing failures" | **45.4** | Phase A 9m | **REPLACE** — 52.0 from old Phase A 8m corpus (184/354≈52%); current Phase A 9m: 201/443=45.4% |
| `\nonTimingForbiddenOnly` | L538 | 0 | "FORBIDDEN-only non-timing failures" | **423** | Phase A 9m | **REPLACE** — 0 is wrong; backup had 315; current Phase A 9m has 423 FORBIDDEN-only non-timing TCC-fail |
| `\nonTimingBeforeOnly` | L539 | 20 | "BEFORE-only non-timing failures" | **20** | Phase A 9m | **KEEP** — correct for Phase A 9m |
| `\consensusFATotal` | L398 | 2,106 | "v6 Phase B TOM∩ASC∩CwT FA. Phase A was 1959." | **2,106** | Phase A 9m | **RELABEL** — value is correct for Phase A 9m (ASC∩CwT∩v4_hard = 2,106); comment incorrectly attributes it to Phase B; Phase B actual = 4,405; "Phase A was 1959" is v5-era (Phase A 8m pre-regen was 1,858 in v6) |
| `\consensusFARate` | L399 | 11.0 | "v6 Phase B. Phase A was 11.6." | **11.05** | Phase A 9m | **RELABEL + minor correction** — 2,106/19,062=11.05%; comment attributes to Phase B (wrong); Phase B actual = 5.76% |
| `\consensusFACritical` | L400 | 139 | "v6 Phase B (orig CwT). Phase A was 432." | **139** | Phase A 9m | **RELABEL** — value correct for Phase A 9m (139 loose-FA episodes with v4_crit=T); comment attributes to Phase B (wrong); Phase B actual = 170 |
| `\consensusFACriticalPct` | L401 | 6.6 | "v6 Phase B. Phase A was 22.1." | **6.60** | Phase A 9m | **RELABEL** — 139/2,106=6.60%; comment attributes to Phase B (wrong); Phase B critical pct = 3.86% |
| `\strictFAThree` | L580 | 5.9 | "v6 Phase B ASC∩PAF∩CwT FA. Phase A was 6.6." | **5.90** | Phase A 9m | **RELABEL** — 1,124/19,062=5.90% correct for Phase A 9m; "Phase B" comment wrong; Phase B 3-way = 3.89%; "Phase A was 6.6" refers to pre-expansion Phase A 8m (1,118/16,944=6.60%) |
| `\strictFAThreeCount` | L581 | 1,124 | "v6 Phase B. Phase A was 1118." | **1,124** | Phase A 9m | **RELABEL** — value correct for Phase A 9m; comment says "Phase B" (wrong); Phase B strict-3way = 2,974; 1,118 was the pre-Llama4Scout Phase A 8m count |
| `\strictFAFour` | L582 | 3.89 | "v6 Phase B TOM∩ASC∩PAF∩CwT FA. Phase A was 6.6." | **3.89** | Phase B 8m | **KEEP** — 2,974/76,464=3.89% verified |
| `\strictFAFourCount` | L583 | 2,974 | "v6 Phase B. Phase A was 1118." | **2,974** | Phase B 8m | **KEEP** — Phase B strict-3way FA count verified |
| `\strictFACriticalPct` | L584 | 2.0 | "v6 Phase B (n=2974). Phase A was 6.2." | **1.96** | Phase A 9m | **REPLACE + RELABEL** — comment claims Phase B with n=2,974; but 2.0% ≈ 22/1,124=1.96% which is Phase A 9m strict-3way-crit/strict3; Phase B actual = 56/2,974=1.88%; this macro is Phase A 9m mislabeled as Phase B |
| `\strictFACriticalCount` | L585 | 123 | "v6 Phase B. Phase A was 69." | **123 (Phase A 8m safety-core)** | Phase A 8m | **RELABEL + CONCEPT WARNING** — 123 = Phase A 8m safety-core count (FORBIDDEN∣BEFORE in strict3-FA), NOT Phase B; Phase B strict-3way v4_crit = 56; "Phase A was 69" is unverified (v5 era); naming "Critical" is misleading — this is safety-core count, not v4_crit count |
| `\strictFACritical` | L1487 | 22 | "refreshed by refresh_paper_macros.py [phase_a_9m_19062]" | **22** | Phase A 9m | **KEEP** — correctly identified as Phase A 9m; 22 = strict-3way-FA episodes with v4_crit=True |

---

## Name-collision resolution: `\strictFACritical` vs `\strictFACriticalCount`

These two macros use incompatible definitions:

| Macro | Line | Value | Actual meaning | Correct corpus |
|---|---|---|---|---|
| `\strictFACritical` | L1487 | 22 | Strict-3way-FA episodes with v4_crit flag (catalogue-critical severity) | Phase A 9m |
| `\strictFACriticalCount` | L585 | 123 | Phase A 8m safety-core count (FORBIDDEN∣BEFORE episodes in strict3-FA) | Phase A 8m |

These measure different things. Suggested rename:

- `\strictFACritical` (L1487, 22) → rename to `\strictFACriticalCountPhaseA` (Phase A 9m v4_crit count)
- `\strictFACriticalCount` (L585, 123) → rename to `\strictFASafetyCorePhaseA8m` or retire; it is the Phase A 8m safety-core, not a "critical" count

The appendix table at L740 uses `\strictFACritical{}` in the "Catalogue-critical" row of the strict-consensus block, which is the correct usage (v4_crit = 22 for Phase A 9m). The same table row would be wrong if `\strictFACriticalCount{123}` were substituted — 123 is not the critical count.

---

## Recommended macro patch (drop-in replacement)

The following replaces stale values and corrects corpus comments. Lines where only the comment changes are marked `% RELABEL ONLY`.

```tex
% --- RECOMPUTED 2026-04-30 against verdict_matrix_v6.json (Phase A 9m, n=19,062) ---
% Source: evidence_pack/analysis/verdict_matrix_v6.json per_episode array
%         evidence_pack/analysis/exp_e9_safety_core.json (cross-check)

% Safety-core FA (strict-3way minus WITHIN-only)
% Previous value 354 was pre-Llama4Scout Phase A 8m non-timing count (wrong concept)
\providecommand{\safetyCoreFAEpisodes}{144}         % Phase A 9m: FORBIDDEN|BEFORE in strict3-FA
\providecommand{\safetyCoreFAPct}{0.76}             % 144/19062

% Safety-core family breakdown (Phase A 9m)
\providecommand{\faWithinOnlyEpisodes}{980}         % WITHIN-only in strict3-FA (= MUST-only cell)
\providecommand{\faForbidOnlyEpisodes}{139}         % FORBIDDEN-only
\providecommand{\faBeforeOnlyEpisodes}{0}           % BEFORE-only
\providecommand{\faMixedSafetyEpisodes}{5}          % FORBIDDEN+WITHIN (mixed)
\providecommand{\faMustOnlyEpisodes}{980}           % alias for \faWithinOnlyEpisodes
\providecommand{\faMustOnlyPct}{87.2}              % 980/1124 pct of strict3-FA

% Non-timing TCC-fail (Phase A 9m)
\newcommand{\nonTimingNaturalCount}{443}            % Phase A 9m: FORBIDDEN|BEFORE, no WITHIN
\newcommand{\nonTimingNaturalPct}{2.32}             % 443/19062  [was 2.09 = stale 354/16944]
\newcommand{\nonTimingACBlindPct}{69.1}             % 306/443  [was 72.0 = old Phase A 8m corpus]
\newcommand{\nonTimingMABBlindPct}{45.4}            % 201/443  [was 52.0 = old Phase A 8m corpus]
\newcommand{\nonTimingForbiddenOnly}{423}           % Phase A 9m FORBIDDEN-only  [was 0]
\newcommand{\nonTimingBeforeOnly}{20}               % Phase A 9m BEFORE-only  [unchanged]

% Consensus FA (ASC∩CwT∩TCC-fail) — Phase A 9m headline corpus
% RELABEL ONLY: values correct, comments were claiming Phase B (wrong)
\newcommand{\consensusFATotal}{2{,}106}             % Phase A 9m TOM∩ASC∩CwT FA  [was: Phase B]
\newcommand{\consensusFARate}{11.05}                % 2106/19062  [was 11.0, Phase B label]
\newcommand{\consensusFACritical}{139}              % Phase A 9m catalogue-critical  [was: Phase B]
\newcommand{\consensusFACriticalPct}{6.60}          % 139/2106  [was 6.6, Phase B label]

% Strict 3-way FA (ASC∩PAF∩CwT∩TCC-fail) — Phase A 9m
% RELABEL ONLY: values correct, comments were claiming Phase B (wrong)
\newcommand{\strictFAThree}{5.90}                   % Phase A 9m  [was: Phase B label]
\newcommand{\strictFAThreeCount}{1{,}124}           % Phase A 9m  [was: Phase B label]

% Strict 4-way FA (TOM∩ASC∩PAF∩CwT∩TCC-fail) — Phase B 8m
\newcommand{\strictFAFour}{3.89}                    % Phase B 8m  [unchanged, correct]
\newcommand{\strictFAFourCount}{2974}               % Phase B 8m  [unchanged, correct]

% Strict-FA critical severity — Phase A 9m
% strictFACriticalPct: was "Phase B (n=2974)" but 22/1124=1.96% = Phase A 9m
\newcommand{\strictFACriticalPct}{1.96}             % 22/1124 Phase A 9m  [was 2.0 Phase B label]
% strictFACriticalCount: 123 = Phase A 8m safety-core (NOT Phase B FA-critical)
% Recommend rename to \strictFASafetyCorePhaseA8m; kept here for backward compat
\newcommand{\strictFACriticalCount}{123}            % Phase A 8m safety-core  [RELABEL: not Phase B]
% strictFACritical: correct, Phase A 9m v4_crit strict-3way-FA count
\providecommand{\strictFACritical}{22}              % Phase A 9m v4_crit strict-3way-FA  [unchanged]
```

---

## Open questions / data gaps

**1. `\nonTimingForbiddenOnly{0}` (L538) — probable inadvertent zero**
The backup shows 315 and the current Phase A 9m computation gives 423. The current value of 0 has no identified source in any corpus or formula. Likely a manual edit error. Correct value is 423 (Phase A 9m).

**2. `\strictFACriticalCount{123}` concept conflict**
This macro is labeled "critical" in both its name and appendix table column, but 123 = Phase A 8m safety-core count (FORBIDDEN∣BEFORE in strict3-FA), not a v4_crit catalogue-critical count. For Phase A 8m, the actual v4_crit strict-3way count is 14. The appendix table at L739–740 uses `\strictFACritical{22}` in the correct "Catalogue-critical" row; `\strictFACriticalCount{123}` appears to be a stale Phase A 8m artifact that was never used in final prose (it does not appear in a rendered table cell with a stated role). Recommend retiring it and using `\strictFASafetyCorePhaseA8m{123}` or the Phase A 9m value of 144.

**3. `\consensusFATotal{2106}` — comment chain discrepancy**
Comment says "Phase A was 1959." The actual Phase A 8m (v6 regenerated) loose-FA is 1,858. The figure 1,959 appears to be from the v5 paper, not v6. The Phase A 8m v5 figure is unverifiable from currently available matrices (they reflect the v6 regenerated corpus). The v5 → v6 transition note in appendix_v18.tex L747 ("restricting the current 9-model verdict matrix to the same 8 models reproduces 1,858 loose-FA") confirms the discrepancy. The comment "Phase A was 1959" should read "Phase A 8m (v6 regen) = 1,858; v5 paper was 1,959."

**4. Finer-grained severity tiers (High/Medium/Low) for `\consensusFAHigh`, `\consensusFAMedium`, `\consensusFALow`**
These are already marked DEPRECATED in auto_numbers.tex (L402–404). Confirmed: per-violation severity scores beyond the binary v4_crit flag are not exposed in the released verdict matrices. As stated in appendix_v18.tex L724: "Finer-grained tier breakdowns require per-violation severity scores not exposed in the released verdict matrix and are deferred to a follow-on appendix release." These macros cannot be recomputed from available data — **GENERATOR MISSING** for tier breakdown beyond v4_crit.

**5. `\consensusFACritFracTotal{0.73}` (L1486, refreshed by refresh_paper_macros.py)**
Computed as 139/19,062 = 0.729% ≈ 0.73%. Verified correct for Phase A 9m.

**6. `\strictFACritFracTotal{0.12}` (L1488, refreshed by refresh_paper_macros.py)**
Computed as 22/19,062 = 0.115% ≈ 0.12%. Verified correct for Phase A 9m.

**7. Phase B critical counts — not included in disputed list but worth noting**
Phase B consensus-FA critical = 170 (3.86% of FA, 0.22% of N). Phase B strict-3way-FA v4_crit = 56 (1.88% of strict3). Neither of these appears in the current auto_numbers.tex as a Phase B figure. The macros that claim to be Phase B (`\consensusFACritical{139}`, `\strictFACriticalCount{123}`) are actually Phase A numbers — the correct Phase B values (170 and 56 respectively) are absent from the macro file entirely.

**8. `nonTimingNaturalPct{2.09}` — diagnostic note on count/pct split update**
The update from 354 → 443 for `\nonTimingNaturalCount` (sometime after the backup was taken on 2026-04-28) updated only the count, not the percentage. This is a partial-update anti-pattern. The backup confirms both were previously consistent (354/16,944 = 2.09%). The current state (443 + 2.09%) pairs a Phase A 9m count with a Phase A 8m percentage, making neither number independently useful for the reader. Both must be updated together.
