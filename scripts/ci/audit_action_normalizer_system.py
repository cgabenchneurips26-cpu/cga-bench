#!/usr/bin/env python3
"""System-wide Action Normalizer Duplication Audit

Checks 4 layers of the action normalizer problem:
  L1: CPG Graph synonym action IDs (same canonical, different raw IDs)
  L2: DIRECT_MAPPINGS duplicate keys (Python dict shadowing)
  L3: Circular / non-convergent aliases
  L4: Scoring impact — do synonym pairs produce different violation verdicts?

Usage:
    PYTHONPATH=. python scripts/ci/audit_action_normalizer_system.py
"""

from __future__ import annotations

import ast
import collections
import json
from pathlib import Path
import sys

import yaml

# ---------------------------------------------------------------------------
# Layer 1: CPG Graph Synonym Detection
# ---------------------------------------------------------------------------


def audit_l1_graph_synonyms(
    graphs_dir: Path,
    normalizer,
) -> list[dict]:
    """Scan all CPG graphs for action IDs that normalize to the same canonical form."""
    findings: list[dict] = []

    for yaml_path in sorted(graphs_dir.glob("*.yaml")):
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        graph_name = yaml_path.stem
        nodes = data.get("nodes", {})
        if isinstance(nodes, list):
            # Some graphs might use list format
            nodes_iter = enumerate(nodes)
        else:
            nodes_iter = nodes.items()

        # Collect all action IDs per node, and graph-wide
        graph_wide_actions: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
        # canonical -> [(raw_id, node_id), ...]

        for node_id, node_data in nodes_iter:
            if not isinstance(node_data, dict):
                continue

            node_actions: list[str] = []
            for key in ("allowed_actions", "mandatory_actions", "forbidden_actions"):
                acts = node_data.get(key, [])
                if isinstance(acts, list):
                    node_actions.extend(acts)
                elif isinstance(acts, dict):
                    node_actions.extend(acts.keys())

            # Check within this node
            canonical_map: dict[str, list[str]] = collections.defaultdict(list)
            for raw_id in node_actions:
                canonical = normalizer.normalize(str(raw_id))
                canonical_map[canonical].append(str(raw_id))
                graph_wide_actions[canonical].append((str(raw_id), str(node_id)))

            # Flag intra-node synonyms
            for canonical, raw_ids in canonical_map.items():
                unique_raws = sorted(set(raw_ids))
                if len(unique_raws) > 1:
                    findings.append(
                        {
                            "layer": "L1",
                            "severity": "HIGH",
                            "type": "intra_node_synonym",
                            "graph": graph_name,
                            "node": str(node_id),
                            "canonical": canonical,
                            "raw_ids": unique_raws,
                            "impact": "Same action counted twice in single node",
                        }
                    )

        # Flag cross-node synonyms (different raw IDs for same canonical across nodes)
        for canonical, entries in graph_wide_actions.items():
            unique_raws = sorted(set(raw for raw, _ in entries))
            if len(unique_raws) > 1:
                nodes_by_raw: dict[str, list[str]] = collections.defaultdict(list)
                for raw, nid in entries:
                    nodes_by_raw[raw].append(nid)
                # Only flag if not already caught as intra-node
                is_cross_only = True
                for nid_set in nodes_by_raw.values():
                    if len(set(nid_set)) > 1:
                        is_cross_only = False
                        break

                findings.append(
                    {
                        "layer": "L1",
                        "severity": "MEDIUM" if is_cross_only else "HIGH",
                        "type": "cross_node_synonym",
                        "graph": graph_name,
                        "canonical": canonical,
                        "raw_ids": unique_raws,
                        "nodes_per_raw": {r: sorted(set(ns)) for r, ns in nodes_by_raw.items()},
                        "impact": "Agent may use either form; omission check depends on normalizer",
                    }
                )

    return findings


# ---------------------------------------------------------------------------
# Layer 2: DIRECT_MAPPINGS Duplicate Key Detection (AST-based)
# ---------------------------------------------------------------------------


def audit_l2_duplicate_keys(normalizer_path: Path) -> list[dict]:
    """Parse action_normalizer.py AST to find duplicate dict keys."""
    findings: list[dict] = []

    source = normalizer_path.read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if "_MAPPINGS" not in target.id and "_DOMAIN" not in target.id:
                continue
            # Found a mapping dict assignment
            dict_name = target.id
            if not isinstance(node.value, ast.Dict):
                continue

            key_occurrences: dict[str, list[tuple[int, str]]] = collections.defaultdict(list)
            for k, v in zip(node.value.keys, node.value.values):
                if k is None:
                    continue
                if isinstance(k, ast.Constant):
                    key_str = str(k.value)
                    val_str = str(v.value) if isinstance(v, ast.Constant) else ast.dump(v)
                    key_occurrences[key_str].append((k.lineno, val_str))

            for key, occurrences in key_occurrences.items():
                if len(occurrences) > 1:
                    values = [v for _, v in occurrences]
                    unique_values = set(values)
                    findings.append(
                        {
                            "layer": "L2",
                            "severity": "HIGH" if len(unique_values) > 1 else "LOW",
                            "type": "duplicate_key",
                            "dict_name": dict_name,
                            "key": key,
                            "occurrences": [{"line": ln, "value": val} for ln, val in occurrences],
                            "shadowed": len(unique_values) > 1,
                            "effective_value": occurrences[-1][1],
                            "impact": (
                                f"Key '{key}' appears {len(occurrences)}x with DIFFERENT values — "
                                f"Python keeps last: '{occurrences[-1][1]}'"
                                if len(unique_values) > 1
                                else f"Key '{key}' appears {len(occurrences)}x with SAME value (harmless)"
                            ),
                        }
                    )

    return findings


# ---------------------------------------------------------------------------
# Layer 3: Circular / Non-Convergent Alias Detection
# ---------------------------------------------------------------------------


def audit_l3_circular_aliases(normalizer) -> list[dict]:
    """Check for A->B, B->A circular aliases and non-convergent pairs."""
    findings: list[dict] = []
    dm = normalizer.config.direct_mappings

    # Check all keys: normalize(k) = v1, normalize(v1) = v2
    # If v2 != v1, the mapping doesn't converge in 1 step
    checked_pairs: set[tuple[str, str]] = set()

    for input_key, mapped_value in dm.items():
        pair = tuple(sorted([input_key, mapped_value]))
        if pair in checked_pairs:
            continue
        checked_pairs.add(pair)

        # Normalize both sides
        norm_input = normalizer.normalize(input_key)
        norm_mapped = normalizer.normalize(mapped_value)

        if norm_input != norm_mapped:
            # Non-convergent: normalizing the two sides gives different results
            # Check if it's circular
            is_circular = (
                mapped_value in dm
                and dm.get(mapped_value) != mapped_value
                and normalizer.normalize(dm.get(mapped_value, "")) != norm_mapped
            )

            findings.append(
                {
                    "layer": "L3",
                    "severity": "HIGH" if is_circular else "MEDIUM",
                    "type": "circular_alias" if is_circular else "non_convergent",
                    "input": input_key,
                    "direct_mapping_target": mapped_value,
                    "normalize(input)": norm_input,
                    "normalize(target)": norm_mapped,
                    "are_aliases_result": normalizer.are_aliases(input_key, mapped_value),
                    "impact": (
                        "Circular: A->B->C where normalize(A) != normalize(B). "
                        "are_aliases() returns False for semantically identical actions"
                    ),
                }
            )

    # Also check synonym groups for convergence
    for canonical, synonyms in normalizer.config.synonym_groups.items():
        for syn in synonyms:
            norm_syn = normalizer.normalize(syn)
            norm_can = normalizer.normalize(canonical)
            if norm_syn != norm_can:
                findings.append(
                    {
                        "layer": "L3",
                        "severity": "MEDIUM",
                        "type": "synonym_non_convergent",
                        "synonym_group_canonical": canonical,
                        "synonym": syn,
                        "normalize(synonym)": norm_syn,
                        "normalize(canonical)": norm_can,
                        "impact": "Synonym doesn't resolve to its declared canonical form",
                    }
                )

    return findings


# ---------------------------------------------------------------------------
# Layer 4: Scoring Impact Analysis
# ---------------------------------------------------------------------------


def audit_l4_scoring_impact(
    l1_findings: list[dict],
    normalizer,
) -> list[dict]:
    """For each L1 synonym pair, check if ViolationExtractor would produce
    different results depending on which raw ID is used.
    """
    findings: list[dict] = []

    for f in l1_findings:
        if f["type"] not in ("intra_node_synonym", "cross_node_synonym"):
            continue

        raw_ids = f["raw_ids"]
        canonical = f["canonical"]

        # Check: does each raw_id normalize to the same canonical?
        norm_results = {}
        for raw_id in raw_ids:
            norm_results[raw_id] = normalizer.normalize(raw_id)

        unique_norms = set(norm_results.values())

        if len(unique_norms) > 1:
            findings.append(
                {
                    "layer": "L4",
                    "severity": "CRITICAL",
                    "type": "scoring_divergence",
                    "graph": f["graph"],
                    "raw_ids": raw_ids,
                    "normalizations": norm_results,
                    "impact": (
                        "SCORING AFFECTED: These graph action IDs normalize to DIFFERENT "
                        "canonical forms. ViolationExtractor will not recognize them as "
                        "the same action. Mandatory action checked against one form will "
                        "NOT match the other, causing false OMISSION violations."
                    ),
                }
            )
        else:
            findings.append(
                {
                    "layer": "L4",
                    "severity": "OK",
                    "type": "scoring_safe",
                    "graph": f["graph"],
                    "raw_ids": raw_ids,
                    "canonical": list(unique_norms)[0],
                    "impact": "Normalizer converges — scoring unaffected",
                }
            )

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    graphs_dir = base / "cpg_model" / "graphs"
    normalizer_path = base / "assessor_core" / "action_normalizer.py"

    # Initialize normalizer
    sys.path.insert(0, str(base))
    sys.path.insert(0, str(base.parent))
    from cga_bench.assessor_core.action_normalizer import ActionNormalizer

    normalizer = ActionNormalizer()  # Default config

    print("=" * 72)
    print("ACTION NORMALIZER SYSTEM-WIDE AUDIT")
    print("=" * 72)

    all_findings: list[dict] = []

    # --- L1 ---
    print("\n[L1] Scanning 25 CPG graphs for synonym action IDs...")
    l1 = audit_l1_graph_synonyms(graphs_dir, normalizer)
    all_findings.extend(l1)
    l1_high = [f for f in l1 if f["severity"] == "HIGH"]
    l1_med = [f for f in l1 if f["severity"] == "MEDIUM"]
    print(f"     Found {len(l1)} synonym pairs ({len(l1_high)} HIGH, {len(l1_med)} MEDIUM)")

    # --- L2 ---
    print("\n[L2] Checking DIRECT_MAPPINGS for duplicate keys (AST parse)...")
    l2 = audit_l2_duplicate_keys(normalizer_path)
    all_findings.extend(l2)
    l2_high = [f for f in l2 if f["severity"] == "HIGH"]
    l2_low = [f for f in l2 if f["severity"] == "LOW"]
    print(f"     Found {len(l2)} duplicate keys ({len(l2_high)} shadowed/HIGH, {len(l2_low)} harmless/LOW)")

    # --- L3 ---
    print("\n[L3] Checking for circular / non-convergent aliases...")
    l3 = audit_l3_circular_aliases(normalizer)
    all_findings.extend(l3)
    l3_high = [f for f in l3 if f["severity"] == "HIGH"]
    l3_med = [f for f in l3 if f["severity"] == "MEDIUM"]
    print(f"     Found {len(l3)} non-convergent pairs ({len(l3_high)} circular/HIGH, {len(l3_med)} MEDIUM)")

    # --- L4 ---
    print("\n[L4] Scoring impact analysis for L1 synonym pairs...")
    l4 = audit_l4_scoring_impact(l1, normalizer)
    all_findings.extend(l4)
    l4_crit = [f for f in l4 if f["severity"] == "CRITICAL"]
    l4_ok = [f for f in l4 if f["severity"] == "OK"]
    print(f"     {len(l4_crit)} CRITICAL (scoring affected), {len(l4_ok)} OK (normalizer converges)")

    # --- Summary ---
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)

    severity_counts = collections.Counter(f["severity"] for f in all_findings)
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "OK"]:
        if severity_counts.get(sev, 0) > 0:
            print(f"  {sev:10s}: {severity_counts[sev]}")

    total_issues = severity_counts.get("CRITICAL", 0) + severity_counts.get("HIGH", 0)
    print(f"\n  Total actionable issues (CRITICAL+HIGH): {total_issues}")

    # --- Detailed output ---
    print("\n" + "=" * 72)
    print("DETAILED FINDINGS")
    print("=" * 72)

    for sev in ["CRITICAL", "HIGH", "MEDIUM"]:
        sev_findings = [f for f in all_findings if f["severity"] == sev]
        if not sev_findings:
            continue
        print(f"\n--- {sev} ({len(sev_findings)}) ---")
        for i, f in enumerate(sev_findings, 1):
            print(f"\n  [{f['layer']}] #{i}: {f['type']}")
            for k, v in f.items():
                if k in ("layer", "severity", "type"):
                    continue
                if isinstance(v, dict):
                    print(f"    {k}:")
                    for kk, vv in v.items():
                        print(f"      {kk}: {vv}")
                elif isinstance(v, list) and len(v) > 3:
                    print(f"    {k}: [{v[0]}, {v[1]}, ... +{len(v) - 2} more]")
                else:
                    print(f"    {k}: {v}")

    # --- Save JSON report ---
    report_path = base / "evidence_pack" / "analysis" / "action_normalizer_system_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(
            {
                "summary": {
                    "total_findings": len(all_findings),
                    "by_severity": dict(severity_counts),
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
