#!/usr/bin/env python3
"""Re-compile SGSC scenarios from frozen atoms with adjustable knobs.

Walks ``<atoms-dir>/<graph_id>/atoms_smoke.json`` for each graph subdir,
re-runs the production compilation pipeline with the current
``CLUSTER_MIN`` / ``CLUSTER_MAX`` constants (or CLI overrides), and writes
``<output-dir>/<graph_id>/<graph_id>_scenarios.json`` matching the v7
production naming convention.

Optionally applies B-4 patient-profile expansion when
``--enable-patient-profiles`` is set; in B-3 we exercise the cluster-only
path.

Usage:
    PYTHONPATH=. python scripts/sgsc/recompile_corpus.py \
        --atoms-dir sgsc_output/v7_e3_combined_overnight/ \
        --output-dir sgsc_output/v7_1_cluster_only/

    PYTHONPATH=. python scripts/sgsc/recompile_corpus.py \
        --atoms-dir sgsc_output/v7_e3_combined_overnight/ \
        --output-dir sgsc_output/v7_1_with_profiles/ \
        --enable-patient-profiles \
        --profile-catalog data/v6_patient_profile_catalog.json \
        --graphs kdigo_contrast_aki
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from sgsc.compilers import scenario_compiler as sc_mod
from sgsc.compilers.counterfactual_compiler import compile_families
from sgsc.compilers.scenario_compiler import (
    compile_seeds,
    seeds_to_scenario_yaml,
    seeds_to_split_scenario_yaml,
)
from sgsc.optimizer.scenario_selector import select_scenarios
from sgsc.schemas.atom import RecommendationAtom

# Default 25 active core graphs (matches sgsc_output/v7_e3_combined_overnight/)
ACTIVE_CORE_GRAPHS: list[str] = [
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


def _load_atoms(path: Path) -> list[RecommendationAtom]:
    """Load and validate ``atoms_smoke.json`` into RecommendationAtom objects."""
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path}: atoms_smoke.json must be a list, got {type(raw).__name__}")
    return [RecommendationAtom.model_validate(a) for a in raw]


def _load_graph_nodes(graph_path: Path) -> dict[str, Any]:
    """Load the compiled graph JSON; return its ``nodes`` mapping (or empty)."""
    if not graph_path.exists():
        return {}
    doc = json.loads(graph_path.read_text())
    nodes = doc.get("nodes") if isinstance(doc, dict) else None
    return nodes if isinstance(nodes, dict) else {}


def _baseline_count(production_dir: Path, graph_id: str) -> int:
    """Read v7.0 production scenario count for delta reporting."""
    p = production_dir / graph_id / f"{graph_id}_scenarios.json"
    if not p.exists():
        return 0
    doc = json.loads(p.read_text())
    return len(doc) if isinstance(doc, dict) else 0


def _override_cluster_bounds(cluster_min: int | None, cluster_max: int | None) -> None:
    """Mutate module-level cluster constants when CLI overrides are provided."""
    if cluster_min is not None:
        sc_mod.CLUSTER_MIN = cluster_min
    if cluster_max is not None:
        sc_mod.CLUSTER_MAX = cluster_max


def _try_load_profile_catalog(path: Path | None) -> dict[str, Any] | None:
    """Load profile catalog JSON if path provided; return None otherwise."""
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Profile catalog not found: {path}")
    return json.loads(path.read_text())


def _expand_with_profiles(
    seeds: list[Any],
    graph_id: str,
    atoms: list[RecommendationAtom],
    graph_nodes: dict[str, Any],
    profile_catalog: dict[str, Any],
    max_profiles_per_cluster: int,
) -> dict[str, dict[str, Any]]:
    """Apply patient-profile expansion (B-4 hook).

    Lazy-imported so B-3 cluster-only runs do not require the B-4 module.
    """
    from scripts.sgsc.patient_profile_expansion import expand_seeds_with_profiles

    return expand_seeds_with_profiles(
        seeds=seeds,
        graph_id=graph_id,
        atoms=atoms,
        graph_nodes=graph_nodes,
        profile_catalog=profile_catalog,
        max_profiles_per_cluster=max_profiles_per_cluster,
    )


def _compile_one_graph(
    graph_id: str,
    atoms_path: Path,
    graph_path: Path,
    output_root: Path,
    *,
    skip_selection: bool,
    enable_profiles: bool,
    profile_catalog: dict[str, Any] | None,
    max_profiles_per_cluster: int,
    cluster_max: int,
) -> dict[str, Any]:
    """Compile a single graph; return summary metrics."""
    atoms = _load_atoms(atoms_path)
    graph_nodes = _load_graph_nodes(graph_path)
    seeds = compile_seeds(atoms, graph_id, cluster_max=cluster_max)
    if skip_selection:
        selected_seeds = list(seeds)
    else:
        families = compile_families(atoms)
        selection = select_scenarios(atoms, seeds, families)
        selected_ids = set(selection.selected_seed_ids)
        selected_seeds = [s for s in seeds if s.seed_id in selected_ids]
    if enable_profiles and profile_catalog is not None:
        scenarios = _expand_with_profiles(
            selected_seeds,
            graph_id,
            atoms,
            graph_nodes,
            profile_catalog,
            max_profiles_per_cluster,
        )
    else:
        scenarios = seeds_to_scenario_yaml(selected_seeds, graph_id, atoms, graph_nodes=graph_nodes)
    public, private = seeds_to_split_scenario_yaml(selected_seeds, graph_id, atoms, graph_nodes=graph_nodes)
    out_dir = output_root / graph_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{graph_id}_scenarios.json").write_text(json.dumps(scenarios, indent=2))
    (out_dir / f"{graph_id}_scenarios_public.json").write_text(json.dumps(public, indent=2))
    (out_dir / f"{graph_id}_scenarios_private.json").write_text(json.dumps(private, indent=2))
    return {
        "graph_id": graph_id,
        "n_atoms": len(atoms),
        "n_seeds_total": len(seeds),
        "n_seeds_selected": len(selected_seeds),
        "n_scenarios": len(scenarios),
    }


def _write_summary(summaries: list[dict[str, Any]], baselines: dict[str, int], output_root: Path) -> None:
    """Persist per-graph delta CSV at the output root."""
    rows: list[dict[str, Any]] = []
    for s in sorted(summaries, key=lambda x: -x["n_scenarios"]):
        baseline = baselines.get(s["graph_id"], 0)
        delta = s["n_scenarios"] - baseline
        ratio = round(s["n_scenarios"] / baseline, 2) if baseline else 0.0
        rows.append(
            {
                "graph_id": s["graph_id"],
                "n_atoms": s["n_atoms"],
                "n_seeds_total": s["n_seeds_total"],
                "n_seeds_selected": s["n_seeds_selected"],
                "v7_0_scenarios": baseline,
                "v7_1_scenarios": s["n_scenarios"],
                "delta": delta,
                "ratio": ratio,
            }
        )
    if not rows:
        return
    summary_path = output_root / "_recompile_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _resolve_graphs(graphs_arg: str | None) -> list[str]:
    """Parse comma-separated --graphs flag or default to active core."""
    if not graphs_arg:
        return list(ACTIVE_CORE_GRAPHS)
    return [g.strip() for g in graphs_arg.split(",") if g.strip()]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--atoms-dir",
        required=True,
        help="root dir containing <graph_id>/atoms_smoke.json subdirs",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--graphs",
        default=None,
        help="comma-separated graph IDs; default = all 25 active core",
    )
    parser.add_argument(
        "--cluster-min",
        type=int,
        default=None,
        help="override CLUSTER_MIN (default: module constant)",
    )
    parser.add_argument(
        "--cluster-max",
        type=int,
        default=None,
        help="override CLUSTER_MAX (default: module constant)",
    )
    parser.add_argument(
        "--skip-selection",
        action="store_true",
        help="bypass set-cover selection (use all seeds)",
    )
    parser.add_argument(
        "--enable-patient-profiles",
        action="store_true",
        help="apply B-4 patient profile expansion (requires --profile-catalog)",
    )
    parser.add_argument(
        "--profile-catalog",
        default="data/v6_patient_profile_catalog.json",
        help="path to v6 profile catalog JSON (used when profiles enabled)",
    )
    parser.add_argument(
        "--max-profiles-per-cluster",
        type=int,
        default=5,
        help="cap profiles per cluster in B-4 expansion (5 = T5+T1+T1+T2+T3/T4)",
    )
    parser.add_argument(
        "--baseline-dir",
        default="sgsc_output/v7_e3_combined_overnight",
        help="v7.0 baseline dir for delta reporting",
    )
    args = parser.parse_args(argv)

    _override_cluster_bounds(args.cluster_min, args.cluster_max)
    profile_catalog = _try_load_profile_catalog(Path(args.profile_catalog)) if args.enable_patient_profiles else None
    if args.enable_patient_profiles and profile_catalog is None:
        print("ERROR: --enable-patient-profiles requires a valid --profile-catalog")
        return 1

    atoms_root = Path(args.atoms_dir)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    baseline_root = Path(args.baseline_dir)
    graphs = _resolve_graphs(args.graphs)
    summaries: list[dict[str, Any]] = []
    baselines: dict[str, int] = {}
    for graph_id in graphs:
        atoms_path = atoms_root / graph_id / "atoms_smoke.json"
        graph_path = atoms_root / graph_id / f"{graph_id}_graph.json"
        if not atoms_path.exists():
            print(f"SKIP {graph_id}: missing atoms file at {atoms_path}")
            continue
        baselines[graph_id] = _baseline_count(baseline_root, graph_id)
        summary = _compile_one_graph(
            graph_id,
            atoms_path,
            graph_path,
            output_root,
            skip_selection=args.skip_selection,
            enable_profiles=args.enable_patient_profiles,
            profile_catalog=profile_catalog,
            max_profiles_per_cluster=args.max_profiles_per_cluster,
            cluster_max=sc_mod.CLUSTER_MAX,
        )
        summaries.append(summary)
    _write_summary(summaries, baselines, output_root)
    total = sum(s["n_scenarios"] for s in summaries)
    baseline_total = sum(baselines.values())
    ratio = round(total / baseline_total, 2) if baseline_total else 0.0
    print(
        f"RECOMPILE -- {len(summaries)} graphs, "
        f"v7.0={baseline_total} -> v7.1={total} (ratio={ratio}x); "
        f"cluster_min={sc_mod.CLUSTER_MIN}, cluster_max={sc_mod.CLUSTER_MAX}; "
        f"profiles={'ON' if args.enable_patient_profiles else 'OFF'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
