# Session Final Summary — 2026-04-23 (CGA-Bench audit harness) — v1

**Branch:** `eval_science`
**Top-level docs:** `260423_btier_self_review.md`, `260423_b3_retry_report.md`,
`260423_option_bc_verification_and_external_extension.md`,
`260423_final_status_report.md`, `260423_option_c_self_review.md`,
`add_external_benchmark_to_audit.md`,
`260423_native_bridge_drift_and_numpy_fix.md`

> **Note (v1 amended 2026-04-23):** the 3 new native bridges in this
> session shipped with a silent-zero bug (numpy scalars silently
> rejected by `isinstance(v, (int, float))`), making them return
> verdict=False on every episode and therefore BSR = 7175/14826 =
> **0.4839** tautologically. The fix landed in commit `a6c83884`
> (numpy scalar support + `native_score` return-key + manifest arg).
> Post-fix BSR values live in `docs/audit/worked-examples.md` and the
> superseding `v2` summary (`0203f29b`). Keep this v1 as a record; do
> not quote its 0.4839 numbers as final.

---

## Commits (오래된 → 최근)

| SHA | 한줄 |
|---|---|
| `362fbda5` | fix(audit): remove v4_hard from ensemble BSR pool — reference contamination 해소 (same 24.3→40.7%, cross 40.2→48.7%) |
| `03140cc6` | test(audit): fix dead assertion (`assert True` → AND⊆OR invariant) |
| `40a49b4f` | fix(audit): drop nonsensical row_max>pooled check (3 false-positive warnings 제거) |
| `b78789bb` | docs(paper): wire TIMING sharpest-separation finding Δ=0.411 into §3.3 |
| `1f738a9e` | feat(audit): B3-retry — constructive π_nord witness with honest floor gap (164×) |
| `181f4a5d` | feat(audit): external benchmark extension + Option B/C verification harness |
| `bc5dd26e` | feat(audit): Gradio demo + MkDocs docs + native-adapter bridge (C4 + C1 finish) |
| `a619a6b1` | feat(audit): 3 additional native bridges + full docs + Dockerfile + Option C self-review |

---

## Shim registry (15 entries, verify 19/19 OK)

| Category | Entries |
|---|---|
| Built-in (9) | `v4_hard`, `active_agent`, `dxem`, `ac_proxy`, `mab_proxy`, `c2_shim`, `acov_shim`, `viol_count`, `llm_judge` |
| EVP / wrappers (4) | `action_coverage`, `c2_score`, `mab_f1`, `always_true` |
| EVP witness (1) | `pi_nord_witness` |
| External style (2) | `ext_medagent_style`, `ext_healthbench_style` |
| External native (4) | `ext_medagent_native`, `ext_art_native`, `ext_agentehr_native`, `ext_healthbench_native` |

---

## Verification matrix

| Gate | Result |
|---|---|
| `pytest tests/test_audit/` | 253 passed |
| `verify_audit_harness.py --fast` | 19/19 OK (llm_judge skip) |
| `mkdocs build --quiet` | 7 rendered pages in `site/` |
| `demo/app.py` in-process smoke | OK (v4_hard + ext_medagent_style reports) |

## 핵심 수치

| 지표 | 값 |
|---|---|
| Ensemble BSR — same-class mean | 40.7% (10 pairs, v4_hard excluded) |
| Ensemble BSR — cross-class mean | 48.7% |
| B2 sharpest single-step drop | TIMING π_term→π_aset, Δ=0.411 |
| π_nord Bayes floor | 0.003 |
| π_nord constructive witness best BSR | 0.4914 (V3_half_expected), 164× gap |
| Active-agent (omission-dominance probe) BSR | 0.0000 — all 7,651 harmful episodes have n_viols=0 |

---

## 논문 방어 매트릭스

| 예상 공격 | 대응 artefact |
|---|---|
| "Theorem is just data-processing" | Contribution 4 재프레이밍 (§3.4 prose + §4.4 audit harness) |
| "Build the evaluator your theorem promises" | 164× gap 정량화 → existence theorem 재프레이밍 (§4.4 π_nord witness gap paragraph) |
| "'Any evaluator' claim scale to external benchmarks?" | 6개 `ext_*` shim (style + native), 4 native bridge가 live audit 돌림 |
| "Where is evaluator blind?" | C3 blindspot grid (domain × violation-type) 매 report.md에 포함 |
| "d_G computed?" | C2 ρ(d_G) + monotonicity violations 매 report.md에 포함 |
| "Reviewer can audit without clone?" | Gradio demo + Dockerfile + MkDocs site (HF Spaces 배포 preparedness) |
| "v4_hard가 ensemble 안에 들어있어 숫자 인위적" | Self-review C1 fix로 이미 제거, 매크로 자동 갱신 |
| "Bayes matrix validator가 매번 warning 냄" | Self-review I2 — row_max>pooled check 제거 |

---

## Deliverables by directory

```
audit/
  shims/                 10 shims incl. pi_nord_witness + active_agent
  shims/_trajectory_cache.py
  wrappers/external.py                 ExternalBenchmarkEvaluator ABC
  wrappers/external_examples.py        2 style emulators
  wrappers/native_adapter.py           NativeAdapterEvaluator ABC + _LazyAdapterBridge
  wrappers/native_adapter_examples.py  4 native bridges

scripts/
  audit/evaluator_audit.py             CLI (Steps 1..6)
  audit/verify_audit_harness.py        19/19 gate (new this session)
  experiments/exp_ensemble_bsr.py      B1 (v4_hard purge)
  experiments/exp_bayes_matrix.py      B2 (check_pooled_present)
  experiments/exp_pi_nord_witness.py   B3 retry 4 variants

evidence_pack/
  audit/ensemble_bsr_macros.tex        \ensembleSameAndMeanPct 40.7 …
  audit/ensemble_bsr_results.json      10-pair run
  audit/bayes_matrix_derived_macros.tex \bayesErrSharpestDrop 0.411 …
  audit/pi_nord_witness_macros.tex     \piNordFloor 0.003 …
  audit/pi_nord_witness_results.json   4-variant sweep

paper/main_final_v17.tex               §3.3 sharpest-separation sentence;
                                       §4.4 ensemble paragraph rewrite +
                                       omission-dominance + π_nord witness gap

demo/                                   Gradio app + Dockerfile + README

docs/audit/                             MkDocs Material site (5 pages)
mkdocs.yml                              Material theme config

docs/260423_*.md                        Session reports (see top of file)
```

## 잔여 미구현 (camera-ready 이후 후보)

- HF Spaces 실제 push — anonymity 보호로 submission까지 보류
- ~~Adapter schema-drift 감지 테스트~~ — **post-session 완료** (a6c83884에 `test_native_adapter_drift.py` 375 LOC 추가)
- ~~numpy scalar 지원 in `_extract_score_from_native_dict`~~ — **post-session 완료** (`_coerce_to_unit_float` helper)

## How to reproduce

```bash
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
# 1. 테스트
PYTHONPATH=. pytest tests/test_audit/ -q
# 2. 전수 harness smoke
PYTHONPATH=. python scripts/audit/verify_audit_harness.py --fast
# 3. 한 evaluator 상세
PYTHONPATH=. python scripts/audit/evaluator_audit.py --shim ext_medagent_native --out-dir audit/reports --top-k 5
# 4. docs 빌드
mkdocs build   # site/
# 5. demo (GPU 불필요)
PYTHONPATH=. python demo/app.py   # http://localhost:7860
```

Push는 anonymous-org 계정에서.
