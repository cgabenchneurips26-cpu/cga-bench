# 3-Tier Action-ID Normalizer — Design & Rationale

**Date**: 2026-04-21  
**Owner**: CGA-Bench benchmark integrity  
**Supersedes**: implicit 1-tier Jaccard normalizer in `agent_runner/rag_agent.py`

---

## 1. Problem statement (summary)

From `260421_empty_actions_root_cause.md` §1-§4:

- Up to 98.6 % of episodes in some `ex_w8_crossmodel` cells terminate early with `consecutive_empty_actions`.
- Real raw capture shows the LLM returns well-formed JSON with clinically-reasonable `action_id` suggestions.
- Those suggestions are rejected by `_normalize_action_id` because they use different conventions than the scenario's per-node `available_actions` list (e.g. `order_lactate` vs `order_lab_lactate`; `order_cbc_with_diff` vs `order_cbc`).
- Jaccard ≥ 0.7 fallback cannot bridge these gaps; Jaccard < 0.7 introduces false matches.
- An alias map of 41 canonical groups / 98 variants (added 2026-04-21 by sub-agent) covers **68 %** of 1,558 observed emissions. A further 2 % can be caught by cross-referencing `universal_clinical_safety.yaml` (75 general-emergency ids). **30 % (471 calls, 25 unique ids) remains uncovered** and would still produce empty actions under the current design.

The empty-action termination is the single most impactful failure mode in the benchmark; it contaminates W8 appendix and (to a lesser degree) E1-E5 macros.

## 2. Guiding principles (user-stated)

1. **The alias map is for CPG-derived canonical ids only.** It MUST NOT be a dumping ground for every model-emitted string; expanding it aggressively creates false-positive merges between clinically distinct actions (e.g. `order_chem_7` — basic 7-test — vs `order_lab_comprehensive_metabolic_panel` — 14-test). These merges would pollute the ground-truth scoring.
2. **Out-of-guideline actions should be recorded, not rejected.** If the model emits a clinically plausible action that is NOT in any CPG graph or synonym of one, that is a **DEVIATION** — a protocol-relevant signal. Forcing an empty-action return discards this signal and causes early termination.
3. **Universal Clinical Safety (UCS) is the general-emergency fallback.** `cpg_model/graphs/universal_clinical_safety.yaml` already enumerates 75 domain-independent "general ER workup" ids. These are clinically appropriate regardless of the specific CPG scenario.
4. **The normalizer must never return `[]` for a non-empty LLM response.** The "empty" signal from the agent must mean "the LLM itself emitted nothing" or "every emitted id failed safety review", not "we couldn't match the id lexically".

## 3. The 3-tier (actually 4-tier) design

Let `S` = scenario's current-node `available_actions` (the strict per-node allowed set).  
Let `A` = alias map reverse lookup (`action_alias_map.yaml::reverse_map`).  
Let `U` = universal_clinical_safety.yaml's allowed action set (75 ids).

For each `action_id` emitted by the model:

```
                                                   ┌─── id ∈ S? ─────────────────────┐
                                                   │                                  │
Tier 1 — exact match in scenario                   │ Yes → return Action(id)          │
                                                   │ No  → try Tier 2                 │
                                                   └──────────────────────────────────┘

                                                   ┌─── A[id] ∈ S? ──────────────────┐
                                                   │                                  │
Tier 2 — alias → canonical → scenario              │ Yes → return Action(A[id])       │
                                                   │ No  → try Tier 3                 │
                                                   └──────────────────────────────────┘

                                                   ┌─── id ∈ U or A[id] ∈ U? ────────┐
                                                   │                                  │
Tier 3 — universal emergency workup fallback       │ Yes → return Action(id,          │
                                                   │          tag=GENERAL_WORKUP)     │
                                                   │ No  → Tier 4                     │
                                                   └──────────────────────────────────┘

                                                   ┌──────────────────────────────────┐
                                                   │                                  │
Tier 4 — DEVIATION (out-of-guideline but not       │ Always → return Action(id,       │
          safety-reviewed; clinically plausible    │           tag=DEVIATION)         │
          proposal)                                 │                                  │
                                                   └──────────────────────────────────┘
```

Only one case still returns `[]` from `_normalize_action_id`:

- **The LLM itself emits no action_id at all** (JSON parse failure, empty list, refusal text).

This is a materially different signal from "we couldn't normalise an id the model did emit".

## 4. Scoring semantics

Scoring isolation (CLAUDE.md §Architecture) means the normalizer lives in the AGENT side. It does not touch `cpg_engine/` or `assessor_core/`. BUT the downstream scorer DOES see the `tag` field on each emitted `Action`. The scorer policy:

| Tag | Example | Scorer treatment |
|---|---|---|
| (none, Tier 1) | `order_cbc` in AABB scenario | per guideline: contributes to C2_mandatory_completion if mandatory, otherwise in allowed set |
| (none, Tier 2 canonical resolved) | `order_lactate` → `order_lab_lactate`, matched to AABB sepsis panel | same as Tier 1 (agent-side remapping is invisible to scorer; scorer sees the canonical id) |
| `GENERAL_WORKUP` | `order_lab_blood_culture` when scenario is DKA and it's in UCS but not in DKA graph's allowed_actions | counted toward the denominator of C1 path-selection, but not flagged as OMISSION/COMMISSION. Does not reduce compliance score. |
| `DEVIATION` | `order_chem_7`, `assess_burn_depth` for a non-burn scenario | DEVIATION violation (1 of the 5 violation types). Reduces compliance score weighted by `violation_type_weights["DEVIATION"]`. |

Observation about Tier 3: `GENERAL_WORKUP` is **NOT** a deviation — it's clinically defensible "general emergency care" that happens to be outside the specific CPG. The scorer should treat it neutrally (no penalty, no credit), preserving the benchmark's ability to discriminate guideline-adherent agents from general-purpose agents.

Tier 4 `DEVIATION` is a *real* guideline violation — the agent took an action that is neither in the scenario's graph nor in universal-emergency fallback. This should be penalised under existing DEVIATION weights.

## 5. Implementation sketch

### 5.1 `agent_runner/rag_agent.py` — `_normalize_action_id`

Current flow (simplified):
```python
def _normalize_action_id(self, action_id, available_actions):
    if action_id in available_actions: return action_id            # Tier 1
    if action_id in self._alias_reverse_map:                        # Tier 2
        canonical = self._alias_reverse_map[action_id]
        if canonical in available_actions: return canonical
    # Jaccard fallback
    best = _jaccard_best(action_id, available_actions, thresh=0.7)
    if best: return best
    return None    # ← this is what makes _generate_actions return []
```

Proposed flow:
```python
def _normalize_action_id(self, action_id, available_actions):
    if action_id in available_actions:
        return (action_id, None)                                    # Tier 1
    if action_id in self._alias_reverse_map:
        canonical = self._alias_reverse_map[action_id]
        if canonical in available_actions:
            return (canonical, None)                                # Tier 2
    if action_id in self._universal_safety_actions:
        return (action_id, "GENERAL_WORKUP")                         # Tier 3
    # map via alias into UCS, in case alias canonical is UCS id
    if action_id in self._alias_reverse_map:
        canonical = self._alias_reverse_map[action_id]
        if canonical in self._universal_safety_actions:
            return (canonical, "GENERAL_WORKUP")                     # Tier 3 via alias
    best = _jaccard_best(action_id, available_actions, thresh=0.7)
    if best:
        return (best, None)                                         # kept for backward compatibility
    return (action_id, "DEVIATION")                                  # Tier 4 — never return None
```

Key change: the function signature becomes `(resolved_id, tag_or_None)` and **never returns `None`**.

### 5.2 `agent_runner/rag_agent.py` — `_generate_actions`

Where the code currently does:
```python
normalized = self._normalize_action_id(raw_id, avail)
if normalized is None:
    continue    # → leads to empty action list → consecutive_empty_actions
```

New code:
```python
resolved_id, tag = self._normalize_action_id(raw_id, avail)
action = Action(
    action_id=resolved_id,
    type=infer_action_type(resolved_id),
    args=parsed_args,
    timestamp_minutes=current_time,
    justification=justification_text,
    semantic_tag=tag,    # new field; None, "GENERAL_WORKUP", or "DEVIATION"
)
actions.append(action)
```

### 5.3 `cpg_model/schemas/base.py` — `Action` schema

Add an optional field:
```python
@dataclass
class Action:
    type: ActionType
    action_id: str
    args: Dict[str, Any]
    timestamp_minutes: float
    justification: Optional[str] = None
    semantic_tag: Optional[str] = None   # "GENERAL_WORKUP" | "DEVIATION" | None
```

Scoring-isolation note: adding a field is compatible with both the agent side and the scoring side. The field is purely informational to scorers; if scorers ignore it, behaviour is identical to the previous system. If scorers honour it (Tier 3 → no-op, Tier 4 → DEVIATION violation), the new semantics kick in.

### 5.4 `assessor_core/violations.py` — Tier 4 honouring

Existing DEVIATION violation detection:
```python
if action.action_id not in allowed_actions and not is_justified:
    violations.append(Violation(type=DEVIATION, ...))
```

New detection path:
```python
if action.semantic_tag == "DEVIATION":
    violations.append(Violation(type=DEVIATION, source="normalizer_tier4", ...))
elif action.semantic_tag == "GENERAL_WORKUP":
    pass   # neutral; neither credit nor penalty
elif action.action_id not in allowed_actions and not is_justified:
    violations.append(Violation(type=DEVIATION, source="scoring_direct", ...))   # existing path
```

This lets us distinguish DEVIATIONs that came through the normalizer from those detected at scoring time, for downstream analysis.

## 6. Coverage expectations (empirical)

Based on `results/debug_raw_test/` raw-sample capture (1,558 calls, 41 unique emitted ids):

| Tier | unique covered | calls covered | cumulative % |
|---|---:|---:|---:|
| Tier 1 (exact) | depends on scenario; see field data | — | baseline |
| Tier 2 (alias) | 14 | 1,059 | 68.0 % |
| Tier 3 (UCS) | +2 | +28 | 70.0 % |
| Tier 4 (DEVIATION) | +25 | +471 | 100.0 % |

After Tier 4, `consecutive_empty_actions` termination drops to ~0 % for cells currently at 98 %, because the normalizer ALWAYS returns something. The 25 ids that would now be tagged DEVIATION will be penalised at scoring time — which is the correct benchmark behaviour (they ARE deviations from the guideline).

## 7. Why this is the correct design

- **Scoring fairness**: model-emitted ids that are clinically bogus (Tier 4 DEVIATION) are properly penalised, not silently ignored.
- **Benchmark integrity**: scenarios with narrow per-node `available_actions` (e.g. AABB has only 5 ids at some nodes) do not artificially collapse to 98 % empty-termination just because the model uses sensible general-ER workup vocabulary.
- **Signal preservation**: the narrow-mode behaviour of qwen4b_react (emitting `order_lab_lactate` across AABB / AKI / stroke / DKA) is measurable as "wrong action for wrong scenario" — exactly a DEVIATION. The existing system discarded this signal.
- **Agent-scorer separation preserved**: the agent remains the sole author of `semantic_tag`; the scorer is the sole consumer. Neither side imports each other's private modules.

## 8. Known limitations

1. **Semantic merging risk** (kept conservative): the alias map does NOT auto-merge near-dupes like `order_chem_7` → `order_lab_comprehensive_metabolic_panel` because they are clinically distinct (7-test vs 14-test). Such ids remain Tier 4 DEVIATION. A future iteration could add a `conservative_semantic_merge` pass for verified equivalences.
2. **UCS coverage is modest** (~75 ids). Ids like `obtain_patient_weight`, `assess_burn_depth`, `assess_airway` are legitimate clinical assessments that are not in UCS today. They will be DEVIATION until UCS is expanded. This is acceptable: DEVIATION is a documented violation type, not an error.
3. **Narrow-mode (qwen4b)** is still a model-capability problem; this design does NOT fix the fact that qwen4b_react emits 6 unique ids across 20 different scenarios. What it DOES fix is: those 6 ids no longer cause early termination — the episode now runs to completion and the scorer correctly flags the scenario-context collapse as cumulative DEVIATION violations.

## 9. Rollout plan

1. **Implement §5.3 schema change** (non-breaking, optional field).  
2. **Implement §5.1 normalizer changes**; add unit tests covering each tier.  
3. **Implement §5.2 `_generate_actions` change** (returns Action with tag instead of dropping).  
4. **Implement §5.4 scorer tag-honouring**; update scoring unit tests.  
5. **Dry-run**: `CGA_DEBUG_RAW_RESPONSE=1 scripts/experiments/full_690_runner.py qwen4b_react --dry-run CGA_DRY_N=20 CGA_DRY_RUNS=1` — expect empty% to drop from 98 % to < 5 %. Compliance score should land between 0.2 and 0.5 (DEVIATION-heavy but non-trivial).  
6. **Full re-run** of the 7 contaminated W8 cells + 3 empty `*_tooluse` cells (user decision #2) + `qwen4b`, `deepseek_r1_7b`, `nemotron30b` in `full_706_v5` (Step-0 reverify decision).  
7. **Aggregate + paper macro diff**; document in `260421_macro_diff.md`.

## 10. File inventory

| File | Change |
|---|---|
| `agent_runner/rag_agent.py` | add UCS load in `__init__`; rewrite `_normalize_action_id`; rewrite `_generate_actions` normalise loop |
| `cpg_model/action_alias_map.yaml` | unchanged; existing 41 groups keep working |
| `cpg_model/graphs/universal_clinical_safety.yaml` | unchanged; consumed as source of Tier 3 set |
| `cpg_model/schemas/base.py` | add `semantic_tag: Optional[str]` to `Action` |
| `assessor_core/violations.py` | honour `semantic_tag` when computing DEVIATION violations |
| `tests/test_agents/test_three_tier_normalizer.py` (new) | 6-8 tests covering each tier |
| `docs/attack_gap_exp_exp/260421_three_tier_normalizer_design.md` | this document |
