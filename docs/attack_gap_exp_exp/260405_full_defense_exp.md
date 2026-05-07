# CGA-Bench 전면 방어: 에피소드 완료 전 코드 레벨 전체 작업

> 이 프롬프트의 모든 작업은 에피소드 완료 전에 **시스템을 만들고**, 
> 완료된 일부 에피소드로 **정합성과 정상동작을 검증**하는 것이 목표.
> 에피소드가 전부 끝나면 경로만 바꿔서 본실행.

---

## 사전 확인: 현재 사용 가능한 에피소드 파악

```bash
echo "=== 현재 에피소드 현황 ==="
for model_dir in results/full_706_v5/*/; do
  model=$(basename "$model_dir")
  count=$(find "$model_dir" -name "*.json" 2>/dev/null | wc -l)
  echo "  $model: $count episodes"
done

echo ""
echo "=== 전체 목표 ==="
echo "  706 scenarios × 3 runs × 7 models = 14,826 episodes"

echo ""
echo "=== 샘플 에피소드 구조 확인 ==="
SAMPLE=$(find results/full_706_v5/ -name "*.json" | head -1)
if [ -n "$SAMPLE" ]; then
  echo "File: $SAMPLE"
  python3 -c "
import json
with open('$SAMPLE') as f: ep = json.load(f)
print('Keys:', sorted(ep.keys()))
print('actions:', type(ep.get('actions')).__name__, '→', len(ep.get('actions',[])), 'items' if isinstance(ep.get('actions'), list) else '')
print('violation_events:', type(ep.get('violation_events')).__name__, '→', len(ep.get('violation_events',[])), 'items' if isinstance(ep.get('violation_events'), list) else '')
print('compliance_score:', ep.get('compliance_score'))
print('scenario_id:', ep.get('scenario_id'))
# evaluator verdict fields
for k in sorted(ep.keys()):
    if 'pass' in k.lower() or 'score' in k.lower() or 'verdict' in k.lower():
        print(f'  {k}: {ep[k]}')
"
fi
```

TEST_DIR 변수를 설정한다. 완료된 모델 중 가장 에피소드가 많은 것을 사용:
```bash
TEST_MODEL=$(ls -d results/full_706_v5/*/ | while read d; do echo "$(find "$d" -name '*.json' | wc -l) $d"; done | sort -rn | head -1 | awk '{print $2}')
TEST_DIR="results/full_706_v5"
echo "Test model dir: $TEST_MODEL ($(find "$TEST_MODEL" -name '*.json' | wc -l) episodes)"
```

---

## Task 1: Constraint Accounting 정정 [치명적, 즉시]

numBefore=0, numMust=557, numHardConstraints=984가 본문과 충돌한다.
BEFORE constraints의 실제 위치를 찾고, hard/soft 분류를 검증하라.

```bash
echo "=== 1-1. sequence_rules 전수 조사 ==="
python3 -c "
import yaml, glob
total_seq = 0
total_cond_before = 0
graphs_with_before = []
for f in sorted(glob.glob('cpg_model/graphs/*.yaml')):
    if '_archive' in f: continue
    g = yaml.safe_load(open(f))
    name = f.split('/')[-1].replace('.yaml','')
    
    # sequence_rules (top-level)
    sr = g.get('sequence_rules', [])
    if isinstance(sr, list):
        total_seq += len(sr)
    
    # conditional_rules with BEFORE
    cr = g.get('conditional_rules', [])
    cond_before = [r for r in (cr or []) if isinstance(r, dict) and r.get('constraint_type','').upper() == 'BEFORE']
    total_cond_before += len(cond_before)
    
    # node-level sequence dependencies
    nodes = g.get('nodes', [])
    if isinstance(nodes, dict): nodes = list(nodes.values())
    node_before = 0
    for node in (nodes or []):
        if not isinstance(node, dict): continue
        deps = node.get('dependencies', []) or node.get('prerequisites', []) or node.get('sequence_after', [])
        if isinstance(deps, list):
            node_before += len(deps)
    
    if sr or cond_before or node_before:
        graphs_with_before.append((name, len(sr or []), len(cond_before), node_before))
    
    if sr:
        for s in sr:
            print(f'  {name} seq_rule: {s}')
    if cond_before:
        for c in cond_before:
            print(f'  {name} cond_BEFORE: {c.get(\"description\",c.get(\"name\",\"\"))}')

print(f'\\nTotal sequence_rules: {total_seq}')
print(f'Total conditional BEFORE: {total_cond_before}')
print(f'Graphs with BEFORE: {len(graphs_with_before)}')
for g, s, c, n in graphs_with_before:
    print(f'  {g}: seq={s} cond_before={c} node_deps={n}')
"

echo ""
echo "=== 1-2. MUST evidence_strength 분포 ==="
python3 -c "
import yaml, glob, collections
hard_count = 0
soft_count = 0
strength_dist = collections.Counter()
for f in sorted(glob.glob('cpg_model/graphs/*.yaml')):
    if '_archive' in f: continue
    g = yaml.safe_load(open(f))
    nodes = g.get('nodes', [])
    if isinstance(nodes, dict): nodes = list(nodes.values())
    for node in (nodes or []):
        if not isinstance(node, dict): continue
        # mandatory = hard
        mandatory = node.get('mandatory_actions', [])
        if isinstance(mandatory, list):
            hard_count += len(mandatory)
        # optional = soft
        optional = node.get('optional_actions', [])
        if isinstance(optional, list):
            soft_count += len(optional)
        # evidence strength on deadlines
        deadlines = node.get('deadlines', {})
        if isinstance(deadlines, dict):
            for action, dl in deadlines.items():
                if isinstance(dl, dict):
                    strength_dist[dl.get('evidence_strength','UNSPECIFIED')] += 1

print(f'Mandatory (hard MUST): {hard_count}')
print(f'Optional (soft SHOULD): {soft_count}')
print(f'Deadline evidence strengths: {dict(strength_dist)}')
"

echo ""
echo "=== 1-3. Derivation Engine에서 실제로 생성되는 BEFORE constraint 확인 ==="
python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from cpg_model.constraint_derivation import ConstraintDerivationEngine
    # 아무 시나리오 하나로 derivation 실행
    import yaml, glob
    graph_files = sorted([f for f in glob.glob('cpg_model/graphs/*.yaml') if '_archive' not in f])
    
    for gf in graph_files[:3]:  # 처음 3개 graph만 테스트
        g = yaml.safe_load(open(gf))
        engine = ConstraintDerivationEngine(g)
        # dummy patient context
        patient = {'age': 65, 'sex': 'M'}
        try:
            constraints = engine.derive(patient)
            before_constraints = [c for c in constraints if c.constraint_type.upper() == 'BEFORE' or c.type.upper() == 'BEFORE']
            name = gf.split('/')[-1].replace('.yaml','')
            print(f'{name}: total={len(constraints)}, BEFORE={len(before_constraints)}')
            for bc in before_constraints[:3]:
                print(f'  {bc}')
        except Exception as e:
            print(f'{gf}: derive failed: {e}')
except ImportError as e:
    print(f'Import failed: {e}')
    print('Try alternative import paths...')
"

echo ""
echo "=== 1-4. E1 perturbation에서 사용된 BEFORE pairs의 실제 출처 ==="
# E1의 17개 BEFORE-only pairs가 어디서 왔는지 확인
find . -path "*/perturbation*" -name "*.json" -o -path "*/perturbation*" -name "*.py" | head -10
grep -r "BEFORE\|before_only\|ordering" scripts/experiments/ --include="*.py" -l | head -5
```

**보고 형식**:
```markdown
## Constraint Accounting 감사 결과

| 출처 | FORBIDDEN | MUST(hard) | SHOULD(soft) | BEFORE | WITHIN(hard) | WITHIN(soft) | Total |
|------|-----------|-----------|-------------|--------|-------------|-------------|-------|
| Graph YAML (node-level) | | | | | | | |
| Graph YAML (sequence_rules) | | | | | | | |
| Graph YAML (conditional_rules) | | | | | | | |
| Derivation Engine 출력 | | | | | | | |

numBefore가 0인 이유: [설명]
수정 방안: [구체적]
```

---

## Task 2: Instrumentation Mimic Ablation 스크립트 구축 [#6]

기존 E4 instrumentation ablation에 AgentClinic-like, MedAgentBench-like 모드를 추가한다.
완료된 에피소드로 정합성 검증한다.

```python
#!/usr/bin/env python3
"""
scripts/experiments/run_instrumentation_mimic.py

E4 확장: 기존 4 조건 + AgentClinic-like + MedAgentBench-like

Usage:
    python scripts/experiments/run_instrumentation_mimic.py \
        --episodes-dir results/full_706_v5 \
        --output evidence_pack/analysis/instrumentation_mimic.json
"""
```

**핵심 로직**: 각 조건에서 "어떤 observable을 masking하는가"를 정의하고, 
masking된 상태에서 TCC를 다시 돌려서 detection 변화를 측정.

```python
ABLATION_MODES = {
    "full": {
        # 모든 observable 사용
        "mask_timestamps": False,
        "mask_ordering": False, 
        "mask_state": False,
        "mask_actions": False,
    },
    "no_timestamps": {
        "mask_timestamps": True,  # WITHIN 못 잡음
    },
    "no_ordering": {
        "mask_ordering": True,  # BEFORE 못 잡음
    },
    "no_state": {
        "mask_state": True,  # conditional FORBIDDEN 못 잡음
    },
    "terminal_only": {
        "mask_timestamps": True,
        "mask_ordering": True,
        "mask_state": True,
        "mask_actions": True,  # 최종 output만
    },
    # === 신규 추가 ===
    "agentclinic_like": {
        # AgentClinic: conversation + diagnosis만
        # → action timestamps 없음, state gating 없음
        # → action set은 conversation에서 추론 가능 (부분적)
        "mask_timestamps": True,
        "mask_state": True,
        "mask_ordering": False,  # conversation order는 있음
        "use_partial_actions": True,  # 대화에서 추론된 action만
    },
    "medagentbench_like": {
        # MedAgentBench: FHIR action log + task-success
        # → timing constraints 없음, ordering 없음
        # → action set은 있음 (FHIR calls)
        "mask_timestamps": True,
        "mask_ordering": True,
        "mask_state": False,  # FHIR에 patient state 있음
    },
}
```

**실제 구현은 기존 코드 패턴을 따른다**:
1. 기존 E3/E4 ablation 스크립트를 찾아서 구조 확인
2. 위 mode 정의를 추가
3. 각 mode에서: hard episodes detected, FA rate, verdict-flip, critical FA 계산

```bash
# 기존 ablation 스크립트 찾기
find . -name "*ablation*" -o -name "*instrumentation*" | grep -v __pycache__ | head -10
# 기존 코드의 masking 로직 확인
grep -r "mask\|ablat\|remove.*timestamp\|no_time" scripts/experiments/ --include="*.py" -l | head -5
```

**검증**: TEST_DIR의 완료된 에피소드로 full과 terminal_only 두 극단만 먼저 돌려서 파이프라인 동작 확인.

---

## Task 3: E7 Paired Delta Analysis 스크립트 구축 [#10]

manual vs engine scenario에서 **같은 graph, 같은 model, 같은 run**끼리 paired comparison.

```python
#!/usr/bin/env python3
"""
scripts/experiments/run_paired_delta_analysis.py

E7 강화: manual vs engine scenarios의 paired delta 분석

산출물:
- Δ false-accept (engine - manual)
- Δ all-oblivious FA
- Engine-added constraint로 처음으로 unsafe가 된 episode 비율
- Newly exposed violation type 분해 (WITHIN/BEFORE/FORBIDDEN/MUST)
- Paired McNemar
- Scenario-clustered CI
- Model × source(manual/auto) interaction
"""
```

**핵심 로직**:
1. 각 에피소드의 scenario_id에서 source(manual/auto) 판별
2. 같은 graph_id를 공유하는 manual/auto scenario pairs 식별
3. 각 pair에서 evaluator verdict 비교
4. Engine-added constraints = (auto scenario constraints) - (manual scenario constraints)
5. Engine-added가 없었으면 pass였을 episode → "newly exposed by engine"

```bash
# manual vs auto scenario 구분 방법 확인
grep -r "source\|manual\|auto" configs/scenarios/ --include="*.yaml" | head -10
# 또는 auto_generated_scenarios.yaml에 있는 것이 auto
ls configs/scenarios/auto_generated_scenarios.yaml
```

**검증**: TEST_DIR에서 sepsis domain의 manual + auto scenario 에피소드를 골라 paired delta가 계산되는지 확인.

---

## Task 4: Held-out Claim Generalization 스크립트 구축 [#11]

held-out domain episodes에서 paper-level claim metrics를 계산.

```python
#!/usr/bin/env python3
"""
scripts/experiments/run_heldout_claim_analysis.py

held-out 5개 domain에서 paper-level claim 검증:
- false-accept rate
- all-oblivious FA
- verdict-flip
- matched-pair detection (if perturbation available)
- manual vs auto delta 유지 여부
- in-domain vs held-out statistical comparison
"""
```

**핵심**: held-out graph IDs 식별 → 해당 scenario의 episodes만 필터 → 동일 metric 계산

```bash
# held-out graph 목록 확인
echo "=== Held-out graphs ==="
ls cpg_model/graphs/ | grep -i "aba_burn\|aabb_trans\|acog_obstetric\|pals_pediatric\|apa_agitation"
# held-out scenarios 확인
grep -r "aba_burn\|aabb\|acog\|pals\|apa_agitation" configs/scenarios/ --include="*.yaml" -l
```

**검증**: TEST_DIR에서 held-out domain 에피소드가 있는지 확인하고, 있으면 metric 계산 파이프라인 테스트.

---

## Task 5: Non-degenerate Terminal LLM Judge 구축 [#8]

DxEM(TOM) 대체: trace를 안 보고 final management plan만 보는 LLM judge.

```python
#!/usr/bin/env python3
"""
scripts/experiments/run_terminal_llm_judge.py

Non-degenerate terminal-output evaluator:
- Episode에서 final management plan text만 추출
- LLM judge에 "이 관리 계획이 [domain] 가이드라인에 부합하는가?" 판정 요청
- Trace 전체를 절대 노출하지 않음
- Hard-violating episode 중 이 judge가 pass시킨 비율 = terminal blindness

vLLM endpoint 필요 (에피소드 완료 후 사용 가능)
"""
```

**핵심 로직**:
1. Episode JSON에서 final output / management plan 추출
2. Scenario의 CPG domain + patient context 추출
3. Prompt: "Given this patient [context] and the clinician's final plan [plan], does this plan adhere to [guideline] guidelines? Answer Yes/No with brief justification."
4. LLM response → pass/fail 파싱
5. Cross-tab with TCC verdict → FA rate

```bash
# episode에서 final output이 어디 저장되는지 확인
python3 -c "
import json
ep = json.load(open('$(find results/full_706_v5/ -name \"*.json\" | head -1)'))
# final output 후보 필드
for k in ['final_output', 'final_plan', 'management_plan', 'diagnosis', 'summary', 'last_response']:
    if k in ep:
        print(f'{k}: {str(ep[k])[:200]}')
# 또는 actions의 마지막 항목
actions = ep.get('actions', [])
if actions:
    print(f'Last action: {actions[-1]}')
"
```

**검증**: 에피소드 1개로 prompt 생성 → 수동으로 LLM 호출 → 파싱 동작 확인. 
vLLM 서버가 점유 중이면 **스크립트만 만들고 dry-run 모드로 검증** (prompt 출력까지만).

---

## Task 6: Scorer Fidelity Audit 프레임워크 구축 [#9]

v3_p1a/b replay 스크립트에 fidelity audit 기능 추가.

```bash
# 기존 replay 스크립트 확인
echo "=== MAB replay ==="
head -80 scripts/experiments/v3_p1b_medagentbench_replay.py

echo ""
echo "=== AC replay ==="  
head -80 scripts/experiments/v3_p1a_agentclinic_replay.py
```

**추가해야 할 것**:

1. **Published examples 재현 테이블**:
   - MedAgentBench 논문의 Table/Figure에서 예시 trajectory + expected score 추출
   - Re-implemented scorer로 같은 입력 → 같은 출력인지 확인
   - Exact agreement, 차이가 나면 원인 분석

2. **Threshold sweep**:
   - MAB-F1의 pass threshold를 0.3~0.7로 sweep
   - AC-Diag의 threshold도 sweep
   - 각 threshold에서 FA rate 변화 → "threshold과 무관하게 blind spot 존재" 입증

3. **Failure case 분석**:
   - Re-implemented scorer가 original과 다를 수 있는 edge cases 식별
   - 이를 table로 명시 → "proxy limitation" section

```python
# v3_p1b에 추가할 fidelity audit 함수 골격
def run_fidelity_audit():
    """
    Published MedAgentBench examples로 scorer 재현 정확도 검증.
    """
    # 1. MedAgentBench 논문의 예시 trajectory 로드
    # 2. 우리 re-implemented scorer로 채점
    # 3. Expected vs actual 비교
    # 4. Agreement metrics
    pass

def run_threshold_sweep(episodes, thresholds=[0.3, 0.4, 0.5, 0.6, 0.7]):
    """
    각 threshold에서 FA rate 계산.
    """
    pass
```

**검증**: TEST_DIR의 에피소드 100개로 replay + threshold sweep 동작 확인.

---

## Task 7: Exact d_G Subset Audit 스크립트 구축 [#13]

ILP exact solver vs tiered solver 비교.

```python
#!/usr/bin/env python3
"""
scripts/experiments/run_exact_dg_audit.py

200 episode subset에서 ILP vs tiered solver 비교:
- Spearman / Pearson correlation
- Rank reversal count
- Conclusion reversal (pass/fail이 바뀌는 경우)
- Exact lower cost 비율
- Violation interaction cases (ILP가 다른 결과를 내는 이유)
"""
```

```bash
# ILP solver 위치 확인
find . -name "*.py" | xargs grep -l "ILP\|ilp\|pulp\|linear_program" 2>/dev/null | head -5
# Tiered solver 위치 확인
find . -name "*.py" | xargs grep -l "tiered\|four.phase\|phase.*solver" 2>/dev/null | head -5
```

**검증**: TEST_DIR에서 10개 에피소드로 양쪽 solver 실행 → 결과 비교 동작 확인.

---

## Task 8: Timing Validity Audit 3-part 강화 [#12]

기존 `run_timing_validity_audit.py`에 3가지 추가 분석을 넣는다.

**추가 분석 1: Action-class duration model**
```python
# 이미 ACTION_CATEGORIES 정의가 있음. 여기에:
# - 각 category별 평균 action 수 / episode
# - category별 timeline position distribution
# - "medication_stat actions이 diagnostic_lab보다 먼저 나오는 비율" 같은 clinical ordering check
```

**추가 분석 2: Parallelizable action batching**
```python
# 실제 임상에서 동시에 오더 가능한 action pairs 정의
PARALLELIZABLE = [
    ("order_cbc", "order_bmp"),  # 둘 다 blood draw
    ("order_cbc", "order_blood_cultures"),
    ("order_troponin", "order_bnp"),  # cardiac panel
    ("continuous_cardiac_monitoring", "pulse_oximetry"),  # 동시 모니터링
]
# 각 pair의 step gap 분포 → gap=0이면 이미 동시, gap>0이면 시뮬레이션 artifact 가능
# 만약 timing violation이 parallelizable pair에서만 발생하면 artifact 의심
# → "timing violation 중 parallelizable pair에서 발생한 비율" 계산
```

**추가 분석 3: Timing violation manual audit sample**
```python
# 20-30개 timing violation을 stratified sample
# 각각에 대해 자동 분류:
#   - genuine_delay: deadline 대비 margin이 크고, 중간에 다른 action이 끼어있음
#   - batching_artifact: parallelizable pair에서 발생, margin이 1 step
#   - ambiguous_deadline: deadline 자체가 논란 가능 (evidence strength low)
#   - mapping_artifact: action normalizer에서 발생한 false match
# 이 분류 결과를 CSV로 출력 → clinician에게 검증 의뢰 가능
```

**검증**: TEST_DIR에서 위 3가지 분석 모두 실행되는지 확인.

---

## Task 9: Clinician Review Packet 생성 [#2, #7 병합]

에피소드 완료 후 즉시 의사에게 보낼 리뷰 패킷을 미리 생성하는 시스템 구축.

```bash
# 기존 패킷 생성 스크립트 확인
find . -name "*clinician*" -o -name "*review_packet*" | grep -v __pycache__ | head -10
```

**패킷 구성**:

**Part A: Episode Review (Section 6 Clinician Validation)**
```python
def generate_episode_review_packet(episodes_dir, output_dir, n=60):
    """
    60 episodes stratified sampling:
    - 30 false-accept (action-set pass + TCC fail)
    - 15 true-pass (all pass, no violations)
    - 15 true-fail (all fail)
    
    각 episode에 대해:
    - Scenario description (patient context, clinical domain)
    - Agent trace (anonymized, evaluator labels withheld)
    - Q1-Q4 response sheet
    
    출력: CSV + 개별 episode PDF
    """
```

**Part B: Constraint Review (Engine Expert Audit)**
```python
def generate_constraint_review_packet(output_dir, n=60):
    """
    60 engine-only constraints stratified sampling:
    - 20 FORBIDDEN
    - 20 REQUIRED  
    - 20 WITHIN
    
    각 constraint에 대해:
    - Source graph + node
    - Triggering conditional rule
    - Patient context where this fires
    - The constraint statement
    - Response: valid / invalid / redundant / clinically important
    
    출력: CSV spreadsheet
    """
```

**검증**: 
- Part A: TEST_DIR에서 30+15+15 sampling이 동작하는지 (에피소드 수가 적으면 비율 조정)
- Part B: engine-only constraint 추출이 동작하는지 (에피소드 불필요, 지금 즉시 테스트 가능)

---

## Task 10: E8 Cross-Benchmark Replay 경로 업데이트 + 테스트 [#9, #14]

v3_p1a/b 스크립트가 full_706_v5를 정상적으로 읽는지 확인.

```bash
# 경로 확인
grep -n "results/" scripts/experiments/v3_p1a_agentclinic_replay.py | head -5
grep -n "results/" scripts/experiments/v3_p1b_medagentbench_replay.py | head -5

# 모델 목록 확인 (7개 모두 포함?)
grep -n "model\|oss120b\|qwen\|gemma\|nemotron" scripts/experiments/v3_p1b_medagentbench_replay.py | head -10
```

**검증**: TEST_DIR의 에피소드 50개로 MAB replay → 파이프라인 동작 확인.
scorer 출력 형식, FA 계산 로직, violation cross-tab이 정상인지.

---

## Task 11: auto_numbers.tex 자동 갱신 파이프라인 구축

모든 post-episode 스크립트가 auto_numbers.tex를 자동 갱신하도록 통합.

```python
#!/usr/bin/env python3
"""
scripts/update_all_auto_numbers.py

모든 분석 스크립트를 순차 실행하고 auto_numbers.tex를 일괄 갱신.

Usage:
    python scripts/update_all_auto_numbers.py --episodes-dir results/full_706_v5
"""

SCRIPTS = [
    ("Post-episode rescore", "make post-episode"),
    ("Constraint counts", "python scripts/extract_constraint_counts.py"),
    ("E8 MAB replay", "python scripts/experiments/v3_p1b_medagentbench_replay.py"),
    ("E8 AC replay", "python scripts/experiments/v3_p1a_agentclinic_replay.py"),
    ("Instrumentation mimic", "python scripts/experiments/run_instrumentation_mimic.py"),
    ("Paired delta", "python scripts/experiments/run_paired_delta_analysis.py"),
    ("Held-out claim", "python scripts/experiments/run_heldout_claim_analysis.py"),
    ("Timing audit", "python scripts/experiments/run_timing_validity_audit.py"),
    ("Post-episode stats", "python scripts/experiments/run_post_episode_stats.py"),
    ("Terminal LLM judge", "python scripts/experiments/run_terminal_llm_judge.py"),
    ("d_G audit", "python scripts/experiments/run_exact_dg_audit.py"),
]

# 각 스크립트가 JSON 출력 → update_auto_numbers() 함수로 tex 갱신
```

**검증**: dry-run 모드로 전체 파이프라인이 에러 없이 실행되는지 확인.

---

## 전체 검증 체크리스트

모든 Task 완료 후, 아래를 보고하라:

```markdown
## Pre-Episode System Readiness

| Task | 스크립트 | 동작 확인 | 산출물 형식 | auto_numbers 연동 |
|------|---------|----------|-----------|-----------------|
| 1. Constraint accounting | 수동 조사 | ✅/❌ | 보고서 | numBefore 등 |
| 2. Instrumentation mimic | run_instrumentation_mimic.py | ✅/❌ | JSON | instrAC*, instrMAB* |
| 3. Paired delta | run_paired_delta_analysis.py | ✅/❌ | JSON | deltaFA*, newlyExposed* |
| 4. Held-out claim | run_heldout_claim_analysis.py | ✅/❌ | JSON | heldout* |
| 5. Terminal LLM judge | run_terminal_llm_judge.py | ✅/❌ (dry-run) | JSON | terminalFA* |
| 6. Scorer fidelity | v3_p1a/b + fidelity | ✅/❌ | JSON+table | crossReplay* |
| 7. d_G audit | run_exact_dg_audit.py | ✅/❌ | JSON | solver* |
| 8. Timing audit (강화) | run_timing_validity_audit.py | ✅/❌ | JSON | timing* |
| 9. Clinician packet | generate_*_packet.py | ✅/❌ | CSV+PDF | — |
| 10. E8 replay paths | v3_p1a/b 경로 | ✅/❌ | — | — |
| 11. Auto-update pipeline | update_all_auto_numbers.py | ✅/❌ (dry-run) | tex | 전체 |

에피소드 완료 후 실행 명령:
```bash
python scripts/update_all_auto_numbers.py --episodes-dir results/full_706_v5
```
```

---

## 우선순위 요약

```
즉시 (지금):
  1. Task 1: Constraint accounting [치명적]
  2. Task 9-B: Constraint review packet (에피소드 불필요)
  3. Task 2-7: 스크립트 구축 + TEST_DIR로 검증

에피소드 완료 후 (경로만 변경):
  4. Task 11: update_all_auto_numbers.py 본실행
  5. Task 9-A: Episode review packet 생성 → 의사 배포
  6. Task 5: Terminal LLM judge 본실행 (vLLM 사용 가능)
```