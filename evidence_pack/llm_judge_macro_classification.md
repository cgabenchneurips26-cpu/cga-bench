# LLM-Judge Macro Classification: Author-Dependent vs Author-Independent

Generated: 2026-04-26

## Classification Criteria

**AUTHOR-INDEPENDENT**: Evaluation pipeline uses ONLY patient context + agent actions. Does NOT access expected_actions, forbidden_actions, or sequence_constraints from CPG configs.

**AUTHOR-DEPENDENT**: Evaluation pipeline injects CPG rubric data (expected_actions, forbidden_actions, sequence_constraints) into prompts.

---

## Summary Table

| Macro Name | Value | Generator Script | Pipeline | Author-Dependent |
|------------|-------|-----------------|----------|------------------|
| **EX-1: Terminal Judge (T0-T3 levels)** |||||
| `\termJudgeTzeroFA` | 1.9 | `run_ex1_llm_judge.py` | T0 (context only) | **NO** |
| `\termJudgeToneFA` | 25.5 | `run_ex1_llm_judge.py` | T1 (context + last 5 actions) | **NO** |
| `\termJudgeTtwoFA` | 30.7 | `run_ex1_llm_judge.py` | T2 (context + full action list, no timestamps) | **NO** |
| `\termJudgeTthreeFA` | 18.5 | `run_ex1_llm_judge.py` | T3 (context + full trace with timestamps) | **NO** |
| `\termJudgeTtwoTthreeGap` | 12.2 | `run_ex1_llm_judge.py` | Derived (T2 - T3) | **NO** |
| `\termJudgeTtwoBSRcond` | 46.3 | `run_ex1_llm_judge.py` | Conditional BSR at T2 | **NO** |
| `\termJudgeTthreeBSRcond` | 28.4 | `run_ex1_llm_judge.py` | Conditional BSR at T3 | **NO** |
| **EX-1: Cross-Validation (Gemma)** |||||
| `\gemmaJudgeTzeroFA` | 32.1 | `run_ex1_llm_judge.py` | T0 cross-validation | **NO** |
| `\gemmaJudgeToneFA` | 34.7 | `run_ex1_llm_judge.py` | T1 cross-validation | **NO** |
| `\gemmaJudgeTtwoFA` | 42.3 | `run_ex1_llm_judge.py` | T2 cross-validation | **NO** |
| `\gemmaJudgeTthreeFA` | 25.9 | `run_ex1_llm_judge.py` | T3 cross-validation | **NO** |
| `\gemmaJudgeTtwoTthreeGap` | 16.4 | `run_ex1_llm_judge.py` | Derived (T2 - T3) | **NO** |
| **EX-1: Default-PASS Prompt** |||||
| `\defaultPassTzeroFA` | 4.2 | `run_ex1_llm_judge.py` | P2 prompt at T0 | **NO** |
| **EX-1: Metadata** |||||
| `\promptJudgeVariants` | 4 | `run_ex1_llm_judge.py` | Count of P1-P4 prompts | **NO** |
| **Y-series: LLM Constraint Catalogues** |||||
| `\llmCatalogueQwen` | 1268 | *HARDCODED* (from `llm_summary.json`) | Qwen catalogue extraction | **NO** |
| `\llmCatalogueGptOss` | 1286 | *HARDCODED* (from `llm_summary_v2.json`) | GPT-OSS catalogue extraction | **NO** |
| `\cdeCatalogueSize` | 1049 | *HARDCODED* (from `engine_audit.json`) | CDE reference count | **N/A** |

---

## Pipeline Details

### EX-1: Terminal Judge (AUTHOR-INDEPENDENT)

**Script**: `scripts/experiments/run_ex1_llm_judge.py`

**Key Function**: `extract_artifact(ep, level)` — Lines 98-130

**Evidence of Independence**:
```python
# T0: Patient context only (what a terminal-output evaluator sees)
# T1: Context + management plan summary (last 5 actions)
# T2: Context + full action list (no timestamps)
# T3: Context + full action trace WITH timestamps (what TCC sees, minus constraints)
```

**What's excluded**: Expected actions, forbidden actions, sequence constraints from CPG configs.

**Prompts Used**: `P1` (strict PASS/FAIL), `P2` (attending YES/NO), `P3` (1-5 scale) — stored in `PROMPTS` dict at line 28-32. All prompts are generic clinical judgment, NOT rubric-aware.

**Output**: `evidence_pack/ex1_llm_judge/ex1_results.json` → `ex1_macros.tex`

**3-Judge Variant**: `evidence_pack/ex1_llm_judge_3judge/ex1_3judge_macros.tex` (Qwen/Gemma/Nemotron cross-validation, same T0-T3 structure)

---

### EXP-2: LLM Judge with Rubric (AUTHOR-DEPENDENT — NOT IN MACRO LIST)

**Script**: `scripts/experiments/exp_2_llm_judge.py`

**Key Evidence**: Line 294-296
```python
"forbidden_actions": sc.get("forbidden_actions", []),
"expected_actions": sc.get("expected_actions", []),
"sequence_constraints": sc.get("sequence_constraints", []),
```

**Prompts**:
- `rubric_free.jinja2` — AUTHOR-INDEPENDENT (pure clinical judgment)
- `rubric_aware.jinja2` — AUTHOR-DEPENDENT (injects forbidden/expected/sequence from CPG)
- `cot_judge.jinja2` — AUTHOR-DEPENDENT (chain-of-thought per constraint)

**Output**: `evidence_pack/exp_2_llm_judge.json` — NO macros extracted to `auto_numbers.tex`

**Status**: This experiment exists but its results are NOT represented in the current paper macro set.

---

### Y-Series: Catalogue Extraction (AUTHOR-INDEPENDENT)

**Purpose**: LLM extracts constraints from CPG text documents (RAG corpus), NOT from scenario configs with expected_actions.

**Y.1 Script**: `scripts/experiments/exp_cde_vs_llm.py`
- Calls Qwen3.5-397B on 25 parsed CPG documents
- Asks LLM to enumerate MUST/FORBIDDEN/WITHIN/BEFORE constraints
- Outputs: `evidence_pack/constraint_comparison/llm_raw/<CPG>.json`
- Summary: `llm_summary.json` → 1268 total constraints

**Y.1v2 Script**: `scripts/experiments/exp_cde_vs_llm_v2.py`
- Same process with GPT-OSS-120B
- Outputs: `llm_summary_v2.json` → 1286 total constraints (after filtering 11 non-canonical "REQUIRED" entries)

**Key Distinction**: These scripts parse guideline DOCUMENTS, not scenario CONFIGS. The LLM never sees expected_actions fields from YAML scenario definitions.

**Macro Location**: `paper/auto_numbers.tex` lines 913-914 (HARDCODED, not auto-generated)

**Note from auto_numbers.tex**:
```tex
% NOTE: gpt-oss v2 total updated 2026-04-24 after filtering 11 non-canonical
% "REQUIRED" entries (AHA-ACLS 5 + GINA-Asthma 6; commit bd6b7132). Post-filter
% 4-type canonical sum = total = 1286; arithmetic exact match.
```

---

## Decision Logic Summary

### Author-Independent Macros (ALL EX-1 + Y-series catalogues)

These macros derive from evaluations that:
1. Use ONLY patient presentation + agent action traces
2. Never access scenario.expected_actions or scenario.forbidden_actions
3. Extract constraints from guideline TEXT (not scenario configs)
4. Evaluate based on generic clinical judgment or document parsing

**Total count**: 16 macros (14 EX-1 + 2 catalogue totals)

### Author-Dependent Macros (NONE in current set)

EXP-2 (rubric_aware/cot_judge) does inject CPG rubric data, but its results are NOT exported to `auto_numbers.tex` in the current paper version.

---

## Verification Commands

```bash
# Confirm run_ex1_llm_judge does NOT use rubric
grep "expected_actions\|forbidden_actions\|sequence_constraints" scripts/experiments/run_ex1_llm_judge.py
# (returns empty)

# Confirm exp_2_llm_judge DOES use rubric
grep "expected_actions\|forbidden_actions\|sequence_constraints" scripts/experiments/exp_2_llm_judge.py
# (returns 3 matches at lines 294-296)

# Confirm catalogue extraction uses documents, not configs
grep "RAG_CORPUS\|parsed.json" scripts/experiments/exp_cde_vs_llm.py
# (confirms it reads from data_release/v5.0/rag_corpus/*.parsed.json)
```

---

## Paper Implications

**Claim**: All LLM-judge macros in the current paper (auto_numbers.tex) are AUTHOR-INDEPENDENT.

**Evidence**:
1. EX-1 pipeline uses T0-T3 artifact ladder with NO rubric injection
2. Y-series catalogues extract from guideline documents, NOT scenario configs
3. EXP-2 rubric-aware results exist but are NOT included in paper macros

**Robustness**: The paper's terminal-judge baseline (EX-1) is NOT contaminated by author knowledge of expected actions. This strengthens the claim that even capable LLMs examining full traces (T3) miss violations without deterministic CPG engines.

---

## HARDCODED Macro Note

`\llmCatalogueQwen` and `\llmCatalogueGptOss` are MANUALLY copied from JSON summaries into `auto_numbers.tex`. They are NOT auto-generated by `extract_auto_numbers.py`.

**Generator scripts exist** (`exp_cde_vs_llm.py`, `exp_cde_vs_llm_v2.py`) but they output to:
- `evidence_pack/constraint_comparison/llm_summary.json` (1268)
- `evidence_pack/constraint_comparison/llm_summary_v2.json` (1286)

These values are then MANUALLY transcribed to `auto_numbers.tex` lines 913-914.

---

## Files Referenced

- `scripts/experiments/run_ex1_llm_judge.py` (288 lines)
- `scripts/experiments/exp_2_llm_judge.py` (24,248 bytes)
- `scripts/experiments/exp_cde_vs_llm.py` (10,328 bytes)
- `scripts/experiments/exp_cde_vs_llm_v2.py` (6,194 bytes)
- `configs/llm_judge_prompts/rubric_free.jinja2` (20 lines)
- `configs/llm_judge_prompts/rubric_aware.jinja2` (30 lines)
- `configs/llm_judge_prompts/cot_judge.jinja2` (42 lines)
- `evidence_pack/ex1_llm_judge/ex1_results.json`
- `evidence_pack/ex1_llm_judge/ex1_macros.tex`
- `evidence_pack/ex1_llm_judge_3judge/ex1_3judge_macros.tex`
- `evidence_pack/constraint_comparison/llm_summary.json`
- `evidence_pack/constraint_comparison/llm_summary_v2.json`
- `evidence_pack/constraint_comparison/compare_summary.json`
- `paper/auto_numbers.tex` (lines 438-476, 913-914)
