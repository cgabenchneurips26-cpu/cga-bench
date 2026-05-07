# Phase 0.C — Offensive Evaluator Audit + D5 Reconciliation

**Date**: 2026-04-26 04:30 UTC
**Scope**: D5 (25.1% reconciliation) + VII (remaining 5 evaluator audits) + macro classification fixes

---

## 1. D5 — faAllOblivious 25.1% vs 11.6% Reconciliation

### Root Cause: DIFFERENT CORPUS (9,982 vs 14,826)

| Source | File | Corpus | Episodes | faAllOblivious |
|--------|------|--------|----------|----------------|
| `auto_numbers.tex:27` | `extract_auto_numbers.py` | v5 canonical | 14,826 (W8) | **11.6%** (1,959) |
| `exact_auto_numbers_update.tex:25` | `compute_exact_evaluator_verdicts.py` | `results/full_706_final` | **9,982** | **25.1%** (2,506) |

**Key evidence**:
- `exact_auto_numbers_update.tex` line 3: "Based on 9982 episodes"
- `compute_exact_evaluator_verdicts.py` line 22: `--episodes-dir results/full_706_final`
- 9,982 is neither v5 (14,826) nor v6 (16,944) — it's an **older partial run**

**Critical coincidence**: In the 9,982 corpus, `faAllOblivious == bsrCTwo == 25.1%` (count=2,506). This means CwT is the bottleneck — TOM (100%) and ASC (79.7%) are redundant filters. This is a valid structural insight but from a stale corpus.

### Verdict

**25.1% is NOT from typed CwT. It is from a stale, smaller corpus.**

The canonical headline number remains **11.6%** (from `auto_numbers.tex`). The `exact_auto_numbers_update.tex` file should NOT be `\input`ed into the paper — it would override correct macros with stale values.

### Action Required
- [ ] Add guard comment to `exact_auto_numbers_update.tex`: "STALE — based on 9,982 episodes from deprecated `results/full_706_final`. Do NOT \input."
- [ ] Verify `results/full_706_final` still exists and document its provenance
- [ ] Consider deleting or archiving `exact_auto_numbers_update.tex`

---

## 2. Remaining 5 Evaluator Audits

### 2.1 MAB Replay Scorer (`\mimicMABDetectionLoss{63.2}`)

| Item | Finding |
|------|---------|
| **Macro** | `\mimicMABDetectionLoss{63.2}` |
| **Generator** | `scripts/experiments/exp_e23_artifact_mimic_ablation.py` |
| **Output** | `evidence_pack/ex23_artifact_ablation/macros.tex` |
| **Corpus** | v5 (14,826) — `RESULTS_DIR = ROOT / "results" / "full_706_v5"` |
| **Definition** | MAB-Artifact mode: F1-only scoring, no timestamps, no ordering. Detection loss = % of TCC-detectable hard violations that MAB misses |
| **Audit status** | **SCRIPT EXISTS, well-documented**. Uses 8 model labels including deepseek_r1_7b. Verdict definition is clear: F1 coverage without temporal constraints. |
| **Macro audit CSV bug** | None — correctly classified as Category B |

**Verdict**: Fully auditable. Script + output exist. Definition clear. **CLOSE.**

### 2.2 AC Replay Scorer (`\mimicACDetectionLoss{84.2}`)

| Item | Finding |
|------|---------|
| **Macro** | `\mimicACDetectionLoss{84.2}` |
| **Generator** | Same `exp_e23_artifact_mimic_ablation.py` |
| **Definition** | AC-Artifact mode: coverage-only scoring, no timestamps/ordering/forbidden check. Detection loss = % of TCC-detectable violations that AC misses |
| **Macro audit CSV BUG** | **`auto_numbers_audit.csv` line 293 classifies it as Category A** ("system/structural constant"). This is WRONG — it's verdict-dependent (Category B). |

**Root cause of misclassification**: The keyword `mimic` contains no B_KEYWORDS match in `generate_macro_audit.py`, and the A_KEYWORDS set includes `mimicprotocol`. The substring `mimic` in `mimicACDetectionLoss` matches the A keyword `mimicprotocol` via the loose `kw in lower` check.

**Fix required**: Add `mimicACDetectionLoss` and `mimicMABDetectionLoss` to `CATEGORY_OVERRIDES` as Category B.

**Verdict**: Definition clear, script exists. Misclassification bug found. **CLOSE after CSV fix.**

### 2.3 OracleAgent Score Formula (`\oracleMeanGap{+11.4}`)

| Item | Finding |
|------|---------|
| **Macros** | `\oracleMeanGap{+11.4}`, `\oracleMinGap{-16.1}`, `\oracleMaxGap{+38.9}` |
| **Generator** | `scripts/experiments/compute_oracle_per_domain.py` — **REFERENCED BUT NOT ON DISK** (per PAPER_TRACEABILITY.md line 288) |
| **JSON source** | `evidence_pack/analysis/oracle_per_domain.json` |
| **Error decomposition** | `evidence_pack/analysis/oracle_error_decomposition.json` — exists, 476 lines |
| **Definition** | Mean Oracle-RAG gap across 8 scenarios in pct-pts. Oracle uses `agent_rules/` decision tables (never cpg_engine). RAG baseline uses BM25/dense retrieval. |

**Critical issue**: **No generator script on disk**. The value +11.4 is hardcoded in `auto_numbers.tex:648`. Cannot be regenerated. The error decomposition JSON exists but doesn't contain the aggregate gap number.

**Fix required**: Either (a) reconstruct `compute_oracle_per_domain.py` from the JSON data, or (b) document in spec that this is a locked Category A constant (since Oracle uses fixed rules, not verdicts).

**Verdict**: **OPEN — missing generator script. P1 priority.**

### 2.4 Pose B Catalogue x Evaluator Protocol

| Item | Finding |
|------|---------|
| **Shim** | `audit/shims/llm_catalogue_shim.py` (LLMCatalogueShim) |
| **Data** | `evidence_pack/constraint_comparison/llm_raw/<CPG>.json` — LLM-extracted constraints |
| **Definition** | PASS iff every MUST is fuzzy-matched by some performed action AND no FORBIDDEN is fuzzy-matched. WITHIN/BEFORE skipped (timestamp incompatibility). |
| **Paper section** | §4.3 "Catalogue-Conditional Audit" (main_final_v17.tex:340-373) |
| **Macros** | `\llmCatalogueQwen{1268}`, `\llmCatalogueGptOss{1286}`, `\cdeCatalogueSize{1049}` + per-type breakdowns |
| **Three pillars** | (1) catalogue-conditional verdicts, (2) per-type ratios, (3) dual-family consensus-FA |

**Key structural limitation**: Shim evaluates only MUST+FORBIDDEN (set-level). WITHIN/BEFORE are explicitly skipped because "timestamps in trajectory are on the CGA clock, not reconciled with LLM-expressed deadlines" (line 11). This means Pose B cannot detect timing/sequence violations — only commission and omission.

**Audit question answered**: The LLM catalogue uses the SAME `LLMCatalogueShim` code regardless of which LLM family (Qwen vs gpt-oss). The difference is which JSON file is loaded, not the evaluator code.

**Verdict**: Well-implemented and documented. Limitation (no WITHIN/BEFORE) is explicitly disclosed. **CLOSE.**

### 2.5 X1/X2 Ablation Verdict Definitions

| Experiment | Script | Macros | Status |
|------------|--------|--------|--------|
| X1 (context-swap) | `exp_x1_context_swap.py` | `ex_x1_context_swap_macros.tex` | **Complete** |
| X2 (violation-event ablation) | `exp_x2_causal_intervention.py` | `ex_x2_macros.tex` (in evidence_pack) | **Complete** |

**X1 verdict definition** (context-swap):
- For each (donor, recipient, pivot_action) triplet, evaluate SAME trajectory under BOTH contexts
- `tcc_flip = (donor.v4_hard != recipient.v4_hard)` — score_episode_against() re-evaluates
- `morph_flip = (clf.predict(E_donor) != clf.predict(E_recipient))` — 0 by construction (features context-blind)
- Result: TCC flip 97.3%, morph flip 0.0%, McNemar stat 1399 (p << 0.001)
- N=1,438 episodes from 98 usable pairs out of 200 discovered triplets

**X2 verdict definition** (violation-event ablation):
- For each hard-violation episode, remove the triggering action + violation_event record
- `tcc_flip = (score_episode(E').v4_hard != E.v4_hard)` — mechanical by construction for single-hard
- `morph_flip = (clf.predict(E') != clf.predict(E))` — non-mechanical
- Result: TCC-morph gap +0.828 on single_hard, +0.416 overall
- Script documents that TCC flip on single-hard is "mechanical" — the substantive result is the GAP

**Verdict**: Both scripts exist, well-documented, output macros exist. Verdict definitions are explicit in docstrings. **CLOSE.**

---

## 3. Macro Audit CSV Classification Fix

### Bug: `\mimicACDetectionLoss` classified as Category A

**File**: `scripts/audit/generate_macro_audit.py`

**Root cause**: `A_KEYWORDS` contains `mimicprotocol`. The check `kw in lower` matches `mimic` as a substring of `mimicacdetectionloss`, routing it to Category A before it reaches B_KEYWORDS (which contains `loss`, `detection`).

**Fix**: Add to `CATEGORY_OVERRIDES`:
```python
r"\mimicACDetectionLoss": "B",
r"\mimicMABDetectionLoss": "B",
r"\mimicHBDetectionLoss": "B",
```

---

## 4. Summary Status

| # | Evaluator Area | Status | Action |
|---|---------------|--------|--------|
| 2.1 | MAB replay (`\mimicMABDetectionLoss`) | **CLOSED** | Script + output verified |
| 2.2 | AC replay (`\mimicACDetectionLoss`) | **CLOSED** (after CSV fix) | Fix macro audit classification |
| 2.3 | OracleAgent (`\oracleMeanGap`) | **OPEN** | Missing generator script — P1 |
| 2.4 | Pose B catalogue | **CLOSED** | Shim + limitations documented |
| 2.5 | X1/X2 ablation | **CLOSED** | Both scripts + macros verified |
| D5 | 25.1% reconciliation | **RESOLVED** | Stale corpus (9,982 ep), not typed CwT |

### Remaining open items after this audit:
1. **P0 #4**: eta-squared computation path lock (0.078 vs 0.284)
2. **P1**: OracleAgent generator script missing — reconstruct or lock as constant
3. **P1**: `exact_auto_numbers_update.tex` guard comment
4. **P1**: Macro audit CSV fix (mimicACDetectionLoss → Category B)

---

## 5. "Every Evaluator Audited" Paper Claim Assessment

After closing 4/5 items above:

| Evaluator / Scorer | Verdict Definition | Script | Output | Status |
|--------------------|-------------------|--------|--------|--------|
| TCC (v4_hard) | `verdict_definitions.py` | N/A (reference) | N/A | Spec'd |
| CwT (C2) | `verdict_definitions.py` | `_episode_cache.py` | verdict_matrix | Spec'd |
| ASC (AC-Proxy) | `verdict_definitions.py` | `_episode_cache.py` | verdict_matrix | Spec'd |
| PAF (MAB-Proxy) | `verdict_definitions.py` | `_episode_cache.py` | verdict_matrix | Spec'd |
| TOM (DxEM) | `verdict_definitions.py` | N/A (constant True) | N/A | Spec'd |
| ACov | `verdict_definitions.py` | = ASC (tau=1.000) | verdict_matrix | Spec'd |
| AC-Artifact | N/A (coverage-only mode) | `exp_e23` | macros.tex | Verified |
| MAB-Artifact | N/A (F1-only mode) | `exp_e23` | macros.tex | Verified |
| HB-Artifact | N/A (coverage+seq mode) | `exp_e23` | macros.tex | Verified |
| LLM Catalogue | MUST+FORBIDDEN only | `llm_catalogue_shim.py` | per-type macros | Verified |
| X1 context-swap | TCC re-eval under swap | `exp_x1_context_swap.py` | macros.tex | Verified |
| X2 violation-ablation | TCC re-eval after removal | `exp_x2_causal_intervention.py` | macros.tex | Verified |
| OracleAgent gap | Oracle-RAG delta | **MISSING script** | oracle_per_domain.json | **OPEN** |

**12/13 evaluator-related components fully audited.** OracleAgent gap is the sole remaining item.
