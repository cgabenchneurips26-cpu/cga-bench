#!/usr/bin/env python3
"""
Action Effects Stub 생성기 (교정판)
=====================================
truly_missing_actions.json 기반. 필드명 감사 결과를 반영.

입력: evidence_pack/field_audit/truly_missing_actions.json
출력: 
  1. mandatory_action_effects.yaml — 118개 mandatory (OMISSION 직접 원인, 즉시 merge)
  2. allowed_action_effects.yaml — 나머지 allowed (재실행 후 평가)
  3. review_summary.md — domain별 검토 가이드

Usage:
    python generate_corrected_stubs.py \
        --missing evidence_pack/field_audit/truly_missing_actions.json \
        --graphs-dir cpg_model/graphs \
        --action-effects cpg_model/action_effects.yaml \
        [--output-dir evidence_pack/fix_actions_v2]
"""

import argparse
import json
import yaml
import re
from collections import defaultdict
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════
# CLINICAL ACTION PATTERN LIBRARY
# ═══════════════════════════════════════════════════════════════════════
# 의료 action 이름에서 precondition/effect를 추론하는 패턴.
# 각 패턴: (regex, preconditions_template, effects_template)

CLINICAL_PATTERNS = [
    # ── Medication administration ──
    (r'^(?:give|administer|infuse|bolus|push)_(.+)',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {f"state.{m.group(1)}_given": True,
                   f"state.{m.group(1)}_time": "current_time"}),

    # ── IV/Fluid management ──
    (r'^(?:start|initiate|begin)_(.+)',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {f"state.{m.group(1)}_started": True}),

    (r'^(?:stop|discontinue|hold|withhold|withdraw)_(.+)',
     lambda m, g: [f"state.{m.group(1)}_started == True"],
     lambda m, g: {f"state.{m.group(1)}_started": False,
                   f"state.{m.group(1)}_stopped": True}),

    # ── Monitoring/Assessment ──
    (r'^(?:monitor|check|assess|evaluate|measure|obtain|perform)_(.+)',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {f"state.{m.group(1)}_assessed": True,
                   f"state.{m.group(1)}_result": "pending"}),

    # ── Ordering ──
    (r'^(?:order|request|send)_(.+)',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {f"state.{m.group(1)}_ordered": True}),

    # ── Consultation ──
    (r'^(?:consult|call|notify|alert|activate)_(.+)',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {f"state.{m.group(1)}_consulted": True}),

    # ── Procedures ──
    (r'^(?:intubate|insert|place|establish|secure|apply)_(.+)',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {f"state.{m.group(1)}_placed": True}),

    # ── Imaging/Diagnostics ──
    (r'^(?:obtain|perform|do)_(?:ct|mri|xray|echo|ekg|ecg|ultrasound|imaging)(.*)$',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {"state.imaging_obtained": True,
                   f"state.{m.group(0).replace(' ','_')}_done": True}),

    # ── Titration/Adjustment ──
    (r'^(?:titrate|adjust|increase|decrease|reduce|taper)_(.+)',
     lambda m, g: [f"state.{m.group(1)}_started == True"],
     lambda m, g: {f"state.{m.group(1)}_adjusted": True}),

    # ── Delayed/Deferred actions (forbidden-type) ──
    (r'^(?:delay|defer|avoid|prevent|restrict)_(.+)',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {f"state.{m.group(1)}_delayed": True}),

    # ── Consider/Evaluate (soft) ──
    (r'^(?:consider|evaluate_for|assess_need|screen_for)_(.+)',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {f"state.{m.group(1)}_considered": True}),

    # ── Transfer/Disposition ──
    (r'^(?:transfer|admit|discharge|move)_(.+)',
     lambda m, g: [f"state.{g}_protocol_active == True"],
     lambda m, g: {f"state.{m.group(1)}_transferred": True,
                   "state.disposition_decided": True}),
]


def infer_from_patterns(action_name, graph_id):
    """패턴 라이브러리에서 precondition/effect 추론"""
    action_lower = action_name.lower().strip()
    graph_short = graph_id.split('_')[0] if graph_id else 'protocol'

    for pattern, prec_fn, eff_fn in CLINICAL_PATTERNS:
        m = re.match(pattern, action_lower)
        if m:
            try:
                preconds = prec_fn(m, graph_short)
                effects = eff_fn(m, graph_short)
                return preconds, effects, True
            except:
                pass

    # Fallback: generic
    safe_name = re.sub(r'[^a-z0-9_]', '_', action_lower)
    return (
        [f"state.{graph_short}_protocol_active == True"],
        {f"state.{safe_name}_done": True},
        False
    )


def classify_action_field(action, graphs_dir):
    """
    Action이 mandatory_actions에 있는지 allowed_actions에 있는지 확인.
    Graph YAML을 직접 스캔.
    """
    # This info should be in truly_missing_actions.json already
    # but we can re-derive if needed
    return 'unknown'


def load_existing_effects(path):
    """기존 action_effects.yaml 구조 파악"""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except:
        return {}, 'unknown'

    if isinstance(data, dict):
        # Check first entry to understand structure
        sample = next(iter(data.values()), None) if data else None
        return data, 'dict'  # {action_name: {effects: ...}}
    elif isinstance(data, list):
        return {e.get('action', ''): e for e in data if isinstance(e, dict)}, 'list'
    return {}, 'unknown'


def determine_field_source(action, graphs_dir):
    """action이 어떤 필드(mandatory/forbidden/allowed)에서 왔는지 확인"""
    field_source = set()
    source_graphs = set()

    for f in sorted(Path(graphs_dir).glob("*.yaml")):
        if f.name.startswith('_'):
            continue
        try:
            with open(f) as fh:
                graph = yaml.safe_load(fh)
        except:
            continue

        nodes = graph.get('nodes', [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        for node in nodes:
            if not isinstance(node, dict):
                continue
            # Check ALL possible field names
            for field in ['mandatory_actions', 'expected_actions', 'required_actions']:
                for a in node.get(field, []):
                    name = (a if isinstance(a, str) else a.get('action', str(a))).lower().strip()
                    if name == action.lower().strip():
                        field_source.add('mandatory')
                        source_graphs.add(f.stem)

            for field in ['forbidden_actions', 'prohibited_actions', 'contraindicated_actions']:
                for a in node.get(field, []):
                    name = (a if isinstance(a, str) else a.get('action', str(a))).lower().strip()
                    if name == action.lower().strip():
                        field_source.add('forbidden')
                        source_graphs.add(f.stem)

            for field in ['allowed_actions', 'optional_actions', 'global_allowed_actions']:
                actions = node.get(field, [])
                if isinstance(actions, list):
                    for a in actions:
                        name = (a if isinstance(a, str) else a.get('action', str(a))).lower().strip()
                        if name == action.lower().strip():
                            field_source.add('allowed')
                            source_graphs.add(f.stem)

        # Also check graph-level allowed_actions
        for field in ['allowed_actions', 'global_allowed_actions']:
            actions = graph.get(field, [])
            if isinstance(actions, list):
                for a in actions:
                    name = (a if isinstance(a, str) else a.get('action', str(a))).lower().strip()
                    if name == action.lower().strip():
                        field_source.add('allowed')
                        source_graphs.add(f.stem)

    return field_source, source_graphs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--missing', default='evidence_pack/field_audit/truly_missing_actions.json')
    parser.add_argument('--graphs-dir', default='cpg_model/graphs')
    parser.add_argument('--action-effects', default='cpg_model/action_effects.yaml')
    parser.add_argument('--output-dir', default='evidence_pack/fix_actions_v2')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load missing actions
    missing_path = Path(args.missing)
    if not missing_path.exists():
        print(f"[ERROR] {missing_path} not found")
        sys.exit(1)

    with open(missing_path) as f:
        missing_data = json.load(f)

    print(f"[INFO] {len(missing_data)} missing actions loaded")

    # Understand existing action_effects format
    existing, fmt = load_existing_effects(args.action_effects)
    print(f"[INFO] Existing action_effects: {len(existing)} entries, format={fmt}")

    # Classify each action by field source
    print(f"\n[STEP 1] Classifying actions by field source...")
    mandatory_stubs = []
    forbidden_stubs = []
    allowed_stubs = []
    unknown_stubs = []

    for item in missing_data:
        action = item['action'] if isinstance(item, dict) else item
        graphs = item.get('graphs', []) if isinstance(item, dict) else []

        # Determine field source
        field_source, source_graphs = determine_field_source(action, args.graphs_dir)
        if not source_graphs and graphs:
            source_graphs = set(graphs)

        primary_graph = sorted(source_graphs)[0] if source_graphs else ''

        # Generate stub
        preconds, effects, matched = infer_from_patterns(action, primary_graph)

        stub = {
            'action': action,
            'preconditions': preconds,
            'effects': effects,
            'field_source': sorted(field_source),
            'graphs': sorted(source_graphs),
            'pattern_matched': matched,
        }

        if 'mandatory' in field_source:
            mandatory_stubs.append(stub)
        elif 'forbidden' in field_source:
            forbidden_stubs.append(stub)
        elif 'allowed' in field_source:
            allowed_stubs.append(stub)
        else:
            unknown_stubs.append(stub)

        if (len(mandatory_stubs) + len(forbidden_stubs) + len(allowed_stubs) + len(unknown_stubs)) % 50 == 0:
            print(f"  ... processed {len(mandatory_stubs) + len(forbidden_stubs) + len(allowed_stubs) + len(unknown_stubs)}")

    print(f"\n[RESULT] Classification:")
    print(f"  Mandatory (OMISSION 직접 원인): {len(mandatory_stubs)}")
    print(f"  Forbidden (COMMISSION 관련):    {len(forbidden_stubs)}")
    print(f"  Allowed (간접 영향):            {len(allowed_stubs)}")
    print(f"  Unknown (소스 불명):            {len(unknown_stubs)}")

    # ── Generate YAML output ──
    def stubs_to_yaml(stubs):
        """stub 리스트를 action_effects.yaml merge 가능한 형태로 변환"""
        result = {}
        for s in stubs:
            entry = {
                'preconditions': s['preconditions'],
                'effects': s['effects'],
            }
            result[s['action']] = entry
        return result

    # 1. Mandatory (즉시 merge)
    mandatory_yaml = stubs_to_yaml(mandatory_stubs)
    mandatory_path = output_dir / 'mandatory_action_effects.yaml'
    with open(mandatory_path, 'w') as f:
        f.write(f"# MANDATORY action_effects stubs ({len(mandatory_stubs)} actions)\n")
        f.write(f"# OMISSION violation의 직접 원인. 즉시 merge 필요.\n")
        f.write(f"# 각 entry의 preconditions/effects를 검토 후 cpg_model/action_effects.yaml에 추가.\n\n")
        yaml.dump(mandatory_yaml, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"[SAVED] {mandatory_path}")

    # 2. Forbidden
    if forbidden_stubs:
        forbidden_yaml = stubs_to_yaml(forbidden_stubs)
        forbidden_path = output_dir / 'forbidden_action_effects.yaml'
        with open(forbidden_path, 'w') as f:
            f.write(f"# FORBIDDEN action_effects stubs ({len(forbidden_stubs)} actions)\n")
            f.write(f"# COMMISSION detection에 필요. 우선순위 2.\n\n")
            yaml.dump(forbidden_yaml, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"[SAVED] {forbidden_path}")

    # 3. Allowed
    if allowed_stubs:
        allowed_yaml = stubs_to_yaml(allowed_stubs)
        allowed_path = output_dir / 'allowed_action_effects.yaml'
        with open(allowed_path, 'w') as f:
            f.write(f"# ALLOWED action_effects stubs ({len(allowed_stubs)} actions)\n")
            f.write(f"# 재실행 후 영향 평가. 우선순위 3.\n\n")
            yaml.dump(allowed_yaml, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"[SAVED] {allowed_path}")

    # 4. Unknown
    if unknown_stubs:
        unknown_yaml = stubs_to_yaml(unknown_stubs)
        unknown_path = output_dir / 'unknown_action_effects.yaml'
        with open(unknown_path, 'w') as f:
            f.write(f"# UNKNOWN source action_effects stubs ({len(unknown_stubs)} actions)\n\n")
            yaml.dump(unknown_yaml, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"[SAVED] {unknown_path}")

    # ── Review summary ──
    lines = []
    lines.append("# Action Effects 수정 가이드")
    lines.append("")
    lines.append(f"## 요약")
    lines.append(f"- Mandatory (즉시): {len(mandatory_stubs)}개")
    lines.append(f"- Forbidden: {len(forbidden_stubs)}개")
    lines.append(f"- Allowed: {len(allowed_stubs)}개")
    lines.append(f"- Unknown: {len(unknown_stubs)}개")
    lines.append("")

    # Domain breakdown for mandatory
    lines.append("## Mandatory Actions by Domain")
    by_domain = defaultdict(list)
    for s in mandatory_stubs:
        for g in s['graphs']:
            by_domain[g].append(s['action'])
    for domain in sorted(by_domain.keys(), key=lambda x: -len(by_domain[x])):
        actions = by_domain[domain]
        lines.append(f"\n### {domain} ({len(actions)}개)")
        for a in sorted(actions):
            matched = any(s['action'] == a and s['pattern_matched'] for s in mandatory_stubs)
            marker = "✅" if matched else "⚠️ "
            lines.append(f"  {marker} {a}")

    lines.append(f"""
## Merge 순서

```bash
# 1. Mandatory (OMISSION 수정)
cat evidence_pack/fix_actions_v2/mandatory_action_effects.yaml >> cpg_model/action_effects.yaml

# 2. 검증
python -m pytest tests/ -x -q

# 3. Dry-run (시나리오 1개)
python scripts/full_690_runner.py --dry-run --scenarios 1

# 4. 전체 재실행
python scripts/full_690_runner.py --output results/full_706_v6

# 5. (재실행 후) Forbidden + Allowed 추가 평가
```
""")

    review_path = output_dir / 'review_summary.md'
    with open(review_path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"[SAVED] {review_path}")

    # ── Merge script ──
    merge_path = output_dir / 'merge_mandatory.sh'
    with open(merge_path, 'w') as f:
        f.write("#!/usr/bin/env bash\n")
        f.write("# Merge mandatory action_effects stubs\n")
        f.write("set -euo pipefail\n\n")
        f.write("AE=cpg_model/action_effects.yaml\n")
        f.write("STUBS=evidence_pack/fix_actions_v2/mandatory_action_effects.yaml\n\n")
        f.write("echo \"[1/4] Backup...\"\n")
        f.write("cp $AE ${AE}.bak.$(date +%Y%m%d_%H%M%S)\n\n")
        f.write("echo \"[2/4] Merge...\"\n")
        f.write("python3 -c \"\n")
        f.write("import yaml\n")
        f.write("with open('$AE') as f: existing = yaml.safe_load(f) or {}\n")
        f.write("with open('$STUBS') as f: new = yaml.safe_load(f) or {}\n")
        f.write("# Remove comment-only keys\n")
        f.write("new = {k:v for k,v in new.items() if not k.startswith('#')}\n")
        f.write("merged = {**existing, **new}\n")
        f.write("print(f'Existing: {len(existing)}, New: {len(new)}, Merged: {len(merged)}')\n")
        f.write("with open('$AE', 'w') as f: yaml.dump(merged, f, default_flow_style=False, allow_unicode=True)\n")
        f.write("\"\n\n")
        f.write("echo \"[3/4] Validate...\"\n")
        f.write("python3 -m pytest tests/ -x -q 2>&1 | tail -5\n\n")
        f.write("echo \"[4/4] Done. Run dry-run to verify:\"\n")
        f.write("echo \"  python scripts/full_690_runner.py --dry-run --scenarios 1\"\n")
    print(f"[SAVED] {merge_path}")

    print(f"\n{'=' * 60}")
    print(f"완료. 다음 단계:")
    print(f"  1. mandatory_action_effects.yaml 검토 ({len(mandatory_stubs)}개)")
    print(f"  2. bash evidence_pack/fix_actions_v2/merge_mandatory.sh")
    print(f"  3. 에피소드 재실행")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()