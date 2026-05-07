# CGA-Bench 방어 실험 실행 가이드 (v11 기준)

> Claude Code 세션에서 순차 실행. 각 실험 완료 후 auto_numbers.tex 갱신 + 논문 반영.
> 기준 데이터: results/full_706_final/ (14,055 episodes, 3-run filtered)
> 마감: Abstract 5/4, Full paper 5/6

---

## 실험 0: 사전 준비 (5분)

### 목적
v11 논문 + appendix를 repo에 반영하고 auto_numbers 수정을 확인한다.

### 실행

```bash
# 1. 논문 파일 교체
cp main_final_v11.tex paper/main_final_v11.tex
cp appendix_v2.tex paper/appendix.tex

# 2. auto_numbers 수정 확인
grep 'numEpisodes' paper/auto_numbers.tex
# 예상: \newcommand{\numEpisodes}{14055}

# 3. 컴파일 테스트
cd paper && pdflatex -interaction=nonstopmode main_final_v11.tex 2>&1 | grep -E "Error|Warning|Undefined"
# Undefined control sequence 있으면 auto_numbers 매크로 누락 → 즉시 수정

# 4. commit
git add paper/
git commit -m "feat(paper): v11 — sharpened prose + all critical fixes + appendix restoration"
```

---

## 실험 2: EX-14 Reproducibility Pack (8h)

### 방어 대상
공격 #6 "Code/data availability E&D 규정 미충족" — Desk-reject 사유

### 산출물
```
reproduce/
  Makefile              — make reproduce 한 줄로 전체 재현
  Dockerfile            — 환경 고정 (Python 3.11, vLLM, 종속성)
  REPRODUCE.md          — 단계별 재현 가이드
  configs/              — 모든 실험의 pre-registered config YAML
  croissant.json        — Croissant metadata (NeurIPS E&D 필수)
  guideline_cards/      — 25개 graph별 Guideline Card markdown
```

### 실행 순서

```bash
# Phase 1: Dockerfile (1h)
# Python 3.11 + vLLM + torch + 종속성 고정
cat > reproduce/Dockerfile << 'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["make", "-C", "reproduce"]
EOF

# Phase 2: Makefile (2h)
# 타겟: data, episodes, score, experiments, paper
cat > reproduce/Makefile << 'EOF'
.PHONY: all data episodes score experiments paper

all: data episodes score experiments paper

data:
	python cpg_model/constraint_derivation.py --output results/constraints/
	python cpg_model/patient_generator.py --output results/scenarios/

episodes:
	@echo "Episodes require GPU. See REPRODUCE.md for instructions."
	@echo "Pre-computed episodes available at [anonymized URL]."

score:
	python scripts/verdict_matrix_v5.py \
		--episodes results/full_706_final/ \
		--output evidence_pack/verdict_matrix_v4.json

experiments:
	python scripts/experiments/exp_e1_verdict_flip.py
	python scripts/experiments/exp_e2_bsr.py
	python scripts/experiments/exp_e3_instrumentation_ablation.py
	python scripts/experiments/exp_e4_operating_point.py
	python scripts/experiments/exp_e5_evaluator_expansion.py
	python scripts/experiments/exp_e18_artifact_mimic.py

paper:
	python scripts/experiments/extract_auto_numbers.py
	cd paper && pdflatex main_final_v11.tex
EOF

# Phase 3: REPRODUCE.md (1h)
# 환경 요구사항, 데이터 다운로드, 단계별 실행, 예상 시간

# Phase 4: Croissant metadata (1h)
# https://github.com/mlcommons/croissant 형식
python -c "
import json
croissant = {
    '@context': {'@vocab': 'http://schema.org/', 'cr': 'http://mlcommons.org/croissant/'},
    '@type': 'cr:Dataset',
    'name': 'CGA-Bench',
    'description': 'Trace-level conformance auditing benchmark for clinical AI agents',
    'license': 'MIT',
    'distribution': [
        {'@type': 'cr:FileSet', 'name': 'cpg_graphs', 'description': '25 CPG YAML graphs'},
        {'@type': 'cr:FileSet', 'name': 'scenarios', 'description': '706 evaluation scenarios'},
        {'@type': 'cr:FileSet', 'name': 'episodes', 'description': '14,055 agent episodes (3-run filtered)'},
    ]
}
with open('reproduce/croissant.json', 'w') as f:
    json.dump(croissant, f, indent=2)
"

# Phase 5: Guideline Cards (2h)
# 25개 graph별 카드 생성
python scripts/generate_guideline_cards.py \
    --graphs cpg_model/graphs/ \
    --output reproduce/guideline_cards/

# Phase 6: Pre-registered configs (1h)
# 각 실험의 하이퍼파라미터를 YAML로 고정
for exp in e1 e2 e3 e4 e5 e6 e7 e8 ex1 ex14 ex15 ex16 ex17 ex18 ex20; do
    cp scripts/experiments/config_${exp}.yaml reproduce/configs/ 2>/dev/null || \
    echo "# Config for ${exp} — parameters extracted from script" > reproduce/configs/${exp}.yaml
done
```

### 논문 반영 위치
- `Code and data availability` 문단 (Conclusion 뒤): 이미 Makefile/Dockerfile/Croissant 언급 있음
- Guideline Cards: Appendix~\ref{app:guideline_cards}에서 "Full cards... included in supplementary materials" → 실제 파일 존재 확인

### 완료 기준
- [ ] `docker build -t cga-bench .` 성공
- [ ] `make data` → constraints + scenarios 재생성
- [ ] `make score` → verdict_matrix_v4.json 재생성
- [ ] `make experiments` → evidence_pack/ 갱신
- [ ] croissant.json 유효성 검증
- [ ] 25개 Guideline Card 생성

---

## 실험 3: EX-17 Solver Agreement (2h)

### 방어 대상
공격 #4 "Solver exact/tiered conflation" — v11에서 ILP primary/tiered upper bound로 분리했으나,
현재 ρ=0.965는 108 에피소드 기준. 14,055ep 전수로 갱신하면 방어 강화.

### 실행

```bash
# 두 solver를 전체 에피소드에서 병렬 실행
python scripts/experiments/exp_e17_solver_agreement.py \
    --episodes results/full_706_final/ \
    --canonical-set evidence_pack/verdict_matrix_v4.json \
    --output evidence_pack/ex17_solver_agreement/

# 스크립트가 없으면 아래 로직으로 작성:
# 1. verdict_matrix_v4.json에서 14,055 episode ID 로드
# 2. 각 episode에 대해:
#    a. tiered solver 실행 → d_G_tiered, violations_tiered
#    b. ILP solver 실행 → d_G_ilp, violations_ilp
# 3. 비교 통계:
#    - Spearman ρ (d_G ranking)
#    - ILP가 lower cost인 비율 (%)
#    - Equal cost 비율 (%)
#    - Tiered가 lower cost인 비율 (%) — 이론적으로 0이어야 하나 edge case 있음
#    - Scatter plot: d_G_tiered vs d_G_ilp
```

### auto_numbers 갱신

```latex
% 기존 (108 episodes 기준):
\newcommand{\solverILPRho}{0.965}
\newcommand{\solverILPPct}{30.6}
\newcommand{\solverSubsetN}{108}

% 갱신 후 (14,055 episodes 기준):
\newcommand{\solverILPRho}{<새 값>}
\newcommand{\solverILPPct}{<새 값>}
\newcommand{\solverSubsetN}{14055}
```

### 논문 반영 위치
- Section 4.6 (Solver): "the two solvers agree on ρ = \solverILPRho{} of episode rankings"
- Appendix Additional Limitations: "\solverSubsetN{} episodes where both solvers run"

### 완료 기준
- [ ] 14,055 에피소드 전수 실행
- [ ] Spearman ρ > 0.95 (기존 0.965와 유사 기대)
- [ ] auto_numbers 3개 매크로 갱신
- [ ] scatter plot 생성 (appendix figure 후보)

---

## 실험 4: EX-20 No-Context Matched Pair (2h)

### 방어 대상
공격 #16 "FORBIDDEN/SEQUENCE under-activated — Theorem Case 4 (π_nctx) 실험적 증거 부재"

### 원리
Theorem Case 4: context-free projection은 conditional FORBIDDEN을 놓친다.
구체적으로: 동일한 trace τ가 allergy 없는 환자에게는 conformant, allergy 있는 환자에게는 nonconformant.
Action set이 동일하고 timestamp도 동일한데 환자 상태만 다른 matched pair.

### 실행

```bash
python scripts/experiments/exp_e20_no_context_pair.py \
    --graphs cpg_model/graphs/ \
    --output evidence_pack/ex20_no_context/

# 스크립트 로직:
# 1. CPG graph에서 conditional FORBIDDEN rules 추출
#    예: "penicillin_allergy == True → FORBIDDEN(amoxicillin)"
# 2. 두 시나리오 생성:
#    a. patient_safe: penicillin_allergy = False
#    b. patient_unsafe: penicillin_allergy = True
# 3. 동일한 trace 구성: [order_blood_cultures, administer_amoxicillin, ...]
# 4. 평가:
#    - π_nctx(τ_safe) = π_nctx(τ_unsafe)  (timestamps + actions 동일)
#    - TCC(τ_safe) = PASS, TCC(τ_unsafe) = FAIL
#    - ASC/PAF/CwT: 환자 상태 무시하므로 둘 다 동일 verdict
# 5. 모든 conditional FORBIDDEN rule에 대해 반복
# 6. 통계: n pairs, detection rate by evaluator
```

### auto_numbers 갱신 (신규)

```latex
\newcommand{\noContextPairs}{<n>}           % matched pair 수
\newcommand{\noContextASCDetect}{0.0}       % ASC detection rate (예상: 0%)
\newcommand{\noContextTCCDetect}{100.0}     % TCC detection rate (예상: 100%)
```

### 논문 반영 위치
Supporting Analyses에 1문단 추가:

> **Conditional-safety witness (Theorem Case 4).**
> To provide a constructive witness for the $\pi_{\text{nctx}}$ case of Theorem~\ref{thm:coarsening}, we generate \noContextPairs{} matched patient pairs sharing identical traces but differing in allergy or contraindication status. In every pair, action-set evaluators assign identical verdicts because they do not condition on patient state; TCC detects the conditional {\sc forbid} violation in all \noContextPairs{} unsafe variants. This confirms that context-free evaluation is structurally blind to conditional safety constraints.

### 완료 기준
- [ ] ≥ 10 matched pairs 생성
- [ ] ASC/PAF/CwT detection = 0% 확인
- [ ] TCC detection = 100% 확인
- [ ] auto_numbers 갱신 + 논문 1문단 추가

---

## 실험 5: EX-4A Clock Sweep (4h)

### 방어 대상
공격 #11 "Timing dominance / timing = clock artifact" — "고정 5분 step이 violation을 만드는 것 아닌가"

### 원리
시뮬레이션 시간 단위를 2, 5, 10, 15, 20분으로 변경하고 TCC verdict가 얼마나 바뀌는지 측정.
만약 5분 step이 artifact라면, step size 변경 시 verdict가 크게 요동해야 한다.
실제로는 대부분의 violation이 margin >> 5분이므로 verdict가 안정적일 것으로 예상.

### 실행

```bash
python scripts/experiments/exp_e4a_clock_sweep.py \
    --episodes results/full_706_final/ \
    --canonical-set evidence_pack/verdict_matrix_v4.json \
    --step-sizes 2,5,10,15,20 \
    --output evidence_pack/ex4a_clock_sweep/

# 스크립트 로직:
# 1. 14,055 에피소드 로드 (3-run filtered)
# 2. 각 step size s에 대해:
#    a. 모든 에피소드의 timestamps를 s-minute 단위로 재계산
#       원래 step i에서의 시간 = i * 5 → 새 시간 = i * s
#    b. TCC 재평가: 새 timestamps으로 WITHIN constraint 체크
#    c. verdict 변경률 계산: |{ep : TCC_s(ep) ≠ TCC_5(ep)}| / 14,055
# 3. 출력:
#    - step_size → verdict_flip_rate table
#    - step_size → mean_margin_change
#    - step_size → newly_passing / newly_failing counts
```

### 예상 결과
```
Step size | TCC pass rate | Verdict change vs 5min
2 min     | ~23%          | ~3-5% (more violations: tighter deadlines)  
5 min     | 25.3%         | baseline
10 min    | ~28%          | ~5-8% (fewer violations: more slack)
15 min    | ~30%          | ~8-12%
20 min    | ~32%          | ~10-15%
```

만약 verdict change가 전 구간에서 < 15%이면 "timing violations are robust to step-size choice"로 결론.

### auto_numbers 갱신 (신규)

```latex
\newcommand{\clockSweepMaxFlip}{<max %>}    % 최대 verdict 변경률
\newcommand{\clockSweepSteps}{5}            % 테스트한 step size 수
```

### 논문 반영 위치
Timing validity audit 문단에 1-2문장 추가:

> As a further robustness check, we re-evaluate all episodes under five alternative time-step sizes (2, 5, 10, 15, 20 minutes). The maximum verdict change relative to the 5-minute baseline is \clockSweepMaxFlip{}\%, confirming that the timing blind spot is not an artifact of the particular step duration.

### 완료 기준
- [ ] 5개 step size 전수 실행
- [ ] verdict change table + 시각화
- [ ] auto_numbers 갱신 + 논문 2문장 추가

---

## 실험 6: Held-out All-Oblivious FA (1h)

### 방어 대상
공격 #18 "Held-out = parsing only — held-out에서도 FA가 높은지 미확인"

### 실행

```bash
python scripts/experiments/exp_heldout_ao_fa.py \
    --episodes results/full_706_final/ \
    --canonical-set evidence_pack/verdict_matrix_v4.json \
    --held-out-graphs cpg_model/graphs/held_out/ \
    --output evidence_pack/heldout_ao_fa/

# 스크립트 로직:
# 1. 14,055 에피소드 중 held-out graph에 해당하는 에피소드 필터
# 2. 각 에피소드에서:
#    - TOM pass? (항상 yes)
#    - ASC pass? (coverage ≥ 0.5)
#    - CwT pass? (coverage-timing ≥ 0.7)
#    - TCC fail? (any hard violation)
# 3. All-oblivious FA = TOM pass ∧ ASC pass ∧ CwT pass ∧ TCC fail
# 4. 통계:
#    - held-out all-oblivious FA rate (%)
#    - held-out all-oblivious FA count
#    - in-domain all-oblivious FA rate (%) for comparison
#    - Fisher exact test: held-out vs in-domain FA rate
```

### auto_numbers 갱신

```latex
% 기존 (이미 일부 존재하나 all-oblivious 미계산):
\newcommand{\heldoutAllObliviousFA}{<값>}      % held-out all-oblivious FA rate (%)
\newcommand{\heldoutAllObliviousCount}{<값>}    % held-out all-oblivious FA count
```

### 논문 반영 위치
Supporting Analyses > Held-out generalizability 문단 확장:

현재:
> On held-out episodes, verdict-flip rate is \vfHeldout{}\% and BSR(ASC) is \bsrHeldoutAC{}\%, closely matching the in-domain pattern.

확장:
> On held-out episodes, verdict-flip rate is \vfHeldout{}\% and BSR(ASC) is \bsrHeldoutAC{}\%, closely matching the in-domain pattern. The all-oblivious false-accept rate (TOM + ASC + CwT pass with hard violations) is \heldoutAllObliviousFA{}\%, comparable to the in-domain rate of \faAllOblivious{}\%, confirming that the blind-spot pattern generalizes to guidelines not used during benchmark development.

### 완료 기준
- [ ] held-out 에피소드 필터 + FA 계산
- [ ] Fisher exact test p-value
- [ ] auto_numbers 갱신 + 논문 1문장 추가

---

## 실행 순서 및 시간 배분

```
Day 1 (8h):
  09:00 - 09:05  실험 0: 사전 준비 (commit + compile)
  09:05 - 17:00  실험 2: EX-14 Reproducibility Pack

Day 2 (5h):
  09:00 - 11:00  실험 3: EX-17 Solver Agreement
  11:00 - 13:00  실험 4: EX-20 No-Context Matched Pair
  14:00 - 15:00  실험 6: Held-out All-Oblivious FA

Day 3 (4h):
  09:00 - 13:00  실험 5: EX-4A Clock Sweep

Day 3 (2h):
  14:00 - 16:00  최종 auto_numbers 갱신 + 논문 반영 + 통독 + compile

5/4 Abstract 제출
5/6 Full paper 제출
```

---

## 실험 완료 후 공격 방어 예상 상태

```
현재 (v11):    ✅ 15/21 (71%) | 🟡 3/21 | ⬜ 2/21 | 🔄 1/21
전부 완료 시:  ✅ 19/21 (90%) | 🟡 1/21 | ⬜ 0/21 | 🔄 1/21

닫히는 공격:
  #4  Solver conflation   → EX-17 14,055ep ✅
  #6  Code/data E&D       → EX-14 Reproducibility ✅
  #16 FORBIDDEN under-act → EX-20 No-Context ✅
  #18 Held-out parsing    → Held-out AO FA ✅

여전히 열린 공격:
  #19 Model diversity (🟡) — Medical/Reasoning model 추가에 24h+ GPU 필요
  #3  Clinician validation (🔄) — 외부 의존, 제출 시 Status 유지

#11 Timing dominance:
  v11에서 EX-4C jitter (1.25%) 이미 반영 → ✅
  EX-4A Clock Sweep 추가 시 → 완전 방어 ✅
```

---

## Claude Code 프롬프트 템플릿

각 실험 시작 시 Claude Code에 아래 형식으로 전달:

```
[실험 ID]: [실험명]
목적: [방어 대상 공격 #번호 + 설명]
데이터: results/full_706_final/ (14,055 episodes, 3-run filtered)
기준: evidence_pack/verdict_matrix_v4.json
출력: evidence_pack/[디렉토리]/
갱신: paper/auto_numbers.tex에 매크로 [N]개 추가/갱신
논문: main_final_v11.tex [Section]에 [N]문단 추가

[구체 로직 설명]
```