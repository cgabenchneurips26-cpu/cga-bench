#!/usr/bin/env python3
"""Held-out 극단 도메인 진단 스크립트
====================================
aba_burn (98.6%), apa_agitation (100%) hard violation 원인 특정.

핵심 질문:
1. 이 도메인들의 constraint density가 다른 도메인 대비 얼마나 높은가?
2. 어떤 violation type이 지배하는가?  
3. 동시 만족 불가능한 constraint 조합이 있는가?
4. Expected action 수 대비 모델이 수행한 action 수는?
5. 다른 held-out 도메인(aabb_transfusion=2.8%)과 무엇이 다른가?

Usage:
    python diagnose_heldout_extremes.py \
        --episodes-dir results/full_706_final \
        --graphs-dir cpg_model/graphs \
        [--output-dir evidence_pack/heldout_audit]
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics
import sys

import yaml

HELD_OUT_DOMAINS = [
    "aba_burn_resuscitation",
    "aabb_transfusion",
    "acog_obstetric_hemorrhage",
    "pals_pediatric_emergency",
    "apa_agitation_management",
]


def load_episodes(episodes_dir):
    """에피소드 JSON 파일 로드"""
    episodes = []
    episodes_dir = Path(episodes_dir)
    if not episodes_dir.exists():
        print(f"[ERROR] {episodes_dir} not found")
        sys.exit(1)

    for model_dir in sorted(episodes_dir.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                if not isinstance(ep, dict):
                    continue
                ep["_model"] = model_dir.name
                ep["_file"] = str(ep_file)
                episodes.append(ep)
            except:
                pass
    print(f"[INFO] Loaded {len(episodes)} episodes")
    return episodes


def load_graphs(graphs_dir):
    """CPG graph YAML 파일 로드"""
    graphs = {}
    graphs_dir = Path(graphs_dir)
    for yaml_file in sorted(graphs_dir.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue
        try:
            with open(yaml_file) as f:
                graph = yaml.safe_load(f)
            graphs[yaml_file.stem] = graph
        except:
            pass
    print(f"[INFO] Loaded {len(graphs)} graphs")
    return graphs


def extract_graph_metrics(graph, graph_id):
    """단일 graph에서 상세 지표 추출"""
    metrics = {
        "graph_id": graph_id,
        "n_nodes": 0,
        "n_expected_actions": 0,
        "n_forbidden_actions": 0,
        "n_deadlines": 0,
        "n_sequence_rules": 0,
        "n_conditional_rules": 0,
        "n_cond_forbidden": 0,
        "n_cond_required": 0,
        "n_cond_within": 0,
        "n_cond_before": 0,
        "expected_actions_list": [],
        "forbidden_actions_list": [],
        "deadline_details": [],
        "sequence_details": [],
        "conditional_rule_details": [],
    }

    nodes = graph.get("nodes", [])
    if isinstance(nodes, dict):
        nodes = list(nodes.values())

    metrics["n_nodes"] = len(nodes)

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id", node.get("name", "unknown"))

        # Expected actions
        expected = node.get("expected_actions", [])
        if isinstance(expected, list):
            metrics["n_expected_actions"] += len(expected)
            for a in expected:
                action_name = a if isinstance(a, str) else a.get("action_id", a.get("action", str(a)))
                metrics["expected_actions_list"].append(
                    {
                        "node": node_id,
                        "action": action_name,
                    }
                )

        # Forbidden actions
        forbidden = node.get("forbidden_actions", [])
        if isinstance(forbidden, list):
            metrics["n_forbidden_actions"] += len(forbidden)
            for a in forbidden:
                action_name = a if isinstance(a, str) else a.get("action_id", a.get("action", str(a)))
                metrics["forbidden_actions_list"].append(
                    {
                        "node": node_id,
                        "action": action_name,
                    }
                )

        # Deadlines
        deadlines = node.get("deadlines", [])
        if isinstance(deadlines, list):
            metrics["n_deadlines"] += len(deadlines)
            for d in deadlines:
                if isinstance(d, dict):
                    metrics["deadline_details"].append(
                        {
                            "node": node_id,
                            "action": d.get("action", ""),
                            "minutes": d.get("minutes", d.get("time_limit", "")),
                        }
                    )
        elif isinstance(deadlines, dict):
            metrics["n_deadlines"] += len(deadlines)
            for action, minutes in deadlines.items():
                metrics["deadline_details"].append(
                    {
                        "node": node_id,
                        "action": action,
                        "minutes": minutes,
                    }
                )

        # Sequence rules
        seq_rules = node.get("sequence_rules", [])
        if isinstance(seq_rules, list):
            metrics["n_sequence_rules"] += len(seq_rules)
            for sr in seq_rules:
                if isinstance(sr, dict):
                    metrics["sequence_details"].append(
                        {
                            "node": node_id,
                            "before": sr.get("before", sr.get("first", "")),
                            "after": sr.get("after", sr.get("then", "")),
                        }
                    )

    # Conditional rules
    cond_rules = graph.get("conditional_rules", [])
    if isinstance(cond_rules, list):
        metrics["n_conditional_rules"] = len(cond_rules)
        for rule in cond_rules:
            if isinstance(rule, dict):
                ctype = rule.get("constraint_type", "").upper()
                if "FORBID" in ctype:
                    metrics["n_cond_forbidden"] += 1
                elif "REQUIRED" in ctype or "MUST" in ctype:
                    metrics["n_cond_required"] += 1
                elif "WITHIN" in ctype:
                    metrics["n_cond_within"] += 1
                elif "BEFORE" in ctype:
                    metrics["n_cond_before"] += 1

                metrics["conditional_rule_details"].append(
                    {
                        "rule_id": rule.get("rule_id", rule.get("id", "")),
                        "condition": str(rule.get("condition", ""))[:100],
                        "constraint_type": ctype,
                        "target_action": rule.get("target_action", rule.get("action", "")),
                        "skip_generation": rule.get("skip_scenario_generation", False),
                    }
                )

    # Computed
    metrics["total_hard_constraints"] = (
        metrics["n_expected_actions"]
        + metrics["n_forbidden_actions"]
        + metrics["n_deadlines"]
        + metrics["n_sequence_rules"]
    )
    metrics["constraint_density"] = metrics["total_hard_constraints"] / max(metrics["n_nodes"], 1)

    return metrics


def analyze_episodes_by_domain(episodes):
    """도메인별 에피소드 분석"""
    domain_stats = defaultdict(
        lambda: {
            "n_episodes": 0,
            "n_hard_violations": 0,
            "violation_types": Counter(),
            "actions_per_episode": [],
            "compliance_scores": [],
            "violated_actions": Counter(),
            "models": defaultdict(
                lambda: {
                    "n_episodes": 0,
                    "n_hard_violations": 0,
                    "actions": [],
                }
            ),
        }
    )

    for ep in episodes:
        # Extract graph/domain
        graph_id = ep.get("graph_id", ep.get("cpg_graph", ""))
        if not graph_id:
            # Try to extract from scenario_id
            sid = ep.get("scenario_id", "")
            for domain in HELD_OUT_DOMAINS:
                if domain in sid:
                    graph_id = domain
                    break
        if not graph_id:
            continue

        model = ep.get("_model", "unknown")
        ds = domain_stats[graph_id]
        ds["n_episodes"] += 1

        # Compliance
        cs = ep.get("compliance_score", 0)
        ds["compliance_scores"].append(cs)

        # Actions count
        actions = ep.get("actions", [])
        n_actions = len(actions) if isinstance(actions, list) else ep.get("actions_count", 0)
        ds["actions_per_episode"].append(n_actions)

        # Violations
        violations = ep.get("violation_events", [])
        has_hard_violation = False

        if isinstance(violations, list) and len(violations) > 0:
            has_hard_violation = True
            ds["n_hard_violations"] += 1

            for v in violations:
                if isinstance(v, dict):
                    vtype = v.get("violation_type", v.get("type", "UNKNOWN")).upper()
                    action = v.get("action", v.get("expected_action", v.get("constraint_action", "unknown")))
                    ds["violation_types"][vtype] += 1
                    ds["violated_actions"][action] += 1
        elif isinstance(violations, list) and len(violations) == 0:
            # Check compliance_score as proxy
            if cs < 1.0:
                # Might have violations not recorded
                pass

        # Model-level
        ds["models"][model]["n_episodes"] += 1
        ds["models"][model]["actions"].append(n_actions)
        if has_hard_violation:
            ds["models"][model]["n_hard_violations"] += 1

    return domain_stats


def detect_constraint_conflicts(graph_metrics):
    """Graph 내 constraint 충돌/비현실성 탐지:
    1. REQUIRED와 FORBIDDEN이 동일 action을 가리키는 경우
    2. Deadline이 지나치게 짧은 경우 (< 5분)
    3. Expected actions가 node 수 대비 과다한 경우
    """
    issues = []
    gid = graph_metrics["graph_id"]

    expected_set = set(e["action"] for e in graph_metrics["expected_actions_list"])
    forbidden_set = set(f["action"] for f in graph_metrics["forbidden_actions_list"])

    # 1. REQUIRED ∩ FORBIDDEN
    conflict = expected_set & forbidden_set
    if conflict:
        issues.append(
            {
                "type": "REQUIRED_FORBIDDEN_CONFLICT",
                "severity": "CRITICAL",
                "detail": f"{len(conflict)} actions are both REQUIRED and FORBIDDEN: {list(conflict)[:5]}",
            }
        )

    # 2. Tight deadlines
    for dl in graph_metrics["deadline_details"]:
        minutes = dl.get("minutes", 999)
        if isinstance(minutes, (int, float)) and minutes <= 5:
            issues.append(
                {
                    "type": "TIGHT_DEADLINE",
                    "severity": "WARNING",
                    "detail": f"Deadline {dl['action']} in node {dl['node']}: {minutes} minutes",
                }
            )

    # 3. Expected actions density
    n_exp = graph_metrics["n_expected_actions"]
    n_nodes = graph_metrics["n_nodes"]
    if n_nodes > 0 and n_exp / n_nodes > 10:
        issues.append(
            {
                "type": "HIGH_EXPECTED_DENSITY",
                "severity": "WARNING",
                "detail": f"{n_exp} expected actions across {n_nodes} nodes ({n_exp / n_nodes:.1f} per node)",
            }
        )

    # 4. Conditional rules that are always active (no real condition)
    for rule in graph_metrics["conditional_rule_details"]:
        cond = rule.get("condition", "")
        if cond in ("True", "true", "1", "True  # always active", ""):
            issues.append(
                {
                    "type": "ALWAYS_ACTIVE_CONDITIONAL",
                    "severity": "INFO",
                    "detail": f"Rule {rule['rule_id']} ({rule['constraint_type']}): condition='{cond}' is always active",
                }
            )

    return issues


def generate_report(graphs, graph_metrics_all, domain_stats, output_dir):
    """종합 보고서"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("=" * 80)
    lines.append("HELD-OUT 극단 도메인 진단 보고서")
    lines.append("=" * 80)

    # 1. 전체 도메인 비교 — constraint density
    lines.append("\n## 1. 전 도메인 Constraint Density 비교")
    lines.append(
        f"{'Graph ID':45s} {'Nodes':>5s} {'Exp':>5s} {'Forb':>5s} {'DL':>5s} {'Seq':>5s} {'Cond':>5s} {'Total':>6s} {'Density':>8s}"
    )
    lines.append("-" * 120)

    densities = []
    for gid in sorted(graph_metrics_all.keys()):
        m = graph_metrics_all[gid]
        is_heldout = any(ho in gid for ho in HELD_OUT_DOMAINS)
        marker = " ★" if is_heldout else ""
        lines.append(
            f"{gid:45s} {m['n_nodes']:5d} {m['n_expected_actions']:5d} "
            f"{m['n_forbidden_actions']:5d} {m['n_deadlines']:5d} {m['n_sequence_rules']:5d} "
            f"{m['n_conditional_rules']:5d} {m['total_hard_constraints']:6d} "
            f"{m['constraint_density']:8.1f}{marker}"
        )
        densities.append((gid, m["constraint_density"], m["total_hard_constraints"]))

    # Stats
    all_densities = [d for _, d, _ in densities]
    heldout_densities = [(gid, d) for gid, d, _ in densities if any(ho in gid for ho in HELD_OUT_DOMAINS)]

    if all_densities:
        lines.append(f"\n  Mean density (all): {statistics.mean(all_densities):.1f}")
        lines.append(f"  Median density (all): {statistics.median(all_densities):.1f}")
        if heldout_densities:
            lines.append(f"  Held-out densities: {', '.join(f'{gid}={d:.1f}' for gid, d in heldout_densities)}")

    # 2. Held-out vs Main 에피소드 비교
    lines.append("\n## 2. 도메인별 Hard Violation Rate (에피소드)")
    lines.append(f"{'Graph ID':45s} {'Episodes':>8s} {'HardViol':>8s} {'Rate':>8s} {'MeanComp':>9s} {'MeanActs':>9s}")
    lines.append("-" * 100)

    domain_rates = []
    for gid in sorted(domain_stats.keys()):
        ds = domain_stats[gid]
        n = ds["n_episodes"]
        n_hv = ds["n_hard_violations"]
        rate = n_hv / n * 100 if n > 0 else 0
        mean_comp = statistics.mean(ds["compliance_scores"]) if ds["compliance_scores"] else 0
        mean_acts = statistics.mean(ds["actions_per_episode"]) if ds["actions_per_episode"] else 0
        is_heldout = any(ho in gid for ho in HELD_OUT_DOMAINS)
        marker = " ★" if is_heldout else ""

        lines.append(f"{gid:45s} {n:8d} {n_hv:8d} {rate:7.1f}% {mean_comp:9.3f} {mean_acts:9.1f}{marker}")
        domain_rates.append((gid, rate, n, is_heldout))

    # 3. 극단 도메인 심층 분석
    extreme_domains = ["aba_burn", "apa_agitation"]
    low_domain = "aabb_transfusion"

    for target in extreme_domains + [low_domain]:
        matching = [(gid, ds) for gid, ds in domain_stats.items() if target in gid]
        if not matching:
            continue

        gid, ds = matching[0]
        lines.append(f"\n## 3. 심층 분석: {gid}")
        lines.append(f"  Episodes: {ds['n_episodes']}")
        lines.append(
            f"  Hard Violation Rate: {ds['n_hard_violations']}/{ds['n_episodes']} = {ds['n_hard_violations'] / max(ds['n_episodes'], 1) * 100:.1f}%"
        )

        # Violation type breakdown
        lines.append("\n  Violation Type Breakdown:")
        total_v = sum(ds["violation_types"].values())
        for vtype, count in ds["violation_types"].most_common():
            lines.append(
                f"    {vtype:20s}: {count:5d} ({count / total_v * 100:.1f}%)"
                if total_v > 0
                else f"    {vtype}: {count}"
            )

        # Most violated actions
        lines.append("\n  Top Violated Actions:")
        for action, count in ds["violated_actions"].most_common(10):
            lines.append(f"    {action:50s}: {count:5d}")

        # Model breakdown
        lines.append("\n  Model-Level Breakdown:")
        for model, mdata in sorted(ds["models"].items()):
            rate = mdata["n_hard_violations"] / mdata["n_episodes"] * 100 if mdata["n_episodes"] > 0 else 0
            mean_acts = statistics.mean(mdata["actions"]) if mdata["actions"] else 0
            lines.append(f"    {model:20s}: {rate:5.1f}% hard viol, mean {mean_acts:.0f} actions")

        # Graph metrics
        matching_graph = [(gid2, m) for gid2, m in graph_metrics_all.items() if target in gid2]
        if matching_graph:
            gid2, m = matching_graph[0]
            lines.append("\n  Graph Structure:")
            lines.append(f"    Nodes: {m['n_nodes']}")
            lines.append(f"    Expected actions: {m['n_expected_actions']}")
            lines.append(f"    Forbidden: {m['n_forbidden_actions']}")
            lines.append(f"    Deadlines: {m['n_deadlines']}")
            lines.append(f"    Sequence rules: {m['n_sequence_rules']}")
            lines.append(f"    Conditional rules: {m['n_conditional_rules']}")
            lines.append(f"    Constraint density: {m['constraint_density']:.1f}")

            # Conflicts
            issues = detect_constraint_conflicts(m)
            if issues:
                lines.append("\n  ⚠️ Detected Issues:")
                for issue in issues:
                    lines.append(f"    [{issue['severity']}] {issue['type']}: {issue['detail']}")

    # 4. aba_burn vs aabb_transfusion 대비 분석
    lines.append("\n## 4. 극단 대비: aba_burn (98.6%) vs aabb_transfusion (2.8%)")

    burn_data = next(((gid, ds) for gid, ds in domain_stats.items() if "aba_burn" in gid), None)
    trans_data = next(((gid, ds) for gid, ds in domain_stats.items() if "aabb_transfusion" in gid), None)
    burn_graph = next(((gid, m) for gid, m in graph_metrics_all.items() if "aba_burn" in gid), None)
    trans_graph = next(((gid, m) for gid, m in graph_metrics_all.items() if "aabb_transfusion" in gid), None)

    if burn_graph and trans_graph:
        _, bm = burn_graph
        _, tm = trans_graph
        lines.append(f"  {'Metric':30s} {'aba_burn':>12s} {'aabb_trans':>12s} {'Ratio':>8s}")
        lines.append("  " + "-" * 70)
        comparisons = [
            ("Nodes", bm["n_nodes"], tm["n_nodes"]),
            ("Expected actions", bm["n_expected_actions"], tm["n_expected_actions"]),
            ("Forbidden", bm["n_forbidden_actions"], tm["n_forbidden_actions"]),
            ("Deadlines", bm["n_deadlines"], tm["n_deadlines"]),
            ("Constraint density", bm["constraint_density"], tm["constraint_density"]),
            ("Conditional rules", bm["n_conditional_rules"], tm["n_conditional_rules"]),
        ]
        for name, bv, tv in comparisons:
            ratio = bv / tv if tv > 0 else float("inf")
            lines.append(f"  {name:30s} {bv:12.1f} {tv:12.1f} {ratio:8.1f}x")

    # 5. 권장 조치
    lines.append("\n## 5. 권장 조치")
    lines.append("=" * 60)
    lines.append("""
  🔴 aba_burn/apa_agitation 98-100% hard violation 대응:
  
  1. [즉시] Violation type breakdown 확인
     - OMISSION 지배적이면: expected_actions가 과다 → soft로 전환 검토
     - FORBIDDEN 지배적이면: conditional rule의 condition 검증
     - WITHIN 지배적이면: deadline 완화 검토
  
  2. [즉시] 모든 모델이 실패하는 specific constraint 식별
     → 위의 "Top Violated Actions"에서 확인
     → 이 action들이 clinically mandatory인지 확인 필요
  
  3. [논문] Held-out 결과를 aggregate로만 쓰지 말고 per-domain breakdown 필수
     → Table에 5개 held-out domain 각각의 violation rate 제시
     → "Cross-domain variance는 constraint density와 상관"이라는 framing
  
  4. [논문] aba_burn/apa_agitation이 높은 이유를 limitation이 아닌
     "constraint-dense domain에서 blind spot이 더 심각"으로 framing 가능
     → 이 경우 constraint가 valid해야 함 (clinician 필요)
  
  5. [코드] aabb_transfusion이 2.8%인 이유도 확인
     → constraint가 너무 느슨하면 sensitivity 문제
     → TCC가 거의 모든 episode를 pass하면 "too lenient" 공격 가능
""")

    report_text = "\n".join(lines)

    report_path = output_dir / "heldout_extreme_diagnosis.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"\n[SAVED] {report_path}")

    # Save domain comparison JSON
    comparison_path = output_dir / "domain_comparison.json"
    comparison = {}
    for gid in sorted(domain_stats.keys()):
        ds = domain_stats[gid]
        n = ds["n_episodes"]
        comparison[gid] = {
            "n_episodes": n,
            "hard_violation_rate": ds["n_hard_violations"] / n * 100 if n > 0 else 0,
            "mean_compliance": statistics.mean(ds["compliance_scores"]) if ds["compliance_scores"] else 0,
            "mean_actions": statistics.mean(ds["actions_per_episode"]) if ds["actions_per_episode"] else 0,
            "violation_type_dist": dict(ds["violation_types"]),
            "is_heldout": any(ho in gid for ho in HELD_OUT_DOMAINS),
        }
    with open(comparison_path, "w") as f:
        json.dump(comparison, f, indent=2)
    print(f"[SAVED] {comparison_path}")

    print(report_text)
    return report_text


def main():
    parser = argparse.ArgumentParser(description="Held-out Extreme Domain Diagnosis")
    parser.add_argument("--episodes-dir", default="results/full_706_final", help="Episode results directory")
    parser.add_argument("--graphs-dir", default="cpg_model/graphs", help="CPG graph YAML directory")
    parser.add_argument("--output-dir", default="evidence_pack/heldout_audit", help="Output directory")
    args = parser.parse_args()

    print("=" * 60)
    print("HELD-OUT 극단 도메인 진단 시작")
    print("=" * 60)

    episodes = load_episodes(args.episodes_dir)
    graphs = load_graphs(args.graphs_dir)

    if not episodes:
        print("[ERROR] No episodes found")
        sys.exit(1)

    # Extract graph metrics for all graphs
    graph_metrics_all = {}
    for gid, graph in graphs.items():
        graph_metrics_all[gid] = extract_graph_metrics(graph, gid)

    # Analyze episodes by domain
    domain_stats = analyze_episodes_by_domain(episodes)

    # Generate report
    generate_report(graphs, graph_metrics_all, domain_stats, args.output_dir)


if __name__ == "__main__":
    main()
