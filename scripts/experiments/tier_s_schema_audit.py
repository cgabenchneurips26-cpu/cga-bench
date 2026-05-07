"""Tier S schema audit (Phase B-1) — validate 31 auto graphs + 535 scenarios.

Read-only sanity check: confirms every Tier S graph YAML and scenario YAML
parses, has the expected schema fields, and that scenario `guideline_graph`
references resolve to actual graph files. Does NOT execute any evaluation.

Schema requirements (graphs)
----------------------------
    graph_id        : str
    guideline_name  : str
    version         : str (recommended)
    entry_node      : str — must be a key in `nodes`
    nodes           : dict[str, NodeSchema]
        node_id, node_type, name, description, precondition,
        mandatory_actions: list[str],
        allowed_actions:  list[str],
        forbidden_actions: list[str],
        deadlines:        dict[str, int]    (optional; values minutes)

Schema requirements (scenarios)
-------------------------------
    scenarios : dict[str, ScenarioSchema]
        scenario_id, description, guideline_graph,
        patient: dict (with at least age, sex, vitals),
        expected_actions: list[str]

Output
------
    evidence_pack/tier_s/tier_s_schema_audit.json
        {
            "graphs": {graph_id: {"path", "errors": [..], "warnings": [..]}, ...},
            "scenarios": {scenario_id: {"path", "errors": [..], "warnings": [..]}, ...},
            "summary": {
                "n_graphs_total": 31,
                "n_graphs_pass": int,
                "n_graphs_fail": int,
                "n_scenarios_total": 535,
                "n_scenarios_pass": int,
                "n_scenarios_fail": int,
                "graphs_with_errors": [...],
                "scenarios_with_errors": [...]
            }
        }

Usage
-----
    PYTHONPATH=..:. /home/anonymous-org/anaconda3/bin/python3.13 \
        scripts/experiments/tier_s_schema_audit.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GRAPHS_DIR = REPO_ROOT / "cpg_model" / "graphs" / "auto"
SCENARIOS_DIR = REPO_ROOT / "configs" / "scenarios" / "auto_v2"
OUTPUT = REPO_ROOT / "evidence_pack" / "tier_s" / "tier_s_schema_audit.json"

REQUIRED_GRAPH_FIELDS = ("graph_id", "guideline_name", "entry_node", "nodes")
REQUIRED_NODE_FIELDS = ("node_id", "node_type", "name", "mandatory_actions", "allowed_actions", "forbidden_actions")
REQUIRED_SCENARIO_FIELDS = ("scenario_id", "description", "guideline_graph", "patient", "expected_actions")
REQUIRED_PATIENT_FIELDS = ("age", "sex")


def validate_graph(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return {"path": str(path.relative_to(REPO_ROOT)), "errors": [f"yaml_parse_error: {e}"], "warnings": []}
    except OSError as e:
        return {"path": str(path.relative_to(REPO_ROOT)), "errors": [f"read_error: {e}"], "warnings": []}

    if not isinstance(data, dict):
        return {"path": str(path.relative_to(REPO_ROOT)), "errors": ["root_not_dict"], "warnings": []}

    for f in REQUIRED_GRAPH_FIELDS:
        if f not in data:
            errors.append(f"missing_top_level_field:{f}")

    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        errors.append("nodes_not_dict")
    else:
        entry = data.get("entry_node")
        if entry and entry not in nodes:
            errors.append(f"entry_node_not_in_nodes:{entry}")

        for node_key, node in nodes.items():
            if not isinstance(node, dict):
                errors.append(f"node_{node_key}_not_dict")
                continue
            for nf in REQUIRED_NODE_FIELDS:
                if nf not in node:
                    errors.append(f"node_{node_key}_missing:{nf}")
            for list_field in ("mandatory_actions", "allowed_actions", "forbidden_actions"):
                v = node.get(list_field)
                if v is not None and not isinstance(v, list):
                    errors.append(f"node_{node_key}_{list_field}_not_list")
            deadlines = node.get("deadlines")
            if deadlines is not None and not isinstance(deadlines, dict):
                errors.append(f"node_{node_key}_deadlines_not_dict")

    # Warnings: missing nice-to-have metadata
    if not data.get("version"):
        warnings.append("missing_version")
    if not data.get("metadata"):
        warnings.append("missing_metadata")

    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "graph_id": data.get("graph_id") if isinstance(data, dict) else None,
        "n_nodes": len(nodes) if isinstance(nodes, dict) else 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_scenarios_file(path: Path, known_graph_ids: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (per-scenario records, file-level errors)."""
    file_errors: list[str] = []
    records: list[dict[str, Any]] = []
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return [], [f"yaml_parse_error: {e}"]
    except OSError as e:
        return [], [f"read_error: {e}"]

    if not isinstance(data, dict) or not isinstance(data.get("scenarios"), dict):
        return [], ["scenarios_root_missing_or_invalid"]

    for sid, sc in data["scenarios"].items():
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(sc, dict):
            errors.append("scenario_not_dict")
            records.append(
                {"scenario_id": sid, "path": str(path.relative_to(REPO_ROOT)), "errors": errors, "warnings": warnings}
            )
            continue
        for f in REQUIRED_SCENARIO_FIELDS:
            if f not in sc:
                errors.append(f"missing_field:{f}")
        gid = sc.get("guideline_graph")
        if gid and gid not in known_graph_ids:
            errors.append(f"unknown_guideline_graph:{gid}")
        patient = sc.get("patient")
        if isinstance(patient, dict):
            for pf in REQUIRED_PATIENT_FIELDS:
                if pf not in patient:
                    errors.append(f"patient_missing:{pf}")
            if "vitals" not in patient:
                warnings.append("patient_missing_vitals")
        elif patient is not None:
            errors.append("patient_not_dict")
        ea = sc.get("expected_actions")
        if ea is not None and not isinstance(ea, list):
            errors.append("expected_actions_not_list")
        elif isinstance(ea, list) and not ea:
            warnings.append("expected_actions_empty")
        records.append(
            {
                "scenario_id": sid,
                "path": str(path.relative_to(REPO_ROOT)),
                "guideline_graph": gid,
                "errors": errors,
                "warnings": warnings,
            }
        )
    return records, file_errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphs-dir", type=Path, default=GRAPHS_DIR)
    parser.add_argument("--scenarios-dir", type=Path, default=SCENARIOS_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Auditing Tier S graphs at {args.graphs_dir}")

    graph_records: dict[str, dict[str, Any]] = {}
    graph_yamls = sorted(args.graphs_dir.glob("*.yaml"))
    known_graph_ids: set[str] = set()
    for p in graph_yamls:
        rec = validate_graph(p)
        gid = rec.get("graph_id") or p.stem
        graph_records[gid] = rec
        if not rec["errors"]:
            known_graph_ids.add(gid)
    print(f"  graphs scanned: {len(graph_records)}")

    print(f"[{time.strftime('%H:%M:%S')}] Auditing Tier S scenarios at {args.scenarios_dir}")
    scenario_records: dict[str, dict[str, Any]] = {}
    file_errors_by_path: dict[str, list[str]] = {}
    scenario_yamls = sorted(args.scenarios_dir.glob("*.yaml"))
    for p in scenario_yamls:
        recs, file_errs = validate_scenarios_file(p, known_graph_ids)
        if file_errs:
            file_errors_by_path[str(p.relative_to(REPO_ROOT))] = file_errs
        for r in recs:
            scenario_records[r["scenario_id"]] = r
    print(f"  scenarios scanned: {len(scenario_records)}  (file-level errors: {len(file_errors_by_path)})")

    # Summary
    n_graphs_pass = sum(1 for r in graph_records.values() if not r["errors"])
    n_graphs_fail = len(graph_records) - n_graphs_pass
    n_scen_pass = sum(1 for r in scenario_records.values() if not r["errors"])
    n_scen_fail = len(scenario_records) - n_scen_pass
    graphs_with_errors = sorted(g for g, r in graph_records.items() if r["errors"])
    scenarios_with_errors = sorted(s for s, r in scenario_records.items() if r["errors"])

    print(f"\n=== Schema Audit Summary ===")
    print(f"  Graphs:    {n_graphs_pass}/{len(graph_records)} pass  ({n_graphs_fail} fail)")
    print(f"  Scenarios: {n_scen_pass}/{len(scenario_records)} pass  ({n_scen_fail} fail)")
    if graphs_with_errors:
        print(f"  Graph errors ({len(graphs_with_errors)}):")
        for g in graphs_with_errors[:10]:
            print(f"    - {g}: {graph_records[g]['errors']}")
        if len(graphs_with_errors) > 10:
            print(f"    ... and {len(graphs_with_errors) - 10} more")
    if scenarios_with_errors:
        print(f"  Scenario errors ({len(scenarios_with_errors)}):")
        for s in scenarios_with_errors[:5]:
            print(f"    - {s}: {scenario_records[s]['errors']}")
        if len(scenarios_with_errors) > 5:
            print(f"    ... and {len(scenarios_with_errors) - 5} more")

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "graphs_dir": str(args.graphs_dir.relative_to(REPO_ROOT)),
        "scenarios_dir": str(args.scenarios_dir.relative_to(REPO_ROOT)),
        "summary": {
            "n_graphs_total": len(graph_records),
            "n_graphs_pass": n_graphs_pass,
            "n_graphs_fail": n_graphs_fail,
            "n_scenarios_total": len(scenario_records),
            "n_scenarios_pass": n_scen_pass,
            "n_scenarios_fail": n_scen_fail,
            "graphs_with_errors": graphs_with_errors,
            "scenarios_with_errors_count": len(scenarios_with_errors),
            "file_errors_by_path": file_errors_by_path,
        },
        "graphs": graph_records,
        "scenarios": scenario_records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, default=str) + "\n")
    elapsed = time.time() - t0
    print(f"\n[{time.strftime('%H:%M:%S')}] Saved: {args.output}  ({elapsed:.1f}s)")
    return 0 if (n_graphs_fail == 0 and n_scen_fail == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
