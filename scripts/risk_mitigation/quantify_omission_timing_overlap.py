#!/usr/bin/env python3
"""OMISSION/TIMING Double-Count 버그 정량화
==========================================
수동 검증에서 발견: ViolationExtractor가 deadline을 넘긴 action을
TIMING이 아닌 OMISSION으로 기록하는 버그.

이 스크립트가 하는 일:
1. 모든 OMISSION violation에서 해당 action이 실제 performed에 있는지 확인
2. Performed인 OMISSION = "false OMISSION" (실제로는 TIMING이어야 함)
3. 비율 계산: false OMISSION / total OMISSION
4. TIMING violation과의 중복 여부 확인 (double-count인지)
5. 영향 추정: false OMISSION을 제거하면 OMISSION rate이 얼마나 떨어지는지

Usage:
    python quantify_omission_timing_overlap.py --episodes-dir results/full_706_v5
"""

import argparse
from collections import Counter
import json
from pathlib import Path


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


def get_action(a):
    if isinstance(a, str):
        return a.lower().strip()
    if isinstance(a, dict):
        return a.get("action_id", a.get("action", a.get("name", str(a)))).lower().strip()
    return str(a).lower().strip()


def analyze_episode(ep):
    """단일 에피소드에서 OMISSION/TIMING overlap 분석"""
    # Performed actions
    performed = set()
    for a in ep.get("actions", []):
        n = get_action(a)
        if n:
            performed.add(n)

    # Expected/mandatory
    expected = set()
    for a in ep.get("expected_actions", ep.get("mandatory_actions", [])):
        n = get_action(a)
        if n:
            expected.add(n)

    violations = ep.get("violation_events", [])
    if not isinstance(violations, list):
        return None

    omission_actions = set()
    timing_actions = set()
    results = {
        "total_omissions": 0,
        "omission_but_performed": 0,  # FALSE OMISSION: action was performed
        "omission_and_timing_same": 0,  # DOUBLE COUNT: same action has both
        "omission_performed_no_timing": 0,  # MISCLASS: performed, no timing recorded
        "true_omission": 0,  # REAL: action genuinely not performed
        "total_timing": 0,
        "false_omission_actions": [],
        "double_count_actions": [],
    }

    for v in violations:
        if not isinstance(v, dict):
            continue
        vtype = v.get("violation_type", v.get("type", "")).upper()
        action = v.get("expected_action") or v.get("action_involved") or v.get("action") or ""
        action = action.lower().strip() if isinstance(action, str) else ""

        if "OMISSION" in vtype or ("MUST" in vtype and "COMMISSION" not in vtype):
            omission_actions.add(action)
            results["total_omissions"] += 1

            if action in performed:
                results["omission_but_performed"] += 1
                results["false_omission_actions"].append(action)
            else:
                results["true_omission"] += 1

        elif "TIMING" in vtype or "WITHIN" in vtype:
            timing_actions.add(action)
            results["total_timing"] += 1

    # Check double-count: same action in both OMISSION and TIMING
    overlap = omission_actions & timing_actions
    results["omission_and_timing_same"] = len(overlap)
    results["double_count_actions"] = list(overlap)

    # MISCLASS: in OMISSION + performed, but NOT in TIMING
    for action in results["false_omission_actions"]:
        if action not in timing_actions:
            results["omission_performed_no_timing"] += 1

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes-dir", default="results/full_706_v5")
    parser.add_argument("--output-dir", default="evidence_pack/omission_timing_overlap")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    episodes = load_episodes(args.episodes_dir)
    print(f"Loaded {len(episodes)} episodes\n")

    # Aggregate
    total = {
        "n_episodes": len(episodes),
        "total_omissions": 0,
        "omission_but_performed": 0,
        "omission_and_timing_same": 0,
        "omission_performed_no_timing": 0,
        "true_omission": 0,
        "total_timing": 0,
        "n_episodes_with_false_omission": 0,
        "n_episodes_with_double_count": 0,
    }

    false_omission_actions = Counter()
    double_count_actions = Counter()
    misclass_actions = Counter()  # performed but recorded as OMISSION, no TIMING
    model_false_omission = Counter()

    for ep in episodes:
        result = analyze_episode(ep)
        if result is None:
            continue

        total["total_omissions"] += result["total_omissions"]
        total["omission_but_performed"] += result["omission_but_performed"]
        total["omission_and_timing_same"] += result["omission_and_timing_same"]
        total["omission_performed_no_timing"] += result["omission_performed_no_timing"]
        total["true_omission"] += result["true_omission"]
        total["total_timing"] += result["total_timing"]

        if result["omission_but_performed"] > 0:
            total["n_episodes_with_false_omission"] += 1
            model_false_omission[ep.get("_model", "unknown")] += result["omission_but_performed"]

        if result["omission_and_timing_same"] > 0:
            total["n_episodes_with_double_count"] += 1

        for a in result["false_omission_actions"]:
            false_omission_actions[a] += 1
        for a in result["double_count_actions"]:
            double_count_actions[a] += 1

    # Report
    lines = []
    lines.append("=" * 70)
    lines.append("OMISSION/TIMING OVERLAP 정량화")
    lines.append("=" * 70)

    n_omissions = total["total_omissions"]
    n_false = total["omission_but_performed"]
    n_true = total["true_omission"]
    n_double = total["omission_and_timing_same"]
    n_misclass = total["omission_performed_no_timing"]

    lines.append(f"\n  Total OMISSION violations: {n_omissions}")
    lines.append(f"  Total TIMING violations: {total['total_timing']}")
    lines.append("")
    lines.append(f"  ┌{'─' * 50}┐")
    lines.append("  │ FALSE OMISSION (performed but marked OMISSION)  │")
    lines.append(
        f"  │   Count: {n_false:>6d} / {n_omissions:>6d} = {n_false / n_omissions * 100:.1f}%{' ' * 12}│"
        if n_omissions > 0
        else "  │   N/A │"
    )
    lines.append(
        f"  │   Episodes affected: {total['n_episodes_with_false_omission']:>6d} / {total['n_episodes']:>6d}{' ' * 8}│"
    )
    lines.append(f"  ├{'─' * 50}┤")
    lines.append("  │ DOUBLE COUNT (same action: OMISSION + TIMING)   │")
    lines.append(f"  │   Count: {n_double:>6d}{' ' * 34}│")
    lines.append(f"  │   Episodes: {total['n_episodes_with_double_count']:>6d}{' ' * 31}│")
    lines.append(f"  ├{'─' * 50}┤")
    lines.append("  │ MISCLASS (performed, OMISSION, no TIMING)       │")
    lines.append(f"  │   Count: {n_misclass:>6d}{' ' * 34}│")
    lines.append(f"  │   = Should be TIMING but system missed it{' ' * 7}│")
    lines.append(f"  ├{'─' * 50}┤")
    lines.append("  │ TRUE OMISSION (genuinely not performed)         │")
    lines.append(
        f"  │   Count: {n_true:>6d} / {n_omissions:>6d} = {n_true / n_omissions * 100:.1f}%{' ' * 12}│"
        if n_omissions > 0
        else "  │   N/A │"
    )
    lines.append(f"  └{'─' * 50}┘")

    # Impact
    lines.append("\n  ★ IMPACT:")
    if n_omissions > 0:
        corrected_omission_rate = n_true / (n_true + total["total_timing"] + n_true)
        lines.append(f"    Current OMISSION rate: {n_omissions / (n_omissions + total['total_timing']) * 100:.1f}%")
        lines.append(
            f"    If false OMISSIONs removed: {n_true / (n_true + total['total_timing'] + n_false) * 100:.1f}%"
        )
        lines.append(f"    Reduction: {n_false / n_omissions * 100:.1f}% of OMISSIONs are false")

    # Top false OMISSION actions
    lines.append("\n  Top FALSE OMISSION actions:")
    for action, count in false_omission_actions.most_common(15):
        lines.append(f"    {action:50s}: {count:5d}")

    # Top double-count actions
    if double_count_actions:
        lines.append("\n  Top DOUBLE-COUNT actions:")
        for action, count in double_count_actions.most_common(10):
            lines.append(f"    {action:50s}: {count:5d}")

    # Model breakdown
    lines.append("\n  FALSE OMISSION by model:")
    for model, count in model_false_omission.most_common():
        lines.append(f"    {model:20s}: {count:5d}")

    # Diagnosis
    lines.append(f"\n{'=' * 60}")
    lines.append("진단:")
    if n_false / max(n_omissions, 1) > 0.3:
        lines.append(
            f"  🔴 CRITICAL: {n_false / n_omissions * 100:.0f}%의 OMISSION이 false — ViolationExtractor 버그 확인"
        )
        lines.append("     → 늦게 수행된 action을 OMISSION으로 처리하고 있음")
        lines.append("     → ViolationExtractor에서 'performed but late' 체크 추가 필요")
        lines.append("     → 수정 후 재채점 필요")
    elif n_false / max(n_omissions, 1) > 0.1:
        lines.append(f"  🟡 WARNING: {n_false / n_omissions * 100:.0f}%의 OMISSION이 false — 유의미한 비율")
        lines.append("     → Normalizer matching 문제일 가능성")
    else:
        lines.append(f"  ✅ False OMISSION rate {n_false / n_omissions * 100:.1f}% — 미미한 수준")
    lines.append(f"{'=' * 60}")

    report_text = "\n".join(lines)

    report_path = output_dir / "omission_timing_overlap.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"[SAVED] {report_path}")

    results_path = output_dir / "omission_timing_overlap.json"
    with open(results_path, "w") as f:
        json.dump(
            {
                "totals": total,
                "false_omission_actions": false_omission_actions.most_common(30),
                "double_count_actions": double_count_actions.most_common(20),
                "model_breakdown": dict(model_false_omission),
            },
            f,
            indent=2,
        )
    print(f"[SAVED] {results_path}")

    print(report_text)


if __name__ == "__main__":
    main()
