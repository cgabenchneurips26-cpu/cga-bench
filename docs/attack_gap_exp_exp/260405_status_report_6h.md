# CGA-Bench 진행 보고 (2026-04-05 17:00 ~ 23:20 KST)

## 1. 에피소드 실행 상황 (full_706_v5)

### 현재 상태: 실행 중 (8개 러너)

| 러너 | 모델 | GPU | 에피소드 파일수 | 목표 (706×3) | 달성률 |
|------|------|-----|----------------|-------------|--------|
| full_690_runner | gemma31b | 외부 | 3,327 | 2,118 | **157%** (초과 → 3-run 필터로 정제) |
| full_690_runner | nemotron30b | 외부 | 3,259 | 2,118 | **154%** |
| full_690_runner | qwen4b | 0,1 | 2,623 | 2,118 | **124%** |
| full_690_runner | qwen35b | 0,1 | 2,960 | 2,118 | **140%** |
| full_690_runner | qwen27b | 3 | 3,177 | 2,118 | **150%** |
| full_690_runner | oss120b | 0,1 | 2,789 | 1,800* | **155%** |
| full_690_runner | qwen397b | 외부 | 2,269 | 2,118 | **107%** |
| shard_runner | qwen397b_s2 | 외부 | (포함) | — | 보조 실행 |

\* oss120b: 600 시나리오 × 3 runs = 1,800 (전체 706 중 600개만 할당)

**GPU 현황**: GPU 0,1,3 사용 중 (vLLM 서버) / GPU 2,4,5,6,7 유휴

### DeepSeek R1 7B 시도 → 실패

- vLLM 서버 배포 성공 (GPU 1개)
- 3-way 샤드 러너 시작
- **문제**: 모델이 JSON action 대신 추론(reasoning) 텍스트만 출력 → 100% empty actions
- **판단**: 모델 아키텍처 문제 (reasoning model은 direct JSON 생성 불가)
- shard runner + vLLM 종료 처리 완료

---

## 2. EX-1 LLM Judge 실험 완료

- **OSS120b 2nd judge** 실행 완료 → `evidence_pack/exp_2_llm_judge.json` 갱신
- Git commit + push 완료: `39428c45 feat(defense): EX-1 oss120b second judge + DeepSeek R1 attempt`

---

## 3. 핵심 작업: 3-Run 필터 + 전체 파이프라인 갱신

### 문제 인식

사용자 지적: "원래 3 run만 하기로 했는데 14,042개를 그냥 다 쓰면 일관된 기준이 아니다. 정제해서 써야 한다."

### 해결: 3-Run Completeness Filter 도입

**원칙**: `(model, scenario)` 쌍이 정확히 3 run 이상인 것만 사용, 초과분은 run_index 0,1,2만 유지

- **적용 전**: 14,073개 (raw dedup) → 일부 2-run, 4-run 쌍 혼재
- **적용 후**: **14,055개** (4,685 complete sets × 3)

### 수정된 파일들

| 파일 | 변경 내용 |
|------|----------|
| `verdict_matrix_v5.py` | `filter_complete_sets()` 함수 추가 — 3-run 미만 쌍 제거 |
| `exp_e3_instrumentation_ablation.py` | **전면 리팩토링** — gap_experiments.py 의존성 완전 제거, canonical-set filter 적용 |
| `exp_e18_artifact_mimic.py` | MODEL_LABELS 필터 + canonical-set filter (verdict_matrix_v4.json 기준) |
| `exp_e1_verdict_flip.py` | N_EPISODES 동적화 (hardcoded 180 → JSON에서 읽기) |
| `exp_e2_bsr.py` | 동일 |
| `exp_e4_operating_point.py` | 동일 |
| `extract_auto_numbers.py` | N_EPISODES 동적화 + `_latex_safe()` (`.` → `p` 변환으로 유효한 LaTeX 매크로명 생성) |

### 일관성 보장 구조

```
verdict_matrix_v5.py ─→ verdict_matrix_v4.json (14,055 episodes)
                              │
      ┌───────────────────────┼───────────────────────┐
      ↓                       ↓                       ↓
  E1/E2/E4/E5             E3 ablation            EX-18 mimic
  (JSON 직접 읽기)    (canonical-set filter)  (canonical-set filter)
```

E3와 EX-18는 raw episode를 직접 로드하지만, `verdict_matrix_v4.json`의 `per_episode` 목록을 참조해 동일한 14,055개만 필터링.

---

## 4. 실험 결과 (14,055 에피소드 기준)

### E1: Verdict-Flip Prevalence

| 항목 | 값 |
|------|-----|
| Flip 비율 | **81.5%** (11,454/14,055) |
| AC-Proxy FA rate | **39.4%** |
| MAB-Proxy FA rate | **31.3%** |
| C2 FA rate | **17.1%** |
| CGA-Bench FA rate | **0.0%** |
| All-Oblivious FA | **13.1%** |

### E2: Blind Spot Rate

| Evaluator | BSR |
|-----------|-----|
| DxEM | 47.7% |
| AC-Proxy | 39.4% |
| MAB-Proxy | 31.3% |
| C2 | 17.1% |
| CGA-Bench | **0.0%** |

### E3: Instrumentation Ablation

| 조건 | Hard Violation Episodes |
|------|----------------------|
| Full (모든 계측) | 6,700/14,055 |
| -Timestamps | 1,198/14,055 |
| -Ordering | 6,661/14,055 |
| -State | 6,492/14,055 |
| Terminal (계측 없음) | 0/14,055 |

### E4: Operating-Point Matched Agreement

| Pass Rate | Fleiss κ | Flip Rate |
|-----------|---------|-----------|
| ≈30% | 0.039 | 78.3% |
| ≈40% | 0.069 | 80.7% |
| ≈50% | 0.038 | 84.3% |

### E5: Evaluator Expansion

| 항목 | 값 |
|------|-----|
| Clusters | 3 |
| Cophenetic correlation | 0.889 |
| Bootstrap ARI | 1.000 |

### EX-18: Artifact Mimic

| Evaluator | Pass Rate | FA+TCC gain |
|-----------|----------|-------------|
| AC-Proxy | 72.3% | 54.5% |
| MAB-Proxy | 54.5% | 57.5% |
| C2 | 33.2% | 42.6% |
| TCC | 52.3% | — |

---

## 5. auto_numbers.tex 정리

### Before → After

| 항목 | Before | After |
|------|--------|-------|
| 매크로 수 | ~470 (중복 포함) | **356** (unique) |
| `?` 플레이스홀더 | 4개 | **0** |
| "refresh after" 코멘트 | 8개 | **0** |
| Period-containing 매크로 | ~80개 (`.`가 든 무효 이름) | **0** |
| 중복 매크로 | 다수 | **0** |
| 기준 에피소드 수 | 혼재 (180, 14,042, 14,043) | **14,055 통일** |

### 주요 정리 작업

1. `\constraintDensityP{?}` 등 4개 orphaned placeholder 삭제
2. 미사용 raw EX-1 매크로 3개 삭제
3. `extract_auto_numbers.py`가 반복 실행 시 추가하던 period-containing 중복 블록 4개 (약 110줄) 삭제
4. `.` → `p` 인코딩으로 유효한 LaTeX 매크로명 생성 (`passRateACProxyAt0p5` 등 20개)
5. 모든 "14,042"/"14,043" 코멘트 → "14,055" 갱신

---

## 6. GPU 자원 정리

| GPU | Before | After |
|-----|--------|-------|
| GPU 2 | vLLM 점유 (zombie) | **해제** (0 MB) |
| GPU 4 | vLLM 점유 | **해제** (0 MB) |
| GPU 5-7 | 유휴 | 유휴 |
| GPU 0,1 | oss120b vLLM | 유지 (실행 중) |
| GPU 3 | qwen27b vLLM | 유지 (실행 중) |

---

## 7. 미커밋 변경사항 (45 files changed)

주요 변경:
- `paper/auto_numbers.tex` — 444줄 변경 (전면 갱신 + 정리)
- `scripts/experiments/exp_e3_*.py` — 전면 리팩토링
- `scripts/experiments/exp_e18_*.py` — canonical filter 추가
- `scripts/experiments/extract_auto_numbers.py` — `_latex_safe()` 수정
- `evidence_pack/` — 모든 E1-E5 + EX-18 JSON/MD/TEX/PNG 갱신
- `paper/appendix.tex`, `paper/appendix_figures.tex` — 이전 세션 수정 포함

---

## 8. 남은 작업

| # | 작업 | 상태 | 비고 |
|---|------|------|------|
| 1 | 실행 중인 에피소드 완료 대기 | **진행중** | 러너 8개 계속 실행 중 |
| 2 | Git commit + push | **대기** | 사용자 승인 필요 |
| 3 | Phase 5: "patient-safety" 용어 수정 | **미착수** | main_final_v10.tex 3곳 |
| 4 | Phase 5: Code/Data availability 확장 | **미착수** | NeurIPS D&B 요구사항 |
| 5 | Phase 6: 추가 모델 (OpenBioLLM-70B 등) | **미착수** | GPU 필요 |
| 6 | `\numEpisodesActual{14055}` 매크로 추가 여부 | **검토 필요** | 본문에서 실제 수치 참조용 |
