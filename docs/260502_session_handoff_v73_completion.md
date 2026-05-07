# Session Handoff — SGSC v7.3 Completion + Canonical Merge + Auto Numbers Generator

**Date**: 2026-05-02 (KST)
**Branch**: `eval_science`
**Last commit**: `e4af154c` (beta-1..6 entailment + normalizer wire-in)
**Working dir**: `/home/anonymous-org/anonymous-project/AnonProject/cga_bench`
**Predecessor handoff**: [260501_session_handoff_v73_runner.md](./260501_session_handoff_v73_runner.md)
**Detailed analysis**: [260502_v7_corpus_session_analysis.md](./260502_v7_corpus_session_analysis.md)

---

## 1. TL;DR

- **SGSC v7.3 본런 9/9 모델 100% 완주** (11,286 episodes, post-CAV canonical)
- 145 → 146 머지 완료. canonical 위치는 `results/v73_full/`. pre-CAV 7,027 eps는 `results/v73_full_146_pre_cav_archive/`로 보관
- v7.3 자동 매크로 파이프라인 구축: `verdict_matrix_v7_3.json` + `auto_numbers_v73_full.tex` (213 macros) + `auto_numbers_v73.tex` (64 macros, cross-pool subset)
- nemotron 144 endpoint 살아있음 (정리 권장)

---

## 2. 완료 작업

### 2.1 nemotron30b 11 graph 마지막 r-instance 복구
| 시도 | 결과 | 핵심 |
|---|---|---|
| v1 | FAIL | 잘못된 모델 ID (`nvidia/Nemotron-...`, NVIDIA 접두 누락) |
| v2 | FAIL | `--trust-remote-code` 누락 |
| v3 | FAIL | `FileNotFoundError: ninja` (FP8 modelopt 커널 의존) |
| v4 | FAIL | `--enforce-eager` 추가했으나 ninja 여전히 필요 |
| v5 | OK (60s) | `pip install --user ninja` + PATH 추가 → ready |
| v6 | FAIL | 멀티 alias `--served-model-name` + GPU 0 orphan 132GB |
| **v7** | **OK (45s)** | orphan kill + FP8 only |

145 runner config 패치: `MODELS["nemotron30b"]["config"]`을 `clean_slate_nemotron30b_local.yaml` (BF16) → `clean_slate_nemotron30b.yaml` (FP8)로 sed.

최종 잔여: 1 r-instance (`aha_acc_aortic_dissection_2022_7711_initial_management_of_bttai_c015 r1`) — checkpoint.json reset 후 처리, CGA 0.4706 기록, 12:50 KST 완주.

### 2.2 145 → 146 canonical 머지
```bash
mv results/v73_full → results/v73_full_146_pre_cav_archive   # 7,027 eps, 5/1 night, false-OMISSION 82%
mv results/v73_full_145 → results/v73_full                    # canonical, 11,286 eps, post-CAV
```

145 로컬 FS에서 rsync 전송 완료 (425MB). dedup 후 정확히 418×9×3=11,286 unique (scen, run_idx) 페어.

### 2.3 자동 매크로 파이프라인 구축 (Phase 1 + Phase 2)

#### 2.3.1 Verdict matrix v7.3 생성

`scripts/experiments/verdict_matrix_v5.py`를 env vars로 v7.3에 적용:

```bash
CGA_VERDICT_RESULTS_DIR=results/v73_full \
CGA_VERDICT_OUTPUT_JSON=evidence_pack/analysis/verdict_matrix_v7_3.json \
CGA_VERDICT_OUTPUT_TEX=evidence_pack/tables/verdict_matrix_v7_3.tex \
PYTHONPATH=. python3 scripts/experiments/verdict_matrix_v5.py
```

Output 핵심:
- 11,286 episodes, 9 models
- v4_hard: 43.5% (4,906)
- v4_crit: 6.4% (721)
- AC pass rate: 9.5%, MAB: 0.2%, C2≥0.7: 30.3%, CGA: 56.5%

`ac_proxy/mab_proxy/c2_pass/v4_hard`는 **모두 episode JSON에서 derive 가능한 proxy** (LLM-judge 재실행 불필요). Threshold: AC=0.5, MAB-F1=0.5, C2=0.7, ACov=0.5.

#### 2.3.2 v7.3 단독 generator

**`scripts/experiments/generate_v73_auto_numbers.py`** (신규):
- Phase 1 (episode JSON 직접): core counts, per-model CGA, sub-scores C1-C5, violations by type, termination dist, token usage, per-graph
- Phase 2 (verdict matrix): AC/MAB/C2/CGA pass rates, BSR, verdict flip, consensus FA, η²(eval/run), Kendall W

Output:
- `paper/auto_numbers_v73_full.tex` (265 lines, **213 macros**, prefix `\vSevenThree*`)
- `evidence_pack/analysis/v7_3_macros.json` (raw 값)

#### 2.3.3 Cross-pool unified generator

**`scripts/experiments/generate_unified_auto_numbers.py`** (수정):
- v7.3 pool 추가 (verdict_matrix_v7_3.json 자동 감지)
- 4-pool 비교: phaseA / v6base / phaseB / **v73**
- Output: `paper/auto_numbers_v73.tex` (64 macros, prefix `\v73*`, phaseA/B와 일관 패턴)
- `paper/auto_numbers_unified_audit.tex`에 cross-pool divergence flags

#### 2.3.4 Naming convention 정리

| 파일 | prefix | 매크로 수 | 용도 |
|---|---|---:|---|
| `auto_numbers_v73_full.tex` | `\vSevenThree*` | 213 | v7.3 단독 풀 분석 |
| `auto_numbers_v73.tex` | `\v73*` | 64 | cross-pool 비교 (phaseA/B/v6base와 동일 패턴) |

`paper/auto_numbers.tex`에 양쪽 모두 `\input` 추가됨.

### 2.4 잘못된 시도 + 취소 (교훈)

세션 중 GPU idle 0%를 채우려고 `W8_RUNS=5` env var로 Llama-Scout runner 12 worker launch 시도. 사용자 지적 후 즉시 취소:
- 모델별 run 횟수 불일치 (Scout=5, 그 외=3) → mean/CI 비교 무의미
- 분석 스크립트 silent bias
- Git hash drift, CAV 상태 변화 추적 불가
- dedup 영원 잠금

처리: 12 workers killed, r3 14 + r4 13 = 27 files 삭제, stale claims 정리.

**교훈**: GPU 가동률 KPI를 위해 spec 밖 작업 만들지 말 것. paper plan에 정합한 작업에만 컴퓨트 투입.

---

## 3. Cross-pool 비교 결과 (참고)

| Evaluator | phaseA | v6base | phaseB | **v73** | spread |
|---|---:|---:|---:|---:|---:|
| DxEM | 100% | 100% | 100% | 100% | 0pp |
| AC-Proxy | 76.9% | 76.9% | 80.0% | **9.5%** | **70.5pp** |
| MAB-Proxy | 52.7% | 51.5% | 39.4% | **0.2%** | **52.5pp** |
| C2≥0.7 | 27.8% | 28.0% | 25.1% | 30.3% | 5.3pp |
| CGA-Bench | 44.6% | 44.8% | 67.0% | 56.5% | 22.4pp |
| Verdict flip | 85.7% | 85.5% | 85.1% | 78.6% | — |
| Consensus FA (3-way) | 5.90% | 5.38% | 3.89% | **0.00%** | — |

**v7.3 AC=9.5%, MAB=0.2% 거대 격차 (paper 가치 있음)**:
- SGSC 시나리오의 expected_actions가 v6 manual보다 훨씬 많음 (avg 25-50개) → coverage threshold 0.5 어려움
- Consensus FA = 0건 → **CAV-wired 시나리오에서는 false accept이 사실상 사라짐** (강력한 ablation 자료)

---

## 4. 파일 변경 목록

### 신규 생성
| 파일 | 설명 |
|---|---|
| `docs/260502_v7_corpus_session_analysis.md` | 14-section 분석 보고서 |
| `docs/260502_session_handoff_v73_completion.md` | (this file) |
| `scripts/experiments/generate_v73_auto_numbers.py` | v7.3 단독 매크로 generator |
| `paper/auto_numbers_v73_full.tex` | 213 매크로 (`\vSevenThree*`) |
| `paper/auto_numbers_v73.tex` | 64 매크로 (`\v73*`) |
| `evidence_pack/analysis/v7_3_macros.json` | raw 매크로 값 |
| `evidence_pack/analysis/verdict_matrix_v7_3.json` | 11,286 ep verdict matrix |
| `evidence_pack/tables/verdict_matrix_v7_3.tex` | verdict matrix LaTeX summary |

### 수정
| 파일 | 변경 |
|---|---|
| `paper/auto_numbers.tex` | `\input{auto_numbers_v73_full.tex}` + `\input{auto_numbers_v73.tex}` 추가 |
| `scripts/experiments/generate_unified_auto_numbers.py` | v7.3 pool 추가 + Python 3.8 UTC import 호환 |

### 145 측 패치 (sudo -u anonymous-org 작업)
| 파일 | 변경 |
|---|---|
| 145:`/home/anonymous-org/bench_ws/cga_bench/scripts/experiments/full_v73_runner.py` | nemotron30b config을 `_local.yaml` (BF16) → `.yaml` (FP8)로 sed (백업: `*.bak_<ts>`) |
| 145:`/home/anonymous-org/bench_ws/cga_bench/results/v73_full/nemotron30b/checkpoint.json` | reset (백업: `checkpoint.json.bak_<ts>`) — 마지막 1 r-instance 처리를 위해 |

### 디렉토리 이동
```
results/v73_full → results/v73_full_146_pre_cav_archive   (pre-CAV 7,027 eps 보관)
results/v73_full_145 → results/v73_full                    (post-CAV canonical 11,286 eps)
```

---

## 5. 미해결 / 다음 작업

### P0 (즉시)
1. **144 nemotron endpoint 정리** — GPU 0번에 살아있음 (PID 1951751 등):
   ```bash
   sudo -u anonymous-org ssh [email-redacted] 'sudo pkill -f "vllm serve.*Nemotron"'
   ```

### P1 (paper 준비)
2. **`auto_numbers.tex` macro 활용**:
   - `\vSevenThreeNEpisodes`, `\vSevenThreeMeanCGA`, `\vSevenThreePassCGA` 등을 paper §SGSC v7.3에 인용
   - `\v73AC`, `\v73MAB` 등 cross-pool 비교 표에 활용
3. **CAV before/after ablation** (146 archive 활용):
   - 같은 (scenario, run_idx)의 pre-CAV vs post-CAV 점수 차이 정량화
   - gemma31b는 +0.258 CGA 점프 (앞서 확인됨)
4. **AC=9.5% 격차 paper 분석**:
   - SGSC expected_actions 평균 vs v6 manual 평균 비교
   - Coverage threshold 의존성 plot

### P2 (deferred)
5. **rescore_v6_with_cav.py 실행** — v6 (706 manual) 결과 post-hoc CAV 적용
6. **Phase A/B에 추가된 패치들과 v7.3 매크로 통합 검증**

---

## 6. 핵심 명령 (재현용)

### v7.3 macros 재계산
```bash
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench

# Step 1: verdict matrix
CGA_VERDICT_RESULTS_DIR=results/v73_full \
CGA_VERDICT_OUTPUT_JSON=evidence_pack/analysis/verdict_matrix_v7_3.json \
CGA_VERDICT_OUTPUT_TEX=evidence_pack/tables/verdict_matrix_v7_3.tex \
PYTHONPATH=. python3 scripts/experiments/verdict_matrix_v5.py

# Step 2: v7.3 단독 매크로 (Phase 1 + 2)
PYTHONPATH=. python3 scripts/experiments/generate_v73_auto_numbers.py

# Step 3: cross-pool 통합 매크로 (phaseA/B/v6base/v73)
PYTHONPATH=. python3 scripts/experiments/generate_unified_auto_numbers.py
```

### 머지 검증
```bash
ls results/v73_full/                       # canonical (post-CAV)
ls results/v73_full_146_pre_cav_archive/   # pre-CAV 보관
for d in results/v73_full/*/; do n=$(basename "$d"); [ "$n" = "_logs" ] && continue; \
  echo "$n: $(ls "$d"/*.json 2>/dev/null | grep -v checkpoint | grep -v model_summary | wc -l)"; done
# 9 models × 1,254 = 11,286 expected (with possible older duplicate files for some models)
```

### Endpoint 헬스체크
```bash
# 144 nemotron (정리 권장)
curl -s -m 5 -H "Authorization: Bearer sk-no-key-required" http://localhost:8013/v1/models | head -c 200

# 145 endpoint들 (idle 상태)
for p in 30210 30211 30213 30216; do
  curl -s -m 3 -H "Authorization: Bearer sk-no-key-required" http://localhost:8013$p/v1/models \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['data'][0]['id'])" 2>/dev/null \
    || echo "$p DOWN"
done
```

---

## 7. 인프라 현 상태

### 144 (H200x8, anonymous-user)
- GPU 0: nemotron 30220 (PID 1951751, 정리 필요)
- GPU 1-7: idle
- nemotron config: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8`, TP=1, max-num-seqs=8, --enforce-eager, --trust-remote-code

### 145 (A100x8, anonymous-org)
- 8장 모두 메모리 점유 (oss120b TP=2 / qwen35b ×2 TP=1 / Llama-Scout TP=4)
- 모두 0% util (작업 종료 후 idle)
- 코드: `/home/anonymous-org/bench_ws/cga_bench/`
- canonical 결과: `/home/anonymous-org/bench_ws/cga_bench/results/v73_full/`

### 146 (localhost, local)
- Claude Code 실행 위치
- vLLM endpoint 없음
- canonical 결과: `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/v73_full/` (145에서 rsync)

---

## 8. 빠른 복귀 체크리스트

```bash
# 1. v7.3 본런 완주 확인
ls /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/v73_full/ | grep -v _archive | grep -v _logs
# Should show: 9 model dirs (deepseek_r1_7b, gemma31b, llama4scout, nemotron30b, oss120b, qwen27b, qwen35b, qwen397b, qwen4b)

# 2. macro 파일 존재 확인
ls /home/anonymous-org/anonymous-project/AnonProject/cga_bench/paper/auto_numbers_v73*.tex
# auto_numbers_v73_full.tex + auto_numbers_v73.tex

# 3. verdict matrix 확인
ls /home/anonymous-org/anonymous-project/AnonProject/cga_bench/evidence_pack/analysis/verdict_matrix_v7_3.json

# 4. 분석 보고서 위치
ls /home/anonymous-org/anonymous-project/AnonProject/cga_bench/docs/260502_*.md
```
