# SGSC Self-Critical Review Report

**Date**: 2026-04-30
**Scope**: Full SGSC implementation (49 files, 6,543 lines, 249 tests)
**Commit under review**: `1e55b3ee` (feat(sgsc): source-grounded scenario compiler)
**Method**: 4 parallel code-reviewer agents (schema, compiler, optimizer/audit, test coverage)

---

## Executive Summary

| Severity | Count | Action Required |
|----------|-------|-----------------|
| Critical | 8 | Must fix before production use |
| Major | 39 | Should fix before paper submission |
| Minor | 48 | Low-risk improvements |
| Nit | 13 | Style/documentation only |
| **Total** | **108** | |

The SGSC implementation is structurally sound: all 249 tests pass, the E2E pipeline produces valid CPG graphs and scenarios loadable by existing CGA-Bench infrastructure, and the 6-layer architecture (schemas -> extraction -> verification -> compilers -> optimizer -> audit) cleanly separates concerns. However, 8 critical findings identify logic bugs and type-safety gaps that would cause silent failures on real-world guideline corpora beyond the SSC sepsis pilot.

---

## Critical Findings (8)

### C-1: `_group_atoms_by_section` defaultdict misuse (compiler)
**File**: `sgsc/compilers/graph_compiler.py:35-40`
**Severity**: Critical (data loss risk)

```python
groups: dict[str, list[RecommendationAtom]] = defaultdict(list)
for atom in atoms:
    key = atom.source.section.strip() or "General"
    groups[key] = groups.get(key, [])  # BUG: bypasses defaultdict
    groups[key].append(atom)
```

The code declares a `defaultdict(list)` but then uses `.get(key, [])` which creates a **new** plain list on every first access, discarding the defaultdict's auto-created list. This works by accident because the new list is immediately assigned back, but it means the `defaultdict` machinery is entirely dead code. More critically, if the logic were ever refactored to rely on `defaultdict` behavior (e.g., `groups[key].append(atom)` without the `.get()` guard), the existing `.get()` pattern would silently override it.

**Fix**: Either use `defaultdict` properly (`groups[key].append(atom)` without `.get()`) or use a plain `dict` with explicit initialization.

---

### C-2: BEFORE constraints produce semantically wrong required_prior_actions (compiler)
**File**: `sgsc/compilers/graph_compiler.py:78-84`

The `required_prior_actions` dict is populated from `atom.sequence.required_prior`, but BEFORE constraints (line 136-142 in `_wire_sequence_edges`) only wire `next_nodes` edges and never populate `required_prior_actions`. This means:

- A BEFORE(blood_cultures, antibiotics) constraint correctly creates an edge from blood_cultures_node -> antibiotics_node
- But the `required_prior_actions` field on the antibiotics node is only populated if the atom explicitly declares `sequence.required_prior`, NOT from `constraint.type == "BEFORE"`

For the SSC sepsis pilot this works because `ssc_r2_blood_cultures` explicitly sets `required_prior`, but guidelines where BEFORE is the only ordering signal will have empty `required_prior_actions` despite having `next_nodes` edges.

**Fix**: In `_build_node()`, also populate `required_prior_actions` from atoms with `constraint.type == "BEFORE"` where `atom.sequence.before` lists actions that must come after.

---

### C-3: recommendation_class raw string crashes for GRADE-based guidelines (compiler)
**File**: `sgsc/compilers/graph_compiler.py:106`

```python
"recommendation_class": rep.evidence.recommendation_class,
```

Uses the first atom's `recommendation_class` as-is. AHA guidelines use "I", "IIa", "IIb", "III" which matches existing CPG graphs. But GRADE-based guidelines (SSC, KDIGO) use "Strong"/"Weak" and some use numeric scales. The CPGNode schema validates `recommendation_class` against a fixed set in some code paths. Any GRADE guideline will produce invalid graph nodes.

**Fix**: Add a `_normalize_recommendation_class()` helper that maps GRADE -> AHA-equivalent (Strong -> "I", Weak -> "IIa") or store both systems with explicit `evidence_system` field.

---

### C-4: ConstraintType inconsistency between SGSC and base.py (schema)
**File**: `sgsc/schemas/atom.py` vs `cpg_model/schemas/base.py`

SGSC's `VALID_CONSTRAINT_TYPES` includes `"EXPECTED"` which does not exist in the base `ConstraintType` enum. Additionally, `AtomConstraint.type` is a plain `str` validated against a frozen set, while the rest of the codebase uses `ConstraintType` enum values. This creates a type-safety gap where SGSC-produced constraints with `type="EXPECTED"` will fail when passed to `DerivedConstraint` or `ViolationExtractor`.

**Fix**: Either add `EXPECTED` to `ConstraintType` in `base.py`, or remove it from SGSC's valid set and map it to `REQUIRED` during compilation.

---

### C-5: AtomConstraint.type as plain str instead of enum/Literal (schema)
**File**: `sgsc/schemas/atom.py`

`AtomConstraint.type: str` with a `@field_validator` checking membership in `VALID_CONSTRAINT_TYPES`. This is weaker than using `Literal["FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN", "EXPECTED"]` or the `ConstraintType` enum, because:

1. IDE autocomplete/type-checking doesn't work
2. Typos in test fixtures aren't caught by mypy
3. Downstream code doing `if atom.constraint.type == "REQIRED"` won't be flagged

**Fix**: Use `Literal` type annotation: `type: Literal["FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN"]`

---

### C-6: Set-cover solver ignores required_k (optimizer)
**File**: `sgsc/optimizer/set_cover_solver.py`

`CoverageItem` has a `required_k: int = 1` field (for k-coverage: requiring k distinct scenarios to cover the same item). The `SetCoverSolver.solve()` method never reads `required_k` -- it marks an item as covered after a single scenario covers it. This means the coverage guarantee is weaker than specified.

For the current pilot (k=1 everywhere), this is benign. But the schema advertises k-coverage support that doesn't exist, which is misleading.

**Fix**: Either implement k-coverage in the solver (decrement a counter per item, only mark covered when counter reaches 0) or remove `required_k` from the schema to avoid false advertising.

---

### C-7: ALTERNATIVE coverage type never extracted (optimizer)
**File**: `sgsc/optimizer/coverage_tracker.py`

The `_extract_coverage_items()` method handles 6 of 7 coverage types (RECOMMENDATION, CONSTRAINT, GUARD, BOUNDARY, MUTATION, SOURCE) but has no extraction logic for ALTERNATIVE. The coverage report always shows `alternative: {total: 0, covered: 0}`. This means clinically equivalent branches (e.g., norepinephrine vs vasopressin for septic shock) are never tested for coverage.

**Fix**: Add ALTERNATIVE extraction logic. The data source should be `atom.scenario_hooks.counterfactual_pairs` or a new `alternatives` field on atoms. For now, at minimum document that ALTERNATIVE is a placeholder.

---

### C-8: Trivially-true assertion in test_forbidden_atoms_create_families (tests)
**File**: `tests/test_sgsc/test_counterfactual_compiler.py`

```python
assert len(families) >= 0  # Always true for any list
```

This test claims to verify that forbidden atoms create counterfactual families but the assertion passes even when `families` is empty (which is the actual result, since forbidden-only atoms don't generate families). The test provides zero verification value.

**Fix**: Either assert `len(families) == 0` with a comment explaining why forbidden atoms don't generate families, or implement family generation for forbidden atoms and assert `len(families) > 0`.

---

## Major Findings (39)

### Compiler Layer (7 major)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| M-C1 | Node type taxonomy collapse: only `plan` and `action` emitted, never `enquiry` or `decision` | `graph_compiler.py:98` | Existing CPG graphs use 4 node types; SGSC graphs are structurally simpler |
| M-C2 | Node merging (max_nodes enforcement) drops `required_prior_actions` and doesn't dedup action lists | `graph_compiler.py:214-224` | Merged nodes may have duplicate action IDs and lose ordering constraints |
| M-C3 | `_section_to_node_id` generates non-deterministic IDs when sections differ only in punctuation | `graph_compiler.py:43-49` | Two sections like "Hour-1 Bundle" and "Hour 1 Bundle" produce the same node_id, triggering dedup suffix |
| M-C4 | `scenario_compiler.py` uses fixed patient template (age=55, M) for all scenarios | `scenario_compiler.py` | No demographic diversity; boundary scenarios don't vary patient context |
| M-C5 | `counterfactual_compiler.py` generates empty `shared_trace_template` for all families | `counterfactual_compiler.py` | Families have pivot variables but no trace steps to replay |
| M-C6 | `mutation_compiler.py` SWAP mutation uses hardcoded `"alternative_action"` placeholder | `mutation_compiler.py` | Swap mutations are structurally invalid -- no actual alternative action selected |
| M-C7 | `constraint_compiler.py` maps BEFORE atoms to DerivedConstraint but `expected_actions` field is always empty for BEFORE type | `constraint_compiler.py` | BEFORE constraints compile to DerivedConstraints with no expected_actions |

### Schema Layer (8 major)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| M-S1 | `SourceReference.quote_hash` not validated as SHA-256 format | `atom.py` | Any string accepted; no integrity check |
| M-S2 | `PopulationCriteria` has no interaction with scenario generation | `atom.py` | Inclusion/exclusion criteria are stored but never used to filter scenarios |
| M-S3 | `ScenarioSeed.boundaries` type `BoundarySpec` not defined inline -- imported from separate model | `seed.py` | Type chain is fragile if BoundarySpec changes |
| M-S4 | `CounterfactualFamily.members` minimum length not enforced by validator | `family.py` | A family with 0 or 1 members is structurally invalid but passes validation |
| M-S5 | `CoverageReport.coverage_ratio` computed externally, not as `@computed_field` | `coverage.py` | Ratio can be inconsistent with `total_items` and `covered_count` |
| M-S6 | `GuidelineQualityCard` AGREE-II scores not bounded to valid range [1-7] | `quality.py` | Quality scores can be 0 or 100 without validation error |
| M-S7 | `TraceStep.action_id` doesn't cross-validate against atom canonical_ids | `family.py` | Trace steps can reference non-existent actions |
| M-S8 | `MutationTemplate.mutation_type` is plain str, not enum | `seed.py` | No compile-time validation of mutation types |

### Optimizer/Audit Layer (7 major)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| M-O1 | `coverage_tracker.py` GUARD extraction only checks `activation_event is not None` | `coverage_tracker.py` | Any atom with an activation event generates a GUARD item, even non-conditional ones |
| M-O2 | `set_cover_solver.py` greedy selection doesn't consider scenario cost/complexity | `set_cover_solver.py` | Solver minimizes count but not computational cost of running scenarios |
| M-O3 | `leakage_scanner.py` only checks `PrivateFields` model, not actual scenario JSON output | `leakage_scanner.py` | Leakage scan validates the seed's private_fields declaration, not the compiled scenario |
| M-O4 | `source_fidelity.py` entailment aggregation treats PENDING as non-entailed | `source_fidelity.py` | Atoms not yet checked count against entailment rate |
| M-O5 | `coverage_reporter.py` markdown table doesn't escape pipe characters in item descriptions | `coverage_reporter.py` | Descriptions containing `|` break markdown table rendering |
| M-O6 | `pipeline.py` step 12 (set-cover) runs even when coverage is already 100% | `pipeline.py` | Unnecessary computation; also masks the signal that coverage was trivially complete |
| M-O7 | `atom_proposer.py` JSON repair doesn't handle LLM outputting YAML instead of JSON | `atom_proposer.py` | Some LLMs (especially Qwen) output YAML when asked for JSON; this silently fails |

### Test Layer (17 major)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| M-T1 | No negative test for AtomConstraint with invalid type string | `test_schemas.py` | Validator coverage gap |
| M-T2 | No test for graph_compiler with multiple sections (multi-node graph) | `test_graph_compiler.py` | Only single-section (1 node) tested |
| M-T3 | No test for graph_compiler max_nodes enforcement (node merging) | `test_graph_compiler.py` | Merging logic untested |
| M-T4 | No test for scenario_compiler with FORBIDDEN-only atoms | `test_scenario_compiler.py` | Edge case untested |
| M-T5 | No test for counterfactual_compiler pivot_threshold extraction | `test_counterfactual_compiler.py` | Threshold logic untested |
| M-T6 | No test for mutation_compiler SWAP and REORDER types | `test_mutation_compiler.py` | Only OMISSION and LATE tested |
| M-T7 | No test for coverage_tracker with duplicate atoms (same action, different constraints) | `test_coverage_tracker.py` | Dedup behavior untested |
| M-T8 | No test for set_cover_solver with conflicting coverage items | `test_set_cover_solver.py` | Edge case untested |
| M-T9 | No test for leakage_scanner with actual leaked private fields | `test_leakage_scanner.py` | Only passing case tested |
| M-T10 | No test for pipeline with LLM extraction (even mocked) | `test_pipeline_e2e.py` | Pipeline E2E only tests precomputed-atoms path |
| M-T11 | No test for CLI argument parsing | (missing) | CLI untested |
| M-T12 | No test for quote_verifier with Unicode/CJK text | `test_quote_verifier.py` | Internationalization untested |
| M-T13 | No property-based tests (hypothesis) for schema round-trip | `test_schemas.py` | Only fixed fixtures tested |
| M-T14 | No integration test verifying SGSC output loads in ScenarioLoader | `test_pipeline_e2e.py` | Compatibility assumed but not tested |
| M-T15 | E2E test assertions are too loose: `coverage_ratio > 0` instead of specific value | `test_pipeline_e2e.py` | Regression detection is weak |
| M-T16 | No test for entailment_checker mock behavior | (missing) | Entailment checker untested |
| M-T17 | No test for multi_model_agreement filtering | (missing) | Agreement filter untested |

---

## Minor Findings (48)

### Schema Layer (8 minor)

| ID | Finding |
|----|---------|
| m-S1 | `atom_id` format not enforced (e.g., `{guideline}_{rec_number}` convention) |
| m-S2 | `ScenarioHooks` could be merged into `AtomConstraint` to reduce nesting |
| m-S3 | `PrivateFields` defaults are all empty lists -- consider making them computed from atoms |
| m-S4 | `FamilyMember.expected_verdict` is str, could be enum (PASS/FAIL/PARTIAL) |
| m-S5 | `CoverageType` enum values are UPPER_CASE but comparison strings are mixed case in tracker |
| m-S6 | `BoundarySpec` lacks `unit` field for dimensional analysis |
| m-S7 | `quality.py` RIGHT checklist items lack severity weights |
| m-S8 | `MutationTemplate` has no `description` field for human readability |

### Compiler Layer (5 minor)

| ID | Finding |
|----|---------|
| m-C1 | `_section_to_node_id` imports `re` inside function body (should be module-level) |
| m-C2 | `_build_node` uses `atoms[0]` as representative without sorting by evidence strength |
| m-C3 | `scenario_compiler` doesn't set `max_duration_minutes` from atom deadline constraints |
| m-C4 | `counterfactual_compiler` hardcodes `"boundary"` as default pivot variable type |
| m-C5 | `constraint_compiler` doesn't handle atoms with both BEFORE and WITHIN constraints |

### Optimizer/Audit Layer (8 minor)

| ID | Finding |
|----|---------|
| m-O1 | `coverage_tracker` SOURCE type extraction doesn't verify quote non-empty |
| m-O2 | `set_cover_solver` tie-breaking is arbitrary (first in iteration order) |
| m-O3 | `scenario_selector` doesn't return uncovered items for debugging |
| m-O4 | `source_fidelity` doesn't compute per-guideline hallucination rates |
| m-O5 | `leakage_scanner` regex patterns are hardcoded, not configurable |
| m-O6 | `coverage_reporter` LaTeX output not implemented (placeholder `_format_latex`) |
| m-O7 | `pipeline.py` doesn't log intermediate step timings |
| m-O8 | `cli.py` doesn't validate that output directory is writable before starting |

### Test Layer (27 minor)

| ID | Finding |
|----|---------|
| m-T1 | `conftest.py` sample atom uses SSC-specific values; need diverse fixtures |
| m-T2 | No parametrized tests for different constraint types in compiler tests |
| m-T3 | Test file naming inconsistency: `test_set_cover_solver.py` vs `test_coverage_tracker.py` |
| m-T4 | No smoke test for `sgsc.cli` module import |
| m-T5 | Missing `__init__.py` in `tests/test_sgsc/` (may affect collection) |
| m-T6 | `test_quote_verifier.py` doesn't test partial quote matching |
| m-T7 | `test_graph_compiler.py` doesn't verify `_generation_pipeline` metadata |
| m-T8 | No test for empty atoms list in counterfactual compiler |
| m-T9 | No test for single-atom input across all compilers |
| m-T10 | `test_schemas.py` doesn't test `model_json_schema()` output stability |
| m-T11 | No test for `CoverageReport` with 0 total items |
| m-T12 | No test for `GuidelineQualityCard` with all-zero scores |
| m-T13 | `test_pipeline_e2e.py` uses hardcoded atom dicts instead of conftest fixtures |
| m-T14 | No test for pipeline with empty recommendations list |
| m-T15 | No test for pipeline with duplicate atom IDs |
| m-T16 | No test for graph compiler with atoms from multiple guidelines |
| m-T17 | No test for scenario compiler respecting `passing_compliance_threshold` |
| m-T18 | No test for mutation compiler `max_mutations` config limit |
| m-T19 | No test for coverage reporter JSON output validity |
| m-T20 | No test for source_fidelity with all UNGROUNDED atoms |
| m-T21 | No test for hallucination_detector threshold computation |
| m-T22 | No performance benchmark for set_cover_solver with large input |
| m-T23 | No test for schema_validator business rule checks |
| m-T24 | No test for atom_proposer prompt formatting |
| m-T25 | No test for entailment_checker with edge-case LLM responses |
| m-T26 | No regression test for the `required_prior_actions` fix (C-2) |
| m-T27 | No test verifying `VERSION` file matches pipeline output version string |

---

## Nit Findings (13)

| ID | Finding |
|----|---------|
| n-1 | `sgsc/__init__.py` has no `__version__` attribute (reads from VERSION file each time) |
| n-2 | `sgsc/schemas/__init__.py` re-exports could use `__all__` for explicit API surface |
| n-3 | Several docstrings use `"""` on same line as content (Google style prefers newline after `"""`) |
| n-4 | `graph_compiler.py` section separator comments use `# ---` with varying dash counts |
| n-5 | `pipeline.py` step numbering in comments doesn't match spec (spec says 15 steps, code has 13) |
| n-6 | `cli.py` uses `argparse` but project convention is `click` (see `run_benchmark.py`) |
| n-7 | `coverage_reporter.py` markdown output doesn't include generation timestamp |
| n-8 | `atom_proposer.py` system prompt is 800+ characters inline; should be a constant or template file |
| n-9 | `set_cover_solver.py` variable name `selected` could be more descriptive (`selected_scenarios`) |
| n-10 | `leakage_scanner.py` uses print() for debug output instead of logging |
| n-11 | `source_fidelity.py` function parameter order inconsistent with other modules |
| n-12 | `hallucination_detector.py` returns float but some callers expect percentage (0-100 vs 0-1) |
| n-13 | `multi_model_agreement.py` hardcodes `agreement_threshold=0.5` as default |

---

## Risk Assessment

### Production Readiness by Layer

| Layer | Files | Tests | Readiness | Blockers |
|-------|-------|-------|-----------|----------|
| Schemas | 7 | 42 | **Good** | C-4, C-5 (type safety) |
| Extraction | 3 | 12 | **Stub** | LLM integration untested |
| Verification | 3 | 18 | **Good** | Unicode edge cases |
| Compilers | 6 | 89 | **Fair** | C-1, C-2, C-3 (logic bugs) |
| Optimizer | 4 | 53 | **Fair** | C-6, C-7 (missing features) |
| Audit | 4 | 24 | **Good** | Leakage scan scope (M-O3) |
| Pipeline/CLI | 2 | 11 | **Fair** | E2E coverage weak |

### Severity Distribution by Layer

```
Schemas:     CC..... MMMMMMMM mmmmmmmm nnnn
Compilers:   CCC.... MMMMMMM  mmmmm    nnn
Optimizer:   CC..... MMMMMMM  mmmmmmmm nnnn
Tests:       C...... MMMMMMMMMMMMMMMMM mmmmmmmmmmmmmmmmmmmmmmmmmmm nn
```

### Top 5 Risks for Paper Submission

1. **BEFORE constraint -> required_prior_actions gap (C-2)**: Any guideline with sequence constraints expressed via BEFORE (not explicit `required_prior`) will produce graphs without ordering enforcement. This affects the fidelity claim.

2. **GRADE recommendation_class crash (C-3)**: KDIGO, SSC, and other GRADE-based guidelines will produce invalid graphs. Since 15/25 CGA-Bench guidelines use GRADE, this blocks scaling beyond the AHA pilot.

3. **ALTERNATIVE coverage permanently zero (C-7)**: The coverage report claims 7 coverage types but one is always 0/0. Reviewers will notice the dead metric.

4. **Fixed patient template (M-C4)**: All SGSC scenarios have identical patient demographics (55M). This undermines the claim of "systematic scenario generation" since patient diversity is a key evaluation dimension.

5. **Weak E2E test assertions (M-T15)**: Coverage ratio `> 0` doesn't catch regressions. A change that drops coverage from 96% to 1% would still pass.

---

## Recommended Fix Priority

### Before paper submission (P0)
- C-1: Fix defaultdict misuse
- C-2: Wire BEFORE constraints into required_prior_actions
- C-3: Add recommendation_class normalization
- C-7: Either implement ALTERNATIVE extraction or remove from coverage types
- M-C4: Add patient template diversity (at minimum age/sex variation)

### Before production use (P1)
- C-4, C-5: Align constraint types with base.py enum
- C-6: Implement or remove k-coverage
- C-8: Fix trivially-true test assertion
- M-C2: Fix node merging to preserve required_prior_actions
- M-T14: Add ScenarioLoader integration test

### Technical debt (P2)
- All remaining Major findings
- Test coverage gaps (M-T1 through M-T17)
- Minor and Nit findings

---

## Appendix A: Review Methodology

Four parallel `oh-my-claudecode:code-reviewer` agents (Opus model) independently reviewed:

1. **Schema agent**: `sgsc/schemas/*.py` + `tests/test_sgsc/test_schemas.py`
2. **Compiler agent**: `sgsc/compilers/*.py` + corresponding tests
3. **Pipeline/optimizer/audit agent**: `sgsc/optimizer/*.py`, `sgsc/audit/*.py`, `sgsc/pipeline.py`, `sgsc/cli.py` + tests
4. **Test coverage agent**: All `tests/test_sgsc/*.py` files cross-referenced against implementation

Each agent used severity ratings:
- **Critical**: Logic bug or type-safety hole that causes silent wrong results
- **Major**: Missing feature, weak validation, or untested code path
- **Minor**: Improvement that reduces risk but doesn't affect correctness today
- **Nit**: Style, naming, or documentation issue

## Appendix B: File Inventory

| Directory | Files | Lines | Tests |
|-----------|-------|-------|-------|
| `sgsc/schemas/` | 7 | ~800 | 42 |
| `sgsc/extraction/` | 4 | ~500 | 12 |
| `sgsc/verification/` | 4 | ~400 | 18 |
| `sgsc/compilers/` | 6 | ~1,200 | 89 |
| `sgsc/optimizer/` | 4 | ~600 | 53 |
| `sgsc/audit/` | 4 | ~500 | 24 |
| `sgsc/pipeline.py` | 1 | ~350 | 8 |
| `sgsc/cli.py` | 1 | ~120 | 3 |
| `sgsc/VERSION` | 1 | 1 | - |
| `sgsc/__init__.py` | 1 | ~20 | - |
| **Total** | **33** | **~4,500** | **249** |

*Test files: 17 files in `tests/test_sgsc/`, ~2,043 lines.*
*Grand total: 49 files, ~6,543 lines.*
