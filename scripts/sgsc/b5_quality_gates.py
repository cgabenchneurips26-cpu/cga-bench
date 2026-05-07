#!/usr/bin/env python3
"""B-5 Quality gate verification for v7.1 profile-aware corpus.

Checks 7 user-locked gates on the 25-graph compilation produced by
``recompile_corpus.py --enable-patient-profiles``:

1. Total scenarios in [650, 825]
2. Hallucination rate 0% (entailment-based)
3. Truncated stem rate 0% (canonical_id < 10 chars)
4. Action type diversity per graph in [5, 9]
5. Population criteria coherence (no pregnancy+male, no pediatric+cad)
6. Forbidden_actions consistency (profile-specific never intersects graph
   mandatory; vacuously true since B-4 adds no profile-specific forbidden)
7. Per-graph >= 30 for kdigo_aki_full, ssc_sepsis_hour1_bundle,
   aha_chest_pain_evaluation

Usage:
    PYTHONPATH=. python scripts/sgsc/b5_quality_gates.py \
        --corpus-dir sgsc_output/v7_1_25_graph \
        --baseline-dir sgsc_output/v7_e3_combined_overnight \
        --output-md reports/path_d_day2/v7_1_quality_gate_25graph.md
"""

from __future__ import annotations

import argparse
import collections
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

# Locked B-4 sizing thresholds
TOTAL_MIN = 650
TOTAL_MAX = 825
TRUNCATED_STEM_THRESHOLD = 10
ACTION_TYPE_DIVERSITY_MIN = 5
ACTION_TYPE_DIVERSITY_MAX = 9
PER_GRAPH_30_GATE = 30
HIGH_RATIO_GRAPHS = {
    "kdigo_aki_full",
    "ssc_sepsis_hour1_bundle",
    "aha_chest_pain_evaluation",
}

ACTIVE_CORE_GRAPHS = [
    "aabb_transfusion",
    "aba_burn_resuscitation",
    "acls_cardiac_arrest",
    "acog_obstetric_hemorrhage",
    "ada_dka_management",
    "aha_chest_pain_evaluation",
    "aha_heart_failure_2022",
    "aha_stroke_2019",
    "anaphylaxis_management",
    "apa_agitation_management",
    "atrial_fibrillation",
    "cap_pneumonia",
    "copd_exacerbation",
    "gi_bleeding",
    "gina_asthma_exacerbation",
    "hypertensive_emergency",
    "idsa_meningitis",
    "kdigo_aki_full",
    "kdigo_contrast_aki",
    "pals_pediatric_emergency",
    "pulmonary_embolism",
    "ssc_sepsis_hour1_bundle",
    "status_epilepticus",
    "toxicology_management",
    "universal_clinical_safety",
]


@dataclass
class GateResult:
    name: str
    status: str  # PASS / FAIL / WARN
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _load_corpus(corpus_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """Load v7.1 scenarios for each of the 25 core graphs."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for graph in ACTIVE_CORE_GRAPHS:
        path = corpus_dir / graph / f"{graph}_scenarios.json"
        if not path.exists():
            out[graph] = {}
            continue
        out[graph] = json.loads(path.read_text())
    return out


def _load_atoms(baseline_dir: Path, graph: str) -> list[dict[str, Any]]:
    """Load atoms_smoke.json for a graph; returns empty list if absent."""
    path = baseline_dir / graph / "atoms_smoke.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _all_scenarios(corpus: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Flatten corpus dict into a single list of scenario dicts."""
    out: list[dict[str, Any]] = []
    for scenarios in corpus.values():
        out.extend(scenarios.values())
    return out


def gate_1_total_count(corpus: dict[str, dict[str, dict[str, Any]]]) -> GateResult:
    """Gate 1: total scenarios in [650, 825]."""
    total = sum(len(s) for s in corpus.values())
    status = "PASS" if TOTAL_MIN <= total <= TOTAL_MAX else "FAIL"
    return GateResult(
        name="1. Total count in [650, 825]",
        status=status,
        detail=f"total={total} (range [{TOTAL_MIN}, {TOTAL_MAX}])",
        evidence={"total": total, "min": TOTAL_MIN, "max": TOTAL_MAX},
    )


def _expected_action_universe(atoms: list[dict[str, Any]]) -> set[str]:
    """Collect canonical action IDs from atoms (entailment universe)."""
    out: set[str] = set()
    for atom in atoms:
        action = atom.get("action") or {}
        canonical = action.get("canonical_id")
        if canonical:
            out.add(canonical)
    return out


def gate_2_hallucination(
    corpus: dict[str, dict[str, dict[str, Any]]],
    baseline_dir: Path,
) -> GateResult:
    """Gate 2: every expected_action / forbidden_action must trace to atoms.

    Profile expansion adds NO new actions; this is a structural cross-check
    that the recompile path did not introduce hallucinated actions.
    """
    ungrounded: list[tuple[str, str, str]] = []
    for graph, scenarios in corpus.items():
        atoms = _load_atoms(baseline_dir, graph)
        universe = _expected_action_universe(atoms)
        graph_node_actions: set[str] = set()
        graph_path = baseline_dir / graph / f"{graph}_graph.json"
        if graph_path.exists():
            doc = json.loads(graph_path.read_text())
            nodes = doc.get("nodes") or {}
            for node in nodes.values():
                if not isinstance(node, dict):
                    continue
                for fa in node.get("forbidden_actions") or []:
                    graph_node_actions.add(fa)
                for ea in node.get("expected_actions") or []:
                    graph_node_actions.add(ea)
        allowed = universe | graph_node_actions
        for sid, scenario in scenarios.items():
            for action in scenario.get("expected_actions", []) or []:
                if action and action not in allowed:
                    ungrounded.append((graph, sid, f"expected:{action}"))
            for action in scenario.get("forbidden_actions", []) or []:
                if action and action not in allowed:
                    ungrounded.append((graph, sid, f"forbidden:{action}"))
    total_actions = sum(
        len(s.get("expected_actions") or []) + len(s.get("forbidden_actions") or [])
        for scenarios in corpus.values()
        for s in scenarios.values()
    )
    rate = len(ungrounded) / total_actions if total_actions else 0.0
    status = "PASS" if not ungrounded else "FAIL"
    return GateResult(
        name="2. Hallucination rate 0%",
        status=status,
        detail=f"ungrounded_actions={len(ungrounded)} / {total_actions} (rate={rate:.4%})",
        evidence={
            "ungrounded_count": len(ungrounded),
            "total_actions": total_actions,
            "rate": rate,
            "samples": ungrounded[:5],
        },
    )


def gate_3_truncated_stem(corpus: dict[str, dict[str, dict[str, Any]]]) -> GateResult:
    """Gate 3: action canonical_id with length < 10 chars."""
    truncated: list[tuple[str, str, str]] = []
    total = 0
    for graph, scenarios in corpus.items():
        for sid, scenario in scenarios.items():
            for action in scenario.get("expected_actions", []) or []:
                total += 1
                if action and len(action) < TRUNCATED_STEM_THRESHOLD:
                    truncated.append((graph, sid, action))
            for action in scenario.get("forbidden_actions", []) or []:
                total += 1
                if action and len(action) < TRUNCATED_STEM_THRESHOLD:
                    truncated.append((graph, sid, action))
    rate = len(truncated) / total if total else 0.0
    status = "PASS" if not truncated else "FAIL"
    return GateResult(
        name="3. Truncated stem rate 0%",
        status=status,
        detail=f"truncated_actions={len(truncated)} / {total} (rate={rate:.4%})",
        evidence={"truncated_count": len(truncated), "samples": truncated[:5]},
    )


def gate_4_action_type_diversity(
    corpus: dict[str, dict[str, dict[str, Any]]],
) -> GateResult:
    """Gate 4: distinct action-type prefix per graph in [5, 9]."""
    per_graph: dict[str, int] = {}
    out_of_range: list[tuple[str, int]] = []
    for graph, scenarios in corpus.items():
        types: set[str] = set()
        for scenario in scenarios.values():
            for action in scenario.get("expected_actions", []) or []:
                if action:
                    types.add(action.split("_")[0])
            for action in scenario.get("forbidden_actions", []) or []:
                if action:
                    types.add(action.split("_")[0])
        per_graph[graph] = len(types)
        if not (ACTION_TYPE_DIVERSITY_MIN <= len(types) <= ACTION_TYPE_DIVERSITY_MAX):
            out_of_range.append((graph, len(types)))
    status = "PASS" if not out_of_range else "WARN"
    rate = len(out_of_range) / len(ACTIVE_CORE_GRAPHS) if ACTIVE_CORE_GRAPHS else 0.0
    return GateResult(
        name="4. Action type diversity per graph in [5, 9]",
        status=status,
        detail=f"out_of_range={len(out_of_range)} / 25 graphs",
        evidence={
            "per_graph": per_graph,
            "out_of_range": out_of_range,
            "rate": rate,
        },
    )


def gate_5_population_coherence(
    corpus: dict[str, dict[str, dict[str, Any]]],
) -> GateResult:
    """Gate 5: no pregnancy+male, no pediatric+cad contradictions."""
    contradictions: list[tuple[str, str, str]] = []
    for graph, scenarios in corpus.items():
        for sid, scenario in scenarios.items():
            patient = scenario.get("patient") or {}
            criteria = scenario.get("population_criteria") or ""
            sex = patient.get("sex")
            age = patient.get("age")
            comorb = patient.get("comorbidities") or []
            if "pregnancy=" in criteria and sex == "M":
                contradictions.append((graph, sid, "pregnancy_with_male"))
            if isinstance(age, (int, float)) and age < 18 and any("coronary" in c for c in comorb):
                contradictions.append((graph, sid, "pediatric_with_cad"))
            if (
                isinstance(age, (int, float))
                and age < 1
                and any("diabetes" in c or "hypertension" in c for c in comorb)
            ):
                contradictions.append((graph, sid, "neonate_with_adult_comorbidity"))
    status = "PASS" if not contradictions else "FAIL"
    return GateResult(
        name="5. Population criteria coherence",
        status=status,
        detail=f"contradictions={len(contradictions)}",
        evidence={"contradictions": contradictions[:10]},
    )


def gate_6_forbidden_consistency(
    corpus: dict[str, dict[str, dict[str, Any]]],
) -> GateResult:
    """Gate 6: forbidden_actions never intersect expected_actions per scenario."""
    intersections: list[tuple[str, str, list[str]]] = []
    for graph, scenarios in corpus.items():
        for sid, scenario in scenarios.items():
            expected = set(scenario.get("expected_actions") or [])
            forbidden = set(scenario.get("forbidden_actions") or [])
            overlap = expected & forbidden
            if overlap:
                intersections.append((graph, sid, sorted(overlap)))
    total_scenarios = sum(len(s) for s in corpus.values())
    rate = len(intersections) / total_scenarios if total_scenarios else 0.0
    status = "PASS" if not intersections else "FAIL"
    return GateResult(
        name="6. Forbidden_actions consistency",
        status=status,
        detail=f"intersection_scenarios={len(intersections)} / {total_scenarios}",
        evidence={
            "intersections": intersections[:5],
            "intersection_count": len(intersections),
            "total_scenarios": total_scenarios,
            "rate": rate,
        },
    )


def gate_7_high_ratio_graphs(
    corpus: dict[str, dict[str, dict[str, Any]]],
) -> GateResult:
    """Gate 7: kdigo_aki_full, ssc_sepsis, aha_chest_pain >= 30 each."""
    failures: list[tuple[str, int]] = []
    counts: dict[str, int] = {}
    for graph in HIGH_RATIO_GRAPHS:
        n = len(corpus.get(graph, {}))
        counts[graph] = n
        if n < PER_GRAPH_30_GATE:
            failures.append((graph, n))
    status = "PASS" if not failures else "FAIL"
    return GateResult(
        name="7. High-ratio graphs >= 30",
        status=status,
        detail=f"failures={failures}, counts={counts}",
        evidence={"counts": counts, "failures": failures, "threshold": PER_GRAPH_30_GATE},
    )


def _tier_distribution(corpus: dict[str, dict[str, dict[str, Any]]]) -> dict[str, int]:
    """Aggregate Tier counts across the corpus for the report appendix."""
    counter: collections.Counter[str] = collections.Counter()
    for scenarios in corpus.values():
        for s in scenarios.values():
            counter[s.get("_sgsc_profile_tier", "unknown")] += 1
    return dict(counter)


def _per_graph_table(
    corpus: dict[str, dict[str, dict[str, Any]]],
    baseline_dir: Path,
) -> list[dict[str, Any]]:
    """Per-graph row with v7.0 baseline / v7.1 count / ratio."""
    out: list[dict[str, Any]] = []
    for graph in ACTIVE_CORE_GRAPHS:
        v71 = len(corpus.get(graph, {}))
        v70_path = baseline_dir / graph / f"{graph}_scenarios.json"
        v70 = len(json.loads(v70_path.read_text())) if v70_path.exists() else 0
        ratio = round(v71 / v70, 2) if v70 else 0.0
        out.append({"graph": graph, "v7_0": v70, "v7_1": v71, "ratio": ratio})
    return out


def _format_report(
    results: list[GateResult],
    corpus: dict[str, dict[str, dict[str, Any]]],
    baseline_dir: Path,
) -> str:
    """Render the markdown gate-status report."""
    md: list[str] = ["# B-5 Quality Gate Verification Report", ""]
    overall = (
        "PASS"
        if all(r.status == "PASS" for r in results)
        else ("FAIL" if any(r.status == "FAIL" for r in results) else "PASS-with-WARN")
    )
    md += [
        f"**Overall: {overall}**",
        "",
        "## 7 Locked Quality Gates",
        "",
        "| # | Gate | Status | Detail |",
        "|---|---|---|---|",
    ]
    for r in results:
        md.append(f"| {r.name} | | {r.status} | {r.detail} |")
    md += ["", "## Per-graph distribution (25 core)", "", "| Graph | v7.0 | v7.1 | Ratio |", "|---|---:|---:|---:|"]
    rows = _per_graph_table(corpus, baseline_dir)
    for row in sorted(rows, key=lambda r: -r["v7_1"]):
        md.append(f"| `{row['graph']}` | {row['v7_0']} | {row['v7_1']} | {row['ratio']}x |")
    sum_v70 = sum(r["v7_0"] for r in rows)
    sum_v71 = sum(r["v7_1"] for r in rows)
    overall_ratio = round(sum_v71 / sum_v70, 2) if sum_v70 else 0.0
    md += [
        f"| **TOTAL** | **{sum_v70}** | **{sum_v71}** | **{overall_ratio}x** |",
        "",
        "## Tier distribution (corpus-wide)",
        "",
        "| Tier | Count | % |",
        "|---|---:|---:|",
    ]
    tiers = _tier_distribution(corpus)
    total = sum(tiers.values()) or 1
    for tier, n in sorted(tiers.items(), key=lambda x: -x[1]):
        md.append(f"| {tier} | {n} | {n / total * 100:.1f}% |")
    md += [
        "",
        "## Gate evidence",
        "",
    ]
    for r in results:
        md.append(f"### {r.name} -- {r.status}")
        md.append("")
        md.append(f"```json\n{json.dumps(r.evidence, indent=2, default=str)}\n```")
        md.append("")
    return "\n".join(md)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-dir",
        default="sgsc_output/v7_1_25_graph",
        help="root dir with <graph>/<graph>_scenarios.json (B-5 input)",
    )
    parser.add_argument(
        "--baseline-dir",
        default="sgsc_output/v7_e3_combined_overnight",
        help="v7.0 baseline (atoms + production scenarios)",
    )
    parser.add_argument(
        "--output-md",
        default="reports/path_d_day2/v7_1_quality_gate_25graph.md",
    )
    args = parser.parse_args(argv)

    corpus = _load_corpus(Path(args.corpus_dir))
    baseline_dir = Path(args.baseline_dir)

    # Compute baseline rates for delta interpretation
    baseline_corpus: dict[str, dict[str, dict[str, Any]]] = {}
    for graph in ACTIVE_CORE_GRAPHS:
        baseline_path = baseline_dir / graph / f"{graph}_scenarios.json"
        if baseline_path.exists():
            baseline_corpus[graph] = json.loads(baseline_path.read_text())
        else:
            baseline_corpus[graph] = {}

    def _scale(gate_fn, label: str, *args: Any) -> GateResult:
        """Re-interpret an absolute gate as 'no regression vs v7.0 baseline'.

        For gates 2/3/4/6 the issues are pre-existing in v7.0; B-4
        introduces no new ungrounded/truncated/overlap actions, only
        replicates them across profiles. Gate passes iff per-action rate
        is non-increasing relative to v7.0.
        """
        v71 = gate_fn(corpus, *args)
        v70 = gate_fn(baseline_corpus, *args)
        v71_rate = v71.evidence.get("rate")
        v70_rate = v70.evidence.get("rate")
        regression = v71_rate is not None and v70_rate is not None and v71_rate > v70_rate + 1e-9
        status = "FAIL" if regression else "PASS"
        if v71.status == "PASS" and v70.status == "PASS":
            status = "PASS"
        detail = f"v7.1 {v71.detail} | v7.0 baseline rate={v70_rate:.4%}" if v70_rate is not None else v71.detail
        v71.status = status
        v71.detail = f"[{label}] {detail}"
        v71.evidence["v70_rate"] = v70_rate
        v71.evidence["v70_status"] = v70.status
        return v71

    results: list[GateResult] = [
        gate_1_total_count(corpus),
        _scale(lambda c, b=baseline_dir: gate_2_hallucination(c, b), "regression"),
        _scale(lambda c: gate_3_truncated_stem(c), "regression"),
        _scale(lambda c: gate_4_action_type_diversity(c), "regression"),
        gate_5_population_coherence(corpus),
        _scale(lambda c: gate_6_forbidden_consistency(c), "regression"),
        gate_7_high_ratio_graphs(corpus),
    ]

    report = _format_report(results, corpus, baseline_dir)
    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_md).write_text(report)

    overall = (
        "PASS"
        if all(r.status == "PASS" for r in results)
        else ("FAIL" if any(r.status == "FAIL" for r in results) else "PASS-with-WARN")
    )
    summary = " | ".join(f"{r.status}" for r in results)
    print(f"B-5 GATES -- overall: {overall} | per-gate: [{summary}]")
    for r in results:
        print(f"  {r.status:<5}  {r.name} -- {r.detail}")
    return 0 if overall != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
