#!/usr/bin/env python3
"""Raw Episode Inspector
======================
OMISSION이 "모델이 엉뚱한 것을 한다"가 진짜인지 raw 데이터로 확인.

확인할 것:
1. Expected action은 정확히 뭔가?
2. 모델이 실제로 뭘 했나? (raw text 포함)
3. Omitted action은 모델이 시도조차 안 했나, 아니면 시도했는데 매칭 실패인가?
4. "Extra" action은 정말 엉뚱한 건가, 아니면 expected의 변형인가?

Usage:
    python inspect_raw_episodes.py --episodes-dir results/full_706_final [--n 20] [--mode omission]

Modes:
    omission  — OMISSION이 많은 에피소드 샘플
    universal — 모든 모델이 실패하는 (scenario, action) 쌍
    mismatch  — performed와 expected가 유사하지만 매칭 안 된 사례
    random    — 랜덤 샘플
"""

import argparse
from collections import defaultdict
from difflib import SequenceMatcher, get_close_matches
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


def extract_action_name(a):
    """Action object에서 이름 추출"""
    if isinstance(a, str):
        return a
    if isinstance(a, dict):
        return a.get("action_id", a.get("action", a.get("name", a.get("id", str(a)))))
    return str(a)


def inspect_episode(ep, show_raw=True):
    """단일 에피소드 상세 출력"""
    lines = []
    lines.append(f"{'─' * 70}")
    lines.append(f"  File: {ep.get('_file', '?')}")
    lines.append(f"  Model: {ep.get('_model', '?')}")
    lines.append(f"  Scenario: {ep.get('scenario_id', '?')}")
    lines.append(f"  Graph: {ep.get('graph_id', ep.get('cpg_graph', '?'))}")
    lines.append(f"  Compliance: {ep.get('compliance_score', '?')}")
    lines.append(f"  Total LLM calls: {ep.get('total_llm_calls', '?')}")

    # Expected actions
    expected_raw = ep.get("expected_actions", ep.get("mandatory_actions", []))
    expected = set()
    lines.append(f"\n  EXPECTED ({len(expected_raw)}):")
    if isinstance(expected_raw, list):
        for a in expected_raw:
            name = extract_action_name(a)
            expected.add(name.lower().strip())
            lines.append(f"    ✓ {name}")
    else:
        lines.append(f"    (none or unexpected format: {type(expected_raw)})")

    # Performed actions
    actions_raw = ep.get("actions", [])
    performed = set()
    lines.append(f"\n  PERFORMED ({len(actions_raw)}):")
    if isinstance(actions_raw, list):
        for i, a in enumerate(actions_raw):
            name = extract_action_name(a)
            name_lower = name.lower().strip()
            performed.add(name_lower)

            # Check if it matches any expected
            matched = name_lower in expected
            marker = "✅" if matched else "➕"

            # Show raw if available
            raw_text = ""
            if show_raw and isinstance(a, dict):
                raw = a.get("raw_action", a.get("raw", a.get("raw_text", "")))
                if raw and raw != name:
                    raw_text = f'  ← raw: "{raw[:80]}"'

            timestamp = ""
            if isinstance(a, dict) and "timestamp_minutes" in a:
                timestamp = f"  t={a['timestamp_minutes']}m"
            elif isinstance(a, dict) and "timestamp" in a:
                timestamp = f"  t={a['timestamp']}"

            lines.append(f"    {marker} [{i + 1:2d}] {name}{timestamp}{raw_text}")
    else:
        lines.append(f"    (none or unexpected format: {type(actions_raw)})")

    # Analysis: Expected vs Performed
    matched = expected & performed
    omitted = expected - performed
    extra = performed - expected

    lines.append("\n  MATCH ANALYSIS:")
    lines.append(
        f"    Matched:  {len(matched)}/{len(expected)} ({len(matched) / len(expected) * 100:.0f}%)"
        if expected
        else "    N/A"
    )
    lines.append(f"    Omitted:  {len(omitted)}")
    lines.append(f"    Extra:    {len(extra)}")

    if omitted:
        lines.append("\n  ❌ OMITTED (expected but not performed):")
        for a in sorted(omitted):
            # Check if any performed action is similar
            close = get_close_matches(a, list(performed), n=1, cutoff=0.5)
            if close:
                sim = SequenceMatcher(None, a, close[0]).ratio()
                lines.append(f"    - {a}")
                lines.append(f'      ↳ closest performed: "{close[0]}" (sim={sim:.2f})')
            else:
                lines.append(f"    - {a}  (no similar performed action)")

    if extra:
        lines.append("\n  ➕ EXTRA (performed but not expected):")
        for a in sorted(list(extra)[:20]):
            # Check if similar to any expected
            close = get_close_matches(a, list(expected), n=1, cutoff=0.5)
            if close:
                sim = SequenceMatcher(None, a, close[0]).ratio()
                lines.append(f"    + {a}")
                lines.append(f'      ↳ closest expected: "{close[0]}" (sim={sim:.2f})')
            else:
                lines.append(f"    + {a}")
        if len(extra) > 20:
            lines.append(f"    ... +{len(extra) - 20} more")

    # Violations
    violations = ep.get("violation_events", [])
    if violations:
        lines.append(f"\n  VIOLATIONS ({len(violations)}):")
        for v in violations[:15]:
            if isinstance(v, dict):
                vtype = v.get("violation_type", v.get("type", "?"))
                vaction = v.get("expected_action", v.get("action_involved", v.get("action", "?")))
                detail = v.get("detail", v.get("message", ""))
                lines.append(f"    [{vtype}] {vaction}")
                if detail:
                    lines.append(f"      {str(detail)[:100]}")
            else:
                lines.append(f"    {v}")
        if len(violations) > 15:
            lines.append(f"    ... +{len(violations) - 15} more")

    return "\n".join(lines)


def select_high_omission_episodes(episodes, n=20):
    """OMISSION이 많은 에피소드 선택"""
    scored = []
    for ep in episodes:
        expected = ep.get("expected_actions", ep.get("mandatory_actions", []))
        actions = ep.get("actions", [])
        violations = ep.get("violation_events", [])

        n_expected = len(expected) if isinstance(expected, list) else 0
        n_actions = len(actions) if isinstance(actions, list) else 0
        n_omissions = 0
        if isinstance(violations, list):
            for v in violations:
                if isinstance(v, dict):
                    vtype = v.get("violation_type", v.get("type", "")).upper()
                    if "OMISSION" in vtype or "MUST" in vtype or "REQUIRED" in vtype:
                        n_omissions += 1

        scored.append((n_omissions, n_expected, ep))

    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [ep for _, _, ep in scored[:n]]


def select_universal_fail_episodes(episodes, n=10):
    """모든 모델이 실패하는 scenario의 에피소드 선택"""
    # Group by scenario
    by_scenario = defaultdict(list)
    for ep in episodes:
        sid = ep.get("scenario_id", "")
        by_scenario[sid].append(ep)

    # Find scenarios where all episodes have omissions
    universal_scenarios = []
    for sid, eps in by_scenario.items():
        if len(eps) < 3:
            continue
        all_have_omission = True
        total_omissions = 0
        for ep in eps:
            violations = ep.get("violation_events", [])
            has_omission = False
            if isinstance(violations, list):
                for v in violations:
                    if isinstance(v, dict):
                        vtype = v.get("violation_type", v.get("type", "")).upper()
                        if "OMISSION" in vtype:
                            has_omission = True
                            total_omissions += 1
            if not has_omission:
                all_have_omission = False
                break
        if all_have_omission:
            universal_scenarios.append((total_omissions, sid, eps))

    universal_scenarios.sort(key=lambda x: -x[0])

    # Return first episode from top scenarios, diverse models
    result = []
    for _, sid, eps in universal_scenarios[: n * 2]:
        for ep in eps[:1]:  # Just first episode per scenario
            result.append(ep)
            if len(result) >= n:
                return result
    return result


def select_near_miss_episodes(episodes, n=20):
    """Performed와 expected가 유사하지만 매칭 안 된 사례"""
    scored = []
    for ep in episodes:
        expected_raw = ep.get("expected_actions", ep.get("mandatory_actions", []))
        actions_raw = ep.get("actions", [])

        expected = set()
        if isinstance(expected_raw, list):
            for a in expected_raw:
                expected.add(extract_action_name(a).lower().strip())

        performed = set()
        if isinstance(actions_raw, list):
            for a in actions_raw:
                performed.add(extract_action_name(a).lower().strip())

        omitted = expected - performed
        near_misses = 0
        for om in omitted:
            close = get_close_matches(om, list(performed), n=1, cutoff=0.5)
            if close:
                near_misses += 1

        if near_misses > 0:
            scored.append((near_misses, ep))

    scored.sort(key=lambda x: -x[0])
    return [ep for _, ep in scored[:n]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes-dir", default="results/full_706_v5")
    parser.add_argument("--n", type=int, default=15)
    parser.add_argument("--mode", default="omission", choices=["omission", "universal", "mismatch", "random", "all"])
    parser.add_argument("--output", default=None)
    parser.add_argument("--model", default=None, help="Filter by model name")
    parser.add_argument("--graph", default=None, help="Filter by graph_id")
    args = parser.parse_args()

    print("=" * 70)
    print(f"Raw Episode Inspector — mode={args.mode}, n={args.n}")
    print("=" * 70)

    episodes = load_episodes(args.episodes_dir)
    print(f"[INFO] {len(episodes)} episodes loaded")

    if not episodes:
        print("[ERROR] No episodes found")
        return

    # Filter
    if args.model:
        episodes = [ep for ep in episodes if args.model in ep.get("_model", "")]
        print(f"[FILTER] Model={args.model}: {len(episodes)} episodes")
    if args.graph:
        episodes = [ep for ep in episodes if args.graph in ep.get("graph_id", ep.get("cpg_graph", ""))]
        print(f"[FILTER] Graph={args.graph}: {len(episodes)} episodes")

    # Select episodes
    if args.mode == "omission":
        selected = select_high_omission_episodes(episodes, args.n)
        print(f"\n[MODE] High-OMISSION episodes (top {len(selected)})")
    elif args.mode == "universal":
        selected = select_universal_fail_episodes(episodes, args.n)
        print(f"\n[MODE] Universal-fail scenarios (top {len(selected)})")
    elif args.mode == "mismatch":
        selected = select_near_miss_episodes(episodes, args.n)
        print(f"\n[MODE] Near-miss episodes ({len(selected)})")
    elif args.mode == "random":
        import random

        selected = random.sample(episodes, min(args.n, len(episodes)))
        print(f"\n[MODE] Random sample ({len(selected)})")
    elif args.mode == "all":
        selected = select_high_omission_episodes(episodes, args.n // 3)
        selected += select_universal_fail_episodes(episodes, args.n // 3)
        selected += select_near_miss_episodes(episodes, args.n // 3)
        print(f"\n[MODE] All modes ({len(selected)})")

    # Inspect
    output_lines = []
    for i, ep in enumerate(selected):
        header = f"\n{'═' * 70}\n  EPISODE {i + 1}/{len(selected)}\n{'═' * 70}"
        inspection = inspect_episode(ep)
        print(header)
        print(inspection)
        output_lines.append(header)
        output_lines.append(inspection)

    # Summary stats
    summary = []
    summary.append(f"\n{'═' * 70}")
    summary.append(f"  SUMMARY ({len(selected)} episodes inspected)")
    summary.append(f"{'═' * 70}")

    total_expected = 0
    total_performed = 0
    total_omitted = 0
    total_extra = 0
    total_near_miss = 0

    for ep in selected:
        expected_raw = ep.get("expected_actions", ep.get("mandatory_actions", []))
        actions_raw = ep.get("actions", [])

        expected = set()
        if isinstance(expected_raw, list):
            for a in expected_raw:
                expected.add(extract_action_name(a).lower().strip())

        performed = set()
        if isinstance(actions_raw, list):
            for a in actions_raw:
                performed.add(extract_action_name(a).lower().strip())

        omitted = expected - performed
        extra = performed - expected

        total_expected += len(expected)
        total_performed += len(performed)
        total_omitted += len(omitted)
        total_extra += len(extra)

        for om in omitted:
            close = get_close_matches(om, list(performed), n=1, cutoff=0.5)
            if close:
                total_near_miss += 1

    summary.append(f"  Total expected: {total_expected}")
    summary.append(f"  Total performed: {total_performed}")
    summary.append(f"  Total omitted: {total_omitted}")
    summary.append(f"  Total extra: {total_extra}")
    summary.append(f"  Near-misses (sim>0.5): {total_near_miss}")
    summary.append(f"  Near-miss / omitted: {total_near_miss / total_omitted * 100:.1f}%" if total_omitted > 0 else "")

    summary_text = "\n".join(summary)
    print(summary_text)
    output_lines.append(summary_text)

    # Save
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = Path("evidence_pack/raw_inspection")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"inspection_{args.mode}.txt"

    with open(out_path, "w") as f:
        f.write("\n".join(output_lines))
    print(f"\n[SAVED] {out_path}")


if __name__ == "__main__":
    main()
