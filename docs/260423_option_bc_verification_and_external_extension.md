# Option B/C Verification and External-Benchmark Extension

**Date:** 2026-04-23
**Branch:** eval_science
**Related:** `docs/260423_btier_self_review.md`, `docs/260423_b3_retry_report.md`,
`docs/attack_gap_exp_exp/260422_evaluator_expansion_option_{b,c}_plan.md`

---

## 목적

1. Option B / Option C의 이미 개발된 구성요소들이 **v6 canonical corpus 위에서 end-to-end로
   정상 동작하는지** 전수 검증.
2. **새로운 외부 오픈소스 의료 벤치마크**(AMEGA, MedChain, 자체 구현 dataset 등)를
   audit harness로 즉시 평가 가능하도록 **extension path** 제공.

---

## 검증: 전수 smoke test 결과

신규 스크립트 `scripts/audit/verify_audit_harness.py`가 `SHIM_REGISTRY`의 모든 shim을
`scripts/audit/evaluator_audit.py`로 end-to-end 실행하고 report.json에 필수 키
(step1_pi_class, step2_bsr, step3_bayes_floor, step6_blindspot_grid)가 존재하는지 검증.

**결과**: `--fast` 모드에서 **15/15 OK, 0 FAIL** (`llm_judge`는 cache-precompute 필요로 skip).

| shim | pi_class | BSR | Bayes floor | Red cells |
|---|---|---|---|---|
| ac_proxy | nctx | 0.4161 | 0.003 | 19/43 |
| acov_shim | nctx | 0.4161 | 0.003 | 19/43 |
| action_coverage | nctx | 0.4997 | 0.003 | 29/43 |
| active_agent | nctx | 0.0000 | 0.003 | 0/43 |
| always_true | term | 0.5161 | 0.436 | 17/43 |
| c2_score | nctx | 0.5710 | 0.003 | 29/43 |
| c2_shim | aset | 0.5814 | 0.024 | 30/43 |
| dxem | term | 0.5161 | 0.436 | 17/43 |
| **ext_healthbench_style** | nctx | 0.4522 | 0.003 | 25/43 |
| **ext_medagent_style** | nctx | 0.5067 | 0.003 | 28/43 |
| mab_f1 | nctx | 0.3990 | 0.003 | 28/43 |
| mab_proxy | term | 0.3975 | 0.436 | 27/43 |
| pi_nord_witness | aset | 0.5076 | 0.024 | 29/43 |
| v4_hard | nctx | 0.0000 | 0.003 | 0/43 |
| viol_count | nctx | 0.6393 | 0.003 | 25/43 |

- 모든 Option B 6 shim ✅
- Option C2 (minimal-repair distance ρ(d_G)) 각 report에 포함 ✅
- Option C3 (blindspot grid, red/yellow/green cells) 각 report에 포함 ✅
- B3 재도전 witness `pi_nord_witness`, ActiveAgent diagnostic도 정상 ✅

### 재현 명령

```bash
PYTHONPATH=. python scripts/audit/verify_audit_harness.py --fast
# summary JSON: /tmp/cga_audit_verify/verify_summary.json
```

---

## Extension: 새로운 외부 벤치마크 평가 path

Option C1(ExternalEvaluatorWrapper)이 기존 리포지토리에 **미구현**이었음. 이를 구현하여,
외부 벤치마크의 scoring style을 CGA-Bench audit harness에 **1개 subclass + 1개
decorator**로 즉시 등록 가능하게 만들었음.

### 추가된 구성 요소

| 파일 | 역할 |
|---|---|
| `audit/wrappers/external.py` | `ExternalBenchmarkEvaluator` 추상 클래스 + `@register_external_benchmark` decorator + `EXTERNAL_BENCHMARK_REGISTRY` |
| `audit/wrappers/external_examples.py` | 2개 worked examples: `MedAgentBenchStyleEvaluator`, `HealthBenchRubricStyleEvaluator` |
| `audit/wrappers/__init__.py` | `EXTERNAL_BENCHMARK_REGISTRY` 엔트리를 자동으로 `ext_<name>` prefix로 `WRAPPER_REGISTRY`에 병합 |
| `tests/test_audit/test_external_wrapper.py` | 등록/verdict/isolation 검증 — 10 tests |
| `scripts/audit/verify_audit_harness.py` | 15 shim 전수 end-to-end smoke |
| `docs/add_external_benchmark_to_audit.md` | 3단계 recipe + 설계 제약 + 재현 명령 |

### 3단계 recipe (요약)

```python
from audit.wrappers.external import (
    ExternalBenchmarkEvaluator, register_external_benchmark,
)

@register_external_benchmark("mybench")
class MyBenchEvaluator(ExternalBenchmarkEvaluator):
    benchmark_name = "MyBench"
    pass_threshold = 0.7
    pi_family_hypothesis = "aset"
    source_url = "https://my-benchmark.org/paper"

    def score_trajectory(self, trajectory: dict) -> float:
        taken = {a["action_id"] for a in trajectory["actions"] if a.get("action_id")}
        expected = set(trajectory.get("expected_actions") or [])
        return len(taken & expected) / max(1, len(expected))
```

이후 즉시:

```bash
PYTHONPATH=. python scripts/audit/evaluator_audit.py --shim ext_mybench --out-dir audit/reports
```

로 π-class 분류, BSR, Bayes floor, blindspot grid, top-K witness까지 모두 산출.

### 설계 제약

- `score_trajectory`는 `n_viols`, `viol_types`, `compliance_score`, `sub_scores`,
  `violation_events` 등 **TCC-derived 필드 접근 금지** (tautological self-agreement 방지).
  `test_external_wrapper.py::test_observed_features_exclude_tcc_fields`가 강제.
- Deterministic + side-effect free (no network/RNG).
- Score range [0, 1] 권장 (다르면 `pass_threshold`도 조정).

### Worked examples 검증

| Shim | Style | BSR | pi_class 판정 | pi_family_hypothesis |
|---|---|---|---|---|
| `ext_medagent_style` | action-list F1 | 0.5067 | nctx | aset |
| `ext_healthbench_style` | rubric-point hits − penalties | 0.4522 | nctx | aset |

두 예제 모두 `aset` 가설이었으나 behavioral classifier는 `nctx`로 분류. 실제 판정이 hypothesis보다 신뢰 대상 (audit step 1이 ground truth). Gap은 scenario-provided `expected_actions`가 patient-conditional mandatory와 괴리되어 경험적 구분력이 생기기 때문.

---

## Test + CI 상태

- 전체 audit 스위트: **242/242 PASS** (`pytest tests/test_audit/ -q` 소요 ~96s)
- 기존 `test_wrapper_registry_contains_all` 하드코딩된 `len==4` assertion을 dynamic 등록에
  맞춰 수정 (core 4 + ext_ prefix 가진 엔트리는 허용)

---

## 작업 경계 (미구현으로 남긴 것)

- **Option C4a Gradio demo (`demo/app.py`)** — 미구현. Reviewer zero-install 경험은 nice-to-have,
  submission 이전에 필요하면 별도 스프린트.
- **Option C4b MkDocs site (`mkdocs.yml` + `docs/audit/`)** — 미구현. 동일 이유.
- **"진짜" external benchmark native scorer 통합** — 현재 examples는 style emulators. 실제
  AMEGA/HealthBench native scorer를 CGA-Bench trajectory에 적용하려면 adapter에
  `score_trajectory` 메서드 추가 필요. 이는 각 adapter 소유자 작업.

Paper 측 영향: Contribution 4가 **"(i) Evaluator ABC + 14 built-in shims + (ii) new-benchmark
extension point with 1-decorator registration + (iii) audit CLI + (iv) verify harness"**로 완결.

---

## Commit 해시 (예정)

이 문서와 함께 커밋되는 신규/수정 파일:

- 신규: `audit/wrappers/external.py`, `audit/wrappers/external_examples.py`,
  `scripts/audit/verify_audit_harness.py`, `tests/test_audit/test_external_wrapper.py`,
  `docs/add_external_benchmark_to_audit.md`, `docs/260423_option_bc_verification_and_external_extension.md`
- 수정: `audit/wrappers/__init__.py` (external 엔트리 병합), `tests/test_audit/test_wrappers.py` (dynamic registry)

---

## Related memory entries

- `project_cga_bench_reviewer_defense.md`
- `project_b3_retry_witness.md`
- `vllm_launch_standard.md`, `gpu_server_constraints.md`, `ssh_remote_hosts.md`
