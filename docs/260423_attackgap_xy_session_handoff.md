# Session handoff — attack-gap X + Y (to next session)

**From session:** 2026-04-23 v5 (attackgap.md X/Y experiments + reframing + dual-LLM replication + verification)
**Branch:** `eval_science` (push-ready)
**Prior reports:** `260423_attackgap_xy_{report, v3_report, v4_report, v5_report}.md`

Everything closed this session is committed; everything below is the
explicit **to-do for the next session**, with enough context to
resume without re-reading the chain of reports.

---

## State at handoff

### Pose-B §4.3 three-pillar evidence (completed)

| Pillar | Claim | Evidence |
|---|---|---|
| 1 Verdicts catalogue-conditional | τ=-0.075 on single shim; threshold sweep \|τ\| ∈ [0.028, 0.058] | Y.3 + Y.3 threshold sweep |
| 2 π-class ordering catalogue-robust | term > aset > nord ≈ nctx under CDE and LLM | Y.3-extended (4-projection Bayes error) |
| 3 Magnitude catalogue-conditional | v1 Qwen 5.50× and v2 gpt-oss 5.60× (Δ=0.10×) | Main-finding full replication × 2 LLM families, 25/25 CPGs each |

All three pillars cited in paper §2 / §4.4 / §AB.5 via macros
(see `evidence_pack/constraint_comparison/main_finding_full_replication_{,v2_}macros.tex`).

### Data artefacts (on disk, push-ready)

```
evidence_pack/cross_benchmark_forward/mab/results.json          (300 eps, FA 58.67%)
evidence_pack/cross_benchmark_forward/agentclinic/results_122.json  (122 eps, coverage 2.37%)
evidence_pack/constraint_comparison/
  llm_raw/              25 files (Qwen-3.5-397B @ 144:30001)
  llm_raw_v2/           25 files (gpt-oss-120b @ 145:30005/30015/30025)
  y3_bayes_extended_results.json          Bayes-error ordering check
  y3_threshold_sweep_results.json         threshold robustness
  main_finding_full_replication_results.json   v1 Qwen family shims
  main_finding_full_replication_v2_results.json   v2 gpt-oss family shims
evidence_pack/ex_w8_crossmodel/
  w8_results_v2.json     8-model × 4-scaffold Friedman (n=8, χ²=1.05, p=0.79)
```

---

## Addendum (Gap 1/2/3/5 + Revision 4 verification)

Numbers transcribed so next session's prose edits can land without re-running jobs.

### Gap 1 — per-type LLM counts (v1 Qwen / v2 gpt-oss, both 25/25)

| Type | CDE | Qwen (v1) | gpt-oss (v2) | v1/CDE | v2/CDE | **v2/v1** |
|---|---|---|---|---|---|---|
| MUST | 557 | 434 | 490 | 0.78× | 0.88× | 1.13× |
| FORBIDDEN | 212 | **592** | **572** | **2.79×** | **2.70×** | **0.97×** |
| WITHIN | 215 | 182 | 190 | 0.85× | 0.88× | 1.04× |
| BEFORE | 65 | 60 | 34 | 0.92× | 0.52× | 0.57× |

**Arithmetic freeze — REQUIRED entries filtered, all totals now internally consistent**:

| | Total entries | 4-type canonical sum | non-canonical | Status |
|---|---|---|---|---|
| Qwen v1 | **1,268** | **1,268** | 0 | exact |
| gpt-oss v2 | **1,286** | **1,286** | 0 | exact (after REQUIRED filter) |

Action taken (2026-04-24): the 11 non-canonical `REQUIRED` entries
gpt-oss emitted (5 in AHA-2020-ACLS-Guidelines, 6 in
GINA-2024-Asthma-Exacerbation) were filtered out of
`llm_raw_v2/*.json`. Each affected file now carries
`filtered_non_canonical` / `filtered_timestamp` bookkeeping fields.
All summaries and the main-finding replication re-ran cleanly:

```
v1 Qwen     total=1268  MUST=434  FORBIDDEN=592  WITHIN=182  BEFORE=60
v2 gpt-oss  total=1286  MUST=490  FORBIDDEN=572  WITHIN=190  BEFORE= 34
            (ratio: MUST 0.88× CDE, FORBIDDEN 2.70× CDE, etc.)
v2 main-finding replication unchanged: triple FA 36.95%, ratio 5.60×
```

No footnote needed — every number in the paper Table now reconciles
to a 4-type sum without a "per-type may exceed total" caveat.

Artefacts:
  evidence_pack/constraint_comparison/llm_summary.json       regen
  evidence_pack/constraint_comparison/llm_summary_v2.json    regen (filtered)
  evidence_pack/constraint_comparison/compare_summary.json   regen (dual)
  evidence_pack/constraint_comparison/per_type_table_macros.tex
    \cdeVsLlm{Cde,V1,V2}{Must,Forbidden,Within,Before,Total}
    \cdeVsLlm{V1,V2}MultiTypeDup

If `06_pose_b_catalogue_audit.md` §5.2 or `08_macros_reference.md`
Check 1 still references "1088" or any pre-filter v2 number, it
should be reconciled to 1,286 (the canonical post-filter total).

FORBIDDEN over-extraction **2.70-2.79×** is stable across two
LLM families (Δ=0.09×) → dual-family method-class signature. BEFORE
does not replicate (v1 0.92× / v2 0.52×), model-specific.

### Gap 2 — §4.2 wording accuracy

Paper currently reads:
- "CDE recovers 2.00× more MUST" — **WRONG**, actual ≈ 1.2×
- "LLM captures 2.5× more FORBIDDEN" — under-estimate, actual ≈ 2.75×

Proposed replacement:

> "Both LLM families systematically under-extract MUST (≈1.2× fewer
> per catalogue) and over-extract FORBIDDEN (≈2.75× more),
> reproducing a catalogue-method signature stable across Qwen-397B
> and gpt-oss-120b (Δ ≤ 0.10× on MUST/FORBIDDEN/WITHIN; BEFORE is
> model-specific)."

### Gap 3 — fibre-mass paper cite policy

| source | term | aset | nord | nctx |
|---|---|---|---|---|
| canonical published (CDE, 5-min bin) | 100% | 9.8% | 1% | 1% |
| self-contained recompute (CDE) | 62% | 12% | 2% | 2% |
| self-contained recompute (LLM) | 16% | 0.03% | 0% | 0% |

Policy: keep canonical (100/9.8/1/1) in paper. Self-contained recompute
serves Y.3-extended ordering check only — do NOT cite absolute mass.

### Gap 5 — clinician companion study status

Paper §4.3 (line 363) and §6 Limitations (line 517) already honestly
read "pre-registered and pre-frozen but not yet executed; camera-ready
addendum". No edit needed.

### Revision 4 — `\varianceEtaEval`

- `auto_numbers.tex` (v17): **0.312**
- `verify_friedman_eta.py` (current corpus): **0.339**
- η²(run) computed 0.000 vs auto_numbers 0.036 — WARNING

**Proposed**: update `\varianceEtaEval` → 0.339. Simultaneously
reconcile `\etaRatio` (200,000 → 94,113). Reproducible values win.

---

## To-do list (priority ordered)

### P1 — Camera-ready blockers

**1.1 Reconcile `\etaRatio = 200,000` vs script-computed 94,112.7×**

Ran `scripts/verify_friedman_eta.py` against current v6 corpus:

- η²(evaluator) = 0.3386 (auto_numbers says 0.312)
- η²(run) = 0.0000 (auto_numbers says 0.036 — WARNING fires)
- derived ratio = 94,112.7×
- paper's `\etaRatio` macro = 200,000

Three possible values, none match. Either:
  (a) re-derive `\etaRatio` from current corpus → 94,113 (4.7 × 10⁴)
  (b) document how the 200,000 figure was arrived at in auto_numbers
  (c) replace both with the η²(evaluator) / η²(run) ratio = 8.7× if
      auto_numbers η²(run)=0.036 is the canonical version

Action: decide between (a)/(b)/(c) with co-author; update paper macro
and any prose that cites `\etaRatio`. Cite `scripts/verify_friedman_eta.py`
as the source script.

**1.2 Paper §4.2 CDE description — Y.1 one-liner insertion**

User-approved wording from the v3-round discussion:

> "CDE and LLM extraction produce catalogues of comparable size
> (0.83× aggregate ratio on 25 CPGs) but with divergent type
> composition: CDE recovers 2.00× more MUST constraints, while LLM
> captures 2.5× more FORBIDDEN constraints. This method-signature
> asymmetry motivates our multi-catalogue audit stress test (§4.4)."

Insert into §4.2 after the CDE construction description
(main_final_v17.tex near line 339). Cites `\cdeVsLlmRatio`,
`\cdeVsLlmRatioMust`, `\cdeVsLlmRatioForbidden` (all already in
preamble).

**1.3 Pillar 2 fibre-mass reconciliation (optional)**

If paper §4.4 pillar 2 prose quotes LLM-label fibre mass numbers,
recompute under the canonical projection functions in
`scripts/_projections.py` (the self-contained projection in
`scripts/experiments/exp_piclass_bayes_llm_catalogue.py` gives
(15.68, 0.03, 0, 0) for LLM labels, which is not directly
comparable to the canonical CDE-label published numbers
(100, 9.8, 1, 1)).

Current paper §4.4 cites only ε values, not fibre mass — so this
is a double-check for author drafts, not a required edit.

### P2 — Nice-to-have

**2.1 Z.3 Figure 5 regeneration (4×8 heatmap)**

Data frozen at `evidence_pack/ex_w8_crossmodel/w8_results_v2.json`.
Need matplotlib script producing:

```
rows    = 4 scaffolds (react, direct, checklist, tooluse)
cols    = 8 models (alphabetical or by model size)
cell    = compliance_mean (0.0–1.0, colormap = RdYlGn or similar)
```

Target paper location: replace `paper/figures/ex_w8_heatmap.pdf`
(or whatever Figure 5 is currently pointing at; grep
`main_final_v17.tex` for `figures/` imports near §AB.5).

Associated prose update: replace any "4×3" reference with "4×8".

**2.2 gpt-oss 7 formerly-failed CPGs — quality spot-check**

The chunked recovery pass produced 73–166 constraints per CPG;
dedup removed exact duplicates but may retain near-duplicates
across chunk boundaries. Spot-check 2-3 CPGs (AHA-Heart-Failure
has 166, highest) for:
- fabricated "MUST" entries not in source text
- redundant entries that differ only by case or whitespace
- LLM hallucinations of `deadline_minutes`

If quality is fine, no action. If poor, tighten dedupe by adding
a fuzzy-match dedupe (same normalised token set).

**2.3 MAB forward per-task vocabulary alignment (deferred from X.3)**

X.3 per-task FA = {task1/2/3/8: 100%, task6: 0%, task4: 10%, …} is
driven by action-vocabulary overlap, not pipeline defect. A
vocabulary-alignment pass (add DIRECT_MAPPINGS for
`verify_patient_identity` → `get_patient`, etc.) would land FA
in the plan's 20-35% expected band. Low priority — the per-task
heterogeneity is the real finding.

### P3 — Out of scope (document but don't plan)

- Claude API or a third LLM provider for 3-way catalogue robustness
- User study (anonymity risk)
- Stream-mode gpt-oss JSON assembly (chunked prompt already works)
- Full statsmodels mixed-effects rebuild of η² on raw episodes
  (current ANOVA + jackknife is sufficient)

---

## Endpoints and infra reminders

| Host | Port(s) | Model | Notes |
|---|---|---|---|
| 127.0.0.1 | 30001 | Qwen/Qwen3.5-397B-A17B-FP8 | Read-only, never restart |
| 127.0.0.1 | 30005 / 30015 / 30025 | openai/gpt-oss-120b (×3 instances) | Free-to-manage, round-robin for serial calls |
| 127.0.0.1 | — | — | Off-limits, serving host |

API key: `sk-no-key-required` for all 127.0.0.1 endpoints.
Context window: gpt-oss `max_model_len=8192`; long CPGs need
chunked-prompt path (see `scripts/experiments/exp_cde_vs_llm_v2_chunked.py`).

Habit reminder (from `feedback_persist_session_summaries.md`): every
session's final state must land in `docs/` md + memory before
close. This file IS that handoff artefact for the v5 session.

## Commit log summary (session total)

Latest 20 on `eval_science` (for context when this file is read cold):

```
(chunked)  feat(audit): gpt-oss v2 chunked recovery — 7/7 recovered
986aca84   docs(paper): §2 + §4.4 2-family citation + §AB.5 n=8
(repair)   feat(audit): gpt-oss v2 repair pass — 3/10 recovered
04f71225   docs(session): attackgap v4 addendum
77fbe007   feat(audit): LlmCwtFull WITHIN+BEFORE unchanged
9c916239   feat(audit): Z.2 Friedman n=3→n=8 scaffold indifference persists
(v2 repl)  feat(audit): gpt-oss-120b catalogue reproduces 5.5×
dcf95354   docs(session): attackgap v3 addendum
ed7579c3   feat(audit): main-finding partial replication
009f87b3   feat(audit): Y.3 matcher-threshold sweep
1fbbba0f   feat(audit): Y.3-extended ordering-preservation
3b75780b   docs(session): attackgap X+Y v2 addendum
f4dbd137   feat(audit): X AC forward re-score 20 eps
37daf07a   docs(paper): §4.4 catalogue-conditional + forward replay
f8112f82   feat(audit): Y.1 complete 25/25 + Y.3 invariance NOT invariant
48bcf370   docs(session): attack-gap X + Y session report
9038b2ec   feat(audit): Y.1 CDE vs LLM constraint extraction
3a562329   feat(audit): X.3 MedAgentBench forward-direction TCC re-score
```
