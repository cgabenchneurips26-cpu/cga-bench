#!/usr/bin/env python3
"""CGA-Bench 파이프라인 심층 진단
================================
118개 BUG_NOT_IN_EFFECTS 이외에 숨어있을 수 있는 모든 버그 카테고리를 조사.

버그 카테고리:
  B1. Action Name Mismatch — graph와 action_effects에서 이름이 미세하게 다름
  B2. Precondition Impossibility — action은 존재하나 precondition이 시나리오에서 불가
  B3. Deadline Impossibility — WITHIN deadline이 time step(5분) 대비 구조적 불가
  B4. Sequence Impossibility — BEFORE constraint가 graph 구조상 역전
  B5. Forbidden/Required Conflict — 같은 patient context에서 동시에 F+R
  B6. Orphan Scenarios — graph_id가 실존하지 않는 시나리오
  B7. Dead Conditional Rules — condition이 어떤 시나리오에서도 true가 안 되는 rule
  B8. Action Normalizer Gap — 모델 출력이 normalize 안 되는 패턴
  B9. Duplicate Constraints — 같은 constraint가 중복 정의
  B10. Expected Action Coverage — action_effects에 있지만 effect/precondition이 비어있음

Usage:
    python deep_pipeline_diagnosis.py \
        --episodes-dir results/full_706_final \
        --graphs-dir cpg_model/graphs \
        --action-effects cpg_model/action_effects.yaml \
        --scenarios-dir configs/scenarios \
        --auto-scenarios configs/scenarios/auto_generated_scenarios.yaml \
        [--normalizer cpg_model/action_normalizer.py] \
        [--output-dir evidence_pack/deep_diagnosis]
"""

import argparse
from collections import defaultdict
from difflib import SequenceMatcher, get_close_matches
import json
from pathlib import Path
import re

import yaml

# ═══════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════


def load_yaml(path):
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[WARN] Failed to load {path}: {e}")
        return None


def load_episodes(episodes_dir):
    episodes = []
    for model_dir in sorted(Path(episodes_dir).iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                ep["_model"] = model_dir.name
                ep["_file"] = str(ep_file)
                episodes.append(ep)
            except:
                pass
    return episodes


def load_graphs(graphs_dir):
    graphs = {}
    for f in sorted(Path(graphs_dir).glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        data = load_yaml(f)
        if data:
            graphs[f.stem] = data
    return graphs


def load_action_effects(path):
    """action_effects.yaml 로드. 다양한 포맷 대응."""
    data = load_yaml(path)
    if not data:
        return {}, {}

    effects = {}  # action_name -> full entry
    preconditions = {}  # action_name -> precondition list

    if isinstance(data, dict):
        # Format: {action_name: {effects: ..., preconditions: ...}}
        for key, val in data.items():
            k = key.lower().strip()
            effects[k] = val if isinstance(val, dict) else {"action": key}
            if isinstance(val, dict):
                preconditions[k] = val.get("preconditions", val.get("precondition", []))
    elif isinstance(data, list):
        # Format: [{action: ..., effects: ..., preconditions: ...}, ...]
        for entry in data:
            if isinstance(entry, dict):
                name = entry.get("action", entry.get("name", "")).lower().strip()
                if name:
                    effects[name] = entry
                    preconditions[name] = entry.get("preconditions", entry.get("precondition", []))

    return effects, preconditions


def load_all_scenarios(scenarios_dir, auto_path=None):
    """모든 시나리오 로드"""
    scenarios = []
    for f in sorted(Path(scenarios_dir).glob("*.yaml")):
        data = load_yaml(f)
        if not data:
            continue
        if isinstance(data, list):
            for s in data:
                if isinstance(s, dict):
                    s["_file"] = str(f)
                    s["_source"] = "auto" if "auto" in f.name else "manual"
                    scenarios.append(s)
        elif isinstance(data, dict):
            items = data.get("scenarios", [data])
            for s in items:
                if isinstance(s, dict):
                    s["_file"] = str(f)
                    s["_source"] = "auto" if "auto" in f.name else "manual"
                    scenarios.append(s)
    return scenarios


# ═══════════════════════════════════════════════════════════════════════
# BUG DETECTORS
# ═══════════════════════════════════════════════════════════════════════


def detect_b1_name_mismatch(graphs, ae_keys):
    """B1: Graph에서 사용하는 action 이름이 action_effects에 없지만,
    유사한 이름(edit distance <= 2)이 존재하는 경우.
    이건 118개 BUG 중 일부가 실제로는 typo일 수 있음을 의미.
    """
    issues = []
    graph_actions = set()

    for gid, graph in graphs.items():
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for field in ["mandatory_actions", "expected_actions", "optional_actions", "forbidden_actions"]:
                actions = node.get(field, [])
                if isinstance(actions, list):
                    for a in actions:
                        name = (a if isinstance(a, str) else a.get("action", str(a))).lower().strip()
                        graph_actions.add((gid, name, field))

        # Conditional rules too
        for rule in graph.get("conditional_rules", []):
            if isinstance(rule, dict):
                target = rule.get("target_action", rule.get("action", "")).lower().strip()
                if target:
                    graph_actions.add((gid, target, "conditional_rule"))

    for gid, action, source in graph_actions:
        if action in ae_keys:
            continue  # exact match, fine

        # Find close matches
        close = get_close_matches(action, list(ae_keys), n=3, cutoff=0.7)
        if close:
            best = close[0]
            ratio = SequenceMatcher(None, action, best).ratio()
            issues.append(
                {
                    "bug": "B1_NAME_MISMATCH",
                    "severity": "HIGH" if ratio > 0.85 else "MEDIUM",
                    "graph_id": gid,
                    "graph_action": action,
                    "closest_in_effects": best,
                    "similarity": round(ratio, 3),
                    "source": source,
                    "fix": f'Rename "{action}" → "{best}" in graph, OR add alias',
                }
            )

    return issues


def detect_b2_precondition_impossibility(graphs, ae_effects, ae_preconditions, episodes):
    """B2: action_effects에 action이 존재하지만, precondition이
    시나리오의 patient context에서 절대 충족 안 되는 경우.

    방법: 에피소드에서 해당 action이 시도되었는데 0% 성공률이면 의심.
    """
    issues = []

    # Build action success map: which actions were successfully performed?
    action_success = defaultdict(lambda: {"attempted": 0, "succeeded": 0, "graphs": set()})

    for ep in episodes:
        graph_id = ep.get("graph_id", ep.get("cpg_graph", ""))
        actions = ep.get("actions", [])
        violations = ep.get("violation_events", [])

        performed_actions = set()
        if isinstance(actions, list):
            for a in actions:
                name = ""
                if isinstance(a, dict):
                    name = a.get("action", a.get("name", "")).lower().strip()
                elif isinstance(a, str):
                    name = a.lower().strip()
                if name:
                    performed_actions.add(name)
                    action_success[name]["succeeded"] += 1
                    action_success[name]["graphs"].add(graph_id)

        # Check expected but not performed
        expected = ep.get("expected_actions", [])
        if isinstance(expected, list):
            for a in expected:
                name = ""
                if isinstance(a, dict):
                    name = a.get("action", a.get("name", "")).lower().strip()
                elif isinstance(a, str):
                    name = a.lower().strip()
                if name:
                    action_success[name]["attempted"] += 1
                    action_success[name]["graphs"].add(graph_id)

    # Find actions in action_effects that are expected but never succeeded
    for action, stats in action_success.items():
        if action not in ae_effects:
            continue  # B1 territory

        if stats["attempted"] > 10 and stats["succeeded"] == 0:
            preconds = ae_preconditions.get(action, [])
            issues.append(
                {
                    "bug": "B2_PRECONDITION_IMPOSSIBLE",
                    "severity": "HIGH",
                    "action": action,
                    "attempted": stats["attempted"],
                    "succeeded": stats["succeeded"],
                    "graphs": list(stats["graphs"])[:5],
                    "preconditions": str(preconds)[:200],
                    "fix": "Check precondition logic in action_effects.yaml",
                }
            )

    return issues


def detect_b3_deadline_impossibility(graphs):
    """B3: WITHIN deadline이 시뮬레이션의 time step(5분/action) 대비
    구조적으로 불가능한 경우.

    예: deadline 5분인데, 그 action까지 최소 2개 action이 선행 → 최소 10분 필요
    """
    TIME_STEP = 5  # minutes per action
    issues = []

    for gid, graph in graphs.items():
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        # Build node dependency graph
        node_deps = {}  # node_id -> set of prerequisite node_ids
        node_by_id = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id", node.get("name", ""))
            node_by_id[nid] = node
            deps = set()
            # Dependencies from edges
            for dep in node.get("dependencies", node.get("prerequisites", [])):
                if isinstance(dep, str):
                    deps.add(dep)
                elif isinstance(dep, dict):
                    deps.add(dep.get("node", dep.get("id", "")))
            node_deps[nid] = deps

        # Check deadlines
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id", node.get("name", ""))

            deadlines = node.get("deadlines", [])
            if isinstance(deadlines, dict):
                deadlines = [{"action": k, "minutes": v} for k, v in deadlines.items()]
            elif not isinstance(deadlines, list):
                continue

            for dl in deadlines:
                if not isinstance(dl, dict):
                    continue
                action = dl.get("action", "")
                minutes = dl.get("minutes", dl.get("time_limit", 999))

                if not isinstance(minutes, (int, float)):
                    continue

                # Estimate minimum steps to reach this node
                min_steps = estimate_min_steps(nid, node_deps)
                min_time = min_steps * TIME_STEP

                if min_time > minutes:
                    issues.append(
                        {
                            "bug": "B3_DEADLINE_IMPOSSIBLE",
                            "severity": "CRITICAL",
                            "graph_id": gid,
                            "node_id": nid,
                            "action": action,
                            "deadline_minutes": minutes,
                            "min_steps_to_reach": min_steps,
                            "min_time_needed": min_time,
                            "fix": f"Increase deadline to >= {min_time} min, or reduce prerequisites",
                        }
                    )
                elif min_time > minutes * 0.8:
                    issues.append(
                        {
                            "bug": "B3_DEADLINE_TIGHT",
                            "severity": "WARNING",
                            "graph_id": gid,
                            "node_id": nid,
                            "action": action,
                            "deadline_minutes": minutes,
                            "min_steps_to_reach": min_steps,
                            "min_time_needed": min_time,
                            "fix": f"Deadline leaves only {minutes - min_time} min slack",
                        }
                    )

    return issues


def estimate_min_steps(node_id, node_deps, visited=None):
    """BFS로 node까지의 최소 step 수 추정"""
    if visited is None:
        visited = set()
    if node_id in visited:
        return 0
    visited.add(node_id)

    deps = node_deps.get(node_id, set())
    if not deps:
        return 0

    max_dep_steps = 0
    for dep in deps:
        dep_steps = estimate_min_steps(dep, node_deps, visited.copy()) + 1
        max_dep_steps = max(max_dep_steps, dep_steps)

    return max_dep_steps


def detect_b4_sequence_impossibility(graphs):
    """B4: BEFORE(A, B) constraint인데, graph 구조상 B가 A보다 선행 node에 있는 경우."""
    issues = []

    for gid, graph in graphs.items():
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        # Build action -> node mapping
        action_to_node = {}
        node_order = {}
        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            nid = node.get("id", node.get("name", ""))
            node_order[nid] = i

            for field in ["mandatory_actions", "expected_actions", "optional_actions", "forbidden_actions"]:
                for a in node.get(field, []):
                    name = (a if isinstance(a, str) else a.get("action", str(a))).lower().strip()
                    action_to_node[name] = nid

        # Check sequence rules
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id", node.get("name", ""))

            for sr in node.get("sequence_rules", []):
                if not isinstance(sr, dict):
                    continue
                before_action = sr.get("before", sr.get("first", "")).lower().strip()
                after_action = sr.get("after", sr.get("then", "")).lower().strip()

                before_node = action_to_node.get(before_action, "")
                after_node = action_to_node.get(after_action, "")

                if before_node and after_node:
                    before_idx = node_order.get(before_node, -1)
                    after_idx = node_order.get(after_node, -1)

                    if before_idx > after_idx and before_idx >= 0 and after_idx >= 0:
                        issues.append(
                            {
                                "bug": "B4_SEQUENCE_REVERSED",
                                "severity": "HIGH",
                                "graph_id": gid,
                                "before_action": before_action,
                                "after_action": after_action,
                                "before_node": before_node,
                                "after_node": after_node,
                                "before_position": before_idx,
                                "after_position": after_idx,
                                "fix": "Swap before/after OR fix node ordering",
                            }
                        )

    return issues


def detect_b5_forbidden_required_conflict(graphs):
    """B5: 같은 patient context 조건에서 action이 동시에 FORBIDDEN + REQUIRED.
    Unconditional level에서의 충돌과 conditional rule level 충돌 모두 체크.
    """
    issues = []

    for gid, graph in graphs.items():
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        # Unconditional: expected_actions ∩ forbidden_actions within same graph
        all_expected = set()
        all_forbidden = set()
        expected_by_node = {}
        forbidden_by_node = {}

        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id", node.get("name", ""))

            exp = set()
            for a in node.get("expected_actions", []):
                name = (a if isinstance(a, str) else a.get("action", str(a))).lower().strip()
                exp.add(name)
                all_expected.add(name)
            expected_by_node[nid] = exp

            forb = set()
            for a in node.get("forbidden_actions", []):
                name = (a if isinstance(a, str) else a.get("action", str(a))).lower().strip()
                forb.add(name)
                all_forbidden.add(name)
            forbidden_by_node[nid] = forb

        # Same-node conflict
        for nid in expected_by_node:
            conflict = expected_by_node.get(nid, set()) & forbidden_by_node.get(nid, set())
            if conflict:
                issues.append(
                    {
                        "bug": "B5_SAME_NODE_CONFLICT",
                        "severity": "CRITICAL",
                        "graph_id": gid,
                        "node_id": nid,
                        "conflicting_actions": list(conflict),
                        "fix": "Action cannot be both expected and forbidden in same node",
                    }
                )

        # Cross-node conflict (might be intentional if different pathways)
        cross_conflict = all_expected & all_forbidden
        if cross_conflict:
            for action in cross_conflict:
                exp_nodes = [n for n, s in expected_by_node.items() if action in s]
                forb_nodes = [n for n, s in forbidden_by_node.items() if action in s]
                # Only flag if not clearly conditional
                issues.append(
                    {
                        "bug": "B5_CROSS_NODE_CONFLICT",
                        "severity": "INFO",  # May be intentional (conditional pathways)
                        "graph_id": gid,
                        "action": action,
                        "expected_in": exp_nodes,
                        "forbidden_in": forb_nodes,
                        "fix": "Verify this is intentional (different patient pathways)",
                    }
                )

        # Conditional rule conflicts
        cond_rules = graph.get("conditional_rules", [])
        if isinstance(cond_rules, list):
            cond_forbidden = defaultdict(list)
            cond_required = defaultdict(list)

            for rule in cond_rules:
                if not isinstance(rule, dict):
                    continue
                ctype = rule.get("constraint_type", "").upper()
                target = rule.get("target_action", rule.get("action", "")).lower().strip()
                condition = str(rule.get("condition", ""))

                if "FORBID" in ctype:
                    cond_forbidden[target].append(condition)
                elif "REQUIRED" in ctype or "MUST" in ctype:
                    cond_required[target].append(condition)

            for action in set(cond_forbidden.keys()) & set(cond_required.keys()):
                f_conds = cond_forbidden[action]
                r_conds = cond_required[action]
                # If same condition appears in both, that's a conflict
                overlap = set(f_conds) & set(r_conds)
                if overlap:
                    issues.append(
                        {
                            "bug": "B5_CONDITIONAL_CONFLICT",
                            "severity": "CRITICAL",
                            "graph_id": gid,
                            "action": action,
                            "conflicting_conditions": list(overlap),
                            "fix": "Same condition cannot make action both required and forbidden",
                        }
                    )

    return issues


def detect_b6_orphan_scenarios(scenarios, graphs):
    """B6: graph_id가 실존하지 않는 시나리오"""
    issues = []
    graph_ids = set(graphs.keys())

    for s in scenarios:
        gid = s.get("graph_id", s.get("cpg_graph", s.get("domain", "")))
        if not gid:
            continue
        if gid not in graph_ids:
            # Try fuzzy match
            close = get_close_matches(gid, list(graph_ids), n=1, cutoff=0.7)
            issues.append(
                {
                    "bug": "B6_ORPHAN_SCENARIO",
                    "severity": "HIGH",
                    "scenario_id": s.get("scenario_id", s.get("id", "unknown")),
                    "graph_id_in_scenario": gid,
                    "closest_graph": close[0] if close else "NONE",
                    "file": s.get("_file", ""),
                    "fix": f'Update graph_id to "{close[0]}"' if close else "Remove scenario or add graph",
                }
            )

    return issues


def detect_b7_dead_conditional_rules(graphs, scenarios):
    """B7: Conditional rule의 condition이 어떤 시나리오의 patient context에서도
    true가 되지 않는 경우 → dead code.
    """
    issues = []

    # Extract all patient contexts from scenarios
    all_patient_fields = set()
    for s in scenarios:
        patient = s.get("patient", s.get("patient_context", {}))
        if isinstance(patient, dict):
            for key in patient.keys():
                all_patient_fields.add(key.lower())

    for gid, graph in graphs.items():
        for rule in graph.get("conditional_rules", []):
            if not isinstance(rule, dict):
                continue
            condition = str(rule.get("condition", ""))
            rule_id = rule.get("rule_id", rule.get("id", ""))

            # Check if condition references fields not in any scenario
            # Simple heuristic: extract variable names from condition
            variables = re.findall(r"(?:patient|state|context)\.(\w+)", condition)
            if not variables:
                variables = re.findall(r"['\"](\w+)['\"]", condition)

            missing_fields = []
            for var in variables:
                if var.lower() not in all_patient_fields and var.lower() not in (
                    "true",
                    "false",
                    "none",
                    "and",
                    "or",
                    "not",
                    "in",
                    "is",
                ):
                    missing_fields.append(var)

            if missing_fields:
                issues.append(
                    {
                        "bug": "B7_POSSIBLY_DEAD_RULE",
                        "severity": "MEDIUM",
                        "graph_id": gid,
                        "rule_id": rule_id,
                        "condition": condition[:150],
                        "missing_fields": missing_fields,
                        "fix": "Verify patient context includes these fields, or remove rule",
                    }
                )

    return issues


def detect_b8_normalizer_gap(episodes):
    """B8: 모델이 출력한 action이 normalize 후 'deviation'으로 분류되는 비율.
    deviation이 과도하면 normalizer가 인식 못하는 패턴이 있다는 뜻.
    """
    issues = []
    deviation_by_model = defaultdict(lambda: {"deviation": 0, "total": 0, "examples": []})

    for ep in episodes:
        model = ep.get("_model", "unknown")
        violations = ep.get("violation_events", [])

        total_actions = 0
        actions = ep.get("actions", [])
        if isinstance(actions, list):
            total_actions = len(actions)

        deviation_count = 0
        if isinstance(violations, list):
            for v in violations:
                if isinstance(v, dict):
                    vtype = v.get("violation_type", v.get("type", "")).upper()
                    if "DEVIATION" in vtype:
                        deviation_count += 1
                        if len(deviation_by_model[model]["examples"]) < 10:
                            deviation_by_model[model]["examples"].append(
                                v.get("action", v.get("raw_action", "unknown"))
                            )

        deviation_by_model[model]["deviation"] += deviation_count
        deviation_by_model[model]["total"] += total_actions

    for model, data in deviation_by_model.items():
        if data["total"] == 0:
            continue
        rate = data["deviation"] / data["total"]
        if rate > 0.3:
            issues.append(
                {
                    "bug": "B8_HIGH_DEVIATION_RATE",
                    "severity": "HIGH",
                    "model": model,
                    "deviation_rate": round(rate, 3),
                    "deviation_count": data["deviation"],
                    "total_actions": data["total"],
                    "examples": data["examples"][:5],
                    "fix": "Add normalizer rules for these action patterns",
                }
            )
        elif rate > 0.15:
            issues.append(
                {
                    "bug": "B8_MODERATE_DEVIATION_RATE",
                    "severity": "MEDIUM",
                    "model": model,
                    "deviation_rate": round(rate, 3),
                    "deviation_count": data["deviation"],
                    "total_actions": data["total"],
                    "examples": data["examples"][:5],
                    "fix": "Review normalizer coverage",
                }
            )

    return issues


def detect_b9_duplicate_constraints(graphs):
    """B9: 같은 graph 내에서 동일 constraint가 중복 정의"""
    issues = []

    for gid, graph in graphs.items():
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        seen_expected = defaultdict(list)
        seen_forbidden = defaultdict(list)
        seen_deadlines = defaultdict(list)

        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id", node.get("name", ""))

            for a in node.get("expected_actions", []):
                name = (a if isinstance(a, str) else a.get("action", str(a))).lower().strip()
                seen_expected[name].append(nid)

            for a in node.get("forbidden_actions", []):
                name = (a if isinstance(a, str) else a.get("action", str(a))).lower().strip()
                seen_forbidden[name].append(nid)

            deadlines = node.get("deadlines", [])
            if isinstance(deadlines, dict):
                for act, mins in deadlines.items():
                    seen_deadlines[(act.lower(), mins)].append(nid)
            elif isinstance(deadlines, list):
                for dl in deadlines:
                    if isinstance(dl, dict):
                        act = dl.get("action", "").lower()
                        mins = dl.get("minutes", dl.get("time_limit", 0))
                        seen_deadlines[(act, mins)].append(nid)

        for action, nodes_list in seen_expected.items():
            if len(nodes_list) > 1:
                issues.append(
                    {
                        "bug": "B9_DUPLICATE_EXPECTED",
                        "severity": "INFO",
                        "graph_id": gid,
                        "action": action,
                        "defined_in_nodes": nodes_list,
                        "fix": "May be intentional (multiple pathways), verify",
                    }
                )

    return issues


def detect_b10_empty_effects(ae_effects, graphs):
    """B10: action_effects.yaml에 action이 존재하지만 effects가 비어있거나
    preconditions가 정의되지 않은 경우. 시뮬레이션에서 state transition이 안 됨.
    """
    issues = []

    # Collect all graph-referenced actions
    graph_actions = set()
    for gid, graph in graphs.items():
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for a in node.get("expected_actions", []):
                name = (a if isinstance(a, str) else a.get("action", str(a))).lower().strip()
                graph_actions.add(name)

    for action in graph_actions:
        if action not in ae_effects:
            continue  # B1 territory

        entry = ae_effects[action]
        if not isinstance(entry, dict):
            issues.append(
                {
                    "bug": "B10_MALFORMED_ENTRY",
                    "severity": "MEDIUM",
                    "action": action,
                    "entry_type": type(entry).__name__,
                    "fix": "action_effects entry should be a dict with effects/preconditions",
                }
            )
            continue

        effects = entry.get("effects", entry.get("effect", entry.get("state_changes", None)))
        if not effects:
            issues.append(
                {
                    "bug": "B10_EMPTY_EFFECTS",
                    "severity": "MEDIUM",
                    "action": action,
                    "fix": "Add state effects so simulation can advance",
                }
            )

    return issues


# ═══════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════


def generate_report(all_issues, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Categorize
    by_bug = defaultdict(list)
    by_severity = defaultdict(list)
    for issue in all_issues:
        by_bug[issue["bug"]].append(issue)
        by_severity[issue["severity"]].append(issue)

    lines = []
    lines.append("=" * 80)
    lines.append("CGA-Bench 파이프라인 심층 진단 보고서")
    lines.append(f"총 {len(all_issues)} issues 발견")
    lines.append("=" * 80)

    # Summary
    lines.append("\n## 요약")
    lines.append(f"  {'Severity':10s} {'Count':>6s}")
    lines.append("  " + "-" * 20)
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "WARNING", "INFO"]:
        count = len(by_severity.get(sev, []))
        marker = " 🔴" if sev == "CRITICAL" else " 🟡" if sev == "HIGH" else ""
        lines.append(f"  {sev:10s} {count:6d}{marker}")

    lines.append(f"\n  {'Bug Category':35s} {'Count':>6s} {'Severity':>10s}")
    lines.append("  " + "-" * 55)
    for bug_type in sorted(by_bug.keys()):
        items = by_bug[bug_type]
        max_sev = "INFO"
        for item in items:
            for s in ["CRITICAL", "HIGH", "MEDIUM", "WARNING", "INFO"]:
                if item["severity"] == s and ["CRITICAL", "HIGH", "MEDIUM", "WARNING", "INFO"].index(s) < [
                    "CRITICAL",
                    "HIGH",
                    "MEDIUM",
                    "WARNING",
                    "INFO",
                ].index(max_sev):
                    max_sev = s
        lines.append(f"  {bug_type:35s} {len(items):6d} {max_sev:>10s}")

    # Detail by category
    for bug_type in sorted(by_bug.keys()):
        items = by_bug[bug_type]
        lines.append(f"\n{'─' * 70}")
        lines.append(f"## {bug_type} ({len(items)} issues)")
        lines.append(f"{'─' * 70}")

        # Show up to 20 examples
        for i, item in enumerate(items[:20]):
            lines.append(f"\n  [{item['severity']}] #{i + 1}")
            for k, v in item.items():
                if k in ("bug", "severity"):
                    continue
                lines.append(f"    {k}: {v}")

        if len(items) > 20:
            lines.append(f"\n  ... and {len(items) - 20} more (see JSON output)")

    # Action items
    lines.append(f"\n{'=' * 70}")
    lines.append("## 즉시 조치 필요 사항")
    lines.append(f"{'=' * 70}")

    critical = by_severity.get("CRITICAL", [])
    high = by_severity.get("HIGH", [])

    if critical:
        lines.append(f"\n  🔴 CRITICAL ({len(critical)}개):")
        for item in critical[:10]:
            lines.append(
                f"    - [{item['bug']}] {item.get('graph_id', '')} / {item.get('action', '')} : {item.get('fix', '')}"
            )

    if high:
        lines.append(f"\n  🟡 HIGH ({len(high)}개):")
        for item in high[:10]:
            lines.append(
                f"    - [{item['bug']}] {item.get('graph_id', item.get('model', ''))} / {item.get('action', item.get('graph_action', ''))} : {item.get('fix', '')}"
            )

    # B1 special: name mismatches that explain some of the 118 BUGs
    b1_high = [i for i in by_bug.get("B1_NAME_MISMATCH", []) if i["severity"] == "HIGH"]
    if b1_high:
        lines.append(f"\n  ★ B1 Name Mismatch ({len(b1_high)}개 high-similarity)")
        lines.append("    이 중 일부는 118개 BUG_NOT_IN_EFFECTS를 설명할 수 있음:")
        for item in b1_high[:15]:
            lines.append(
                f"    '{item['graph_action']}' → '{item['closest_in_effects']}' (similarity={item['similarity']})"
            )
        lines.append(f"    → 이름만 고치면 action_effects 추가 없이 해결되는 BUG 수: ~{len(b1_high)}")

    report_text = "\n".join(lines)

    report_path = output_dir / "deep_diagnosis_report.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"[SAVED] {report_path}")

    # Save all issues as JSON
    json_path = output_dir / "deep_diagnosis_all_issues.json"
    with open(json_path, "w") as f:
        json.dump(all_issues, f, indent=2, default=str)
    print(f"[SAVED] {json_path}")

    # Save fix list (CRITICAL + HIGH only)
    fix_path = output_dir / "fix_list_priority.json"
    fix_items = [i for i in all_issues if i["severity"] in ("CRITICAL", "HIGH")]
    with open(fix_path, "w") as f:
        json.dump(fix_items, f, indent=2, default=str)
    print(f"[SAVED] {fix_path} ({len(fix_items)} items)")

    # Save B1 rename suggestions
    rename_path = output_dir / "b1_rename_suggestions.json"
    renames = [
        {
            "from": i["graph_action"],
            "to": i["closest_in_effects"],
            "graph_id": i["graph_id"],
            "similarity": i["similarity"],
        }
        for i in by_bug.get("B1_NAME_MISMATCH", [])
        if i["severity"] == "HIGH"
    ]
    with open(rename_path, "w") as f:
        json.dump(renames, f, indent=2)
    print(f"[SAVED] {rename_path} ({len(renames)} renames)")

    print(report_text)


def main():
    parser = argparse.ArgumentParser(description="Deep Pipeline Diagnosis")
    parser.add_argument("--episodes-dir", default="results/full_706_final")
    parser.add_argument("--graphs-dir", default="cpg_model/graphs")
    parser.add_argument("--action-effects", default="cpg_model/action_effects.yaml")
    parser.add_argument("--scenarios-dir", default="configs/scenarios")
    parser.add_argument("--auto-scenarios", default="configs/scenarios/auto_generated_scenarios.yaml")
    parser.add_argument("--output-dir", default="evidence_pack/deep_diagnosis")
    args = parser.parse_args()

    print("=" * 80)
    print("CGA-Bench 파이프라인 심층 진단")
    print("=" * 80)

    # Load
    episodes = load_episodes(args.episodes_dir) if Path(args.episodes_dir).exists() else []
    graphs = load_graphs(args.graphs_dir)
    ae_effects, ae_preconditions = load_action_effects(args.action_effects)
    scenarios = load_all_scenarios(args.scenarios_dir)

    ae_keys = set(ae_effects.keys())
    print(
        f"\n[DATA] {len(episodes)} episodes, {len(graphs)} graphs, "
        f"{len(ae_keys)} action_effects, {len(scenarios)} scenarios"
    )

    all_issues = []

    # Run all detectors
    detectors = [
        ("B1: Action Name Mismatch", lambda: detect_b1_name_mismatch(graphs, ae_keys)),
        (
            "B2: Precondition Impossibility",
            lambda: (
                detect_b2_precondition_impossibility(graphs, ae_effects, ae_preconditions, episodes) if episodes else []
            ),
        ),
        ("B3: Deadline Impossibility", lambda: detect_b3_deadline_impossibility(graphs)),
        ("B4: Sequence Impossibility", lambda: detect_b4_sequence_impossibility(graphs)),
        ("B5: Forbidden/Required Conflict", lambda: detect_b5_forbidden_required_conflict(graphs)),
        ("B6: Orphan Scenarios", lambda: detect_b6_orphan_scenarios(scenarios, graphs)),
        ("B7: Dead Conditional Rules", lambda: detect_b7_dead_conditional_rules(graphs, scenarios)),
        ("B8: Normalizer Gap", lambda: detect_b8_normalizer_gap(episodes) if episodes else []),
        ("B9: Duplicate Constraints", lambda: detect_b9_duplicate_constraints(graphs)),
        ("B10: Empty Effects", lambda: detect_b10_empty_effects(ae_effects, graphs)),
    ]

    for name, detector in detectors:
        print(f"\n[DETECT] {name}...")
        issues = detector()
        print(f"  → {len(issues)} issues found")
        all_issues.extend(issues)

    print(f"\n[TOTAL] {len(all_issues)} issues across all categories")

    # Generate report
    generate_report(all_issues, args.output_dir)

    print("\n" + "=" * 80)
    print("심층 진단 완료")
    print("=" * 80)


if __name__ == "__main__":
    main()
