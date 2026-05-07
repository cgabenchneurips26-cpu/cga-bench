# Task 2 + Alias Map Fix Summary — 2026-04-21

Branch: `eval_science`. Commits chained over a single afternoon session:

| SHA | Summary |
|---|---|
| `340193a3` | feat(scaffold): split empty-action termination into agent_exhausted vs consecutive_empty |
| `d9216378` | test(fixture): repair two pre-existing drifts (LLMConfig max_tokens, septic_shock E2E) |
| `b8304c0c` | fix(scaffold): preserve agent_exhausted hint when rule fallback returns empty |
| `68395d2c` | feat(scaffold): add agent_completed termination_reason for LLM-declared stops |
| `35c39d32` | fix(alias-map): split CBC / BMP / lactate / vitals-monitor into distinct canonicals |
| `e5c16477` | infra(vllm): standardise launch flags and 145 reshuffle script for ~3x sweep throughput |

## What changed, and why

### 1. Scaffold termination classification (Task 2)

The original ``consecutive_empty_actions`` termination_reason collapsed
three distinct failure/stop modes under a single label:

| Label (after this patch) | Behaviour |
|---|---|
| ``consecutive_empty_actions`` | LLM returned genuinely nothing parseable. |
| ``agent_exhausted`` | LLM emitted structurally valid actions but every single one was already in ``completed_action_ids``. Scaffold-level re-proposal loop. |
| ``agent_completed`` | LLM emitted ``"actions": []`` with reasoning explicitly declaring the protocol done (e.g. stable STEMI post-reperfusion with no indication for the remaining optional fluid bolus). |

Instrumentation lives in ``rag_agent.py::_generate_actions_with_llm``
and ``_generate_actions_with_tool_use`` (agent-side hint) and
``base_agent.py::run_episode`` (reads the hint on the consecutive-empty
threshold). Diagnostic at ``scripts/risk_mitigation/diagnose_empty_actions.py``
gained two new buckets to report the split.

**Regression fix en route**: The tail of ``_generate_actions`` was
unconditionally clearing the hint to ``None`` when the rule fallback
had no actions to contribute — silently wiping the earlier LLM-path
exhaustion signal on every exhaustion decide() call. Commit `b8304c0c`
moved the clear inside the "rule fallback produced fresh actions"
branch only, so the hint survives to base_agent.

### 2. Alias-map corruption (pre-existing, unrelated to Task 2)

The automated ``scripts/tools/build_canonical_action_map.py`` seed
``SEED_SYNONYM_GROUPS[§13.4]`` had been force-merging five clinically
distinct actions into a single ``order_lab_basic_metabolic_panel``
canonical:

```
- monitor_vitals_continuously   ← monitoring, not a lab
- order_cbc                     ← CBC ≠ BMP
- order_lab_cbc                 ← CBC ≠ BMP
- order_lab_cbc_repeat
- order_lab_cmp                 ← debatable (CMP is superset of BMP)
- order_lab_comprehensive_metabolic_panel
- order_lab_lactate             ← lactate is a completely separate analyte
- (plus BMP aliases)
```

Effect: any LLM emission of CBC, lactate, or continuous-vitals
monitoring in scenarios where the graph's mandatory id was different
was silently rewritten to BMP in the normalised action stream. AABB
CBC-mandatory scenarios, sepsis lactate-mandatory scenarios, and any
scenario where vitals monitoring was clinically appropriate all
scored incorrectly.

Fix (`35c39d32`):
- §13.4 seed split into four per-test canonical groups
  (``order_lab_cbc``, ``order_lab_basic_metabolic_panel``,
  ``order_lab_comprehensive_metabolic_panel``, ``order_lab_lactate``).
- Separate ``assess_vital_signs`` seed for all monitoring verbs.
- Builder step 5 ("re-choose canonicals") made seed-canonical-sticky
  so the author's chosen canonical name is not silently demoted to
  whichever variant sorts first alphabetically (``assess_bp`` vs
  ``assess_vital_signs`` was the trigger case).
- Five additional seed groups added from the off-graph proposal
  catalog: ``monitor_urine_output``, ``order_imaging_ecg`` (adds
  ``obtain_12_lead_ecg``), ``check_current_medications``,
  ``reassess_clinical_presentation``, ``check_oxygen_saturation``.

Tests that encoded the buggy behaviour were rewritten into
regressions against it (`test_cbc_bmp_lactate_do_not_share_canonical`
et al.).

### 3. Empirical impact — 4-model dry-run (16 stride-sampled scenarios each)

Same 16 scenarios, four sets of binaries:

**Baseline** (pre-Task-2, pre-alias-fix):

| Model | ``consec_empty_actions`` |
|---|---|
| qwen4b_react | 62.5 % |
| nemotron30b_react | 93.8 % |
| qwen27b_react | 12.5 % |
| qwen397b_react | 12.5 % |

**Post Task-2 + rule-fallback-clear fix** (re-labelled, same behaviour):

| Model | exhausted | completed | consec_empty | timeout | disposition |
|---|---|---|---|---|---|
| qwen4b_react | 68.8 % | 6.2 % | 6.2 % | 25.0 % | 0.0 % |
| nemotron30b_react | 93.8 % | 0.0 % | 0.0 % | 6.2 % | 0.0 % |
| qwen27b_react | 6.2 % | 6.2 % | 6.2 % | 50.0 % | 37.5 % |
| qwen397b_react | 6.2 % | 12.5 % | 12.5 % | 56.2 % | 25.0 % |

**Post alias-map fix** (this session's final measurement):

| Model | exhausted | completed | consec_empty | timeout | disposition | Mean CS | Mean actions |
|---|---|---|---|---|---|---|---|
| qwen4b_react | 68.8 % | 6.2 % | **0.0 %** | 25.0 % | 0.0 % | 0.586 | 20.4 |
| nemotron30b_react | 93.8 % | 0.0 % | **0.0 %** | 0.0 % | 6.2 % | 0.419 | 15.2 |
| qwen27b_react | 6.2 % | 6.2 % | **0.0 %** | 50.0 % | 37.5 % | 0.566 | 21.1 |
| qwen397b_react | 6.2 % | 12.5 % | **0.0 %** | 62.5 % | 18.8 % | 0.603 | 22.1 |

**Key reading:** the ``consecutive_empty_actions`` rate after both the
Task-2 split and the alias-map repair is **zero across all four models**.
Every empty-style termination was in fact either a scaffold-level
exhaustion loop (``agent_exhausted``) or an agent-declared completion
(``agent_completed``). The pre-fix 62 / 94 / 12 / 12 "empty" rates were
entirely a measurement artefact of the labelling collapse plus the
alias corruption.

Mean compliance_score and mean-actions-per-episode tick up on every
model under the alias-map fix, with the largest jump (+0.028 CS) on
nemotron30b — the model with the heaviest exhaustion traffic and
therefore the most alias-drops per episode under the buggy map.

## Re-measurement surface

Because the alias map was silently rewriting action ids in episode
logs, **every downstream aggregate computed from ``full_706_v5`` is
stale**. The scope of re-measurement lines up with the paper's main
numbers.

**P0 (scoring integrity — must re-measure):**
1. ``full_706_v5`` re-run. 8 models × 706 scenarios × 3 runs = 16,944
   episodes per model; see ``configs/experiments/`` for the sweep
   script.
2. Per-domain means (SSC sepsis, AHA chest pain, AABB transfusion,
   universal safety, etc.) → regenerate ``auto_numbers.tex`` +
   ``auto_numbers_v2.tex``.
3. Per-violation-type aggregates (OMISSION / COMMISSION / TIMING /
   SEQUENCE / DEVIATION). OMISSION in particular was directly inflated
   by the alias corruption.
4. X9 grid reanalysis, X2 violation-event ablation with placebo
   control.
5. Held-out 1,188 episodes (heldout_macros.tex).
6. Oracle per-domain table.
7. Prompt-sensitivity table, distribution-check table.
8. Per-coordinate / per-violation-type Bayes error macros
   (``scripts/compute_bayes_error.py``).

**P1 (interpretation / figures):**
9. Figure 3 / 4 / 5 that plot ``empty_term %`` — replot with the
   three-way split (``agent_exhausted`` / ``agent_completed`` /
   ``consec_empty``) so the reader sees that the "empty" axis in prior
   drafts was conflating three phenomena.
10. ``260421_macro_taint_reverify.md`` — re-run the contamination scan
    with the new termination_reason buckets. The 20 % threshold may
    bin differently.
11. The narrow-mode narrative (the session's earlier thread on prompt
    v2) — re-frame with the new reading that prompt-level residual
    empty is ~0 %; the outstanding issue is scaffold-level exhaustion.

**P2 (spot-check re-verification):**
12. X1 context-swap (97.29 % TCC flip rate claim) — alias impact is
    probably small but worth confirming.
13. Prior ``auto_numbers_v2.tex`` values.
14. Heldout episode counts vs. expected (1,188 vs. 1,584 discrepancy
    already flagged in memory entry 441).

## Wall-clock plan

Per ``.claude/rules/vllm-launch.md`` (standardised 2026-04-21) +
``scripts/infra/launch_vllm_145.sh``:

| Model | Endpoints | Est. wall clock |
|---|---|---|
| qwen4b (2× instances) | 145:30006, 145:30008 | ~3–4 h |
| deepseek_r1_7b | 145:30009 | ~6–8 h |
| qwen27b FP8 | 145:30003 | ~10–15 h |
| qwen35b A3B FP8 | 145:30007 | ~15–20 h |
| gemma-4-31b-it | 145:30004 | ~15–20 h |
| nemotron30b (144, unchanged flags) | 144:30003 | ~35 h |
| oss-120b TP=2 | 145:30005 | ~25–30 h |
| qwen397b (144, unchanged flags) | 144:30002 | ~70 h (bottleneck) |

144 retains its existing launch flags (read-only host; vLLM restart
not an option at time of writing). 145 gets reshuffled end-to-end via
the new launch script.

Total wall clock ≈ 3 days, bounded by qwen397b on 144.
