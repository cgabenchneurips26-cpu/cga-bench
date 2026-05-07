#!/usr/bin/env python3
r"""Representativeness analysis for SGSC Pilot-14 (and full-25) guidelines.

Computes 8+ stratification dimensions across SGSC output to produce a
domain complexity profile that defends against cherry-pick accusations.

Usage:
    PYTHONPATH=. python scripts/sgsc/analyze_representativeness.py
    PYTHONPATH=. python scripts/sgsc/analyze_representativeness.py \
        --registry configs/sgsc/full_25_registry.json \
        --sgsc-dir sgsc_output \
        --output-dir evidence_pack/analysis
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

logger = logging.getLogger("analyze_representativeness")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    """Return the current HEAD commit hash, or 'unknown' on failure."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _hash_files(paths: list[Path]) -> str:
    """Return a deterministic SHA-256 over the content of all *existing* paths."""
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def _load_json(path: Path) -> object | None:
    """Load JSON from *path*; return None and log a warning on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Axis implementations
# ---------------------------------------------------------------------------


def _axis_domain(guidelines: list[dict]) -> dict:
    """Axis 1 — count guidelines per domain."""
    dist: dict[str, int] = {}
    for g in guidelines:
        domain = g.get("domain") or "unknown"
        dist[domain] = dist.get(domain, 0) + 1
    return {
        "domain_distribution": dist,
        "domain_count": len(dist),
    }


def _axis_constraint_type(guidelines: list[dict], sgsc_dir: Path) -> dict:
    """Axis 2 — distribution of constraint types across all guideline outputs."""
    type_dist: dict[str, int] = {}
    total = 0
    missing = 0

    for g in guidelines:
        gid = g["guideline_id"]
        cpath = sgsc_dir / gid / f"{gid}_constraints.json"
        if not cpath.exists():
            logger.debug("Constraints file missing: %s", cpath)
            missing += 1
            continue

        data = _load_json(cpath)
        if data is None:
            missing += 1
            continue

        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                ctype = item.get("constraint_type") or item.get("type") or "UNKNOWN"
                type_dist[ctype] = type_dist.get(ctype, 0) + 1
                total += 1
        elif isinstance(data, dict):
            # Possible dict-of-constraints format
            for key, item in data.items():
                if isinstance(item, dict):
                    ctype = item.get("constraint_type") or item.get("type") or key
                    type_dist[ctype] = type_dist.get(ctype, 0) + 1
                    total += 1

    return {
        "constraint_type_distribution": type_dist,
        "total_constraints_loaded": total,
        "guidelines_missing_constraints": missing,
    }


def _axis_conditionality(guidelines: list[dict], sgsc_dir: Path) -> dict:
    """Axis 3 — percentage of atoms that carry a non-empty guard condition."""
    total_atoms = 0
    guarded = 0
    missing = 0

    for g in guidelines:
        gid = g["guideline_id"]
        gdir = sgsc_dir / gid

        # Try multiple file name conventions
        candidates = [
            gdir / "atoms_smoke.json",
            gdir / f"{gid}_atoms.json",
            gdir / "atoms.json",
        ]
        atom_file: Path | None = next((c for c in candidates if c.exists()), None)

        if atom_file is None:
            logger.debug("No atom file found for %s", gid)
            missing += 1
            continue

        data = _load_json(atom_file)
        if not isinstance(data, list):
            missing += 1
            continue

        for atom in data:
            if not isinstance(atom, dict):
                continue
            total_atoms += 1

            # guard field: explicit key
            guard = atom.get("guard")
            if guard is not None and guard != {} and guard != "":
                guarded += 1
                continue

            # Fallback: constraint.activation_event or condition sub-field
            constraint = atom.get("constraint")
            if isinstance(constraint, dict):
                activation = constraint.get("activation_event") or constraint.get("condition")
                if activation and activation not in ("", "any", "always"):
                    guarded += 1

    pct = round(100.0 * guarded / total_atoms, 1) if total_atoms > 0 else 0.0
    return {
        "total_atoms": total_atoms,
        "guarded_atom_count": guarded,
        "guarded_atom_pct": pct,
        "guidelines_missing_atoms": missing,
    }


def _axis_timing(guidelines: list[dict], sgsc_dir: Path) -> dict:
    """Axis 4 — proportion of constraints that carry a deadline/timing field."""
    total = 0
    timed = 0
    missing = 0

    for g in guidelines:
        gid = g["guideline_id"]
        cpath = sgsc_dir / gid / f"{gid}_constraints.json"
        if not cpath.exists():
            missing += 1
            continue

        data = _load_json(cpath)
        if data is None:
            missing += 1
            continue

        items: list[dict] = []
        if isinstance(data, list):
            items = [d for d in data if isinstance(d, dict)]
        elif isinstance(data, dict):
            items = [v for v in data.values() if isinstance(v, dict)]

        for item in items:
            total += 1
            deadline = item.get("deadline") or item.get("deadline_minutes") or item.get("timing")
            if deadline is not None and deadline not in ("", 0, None):
                timed += 1

    pct = round(100.0 * timed / total, 1) if total > 0 else 0.0
    return {
        "timed_constraint_count": timed,
        "total_constraints_for_timing": total,
        "timed_constraint_pct": pct,
        "guidelines_missing_constraints_timing": missing,
    }


def _axis_alternatives(guidelines: list[dict], sgsc_dir: Path) -> dict:
    """Axis 5 — proportion of scenarios that are counterfactual variants."""
    total_scenarios = 0
    counterfactual_count = 0
    missing = 0

    for g in guidelines:
        gid = g["guideline_id"]
        spath = sgsc_dir / gid / f"{gid}_scenarios.json"
        if not spath.exists():
            logger.debug("Scenarios file missing: %s", spath)
            missing += 1
            continue

        data = _load_json(spath)
        if data is None:
            missing += 1
            continue

        scenarios: list[dict] = []
        if isinstance(data, dict):
            scenarios = [v for v in data.values() if isinstance(v, dict)]
        elif isinstance(data, list):
            scenarios = [s for s in data if isinstance(s, dict)]

        for scen in scenarios:
            total_scenarios += 1
            # Detect counterfactual membership via explicit fields or metadata
            is_cf = (
                scen.get("family_id") is not None
                or scen.get("counterfactual_of") is not None
                or scen.get("is_counterfactual") is True
            )
            if not is_cf:
                meta = scen.get("_sgsc_metadata") or {}
                if isinstance(meta, dict) and (
                    meta.get("family_id") is not None
                    or meta.get("counterfactual_of") is not None
                    or meta.get("is_counterfactual") is True
                ):
                    is_cf = True
            if is_cf:
                counterfactual_count += 1

    pct = round(100.0 * counterfactual_count / total_scenarios, 1) if total_scenarios > 0 else 0.0
    return {
        "total_scenarios": total_scenarios,
        "counterfactual_scenario_count": counterfactual_count,
        "counterfactual_pct": pct,
        "guidelines_missing_scenarios": missing,
    }


def _axis_source_quality(analysis_dir: Path) -> dict:
    """Axis 6 — extract source quality metrics from field entailment report."""
    report_path = analysis_dir / "field_entailment_report.json"
    if not report_path.exists():
        logger.info("field_entailment_report.json not found; skipping source_quality axis")
        return {"source_quality_available": False}

    data = _load_json(report_path)
    if not isinstance(data, dict):
        return {"source_quality_available": False, "parse_error": True}

    metrics = data.get("metrics", {})
    return {
        "source_quality_available": True,
        "source_quality": {
            "field_pass_rates": metrics.get("field_pass_rates", {}),
            "fuzzy_only_count": metrics.get("fuzzy_only_count", 0),
            "contradiction_candidates": metrics.get("contradiction_candidates", 0),
            "threshold_sensitivity": metrics.get("threshold_sensitivity", {}),
        },
    }


def _axis_scenario_yield(guidelines: list[dict], sgsc_dir: Path) -> dict:
    """Axis 7 — scenarios-per-atom yield for each guideline."""
    per_guideline: list[dict] = []

    for g in guidelines:
        gid = g["guideline_id"]
        gdir = sgsc_dir / gid

        # Count atoms
        atom_count = 0
        for fname in ["atoms_smoke.json", f"{gid}_atoms.json", "atoms.json"]:
            ap = gdir / fname
            if ap.exists():
                adata = _load_json(ap)
                if isinstance(adata, list):
                    atom_count = len(adata)
                break

        # Count scenarios
        scenario_count = 0
        spath = gdir / f"{gid}_scenarios.json"
        if spath.exists():
            sdata = _load_json(spath)
            if isinstance(sdata, (dict, list)):
                scenario_count = len(sdata)

        yld = round(scenario_count / atom_count, 2) if atom_count > 0 else 0.0
        per_guideline.append(
            {
                "id": gid,
                "scenarios": scenario_count,
                "atoms": atom_count,
                "yield": yld,
            }
        )

    yields = [e["yield"] for e in per_guideline]
    avg_yield = round(sum(yields) / len(yields), 2) if yields else 0.0
    min_yield = round(min(yields), 2) if yields else 0.0
    max_yield = round(max(yields), 2) if yields else 0.0

    return {
        "per_guideline_yield": per_guideline,
        "avg_yield": avg_yield,
        "min_yield": min_yield,
        "max_yield": max_yield,
    }


def _axis_transition_complexity(guidelines: list[dict], sgsc_dir: Path) -> dict:
    """Axis 8 — graphs that have at least one non-empty auto_transition_conditions entry."""
    graphs_checked = 0
    graphs_with_transitions = 0
    missing = 0

    for g in guidelines:
        gid = g["guideline_id"]
        gpath = sgsc_dir / gid / f"{gid}_graph.json"
        if not gpath.exists():
            logger.debug("Graph file missing: %s", gpath)
            missing += 1
            continue

        data = _load_json(gpath)
        if not isinstance(data, dict):
            missing += 1
            continue

        graphs_checked += 1
        nodes = data.get("nodes", {})
        node_list: list[dict] = []
        if isinstance(nodes, dict):
            node_list = [v for v in nodes.values() if isinstance(v, dict)]
        elif isinstance(nodes, list):
            node_list = [n for n in nodes if isinstance(n, dict)]

        found_transition = False
        for node in node_list:
            atc = node.get("auto_transition_conditions")
            if isinstance(atc, list) and len(atc) > 0:
                found_transition = True
                break

        if found_transition:
            graphs_with_transitions += 1

    pct = round(100.0 * graphs_with_transitions / graphs_checked, 1) if graphs_checked > 0 else 0.0
    return {
        "graphs_checked": graphs_checked,
        "graphs_with_transitions": graphs_with_transitions,
        "transition_pct": pct,
        "guidelines_missing_graphs": missing,
    }


def _axis_held_out(guidelines: list[dict]) -> dict:
    """Axis 9 — count and list held-out guidelines."""
    held_out_ids = [g["guideline_id"] for g in guidelines if g.get("held_out") is True]
    return {
        "held_out_count": len(held_out_ids),
        "held_out_ids": held_out_ids,
    }


# ---------------------------------------------------------------------------
# LaTeX macro generation
# ---------------------------------------------------------------------------


def _build_macros(metrics: dict) -> list[str]:
    r"""Build the set of \providecommand macros for auto_numbers_sgsc.tex."""
    domain_count = metrics.get("domain", {}).get("domain_count", 0)
    guarded_pct = metrics.get("conditionality", {}).get("guarded_atom_pct", 0.0)
    timed_pct = metrics.get("timing", {}).get("timed_constraint_pct", 0.0)
    cf_pct = metrics.get("alternatives", {}).get("counterfactual_pct", 0.0)
    avg_yield = metrics.get("scenario_yield", {}).get("avg_yield", 0.0)
    held_out = metrics.get("held_out", {}).get("held_out_count", 0)
    trans_pct = metrics.get("transition_complexity", {}).get("transition_pct", 0.0)

    return [
        f"\\providecommand{{\\sgscDomainCount}}{{{domain_count}}}",
        f"\\providecommand{{\\sgscGuardedAtomPct}}{{{guarded_pct}}}",
        f"\\providecommand{{\\sgscTimedConstraintPct}}{{{timed_pct}}}",
        f"\\providecommand{{\\sgscCounterfactualPct}}{{{cf_pct}}}",
        f"\\providecommand{{\\sgscAvgScenarioYield}}{{{avg_yield}}}",
        f"\\providecommand{{\\sgscHeldOutCount}}{{{held_out}}}",
        f"\\providecommand{{\\sgscTransitionPct}}{{{trans_pct}}}",
    ]


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------


def run_analysis(registry_path: Path, output_base: Path, sgsc_dir: Path) -> dict:
    """Run all representativeness axes and return the standard JSON contract.

    Args:
        registry_path: Path to pilot_14_registry.json or full_25_registry.json.
        output_base:   Directory for evidence_pack/analysis outputs.
        sgsc_dir:      Root directory of SGSC output (one sub-dir per guideline).

    Returns:
        A dict conforming to the standard JSON check contract.
    """
    # ---- Load registry ----
    registry_data = _load_json(registry_path)
    if not isinstance(registry_data, dict) or "guidelines" not in registry_data:
        return {
            "check_name": "representativeness_analysis",
            "status": "fail",
            "commit": _git_commit(),
            "input_hash": "",
            "output_hash": "",
            "metrics": {},
            "failures": [{"detail": f"Registry file unreadable or missing 'guidelines': {registry_path}"}],
        }

    guidelines: list[dict] = [g for g in registry_data["guidelines"] if isinstance(g, dict)]
    logger.info("Loaded %d guidelines from %s", len(guidelines), registry_path)

    # Input files for hashing
    input_files: list[Path] = [registry_path]
    for g in guidelines:
        gid = g["guideline_id"]
        input_files.extend(
            [
                sgsc_dir / gid / f"{gid}_constraints.json",
                sgsc_dir / gid / "atoms_smoke.json",
                sgsc_dir / gid / f"{gid}_scenarios.json",
                sgsc_dir / gid / f"{gid}_graph.json",
            ]
        )

    analysis_dir = REPO_ROOT / "evidence_pack" / "analysis"

    # ---- Run all axes ----
    failures: list[dict] = []

    domain_metrics = _axis_domain(guidelines)
    constraint_metrics = _axis_constraint_type(guidelines, sgsc_dir)
    conditionality_metrics = _axis_conditionality(guidelines, sgsc_dir)
    timing_metrics = _axis_timing(guidelines, sgsc_dir)
    alternatives_metrics = _axis_alternatives(guidelines, sgsc_dir)
    source_quality_metrics = _axis_source_quality(analysis_dir)
    scenario_yield_metrics = _axis_scenario_yield(guidelines, sgsc_dir)
    transition_metrics = _axis_transition_complexity(guidelines, sgsc_dir)
    held_out_metrics = _axis_held_out(guidelines)

    # ---- Aggregate metrics ----
    metrics = {
        "guideline_count": len(guidelines),
        "registry": str(registry_path.name),
        "domain": domain_metrics,
        "constraint_type": constraint_metrics,
        "conditionality": conditionality_metrics,
        "timing": timing_metrics,
        "alternatives": alternatives_metrics,
        "source_quality": source_quality_metrics,
        "scenario_yield": scenario_yield_metrics,
        "transition_complexity": transition_metrics,
        "held_out": held_out_metrics,
    }

    # ---- Determine status ----
    # warn if >50% guidelines are missing critical artifacts
    n_missing_constraints = constraint_metrics.get("guidelines_missing_constraints", 0)
    n_missing_atoms = conditionality_metrics.get("guidelines_missing_atoms", 0)
    n_missing_scenarios = alternatives_metrics.get("guidelines_missing_scenarios", 0)
    n_guidelines = max(len(guidelines), 1)

    warn_threshold = 0.5
    if (
        n_missing_constraints / n_guidelines > warn_threshold
        or n_missing_atoms / n_guidelines > warn_threshold
        or n_missing_scenarios / n_guidelines > warn_threshold
    ):
        status = "warn"
        failures.append(
            {
                "detail": (
                    f"High missing-file rate — constraints missing: {n_missing_constraints}, "
                    f"atoms missing: {n_missing_atoms}, "
                    f"scenarios missing: {n_missing_scenarios} "
                    f"(out of {len(guidelines)} guidelines)"
                )
            }
        )
    else:
        status = "pass"

    # Build report (without output_hash first, then compute it)
    report = {
        "check_name": "representativeness_analysis",
        "status": status,
        "commit": _git_commit(),
        "input_hash": _hash_files(input_files),
        "output_hash": "",
        "metrics": metrics,
        "failures": failures,
    }

    report_bytes = json.dumps(report, sort_keys=True).encode()
    report["output_hash"] = hashlib.sha256(report_bytes).hexdigest()

    # ---- Write JSON output ----
    output_base.mkdir(parents=True, exist_ok=True)
    out_path = output_base / "representativeness_profile.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Profile written to %s", out_path)

    # ---- Append LaTeX macros ----
    macros = _build_macros(metrics)
    tex_path = REPO_ROOT / "paper" / "auto_numbers_sgsc.tex"
    _append_macros(tex_path, macros)

    return report


def _append_macros(tex_path: Path, macros: list[str]) -> None:
    """Append representativeness macros to auto_numbers_sgsc.tex (print to stdout).

    Prints the block so the caller can redirect if needed, and also appends
    (without overwrite) if the file is writable.
    """
    block_lines = [
        "% --- Representativeness analysis macros (analyze_representativeness.py) ---",
        *macros,
        "",
    ]

    block = "\n".join(block_lines) + "\n"
    print()
    print("% LaTeX macros for auto_numbers_sgsc.tex:")
    print(block, end="")

    try:
        existing = tex_path.read_text(encoding="utf-8") if tex_path.exists() else ""
        # Only append if this block is not already present (idempotent)
        marker = "% --- Representativeness analysis macros"
        if marker not in existing:
            with tex_path.open("a", encoding="utf-8") as fh:
                fh.write(block)
            logger.info("Macros appended to %s", tex_path)
        else:
            logger.info("Macros already present in %s — skipping append", tex_path)
    except OSError as exc:
        logger.warning("Could not append macros to %s: %s", tex_path, exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run representativeness analysis CLI."""
    parser = argparse.ArgumentParser(
        description="Representativeness analysis — domain complexity profile for SGSC pilot."
    )
    parser.add_argument(
        "--registry",
        default=str(REPO_ROOT / "configs" / "sgsc" / "pilot_14_registry.json"),
        help="Path to pilot_14_registry.json or full_25_registry.json",
    )
    parser.add_argument(
        "--sgsc-dir",
        default=str(REPO_ROOT / "sgsc_output"),
        help="Root directory of SGSC output (one sub-dir per guideline_id)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "evidence_pack" / "analysis"),
        help="Directory to write representativeness_profile.json",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    registry_path = Path(args.registry)
    sgsc_dir = Path(args.sgsc_dir)
    output_dir = Path(args.output_dir)

    if not registry_path.exists():
        logger.error("Registry file not found: %s", registry_path)
        return 1

    if not sgsc_dir.is_dir():
        logger.error("SGSC output dir not found: %s", sgsc_dir)
        return 1

    report = run_analysis(registry_path, output_dir, sgsc_dir)

    # ---- Summary printout ----
    m = report["metrics"]
    print()
    print("=== Representativeness Profile ===")
    print(f"Status     : {report['status'].upper()}")
    print(f"Registry   : {m.get('registry', '?')}")
    print(f"Guidelines : {m.get('guideline_count', 0)}")

    dm = m.get("domain", {})
    print(f"\n[Axis 1] Domains ({dm.get('domain_count', 0)} unique):")
    for dom, cnt in sorted(dm.get("domain_distribution", {}).items()):
        print(f"  {dom}: {cnt}")

    cm = m.get("constraint_type", {})
    print(f"\n[Axis 2] Constraint types ({cm.get('total_constraints_loaded', 0)} total):")
    for ctype, cnt in sorted(cm.get("constraint_type_distribution", {}).items()):
        print(f"  {ctype}: {cnt}")

    cond = m.get("conditionality", {})
    print(
        f"\n[Axis 3] Guarded atoms: {cond.get('guarded_atom_count', 0)}"
        f" / {cond.get('total_atoms', 0)}"
        f" = {cond.get('guarded_atom_pct', 0)}%"
    )

    tm = m.get("timing", {})
    print(
        f"[Axis 4] Timed constraints: {tm.get('timed_constraint_count', 0)}"
        f" / {tm.get('total_constraints_for_timing', 0)}"
        f" = {tm.get('timed_constraint_pct', 0)}%"
    )

    alt = m.get("alternatives", {})
    print(
        f"[Axis 5] Counterfactual scenarios: {alt.get('counterfactual_scenario_count', 0)}"
        f" / {alt.get('total_scenarios', 0)}"
        f" = {alt.get('counterfactual_pct', 0)}%"
    )

    sq = m.get("source_quality", {})
    if sq.get("source_quality_available"):
        inner = sq.get("source_quality", {})
        fpr = inner.get("field_pass_rates", {})
        print(
            f"[Axis 6] Source quality available — fuzzy-only: {inner.get('fuzzy_only_count', 0)},",
            f"contradiction candidates: {inner.get('contradiction_candidates', 0)}",
        )
        if fpr:
            print("         Field pass rates:")
            for field, rate in sorted(fpr.items()):
                print(f"           {field:14s}: {rate:.1%}")
    else:
        print("[Axis 6] Source quality: not available (run check_field_entailment_acceptance.py first)")

    sy = m.get("scenario_yield", {})
    print(
        f"[Axis 7] Scenario yield — avg: {sy.get('avg_yield', 0)},"
        f" min: {sy.get('min_yield', 0)}, max: {sy.get('max_yield', 0)}"
    )

    tc = m.get("transition_complexity", {})
    print(
        f"[Axis 8] Graphs with transitions: {tc.get('graphs_with_transitions', 0)}"
        f" / {tc.get('graphs_checked', 0)}"
        f" = {tc.get('transition_pct', 0)}%"
    )

    ho = m.get("held_out", {})
    print(f"[Axis 9] Held-out: {ho.get('held_out_count', 0)} guidelines")
    if ho.get("held_out_ids"):
        print(f"         {ho['held_out_ids']}")

    if report["failures"]:
        print("\nWarnings/Failures:")
        for f in report["failures"]:
            print(f"  - {f.get('detail', f)}")

    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
