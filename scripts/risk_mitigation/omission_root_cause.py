#!/usr/bin/env python3
"""OMISSION Root Cause Analysis (v2)
===================================
Action_effects에 mandatory는 모두 존재함이 확인됨.
그렇다면 왜 OMISSION이 50.5%인가? 세 가지 가설을 검증:

H1: Engine Over-Specification
   → conditional rule이 mandatory를 과다 생성
   → 방법: manual vs engine-derived constraint별 OMISSION rate 비교
   → manual에서도 높으면 H1 기각

H2: Action Normalizer Gap  
   → 모델이 action을 시도했는데 normalizer가 인식 못함
   → 방법: deviation actions 중 expected action과 유사한 것 탐지
   → deviation이 expected와 high-similarity면 H2 확인

H3: Precondition Chain Block
   → action_effects에 있지만 precondition이 시뮬레이션에서 충족 불가
   → 방법: 해당 action의 perform_rate가 0%이고 precondition 조건 확인

추가 분석:
   - OMISSION이 집중되는 specific actions 상위 20개
   - Graph/domain별 OMISSION concentration
   - Model-specific vs universal OMISSION (모든 모델이 실패 vs 일부만)

Usage:
    python omission_root_cause_v2.py \
        --episodes-dir results/full_706_final \
        --graphs-dir cpg_model/graphs \
        --action-effects cpg_model/action_effects.yaml \
        [--output-dir evidence_pack/omission_root_cause]
"""

import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher, get_close_matches
import json
from pathlib import Path
import statistics

import yaml


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
                episodes.append(ep)
            except:
                pass
    return episodes


def load_action_effects_keys(path):
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return {k.lower().strip() for k in data.keys()}
        elif isinstance(data, list):
            return {e.get("action", "").lower().strip() for e in data if isinstance(e, dict)}
    except:
        pass
    return set()


def _derive_graph_id(scenario_id: str) -> str:
    """Derive graph_id from scenario_id prefix (e.g., 'aabb_t_basic_...' -> 'aabb_t')."""
    # Known graph prefixes (2-part like aabb_t, aba_bu, aha_cp, etc.)
    parts = scenario_id.split("_")
    # Try 2-part prefix first (covers aabb_t, aba_bu, aha_cp, etc.)
    if len(parts) >= 3 and f"{parts[0]}_{parts[1]}" in _GRAPH_PREFIXES:
        return f"{parts[0]}_{parts[1]}"
    # Single-part prefix (aki, asthma, acls, dka, af, copd, anaph, cap, adhf, ckd, contrast)
    if parts[0] in _GRAPH_PREFIXES:
        return parts[0]
    # Fallback: first two parts
    return "_".join(parts[:2]) if len(parts) >= 2 else scenario_id


# Known graph prefixes derived from scenario naming convention
_GRAPH_PREFIXES = {
    "aabb_t",
    "aba_bu",
    "aha_cp",
    "aha_hf",
    "aha_st",
    "aki",
    "asthma",
    "acls",
    "dka",
    "af",
    "copd",
    "anaph",
    "cap",
    "caki",
    "apa",
    "acog",
    "adhf",
    "ckd",
    "contrast",
}

# Auto-derived scenario markers (within scenario_id, not prefix)
_AUTO_MARKERS = {"_combo_", "_pathway_", "_trap_", "_single_trigger_", "_value_", "_time_sin_", "_combinatorial_"}


def extract_episode_data(ep):
    """에피소드에서 필요한 데이터 추출"""
    # Performed actions
    performed = set()
    performed_raw = []
    actions = ep.get("actions", [])
    if isinstance(actions, list):
        for a in actions:
            if isinstance(a, dict):
                name = a.get("action_id", a.get("action", a.get("name", ""))).lower().strip()
                raw = a.get("raw_action", a.get("raw", name))
                if name:
                    performed.add(name)
                    performed_raw.append({"normalized": name, "raw": raw})
            elif isinstance(a, str):
                performed.add(a.lower().strip())
                performed_raw.append({"normalized": a.lower().strip(), "raw": a})

    # Expected/mandatory actions
    expected = set()
    exp_list = ep.get("expected_actions", ep.get("mandatory_actions", []))
    if isinstance(exp_list, list):
        for a in exp_list:
            if isinstance(a, dict):
                name = a.get("action", a.get("name", "")).lower().strip()
            elif isinstance(a, str):
                name = a.lower().strip()
            else:
                continue
            if name:
                expected.add(name)

    # Violations
    violations = ep.get("violation_events", [])
    omissions = []
    deviations = []
    if isinstance(violations, list):
        for v in violations:
            if not isinstance(v, dict):
                continue
            vtype = v.get("violation_type", v.get("type", "")).upper()
            if "OMISSION" in vtype or "MUST" in vtype or "REQUIRED" in vtype:
                action = v.get("expected_action", v.get("action_involved", v.get("action", "unknown")))
                omissions.append(action.lower().strip() if isinstance(action, str) else str(action))
            elif "DEVIATION" in vtype:
                action = v.get("action_involved", v.get("action", v.get("raw_action", "unknown")))
                deviations.append(action.lower().strip() if isinstance(action, str) else str(action))

    return {
        "performed": performed,
        "performed_raw": performed_raw,
        "expected": expected,
        "omissions": omissions,
        "deviations": deviations,
        "model": ep.get("_model", "unknown"),
        "scenario_id": ep.get("scenario_id", ""),
        "graph_id": ep.get("graph_id", ep.get("cpg_graph", "")) or _derive_graph_id(ep.get("scenario_id", "")),
        "compliance_score": ep.get("compliance_score", 0),
    }


# ═══════════════════════════════════════════════════════════════════════
# HYPOTHESIS 1: Engine Over-Specification
# ═══════════════════════════════════════════════════════════════════════


def test_h1_over_specification(episodes_data):
    """Manual vs auto scenario에서 OMISSION rate 비교.
    Auto에서만 높으면 engine over-specification.
    둘 다 비슷하면 모델 능력 문제.
    """
    manual_episodes = 0
    manual_omissions = 0
    manual_expected = 0
    auto_episodes = 0
    auto_omissions = 0
    auto_expected = 0

    for ed in episodes_data:
        sid = ed["scenario_id"]
        # Heuristic: auto-derived scenarios contain these markers within the ID
        is_auto = any(marker in sid for marker in _AUTO_MARKERS)

        n_omissions = len(ed["omissions"])
        n_expected = len(ed["expected"])

        if is_auto:
            auto_episodes += 1
            auto_omissions += n_omissions
            auto_expected += n_expected
        else:
            manual_episodes += 1
            manual_omissions += n_omissions
            manual_expected += n_expected

    return {
        "manual": {
            "episodes": manual_episodes,
            "total_omissions": manual_omissions,
            "total_expected": manual_expected,
            "omission_rate": manual_omissions / manual_expected if manual_expected > 0 else 0,
            "omissions_per_episode": manual_omissions / manual_episodes if manual_episodes > 0 else 0,
        },
        "auto": {
            "episodes": auto_episodes,
            "total_omissions": auto_omissions,
            "total_expected": auto_expected,
            "omission_rate": auto_omissions / auto_expected if auto_expected > 0 else 0,
            "omissions_per_episode": auto_omissions / auto_episodes if auto_episodes > 0 else 0,
        },
        "ratio": (auto_omissions / auto_expected) / (manual_omissions / manual_expected)
        if manual_expected > 0 and manual_omissions > 0 and auto_expected > 0
        else None,
    }


# ═══════════════════════════════════════════════════════════════════════
# HYPOTHESIS 2: Action Normalizer Gap
# ═══════════════════════════════════════════════════════════════════════


def test_h2_normalizer_gap(episodes_data):
    """Deviation actions 중 expected action과 유사한 것 탐지.
    similarity > 0.7이면 normalizer가 놓친 것.
    """
    normalizer_misses = []
    total_deviations = 0
    total_omissions = 0

    for ed in episodes_data:
        total_deviations += len(ed["deviations"])
        total_omissions += len(ed["omissions"])

        for dev_action in ed["deviations"]:
            # Check if this deviation is similar to any expected action
            for exp_action in ed["expected"]:
                if exp_action in ed["performed"]:
                    continue  # Already matched, not relevant
                sim = SequenceMatcher(None, dev_action, exp_action).ratio()
                if sim >= 0.6:
                    normalizer_misses.append(
                        {
                            "deviation": dev_action,
                            "expected": exp_action,
                            "similarity": round(sim, 3),
                            "model": ed["model"],
                            "scenario_id": ed["scenario_id"],
                        }
                    )

    # Deduplicate by (deviation, expected) pair
    unique_pairs = {}
    for miss in normalizer_misses:
        key = (miss["deviation"], miss["expected"])
        if key not in unique_pairs or miss["similarity"] > unique_pairs[key]["similarity"]:
            unique_pairs[key] = miss

    return {
        "total_deviations": total_deviations,
        "total_omissions": total_omissions,
        "normalizer_misses": len(unique_pairs),
        "top_misses": sorted(unique_pairs.values(), key=lambda x: -x["similarity"])[:30],
        "miss_rate": len(unique_pairs) / total_deviations if total_deviations > 0 else 0,
    }


# ═══════════════════════════════════════════════════════════════════════
# HYPOTHESIS 3: Universal vs Model-Specific OMISSION
# ═══════════════════════════════════════════════════════════════════════


def test_h3_universality(episodes_data):
    """각 (scenario, expected_action) 조합에서:
    - 모든 모델이 실패 = universal → constraint 문제 or precondition block
    - 일부 모델만 실패 = model-specific → 모델 능력 차이 (정상)
    """
    # (scenario, action) → {model: performed?}
    action_performance = defaultdict(lambda: defaultdict(bool))
    action_scenarios = defaultdict(set)

    for ed in episodes_data:
        sid = ed["scenario_id"]
        model = ed["model"]

        for exp_action in ed["expected"]:
            key = (sid, exp_action)
            if exp_action in ed["performed"]:
                action_performance[key][model] = True
            else:
                action_performance[key][model] = False
            action_scenarios[exp_action].add(sid)

    universal_fail = []  # All models fail
    partial_fail = []  # Some models fail
    universal_pass = []  # All models pass

    for (sid, action), model_results in action_performance.items():
        n_models = len(model_results)
        n_pass = sum(1 for v in model_results.values() if v)

        if n_pass == 0:
            universal_fail.append({"scenario": sid, "action": action, "n_models": n_models})
        elif n_pass == n_models:
            universal_pass.append({"scenario": sid, "action": action, "n_models": n_models})
        else:
            partial_fail.append(
                {
                    "scenario": sid,
                    "action": action,
                    "n_pass": n_pass,
                    "n_models": n_models,
                    "pass_rate": n_pass / n_models,
                }
            )

    # Aggregate by action
    universal_fail_actions = Counter(uf["action"] for uf in universal_fail)
    partial_fail_actions = Counter(pf["action"] for pf in partial_fail)

    return {
        "universal_fail": len(universal_fail),
        "partial_fail": len(partial_fail),
        "universal_pass": len(universal_pass),
        "total": len(universal_fail) + len(partial_fail) + len(universal_pass),
        "universal_fail_rate": len(universal_fail) / (len(universal_fail) + len(partial_fail) + len(universal_pass))
        if (len(universal_fail) + len(partial_fail) + len(universal_pass)) > 0
        else 0,
        "top_universal_fail_actions": universal_fail_actions.most_common(20),
        "top_partial_fail_actions": partial_fail_actions.most_common(20),
    }


# ═══════════════════════════════════════════════════════════════════════
# TOP OMITTED ACTIONS ANALYSIS
# ═══════════════════════════════════════════════════════════════════════


def analyze_top_omissions(episodes_data, ae_keys):
    """가장 자주 OMISSION되는 action 상위 분석"""
    omission_counts = Counter()
    omission_by_graph = defaultdict(Counter)
    omission_by_model = defaultdict(Counter)

    for ed in episodes_data:
        for action in ed["omissions"]:
            omission_counts[action] += 1
            omission_by_graph[ed["graph_id"]][action] += 1
            omission_by_model[ed["model"]][action] += 1

    # For top omissions, check if in action_effects
    top_omissions = []
    for action, count in omission_counts.most_common(30):
        in_ae = action in ae_keys
        # Find close match if not exact
        close = get_close_matches(action, list(ae_keys), n=1, cutoff=0.7) if not in_ae else []
        top_omissions.append(
            {
                "action": action,
                "count": count,
                "in_action_effects": in_ae,
                "closest_match": close[0] if close else None,
                "top_graphs": [
                    (gid, omission_by_graph[gid].get(action, 0))
                    for gid in sorted(omission_by_graph.keys(), key=lambda g: -omission_by_graph[g].get(action, 0))[:3]
                ],
            }
        )

    # Graph concentration
    graph_total = Counter()
    for gid, counts in omission_by_graph.items():
        graph_total[gid] = sum(counts.values())

    return {
        "top_omissions": top_omissions,
        "graph_concentration": graph_total.most_common(15),
        "total_omissions": sum(omission_counts.values()),
    }


# ═══════════════════════════════════════════════════════════════════════
# EXPECTED ACTION COUNT ANALYSIS
# ═══════════════════════════════════════════════════════════════════════


def analyze_expected_distribution(episodes_data):
    """에피소드당 expected action 수 분포.
    너무 많으면 → engine이 과다 지정한 것.
    """
    expected_counts = []
    performed_counts = []
    omission_counts = []

    for ed in episodes_data:
        expected_counts.append(len(ed["expected"]))
        performed_counts.append(len(ed["performed"]))
        omission_counts.append(len(ed["omissions"]))

    coverage_rates = []
    for ed in episodes_data:
        if len(ed["expected"]) > 0:
            coverage = len(ed["performed"] & ed["expected"]) / len(ed["expected"])
            coverage_rates.append(coverage)

    return {
        "expected": {
            "mean": round(statistics.mean(expected_counts), 1) if expected_counts else 0,
            "median": round(statistics.median(expected_counts), 1) if expected_counts else 0,
            "max": max(expected_counts) if expected_counts else 0,
            "min": min(expected_counts) if expected_counts else 0,
        },
        "performed": {
            "mean": round(statistics.mean(performed_counts), 1) if performed_counts else 0,
            "median": round(statistics.median(performed_counts), 1) if performed_counts else 0,
        },
        "omissions_per_episode": {
            "mean": round(statistics.mean(omission_counts), 1) if omission_counts else 0,
            "median": round(statistics.median(omission_counts), 1) if omission_counts else 0,
        },
        "coverage_rate": {
            "mean": round(statistics.mean(coverage_rates), 3) if coverage_rates else 0,
            "median": round(statistics.median(coverage_rates), 3) if coverage_rates else 0,
        },
        "gap": round(statistics.mean(expected_counts) - statistics.mean(performed_counts), 1)
        if expected_counts and performed_counts
        else 0,
    }


def generate_report(h1, h2, h3, top_omissions, expected_dist, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("=" * 80)
    lines.append("OMISSION ROOT CAUSE ANALYSIS v2")
    lines.append("전제: mandatory actions는 모두 action_effects에 존재함")
    lines.append("=" * 80)

    # H1: Over-specification
    lines.append("\n## H1: Engine Over-Specification 검증")
    lines.append(f"  Manual scenarios: {h1['manual']['episodes']} episodes")
    lines.append(f"    OMISSION rate: {h1['manual']['omission_rate']:.3f}")
    lines.append(f"    Omissions/episode: {h1['manual']['omissions_per_episode']:.1f}")
    lines.append(f"  Auto scenarios: {h1['auto']['episodes']} episodes")
    lines.append(f"    OMISSION rate: {h1['auto']['omission_rate']:.3f}")
    lines.append(f"    Omissions/episode: {h1['auto']['omissions_per_episode']:.1f}")
    if h1["ratio"] is not None:
        lines.append(f"  Auto/Manual OMISSION rate ratio: {h1['ratio']:.2f}x")
        if h1["ratio"] > 2.0:
            lines.append(f"  ⚠️ Auto가 {h1['ratio']:.1f}x 높음 → Engine over-specification 가능성 높음")
        elif h1["ratio"] > 1.2:
            lines.append("  🟡 Auto가 약간 높음 → 부분적 over-specification")
        else:
            lines.append("  ✅ 비슷함 → Over-specification이 아닌 모델 능력 문제")

    # H2: Normalizer gap
    lines.append("\n## H2: Action Normalizer Gap 검증")
    lines.append(f"  Total deviations: {h2['total_deviations']}")
    lines.append(f"  Total omissions: {h2['total_omissions']}")
    lines.append(f"  Deviation-OMISSION overlaps (sim >= 0.6): {h2['normalizer_misses']}")
    if h2["normalizer_misses"] > 0:
        lines.append(f"  ⚠️ {h2['normalizer_misses']}개 deviation이 expected action과 유사")
        lines.append("     → Normalizer가 이들을 인식했으면 OMISSION이 감소했을 것")
        lines.append("\n  Top misses:")
        for miss in h2["top_misses"][:15]:
            lines.append(
                f"    '{miss['deviation']}' ≈ '{miss['expected']}' (sim={miss['similarity']}) [{miss['model']}]"
            )
    else:
        lines.append("  ✅ Normalizer gap 없음")

    # H3: Universal vs model-specific
    lines.append("\n## H3: Universal vs Model-Specific OMISSION")
    total_h3 = h3["total"]
    lines.append(
        f"  Universal fail (모든 모델 실패): {h3['universal_fail']} ({h3['universal_fail'] / total_h3 * 100:.1f}%)"
        if total_h3 > 0
        else "  N/A"
    )
    lines.append(f"  Partial fail (일부만 실패):     {h3['partial_fail']}")
    lines.append(f"  Universal pass (모든 모델 성공): {h3['universal_pass']}")

    if h3["universal_fail_rate"] > 0.5:
        lines.append(f"  🔴 Universal fail이 {h3['universal_fail_rate'] * 100:.0f}%")
        lines.append("     → Constraint 자체가 비현실적이거나 precondition block")
    elif h3["universal_fail_rate"] > 0.2:
        lines.append(f"  🟡 Universal fail이 {h3['universal_fail_rate'] * 100:.0f}%")
        lines.append("     → 일부 constraint가 문제이나 대부분은 모델 능력 차이")
    else:
        lines.append(f"  ✅ Universal fail이 {h3['universal_fail_rate'] * 100:.0f}%로 낮음")
        lines.append("     → 대부분 모델 능력 차이. Constraint는 적절함")

    if h3["top_universal_fail_actions"]:
        lines.append("\n  Top universal-fail actions (모든 모델이 실패하는 action):")
        for action, count in h3["top_universal_fail_actions"][:15]:
            lines.append(f"    {action:50s}: {count:4d} scenarios")

    # Expected distribution
    lines.append("\n## Expected Action 분포 분석")
    ed = expected_dist
    lines.append(
        f"  Expected per episode: mean={ed['expected']['mean']}, median={ed['expected']['median']}, max={ed['expected']['max']}"
    )
    lines.append(f"  Performed per episode: mean={ed['performed']['mean']}, median={ed['performed']['median']}")
    lines.append(f"  Gap (expected - performed): {ed['gap']}")
    lines.append(f"  Coverage rate: mean={ed['coverage_rate']['mean']:.1%}, median={ed['coverage_rate']['median']:.1%}")

    if ed["expected"]["mean"] > 30:
        lines.append(f"  ⚠️ 평균 expected={ed['expected']['mean']} — 에피소드당 요구 action이 매우 많음")
    if ed["gap"] > 10:
        lines.append(f"  ⚠️ Gap={ed['gap']} — 모델이 expected의 상당 부분을 놓침")

    # Top omitted actions
    lines.append("\n## Top Omitted Actions (상위 20)")
    for item in top_omissions["top_omissions"][:20]:
        ae_marker = "✅" if item["in_action_effects"] else "❌"
        close_marker = f" → {item['closest_match']}" if item["closest_match"] else ""
        graphs = ", ".join(g for g, c in item["top_graphs"])
        lines.append(f"  {ae_marker} {item['action']:45s}: {item['count']:5d}  [{graphs}]{close_marker}")

    # Graph concentration
    lines.append("\n## OMISSION Graph 집중도")
    total_omissions = top_omissions["total_omissions"]
    cumul = 0
    for gid, count in top_omissions["graph_concentration"][:10]:
        cumul += count
        pct = count / total_omissions * 100 if total_omissions > 0 else 0
        cum_pct = cumul / total_omissions * 100 if total_omissions > 0 else 0
        lines.append(f"  {gid:40s}: {count:5d} ({pct:5.1f}%, cumul {cum_pct:5.1f}%)")

    # Diagnosis
    lines.append(f"\n{'=' * 70}")
    lines.append("## 최종 진단")
    lines.append(f"{'=' * 70}")

    diagnosis = []
    if h1["ratio"] and h1["ratio"] > 2.0:
        diagnosis.append("H1 확인: Engine over-specification이 OMISSION의 주요 원인")
    if h2["normalizer_misses"] > 50:
        diagnosis.append("H2 확인: Normalizer gap이 상당 — action 인식 개선 필요")
    if h3["universal_fail_rate"] > 0.3:
        diagnosis.append("H3 확인: Universal fail이 높음 — constraint 또는 precondition 검토 필요")

    if not diagnosis:
        diagnosis.append("주요 원인: 모델 능력 차이 (constraint는 적절)")

    for d in diagnosis:
        lines.append(f"  ★ {d}")

    lines.append("""
## 권장 조치
  
  H1 확인 시:
    → Engine의 conditional rule 중 over-specification 의심 항목 식별
    → Clinician에게 "이 action이 이 환자에서 mandatory인가?" 확인
    → Invalid → soft 전환
  
  H2 확인 시:
    → top_misses의 deviation-expected 쌍을 normalizer에 alias로 추가
    → cpg_model/action_normalizer.py에 매핑 규칙 추가
  
  H3 확인 시 (universal fail):
    → Top universal-fail actions의 precondition 체인 검토
    → action_effects.yaml에서 해당 action의 precondition이 충족 가능한지 확인
  
  어떤 경우든:
    → 논문 E7에서 OMISSION breakdown 보고 (engine over-spec vs model gap)
    → Clinician validation에서 constraint validity 확인
""")

    report_text = "\n".join(lines)

    report_path = output_dir / "omission_root_cause_v2.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"[SAVED] {report_path}")

    # Save structured results
    results = {
        "h1_over_specification": h1,
        "h2_normalizer_gap": {
            "total_deviations": h2["total_deviations"],
            "normalizer_misses": h2["normalizer_misses"],
            "miss_rate": h2["miss_rate"],
            "top_misses": h2["top_misses"][:20],
        },
        "h3_universality": {
            "universal_fail": h3["universal_fail"],
            "universal_fail_rate": h3["universal_fail_rate"],
            "partial_fail": h3["partial_fail"],
            "universal_pass": h3["universal_pass"],
            "top_universal_fail_actions": h3["top_universal_fail_actions"][:20],
        },
        "expected_distribution": expected_dist,
        "top_omissions": top_omissions["top_omissions"][:20],
        "graph_concentration": top_omissions["graph_concentration"][:10],
    }
    with open(output_dir / "omission_root_cause_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"[SAVED] {output_dir / 'omission_root_cause_results.json'}")

    # Save normalizer fix suggestions if H2
    if h2["top_misses"]:
        with open(output_dir / "normalizer_fix_suggestions.json", "w") as f:
            json.dump(h2["top_misses"], f, indent=2)
        print(f"[SAVED] {output_dir / 'normalizer_fix_suggestions.json'}")

    print(report_text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes-dir", default="results/full_706_v5")
    parser.add_argument("--graphs-dir", default="cpg_model/graphs")
    parser.add_argument("--action-effects", default="assessor_core/action_effects.yaml")
    parser.add_argument("--output-dir", default="evidence_pack/omission_root_cause")
    args = parser.parse_args()

    print("=" * 70)
    print("OMISSION ROOT CAUSE ANALYSIS v2")
    print("=" * 70)

    episodes = load_episodes(args.episodes_dir)
    ae_keys = load_action_effects_keys(args.action_effects)
    print(f"[INFO] {len(episodes)} episodes, {len(ae_keys)} action_effects")

    if not episodes:
        print("[ERROR] No episodes")
        return

    # Extract data
    print("\n[STEP 1] Extracting episode data...")
    episodes_data = [extract_episode_data(ep) for ep in episodes]

    # Test hypotheses
    print("[STEP 2] H1: Engine Over-Specification...")
    h1 = test_h1_over_specification(episodes_data)

    print("[STEP 3] H2: Action Normalizer Gap...")
    h2 = test_h2_normalizer_gap(episodes_data)

    print("[STEP 4] H3: Universal vs Model-Specific...")
    h3 = test_h3_universality(episodes_data)

    print("[STEP 5] Top Omitted Actions...")
    top_omissions = analyze_top_omissions(episodes_data, ae_keys)

    print("[STEP 6] Expected Action Distribution...")
    expected_dist = analyze_expected_distribution(episodes_data)

    print("[STEP 7] Generating report...")
    generate_report(h1, h2, h3, top_omissions, expected_dist, args.output_dir)

    print("\n" + "=" * 70)
    print("분석 완료")
    print("=" * 70)


if __name__ == "__main__":
    main()
