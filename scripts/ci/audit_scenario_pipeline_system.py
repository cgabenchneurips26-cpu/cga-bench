#!/usr/bin/env python3
"""System-wide Scenario Generation Pipeline Audit

Checks bug classes BEYOND the action normalizer (which has its own audit).
Focuses on the guideline -> scenario generation pipeline:

  B1: walk_reachable_path ALL-branch collection (mutually exclusive actions)
  B2: Substring matching weakness in conditional_next
  B3: forbidden_actions never normalized (asymmetry with scoring)
  B4: 3 generators produce DIFFERENT expected_actions for same graph
  B5: _is_node_active() defaults True for state-based preconditions
  B6: Scenario expected_actions vs CDE expected_actions divergence
  B7: global_union fallback includes mutually exclusive branch actions
  B8: guideline_graph reference validation (broken references)

Usage:
    PYTHONPATH=. python scripts/ci/audit_scenario_pipeline_system.py
"""

from __future__ import annotations

import collections
import json
from pathlib import Path
import sys

import yaml

BASE = Path(__file__).resolve().parents[2]
GRAPHS_DIR = BASE / "cpg_model" / "graphs"
SCENARIOS_DIR = BASE / "configs" / "scenarios"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_all_graphs() -> dict[str, dict]:
    """Load all CPG graph YAMLs."""
    graphs: dict[str, dict] = {}
    for p in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(p) as f:
            data = yaml.safe_load(f) or {}
        graphs[p.stem] = data
    return graphs


def _load_all_scenarios() -> dict[str, dict]:
    """Load all scenario YAMLs into flat dict."""
    scenarios: dict[str, dict] = {}
    for p in sorted(SCENARIOS_DIR.glob("*.yaml")):
        with open(p) as f:
            data = yaml.safe_load(f) or {}
        scns = data.get("scenarios", {})
        if isinstance(scns, dict):
            for sid, sdef in scns.items():
                if isinstance(sdef, dict):
                    sdef["_source_file"] = p.name
                    scenarios[sid] = sdef
    return scenarios


def _walk_reachable_path_with_diagnosis(
    graph: dict, working_diagnosis: str | None = None
) -> tuple[list[str], list[str]]:
    """Reimplementation of walk_reachable_path returning (actions, visited_nodes)."""
    nodes = graph.get("nodes") or {}
    entry = graph.get("entry_node", "")
    if not entry or entry not in nodes:
        return [], []

    visited: set[str] = set()
    visited_ordered: list[str] = []
    queue: list[str] = [entry]
    mandatory: list[str] = []
    seen: set[str] = set()

    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        visited_ordered.append(nid)
        node = nodes.get(nid)
        if not node or not isinstance(node, dict):
            continue

        for action in node.get("mandatory_actions") or []:
            if action not in seen:
                mandatory.append(action)
                seen.add(action)

        cond_next = node.get("conditional_next") or {}
        next_nodes = list(node.get("next_nodes") or [])

        if cond_next and working_diagnosis:
            matched = False
            for cond, target in cond_next.items():
                if working_diagnosis in cond or cond == "True" or cond == "'True'":
                    if not matched:
                        queue.append(target)
                        matched = True
            if not matched and cond_next:
                first_target = next(iter(cond_next.values()))
                queue.append(first_target)
        elif cond_next:
            # No working_diagnosis: follow ALL branches
            for target in cond_next.values():
                queue.append(target)

        for nxt in next_nodes:
            queue.append(nxt)

    return mandatory, visited_ordered


# ---------------------------------------------------------------------------
# B1: walk_reachable_path ALL-branch collection
# ---------------------------------------------------------------------------


def audit_b1_allbranch_collection(graphs: dict[str, dict]) -> list[dict]:
    """Detect graphs where walk_reachable_path(dx=None) collects from
    mutually exclusive branches, inflating expected_actions.
    """
    findings: list[dict] = []

    for gid, graph in graphs.items():
        nodes = graph.get("nodes") or {}
        # Find nodes with conditional_next (branch points)
        branch_nodes: list[str] = []
        for nid, node in nodes.items():
            if not isinstance(node, dict):
                continue
            cond_next = node.get("conditional_next")
            if cond_next and isinstance(cond_next, dict) and len(cond_next) > 1:
                branch_nodes.append(nid)

        if not branch_nodes:
            continue

        # Walk with no dx -> ALL branches
        all_actions, all_nodes = _walk_reachable_path_with_diagnosis(graph, None)

        # Walk each branch individually to see what's exclusive
        for branch_nid in branch_nodes:
            node = nodes[branch_nid]
            cond_next = node.get("conditional_next") or {}
            branch_actions: dict[str, set[str]] = {}

            for cond, target_nid in cond_next.items():
                # Walk from this branch target only
                sub_actions = set()
                sub_visited: set[str] = set()
                sub_queue = [target_nid]
                while sub_queue:
                    snid = sub_queue.pop(0)
                    if snid in sub_visited:
                        continue
                    sub_visited.add(snid)
                    snode = nodes.get(snid)
                    if not snode or not isinstance(snode, dict):
                        continue
                    for a in snode.get("mandatory_actions") or []:
                        sub_actions.add(a)
                    for nxt in snode.get("next_nodes") or []:
                        sub_queue.append(nxt)
                    for cn_target in (snode.get("conditional_next") or {}).values():
                        sub_queue.append(cn_target)

                branch_actions[cond] = sub_actions

            # Find actions that are EXCLUSIVE to one branch
            all_branch_conds = list(branch_actions.keys())
            for i, c1 in enumerate(all_branch_conds):
                for c2 in all_branch_conds[i + 1 :]:
                    exclusive_to_c1 = branch_actions[c1] - branch_actions[c2]
                    exclusive_to_c2 = branch_actions[c2] - branch_actions[c1]
                    if exclusive_to_c1 and exclusive_to_c2:
                        findings.append(
                            {
                                "bug_class": "B1",
                                "severity": "HIGH",
                                "type": "mutually_exclusive_branch_actions",
                                "graph": gid,
                                "branch_node": branch_nid,
                                "condition_1": c1,
                                "condition_2": c2,
                                "exclusive_to_c1": sorted(exclusive_to_c1),
                                "exclusive_to_c2": sorted(exclusive_to_c2),
                                "impact": (
                                    "walk_reachable_path(dx=None) collects BOTH sets "
                                    "into expected_actions, but they are mutually exclusive. "
                                    "Agent can only take one branch -> false OMISSION for the other."
                                ),
                            }
                        )

    return findings


# ---------------------------------------------------------------------------
# B2: Substring matching weakness in conditional_next
# ---------------------------------------------------------------------------


def audit_b2_substring_matching(graphs: dict[str, dict]) -> list[dict]:
    """Detect conditional_next conditions where substring matching
    would produce ambiguous results.
    """
    findings: list[dict] = []

    for gid, graph in graphs.items():
        nodes = graph.get("nodes") or {}
        for nid, node in nodes.items():
            if not isinstance(node, dict):
                continue
            cond_next = node.get("conditional_next") or {}
            if len(cond_next) < 2:
                continue

            conditions = list(cond_next.keys())
            # Check if any condition is a substring of another
            for i, c1 in enumerate(conditions):
                for c2 in conditions[i + 1 :]:
                    if c1 == "True" or c2 == "True":
                        continue
                    if c1 in c2 or c2 in c1:
                        findings.append(
                            {
                                "bug_class": "B2",
                                "severity": "MEDIUM",
                                "type": "substring_ambiguity",
                                "graph": gid,
                                "node": nid,
                                "condition_1": c1,
                                "condition_2": c2,
                                "is_substring": f"'{c1}' in '{c2}'" if c1 in c2 else f"'{c2}' in '{c1}'",
                                "impact": (
                                    "walk_reachable_path uses `working_diagnosis in cond` — "
                                    "a diagnosis matching the shorter string will ALSO match "
                                    "the longer one, potentially following the wrong branch."
                                ),
                            }
                        )

    return findings


# ---------------------------------------------------------------------------
# B3: forbidden_actions never normalized
# ---------------------------------------------------------------------------


def audit_b3_forbidden_normalization(graphs: dict[str, dict], scenarios: dict[str, dict]) -> list[dict]:
    """Check if forbidden_actions in scenarios/graphs are stored raw
    while the scoring path normalizes performed actions.
    """
    findings: list[dict] = []

    # Initialize normalizer
    try:
        sys.path.insert(0, str(BASE))
        sys.path.insert(0, str(BASE.parent))
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer

        normalizer = ActionNormalizer()
    except ImportError:
        return [
            {
                "bug_class": "B3",
                "severity": "SKIP",
                "type": "import_failed",
                "impact": "Could not import ActionNormalizer",
            }
        ]

    # Check graph-level forbidden_actions
    for gid, graph in graphs.items():
        nodes = graph.get("nodes") or {}
        for nid, node in nodes.items():
            if not isinstance(node, dict):
                continue
            for fa in node.get("forbidden_actions") or []:
                normalized = normalizer.normalize(str(fa))
                if normalized != fa:
                    findings.append(
                        {
                            "bug_class": "B3",
                            "severity": "MEDIUM",
                            "type": "graph_forbidden_not_normalized",
                            "graph": gid,
                            "node": nid,
                            "raw_forbidden": fa,
                            "normalized_form": normalized,
                            "impact": (
                                "Graph stores raw forbidden_action, but ViolationExtractor "
                                "normalizes performed actions. If agent performs the "
                                "NORMALIZED form, commission check may miss it because "
                                "the stored forbidden form doesn't match."
                            ),
                        }
                    )

    # Check scenario-level forbidden_actions
    for sid, scn in scenarios.items():
        for fa in scn.get("forbidden_actions") or []:
            normalized = normalizer.normalize(str(fa))
            if normalized != fa:
                findings.append(
                    {
                        "bug_class": "B3",
                        "severity": "MEDIUM",
                        "type": "scenario_forbidden_not_normalized",
                        "scenario": sid,
                        "raw_forbidden": fa,
                        "normalized_form": normalized,
                        "impact": (
                            "Scenario stores raw forbidden_action. Scoring may "
                            "miss COMMISSION violations for the normalized form."
                        ),
                    }
                )

    return findings


# ---------------------------------------------------------------------------
# B4: 3 generators produce different expected_actions
# ---------------------------------------------------------------------------


def audit_b4_generator_inconsistency(graphs: dict[str, dict], scenarios: dict[str, dict]) -> list[dict]:
    """Compare expected_actions produced by different generators for the same graph."""
    findings: list[dict] = []

    # Group scenarios by graph
    graph_scenarios: dict[str, list[tuple[str, dict]]] = collections.defaultdict(list)
    for sid, scn in scenarios.items():
        gg = scn.get("guideline_graph") or scn.get("cpg_graph") or ""
        if gg:
            graph_scenarios[gg].append((sid, scn))

    for gg, scn_list in graph_scenarios.items():
        # Separate by source file to identify generator
        by_source: dict[str, list[tuple[str, dict]]] = collections.defaultdict(list)
        for sid, scn in scn_list:
            src = scn.get("_source_file", "unknown")
            by_source[src].append((sid, scn))

        if len(by_source) < 2:
            continue

        # Collect unique expected_action sets per source
        source_action_sets: dict[str, list[frozenset[str]]] = {}
        for src, items in by_source.items():
            sets: list[frozenset[str]] = []
            for sid, scn in items:
                ea = scn.get("expected_actions") or []
                if ea:
                    sets.append(frozenset(ea))
            source_action_sets[src] = sets

        # Compare between sources
        sources = list(source_action_sets.keys())
        for i, s1 in enumerate(sources):
            for s2 in sources[i + 1 :]:
                sets1 = source_action_sets[s1]
                sets2 = source_action_sets[s2]
                if not sets1 or not sets2:
                    continue

                # Find the union of all expected_actions per source
                union1 = set().union(*sets1) if sets1 else set()
                union2 = set().union(*sets2) if sets2 else set()

                only_in_s1 = union1 - union2
                only_in_s2 = union2 - union1

                if only_in_s1 or only_in_s2:
                    findings.append(
                        {
                            "bug_class": "B4",
                            "severity": "HIGH" if only_in_s1 and only_in_s2 else "MEDIUM",
                            "type": "generator_inconsistency",
                            "graph": gg,
                            "source_1": s1,
                            "source_2": s2,
                            "n_scenarios_s1": len(by_source[s1]),
                            "n_scenarios_s2": len(by_source[s2]),
                            "only_in_s1": sorted(only_in_s1)[:10],
                            "only_in_s2": sorted(only_in_s2)[:10],
                            "impact": (
                                "Different generators produce different expected_actions "
                                "for the same CPG graph. Scenarios from one generator may "
                                "require actions that scenarios from another generator don't, "
                                "creating inconsistent evaluation criteria."
                            ),
                        }
                    )

    return findings


# ---------------------------------------------------------------------------
# B5: CDE _is_node_active defaults True for state-based preconditions
# ---------------------------------------------------------------------------


def audit_b5_state_precondition_default(graphs: dict[str, dict]) -> list[dict]:
    """Find nodes with state-based preconditions that CDE defaults to True,
    potentially including mandatory_actions from unreachable nodes.
    """
    findings: list[dict] = []

    for gid, graph in graphs.items():
        nodes = graph.get("nodes") or {}
        for nid, node in nodes.items():
            if not isinstance(node, dict):
                continue
            precondition = node.get("precondition")
            if precondition is None:
                continue

            precond_str = str(precondition)
            mandatory = node.get("mandatory_actions") or []

            if "state." in precond_str and mandatory:
                findings.append(
                    {
                        "bug_class": "B5",
                        "severity": "MEDIUM",
                        "type": "state_precondition_default_true",
                        "graph": gid,
                        "node": nid,
                        "precondition": precond_str,
                        "mandatory_actions": mandatory,
                        "impact": (
                            "CDE defaults _is_node_active()=True for state-based "
                            "preconditions. This node's mandatory_actions will be "
                            "included in expected_actions even when the state condition "
                            "is not actually met, causing false OMISSION violations."
                        ),
                    }
                )

    return findings


# ---------------------------------------------------------------------------
# B6: Scenario expected_actions vs walk_reachable_path divergence
# ---------------------------------------------------------------------------


def audit_b6_scenario_vs_walk(graphs: dict[str, dict], scenarios: dict[str, dict]) -> list[dict]:
    """Compare scenario expected_actions against what walk_reachable_path
    would produce, to detect stale or incorrect expected_actions.
    """
    findings: list[dict] = []

    for sid, scn in scenarios.items():
        gg = scn.get("guideline_graph") or scn.get("cpg_graph") or ""
        if not gg or gg not in graphs:
            continue

        graph = graphs[gg]
        scn_expected = set(scn.get("expected_actions") or [])
        if not scn_expected:
            continue

        # Get working_diagnosis from scenario
        dx = scn.get("working_diagnosis") or scn.get("diagnosis") or ""

        # Walk with and without diagnosis
        walk_with_dx, _ = _walk_reachable_path_with_diagnosis(graph, dx if dx else None)
        walk_no_dx, _ = _walk_reachable_path_with_diagnosis(graph, None)

        walk_with_dx_set = set(walk_with_dx)
        walk_no_dx_set = set(walk_no_dx)

        # Actions in scenario but NOT in any walk
        orphan_actions = scn_expected - walk_no_dx_set
        if orphan_actions:
            findings.append(
                {
                    "bug_class": "B6",
                    "severity": "HIGH",
                    "type": "orphan_expected_actions",
                    "scenario": sid,
                    "graph": gg,
                    "orphan_actions": sorted(orphan_actions),
                    "n_scenario_expected": len(scn_expected),
                    "n_walk_all": len(walk_no_dx_set),
                    "impact": (
                        "Scenario has expected_actions that don't appear in ANY "
                        "graph node's mandatory_actions. These cannot be satisfied "
                        "by the CPG engine and will always produce OMISSION violations."
                    ),
                }
            )

    return findings


# ---------------------------------------------------------------------------
# B7: global_union fallback with mutually exclusive branches
# ---------------------------------------------------------------------------


def audit_b7_global_union_exclusive(graphs: dict[str, dict]) -> list[dict]:
    """For graphs with conditional_next branches, check if the global union
    of mandatory_actions includes actions from mutually exclusive branches.
    """
    findings: list[dict] = []

    for gid, graph in graphs.items():
        nodes = graph.get("nodes") or {}

        # Collect global union (same as generate_scenarios_v3.py)
        global_union: list[str] = []
        seen: set[str] = set()
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            for a in node.get("mandatory_actions") or []:
                if a not in seen:
                    global_union.append(a)
                    seen.add(a)

        # Find branch-specific diagnoses
        branch_diagnoses: list[str] = []
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            cond_next = node.get("conditional_next") or {}
            for cond in cond_next:
                if cond not in ("True", "'True'"):
                    branch_diagnoses.append(cond)

        if not branch_diagnoses:
            continue

        # Walk each branch individually
        branch_action_sets: dict[str, set[str]] = {}
        for dx in branch_diagnoses:
            actions, _ = _walk_reachable_path_with_diagnosis(graph, dx)
            branch_action_sets[dx] = set(actions)

        # Check if global union has more actions than any single branch
        global_set = set(global_union)
        for dx, branch_set in branch_action_sets.items():
            extra_in_global = global_set - branch_set
            if extra_in_global:
                findings.append(
                    {
                        "bug_class": "B7",
                        "severity": "HIGH",
                        "type": "global_union_excess",
                        "graph": gid,
                        "diagnosis": dx,
                        "global_union_size": len(global_set),
                        "branch_size": len(branch_set),
                        "extra_actions": sorted(extra_in_global)[:10],
                        "n_extra": len(extra_in_global),
                        "impact": (
                            "generate_scenarios_v3 falls back to global_union when "
                            "walk_reachable_path returns empty. Global union has "
                            f"{len(extra_in_global)} more actions than the {dx} branch. "
                            "These extra actions come from other branches and cannot "
                            "be performed by agents following this diagnosis path."
                        ),
                    }
                )

    return findings


# ---------------------------------------------------------------------------
# B8: guideline_graph reference validation
# ---------------------------------------------------------------------------


def audit_b8_graph_references(graphs: dict[str, dict], scenarios: dict[str, dict]) -> list[dict]:
    """Check that all scenario guideline_graph references point to existing graphs."""
    findings: list[dict] = []
    valid_graphs = set(graphs.keys())

    missing_refs: dict[str, list[str]] = collections.defaultdict(list)
    for sid, scn in scenarios.items():
        gg = scn.get("guideline_graph") or scn.get("cpg_graph") or ""
        if gg and gg not in valid_graphs:
            missing_refs[gg].append(sid)

    for gg, sids in missing_refs.items():
        findings.append(
            {
                "bug_class": "B8",
                "severity": "CRITICAL",
                "type": "missing_graph_reference",
                "referenced_graph": gg,
                "n_scenarios": len(sids),
                "example_scenarios": sids[:5],
                "impact": (
                    f"{len(sids)} scenarios reference graph '{gg}' which does not "
                    "exist in cpg_model/graphs/. These scenarios cannot be evaluated."
                ),
            }
        )

    return findings


# ---------------------------------------------------------------------------
# B9: Duplicate expected_actions within single scenario (non-normalizer)
# ---------------------------------------------------------------------------


def audit_b9_exact_duplicates(scenarios: dict[str, dict]) -> list[dict]:
    """Find scenarios with exact duplicate expected_actions (pre-normalization)."""
    findings: list[dict] = []

    for sid, scn in scenarios.items():
        ea = scn.get("expected_actions") or []
        if len(ea) != len(set(ea)):
            dupes = [a for a, c in collections.Counter(ea).items() if c > 1]
            findings.append(
                {
                    "bug_class": "B9",
                    "severity": "LOW",
                    "type": "exact_duplicate_expected",
                    "scenario": sid,
                    "duplicates": dupes,
                    "impact": "Same action listed multiple times in expected_actions.",
                }
            )

    # Same for forbidden
    for sid, scn in scenarios.items():
        fa = scn.get("forbidden_actions") or []
        if len(fa) != len(set(fa)):
            dupes = [a for a, c in collections.Counter(fa).items() if c > 1]
            findings.append(
                {
                    "bug_class": "B9",
                    "severity": "LOW",
                    "type": "exact_duplicate_forbidden",
                    "scenario": sid,
                    "duplicates": dupes,
                    "impact": "Same action listed multiple times in forbidden_actions.",
                }
            )

    return findings


# ---------------------------------------------------------------------------
# B10: expected ∩ forbidden conflict
# ---------------------------------------------------------------------------


def audit_b10_expected_forbidden_conflict(scenarios: dict[str, dict]) -> list[dict]:
    """Find scenarios where the same action is both expected AND forbidden."""
    findings: list[dict] = []

    for sid, scn in scenarios.items():
        ea = set(scn.get("expected_actions") or [])
        fa = set(scn.get("forbidden_actions") or [])
        overlap = ea & fa
        if overlap:
            findings.append(
                {
                    "bug_class": "B10",
                    "severity": "CRITICAL",
                    "type": "expected_forbidden_conflict",
                    "scenario": sid,
                    "conflicting_actions": sorted(overlap),
                    "impact": (
                        "Action is both expected AND forbidden. Agent is penalized "
                        "whether they perform it (COMMISSION) or not (OMISSION)."
                    ),
                }
            )

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 72)
    print("SCENARIO GENERATION PIPELINE — SYSTEM-WIDE AUDIT")
    print("(Beyond action normalizer — structural pipeline bugs)")
    print("=" * 72)

    graphs = _load_all_graphs()
    scenarios = _load_all_scenarios()
    print(f"\nLoaded {len(graphs)} graphs, {len(scenarios)} scenarios")

    all_findings: list[dict] = []

    # --- B1 ---
    print("\n[B1] walk_reachable_path ALL-branch collection...")
    b1 = audit_b1_allbranch_collection(graphs)
    all_findings.extend(b1)
    print(f"     {len(b1)} mutually exclusive branch pairs found")

    # --- B2 ---
    print("\n[B2] Substring matching ambiguity in conditional_next...")
    b2 = audit_b2_substring_matching(graphs)
    all_findings.extend(b2)
    print(f"     {len(b2)} ambiguous condition pairs found")

    # --- B3 ---
    print("\n[B3] forbidden_actions normalization gap...")
    b3 = audit_b3_forbidden_normalization(graphs, scenarios)
    all_findings.extend(b3)
    b3_graph = [f for f in b3 if f["type"] == "graph_forbidden_not_normalized"]
    b3_scn = [f for f in b3 if f["type"] == "scenario_forbidden_not_normalized"]
    print(f"     {len(b3_graph)} graph-level + {len(b3_scn)} scenario-level raw forbidden actions")

    # --- B4 ---
    print("\n[B4] Generator inconsistency (same graph, different expected_actions)...")
    b4 = audit_b4_generator_inconsistency(graphs, scenarios)
    all_findings.extend(b4)
    print(f"     {len(b4)} graph-source pairs with divergent expected_actions")

    # --- B5 ---
    print("\n[B5] state-based precondition default True...")
    b5 = audit_b5_state_precondition_default(graphs)
    all_findings.extend(b5)
    total_ma = sum(len(f.get("mandatory_actions", [])) for f in b5)
    print(f"     {len(b5)} nodes with state. preconditions ({total_ma} mandatory_actions)")

    # --- B6 ---
    print("\n[B6] Scenario expected_actions vs walk_reachable_path divergence...")
    b6 = audit_b6_scenario_vs_walk(graphs, scenarios)
    all_findings.extend(b6)
    print(f"     {len(b6)} scenarios with orphan expected_actions")

    # --- B7 ---
    print("\n[B7] global_union fallback excess...")
    b7 = audit_b7_global_union_exclusive(graphs)
    all_findings.extend(b7)
    print(f"     {len(b7)} graph-diagnosis pairs with excess global_union actions")

    # --- B8 ---
    print("\n[B8] guideline_graph reference validation...")
    b8 = audit_b8_graph_references(graphs, scenarios)
    all_findings.extend(b8)
    print(f"     {len(b8)} missing graph references")

    # --- B9 ---
    print("\n[B9] Exact duplicate expected/forbidden actions...")
    b9 = audit_b9_exact_duplicates(scenarios)
    all_findings.extend(b9)
    print(f"     {len(b9)} scenarios with exact duplicates")

    # --- B10 ---
    print("\n[B10] expected ∩ forbidden conflict...")
    b10 = audit_b10_expected_forbidden_conflict(scenarios)
    all_findings.extend(b10)
    print(f"     {len(b10)} scenarios with expected/forbidden conflicts")

    # --- Summary ---
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)

    severity_counts = collections.Counter(f["severity"] for f in all_findings)
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "OK", "SKIP"]:
        if severity_counts.get(sev, 0) > 0:
            print(f"  {sev:10s}: {severity_counts[sev]}")

    bug_counts = collections.Counter(f["bug_class"] for f in all_findings)
    print("\n  Per bug class:")
    for bc in sorted(bug_counts):
        print(f"    {bc}: {bug_counts[bc]}")

    total_issues = severity_counts.get("CRITICAL", 0) + severity_counts.get("HIGH", 0)
    print(f"\n  Total actionable issues (CRITICAL+HIGH): {total_issues}")

    # --- Detailed output for HIGH+ ---
    print("\n" + "=" * 72)
    print("DETAILED FINDINGS (CRITICAL + HIGH)")
    print("=" * 72)

    for sev in ["CRITICAL", "HIGH"]:
        sev_findings = [f for f in all_findings if f["severity"] == sev]
        if not sev_findings:
            continue
        print(f"\n--- {sev} ({len(sev_findings)}) ---")
        for i, f in enumerate(sev_findings, 1):
            print(f"\n  [{f['bug_class']}] #{i}: {f['type']}")
            for k, v in f.items():
                if k in ("bug_class", "severity", "type"):
                    continue
                if isinstance(v, list) and len(v) > 5:
                    print(f"    {k}: [{', '.join(str(x) for x in v[:5])}  ... +{len(v) - 5} more]")
                elif isinstance(v, dict):
                    print(f"    {k}:")
                    for kk, vv in v.items():
                        print(f"      {kk}: {vv}")
                else:
                    print(f"    {k}: {v}")

    # --- Save JSON report ---
    report_path = BASE / "evidence_pack" / "analysis" / "scenario_pipeline_system_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(
            {
                "summary": {
                    "total_findings": len(all_findings),
                    "by_severity": dict(severity_counts),
                    "by_bug_class": dict(bug_counts),
                    "actionable": total_issues,
                },
                "findings": all_findings,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nFull report saved: {report_path}")

    return 1 if total_issues > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
