# ALLM.H Artifact Index — 2026-05-05

Single point of reference for all ALLM.H-related computation artifacts produced in the 2026-05-04 ~ 2026-05-05 sessions. Use this index to navigate paper macros, raw analysis data, and detailed reports.

---

## 1. ALLM.H Consolidated Macros (NEW)

**`paper/auto_numbers_allmh.tex`** — 184 lines, 91 macros, 9.4 KB

Substrate-prefixed macros (no name conflicts) covering 5 substrates:
- `\allmhVThreeFull*` — V7.3 Full (n=12,540, 10 models)
- `\allmhVThreeCatA*` — V7.3 Cat A subset (n=1,350, 10 models)
- `\allmhVThreeExpanded*` — V7.3 Expanded (n=20,400, 10 models)
- `\allmhVSixSevenSix*` — V6 706 manual (n=21,180, 10 models)
- `\allmhVSixPhaseB*` — V6 Phase B (n=86,022, 9 models)
- `\allmhLadder*` — 5-substrate typed CwT comparison

Plus model metadata (`\allmhModelName`, `\allmhBaseModel`, `\allmhAdapter`, etc.) and the substrate-dependent finding macros (`\allmhBestSubstrate`, `\allmhWorstSubstrate`, `\allmhRankSpread`, etc.).

---

## 2. Per-Substrate Full Macros (10/9-model, includes ALLM.H + 9/8 other models)

| File | Lines | Substrate | n | Models |
|------|-------|-----------|---|--------|
| `paper/auto_numbers_v73_full_with_allmh.tex` | 283 | V7.3 Full | 12,540 | 10 |
| `paper/auto_numbers_v73_expanded_with_allmh.tex` | 283 | V7.3 Expanded | 20,400 | 10 |
| `paper/auto_numbers_v6_706_with_allmh.tex` | 283 | V6 706 manual | 21,180 | 10 |
| `paper/auto_numbers_v6_phase_b_with_allmh.tex` | 265 | V6 Phase B | 86,022 | 9 |

These use the original `\vSevenThree*` prefix (clashing across substrates if loaded together). Use `auto_numbers_allmh.tex` for cross-substrate macros and these for per-substrate full tables.

---

## 3. Raw Analysis Data (paper-source-of-truth JSON)

### Typed CwT (cross-substrate ladder)
| Path | Substrate | Key fields |
|------|-----------|-----------|
| `evidence_pack/analysis/v73_full_with_allmh_typed_cwt.json` | V7.3 Full | η²eval orig 0.260, typed 0.427, Δ +0.167 |
| `evidence_pack/analysis/v73_cat_a_with_allmh_typed_cwt.json` | V7.3 Cat A | η²eval orig 0.255, typed 0.386, Δ +0.132 |
| `evidence_pack/analysis/v73_expanded_with_allmh_typed_cwt.json` | V7.3 Expanded | η²eval orig 0.156, typed 0.420, Δ **+0.264** |
| `evidence_pack/analysis/v6_706_with_allmh_typed_cwt.json` | V6 706 | η²eval orig 0.114, typed 0.052, Δ **−0.061** |
| `evidence_pack/analysis/v6_phase_b_with_allmh_typed_cwt.json` | V6 Phase B | η²eval orig 0.178, typed 0.094, Δ **−0.084** |

### Verdict matrix (5-evaluator: AC / MAB / C2 / ACov / CGA-Bench)
| Path | n | Models |
|------|---|--------|
| `evidence_pack/analysis/verdict_matrix_v7_3_with_allmh.json` | 12,540 | 10 |
| `evidence_pack/analysis/verdict_matrix_v73_expanded_with_allmh.json` | 20,400 | 10 |
| `evidence_pack/analysis/verdict_matrix_v6_706_with_allmh.json` | 21,180 | 10 |
| `evidence_pack/analysis/verdict_matrix_v6_phase_b_with_allmh.json` | 86,022 | 9 |

### Phase 1 raw macros (per-model CGA / sub-scores / token / violation)
- `evidence_pack/analysis/v7_3_with_allmh_macros.json`
- `evidence_pack/analysis/v73_expanded_with_allmh_macros.json`
- `evidence_pack/analysis/v6_706_with_allmh_macros.json`
- `evidence_pack/analysis/v6_phase_b_with_allmh_macros.json`

---

## 4. Detailed Reports (markdown)

### Methodology + critical analysis
- **`docs/critical_review/deviation_metric_reconsideration_20260504.md`** (171 lines, 6 sections, 19 sub-sections)
  - DEVIATION rubric flaw analysis using ALLM.H ARDS scenario as case study (ALLM.H 0.750 vs qwen397b 0.000 with same 24 actions)
  - typed_compliance design rationale (FA 2×, η² −56%, run/eval reversal)
  - paper v1 / benchmark v2 recommendations
  - "ALLM.H 보고는 dual metric 의무" 결정의 근거

### Submission artifacts
- **`paper_artifacts/CROISSANT_README.md`** — NeurIPS 2026 D&B Croissant submission guide
- **`paper_artifacts/croissant_v7_3_minimal_valid.json`** — validator-passing Croissant file (9 RAI fields)

### Repo structure
- **`docs/paper_macros_fillin_report_20260505.md`** — auto_numbers_fallback.tex 58 placeholder fillin (not ALLM.H specific but related to V7.3 paper)

---

## 5. Memory Topic Files (cross-session knowledge)

Persistent knowledge stored in `/home/anonymous-user/.claude/projects/-home-anonymous-org-AnonProject-anonymous-user-AnonProject/memory/`:

- **`project_allm_h_v73_deployment.md`** (232 lines, ~21 KB)
  - Endpoint provisioning (148:8000, max_len 8192), repo structure (LoRA adapter on Gemma-4-31B base)
  - 5/5 substrate readiness + paper-ready inventory
  - 64-worker single-substrate sweet spot (vs 96 = 146 CPU saturation)
  - generate_v73_auto_numbers.py corpus filter bug + monkey-patch workaround
  - Symlink dirs work for typed_cwt + verdict_matrix but NOT auto_numbers
  - V6 706 ALLM.H scope mismatch (942 scenarios → archive 708 to align with 706 reference)
  - Per-substrate ALLM.H rank pattern (V7.3 top-5, V6 bottom-9-10)

- **`project_v73_typed_cwt_sanity_3check.md`** (~10 KB)
  - 5-substrate typed CwT monotonic ladder: V7.3 Expanded (+0.264) → V7.3 Full (+0.167) → V7.3 Cat A (+0.132) → V6 706 (−0.061) → V6 Phase B (**−0.084**)
  - anonymous-user plan η²=0.2558 was V7.3 Cat A misreference (Expanded baseline=0.156)
  - DEVIATION 2-flavor decomposition (invention + selection bias) supported by data
  - V6 manual core typed CwT REVERSAL — author-bias absent in expert-curated corpus

---

## 6. Headline numbers (TL;DR for paper §5 ALLM.H subsection)

```
ALLM.H = LoRA adapter on google/gemma-4-31b-it (Korean medical SFT, KorMedMCQA + simpo)

Per-substrate CGA mean / CGA pass% / Rank:
  V7.3 Full      :  0.5902 / 79.3% / 5/10  ← top 5
  V7.3 Expanded  :  0.5985 / 80.8% / 5/10  ← top 5
  V6 706 manual  :  0.5053 / 52.1% / 9/10  ← bottom 2
  V6 Phase B     :  0.4461 / 54.7% / 8/9   ← bottom 2

Substrate dependence: rank 5 → 9 (4-rank spread), CGA 0.598 → 0.446 (0.144 absolute drop, 25% relative)

DEVIATION-mediated bias: ALLM.H's medical-SFT vocabulary aligns with auto-generated SGSC
graph terms (V7.3) but NOT with expert-curated V6 manual graphs.

Recommended paper claim: "ALLM.H demonstrates substrate-dependent gains, with strongest
performance on auto-generated SGSC corpora (top-5/10 in V7.3) and weakest on expert-
curated manual corpora (bottom-2 in V6). This pattern is consistent with the DEVIATION
2-flavor decomposition (invention + selection bias) — ALLM.H benefits from corpus
vocabulary invention bias and is penalized by selection bias under graph-anchored
expert vocabulary."
```

---

## 7. Reproduction commands

```bash
# Re-run typed CwT on any substrate
PYTHONPATH=$(pwd):$(dirname $(pwd)) python scripts/experiments/compute_typed_cwt.py \
  --results-dir results/<substrate> \
  --output evidence_pack/analysis/<substrate>_typed_cwt.json

# Re-run verdict matrix (env-var driven)
PYTHONPATH=. CGA_VERDICT_RESULTS_DIR=results/<substrate> \
  CGA_VERDICT_OUTPUT_JSON=evidence_pack/analysis/verdict_matrix_<substrate>.json \
  CGA_VERDICT_OUTPUT_TEX=evidence_pack/analysis/verdict_matrix_<substrate>.tex \
  python3 -c "import sys; sys.path.insert(0,'scripts/experiments'); import verdict_matrix_v5 as V; V.COMPLETE_MODELS = frozenset(V.COMPLETE_MODELS | {'allm_h'}); V.MODEL_LABELS['allm_h'] = 'ALLMH'; V.main()"

# Re-run auto_numbers (with monkey-patched corpus filter for non-V7.3)
# See memory `project_allm_h_v73_deployment.md` §"generate_v73_auto_numbers.py corpus filter bug"
```
