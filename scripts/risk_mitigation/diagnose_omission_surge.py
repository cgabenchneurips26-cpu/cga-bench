#!/usr/bin/env python3
"""OMISSION 29.3x Surge 진단 스크립트
===================================
clinician audit 없이 코드 레벨에서 engine-derived REQUIRED constraints의
structural precision을 추정하고, over-specification 원인을 특정한다.

핵심 질문:
1. Engine이 REQUIRED로 지정한 action 중 "어떤 모델도 수행하지 않는" 것은 몇 %?
   → 이것이 높으면 constraint가 비현실적으로 엄격할 가능성
2. OMISSION violation 중 engine-only constraint에서 발생한 비율은?
   → 이것이 높으면 engine이 과다 지정한 것
3. 어떤 graph/domain이 OMISSION을 지배하는가?
4. "모든 모델이 실패하는" REQUIRED constraint는 진짜 어려운 것인가, 아니면 invalid인가?

Usage:
    python diagnose_omission_surge.py \
        --episodes-dir results/full_706_final \
        --graphs-dir cpg_model/graphs \
        --scenarios-dir configs/scenarios \
        --auto-scenarios configs/scenarios/auto_generated_scenarios.yaml \
        [--output-dir evidence_pack/omission_audit]
"""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import sys

import yaml


def load_episodes(episodes_dir):
    """에피소드 JSON 파일 로드"""
    episodes = []
    episodes_dir = Path(episodes_dir)
    if not episodes_dir.exists():
        print(f"[ERROR] Episodes directory not found: {episodes_dir}")
        sys.exit(1)

    for model_dir in sorted(episodes_dir.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        model_name = model_dir.name
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                if not isinstance(ep, dict):
                    continue
                ep["_model"] = model_name
                ep["_file"] = str(ep_file)
                episodes.append(ep)
            except Exception as e:
                print(f"[WARN] Failed to load {ep_file}: {e}")
    print(f"[INFO] Loaded {len(episodes)} episodes from {episodes_dir}")
    return episodes


def load_graphs(graphs_dir):
    """CPG graph YAML 파일 로드"""
    graphs = {}
    graphs_dir = Path(graphs_dir)
    if not graphs_dir.exists():
        print(f"[ERROR] Graphs directory not found: {graphs_dir}")
        sys.exit(1)

    for yaml_file in sorted(graphs_dir.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue
        try:
            with open(yaml_file) as f:
                graph = yaml.safe_load(f)
            graph_id = yaml_file.stem
            graphs[graph_id] = graph
        except Exception as e:
            print(f"[WARN] Failed to load {yaml_file}: {e}")
    print(f"[INFO] Loaded {len(graphs)} graphs")
    return graphs


def load_scenarios(scenarios_dir, auto_scenarios_path=None):
    """시나리오 YAML 파일 로드. manual vs auto 구분."""
    manual = []
    auto = []
    scenarios_dir = Path(scenarios_dir)

    # Manual scenarios
    for yaml_file in sorted(scenarios_dir.glob("*.yaml")):
        if "auto_generated" in yaml_file.name:
            continue
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if isinstance(data, list):
                for s in data:
                    s["_source"] = "manual"
                    s["_file"] = str(yaml_file)
                    manual.append(s)
            elif isinstance(data, dict):
                if "scenarios" in data:
                    for s in data["scenarios"]:
                        s["_source"] = "manual"
                        s["_file"] = str(yaml_file)
                        manual.append(s)
                else:
                    data["_source"] = "manual"
                    data["_file"] = str(yaml_file)
                    manual.append(data)
        except Exception as e:
            print(f"[WARN] Failed to load {yaml_file}: {e}")

    # Auto-generated scenarios
    if auto_scenarios_path:
        auto_path = Path(auto_scenarios_path)
        if auto_path.exists():
            try:
                with open(auto_path) as f:
                    data = yaml.safe_load(f)
                if isinstance(data, list):
                    for s in data:
                        s["_source"] = "auto"
                        auto.extend(data)
                        break
                elif isinstance(data, dict) and "scenarios" in data:
                    for s in data["scenarios"]:
                        s["_source"] = "auto"
                        auto.append(s)
            except Exception as e:
                print(f"[WARN] Failed to load auto scenarios: {e}")

    print(f"[INFO] Loaded {len(manual)} manual, {len(auto)} auto scenarios")
    return manual, auto


def extract_graph_constraints(graphs):
    """각 graph에서 constraint 수를 추출.
    Returns: {graph_id: {type: count, ...}, ...}
    """
    graph_constraints = {}

    for gid, graph in graphs.items():
        counts = Counter()
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        for node in nodes:
            if not isinstance(node, dict):
                continue
            # REQUIRED (expected_actions)
            expected = node.get("expected_actions", [])
            if isinstance(expected, list):
                counts["REQUIRED"] += len(expected)
            # FORBIDDEN
            forbidden = node.get("forbidden_actions", [])
            if isinstance(forbidden, list):
                counts["FORBIDDEN"] += len(forbidden)
            # WITHIN (deadlines)
            deadlines = node.get("deadlines", [])
            if isinstance(deadlines, list) or isinstance(deadlines, dict):
                counts["WITHIN"] += len(deadlines)
            # BEFORE (sequence_rules)
            seq_rules = node.get("sequence_rules", [])
            if isinstance(seq_rules, list):
                counts["BEFORE"] += len(seq_rules)

        # Conditional rules
        cond_rules = graph.get("conditional_rules", [])
        if isinstance(cond_rules, list):
            for rule in cond_rules:
                if isinstance(rule, dict):
                    ctype = rule.get("constraint_type", "").upper()
                    if ctype in ("FORBIDDEN", "REQUIRED", "WITHIN", "BEFORE"):
                        counts[f"COND_{ctype}"] += 1

        graph_constraints[gid] = dict(counts)

    return graph_constraints


def analyze_violation_by_type(episodes):
    """에피소드별 violation type 분포 분석"""
    type_counts = Counter()
    type_by_model = defaultdict(Counter)
    type_by_graph = defaultdict(Counter)
    type_by_source = defaultdict(Counter)  # manual vs auto

    for ep in episodes:
        model = ep.get("_model", "unknown")
        graph_id = ep.get("graph_id", ep.get("cpg_graph", "unknown"))
        scenario_id = ep.get("scenario_id", "")
        source = "auto" if "auto" in scenario_id.lower() or scenario_id.startswith("gen_") else "manual"

        violations = ep.get("violation_events", [])
        if not violations:
            continue

        for v in violations:
            if isinstance(v, dict):
                vtype = v.get("violation_type", v.get("type", "UNKNOWN")).upper()
            elif isinstance(v, str):
                vtype = v.upper()
            else:
                continue

            # Normalize
            if "OMISSION" in vtype or "MUST" in vtype or "REQUIRED" in vtype:
                vtype = "OMISSION"
            elif "COMMISSION" in vtype or "FORBID" in vtype:
                vtype = "COMMISSION"
            elif "TIMING" in vtype or "WITHIN" in vtype:
                vtype = "TIMING"
            elif "SEQUENCE" in vtype or "BEFORE" in vtype:
                vtype = "SEQUENCE"
            elif "DEVIATION" in vtype:
                vtype = "DEVIATION"

            type_counts[vtype] += 1
            type_by_model[model][vtype] += 1
            type_by_graph[graph_id][vtype] += 1
            type_by_source[source][vtype] += 1

    return type_counts, type_by_model, type_by_graph, type_by_source


def analyze_required_constraint_feasibility(episodes):
    """핵심 분석: 각 REQUIRED action에 대해
    - 몇 개 모델이 수행했는가?
    - 모든 모델이 실패한 REQUIRED는 무엇인가?
    - scenario별로 기대 action 수 vs 실제 action 수
    """
    # scenario_id → {expected_actions, model_actions, violations}
    scenario_data = defaultdict(
        lambda: {
            "expected": set(),
            "model_performed": defaultdict(set),
            "model_violations": defaultdict(list),
            "graph_id": "",
            "source": "",
            "n_episodes": 0,
        }
    )

    for ep in episodes:
        sid = ep.get("scenario_id", "")
        model = ep.get("_model", "unknown")
        graph_id = ep.get("graph_id", ep.get("cpg_graph", ""))

        sd = scenario_data[sid]
        sd["graph_id"] = graph_id
        sd["n_episodes"] += 1

        # Determine source
        if (
            "auto" in sid.lower()
            or sid.startswith("gen_")
            or sid.startswith("combo_")
            or sid.startswith("pathway_")
            or sid.startswith("val_")
        ):
            sd["source"] = "auto"
        else:
            sd["source"] = "manual"

        # Expected actions
        expected = ep.get("expected_actions", [])
        if isinstance(expected, list):
            for a in expected:
                if isinstance(a, dict):
                    sd["expected"].add(a.get("action", a.get("name", str(a))))
                elif isinstance(a, str):
                    sd["expected"].add(a)

        # Performed actions
        actions = ep.get("actions", [])
        if isinstance(actions, list):
            for a in actions:
                if isinstance(a, dict):
                    act_name = a.get("action_id", a.get("action", a.get("name", "")))
                    if act_name:
                        sd["model_performed"][model].add(act_name)
                elif isinstance(a, str):
                    sd["model_performed"][model].add(a)

        # Violations
        violations = ep.get("violation_events", [])
        if isinstance(violations, list):
            for v in violations:
                if isinstance(v, dict):
                    sd["model_violations"][model].append(v)

    return scenario_data


def compute_structural_precision(scenario_data):
    """Structural Precision 추정 (clinician 없이):

    For each REQUIRED action across all scenarios:
    - "never_performed": 어떤 모델도, 어떤 episode에서도 수행하지 않은 action
    - "sometimes_performed": 일부 모델이 수행
    - "always_performed": 모든 모델이 수행

    never_performed가 높으면 → constraint가 비현실적
    always_performed가 높으면 → constraint가 당연히 valid
    """
    action_performance = defaultdict(
        lambda: {
            "models_performed": set(),
            "models_total": set(),
            "scenarios": set(),
            "source": set(),
        }
    )

    for sid, sd in scenario_data.items():
        for exp_action in sd["expected"]:
            key = (sd["graph_id"], exp_action)
            action_performance[key]["scenarios"].add(sid)
            action_performance[key]["source"].add(sd["source"])

            for model, performed in sd["model_performed"].items():
                action_performance[key]["models_total"].add(model)
                if exp_action in performed:
                    action_performance[key]["models_performed"].add(model)

    # Classify
    never = []
    sometimes = []
    always = []

    for (graph_id, action), data in action_performance.items():
        n_total = len(data["models_total"])
        n_performed = len(data["models_performed"])

        if n_total == 0:
            continue

        entry = {
            "graph_id": graph_id,
            "action": action,
            "n_models_performed": n_performed,
            "n_models_total": n_total,
            "perform_rate": n_performed / n_total,
            "n_scenarios": len(data["scenarios"]),
            "source": list(data["source"]),
        }

        if n_performed == 0:
            never.append(entry)
        elif n_performed == n_total:
            always.append(entry)
        else:
            sometimes.append(entry)

    return never, sometimes, always


def compute_omission_attribution(episodes):
    """OMISSION violation을 원인별로 분류:
    1. engine-only REQUIRED (manual에 없는 constraint)
    2. shared REQUIRED (manual에도 있는 constraint)
    3. graph별 기여도
    """
    omission_by_scenario = defaultdict(
        lambda: {
            "total_omissions": 0,
            "actions_missed": Counter(),
            "graph_id": "",
            "source": "",
        }
    )

    for ep in episodes:
        sid = ep.get("scenario_id", "")
        graph_id = ep.get("graph_id", ep.get("cpg_graph", ""))

        violations = ep.get("violation_events", [])
        if not violations:
            continue

        for v in violations:
            if not isinstance(v, dict):
                continue
            vtype = v.get("violation_type", v.get("type", "")).upper()
            if "OMISSION" in vtype or "MUST" in vtype or "REQUIRED" in vtype:
                action = v.get("action", v.get("constraint_action", v.get("expected_action", "unknown")))
                omission_by_scenario[sid]["total_omissions"] += 1
                omission_by_scenario[sid]["actions_missed"][action] += 1
                omission_by_scenario[sid]["graph_id"] = graph_id
                if (
                    "auto" in sid.lower()
                    or sid.startswith("gen_")
                    or sid.startswith("combo_")
                    or sid.startswith("pathway_")
                    or sid.startswith("val_")
                ):
                    omission_by_scenario[sid]["source"] = "auto"
                else:
                    omission_by_scenario[sid]["source"] = "manual"

    return omission_by_scenario


def generate_report(
    type_counts,
    type_by_model,
    type_by_graph,
    type_by_source,
    never,
    sometimes,
    always,
    omission_by_scenario,
    output_dir,
):
    """종합 보고서 생성"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("=" * 80)
    lines.append("OMISSION SURGE 진단 보고서")
    lines.append("=" * 80)

    # 1. 전체 violation type 분포
    lines.append("\n## 1. Violation Type 분포 (전체)")
    total = sum(type_counts.values())
    for vtype, count in type_counts.most_common():
        pct = count / total * 100 if total > 0 else 0
        lines.append(f"  {vtype:15s}: {count:6d} ({pct:5.1f}%)")
    lines.append(f"  {'TOTAL':15s}: {total:6d}")

    # OMISSION ratio
    omission_count = type_counts.get("OMISSION", 0)
    non_omission = total - omission_count
    if non_omission > 0:
        lines.append(f"\n  OMISSION / non-OMISSION ratio: {omission_count / non_omission:.1f}x")
    lines.append(f"  OMISSION %: {omission_count / total * 100:.1f}%" if total > 0 else "  No violations")

    # 2. Manual vs Auto
    lines.append("\n## 2. Manual vs Auto 시나리오 Violation 비교")
    for source in ["manual", "auto"]:
        lines.append(f"\n  [{source.upper()}]")
        src_total = sum(type_by_source[source].values())
        for vtype, count in type_by_source[source].most_common():
            pct = count / src_total * 100 if src_total > 0 else 0
            lines.append(f"    {vtype:15s}: {count:6d} ({pct:5.1f}%)")

    # 핵심 비교
    manual_omission = type_by_source["manual"].get("OMISSION", 0)
    auto_omission = type_by_source["auto"].get("OMISSION", 0)
    manual_total_viols = sum(type_by_source["manual"].values())
    auto_total_viols = sum(type_by_source["auto"].values())

    lines.append("\n  ⚠️ OMISSION 비율 비교:")
    lines.append(
        f"    Manual: {manual_omission}/{manual_total_viols} = {manual_omission / manual_total_viols * 100:.1f}%"
        if manual_total_viols > 0
        else "    Manual: N/A"
    )
    lines.append(
        f"    Auto:   {auto_omission}/{auto_total_viols} = {auto_omission / auto_total_viols * 100:.1f}%"
        if auto_total_viols > 0
        else "    Auto: N/A"
    )
    if manual_omission > 0:
        lines.append(
            f"    Auto/Manual OMISSION ratio: {auto_omission / manual_omission:.1f}x" if manual_omission > 0 else ""
        )

    # 3. Graph별 OMISSION 기여도
    lines.append("\n## 3. Graph별 OMISSION 기여도 (Top 10)")
    graph_omission = [(gid, counts.get("OMISSION", 0)) for gid, counts in type_by_graph.items()]
    graph_omission.sort(key=lambda x: -x[1])
    total_omission = sum(c for _, c in graph_omission)
    cumulative = 0
    for i, (gid, count) in enumerate(graph_omission[:15]):
        cumulative += count
        pct = count / total_omission * 100 if total_omission > 0 else 0
        cum_pct = cumulative / total_omission * 100 if total_omission > 0 else 0
        lines.append(f"  {i + 1:2d}. {gid:40s}: {count:5d} ({pct:5.1f}%, cumul {cum_pct:5.1f}%)")

    # 4. Structural Precision
    lines.append("\n## 4. Structural Precision (clinician 없이 추정)")
    lines.append("  REQUIRED actions 분류:")
    lines.append(f"    Never performed (어떤 모델도 수행 안함):  {len(never):4d}")
    lines.append(f"    Sometimes performed (일부 모델만 수행):   {len(sometimes):4d}")
    lines.append(f"    Always performed (모든 모델이 수행):      {len(always):4d}")

    total_req = len(never) + len(sometimes) + len(always)
    if total_req > 0:
        lines.append(f"    Total unique (graph, action) pairs:      {total_req:4d}")
        structural_precision = (len(sometimes) + len(always)) / total_req
        lines.append(f"\n  ⚠️ Structural Precision 추정: {structural_precision:.3f}")
        lines.append("     (= 적어도 하나의 모델이 수행한 action 비율)")
        lines.append("     이 값이 0.217보다 높으면 engine precision이 과소평가된 것")

    # 5. Never-performed 상세 (가장 위험)
    lines.append("\n## 5. ⚠️ NEVER-PERFORMED REQUIRED Actions (Over-Specification 후보)")
    lines.append("   이 action들은 어떤 모델도 어떤 episode에서도 수행하지 않음.")
    lines.append("   → Clinician에게 이것들만 우선 검증 요청 가능")
    never_by_graph = defaultdict(list)
    for entry in never:
        never_by_graph[entry["graph_id"]].append(entry)

    for gid, entries in sorted(never_by_graph.items(), key=lambda x: -len(x[1])):
        lines.append(f"\n  [{gid}] ({len(entries)} never-performed actions)")
        for entry in sorted(entries, key=lambda x: -x["n_scenarios"]):
            lines.append(
                f"    - {entry['action']:50s} (in {entry['n_scenarios']} scenarios, source: {entry['source']})"
            )

    # 6. Model별 violation 패턴
    lines.append("\n## 6. Model별 OMISSION 패턴")
    for model, counts in sorted(type_by_model.items()):
        omit = counts.get("OMISSION", 0)
        total_v = sum(counts.values())
        pct = omit / total_v * 100 if total_v > 0 else 0
        lines.append(f"  {model:20s}: OMISSION {omit:5d}/{total_v:5d} ({pct:5.1f}%)")

    # 7. 행동 가이드
    lines.append("\n## 7. 권장 조치")
    lines.append("=" * 60)

    if len(never) > 0:
        lines.append(f"\n  🔴 CRITICAL: {len(never)} REQUIRED actions가 모든 모델에서 미수행")
        lines.append("     → 이 중 다수가 invalid constraint일 가능성 높음")
        lines.append("     → Clinician에게 이 리스트만 보내서 valid/invalid 판정 받기")
        lines.append("     → Invalid로 판정된 것은 graph YAML에서 soft로 변경 or 삭제")

    # auto-only never-performed
    auto_never = [n for n in never if "auto" in n["source"]]
    manual_never = [n for n in never if "manual" in n["source"]]
    lines.append(f"\n  Never-performed 중 Auto-only: {len(auto_never)}")
    lines.append(f"  Never-performed 중 Manual에도 있음: {len(manual_never)}")
    if len(auto_never) > len(manual_never) * 3:
        lines.append("  ⚠️ Auto-only never-performed가 3배 이상 → Engine over-specification 확인")

    # Graph concentration
    if graph_omission:
        top3_pct = sum(c for _, c in graph_omission[:3]) / total_omission * 100 if total_omission > 0 else 0
        if top3_pct > 50:
            top3_names = [gid for gid, _ in graph_omission[:3]]
            lines.append(f"\n  ⚠️ Top 3 graphs가 OMISSION의 {top3_pct:.0f}% 차지:")
            for name in top3_names:
                lines.append(f"     - {name}")
            lines.append("     → 이 graph들의 constraint 적정성 우선 검토")

    report_text = "\n".join(lines)

    # Save report
    report_path = output_dir / "omission_surge_diagnosis.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"\n[SAVED] {report_path}")

    # Save never-performed as CSV (clinician에게 보낼 수 있도록)
    csv_path = output_dir / "never_performed_required_actions.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["graph_id", "action", "n_scenarios", "source", "n_models_total", "clinician_valid"]
        )
        writer.writeheader()
        for entry in sorted(never, key=lambda x: (-x["n_scenarios"], x["graph_id"])):
            writer.writerow(
                {
                    "graph_id": entry["graph_id"],
                    "action": entry["action"],
                    "n_scenarios": entry["n_scenarios"],
                    "source": ", ".join(entry["source"]),
                    "n_models_total": entry["n_models_total"],
                    "clinician_valid": "",  # clinician이 채울 칸
                }
            )
    print(f"[SAVED] {csv_path}")

    # Save per-graph violation summary
    graph_summary_path = output_dir / "per_graph_violation_summary.json"
    summary = {}
    for gid, counts in type_by_graph.items():
        summary[gid] = dict(counts)
    with open(graph_summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[SAVED] {graph_summary_path}")

    print(report_text)
    return report_text


def main():
    parser = argparse.ArgumentParser(description="OMISSION Surge Diagnosis")
    parser.add_argument("--episodes-dir", default="results/full_706_final", help="Episode results directory")
    parser.add_argument("--graphs-dir", default="cpg_model/graphs", help="CPG graph YAML directory")
    parser.add_argument("--scenarios-dir", default="configs/scenarios", help="Scenario YAML directory")
    parser.add_argument(
        "--auto-scenarios",
        default="configs/scenarios/auto_generated_scenarios.yaml",
        help="Auto-generated scenarios YAML",
    )
    parser.add_argument("--output-dir", default="evidence_pack/omission_audit", help="Output directory")
    args = parser.parse_args()

    print("=" * 60)
    print("OMISSION SURGE 진단 시작")
    print("=" * 60)

    # Load data
    episodes = load_episodes(args.episodes_dir)
    graphs = load_graphs(args.graphs_dir)

    if not episodes:
        print("[ERROR] No episodes found. Check --episodes-dir path.")
        sys.exit(1)

    # Analysis 1: Violation type distribution
    print("\n[STEP 1] Violation type 분포 분석...")
    type_counts, type_by_model, type_by_graph, type_by_source = analyze_violation_by_type(episodes)

    # Analysis 2: Required constraint feasibility
    print("[STEP 2] REQUIRED constraint feasibility 분석...")
    scenario_data = analyze_required_constraint_feasibility(episodes)

    # Analysis 3: Structural precision
    print("[STEP 3] Structural precision 추정...")
    never, sometimes, always = compute_structural_precision(scenario_data)

    # Analysis 4: Omission attribution
    print("[STEP 4] OMISSION attribution 분석...")
    omission_by_scenario = compute_omission_attribution(episodes)

    # Generate report
    print("[STEP 5] 보고서 생성...")
    generate_report(
        type_counts,
        type_by_model,
        type_by_graph,
        type_by_source,
        never,
        sometimes,
        always,
        omission_by_scenario,
        args.output_dir,
    )

    print("\n" + "=" * 60)
    print("진단 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
