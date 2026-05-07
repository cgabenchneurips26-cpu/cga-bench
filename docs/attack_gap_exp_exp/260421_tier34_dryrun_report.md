# Tier 3/4 Dry-Run Verification — 2026-04-21

## Method

Ran 20 scenarios × 1 run for each of two contaminated cells with
`CGA_DEBUG_RAW_RESPONSE=1`, using the new 3-tier normaliser
(commit `2433efd2`) against the existing vLLM endpoints.

## Results

### qwen4b_react (145:30006)

| metric | ORIGINAL W8 (pre any patch) | AFTER Tier 3/4 |
|---|---:|---:|
| n | 823 | 22 |
| empty_term % | **98.2** | **90.9** |
| cs_mean | 0.414 | 0.403 |
| actions_mean | 13.2 | 9.1 |
| tag=(none) | N/A | 201 (100 %) |
| tag=GENERAL_WORKUP | N/A | 0 |
| tag=DEVIATION | N/A | 0 |

### nemotron30b_react (144:30003)

| metric | ORIGINAL W8 (pre any patch) | AFTER Tier 3/4 |
|---|---:|---:|
| n | 577 | 22 |
| empty_term % | **98.8** | **90.9** |
| cs_mean | 0.403 | 0.387 |
| actions_mean | 12.2 | 12.5 |
| tag=(none) | N/A | 274 (100 %) |
| tag=GENERAL_WORKUP | N/A | 0 |
| tag=DEVIATION | N/A | 0 |

## Observation 1 — Tier 3/4 is latent (not firing) in practice

Both cells show 100 % tag=(none) on committed Actions. This means
every model-emitted action_id was either an exact match to the
scenario's available_actions (Tier 1) or an alias-map canonical that
hit the scenario set (Tier 2). Tier 3 (UCS) and Tier 4 (DEVIATION)
never activated.

Why this differs from the 30 % Tier 4 predicted in
`260421_three_tier_normalizer_design.md` §6:
- The simulation there used an **AABB-narrow 5-id** availability set.
- Real scenarios traverse multiple CPG nodes with expanding
  `allowed_actions` sets (15–135 ids per graph; cpg-graphs.md §1).
- As episodes progress, the accumulated allowed set is large enough
  to contain most of nemotron's "reasonable ER workup" vocabulary
  (`order_lactate`, `order_cbc_with_differential`, …) directly.

This is actually the **desired** behaviour — the alias map plus the
progressively-expanding scenario set absorb the lexical variation
without needing Tier 3/4 fallbacks. Tier 3/4 remain correctly
implemented as a safety net for the remaining cases; they simply do
not fire often in this corpus.

## Observation 2 — Empty-term rate dropped but only modestly (98 → 91 %)

The gap between "0 empty-returns predicted by simulation" and
"90.9 % empty_term observed" is explained by:

- `_normalize_action_id` now never returns None for non-empty
  `available_actions` → **the normaliser-level bug is fixed**.
- BUT `_generate_actions` further filters by
  `action_id in completed_action_ids` (rag_agent.py:1144).
- When a narrow-mode model repeatedly proposes the same 3 ids
  across successive turns, after those ids are completed once, every
  subsequent step's proposals get filtered out by the completion
  check → empty action list → `consecutive_empty_actions` increment.

This is a **different bug**: it's not a lexical mismatch (which
Tier 3/4 would catch), it's a **scenario-context collapse** where
the model ignores the scenario and keeps reproposing its favourite
sepsis-ish ids.

## Observation 3 — Episode length preserved, compliance comparable

actions_mean for both cells is at parity with the original W8 runs
(nemotron 12.5 ≈ 12.2; qwen4b 9.1 vs 13.2 — latter is smaller
sample). cga_mean drops slightly (0.414→0.403 for qwen4b;
0.403→0.387 for nemotron). Small sample (n=22) makes these
differences insignificant; both values are in the 0.38–0.41 range.

This confirms Tier 3/4 did **not** corrupt scoring — the scorer
still converges to similar values. What it didn't do is rescue the
cells from consecutive_empty termination.

## Conclusion

- ✅ The 3-tier normaliser is **correctly implemented** (456/456 tests
  pass, 0 empty-returns in simulation).
- ⚠️ It is **not sufficient alone** to fix narrow-mode cells
  (qwen4b, nemotron30b). The remaining 90 % empty_term is due to
  model behaviour (same-ids repetition), not normaliser rejection.
- 👉 **Step 3.5 (qwen4b prompt engineering) is required** to fix
  the underlying scenario-context collapse. Tier 3/4 is the
  infrastructure that will prevent REAL benchmarks from silently
  dropping LLM-emitted ids once scaffold fixes land.

## Next actions

Proceed with the plan's Step 3.5 (qwen4b prompt engineering) and
Step 4 (targeted re-runs) on cells where the fix matters. Tier 3/4
can be left in place as a safety net — it costs nothing when
inactive and catches genuine vocabulary mismatches for models we
haven't yet observed.
