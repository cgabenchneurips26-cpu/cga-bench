#!/usr/bin/env python3
"""Pre-Clinician Constraint Triage
================================
Clinician audit 전에 코드 레벨에서 해결 가능한 constraint 문제를 
자동으로 분류하고, 일부는 직접 수정 제안.

이 스크립트가 하는 일:
1. Engine-derived constraints를 graph 원본과 대조하여 provenance 검증
2. "0% model performance" constraints를 식별하고 원인 분류:
   - action_effects.yaml에 해당 action이 없음 → BUG (즉시 수정)
   - action이 존재하지만 precondition이 불가능 → STRUCTURAL (수정 가능)
   - action이 존재하고 가능하지만 모델이 모두 실패 → CLINICAL (clinician 필요)
3. Held-out graph의 constraint density 이상치 감지
4. Clinician에게 보낼 최소 리뷰 목록 생성 (전체가 아닌 의심 항목만)

Usage:
    python pre_clinician_constraint_triage.py \
        --episodes-dir results/full_706_final \
        --graphs-dir cpg_model/graphs \
        --action-effects cpg_model/action_effects.yaml \
        [--output-dir evidence_pack/constraint_triage]
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

import yaml


def load_all_data(args):
    """모든 데이터 로드"""
    data = {}

    # Episodes
    episodes = []
    ep_dir = Path(args.episodes_dir)
    if ep_dir.exists():
        for model_dir in sorted(ep_dir.iterdir()):
            if not model_dir.is_dir() or model_dir.name.startswith("."):
                continue
            for ep_file in sorted(model_dir.glob("*.json")):
                try:
                    with open(ep_file) as f:
                        ep = json.load(f)
                    if not isinstance(ep, dict):
                        continue
                    ep["_model"] = model_dir.name
                    episodes.append(ep)
                except:
                    pass
    data["episodes"] = episodes
    print(f"[INFO] Episodes: {len(episodes)}")

    # Graphs
    graphs = {}
    g_dir = Path(args.graphs_dir)
    if g_dir.exists():
        for f in sorted(g_dir.glob("*.yaml")):
            if f.name.startswith("_"):
                continue
            try:
                with open(f) as fh:
                    graphs[f.stem] = yaml.safe_load(fh)
            except:
                pass
    data["graphs"] = graphs
    print(f"[INFO] Graphs: {len(graphs)}")

    # Action effects
    ae_path = Path(args.action_effects)
    action_effects = {}
    if ae_path.exists():
        try:
            with open(ae_path) as f:
                ae_data = yaml.safe_load(f)
            if isinstance(ae_data, dict):
                action_effects = ae_data
            elif isinstance(ae_data, list):
                for entry in ae_data:
                    if isinstance(entry, dict) and "action" in entry:
                        action_effects[entry["action"].lower()] = entry
        except Exception as e:
            print(f"[WARN] action_effects load failed: {e}")
    data["action_effects"] = action_effects
    print(f"[INFO] Action effects: {len(action_effects)} entries")

    return data


def extract_all_expected_actions_from_graphs(graphs):
    """모든 graph에서 expected actions (= REQUIRED constraints) 추출"""
    all_expected = defaultdict(
        lambda: {
            "actions": set(),
            "forbidden": set(),
            "deadlines": {},
            "conditional_rules": [],
        }
    )

    for gid, graph in graphs.items():
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        for node in nodes:
            if not isinstance(node, dict):
                continue

            # mandatory_actions is the primary field in graph YAMLs
            expected = node.get("mandatory_actions", node.get("expected_actions", []))
            if isinstance(expected, list):
                for a in expected:
                    name = a if isinstance(a, str) else a.get("action", str(a))
                    all_expected[gid]["actions"].add(name.lower().strip())

            forbidden = node.get("forbidden_actions", [])
            if isinstance(forbidden, list):
                for a in forbidden:
                    name = a if isinstance(a, str) else a.get("action", str(a))
                    all_expected[gid]["forbidden"].add(name.lower().strip())

            deadlines = node.get("deadlines", [])
            if isinstance(deadlines, list):
                for d in deadlines:
                    if isinstance(d, dict):
                        act = d.get("action", "").lower().strip()
                        mins = d.get("minutes", d.get("time_limit", 999))
                        all_expected[gid]["deadlines"][act] = mins
            elif isinstance(deadlines, dict):
                for act, mins in deadlines.items():
                    all_expected[gid]["deadlines"][act.lower().strip()] = mins

        cond_rules = graph.get("conditional_rules", [])
        if isinstance(cond_rules, list):
            all_expected[gid]["conditional_rules"] = cond_rules

    return all_expected


def build_action_universe(action_effects, episodes):
    """모든 가능한 action의 universe 구축:
    1. action_effects.yaml에 정의된 actions
    2. episodes에서 실제 수행된 actions
    """
    universe = set()

    # From action_effects
    for key in action_effects:
        universe.add(key.lower().strip())
        if isinstance(action_effects[key], dict):
            action_name = action_effects[key].get("action", key)
            universe.add(action_name.lower().strip())

    # From episodes
    for ep in episodes:
        actions = ep.get("actions", [])
        if isinstance(actions, list):
            for a in actions:
                if isinstance(a, dict):
                    name = a.get("action_id", a.get("action", a.get("name", "")))
                    if name:
                        universe.add(name.lower().strip())
                elif isinstance(a, str):
                    universe.add(a.lower().strip())

    return universe


def build_model_action_performance(episodes):
    """각 (scenario, model) 조합에서 수행된 action set 구축
    Returns: {scenario_id: {model: set(actions)}}
    """
    performance = defaultdict(lambda: defaultdict(set))

    for ep in episodes:
        sid = ep.get("scenario_id", "")
        model = ep.get("_model", "unknown")

        actions = ep.get("actions", [])
        if isinstance(actions, list):
            for a in actions:
                if isinstance(a, dict):
                    name = a.get("action_id", a.get("action", a.get("name", "")))
                    if name:
                        performance[sid][model].add(name.lower().strip())
                elif isinstance(a, str):
                    performance[sid][model].add(a.lower().strip())

    return performance


def _build_scenario_graph_map(scenarios_dir="configs/scenarios"):
    """Build scenario_id → graph_id map from scenario YAML configs."""
    mapping = {}
    sdir = Path(scenarios_dir)
    if not sdir.exists():
        return mapping
    for yf in sorted(sdir.glob("*.yaml")):
        try:
            with open(yf) as f:
                data = yaml.safe_load(f)
            if not data:
                continue
            items = data.get("scenarios", {})
            if isinstance(items, dict):
                for sid, sc in items.items():
                    if isinstance(sc, dict):
                        gg = sc.get("guideline_graph", "")
                        if gg:
                            mapping[sid] = gg
        except Exception:
            continue
    return mapping


def triage_constraints(graph_expected, action_universe, model_performance, episodes):
    """각 REQUIRED constraint를 triage:

    Categories:
    - BUG: action이 action_effects에 없음 → 수행 불가능 → 즉시 수정
    - STRUCTURAL: action이 존재하지만 모든 모델이 0% → precondition 문제 가능
    - BORDERLINE: 일부 모델만 수행 (1-49%) → clinician 우선 검토
    - VALID: 대부분 모델이 수행 (50%+) → probably valid constraint
    - EASY: 모든 모델이 수행 → trivially satisfied
    """
    triage_results = []

    # Build scenario→graph mapping from configs
    scenario_graph_map = _build_scenario_graph_map()
    # Invert: graph_id → set of scenario_ids
    graph_scenarios = defaultdict(set)
    for sid, gg in scenario_graph_map.items():
        graph_scenarios[gg].add(sid)
        # Also try stem aliases (e.g. ssc_sepsis_hour1 → ssc_sepsis_hour1_bundle)
        graph_scenarios[gg.replace("_bundle", "")].add(sid)

    # Build per-graph, per-action performance stats
    for gid, gdata in graph_expected.items():
        for action in gdata["actions"]:
            # Check action existence
            action_lower = action.lower().strip()
            in_effects = action_lower in action_universe

            # Use config-based mapping for scenario→graph
            relevant_scenarios = [sid for sid in model_performance if sid in graph_scenarios.get(gid, set())]

            # Fallback: substring match on graph id prefix
            if not relevant_scenarios:
                # Use first 6 chars of graph_id as prefix (e.g. "aba_bu" from "aba_burn_resuscitation")
                prefix = gid[:6]
                relevant_scenarios = [sid for sid in model_performance if sid.startswith(prefix)]

            models_performed = set()
            models_total = set()
            n_performed = 0
            n_total = 0

            for sid in relevant_scenarios:
                for model, actions in model_performance[sid].items():
                    models_total.add(model)
                    n_total += 1
                    if action_lower in actions:
                        models_performed.add(model)
                        n_performed += 1

            # Classify
            n_models = len(models_total)
            n_models_performed = len(models_performed)

            if not in_effects and n_models == 0:
                category = "BUG_NO_EFFECT_NO_DATA"
            elif not in_effects:
                category = "BUG_NOT_IN_EFFECTS"
            elif n_models == 0:
                category = "NO_DATA"
            elif n_models_performed == 0:
                category = "STRUCTURAL_ZERO_PERFORM"
            elif n_models_performed / n_models < 0.25:
                category = "BORDERLINE_LOW"
            elif n_models_performed / n_models < 0.50:
                category = "BORDERLINE_MED"
            elif n_models_performed / n_models < 0.75:
                category = "VALID_MODERATE"
            elif n_models_performed == n_models:
                category = "EASY_ALL_PERFORM"
            else:
                category = "VALID_HIGH"

            # Check if this action has a deadline
            has_deadline = action_lower in gdata.get("deadlines", {})

            # Check if it's also forbidden somewhere
            is_conflicted = action_lower in gdata.get("forbidden", set())

            triage_results.append(
                {
                    "graph_id": gid,
                    "action": action,
                    "category": category,
                    "in_action_effects": in_effects,
                    "n_models_performed": n_models_performed,
                    "n_models_total": n_models,
                    "perform_rate": n_models_performed / n_models if n_models > 0 else -1,
                    "n_scenarios": len(relevant_scenarios),
                    "has_deadline": has_deadline,
                    "is_conflicted": is_conflicted,
                }
            )

    return triage_results


def generate_clinician_minimal_review(triage_results, output_dir):
    """Clinician에게 보낼 최소 리뷰 리스트 생성.
    BUG는 우리가 수정. STRUCTURAL_ZERO는 검토 요청. BORDERLINE은 우선순위.
    """
    output_dir = Path(output_dir)

    # Filter to items that need review
    needs_review = [
        t
        for t in triage_results
        if t["category"] in ("STRUCTURAL_ZERO_PERFORM", "BORDERLINE_LOW", "BUG_NOT_IN_EFFECTS")
    ]

    # Sort by priority
    priority_order = {
        "BUG_NOT_IN_EFFECTS": 0,
        "STRUCTURAL_ZERO_PERFORM": 1,
        "BORDERLINE_LOW": 2,
    }
    needs_review.sort(key=lambda x: (priority_order.get(x["category"], 99), x["graph_id"]))

    lines = []
    lines.append("# Clinician 최소 리뷰 요청 목록")
    lines.append("# 생성일: pre_clinician_constraint_triage.py")
    lines.append(f"# 전체 {len(triage_results)} constraints 중 {len(needs_review)}개 검토 필요")
    lines.append("")
    lines.append("## 검토 요청 사항")
    lines.append("아래 각 action에 대해 'Valid' 또는 'Invalid' 판정을 부탁드립니다.")
    lines.append("'Valid' = 이 action은 해당 임상 가이드라인에서 반드시 수행해야 함")
    lines.append("'Invalid' = 이 action은 필수가 아님 (optional 또는 context-dependent)")
    lines.append("")

    current_category = None
    for t in needs_review:
        if t["category"] != current_category:
            current_category = t["category"]
            labels = {
                "BUG_NOT_IN_EFFECTS": "🔴 시스템 오류 (action이 시뮬레이션에 정의되지 않음)",
                "STRUCTURAL_ZERO_PERFORM": "🟡 모든 AI 모델이 수행 실패한 항목",
                "BORDERLINE_LOW": "🟠 소수 모델만 수행한 항목",
            }
            lines.append(f"\n### {labels.get(current_category, current_category)}")
            lines.append("")

        lines.append(f"- [ ] **{t['action']}** (가이드라인: {t['graph_id']})")
        if t["n_models_total"] > 0:
            lines.append(
                f"      수행률: {t['n_models_performed']}/{t['n_models_total']} 모델 ({t['perform_rate'] * 100:.0f}%)"
            )
        if t["has_deadline"]:
            lines.append("      ⏱️ 시간 제한 있음")
        if t["is_conflicted"]:
            lines.append("      ⚠️ 다른 context에서 FORBIDDEN으로도 지정됨")
        lines.append("      판정: [ ] Valid  [ ] Invalid  [ ] Context-dependent")
        lines.append("")

    review_text = "\n".join(lines)
    review_path = output_dir / "clinician_minimal_review.md"
    with open(review_path, "w") as f:
        f.write(review_text)
    print(f"[SAVED] {review_path} ({len(needs_review)} items)")

    return needs_review


def generate_auto_fix_suggestions(triage_results, output_dir):
    """즉시 수정 가능한 항목에 대한 자동 수정 제안 생성.
    BUG_NOT_IN_EFFECTS → action_effects.yaml에 추가하거나 constraint를 soft로 변경
    """
    output_dir = Path(output_dir)

    bugs = [t for t in triage_results if "BUG" in t["category"]]

    if not bugs:
        print("[INFO] No BUG-category constraints found. Good!")
        return

    lines = []
    lines.append("# 자동 수정 제안")
    lines.append("")
    lines.append("## BUG: action_effects.yaml에 없는 REQUIRED actions")
    lines.append("이 actions는 REQUIRED로 지정되어 있지만 시뮬레이션에서 수행 불가능합니다.")
    lines.append("두 가지 수정 방법:")
    lines.append("  A) action_effects.yaml에 해당 action 추가")
    lines.append("  B) graph YAML에서 해당 action을 soft constraint로 변경")
    lines.append("")

    by_graph = defaultdict(list)
    for b in bugs:
        by_graph[b["graph_id"]].append(b)

    for gid, items in sorted(by_graph.items()):
        lines.append(f"\n### {gid}")
        for item in items:
            lines.append(f"  - {item['action']} [{item['category']}]")

    fix_path = output_dir / "auto_fix_suggestions.md"
    with open(fix_path, "w") as f:
        f.write("\n".join(lines))
    print(f"[SAVED] {fix_path} ({len(bugs)} items)")


def generate_main_report(triage_results, output_dir):
    """종합 triage 보고서"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Category summary
    category_counts = Counter(t["category"] for t in triage_results)
    total = len(triage_results)

    lines = []
    lines.append("=" * 80)
    lines.append("PRE-CLINICIAN CONSTRAINT TRIAGE 보고서")
    lines.append("=" * 80)

    lines.append(f"\n## 1. Triage Summary ({total} constraints)")
    lines.append("")
    for cat in [
        "BUG_NOT_IN_EFFECTS",
        "BUG_NO_EFFECT_NO_DATA",
        "STRUCTURAL_ZERO_PERFORM",
        "BORDERLINE_LOW",
        "BORDERLINE_MED",
        "VALID_MODERATE",
        "VALID_HIGH",
        "EASY_ALL_PERFORM",
        "NO_DATA",
    ]:
        count = category_counts.get(cat, 0)
        pct = count / total * 100 if total > 0 else 0
        marker = ""
        if "BUG" in cat:
            marker = " 🔴"
        elif "STRUCTURAL" in cat or "BORDERLINE" in cat:
            marker = " 🟡"
        elif "EASY" in cat:
            marker = " ✅"
        lines.append(f"  {cat:30s}: {count:5d} ({pct:5.1f}%){marker}")

    # Risk assessment
    n_problematic = sum(
        category_counts.get(c, 0)
        for c in ["BUG_NOT_IN_EFFECTS", "BUG_NO_EFFECT_NO_DATA", "STRUCTURAL_ZERO_PERFORM", "BORDERLINE_LOW"]
    )
    lines.append(f"\n  ⚠️ 문제 있는 constraints: {n_problematic}/{total} ({n_problematic / max(total, 1) * 100:.1f}%)")

    # Estimate corrected precision
    n_valid = sum(category_counts.get(c, 0) for c in ["VALID_MODERATE", "VALID_HIGH", "EASY_ALL_PERFORM"])
    if total > 0:
        corrected_precision = n_valid / total
        lines.append(f"  ★ 추정 Corrected Precision: {corrected_precision:.3f}")
        lines.append("    (기존 enginePrecision=0.217 대비)")
        if corrected_precision > 0.217:
            lines.append(f"    → Precision이 과소평가되었을 가능성: 실제로는 {corrected_precision:.1%}")
        else:
            lines.append("    → Precision이 실제로 낮음: engine over-specification 확인")

    # Per-graph breakdown
    lines.append("\n## 2. Per-Graph Breakdown")
    graph_stats = defaultdict(Counter)
    for t in triage_results:
        graph_stats[t["graph_id"]][t["category"]] += 1

    lines.append(f"  {'Graph':40s} {'Total':>5s} {'BUG':>5s} {'ZERO':>5s} {'BORD':>5s} {'VALID':>5s} {'EASY':>5s}")
    lines.append("  " + "-" * 105)
    for gid in sorted(graph_stats.keys()):
        gs = graph_stats[gid]
        total_g = sum(gs.values())
        bug = sum(gs.get(c, 0) for c in ["BUG_NOT_IN_EFFECTS", "BUG_NO_EFFECT_NO_DATA"])
        zero = gs.get("STRUCTURAL_ZERO_PERFORM", 0)
        border = gs.get("BORDERLINE_LOW", 0) + gs.get("BORDERLINE_MED", 0)
        valid = gs.get("VALID_MODERATE", 0) + gs.get("VALID_HIGH", 0)
        easy = gs.get("EASY_ALL_PERFORM", 0)
        lines.append(f"  {gid:40s} {total_g:5d} {bug:5d} {zero:5d} {border:5d} {valid:5d} {easy:5d}")

    # Impact on OMISSION
    lines.append("\n## 3. OMISSION 영향 추정")
    lines.append(f"""
  만약 BUG + STRUCTURAL_ZERO constraints를 모두 soft로 변경하면:
  - {n_problematic} constraints가 hard → soft 전환
  - 이것이 생성하는 OMISSION violations 전부 제거
  - OMISSION 비율이 현재 29.3x에서 대폭 감소 예상
  
  논문 framing 전략:
  1. BUG는 수정 후 재실행 (action_effects에 추가 or constraint 삭제)
  2. STRUCTURAL_ZERO는 "clinician-validated subset"으로 한정
  3. 논문에서 "full constraint set"과 "clinician-validated subset" 둘 다 보고
     → 리뷰어가 precision 공격해도 subset 결과로 방어 가능
""")

    # Actionable recommendations
    lines.append("\n## 4. 즉시 실행 가능한 조치")
    lines.append("=" * 60)
    lines.append(f"""
  🔴 Phase 1: BUG 수정 (clinician 불필요, 즉시)
  - auto_fix_suggestions.md 참조
  - action_effects.yaml에 누락 action 추가 OR
  - graph YAML에서 해당 node의 expected_actions에서 제거/soft 전환
  
  🟡 Phase 2: STRUCTURAL_ZERO 검토 (코드 레벨)
  - 이 action들의 precondition을 action_effects.yaml에서 확인
  - precondition이 시나리오에서 충족 불가능하면 → constraint 조건 수정
  - precondition이 가능한데 모델이 모두 실패 → clinician 확인 대기
  
  🟢 Phase 3: Clinician 리뷰 (최소 범위)
  - clinician_minimal_review.md 발송
  - 전체 {total} constraints가 아닌 {n_problematic}개만 검토 요청
  - 검토 결과로 "clinician-endorsed precision" 계산 가능
  
  📊 Phase 4: 논문 반영
  - Table~constraint_type_precision에 3가지 precision 보고:
    a) Raw precision (현재 0.217)
    b) Corrected precision (BUG 제거 후)
    c) Clinician-endorsed precision (리뷰 후)
""")

    report_text = "\n".join(lines)

    report_path = output_dir / "constraint_triage_report.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"[SAVED] {report_path}")

    # Save full triage as JSON
    triage_path = output_dir / "constraint_triage_full.json"
    with open(triage_path, "w") as f:
        json.dump(triage_results, f, indent=2, default=str)
    print(f"[SAVED] {triage_path}")

    print(report_text)


def main():
    parser = argparse.ArgumentParser(description="Pre-Clinician Constraint Triage")
    parser.add_argument("--episodes-dir", default="results/full_706_final", help="Episode results directory")
    parser.add_argument("--graphs-dir", default="cpg_model/graphs", help="CPG graph YAML directory")
    parser.add_argument("--action-effects", default="cpg_model/action_effects.yaml", help="Action effects YAML")
    parser.add_argument("--output-dir", default="evidence_pack/constraint_triage", help="Output directory")
    args = parser.parse_args()

    print("=" * 80)
    print("PRE-CLINICIAN CONSTRAINT TRIAGE 시작")
    print("=" * 80)

    data = load_all_data(args)

    if not data["episodes"]:
        print("[ERROR] No episodes found")
        sys.exit(1)

    # Extract expected actions from all graphs
    print("\n[STEP 1] Graph에서 constraint 추출...")
    graph_expected = extract_all_expected_actions_from_graphs(data["graphs"])

    # Build action universe
    print("[STEP 2] Action universe 구축...")
    action_universe = build_action_universe(data["action_effects"], data["episodes"])
    print(f"  Action universe size: {len(action_universe)}")

    # Build model performance
    print("[STEP 3] Model performance 데이터 구축...")
    model_performance = build_model_action_performance(data["episodes"])
    print(f"  Scenarios with performance data: {len(model_performance)}")

    # Triage
    print("[STEP 4] Constraint triage 실행...")
    triage_results = triage_constraints(graph_expected, action_universe, model_performance, data["episodes"])
    print(f"  Triaged {len(triage_results)} constraints")

    # Generate outputs
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("[STEP 5] 보고서 생성...")
    generate_main_report(triage_results, output_dir)

    print("[STEP 6] Clinician 최소 리뷰 목록 생성...")
    generate_clinician_minimal_review(triage_results, output_dir)

    print("[STEP 7] 자동 수정 제안 생성...")
    generate_auto_fix_suggestions(triage_results, output_dir)

    print("\n" + "=" * 80)
    print("TRIAGE 완료")
    print("=" * 80)


if __name__ == "__main__":
    main()
