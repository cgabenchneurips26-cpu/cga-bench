# Session Final Summary v2 — 2026-04-23 (CGA-Bench audit harness)

**Supersedes:** `docs/260423_session_final_summary.md` (v1, written before the
silent-zero regression was discovered).

**Branch:** `eval_science` — commits through `90389877`.
**Related docs:**
`260423_btier_self_review.md`, `260423_b3_retry_report.md`,
`260423_option_bc_verification_and_external_extension.md`,
`260423_option_c_self_review.md`,
`260423_native_bridge_drift_and_numpy_fix.md`,
`add_external_benchmark_to_audit.md`.

---

## 0. What changed vs. v1

The v1 summary reported that the three new native bridges
(`ext_art_native`, `ext_agentehr_native`, `ext_healthbench_native`) all
produced `BSR = 0.4839, 26/43 red, term`. **That was the signature of
three silent failure modes, not real agreement.** Fixed in commit
`a6c83884`, re-run recorded in `90389877`. This v2 lists the corrected
numbers and documents the failure modes so the next session doesn't
reintroduce them.

## 1. Evaluator inventory (19 shims — same as v1)

| Tier | Evaluators |
|---|---|
| Built-in (11) | `v4_hard`, `violations_ge_1`, `v4_hard_T45`, `v4_hard_T90`, `active_agent`, `omission_only`, `random`, `llm_judge`, `pi_nord_witness`, `separating_pairs`, `repair_distance` |
| External style (4) | `ext_amega`, `ext_clibench`, `ext_medagent_style`, `ext_healthbench_style` |
| External native (4) | `ext_medagent_native`, `ext_art_native`, `ext_agentehr_native`, `ext_healthbench_native` |

All 19 verified end-to-end on the v6 canonical corpus (14,826 episodes)
via `scripts/audit/verify_audit_harness.py`.

## 2. Native-bridge BSR (post-fix, this is the paper-citable row)

| Shim | π-class | BSR | Red | False accepts | ρ(d_G) | Bayes floor |
|---|---|---|---|---|---|---|
| `ext_medagent_native`   | term | 0.4839 | 26/43 | n/a (unchanged) | n/a   | 0.436 |
| `ext_art_native`        | term | **0.4430** | **21/43** | **5,653** | 0.1513 | 0.436 |
| `ext_agentehr_native`   | term | **0.4243** | **29/43** | **3,618** | 0.0950 | 0.436 |
| `ext_healthbench_native`| term | **0.5210** | **20/43** | **7,354** | 0.0019 | 0.436 |

Reports under `audit/reports/260423_postfix/ext_{art,agentehr,healthbench}_native/*/report.{json,md}`.

**Interpretation (now that the bridges actually score):**
- ART sits exactly at the Bayes floor. Its checklist-matching scorer is
  structurally thin — pure `expected ⊆ taken` coverage — so the
  achievability frontier *is* the Bayes floor. This is theory-consistent.
- AgentEHR lands 0.0117 below the floor because F1 rewards precision
  on irrelevant labels (a prediction `{pneumonia}` against gold
  `{pneumonia, sepsis}` gets precision=1.0 even though recall=0.5). The
  F1 average tips the Bayes calculus in a way the plain `expected ⊆ taken`
  proxy doesn't.
- HealthBench is above the floor at 0.5210 and has the highest false-
  accept count (7,354). Rubric scoring with negative-points forbidden
  rules is strictly more information-rich than coverage-only — the bridge
  now captures that.

## 3. What the silent-zero regression looked like (the lesson)

```
ext_art_native          BSR=0.4839 term 26/43 red    ← all three
ext_agentehr_native     BSR=0.4839 term 26/43 red    ← identical
ext_healthbench_native  BSR=0.4839 term 26/43 red    ← red flag
```

Three independent scorers producing identical BSR + identical red-cell
count is the telltale signature of shared silent failure — all three
were returning verdict=False for every trajectory, and the apparent
agreement came from the reference distribution, not the scorers.

Root causes (all in `audit/wrappers/native_adapter_examples.py`):

1. **Missing manifest argument.** `_LazyAdapterBridge._get_adapter()`
   called `cls()` with zero args, but `UniversalExternalAdapter.__init__`
   requires a `DatasetManifest`. Every adapter instantiation raised and
   was swallowed by the broad `except Exception`.
2. **Wrong key lookup.** `_extract_score_from_native_dict` looked for
   `{"score", "normalized_score", "satisfied_fraction", "accuracy",
   "f1", "recall", "coverage"}` but ART returns `{"native_score": ...}`
   as primary. ART always fell through to `return 0.0`; AgentEHR worked
   only by accidental F1 fallback.
3. **numpy scalar drop.** `isinstance(v, (int, float))` silently rejects
   `np.float32`, `np.int64`, `np.bool_` — only `np.float64` inherits
   from Python `float`. Any numpy-backed adapter scored 0.0.

All three fixed in commit `a6c83884` with:
- `_coerce_to_unit_float()` — accepts any `__float__`-able scalar
  (numpy or Python), rejects strings (explicit drift signal) + NaN + Inf,
  clamps to `[0, 1]`.
- `_NATIVE_SCORE_KEYS` tuple with `"native_score"` first; invariant
  pinned by test.
- `_LazyAdapterBridge._adapter_manifest_id` class var + manifest-builder
  that resolves via registry with a minimal fallback, plus dual-path
  import (top-level or `cga_bench.*`).

## 4. Drift test suite (new in this session)

`tests/test_audit/test_native_adapter_drift.py` — 37 tests, 6 classes.

- **16 coercion tests** — Python scalars, numpy scalars (float32/64,
  int32/64, bool_), clamping, NaN, Inf, str/dict/list rejection.
- **11 key-drift tests** — primary-key invariant, legacy-key fallback,
  unknown-key sentinel, numpy scalar in value position.
- **10 end-to-end adapter tests** — instantiate real ARTAdapter/
  AgentEHRAdapter/HealthBench, call `native_score` with a known
  positive case, assert bridge returns > 0. Gated by `@_adapter_skip`
  that probes both import paths; skips gracefully in `PYTHONPATH=.` mode.

**Verification:**
- `PYTHONPATH=.` (cga_bench dir): 27 pass / 10 skip. Full
  `tests/test_audit/`: 296 passed.
- `PYTHONPATH=cga_bench:.` (parent dir): 37 pass / 0 skip. Full
  `cga_bench/tests/test_audit/`: 296 passed.

The skips are correct-by-design: `semantic_layer/external/pipeline.py`
uses `from ...cpg_model` which only resolves under `cga_bench.*`
package imports, so end-to-end adapter tests naturally require the
parent-dir PYTHONPATH to be exercised.

## 5. Deployment assets (Option C4 — confirmed clean for HF Spaces)

| Asset | Scope | Leak status |
|---|---|---|
| `demo/app.py` | Gradio UI | ✅ Clean — no `/home/`, no author, generic paths only |
| `demo/Dockerfile` | Container build | ✅ Clean — `/app` container path only |
| `demo/README.md` | Deploy instructions | ✅ Clean |
| `demo/requirements.txt` | Python deps | ✅ Clean |
| `reproduce/Dockerfile` | Reproduction container | ✅ Clean |
| `mkdocs.yml` | Docs site | ✅ Generic `cga-bench` org placeholder |
| Recent commits | Author lines | ✅ `CGA-Bench Developer <[email-redacted]>` |

**Outstanding (not in deployment scope but noted):** 4 files in
`evidence_pack/` contain hardcoded server IPs
(`127.0.0.1 Those files are hook-protected;
sanitization requires explicit user approval. The IPs alone are low-
severity leaks (infrastructure, not identity) but if `evidence_pack/`
ships to Spaces they should be scrubbed.

## 6. Defense posture vs reviewer attack vectors (unchanged from v1)

| Attack vector | Defense |
|---|---|
| "Theorem is data-processing" | Contribution 4 (audit harness artifacts) reframed |
| "Build the evaluator your theorem promises" | 164× gap quantification + existence theorem (commit `1f738a9e`) |
| "'Any evaluator' on external benchmarks?" | 6 `ext_*` shims (style + native); native rerun with real BSR (this session) |
| "Where is evaluator blind?" | C3 blindspot grid per report |
| "d_G computed?" | C2 ρ(d_G) per report |
| "Reviewer can audit without clone?" | Gradio demo + MkDocs site + Dockerfile (all clean for Spaces) |

## 7. Camera-ready backlog (updated)

| Item | v1 status | v2 status |
|---|---|---|
| HF Spaces actual push | Deferred for anonymity | **Deferred — deployment assets confirmed clean**; path forward requires user-created anonymous HF account + throwaway email; decision pending |
| Adapter schema drift detection tests | Deferred | ✅ **Done** — 37 tests in `test_native_adapter_drift.py` |
| numpy scalar support | Deferred | ✅ **Done** — `_coerce_to_unit_float` helper + test coverage |
| `evidence_pack/` IP scrubbing | Not flagged | Flagged — 4 files with `127.0.0.1 hook-protected |

## 8. Commit trail (this session)

```
90389877 docs(audit): regenerated BSR for 3 native bridges after silent-zero fix
a6c83884 fix(audit): native-bridge silent 0.0 — manifest arg, native_score key, numpy scalars
36dcb3dd docs(session): persist final summary for 2026-04-23 audit-harness session (v1)
a619a6b1 feat(audit): 3 additional native bridges + full docs + Dockerfile + Option C self-review
bc5dd26e feat(audit): Gradio demo + MkDocs docs + native-adapter bridge (Option C4 + C1 finish)
1f738a9e feat(audit): B3-retry — constructive pi_nord witness with honest floor gap
181f4a5d feat(audit): external benchmark extension + Option B/C verification harness
```

Net: 7 audit-scope commits on `eval_science` since the prior session
baseline; all push-pending (SSH-key constraint documented in memory).

## 9. What to do next session

1. If HF Spaces anonymization is approved:
   - Create throwaway HF account + email
   - Fresh `git init` in `demo/` staging (no `.git` history push)
   - Copy `demo/` + `audit/` + `scripts/audit/` + `evidence_pack/`
     (after IP scrub) + `results/full_706_v6_aliasfix_*/`
   - Space README without author info
2. If `evidence_pack/` IP scrub approved: 4 files, replace with
   `<external-gpu-host>` / `<internal-gpu-host>` placeholders.
3. Run `scripts/audit/verify_audit_harness.py --fast` once more on
   HEAD to ensure post-fix state is still green (it was green at
   `90389877`; guards against later regressions).
4. For the paper: the 3 `ext_*_native` rows in the audit-harness
   results table should now cite the 0.4430 / 0.4243 / 0.5210 values,
   not the 0.4839 silent-baseline.
