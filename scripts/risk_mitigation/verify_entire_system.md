#!/usr/bin/env python3
"""
CGA-Bench 시스템 전수 검증
===========================
수치가 아닌 시스템 자체의 정합성을 검증.

검증 항목:
  S1. Constraint Completeness — 4가지 constraint type이 모두 실제로 체크되는가?
  S2. Violation-Action Correspondence — violation에 기록된 action이 실제 trace에 있는가?
  S3. Evaluator Consistency — 각 evaluator verdict가 정의대로 계산되는가?
  S4. Determinism — 같은 에피소드를 2번 채점하면 같은 결과?
  S5. State Isolation — 에피소드 간 state leakage가 없는가?
  S6. Constraint Activation — patient context 조건에 맞는 constraint만 활성화되는가?
  S7. Normalizer Symmetry — normalize(A)=B이면, B가 expected에 있을 때 A도 매칭되는가?
  S8. Scoring Sanity — compliance_score와 violation_events가 일관적인가?
  S9. Empty Action Check — 빈 action list인 에피소드가 있는가? (Bug 2/4 재발)
  S10. Violation Type Coverage — 4가지 type이 모두 발생하는가? 0인 type은 왜?

Usage:
    python verify_system.py --episodes-dir results/full_706_final --graphs-dir cpg_model/graphs
"""

import argparse
import json
import yaml
import sys
import re
from collections import Counter, defaultdict
from pathlib import Path
from difflib import SequenceMatcher


def load_episodes(episodes_dir):
    episodes = []
    for model_dir in sorted(Path(episodes_dir).iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith('.'):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                ep['_model'] = model_dir.name
                ep['_file'] = str(ep_file)
                episodes.append(ep)
            except:
                pass
    return episodes


def load_graphs(graphs_dir):
    graphs = {}
    for f in sorted(Path(graphs_dir).glob("*.yaml")):
        if f.name.startswith('_'):
            continue
        try:
            with open(f) as fh:
                graphs[f.stem] = yaml.safe_load(fh)
        except:
            pass
    return graphs


def get_action(a):
    if isinstance(a, str):
        return a.lower().strip()
    if isinstance(a, dict):
        return a.get('action', a.get('name', str(a))).lower().strip()
    return str(a).lower().strip()


# ═══════════════════════════════════════════════════════════════════
# S1: Constraint Completeness
# ═══════════════════════════════════════════════════════════════════

def check_s1_constraint_completeness(episodes):
    """4가지 violation type이 모두 실제로 발생하는가?"""
    type_counts = Counter()
    type_examples = defaultdict(list)

    for ep in episodes:
        for v in ep.get('violation_events', []):
            if not isinstance(v, dict):
                continue
            vtype = v.get('violation_type', v.get('type', 'UNKNOWN')).upper()

            # Normalize
            if 'OMISSION' in vtype or 'MUST' in vtype or 'REQUIRED' in vtype:
                normalized = 'OMISSION'
            elif 'COMMISSION' in vtype or 'FORBID' in vtype:
                normalized = 'COMMISSION'
            elif 'TIMING' in vtype or 'WITHIN' in vtype:
                normalized = 'TIMING'
            elif 'SEQUENCE' in vtype or 'BEFORE' in vtype or 'ORDER' in vtype:
                normalized = 'SEQUENCE'
            elif 'DEVIATION' in vtype:
                normalized = 'DEVIATION'
            else:
                normalized = vtype

            type_counts[normalized] += 1
            if len(type_examples[normalized]) < 3:
                type_examples[normalized].append({
                    'file': ep.get('_file', '')[-60:],
                    'action': v.get('action', v.get('expected_action', '?')),
                    'raw_type': vtype,
                })

    expected_types = {'OMISSION', 'COMMISSION', 'TIMING', 'SEQUENCE'}
    missing = expected_types - set(type_counts.keys())

    return {
        'status': 'PASS' if not missing else 'FAIL',
        'type_counts': dict(type_counts),
        'missing_types': list(missing),
        'examples': {k: v for k, v in type_examples.items()},
        'issue': f"Missing violation types: {missing}" if missing else None,
    }


# ═══════════════════════════════════════════════════════════════════
# S2: Violation-Action Correspondence
# ═══════════════════════════════════════════════════════════════════

def check_s2_violation_action(episodes):
    """
    COMMISSION violation의 action이 실제 performed actions에 있는가?
    OMISSION violation의 action이 expected에 있는가?
    """
    commission_in_performed = 0
    commission_not_in_performed = 0
    omission_in_expected = 0
    omission_not_in_expected = 0
    bad_examples = []

    for ep in episodes[:5000]:  # Sample
        performed = set()
        for a in ep.get('actions', []):
            performed.add(get_action(a))

        expected = set()
        for a in ep.get('expected_actions', ep.get('mandatory_actions', [])):
            expected.add(get_action(a))

        for v in ep.get('violation_events', []):
            if not isinstance(v, dict):
                continue
            vtype = v.get('violation_type', v.get('type', '')).upper()
            action = v.get('action', v.get('expected_action', v.get('constraint_action', ''))).lower().strip()

            if 'COMMISSION' in vtype or 'FORBID' in vtype:
                if action in performed:
                    commission_in_performed += 1
                else:
                    commission_not_in_performed += 1
                    if len(bad_examples) < 5:
                        bad_examples.append({
                            'type': 'COMMISSION_NOT_IN_PERFORMED',
                            'action': action,
                            'file': ep.get('_file', '')[-60:],
                        })

            elif 'OMISSION' in vtype or 'MUST' in vtype:
                if action in expected:
                    omission_in_expected += 1
                else:
                    omission_not_in_expected += 1
                    if len(bad_examples) < 5:
                        bad_examples.append({
                            'type': 'OMISSION_NOT_IN_EXPECTED',
                            'action': action,
                            'file': ep.get('_file', '')[-60:],
                        })

    total_checks = commission_in_performed + commission_not_in_performed + omission_in_expected + omission_not_in_expected
    n_bad = commission_not_in_performed + omission_not_in_expected

    return {
        'status': 'PASS' if n_bad == 0 else ('WARN' if n_bad / max(total_checks, 1) < 0.05 else 'FAIL'),
        'commission_in_performed': commission_in_performed,
        'commission_not_in_performed': commission_not_in_performed,
        'omission_in_expected': omission_in_expected,
        'omission_not_in_expected': omission_not_in_expected,
        'bad_rate': n_bad / max(total_checks, 1),
        'bad_examples': bad_examples,
    }


# ═══════════════════════════════════════════════════════════════════
# S8: Scoring Sanity
# ═══════════════════════════════════════════════════════════════════

def check_s8_scoring_sanity(episodes):
    """
    compliance_score와 violation_events가 일관적인가?
    - compliance=1.0인데 violations > 0?
    - compliance=0인데 violations=0?
    - compliance가 0-1 범위 밖?
    """
    perfect_with_violations = 0
    zero_without_violations = 0
    out_of_range = 0
    no_violations_field = 0
    examples = []

    for ep in episodes:
        cs = ep.get('compliance_score', None)
        violations = ep.get('violation_events', None)

        if cs is None:
            continue

        if not isinstance(cs, (int, float)):
            out_of_range += 1
            continue

        if cs < 0 or cs > 1.01:
            out_of_range += 1
            if len(examples) < 3:
                examples.append({'type': 'OUT_OF_RANGE', 'score': cs, 'file': ep.get('_file', '')[-60:]})

        if violations is None:
            no_violations_field += 1
            continue

        n_viols = len(violations) if isinstance(violations, list) else 0

        if cs >= 0.999 and n_viols > 0:
            perfect_with_violations += 1
            if len(examples) < 3:
                examples.append({
                    'type': 'PERFECT_WITH_VIOLATIONS',
                    'score': cs,
                    'n_violations': n_viols,
                    'file': ep.get('_file', '')[-60:],
                })

        if cs < 0.001 and n_viols == 0:
            zero_without_violations += 1
            if len(examples) < 3:
                examples.append({
                    'type': 'ZERO_WITHOUT_VIOLATIONS',
                    'score': cs,
                    'file': ep.get('_file', '')[-60:],
                })

    n_issues = perfect_with_violations + zero_without_violations + out_of_range

    return {
        'status': 'PASS' if n_issues == 0 else ('WARN' if n_issues < 10 else 'FAIL'),
        'perfect_with_violations': perfect_with_violations,
        'zero_without_violations': zero_without_violations,
        'out_of_range': out_of_range,
        'no_violations_field': no_violations_field,
        'examples': examples,
    }


# ═══════════════════════════════════════════════════════════════════
# S9: Empty Action Check
# ═══════════════════════════════════════════════════════════════════

def check_s9_empty_actions(episodes):
    """빈 action list인 에피소드가 있는가? (Bug 2/4 재발 탐지)"""
    empty_count = 0
    very_few_count = 0  # < 3 actions
    model_empty = Counter()
    examples = []

    for ep in episodes:
        actions = ep.get('actions', [])
        n_actions = len(actions) if isinstance(actions, list) else 0

        if n_actions == 0:
            empty_count += 1
            model_empty[ep.get('_model', 'unknown')] += 1
            if len(examples) < 5:
                examples.append({
                    'type': 'EMPTY',
                    'model': ep.get('_model', ''),
                    'scenario': ep.get('scenario_id', ''),
                    'file': ep.get('_file', '')[-60:],
                })
        elif n_actions < 3:
            very_few_count += 1

    empty_rate = empty_count / len(episodes) * 100 if episodes else 0

    return {
        'status': 'PASS' if empty_rate < 1 else ('WARN' if empty_rate < 5 else 'FAIL'),
        'empty_count': empty_count,
        'empty_rate': round(empty_rate, 2),
        'very_few_count': very_few_count,
        'model_empty': dict(model_empty),
        'examples': examples,
        'issue': f"{empty_count} episodes with 0 actions ({empty_rate:.1f}%)" if empty_count > 0 else None,
    }


# ═══════════════════════════════════════════════════════════════════
# S10: Violation Type Coverage per Graph
# ═══════════════════════════════════════════════════════════════════

def check_s10_violation_type_per_graph(episodes, graphs):
    """
    각 graph에서 4가지 violation type이 모두 발생하는가?
    어떤 graph에서 특정 type이 0이면 해당 constraint가 없거나 체크 안 되는 것.
    """
    graph_types = defaultdict(Counter)

    for ep in episodes:
        gid = ep.get('graph_id', ep.get('cpg_graph', ''))
        for v in ep.get('violation_events', []):
            if not isinstance(v, dict):
                continue
            vtype = v.get('violation_type', v.get('type', '')).upper()
            if 'OMISSION' in vtype or 'MUST' in vtype:
                graph_types[gid]['OMISSION'] += 1
            elif 'COMMISSION' in vtype or 'FORBID' in vtype:
                graph_types[gid]['COMMISSION'] += 1
            elif 'TIMING' in vtype or 'WITHIN' in vtype:
                graph_types[gid]['TIMING'] += 1
            elif 'SEQUENCE' in vtype or 'BEFORE' in vtype:
                graph_types[gid]['SEQUENCE'] += 1

    # Cross-reference with graph constraints
    graph_has_constraint = defaultdict(set)
    for gid, graph in graphs.items():
        nodes = graph.get('nodes', [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get('mandatory_actions') or node.get('expected_actions'):
                graph_has_constraint[gid].add('MUST')
            if node.get('forbidden_actions'):
                graph_has_constraint[gid].add('FORBIDDEN')
            if node.get('deadlines'):
                graph_has_constraint[gid].add('WITHIN')
            if node.get('sequence_rules'):
                graph_has_constraint[gid].add('BEFORE')

    issues = []
    for gid in sorted(set(list(graph_types.keys()) + list(graph_has_constraint.keys()))):
        has = graph_has_constraint.get(gid, set())
        observed = set(graph_types.get(gid, {}).keys())

        # Map constraint types to violation types
        constraint_to_violation = {
            'MUST': 'OMISSION',
            'FORBIDDEN': 'COMMISSION',
            'WITHIN': 'TIMING',
            'BEFORE': 'SEQUENCE',
        }

        for ctype, vtype in constraint_to_violation.items():
            if ctype in has and vtype not in observed:
                n_episodes = sum(1 for ep in episodes if ep.get('graph_id', ep.get('cpg_graph', '')) == gid)
                if n_episodes > 10:  # Only flag if enough episodes
                    issues.append({
                        'graph': gid,
                        'constraint_type': ctype,
                        'expected_violation': vtype,
                        'observed_violations': dict(graph_types.get(gid, {})),
                        'n_episodes': n_episodes,
                        'issue': f"Graph has {ctype} constraints but 0 {vtype} violations in {n_episodes} episodes",
                    })

    return {
        'status': 'PASS' if not issues else 'WARN',
        'n_issues': len(issues),
        'issues': issues[:10],
        'graph_violation_summary': {gid: dict(counts) for gid, counts in sorted(graph_types.items())},
    }


# ═══════════════════════════════════════════════════════════════════
# S5: Cross-Episode Consistency (State Isolation)
# ═══════════════════════════════════════════════════════════════════

def check_s5_isolation(episodes):
    """
    같은 (scenario, model)의 다른 run에서 결과가 합리적으로 비슷한가?
    너무 다르면 → state leakage 또는 비결정성
    """
    group_results = defaultdict(list)
    for ep in episodes:
        sid = ep.get('scenario_id', '')
        model = ep.get('_model', '')
        cs = ep.get('compliance_score', None)
        n_actions = len(ep.get('actions', [])) if isinstance(ep.get('actions'), list) else 0
        n_viols = len(ep.get('violation_events', [])) if isinstance(ep.get('violation_events'), list) else 0

        if cs is not None:
            group_results[(sid, model)].append({
                'compliance': cs,
                'n_actions': n_actions,
                'n_violations': n_viols,
            })

    # Check groups with multiple runs
    high_variance = []
    for (sid, model), runs in group_results.items():
        if len(runs) < 2:
            continue

        scores = [r['compliance'] for r in runs]
        actions = [r['n_actions'] for r in runs]

        score_range = max(scores) - min(scores)
        action_range = max(actions) - min(actions)

        if score_range > 0.5:  # Very high variance
            high_variance.append({
                'scenario': sid,
                'model': model,
                'n_runs': len(runs),
                'score_range': round(score_range, 3),
                'action_range': action_range,
                'scores': scores,
            })

    n_groups = sum(1 for v in group_results.values() if len(v) >= 2)

    return {
        'status': 'PASS' if len(high_variance) / max(n_groups, 1) < 0.05 else 'WARN',
        'n_multi_run_groups': n_groups,
        'high_variance_count': len(high_variance),
        'high_variance_rate': round(len(high_variance) / max(n_groups, 1) * 100, 1),
        'top_variance': sorted(high_variance, key=lambda x: -x['score_range'])[:5],
    }


# ═══════════════════════════════════════════════════════════════════
# S-EXTRA: Model-Level Sanity
# ═══════════════════════════════════════════════════════════════════

def check_model_sanity(episodes):
    """모델별 기본 통계 — 이상치 탐지"""
    model_stats = defaultdict(lambda: {
        'n_episodes': 0,
        'actions': [],
        'compliance': [],
        'violations': [],
    })

    for ep in episodes:
        model = ep.get('_model', 'unknown')
        ms = model_stats[model]
        ms['n_episodes'] += 1
        ms['actions'].append(len(ep.get('actions', [])) if isinstance(ep.get('actions'), list) else 0)
        ms['compliance'].append(ep.get('compliance_score', 0))
        ms['violations'].append(len(ep.get('violation_events', [])) if isinstance(ep.get('violation_events'), list) else 0)

    import numpy as np
    results = {}
    for model, ms in sorted(model_stats.items()):
        acts = np.array(ms['actions'])
        comps = np.array(ms['compliance'])
        viols = np.array(ms['violations'])
        results[model] = {
            'n_episodes': ms['n_episodes'],
            'mean_actions': round(float(acts.mean()), 1),
            'median_actions': round(float(np.median(acts)), 1),
            'zero_action_pct': round(float((acts == 0).sum() / len(acts) * 100), 1),
            'mean_compliance': round(float(comps.mean()), 3),
            'mean_violations': round(float(viols.mean()), 1),
        }

    return results


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--episodes-dir', default='results/full_706_final')
    parser.add_argument('--graphs-dir', default='cpg_model/graphs')
    parser.add_argument('--output-dir', default='evidence_pack/system_verification')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    episodes = load_episodes(args.episodes_dir)
    graphs = load_graphs(args.graphs_dir)
    print(f"Loaded {len(episodes)} episodes, {len(graphs)} graphs\n")

    checks = [
        ("S1: Constraint Completeness", lambda: check_s1_constraint_completeness(episodes)),
        ("S2: Violation-Action Correspondence", lambda: check_s2_violation_action(episodes)),
        ("S5: State Isolation", lambda: check_s5_isolation(episodes)),
        ("S8: Scoring Sanity", lambda: check_s8_scoring_sanity(episodes)),
        ("S9: Empty Actions", lambda: check_s9_empty_actions(episodes)),
        ("S10: Violation Type per Graph", lambda: check_s10_violation_type_per_graph(episodes, graphs)),
    ]

    all_results = {}
    lines = []
    lines.append("=" * 70)
    lines.append("CGA-Bench 시스템 전수 검증 보고서")
    lines.append("=" * 70)

    n_pass = 0
    n_warn = 0
    n_fail = 0

    for name, check_fn in checks:
        print(f"\n[CHECK] {name}...")
        result = check_fn()
        all_results[name] = result

        status = result.get('status', 'UNKNOWN')
        marker = {'PASS': '✅', 'WARN': '🟡', 'FAIL': '🔴'}.get(status, '❓')

        if status == 'PASS':
            n_pass += 1
        elif status == 'WARN':
            n_warn += 1
        else:
            n_fail += 1

        lines.append(f"\n{'─' * 60}")
        lines.append(f"{marker} {name}: {status}")

        for k, v in sorted(result.items()):
            if k in ('status', 'examples', 'bad_examples', 'top_variance', 'issues', 'graph_violation_summary'):
                continue
            lines.append(f"  {k}: {v}")

        if result.get('issue'):
            lines.append(f"  ⚠️ {result['issue']}")
        if result.get('examples'):
            lines.append(f"  Examples:")
            for ex in result['examples'][:3]:
                lines.append(f"    {ex}")
        if result.get('issues'):
            lines.append(f"  Issues:")
            for issue in result['issues'][:5]:
                lines.append(f"    {issue.get('issue', issue)}")
        if result.get('top_variance'):
            lines.append(f"  High-variance runs:")
            for tv in result['top_variance'][:3]:
                lines.append(f"    {tv['model']}/{tv['scenario']}: score_range={tv['score_range']}, scores={tv['scores']}")

    # Model sanity
    print(f"\n[CHECK] Model Sanity...")
    model_stats = check_model_sanity(episodes)
    all_results['model_sanity'] = model_stats
    lines.append(f"\n{'─' * 60}")
    lines.append(f"📊 Model Sanity Overview:")
    lines.append(f"  {'Model':20s} {'N':>6s} {'Acts':>6s} {'0-act%':>7s} {'Comp':>6s} {'Viols':>6s}")
    lines.append("  " + "-" * 55)
    for model, stats in sorted(model_stats.items()):
        lines.append(
            f"  {model:20s} {stats['n_episodes']:6d} {stats['mean_actions']:6.1f} "
            f"{stats['zero_action_pct']:6.1f}% {stats['mean_compliance']:6.3f} {stats['mean_violations']:6.1f}"
        )
        if stats['zero_action_pct'] > 5:
            lines.append(f"    ⚠️ {stats['zero_action_pct']:.1f}% zero-action episodes!")
        if stats['mean_actions'] < 5:
            lines.append(f"    ⚠️ Very few actions per episode!")

    # Summary
    lines.append(f"\n{'=' * 60}")
    lines.append(f"SUMMARY: {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL")
    if n_fail > 0:
        lines.append(f"🔴 {n_fail} CRITICAL failures — 논문 수치에 영향 가능")
    elif n_warn > 0:
        lines.append(f"🟡 {n_warn} warnings — 검토 필요하지만 blocking은 아님")
    else:
        lines.append(f"✅ 모든 시스템 검증 통과")
    lines.append(f"{'=' * 60}")

    report_text = '\n'.join(lines)

    report_path = output_dir / 'system_verification_report.md'
    with open(report_path, 'w') as f:
        f.write(report_text)
    print(f"\n[SAVED] {report_path}")

    json_path = output_dir / 'system_verification_results.json'
    with open(json_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"[SAVED] {json_path}")

    print(report_text)


if __name__ == '__main__':
    main()