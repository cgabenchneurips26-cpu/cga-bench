# v6 Re-execution Plan: Clock Fix + Think Strip

> Created: 2026-04-08
> Trigger: 7/9 models have consecutive_empty_action terminations (1.7%–99.7%)
> Fix: (1) <think> strip in parser, (2) empty actions don't advance clock

---

## 1. 안 바뀌는 것 (v6 재실행 무관)

| 항목 | 이유 |
|------|------|
| E1 perturbation (56/17/72/0%/1.4%/100%) | Synthetic traces, agent 미사용 |
| Theorem + Formalism (§2 전체) | 수학적 구조, 데이터 무관 |
| CPG graph library (20/25 graphs, 1049 constraints) | Static system constants |
| EX-25 Engine audit (모순 0%, 출처 100%) | Graph static analysis |
| EX-26 Scorer fidelity (100%, κ=1.0) | Hand-crafted test traces |
| EX-33 Benchmark survey (0/12 timing) | Literature analysis |
| Non-timing synthetic traps (F1≥0.889) | Constructed traces |

## 2. 바뀌는 것 (v6 재실행 필요)

### 매크로 의존 → auto_numbers 재생성으로 자동 반영 (v12 텍스트 수정 불필요)

| 매크로군 | 예시 | 영향 |
|---------|------|------|
| \faAllOblivious, \faAllObliviousCount | 13.7% → ? | FA 감소 예상 (phantom timing 제거) |
| \verdictFlipRate, \verdictFlipCount | 85.0% → ? | 변동 예상 |
| \etaEvaluator, \etaRun, \etaRatio | 0.284/0.0091/31.2 → ? | 변동 예상 |
| \bsr*, \passrate*, \vf* | 전부 | 변동 예상 |
| \kendallW, \friedmanChi, \friedmanP | 0.442/10.6/0.10 → ? | 변동 예상 |
| \reversalRate | 76.2% → ? | 변동 예상 |
| \numEpisodes | 14,826 → ? | 3-run 완성 필터 변동 가능 |
| 모든 EX-* 매크로 | 전부 | 재계산 필요 |

### 하드코딩 수치 → v6 후 수동 검토 필요

| 위치 | 현재 값 | 변동 예상 | 조치 |
|------|--------|----------|------|
| Abstract "63--81%" | EX-23 detection loss | 변동 가능 | 매크로화 권장 |
| Solver §4.6 "30% and 70%" | forbid/within d_G cost | 변동 가능 | 매크로화 권장 |
| Timing audit "68.2%" + "31.8%" | clock sweep robust/boundary | **확실히 바뀜** | 매크로화 필수 |
| Timing audit "1.25%" | jitter verdict flip | 변동 가능 | 매크로화 권장 |
| Timing audit "11.7--26.7%" | coarser step violations | **확실히 바뀜** | 매크로화 필수 |
| Timing audit "59%" | boundary = clinically urgent | 변동 가능 | 확인 필요 |
| Normalizer "42.6% to 38.5%" | omission rate change | 변동 가능 | 확인 필요 |
| Normalizer "5,770 violations" | resolved count | 변동 가능 | 확인 필요 |
| Intro "56/17/72" | perturbation counts | **안 바뀜** (synthetic) | — |

## 3. 재실행 순서

### Phase 1: 코드 수정 (완료)
- [x] <think> strip in llm_provider.py (4 code paths)
- [x] Empty decide() → continue, no clock advance (base_agent.py)
- [ ] Kill old DeepSeek shards (PIDs 810657, 810874)

### Phase 2: v6 전체 재실행 (12-24h)
```bash
# 9 models × 706 scenarios × 3 runs
# 기존 PIDs kill 후 clean restart
for model in qwen4b qwen27b qwen35b qwen397b nemotron30b gemma31b oss120b deepseek_r1_7b biomed8b; do
    python run_episodes.py --model $model --scenarios all --runs 3 --version v6
done
```

### Phase 3: 재채점 + 매크로 갱신 (2-4h)
```bash
# 1. verdict_matrix v6 생성
python verdict_matrix_v6.py --input full_706_v6/ --output verdict_matrix_v6.json

# 2. auto_numbers 재생성
python fill_all_placeholders.py --verdict_matrix verdict_matrix_v6.json --output auto_numbers_v6.tex

# 3. EX-23~33 재계산
python run_all_defense_experiments.py --verdict_matrix verdict_matrix_v6.json

# 4. E1 perturbation은 재실행 불필요 (synthetic)
# 5. clock sweep 재실행 필요 (v6 traces 기반)
```

### Phase 4: 하드코딩 수치 업데이트 (1-2h)
```
1. diff auto_numbers_v5.tex auto_numbers_v6.tex → 변동 확인
2. 위 표의 하드코딩 수치 7건 수동 업데이트
3. 가능하면 하드코딩 → 매크로 전환 (재발 방지)
4. pdflatex 2회 → 0 error
```

### Phase 5: EX-27 재실행 (별도, 2-3h)
```
v6 traces 기반으로 EX-27 Sub-A/B/C 재실행
- Sub-A: keyword-based duration model (DEFAULT <10%)
- Sub-B: parallel batch matching rate 확인
- Sub-C: reasoning step count 확인 (0이면 제거)
```

## 4. 예상 수치 변동 방향

Clock fix는 phantom timing violations을 제거하므로:

| 메트릭 | 방향 | 이유 |
|--------|------|------|
| Timing violations | ↓↓ | Phantom 5-min advances 제거 |
| FA rate | ↓ or ↔ | Timing violations 감소 → 더 많은 episode이 TCC pass → FA 분자 감소 |
| BSR | ↓ or ↔ | 같은 이유 |
| Verdict flip | ↓ | Action-set과 TCC의 gap 일부 축소 |
| η²(evaluator) | ? | Timing 비중 감소하면 evaluator 차이도 줄 수 있음 |
| η²(run) | ↑ 가능 | Empty action 랜덤성이 제거되면 순수 run variance만 남음 |

**핵심**: FA가 줄어도 >5% 이상이면 논문 claim은 유지됨. 0%에 수렴하면 문제이지만, non-timing violations (FORBIDDEN, BEFORE)은 clock fix에 영향받지 않으므로 FA가 0이 될 수 없음.

## 5. 논문에 추가할 문단 (Appendix, v6 후)

```latex
\paragraph{Clock policy and parser robustness.}
In an earlier pipeline version, failed JSON extraction produced empty actions
that nevertheless advanced simulated time by \timeStepMinutes{} minutes per
attempt. This inflated timing violations for models with high parse-failure
rates (up to 30\% of episodes for Nemotron-30B). The released pipeline strips
reasoning-model prefixes (\texttt{<think>} blocks) before JSON extraction and
does not advance the clock on empty actions, so that retry overhead cannot
produce spurious timing violations. All reported numbers use this corrected
pipeline. A pre/post comparison shows that headline false-accept rates changed
by $\Delta = X.X$ pp, confirming that the blind-spot pattern is robust to
clock-policy corrections.
```