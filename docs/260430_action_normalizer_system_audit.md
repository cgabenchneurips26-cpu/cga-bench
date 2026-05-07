# Action Normalizer System-Wide Audit Report

**Date**: 2026-04-30
**Scope**: All 25 CPG graphs, ActionNormalizer, ViolationExtractor scoring path, 50,837 v6 episodes
**Status**: 715 confirmed false OMISSION violations identified — scoring is affected
**Trigger**: `docs/clinician_validation/260430_action_normalizer_dup_analysis.md`

---

## Executive Summary

The action normalizer duplication bug, initially discovered in the clinician validation display layer, is confirmed as a **system-wide problem that affects scoring**. The audit found **715 false OMISSION violations** across 50,837 v6 episodes (1.4% of all episodes), predominantly in auto-generated scenarios (694 auto, 21 manual). The root cause is a 3-layer pipeline failure: CPG graphs define synonym action IDs, the auto-generation script propagates them raw into `expected_actions`, and the normalizer fails to converge them to the same canonical form.

### Key Numbers

| Metric | Value |
|--------|-------|
| False OMISSION violations confirmed | **715** |
| Candidate-to-confirmation rate | **96.6%** (715 / 740) |
| From auto-generated scenarios | **694** (97.1%) |
| From manual scenarios | **21** (2.9%) |
| Graphs affected | **3** (kdigo_contrast_aki, idsa_meningitis, ada_dka_management) |
| Episodes with both synonym forms | **6,129** (12.1% of all episodes) |
| Compliance score delta | +1.74 pp (affected group biased upward by other factors; false OMISSION drags score DOWN from correct value) |

---

## Layer-by-Layer Analysis

### Layer 1: CPG Graph Synonym Action IDs

**Finding**: 60 HIGH-severity intra-node synonym pairs across 25 graphs.

When CPG graph YAML files are hand-authored across different development phases, the same clinical action gets defined under different `action_id` strings. Two manifestations:

- **Intra-node**: Both IDs appear in the same node's `allowed_actions` or `mandatory_actions` (e.g., `order_echocardiogram` and `order_imaging_echocardiogram` in the same node of `atrial_fibrillation.yaml`)
- **Cross-node**: Different nodes in the same graph use different IDs for the same action (e.g., `order_stat_ct_head` in early nodes vs `stat_ct_head` in later nodes of `aha_stroke_2019.yaml`)

**Impact**: Agents see both IDs in their `available_actions` list and may use either form depending on LLM output. Both forms get stored in episode logs.

### Layer 2: DIRECT_MAPPINGS Duplicate Keys

**Finding**: 0 duplicate keys found via AST parsing of current source.

The runtime values confirm the analysis doc's findings (e.g., `optimize_fluid_status` → `optimize_volume_status`, `discontinue_nephrotoxins` → `hold_nephrotoxic_medications`), but the AST parser found no actual duplicate keys in the current version of `action_normalizer.py`. The Python dict already resolved these — only the last value persists.

**Impact**: No active scoring impact from this layer in the current codebase.

### Layer 3: Circular / Non-Convergent Aliases

**Finding**: 13 HIGH (circular), 78 MEDIUM (non-convergent) alias pairs.

The normalizer performs a single-pass lookup. When mappings form chains (A→B→C) or cycles (A→B, B→A), the result depends on which input you start with.

**Confirmed circular alias with scoring impact**:

```
assess_urine_output  →  normalize()  →  monitor_urine_output
monitor_urine_output →  normalize()  →  assess_urine_output
```

These two IDs normalize to **each other**, so `are_aliases()` returns `False` and `_action_satisfies_requirement()` fails at all 3 matching steps.

**Other confirmed scoring-safe pairs** (normalizer converges correctly):
- `stat_ct_head` ↔ `order_stat_ct_head` → both converge to `order_stat_ct_head` ✓
- `give_bronchodilator` ↔ `give_short_acting_bronchodilator` → both converge ✓
- `give_antibiotics` ↔ `give_broad_spectrum_antibiotics` → both converge ✓

### Layer 4: Scoring Impact (L1 Pairs)

**Finding**: 0 CRITICAL from L1 pairs. All 80 L1 synonym pairs converge under normalization.

This means the normalizer handles most graph-level synonyms correctly. The scoring bugs arise from a different class of problem — same-action pairs that **diverge** under normalization (Layer 5).

### Layer 5: Same Action, Different Canonical (Scoring Bugs)

**Finding**: 7 confirmed bugs where the same clinical action normalizes to different canonical forms.

| # | Graph | Pattern | Action A → Canonical A | Action B → Canonical B | Mandatory |
|---|-------|---------|------------------------|------------------------|-----------|
| 1 | `kdigo_contrast_aki` | prefix_lab | `order_creatinine` → `check_baseline_egfr` | `order_lab_creatinine` → `order_lab_bmp` | No |
| 2 | `kdigo_contrast_aki` | circular_alias | `assess_urine_output` → `monitor_urine_output` | `monitor_urine_output` → `assess_urine_output` | **Yes** |
| 3 | `pulmonary_embolism` | prefix_imaging | `order_ecg` → `obtain_12_lead_ecg` | `order_imaging_ecg` → `order_imaging_electrocardiogram` | No |
| 4 | `idsa_meningitis` | assessment_verb | `assess_neurological_status` → (identity) | `monitor_neurological_status` → (identity) | **Yes** |
| 5 | `ada_dka_management` | word_order_flip | `consult_endocrinology` → (identity) | `endocrinology_consult` → (identity) | No |
| 6 | `aha_stroke_2019` | verb_dropped | `give_osmotic_therapy` → (identity) | `osmotic_therapy` → (identity) | No |
| 7 | (normalizer-level) | circular_alias | `assess_urine_output` ↔ `monitor_urine_output` | never converges | **Yes** |

**Why the scorer fails**: `ViolationExtractor._action_satisfies_requirement()` (`violations.py:642-667`) has 3 matching steps:

1. **Step 1** (exact match): Fails when agent uses form B but graph mandates form A
2. **Step 2** (normalize both): Fails because `normalize(A) != normalize(B)` for these 7 bugs
3. **Step 3** (`are_aliases()`): Fails because `are_aliases()` normalizes both sides and compares — same result as step 2

Result: **false OMISSION violation** recorded.

---

## Auto vs Manual Analysis

### Scenario Distribution

| Graph | Manual | Auto | Total |
|-------|--------|------|-------|
| `kdigo_contrast_aki` | 5 | 37 | 42 |
| `pulmonary_embolism` | 5 | 24 | 29 |
| `ada_dka_management` | 12 | 30 | 42 |
| `aha_stroke_2019` | 13 | 24 | 37 |
| `idsa_meningitis` | 0 | 31 | 31 |

### Episode Impact Split

| Bug | Manual false OMISSION | Auto false OMISSION | Total |
|-----|----------------------|---------------------|-------|
| `idsa_meningitis`: assess/monitor_neurological_status | 0 | **477** | 477 |
| `kdigo_contrast_aki`: assess/monitor_urine_output | 0 | **217** | 217 |
| `ada_dka_management`: consult/endocrinology_consult | **18** | 0 | 18 |
| `kdigo_contrast_aki`: order/order_lab_creatinine | **3** | 0 | 3 |
| **Total** | **21** | **694** | **715** |

### Root Cause: Auto-Generation Pipeline

The auto-generation pipeline in `scripts/generate_scenarios_v3.py` (lines 128-142) derives `expected_actions` by iterating ALL CPG graph nodes and collecting their `mandatory_actions`:

```python
# generate_scenarios_v3.py:128-138
# Precompute expected_actions per diagnosis from CPG mandatory_actions.
global_union: list[str] = []
seen: set[str] = set()
for node in (graph.get("nodes") or {}).values():
    for a in node.get("mandatory_actions") or []:
        if a not in seen:
            global_union.append(a)
            seen.add(a)
```

**Problem**: When the graph defines `assess_neurological_status` as mandatory in node A and `monitor_neurological_status` as mandatory in node B, BOTH end up in `expected_actions`. The `seen` set only catches exact duplicates, not semantic equivalents.

**Causal chain**:

```
CPG graph has "assess_neurological_status" in node A
  AND "monitor_neurological_status" in node B
    ↓
generate_scenarios_v3.py collects BOTH into expected_actions (no normalization)
    ↓
auto_generated_scenarios.yaml stores both:
  expected_actions: [assess_neurological_status, monitor_neurological_status, ...]
    ↓
Agent performs "monitor_neurological_status" (one form only)
    ↓
ViolationExtractor checks: was "assess_neurological_status" performed?
  Step 1: "monitor_neurological_status" != "assess_neurological_status" → FAIL
  Step 2: normalize("monitor...") = "assess..." but normalize("assess...") = "monitor..." → FAIL
  Step 3: are_aliases() → normalize both → still different → FAIL
    ↓
FALSE OMISSION violation recorded
```

### Why Auto Is Disproportionately Affected

| Factor | Manual | Auto |
|--------|--------|------|
| `expected_actions` authoring | Hand-curated, typically uses ONE form | Algorithmically derived from ALL graph nodes |
| Synonym deduplication | Human author naturally picks consistent naming | Script uses `set()` dedup — only catches exact duplicates |
| `idsa_meningitis` scenarios | 0 manual (no manual file exists) | 31 auto — 100% from auto-generation |
| Graph coverage | Authors cherry-pick specific paths | Cross-product covers ALL branches → encounters ALL synonym pairs |

The manual scenarios for `ada_dka_management` (18 false OMISSIONs) contain `endocrinology_consult` in `expected_actions` — this was hand-authored using the word-order-flipped form, while agents consistently output `consult_endocrinology`.

---

## Compliance Score Impact

| Group | N | Mean compliance | Mean violations |
|-------|---|-----------------|-----------------|
| Affected (false OMISSION present) | 712 | 0.4435 | 11.82 |
| Unaffected (same graphs, no false OMISSION) | 7,569 | 0.4261 | 13.48 |

The affected group scores +1.74 pp higher than unaffected — counterintuitive until we note that affected episodes are ones where the agent DID perform the action (under the wrong name). These agents are generally higher-performing. The false OMISSION **artificially lowers** their score from what it should be. The true delta (if false OMISSIONs were removed) would be even larger.

---

## Pattern Taxonomy

| Pattern | Description | Bugs | Auto-gen root cause |
|---------|-------------|------|---------------------|
| **circular_alias** | A→B and B→A in normalizer DIRECT_MAPPINGS | 2 | Normalizer design: single-pass, no fixed-point iteration |
| **assessment_verb_variant** | `assess_X` vs `monitor_X` for same measurement | 1 | Graph uses both; auto-gen collects both |
| **prefix_lab** | `order_X` vs `order_lab_X` for same lab test | 1 | Graph lists both naming conventions |
| **prefix_imaging** | `order_X` vs `order_imaging_X` for same study | 1 | Graph lists both; normalizer maps asymmetrically |
| **word_order_flip** | `verb_noun` vs `noun_verb` for same action | 1 | Graph uses different forms in different nodes |
| **verb_dropped** | `give_X` vs `X` (verb prefix missing) | 1 | Graph drops prefix in later nodes |

---

## Recommended Fixes

### P0: Fix False OMISSION Violations (Immediate)

**Fix A**: Add normalizer pass in `generate_scenarios_v3.py` and `generate_all_scenarios.py`:

```python
from cga_bench.assessor_core.action_normalizer import ActionNormalizer

normalizer = ActionNormalizer()

# After collecting expected_actions:
canonical_seen = set()
deduped = []
for a in expected_actions:
    canonical = normalizer.normalize(a)
    if canonical not in canonical_seen:
        canonical_seen.add(canonical)
        deduped.append(canonical)  # Store canonical form, not raw
expected_actions = deduped
```

**Fix B**: Fix the 3 normalizer divergences:

1. Add `"assess_neurological_status": "monitor_neurological_status"` (or vice versa) to DIRECT_MAPPINGS
2. Add `"endocrinology_consult": "consult_endocrinology"` to DIRECT_MAPPINGS
3. Break the `assess_urine_output` ↔ `monitor_urine_output` circular alias by picking one canonical form

### P1: Graph-Level Deduplication

Run `scripts/ci/audit_action_normalizer_system.py` to identify all synonym pairs, then clean up the 5 affected graphs to use consistent action IDs.

### P2: Normalizer Fixed-Point Iteration

Change `normalize()` to iterate until convergence (max 3 steps) to prevent circular aliases:

```python
def normalize(self, action_id, cpg_id=None):
    result = action_id
    for _ in range(3):
        next_result = self._single_pass_normalize(result, cpg_id)
        if next_result == result:
            break
        result = next_result
    return result
```

### P3: CI Gate

Add `scripts/ci/audit_action_normalizer_system.py` to CI pipeline. Gate: 0 CRITICAL findings allowed.

---

## Artifacts

| File | Description |
|------|-------------|
| `evidence_pack/analysis/action_normalizer_system_audit.json` | Full L1-L4 machine-readable report (251 findings) |
| `scripts/ci/audit_action_normalizer_system.py` | Audit script (runnable, exit code 1 = issues found) |
| `docs/260430_action_normalizer_system_audit.md` | This document |
| `docs/clinician_validation/260430_action_normalizer_dup_analysis.md` | Original trigger analysis |

---

## Appendix A: Per-Bug Episode Detail

### Bug #1: `idsa_meningitis` — assess/monitor_neurological_status (477 false OMISSIONs)

- **100% auto-generated** (no manual meningitis scenarios exist)
- Auto-generated `expected_actions` contains BOTH `assess_neurological_status` AND `monitor_neurological_status`
- Agents consistently output `monitor_neurological_status` (monitoring is the agent's framing)
- The system expects `assess_neurological_status` and records OMISSION

### Bug #2: `kdigo_contrast_aki` — assess/monitor_urine_output (217 false OMISSIONs)

- **100% auto-generated**
- `assess_urine_output` appears in `post_contrast_monitoring` node
- `monitor_urine_output` appears in `risk_assessment` node
- Agents perform `monitor_urine_output`; system expects `assess_urine_output`
- Circular alias in normalizer prevents convergence

### Bug #3: `ada_dka_management` — consult/endocrinology_consult (18 false OMISSIONs)

- **100% manual** (all 18 from hand-authored DKA scenarios)
- Manual `expected_actions` uses `endocrinology_consult` (word order flip)
- Agents consistently output `consult_endocrinology` (verb-first convention)
- Normalizer has no mapping between these forms

### Bug #4: `kdigo_contrast_aki` — order/order_lab_creatinine (3 false OMISSIONs)

- **100% manual**
- Both forms coexist in the same `risk_assessment` node
- `order_creatinine` → `check_baseline_egfr` (AKI-domain specific mapping)
- `order_lab_creatinine` → `order_lab_bmp` (generic pattern rule)
- Most agents perform both forms (556 episodes), but 3 manual episodes only perform `order_creatinine`

---

## Appendix B: Reproduction Commands

```bash
# Run the full 4-layer audit
PYTHONPATH=. python scripts/ci/audit_action_normalizer_system.py

# Verify specific normalizer behavior
PYTHONPATH=. python -c "
from cga_bench.assessor_core.action_normalizer import ActionNormalizer
n = ActionNormalizer()
print(n.normalize('assess_urine_output'))   # monitor_urine_output
print(n.normalize('monitor_urine_output'))  # assess_urine_output
print(n.are_aliases('assess_urine_output', 'monitor_urine_output'))  # False
"
```
