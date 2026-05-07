# Claude Code 세션 프롬프트: ?? 플레이스홀더 전면 해소 + E8 완료

## 컨텍스트

NeurIPS 2026 CGA-Bench 논문. 마감 5/6 (abstract 5/4).
에피소드 실행 중 (67.7% 완료, qwen27b/35b 거의 끝남, qwen397b가 병목 ~20-24h).
이전 세션에서: normalizer 수정 (42.6%→38.5% omission), re-scoring 완료 (9,982 episodes), 
exact verdict 확정 (FA 25.1%, verdict-flip 91.6%, ASC FA 59.3%).

`paper/auto_numbers.tex`에 **28개 `??` 플레이스홀더**가 남아있다.
대부분 기존 9,982 에피소드로 계산 가능. 에피소드 완료를 기다릴 필요 없음.

## 작업 순서 (우선순위)

### Task 0: 에피소드 상태 확인
```bash
for m in oss120b qwen35b qwen27b qwen4b qwen397b nemotron30b gemma31b; do
  echo "$m: $(ls results/full_706_final/$m/*.json 2>/dev/null | wc -l) / 2118"
done
ps aux | grep run_episode | grep -v grep | wc -l
```
qwen27b, qwen35b가 완료되었는지 확인. 완료된 모델이 5개 이상이면 통계적으로 충분.

### Task 1: E8 Adapter 상태 확인 (신규 서버 127.0.0.1
```bash
# 신규 서버 접속
ssh [email-redacted]

# GPU 3 (port 8203) 상태
nvidia-smi | grep -A2 "GPU 3"
ps aux | grep -E "adapter|e8|external" | grep -v grep

# Adapter 결과 확인
ls -la results/e8_adapter*/
# 또는
find . -path "*e8*adapter*" -name "*.json" | head -20

# AgentClinic adapter 결과
ls results/e8_adapter_agentclinic/ 2>/dev/null && echo "AC adapter exists" || echo "AC adapter NOT found"

# MedAgentBench adapter 결과  
ls results/e8_adapter_medagentbench/ 2>/dev/null && echo "MAB adapter exists" || echo "MAB adapter NOT found"
```

**확인할 것:**
- AgentClinic 53개 domain-matched 시나리오 생성 완료 여부
- MedAgentBench 300개 에피소드 변환 완료 여부
- 하나만 됐으면 나머지 시작
- 둘 다 안 됐으면 `run_e8_adapter_direction.py` 또는 `run_external_benchmark.py` 실행

**E8 Adapter 실행 (미완료 시):**
```bash
# 신규 서버에서
cd /path/to/cga-bench
# AgentClinic adapter
CUDA_VISIBLE_DEVICES=3 python scripts/run_e8_adapter_direction.py \
    --benchmark agentclinic \
    --model qwen35b \
    --port 8203 \
    --output results/e8_adapter_agentclinic/

# MedAgentBench adapter  
CUDA_VISIBLE_DEVICES=3 python scripts/run_e8_adapter_direction.py \
    --benchmark medagentbench \
    --model qwen35b \
    --port 8203 \
    --output results/e8_adapter_medagentbench/
```

### Task 2: Variance Decomposition (η²)
기존 9,982 에피소드에서 ANOVA 실행. 채울 매크로 6개:
`etaEvaluator`, `etaRun`, `etaRatio`, `evalEntropy`, `runInstability`, `wilcoxonP`

```bash
python scripts/experiments/run_post_episode_stats.py \
    --episodes-dir results/full_706_final \
    --output evidence_pack/variance_decomposition.json
```

스크립트가 없거나 경로가 다르면 직접 계산:
- 각 에피소드에 5개 evaluator verdict (TOM, ASC, CwT, PAF, TCC) 적용
- Two-way ANOVA: verdict ~ evaluator + run + evaluator×run
- η²(evaluator) = SS_evaluator / SS_total
- η²(run) = SS_run / SS_total
- etaRatio = η²(evaluator) / η²(run)
- Wilcoxon signed-rank: evaluator pairs 간 verdict 차이 유의성

### Task 3: Engine vs Manual (E7 테이블)
기존 에피소드를 manual/auto로 분리. 채울 매크로 8개:
`vfManual`, `vfAuto`, `bsrManualAC`, `bsrAutoAC`, `violManual`, `violAuto`, `ctypeManual`, `ctypeAuto`

시나리오 소스 판별:
- `configs/scenarios/auto_generated_scenarios.yaml`에 있으면 auto
- 그 외 `configs/scenarios/*.yaml`에 있으면 manual
- scenario_id prefix: `gen_`, `combo_`, `pathway_`, `val_`, `single_trigger_` → auto

각 그룹에 대해:
- Verdict-flip rate (≥1 evaluator pair disagreement)
- BSR(ASC) = P(ASC=pass ∧ TCC=fail) / N
- Mean violations per episode
- Constraint type coverage (FORBIDDEN, REQUIRED, BEFORE, WITHIN 중 몇 개 유형 커버)

### Task 4: Held-out Generalizability
채울 매크로 2개: `vfHeldout`, `bsrHeldoutAC`

held-out 도메인: aba_burn, aabb_transfusion, acog_obstetric, pals_pediatric, apa_agitation
- 해당 도메인 에피소드만 필터
- verdict-flip rate, BSR(ASC) 계산

**주의**: `heldoutFARate`(77.0%), `heldoutAORate`(34.6%) 등은 이미 채워져 있음(L411-418). 
`vfHeldout`과 `bsrHeldoutAC`만 계산하면 됨.

### Task 5: Difficulty Equivalence
채울 매크로 2개: `cohenDDifficulty`, `spearmanManualAuto`

- Manual vs auto 시나리오의 compliance_score 분포 비교
- Cohen's d = (mean_auto - mean_manual) / pooled_sd
- Model ordering: 각 evaluator에서 model ranking을 manual/auto별로 계산, Spearman ρ

### Task 6: Mixed-Effects GEE
채울 매크로 7개: `geeMethod` ~ `geeORPAF`

```python
# pip install statsmodels
import statsmodels.api as sm
from statsmodels.genmod.generalized_estimating_equations import GEE
from statsmodels.genmod.families import Binomial

# 데이터: 각 (episode, evaluator) 조합의 verdict (0/1)
# evaluator를 dummy variable로 (TCC=reference)
# scenario를 clustering unit로
# GEE logistic with exchangeable correlation

model = GEE.from_formula(
    "verdict ~ C(evaluator, Treatment(reference='TCC'))",
    groups="scenario_id",
    data=df,
    family=Binomial(),
    cov_struct=sm.cov_struct.Exchangeable()
)
result = model.fit()
# OR = exp(coefficient)
```

### Task 7: Ranking Flip (Friedman/Kendall)
채울 매크로 5개: `friedmanChi`, `friedmanP`, `kendallW`, `reversalRate`, `topOneFlip`

- 각 evaluator에서 model별 pass rate → model ranking
- Friedman test: evaluator 간 model ranking 일치 여부
- Kendall's W: concordance 정도
- Reversal rate: model pair 중 rank 역전 비율
- Top-1 flip: ASC 1등 ≠ TCC 1등?

### Task 8: Timing Validity Audit
채울 매크로 7개: `timingNWithinViols` ~ `timingNScenariosAgree`

에피소드의 violation_events에서 WITHIN violation 추출:
- 각 violation의 deadline vs actual time → margin 계산
- margin 분포: mean, median
- boundary 비율: margin < 5min 인 비율
- over-60 비율: margin > 60min 인 비율
- Cross-model Jaccard: 같은 시나리오에서 모델 간 동일 constraint 위반 비율

### Task 9: E8 Replay
채울 매크로 2개: `crossReplayMABBlindPct`, `crossReplayACBlindPct`

기존 9,982 에피소드에 MedAgentBench/AgentClinic scorer를 재구현 적용:
```bash
python scripts/experiments/run_e8_replay.py \
    --episodes-dir results/full_706_final \
    --output evidence_pack/e8_replay_results.json
```

스크립트가 없으면:
- MAB-F1: action-set F1 (expected vs performed) with forbidden penalty
- AC-Diag: diagnostic accuracy + action coverage
- 각 scorer의 pass/fail verdict 계산 후 TCC와 비교
- BSR_cond = P(TCC=fail | external_scorer=pass)

### Task 10: auto_numbers.tex 갱신
모든 결과를 `paper/auto_numbers.tex`에 반영:
```bash
python scripts/update_all_auto_numbers.py \
    --episodes-dir results/full_706_final \
    --skip-vllm
```

또는 수동으로 각 `??`를 computed value로 교체.
**주의**: `\renewcommand`가 아닌 `\newcommand`이므로 중복 정의 에러 주의. 
기존 정의를 찾아서 값만 교체할 것.

### Task 11: 최종 검증
```bash
# LaTeX 컴파일 테스트
cd paper/
pdflatex -halt-on-error main_final_v8.tex 2>&1 | grep -E "Error|Warning|Undefined"

# ?? 잔존 확인
grep -c '??' auto_numbers.tex
grep '??' auto_numbers.tex
```

## 주의사항

1. **E3-E5 수치(L60-247)는 기존 180 에피소드 기준** — 에피소드 완료 후 9,982+로 갱신 필요하지만, 지금은 건드리지 않음. E1-E2만 re-scoring 반영됨.

2. **numModels=5 (L263)** — Gemma/Nemotron 에피소드가 완료되면 7로 변경. 지금은 5 유지.

3. **numEpisodes=9982 (L24)** — 에피소드 완료 후 최종 수로 갱신.

4. **E7 paired delta (L400-406)는 이미 채워짐** — 기존 7,229 에피소드 기준. 최종 에피소드로 갱신 필요하지만 지금은 유지.

5. **Normalizer 수정이 반영된 에피소드로 계산할 것** — re-scoring된 결과를 사용. 원본이 아닌 normalizer-fix 적용된 violation_events 기준.

6. **E8 Adapter 신규 서버 정보**:
   - SSH: `ssh [email-redacted]`
   - GPU 3: qwen35b, port 8203
   - 배포 프롬프트: `claude_code_e8_adapter_fresh_gen.md` 참조
   - 모델 리스트: qwen27b + qwen35b (이전 세션에서 추가됨)

## 성공 기준

- `grep '??' paper/auto_numbers.tex` 결과가 5개 이하 (clinician-dependent만 남음)
- E8 Replay 매크로 2개 채워짐
- E8 Adapter 상태 확인 + 미완료 시 실행 시작
- `pdflatex main_final_v8.tex` 에러 없음