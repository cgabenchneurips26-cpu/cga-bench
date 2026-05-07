
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""v3_p7_forbidden_exposure.py — Forbidden constraint exposure analysis.

Analyzes all forbidden constraints across CGA-Bench:
- Which are triggered by agents (commission violations)
- Which are never tested (zero-exposure)
- Which are mandatory-yet-conditional (appear as mandatory elsewhere)
- Trap identification (same action mandatory in one node, forbidden in another)

Data sources:
  - cpg_model/graphs/*.yaml (14 graphs)
  - configs/scenarios/*.yaml (16 scenario files)
  - results/clean_slate_rescored/{model}/*.json (180 rescored episodes)
  - results/clean_slate_20260331_210910/{model}/*.json (180 original episodes)

Run: PYTHONPATH=. python scripts/experiments/v3_p7_forbidden_exposure.py
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
from pathlib import Path
import textwrap

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"
SCENARIOS_DIR = ROOT / "configs" / "scenarios"
RESCORED_DIR = ROOT / "results" / "clean_slate_rescored"
ORIGINAL_DIR = ROOT / "results" / "clean_slate_20260331_210910"
OUTPUT_DIR = ROOT / "evidence_pack" / "analysis"
TABLES_DIR = ROOT / "evidence_pack" / "tables"

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_DISPLAY = {
    "oss120b": "Qwen2.5-72B",
    "qwen27b": "Qwen2.5-27B",
    "qwen35b": "Qwen2.5-35B",
    "qwen4b": "Qwen2.5-4B",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ForbiddenConstraint:
    graph_id: str
    node_id: str
    action_id: str
    source: str  # "graph_node" or "scenario_override"
    scenario_id: str  # which scenario surfaces this graph
    recommendation_class: str
    evidence_level: str
    # populated during analysis
    classification: str = ""  # zero_exposure | triggered | mandatory_yet_conditional | attempted_but_correct
    attempts: int = 0  # how many episodes attempted this action
    commissions: int = 0  # how many resulted in commission violations
    models_attempted: list = field(default_factory=list)
    is_also_mandatory: bool = False
    mandatory_in_nodes: list = field(default_factory=list)


@dataclass
class EpisodeRecord:
    scenario_id: str
    model: str
    run_index: int
    actions_taken: list[str]
    forbidden_actions: list[str]
    commission_violations: list[str]  # action_ids from commission violations


# ---------------------------------------------------------------------------
# Step 1: Load CPG graphs
# ---------------------------------------------------------------------------


def load_graphs() -> dict[str, dict]:
    """Returns {file_stem: {node_id: node_dict}}.

    Keyed by file stem (e.g. 'aha_chest_pain') so it matches
    the `guideline_graph` field in scenario configs.  The internal
    graph_id field (e.g. 'aha_chest_pain_evaluation') is stored
    inside each node dict as '__graph_id__' for display purposes.
    """
    graphs: dict[str, dict] = {}
    for path in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(path) as f:
            raw = yaml.safe_load(f)
        if not raw:
            continue
        nodes = raw.get("nodes", {})
        internal_graph_id = raw.get("graph_id", path.stem)
        # Tag each node with the internal graph_id for reporting
        for node in nodes.values():
            if isinstance(node, dict):
                node["__graph_id__"] = internal_graph_id
        graphs[path.stem] = nodes
    return graphs


# ---------------------------------------------------------------------------
# Step 2: Load scenario configs
# ---------------------------------------------------------------------------


def load_scenarios() -> dict[str, dict]:
    """Returns {scenario_id: scenario_dict} with guideline_graph populated."""
    scenarios: dict[str, dict] = {}

    def _ingest_section(section: dict) -> None:
        if not isinstance(section, dict):
            return
        for sid, sc in section.items():
            if isinstance(sc, dict):
                scenarios[sid] = sc

    for path in sorted(SCENARIOS_DIR.glob("*.yaml")):
        with open(path) as f:
            raw = yaml.safe_load(f)
        if not raw:
            continue
        for key in ("scenarios", "trap_scenarios"):
            _ingest_section(raw.get(key, {}))

    return scenarios


# ---------------------------------------------------------------------------
# Step 3: Build forbidden constraint inventory
# ---------------------------------------------------------------------------


def build_constraint_inventory(
    graphs: dict[str, dict],
    scenarios: dict[str, dict],
) -> list[ForbiddenConstraint]:
    """One ForbiddenConstraint entry per (scenario_id, action_id) pair."""
    # Map: graph_id -> set of all mandatory actions across all nodes
    graph_mandatory: dict[str, set[str]] = {}
    # Map: graph_id -> {action_id: [node_ids where mandatory]}
    graph_mandatory_nodes: dict[str, dict[str, list[str]]] = {}
    for graph_id, nodes in graphs.items():
        mandatory_set: set[str] = set()
        mandatory_nodes: dict[str, list[str]] = defaultdict(list)
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            for act in node.get("mandatory_actions", []) or []:
                mandatory_set.add(act)
                mandatory_nodes[act].append(node_id)
        graph_mandatory[graph_id] = mandatory_set
        graph_mandatory_nodes[graph_id] = dict(mandatory_nodes)

    # Map scenario_id -> graph_id (only scenarios that appeared in episodes)
    scenario_graph: dict[str, str] = {}
    for sid, sc in scenarios.items():
        g = sc.get("guideline_graph")
        if g:
            scenario_graph[sid] = g

    constraints: list[ForbiddenConstraint] = []
    seen: set[tuple[str, str]] = set()  # (scenario_id, action_id)

    for scenario_id, sc in scenarios.items():
        graph_id = sc.get("guideline_graph", "")
        if not graph_id or graph_id not in graphs:
            continue

        nodes = graphs[graph_id]
        # Collect scenario-level forbidden override
        scenario_override: list[str] = sc.get("forbidden_actions", []) or []

        # --- From graph nodes ---
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            rec_class = node.get("recommendation_class", "")
            ev_level = node.get("evidence_level", "")
            for act in node.get("forbidden_actions", []) or []:
                key = (scenario_id, act)
                if key in seen:
                    continue
                seen.add(key)
                is_also_mandatory = act in graph_mandatory.get(graph_id, set())
                mandatory_nodes_list = graph_mandatory_nodes.get(graph_id, {}).get(act, [])
                constraints.append(
                    ForbiddenConstraint(
                        graph_id=graph_id,
                        node_id=node_id,
                        action_id=act,
                        source="graph_node",
                        scenario_id=scenario_id,
                        recommendation_class=str(rec_class),
                        evidence_level=str(ev_level),
                        is_also_mandatory=is_also_mandatory,
                        mandatory_in_nodes=mandatory_nodes_list,
                    )
                )

        # --- From scenario-level overrides ---
        for act in scenario_override:
            key = (scenario_id, act)
            if key in seen:
                continue
            seen.add(key)
            is_also_mandatory = act in graph_mandatory.get(graph_id, set())
            mandatory_nodes_list = graph_mandatory_nodes.get(graph_id, {}).get(act, [])
            constraints.append(
                ForbiddenConstraint(
                    graph_id=graph_id,
                    node_id="scenario_override",
                    action_id=act,
                    source="scenario_override",
                    scenario_id=scenario_id,
                    recommendation_class="",
                    evidence_level="",
                    is_also_mandatory=is_also_mandatory,
                    mandatory_in_nodes=mandatory_nodes_list,
                )
            )

    return constraints


# ---------------------------------------------------------------------------
# Step 4: Load episode data
# ---------------------------------------------------------------------------


def load_episodes() -> list[EpisodeRecord]:
    """Load original episodes (actions taken) merged with rescored violations."""
    # original episodes: actions taken + forbidden_actions per episode
    orig_map: dict[str, EpisodeRecord] = {}
    for model in MODELS:
        model_dir = ORIGINAL_DIR / model
        if not model_dir.is_dir():
            continue
        for path in sorted(model_dir.glob("*.json")):
            with open(path) as f:
                d = json.load(f)
            sid = d.get("scenario_id") or ""
            if not sid:
                continue
            run_idx = d.get("run_index", 0)
            actions_taken = [
                a.get("action_id", "") for a in (d.get("actions") or []) if isinstance(a, dict) and a.get("action_id")
            ]
            forbidden = d.get("forbidden_actions") or []
            key = f"{model}::{sid}::{run_idx}"
            orig_map[key] = EpisodeRecord(
                scenario_id=sid,
                model=model,
                run_index=run_idx,
                actions_taken=actions_taken,
                forbidden_actions=forbidden,
                commission_violations=[],
            )

    # rescored episodes: commission violations
    for model in MODELS:
        model_dir = RESCORED_DIR / model
        if not model_dir.is_dir():
            continue
        for path in sorted(model_dir.glob("*.json")):
            with open(path) as f:
                d = json.load(f)
            sid = d.get("scenario_id") or ""
            if not sid:
                continue
            run_idx = d.get("run_index", 0)
            key = f"{model}::{sid}::{run_idx}"
            commissions = [
                v.get("action_involved", "")
                for v in (d.get("new_violation_events") or [])
                if isinstance(v, dict) and v.get("violation_type") == "commission" and v.get("action_involved")
            ]
            if key in orig_map:
                orig_map[key].commission_violations = commissions
            else:
                # rescored exists but no original — create minimal record
                orig_map[key] = EpisodeRecord(
                    scenario_id=sid,
                    model=model,
                    run_index=run_idx,
                    actions_taken=[],
                    forbidden_actions=[],
                    commission_violations=commissions,
                )

    return list(orig_map.values())


# ---------------------------------------------------------------------------
# Step 5: Annotate constraints with exposure data
# ---------------------------------------------------------------------------


def annotate_exposure(
    constraints: list[ForbiddenConstraint],
    episodes: list[EpisodeRecord],
) -> None:
    """Mutates each constraint in-place with attempt/commission counts."""
    # Group episodes by scenario_id
    by_scenario: dict[str, list[EpisodeRecord]] = defaultdict(list)
    for ep in episodes:
        by_scenario[ep.scenario_id].append(ep)

    for fc in constraints:
        relevant = by_scenario.get(fc.scenario_id, [])
        if not relevant:
            # scenario not in episodes at all
            fc.attempts = 0
            fc.commissions = 0
            fc.models_attempted = []
            if fc.is_also_mandatory:
                fc.classification = "mandatory_yet_conditional"
            else:
                fc.classification = "zero_exposure"
            continue

        attempted_models: set[str] = set()
        total_attempts = 0
        total_commissions = 0

        for ep in relevant:
            if fc.action_id in ep.actions_taken:
                total_attempts += 1
                attempted_models.add(ep.model)
            if fc.action_id in ep.commission_violations:
                total_commissions += 1

        fc.attempts = total_attempts
        fc.commissions = total_commissions
        fc.models_attempted = sorted(attempted_models)

        # Classify by observed behavior (triggered takes highest precedence).
        # is_also_mandatory is tracked separately as a boolean flag; a constraint
        # can be BOTH mandatory_yet_conditional AND triggered (e.g. DKA insulin).
        if total_commissions > 0:
            if fc.is_also_mandatory:
                fc.classification = "triggered_mandatory_yet_conditional"
            else:
                fc.classification = "triggered"
        elif total_attempts > 0:
            fc.classification = "attempted_but_correct"
        elif fc.is_also_mandatory:
            fc.classification = "mandatory_yet_conditional"
        else:
            fc.classification = "zero_exposure"


# ---------------------------------------------------------------------------
# Step 6: Candidate trap identification across graphs
# ---------------------------------------------------------------------------


def find_candidate_traps(graphs: dict[str, dict]) -> list[dict]:
    """Find actions appearing as both mandatory and forbidden across different nodes."""
    traps = []

    for graph_id, nodes in graphs.items():
        mandatory_map: dict[str, list[str]] = defaultdict(list)
        forbidden_map: dict[str, list[str]] = defaultdict(list)

        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            for act in node.get("mandatory_actions", []) or []:
                mandatory_map[act].append(node_id)
            for act in node.get("forbidden_actions", []) or []:
                forbidden_map[act].append(node_id)

        overlap = set(mandatory_map.keys()) & set(forbidden_map.keys())
        for act in sorted(overlap):
            traps.append(
                {
                    "graph_id": graph_id,
                    "action_id": act,
                    "mandatory_in_nodes": mandatory_map[act],
                    "forbidden_in_nodes": forbidden_map[act],
                }
            )

    return traps


# ---------------------------------------------------------------------------
# Step 7: DKA insulin trap deep-dive
# ---------------------------------------------------------------------------


def analyze_dka_insulin_trap(
    constraints: list[ForbiddenConstraint],
    episodes: list[EpisodeRecord],
) -> dict:
    """Detailed analysis of start_insulin_infusion in dka_hypokalemia_trap."""
    TARGET_ACTION = "start_insulin_infusion"
    TARGET_SCENARIO = "dka_hypokalemia_trap"

    relevant_eps = [ep for ep in episodes if ep.scenario_id == TARGET_SCENARIO]
    total_episodes = len(relevant_eps)

    by_model: dict[str, dict] = {}
    for model in MODELS:
        model_eps = [ep for ep in relevant_eps if ep.model == model]
        triggered = sum(1 for ep in model_eps if TARGET_ACTION in ep.commission_violations)
        attempted = sum(1 for ep in model_eps if TARGET_ACTION in ep.actions_taken)
        by_model[MODEL_DISPLAY[model]] = {
            "episodes": len(model_eps),
            "attempted": attempted,
            "triggered_commission": triggered,
            "trigger_rate": round(triggered / len(model_eps), 3) if model_eps else 0.0,
        }

    total_triggered = sum(1 for ep in relevant_eps if TARGET_ACTION in ep.commission_violations)
    total_attempted = sum(1 for ep in relevant_eps if TARGET_ACTION in ep.actions_taken)

    # Cross-graph: is insulin mandatory in DKA nodes?
    graph_context = {
        "action": TARGET_ACTION,
        "scenario": TARGET_SCENARIO,
        "graph": "ada_dka_management",
        "mandatory_in_nodes": [
            "insulin_infusion_initiation",
            "insulin_management",
        ],
        "forbidden_in_nodes": [
            "potassium_replacement_first",
        ],
        "clinical_rationale": (
            "Insulin is the definitive treatment for DKA (mandatory in insulin_infusion_initiation). "
            "However, when potassium < 3.3 mEq/L, insulin drives K+ into cells, worsening "
            "hypokalemia and risking fatal cardiac arrhythmia. The ADA guideline therefore "
            "forbids insulin before potassium correction — creating a mandatory-yet-conditional trap."
        ),
    }

    return {
        "total_episodes": total_episodes,
        "total_attempted": total_attempted,
        "total_triggered": total_triggered,
        "overall_trigger_rate": round(total_triggered / total_episodes, 3) if total_episodes else 0.0,
        "by_model": by_model,
        "graph_context": graph_context,
    }


# ---------------------------------------------------------------------------
# Step 8: Summary statistics
# ---------------------------------------------------------------------------


def compute_summary(
    constraints: list[ForbiddenConstraint],
    episodes: list[EpisodeRecord],
    candidate_traps: list[dict],
) -> dict:
    total = len(constraints)
    # Deduplicate by (graph_id, action_id) for cross-scenario counting
    unique_pairs: set[tuple[str, str]] = {(fc.graph_id, fc.action_id) for fc in constraints}

    by_class: dict[str, int] = defaultdict(int)
    for fc in constraints:
        by_class[fc.classification] += 1

    scenario_ids_in_episodes = {ep.scenario_id for ep in episodes}
    testable = [fc for fc in constraints if fc.scenario_id in scenario_ids_in_episodes]
    testable_total = len(testable)
    testable_zero = sum(1 for fc in testable if fc.classification == "zero_exposure")
    # triggered includes both pure triggered and triggered_mandatory_yet_conditional
    testable_triggered = sum(
        1 for fc in testable if fc.classification in ("triggered", "triggered_mandatory_yet_conditional")
    )
    # mandatory_yet_conditional includes both pure myc and triggered_myc
    testable_myc = sum(
        1
        for fc in testable
        if fc.classification in ("mandatory_yet_conditional", "triggered_mandatory_yet_conditional")
    )
    testable_triggered_myc = sum(1 for fc in testable if fc.classification == "triggered_mandatory_yet_conditional")
    testable_abc = sum(1 for fc in testable if fc.classification == "attempted_but_correct")

    pct = lambda n: round(100.0 * n / testable_total, 1) if testable_total else 0.0

    return {
        "total_constraints": total,
        "unique_graph_action_pairs": len(unique_pairs),
        "by_scenario_classification": dict(by_class),
        "testable_constraints": testable_total,
        "zero_exposure": testable_zero,
        "zero_exposure_pct": pct(testable_zero),
        "triggered": testable_triggered,
        "triggered_pct": pct(testable_triggered),
        "triggered_mandatory_yet_conditional": testable_triggered_myc,
        "mandatory_yet_conditional": testable_myc,
        "mandatory_yet_conditional_pct": pct(testable_myc),
        "attempted_but_correct": testable_abc,
        "attempted_but_correct_pct": pct(testable_abc),
        "candidate_traps_in_graphs": len(candidate_traps),
        "total_episodes_analyzed": len(episodes),
    }


# ---------------------------------------------------------------------------
# Step 9: Build structured output
# ---------------------------------------------------------------------------


def build_output(
    constraints: list[ForbiddenConstraint],
    candidate_traps: list[dict],
    dka_trap: dict,
    summary: dict,
    episodes: list[EpisodeRecord],
    graphs: dict[str, dict],
) -> dict:
    scenario_ids_in_episodes = {ep.scenario_id for ep in episodes}

    # Per-scenario exposure table
    per_scenario: dict[str, dict] = {}
    for fc in constraints:
        if fc.scenario_id not in per_scenario:
            per_scenario[fc.scenario_id] = {
                "graph_id": fc.graph_id,
                "in_episodes": fc.scenario_id in scenario_ids_in_episodes,
                "constraints": [],
            }
        per_scenario[fc.scenario_id]["constraints"].append(
            {
                "action_id": fc.action_id,
                "node_id": fc.node_id,
                "source": fc.source,
                "recommendation_class": fc.recommendation_class,
                "evidence_level": fc.evidence_level,
                "classification": fc.classification,
                "attempts": fc.attempts,
                "commissions": fc.commissions,
                "models_attempted": fc.models_attempted,
                "is_also_mandatory": fc.is_also_mandatory,
                "mandatory_in_nodes": fc.mandatory_in_nodes,
            }
        )

    # Full constraint list sorted by scenario + action
    constraint_list = sorted(
        [
            {
                "scenario_id": fc.scenario_id,
                "graph_id": fc.graph_id,
                "node_id": fc.node_id,
                "action_id": fc.action_id,
                "source": fc.source,
                "recommendation_class": fc.recommendation_class,
                "evidence_level": fc.evidence_level,
                "classification": fc.classification,
                "attempts": fc.attempts,
                "commissions": fc.commissions,
                "models_attempted": fc.models_attempted,
                "is_also_mandatory": fc.is_also_mandatory,
                "mandatory_in_nodes": fc.mandatory_in_nodes,
            }
            for fc in constraints
        ],
        key=lambda x: (x["scenario_id"], x["action_id"]),
    )

    return {
        "metadata": {
            "analysis": "v3_p7_forbidden_exposure",
            "description": "Forbidden constraint exposure analysis across CGA-Bench",
            "graphs_analyzed": sorted(graphs.keys()),
            "total_episodes": summary["total_episodes_analyzed"],
            "models": [MODEL_DISPLAY[m] for m in MODELS],
        },
        "summary": summary,
        "dka_insulin_trap": dka_trap,
        "candidate_traps": candidate_traps,
        "per_scenario": per_scenario,
        "constraint_inventory": constraint_list,
    }


# ---------------------------------------------------------------------------
# Step 10: Write Markdown report
# ---------------------------------------------------------------------------


def write_markdown(output: dict, path: Path) -> None:
    s = output["summary"]
    dka = output["dka_insulin_trap"]
    traps = output["candidate_traps"]
    per_sc = output["per_scenario"]

    lines: list[str] = []
    a = lines.append

    a("# Forbidden Constraint Exposure Analysis (P7)")
    a("")
    a("## Overview")
    a("")
    a(
        f"Analyzed **{s['total_constraints']} forbidden constraint instances** across "
        f"**{len(per_sc)} scenarios** and **{s['total_episodes_analyzed']} episodes** "
        f"(4 models × 15 scenarios × 3 runs)."
    )
    a("")
    a(f"Unique (graph, action) pairs: **{s['unique_graph_action_pairs']}**")
    a("")

    # --- Summary table ---
    a("## Summary Statistics")
    a("")
    a("| Metric | N | % of testable |")
    a("|--------|---|---------------|")
    a(f"| Total constraint instances | {s['total_constraints']} | — |")
    a(f"| Unique graph×action pairs | {s['unique_graph_action_pairs']} | — |")
    a(f"| Testable (in episodes) | {s['testable_constraints']} | 100% |")
    a(f"| Zero-exposure (never attempted) | {s['zero_exposure']} | {s['zero_exposure_pct']}% |")
    a(f"| Triggered (commission violation) | {s['triggered']} | {s['triggered_pct']}% |")
    a(f"| — of which mandatory-yet-conditional | {s['triggered_mandatory_yet_conditional']} | — |")
    a(
        f"| Mandatory-yet-conditional (not triggered) | {s['mandatory_yet_conditional'] - s['triggered_mandatory_yet_conditional']} | {round(100.0 * (s['mandatory_yet_conditional'] - s['triggered_mandatory_yet_conditional']) / s['testable_constraints'], 1) if s['testable_constraints'] else 0}% |"
    )
    a(f"| Attempted but no violation | {s['attempted_but_correct']} | {s['attempted_but_correct_pct']}% |")
    a(f"| Candidate traps across graphs | {s['candidate_traps_in_graphs']} | — |")
    a("")

    a("> **Implication**: A high zero-exposure rate means that many forbidden constraints")
    a("> exist in the CPG graphs but are never exercised by the 15 evaluated scenarios.")
    a("> Only triggered constraints provide evidence that agents are tested on specific hazards.")
    a("")

    # --- Full inventory table ---
    a("## Forbidden Constraint Inventory")
    a("")
    a("Columns: scenario | action | source | class | attempts | commissions | classification")
    a("")
    a("| Scenario | Action | Source | RecClass | Attempts | Commissions | Classification |")
    a("|----------|--------|--------|----------|----------|-------------|----------------|")
    for row in output["constraint_inventory"]:
        sid = row["scenario_id"]
        act = row["action_id"]
        src = "override" if row["source"] == "scenario_override" else row["node_id"]
        rc = row["recommendation_class"] or "—"
        atts = row["attempts"]
        comms = row["commissions"]
        cls_ = row["classification"]
        a(f"| {sid} | `{act}` | {src} | {rc} | {atts} | {comms} | **{cls_}** |")
    a("")

    # --- Per-scenario exposure analysis ---
    a("## Per-Scenario Exposure Analysis")
    a("")
    for sid in sorted(per_sc.keys()):
        info = per_sc[sid]
        in_ep = "yes" if info["in_episodes"] else "no (not in eval episodes)"
        cs = info["constraints"]
        triggered = [c for c in cs if c["classification"] == "triggered"]
        zero = [c for c in cs if c["classification"] == "zero_exposure"]
        myc = [c for c in cs if c["classification"] == "mandatory_yet_conditional"]

        a(f"### {sid}")
        a(f"Graph: `{info['graph_id']}` | In episodes: {in_ep}")
        a("")
        a(f"- Total constraints: {len(cs)}")
        a(f"- Triggered: {len(triggered)}")
        a(f"- Zero-exposure: {len(zero)}")
        a(f"- Mandatory-yet-conditional: {len(myc)}")
        if triggered:
            a("")
            a("**Triggered constraints:**")
            for c in triggered:
                a(
                    f"  - `{c['action_id']}` — {c['commissions']} commission(s) across "
                    f"{c['attempts']} attempt(s), models: {c['models_attempted']}"
                )
        if zero:
            a("")
            a("**Zero-exposure constraints (never attempted):**")
            for c in zero:
                a(f"  - `{c['action_id']}` (node: {c['node_id']})")
        a("")

    # --- DKA insulin trap ---
    a("## DKA Insulin Trap Deep-Dive")
    a("")
    ctx = dka["graph_context"]
    a(f"**Action**: `{ctx['action']}`  ")
    a(f"**Scenario**: `{ctx['scenario']}`  ")
    a(f"**Graph**: `{ctx['graph']}`")
    a("")
    a("### Clinical Rationale")
    a("")
    a(ctx["clinical_rationale"])
    a("")
    a("### Graph Structure")
    a(f"- Mandatory in nodes: {ctx['mandatory_in_nodes']}")
    a(f"- Forbidden in nodes: {ctx['forbidden_in_nodes']}")
    a("")
    a("### Trigger Statistics")
    a("")
    a(f"- Total episodes for scenario: **{dka['total_episodes']}**")
    a(
        f"- Episodes where agent attempted insulin: **{dka['total_attempted']}** "
        f"({round(100 * dka['total_attempted'] / dka['total_episodes'], 1) if dka['total_episodes'] else 0}%)"
    )
    a(
        f"- Commission violations triggered: **{dka['total_triggered']}** "
        f"(trigger rate: {dka['overall_trigger_rate'] * 100:.1f}%)"
    )
    a("")
    a("| Model | Episodes | Attempted | Commission | Trigger Rate |")
    a("|-------|----------|-----------|------------|--------------|")
    for model_name, stats in dka["by_model"].items():
        a(
            f"| {model_name} | {stats['episodes']} | {stats['attempted']} | "
            f"{stats['triggered_commission']} | {stats['trigger_rate'] * 100:.1f}% |"
        )
    a("")

    # --- Candidate traps ---
    a("## Candidate Trap Identification")
    a("")
    a("Actions that appear as **both mandatory and forbidden** in different nodes of the same graph:")
    a("")
    if traps:
        a("| Graph | Action | Mandatory In | Forbidden In |")
        a("|-------|--------|-------------|-------------|")
        for t in traps:
            a(
                f"| `{t['graph_id']}` | `{t['action_id']}` | "
                f"{', '.join(t['mandatory_in_nodes'])} | "
                f"{', '.join(t['forbidden_in_nodes'])} |"
            )
        a("")
        a("### Clinical Interpretations")
        a("")
        # Known patterns with clinical context
        known_patterns = {
            "start_insulin_infusion": (
                "**DKA Insulin Trap**: Insulin is the definitive DKA therapy but is "
                "contraindicated before K+ correction (K < 3.3 mEq/L). Models that "
                "follow the general protocol (give insulin) without checking potassium "
                "first will trigger a commission violation."
            ),
            "give_nitroglycerin": (
                "**RV Infarct Nitrate Trap**: Nitrates are standard for most STEMI but "
                "are absolutely contraindicated in inferior STEMI with RV involvement "
                "because they cause profound hypotension by reducing RV preload."
            ),
            "give_nitrates_if_rv_infarct": (
                "**RV Infarct Nitrate Trap (conditional label)**: This action_id "
                "explicitly encodes the conditional: nitrates are forbidden specifically "
                "when RV infarct is present."
            ),
            "give_contrast": (
                "**Contrast-AKI Trap**: IV contrast is needed for CT angiography but is "
                "forbidden in patients with eGFR < 30, where it causes nephrotoxicity."
            ),
            "start_beta_blocker": (
                "**Beta-Blocker Context Trap**: Beta-blockers are mandatory in stable "
                "HFrEF but forbidden in acute decompensated heart failure (ADHF) with "
                "signs of low output, where negative inotropy worsens cardiogenic shock."
            ),
            "give_thrombolytics": (
                "**Thrombolytic Timing Trap**: tPA is mandatory for eligible ischemic "
                "stroke within 4.5h but forbidden after hemorrhagic transformation is "
                "detected or when contraindications are present."
            ),
            "anticoagulation": (
                "**Anticoagulation Timing in Stroke**: Anticoagulation prevents stroke "
                "recurrence in AF but is forbidden within 24h of tPA administration due "
                "to bleeding risk."
            ),
        }
        for t in traps:
            act = t["action_id"]
            if act in known_patterns:
                a(f"**`{act}` ({t['graph_id']})**")
                a("")
                a(known_patterns[act])
                a("")
    else:
        a("No cross-node mandatory-yet-forbidden patterns found in the loaded graphs.")
        a("")

    # --- Benchmark validity implications ---
    a("## Benchmark Validity Implications")
    a("")
    a("### What zero-exposure means")
    a("")
    a(
        textwrap.dedent("""\
        Forbidden constraints with zero exposure exist in the CPG graph but were never
        triggered in 180 evaluated episodes. This can occur because:
        1. The constraint belongs to a graph node that is never reached in the evaluated scenarios
           (e.g., a node triggered only by specific patient vital sign thresholds).
        2. The agents never attempt that action because their retrieval/generation does not
           produce it (vocabulary coverage gap).
        3. The constraint is scenario-context-specific and the 15 evaluated scenarios do not
           exercise that specific patient state.
        """)
    )
    a("### What triggered constraints validate")
    a("")
    a(
        textwrap.dedent("""\
        Each triggered constraint represents a **measurable safety test**: the benchmark
        has empirically demonstrated that some models are tempted to perform the forbidden
        action and that the scoring system correctly penalizes it. High trigger rates on
        mandatory-yet-conditional actions (e.g., DKA insulin, STEMI nitrates) validate
        that the trap scenarios are functioning as intended.
        """)
    )
    a("### Recommendations")
    a("")
    a(
        "1. Prioritize expanding scenarios that exercise zero-exposure constraints in critical "
        "graph nodes (especially `recommendation_class: I` constraints)."
    )
    a(
        f"2. The {len(traps)} candidate trap patterns identified are the strongest candidates for "
        "new trap scenario development, as they already have CPG structural support."
    )
    a(
        "3. Zero-exposure rate of {0}% suggests the benchmark's actual coverage of forbidden "
        "constraint space is narrower than the raw count implies; reported numbers should "
        "distinguish between 'constraints in graphs' vs 'constraints tested'.".format(s["zero_exposure_pct"])
    )
    a("")

    path.write_text("\n".join(lines))
    print(f"  Written: {path}")


# ---------------------------------------------------------------------------
# Step 11: Write LaTeX table
# ---------------------------------------------------------------------------


def write_latex(output: dict, path: Path) -> None:
    s = output["summary"]
    constraints = output["constraint_inventory"]

    # Group by scenario for condensed table
    by_scenario: dict[str, list] = defaultdict(list)
    for row in constraints:
        by_scenario[row["scenario_id"]].append(row)

    lines: list[str] = []
    a = lines.append

    a(r"\begin{table}[ht]")
    a(r"\centering")
    a(r"\small")
    a(
        r"\caption{Forbidden Constraint Exposure Analysis. "
        r"Classification: \textit{trigger} = commission violation observed; "
        r"\textit{zero} = never attempted; \textit{myc} = mandatory-yet-conditional; "
        r"\textit{abc} = attempted without violation.}"
    )
    a(r"\label{tab:forbidden_exposure}")
    a(r"\begin{tabular}{llrrrl}")
    a(r"\toprule")
    a(r"Scenario & Forbidden Action & Attempts & Commissions & Episodes & Classification \\")
    a(r"\midrule")

    episode_counts: dict[str, int] = defaultdict(int)
    for ep_info in output.get("per_scenario", {}).items():
        pass  # counts come from episodes
    # count episodes per scenario from constraint data
    ep_counts: dict[str, int] = {}
    for row in constraints:
        sid = row["scenario_id"]
        if sid not in ep_counts:
            ep_counts[sid] = 0  # filled from episode list

    # get episode counts from metadata
    per_sc = output.get("per_scenario", {})

    for sid in sorted(by_scenario.keys()):
        rows = by_scenario[sid]
        for i, row in enumerate(rows):
            act = row["action_id"].replace("_", r"\_")
            cls_map = {
                "triggered": r"\textbf{trigger}",
                "triggered_mandatory_yet_conditional": r"\textbf{trigger+myc}",
                "zero_exposure": "zero",
                "mandatory_yet_conditional": "myc",
                "attempted_but_correct": "abc",
            }
            cls_ = cls_map.get(row["classification"], row["classification"])
            sid_tex = sid.replace("_", r"\_") if i == 0 else ""
            a(f"{sid_tex} & \\texttt{{{act}}} & {row['attempts']} & {row['commissions']} & — & {cls_} \\\\")
        a(r"\midrule")

    a(r"\bottomrule")
    a(r"\end{tabular}")
    a(r"\end{table}")
    a("")
    # Summary table
    a(r"\begin{table}[ht]")
    a(r"\centering")
    a(r"\small")
    a(r"\caption{Forbidden constraint exposure summary statistics.}")
    a(r"\label{tab:forbidden_exposure_summary}")
    a(r"\begin{tabular}{lrr}")
    a(r"\toprule")
    a(r"Category & Count & \% of testable \\")
    a(r"\midrule")
    a(f"Total constraint instances & {s['total_constraints']} & — \\\\")
    a(f"Unique graph$\\times$action pairs & {s['unique_graph_action_pairs']} & — \\\\")
    a(f"Testable (in eval episodes) & {s['testable_constraints']} & 100\\% \\\\")
    a(r"\midrule")
    a(f"Zero-exposure & {s['zero_exposure']} & {s['zero_exposure_pct']}\\% \\\\")
    a(f"Triggered (commission) & {s['triggered']} & {s['triggered_pct']}\\% \\\\")
    a(f"\\quad of which mandatory-yet-conditional & {s['triggered_mandatory_yet_conditional']} & — \\\\")
    a(
        f"Mandatory-yet-conditional (all) & {s['mandatory_yet_conditional']} & {s['mandatory_yet_conditional_pct']}\\% \\\\"
    )
    a(f"Attempted without violation & {s['attempted_but_correct']} & {s['attempted_but_correct_pct']}\\% \\\\")
    a(r"\bottomrule")
    a(r"\end{tabular}")
    a(r"\end{table}")

    path.write_text("\n".join(lines))
    print(f"  Written: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== v3_p7_forbidden_exposure: Forbidden Constraint Exposure Analysis ===")
    print()

    # Ensure output dirs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/7] Loading CPG graphs...")
    graphs = load_graphs()
    print(f"      {len(graphs)} graphs loaded: {sorted(graphs.keys())}")

    print("[2/7] Loading scenario configs...")
    scenarios = load_scenarios()
    print(f"      {len(scenarios)} scenarios loaded")

    print("[3/7] Building forbidden constraint inventory...")
    constraints = build_constraint_inventory(graphs, scenarios)
    print(
        f"      {len(constraints)} constraint instances across {len(set(fc.scenario_id for fc in constraints))} scenarios"
    )

    print("[4/7] Loading episode data...")
    episodes = load_episodes()
    print(f"      {len(episodes)} episodes loaded")
    scenario_ids_in_episodes = {ep.scenario_id for ep in episodes}
    print(f"      Scenarios covered: {sorted(scenario_ids_in_episodes)}")

    print("[5/7] Annotating exposure...")
    annotate_exposure(constraints, episodes)
    by_class: dict[str, int] = defaultdict(int)
    for fc in constraints:
        by_class[fc.classification] += 1
    for cls_, cnt in sorted(by_class.items()):
        print(f"      {cls_}: {cnt}")

    print("[6/7] Finding candidate traps...")
    candidate_traps = find_candidate_traps(graphs)
    print(f"      {len(candidate_traps)} candidate traps found")
    for t in candidate_traps:
        print(
            f"      {t['graph_id']} :: {t['action_id']} "
            f"(mandatory in {t['mandatory_in_nodes']}, forbidden in {t['forbidden_in_nodes']})"
        )

    print("[7/7] Analyzing DKA insulin trap...")
    dka_trap = analyze_dka_insulin_trap(constraints, episodes)
    print(
        f"      trigger rate: {dka_trap['overall_trigger_rate'] * 100:.1f}% "
        f"({dka_trap['total_triggered']}/{dka_trap['total_episodes']} episodes)"
    )

    summary = compute_summary(constraints, episodes, candidate_traps)

    output = build_output(constraints, candidate_traps, dka_trap, summary, episodes, graphs)

    # Write outputs
    json_path = OUTPUT_DIR / "v3_forbidden_exposure.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWritten: {json_path}")

    md_path = OUTPUT_DIR / "v3_forbidden_exposure.md"
    write_markdown(output, md_path)

    tex_path = TABLES_DIR / "forbidden_exposure.tex"
    write_latex(output, tex_path)

    # Print final summary
    print()
    print("=== SUMMARY ===")
    print(f"  Total forbidden constraint instances : {summary['total_constraints']}")
    print(f"  Unique (graph, action) pairs         : {summary['unique_graph_action_pairs']}")
    print(f"  Testable (in eval episodes)           : {summary['testable_constraints']}")
    print(f"  Zero-exposure                         : {summary['zero_exposure']} ({summary['zero_exposure_pct']}%)")
    print(f"  Triggered (commission)                : {summary['triggered']} ({summary['triggered_pct']}%)")
    print(f"    of which mandatory-yet-conditional  : {summary['triggered_mandatory_yet_conditional']}")
    print(
        f"  Mandatory-yet-conditional (all)       : {summary['mandatory_yet_conditional']} ({summary['mandatory_yet_conditional_pct']}%)"
    )
    print(
        f"  Attempted but no violation            : {summary['attempted_but_correct']} ({summary['attempted_but_correct_pct']}%)"
    )
    print(f"  Candidate traps in graphs             : {summary['candidate_traps_in_graphs']}")
    print()
    print(f"  DKA insulin trap trigger rate         : {dka_trap['overall_trigger_rate'] * 100:.1f}%")
    print()
    print("Outputs:")
    print(f"  {json_path}")
    print(f"  {md_path}")
    print(f"  {tex_path}")


if __name__ == "__main__":
    main()
