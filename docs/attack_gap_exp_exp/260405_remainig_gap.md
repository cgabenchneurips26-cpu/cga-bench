# Claude Code 세션 프롬프트: 남은 실행 가능 작업 전부 처리

## 컨텍스트 요약

NeurIPS 2026 CGA-Bench. 마감 5/6 (abstract 5/4).
에피소드: ~67% 완료 (10,950+), qwen27b/35b 완료, qwen397b가 병목 (~20-24h 남음).
시스템 검증 완료: 모든 버그가 violation TYPE 분류에만 영향, **TCC verdict(FA/BSR)는 무영향** 확인됨.

현재 확정된 핵심 수치:
- FA 25.1%, verdict-flip 91.6%, ASC FA 59.3%
- η²(evaluator)=0.312, η²(run)≈0.00002, ratio ~16,000x
- Friedman χ²=21.0, p<0.001, reversal 76.2%, top-1 flip=yes
- E8 Replay: MAB 44.5%, AC 59.6%
- auto_numbers.tex: 5개 `??` 남음 (전부 clinician-dependent prec*)

## 작업 (우선순위)

---

### Task 1: WS-3 LLM Judge (Non-degenerate terminal baseline)
**왜 급한가**: 리뷰어가 "DxEM은 trivial control"이라고 공격하면 방어 불가. LLM judge가 있으면 "terminal-output evaluator도 blind"가 증명됨.

**설계**:
- 입력: episode의 **final management summary/diagnosis만** (action trace 전체를 보여주면 안 됨)
- LLM: 현재 vLLM에서 사용 가능한 모델 (qwen35b 등)
- 프롬프트: "이 환자의 최종 관리 계획이 가이드라인을 준수하는가? Yes/No"
- 출력: pass/fail verdict
- 비교: LLM judge verdict vs TCC verdict → BSR 계산

**실행**:
```bash
# 스크립트 확인
ls scripts/experiments/run_ws3_llm_judge.py
# 또는 scripts/run_ws3_llm_judge.py

# vLLM endpoint 확인
curl -s http://localhost:8013/v1/models | head -5  # qwen35b
# 또는 신규 서버
curl -s http://localhost:8013/v1/models | head -5

# 실행 (500 에피소드 샘플로 충분)
python scripts/experiments/run_ws3_llm_judge.py \
    --episodes-dir results/full_706_final \
    --vllm-url http://localhost:8013/v1 \
    --sample 500 \
    --output evidence_pack/ws3_llm_judge.json
```

스크립트가 없으면 직접 구현:
```python
# 핵심 로직:
for ep in sample_episodes:
    # 1. terminal output만 추출
    terminal = ep.get('final_diagnosis', ep.get('diagnosis', ''))
    management = ep.get('management_plan', ep.get('final_plan', ''))
    scenario_desc = ep.get('scenario_description', '')
    
    # 2. LLM에 terminal-only 정보 제공
    prompt = f"""You are a clinical guideline compliance reviewer.
    
Patient scenario: {scenario_desc}

The AI agent's final assessment:
- Diagnosis: {terminal}
- Management plan: {management}

Based ONLY on the final assessment above (not on the process), 
does this management plan adequately follow clinical guidelines?

Answer: PASS or FAIL (one word only)"""
    
    # 3. vLLM 호출
    response = requests.post(vllm_url + "/chat/completions", json={
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 10,
        "temperature": 0,
    })
    
    # 4. verdict 추출
    llm_verdict = 'PASS' if 'pass' in response_text.lower() else 'FAIL'
    
    # 5. TCC와 비교
    tcc_verdict = 'PASS' if not ep.get('violation_events') else 'FAIL'
```

**채울 매크로** (필요 시 auto_numbers에 추가):
```latex
\newcommand{\llmJudgePassRate}{??}     % LLM judge pass rate
\newcommand{\llmJudgeBSR}{??}          % BSR of LLM judge
\newcommand{\llmJudgeFARate}{??}       % FA: LLM=pass AND TCC=fail
```

---

### Task 2: Normalizer 2차 수정 (ACLS aliases)
**왜 급한가**: FALSE OMISSION 18.1% 중 ACLS가 주범 (attach_defibrillator_pads, begin_high_quality_cpr, analyze_rhythm, deliver_defibrillation — 3,651건 합계).

**수정 대상** (quantify_omission_timing_overlap.py 결과의 top false OMISSION actions):
```bash
cat evidence_pack/omission_timing_overlap/omission_timing_overlap.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Top false OMISSION actions:')
for action, count in data.get('false_omission_actions', [])[:20]:
    print(f'  {action}: {count}')
"
```

각 action에 대해:
1. 모델이 실제로 출력한 raw action 확인 (에피소드 JSON의 actions 필드)
2. action_normalizer.py에 alias 매핑 추가
3. `defibrillate` → `deliver_defibrillation`, `start_cpr` → `begin_high_quality_cpr` 등

**검증**: 수정 후 FALSE OMISSION rate 재측정
```bash
python scripts/risk_mitigation/quantify_omission_timing_overlap.py --episodes-dir results/full_706_final
# 목표: 18.1% → < 10%
```

---

### Task 3: Re-scoring (normalizer 2차 수정 반영)
```bash
python scripts/risk_mitigation/compute_exact_evaluator_verdicts.py \
    --episodes-dir results/full_706_final \
    --output-dir evidence_pack/exact_verdicts_v3
```

**주의**: TCC verdict는 변하지 않지만 (DEVIATION은 hard가 아님), violation type 분포가 바뀌므로:
- OMISSION/TIMING/DEVIATION 비율이 정확해짐
- 논문의 "violation type breakdown" 표가 정확해짐
- OMISSION rate이 38.5%에서 더 내려갈 수 있음

---

### Task 4: E3-E5 수치 갱신 (old 180-ep → 현재 에피소드)
**왜 급한가**: E3(instrumentation ablation), E4(operating-point), E5(cluster) 수치가 아직 old 180 에피소드 기준. 리뷰어가 "E1-E2는 10,000 episodes인데 E3-E5는 180?"이라고 공격.

**E3: Instrumentation Ablation**
이건 설계상 controlled perturbation이라 180 에피소드로도 valid하지만, 더 큰 sample이면 더 좋음.
```bash
# 기존 스크립트가 있으면:
python scripts/experiments/run_instrumentation_ablation.py \
    --episodes-dir results/full_706_final \
    --sample 500 \
    --output evidence_pack/e3_instrumentation_v2.json

# 없으면: 기존 E3 로직을 현재 에피소드에서 재실행
# 핵심: 같은 에피소드에서 timestamps/ordering/state를 제거한 후 재채점
```

**E4: Operating-Point Matching**
```bash
python scripts/experiments/run_operating_point_matching.py \
    --episodes-dir results/full_706_final \
    --output evidence_pack/e4_operating_point_v2.json
```
현재 에피소드에서 ASC/CwT/PAF threshold sweep → matched pass rate에서 κ 재계산.

**E5: Evaluator Family Expansion**
```bash
python scripts/experiments/run_evaluator_expansion.py \
    --episodes-dir results/full_706_final \
    --output evidence_pack/e5_cluster_v2.json
```
12 evaluator variants의 cluster 분석. 현재 에피소드에서 재실행.

**주의**: E3-E5 스크립트가 기존 코드에 있는지 먼저 확인:
```bash
ls scripts/experiments/run_*
find scripts/ -name "*instrumentation*" -o -name "*operating_point*" -o -name "*evaluator*expansion*"
```

---

### Task 5: E8 Adapter 상태 확인 + 완료
```bash
# 신규 서버 확인
ssh [email-redacted] << 'EOF'
echo "=== GPU Status ==="
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used --format=csv

echo "=== E8 Adapter Results ==="
find . -path "*e8*adapter*" -name "*.json" 2>/dev/null | wc -l
ls -la results/e8_adapter*/ 2>/dev/null

echo "=== AgentClinic Adapter ==="
ls results/e8_adapter_agentclinic/*.json 2>/dev/null | wc -l

echo "=== MedAgentBench Adapter ==="
ls results/e8_adapter_medagentbench/*.json 2>/dev/null | wc -l

echo "=== Running Processes ==="
ps aux | grep -E "adapter|e8|external" | grep -v grep
EOF
```

결과에 따라:
- 둘 다 완료 → 결과 수집 + auto_numbers의 cross* 매크로 채우기
- 하나만 완료 → 나머지 시작
- 둘 다 미시작 → 즉시 시작

---

### Task 6: WS-5 Contamination Probe
```bash
# 스크립트 확인
ls scripts/experiments/run_ws5_contamination.py

# 실행 (vLLM 필요)
python scripts/experiments/run_ws5_contamination.py \
    --vllm-url http://localhost:8013/v1 \
    --output evidence_pack/ws5_contamination.json
```

이건 우선순위가 낮지만, vLLM이 돌고 있으면 병렬로 시작 가능.

---

### Task 7: Friedman/η² 교정값 auto_numbers 반영
이전 검증에서 발견된 버그 교정:
```bash
# paper/auto_numbers.tex에서 아래 값 교정:
# friedmanChi: 0.1 → 21.0
# friedmanP: 0.996 → <0.001
# etaRun: 0.036 → 0.00002
# etaRatio: 8.7 → 16262
# kendallW: 0.411 → [재계산 값]

# 확인:
grep -n 'friedmanChi\|friedmanP\|etaRun\|etaRatio\|kendallW' paper/auto_numbers.tex
```

**Kendall's W 재계산**:
이전 verify_friedman_eta.py에서 rank sum이 모두 28로 동일 → W=0.
하지만 이건 **evaluator별 model ranking의 concordance**이므로, 올바른 계산은:
- k = 4 evaluators (judges)
- n = 7 models (objects)
- R_i = model i의 rank sum across evaluators
- W = 12 * Σ(R_i - R̄)² / (k² * n * (n² - 1))

```python
import numpy as np
# pass rate matrix에서 rank matrix 계산 (row=model, col=evaluator)
# R_i = row sum of ranks
R_i = rank_matrix.sum(axis=1)  # per model
R_bar = R_i.mean()
k = 4  # evaluators
n = 7  # models
S = np.sum((R_i - R_bar) ** 2)
W = (12 * S) / (k**2 * n * (n**2 - 1))
```

---

## 실행 순서 (병렬 가능한 것은 병렬로)

```
[GPU 작업 — 백그라운드]
├─ Task 1: WS-3 LLM Judge (500 ep × qwen35b)
├─ Task 5: E8 Adapter 확인/실행 (신규 서버)
└─ Task 6: WS-5 Contamination (병렬 가능 시)

[CPU 작업 — 순차]
├─ Task 7: Friedman/η² 교정 (5분)
├─ Task 2: Normalizer 2차 수정 (30분)
├─ Task 3: Re-scoring (15분)
└─ Task 4: E3-E5 갱신 (각 15분)
```

## 성공 기준

1. WS-3 LLM judge BSR 확보 → "terminal-output evaluator도 blind" 증명
2. FALSE OMISSION < 10% (normalizer 2차 수정 후)
3. E3-E5 수치가 현재 에피소드 기준으로 갱신됨
4. Friedman/η² 교정값이 auto_numbers에 반영됨
5. E8 Adapter 상태 확인 완료

## 주의사항

- **에피소드가 아직 실행 중**: qwen397b, oss120b가 미완료. 현재 가용 에피소드(~11,000)로 작업하되, 완료 후 최종 갱신 필요.
- **vLLM endpoint**: 에피소드 실행에 쓰이는 GPU와 WS-3/WS-5에 쓰이는 GPU가 충돌하지 않도록 주의. 에피소드 완료된 모델의 GPU를 WS-3에 활용.
- **auto_numbers.tex 중복 정의**: `\newcommand` 중복 시 LaTeX 에러. 기존 정의를 찾아서 값만 교체할 것.
- **Normalizer 수정 후 반드시 기존 테스트 통과 확인**: `python -m pytest tests/ -x -q`