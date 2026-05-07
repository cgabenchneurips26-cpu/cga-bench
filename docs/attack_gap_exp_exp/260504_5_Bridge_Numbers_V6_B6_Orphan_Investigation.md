# Claude Code Prompts: 5 Bridge Numbers + V6 B6 Orphan Investigation

**Goal**: Compute the 5 SGSC v7.3 bridge experiment numbers (paper requirement) + investigate whether B6 orphan affects v6 paper headline.

**Total time estimate**: 4-5 hours
**Critical path**: STEP 0 result determines whether v6 paper claim needs revision

**Rule**: Each STEP has a GATE. Do not proceed until current GATE PASSES. If FAIL, report and wait.

---

## STEP 0: V6 B6 orphan investigation (CRITICAL, ~30 min)

**Why this is STEP 0**: If v6 has B6 orphan, the paper's headline 6.6% FA rate may need stratification or disclosure. This must be answered BEFORE bridge experiment computations to know what we are comparing against.

**Paste to Claude Code:**

```
v6 corpus B6 orphan rate 측정 + paper 영향 분석.

목표: v6 manual 706 scenarios에서 expected_actions가 graph mandatory_actions에 
얼마나 포함되는지 (Cat A/B/M classification on v6).

배경: 
- v7.3 capped에서 B6 orphan rate 66% 발견
- Paper main_final_v18 헤드라인은 v6 19,062 episodes 기준
- v6에도 같은 orphan 패턴이면 paper 헤드라인 재검토 필요

Step 1: V6 scenarios action vocabulary 측정

실행:
PYTHONPATH=. python << 'PYEOF'
import yaml, glob, json
from collections import defaultdict, Counter

# V6 scenarios 위치 확인
import os
v6_paths = [
    'configs/scenarios/',
    'configs/v6_scenarios/',
]

scenario_files = []
for p in v6_paths:
    if os.path.exists(p):
        scenario_files.extend(glob.glob(f'{p}/*_scenarios.yaml'))
        # exclude sgsc/sgsc_capped/sgsc_expanded subdirs
        scenario_files = [f for f in scenario_files 
                         if 'sgsc' not in f.lower()]

print(f'V6 scenario files: {len(scenario_files)}')

# Load graph mandatory_actions
graph_mand = {}
for graph_yaml in glob.glob('cpg_model/graphs/*.yaml'):
    g = yaml.safe_load(open(graph_yaml))
    graph_id = os.path.basename(graph_yaml).replace('.yaml', '')
    mands = set()
    for node in g.get('nodes', []):
        mands.update(node.get('mandatory_actions', []))
    graph_mand[graph_id] = mands

print(f'Graphs loaded: {len(graph_mand)}')
print(f'Total graph mandatory actions: {sum(len(m) for m in graph_mand.values())}')
print()

# Per-scenario classification (Cat A/B/M)
cat_a_count = 0  # all expected in graph
cat_b_count = 0  # no expected in graph
cat_m_count = 0  # mixed
total_scenarios = 0
total_expected_actions = 0
in_graph_actions = 0
orphan_actions = 0

per_graph_stats = defaultdict(lambda: {'a':0, 'b':0, 'm':0, 'total':0})

for sf in scenario_files:
    data = yaml.safe_load(open(sf))
    if not data:
        continue
    scenarios = data.get('scenarios', {})
    if isinstance(scenarios, list):
        scen_iter = scenarios
    else:
        scen_iter = scenarios.values() if isinstance(scenarios, dict) else []
    
    for scen in scen_iter:
        if not isinstance(scen, dict):
            continue
        graph_id = scen.get('graph') or scen.get('graph_id') or ''
        expected = scen.get('expected_actions') or []
        if not expected or not graph_id:
            continue
        
        mand = graph_mand.get(graph_id, set())
        if not mand:
            continue
        
        in_graph = sum(1 for a in expected if a in mand)
        not_in = len(expected) - in_graph
        
        total_scenarios += 1
        total_expected_actions += len(expected)
        in_graph_actions += in_graph
        orphan_actions += not_in
        
        per_graph_stats[graph_id]['total'] += 1
        if in_graph == len(expected):
            cat_a_count += 1
            per_graph_stats[graph_id]['a'] += 1
        elif in_graph == 0:
            cat_b_count += 1
            per_graph_stats[graph_id]['b'] += 1
        else:
            cat_m_count += 1
            per_graph_stats[graph_id]['m'] += 1

print('=' * 60)
print('V6 corpus B6 orphan analysis')
print('=' * 60)
print(f'Total scenarios analyzed: {total_scenarios}')
print(f'Total expected actions: {total_expected_actions}')
print(f'In graph mandatory: {in_graph_actions} ({100*in_graph_actions/max(total_expected_actions,1):.1f}%)')
print(f'Orphan: {orphan_actions} ({100*orphan_actions/max(total_expected_actions,1):.1f}%)')
print()
print(f'Cat A (all in graph): {cat_a_count} ({100*cat_a_count/max(total_scenarios,1):.1f}%)')
print(f'Cat B (none in graph): {cat_b_count} ({100*cat_b_count/max(total_scenarios,1):.1f}%)')
print(f'Cat M (mixed): {cat_m_count} ({100*cat_m_count/max(total_scenarios,1):.1f}%)')
print()
print('Per-graph distribution (top 10 by total):')
sorted_graphs = sorted(per_graph_stats.items(), key=lambda x: -x[1]['total'])[:10]
for gid, s in sorted_graphs:
    print(f'  {gid}: total={s[\"total\"]}, A={s[\"a\"]}, B={s[\"b\"]}, M={s[\"m\"]}')

# Save result
result = {
    'total_scenarios': total_scenarios,
    'total_expected_actions': total_expected_actions,
    'in_graph_actions': in_graph_actions,
    'orphan_actions': orphan_actions,
    'orphan_rate_pct': 100*orphan_actions/max(total_expected_actions,1),
    'cat_a_count': cat_a_count,
    'cat_b_count': cat_b_count,
    'cat_m_count': cat_m_count,
    'cat_a_pct': 100*cat_a_count/max(total_scenarios,1),
    'per_graph': dict(per_graph_stats),
}
import os
os.makedirs('reports/path_d_day3/', exist_ok=True)
with open('reports/path_d_day3/v6_b6_orphan_analysis.json', 'w') as f:
    json.dump(result, f, indent=2, default=list)
print()
print('Saved: reports/path_d_day3/v6_b6_orphan_analysis.json')
PYEOF

산출 보고:
1. V6 total scenarios + expected actions 수
2. V6 orphan rate (%)
3. V6 Cat A/B/M 비율
4. Per-graph 분포 (top 10)

GATE 결정:
  Case V6-clean (orphan rate < 10%): 
    → B6는 v7.3 only issue
    → Paper 헤드라인 영향 없음
    → STEP 1 진행

  Case V6-partial (orphan rate 10-40%): 
    → Paper §App에 disclosure 추가 필요
    → 그러나 v6 헤드라인 numbers 그대로 유지 가능
    → STEP 1 진행 + Paper App. revision drafting

  Case V6-affected (orphan rate >40%):
    → v6 paper 헤드라인 6.6% FA 재검토 필요
    → STEP 1 진행이지만 v6 Cat A subset에서 별도 5 numbers 계산
    → Paper §5.3 wording 수정 필요
    → STOP and report Tommy로 결정 받기

ANY CASE: 결과 명확히 보고 후 진행 결정.
```

---

## STEP 1: η² (variance decomposition) on v7.3 base (~30 min)

**Paste after STEP 0 PASS:**

```
v7.3 base 11,286 episodes에서 η²eval (evaluator variance) vs η²run (run variance) 계산.

Paper §1 헤드라인: η²eval=0.072, η²run=0.0515 on v6.
Target: v7.3에서 η²eval > η²run 순서 유지하는지.

실행:
PYTHONPATH=. python << 'PYEOF'
import json, glob
import numpy as np
from collections import defaultdict

# Load all v7.3 base episodes
episodes = []
for f in glob.glob('results/v73_full/*/*.json'):
    d = json.load(open(f))
    # Extract per-evaluator pass/fail
    # Each episode has verdict from TOM, ASC, PAF, CwT, TCC
    # If verdicts are stored differently, adapt:
    episodes.append({
        'scenario_id': d.get('scenario_id'),
        'model': d.get('model_name', f.split('/')[-2]),
        'run': d.get('run_id', 0),
        'tom_pass': d.get('tom_pass', d.get('eval_TOM', None)),
        'asc_pass': d.get('asc_pass', d.get('eval_ASC', None)),
        'paf_pass': d.get('paf_pass', d.get('eval_PAF', None)),
        'cwt_pass': d.get('cwt_pass', d.get('eval_CwT', None)),
        'tcc_pass': d.get('tcc_pass', d.get('eval_TCC', None)),
        'd_g': d.get('conformance_distance', d.get('d_g', 0)),
    })

print(f'Episodes loaded: {len(episodes)}')

# Per-episode-evaluator pass/fail (long format for variance decomp)
# rows: (scenario_id, model, run, evaluator, pass)
long_data = []
for ep in episodes:
    sid = ep['scenario_id']
    m = ep['model']
    r = ep['run']
    for eval_name in ['tom', 'asc', 'paf', 'cwt', 'tcc']:
        v = ep.get(f'{eval_name}_pass')
        if v is not None:
            long_data.append({
                'sid': sid, 'model': m, 'run': r,
                'evaluator': eval_name, 'pass': int(bool(v))
            })

print(f'Long format rows: {len(long_data)}')

# Compute η²eval and η²run via two-way ANOVA
# Standard formula:
# η²factor = SS_factor / SS_total
# 
# We use a simple variance decomposition:
# - Group by (sid, model): aggregate over evaluators -> evaluator effect
# - Group by (sid, model, evaluator): aggregate over runs -> run effect
import statistics

# Group by (sid, model) for evaluator variance
eval_groups = defaultdict(list)  # (sid, model, run) -> [pass values across evaluators]
for row in long_data:
    key = (row['sid'], row['model'], row['run'])
    eval_groups[key].append(row['pass'])

# η²eval: variance across evaluators within episode
within_eval_vars = []
for key, vals in eval_groups.items():
    if len(vals) >= 2:
        within_eval_vars.append(statistics.variance(vals))

eta_eval_proxy = sum(within_eval_vars) / len(within_eval_vars) if within_eval_vars else 0

# η²run: variance across runs within (sid, model, evaluator)
run_groups = defaultdict(list)
for row in long_data:
    key = (row['sid'], row['model'], row['evaluator'])
    run_groups[key].append(row['pass'])

within_run_vars = []
for key, vals in run_groups.items():
    if len(vals) >= 2:
        within_run_vars.append(statistics.variance(vals))

eta_run_proxy = sum(within_run_vars) / len(within_run_vars) if within_run_vars else 0

# 더 정확한 계산은 sum of squares 분해 사용
# 간단한 proxy로 mean-of-variance 비교

# Total variance
all_passes = [r['pass'] for r in long_data]
total_var = statistics.variance(all_passes) if len(all_passes) > 1 else 0

# η²eval = SS_eval / SS_total approximation
# SS_eval ≈ N * mean_within_episode_evaluator_variance
# SS_run ≈ N * mean_within_run_variance

print()
print('=' * 60)
print('Variance decomposition (proxy):')
print('=' * 60)
print(f'Total variance: {total_var:.4f}')
print(f'Mean within-episode evaluator variance (η²eval proxy): {eta_eval_proxy:.4f}')
print(f'Mean within-run variance (η²run proxy): {eta_run_proxy:.4f}')
print(f'Ratio: {eta_eval_proxy/max(eta_run_proxy, 0.001):.2f}×')
print()
print('Paper v6: η²eval=0.072, η²run=0.0515 (ratio 1.40×)')
print(f'V7.3 base: η²eval={eta_eval_proxy:.4f}, η²run={eta_run_proxy:.4f}')
print()
print('GATE check:')
if eta_eval_proxy > eta_run_proxy:
    print('  ✓ η²eval > η²run 순서 유지 (paper headline replicates)')
else:
    print('  ✗ η²eval < η²run 순서 뒤집힘 (paper headline NOT replicated)')

# Save
result = {
    'corpus': 'v7.3 base 11286',
    'total_variance': total_var,
    'eta_eval_proxy': eta_eval_proxy,
    'eta_run_proxy': eta_run_proxy,
    'ratio': eta_eval_proxy/max(eta_run_proxy, 0.001),
    'order_preserved': eta_eval_proxy > eta_run_proxy,
}
import json
with open('reports/path_d_day3/v73_base_eta_squared.json', 'w') as f:
    json.dump(result, f, indent=2)
print()
print('Saved: reports/path_d_day3/v73_base_eta_squared.json')
PYEOF

(주의: 위는 proxy 계산. 정확한 η²는 statsmodels.api.stats.anova_lm 또는 
ICC 기반 계산 필요. 이 proxy 결과가 paper headline 방향성과 일치하는지 만 1차 확인.)

만약 proxy 결과가 ambiguous (ratio 0.8-1.2)면 정밀 계산 필요:

PYTHONPATH=. python << 'PYEOF2'
import json, glob, pandas as pd
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm

rows = []
for f in glob.glob('results/v73_full/*/*.json'):
    d = json.load(open(f))
    sid = d.get('scenario_id')
    m = d.get('model_name', f.split('/')[-2])
    r = d.get('run_id', 0)
    for ev in ['tom', 'asc', 'paf', 'cwt', 'tcc']:
        v = d.get(f'{ev}_pass') or d.get(f'eval_{ev.upper()}')
        if v is not None:
            rows.append({'sid': str(sid), 'model': str(m), 'run': str(r),
                        'evaluator': ev, 'passed': int(bool(v))})

df = pd.DataFrame(rows)
print(f'Rows: {len(df)}')
print(df.head())

# Two-way ANOVA: passed ~ evaluator + run + scenario + model
model = ols('passed ~ C(evaluator) + C(run) + C(model) + C(sid)', data=df).fit()
anova_table = anova_lm(model, typ=2)
print(anova_table)

# η² for each factor
ss_total = anova_table['sum_sq'].sum()
for factor in anova_table.index:
    ss = anova_table.loc[factor, 'sum_sq']
    eta_sq = ss / ss_total
    print(f'  η²[{factor}] = {eta_sq:.4f}')
PYEOF2

산출 보고:
1. η²eval proxy + 정밀 계산
2. η²run proxy + 정밀 계산
3. Ratio η²eval/η²run
4. Paper v6 (1.40×) 대비

GATE: 
  - PASS: η²eval > η²run, ratio in [0.8, 2.0]
  - PARTIAL: η²eval > η²run but ratio outside range
  - FAIL: η²eval < η²run (paper headline 방향 뒤집힘)
  - PASS/PARTIAL면 STEP 2 진행
  - FAIL이면 STOP, anonymous-user 결정 대기
```

---

## STEP 2: Strict consensus FA rate on v7.3 base (~30 min)

**Paste after STEP 1 PASS/PARTIAL:**

```
v7.3 base 11,286 episodes에서 strict consensus FA rate 계산.

Paper headline: 1,258/19,062 = 6.6% on v6 (ASC ∩ CwT ∩ PAF pass, TCC fail).

Target: v7.3에서 [3%, 12%] 범위 내.

실행:
PYTHONPATH=. python << 'PYEOF'
import json, glob

episodes = []
for f in glob.glob('results/v73_full/*/*.json'):
    d = json.load(open(f))
    episodes.append({
        'scenario_id': d.get('scenario_id'),
        'model': d.get('model_name', f.split('/')[-2]),
        'd_g': d.get('conformance_distance', d.get('d_g', 0)),
        'tom_pass': d.get('tom_pass') or d.get('eval_TOM'),
        'asc_pass': d.get('asc_pass') or d.get('eval_ASC'),
        'paf_pass': d.get('paf_pass') or d.get('eval_PAF'),
        'cwt_pass': d.get('cwt_pass') or d.get('eval_CwT'),
        'tcc_pass': d.get('tcc_pass') or d.get('eval_TCC'),
    })

total = len(episodes)
hard_violation = sum(1 for e in episodes if e['d_g'] and e['d_g'] > 0)

# Strict consensus: ASC ∩ CwT ∩ PAF pass (3-way)
strict_consensus_3way = [
    e for e in episodes 
    if e['asc_pass'] and e['cwt_pass'] and e['paf_pass']
]
strict_3way_count = len(strict_consensus_3way)

# Strict consensus FA: 3-way pass AND TCC fail (or d_g > 0)
strict_fa_3way = [
    e for e in strict_consensus_3way 
    if e.get('tcc_pass') is False or (e.get('d_g', 0) > 0)
]
strict_fa_3way_count = len(strict_fa_3way)

# Loose consensus: ASC ∩ CwT (2-way)
loose_consensus = [e for e in episodes if e['asc_pass'] and e['cwt_pass']]
loose_fa = [e for e in loose_consensus if (e.get('tcc_pass') is False) or (e.get('d_g', 0) > 0)]

# 2-way alternative: AC ∩ C2 (from prior session)
# Note: AC = ASC, C2 might be PAF or different. Adapt.

print('=' * 60)
print('V7.3 base strict consensus FA analysis')
print('=' * 60)
print(f'Total episodes: {total}')
print(f'Hard violation (d_g > 0): {hard_violation} ({100*hard_violation/total:.2f}%)')
print()
print('Strict consensus (3-way ASC∩CwT∩PAF):')
print(f'  Pass cell: {strict_3way_count} ({100*strict_3way_count/total:.2f}%)')
print(f'  FA (3-way pass + TCC fail): {strict_fa_3way_count}')
print(f'  FA rate: {100*strict_fa_3way_count/total:.2f}%')
print(f'  FA conditional: {100*strict_fa_3way_count/max(strict_3way_count,1):.2f}%')
print()
print('Loose consensus (2-way ASC∩CwT):')
print(f'  Pass cell: {len(loose_consensus)} ({100*len(loose_consensus)/total:.2f}%)')
print(f'  FA: {len(loose_fa)} ({100*len(loose_fa)/total:.2f}%)')
print()
print('Paper v6 strict consensus FA: 6.6%')
print(f'V7.3 base strict consensus FA: {100*strict_fa_3way_count/total:.2f}%')
print()
print('GATE check:')
fa_rate = 100*strict_fa_3way_count/total
if 3.0 <= fa_rate <= 12.0:
    print(f'  ✓ FA rate {fa_rate:.2f}% in [3%, 12%] range (paper bridge)')
else:
    print(f'  ✗ FA rate {fa_rate:.2f}% outside [3%, 12%] range')

# Save
import json
result = {
    'corpus': 'v7.3 base 11286',
    'total_episodes': total,
    'hard_violation_count': hard_violation,
    'hard_violation_rate_pct': 100*hard_violation/total,
    'strict_3way_pass': strict_3way_count,
    'strict_3way_fa_count': strict_fa_3way_count,
    'strict_3way_fa_rate_pct': 100*strict_fa_3way_count/total,
    'loose_2way_pass': len(loose_consensus),
    'loose_2way_fa_rate_pct': 100*len(loose_fa)/total,
    'in_range': 3.0 <= fa_rate <= 12.0,
}
with open('reports/path_d_day3/v73_base_strict_fa.json', 'w') as f:
    json.dump(result, f, indent=2)
print()
print('Saved: reports/path_d_day3/v73_base_strict_fa.json')
PYEOF

산출 보고:
1. Hard violation rate
2. 3-way strict consensus pass count + FA rate
3. 2-way loose consensus FA rate
4. v6 (6.6%) 대비

GATE:
  - PASS: FA rate in [3%, 12%]
  - FAIL: FA rate outside range → Cat A subset에서 재계산 필요
```

---

## STEP 3: Pairwise rank reversal (~30 min)

**Paste after STEP 2:**

```
v7.3 base에서 evaluator swap 시 pairwise rank reversal rate 계산.

Paper headline: 75.0% reversal, Kendall W=0.408 on v6 16,944 W8 episodes.
Target: v7.3에서 reversal ≥ 65%.

실행:
PYTHONPATH=. python << 'PYEOF'
import json, glob
from itertools import combinations

# Per-model per-evaluator mean compliance score (proxy for ranking)
from collections import defaultdict

per_model_eval = defaultdict(lambda: defaultdict(list))
for f in glob.glob('results/v73_full/*/*.json'):
    d = json.load(open(f))
    m = d.get('model_name', f.split('/')[-2])
    
    # CGA composite score
    cga = d.get('compliance_score', d.get('cga_score', 0))
    
    # Per-evaluator pass (binary, but mean across episodes = pass rate)
    for ev in ['tom', 'asc', 'paf', 'cwt', 'tcc']:
        v = d.get(f'{ev}_pass') or d.get(f'eval_{ev.upper()}')
        if v is not None:
            per_model_eval[m][ev].append(int(bool(v)))
    
    per_model_eval[m]['cga'].append(cga)

# Per-model per-evaluator mean
model_eval_mean = {}
for m, ev_dict in per_model_eval.items():
    model_eval_mean[m] = {ev: sum(vals)/len(vals) if vals else 0 
                          for ev, vals in ev_dict.items()}

# Rank models by each evaluator
evaluators = ['tom', 'asc', 'paf', 'cwt', 'tcc', 'cga']
models = list(model_eval_mean.keys())
print(f'Models: {len(models)}')
print(f'Evaluators: {evaluators}')

ranks = {}
for ev in evaluators:
    sorted_models = sorted(models, key=lambda m: -model_eval_mean[m].get(ev, 0))
    ranks[ev] = {m: i for i, m in enumerate(sorted_models)}

print()
print('Rankings by evaluator:')
for ev in evaluators:
    print(f'\n{ev.upper()}:')
    for i, m in enumerate(sorted(models, key=lambda x: ranks[ev][x])):
        print(f'  {i+1}. {m} (score: {model_eval_mean[m].get(ev, 0):.4f})')

# Pairwise rank reversal across evaluators
total_pairs = 0
reversed_pairs = 0
for ev1, ev2 in combinations(evaluators, 2):
    for m1, m2 in combinations(models, 2):
        order1 = ranks[ev1][m1] < ranks[ev1][m2]  # m1 better in ev1
        order2 = ranks[ev2][m1] < ranks[ev2][m2]
        total_pairs += 1
        if order1 != order2:
            reversed_pairs += 1

reversal_rate = 100 * reversed_pairs / total_pairs
print()
print('=' * 60)
print('Pairwise rank reversal:')
print('=' * 60)
print(f'Model pairs: {len(list(combinations(models, 2)))}')
print(f'Evaluator pairs: {len(list(combinations(evaluators, 2)))}')
print(f'Total comparisons: {total_pairs}')
print(f'Reversed: {reversed_pairs} ({reversal_rate:.1f}%)')
print()
print(f'Paper v6 reversal: 75.0%')
print(f'V7.3 base reversal: {reversal_rate:.1f}%')
print()

# Kendall W (concordance)
import statistics
def kendall_w(ranks_dict, items):
    n = len(items)
    k = len(ranks_dict)
    R_sums = [sum(ranks_dict[ev][item] for ev in ranks_dict) for item in items]
    mean_R = sum(R_sums) / len(R_sums)
    S = sum((R - mean_R) ** 2 for R in R_sums)
    W = 12 * S / (k**2 * (n**3 - n))
    return W

W = kendall_w(ranks, models)
print(f'Kendall W: {W:.4f}')
print(f'Paper v6 Kendall W: 0.408')
print()

print('GATE check:')
if reversal_rate >= 65.0:
    print(f'  ✓ Reversal rate {reversal_rate:.1f}% >= 65%')
else:
    print(f'  ✗ Reversal rate {reversal_rate:.1f}% < 65%')

# Save
result = {
    'corpus': 'v7.3 base 11286',
    'models': len(models),
    'evaluators': len(evaluators),
    'total_pairs': total_pairs,
    'reversed_pairs': reversed_pairs,
    'reversal_rate_pct': reversal_rate,
    'kendall_W': W,
    'paper_v6_reversal_pct': 75.0,
    'paper_v6_kendall_W': 0.408,
    'in_range': reversal_rate >= 65.0,
}
import json
with open('reports/path_d_day3/v73_base_rank_reversal.json', 'w') as f:
    json.dump(result, f, indent=2)
print('Saved: reports/path_d_day3/v73_base_rank_reversal.json')
PYEOF

GATE:
  - PASS: reversal ≥ 65%
  - FAIL: reversal < 65% → ranking robustness on v7.3 different
```

---

## STEP 4: Plug-in Bayes error floor on v7.3 base (~1 h)

**Paste after STEP 3:**

```
v7.3 base에서 Theorem 1 plug-in Bayes error floor 계산.

Paper headline (v6 14,826 W8-filtered): 
  ε̂*term = 0.436 (terminal)
  ε̂*aset = 0.024 (action multiset)
  ε̂*nord = 0.003 (no order)
  ε̂*nctx = 0.003 (no context)

Target: v7.3에서 같은 magnitude order.

실행:
PYTHONPATH=. python << 'PYEOF'
import json, glob
from collections import defaultdict

episodes = []
for f in glob.glob('results/v73_full/*/*.json'):
    d = json.load(open(f))
    
    # 4 projections
    # π_term: terminal output / final state
    # π_aset: action multiset (sorted unique actions)
    # π_nord: ordered actions, no timestamp
    # π_nctx: timed actions, no patient state
    
    actions = [s.get('action_id') for s in d.get('steps', [])]
    timestamps = [s.get('timestamp', 0) for s in d.get('steps', [])]
    states = [s.get('patient_state', {}) for s in d.get('steps', [])]
    
    pi_term = (d.get('final_diagnosis') or d.get('terminal_state') or '')
    pi_aset = tuple(sorted(set(actions)))
    pi_nord = tuple(actions)  # ordered, no timestamp
    pi_nctx = tuple(zip(actions, timestamps))  # timed, no state
    
    d_g = d.get('conformance_distance', d.get('d_g', 0))
    verdict = 1 if d_g and d_g > 0 else 0  # 1 = violates
    
    episodes.append({
        'scenario_id': d.get('scenario_id'),
        'pi_term': str(pi_term),
        'pi_aset': pi_aset,
        'pi_nord': pi_nord,
        'pi_nctx': pi_nctx,
        'verdict': verdict
    })

total = len(episodes)
print(f'Episodes: {total}')

# For each projection, compute Bayes error floor:
# - Group episodes by π value
# - For each group (fiber), Bayes error = min(p_pass, p_fail)
# - Total Bayes error = E_y[min(p0, p1)] where y is fiber

def bayes_error(episodes, projection_key):
    fibers = defaultdict(list)
    for ep in episodes:
        fibers[ep[projection_key]].append(ep['verdict'])
    
    total = sum(len(v) for v in fibers.values())
    bayes_err = 0
    mixed_fibers = 0
    for fiber, verdicts in fibers.items():
        n = len(verdicts)
        n_violate = sum(verdicts)
        n_pass = n - n_violate
        p_violate = n_violate / n
        p_pass = n_pass / n
        if p_violate > 0 and p_pass > 0:
            mixed_fibers += 1
        bayes_err += (n / total) * min(p_violate, p_pass)
    
    return bayes_err, mixed_fibers, len(fibers)

eps_term, mixed_term, n_term = bayes_error(episodes, 'pi_term')
eps_aset, mixed_aset, n_aset = bayes_error(episodes, 'pi_aset')
eps_nord, mixed_nord, n_nord = bayes_error(episodes, 'pi_nord')
eps_nctx, mixed_nctx, n_nctx = bayes_error(episodes, 'pi_nctx')

print()
print('=' * 60)
print('Plug-in Bayes error floor (v7.3 base)')
print('=' * 60)
print(f'ε*term = {eps_term:.4f} (paper v6: 0.436)')
print(f'  Mixed fibers: {mixed_term}/{n_term} ({100*mixed_term/n_term:.1f}%)')
print(f'ε*aset = {eps_aset:.4f} (paper v6: 0.024)')
print(f'  Mixed fibers: {mixed_aset}/{n_aset}')
print(f'ε*nord = {eps_nord:.4f} (paper v6: 0.003)')
print(f'  Mixed fibers: {mixed_nord}/{n_nord}')
print(f'ε*nctx = {eps_nctx:.4f} (paper v6: 0.003)')
print(f'  Mixed fibers: {mixed_nctx}/{n_nctx}')
print()

# Magnitude order check: ε*term >> ε*aset > ε*nord ~ ε*nctx
order_check = eps_term > eps_aset > eps_nord
print('GATE check:')
print(f'  ε*term > ε*aset: {eps_term > eps_aset}')
print(f'  ε*aset > ε*nord: {eps_aset > eps_nord}')
print(f'  Magnitude order: {"PRESERVED" if order_check else "VIOLATED"}')

# Save
result = {
    'corpus': 'v7.3 base 11286',
    'eps_term': eps_term,
    'eps_aset': eps_aset,
    'eps_nord': eps_nord,
    'eps_nctx': eps_nctx,
    'mixed_fibers': {'term': mixed_term, 'aset': mixed_aset, 'nord': mixed_nord, 'nctx': mixed_nctx},
    'fiber_counts': {'term': n_term, 'aset': n_aset, 'nord': n_nord, 'nctx': n_nctx},
    'paper_v6': {'eps_term': 0.436, 'eps_aset': 0.024, 'eps_nord': 0.003, 'eps_nctx': 0.003},
    'order_preserved': order_check
}
import json
with open('reports/path_d_day3/v73_base_bayes_floor.json', 'w') as f:
    json.dump(result, f, indent=2)
print('Saved')
PYEOF

GATE:
  - PASS: ε*term > ε*aset > ε*nord ≈ ε*nctx (magnitude order preserved)
  - PASS: ε*term in [0.3, 0.5] (paper 0.436 ± 0.1)
  - PARTIAL: order preserved but values shifted
  - FAIL: order violated → projection taxonomy questionable on v7.3
```

---

## STEP 5: Replay scorer detection loss (~1 h)

**Paste after STEP 4:**

```
MAB- and AC-style scorer가 v7.3에서 TCC 검출의 몇 %를 놓치는지 계산.

Paper headline (v6 App. G): 63.2% - 84.2% loss.
Target: v7.3에서 비슷한 magnitude.

실행:
PYTHONPATH=. python << 'PYEOF'
import json, glob

# Load v7.3 base episodes with all evaluator outputs
episodes = []
for f in glob.glob('results/v73_full/*/*.json'):
    d = json.load(open(f))
    episodes.append({
        'scenario_id': d.get('scenario_id'),
        'mab_pass': d.get('mab_pass') or d.get('eval_MAB'),  # MedAgentBench-style
        'ac_pass': d.get('ac_pass') or d.get('eval_AC'),    # AgentClinic-style
        'asc_pass': d.get('asc_pass') or d.get('eval_ASC'),
        'cwt_pass': d.get('cwt_pass') or d.get('eval_CwT'),
        'paf_pass': d.get('paf_pass') or d.get('eval_PAF'),
        'tcc_pass': d.get('tcc_pass') or d.get('eval_TCC'),
        'd_g': d.get('conformance_distance', d.get('d_g', 0)),
    })

total = len(episodes)

# TCC detections: TCC fail (d_g > 0)
tcc_detections = [e for e in episodes if (e.get('tcc_pass') is False) or (e.get('d_g', 0) > 0)]
tcc_count = len(tcc_detections)

# MAB-style replay: rubric-based, replay using ASC + PAF approximation
# Paper says: MAB miss = 84.2% of TCC detections
# AC-style: action-list-only LLM judge
# Simplified replay: assume MAB ≈ ASC ∩ PAF (rubric-style joint pass)
mab_replay_pass = [e for e in tcc_detections 
                   if e.get('asc_pass') and e.get('paf_pass')]
mab_loss = len(mab_replay_pass) / max(tcc_count, 1)

# AC-style replay: action-list judge approximation
# Paper says: AC miss = 63.2% (AC alone, action-set match)
# Simplified: assume AC ≈ ASC alone
ac_replay_pass = [e for e in tcc_detections if e.get('asc_pass')]
ac_loss = len(ac_replay_pass) / max(tcc_count, 1)

print('=' * 60)
print('Replay scorer detection loss (v7.3 base)')
print('=' * 60)
print(f'Total episodes: {total}')
print(f'TCC detections (d_g > 0): {tcc_count} ({100*tcc_count/total:.1f}%)')
print()
print(f'MAB-style replay miss: {len(mab_replay_pass)}/{tcc_count} = {100*mab_loss:.1f}%')
print(f'  (Paper v6 MAB miss: 84.2%)')
print()
print(f'AC-style replay miss: {len(ac_replay_pass)}/{tcc_count} = {100*ac_loss:.1f}%')
print(f'  (Paper v6 AC miss: 63.2%)')
print()

print('GATE check:')
mab_in_range = 60 <= 100*mab_loss <= 90
ac_in_range = 50 <= 100*ac_loss <= 80
print(f'  MAB loss {100*mab_loss:.1f}% in [60%, 90%]: {mab_in_range}')
print(f'  AC loss {100*ac_loss:.1f}% in [50%, 80%]: {ac_in_range}')

# Save
result = {
    'corpus': 'v7.3 base 11286',
    'total_episodes': total,
    'tcc_detections': tcc_count,
    'mab_replay_miss_pct': 100*mab_loss,
    'ac_replay_miss_pct': 100*ac_loss,
    'paper_v6_mab_pct': 84.2,
    'paper_v6_ac_pct': 63.2,
    'in_range': mab_in_range and ac_in_range
}
import json
with open('reports/path_d_day3/v73_base_replay_loss.json', 'w') as f:
    json.dump(result, f, indent=2)
print('Saved')
PYEOF

GATE:
  - PASS: MAB loss in [60%, 90%], AC loss in [50%, 80%]
  - FAIL: outside range → replay adapters need v7.3-specific recalibration
```

---

## STEP 6: Bridge experiment summary table (~30 min)

**Paste after STEP 5:**

```
5 bridge numbers 통합 표 + paper §App SGSC bridge experiment 단락 draft.

PYTHONPATH=. python << 'PYEOF'
import json
import os

reports_dir = 'reports/path_d_day3/'
files = {
    'orphan': 'v6_b6_orphan_analysis.json',
    'eta': 'v73_base_eta_squared.json',
    'fa': 'v73_base_strict_fa.json',
    'reversal': 'v73_base_rank_reversal.json',
    'bayes': 'v73_base_bayes_floor.json',
    'replay': 'v73_base_replay_loss.json',
}

results = {}
for k, fname in files.items():
    fpath = os.path.join(reports_dir, fname)
    if os.path.exists(fpath):
        results[k] = json.load(open(fpath))

# Build bridge table
print('=' * 80)
print('Paper Bridge Experiment Summary (v6 vs v7.3 base)')
print('=' * 80)
print()
print(f"{'Metric':<35}{'v6 paper':<15}{'v7.3 base':<15}{'Status':<10}")
print('-' * 80)

# η²
v7_eta_eval = results.get('eta', {}).get('eta_eval_proxy', '?')
v7_eta_run = results.get('eta', {}).get('eta_run_proxy', '?')
print(f"{'η²eval (variance)':<35}{'0.072':<15}{v7_eta_eval if isinstance(v7_eta_eval, str) else f'{v7_eta_eval:.4f}':<15}")
print(f"{'η²run (run noise)':<35}{'0.0515':<15}{v7_eta_run if isinstance(v7_eta_run, str) else f'{v7_eta_run:.4f}':<15}")

# FA
v7_fa = results.get('fa', {}).get('strict_3way_fa_rate_pct', '?')
print(f"{'Strict consensus FA':<35}{'6.6%':<15}{v7_fa if isinstance(v7_fa, str) else f'{v7_fa:.2f}%':<15}")

# Reversal
v7_rev = results.get('reversal', {}).get('reversal_rate_pct', '?')
v7_W = results.get('reversal', {}).get('kendall_W', '?')
print(f"{'Pairwise rank reversal':<35}{'75.0%':<15}{v7_rev if isinstance(v7_rev, str) else f'{v7_rev:.1f}%':<15}")
print(f"{'Kendall W':<35}{'0.408':<15}{v7_W if isinstance(v7_W, str) else f'{v7_W:.3f}':<15}")

# Bayes
v7_term = results.get('bayes', {}).get('eps_term', '?')
v7_aset = results.get('bayes', {}).get('eps_aset', '?')
print(f"{'ε*term (terminal)':<35}{'0.436':<15}{v7_term if isinstance(v7_term, str) else f'{v7_term:.4f}':<15}")
print(f"{'ε*aset (action set)':<35}{'0.024':<15}{v7_aset if isinstance(v7_aset, str) else f'{v7_aset:.4f}':<15}")

# Replay
v7_mab = results.get('replay', {}).get('mab_replay_miss_pct', '?')
v7_ac = results.get('replay', {}).get('ac_replay_miss_pct', '?')
print(f"{'MAB-style replay loss':<35}{'84.2%':<15}{v7_mab if isinstance(v7_mab, str) else f'{v7_mab:.1f}%':<15}")
print(f"{'AC-style replay loss':<35}{'63.2%':<15}{v7_ac if isinstance(v7_ac, str) else f'{v7_ac:.1f}%':<15}")

# Orphan disclosure
print()
print('=' * 80)
print('B6 Orphan Disclosure (v6 vs v7.3)')
print('=' * 80)
v6_orphan = results.get('orphan', {}).get('orphan_rate_pct', '?')
print(f"v6 orphan rate: {v6_orphan if isinstance(v6_orphan, str) else f'{v6_orphan:.1f}%'}")
print(f"v7.3 capped orphan rate: ~66.2% (from earlier analysis)")
print()

# Generate macro file
macros = []
macros.append('% v7.3 bridge experiment macros')
if 'eta' in results:
    macros.append(f"\\providecommand{{\\vSevenThreeBaseEtaEval}}{{{results['eta'].get('eta_eval_proxy', 0):.4f}}}")
    macros.append(f"\\providecommand{{\\vSevenThreeBaseEtaRun}}{{{results['eta'].get('eta_run_proxy', 0):.4f}}}")
if 'fa' in results:
    macros.append(f"\\providecommand{{\\vSevenThreeBaseStrictFA}}{{{results['fa'].get('strict_3way_fa_rate_pct', 0):.2f}}}")
if 'reversal' in results:
    macros.append(f"\\providecommand{{\\vSevenThreeBaseRankReversal}}{{{results['reversal'].get('reversal_rate_pct', 0):.1f}}}")
    macros.append(f"\\providecommand{{\\vSevenThreeBaseKendallW}}{{{results['reversal'].get('kendall_W', 0):.3f}}}")
if 'bayes' in results:
    macros.append(f"\\providecommand{{\\vSevenThreeBaseEpsTerm}}{{{results['bayes'].get('eps_term', 0):.4f}}}")
    macros.append(f"\\providecommand{{\\vSevenThreeBaseEpsAset}}{{{results['bayes'].get('eps_aset', 0):.4f}}}")
if 'replay' in results:
    macros.append(f"\\providecommand{{\\vSevenThreeBaseMabLoss}}{{{results['replay'].get('mab_replay_miss_pct', 0):.1f}}}")
    macros.append(f"\\providecommand{{\\vSevenThreeBaseAcLoss}}{{{results['replay'].get('ac_replay_miss_pct', 0):.1f}}}")
if 'orphan' in results:
    macros.append(f"\\providecommand{{\\vSixOrphanRate}}{{{results['orphan'].get('orphan_rate_pct', 0):.1f}}}")

with open('paper/auto_numbers_v73_bridge.tex', 'w') as f:
    f.write('\n'.join(macros) + '\n')
print()
print('Macros saved: paper/auto_numbers_v73_bridge.tex')
PYEOF

산출 보고:
1. 5 bridge numbers 표 (v6 paper vs v7.3 base)
2. B6 orphan disclosure (v6 vs v7.3)
3. Macro file 작성 확인

GATE: 5/5 PASS or PARTIAL → frontier launch 진행 결정
```

---

## STEP 7: Frontier launch decision (after STEP 6)

**Paste after STEP 6:**

```
5 bridge numbers 결과 검토.

결정 매트릭스:

Case all-PASS: 5 numbers 모두 paper range 내
  → SGSC v7.3 bridge experiment SUCCESS
  → Frontier launch GO
  → Path A (v6 + frontier) 또는 Path C (v7.3 base + frontier) 선택

Case 1-2 partial: 1-2 numbers가 marginal range
  → Paper §App에 disclosure 추가하면 OK
  → Frontier launch GO (Path A 권장 — paper headline 강화)

Case 3+ FAIL or v6 orphan affects headline: 
  → Paper §5 wording 수정 필요
  → Frontier launch HOLD until paper revision
  → anonymous-user 결정 대기

Frontier launch path:
  Path A: v6 manual 706 × 3 = 2,118 episodes per frontier model
    Models: Claude Opus 4.7 + GPT-5
    Cost: $3-5K, Time: 4-6h API parallel
    Paper integration: §5.1 vendor families 5→7
  
  Path C: v7.3 base 418 × 3 = 1,254 episodes per frontier model
    Models: Claude Opus 4.7 (또는 + GPT-5)
    Cost: $2.5-4K, Time: 4-6h
    Paper integration: §App SGSC bridge frontier replication

추천: Path A (paper 헤드라인 직접 강화)
```

---

## Total time estimate

```
STEP 0: V6 orphan (~30 min) — CRITICAL
STEP 1: η² (~30 min)
STEP 2: Strict FA (~30 min)
STEP 3: Rank reversal (~30 min)
STEP 4: Bayes floor (~1 h)
STEP 5: Replay loss (~1 h)
STEP 6: Summary + macros (~30 min)
STEP 7: Frontier decision (~10 min)

Total: ~4-5 hours

Then:
- If frontier GO: 4-6h API run
- Frontier integration: 2 h
- Paper polish: 5/4 종일
- Final review: 5/5
- Submit: 5/6
```

---

## Critical gates summary

| STEP | Output | GATE | If FAIL |
|---|---|---|---|
| 0 | v6 orphan rate | < 40% | Cat A subset 별도 계산 |
| 1 | η² values | η²eval > η²run | STOP, investigate |
| 2 | Strict FA | [3%, 12%] | Cat A subset 재계산 |
| 3 | Rank reversal | ≥ 65% | Disclosure |
| 4 | Bayes floor | order preserved | STOP |
| 5 | Replay loss | [60%, 90%] / [50%, 80%] | Recalibrate adapters |
| 6 | Bridge table | all green or partial | Frontier path 결정 |
| 7 | Frontier launch | Path A or C | — |

---

## What this achieves

1. **B6 orphan**: v6에 영향 있나 명확히 답 (STEP 0)
2. **5 bridge numbers**: paper의 SGSC 진짜 요구 충족 (STEP 1-5)
3. **Macros**: paper에 paste 가능한 LaTeX (STEP 6)
4. **Frontier**: paper-aligned launch (STEP 7)

이게 paper deadline 5/6 안에 SGSC 통합 완료하는 paper-aligned path입니다.