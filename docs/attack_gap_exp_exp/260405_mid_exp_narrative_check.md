# 중간 결과 분석: 논문 narrative 생존 확인

> qwen27b 1,693 + qwen35b 1,654 = 3,347 episodes로 핵심 수치 preview.
> 전체 완료 전에 "narrative가 살아있는지" 확인하는 것이 목적.
> 최종 수치는 전체 완료 후 update_all_auto_numbers.py로 갱신.

---

## 1. 핵심 수치 빠른 preview

논문의 생사를 결정하는 숫자 5개를 먼저 뽑는다.

```python
#!/usr/bin/env python3
"""
Quick narrative check: 5 critical numbers from partial episodes.
"""
import json, glob, os, sys
from collections import Counter, defaultdict

sys.path.insert(0, '.')

EPISODES_DIR = "results/full_706_v5"

# Load all available episodes
episodes = []
for model_dir in sorted(glob.glob(os.path.join(EPISODES_DIR, "*"))):
    if not os.path.isdir(model_dir):
        continue
    model = os.path.basename(model_dir)
    for f in sorted(glob.glob(os.path.join(model_dir, "*.json"))):
        try:
            ep = json.load(open(f))
            ep['_model'] = model
            episodes.append(ep)
        except:
            continue

print(f"=== Loaded {len(episodes)} episodes from {len(set(e['_model'] for e in episodes))} models ===\n")

# --- NUMBER 1: All-process-oblivious false-accept ---
# Episodes that pass ALL action-set evaluators but have hard violations
n_hard_viol = 0
n_all_oblivious_pass = 0
n_all_oblivious_pass_and_hard = 0

for ep in episodes:
    violations = ep.get('violation_events', [])
    hard_viols = [v for v in violations if isinstance(v, dict) and 
                  v.get('severity', v.get('type', '')).upper() in 
                  ('HARD', 'FORBIDDEN', 'WITHIN', 'BEFORE', 'CRITICAL')]
    has_hard = len(hard_viols) > 0
    if has_hard:
        n_hard_viol += 1
    
    # Check evaluator verdicts (try multiple field names)
    compliance = ep.get('compliance_score', 0)
    # TCC: hard violation = fail
    tcc_pass = not has_hard
    
    # Action-set evaluators: approximate from available fields
    # Try to find individual evaluator results
    ac_pass = None
    mab_pass = None
    cwt_pass = None
    
    for key_prefix in ['ac_proxy', 'action_coverage', 'asc']:
        for key in [f'{key_prefix}_pass', f'{key_prefix}_score']:
            if key in ep:
                val = ep[key]
                ac_pass = bool(val) if isinstance(val, bool) else (val >= 0.5 if isinstance(val, (int, float)) else None)
                break
    
    for key_prefix in ['mab_proxy', 'mab_f1', 'paf']:
        for key in [f'{key_prefix}_pass', f'{key_prefix}_score']:
            if key in ep:
                val = ep[key]
                mab_pass = bool(val) if isinstance(val, bool) else (val >= 0.5 if isinstance(val, (int, float)) else None)
                break
    
    for key_prefix in ['c2', 'cwt', 'coverage_timing']:
        for key in [f'{key_prefix}_pass', f'{key_prefix}_score']:
            if key in ep:
                val = ep[key]
                cwt_pass = bool(val) if isinstance(val, bool) else (val >= 0.7 if isinstance(val, (int, float)) else None)
                break
    
    # If we can't find individual evaluator fields, use compliance_score as proxy
    if ac_pass is None and compliance is not None:
        ac_pass = compliance >= 0.5
    if cwt_pass is None and compliance is not None:
        cwt_pass = compliance >= 0.7
    
    all_oblivious_pass = (ac_pass == True) and (cwt_pass == True)
    # DxEM/TOM always passes, so we don't check it
    
    if all_oblivious_pass:
        n_all_oblivious_pass += 1
        if has_hard:
            n_all_oblivious_pass_and_hard += 1

fa_all = n_all_oblivious_pass_and_hard / max(len(episodes), 1) * 100
print(f"NUMBER 1: All-oblivious FA = {fa_all:.1f}%")
print(f"  ({n_all_oblivious_pass_and_hard} episodes pass all action-set evaluators AND have hard violations)")
print(f"  Total hard-violating: {n_hard_viol}/{len(episodes)} ({n_hard_viol/max(len(episodes),1)*100:.1f}%)")
print(f"  All-oblivious pass: {n_all_oblivious_pass}/{len(episodes)}")

# --- NUMBER 2: Verdict-flip rate ---
# At least one evaluator pair disagrees
n_flip = 0
for ep in episodes:
    violations = ep.get('violation_events', [])
    has_hard = any(isinstance(v, dict) and v.get('severity','').upper() in ('HARD','FORBIDDEN','WITHIN','BEFORE','CRITICAL') for v in violations)
    compliance = ep.get('compliance_score', 0)
    
    tcc_pass = not has_hard
    approx_ac_pass = compliance >= 0.5 if compliance is not None else True
    
    if tcc_pass != approx_ac_pass:
        n_flip += 1

vf_rate = n_flip / max(len(episodes), 1) * 100
print(f"\nNUMBER 2: Verdict-flip rate ≈ {vf_rate:.1f}%")

# --- NUMBER 3: Hard violation prevalence ---
hard_pct = n_hard_viol / max(len(episodes), 1) * 100
print(f"\nNUMBER 3: Hard violation prevalence = {hard_pct:.1f}%")

# --- NUMBER 4: Violation type distribution ---
viol_types = Counter()
for ep in episodes:
    for v in ep.get('violation_events', []):
        if isinstance(v, dict):
            vtype = v.get('type', v.get('constraint_type', 'UNKNOWN')).upper()
            viol_types[vtype] += 1

print(f"\nNUMBER 4: Violation types")
for vtype, count in viol_types.most_common():
    print(f"  {vtype}: {count}")

# --- NUMBER 5: Model ranking (pass rate by model) ---
print(f"\nNUMBER 5: Model pass rates")
model_stats = defaultdict(lambda: {'total': 0, 'hard_viol': 0, 'compliance_sum': 0})
for ep in episodes:
    model = ep['_model']
    model_stats[model]['total'] += 1
    violations = ep.get('violation_events', [])
    has_hard = any(isinstance(v, dict) and v.get('severity','').upper() in ('HARD','FORBIDDEN','WITHIN','BEFORE','CRITICAL') for v in violations)
    if has_hard:
        model_stats[model]['hard_viol'] += 1
    model_stats[model]['compliance_sum'] += (ep.get('compliance_score', 0) or 0)

for model in sorted(model_stats):
    s = model_stats[model]
    tcc_pass = (s['total'] - s['hard_viol']) / max(s['total'], 1) * 100
    avg_compliance = s['compliance_sum'] / max(s['total'], 1)
    print(f"  {model:15s}: n={s['total']:5d}, TCC_pass={tcc_pass:.1f}%, avg_compliance={avg_compliance:.3f}, hard_viol={s['hard_viol']}")

# --- NARRATIVE CHECK ---
print(f"\n{'='*60}")
print(f"NARRATIVE SURVIVAL CHECK")
print(f"{'='*60}")
if fa_all > 5:
    print(f"✅ All-oblivious FA = {fa_all:.1f}% → 논문 핵심 주장 생존")
elif fa_all > 1:
    print(f"⚠️ All-oblivious FA = {fa_all:.1f}% → 주장 약화, framing 조정 필요")
else:
    print(f"🔴 All-oblivious FA = {fa_all:.1f}% → 심각한 narrative 위기")

if hard_pct > 20:
    print(f"✅ Hard violation prevalence = {hard_pct:.1f}% → blind spot이 실재")
elif hard_pct > 5:
    print(f"⚠️ Hard violation prevalence = {hard_pct:.1f}% → 약하지만 유의미")
else:
    print(f"🔴 Hard violation prevalence = {hard_pct:.1f}% → blind spot이 드묾")

if len(viol_types) >= 3:
    print(f"✅ Violation diversity = {len(viol_types)} types → 다양한 blind spot")
else:
    print(f"⚠️ Violation diversity = {len(viol_types)} types → 단일 유형 편중 우려")
```

---

## 2. E7 Paired Delta (중간 결과)

이미 검증된 스크립트를 현재 에피소드로 다시 실행.

```bash
PYTHONPATH=. python scripts/experiments/run_paired_delta_analysis.py \
  --episodes-dir results/full_706_v5 \
  --output evidence_pack/analysis/paired_delta_preview.json
```

주목할 수치:
- manual FA vs auto FA 차이 → engine necessity
- Newly exposed violation types → engine이 뭘 더 잡는지

---

## 3. Held-out vs In-domain (중간 결과)

```bash
PYTHONPATH=. python scripts/experiments/run_heldout_episode_analysis.py \
  --episodes-dir results/full_706_v5 \
  --output evidence_pack/analysis/heldout_preview.json
```

주목할 수치:
- held-out FA rate ≈ in-domain FA rate → generalization claim 생존
- held-out에도 다양한 violation type → paper-level claim 유지

---

## 4. Timing Validity Audit (중간 결과)

```bash
PYTHONPATH=. python scripts/experiments/run_timing_validity_audit.py \
  --episodes-dir results/full_706_v5 \
  --output evidence_pack/analysis/timing_audit_preview.json
```

주목할 수치:
- median margin past deadline → 크면 genuine delay (좋음)
- boundary clustering % → 낮으면 artifact 아님 (좋음)
- cross-model Jaccard → 높으면 scenario-driven (좋음)

---

## 5. E8 Replay (qwen27b + qwen35b만으로)

```bash
# MAB replay
PYTHONPATH=. python scripts/experiments/v3_p1b_medagentbench_replay.py \
  --episodes-dir results/full_706_v5 \
  --output evidence_pack/analysis/e8_mab_replay_preview.json

# AC replay
PYTHONPATH=. python scripts/experiments/v3_p1a_agentclinic_replay.py \
  --episodes-dir results/full_706_v5 \
  --output evidence_pack/analysis/e8_ac_replay_preview.json
```

주목할 수치:
- MAB-F1 pass 중 TCC fail % → cross-benchmark blind spot 확인
- AC-Diag pass 중 TCC fail % → 같은 패턴

---

## 6. Episode JSON 구조 상세 확인

위 스크립트가 실패할 경우를 대비해, episode JSON의 정확한 필드 구조를 먼저 파악.

```bash
echo "=== Episode JSON field 심층 분석 ==="
python3 -c "
import json, glob, os

# 각 모델에서 1개씩 샘플
for model_dir in sorted(glob.glob('results/full_706_v5/*/')):
    model = os.path.basename(model_dir.rstrip('/'))
    files = sorted(glob.glob(os.path.join(model_dir, '*.json')))
    if not files:
        continue
    ep = json.load(open(files[0]))
    print(f'\\n=== {model} ({len(files)} episodes) ===')
    print(f'Keys: {sorted(ep.keys())}')
    
    # Actions
    actions = ep.get('actions', [])
    if actions:
        print(f'actions: {len(actions)} items')
        if isinstance(actions[0], dict):
            print(f'  action[0] keys: {sorted(actions[0].keys())}')
            print(f'  action[0]: {json.dumps(actions[0])[:200]}')
        else:
            print(f'  action[0]: {actions[0]}')
    
    # Violations
    viols = ep.get('violation_events', [])
    if viols:
        print(f'violation_events: {len(viols)} items')
        if isinstance(viols[0], dict):
            print(f'  viol[0] keys: {sorted(viols[0].keys())}')
            print(f'  viol[0]: {json.dumps(viols[0])[:200]}')
    
    # Score fields
    for k in sorted(ep.keys()):
        if 'score' in k.lower() or 'pass' in k.lower() or 'rate' in k.lower() or 'verdict' in k.lower():
            print(f'{k}: {ep[k]}')
"
```

---

## 7. 보고 형식

```markdown
## 중간 결과 Narrative Check (N=3,347 episodes)

| 수치 | 값 | 논문 생존? |
|------|-----|----------|
| All-oblivious FA | X% | ✅/⚠️/🔴 |
| Hard violation prevalence | X% | ✅/⚠️/🔴 |
| Verdict-flip rate | X% | ✅/⚠️/🔴 |
| Timing dominant? | WITHIN X%, FORBIDDEN Y% | ✅/⚠️ |
| Model ordering consistent? | [ranking] | ✅/⚠️ |

### E7 Paired Delta
| | Manual | Auto | Δ |
|---|--------|------|---|
| FA rate | X% | Y% | +Z pp |

### Timing Audit
| | Value |
|---|------|
| Median margin | X min |
| Boundary clustered | X% |
| Cross-model Jaccard | X |

### E8 Replay
| Scorer | Blind-spot rate |
|--------|----------------|
| MAB-F1 | X% |
| AC-Diag | X% |

### 조기 경보
- [있으면 기재: 예상과 크게 다른 수치, narrative 위험 등]
```