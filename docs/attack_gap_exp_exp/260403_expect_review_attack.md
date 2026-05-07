> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Task: Episode 실행 대기 중 병렬 구현 — 8개 방어

실행(5,490 episodes)이 3-4일 걸린다. 그 동안 실행 결과가 불필요한 방어를 구현한다.

---

## 1. Evaluator Agreement Analysis (공격 1.1)

"같은 trace에서 evaluator가 다른 결론을 내리는 게 정말 문제인가?"에 대한 정량적 답변.

### 파일: `scripts/evaluator_agreement.py`

```python
"""
기존 verdict_matrix_v4.json (또는 v5)에서:
1. 6개 evaluator 쌍별 Cohen's kappa
2. 전체 Fleiss' kappa
3. Agreement matrix (heatmap용 데이터)
4. Most-disagreed episodes 추출
"""
import json
import numpy as np
from itertools import combinations
from pathlib import Path

def load_verdict_matrix(path="evidence_pack/analysis/verdict_matrix_v4.json"):
    with open(path) as f:
        return json.load(f)

def cohens_kappa(rater1, rater2):
    """Binary ratings → Cohen's kappa"""
    assert len(rater1) == len(rater2)
    n = len(rater1)
    # Observed agreement
    agree = sum(a == b for a, b in zip(rater1, rater2))
    po = agree / n
    # Expected agreement
    p1_yes = sum(rater1) / n
    p2_yes = sum(rater2) / n
    pe = p1_yes * p2_yes + (1 - p1_yes) * (1 - p2_yes)
    # Kappa
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)

def fleiss_kappa(matrix):
    """
    matrix: N×k where N=subjects, k=categories
    matrix[i][j] = number of raters who assigned subject i to category j
    """
    N, k = matrix.shape
    n = matrix.sum(axis=1)[0]  # raters per subject (assuming constant)
    
    # Proportion in each category
    p = matrix.sum(axis=0) / (N * n)
    
    # Per-subject agreement
    P = (matrix ** 2).sum(axis=1) - n
    P = P / (n * (n - 1))
    
    P_bar = P.mean()
    Pe = (p ** 2).sum()
    
    if Pe == 1.0:
        return 1.0
    return (P_bar - Pe) / (1 - Pe)

def main():
    vm = load_verdict_matrix()
    
    evaluators = ["DxEM", "AC-Proxy", "MAB-Proxy", "C2", "ACov", "UP_any"]
    # 각 evaluator의 binary verdict를 episode별로 추출
    # vm 구조에 맞게 조정 필요
    
    episodes = list(vm.keys()) if isinstance(vm, dict) else vm
    
    # ... evaluator별 pass/fail vector 구성 ...
    # 이건 실제 vm 구조에 따라 코드 조정 필요
    
    # Pairwise Cohen's kappa
    print("=== Pairwise Cohen's Kappa ===")
    kappa_matrix = {}
    for e1, e2 in combinations(evaluators, 2):
        k = cohens_kappa(verdicts[e1], verdicts[e2])
        kappa_matrix[(e1, e2)] = k
        print(f"  {e1} vs {e2}: κ={k:.3f}")
    
    # Fleiss' kappa
    # ... construct rating matrix ...
    fk = fleiss_kappa(rating_matrix)
    print(f"\nFleiss' kappa (all 6 evaluators): κ={fk:.3f}")
    
    # Interpretation
    if fk < 0.2:
        interp = "slight agreement"
    elif fk < 0.4:
        interp = "fair agreement"
    elif fk < 0.6:
        interp = "moderate agreement"
    elif fk < 0.8:
        interp = "substantial agreement"
    else:
        interp = "almost perfect agreement"
    print(f"Interpretation: {interp}")
    
    # Most-disagreed episodes
    # 6개 evaluator 중 pass/fail이 갈리는 episode 찾기
    disagreement_scores = []
    for ep_id in episode_ids:
        votes = [verdicts[e][ep_id] for e in evaluators]
        # 불일치 = min(pass_count, fail_count) / total
        pass_count = sum(votes)
        fail_count = len(votes) - pass_count
        disagreement = min(pass_count, fail_count) / len(votes)
        disagreement_scores.append((ep_id, disagreement, pass_count, fail_count))
    
    disagreement_scores.sort(key=lambda x: -x[1])
    print(f"\n=== Top 10 Most-Disagreed Episodes ===")
    for ep_id, score, pc, fc in disagreement_scores[:10]:
        print(f"  {ep_id}: {pc} pass / {fc} fail (disagreement={score:.2f})")
    
    # 결과 저장
    results = {
        "pairwise_kappa": {f"{e1}_vs_{e2}": round(k, 3) for (e1, e2), k in kappa_matrix.items()},
        "fleiss_kappa": round(fk, 3),
        "interpretation": interp,
        "top_disagreed_episodes": [{"episode": ep, "pass": pc, "fail": fc} 
                                     for ep, _, pc, fc in disagreement_scores[:20]]
    }
    with open("evidence_pack/analysis/evaluator_agreement.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
```

실제 verdict_matrix의 구조를 읽어서 코드를 조정하라. 핵심은 kappa 값과 most-disagreed episodes 목록.

---

## 2. Case Study 자동 선정 (공격 1.2)

### 파일: `scripts/select_case_studies.py`

```python
"""
Verdict matrix에서 evaluator 간 최대 불일치를 보이는 episode를 선정하고,
case study 작성에 필요한 정보를 추출.
"""
def select_case_studies(verdict_matrix_path, episode_dir, n=5):
    """
    선정 기준:
    1. 3 pass + 3 fail (최대 불일치)
    2. 다양한 시나리오 domain에서 선정
    3. Agent가 실제로 의미있는 action을 한 episode (너무 짧은 거 제외)
    """
    # ... 불일치 점수 기반 선정 ...
    
    for episode in selected:
        print(f"""
=== Case Study: {episode['id']} ===
Scenario: {episode['scenario_id']}
Domain: {episode['domain']}
Model: {episode['model']}

Agent Actions (summary):
{format_agent_actions(episode)}

Evaluator Verdicts:
  DxEM:      {'PASS' if episode['verdicts']['DxEM'] else 'FAIL'}
  AC-Proxy:  {'PASS' if episode['verdicts']['AC-Proxy'] else 'FAIL'}
  C2:        {'PASS' if episode['verdicts']['C2'] else 'FAIL'}
  ...

Key Disagreement:
  {explain_disagreement(episode)}

Clinical Impact:
  {assess_clinical_impact(episode)}
""")
```

---

## 3. Benchmark Comparison Table (공격 2.1)

### 파일: `scripts/generate_benchmark_comparison.py`

이건 web search가 필요하므로, 코드 대신 **비교표 구조**를 먼저 정의한다.

```python
"""
기존 의료 AI 벤치마크 비교표 생성.
"""

benchmarks = [
    {
        "name": "CGA-Bench (ours)",
        "year": 2026,
        "task_type": "interactive agent evaluation",
        "evaluation": "multi-evaluator, CPG-grounded",
        "scenarios": 366,
        "domains": 20,
        "constraint_types": ["FORBIDDEN", "BEFORE", "WITHIN", "conditional"],
        "cpg_grounded": True,
        "auto_generation": True,
        "provenance": True,
    },
    {
        "name": "MedQA",
        "year": 2021,
        "task_type": "multiple choice QA",
        "evaluation": "accuracy",
        "scenarios": "12,723",
        "domains": "general",
        "constraint_types": [],
        "cpg_grounded": False,
        "auto_generation": False,
        "provenance": False,
    },
    # ... HealthBench, AgentBench-Med, CLUE, MedBench 등 추가
]

# Markdown 표 생성
# LaTeX 표 생성 (논문용)
```

**이 스크립트에서 비교할 벤치마크 목록을 web search로 확인하라:**
- MedQA (Jin et al., 2021)
- HealthBench (OpenAI, 2025)
- AgentBench (Liu et al., 2023)
- MedAgentBench (2024/2025)
- CLUE (Chiang et al.)
- ClinicalBench
- 기타 최근 의료 agent 벤치마크

검색 후 비교표를 `evidence_pack/tables/benchmark_comparison.tex`로 생성.

---

## 4. Clinician Review Packet 생성 (공격 3.1)

### 파일: `scripts/generate_clinician_review_packet.py`

```python
"""
임상가 리뷰용 패킷 생성.
각 conditional rule을 자연어 질문으로 변환.
"""
def generate_packet():
    all_rules = collect_all_conditional_rules()  # 172개
    
    questions = []
    for rule in all_rules:
        q = {
            "rule_id": rule["rule_id"],
            "graph": rule["_graph_id"],
            "severity": rule["severity"],
            "clinical_question": format_clinical_question(rule),
            "expected_answer": "Yes" if rule["effect"]["type"] == "FORBIDDEN" else "Should be done",
            "evidence_cited": rule["evidence"],
        }
        questions.append(q)
    
    # CRITICAL만 먼저 (60개) — 임상가 시간 절약
    critical = [q for q in questions if q["severity"] == "CRITICAL"]
    high = [q for q in questions if q["severity"] == "HIGH"]
    
    # CSV 출력 (Google Sheets로 공유 가능)
    save_csv(critical, "evidence_pack/clinician_review/critical_rules.csv")
    save_csv(high, "evidence_pack/clinician_review/high_rules.csv")
    
    print(f"Generated {len(critical)} CRITICAL + {len(high)} HIGH questions")

def format_clinical_question(rule):
    """
    Rule을 자연어 질문으로 변환.
    
    예: 
    rule_id: "DKA-HYPOK-INSULIN-GATE"
    condition: "patient.labs.potassium < 3.3"
    effect: FORBIDDEN [start_insulin_infusion]
    →
    "A patient presents with DKA. Serum potassium is 2.9 mEq/L.
     Is it safe to start an insulin infusion at this point?
     [ ] Yes  [ ] No  [ ] Depends (explain)"
    """
    # condition을 자연어로
    condition_nl = condition_to_natural_language(rule["condition"])
    # effect를 질문으로
    if rule["effect"]["type"] == "FORBIDDEN":
        actions_nl = ", ".join(action_to_natural_language(a) for a in rule["effect"]["actions"])
        return f"Clinical scenario: {condition_nl}\nQuestion: Is it safe to {actions_nl}?\n[ ] Yes, safe  [ ] No, contraindicated  [ ] Depends (explain)"
    elif rule["effect"]["type"] == "REQUIRED":
        actions_nl = ", ".join(action_to_natural_language(a) for a in rule["effect"]["actions"])
        return f"Clinical scenario: {condition_nl}\nQuestion: Should the clinician {actions_nl}?\n[ ] Yes, required  [ ] No, not needed  [ ] Depends (explain)"
    
    return rule["description"]
```

---

## 5. Action Annotation Sheet 생성 (공격 3.3)

### 파일: `scripts/generate_action_annotation_sheet.py`

```python
"""
기존 episode에서 agent raw output + normalizer 결과를 추출하여
human annotation용 CSV 생성.
"""
def generate_annotation_sheet(episode_dir, sample_size=100):
    episodes = load_episodes(episode_dir)
    
    # 랜덤 샘플링 (시나리오 domain별 층화)
    sampled = stratified_sample(episodes, n=sample_size)
    
    rows = []
    for ep in sampled:
        for step in ep["agent_actions"]:
            raw_output = step["raw_text"]
            normalized = step["normalized_action"]  # ActionNormalizer 결과
            matched_expected = step.get("matched_expected_action", "")
            
            rows.append({
                "episode_id": ep["episode_id"],
                "scenario_id": ep["scenario_id"],
                "step_number": step["step"],
                "raw_agent_output": raw_output[:200],  # 200자 제한
                "normalized_action": normalized,
                "matched_expected": matched_expected,
                "annotator_correct": "",  # annotator가 채울 칸
                "annotator_correct_action": "",  # 맞는 action이 뭔지
                "annotator_notes": "",
            })
    
    save_csv(rows, "evidence_pack/annotation/action_annotation_sheet.csv")
    print(f"Generated annotation sheet: {len(rows)} rows from {sample_size} episodes")
```

**기존 episode가 있는 경우(results/clean_slate_rescored/)에서 실행. 없으면 template만 생성.**

---

## 6. Condition Safety Tests (공격 3.5)

### 파일: `tests/test_condition_safety.py`

```python
"""
ConstraintDerivationEngine._evaluate_condition()의 보안 테스트.
악의적 condition string이 코드를 실행하지 못하는지 확인.
"""
from cpg_model.constraint_derivation import ConstraintDerivationEngine

engine = ConstraintDerivationEngine()
patient = {"age": 50, "labs": {}, "comorbidities": [], "allergies": [], "medications": []}

def test_no_import():
    assert engine._evaluate_condition("__import__('os').system('ls')", patient) == False

def test_no_open():
    assert engine._evaluate_condition("open('/etc/passwd').read()", patient) == False

def test_no_exec():
    assert engine._evaluate_condition("exec('print(1)')", patient) == False

def test_no_eval_nested():
    assert engine._evaluate_condition("eval('1+1')", patient) == False

def test_no_lambda():
    result = engine._evaluate_condition("(lambda: True)()", patient)
    # lambda가 실행되면 True 반환. 실행 안 되면 False.
    # 보안상 False여야 함 (또는 exception catch)
    assert result == False

def test_no_class_access():
    assert engine._evaluate_condition("''.__class__.__mro__[-1].__subclasses__()", patient) == False

def test_no_globals():
    assert engine._evaluate_condition("globals()", patient) == False

def test_no_subprocess():
    assert engine._evaluate_condition("__import__('subprocess').run(['ls'])", patient) == False

def test_extremely_long_condition():
    """DoS 방지: 매우 긴 condition string"""
    long_condition = "patient.age > 1 and " * 10000 + "True"
    # timeout이나 length check가 있어야 함
    try:
        result = engine._evaluate_condition(long_condition, patient)
        # 결과가 나오더라도 OK, timeout 없으면 경고
    except:
        pass  # exception이면 OK

def test_normal_conditions_still_work():
    """보안 강화 후에도 정상 조건이 작동하는지"""
    assert engine._evaluate_condition("patient.age > 18", {"age": 50}) == True
    assert engine._evaluate_condition("'diabetes' in patient.comorbidities", 
                                       {"comorbidities": ["diabetes"]}) == True
    assert engine._evaluate_condition("patient.labs.potassium < 3.3", 
                                       {"labs": {"potassium": 2.9}}) == True
```

---

## 7. Reproducibility Makefile (공격 6.1)

### 파일: `Makefile`

```makefile
.PHONY: all install validate generate-scenarios test dry-run reproduce clean

PYTHON ?= python3
VENV ?= .venv

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt

validate:
	$(PYTHON) scripts/validate_conditional_rules.py
	$(PYTHON) -c "from cpg_model.scenario_loader import ScenarioLoader; s=ScenarioLoader().load_all_scenarios(); print(f'{len(s)} scenarios loaded')"

generate-scenarios:
	$(PYTHON) scripts/generate_all_scenarios.py

test:
	$(PYTHON) -m pytest tests/ -x -q

audit:
	$(PYTHON) scripts/generate_audit_matrix.py
	$(PYTHON) scripts/cross_reference_manual_vs_derived.py

dry-run:
	$(PYTHON) run_benchmark.py --scenario septic_shock_basic --model configs/models/rag_qwen3_4b.yaml --runs 1 --dry-run

reproduce: validate generate-scenarios test audit
	@echo "============================================"
	@echo "Reproducibility check PASSED"
	@echo "============================================"

clean:
	rm -rf $(VENV) __pycache__ .pytest_cache
	find . -name "*.pyc" -delete
```

### 파일: `README.md` (anonymous repo용)

```markdown
# CGA-Bench: Clinical Guideline Adherence Benchmark

## Quick Start

```bash
make install
make reproduce  # validates all scenarios + tests
make dry-run    # runs 1 episode as smoke test
```

## Full Benchmark Run

```bash
make generate-scenarios
bash scripts/run_full_benchmark.sh
```

## Structure

- `cpg_model/graphs/` — 20 CPG guideline graphs with conditional rules
- `cpg_model/constraint_derivation.py` — Constraint Derivation Engine  
- `cpg_model/patient_generator.py` — Automatic scenario generation
- `configs/scenarios/` — 366 clinical scenarios (105 manual + 261 auto-generated)
- `evidence_pack/` — Rule coverage audit, provenance chains
- `scripts/` — Analysis and utility scripts
- `tests/` — 169 unit tests
```

---

## 8. Rule Summary Tables (공격 A.1)

### 파일: `scripts/generate_rule_summary.py`

```python
"""
172개 conditional rule의 리뷰어 친화적 요약 생성.
"""
def generate_summary():
    rules = collect_all_conditional_rules()
    
    # 1. Severity 분포
    severity_dist = Counter(r["severity"] for r in rules)
    
    # 2. 유형 분류
    type_dist = Counter()
    for r in rules:
        if any(x in r["condition"] for x in ["allergies", "allergy"]):
            type_dist["Drug allergy / cross-reactivity"] += 1
        elif any(x in r["condition"] for x in ["labs.", "potassium", "glucose", "egfr", "ph"]):
            type_dist["Lab-value gated"] += 1
        elif any(x in r["condition"] for x in ["comorbidities", "pregnancy", "ckd", "liver"]):
            type_dist["Comorbidity-conditional"] += 1
        elif any(x in r["condition"] for x in ["age", "patient.age"]):
            type_dist["Age-based"] += 1
        elif any(x in r["condition"] for x in ["medications", "warfarin", "metformin"]):
            type_dist["Medication interaction"] += 1
        elif any(x in r["condition"] for x in ["vitals", "sbp", "hr", "spo2"]):
            type_dist["Vitals-based"] += 1
        else:
            type_dist["Other"] += 1
    
    # 3. Graph별 rule 밀도
    graph_density = Counter(r["_graph_id"] for r in rules)
    
    # 4. 대표 rule 5개 (각 type에서 1개씩)
    representative = select_representative_rules(rules, n=5)
    
    # LaTeX 표 생성
    generate_latex_tables(severity_dist, type_dist, graph_density, representative)
    
    # Markdown 요약
    generate_markdown_summary(severity_dist, type_dist, graph_density, representative)
    
    print(f"""
Rule Summary:
  Total rules: {len(rules)}
  By severity: {dict(severity_dist)}
  By type: {dict(type_dist)}
  Graphs with most rules: {graph_density.most_common(5)}
""")
```

### 파일: `scripts/generate_patient_realism_report.py` (공격 A.2)

```python
"""
생성된 patient의 임상적 현실성 분석.
"""
def analyze_patient_realism():
    loader = ScenarioLoader()
    scenarios = loader.load_all_scenarios()
    
    ages = []
    sexes = []
    potassiums = []
    glucoses = []
    phs = []
    
    issues = []
    
    for s in scenarios:
        p = s.patient if isinstance(s.patient, dict) else vars(s.patient)
        
        age = p.get("age")
        if age:
            ages.append(age)
            if age < 1 or age > 110:
                issues.append(f"{s.scenario_id}: age={age}")
        
        sex = p.get("sex")
        if sex:
            sexes.append(sex)
        
        labs = p.get("labs", {})
        if "potassium" in labs:
            potassiums.append(labs["potassium"])
        if "glucose" in labs:
            glucoses.append(labs["glucose"])
        if "ph" in labs:
            phs.append(labs["ph"])
        
        # 비현실적 조합 탐지
        comorbidities = p.get("comorbidities", [])
        if "pregnancy" in comorbidities and p.get("sex") == "M":
            issues.append(f"{s.scenario_id}: male + pregnancy")
        if age and age < 10 and "type_2_diabetes" in comorbidities:
            issues.append(f"{s.scenario_id}: age {age} + T2DM (unlikely)")
        if age and age > 80 and "pregnancy" in comorbidities:
            issues.append(f"{s.scenario_id}: age {age} + pregnancy (unlikely)")
    
    print(f"""
=== Patient Realism Report ===

Demographics:
  Age: min={min(ages)}, max={max(ages)}, mean={sum(ages)/len(ages):.0f}, median={sorted(ages)[len(ages)//2]}
  Sex: {Counter(sexes)}

Lab Distributions:
  Potassium ({len(potassiums)} values): {min(potassiums):.1f} - {max(potassiums):.1f}, mean={sum(potassiums)/len(potassiums):.1f}
  Glucose ({len(glucoses)} values): {min(glucoses):.0f} - {max(glucoses):.0f}
  pH ({len(phs)} values): {min(phs):.2f} - {max(phs):.2f}

Issues found: {len(issues)}
""")
    for issue in issues:
        print(f"  - {issue}")
    
    # 저장
    save_report("evidence_pack/patient_realism_report.md", ...)
```

---

## Completion Criteria

- [ ] evaluator_agreement.json 생성 (kappa values + most-disagreed episodes)
- [ ] case_studies/ 디렉토리에 top 5 disagreed episode 상세 정보
- [ ] benchmark_comparison.tex 생성 (최소 5개 벤치마크 비교)
- [ ] clinician_review/ 패킷 생성 (CRITICAL + HIGH CSV)
- [ ] action_annotation_sheet.csv 생성 (또는 template)
- [ ] test_condition_safety.py 전체 통과
- [ ] Makefile + README.md 생성
- [ ] rule_summary 통계 + LaTeX 표 생성
- [ ] patient_realism_report.md 생성 (issues 0 또는 모두 justified)
- [ ] 모든 기존 테스트 통과 유지