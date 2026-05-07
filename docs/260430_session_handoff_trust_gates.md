# Session Handoff — SGSC Trust Gates Implementation
<!-- Date: 2026-04-30 ~08:35 UTC -->

## Summary

Implementing 8 trust gates from critical gap analysis (`docs/attack_gap_exp_exp/260430_sgsc_critical_gap.md`).
Plan approved and execution started. Phases A-D running in parallel; E-H blocked on dependencies.

---

## Phase Status

| Phase | Gate | Status | Agent | Notes |
|-------|------|--------|-------|-------|
| **A** | Fix C-8 assertion + atom granularity doc | **DONE** | main thread | Strict AND assertion, atom.py docstring updated |
| **B** | Public/private scenario split + leakage scanner | **DONE** | a4a82d7 (completed) | 258 tests passed. Split functions, 7 new leak patterns, pipeline output split |
| **C** | Field-level entailment (mandatory) | **IN PROGRESS** | a4deb1f (running) | Entailment checker rewritten with 6 fields. Fixing: fixture atoms failing sequence entailment → adjusting rule-based checker |
| **D** | MC/DC coverage extension + ALTERNATIVE | **IN PROGRESS** | ab86a77 (running) | CoverageType expanded (7→13), sequence+alternative families added. Fixing: test_coverage_type_values count mismatch |
| **E** | Compiler mutation testing (7 injections) | PENDING | — | Blocked on B+D |
| **F** | Observation leakage closure (cds_assistance) | PENDING | — | Blocked on B |
| **G** | Dataset manifest + CI | PENDING | — | Blocked on B |
| **H** | E2E harness + clinician validation packet | PENDING | — | Blocked on B+C+D |

---

## Completed Changes (Phase A + B)

### Phase A — Files Modified
1. **`tests/test_sgsc/test_pipeline_e2e.py:276-277`** — C-8 assertion strengthened:
   - Before: `assert result.hallucination_rate > 0.5 or len(result.atoms) == 0` (OR-logic weakness)
   - After: `assert len(result.atoms) == 0` AND `assert result.hallucination_rate == 1.0` (strict AND)
2. **`sgsc/schemas/atom.py:1-15`** — Module docstring rewritten:
   - Clarifies atom = atomic action-constraint pair, NOT guideline recommendation
   - Example decomposition: "blood cultures before antibiotics within 1 hour" → 3 atoms
   - Documents naming invariant: `{guideline}_{action}_{constraint}`

### Phase B — Files Modified (by agent a4a82d7)
1. **`sgsc/compilers/scenario_compiler.py:252-319`** — Added:
   - `_PRIVATE_KEYS` / `_PUBLIC_KEYS` frozensets
   - `split_scenario_public_private()` — splits full scenario into agent-visible + scorer-only
   - `seeds_to_split_scenario_yaml()` — generates both public and private dicts
2. **`sgsc/audit/leakage_scanner.py`** — Added:
   - 7 new patterns: `expected_actions`, `forbidden_actions`, `mandatory_actions`, `ground_truth`, `trap_description`, `passing_compliance_threshold`, `coverage_targets`
   - `scan_public_scenarios()` — checks public scenarios for private field leakage
3. **`sgsc/pipeline.py`** — Added:
   - `scenarios_public` / `scenarios_private` fields on `PipelineResult`
   - Step 13 outputs `{id}_scenarios_public.json` + `{id}_scenarios_private.json`
   - Step 14 runs public-only leakage audit
4. **`tests/test_sgsc/test_scenario_compiler.py`** — 4 new tests (`TestPublicPrivateSplit`)
5. **`tests/test_sgsc/test_leakage_scanner.py`** — 5 new tests (`TestPublicLeakageScanner`)

---

## In-Progress Changes (Phase C + D)

### Phase C — Field-Level Entailment (a4deb1f)
- **`sgsc/verification/entailment_checker.py`** — Full rewrite with 6 field-level checks:
  - action, guard, exclusion, timing, sequence, evidence
  - Rule-based fallback when no LLM available
- **`sgsc/pipeline.py`** — `enable_entailment` removed, `entailment_mode` added
- **Known issue being fixed**: Rule-based sequence check too strict for fixture atoms — agent is adjusting thresholds
- **New test file**: `tests/test_sgsc/test_entailment_checker.py`

### Phase D — MC/DC Coverage (ab86a77)
- **`sgsc/schemas/coverage.py`** — 6 new CoverageType members:
  - `GUARD_TRUE`, `GUARD_FALSE`, `TIMING_COMPLIANT`, `TIMING_VIOLATED`, `ORDER_COMPLIANT`, `ORDER_VIOLATED`
  - `ALTERNATIVE` activated (was reserved placeholder)
- **`sgsc/optimizer/coverage_tracker.py`** — New extraction functions:
  - `extract_guard_pair_items()`, `extract_timing_pair_items()`, `extract_order_pair_items()`, `extract_alternative_items()`
- **`sgsc/compilers/counterfactual_compiler.py`** — New family generators:
  - `compile_sequence_families()`, `compile_alternative_families()`
- **Known issue being fixed**: `test_coverage_type_values` asserts `len(CoverageType) == 7` but now 13

---

## Current Test Failures (6)

All caused by Phase C + D in-progress changes:

| Test | Cause | Fix Owner |
|------|-------|-----------|
| `test_optional_fields` | `enable_entailment` removed from PipelineConfig | Phase C agent |
| `test_full_pipeline_precomputed` | Entailment rejects all fixture atoms | Phase C agent |
| `test_forbidden_atoms_create_families` | Entailment rejects all fixture atoms | Phase C agent |
| `test_mutations_generated` | Entailment rejects all fixture atoms | Phase C agent |
| `test_coverage_type_values` | CoverageType count 7→13 | Phase D agent |
| `test_combines_both_types` | Counterfactual families expanded | Phase D agent |

---

## Remaining Work After C+D Complete

### Phase E — Compiler Mutation Testing
- 7 mutation injections: deadline offset, direction reversal, FORBIDDEN↔REQUIRED swap, guard negation, quote hash mismatch, prior merge drop, private field leakage
- New test file: `tests/test_sgsc/test_compiler_mutation_robustness.py`

### Phase F — Observation Leakage Closure
- Add `cds_assistance: bool = False` to `EnvironmentConfig` in `scenario_engine/environment.py`
- Make `mandatory_actions` in `Observation` conditional on `cds_assistance=True`
- Default benchmark: empty list (no leakage)

### Phase G — Dataset Manifest
- New file: `sgsc/manifest.py` — `BenchmarkManifest` dataclass + hash verification
- CI integration for scenario count validation

### Phase H — E2E Harness + Clinician Packet
- `sgsc/e2e_harness.py` — real-corpus end-to-end validation
- `sgsc/validation_packet.py` — clinician review packet generator (100 atom + 100 constraint + 60 scenario + 60 trace reviews)

---

## Key Decisions

1. **Entailment made mandatory** (Gate 2): No more `enable_entailment` flag. Mode is `entailment_mode: str` with values `rule_based` / `llm` / `llm_strict`.
2. **ALTERNATIVE activated** (Gate 5 / 8.3): Was reserved placeholder, now generates actual alternative-branch families from `counterfactual_pairs`.
3. **Public/private split** is structural, not optional: Pipeline always outputs both files; leakage audit runs on public-only.

---

## Background Agent IDs (for resume)

- `a4a82d7` — Phase B (COMPLETED)
- `a4deb1f` — Phase C (RUNNING — field-level entailment)
- `ab86a77` — Phase D (RUNNING — MC/DC coverage)

---

## Commands to Continue

```bash
# Check current test state
PYTHONPATH=. pytest tests/test_sgsc/ -q --tb=short

# After C+D agents complete, run full verification
PYTHONPATH=. pytest tests/test_sgsc/ -v

# Proceed to Phase E (after D completes)
# Proceed to Phase F (after B — already done)
# Proceed to Phase G (after B — already done)
```

## Git State

- Branch: `eval_science`
- Last commit: `03aeed58` (P0 fixes + analysis report)
- Uncommitted: Phase A+B+C+D changes (commit after all pass)
- Plan file: `/home/anonymous-user/.claude/plans/structured-imagining-reef.md`
