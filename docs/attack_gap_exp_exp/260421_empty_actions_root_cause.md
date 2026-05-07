# Empty-Actions 98% Bug — Root Cause Analysis

**Session date**: 2026-04-21
**Severity**: CRITICAL — benchmark-wide measurement integrity issue
**Status**: DIAGNOSED. Fix path identified. Re-runs required.

This document captures the live-session investigation that traced the
`consecutive_empty_actions` termination (up to 98.6% of episodes in some
cells) to its actual root cause. It must NOT be lost between sessions.

---

## 1. TL;DR

- Diagnostic classifier flagged qwen4b_react (98.1%), nemotron30b_react
  (98.6%), qwen35b_tooluse (87%), qwen4b_checklist (58.6%),
  qwen35b_react (28.5%), qwen397b_react (24.8%), gemma31b_direct
  (20.3%) as CRITICAL/HIGH empty-actions cells.
- Initial hypothesis was `<think>` token parsing failure. **Ruled out.**
  `agent_runner/llm_provider.py` already implements `_strip_think_blocks`
  at 10 call sites; vLLM is called with
  `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`; chain
  logs contain zero `<think>` occurrences; live endpoint test with
  `Qwen/Qwen3-4B-Instruct-2507` returns clean JSON and empty
  `reasoning_content`.
- **Real root cause (confirmed by live raw-response capture)**: the LLM
  returns well-formed JSON with three `action_id` suggestions, but the
  suggestions are **outside the scenario's `available_actions`** list.
  `rag_agent._normalize_action_id()` rejects them (Jaccard < 0.7) and
  returns an empty list, which is logged as `"LLM returned empty
  actions"`. The code path is correct defense; the **scenario's
  available_actions is too narrow** to accept clinically valid
  suggestions.
- This is a **benchmark design issue**, not a model capability issue,
  and not a small-model-only issue: qwen397b (397B) shows 24.8%
  empty in react, qwen35b (35B) shows 87% in tooluse.
- Only oss120b (all scaffolds 8-12%) and qwen27b (0-1.2%) are healthy.
  Those two happen to copy scenario action_id strings verbatim; others
  generate clinically reasonable action names that do not lexically
  match the list.

---

## 2. Evidence chain

### 2.1 Diagnostic table (`diagnose_empty_actions.py` on `results/ex_w8_crossmodel`)

| Model | react | direct | checklist | tooluse |
|---|---|---|---|---|
| oss120b (120B) | 12.0% | 8.8% | 8.9% | 9.5% |
| qwen27b (27B) | 1.2% | — | 0.0% | — |
| qwen35b (35B) | 28.5% | 17.4% | 12.0% | **87.0%** |
| qwen4b (4B) | **98.1%** | 15.7% | **58.6%** | — |
| qwen397b (397B) | **24.8%** | 7.1% | — | — |
| nemotron30b (30B) | **98.6%** | — | — | — |
| gemma31b (31B) | 13.6% | **20.3%** | 12.3% | 13.0% |

Bold = >= 20% empty termination rate.

### 2.2 Live raw-response capture (qwen4b_react, AABB transfusion scenario)

Model returned, consistently across all 10 sampled calls:

```json
{"actions": [
  {"action_id": "order_lab_lactate", "justification": "..."},
  {"action_id": "order_lab_comprehensive_metabolic_panel", "justification": "..."},
  {"action_id": "monitor_vitals_continuously", "justification": "..."}
]}
```

Scenario's accepted actions (observed in `episode["actions"][...]`):

```
assess_hemodynamic_status, order_cbc, order_type_and_screen,
assess_active_bleeding, review_transfusion_history
```

The three proposed ids (`order_lab_lactate`, `order_lab_comprehensive_metabolic_panel`,
`monitor_vitals_continuously`) are all clinically reasonable in a
transfusion/shock-screening context but are **not** in the scenario's
`available_actions`. Normalizer rejects all three → `_generate_actions`
returns `[]` → BaseAgent's consecutive-empty counter increments →
episode terminates at step 7 with `consecutive_empty_actions`.

### 2.3 nemotron30b_react same pattern

Model returns `order_lactate`, `order_cbc_with_diff`,
`order_basic_metabolic_panel` — again clinically reasonable, still
outside scenario's list. Same rejection → same early termination.

---

## 3. Why this is NOT what we thought

| Prior hypothesis | Evidence that refutes it |
|---|---|
| Qwen cannot follow instructions | Response is well-formed JSON with reasoning text; scaffold instructions are structurally followed |
| `<think>` token parsing bug | Chain log shows zero `<think>` occurrences; live endpoint returns empty `reasoning_content` |
| Model "gives up" / returns empty | All 10 raw samples contain 3 valid action suggestions each |
| Small-model capacity limit | qwen397b (397B) also shows 24.8% empty in react |
| ReAct/tool-use scaffold is bad | checklist / direct also affected in some cells |
| Normalizer is buggy | Normalizer is correct; the `available_actions` list is too narrow |

---

## 4. Root cause, precisely

`available_actions` in each scenario YAML is an **under-coverage**
action set. Models that produce reasonable clinical workup actions
using their own id conventions ("order_lab_lactate",
"order_basic_metabolic_panel") get rejected because the scenario list
uses a different convention ("order_cbc", "order_type_and_screen"),
even though the *clinical* meaning overlaps.

Two compounding effects:

1. Small / non-oss120b / non-qwen27b models are less likely to copy
   scenario strings verbatim. They synthesize reasonable ids from
   their training distribution.
2. `_normalize_action_id` uses Jaccard >= 0.7 to fuzzy-match, which is
   too strict for *conceptually* similar ids with different tokens
   (e.g., `order_lactate` vs `order_cbc_with_diff`).

---

## 5. S2-symlink integrity failure (separate issue found in same session)

Seven `*_s2` cells in `results/ex_w8_crossmodel/` are **symlinks** to
their `*_s1` siblings, not independent seed runs:

- `qwen4b_tooluse_s2` -> `qwen4b_tooluse`
- `qwen27b_checklist_s2` -> `qwen27b_checklist`
- `qwen4b_checklist_s2` -> `qwen4b_checklist`
- `qwen397b_tooluse_s2` -> `qwen397b_tooluse`
- `qwen27b_tooluse_s2` -> `qwen27b_tooluse`
- `qwen35b_react_s2` -> `qwen35b_react`
- `qwen397b_direct_s2` -> `qwen397b_direct`

Any paper claim using `*_s2` as a seed-robustness or independent-shard
result is **invalid**. Must audit `auto_numbers*.tex` for macros that
draw from these cells and correct before submission.

---

## 6. Code patches applied this session

All patches are env-var gated so production runs are unaffected until
`CGA_DEBUG_RAW_RESPONSE=1` is set.

### `agent_runner/llm_provider.py`
- `VLLMProvider.complete()` now stores `self._last_raw_content = content`
- `OpenAIProvider.complete()` same (OpenAI-compatible endpoints)
- `complete_with_tools()` stores either `msg.content` or a
  stringified tool-call dump (`<tool_calls>name(args),...</tool_calls>`)

### `agent_runner/rag_agent.py`
- `RAGAgent.__init__` / `reset()` initialise
  `self._empty_raw_samples: list[dict] = []` (ring buffer, 20)
  and `self._llm_call_counter: int = 0`
- `_generate_actions` now snapshots the raw LLM content into the
  buffer when an empty-actions warning fires, gated by
  `os.environ.get("CGA_DEBUG_RAW_RESPONSE")`

### `scripts/experiments/full_690_runner.py`
- `episode_result` now includes
  `"empty_raw_samples": list(getattr(agent, "_empty_raw_samples", []))`
  so the raw samples survive into the per-episode JSON
- `--dry-run` now honors `CGA_DRY_N` / `CGA_DRY_RUNS` env vars
  (default 1 each) for sample-size-20 triage runs

### Result
Any episode run with `CGA_DEBUG_RAW_RESPONSE=1` in env now carries
the raw LLM content that triggered the empty-actions path, up to 20
samples per episode.

---

## 7. What 4 patch options were considered and why 3 of them are wrong

| Option | Verdict |
|---|---|
| A. Lower Jaccard threshold 0.7 -> 0.5 | Doesn't help: `order_lab_lactate` vs `order_cbc` would not match at any reasonable Jaccard threshold |
| B. Extend `DIRECT_MAPPINGS` (`order_lactate` -> `order_lab_lactate`, etc.) | Doesn't help: the *target* isn't in the scenario list either |
| C. Fuzzy best-match snap | Unsafe: snaps clinically distinct actions to each other, polluting ground-truth |
| D. Prompt re-emphasis ("MUST copy exact id") | Already present at line 929-938 of `rag_agent.py`; ineffective |

The only solutions that actually address the root cause:

- E. **Expand scenario `available_actions`** to cover clinically-valid
  workup actions, regardless of id convention. Likely requires ~20-40
  new ids per scenario on average.
- F. **Record rejected actions** as a new failure-mode field
  (`rejected_action_proposals`) so that "empty" is disambiguated into
  "truly silent" vs "proposed but rejected". Our `empty_raw_samples`
  patch is already half of this.
- G. **Constrained decoding** at the vLLM layer (`guided_choice` =
  scenario's allowed ids) to force the model to emit only in-list
  ids. Heaviest change, but eliminates mismatch entirely.

E + F is the minimum-viable fix. G is the cleanest.

---

## 8. Remaining unknowns (waiting on this session's 9-cell dry-run)

Running in background:
- qwen4b_react, nemotron30b_react, qwen35b_tooluse, qwen4b_checklist,
  qwen35b_react, qwen27b_checklist (control), gemma31b_direct
- plus qwen397b_react + oss120b_react for model-size-invariance test

Each cell: 20 scenarios × 1 run × `CGA_DEBUG_RAW_RESPONSE=1`, results
under `results/debug_raw_test/`. Target analyses:
- unique action_ids proposed per cell
- overlap rate between proposed ids and scenario `available_actions`
- distribution of rejection reasons (not-in-list vs lexically-similar-but-off)
- confirmation that qwen397b suffers the same out-of-list phenomenon
  as qwen4b (if so, "benchmark-design issue" is confirmed)

---

## 9. Paper impact (preliminary)

If the root-cause analysis holds (waiting for full dry-run):

- **AO-FA claims across models** that include qwen4b_react,
  nemotron30b_react, qwen35b_tooluse, qwen4b_checklist,
  qwen35b_react, qwen397b_react, gemma31b_direct need re-examination.
  These cells are not measuring guideline adherence; they are
  measuring lexical overlap with our `available_actions` list.
- **W8 scaffold independence** appendix claim is especially at risk.
- **Reviewer attack surface**: "your benchmark rejects clinically valid
  proposals because your action-id list is too narrow" is a 30-second
  objection that, if raised, is difficult to counter without the
  re-run.
- **S2 seed-robustness** claim is separately invalid due to the
  symlink issue (Section 5).

The honest defensive path is:
1. Fix `available_actions` coverage (E), widen scenarios.
2. Re-run affected cells with raw-response capture (F already in place).
3. Acknowledge S2 symlink issue; drop or re-run affected cells.
4. Report the rejected-proposal rate as an explicit finding rather
   than hide it behind `consecutive_empty_actions`.

---

## 10. Action items (priority ordered)

P0 (this session / today)
- [x] Write `docs/attack_gap_exp_exp/260421_empty_rate_exclusion.md`-equivalent (this file)
- [ ] Finish 9-cell dry-run with `CGA_DEBUG_RAW_RESPONSE=1`
- [ ] Quantify `available_actions` per-scenario statistics (mean/min/max/domain variance)
- [ ] Re-analyze `/tmp/chain_w8_*.log` warning patterns now that we know they are rejections, not empties
- [ ] Audit every `*_s2` cell and document which paper macros depend on symlinked data
- [ ] Git-commit code patches + this MD (no binary data)

P1 (this week)
- [ ] Expand `available_actions` across the 25 CPG graphs to cover clinically valid workup vocabulary (~20-40 ids per graph)
- [ ] Re-run the 7 CRITICAL/HIGH cells with the widened lists
- [ ] Introduce `rejected_action_proposals` field alongside `actions`
- [ ] Evaluate `guided_choice` constrained decoding in vLLM for a pilot cell

P2 (pre-submission)
- [ ] Re-compute all AO-FA / W8 / scaffold-independence numbers on the clean data
- [ ] Paper Section (Limitations) update describing the coverage gap
- [ ] Reviewer rebuttal passage ready

---

*Do not delete this document. Extend in place as analyses complete.*

---

## 11. Supporting statistics (computed this session)

### 11.1 Scenario YAML coverage (`configs/scenarios/*.yaml`)

- **Total scenarios**: 716 (13 curated domains + 601 auto-generated + 8 primary_care + 2 e2e)
- **expected_actions per scenario**: mean 12.7, median 13, min 0, max 31, stdev 6.1
- **forbidden_actions per scenario**: mean 11.0, median 11, min 0, max 27, stdev 6.8
- Unique `expected_actions` across corpus: **602**
- Unique `forbidden_actions` across corpus: **618**

### 11.2 CPG graph vocabulary (`cpg_model/graphs/*.yaml`)

| Graph | unique action ids |
|---|---:|
| aabb_transfusion | 39 |
| aba_burn_resuscitation | 50 |
| acls_cardiac_arrest | 58 |
| acog_obstetric_hemorrhage | 32 |
| ada_dka_management | 78 |
| aha_chest_pain_evaluation | 57 |
| aha_heart_failure_2022 | 109 |
| **aha_stroke_2019** | **135** |
| anaphylaxis_management | 52 |
| apa_agitation_management | 43 |
| atrial_fibrillation | 31 |
| cap_pneumonia | 15 |
| copd_exacerbation | 23 |
| gi_bleeding | 22 |
| gina_asthma_exacerbation | 57 |
| hypertensive_emergency | 27 |
| idsa_meningitis | 53 |
| kdigo_aki_full | 78 |
| kdigo_contrast_aki | 67 |
| pals_pediatric_emergency | 35 |
| pulmonary_embolism | 28 |
| ssc_sepsis_hour1_bundle | 46 |
| status_epilepticus | 68 |
| toxicology_management | 93 |
| universal_clinical_safety | 74 |

- **Total unique action ids across all 25 graphs**: **1033**
- `available_actions` is **NOT** a scenario-level field; it is populated
  at runtime from the CPG graph's per-node `allowed_actions` (see
  `agent_runner/rag_agent.py:742`). So each step of each episode shows
  only the subset of action ids that the current graph node permits,
  not the full 39-135 per-graph vocabulary.

### 11.3 Chain-log warning re-analysis (`/tmp/chain_w8_*.log`)

Re-interpretation: each `"LLM returned empty actions"` line represents
an in-flight LLM call whose parsed actions were all rejected by
`_normalize_action_id`, not a physically-empty response.

| chain | HTTP 200 | empty/200 | retry/200 | termination/progress |
|---|---:|---:|---:|---:|
| nemotron30b_144 | 9,569 | **67.6%** | 31.8% | **98.5%** |
| qwen4b | 16,155 | **51.6%** | 25.5% | **69.4%** |
| qwen4b_s2 | 7,296 | 36.0% | 17.9% | 56.2% |
| qwen397b_F | 1,682 | 21.4% | 10.7% | 24.7% |
| qwen397b_G | 4,623 | 9.5% | 4.5% | 6.8% |
| crossmodel | 9,685 | 5.0% | 3.1% | 4.6% |
| qwen27b | 4,471 | 3.2% | 1.3% | 1.2% |
| qwen27b_s2 | 3,698 | **0.1%** | 0.0% | 0.0% |

Interpretations:

- nemotron30b_144 issues 9,569 successful HTTP calls, of which
  **~6,500** (67.6%) fail normalizer. 98.5% of the episodes in its
  progress stream terminate on `consecutive_empty_actions`.
- qwen4b's retry path re-fires the same prompt with identical failure
  in ~half the retries (25.5% / 51.6% ≈ 50%).
- qwen27b_s2's 0.1% rate is **inconsistent with being a symlink of
  qwen27b (3.2%)** — this chain is writing to a distinct filesystem
  path (possibly the symlink is a newer overlay or the actual
  underlying directory). Requires clarification; the paper's
  seed-robustness numbers may or may not cover this cell depending on
  which filesystem state was sampled.

### 11.4 Action-vocabulary mismatch hypothesis

The 1033 CPG-graph action ids include domain-specific conventions:
- AABB uses `order_cbc`, `order_type_and_screen`
- Sepsis uses `order_lab_lactate`
- These are *clinically synonymous* for shock screening but
  *lexically different* ids
- When a model is evaluated on an AABB scenario, it may use
  "general clinical reasoning" and propose `order_lab_lactate`.
  That id exists in the corpus (in sepsis) but not in AABB's
  39-id vocabulary, so normalizer rejects it.

**Concrete implication**: benchmarking here is partly measuring
"can the model guess which synonym convention this particular graph
uses" rather than "does the model know what to do clinically".

### 11.5 Revised action plan

P0 (blocking):
- [x] MD captured (this file)
- [ ] S2 symlink audit: confirm whether `qwen27b_s2` 0.1% vs `qwen27b`
      3.2% is a paper-macro contradiction
- [ ] Cross-graph synonym inventory: find all lexically-different-but-
      semantically-same action id pairs (`order_cbc` ~ `order_lab_cbc`
      style) and build a canonicalization map
- [ ] Inject canonical action ids into every CPG graph's node
      `allowed_actions` (or widen the normalizer to accept canonical
      form + per-graph variant)

P1 (re-run after fix):
- [ ] Re-run every cell with empty-rate >= 20% after widening
      `allowed_actions` coverage
- [ ] Capture `empty_raw_samples` as first-class field (already wired)
- [ ] Publish rejection-rate alongside compliance-score for
      transparency

P2 (paper):
- [ ] Rewrite Limitations section to explain the "lexical synonym
      mismatch" finding as a distinct result
- [ ] Drop or footnote any claim that relies on `*_s2` cells until
      symlink / seed issue is resolved

---

## 12. Shard code behaviour (shard_runner.py)

`scripts/experiments/shard_runner.py` line 342:
```python
out_dir = Path(output_dir) / original_key
```

- `shard_runner.py qwen27b_s2 <port> results/ex_w8_crossmodel` writes
  its episodes to `results/ex_w8_crossmodel/qwen27b/` (the `original_key`
  bucket), NOT to a dedicated `qwen27b_s2/` directory.
- This means an S2 shard's output is merged into the non-S2 directory
  by design. Running s1 and s2 in parallel doubles coverage in the
  same bucket.
- The symlinks `qwen27b_checklist_s2 -> qwen27b_checklist` etc. are
  therefore **a view bug, not a shard bug**: someone created the
  symlinks hoping to expose an s2 breakout that the shard runner never
  actually writes to.
- Confirmation: `ls results/ex_w8_crossmodel/qwen27b_s2` returns 0
  files, and `readlink -f` resolves to the same literal path (no
  actual target) - the directory name `qwen27b_s2` without scaffold
  suffix does NOT exist. The scaffold-suffixed symlinks
  (`qwen27b_checklist_s2`, `qwen27b_tooluse_s2`) point to real
  non-S2 cells and thus contain the merged s1+s2 data.

### Immediate consequence for paper

`auto_numbers.tex` line 694-722 defines the W8 block:
```tex
\newcommand{\wEightTotalEpisodes}{8,472}   % 12 cells x 706
\newcommand{\wEightNPerCell}{706}
\newcommand{\wEightAggReactAOFA}{19.5}
\newcommand{\wEightAggDirectAOFA}{17.5}
\newcommand{\wEightAggChecklistAOFA}{19.0}
\newcommand{\wEightAggToolUseAOFA}{19.1}
\newcommand{\wEightFriedmanChi}{1.0}
\newcommand{\wEightFriedmanP}{0.80}
\newcommand{\wEightKendallW}{0.11}
\newcommand{\wEightComplianceMin}{0.539}   % gemma31b direct
\newcommand{\wEightComplianceMax}{0.796}   % oss120b tooluse
\newcommand{\wEightQwenTUActions}{5.3}     % qwen*_tooluse mean actions
\newcommand{\wEightQwenTUFA}{0.1}
```

- The "12 cells" = 4 scaffolds × 3 models. The comments identify
  gemma31b + oss120b + (one of qwen35b/qwen27b).
- Several of the cells in this aggregate fall in the 20-98% empty
  bucket (qwen35b_tooluse 87%, gemma31b_direct 20.3%). The aggregated
  Friedman/Kendall and AO-FA numbers above include these cells.
- Therefore: **the W8 appendix Friedman p=0.80 and AO-FA range 17.5-19.5
  are derived from episode pools that are dominated by normalizer
  rejections on some cells**. Need per-cell breakdown to decide which
  macros are rescuable.

---

## 13. Cross-graph synonym inventory (35 canonical groups, 148 near-dupes)

### 13.1 Full synonym groups (same canonical form, ≥2 variants)

18 groups, 37 ids total. Selected examples:

```
[cbc]
  order_cbc          -> aabb_transfusion, aha_heart_failure_2022
  order_lab_cbc      -> aba_burn_resuscitation, ada_dka_management,
                        aha_stroke_2019, atrial_fibrillation, ...

[creatinine]
  order_creatinine      -> kdigo_aki_full, kdigo_contrast_aki
  order_lab_creatinine  -> atrial_fibrillation, kdigo_contrast_aki,
                           universal_clinical_safety

[urinalysis]
  order_urinalysis      -> ada_dka_management, kdigo_aki_full, ...
  order_lab_urinalysis  -> hypertensive_emergency, kdigo_aki_full, ...

[ecg]
  obtain_ecg  -> apa_agitation_management
  order_ecg   -> ada_dka_management, aha_heart_failure_2022, ...

[type_and_crossmatch]
  order_type_and_crossmatch      -> acog_obstetric_hemorrhage, gi_bleeding
  order_lab_type_and_crossmatch  -> gi_bleeding

[glucose]
  check_glucose     -> aha_stroke_2019, apa_agitation_management, ...
  order_lab_glucose -> acls_cardiac_arrest, ada_dka_management, ...

[lumbar_puncture]
  order_lumbar_puncture   -> status_epilepticus
  perform_lumbar_puncture -> idsa_meningitis

[beta_blocker]
  give_beta_blocker       -> aha_heart_failure_2022, atrial_fibrillation, ...
  initiate_beta_blocker   -> aha_heart_failure_2022
  consider_beta_blocker   -> aha_heart_failure_2022
```

### 13.2 Near-duplicate pairs (Jaccard ≥ 0.6, different string)

148 pairs total. Top examples:

```
J=0.80  order_lab_type_and_crossmatch    <->  order_type_and_crossmatch
J=0.80  order_lab_serial_drug_levels     <->  order_lab_serial_levels
J=0.80  order_lab_liver_function         <->  order_lab_serial_liver_function
J=0.80  give_prbc_ffp_platelets          <->  give_prbc_ffp_platelets_1_1_1
J=0.80  give_epinephrine_1mg_iv          <->  give_epinephrine_1mg_iv_immediately
J=0.80  establish_iv_io_access           <->  establish_iv_or_io_access
J=0.75  order_stat_ct_head               <->  stat_ct_head
J=0.75  order_lab_cbc                    <->  order_lab_cbc_repeat
J=0.75  order_chest_xray                 <->  order_imaging_chest_xray
J=0.75  request_social_work_consult      <->  social_work_consult
J=0.75  discharge_without_insulin        <->  discharge_without_insulin_plan
```

### 13.3 Implication for normalizer fix

The current `_normalize_action_id` Jaccard threshold 0.7 would fire
on ≥36 of the 148 near-duplicates already. However, the real fix is
a **canonicalization pass on the CPG graphs themselves**:
choose one canonical id per canonical form and record the synonyms
as explicit aliases. This turns the benchmark deterministic (no
model-by-luck effects from which graph picked which id variant).

- Estimated effort: 148 near-duplicates + 18 full groups = ~150
  canonicalization decisions. Automatable as a script that prints
  each group and asks for the canonical choice, or uses a heuristic
  ("prefer `order_lab_*` for labs, `give_*` for meds, stripped
  prefixes for events").
- After canonicalization, re-run `diagnose_empty_actions.py` on a
  20-scenario dry-run per cell to see how much of the 20-98% empty
  rate drops.

---

## 14. Paper macros at risk of being incorrect

From `paper/auto_numbers.tex`:

| Macro | Current value | At risk because |
|---|---|---|
| \wEightTotalEpisodes | 8,472 | Aggregates over cells with ≥20% normalizer rejection |
| \wEightAggReactAOFA | 19.5 | react cell pool dominated by rejection-early-termination |
| \wEightAggToolUseAOFA | 19.1 | qwen*_tooluse 87% rejection |
| \wEightAggDirectAOFA | 17.5 | gemma31b_direct 20.3% rejection |
| \wEightFriedmanChi/P/KendallW | (1.0, 0.80, 0.11) | Depends on uniformly-contaminated cell set |
| \wEightComplianceMin | 0.539 | gemma31b_direct (20.3% rej) |
| \wEightQwenTUActions | 5.3 | qwen35b_tooluse 87% rejection; low actions BY DESIGN of the bug |
| \wEightQwenTUPassCGA | 83.3 | 83.3% of 5.3-action episodes "pass TCC" — but 87% never even got past rejection loop |
| \promptScaffoldN | 2118 | = 706 × 3 runs, but 3 runs include rejection-contaminated data |
| *_s2 derived macros (if any) | — | Depend on symlink / shard behaviour documented in §12 |

Re-derivation plan: after canonical-id + re-run, re-compute every
macro above and update `paper/auto_numbers.tex` with an explicit
diff log.               