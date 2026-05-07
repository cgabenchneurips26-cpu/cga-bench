> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Task: 에피소드 실행 중간점검

실행이 12% 진행된 시점. 생성된 ~245 episodes를 분석하여:
1. Episode 품질이 정상인지
2. 실행 시간 추정이 맞는지
3. 조기 발견 가능한 문제가 있는지
4. 논문 결과의 방향성을 미리 엿볼 수 있는지

**실행 중인 프로세스를 방해하지 않도록 결과 JSON만 읽기(read-only)로 분석.**

---

## Check 1: Episode 품질 — 빈 episode, 짧은 episode, crash

```python
# scripts/midrun_check.py
import json
from pathlib import Path
from collections import defaultdict, Counter

OUTPUT = Path("results/full_690")
MODELS = ["oss120b", "qwen35b", "qwen27b", "qwen4b", "qwen397b"]

empty = []
short = []      # actions < 3
normal = []
errors = []
total_by_model = Counter()
actions_by_model = defaultdict(list)

for model in MODELS:
    model_dir = OUTPUT / model
    if not model_dir.exists():
        print(f"SKIP: {model} — dir not found")
        continue
    
    for f in sorted(model_dir.glob("*.json")):
        try:
            with open(f) as fh:
                ep = json.load(fh)
        except json.JSONDecodeError:
            errors.append(f"JSON_ERROR: {f.name}")
            continue
        
        total_by_model[model] += 1
        actions = ep.get("actions_count", 0)
        actions_by_model[model].append(actions)
        scenario = ep.get("scenario_id", "unknown")
        
        if actions == 0:
            empty.append(f"{model}/{scenario}")
        elif actions < 3:
            short.append(f"{model}/{scenario} (actions={actions})")
        else:
            normal.append(f"{model}/{scenario}")

print("=" * 60)
print("MIDRUN QUALITY CHECK")
print("=" * 60)

print(f"\nTotal episodes: {sum(total_by_model.values())}")
for m, c in total_by_model.most_common():
    avg_actions = sum(actions_by_model[m]) / len(actions_by_model[m]) if actions_by_model[m] else 0
    print(f"  {m}: {c} episodes, avg actions={avg_actions:.1f}")

print(f"\nEmpty (actions=0): {len(empty)}")
for e in empty[:10]:
    print(f"  {e}")
if len(empty) > 10:
    print(f"  ... +{len(empty)-10} more")

print(f"\nShort (actions<3): {len(short)}")
for s in short[:10]:
    print(f"  {s}")

print(f"\nJSON errors: {len(errors)}")
for e in errors[:5]:
    print(f"  {e}")

print(f"\nNormal: {len(normal)}")

# 빈 episode 비율
empty_rate = len(empty) / max(sum(total_by_model.values()), 1) * 100
print(f"\nEmpty rate: {empty_rate:.1f}%")
if empty_rate > 5:
    print("WARNING: >5% empty episodes — investigate")
elif empty_rate > 0:
    print("INFO: Some empty episodes (expected for difficult scenarios)")
else:
    print("OK: No empty episodes")
```

## Check 2: 실행 시간 추정 보정

```python
# scripts/midrun_timing.py
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

OUTPUT = Path("results/full_690")
MODELS = ["oss120b", "qwen35b", "qwen27b", "qwen4b", "qwen397b"]
TARGET_PER_MODEL = 2070

for model in MODELS:
    model_dir = OUTPUT / model
    if not model_dir.exists():
        continue
    
    files = sorted(model_dir.glob("*.json"))
    if len(files) < 2:
        print(f"{model}: Not enough episodes for timing estimate")
        continue
    
    # 파일 modification time으로 추정
    first_mtime = files[0].stat().st_mtime
    last_mtime = files[-1].stat().st_mtime
    elapsed_seconds = last_mtime - first_mtime
    elapsed_hours = elapsed_seconds / 3600
    
    completed = len(files)
    remaining = TARGET_PER_MODEL - completed
    
    if completed > 0 and elapsed_seconds > 0:
        rate = completed / elapsed_hours  # episodes per hour
        eta_hours = remaining / rate
        
        print(f"{model}:")
        print(f"  Completed: {completed}/{TARGET_PER_MODEL} ({completed/TARGET_PER_MODEL*100:.1f}%)")
        print(f"  Elapsed: {elapsed_hours:.1f}h")
        print(f"  Rate: {rate:.1f} episodes/hour ({60/rate:.1f} min/episode)")
        print(f"  ETA: {eta_hours:.1f}h ({eta_hours/24:.1f} days)")
    else:
        print(f"{model}: {completed} episodes, timing N/A")

print(f"\nWall-clock ETA = max(model ETAs)")
```

## Check 3: Scoring 정상 작동 — Violation이 실제로 탐지되는가

```python
# scripts/midrun_violations.py
import json
from pathlib import Path
from collections import defaultdict, Counter

OUTPUT = Path("results/full_690")

violation_counts = Counter()
model_violations = defaultdict(list)
scenarios_with_violations = set()
scenarios_without = set()

for model_dir in OUTPUT.iterdir():
    if not model_dir.is_dir():
        continue
    model = model_dir.name
    
    for f in model_dir.glob("*.json"):
        try:
            with open(f) as fh:
                ep = json.load(fh)
        except:
            continue
        
        scenario = ep.get("scenario_id", "unknown")
        
        # violation 추출 (JSON 구조에 따라 key 조정)
        violations = ep.get("new_total_violations", ep.get("total_violations", 0))
        violation_types = ep.get("new_violations_by_type", ep.get("violations_by_type", {}))
        
        model_violations[model].append(violations)
        
        if violations > 0:
            scenarios_with_violations.add(scenario)
            for vtype, count in violation_types.items() if isinstance(violation_types, dict) else []:
                violation_counts[vtype] += count
        else:
            scenarios_without.add(scenario)

print("=" * 60)
print("MIDRUN VIOLATION CHECK")
print("=" * 60)

for model in sorted(model_violations.keys()):
    viols = model_violations[model]
    has_viol = sum(1 for v in viols if v > 0)
    pct = has_viol / len(viols) * 100 if viols else 0
    avg = sum(viols) / len(viols) if viols else 0
    print(f"\n{model}:")
    print(f"  Episodes: {len(viols)}")
    print(f"  With violations: {has_viol} ({pct:.0f}%)")
    print(f"  Avg violations: {avg:.1f}")

print(f"\nViolation types:")
for vtype, count in violation_counts.most_common():
    print(f"  {vtype}: {count}")

print(f"\nScenarios with at least 1 violation (any model): {len(scenarios_with_violations)}")
print(f"Scenarios with 0 violations (all models): {len(scenarios_without - scenarios_with_violations)}")

# 위험 신호: violation이 전혀 없으면 scoring이 안 되고 있는 것
if not any(v > 0 for viols in model_violations.values() for v in viols):
    print("\n*** CRITICAL: No violations detected in any episode! ***")
    print("Scoring may not be working. Check scorer pipeline.")
```

## Check 4: Model 간 행동 차이 — 같은 시나리오에서 다른 결과를 내는가

```python
# scripts/midrun_model_diversity.py
import json
from pathlib import Path
from collections import defaultdict

OUTPUT = Path("results/full_690")

# 시나리오별, 모델별 compliance score 수집
scores = defaultdict(dict)  # {scenario: {model: [scores]}}

for model_dir in OUTPUT.iterdir():
    if not model_dir.is_dir():
        continue
    model = model_dir.name
    
    for f in model_dir.glob("*.json"):
        try:
            with open(f) as fh:
                ep = json.load(fh)
        except:
            continue
        
        scenario = ep.get("scenario_id", "")
        score = ep.get("new_compliance_score", ep.get("compliance_score", None))
        
        if scenario and score is not None:
            scores[scenario].setdefault(model, []).append(score)

# 시나리오별 모델 간 score 차이
interesting = []
for scenario, model_scores in scores.items():
    if len(model_scores) < 2:
        continue
    
    model_avgs = {m: sum(s)/len(s) for m, s in model_scores.items()}
    spread = max(model_avgs.values()) - min(model_avgs.values())
    
    if spread > 0.3:  # 30% 이상 차이
        best = max(model_avgs, key=model_avgs.get)
        worst = min(model_avgs, key=model_avgs.get)
        interesting.append({
            "scenario": scenario,
            "spread": spread,
            "best": f"{best}={model_avgs[best]:.2f}",
            "worst": f"{worst}={model_avgs[worst]:.2f}",
        })

interesting.sort(key=lambda x: -x["spread"])

print("=" * 60)
print("MODEL DIVERSITY CHECK")
print("=" * 60)
print(f"\nScenarios with >30% model spread: {len(interesting)}")
for item in interesting[:15]:
    print(f"  {item['scenario']}: spread={item['spread']:.2f} (best={item['best']}, worst={item['worst']})")

if not interesting:
    print("No significant model diversity yet (may need more episodes)")
```

## Check 5: Evaluator Disagreement 미리보기

```python
# scripts/midrun_evaluator_preview.py
"""
기존 6개 evaluator의 verdict를 현재 episodes에서 계산해보기.
Episode JSON에 이미 scoring 결과가 있으므로 추출만 하면 됨.
"""
import json
from pathlib import Path
from collections import defaultdict

OUTPUT = Path("results/full_690")

# Episode별 evaluator verdict 추출
# JSON 구조에 따라 key 조정 필요
episode_verdicts = []

for model_dir in OUTPUT.iterdir():
    if not model_dir.is_dir():
        continue
    
    for f in list(model_dir.glob("*.json"))[:50]:  # 모델당 50개만 샘플
        try:
            with open(f) as fh:
                ep = json.load(fh)
        except:
            continue
        
        # 가능한 score 필드들
        c2 = ep.get("new_compliance_score", ep.get("compliance_score"))
        violations = ep.get("new_total_violations", ep.get("total_violations", 0))
        sub_scores = ep.get("new_sub_scores", ep.get("sub_scores", {}))
        
        if c2 is not None:
            episode_verdicts.append({
                "scenario": ep.get("scenario_id"),
                "model": model_dir.name,
                "c2": c2,
                "violations": violations,
                "sub_scores": sub_scores,
            })

print(f"Sampled {len(episode_verdicts)} episodes for evaluator preview")

if episode_verdicts:
    # C2 score 분포
    c2_scores = [e["c2"] for e in episode_verdicts if e["c2"] is not None]
    print(f"\nC2 (compliance) distribution:")
    print(f"  min={min(c2_scores):.3f}, max={max(c2_scores):.3f}, mean={sum(c2_scores)/len(c2_scores):.3f}")
    
    # C2 >= 0.7 (pass) vs < 0.7 (fail)
    pass_c2 = sum(1 for s in c2_scores if s >= 0.7)
    print(f"  Pass (C2>=0.7): {pass_c2}/{len(c2_scores)} ({pass_c2/len(c2_scores)*100:.0f}%)")
    
    # Violation 분포
    viols = [e["violations"] for e in episode_verdicts]
    print(f"\nViolation distribution:")
    print(f"  0 violations: {sum(1 for v in viols if v == 0)} ({sum(1 for v in viols if v == 0)/len(viols)*100:.0f}%)")
    print(f"  1-3 violations: {sum(1 for v in viols if 0 < v <= 3)}")
    print(f"  4+ violations: {sum(1 for v in viols if v > 3)}")
```

## Check 6: 기존 181 episodes와의 일관성

```python
# scripts/midrun_consistency.py
"""
기존 clean_slate_rescored의 시나리오 중 현재 실행에도 포함된 것이 있으면,
같은 모델의 score가 비슷한 범위인지 확인.
(완전 동일하지는 않음 — graph가 V2로 바뀌었으므로. 하지만 극단적 차이는 문제)
"""
import json
from pathlib import Path
from collections import defaultdict

old_dir = Path("results/clean_slate_rescored")
new_dir = Path("results/full_690")

# 기존 episode의 score
old_scores = defaultdict(dict)
for f in old_dir.glob("**/*.json"):
    try:
        with open(f) as fh:
            ep = json.load(fh)
        scenario = ep.get("scenario_id", "")
        model = ep.get("model_name", "").lower()
        score = ep.get("new_compliance_score", ep.get("compliance_score"))
        if scenario and score is not None:
            old_scores[scenario][model] = score
    except:
        pass

# 새 episode의 score
new_scores = defaultdict(dict)
for model_dir in new_dir.iterdir():
    if not model_dir.is_dir():
        continue
    for f in model_dir.glob("*.json"):
        try:
            with open(f) as fh:
                ep = json.load(fh)
            scenario = ep.get("scenario_id", "")
            score = ep.get("new_compliance_score", ep.get("compliance_score"))
            if scenario and score is not None:
                new_scores[scenario].setdefault(model_dir.name, []).append(score)
        except:
            pass

# 비교
print("Old vs New Score Comparison (overlapping scenarios)")
print("=" * 60)

comparisons = 0
large_diffs = []

for scenario in old_scores:
    if scenario not in new_scores:
        continue
    for old_model, old_score in old_scores[scenario].items():
        # model name 매핑 (기존 이름 → 현재 디렉토리 이름)
        for new_model, new_score_list in new_scores[scenario].items():
            if old_model.replace("-", "").replace(".", "") in new_model.replace("-", "").replace(".", ""):
                new_avg = sum(new_score_list) / len(new_score_list)
                diff = abs(new_avg - old_score)
                comparisons += 1
                if diff > 0.3:
                    large_diffs.append(f"{scenario} ({old_model}): old={old_score:.3f}, new={new_avg:.3f}, diff={diff:.3f}")

print(f"Comparisons: {comparisons}")
print(f"Large differences (>0.3): {len(large_diffs)}")
for d in large_diffs[:10]:
    print(f"  {d}")

if not large_diffs:
    print("OK: No large score differences")
```

---

**6개 check를 모두 실행하고 결과를 raw로 보고하라.** 특히:
- Check 1: empty episode 비율
- Check 2: ETA 보정값
- Check 3: violation 탐지 여부 (0이면 critical)
- Check 5: C2 pass rate, violation 분포