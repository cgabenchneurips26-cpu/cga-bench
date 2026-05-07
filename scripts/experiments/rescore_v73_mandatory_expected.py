"""Rescore V7.3 SGSC verdict matrix with expected_actions := graph.mandatory_actions union.

Bug B fix (per docs/critical_review/v73_p1_p4_diagnosis_20260506.md):
  Original SGSC compiler sets expected_actions = [seed source_atoms] (mean 2.4 actions).
  This causes 81% AC=0 and 81% MAB=0 collapse on V7.3.

This script recomputes AC/MAB using the broader graph.mandatory_actions union for
each scenario's CPG graph. Keeps c2_score, v4_hard, dxem unchanged.

Usage:
    PYTHONPATH=. python scripts/experiments/rescore_v73_mandatory_expected.py \\
        --vmatrix evidence_pack/analysis/verdict_matrix_v7_3_with_allmh_typed.json \\
        --results-dir results/v73_full_with_allmh \\
        --scenarios-dir configs/scenarios \\
        --graphs-dir cpg_model/graphs \\
        --output evidence_pack/analysis/verdict_matrix_v7_3_with_allmh_typed_mandfix.json
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import sys
import time

import yaml

AC_COVERAGE_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5


def load_graphs(graphs_dir: str) -> dict:
    out = {}
    paths = glob.glob(f"{graphs_dir}/*.yaml") + glob.glob(f"{graphs_dir}/auto/*.yaml")
    for gp in paths:
        try:
            g = yaml.safe_load(open(gp))
            gid = g.get("graph_id")
            if not gid:
                continue
            mand = set()
            allowed = set()
            for nid, node in (g.get("nodes") or {}).items():
                for a in node.get("mandatory_actions") or []:
                    mand.add(a)
                for a in node.get("allowed_actions") or []:
                    allowed.add(a)
            out[gid] = {"mandatory": mand, "allowed": allowed}
        except Exception:
            continue
    return out


def load_scenario_to_graph(scenarios_dir: str) -> dict:
    out = {}
    for sp in glob.glob(f"{scenarios_dir}/**/*scenarios.yaml", recursive=True):
        try:
            d = yaml.safe_load(open(sp))
            if isinstance(d, dict) and "scenarios" in d:
                for sid, sc in d["scenarios"].items():
                    out[sid] = sc.get("guideline_graph")
        except Exception:
            continue
    return out


def index_results(results_dir: str) -> dict:
    out = {}
    for jp in glob.glob(f"{results_dir}/**/*.json", recursive=True):
        try:
            d = json.loads(open(jp).read())
            sid = d.get("scenario_id")
            ri = d.get("run_index")
            mdl = Path(jp).parent.name
            if sid is None or ri is None:
                continue
            actions = d.get("actions") or []
            agent = {a.get("action_id") for a in actions if isinstance(a, dict)}
            agent.discard(None)
            out[(sid, ri, mdl)] = agent
        except Exception:
            continue
    return out


def f1_score(p_set: set, e_set: set) -> float:
    if not e_set:
        return 0.0
    inter = len(p_set & e_set)
    p = inter / len(p_set) if p_set else 0.0
    r = inter / len(e_set)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def coverage(p_set: set, e_set: set) -> float:
    if not e_set:
        return 1.0
    return len(p_set & e_set) / len(e_set)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vmatrix", required=True)
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--scenarios-dir", default="configs/scenarios")
    ap.add_argument("--graphs-dir", default="cpg_model/graphs")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    t0 = time.time()
    print(f"loading {args.vmatrix}")
    vm = json.loads(open(args.vmatrix).read())
    pe = vm["per_episode"]
    print(f"  per_episode: {len(pe)}")

    print("indexing graphs")
    graphs = load_graphs(args.graphs_dir)
    print(f"  graphs: {len(graphs)}")

    print("indexing scenarios")
    scen = load_scenario_to_graph(args.scenarios_dir)
    print(f"  scenarios: {len(scen)}")

    print("indexing results agent actions")
    agent_idx = index_results(args.results_dir)
    print(f"  agent_idx: {len(agent_idx)}")

    matched = 0
    missing_graph = 0
    missing_actions = 0
    for ep in pe:
        sid = ep["scenario_id"]
        ri = ep["run_index"]
        mdl = ep["model_dir"]
        gid = scen.get(sid)
        if gid is None or gid not in graphs:
            missing_graph += 1
            continue
        agent = agent_idx.get((sid, ri, mdl))
        if agent is None:
            missing_actions += 1
            continue
        mand = graphs[gid]["mandatory"]
        if not mand:
            ep["ac_proxy_mandfix"] = ep.get("ac_proxy", False)
            ep["mab_proxy_mandfix"] = ep.get("mab_proxy", False)
            ep["action_coverage_mandfix"] = ep.get("action_coverage", 0.0)
            ep["mab_f1_mandfix"] = ep.get("mab_f1", 0.0)
            continue
        cov = coverage(agent, mand)
        f1 = f1_score(agent, mand)
        ep["ac_proxy_mandfix"] = cov >= AC_COVERAGE_THRESHOLD
        ep["mab_proxy_mandfix"] = f1 >= MAB_F1_THRESHOLD
        ep["action_coverage_mandfix"] = round(cov, 4)
        ep["mab_f1_mandfix"] = round(f1, 4)
        matched += 1

    md = vm.setdefault("metadata", {})
    md["mandfix"] = {
        "applied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "matched": matched,
        "missing_graph": missing_graph,
        "missing_actions": missing_actions,
        "definition": "AC/MAB recomputed against graph.mandatory_actions union (Bug B fix)",
    }

    with open(args.output, "w") as f:
        json.dump(vm, f, indent=2)
    print(f"matched={matched} missing_graph={missing_graph} missing_actions={missing_actions}")
    print(f"saved → {args.output}  ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
