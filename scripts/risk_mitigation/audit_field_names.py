#!/usr/bin/env python3
"""
Graph YAML 필드명 감사 + 전체 스크립트 패치
=============================================
Graph YAML에서 실제 사용되는 필드명을 전수 스캔하고,
diagnostic 스크립트들이 참조하는 필드명과 대조.

Phase 1: 실제 필드명 확인
Phase 2: 118개 BUG를 올바른 필드명으로 재분류 (B1 재실행)
Phase 3: action_effects.yaml과 cross-reference

Usage:
    python audit_field_names.py --graphs-dir cpg_model/graphs --action-effects cpg_model/action_effects.yaml
"""

import argparse
import json
import yaml
import sys
from collections import Counter, defaultdict
from pathlib import Path
from difflib import get_close_matches, SequenceMatcher


def scan_all_field_names(graphs_dir):
    """Graph YAML의 모든 노드 필드명을 전수 스캔"""
    field_counts = Counter()
    field_examples = defaultdict(list)
    all_graphs = {}

    for f in sorted(Path(graphs_dir).glob("*.yaml")):
        if f.name.startswith('_'):
            continue
        try:
            with open(f) as fh:
                graph = yaml.safe_load(fh)
            all_graphs[f.stem] = graph
        except Exception as e:
            print(f"[WARN] {f}: {e}")
            continue

        nodes = graph.get('nodes', [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        for node in nodes:
            if not isinstance(node, dict):
                continue
            for key in node.keys():
                field_counts[key] += 1
                if len(field_examples[key]) < 3:
                    field_examples[key].append(f"{f.stem}/{node.get('id', node.get('name', '?'))}")

    return field_counts, field_examples, all_graphs


def find_action_fields(field_counts):
    """Action 관련 필드명 후보 식별"""
    action_keywords = ['action', 'expected', 'mandatory', 'required', 'forbidden',
                       'prohibited', 'contraindicated', 'allowed', 'optional',
                       'deadline', 'timing', 'sequence', 'before', 'order']

    action_fields = {}
    for field, count in field_counts.most_common():
        for kw in action_keywords:
            if kw in field.lower():
                action_fields[field] = count
                break

    return action_fields


def extract_actions_with_correct_fields(graphs, action_fields):
    """올바른 필드명을 사용하여 모든 action 추출"""

    # Determine the actual field names for expected/mandatory and forbidden
    expected_candidates = [f for f in action_fields if any(
        kw in f.lower() for kw in ['expected', 'mandatory', 'required_action']
    )]
    forbidden_candidates = [f for f in action_fields if any(
        kw in f.lower() for kw in ['forbidden', 'prohibited', 'contraindicated']
    )]
    deadline_candidates = [f for f in action_fields if any(
        kw in f.lower() for kw in ['deadline', 'time_limit', 'within']
    )]
    sequence_candidates = [f for f in action_fields if any(
        kw in f.lower() for kw in ['sequence', 'before', 'order']
    )]

    print(f"\n[FIELD MAPPING]")
    print(f"  Expected/Mandatory fields: {expected_candidates}")
    print(f"  Forbidden fields: {forbidden_candidates}")
    print(f"  Deadline fields: {deadline_candidates}")
    print(f"  Sequence fields: {sequence_candidates}")

    # Extract all actions using ALL candidate field names
    all_expected = set()
    all_forbidden = set()
    action_to_graph = defaultdict(set)

    for gid, graph in graphs.items():
        nodes = graph.get('nodes', [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        for node in nodes:
            if not isinstance(node, dict):
                continue

            # Try all possible field names for expected/mandatory
            for field in expected_candidates + ['expected_actions', 'mandatory_actions',
                                                 'required_actions', 'actions']:
                actions = node.get(field, [])
                if isinstance(actions, list):
                    for a in actions:
                        name = (a if isinstance(a, str) else
                                a.get('action', a.get('name', a.get('id', str(a)))))
                        name_clean = name.lower().strip() if isinstance(name, str) else str(name).lower().strip()
                        all_expected.add(name_clean)
                        action_to_graph[name_clean].add(gid)

            # Try all possible field names for forbidden
            for field in forbidden_candidates + ['forbidden_actions', 'prohibited_actions',
                                                   'contraindicated_actions']:
                actions = node.get(field, [])
                if isinstance(actions, list):
                    for a in actions:
                        name = (a if isinstance(a, str) else
                                a.get('action', a.get('name', a.get('id', str(a)))))
                        name_clean = name.lower().strip() if isinstance(name, str) else str(name).lower().strip()
                        all_forbidden.add(name_clean)
                        action_to_graph[name_clean].add(gid)

    return all_expected, all_forbidden, action_to_graph


def cross_reference_with_effects(all_actions, action_effects_path):
    """action_effects.yaml과 cross-reference"""
    try:
        with open(action_effects_path) as f:
            ae_data = yaml.safe_load(f)
    except:
        print(f"[ERROR] Cannot load {action_effects_path}")
        return set(), set(), {}

    ae_keys = set()
    if isinstance(ae_data, dict):
        ae_keys = {k.lower().strip() for k in ae_data.keys()}
    elif isinstance(ae_data, list):
        ae_keys = {e.get('action', '').lower().strip() for e in ae_data if isinstance(e, dict)}

    present = all_actions & ae_keys
    missing = all_actions - ae_keys

    # B1: close matches for missing
    b1_matches = {}
    for action in missing:
        close = get_close_matches(action, list(ae_keys), n=3, cutoff=0.7)
        if close:
            best = close[0]
            sim = SequenceMatcher(None, action, best).ratio()
            b1_matches[action] = {'match': best, 'similarity': round(sim, 3)}

    return present, missing, b1_matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--graphs-dir', default='cpg_model/graphs')
    parser.add_argument('--action-effects', default='cpg_model/action_effects.yaml')
    parser.add_argument('--output-dir', default='evidence_pack/field_audit')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Graph YAML 필드명 전수 감사")
    print("=" * 70)

    # Phase 1: Scan all field names
    print("\n[Phase 1] 필드명 스캔...")
    field_counts, field_examples, graphs = scan_all_field_names(args.graphs_dir)

    print(f"\n  전체 노드 필드명 (빈도순):")
    for field, count in field_counts.most_common():
        examples = field_examples[field][:2]
        print(f"    {field:35s}: {count:4d}  (예: {', '.join(examples)})")

    action_fields = find_action_fields(field_counts)
    print(f"\n  Action 관련 필드:")
    for field, count in sorted(action_fields.items(), key=lambda x: -x[1]):
        print(f"    {field:35s}: {count:4d}")

    # Phase 2: Extract actions with correct fields
    print(f"\n[Phase 2] 올바른 필드로 action 추출...")
    all_expected, all_forbidden, action_to_graph = extract_actions_with_correct_fields(
        graphs, action_fields
    )
    all_actions = all_expected | all_forbidden
    print(f"  Expected/Mandatory actions: {len(all_expected)}")
    print(f"  Forbidden actions: {len(all_forbidden)}")
    print(f"  Total unique actions: {len(all_actions)}")

    # Phase 3: Cross-reference with action_effects
    print(f"\n[Phase 3] action_effects.yaml과 대조...")
    present, missing, b1_matches = cross_reference_with_effects(
        all_actions, args.action_effects
    )
    print(f"  Present in effects: {len(present)}")
    print(f"  Missing from effects: {len(missing)}")
    print(f"  B1 close matches: {len(b1_matches)}")

    # Classify B1 matches by similarity
    high_sim = {k: v for k, v in b1_matches.items() if v['similarity'] >= 0.85}
    med_sim = {k: v for k, v in b1_matches.items() if 0.70 <= v['similarity'] < 0.85}
    no_match = missing - set(b1_matches.keys())

    print(f"\n  ★ B1 분류 (올바른 필드명 기준):")
    print(f"    High similarity (>=0.85, rename으로 해결): {len(high_sim)}")
    print(f"    Medium similarity (0.70-0.85, 확인 필요):  {len(med_sim)}")
    print(f"    No match (진짜 새로 추가 필요):            {len(no_match)}")

    if high_sim:
        print(f"\n  High-similarity B1 renames:")
        for action, info in sorted(high_sim.items(), key=lambda x: -x[1]['similarity'])[:20]:
            graphs_list = sorted(action_to_graph.get(action, set()))[:3]
            print(f"    '{action}' → '{info['match']}' (sim={info['similarity']}) [{', '.join(graphs_list)}]")

    # Phase 4: Generate corrected reports
    print(f"\n[Phase 4] 보고서 생성...")

    report = {
        'field_names': {f: {'count': c, 'examples': field_examples[f][:3]}
                        for f, c in field_counts.most_common()},
        'action_fields': dict(action_fields),
        'total_expected': len(all_expected),
        'total_forbidden': len(all_forbidden),
        'total_unique': len(all_actions),
        'present_in_effects': len(present),
        'missing_from_effects': len(missing),
        'b1_high_similarity': len(high_sim),
        'b1_medium_similarity': len(med_sim),
        'truly_missing': len(no_match),
        'corrected_bug_count': len(no_match),  # 실제로 추가해야 할 수
    }

    # Save
    with open(output_dir / 'field_audit_report.json', 'w') as f:
        json.dump(report, f, indent=2, default=str)

    with open(output_dir / 'b1_corrected_renames.json', 'w') as f:
        json.dump([
            {'from': k, 'to': v['match'], 'similarity': v['similarity'],
             'graphs': sorted(action_to_graph.get(k, set()))}
            for k, v in sorted(high_sim.items(), key=lambda x: -x[1]['similarity'])
        ], f, indent=2)

    with open(output_dir / 'truly_missing_actions.json', 'w') as f:
        json.dump([
            {'action': a, 'graphs': sorted(action_to_graph.get(a, set())),
             'in_expected': a in all_expected, 'in_forbidden': a in all_forbidden}
            for a in sorted(no_match)
        ], f, indent=2)

    with open(output_dir / 'missing_with_context.txt', 'w') as f:
        f.write(f"# 진짜 누락된 actions ({len(no_match)}개)\n")
        f.write(f"# B1 rename으로 해결 가능: {len(high_sim)}개\n")
        f.write(f"# action_effects.yaml에 새로 추가 필요: {len(no_match)}개\n\n")
        for a in sorted(no_match):
            gs = sorted(action_to_graph.get(a, set()))
            f.write(f"{a:50s}  [{', '.join(gs)}]\n")

    # Generate corrected apply_renames.py
    if high_sim:
        with open(output_dir / 'apply_corrected_renames.py', 'w') as f:
            f.write('#!/usr/bin/env python3\n')
            f.write('"""Apply corrected B1 renames to graph YAML files.\n')
            f.write(f'   {len(high_sim)} renames with similarity >= 0.85"""\n\n')
            f.write('import sys\nfrom pathlib import Path\n\n')
            f.write('RENAMES = {\n')
            for action, info in sorted(high_sim.items()):
                f.write(f'    "{action}": "{info["match"]}",\n')
            f.write('}\n\n')
            f.write('def apply(graphs_dir):\n')
            f.write('    changed_total = 0\n')
            f.write('    for yf in sorted(Path(graphs_dir).glob("*.yaml")):\n')
            f.write('        with open(yf) as fh:\n')
            f.write('            content = fh.read()\n')
            f.write('        original = content\n')
            f.write('        for old, new in RENAMES.items():\n')
            f.write('            if old in content:\n')
            f.write('                content = content.replace(old, new)\n')
            f.write('                print(f"  {yf.name}: {old} → {new}")\n')
            f.write('                changed_total += 1\n')
            f.write('        if content != original:\n')
            f.write('            with open(yf, "w") as fh:\n')
            f.write('                fh.write(content)\n')
            f.write('    print(f"\\nTotal renames applied: {changed_total}")\n\n')
            f.write('if __name__ == "__main__":\n')
            f.write('    apply(sys.argv[1] if len(sys.argv) > 1 else "cpg_model/graphs")\n')

    print(f"\n{'=' * 70}")
    print(f"결과 요약")
    print(f"{'=' * 70}")
    print(f"  기존 진단: 118개 BUG (expected_actions 필드 사용)")
    print(f"  교정 후:   {len(missing)}개 missing (모든 필드명 커버)")
    print(f"    - B1 Rename으로 해결: {len(high_sim)}개")
    print(f"    - 진짜 추가 필요:     {len(no_match)}개")
    print(f"")
    print(f"  수정 순서:")
    print(f"    1. python {output_dir}/apply_corrected_renames.py cpg_model/graphs")
    print(f"    2. {output_dir}/truly_missing_actions.json의 {len(no_match)}개 → action_effects.yaml에 추가")
    print(f"    3. pytest + 재실행")
    print(f"{'=' * 70}")

    # Save all outputs
    for fname in ['field_audit_report.json', 'b1_corrected_renames.json',
                   'truly_missing_actions.json', 'missing_with_context.txt']:
        print(f"[SAVED] {output_dir / fname}")


if __name__ == '__main__':
    main()