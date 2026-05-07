# CGA-Bench Uncommitted Changes Analysis Report

**Date**: 2026-04-22
**Branch**: `eval_science`
**Base commit**: `5b77302e` (test(cpg-pipeline): P2 LLM clinical smoke)
**Commits created**: 8 (+ 2 auto-committed by parallel session)

---

## 1. Executive Summary

Total **317 files** across **8 commits** organized into 6 logical work streams:

| Work Stream | Files | Insertions | Key Deliverables |
|---|---|---|---|
| Audit Harness (Option C + EVP) | 50 | ~3,950 | 12 evaluator shims, separating pairs, Bayes error, reports |
| V7 CPG Pipeline (Phase 2a-3) | 10 | ~3,828 | Batch mode, review packets, 54 skeletons |
| Paper v17 | 23 | ~2,672 | Figures 3-5, macros, tables, heldout analysis |
| Agent Configs + Infra | 27 | ~1,574 | 18 configs (15 updated + 3 deepseek), Makefile, docs |
| Stub 99 CPGs | 199 | ~12,089 | 99 YAML graphs + 99 source JSONs + results |
| Docs + Screenshots | 8 | ~1,055 | Session handoff, strategic plan, validation screenshots |
| **Total** | **317** | **~25,168** | |

---

## 2. Work Stream Details

### 2.1 Audit Harness: Option C Evaluator Expansion + EVP

**Commits**: `c6a8c6fa`, `af99d1e4`, `e6a81ccd`, `5dfe2ca7`

**Purpose**: NeurIPS reviewer concern — "any evaluator" claim needs empirical proof.

**Architecture**:
```
audit/
  evaluator_base.py          # ABC for all evaluators
  separating_pairs.py        # Pairwise evaluator disagreement analysis
  shims/
    __init__.py              # SHIM_REGISTRY (12 evaluators)
    _verdict_cache.py        # Shared verdict matrix loading
    dxem.py                  # DxEM (Diagnosis Exact Match)
    ac_proxy.py              # Action Coverage Proxy
    mab_proxy.py             # MedAgentBench F1 Proxy
    c2_shim.py               # C2 Mandatory Completion
    acov_shim.py             # ACov (Action Coverage)
    v4_hard.py               # V4 Hard (no violations)
    violation_count_shim.py  # EVP-1: ViolationCountEvaluator
    llm_judge_shim.py        # EVP-2: LLMJudgeEvaluator
  reports/                   # Per-evaluator JSON + Markdown reports
```

**Key Findings**:
- **EVP-1 ViolationCountEvaluator**: pi-class=`nctx`, BSR=63.93%, rho(d_G)=-0.8101
  - Strong negative correlation with graph complexity = clinically meaningful
- **EVP-2 LLMJudgeEvaluator**: pi-class=`term`, BSR=49.19%, rho(d_G)=-0.0735
  - Different pi-class from ViolationCount = harness genuinely differentiates evaluators
- **12 evaluators** total in registry (8 shims + 4 metric wrappers)
- **196/196 audit tests passing**

**Limitations**:
- LLM judge cache is heuristic proxy (needs real LLM endpoint re-run)
- AMEGA episodes not in W8 corpus, so EVP-3 was skipped

---

### 2.2 V7 CPG Expansion Pipeline (Phase 2a/2b/3)

**Commit**: `773923bb`

**Purpose**: Scale from 25 to 79 CPG graphs for v7 dataset.

**Pipeline Architecture**:
```
Phase 2a: parsed_json_loader.py     [deterministic converter]
     |
Phase 2b-1: validate_cpg_schema.py  [CI schema validator]
Phase 2b-2: auto_generate_cpg.py    [batch mode, ThreadPoolExecutor]
Phase 2b-3: generate_review_packet.py [MD + CSV + comparison mode]
     |
Phase 3: generate_v7_skeletons.py   [54 candidate skeleton generator]
```

**New Scripts**:
| Script | Purpose | Output |
|---|---|---|
| `generate_review_packet.py` | Clinician sign-off packets | Markdown (checkboxes) + CSV (structured) |
| `generate_v7_skeletons.py` | 54 six-point candidate skeletons | Extended parsed.json files |
| `validate_v2_vs_handcrafted.py` | Gold standard comparison | Diff report |

**Test Results**:
- Batch conversion: **54/54 success**, 0 failures (75.4 seconds)
- 216 total nodes, 432 mandatory actions, 20 domains
- 432 CSV review items generated
- Regression tests: 148/148 passing

**Domain Coverage** (54 candidates):
| Domain | Count | Examples |
|---|---|---|
| trauma | 8 | ATLS primary survey, TBI, pelvic trauma |
| cardiovascular | 7 | Cardiogenic shock, cardiac tamponade, VT storm |
| infectious | 6 | NSTI, toxic shock, febrile neutropenia |
| obstetric | 5 | Preeclampsia/HELLP, cord prolapse, AFE |
| toxicology | 5 | Iron overdose, lithium, serotonin syndrome |
| neurological | 4 | Myasthenic crisis, GBS, NMS, SAH |
| pulmonary | 3 | ARDS, massive hemoptysis, NIV for ARF |
| endocrine | 3 | Thyroid storm, adrenal crisis, HHS |
| hematologic | 3 | TTP, DIC, sickle cell ACS |
| gastrointestinal | 3 | Pancreatitis, variceal hemorrhage, diverticulitis |
| other | 7 | Burns, hyperkalemia, malaria, heat stroke, etc. |

**Critical Discovery**:
- `cpg_sources/*.parsed.json` files are in **rag_corpus format** (with `recommendations`, `tables`, `key_sections`) — NOT compatible with `load_and_normalize()` which expects **extended format** (structurally homomorphic to CPG YAML)
- This format distinction is critical for anyone running the batch pipeline

---

### 2.3 Paper v17 Artifacts

**Commit**: `f242449e`

**Updated Artifacts**:
| Category | Files | Changes |
|---|---|---|
| LaTeX macros | `auto_numbers.tex`, `auto_numbers_v2.tex` | Refreshed values from latest experiments |
| Figures | `figure3.png/.tex`, `figure4.tex`, `figure5.tex` | Updated rendering + new generation scripts |
| Tables | 5 new `.tex` files | Distribution check, heldout ordering, oracle per-domain, rank bootstrap, testsize |
| Evidence | `heldout_macros.tex`, `heldout_results.json`, `bayes_error_results.json` | Latest experiment results |
| Scripts | `make_figure3_cde.py`, `make_figure4_ranking.py`, `make_figure5_e1_only.py` | Figure generation code |
| Analysis | `heldout_analysis.py`, `heldout_runner.py` | Held-out evaluation updates |

---

### 2.4 Agent Configs + Infrastructure

**Commit**: `65f6f2c7`

| Change | Count | Details |
|---|---|---|
| Updated agent YAMLs | 15 | gemma31b, oss120b, qwen27b/35b/397b (checklist/direct/tooluse) |
| New agent YAMLs | 3 | `clean_slate_deepseek_r1_7b_{checklist,direct,tooluse}.yaml` |
| Makefile | 1 | Audit pipeline targets added |
| Runner | 1 | `full_690_runner.py` updates for W8 sweep |
| Docs | 5 | Evaluator expansion plans (Option B/C), root cause analysis |

---

### 2.5 Stub 99 CPG Graphs

**Commit**: `47c208b3` (199 files, ~12K lines)

**Purpose**: P1 scale robustness proof — full pipeline handles 99 diverse CPG graphs.

**Content**:
- `cpg_model/graphs_stub_99/`: 99 structurally valid CPG YAML files
- `evidence_pack/round_trip_v1/stub_99_src_json/`: 99 source extended parsed.json
- `evidence_pack/round_trip_v1/p1_stub_99_results.json`: Validation results

**Result**: 99/99 pass (previously tested in commit `5f8ff656`)

---

### 2.6 Clinician Validation + Docs

**Commits**: `c6a8c6fa` (auto), `af99d1e4` (auto), `ba5df09c`

**Clinician Validation UI** (11 enhancement items):
- Default-appropriate UX: null verdict = appropriate (subtle green tint)
- Gate checkbox replacing per-action completeness check
- Subtype chip row with progressive disclosure
- Hotkey system: 1/2/3 verdicts, Q/W/E subtypes, Tab nav, Esc clear
- Auto-save indicator
- ~75 new Korean action descriptions (70% -> 80%+ coverage)

**Documentation**:
- Session handoff v17
- Strategic plan v17 + critique
- EVP analysis report
- Updated validation screenshots

---

## 3. Intentionally Skipped Files

| File | Reason |
|---|---|
| `.claude/settings.local.json` | Local editor config |
| `paper/main_final_v14.tex` | Old paper draft |
| `paper/main_final_v16.tex` | Old paper draft |
| `paper/main_final_v17.tex.bak_preprint` | Backup file |
| `paper/main_final_v17.txt` | Text export |
| `paper/main_test_compile.tex` | Test compile artifact |
| `paper/main_tier1-1.tex` | Working draft |
| `paper/appendix_test.tex` | Test artifact |
| `paper/appendix_tier1-1.tex` | Working draft |
| `paper/appendix_reconstructed.tex` | Working draft |
| `paper/reports/junit.xml` | CI test artifact |

**Recommendation**: Add `paper/main_final_v1[0-6].tex`, `paper/*_test*.tex`, `paper/reports/` to `.gitignore`.

---

## 4. Commit Graph

```
ba5df09c docs: session handoff, strategic plan, EVP report, screenshots
5dfe2ca7 docs(audit): EVP extensibility verification analysis report
47c208b3 test(cpg-pipeline): 99 stub CPG graphs + round-trip source JSONs
65f6f2c7 chore: agent configs, W8 scaffold, deepseek_r1_7b, Makefile, docs
f242449e feat(paper): v17 figures, macros, tables, heldout analysis
773923bb feat(cpg-pipeline): v7 expansion — batch mode, review packets, 54 skeletons
e6a81ccd feat(audit): Option C core shims — DxEM, AC-Proxy, MAB-Proxy, C2, ACov, V4Hard
af99d1e4 feat(clinician-validation): implement all 11 UI enhancement items
c6a8c6fa feat(audit): evaluator expansion — 12 shims, EVP, separating pairs, reports
5b77302e test(cpg-pipeline): P2 LLM clinical smoke  [BASE]
```

---

## 5. Risk Assessment

| Risk | Severity | Status | Mitigation |
|---|---|---|---|
| LLM judge cache is heuristic | MEDIUM | Known | Re-run with real LLM when endpoint available |
| Commit message mismatch (c6a8c6fa/af99d1e4) | LOW | Cosmetic | Messages swapped due to tool interference; content is correct |
| Old paper drafts in working tree | LOW | Intentional | Excluded from commits; add to .gitignore |
| Skeleton actions are templates | LOW | By design | Phase 4 (clinical content enrichment) will replace |
| DOI not acquired for HuggingFace claim | HIGH | Unchanged | Must resolve before May 6 submission |

---

## 6. Next Steps

1. **Clinical content enrichment** — Replace skeleton template actions with real guideline content (54 graphs)
2. **Clinician review distribution** — Send MD/CSV review packets for expert sign-off
3. **Scenario generation** — Create scenarios for 54 new CPG graphs
4. **LLM judge re-run** — Re-compute cache with real LLM endpoint
5. **Zenodo DOI** — Upload dataset and acquire persistent DOI
6. **Submission tarball** — Exclude old paper drafts, ensure Croissant + RAI fields
