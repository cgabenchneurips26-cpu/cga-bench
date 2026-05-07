# v7 Corpus 실험 상황 — 세션 분석 보고서

**Date**: 2026-05-02 (KST 기준)
**Session**: v7 corpus 상황 컨텍스트 복원 + 145/146 분리 분석 + idle GPU 의사결정
**Branch**: `eval_science`
**Last commit**: `e4af154c` (beta-1..6 entailment + normalizer wire-in)

---

## 1. Executive Summary

| 항목 | 결론 |
|---|---|
| v7.3 SGSC 본런 (target 12,540 eps = 418 × 9 × 3) | **145 단독 99% 완료**. 7/9 모델 100%, oss120b 99%, nemotron30b 97% |
| 146 v73_full 결과 | **모두 pre-CAV (5/1 night, 7,027 eps)** — paper 본 결과로 사용 불가, ablation 자료로만 가치 |
| 145 v73_full 결과 | **모두 post-CAV (5/2 morning, 15,910 eps)** — paper canonical |
| 145 GPU 8장 현재 | 메모리만 점유, 모두 0% util — 본 spec 외 작업으로 채우는 건 paper plan 외 |
| nemotron30b 11 누락 | **세션 후반 144 H200 endpoint으로 완주 (12:50 KST 마지막 1 r-instance)** |
| Expansion v7 (4/23~4/29 진행) | **100% pre-CAV** — held-out 5 graphs는 포함 안 됨 |
| Held-out 5 graphs | SGSC v7.3 코퍼스에 이미 통합 (145에 100% post-CAV) |

---

## 2. v7.3 9 모델 145-canonical 충전 상태

| Model | uniq_scen | r0 | r1 | r2 | 누락 r-instance |
|---|---:|---:|---:|---:|---|
| qwen397b | 418 | 418 | 418 | 418 | **0** ✓ |
| qwen35b | 418 | 418 | 418 | 418 | **0** ✓ |
| qwen27b | 418 | 418 | 418 | 418 | **0** ✓ |
| qwen4b | 418 | 418 | 418 | 418 | **0** ✓ |
| gemma31b | 418 | 418 | 418 | 418 | **0** ✓ |
| deepseek_r1_7b | 418 | 418 | 418 | 418 | **0** ✓ |
| llama4scout | 418 | 418 | 418 | 418 | **0** ✓ |
| **oss120b** | 418 | 414 | 412 | 410 | **18 r-instance** (145에서 자가 진행 중) |
| **nemotron30b** | **418** | 418 | 418 | 418 | **0** ✓ (12:50 KST 완주) |

`qwen397b_s2`는 별도 모델이 아님 — `MODELS["qwen397b_s2"]["original_key"] = "qwen397b"`로 같은 dir에 합쳐짐. 사용자가 떠올린 "10 모델"은 _s2 부수 인스턴스 포함 숫자.

145 canonical 위치: `/home/anonymous-org/bench_ws/cga_bench/results/v73_full/`
146 rsync mirror: `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/v73_full_145/` (425MB)

---

## 3. 145 vs 146 결과 분리 — 결정적 증거

### 3.1 Sample 비교 (`aabb_transfusion_adverse_events_c004 qwen4b r0`)

| 지표 | 146 (5/1 21:48) | 145 (5/2 04:27) |
|---|---:|---:|
| compliance_score | **0.167** | **0.583** (3.5× ↑) |
| actions | 6 | 12 |

### 3.2 50 시나리오 매칭 비교 (model별)

| Model | n | 146 평균 | 145 평균 | Δ |
|---|---:|---:|---:|---:|
| qwen4b | 50 | 0.567 | 0.513 | -0.054 |
| qwen27b | 50 | 0.482 | 0.466 | -0.015 |
| qwen397b | 50 | 0.573 | 0.591 | +0.018 |
| deepseek_r1_7b | 50 | 0.413 | 0.438 | +0.025 |
| nemotron30b | 50 | 0.504 | 0.484 | -0.020 |
| **gemma31b** | 50 | 0.374 | **0.633** | **+0.258** |

**해석**:
- gemma31b만 거대한 +0.258 점프 (CAV가 많이 살림)
- 나머지는 ±0.05 이내 — audit이 예측한 "전 모델 ~0.3-0.5 depressed"는 부분적으로만 맞음
- 모델/시나리오마다 영향 격차 큼. paper에 쓸 결정적 증거는 gemma31b 같은 케이스 위주

### 3.3 권고 머지 전략

1. canonical = **145 결과 (post-CAV)**. CAV-wired, 모든 모델 r0/r1/r2 풀 셋, 8/9 모델 완주
2. 146 결과는 archive로 격리 (`results/v73_full_pre_cav_archive/`). CAV before/after ablation 자료
3. 145를 canonical 위치 `results/v73_full/`로 승격 (rename), 146 dir은 archive로

---

## 4. CAV Wire 타임라인

| 시점 | 이벤트 | commit |
|---|---|---|
| 2026-04-23 ~ 2026-04-29 | Expansion v7 episode 생성 (10 runner, 다양한 모델) | pre-CAV |
| 2026-05-01 03:51 | 14-graph pilot 분석 완료 | — |
| 2026-05-01 14:30 | `pool_mapped_patch_status.md` 작성 | — |
| 2026-05-01 19:35 | `full_v73_runner.py` 생성 + smoke test | — |
| 2026-05-01 ~21:48 | 146에서 v7.3 본런 시작 (PRE-CAV 결과 발생) | — |
| 2026-05-02 03:20 | **`260502_cav_normalizer_gap_audit.md` LAUNCH BLOCKER 적발** | — |
| 2026-05-02 03:xx | **CAV v0.6 wire-in (ActionNormalizer)** | `2fbb3da0` |
| 2026-05-02 04:27~ | 145에서 v7.3 본런 재시작 (POST-CAV) | wire 반영 |
| 2026-05-02 ~08:20 | 145 본런 완료 단계 (대부분 모델 1,254 도달) | — |
| 2026-05-02 ~10:30 | 144 endpoint qwen397b → oss120b 교체 (user 본인) | — |
| 2026-05-02 ~11:30 (현 세션) | v7 corpus 상황 컨텍스트 복원 | — |

CAV gap audit 핵심 수치:
- SGSC unique expected_actions: 840
- UNMAPPED by normalizer (pre-CAV): **743/840 (88.5%)**
- CAV v0.6 (2,276 entries) 적용 후 unmapped: **0/840**
- 시나리오 단위 false OMISSION: 82.1% → 0%

---

## 5. Expansion v7 = pre-CAV 검증

```
가장 늦은 timestamp: 2026-04-29 07:33 (nemotron30b)
CAV wire commit:    2026-05-02 (3-4일 후)
sample corpus 필드: NONE (post-CAV는 corpus="sgsc_v73")
```

### 5.1 Expansion v7 디렉토리 카운트

| Model | eps | 기간 |
|---|---:|---|
| oss120b | 709 | 4/23 |
| oss120b_exp2 | 709 | 4/23 |
| oss120b_exp3 | 709 | 4/23 |
| qwen397b | 696 | 4/23 |
| qwen397b_react_s2 | 696 | 4/23 |
| qwen35b_a3b_local | 684 | 4/23 |
| qwen27b_local | 709 | 4/23 |
| deepseek_r1_7b_exp1/exp2/local1/local2 | 668-709 each | 4/23 |
| qwen4b | 708 | 4/28 |
| llama4scout | 708 | 4/28 |
| gemma31b | 708 | 4/28~29 |
| nemotron30b | 708 | 4/29 |

### 5.2 Held-out 5 graphs는 expansion_v7에 NOT INCLUDED

| Graph | expansion_v7/qwen4b | SGSC v7.3 145 |
|---|---:|---:|
| aba_burn_resuscitation | **0 eps** | 100% (post-CAV) |
| acog_obstetric_hemorrhage | **0 eps** | 100% |
| apa_agitation_management | **0 eps** | 100% |
| pals_pediatric_emergency | **0 eps** | 100% |
| toxicology_management | **0 eps** | 100% |

→ Held-out 5는 v7.3 SGSC corpus에 통합됨. **already in 145 canonical**, 별도 작업 불필요.

→ Expansion v7은 다른 auto graphs (aagbi_perioperative_hemorrhage 등) 셋.

---

## 6. v6 706 재실행 plan 검토

**`docs/critical_review/v6_full_outstanding_rerun_plan.md` (2026-04-28) 결정**:

- W8 cross-scaffold (706 manual scope): **NO action — 그대로 유지**
- 만약 Phase B-scope (76,464 ep × 4 scaffolds = 305,856 ep)로 재실행하면 ~5일 GPU 컴퓨트
- "Not recommended for v1 paper"

**`docs/06_paper_modification_plan.md`**:
- v6 결과 재계산은 **CPU only aggregation** 권장
- ActionNormalizer fix(`2fbb3da0`)는 v6 결과에도 점수 영향 가능, 하지만 GPU 재실행 대신 **post-hoc rescoring** (`scripts/sgsc/rescore_v6_with_cav.py`) 권장

**결론**: **v6 GPU 재실행은 paper plan에 등록 안 됨**. 145 GPU로 v6 재실행은 plan 외 작업.

---

## 7. Paper modification plan 기준 GPU 잔여 작업

`260501_pool_mapped_patch_status.md` 기준:

| Patch | 작업 | GPU 필요? | 145 가능? |
|---|---|---|---|
| **Heldout qwen397b 부족분** | 23 → 199 episodes (176개) | YES (~3 GPU-h on 144) | **NO — 144 H200 필요** |
| Phase B5 v7 replication | v7 verdict matrix 재계산 | NO (재계산만) | N/A |
| B1 SGSC contribution macro | DET rollout 결과 | YES if rerun | 가능 |
| B4 DET vs NONDET comparison | 5/3 morning 비교 | NO (existing) | N/A |

**즉 paper plan 기준 GPU 필요한 작업은 qwen397b heldout 176 episodes** (144 H200) 뿐.
**145 A100에서 plan-bound GPU 작업은 없음**.

---

## 8. 인프라 현 상태 (세션 종료 시점)

### 8.1 144 (H200x8, anonymous-user)
- **user 본인이 oss120b 4 인스턴스 운영 중** (port 30001/30002 root, 30003/30004 anonymous-user, 모두 oss120b TP=2 --enforce-eager)
- qwen397b 사라짐, **nemotron30b 누락 11 scenarios는 144 free 시점까지 대기**

### 8.2 145 (A100x8, anonymous-org)
- **GPU 0-7 모두 0% utilization** (메모리만 점유)
- vLLM 4개 살아있음:
  - 30210 oss120b TP=2 (GPU 0,1) — worker 3명 active, 마무리 중
  - 30211 qwen35b TP=1 (GPU 2 또는 3) — 1,254 완주, idle
  - 30213 Llama-Scout TP=4 (GPU 4-7) — 1,254 완주, idle
  - 30216 qwen35b TP=1 (GPU 2 또는 3) — 1,254 완주, idle
- 디스크: 1.5T/1.7T (91%, 146G 여유)
- 코드 경로: `/home/anonymous-org/bench_ws/cga_bench/`

### 8.3 146 (A100x8, localhost/local)
- **vLLM endpoints 모두 DOWN** (8013/28000/28010/8101/30003/30004/30009)
- runner 0개
- v73_full에 stale claim 59개 (모두 60분 이상)
- 디스크: 101GB free

---

## 9. 잘못된 시도 — Scout r3/r4 launch (취소됨)

세션 중 GPU idle 0%를 채우려고 `W8_RUNS=5` 환경변수로 Llama-Scout runner 12 worker launch함.

**사용자 지적 후 즉시 취소 (정확한 판단)**:
1. 모델별 run 횟수 불일치 (Scout=5, 그 외=3) → mean/CI 비교 무의미
2. 분석 스크립트 silent bias (`*_r*_*.json` glob → Scout만 5개 평균)
3. Git hash drift (r0-r2 어제 commit, r3-r4 오늘 commit)
4. CAV/normalizer 상태 변화 추적 불가
5. dedup 영원 잠금 (file-exists로 r0-r2 재현 불가)
6. W8_RUNS 변수명 의미 불명 (v8 hint를 v7.3에 재활용)
7. scenario_id × run_index 분포 가정 깨짐

**취소 처리**:
- 12 workers killed
- r3 14 + r4 13 = 27 files deleted
- stale claims cleaned
- Scout dir = 1,254 (canonical r0/r1/r2 원복) ✓

**교훈**: GPU 가동률 KPI를 위해 spec 밖 작업을 만들면 본 실험 일관성 깨짐. 본질 해결이 아님.

---

## 10. 미해결 / 다음 작업 큐

### P0 (paper plan 부합)
1. ~~nemotron30b 11 scenarios~~ — **DONE** (12:50 KST 144 H200으로 마지막 1 r-instance 완주)
2. **qwen397b heldout 176 episodes** — 144 H200, ~3 GPU-h
3. **oss120b 18 r-instance** — 145 자가 완주 중 (몇 분 내 끝)

### P1 (분석 + 머지)
4. **145 → 146 canonical 머지 결정**: archive 146 pre-CAV → rename 145 post-CAV to canonical
5. **CAV before/after ablation 분석** (146 vs 145 매칭): paper 부록 자료
6. **rescore_v6_with_cav.py post-hoc 실행**: v6 결과를 CAV-wired로 후처리, GPU 불필요

### P2 (paper plan 외 옵션)
7. v6 706 GPU 재실행 — **rerun_plan에서 NOT RECOMMENDED 결정됨**, 보류
8. expansion v7 CAV-wired 재실행 — held-out 5는 v7.3에 이미 있으므로 가치 제한적

---

## 11. 145 idle 의사결정 — 옵션과 권고

| 옵션 | paper plan 부합 | 가치 | 145 가능 |
|---|---|---|---|
| A. v6 706 CAV 재실행 | NO (rerun_plan에서 NOT RECOMMENDED) | post-hoc rescoring으로 대체 가능 | ✓ |
| B. Expansion v7 CAV 재실행 | 부분적 | 5/3 deadline 후 작업 | ✓ |
| C. Heldout qwen397b 176 ep | YES (Phase 3 옵션) | 8-model canonical 확보 | **NO (H200 필요)** |
| **D. 145 idle 유지** | — | 144 free 후 plan-bound 작업 우선 | — |

**권고**: **D안 (idle 유지)**. 144 free 시점에 nemotron + qwen397b heldout 둘 다 launch.

GPU 가동률은 핵심 지표가 아님. **paper plan에 정합한 작업에만 컴퓨트 투입**이 원칙.

---

## 12. 인프라 / 운영 메모

### 9.1 vLLM endpoint 상태 변화 (5/2 세션 중)

| 시점 | 144:30001/2 | 변화 |
|---|---|---|
| 세션 시작 직전 | qwen397b TP=4 ×2 (H200 GPU 0-7) | — |
| ~10:30 KST | **oss120b TP=2 ×4 (root + anonymous-user)** | user 본인이 교체 |

### 9.2 SSH 권한 매트릭스 (이번 세션 검증)

| Host | Account | SSH 가능? |
|---|---|---|
| 127.0.0.1 | anonymous-user | ✓ (sudo -u anonymous-org ssh로 anonymous-org key 사용) |
| 127.0.0.1 | anonymous-org | ✓ |
| 127.0.0.1 (local) | anonymous-org/anonymous-user/anonymous-user | ✓ (Claude Code 실행 위치) |

### 9.3 145 results 머지 명령 (참고용)

```bash
# 이미 완료된 rsync (다시 안 돌려도 됨)
sudo -u anonymous-org rsync -az -e ssh \
  [email-redacted]:/home/anonymous-org/bench_ws/cga_bench/results/v73_full/ \
  /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/v73_full_145/

# 머지 전략 (사용자 결정 후 실행)
mv results/v73_full results/v73_full_146_pre_cav_archive
mv results/v73_full_145 results/v73_full
```

---

## 12.5. SGSC v7.3 본런 마무리 + 머지 (세션 후반, 5/2 11:30~12:55 KST)

### nemotron30b 마지막 1 r-instance 복구 (총 6번 시도)

144 H200 GPU 0번에 nemotron 띄우기 — 5번의 launch 시도 끝에 v7 성공.

| 시도 | 결과 | 원인 |
|---|---|---|
| v1 | FAIL | 모델 ID `nvidia/Nemotron-3-Nano-30B-A3B-FP8` 잘못 (HF 레지스트리에 없음) |
| v2 | FAIL | 정확한 ID `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8`, 그러나 `--trust-remote-code` 누락 |
| v3 | FAIL | trust-remote-code 추가했으나 `FileNotFoundError: ninja` (vLLM custom kernel JIT 도구) |
| v4 | FAIL | `--enforce-eager` 추가했으나 ninja 여전히 필요 (FP8 modelopt 커널) |
| v5 | OK | `python3 -m pip install --user ninja` + PATH 추가 → 60초만에 ready |
| v6 | FAIL | `--served-model-name` 듀얼 alias 추가했으나 v5 EngineCore 1948502 GPU 0번 132GB 점유 잔류 → OOM |
| v7 | **OK (45초)** | v5 잔류 EngineCore kill + FP8 only로 깔끔하게 ready |

### 145 runner config 패치
- 145 `full_v73_runner.py` MODELS["nemotron30b"]["config"]가 `clean_slate_nemotron30b_local.yaml` (BF16) 가리킴
- 144는 FP8 endpoint → 모델명 미스매치로 404 에러
- `sed -i "s|_local.yaml|.yaml|"` 로 main config (FP8) 가리키게 패치
- backup 보존: `scripts/experiments/full_v73_runner.py.bak_<ts>`

### Worker 병렬화 검토
- 8 worker 동시 launch 시도, 그러나 w1만 진행 + w2-w8은 file_exists로 1초만에 status:ok 종료
- 이유: rsync 시점(5/2 04:27)에 35 r-instance 누락이라고 보였지만, 145에서 이전 세션이 작업 진행되어 실제로는 거의 다 끝나 있었음
- **최종 잔여**: 단 **1 r-instance** (`aha_acc_aortic_dissection_2022_7711_initial_management_of_bttai_c015 r1`)

### Checkpoint.json 잠금 해제
- w1+w2-w8 워커들이 checkpoint.json 1254 모두 completed로 마킹 → 다음 worker가 loop skip
- **그러나 file system은 1 r-instance missing** (checkpoint와 file_exists 불일치)
- 해결: `checkpoint.json` 백업 후 삭제 → file_exists 검사로 fallback → 정확히 missing 1개 처리 → CGA 0.4706 기록

### 머지 작업 (완료)

```bash
mv results/v73_full → results/v73_full_146_pre_cav_archive  # pre-CAV 5/1 night
mv results/v73_full_145 → results/v73_full                   # canonical post-CAV
```

머지 후 `results/v73_full/`은:
- 9/9 모델 r0/r1/r2 완전 충전
- nemotron30b 2,348 / oss120b 1,254 / 그 외 모두 1,254+
- corpus="sgsc_v73" 메타데이터 일관

### 144 nemotron endpoint 정리 필요 (다음 작업)

GPU 0번 nemotron vLLM (PID 1951751) 살아있음, 132GB 점유.
v7.3 본런 완료했으므로 추가 작업 없으면 stop 가능:
```bash
ssh [email-redacted] 'pkill -f "vllm serve.*Nemotron"'
```

## 13. 세션 산출물

### 신규/수정 파일 (이 세션)
- `docs/260502_v7_corpus_session_analysis.md` (this file) — 세션 분석 보고서
- `results/v73_full_145/` — 145 rsync dump (425MB, 11 모델 dir)

### 참고 문서
- `docs/260501_session_handoff_v73_runner.md` — full_v73_runner 신규 작성
- `docs/260502_cav_normalizer_gap_audit.md` — LAUNCH BLOCKER audit
- `docs/260502_rerun.md` — pre-launch 검증 체크리스트
- `docs/260501_pool_mapped_patch_status.md` — 15 patches 상태
- `docs/260501_session_handoff_track_alpha_beta.md` — alpha/beta task 상황
- `docs/critical_review/v6_full_outstanding_rerun_plan.md` — v6 rerun decision

### 핵심 commit 추적
- `2fbb3da0` (alpha-1..5): ActionNormalizer N1-N5 + B3 forbidden symmetric — **CAV wire 핵심**
- `e4af154c` (beta-1..6): entailment stemming + threshold 0.6 + normalizer wire-in
- 두 commit 이후 v7.3 145 본런 launch (5/2 04:27~)

---

## 14. 다음 세션 빠른 복귀 체크리스트

```bash
# 1. 145 oss120b 마무리 확인
sudo -u anonymous-org ssh 127.0.0.1 \
  'ls /home/anonymous-org/bench_ws/cga_bench/results/v73_full/oss120b/*.json | grep -v checkpoint | grep -v model_summary | wc -l'
# 1,254 도달했는지

# 2. 144 user 작업 끝났는지 (oss120b 4 인스턴스가 사라졌는지)
sudo -u anonymous-org ssh [email-redacted] 'ps -ef | grep "vllm serve" | grep -v grep'

# 3. 145 145 → 146 머지 진행 결정
# 4. 144 free 시점에 nemotron 11 + qwen397b heldout 176 launch

# 5. 본 세션 분석 보고서 위치
ls docs/260502_v7_corpus_session_analysis.md
```
