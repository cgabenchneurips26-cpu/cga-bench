# Session Handoff: v7.3 SGSC Episode Runner Pipeline

**Date**: 2026-05-01 19:35 KST
**Branch**: `eval_science`
**Session**: full_v73_runner.py 생성 + smoke test 완료

---

## 완료된 작업

### 1. SGSC JSON → YAML Converter (Task #14)

**파일**: `scripts/sgsc/sgsc_to_yaml.py`

- `sgsc_output/v7_e3_combined_v3/` (core 25) + `sgsc_output/v7_2_atoms_v3/` (expansion 25) → `configs/scenarios/sgsc/*_scenarios.yaml`
- 49 graphs 중 48 productive (east_damage_control_mtp_2017 = 0 scenarios)
- **418 scenarios** 변환 완료, ScenarioLoader 검증 통과

### 2. ScenarioLoader SGSC 지원 (eval_harness/scenario_loader.py)

- `include_sgsc` 파라미터 추가 (`CGA_BENCH_INCLUDE_SGSC` env var)
- `sgsc/` glob 패턴 추가
- v5/v6 (942) + SGSC (418) = 1,360 통합 로딩 가능

### 3. full_690_runner.py SGSC 패치

- `--include-sgsc`, `--sgsc-only` CLI 플래그 추가
- `load_all_scenario_ids()` + `run_single_episode()` 모두 `CGA_BENCH_SGSC_ONLY` 환경변수 지원
- **주의**: v6 전용 runner이므로 v7.3 프로덕션 런에는 사용하지 않을 것

### 4. full_v73_runner.py 신규 생성 (Task #17)

**파일**: `scripts/experiments/full_v73_runner.py`

v7.3 전용 runner. `full_690_runner.py`와의 차이점:

| 항목 | full_690 (v6) | full_v73 (v7.3) |
|---|---|---|
| 시나리오 소스 | v5/v6 YAML (706) + optional SGSC | SGSC-only (418), 플래그 불필요 |
| MODELS dict | 50+ entries (W8 scaffolds, S2 등) | 10 baseline 모델, 정리된 포트 |
| qwen397b 포트 | 30003 (stale) | 30001 (current) |
| Target count | 하드코딩 706 | `SCENARIO_COUNT = 418` |
| experiment_id | `"full_690"` | `"full_v73"` |
| Output dir | `results/full_690_*` | `results/v73_*` |
| 결과 메타데이터 | — | `"corpus": "sgsc_v73"` 태그 |
| 인프라 | 자체 구현 | full_690에서 import (dedup, claims, sharding, checkpoint, health) |

### 5. Endpoint Health Check (Task #15 — 부분)

| Endpoint | Model | Status |
|---|---|---|
| 127.0.0.1 | Qwen/Qwen3.5-397B-A17B-FP8 | **ONLINE** |
| 127.0.0.1 | Qwen/Qwen3.5-397B-A17B-FP8 | **ONLINE** |
| 127.0.0.1 | gemma31b | OFFLINE |
| 127.0.0.1 | nemotron30b | OFFLINE |
| 127.0.0.1 | deepseek_r1_7b | OFFLINE |
| 127.0.0.1 | llama4scout | OFFLINE |
| localhost:28000 | oss120b | OFFLINE |
| localhost:28010 | qwen27b | OFFLINE |
| localhost:8013 | qwen35b | OFFLINE |
| localhost:8101 | qwen4b | OFFLINE |

### 6. Smoke Test 결과 (Task #16)

1×1×1 smoke test 2회 실행 (full_690 + full_v73), 모두 성공:

| 항목 | 값 |
|---|---|
| Scenario | `aabb_transfusion_adverse_events_c004` (SGSC v7.3 core) |
| Model | Qwen3.5-397B via 127.0.0.1 |
| CGA score | **0.75** |
| Violations | 6 (timing:1, deviation:3, omission:2) |
| Forbidden triggered | 0 |
| LLM calls | 12-13 |
| Total tokens | ~32K |
| Empty responses | 0 |
| JSON parse retries | 1 (자동 복구) |
| Termination | timeout (120min sim) |

### 7. ActionNormalizer 호환성 확인

- N1-N5 + B3 (commit `2fbb3da0`) 변경사항은 `ViolationExtractor`와 `cpg_engine.engine` 내부에서 자동 적용
- Runner에서 별도 import/wiring 불필요
- v7.3 runner에서 정상 동작 확인

---

## 앞으로 할 작업

### P0: 8 Endpoint 런칭 (수동 작업 필요)

SSH 접속 후 vLLM 인스턴스 런칭 필요. 참조: `docs/vllm_ops_knowhow.md`, `.claude/rules/vllm-launch.md`

```bash
# 144 (H200x8)
# gemma31b — port 30003, TP=1
CUDA_VISIBLE_DEVICES=4 nohup ~/.local/bin/vllm serve google/gemma-4-31b-it \
  --port 30003 --tensor-parallel-size 1 --max-model-len 8192 \
  --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill \
  --max-num-seqs 256 --api-key sk-no-key-required \
  --trust-remote-code --limit-mm-per-prompt '{"image":0}' \
  > ~/vllm_logs/gemma31b.log 2>&1 & disown

# nemotron30b — port 30004, TP=1, max-num-seqs=8 (Xid 43)
# H200 ONLY (compute capability 9.0 required)
CUDA_VISIBLE_DEVICES=5 nohup ~/.local/bin/vllm serve nvidia/Nemotron-3-Nano-30B-A3B-FP8 \
  --port 30004 --tensor-parallel-size 1 --max-model-len 8192 \
  --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill \
  --max-num-seqs 8 --api-key sk-no-key-required \
  > ~/vllm_logs/nemotron30b.log 2>&1 & disown

# 145 (A100x8)
# deepseek_r1_7b — port 30009, TP=1
# llama4scout — port 8201, TP=4 (218GB BF16, A100 TP=4 필수)

# localhost (146)
# oss120b — port 28000, TP=2
# qwen35b — port 8013, TP=1
# qwen27b — port 28010, TP=1
# qwen4b — port 8101, TP=1
```

런칭 후 health check:
```bash
for ep in 30003 30004; do
  curl -s -m 5 -H "Authorization: Bearer sk-no-key-required" \
    http://localhost:8013${ep}/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])"
done
```

### P1: Full v7.3 Benchmark Run

모든 endpoint 가동 후:

```bash
# 모델별 개별 실행
PYTHONPATH=. python scripts/experiments/full_v73_runner.py qwen397b results/v73_full
PYTHONPATH=. python scripts/experiments/full_v73_runner.py qwen397b_s2 results/v73_full  # 병렬 2nd instance
PYTHONPATH=. python scripts/experiments/full_v73_runner.py oss120b results/v73_full
PYTHONPATH=. python scripts/experiments/full_v73_runner.py qwen35b results/v73_full
PYTHONPATH=. python scripts/experiments/full_v73_runner.py qwen27b results/v73_full
PYTHONPATH=. python scripts/experiments/full_v73_runner.py qwen4b results/v73_full
PYTHONPATH=. python scripts/experiments/full_v73_runner.py gemma31b results/v73_full
PYTHONPATH=. python scripts/experiments/full_v73_runner.py nemotron30b results/v73_full
PYTHONPATH=. python scripts/experiments/full_v73_runner.py deepseek_r1_7b results/v73_full
PYTHONPATH=. python scripts/experiments/full_v73_runner.py llama4scout results/v73_full

# 예상 에피소드: 418 × 10 models × 3 runs = 12,540
# 예상 용량: ~610 MB (12,540 × ~50 KB)
```

Sharded 실행 (대형 모델):
```bash
# qwen397b 2-shard (30001 + 30002)
PYTHONPATH=. python scripts/experiments/full_v73_runner.py qwen397b results/v73_full --shard 1/2 --port 30001 &
PYTHONPATH=. python scripts/experiments/full_v73_runner.py qwen397b_s2 results/v73_full --shard 2/2 --port 30002 &
```

### P2: 30분 모니터링 프로토콜

런 시작 후 30분간:

```bash
# 5분 간격 체크
watch -n 300 'for m in qwen397b oss120b qwen35b qwen27b qwen4b gemma31b nemotron30b deepseek_r1_7b llama4scout; do
  d=results/v73_full/$m
  [ -d "$d" ] && echo "$m: $(ls $d/*.json 2>/dev/null | grep -v checkpoint | grep -v model_summary | wc -l) episodes"
done'
```

감시 항목:
- Empty action rate > 20% → prompt 문제
- Endpoint 응답 지연 > 30s → GPU 메모리 부족
- JSON parse retry > 10% → thinking model strip 필요
- Connection refused → endpoint 다운

### P3: Macro / Paper 업데이트

모델 수 결정 후:
- `\sgscModelCount{8}` → 9 또는 10 (Llama-4-Scout 포함 여부)
- v7.3 결과 기반 새 auto_numbers 생성 스크립트 필요

### P4: CAV v0.6 Integration (Optional)

- `cav_v0_6/cav_v0_6.json` (2,276 entries, 100% alignment) 빌드 완료
- 현재 runner에 wired 되어있지 않음
- Post-hoc rescoring 가능: `scripts/sgsc/rescore_v6_with_cav.py`

---

## 생성/수정된 파일 목록

### 신규 생성
| 파일 | 설명 |
|---|---|
| `scripts/experiments/full_v73_runner.py` | v7.3 전용 episode runner |
| `scripts/sgsc/sgsc_to_yaml.py` | SGSC JSON → YAML 변환기 |
| `configs/scenarios/sgsc/*.yaml` (49 files) | v7.3 시나리오 YAML |

### 수정
| 파일 | 변경 |
|---|---|
| `eval_harness/scenario_loader.py` | `include_sgsc` 파라미터 + `sgsc/` glob |
| `scripts/experiments/full_690_runner.py` | `--include-sgsc`, `--sgsc-only` 플래그 (v6 호환) |

---

## 이전 세션에서 이월된 완료 항목 (참고)

| Task | Status | 산출물 |
|---|---|---|
| C-6: Entailment audit | DONE | 58.2% over-rejection 발견 |
| C-7a: Entailment 3 fixes | DONE | stemming + threshold 0.6 |
| C-7b: Core 25 re-extraction | DONE | 883 atoms, 143 scenarios |
| C-7c: Expansion 25 re-extraction | DONE | 611 atoms, 275 scenarios |
| C-5: v7.3 final compile | DONE | 418 scenarios, macros 수정 |
| Task #10: Counterfactual families | DONE | 1,860 families (2.4 MB) |
| Task #11: CAV v0.6 | DONE | 2,276 entries, 100% alignment |
| Task #12: Launch verification | DONE | 3 blockers identified |
| Task #13: Environment smoke | DONE | 7/7 actions pass |
| Scenario count discrepancy | DONE | 1,590 = vectors, 418 = runnable |

---

## 핵심 주의사항

1. **full_690_runner.py는 v6 전용**. v7.3 프로덕션 런에는 `full_v73_runner.py` 사용할 것.
2. **ActionNormalizer N1-N5 + B3**: 자동 적용됨. Runner 수준 wiring 불필요.
3. **SGSC 시나리오 수는 418** (NOT 1,590). 1,590은 coverage vectors (seeds + counterfactual families).
4. **qwen397b 포트**: v73_runner는 30001 (현재 활성). v6 runner의 30003은 stale.
5. **결과 구분**: v7.3 결과에는 `"corpus": "sgsc_v73"` 메타데이터 포함.
6. **Disk space**: 101 GB free. 12,540 episodes × ~50 KB = ~610 MB. 충분하지만 여유롭지는 않음.
