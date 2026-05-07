# Session Handoff — Track alpha + Track beta (ActionNormalizer + SGSC Hardening)

<!-- Date: 2026-05-01 ~02:40 UTC -->
<!-- Branch: eval_science -->
<!-- Last commit: 6b3c1e5f (P-series close-out) -->
<!-- Changes NOT YET COMMITTED -->

---

## 1. Origin Spec Documents

| Document | Path | Role |
|----------|------|------|
| SGSC Engineering Spec | `docs/specs/source_grounded_scenario_compiler.md` | Original SGSC architecture spec (RecommendationAtom IR, compiler pipeline) |
| SGSC Critical Gap Analysis | `docs/attack_gap_exp_exp/260430_sgsc_critical_gap.md` | anonymous-user's critical review — 8 trust gates identified |
| Track beta Plan | `~/.claude/plans/swift-leaping-pixel.md` | beta-1 through beta-7 execution plan (entailment hardening + normalizer) |
| CDE Rescoring Gap | `docs/attack_gap_exp_exp/260430_CDE_rescoring_gap.md` | 9-item gap analysis (C1-C3, H1-H4, M1, L3) |
| CDE Gap-2 Plan | `docs/attack_gap_exp_exp/260430_CDE_rescore_gap_2.md` | P1-P7 engine hardening plan |
| Trust Gates Handoff | `docs/260430_session_handoff_trust_gates.md` | Previous session: trust gates Phase A-H |
| P0-P2 Eval Validity | `docs/sgsc/260430_exp_plan_Evaluation_validity.md` | P0-P2 evaluation validity experiment plan |
| SGSC Pilot-14 Report | `docs/sgsc/260430_sgsc_pilot14_analysis_report.md` | Pilot-14 batch run analysis |

---

## 2. What Was Completed This Session

### Track alpha (ActionNormalizer Fixes) — ALL 5 TASKS COMPLETE

| Task | Description | Key Files |
|------|-------------|-----------|
| alpha-1 | N1/N2 normalizer bug fixes (domain-specific mapping errors) | `assessor_core/action_normalizer.py` |
| alpha-2 | N3-N5 normalizer fixes (endocrinology_consult word-order, etc.) | `assessor_core/action_normalizer.py` |
| alpha-3 | B3 Forbidden Symmetric Normalization — 4 check sites patched | `cpg_engine/engine.py`, `cpg_engine/stepper.py`, `assessor_core/violations.py` |
| alpha-4 | Full Integration Sanity Gate — 1,089 tests pass | `tests/snapshots/*.json` (3 regenerated) |
| alpha-5 | CAV v0.5 build infrastructure + Phase 1 vocabulary harvesting | New scripts (not yet committed) |

**Key architectural decision (alpha-3)**: B3 uses a 2-layer boundary + defensive strategy:
- **Boundary layer**: `cpg_engine/engine.py` normalizes forbidden actions at aggregation points
- **Defensive layer**: `assessor_core/violations.py` adds a second normalization before COMMISSION checks
- **Runtime guard**: `cpg_engine/stepper.py` normalizes in lightweight forbidden-action check

### Track beta (SGSC Entailment Hardening) — 6 of 7 TASKS COMPLETE

| Task | Status | Description | Key Files |
|------|--------|-------------|-----------|
| beta-1 | DONE | Stemming in entailment checker | `sgsc/verification/entailment_checker.py` |
| beta-2 | DONE | Forward grounding_threshold from PipelineConfig | `sgsc/pipeline.py` |
| beta-3 | DONE | Raise default thresholds 0.5 -> 0.6 | `entailment_checker.py`, `pipeline.py` |
| beta-4 | DONE | Wire ActionNormalizer into SGSC pipeline (Step 2b) | `sgsc/pipeline.py` |
| beta-5 | DONE | Defensive normalization in graph + scenario compilers | `sgsc/compilers/graph_compiler.py`, `sgsc/compilers/scenario_compiler.py` |
| beta-6 | DONE | Cross-system integration verification | 1,097/1,097 tests pass |
| **beta-7** | **PENDING** | **Kickoff SGSC-3 25-guideline overnight run** | Needs endpoint config |

---

## 3. Test Status (as of session end)

```
Cross-system integration: 1,097/1,097 PASS
  - assessor_core + engine: 527 tests
  - sgsc: 570 tests
Ruff lint: 0 new issues (51 pre-existing)
```

Verification command:
```bash
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
PYTHONPATH=. pytest tests/test_assessor/ tests/test_engine/ tests/test_sgsc/ -v
ruff check sgsc/ assessor_core/ cpg_engine/
```

---

## 4. Uncommitted Files (22 files across Track alpha + Track beta)

### Track alpha files (assessor_core + cpg_engine + snapshots)
```
assessor_core/action_normalizer.py          # N1-N5 fixes + new direct mappings
assessor_core/violations.py                 # B3 defensive forbidden normalization
cpg_engine/engine.py                        # B3 boundary normalization + P1 graph validator
cpg_engine/stepper.py                       # B3 runtime forbidden-action guard
tests/test_assessor/test_action_normalizer.py  # N1-N5 regression tests
tests/test_assessor/test_violations.py      # B3 forbidden normalization tests
tests/test_engine/test_aha_chest_pain.py    # Updated for normalized forbidden forms
tests/snapshots/aha_chest_pain_evaluation.json  # Regenerated (normalized forbidden)
tests/snapshots/aha_stroke_2019.json        # Regenerated
tests/snapshots/kdigo_contrast_aki.json     # Regenerated
KNOWN_ISSUES.md                             # Sections 6-8, 6-9 (Phase 2 + gate behavior)
```

### Track beta files (sgsc pipeline + compilers + tests)
```
sgsc/verification/entailment_checker.py     # beta-1 stemming + beta-3 threshold 0.6
sgsc/pipeline.py                            # beta-2 threshold forwarding + beta-4 normalizer wire-in
sgsc/compilers/graph_compiler.py            # beta-5 defensive normalization
sgsc/compilers/scenario_compiler.py         # beta-5 defensive normalization
sgsc/extraction/atom_proposer.py            # beta-4 related changes
sgsc/schemas/atom.py                        # Docstring clarification (Phase A)
sgsc/cli.py                                 # Minor fix
tests/test_sgsc/test_entailment_checker.py  # beta-1 stemming tests (7 new)
tests/test_sgsc/test_pipeline_e2e.py        # beta-2/beta-4 tests (4 new)
tests/test_sgsc/test_graph_compiler.py      # beta-5 defensive normalization (3 new)
tests/test_sgsc/test_scenario_compiler.py   # beta-5 defensive normalization (2 new)
tests/test_sgsc/test_compiler_mutation_robustness.py  # Updated for canonical forms
tests/test_sgsc/test_atom_proposer.py       # Updated for normalizer
tests/test_sgsc/test_manifest.py            # Minor fix
```

---

## 5. What Needs to Be Done Next

### Immediate (before commit)

1. **Commit Track alpha + Track beta changes**
   - Suggest 2 separate commits (alpha first, then beta) to keep history clean
   - Track alpha: `feat(assessor+engine): alpha-1..5 ActionNormalizer N1-N5 + B3 forbidden symmetric normalization`
   - Track beta: `feat(sgsc): beta-1..6 entailment stemming + threshold 0.6 + normalizer wire-in + defensive normalization`

2. **beta-7: SGSC-3 25-guideline overnight run**
   - Precondition: beta-6 confirmed (DONE)
   - Endpoint needed: `http://localhost:8013/v1` (Gemma-4-31b-it) or another available endpoint
   - Command:
   ```bash
   cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
   PYTHONPATH=. python scripts/sgsc/run_full_25.py --dry-run  # pre-flight
   nohup PYTHONPATH=. python scripts/sgsc/run_full_25.py \
     --endpoint http://localhost:8013/v1 \
     --skip-existing \
     > reports/sgsc_3_overnight.log 2>&1 &
   echo $! > reports/sgsc_3_pid.txt
   ```

### Short-term

3. **P3 Evaluation Validity** (per spec `docs/sgsc/260430_exp_plan_Evaluation_validity.md`)
   - FHIR/CQL crosswalk
   - Cross-benchmark positioning
   - P0 (committed `adad0dea`), P1 (committed `1dd4f78e`), P2 (committed `44c4232a`) all done

4. **NeurIPS deadline pressure**
   - May 4: Abstract submission
   - May 6: Full paper submission
   - DOI still NOT acquired (Zenodo)
   - LICENSE file untracked

---

## 6. Key Pitfalls Discovered This Session

| Pitfall | Details |
|---------|---------|
| Frozen Pydantic mutation | `AtomAction`/`AtomSequence` are `frozen=True`. Use `atom.action = atom.action.model_copy(update={"canonical_id": normalized})` — direct assignment fails silently |
| Defensive normalization breaks assertions | Existing tests asserting raw action IDs (e.g., `"give_nitroglycerin"`) fail after normalization maps to canonical form (`"give_nitrates_if_indicated"`). Fix: use `try/except ImportError` pattern to resolve canonical forms dynamically |
| ruff RUF003 Greek characters | `alpha` in comments triggers RUF003 if using actual Greek letter. Use ASCII "alpha" or "Track-alpha" |
| ruff B905 zip strict | `zip(a, b)` without `strict=` triggers B905. Always use `strict=True` |
| B3 check sites count | Originally scoped as 2 forbidden-check sites; actual audit found 4 distinct sites needing normalization |
| Snapshot regeneration | B3 normalization changes forbidden action forms in CPG engine output, requiring snapshot JSON regeneration for 3 graphs |

---

## 7. Architecture Reference: 2-Layer Normalization

```
                    SGSC Pipeline
                    ============
  LLM Atom Proposal
         |
    [beta-4: _normalize_atom_actions()]     <-- PRIMARY: pipeline Step 2b
         |
    Entailment Check (beta-1 stemming, beta-3 threshold 0.6)
         |
    Graph Compiler
         |
    [beta-5: _defensive_normalize_graph()]  <-- DEFENSIVE: compiler boundary
         |
    Scenario Compiler
         |
    [beta-5: defensive normalize block]     <-- DEFENSIVE: compiler boundary
         |
    Output YAML (canonical action IDs guaranteed)


                    Scoring Pipeline
                    ================
  CPG Engine evaluate()
         |
    [alpha-3: normalize at aggregation]     <-- BOUNDARY: engine.py
         |
    CPG Stepper check_forbidden()
         |
    [alpha-3: normalize at runtime]         <-- RUNTIME: stepper.py
         |
    ViolationExtractor
         |
    [alpha-3: defensive normalize]          <-- DEFENSIVE: violations.py
         |
    Score (symmetric forbidden matching guaranteed)
```

---

## 8. Memory / Context Files

| File | Path | Purpose |
|------|------|---------|
| Project Memory | `~/.claude/projects/-home-anonymous-org-AnonProject-anonymous-user-AnonProject/memory/MEMORY.md` | Persistent cross-session memory (updated this session) |
| Plan File | `~/.claude/plans/swift-leaping-pixel.md` | Track beta execution plan (beta-1 through beta-7) |
| CLAUDE.md | `cga_bench/CLAUDE.md` | Project instructions for Claude Code |
| KNOWN_ISSUES.md | `cga_bench/KNOWN_ISSUES.md` | Known issues and recurring patterns |

---

## 9. Quick Resume Checklist

```bash
# 1. Verify tests still pass
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
PYTHONPATH=. pytest tests/test_assessor/ tests/test_engine/ tests/test_sgsc/ -v

# 2. Check uncommitted changes
git diff --stat HEAD

# 3. Read the plan
cat ~/.claude/plans/swift-leaping-pixel.md

# 4. Commit if ready
# (see Section 5 for suggested commit messages)

# 5. Proceed to beta-7 (SGSC-3 overnight run)
# (see Section 5 for kickoff command)
```
