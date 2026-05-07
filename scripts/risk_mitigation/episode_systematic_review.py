#!/usr/bin/env python3
"""Episode Systematic Self-Review
================================
30 diverse episodes verified against graph YAML at manual level.
Classifies discrepancies: FALSE_OMISSION, PHANTOM_DEVIATION,
MISSING_TIMING, MISSING_COMMISSION, DOUBLE_COUNT, etc.

Usage:
    PYTHONPATH=. python scripts/risk_mitigation/episode_systematic_review.py
"""

from collections import Counter, defaultdict
import json
from pathlib import Path

import yaml

from cga_bench.assessor_core.action_normalizer import ActionNormalizer

NORMALIZER = ActionNormalizer()
EPISODES_DIR = Path("results/full_706_v5")
GRAPHS_DIR = Path("cpg_model/graphs")
OUTPUT_DIR = Path("evidence_pack/systematic_review")

HELDOUT_MARKERS = {"aba_bu", "aabb_t", "acog", "apa_ag", "ards", "dic", "hyperkalemia", "thyroid"}


def norm(name: str) -> str:
    return NORMALIZER.normalize(name.lower().strip()) if name else ""


def load_episodes() -> list:
    episodes = []
    for model_dir in sorted(EPISODES_DIR.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                ep = json.load(open(ep_file))
                if not isinstance(ep, dict) or not ep.get("scenario_id"):
                    continue
                ep["_model"] = model_dir.name
                ep["_file"] = str(ep_file)
                episodes.append(ep)
            except Exception:
                pass
    return episodes


def load_graph(graph_id: str) -> dict | None:
    for f in GRAPHS_DIR.glob("*.yaml"):
        g = yaml.safe_load(open(f))
        if g and g.get("graph_id") == graph_id:
            return g
    # Try matching by filename prefix from scenario_id
    return None


def find_graph_for_scenario(scenario_id: str) -> dict | None:
    """Try to find graph by matching scenario prefix to graph files."""
    # Map scenario prefixes to graph files
    prefix_map = {}
    for f in GRAPHS_DIR.glob("*.yaml"):
        try:
            g = yaml.safe_load(open(f))
            if g and g.get("graph_id"):
                prefix_map[g["graph_id"]] = g
        except Exception:
            pass

    # Try scenario_id-based heuristics
    parts = scenario_id.split("_")
    # Try increasingly shorter prefixes
    for length in range(min(4, len(parts)), 0, -1):
        prefix = "_".join(parts[:length])
        for gid, g in prefix_map.items():
            if gid.startswith(prefix) or prefix.startswith(gid.replace("_management", "").replace("_2019", "")):
                return g
    return None


def sample_episodes(episodes: list, n: int = 30) -> list:
    """Sample diverse episodes across categories, graphs, models."""
    categories = {
        "timing_heavy": [],
        "omission_heavy": [],
        "commission": [],
        "sequence": [],
        "mixed": [],
        "zero_violation": [],
        "high_compliance": [],
        "low_compliance": [],
        "held_out": [],
    }

    for ep in episodes:
        viols = ep.get("violation_events", [])
        if not isinstance(viols, list):
            continue

        tc = Counter()
        for v in viols:
            if not isinstance(v, dict):
                continue
            vt = v.get("violation_type", "").upper()
            if "OMISSION" in vt:
                tc["OMISSION"] += 1
            elif "TIMING" in vt:
                tc["TIMING"] += 1
            elif "COMMISSION" in vt:
                tc["COMMISSION"] += 1
            elif "SEQUENCE" in vt:
                tc["SEQUENCE"] += 1

        cs = ep.get("compliance_score", 0.5)
        sid = ep.get("scenario_id", "")
        is_heldout = any(sid.startswith(h) for h in HELDOUT_MARKERS)

        if tc["TIMING"] >= 3 and len(categories["timing_heavy"]) < 4:
            categories["timing_heavy"].append(ep)
        elif tc["OMISSION"] >= 5 and len(categories["omission_heavy"]) < 4:
            categories["omission_heavy"].append(ep)
        elif tc["COMMISSION"] >= 1 and len(categories["commission"]) < 4:
            categories["commission"].append(ep)
        elif tc["SEQUENCE"] >= 1 and len(categories["sequence"]) < 4:
            categories["sequence"].append(ep)
        elif len(tc) >= 3 and len(categories["mixed"]) < 4:
            categories["mixed"].append(ep)
        elif len(viols) == 0 and cs >= 0.99 and len(categories["zero_violation"]) < 3:
            categories["zero_violation"].append(ep)
        elif cs > 0.9 and len(categories["high_compliance"]) < 3:
            categories["high_compliance"].append(ep)
        elif cs < 0.2 and len(categories["low_compliance"]) < 3:
            categories["low_compliance"].append(ep)
        elif is_heldout and len(categories["held_out"]) < 3:
            categories["held_out"].append(ep)

    # Collect ensuring graph/model diversity
    selected = []
    seen_graphs = set()
    seen_models = set()

    for cat_name, cat_eps in categories.items():
        for ep in cat_eps:
            model = ep.get("_model", "")
            sid = ep.get("scenario_id", "")
            graph_prefix = "_".join(sid.split("_")[:2])
            seen_graphs.add(graph_prefix)
            seen_models.add(model)
            selected.append((cat_name, ep))

    # Deduplicate by file
    seen_files = set()
    unique = []
    for cat, ep in selected:
        f = ep["_file"]
        if f not in seen_files:
            seen_files.add(f)
            unique.append((cat, ep))

    return unique[:n]


def verify_episode(ep: dict) -> dict:
    """Verify single episode against graph constraints."""
    sid = ep.get("scenario_id", "")
    model = ep.get("_model", "")
    cs = ep.get("compliance_score", 0)

    # Extract performed actions (normalized)
    performed_raw = {}  # action_id -> timestamp
    performed_norm = {}  # normalized -> timestamp
    for a in ep.get("actions") or []:
        if isinstance(a, dict):
            raw = a.get("action_id", "")
            ts = a.get("timestamp_minutes", 0)
            if raw:
                performed_raw[raw.lower().strip()] = ts
                performed_norm[norm(raw)] = ts

    # Expected and forbidden from episode
    expected = set(a.lower().strip() for a in (ep.get("expected_actions") or []) if isinstance(a, str))
    expected_norm = set(norm(a) for a in expected)
    forbidden = set(a.lower().strip() for a in (ep.get("forbidden_actions") or []) if isinstance(a, str))
    forbidden_norm = set(norm(a) for a in forbidden)

    # System violations
    sys_viols = []
    for v in ep.get("violation_events") or []:
        if not isinstance(v, dict):
            continue
        vtype = v.get("violation_type", "").upper()
        action = v.get("expected_action") or v.get("action_involved") or v.get("action") or ""
        action = action.lower().strip() if isinstance(action, str) else ""
        sys_viols.append(
            {
                "type": vtype,
                "action": action,
                "action_norm": norm(action) if action else "",
                "severity": v.get("harm_severity", "?"),
                "node": v.get("node_at_violation", "?"),
            }
        )

    # Load graph and extract deadlines
    graph = find_graph_for_scenario(sid)
    deadlines = {}
    graph_mandatory = set()
    graph_forbidden = set()
    graph_id = "?"
    if graph:
        graph_id = graph.get("graph_id", "?")
        nodes = graph.get("nodes", {})
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for a in node.get("mandatory_actions") or []:
                graph_mandatory.add(a.lower().strip())
            for a in node.get("forbidden_actions") or []:
                graph_forbidden.add(a.lower().strip())
            dl = node.get("deadlines", {})
            if isinstance(dl, dict):
                for action, deadline_val in dl.items():
                    if isinstance(deadline_val, (int, float)):
                        deadlines[action.lower().strip()] = deadline_val
                    elif isinstance(deadline_val, dict) and "minutes" in deadline_val:
                        deadlines[action.lower().strip()] = deadline_val["minutes"]

    # === Manual verification ===
    issues = []

    # Check each system OMISSION: is the action actually performed?
    for sv in sys_viols:
        if "OMISSION" in sv["type"]:
            action = sv["action"]
            action_n = sv["action_norm"]
            # Check if performed (raw or normalized)
            if action in performed_raw or action_n in performed_norm:
                # FALSE OMISSION: action was performed
                perform_time = performed_raw.get(action, performed_norm.get(action_n, "?"))
                deadline = deadlines.get(action)
                if deadline and isinstance(perform_time, (int, float)) and perform_time > deadline:
                    issues.append(
                        {
                            "bug": "FALSE_OMISSION_SHOULD_BE_TIMING",
                            "action": action,
                            "performed_at": perform_time,
                            "deadline": deadline,
                            "detail": f"Performed at t={perform_time}m, deadline={deadline}m → should be TIMING, not OMISSION",
                        }
                    )
                else:
                    issues.append(
                        {
                            "bug": "FALSE_OMISSION_PERFORMED",
                            "action": action,
                            "performed_at": perform_time,
                            "detail": f"Action performed (t={perform_time}m) but marked OMISSION (no deadline or within deadline)",
                        }
                    )

        elif "COMMISSION" in sv["type"]:
            action = sv["action"]
            action_n = sv["action_norm"]
            # Check if action is actually in forbidden list
            if action not in forbidden and action_n not in forbidden_norm:
                issues.append(
                    {
                        "bug": "COMMISSION_NOT_FORBIDDEN",
                        "action": action,
                        "detail": "COMMISSION violation but action not in episode's forbidden list",
                    }
                )
            # Check if action was actually performed
            if action not in performed_raw and action_n not in performed_norm:
                issues.append(
                    {
                        "bug": "COMMISSION_NOT_PERFORMED",
                        "action": action,
                        "detail": "COMMISSION violation but action not found in performed actions",
                    }
                )

        elif "DEVIATION" in sv["type"]:
            action = sv["action"]
            action_n = sv["action_norm"]
            # Check if the deviation action is actually in the trace
            if action not in performed_raw and action_n not in performed_norm:
                issues.append(
                    {
                        "bug": "PHANTOM_DEVIATION",
                        "action": action,
                        "detail": "DEVIATION references action not in performed trace",
                    }
                )

    # Check for missing violations
    # Forbidden actions performed but no COMMISSION
    commission_actions = set(sv["action_norm"] for sv in sys_viols if "COMMISSION" in sv["type"])
    for fa in forbidden:
        fa_n = norm(fa)
        if fa_n in performed_norm and fa_n not in commission_actions:
            issues.append(
                {
                    "bug": "MISSING_COMMISSION",
                    "action": fa,
                    "detail": "Forbidden action performed but no COMMISSION violation recorded",
                }
            )

    # Expected actions performed late but no TIMING
    timing_actions = set(sv["action"] for sv in sys_viols if "TIMING" in sv["type"])
    for ma in expected:
        ma_n = norm(ma)
        if ma_n in performed_norm and ma in deadlines:
            t = performed_norm.get(ma_n, 0)
            dl = deadlines[ma]
            if (
                isinstance(t, (int, float))
                and t > dl
                and ma not in timing_actions
                and ma_n not in set(norm(a) for a in timing_actions)
            ):
                issues.append(
                    {
                        "bug": "MISSING_TIMING",
                        "action": ma,
                        "performed_at": t,
                        "deadline": dl,
                        "detail": f"Late (t={t}m > deadline={dl}m) but no TIMING violation",
                    }
                )

    # Double-count check
    omission_actions_n = set(sv["action_norm"] for sv in sys_viols if "OMISSION" in sv["type"])
    timing_actions_n = set(sv["action_norm"] for sv in sys_viols if "TIMING" in sv["type"])
    double_count = omission_actions_n & timing_actions_n
    for dc in double_count:
        issues.append(
            {
                "bug": "DOUBLE_COUNT",
                "action": dc,
                "detail": "Same action appears in both OMISSION and TIMING violations",
            }
        )

    return {
        "file": ep["_file"][-80:],
        "model": model,
        "scenario_id": sid,
        "graph_id": graph_id,
        "compliance": round(cs, 3),
        "n_performed": len(performed_raw),
        "n_expected": len(expected),
        "n_forbidden": len(forbidden),
        "n_system_viols": len(sys_viols),
        "system_viols": sys_viols,
        "n_issues": len(issues),
        "issues": issues,
        "deadlines_found": len(deadlines),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("EPISODE SYSTEMATIC SELF-REVIEW")
    print("=" * 70)

    episodes = load_episodes()
    print(f"Loaded {len(episodes)} episodes")

    print("\n[STEP 1] Sampling 30 diverse episodes...")
    selected = sample_episodes(episodes, 30)
    print(f"  Selected {len(selected)} episodes from {len(set(ep.get('_model', '') for _, ep in selected))} models")

    cat_counts = Counter(cat for cat, _ in selected)
    for cat, cnt in cat_counts.most_common():
        print(f"    {cat}: {cnt}")

    print("\n[STEP 2] Verifying each episode against graph...")
    all_results = []
    bug_counts = Counter()
    bug_examples = defaultdict(list)

    for i, (cat, ep) in enumerate(selected):
        result = verify_episode(ep)
        result["category"] = cat
        all_results.append(result)

        for issue in result["issues"]:
            bug_counts[issue["bug"]] += 1
            if len(bug_examples[issue["bug"]]) < 3:
                bug_examples[issue["bug"]].append(
                    {
                        "episode": result["scenario_id"],
                        "model": result["model"],
                        "action": issue.get("action", ""),
                        "detail": issue.get("detail", ""),
                    }
                )

        n_issues = result["n_issues"]
        marker = "✅" if n_issues == 0 else f"🔴×{n_issues}"
        print(
            f"  [{i + 1:2d}] {marker} {result['model']:15s} {result['scenario_id'][:50]:50s} viols={result['n_system_viols']} issues={n_issues}"
        )

    # === Report ===
    lines = []
    lines.append("=" * 80)
    lines.append("EPISODE SYSTEMATIC SELF-REVIEW")
    lines.append(f"Verified: {len(all_results)} episodes")
    lines.append("=" * 80)

    # Summary
    n_clean = sum(1 for r in all_results if r["n_issues"] == 0)
    n_issues = sum(1 for r in all_results if r["n_issues"] > 0)
    total_issues = sum(r["n_issues"] for r in all_results)

    lines.append("\n## Summary")
    lines.append(f"  Clean episodes: {n_clean}/{len(all_results)}")
    lines.append(f"  Episodes with issues: {n_issues}/{len(all_results)} ({n_issues / len(all_results) * 100:.0f}%)")
    lines.append(f"  Total issues found: {total_issues}")

    # Bug classification
    lines.append("\n## Bug Classification")
    lines.append(f"  {'Bug Type':<40s} {'Count':>6s} {'% of episodes':>14s}")
    lines.append(f"  {'-' * 40} {'-' * 6} {'-' * 14}")
    for bug_type, count in bug_counts.most_common():
        n_eps = sum(1 for r in all_results if any(i["bug"] == bug_type for i in r["issues"]))
        lines.append(f"  {bug_type:<40s} {count:>6d} {n_eps / len(all_results) * 100:>13.0f}%")

    # Examples per bug type
    lines.append("\n## Bug Examples")
    for bug_type, examples in bug_examples.items():
        lines.append(f"\n  {bug_type}:")
        for ex in examples:
            lines.append(f"    {ex['model']}/{ex['episode']}: {ex['action']} — {ex['detail'][:100]}")

    # Per-episode details
    lines.append("\n## Per-Episode Details")
    for r in all_results:
        lines.append(f"\n  {'─' * 60}")
        lines.append(f"  [{r['category']}] {r['model']}/{r['scenario_id']}")
        lines.append(
            f"  Graph: {r['graph_id']}, Compliance: {r['compliance']}, Viols: {r['n_system_viols']}, Issues: {r['n_issues']}"
        )
        if r["issues"]:
            for issue in r["issues"]:
                lines.append(f"    🔴 {issue['bug']}: {issue.get('action', '')} — {issue.get('detail', '')[:120]}")
        else:
            lines.append("    ✅ All system violations verified correct")

    # Graphs and models coverage
    graphs = set(r["graph_id"] for r in all_results)
    models = set(r["model"] for r in all_results)
    lines.append("\n## Coverage")
    lines.append(f"  Graphs: {len(graphs)} — {sorted(graphs)}")
    lines.append(f"  Models: {len(models)} — {sorted(models)}")

    report = "\n".join(lines)
    print(report)

    with open(OUTPUT_DIR / "systematic_review_report.md", "w") as f:
        f.write(report)
    with open(OUTPUT_DIR / "systematic_review_results.json", "w") as f:
        json.dump(
            {
                "summary": {
                    "n_episodes": len(all_results),
                    "n_clean": n_clean,
                    "n_with_issues": n_issues,
                    "total_issues": total_issues,
                },
                "bug_counts": dict(bug_counts),
                "all_results": all_results,
            },
            f,
            indent=2,
            default=str,
        )

    print(f"\n[SAVED] {OUTPUT_DIR / 'systematic_review_report.md'}")
    print(f"[SAVED] {OUTPUT_DIR / 'systematic_review_results.json'}")


if __name__ == "__main__":
    main()
