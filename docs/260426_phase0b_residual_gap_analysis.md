# Phase 0.B — Residual Gap Analysis & Inconsistency Resolution

> **Status**: Post-Phase 0 critical review response
> **Date**: 2026-04-26
> **Scope**: 9 uncovered evaluator areas (§II), 7 internal inconsistencies (§III), 4 implicit decisions (§IV)
> **Evidence basis**: All code paths grep'd and read; no speculation.

---

## II. Residual Evaluator Gaps — Evidence-Based Assessment

### II.1 LLM-Judge Input Field Audit — AUTHOR-DEPENDENCY CONFIRMED

**Two independent LLM-judge pipelines exist:**

| Pipeline | Script | Prompt variants | Receives `expected_actions`? | Author-dependent? |
|----------|--------|----------------|-----------------------------|--------------------|
| EX-1 | `run_ex1_llm_judge.py` | T0/T1/T2/T3 | **No** (line 99-136: only `actions`, no constraints) | No |
| EXP-2 | `exp_2_llm_judge.py` | rubric_free / rubric_aware / cot_judge | **Partial** (see below) | Partially |

**Per-template breakdown** (from `configs/llm_judge_prompts/`):

| Template | `expected_actions` | `forbidden_actions` | `sequence_constraints` | Author-dependent? |
|----------|-------------------|--------------------|-----------------------|--------------------|
| `rubric_free.jinja2` | No | No | No | **No** |
| `rubric_aware.jinja2` | **Yes** (line 17) | **Yes** (line 14) | **Yes** (line 20) | **Yes** |
| `cot_judge.jinja2` | **Yes** (line 17) | **Yes** (line 14) | **Yes** (line 20) | **Yes** |

**Source of leakage**: `exp_2_llm_judge.py:294-296` injects scenario config fields:
```python
"forbidden_actions": sc.get("forbidden_actions", []),
"expected_actions": sc.get("expected_actions", []),
"sequence_constraints": sc.get("sequence_constraints", []),
```

**Impact on paper hero numbers**: Paper macros `\termJudgeTzeroFA` through `\termJudgeTthreeFA`
come from EX-1 pipeline (T0-T3), which does NOT receive expected_actions.
These are **author-independent** and safe.

However, if any paper number cites rubric_aware or cot_judge variants, those
numbers are **author-dependent** (CPG constraints fed directly to judge as rubric).

**Phase 1 action**: Tag each LLM-judge macro with its source pipeline.
rubric_aware/cot_judge results should be disclosed as "oracle-informed" baselines.

### II.2 MedAgentBench (MAB) Replay Scorer

Deferred to Phase 1. Requires audit of `replay_adapters/` directory.
Paper hero number: `\mimicMABDetectionLoss{63.2}`.

### II.3 AgentClinic (AC) Replay Scorer

Deferred to Phase 1. Paper hero number: `\mimicACDetectionLoss{84.2}`.

### II.4 OracleAgent Score Formula

Deferred to Phase 1. Paper macros: `\oracleMeanGap`, `\oracleNDomains`.

### II.5 Constructive pi_nord Witness — ALREADY DOCUMENTED

The pi_nord witness is fully documented in the shim inventory table
(`tables_audit_kit_shim_inventory.tex:19-20`):

- V1_strict: BSR=0.5076, pi-class=aset (registered shim, canonical harness run)
- V3_half_expected: BSR=0.4914 (`\piNordWitnessBSR`), gap factor 164x vs pi_nord floor 0.003

The pi-class labeling (aset, not nord) is correct per the behavioural classifier.
The "pi_nord witness" name reflects the INTENDED test target, not the
achieved pi-class. This framing should be explicit in the paper.

**Phase 1 action**: Clarify in paper text that "pi_nord witness" tested whether
a pi_nord-admissible evaluator could approach the Bayes floor; the result shows
it cannot — it behaviorally collapses to pi_aset, demonstrating a
164x achievability gap.

### II.6 Pose B Catalogue x Evaluator

Deferred to Phase 1. Paper macros: `\mainReplTriplePct{36.31}` etc.

### II.7 Reversal Rate — DEFINITION VERIFIED

From `verify_friedman_eta.py:236-268`:

```
For each model pair (i,j) in C(n_models, 2):
  For each evaluator pair (e1,e2):
    If model_i ranked higher than model_j by e1
       BUT model_i ranked lower than model_j by e2:
      → reversal found for this model pair (break)
reversal_rate = n_reversed_pairs / n_total_pairs * 100
```

- **Unit**: model-pair level (NOT episode-level, NOT scenario-level)
- **7 models** → C(7,2) = 21 pairs → 75% ≈ 15-16/21 pairs reversed
- **8 models** → C(8,2) = 28 pairs → paper also says "21/28" in v17 text
- `\reversalRate{75.0}` is from 7-model (v5/W8) computation

**IMPORTANT**: `recompute_hero_numbers.py:59-102` uses a DIFFERENT definition —
per-scenario, per-evaluator-pair reversal counting. This yields a different
(much higher) percentage. The two should NOT be conflated.

**Phase 1 action**: Ensure paper cites the model-pair-level definition (75%)
and not the scenario-level variant. Add explicit formula to spec document.

### II.8 X1/X2 Violation Ablation

Deferred to Phase 1.

### II.9 Robustness Dashboard Probes

Deferred to Phase 1. Each probe has different verdict dependency.

---

## III. Internal Inconsistencies — Resolution

### III.1 n_viols +0.74 Correlation Explanation — STALE TEXT, FIX NEEDED

**The contradiction** (verbatim):

Phase 0 report §4.3:
> "아무것도 안 하는 에이전트: n_viols = 0 (commission/timing 없음), 그러나 omission으로 TCC **FAIL**"

Phase 0 spec §2.1 (TCC verdict definition):
> "omission은 제외... 아무것도 하지 않은 에이전트(omission만 있는)도 TCC를 **통과**한다"

**Resolution**: The report §4.3 text is **WRONG**. The spec §2.1 is **CORRECT**.

Under the Phase 0 TCC definition (HARD = {commission, timing, sequence}),
omission-only agents have:
- n_viols = 0 (no commission or timing)
- v4_hard = False (TCC **PASSES** — no hard violations)

The +0.74 positive correlation holds because:
- **Active agents** that perform many actions accumulate BOTH commission/timing
  violations (n_viols > 0) AND hard violations (v4_hard = True / TCC fail)
- **Inactive agents** that do nothing have n_viols = 0 AND v4_hard = False (TCC pass)
- The n_viols proxy is CONCORDANT with v4_hard, not discordant

**ADDITIONAL PAPER BUG**: `tables_audit_kit_shim_inventory.tex:36` says:
> "viol_count is **anti-correlated** with d_G"

But `tables_audit_kit_shim_inventory.tex:25` shows:
> `ρ(d_G) = **+**0.74`

The `+` sign contradicts "anti-correlated". The footnote text should say
"**positively** correlated" or simply "correlated".

**Affected files**:
- `docs/260426_phase0_spec_freeze_report.md` §4.3 — fix explanation
- `paper/tables_audit_kit_shim_inventory.tex:36` — fix "anti-correlated" → "positively correlated"

### III.2 eta-squared Values — THREE DIFFERENT COMPUTATIONS

**Evidence from codebase** (4 distinct value sets found):

| Source | eta2(eval) | eta2(run) | Ratio | Evaluator set | Data |
|--------|-----------|-----------|-------|--------------|------|
| `auto_numbers.tex:262-264` | 0.078 | <0.001 | 200,000x | ASC,CwT,PAF,TCC (4, no TOM) | Binary verdicts |
| `auto_numbers.tex:878-879` (CRES-5) | 0.072 | 0.0515 | ~1.4x | Unknown | CRES-5 specific |
| `verify_friedman_eta.py:415-417` (comparison target) | 0.312 | 0.036 | 8.7x | Unknown | Historical |
| MEMORY.md canonical | 0.284 | ~0.009 | 31.2x | Unknown | W8? Different path |

**Root cause**: Each script computes eta-squared differently:
1. `audit_all_auto_numbers.py:296-335` — 1-way ANOVA on flattened (episode × evaluator) data
2. `verify_friedman_eta.py:320-410` — Same 1-way approach, but loads raw episodes not verdict matrix
3. `recompute_hero_numbers.py:105-141` — Same formula but uses verdict_matrix_v6_typed.json
4. CRES-5 — Possibly different evaluator subset or continuous scores (not binary)

**Key issue**: The **ratio** is what matters for the paper claim. 200,000x and 1.4x
tell completely different stories.

- 200,000x comes from eta2(run) ≈ 0.0000004, which is near-zero because run means
  are almost identical (range < 0.01). This is the CORRECT interpretation: evaluator
  explains 7.8% of variance, run explains ~0%.
- 1.4x comes from CRES-5 which may use continuous scores or a different evaluator set
  where run variance is higher.

**Phase 1 action (CRITICAL)**:
1. Pick ONE canonical computation path and lock it
2. Recompute with typed verdicts
3. Document which evaluator set (4 non-degenerate vs 5 vs 6)
4. Paper abstract should cite the LOCKED value, not a mixture

### III.3 DxEM Pass Rate — CONFIRMED BUG, TWO CONFLICTING MACROS

**Evidence**:
- `auto_numbers.tex:249`: `\passrateDxEM{100.0}` — **CORRECT** per Phase 0 spec
- `auto_numbers.tex:994`: `\dxemPassRate{50.5}` — **WRONG** (stale or misattributed)

**Usage**:
- `\passrateDxEM` used in main tables (correct)
- `\dxemPassRate` used in shim inventory footnote: "dxem returns pass on 50.5% of episodes (degenerate)"

**Probable origin of 50.5**: TCC pass rate is 49.5% (`\passrateCGA{49.5}`).
TCC **fail** rate = 100 - 49.5 = 50.5. The 50.5 was likely the TCC fail rate
misattributed to dxemPassRate.

**Fix needed**:
- `auto_numbers.tex:994`: Change `\dxemPassRate{50.5}` → `\dxemPassRate{100.0}`
- `tables_audit_kit_shim_inventory.tex:36`: Footnote text automatically corrected

### III.4 ASC Pi-Class — STRUCTURAL vs BEHAVIOURAL DISTINCTION

**Structural analysis**: ASC computes `|performed ∩ expected| / |expected|` —
this is a set operation, structurally pi_aset.

**Behavioural classification**: Separating-pair test classifies ASC as pi_nctx.

**Resolution**: The discrepancy is real but NOT a bug. ASC's verdict depends on
`expected_actions`, which varies per-scenario (patient context determines which
actions are mandatory). Therefore ASC is **structurally** pi_aset but
**behaviourally** pi_nctx — it implicitly conditions on context through the
scenario-dependent expected_actions set.

**Phase 1 action**: Paper should explicitly state:
> "ASC operates on action sets (structurally pi_aset) but is classified as
> pi_nctx by the behavioural separation test because expected_actions varies
> with patient context."

### III.5 Strict FA 6.6% vs All-Oblivious 11.6% — RESOLVED, CONSISTENT

**Definitions from code** (`audit_all_auto_numbers.py:250-251`,
`exp_strict_consensus_fa.py:6-7`):

| Macro | Definition | Count | Rate |
|-------|-----------|-------|------|
| `\faAllOblivious{11.6}` | TOM ∩ ASC ∩ CwT pass + TCC fail (PAF **not** required) | 1,959 | 11.6% |
| `\strictFAThree{6.6}` | ASC ∩ PAF ∩ CwT pass + TCC fail (PAF required) | 1,118 | 6.6% |
| `\strictFAFour{6.6}` | TOM ∩ ASC ∩ PAF ∩ CwT pass + TCC fail (= strictFA3, TOM=100%) | 1,118 | 6.6% |

Since TOM=100%, faAllOblivious = (ASC ∩ CwT pass + TCC fail) without PAF gate.
Adding PAF requirement makes it more restrictive → fewer false accepts → 6.6% < 11.6%. **Consistent.**

**Note**: `evidence_pack/exact_verdicts/exact_auto_numbers_update.tex:25` has
`\faAllOblivious{25.1}` — this is from a DIFFERENT (v6 full? different C2?) computation.
Phase 1 must reconcile which corpus/C2-variant each macro comes from.

### III.6 Per-Violation-Type Bayes Matrix — GAP CONFIRMED

Phase 0 spec §3.4 documents only 4 aggregate Bayes errors (term/aset/nord/nctx).
Paper has 20 per-type cells (`\bayesErrTermOmission` etc.). These are not
covered by Phase 0 and must be recomputed under typed verdicts in Phase 3.

### III.7 Bootstrap CIs — GAP CONFIRMED

Phase 0 spec §6 documents bootstrap parameters (B=1000, seed=42) but does not
include CI results. Paper macros `\bayesErrTermCI{[0.428,0.444]}` etc. exist.
Phase 3 must recompute.

---

## IV. Implicit Decision Verification

### IV.1 Corpus — v6 = 16,944 LOCKED

Phase 0 locks v6 (16,944 episodes, 8 models). The "18,586" figure mentioned in
earlier analysis likely comes from a different snapshot (possibly including
expansion scenarios). 16,944 = 8 models × 706 scenarios × 3 runs = 16,944. **Verified.**

### IV.2 d_G — d_G-typed (alpha) LOCKED

Phase 0 spec §3: commission(1.0) + timing(0.5) + sequence(0.6), DEVIATION excluded.

### IV.3 C1 Handling — epsilon (keep + flag) LOCKED

Phase 0 spec Appendix B retains C1 formula unchanged. DEVIATION is flagged as
author-dependent in the source-grounding audit (§10) but not dropped.
This is backward-compatible and correct.

### IV.4 TOM — RESOLVED

100% pass rate, excluded from non-degenerate evaluator pool. Documented.

### IV.5 Pre-registration — INTERNAL TAG

Git tag `re-experiment-v1-spec-frozen` applied. No external pre-registration
(arXiv/OSF) planned. Internal scope is sufficient for NeurIPS review.

### IV.6-IV.7 — OPEN

New experiments inclusion and sensitivity reporting depth are deferred to Phase 4+.

---

## Priority Actions for Phase 1 Entry

### P0 (block Phase 1)

| # | Item | Files affected | Action |
|---|------|---------------|--------|
| 1 | Fix `\dxemPassRate{50.5}` → 100.0 | `auto_numbers.tex:994` | Change value |
| 2 | Fix shim table "anti-correlated" | `tables_audit_kit_shim_inventory.tex:36` | "positively correlated" |
| 3 | Fix report §4.3 omission explanation | `docs/260426_phase0_spec_freeze_report.md` | Rewrite paragraph |
| 4 | Lock ONE eta-squared computation path | `auto_numbers.tex:262-264` | Audit + decide |

### P1 (before Phase 2 re-scoring)

| # | Item | Files affected | Action |
|---|------|---------------|--------|
| 5 | Tag LLM-judge macros by pipeline | Paper text | Disclose rubric variants as oracle-informed |
| 6 | ASC pi-class framing | Paper text | Add structural vs behavioural explanation |
| 7 | Reversal rate definition | `re_experiment_protocol_v1.md` | Add explicit formula |
| 8 | faAllOblivious corpus reconciliation | Multiple | Check 11.6% vs 25.1% (exact_verdicts) |

### P2 (Phase 3 recompute)

| # | Item |
|---|------|
| 9 | Per-violation-type Bayes matrix (20 cells) |
| 10 | Bootstrap CIs for all Bayes errors |
| 11 | Typed CwT verdict impact on all hero numbers |
| 12 | MAB/AC replay scorer audit |
| 13 | OracleAgent score formula spec |
| 14 | Pose B catalogue x evaluator verification |
| 15 | X1/X2 ablation verdict definitions |
| 16 | Robustness dashboard probe dependencies |

---

## Appendix: v4_hard Semantics Cross-Reference

Multiple code paths use different v4_hard conventions:

| Script | Convention | Evidence |
|--------|-----------|----------|
| `recompute_hero_numbers.py:38-41` | v4_hard=True → HAS violations → TCC FAIL | Explicit comment |
| `recompute_hero_numbers.py:71` | `(not ep[ev])` when ev=v4_hard → inverts for pass rate | Inversion on use |
| `audit_all_auto_numbers.py:241` | `v["TCC"]` with direct boolean comparison | Uses TCC key, not v4_hard |
| `verdict_matrix_v6.json` | v4_hard=True/False as flat boolean | Source of truth |

The convention v4_hard=True means "episode has hard violations" (TCC FAILS it)
is empirically verified but creates INVERTED semantics vs other evaluator columns
where True=pass. This inversion is a recurrent source of bugs.

**Phase 1 recommendation**: Verdict definitions module should export a
`tcc_pass(ep)` convenience that returns `not ep["v4_hard"]` to eliminate
the inversion confusion.
