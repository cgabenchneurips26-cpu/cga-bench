#!/usr/bin/env python3
"""
Missing Action Effects 생성기
==============================
118개 BUG_NOT_IN_EFFECTS actions에 대해 action_effects.yaml 엔트리를 
graph 컨텍스트 기반으로 자동 생성.

두 단계:
1. B1 Name Mismatch 해결: similarity > 0.85이면 graph에서 이름 교정
   → action_effects에 새 엔트리 추가 불필요 (rename으로 해결)
2. 진짜 누락: graph node context에서 precondition/effect 추론
   → skeleton entry 생성 → 사람이 검토 후 반영

Usage:
    python generate_missing_action_effects.py \
        --graphs-dir cpg_model/graphs \
        --action-effects cpg_model/action_effects.yaml \
        --triage-json evidence_pack/constraint_triage/constraint_triage_full.json \
        --b1-renames evidence_pack/deep_diagnosis/b1_rename_suggestions.json \
        [--output evidence_pack/fix_actions]
"""

import argparse
import json
import yaml
from collections import defaultdict
from pathlib import Path


def load_yaml(path):
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except:
        return None


def load_action_effects(path):
    data = load_yaml(path)
    if not data:
        return {}
    if isinstance(data, dict):
        return {k.lower().strip(): v for k, v in data.items()}
    elif isinstance(data, list):
        return {e.get('action', '').lower().strip(): e for e in data if isinstance(e, dict)}
    return {}


def load_graphs(graphs_dir):
    graphs = {}
    for f in sorted(Path(graphs_dir).glob("*.yaml")):
        if f.name.startswith('_'):
            continue
        data = load_yaml(f)
        if data:
            graphs[f.stem] = data
    return graphs


def extract_action_context(graphs):
    """
    Graph에서 각 action의 컨텍스트 추출:
    - 어떤 node에 있는지
    - 어떤 다른 action과 같은 node에 있는지
    - 해당 node의 description
    - 해당 node의 preconditions/dependencies
    - 도메인 (graph_id)
    """
    action_context = defaultdict(lambda: {
        'graphs': set(),
        'nodes': [],
        'co_actions': set(),
        'node_descriptions': [],
        'is_expected': False,
        'is_forbidden': False,
        'has_deadline': False,
        'deadline_minutes': None,
    })

    for gid, graph in graphs.items():
        nodes = graph.get('nodes', [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get('id', node.get('name', ''))
            desc = node.get('description', node.get('desc', ''))

            node_actions = set()

            for a in node.get('expected_actions', []):
                name = (a if isinstance(a, str) else a.get('action', str(a))).lower().strip()
                node_actions.add(name)
                ctx = action_context[name]
                ctx['graphs'].add(gid)
                ctx['nodes'].append(nid)
                ctx['is_expected'] = True
                if desc:
                    ctx['node_descriptions'].append(desc)

            for a in node.get('forbidden_actions', []):
                name = (a if isinstance(a, str) else a.get('action', str(a))).lower().strip()
                node_actions.add(name)
                ctx = action_context[name]
                ctx['graphs'].add(gid)
                ctx['is_forbidden'] = True

            deadlines = node.get('deadlines', [])
            if isinstance(deadlines, dict):
                for act, mins in deadlines.items():
                    ctx = action_context[act.lower().strip()]
                    ctx['has_deadline'] = True
                    ctx['deadline_minutes'] = mins
            elif isinstance(deadlines, list):
                for dl in deadlines:
                    if isinstance(dl, dict):
                        act = dl.get('action', '').lower().strip()
                        ctx = action_context[act]
                        ctx['has_deadline'] = True
                        ctx['deadline_minutes'] = dl.get('minutes', dl.get('time_limit', None))

            # Co-actions
            for name in node_actions:
                action_context[name]['co_actions'].update(node_actions - {name})

    return action_context


def infer_precondition_from_context(action_name, ctx, existing_effects):
    """
    Action의 precondition을 컨텍스트에서 추론.
    
    전략:
    1. 같은 node의 co-action 중 existing_effects에 있는 것의 effect를 보고,
       비슷한 패턴의 precondition 추론
    2. Graph domain에서 일반적인 precondition 패턴 적용
    3. Node description에서 힌트 추출
    """
    preconditions = []

    # Domain-based default preconditions
    graphs = list(ctx['graphs'])
    for gid in graphs:
        domain = gid.lower()
        if 'sepsis' in domain:
            preconditions.append(f"state.{domain}_protocol_active == True")
        elif 'cardiac' in domain or 'stemi' in domain or 'acls' in domain:
            preconditions.append(f"state.cardiac_protocol_active == True")
        elif 'burn' in domain:
            preconditions.append(f"state.burn_protocol_active == True")
        elif 'transfusion' in domain:
            preconditions.append(f"state.transfusion_protocol_active == True")
        elif 'stroke' in domain:
            preconditions.append(f"state.stroke_protocol_active == True")

    # Look at co-actions for pattern
    for co_act in ctx['co_actions']:
        if co_act in existing_effects:
            co_entry = existing_effects[co_act]
            if isinstance(co_entry, dict):
                co_preconds = co_entry.get('preconditions', co_entry.get('precondition', []))
                if co_preconds and isinstance(co_preconds, list):
                    # Use similar preconditions
                    for p in co_preconds[:2]:
                        if isinstance(p, str) and p not in preconditions:
                            preconditions.append(f"# inferred from co-action {co_act}: {p}")

    return preconditions if preconditions else ["# TODO: define precondition"]


def infer_effects_from_context(action_name, ctx):
    """Action의 effects를 이름과 컨텍스트에서 추론."""
    effects = {}

    # Parse action name for clues
    name_lower = action_name.lower()

    # Common patterns
    if any(w in name_lower for w in ['administer', 'give', 'infuse', 'bolus']):
        # Drug administration
        drug = name_lower.replace('administer_', '').replace('give_', '')
        effects[f'state.{drug}_administered'] = True
        effects[f'state.{drug}_time'] = 'current_time'

    elif any(w in name_lower for w in ['order', 'request']):
        target = name_lower.replace('order_', '').replace('request_', '')
        effects[f'state.{target}_ordered'] = True

    elif any(w in name_lower for w in ['check', 'assess', 'evaluate', 'monitor']):
        target = name_lower.replace('check_', '').replace('assess_', '').replace('evaluate_', '').replace('monitor_', '')
        effects[f'state.{target}_assessed'] = True

    elif any(w in name_lower for w in ['obtain', 'draw', 'collect']):
        target = name_lower.replace('obtain_', '').replace('draw_', '').replace('collect_', '')
        effects[f'state.{target}_obtained'] = True

    elif any(w in name_lower for w in ['intubate', 'ventilat']):
        effects['state.airway_secured'] = True

    elif 'iv_access' in name_lower or 'establish_iv' in name_lower:
        effects['state.iv_access'] = True

    elif any(w in name_lower for w in ['consult', 'call', 'notify']):
        target = name_lower.replace('consult_', '').replace('call_', '').replace('notify_', '')
        effects[f'state.{target}_consulted'] = True

    elif any(w in name_lower for w in ['start', 'initiate', 'begin']):
        target = name_lower.replace('start_', '').replace('initiate_', '').replace('begin_', '')
        effects[f'state.{target}_started'] = True

    elif any(w in name_lower for w in ['stop', 'discontinue', 'hold']):
        target = name_lower.replace('stop_', '').replace('discontinue_', '').replace('hold_', '')
        effects[f'state.{target}_stopped'] = True

    if not effects:
        effects[f'state.{name_lower}_completed'] = True

    return effects


def generate_entries(missing_actions, action_context, existing_effects, renames):
    """
    누락된 action에 대한 action_effects 엔트리 생성.
    B1 renames는 별도 처리.
    """
    # Build rename map
    rename_map = {}
    if renames:
        for r in renames:
            if r.get('similarity', 0) >= 0.85:
                rename_map[r['from'].lower().strip()] = r['to'].lower().strip()

    new_entries = []
    rename_fixes = []
    truly_missing = []

    for action in missing_actions:
        action_lower = action.lower().strip()

        # Check if B1 rename resolves this
        if action_lower in rename_map:
            rename_fixes.append({
                'original': action,
                'rename_to': rename_map[action_lower],
                'action': 'RENAME_IN_GRAPH',
            })
            continue

        # Generate new entry
        ctx = action_context.get(action_lower, {
            'graphs': set(),
            'nodes': [],
            'co_actions': set(),
            'node_descriptions': [],
            'is_expected': False,
            'is_forbidden': False,
        })

        preconditions = infer_precondition_from_context(action_lower, ctx, existing_effects)
        effects = infer_effects_from_context(action_lower, ctx)

        entry = {
            'action': action,
            'preconditions': preconditions,
            'effects': effects,
            'graphs': list(ctx['graphs']) if isinstance(ctx['graphs'], set) else [],
            'nodes': ctx.get('nodes', [])[:3],
            'is_expected': ctx.get('is_expected', False),
            'is_forbidden': ctx.get('is_forbidden', False),
            '_review_status': 'AUTO_GENERATED',
            '_notes': 'Preconditions and effects are inferred. Review before use.',
        }

        new_entries.append(entry)
        truly_missing.append(action)

    return new_entries, rename_fixes, truly_missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--graphs-dir', default='cpg_model/graphs')
    parser.add_argument('--action-effects', default='cpg_model/action_effects.yaml')
    parser.add_argument('--triage-json', default='evidence_pack/constraint_triage/constraint_triage_full.json')
    parser.add_argument('--b1-renames', default='evidence_pack/deep_diagnosis/b1_rename_suggestions.json')
    parser.add_argument('--output', default='evidence_pack/fix_actions')
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Missing Action Effects 생성기")
    print("=" * 60)

    # Load data
    graphs = load_graphs(args.graphs_dir)
    existing_effects = load_action_effects(args.action_effects)
    print(f"[INFO] {len(graphs)} graphs, {len(existing_effects)} existing action_effects")

    # Load triage results to find BUG actions
    triage = []
    triage_path = Path(args.triage_json)
    if triage_path.exists():
        with open(triage_path) as f:
            triage = json.load(f)
    else:
        print(f"[WARN] Triage JSON not found: {triage_path}")
        print("       Will extract missing actions directly from graphs.")

    # Load B1 renames
    renames = []
    rename_path = Path(args.b1_renames)
    if rename_path.exists():
        with open(rename_path) as f:
            renames = json.load(f)
        print(f"[INFO] {len(renames)} B1 rename suggestions loaded")

    # Find missing actions
    if triage:
        missing_actions = [
            t['action'] for t in triage
            if t.get('category', '').startswith('BUG')
        ]
    else:
        # Extract directly
        all_graph_actions = set()
        for gid, graph in graphs.items():
            nodes = graph.get('nodes', [])
            if isinstance(nodes, dict):
                nodes = list(nodes.values())
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                for a in node.get('expected_actions', []):
                    name = (a if isinstance(a, str) else a.get('action', str(a)))
                    all_graph_actions.add(name)
                for a in node.get('forbidden_actions', []):
                    name = (a if isinstance(a, str) else a.get('action', str(a)))
                    all_graph_actions.add(name)

        missing_actions = [a for a in all_graph_actions if a.lower().strip() not in existing_effects]

    missing_actions = list(set(missing_actions))
    print(f"[INFO] {len(missing_actions)} missing actions to process")

    # Extract action context
    action_context = extract_action_context(graphs)

    # Generate entries
    new_entries, rename_fixes, truly_missing = generate_entries(
        missing_actions, action_context, existing_effects, renames
    )

    print(f"\n[RESULT]")
    print(f"  B1 Renames (graph 이름 교정으로 해결): {len(rename_fixes)}")
    print(f"  New entries (action_effects.yaml 추가 필요): {len(new_entries)}")

    # Save new entries as YAML (action_effects.yaml에 append 가능한 형태)
    new_effects_path = output_dir / 'new_action_effects.yaml'
    new_effects_data = {}
    for entry in new_entries:
        action_name = entry.pop('action')
        # Clean up internal fields
        for key in ['_review_status', '_notes', 'graphs', 'nodes', 'is_expected', 'is_forbidden']:
            entry.pop(key, None)
        new_effects_data[action_name] = entry

    with open(new_effects_path, 'w') as f:
        f.write("# AUTO-GENERATED missing action effects\n")
        f.write("# Review each entry before merging into cpg_model/action_effects.yaml\n")
        f.write("# Generated by: generate_missing_action_effects.py\n\n")
        yaml.dump(new_effects_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"[SAVED] {new_effects_path}")

    # Save rename fixes
    rename_path = output_dir / 'graph_rename_fixes.json'
    with open(rename_path, 'w') as f:
        json.dump(rename_fixes, f, indent=2)
    print(f"[SAVED] {rename_path}")

    # Save rename as a patch script
    patch_path = output_dir / 'apply_renames.py'
    with open(patch_path, 'w') as f:
        f.write('#!/usr/bin/env python3\n')
        f.write('"""Apply B1 name renames to graph YAML files."""\n')
        f.write('import yaml, sys\n')
        f.write('from pathlib import Path\n\n')
        f.write('RENAMES = [\n')
        for r in rename_fixes:
            f.write(f'    ("{r["original"]}", "{r["rename_to"]}"),\n')
        f.write(']\n\n')
        f.write('def apply_renames(graphs_dir):\n')
        f.write('    for yaml_file in sorted(Path(graphs_dir).glob("*.yaml")):\n')
        f.write('        with open(yaml_file) as fh:\n')
        f.write('            content = fh.read()\n')
        f.write('        changed = False\n')
        f.write('        for old, new in RENAMES:\n')
        f.write('            if old in content:\n')
        f.write('                content = content.replace(old, new)\n')
        f.write('                changed = True\n')
        f.write('                print(f"  {yaml_file.name}: {old} → {new}")\n')
        f.write('        if changed:\n')
        f.write('            with open(yaml_file, "w") as fh:\n')
        f.write('                fh.write(content)\n\n')
        f.write('if __name__ == "__main__":\n')
        f.write('    graphs_dir = sys.argv[1] if len(sys.argv) > 1 else "cpg_model/graphs"\n')
        f.write('    apply_renames(graphs_dir)\n')
    print(f"[SAVED] {patch_path}")

    # Summary
    print(f"""
{'=' * 60}
수정 실행 순서:
{'=' * 60}

1. B1 Renames 적용 ({len(rename_fixes)}개):
   python {patch_path} cpg_model/graphs
   → graph YAML에서 action 이름 교정

2. New action_effects 검토 + merge ({len(new_entries)}개):
   # 검토:
   cat {new_effects_path}
   # merge (주의: 수동 검토 후):
   # existing action_effects.yaml에 내용 append

3. 검증:
   python -m pytest tests/ -x
   python scripts/validate_conditional_rules.py

4. 에피소드 재실행:
   bash scripts/run_full_episodes.sh
{'=' * 60}
""")


if __name__ == '__main__':
    main()
