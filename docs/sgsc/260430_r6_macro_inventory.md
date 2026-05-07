# SGSC v7 Transition: Paper Macro Inventory (v6 baseline)

**Purpose**: Catalogue every paper macro in the targeted families so the SGSC v7
switchover team knows (a) what the current v6 value is, (b) where each macro is
used in the paper, and (c) whether the macro must be updated with v7 numbers or
kept as a v6 reference point.

**Source files audited**:
- `paper/auto_numbers.tex` (577 `\newcommand`/`\renewcommand` definitions + ~150 `\providecommand`)
- `paper/main_final_v18.tex` (717 lines)
- `paper/appendix_v18.tex` (2312 lines)

**Date generated**: 2026-04-30
**Branch**: `eval_science`

---

## Category Definitions

| Category | Meaning |
|---|---|
| **v7-swap** | Macro appears in a paper headline claim or main-text number; value must be recomputed from v7 corpus before submission |
| **v6-baseline** | Macro is a v6 reference value used for comparison, appendix disclosure, or robustness table; keep as v6, add v7 sibling if needed |
| **v6-structural** | Macro describes a fixed structural property (graph count, constraint type count) that v7 expansion changes but is not a "result"; must be reviewed but may or may not need updating depending on whether the paper scope changes |

---

## Summary Count

Sections 1–3 group macros by category without per-row labels. Section 4 adds
`\providecommand` macros with explicit category labels. Counts below include all rows
across all sections.

| Category | Sections 1–3 rows | Section 4 rows | Total |
|---|---|---|---|
| v7-swap | 55 | 9 | **64** |
| v6-baseline | 44 | 13 | **57** |
| v6-structural | 18 | 0 | **18** |
| **Total tracked** | **117** | **22** | **139** |

---

## Section 1: Must Swap to v7 (`v7-swap`)

These macros appear in abstract, introduction, findings sections, or defense/robustness tables
as the primary reported values. All must be recomputed on the v7 corpus.

### 1.1 Strict False-Accept (strictFA*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\strictFAThree` | `5.90` | main:242, main:255, main:479, main:482, app:741, app:803, app:807, app:1863, app:2014–2015, app:2218, app:2225 | **Headline number**: ASC∩PAF∩CwT FA rate (Phase A 9m). Most cited number in paper. |
| `\strictFAThreeCount` | `1,124` | main:242, main:255, app:741, app:807 | Count of strict-3-way FA episodes. Paired with `\strictFAThree`. |
| `\strictFACriticalPct` | `1.96` | main:255, app:740 | % of strictFA3 that are catalogue-critical. |
| `\strictFACritical` | `22` | main:255, app:740, app:750 | Raw count of catalogue-critical strict-3-FA episodes. |
| `\strictFACritFracTotal` | `0.12` | main:255, app:740 | Catalogue-critical FA as % of all episodes. |
| `\strictFAMedianViols` | `1` | (appendix) | Median hard violations per strict-FA episode. |

### 1.2 Consensus False-Accept (consensusFA*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\consensusFATotal` | `2,106` | main:255 | Loose ASC∩CwT FA count (Phase A 9m). |
| `\consensusFARate` | `11.05` | (appendix) | 2106/19062 × 100. |
| `\consensusFACritical` | `139` | main:255, app:750 | Loose-consensus catalogue-critical FA count. |
| `\consensusFACriticalPct` | `6.60` | main:255 | 139/2106 × 100. |
| `\consensusFAModelRange` | `0.56--6.11` | (appendix) | Per-model FA range. |

### 1.3 Safety Core (safetyCore*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\safetyCoreFAEpisodes` | `144` | main:255, app:803, app:818 | Non-MUST-only episodes passing strict consensus. |
| `\safetyCoreFAPct` | `0.76` | app:807 | 144/19062 × 100. |
| `\safetyCorePctOfStrictFA` | `12.8` | main:255, app:803 | 144/1124 = 12.81%. |
| `\safetyCoreWilsonLo` | `11.0` | main:255, app:803 | Wilson 95% CI lower. |
| `\safetyCoreWilsonHi` | `14.9` | main:255, app:803 | Wilson 95% CI upper. |

### 1.4 Conflict Patterns (conflict*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\conflictPatternsN` | `11` | main:479, app:2184, app:2213, app:2218, app:2267 | Same-action conflict patterns across 25 CPGs. |
| `\conflictGraphsN` | `9` | main:479, app:2184, app:2291 | CPGs with at least one conflict pattern. |
| `\conflictViolationN` | `11` | app:2226 | CONFLICT violations emitted in demo pipeline. |
| `\conflictTouchEpisodes` | `3584` | app:2271 | Episodes where agent performed conflict-prone action. |
| `\conflictTouchPct` | `21.2` | app:2271, app:2275 | % of 16,944 Phase A 8m episodes (upper bound). |
| `\conflictTouchScenarios` | `264` | app:2272 | Unique scenarios touched. |
| `\conflictTouchActionsN` | `11` | app:2273 | Conflict-prone actions tracked. |
| `\conflictTouchStrictPct` | `20.2` | app:2275 | Strict exact-match lower bound. |

### 1.5 Tier Classifications (tier*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\tierAN` | `0` | main:479, app:2180 | Tier-A patterns (mechanically resolvable). |
| `\tierBN` | `9` | main:479, app:2181, app:2286 | Tier-B: static mandatory + conditional FORBIDDEN. |
| `\tierCN` | `2` | main:479, app:2182 | Tier-C: genuine OR_REQUIRED semantics. |
| `\tierSExtraCPGs` | `17` | main:476 | Additional CPGs in Tier-S robustness expansion. |
| `\tierSExtraEpisodes` | `11235` | main:476 | Additional episodes in Tier-S expansion. |
| `\tierSMaxMetricShift` | `3` | main:476 | Max metric shift (pp) across expansion. |

### 1.6 Statistical Tests — Ranking (friedman*, kendall*, reversal*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\friedmanChi` | `31.3` | app:1315 | Friedman χ² (v6 Phase B). |
| `\friedmanP` | `<0.001` | app:1315 | Friedman p-value (v6 Phase B). |
| `\kendallW` | `0.219` | main:242, main:443, app:1315 | Kendall W concordance (v6 Phase B). |
| `\reversalRate` | `96.4` | main:242, main:443, main:482 | % of model pairs reversing under evaluator swap. |
| `\rankBootstrapKendallW` | `0.408` | app:1315 | Bootstrap point-estimate Kendall W. |
| `\rankBootstrapKendallWLo` | `0.342` | main:443, app:1315 | 95% CI lower. |
| `\rankBootstrapKendallWHi` | `0.461` | main:443, app:1315 | 95% CI upper. |
| `\rankBootstrapTopOneStablePct` | `75` | app:1315 | % evaluators with >=95% stable top-1. |

### 1.7 Graph Validator (graphValidator*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\graphValidatorChecksN` | `6` | app:2295 | Structural checks per graph (v1.2 engine). |
| `\graphValidatorGraphsN` | `25` | app:2298, app:2302–2303 | CPGs validated. |
| `\graphValidatorTotalN` | `150` | app:2298 | 6 × 25 = total validations. |
| `\graphValidatorErrorsN` | `0` | app:2299 | Errors found. |

### 1.8 Normalizer (normali*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\normalizerCurrentDelta` | `3.81` | main:293, app:1584 | Strict-vs-current pp gap (mean compliance). |
| `\normalizerBlindspotN` | `18` | app:2180, app:2308 | Canonical-form collisions (mandatory∩forbidden). |
| `\normalizerRawActionsN` | `1458` | app:2302 | Unique raw action IDs across 25 graphs. |
| `\normalizerCanonicalN` | `1366` | app:2304 | Unique canonical forms. |
| `\normalizerMultiCanonicalN` | `59` | app:2306 | Groups where multiple raw IDs share one canonical. |

### 1.9 Held-out Generalization (heldout*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\heldoutCondFA` | `62.2` | main:419, app:1343 | Held-out conditional FA (%). |
| `\heldoutN` | `1584` | main:385, main:419, app:35, app:1003, app:1343, app:1412 | Held-out episode count (8 models). |
| `\heldoutFARate` | `18.82` | (appendix) | v6 heldout FA rate. |
| `\heldoutFlipRate` | `98.34` | (appendix) | v6 heldout verdict-flip rate. |
| `\heldoutCompliance` | `0.580` | (appendix) | v6 heldout mean compliance. |

### 1.10 Traceability (trace*)

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\traceGraphsN` | `97` | (appendix) | Total graphs audited (25 core + 72 auto). |
| `\traceQuoteCoverageRate` | `77.2%` | (appendix) | Quote verified or grounded rate. |
| `\traceReachabilityRate` | `55.2%` | (appendix) | Scenarios where expected_actions all reachable. |

---

## Section 2: Keep as v6 Baseline (`v6-baseline`)

These macros are v6 reference values cited for comparison, provenance, or sensitivity
disclosure. They should NOT be overwritten with v7 values; instead add v7-specific sibling
macros (e.g., `\strictFAThreeVSeven`) and reference both in the paper.

### 2.1 Phase/Corpus Reference Values

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\strictFAAOnlyPct` | `5.4` | main:199 (providecommand), app:2014 | Phase A 8m strict FA for narrative comparison. |
| `\strictFAThreePre` | `6.6` | app:2218, app:2225 | Pre-CDE-patch FA rate (Phase A 8m). |
| `\strictFAThreeFixed` | `6.6` | app:2218, app:2225 | Post-CDE-patch FA (qualitatively unchanged). |
| `\strictFAFour` | `3.89` | (auto_numbers defined) | Phase B 8m 4-way strict FA rate. |
| `\strictFAFourCount` | `2974` | (auto_numbers defined) | Phase B 8m count. |
| `\strictFACriticalPctPhaseB` | `1.88` | (providecommand) | Phase B 8m strict-3way v4_crit %. |
| `\phaseAEpisodes` | `16,944` | main:200, app:1593 | Phase A 8-model corpus size. |
| `\phaseBEpisodes` | `76,464` | main:476 | Phase B auto-expanded corpus size. |
| `\cellPairReversal` | `26.5` | main:476 | Phase B cell-level pair reversal (%). |

### 2.2 Held-out Baseline Numbers

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\heldoutAllObliviousFA` | `5.8` | app:715 | Held-out all-oblivious FA rate (%). |
| `\heldoutAllObliviousCount` | `92` | (auto_numbers) | Count. |
| `\heldoutAOPassRate` | `9.3` | (auto_numbers) | Held-out AO pass rate. |
| `\heldoutOrderingMatch` | `5/5` | app:1010 | Top-1 most-blind evaluator match on held-out. |
| `\heldoutOrderingMatchPct` | `100` | app:1011 | Match rate %. |
| `\heldoutOrderingMeanRho` | `0.50` | app:1012, app:1018 | Mean Spearman rho across 5 held-out domains. |
| `\heldoutFisherP` | `<0.001` | (auto_numbers) | Fisher p for held-out vs in-domain FA. |
| `\indomainCondFA` | `37.1` | main:419, app:1343 | In-domain conditional FA (%). |
| `\indomainFARate` | `5.38` | (auto_numbers) | v6 in-domain Phase B FA rate. |
| `\indomainCompliance` | `0.511` | (auto_numbers) | v6 in-domain Phase B mean compliance. |

### 2.3 Normalizer Ablation Reference Values

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\normalizerStrictBaseline` | `0.691` | app:1584 | Strict-mode mean compliance (lower bound). |
| `\normalizerCurrentCompliance` | `0.729` | app:1584 | Current-mode mean compliance. |
| `\normalizerDirectDelta` | `3.91` | app:1584 | Direct-only pp gap. |
| `\normalizerPatternDelta` | `0.09` | app:1584 | Pattern-rules pp contribution. |
| `\normalizerFuzzyNet` | `-0.10` | app:1584 | Fuzzy-fallback net pp (≈ 0). |
| `\normalizerDirectMappings` | `500` | app:1582 | Human-audited direct mappings count. |
| `\normalizerPerTypeMaxShift` | `2.1` | main:293, app:1584, app:1591 | Max per-type detection shift (pp). |
| `\normalizerOmissionShift` | `2.1` | app:1586 | OMISSION per-type shift. |
| `\normalizerOtherTypesMaxShift` | `1.0` | app:1586 | Other violation types max shift. |
| `\normalizerNMEpisodes` | `9674` | app:1586 | Near-miss analysis episode count. |
| `\normalizerNMPairs` | `356` | app:1586 | Alias pairs identified. |
| `\normalizerHighConfAliases` | `86` | app:1586 | High-confidence pairs (≥0.7 similarity). |
| `\normalizerAblationEpisodes` | `16944` | app:1593 | 8-model v5 ablation subset. |
| `\normalizerUnmappedN` | `1279` | (auto_numbers) | Self-normalising actions count. |
| `\normalizerUnmappedPct` | `87.7` | app:2305 | Self-normalising rate (%). |

### 2.4 CDE Conflict Audit Reference

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\cdeAuditCpgsTotal` | `25` | main:479 | CPGs scanned by conflict auditor. |
| `\cdeNormIntersectionN` | `10` | app:2180 | Normalizer blindspots also in CDE conflict audit. |
| `\scnTwelveImpactN` | `7` | app:2213 | Patterns with changed scoring after v1.1 patch. |

### 2.5 Tier-S Expansion Reference

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\tierSAggEpisodes` | `7654` | (auto_numbers) | Tier-S aggregate episodes. |
| `\tierSCorpusMultiplier` | `4` | (auto_numbers) | Corpus multiplier for Tier-S. |
| `\tierSGraphsPassed` | `31` | (auto_numbers) | Graphs passing Tier-S validation. |
| `\tierSGraphsTotal` | `31` | (auto_numbers) | Total Tier-S graphs. |
| `\tierSScenariosPassed` | `2480` | (auto_numbers) | Scenarios passing Tier-S. |
| `\tierSScenariosTotal` | `2480` | (auto_numbers) | Total Tier-S scenarios. |
| `\tierSExtraScenarios` | `535` | (auto_numbers) | Extra scenarios in Tier-S expansion. |

---

## Section 3: Structural / Corpus-Scope Macros (`v6-structural`)

These describe the corpus structure. v7 expansion changes some of these values.
Review each: if the paper explicitly scopes a claim to "25 CPGs" or "706 scenarios",
the structural macro must be updated if the scope changes.

| Macro | v6 Value | Usage locations | Notes |
|---|---|---|---|
| `\numGraphsMain` | `20` | (auto_numbers) | Core CPG graph count. |
| `\numGraphsHeldout` | `5` | main:419, app:1343 | Held-out graph count. |
| `\numGraphsTotal` | `25` | main:242, main:482 | Total CPG graphs. |
| `\numTotalScenarios` | `706` | main:476 | Total manual scenarios. |
| `\numManualScenarios` | `105` | main:242 | Expert-authored scenarios. |
| `\numAutoScenarios` | `601` | (auto_numbers) | Auto-generated scenarios. |
| `\numModels` | `9` | main:242, main:476, app:1315 | Models in Phase A evaluation. |
| `\numRuns` | `3` | main:242 | Runs per model-scenario pair. |
| `\numEpisodes` | `19,062` | main:242, main:255, main:482, app:807 | Phase A 9m total episodes. |
| `\numHardConstraints` | `1049` | (auto_numbers) | Total hard constraints across all graphs. |
| `\numForbidden` | `212` | (auto_numbers) | FORBIDDEN constraint count. |
| `\numMust` | `557` | (auto_numbers) | MUST constraint count. |
| `\numBefore` | `65` | (auto_numbers) | BEFORE constraint count. |
| `\numWithin` | `215` | (auto_numbers) | WITHIN constraint count. |
| `\numConditionalRules` | `312` | (auto_numbers) | Conditional rule count. |
| `\numNodes` | `167` | (auto_numbers) | Graph node count. |
| `\auditNGraphs` | `25` | (auto_numbers) | Graphs in constraint audit. |
| `\auditUniqueActions` | `611` | (auto_numbers) | Distinct action IDs across graphs. |

---

## Section 4: Additional `providecommand` Macros Used in Appendix

The following macros are defined via `\providecommand` (fallback definitions in the appendix
preamble), not in `auto_numbers.tex`. They are active in the current paper and most are
v6-baseline values needed for the normalizer appendix section.

| Macro | v6 Value | Category | Notes |
|---|---|---|---|
| `\normalizerMMEpisodes` | `16944` | v6-baseline | Multi-model replay episode count. |
| `\normalizerMMModels` | `8` | v6-baseline | Models in MM replay. |
| `\normalizerMMPerModelEpisodes` | `2118` | v6-baseline | Per-model episodes. |
| `\normalizerMMMeanDelta` | `+3.6` | v6-swap | Mean pp gap across 8 models. |
| `\normalizerMMMinDelta` | `+3.2` | v6-baseline | Min pp gap. |
| `\normalizerMMMaxDelta` | `+4.1` | v6-baseline | Max pp gap. |
| `\normalizerMMRangePP` | `0.9` | v6-baseline | Range pp spread. |
| `\normalizerMMSpearman` | `1.000` | v6-swap | Cross-model rank Spearman (perfect). |
| `\normalizerMMKendall` | `1.000` | v6-swap | Cross-model rank Kendall τ. |
| `\normalizerMMRankInversions` | `0` | v6-swap | Rank inversions across 8 models. |
| `\cwtFourTypeRetentionPct` | `82` | v7-swap | % matched-pair discrimination retained after deviation exclusion. |
| `\safetyCorePctOfStrictFA` | `12.8` | v7-swap | (duplicate; also in main `\providecommand` block) |
| `\safetyCoreWilsonLo` | `11.0` | v7-swap | (duplicate) |
| `\safetyCoreWilsonHi` | `14.9` | v7-swap | (duplicate) |
| `\faMustOnlyEpisodes` | `980` | v6-baseline | MUST-only omission cell count. |
| `\faForbidOnlyEpisodes` | `139` | v6-baseline | FORBIDDEN-only cell count. |
| `\faMixedSafetyEpisodes` | `5` | v6-baseline | FORBIDDEN+WITHIN mixed. |
| `\faBeforeOnlyEpisodes` | `0` | v6-baseline | BEFORE-only cell count. |
| `\strictFACritical` | `22` | v7-swap | (duplicate; primary definition here as providecommand) |
| `\strictFACritFracTotal` | `0.12` | v7-swap | (duplicate) |
| `\strictFAAOnlyPct` | `5.4` | v6-baseline | Phase A 8m for narrative. |
| `\phaseBEpisodes` | `76,464` | v6-baseline | Phase B corpus size. |
| `\cellPairReversal` | `26.5` | v6-baseline | Phase B cell-level pair reversal. |
| `\tierSExtraCPGs` | `17` | v7-swap | (also in auto_numbers providecommand) |
| `\tierSExtraEpisodes` | `11235` | v7-swap | (also in auto_numbers providecommand) |
| `\tierSMaxMetricShift` | `3` | v7-swap | (also in auto_numbers providecommand) |

---

## Section 5: v7 Switchover Action Plan

### Step 1 — Recompute v7-swap macros
Run the SGSC v7 evaluation pipeline on the expanded corpus and update the following
values in `paper/auto_numbers.tex`. For each macro, the new `\providecommand` block in
the appendix preamble will be overridden automatically since `\newcommand` takes priority.

**Critical path (abstract + findings section):**
1. `\strictFAThree` — headline FA rate
2. `\strictFAThreeCount` — paired count
3. `\kendallW` — concordance
4. `\reversalRate` — ranking reversal
5. `\safetyCoreFAEpisodes` + `\safetyCorePctOfStrictFA` + Wilson CIs
6. `\conflictPatternsN` / `\conflictGraphsN` / `\tierAN` / `\tierBN` / `\tierCN`
7. `\heldoutCondFA` + `\heldoutN`
8. `\graphValidatorChecksN` / `\graphValidatorGraphsN` / `\graphValidatorTotalN`
9. `\normalizerBlindspotN` / `\normalizerRawActionsN` / `\normalizerCanonicalN`
10. `\traceGraphsN` / `\traceQuoteCoverageRate` / `\traceReachabilityRate`

### Step 2 — Rename v6 reference macros
For macros that will be cited as v6 comparators in the paper text, rename the existing
definition (e.g., `\strictFAThreeSix`) and add the new v7 macro with the original name
so existing LaTeX prose compiles without changes.

### Step 3 — Structural macro review
Confirm whether the paper scope statement changes from "25 CPGs / 706 scenarios / 9 models".
If so, update the `v6-structural` group in Section 3.

### Step 4 — Verify `\providecommand` fallback consistency
The appendix preamble block (lines ~86–230 of `main_final_v18.tex` and the matching block
in `appendix_v18.tex`) contains fallback `\providecommand` definitions that are silently
overridden by `auto_numbers.tex`. After updating `auto_numbers.tex`, verify the fallback
values are also updated to avoid confusion when compiling appendix standalone.

### Step 5 — Regression check
Run:
```bash
# Verify no v7 macro names collide with existing v6 names
grep -c 'newcommand' paper/auto_numbers.tex

# Check paper compiles clean
pdflatex -interaction=nonstopmode paper/main_final_v18.tex 2>&1 | grep -E 'Error|Warning.*undefined'
```

---

## Appendix: Full Macro Definition Line Index (auto_numbers.tex)

Quick-reference line numbers for each targeted-family macro in `auto_numbers.tex`:

| Macro | Line |
|---|---|
| `\strictFAThree` | 592 |
| `\strictFAThreeCount` | 593 |
| `\strictFAFour` | 594 |
| `\strictFAFourCount` | 595 |
| `\strictFACriticalPct` | 596 |
| `\strictFAMedianViols` | 599 |
| `\friedmanChi` | 308 |
| `\friedmanP` | 309 |
| `\kendallW` | 310 |
| `\reversalRate` | 311 |
| `\rankBootstrapKendallW` | 645 |
| `\rankBootstrapKendallWLo` | 646 |
| `\rankBootstrapKendallWHi` | 647 |
| `\rankBootstrapTopOneStablePct` | 650 |
| `\heldoutAllObliviousFA` | 328 |
| `\heldoutCondFA` | 331 |
| `\heldoutN` | 469 |
| `\heldoutOrderingMatch` | 627 |
| `\heldoutOrderingMatchPct` | 628 |
| `\heldoutOrderingMeanRho` | 629 |
| `\heldoutFARate` | 1146 |
| `\heldoutFlipRate` | 1148 |
| `\heldoutCompliance` | 1149 |
| `\indomainCondFA` | 333 |
| `\indomainFARate` | 1150 |
| `\indomainCompliance` | 1151 |
| `\consensusFATotal` | 398 |
| `\consensusFARate` | 399 |
| `\consensusFACritical` | 400 |
| `\consensusFACriticalPct` | 401 |
| `\consensusFAModelRange` | 410 |
| `\auditNGraphs` | 413 |
| `\normalizerCurrentDelta` | (providecommand ~1047) |
| `\normalizerBlindspotN` | 1547 |
| `\normalizerRawActionsN` | 1542 |
| `\normalizerCanonicalN` | 1543 |
| `\normalizerMultiCanonicalN` | 1546 |
| `\strictFACritical` | 1500 (providecommand) |
| `\strictFACritFracTotal` | 1501 (providecommand) |
| `\strictFAThreePre` | 1512 (providecommand) |
| `\strictFAThreeFixed` | 1513 (providecommand) |
| `\conflictPatternsN` | 1514 (providecommand) |
| `\conflictGraphsN` | 1516 (providecommand) |
| `\tierAN` | 1517 (providecommand) |
| `\tierBN` | 1518 (providecommand) |
| `\tierCN` | 1519 (providecommand) |
| `\conflictViolationN` | 1520 (providecommand) |
| `\scnTwelveImpactN` | 1521 (providecommand) |
| `\safetyCorePctOfStrictFA` | 432 (providecommand) |
| `\safetyCoreWilsonLo` | 433 (providecommand) |
| `\safetyCoreWilsonHi` | 434 (providecommand) |
| `\graphValidatorChecksN` | 1531 (providecommand) |
| `\graphValidatorTotalN` | 1532 (providecommand) |
| `\graphValidatorGraphsN` | 1533 (providecommand) |
| `\graphValidatorErrorsN` | 1534 (providecommand) |
| `\normalizerUnmappedN` | 1544 (providecommand) |
| `\normalizerUnmappedPct` | 1545 (providecommand) |
| `\conflictTouchEpisodes` | 1555 (providecommand) |
| `\conflictTouchScenarios` | 1556 (providecommand) |
| `\conflictTouchPct` | 1557 (providecommand) |
| `\conflictTouchStrictPct` | 1558 (providecommand) |
| `\conflictTouchActionsN` | 1560 (providecommand) |
| `\traceGraphsN` | 1566 (providecommand) |
| `\traceQuoteCoverageRate` | 1570 (providecommand) |
| `\traceReachabilityRate` | 1576 (providecommand) |
| `\cdeAuditCpgsTotal` | 1525 (providecommand) |
| `\cdeNormIntersectionN` | 1515 (providecommand) |
| `\tierSAggEpisodes` | 1488 (providecommand) |
| `\tierSExtraCPGs` | 1490 (providecommand) |
| `\tierSExtraEpisodes` | 1491 (providecommand) |
| `\tierSMaxMetricShift` | 1495 (providecommand) |
| `\tierSGraphsPassed` | 1493 (providecommand) |
| `\tierSScenariosTotal` | 1497 (providecommand) |
| `\safetyCoreFAEpisodes` | 221 (providecommand) |
| `\safetyCoreFAPct` | 222 (providecommand) |
| `\numGraphsMain` | 214 |
| `\numGraphsHeldout` | 215 |
| `\numGraphsTotal` | 216 |
| `\numTotalScenarios` | 218 |
| `\numManualScenarios` | 4 |
| `\numAutoScenarios` | 5 |
| `\numModels` | 225 |
| `\numRuns` | 226 |
| `\numEpisodes` | 229 |
| `\numHardConstraints` | 238 |
| `\numForbidden` | 232 |
| `\numMust` | 233 |
| `\numBefore` | 235 |
| `\numWithin` | 236 |
| `\numConditionalRules` | 217 |
| `\numNodes` | 220 |
| `\cwtFourTypeRetentionPct` | 1417 (providecommand) |
