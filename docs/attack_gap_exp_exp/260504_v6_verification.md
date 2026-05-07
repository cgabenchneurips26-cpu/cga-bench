# Option β-full Sequential Prompts: V6 Full Verification → Frontier Launch

**Goal**: Verify ALL paper main_final_v18.pdf headline numbers reproduce on current code state, then launch Path A frontier.

**Total time estimate**: 2-3h verification + 4-6h frontier compute

**Critical principle**: Paper에 적힌 모든 number가 *current code*로 reproducible해야 함. 재현 불가능한 number는 paper에 있으면 안 됨.

**Rule**: 각 STEP의 GATE에서 결과 보고. PASS시 다음, FAIL시 STOP.

---

## V6 Full Verification — 8 STEPs (~2-3h)

각 STEP은 paper main_final_v18.pdf의 *specific number*를 verify합니다.

---

### STEP V1: Setup + corpus integrity (10분)

**Paste:**

```
V6 verdict matrix integrity 사전 검증.

Paper main_final_v18.pdf headline numbers를 현재 code로 재현 가능한지 확인 시작.

Step 1: V6 corpus 파일 목록 확인
ls -la results/v6_full/
ls -la results/v6_phase_b/ 2>/dev/null
find . -name "verdict_matrix*.json" -path "*v6*" 2>/dev/null

Step 2: 각 verdict matrix 파일의 episode count 확인
python << 'PYEOF'
import json, glob, os

verdict_files = []
for pattern in ['**/verdict_matrix_v6_*.json', '**/verdict_matrix*.json']:
    for f in glob.glob(pattern, recursive=True):
        if 'v6' in f.lower() or 'phase' in f.lower():
            verdict_files.append(f)

print(f'Found {len(verdict_files)} verdict matrix files')
for f in sorted(set(verdict_files)):
    try:
        with open(f) as fh:
            data = json.load(fh)
        if isinstance(data, list):
            n = len(data)
            sample = data[0] if data else {}
        elif isinstance(data, dict):
            n = len(data.get('episodes', data))
            sample = list((data.get('episodes', data)).values())[0] if n > 0 else {}
        print(f'  {f}: {n} episodes')
        print(f'    Keys: {list(sample.keys())[:10]}')
    except Exception as e:
        print(f'  {f}: ERROR {e}')
PYEOF

Step 3: 핵심 corpus 정의 확인 (paper §5.1)
- V6 Full: 19,062 episodes (9 models × 706 scenarios × 3 runs)
- V6 W8: 16,944 (8-model ranking subset)
- V6 Phase B (auto-expanded): 76,464
- V6 Bayes-floor subsample: 14,826
- V6 Held-out: 1,584

각 corpus의 verdict matrix 파일 경로 매핑 보고.

산출 보고:
- 발견된 verdict matrix 파일들 (경로 + episode count)
- 각 corpus 정의 매핑
- 파일 무결성 (JSON parseable, evaluator fields 존재)

GATE: 5개 corpus 모두 식별됨 + JSON valid → STEP V2
```

---

### STEP V2: Verify Paper §Abstract η²eval=0.072, η²run=0.0515 (15분)

**Paste after V1:**

```
Paper §Abstract와 §1 의 η² claim 재현 검증.

Paper §1 Introduction:
"Across 19,062 episodes, 9 models, and 25 domains, variance decomposition 
assigns η²eval=0.072 to evaluator choice and η²run=0.0515 to run variance"

검증 코드:
python << 'PYEOF'
import json, glob
import numpy as np
from collections import defaultdict

# Paper Abstract corpus: 19,062 episodes (Phase A 9-model)
# Find the right verdict matrix
target_files = [
    'reports/verdict_matrix_v6_phase_a.json',
    'reports/verdict_matrix_v6_full.json', 
    'reports/path_d_day3/verdict_matrix_v6_full.json',
]

target_file = None
for f in target_files:
    import os
    if os.path.exists(f):
        target_file = f
        break

if not target_file:
    # Search
    for f in glob.glob('**/*verdict_matrix*v6*.json', recursive=True):
        with open(f) as fh:
            data = json.load(fh)
        n = len(data) if isinstance(data, list) else len(data.get('episodes', data))
        if 18000 < n < 20000:
            target_file = f
            print(f'Found 19K target: {f} ({n} episodes)')
            break

if not target_file:
    print('ERROR: Cannot find 19,062-episode corpus')
    exit(1)

with open(target_file) as f:
    episodes = json.load(f)
if isinstance(episodes, dict):
    episodes = list(episodes.get('episodes', episodes).values())

print(f'Loaded {len(episodes)} episodes from {target_file}')

# η² computation using paper methodology
# For each episode: aggregate across evaluators (with v4_hard inverted)
# Compute variance decomposition

# Gather (scenario_id, model, run, evaluator) → pass/fail
import pandas as pd
rows = []
for ep in episodes:
    sid = ep.get('scenario_id', '')
    m = ep.get('model_name', ep.get('model', ''))
    r = ep.get('run_id', ep.get('run', 0))
    
    # Paper evaluators: TOM, ASC, PAF, CwT, TCC
    # Proxy mapping: dxem→TOM, ac_proxy→ASC, mab_proxy→PAF, c2_pass→CwT, NOT v4_hard→TCC
    rows.append({'sid':str(sid), 'model':str(m), 'run':str(r),
                 'evaluator':'TOM', 'pass':int(bool(ep.get('dxem', False)))})
    rows.append({'sid':str(sid), 'model':str(m), 'run':str(r),
                 'evaluator':'ASC', 'pass':int(bool(ep.get('ac_proxy', False)))})
    rows.append({'sid':str(sid), 'model':str(m), 'run':str(r),
                 'evaluator':'PAF', 'pass':int(bool(ep.get('mab_proxy', False)))})
    rows.append({'sid':str(sid), 'model':str(m), 'run':str(r),
                 'evaluator':'CwT', 'pass':int(bool(ep.get('c2_pass', False)))})
    rows.append({'sid':str(sid), 'model':str(m), 'run':str(r),
                 'evaluator':'TCC', 'pass':int(not bool(ep.get('v4_hard', True)))})

df = pd.DataFrame(rows)
print(f'Long format rows: {len(df)}')

# Two-way ANOVA via statsmodels
try:
    from statsmodels.formula.api import ols
    from statsmodels.stats.anova import anova_lm
    
    model = ols('Q("pass") ~ C(evaluator) + C(run) + C(model) + C(sid)', data=df).fit()
    anova = anova_lm(model, typ=2)
    print(anova)
    
    ss_total = anova['sum_sq'].sum()
    eta_eval = anova.loc['C(evaluator)', 'sum_sq'] / ss_total
    eta_run = anova.loc['C(run)', 'sum_sq'] / ss_total
    
    print(f'\\nη²(eval) = {eta_eval:.4f}  (paper: 0.072)')
    print(f'η²(run)  = {eta_run:.4f}  (paper: 0.0515)')
    print(f'\\nDelta from paper:')
    print(f'  η²(eval): {eta_eval - 0.072:+.4f}')
    print(f'  η²(run):  {eta_run - 0.0515:+.4f}')
    
    # GATE check
    eval_match = abs(eta_eval - 0.072) < 0.02
    run_match = abs(eta_run - 0.0515) < 0.01
    order_match = eta_eval > eta_run
    
    print(f'\\nGATE checks:')
    print(f'  η²(eval) within ±0.02: {eval_match}')
    print(f'  η²(run) within ±0.01: {run_match}')
    print(f'  η²(eval) > η²(run) order: {order_match}')
    
    # Save
    import os
    os.makedirs('reports/path_d_day3/', exist_ok=True)
    with open('reports/path_d_day3/v6_eta_verification.json', 'w') as f:
        json.dump({
            'corpus': target_file,
            'n_episodes': len(episodes),
            'eta_eval_recomputed': eta_eval,
            'eta_run_recomputed': eta_run,
            'eta_eval_paper': 0.072,
            'eta_run_paper': 0.0515,
            'delta_eval': eta_eval - 0.072,
            'delta_run': eta_run - 0.0515,
            'gate_eval_match': bool(eval_match),
            'gate_run_match': bool(run_match),
            'gate_order_match': bool(order_match),
        }, f, indent=2)
    print('\\nSaved: reports/path_d_day3/v6_eta_verification.json')
    
except ImportError:
    print('statsmodels not available, using proxy calculation')
PYEOF

산출 보고:
1. η²(eval) recomputed vs paper 0.072
2. η²(run) recomputed vs paper 0.0515
3. Delta from paper
4. GATE 결과

GATE:
  - PASS: |Δη²(eval)| ≤ 0.02 AND |Δη²(run)| ≤ 0.01 AND order preserved
  - PARTIAL: order preserved but values shift > tolerance → disclosure 필요
  - FAIL: order violated → STOP, anonymous-user 결정
```

---

### STEP V3: Verify Paper §Abstract 6.6% strict FA (1258/19,062) (15분)

**Paste after V2:**

```
Paper §Abstract와 §5.3 strict consensus FA 재현 검증.

Paper §5.3:
"1258/19,062 (6.6%) pass the strict consensus ASC∩CwT∩PAF, 
with median 2.0 hard violations per false accept."

검증:
python << 'PYEOF'
import json, glob

target_file = None
for pattern in ['reports/verdict_matrix_v6_phase_a.json', 
                'reports/verdict_matrix_v6_full.json',
                '**/*verdict_matrix*v6*phase*.json']:
    for f in glob.glob(pattern, recursive=True):
        import os
        if os.path.exists(f):
            target_file = f
            break
    if target_file:
        break

with open(target_file) as f:
    episodes = json.load(f)
if isinstance(episodes, dict):
    episodes = list(episodes.get('episodes', episodes).values())

# Filter to Phase A 9-model 19,062 (or W8 16,944)
print(f'Total: {len(episodes)}')

# Strict 3-way consensus: ASC ∩ CwT ∩ PAF pass + d_g > 0 (TCC fail)
strict_pass = [e for e in episodes 
               if e.get('ac_proxy') and e.get('c2_pass') and e.get('mab_proxy')]
strict_fa = [e for e in strict_pass if e.get('v4_hard')]  # has hard violations

n_total = len(episodes)
n_strict_pass = len(strict_pass)
n_strict_fa = len(strict_fa)

fa_rate = 100 * n_strict_fa / n_total

print(f'Strict 3-way consensus pass: {n_strict_pass}')
print(f'Strict consensus FA (and TCC fail): {n_strict_fa}')
print(f'FA rate: {fa_rate:.2f}%')
print(f'Paper: 6.6% (1258/19,062)')

# Median d_g per FA
d_gs = [e.get('d_g', 0) for e in strict_fa if e.get('d_g')]
import statistics
median_dg = statistics.median(d_gs) if d_gs else 0
print(f'Median d_g per FA: {median_dg:.2f}')
print(f'Paper: 2.0')

# Loose 2-way consensus (ASC ∩ CwT)
loose_pass = [e for e in episodes if e.get('ac_proxy') and e.get('c2_pass')]
loose_fa = [e for e in loose_pass if e.get('v4_hard')]
print(f'\\nLoose 2-way consensus pass: {len(loose_pass)} ({100*len(loose_pass)/n_total:.1f}%)')
print(f'Loose 2-way FA: {len(loose_fa)} ({100*len(loose_fa)/n_total:.2f}%)')
print(f'Paper loose: 11.1% (2106/19,062)')

# GATE check
fa_match = abs(fa_rate - 6.6) < 0.5  # ±0.5pp tolerance
n_match = abs(n_strict_fa - 1258) < 50  # ±50 episodes

print(f'\\nGATE:')
print(f'  FA rate within ±0.5pp: {fa_match} ({fa_rate:.2f}% vs 6.6%)')
print(f'  N within ±50: {n_match} ({n_strict_fa} vs 1258)')

# Save
result = {
    'corpus': target_file,
    'n_total': n_total,
    'strict_3way_pass': n_strict_pass,
    'strict_3way_fa_n': n_strict_fa,
    'strict_3way_fa_rate_pct': fa_rate,
    'paper_n': 1258,
    'paper_rate_pct': 6.6,
    'delta_n': n_strict_fa - 1258,
    'delta_pct': fa_rate - 6.6,
    'median_dg': median_dg,
    'paper_median_dg': 2.0,
    'loose_2way_pass': len(loose_pass),
    'loose_2way_fa': len(loose_fa),
    'gate_fa_match': bool(fa_match),
    'gate_n_match': bool(n_match),
}
with open('reports/path_d_day3/v6_strict_fa_verification.json', 'w') as f:
    json.dump(result, f, indent=2)
print('Saved: reports/path_d_day3/v6_strict_fa_verification.json')
PYEOF

GATE:
  - PASS: FA rate within ±0.5pp of 6.6% AND N within ±50 of 1258
  - PARTIAL: rate match but N differs → corpus subset issue
  - FAIL: rate >2pp shift → main text 수정 필요
```

---

### STEP V4: Verify Paper §5.6 75.0% rank reversal + Kendall W=0.408 (20분)

**Paste after V3:**

```
Paper §5.6 rank reversal + Kendall W 재현.

Paper §5.6:
"Among (8 choose 2) model pairs, 75.0% reverse rank under evaluator swap 
(Kendall W=0.408, episode-level bootstrap CI [0.342, 0.461])"

This is on W8-filtered 16,944 episodes (8 models).

python << 'PYEOF'
import json, glob
from collections import defaultdict
from itertools import combinations

# Find W8 corpus
target = None
for pattern in ['reports/verdict_matrix_v6_typed_phase1.json',
                'reports/verdict_matrix*w8*.json',
                '**/*verdict_matrix*16944*.json']:
    import glob, os
    for f in glob.glob(pattern, recursive=True):
        if os.path.exists(f):
            with open(f) as fh:
                data = json.load(fh)
            n = len(data) if isinstance(data, list) else len(data.get('episodes', data))
            if 16000 < n < 18000:
                target = f
                print(f'Found W8 corpus: {f} ({n} episodes)')
                break
    if target:
        break

if not target:
    # Filter from full 19,062 by model count
    for f in glob.glob('**/*verdict_matrix*v6*.json', recursive=True):
        with open(f) as fh:
            data = json.load(fh)
        eps = data if isinstance(data, list) else list(data.get('episodes', data).values())
        models = set(e.get('model_name', e.get('model', '')) for e in eps)
        if len(models) == 9:  # full 9-model
            # Filter to W8: drop one model (typically nemotron or smallest)
            # Need paper's W8 definition — most likely drops 1 model below threshold
            target = f
            print(f'Using full v6, will filter to W8: {f}')
            break

with open(target) as f:
    eps = json.load(f)
if isinstance(eps, dict):
    eps = list(eps.get('episodes', eps).values())

# W8 filter: drop one model (paper's filter — needs verification)
# Paper says "8-model ranking subset"; identify which model is excluded
models = sorted(set(e.get('model_name', e.get('model', '')) for e in eps))
print(f'Models in corpus: {models}')

# Per-model per-evaluator pass rate (rank by this)
per_model_eval = defaultdict(lambda: defaultdict(list))
for e in eps:
    m = e.get('model_name', e.get('model', ''))
    for ev_name, ev_field, invert in [
        ('TOM', 'dxem', False), ('ASC', 'ac_proxy', False),
        ('PAF', 'mab_proxy', False), ('CwT', 'c2_pass', False),
        ('TCC', 'v4_hard', True)
    ]:
        v = e.get(ev_field)
        if v is not None:
            v = bool(v)
            if invert: v = not v
            per_model_eval[m][ev_name].append(int(v))

# Mean pass rate per (model, evaluator)
model_eval_pass = {m: {ev: sum(vs)/len(vs) if vs else 0 
                        for ev, vs in evs.items()}
                    for m, evs in per_model_eval.items()}

# Rank models by each evaluator
evaluators = ['TOM', 'ASC', 'PAF', 'CwT', 'TCC']
ranks = {}
for ev in evaluators:
    sorted_m = sorted(models, key=lambda m: -model_eval_pass[m].get(ev, 0))
    ranks[ev] = {m: i for i, m in enumerate(sorted_m)}

# Pairwise reversal
total_pairs = 0
reversed_pairs = 0
for ev1, ev2 in combinations(evaluators, 2):
    for m1, m2 in combinations(models, 2):
        order1 = ranks[ev1][m1] < ranks[ev1][m2]
        order2 = ranks[ev2][m1] < ranks[ev2][m2]
        total_pairs += 1
        if order1 != order2:
            reversed_pairs += 1

reversal = 100 * reversed_pairs / total_pairs

# Kendall W
n = len(models)
k = len(evaluators)
R_sums = [sum(ranks[ev][m] for ev in evaluators) for m in models]
mean_R = sum(R_sums) / len(R_sums)
S = sum((R - mean_R) ** 2 for R in R_sums)
W = 12 * S / (k**2 * (n**3 - n))

print(f'\\nReversal rate: {reversal:.1f}%')
print(f'Paper: 75.0%')
print(f'Delta: {reversal - 75.0:+.1f}pp')
print(f'\\nKendall W: {W:.3f}')
print(f'Paper: 0.408')
print(f'Delta: {W - 0.408:+.3f}')

# GATE
rev_match = abs(reversal - 75.0) < 5.0
W_match = abs(W - 0.408) < 0.05

print(f'\\nGATE:')
print(f'  Reversal within ±5pp: {rev_match}')
print(f'  Kendall W within ±0.05: {W_match}')

result = {
    'corpus': target,
    'n_models': n,
    'n_episodes': len(eps),
    'reversal_pct': reversal,
    'kendall_W': W,
    'paper_reversal_pct': 75.0,
    'paper_kendall_W': 0.408,
    'delta_reversal': reversal - 75.0,
    'delta_W': W - 0.408,
    'gate_reversal_match': bool(rev_match),
    'gate_W_match': bool(W_match),
}
with open('reports/path_d_day3/v6_reversal_verification.json', 'w') as f:
    json.dump(result, f, indent=2)
print('Saved')
PYEOF

GATE:
  - PASS: reversal within ±5pp AND Kendall W within ±0.05
  - PARTIAL: one matches → minor disclosure
  - FAIL: both shift → main text 수정 필요
```

---

### STEP V5: Verify Paper §5.3 Table 1 per-evaluator FA rates (15분)

**Paste after V4:**

```
Paper §5.3 Table 1 per-evaluator FA 재현.

Paper Table 1 (19,062 episodes):
  TOM: Pass 100.0%, FA 55.4%
  ASC: Pass 74.4%, FA 46.8%, BSR_cond 57.1%
  CwT: Pass 35.6%, FA 11.9%, BSR_cond 39.3%
  PAF: Pass 52.9%, FA 34.3%, BSR_cond 60.3%
  TCC: Pass 49.5%, FA 0.0% (structural)

python << 'PYEOF'
import json, glob, os

target = None
for pattern in ['reports/verdict_matrix_v6_phase_a.json', 
                'reports/verdict_matrix_v6_full.json']:
    if os.path.exists(pattern):
        target = pattern
        break

if not target:
    # Find 19K
    for f in glob.glob('**/*verdict_matrix*v6*.json', recursive=True):
        with open(f) as fh:
            data = json.load(fh)
        n = len(data) if isinstance(data, list) else len(data.get('episodes', data))
        if 18000 < n < 20000:
            target = f
            break

with open(target) as f:
    eps = json.load(f)
if isinstance(eps, dict):
    eps = list(eps.get('episodes', eps).values())

n_total = len(eps)
print(f'Episodes: {n_total}')

paper = {
    'TOM': {'pass': 100.0, 'fa': 55.4},
    'ASC': {'pass': 74.4, 'fa': 46.8, 'bsr_cond': 57.1},
    'CwT': {'pass': 35.6, 'fa': 11.9, 'bsr_cond': 39.3},
    'PAF': {'pass': 52.9, 'fa': 34.3, 'bsr_cond': 60.3},
    'TCC': {'pass': 49.5, 'fa': 0.0},
}

evaluator_map = [
    ('TOM', 'dxem', False),
    ('ASC', 'ac_proxy', False),
    ('CwT', 'c2_pass', False),
    ('PAF', 'mab_proxy', False),
    ('TCC', 'v4_hard', True),
]

print(f'\\n{"Eval":<6}{"Pass%":<10}{"FA%":<10}{"BSR":<10}{"Match?":<10}')
print('-' * 60)

results = {}
for ev_name, field, invert in evaluator_map:
    n_pass = 0
    n_fa = 0  # pass but d_g > 0 (v4_hard True)
    n_pass_with_violation = 0
    
    for e in eps:
        v = e.get(field)
        has_violation = bool(e.get('v4_hard'))
        if v is None:
            continue
        v = bool(v)
        if invert: v = not v
        
        if v:  # passed this evaluator
            n_pass += 1
            if has_violation:
                n_fa += 1
                n_pass_with_violation += 1
    
    pass_pct = 100 * n_pass / n_total
    fa_pct = 100 * n_fa / n_total
    bsr_cond = 100 * n_pass_with_violation / max(n_pass, 1)
    
    paper_pass = paper[ev_name]['pass']
    paper_fa = paper[ev_name]['fa']
    
    delta_pass = pass_pct - paper_pass
    delta_fa = fa_pct - paper_fa
    
    match = abs(delta_pass) < 2.0 and abs(delta_fa) < 2.0
    
    print(f'{ev_name:<6}{pass_pct:<10.1f}{fa_pct:<10.1f}{bsr_cond:<10.1f}{"OK" if match else "DIFF":<10}')
    print(f'      Paper: {paper_pass:<10.1f}{paper_fa:<10.1f}')
    print(f'      Δ:     {delta_pass:+.1f}pp     {delta_fa:+.1f}pp')
    
    results[ev_name] = {
        'recomputed_pass_pct': pass_pct,
        'recomputed_fa_pct': fa_pct,
        'paper_pass_pct': paper_pass,
        'paper_fa_pct': paper_fa,
        'delta_pass': delta_pass,
        'delta_fa': delta_fa,
        'match': match
    }

# Save
with open('reports/path_d_day3/v6_table1_verification.json', 'w') as f:
    json.dump({'corpus': target, 'n_episodes': n_total, 'results': results}, f, indent=2)
print('\\nSaved: reports/path_d_day3/v6_table1_verification.json')

# Aggregate gate
all_match = all(r['match'] for r in results.values())
print(f'\\nALL evaluators within ±2pp: {all_match}')
PYEOF

GATE:
  - PASS: 모든 evaluator pass% AND fa% within ±2pp of paper
  - PARTIAL: 1-2 evaluator shift → disclosure
  - FAIL: 3+ evaluator shift > 2pp → main text Table 1 update 필요
```

---

### STEP V6: Verify Paper §3.4 Bayes floor numbers (15분)

**Paste after V5:**

```
Paper §3.4 Corollary 2 plug-in Bayes error floor 재현.

Paper Cor. 2:
"Let D̂ be the uniform empirical distribution over the 14,826 CGA-Bench episodes 
on which all four projections are defined.
ε*term=0.436, ε*aset=0.024, ε*nord=0.003, ε*nctx=0.003"

python << 'PYEOF'
import json, glob, os
from collections import defaultdict

# Find 14,826 corpus (Bayes-floor subsample)
target = None
for f in glob.glob('**/*verdict_matrix*v6*.json', recursive=True):
    with open(f) as fh:
        data = json.load(fh)
    eps = data if isinstance(data, list) else list(data.get('episodes', data).values())
    n = len(eps)
    if 14000 < n < 16000:
        target = f
        print(f'Found Bayes-floor corpus candidate: {f} ({n} episodes)')
        break

if not target:
    # Use Phase A 19,062 and filter (may need W8 + remove one more)
    for f in glob.glob('**/*verdict_matrix*v6*.json', recursive=True):
        with open(f) as fh:
            data = json.load(fh)
        eps = data if isinstance(data, list) else list(data.get('episodes', data).values())
        if len(eps) > 18000:
            target = f
            print(f'Using full corpus, will need filtering: {f}')
            break

with open(target) as f:
    eps = json.load(f)
if isinstance(eps, dict):
    eps = list(eps.get('episodes', eps).values())

# Filter to W8 + verify subset matches 14,826 paper count
# Paper: "7-model Bayes-floor subsample (14,826)"
# This is even smaller than W8 (16,944), so 7-model

print(f'Loaded {len(eps)} episodes')

# Compute 4 projection Bayes floors
def compute_bayes_floor(episodes, projection_fn):
    fibers = defaultdict(list)
    for ep in episodes:
        try:
            pi_val = projection_fn(ep)
            verdict = 1 if ep.get('v4_hard') else 0
            fibers[pi_val].append(verdict)
        except Exception:
            continue
    
    if not fibers:
        return 0, 0, 0
    
    total = sum(len(v) for v in fibers.values())
    bayes_err = 0
    mixed = 0
    for fiber, verdicts in fibers.items():
        n = len(verdicts)
        n_violate = sum(verdicts)
        p_violate = n_violate / n
        p_pass = 1 - p_violate
        if p_violate > 0 and p_pass > 0:
            mixed += 1
        bayes_err += (n / total) * min(p_violate, p_pass)
    
    return bayes_err, mixed, len(fibers), total

# π_term: terminal output / final state
def pi_term(ep):
    return ep.get('terminal_state') or ep.get('final_diagnosis') or str(ep.get('end_state', ''))

# π_aset: action multiset (sorted unique)
def pi_aset(ep):
    actions = ep.get('actions', []) or [s.get('action_id') for s in ep.get('steps', [])]
    return tuple(sorted(set(actions)))

# π_nord: ordered actions
def pi_nord(ep):
    actions = ep.get('actions', []) or [s.get('action_id') for s in ep.get('steps', [])]
    return tuple(actions)

# π_nctx: timed actions (no patient state)
def pi_nctx(ep):
    actions = ep.get('actions', []) or [s.get('action_id') for s in ep.get('steps', [])]
    timestamps = ep.get('timestamps', []) or [s.get('timestamp', 0) for s in ep.get('steps', [])]
    return tuple(zip(actions, timestamps))

projections = {
    'term': pi_term,
    'aset': pi_aset,
    'nord': pi_nord,
    'nctx': pi_nctx,
}

paper_targets = {'term': 0.436, 'aset': 0.024, 'nord': 0.003, 'nctx': 0.003}

print(f'\\n{"Proj":<6}{"ε* recomputed":<18}{"ε* paper":<12}{"Δ":<10}{"Match?":<8}')
print('-' * 60)
results = {}
for proj_name, proj_fn in projections.items():
    bayes_err, mixed, n_fibers, total = compute_bayes_floor(eps, proj_fn)
    paper_eps = paper_targets[proj_name]
    delta = bayes_err - paper_eps
    match = abs(delta) < 0.02 if proj_name == 'term' else abs(delta) < 0.005
    
    print(f'{proj_name:<6}{bayes_err:<18.4f}{paper_eps:<12.4f}{delta:+.4f}    {"OK" if match else "DIFF"}')
    results[proj_name] = {
        'recomputed': bayes_err,
        'paper': paper_eps,
        'delta': delta,
        'mixed_fibers': mixed,
        'total_fibers': n_fibers,
        'match': match
    }

# Order check
order_check = (results['term']['recomputed'] > results['aset']['recomputed'] > 
               results['nord']['recomputed'] >= results['nctx']['recomputed'])
print(f'\\nMagnitude order term > aset > nord >= nctx: {order_check}')

with open('reports/path_d_day3/v6_bayes_floor_verification.json', 'w') as f:
    json.dump({
        'corpus': target,
        'n_episodes': len(eps),
        'results': results,
        'order_preserved': order_check
    }, f, indent=2)
print('Saved')
PYEOF

GATE:
  - PASS: Order preserved AND ε*term within ±0.02 AND others within ±0.005
  - FAIL: order violated → STOP
```

---

### STEP V7: Verify Paper §App G Replay loss 84.2/63.2 (15분)

**Paste after V6:**

```
Paper §App G replay scorer detection loss 재현.

Paper §1 abstract: "replaying released scoring paradigms loses 63.2-84.2% of TCC detections"
Paper §5.5: "MAB- and AC-style rubrics miss 63.2/84.2% of TCC detections"

(63.2% AC-style, 84.2% MAB-style — paper App. G)

python << 'PYEOF'
import json, glob, os

target = None
for f in glob.glob('**/*verdict_matrix*v6*.json', recursive=True):
    with open(f) as fh:
        data = json.load(fh)
    eps = data if isinstance(data, list) else list(data.get('episodes', data).values())
    if 18000 < len(eps) < 20000:
        target = f
        break

with open(target) as f:
    eps = json.load(f)
if isinstance(eps, dict):
    eps = list(eps.get('episodes', eps).values())

n_total = len(eps)

# TCC detections = v4_hard True (has hard violations)
tcc_detections = [e for e in eps if e.get('v4_hard')]
n_tcc = len(tcc_detections)

# MAB-style replay miss = TCC detected AND mab_proxy passed
# (i.e., MAB-style scorer would PASS this episode despite TCC failing)
mab_miss = [e for e in tcc_detections if e.get('mab_proxy')]
mab_miss_pct = 100 * len(mab_miss) / max(n_tcc, 1)

# AC-style replay miss = TCC detected AND ac_proxy passed
ac_miss = [e for e in tcc_detections if e.get('ac_proxy')]
ac_miss_pct = 100 * len(ac_miss) / max(n_tcc, 1)

print(f'Total episodes: {n_total}')
print(f'TCC detections: {n_tcc} ({100*n_tcc/n_total:.1f}%)')
print()
print(f'MAB-style replay miss: {len(mab_miss)}/{n_tcc} = {mab_miss_pct:.1f}%')
print(f'  Paper: 84.2%, Δ: {mab_miss_pct - 84.2:+.1f}pp')
print()
print(f'AC-style replay miss: {len(ac_miss)}/{n_tcc} = {ac_miss_pct:.1f}%')
print(f'  Paper: 63.2%, Δ: {ac_miss_pct - 63.2:+.1f}pp')

mab_match = abs(mab_miss_pct - 84.2) < 5
ac_match = abs(ac_miss_pct - 63.2) < 5

print(f'\\nGATE:')
print(f'  MAB miss within ±5pp: {mab_match}')
print(f'  AC miss within ±5pp: {ac_match}')

with open('reports/path_d_day3/v6_replay_loss_verification.json', 'w') as f:
    json.dump({
        'corpus': target,
        'n_total': n_total,
        'n_tcc': n_tcc,
        'mab_miss_recomputed': mab_miss_pct,
        'mab_miss_paper': 84.2,
        'mab_match': bool(mab_match),
        'ac_miss_recomputed': ac_miss_pct,
        'ac_miss_paper': 63.2,
        'ac_match': bool(ac_match),
    }, f, indent=2)
PYEOF

GATE:
  - PASS: Both within ±5pp
  - PARTIAL: One matches → minor disclosure
  - FAIL: Both shift → §App G update 필요
```

---

### STEP V8: Verification summary + decision (10분)

**Paste after V7:**

```
V6 Full verification 결과 종합.

python << 'PYEOF'
import json
import os

reports_dir = 'reports/path_d_day3/'
verifications = {
    'eta': 'v6_eta_verification.json',
    'strict_fa': 'v6_strict_fa_verification.json',
    'reversal': 'v6_reversal_verification.json',
    'table1': 'v6_table1_verification.json',
    'bayes': 'v6_bayes_floor_verification.json',
    'replay': 'v6_replay_loss_verification.json',
}

results = {}
for k, fname in verifications.items():
    fpath = os.path.join(reports_dir, fname)
    if os.path.exists(fpath):
        results[k] = json.load(open(fpath))

print('=' * 80)
print('V6 PAPER NUMBERS VERIFICATION SUMMARY')
print('=' * 80)
print()

# η²
if 'eta' in results:
    r = results['eta']
    print(f"η²(eval): {r['eta_eval_recomputed']:.4f} vs paper {r['eta_eval_paper']:.4f}  Δ={r['delta_eval']:+.4f}  {'✓' if r['gate_eval_match'] else '✗'}")
    print(f"η²(run):  {r['eta_run_recomputed']:.4f} vs paper {r['eta_run_paper']:.4f}  Δ={r['delta_run']:+.4f}  {'✓' if r['gate_run_match'] else '✗'}")
    print()

# Strict FA
if 'strict_fa' in results:
    r = results['strict_fa']
    print(f"Strict FA: {r['strict_3way_fa_rate_pct']:.2f}% vs paper {r['paper_rate_pct']:.1f}%  Δ={r['delta_pct']:+.2f}pp  {'✓' if r['gate_fa_match'] else '✗'}")
    print(f"FA count: {r['strict_3way_fa_n']} vs paper {r['paper_n']}  Δ={r['delta_n']:+d}  {'✓' if r['gate_n_match'] else '✗'}")
    print()

# Reversal
if 'reversal' in results:
    r = results['reversal']
    print(f"Reversal: {r['reversal_pct']:.1f}% vs paper {r['paper_reversal_pct']:.1f}%  Δ={r['delta_reversal']:+.1f}pp  {'✓' if r['gate_reversal_match'] else '✗'}")
    print(f"Kendall W: {r['kendall_W']:.3f} vs paper {r['paper_kendall_W']:.3f}  Δ={r['delta_W']:+.3f}  {'✓' if r['gate_W_match'] else '✗'}")
    print()

# Table 1
if 'table1' in results:
    r = results['table1']
    print('Table 1 per-evaluator FA:')
    for ev, info in r['results'].items():
        print(f"  {ev}: pass {info['recomputed_pass_pct']:.1f}% vs {info['paper_pass_pct']:.1f}%  fa {info['recomputed_fa_pct']:.1f}% vs {info['paper_fa_pct']:.1f}%  {'✓' if info['match'] else '✗'}")
    print()

# Bayes
if 'bayes' in results:
    r = results['bayes']
    print('Bayes error floor:')
    for proj, info in r['results'].items():
        print(f"  ε*{proj}: {info['recomputed']:.4f} vs paper {info['paper']:.4f}  Δ={info['delta']:+.4f}  {'✓' if info['match'] else '✗'}")
    print(f"  Order preserved: {r['order_preserved']}")
    print()

# Replay
if 'replay' in results:
    r = results['replay']
    print(f"MAB miss: {r['mab_miss_recomputed']:.1f}% vs paper {r['mab_miss_paper']:.1f}%  {'✓' if r['mab_match'] else '✗'}")
    print(f"AC miss:  {r['ac_miss_recomputed']:.1f}% vs paper {r['ac_miss_paper']:.1f}%  {'✓' if r['ac_match'] else '✗'}")
    print()

# Aggregate decision
print('=' * 80)
print('AGGREGATE DECISION')
print('=' * 80)

all_pass = True
issues = []

for k in results:
    r = results[k]
    if 'gate' in str(r).lower():
        # Find any False gates
        def check_recursive(d, path=''):
            global all_pass, issues
            if isinstance(d, dict):
                for kk, vv in d.items():
                    if 'match' in kk.lower() or 'gate' in kk.lower():
                        if vv is False:
                            all_pass = False
                            issues.append(f'{path}.{kk}: FAIL')
                    elif isinstance(vv, dict):
                        check_recursive(vv, f'{path}.{kk}')
        check_recursive(r, k)

if all_pass:
    print('✓ ALL paper numbers REPRODUCE within tolerance')
    print('  → Frontier launch GO')
else:
    print('Issues:')
    for i in issues:
        print(f'  - {i}')
    print()
    print('Decision matrix:')
    print('  - 1-2 issues, all <2pp: PARTIAL → frontier GO + disclosure paragraph')
    print('  - 3+ issues OR any >5pp: FAIL → STOP, paper main text revision')

# Save aggregate
with open('reports/path_d_day3/v6_verification_summary.json', 'w') as f:
    json.dump({
        'all_pass': all_pass,
        'issues': issues,
        'individual_results': results,
    }, f, indent=2)
print()
print('Saved: reports/path_d_day3/v6_verification_summary.json')
PYEOF

이 결과 보고 후 결정:
  Case ALL PASS: Frontier launch GO (다음 prompt set)
  Case PARTIAL (1-2 issues, small): Frontier launch GO + paper §App disclosure
  Case FAIL (3+ issues OR >5pp): STOP, paper main text 수정 필요
```

---

## Frontier Launch — 4 STEPs (~5h)

V6 verification PASS or PARTIAL 후에만 진행.

---

### STEP F1: Frontier endpoint setup + smoke (15분)

**Paste after V8 PASS:**

```
Frontier API endpoint setup + smoke test.

Path A: V6 manual 706 scenarios + 2 frontier models (Claude Opus + GPT-5)

Step 1: API key validation
echo $ANTHROPIC_API_KEY | head -c 20
echo $OPENAI_API_KEY | head -c 20

Step 2: SDK 설치 확인
python -c "import anthropic; print('anthropic:', anthropic.__version__)"
python -c "import openai; print('openai:', openai.__version__)"

Step 3: Smoke 1 episode each model on V6 scenario
SAMPLE_SCENARIO=$(find configs/scenarios -name "*.yaml" | grep -v sgsc | head -1)
echo "Sample scenario: $SAMPLE_SCENARIO"

Step 4: Test API calls
python << 'PYEOF'
import os, time

# Anthropic test
import anthropic
client = anthropic.Anthropic()
resp = client.messages.create(
    model='claude-opus-4-7',
    max_tokens=100,
    messages=[{'role': 'user', 'content': 'Test'}]
)
print(f'Anthropic OK: {resp.usage.input_tokens} in, {resp.usage.output_tokens} out')

# OpenAI test
import openai
client = openai.OpenAI()
resp = client.chat.completions.create(
    model='gpt-5',
    messages=[{'role': 'user', 'content': 'Test'}],
    max_completion_tokens=100
)
print(f'OpenAI OK: {resp.usage.prompt_tokens} in, {resp.usage.completion_tokens} out')
PYEOF

Step 5: Single full episode test (Claude Opus on 1 V6 scenario)
PYTHONPATH=. python scripts/experiments/run_frontier.py \
  --model claude-opus-4-7 \
  --scenarios-dir configs/scenarios \
  --max-scenarios 1 \
  --runs-per-scenario 1 \
  --output /tmp/frontier_smoke/claude_opus/

검증:
- Episode JSON 산출
- Trace에 actions
- Compliance score 계산
- API cost 합리적 ($0.50 미만)

GATE: 2 frontier 모두 smoke PASS → STEP F2
```

---

### STEP F2: Path A frontier launch (5분 setup, ~4-6h compute)

**Paste after F1:**

```
V6 706 scenarios × 3 runs × 2 frontier models = 4,236 episodes

Step 1: Watchdog setup
cat > /tmp/frontier_watchdog.sh << 'EOF'
#!/bin/bash
LAUNCH_TIME=$(date +%s)
TARGET=4236
LOG=/tmp/frontier_watchdog.log

while true; do
  sleep 600
  ELAPSED=$(($(date +%s) - LAUNCH_TIME))
  COUNT=$(find results/v6_frontier -name "*.json" 2>/dev/null | wc -l)
  RATE=$(echo "scale=1; $COUNT / ($ELAPSED / 3600)" | bc)
  echo "[$(date)] $COUNT/$TARGET, rate ${RATE}/h, elapsed ${ELAPSED}s" >> $LOG
  
  if [ $ELAPSED -gt 1800 ] && [ $COUNT -lt 100 ]; then
    echo "ABORT: only $COUNT after 30min" >> $LOG
    pkill -f run_frontier
    exit 1
  fi
done
EOF
chmod +x /tmp/frontier_watchdog.sh
nohup /tmp/frontier_watchdog.sh > /dev/null 2>&1 &

Step 2: Backup pre-launch
mkdir -p results/v6_full_backup_$(date +%Y%m%d_%H%M)
cp -r results/v6_full results/v6_full_backup_$(date +%Y%m%d_%H%M)/ 2>/dev/null || true

Step 3: Launch parallel frontier
mkdir -p results/v6_frontier/

# Claude Opus 4.7
nohup PYTHONPATH=. python scripts/experiments/run_frontier.py \
  --model claude-opus-4-7 \
  --scenarios-dir configs/scenarios \
  --runs-per-scenario 3 \
  --concurrent 10 \
  --output results/v6_frontier/claude_opus/ \
  --resume \
  > /tmp/frontier_claude.log 2>&1 &
echo $! > /tmp/frontier_claude.pid

# GPT-5
nohup PYTHONPATH=. python scripts/experiments/run_frontier.py \
  --model gpt-5 \
  --scenarios-dir configs/scenarios \
  --runs-per-scenario 3 \
  --concurrent 10 \
  --output results/v6_frontier/gpt5/ \
  --resume \
  > /tmp/frontier_gpt5.log 2>&1 &
echo $! > /tmp/frontier_gpt5.pid

Step 4: 30min check
sleep 1800
echo "=== 30min status ==="
echo "Claude Opus:"
find results/v6_frontier/claude_opus -name "*.json" 2>/dev/null | wc -l
tail -5 /tmp/frontier_claude.log
echo "GPT-5:"
find results/v6_frontier/gpt5 -name "*.json" 2>/dev/null | wc -l
tail -5 /tmp/frontier_gpt5.log

산출 보고:
- Both endpoints alive
- 30min episode counts
- Estimated rate per model
- API errors (rate limit, 5xx)

GATE:
  - Both producing > 50 episodes/30min
  - No persistent 5xx errors
  - Estimated completion within 6h
  - PASS → wait for completion (4-6h)
  - FAIL → investigate
```

---

### STEP F3: Frontier results scoring (after compute, ~1h)

**Paste when frontier compute completes:**

```
Frontier 결과 scoring + V6 verdict matrix 통합.

Step 1: Episode count verification
for model in claude_opus gpt5; do
  n=$(find results/v6_frontier/$model -name "*.json" | wc -l)
  echo "$model: $n / 2118 expected"
done

Step 2: Score frontier episodes with full evaluator suite
PYTHONPATH=. python scripts/experiments/score_frontier_episodes.py \
  --episodes-dir results/v6_frontier/ \
  --output reports/path_d_day3/verdict_matrix_v6_frontier.json \
  --evaluators TOM,ASC,PAF,CwT,TCC,DxEM,AC,MAB,C2,ACov

Step 3: Combine V6 base + frontier verdicts
python << 'PYEOF'
import json
v6_base = json.load(open('reports/verdict_matrix_v6_full.json'))
v6_frontier = json.load(open('reports/path_d_day3/verdict_matrix_v6_frontier.json'))

# Merge
v6_combined = (v6_base if isinstance(v6_base, list) else list(v6_base.values())) + \
              (v6_frontier if isinstance(v6_frontier, list) else list(v6_frontier.values()))

print(f'V6 base: {len(v6_base)}')
print(f'Frontier: {len(v6_frontier)}')
print(f'Combined: {len(v6_combined)}')

with open('reports/path_d_day3/verdict_matrix_v6_combined.json', 'w') as f:
    json.dump(v6_combined, f)
PYEOF

Step 4: Recompute paper headline numbers on combined corpus
이 작업은 STEP V2-V7과 동일한 코드를 v6_combined에 적용:

PYTHONPATH=. python scripts/experiments/recompute_paper_numbers.py \
  --corpus reports/path_d_day3/verdict_matrix_v6_combined.json \
  --output reports/path_d_day3/v6_with_frontier_verification.json

산출 보고:
- Per-frontier-model CGA distribution
- Combined corpus stats vs V6-only
- η², FA, reversal, Bayes, replay 모두 with frontier
- Paper §5.1 5+2=7 vendor families 효과
```

---

### STEP F4: Paper integration + macro lock (1h)

**Paste after F3:**

```
Frontier integration into paper.

Step 1: Macro file consolidation
python scripts/experiments/generate_paper_macros.py \
  --v6-base reports/verdict_matrix_v6_full.json \
  --v6-frontier reports/path_d_day3/verdict_matrix_v6_frontier.json \
  --v7-base reports/verdict_matrix_v7_full.json \
  --output paper/auto_numbers_final.tex

Macros 산출:
- v6 verified numbers (post-verification)
- v6+frontier numbers (paper §5.1 update)
- v7.3 bridge numbers (corrected)
- Frontier-specific (per-model CGA, ranking)

Step 2: Paper text drafting (anonymous-user 직접):

§5.1 wording update:
"primary 9 open-weight models spanning 5 vendor families ... + 2 frontier 
closed-weight models (Claude Opus 4.7 from Anthropic, GPT-5 from OpenAI)"

§5.6 Table update:
Add 2 frontier rows to ranking tables

§App SGSC bridge:
V7.3 bridge experiment paragraph (corrected metrics)

§App Frontier replication:
"Frontier model replication (4,236 episodes)"
- η², FA, reversal results with frontier
- Confirms paper headline holds for frontier

§App Reproducibility:
- Verification 결과 disclosure
- Code commit hash + verdict matrix SHA-256

산출 보고:
- Macro file consolidated
- Paper sections drafted (paste-ready)
- Verification + frontier 결과 통합
```

---

## Decision matrix at each STEP

| STEP | Outcome | Action |
|---|---|---|
| V1 | All corpora identified | Continue V2 |
| V2 | η² match | Continue V3 |
| V2 | η² order preserved, values shift | Disclosure, Continue V3 |
| V2 | η² order violated | STOP, paper revision |
| V3-V7 | Each metric within tolerance | Continue |
| V3-V7 | Within tolerance with disclosure | Continue + draft disclosure |
| V3-V7 | Outside tolerance | STOP, evaluate impact |
| V8 | All PASS | Frontier launch F1 |
| V8 | 1-2 partial | Frontier launch + disclosure |
| V8 | 3+ FAIL | STOP, paper revision |

---

## Total time

```
V1-V8 verification: ~2h
F1 setup + smoke: 15min
F2 launch + 30min monitor: 35min
F2 wait for compute: 4-6h
F3 scoring: 1h
F4 integration: 1h

Total: ~8-10h with sleep window in between
```

```
5/3 evening (16:00 시작 가정):
  16:00-18:00: V1-V8 verification
  18:00: V8 결과 확인 + decision
  
  Case PASS:
    18:00-18:15: F1 smoke
    18:15: F2 launch
    18:15-23:00: Monitor first hour, sleep
    23:00-5/4 06:00: Frontier compute (~6h)
    5/4 06:00 wake: F3 scoring (1h)
    5/4 07:00: F4 paper integration (1h)
    5/4 08:00: Paper polish 본격 시작
    5/4-5/5: Polish
    5/6: Submit
```

---

## Critical reminders

1. **각 STEP의 GATE**가 있는 이유: small shift는 disclosure 가능, large shift는 paper revision 필요
2. **Verification은 frontier 보다 우선**: 만약 V6 numbers가 unreliable이면 frontier 결과도 의미 약함
3. **Disclosure는 paper-strengthening**: "We verified all reported numbers reproduce within ±X% under current code"
4. **Reproducibility는 NeurIPS critical**: reviewer가 reproduce 못 하면 paper integrity 위협

---

## Single sentence summary

**STEP V1-V8** 까지 V6 paper 모든 headline numbers를 *current code*로 재현 검증 → PASS or PARTIAL 시 **F1-F4** Path A frontier launch (V6 + Claude Opus + GPT-5) → 5/4 morning 결과 + integration → 5/4-5/5 polish → 5/6 submit.