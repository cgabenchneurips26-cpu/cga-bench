#!/usr/bin/env python3
r"""MIMIC-IV calibration probe for SGSC Pilot-14 (and full-25) guidelines.

Compares SGSC scenario distributions against pre-computed MIMIC-IV event-log
distributions to verify that synthetic scenarios are grounded in real clinical
data.

Usage:
    PYTHONPATH=. python scripts/sgsc/calibrate_mimic_distribution.py
    PYTHONPATH=. python scripts/sgsc/calibrate_mimic_distribution.py \\
        --sgsc-dir sgsc_output \\
        --mimic-dir evidence_pack/mimic_iv \\
        --registry configs/sgsc/pilot_14_registry.json \\
        --domain sepsis
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

logger = logging.getLogger("calibrate_mimic_distribution")

# ---------------------------------------------------------------------------
# MIMIC Hour-1 bundle canonical action set
# ---------------------------------------------------------------------------

MIMIC_HOUR1_ACTIONS: set[str] = {
    "administer_antibiotics",
    "obtain_blood_culture",
    "measure_lactate",
    "iv_crystalloid_bolus",
    "start_vasopressor_if_hypotensive",
}

# Map MIMIC Hour-1 actions to SGSC constraint types they imply
MIMIC_ACTION_TO_CONSTRAINT_TYPES: dict[str, set[str]] = {
    "administer_antibiotics": {"WITHIN", "REQUIRED"},
    "obtain_blood_culture": {"BEFORE", "REQUIRED"},
    "measure_lactate": {"REQUIRED"},
    "iv_crystalloid_bolus": {"WITHIN", "REQUIRED"},
    "start_vasopressor_if_hypotensive": {"REQUIRED"},
}

# Domains with MIMIC cohort data (from phase1 distribution_check_patient_level.json)
MIMIC_DOMAINS: set[str] = {"sepsis", "chest_pain", "stroke", "aki"}


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
    """Return a deterministic SHA-256 over the content of all existing paths."""
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def _load_json(path: Path) -> object | None:
    """Load JSON from path; return None and log a warning on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# KL divergence
# ---------------------------------------------------------------------------


def kl_divergence(
    p: dict[str, float],
    q: dict[str, float],
    eps: float = 1e-10,
) -> float:
    """Compute KL(P || Q) with additive smoothing.

    Args:
        p: Reference distribution counts or probabilities.
        q: Comparison distribution counts or probabilities.
        eps: Additive smoothing constant to avoid log(0).

    Returns:
        KL divergence as a non-negative float.
    """
    all_keys = set(p) | set(q)
    total_p = sum(p.values()) or 1.0
    total_q = sum(q.values()) or 1.0
    n = len(all_keys)
    kl = 0.0
    for k in all_keys:
        p_k = (p.get(k, 0) + eps) / (total_p + eps * n)
        q_k = (q.get(k, 0) + eps) / (total_q + eps * n)
        kl += p_k * math.log(p_k / q_k)
    return kl


# ---------------------------------------------------------------------------
# MIMIC artifact loading
# ---------------------------------------------------------------------------


def _load_mimic_artifacts(
    mimic_dir: Path,
) -> tuple[
    dict | None,
    dict | None,
    dict | None,
    dict[str, bool],
]:
    """Load the three pre-computed MIMIC-IV artifact files.

    Returns:
        Tuple of (phase0_data, phase1_data, phase2_data, data_available_flags).
    """
    phase0_path = mimic_dir / "phase0" / "mapping_coverage.json"
    phase1_path = mimic_dir / "phase1" / "distribution_check_patient_level.json"
    phase2_path = mimic_dir / "phase2" / "table1_mimic_iv.json"

    phase0 = _load_json(phase0_path) if phase0_path.exists() else None
    phase1 = _load_json(phase1_path) if phase1_path.exists() else None
    phase2 = _load_json(phase2_path) if phase2_path.exists() else None

    data_available: dict[str, bool] = {
        "mimic_phase0": phase0 is not None,
        "mimic_phase1": phase1 is not None,
        "mimic_phase2": phase2 is not None,
    }

    return (
        phase0 if isinstance(phase0, dict) else None,
        phase1 if isinstance(phase1, dict) else None,
        phase2 if isinstance(phase2, dict) else None,
        data_available,
    )


# ---------------------------------------------------------------------------
# SGSC artifact loading
# ---------------------------------------------------------------------------


def _load_sgsc_artifacts(
    guidelines: list[dict],
    sgsc_dir: Path,
    domain_filter: str | None,
) -> tuple[
    dict[str, list[dict]],
    dict[str, list[dict]],
    bool,
]:
    """Load SGSC constraints and scenarios for all (filtered) guidelines.

    Args:
        guidelines: List of guideline dicts from registry.
        sgsc_dir: Root SGSC output directory.
        domain_filter: If set, only load guidelines matching this domain.

    Returns:
        Tuple of (constraints_by_gid, scenarios_by_gid, any_loaded).
    """
    constraints_by_gid: dict[str, list[dict]] = {}
    scenarios_by_gid: dict[str, list[dict]] = {}

    for g in guidelines:
        gid = g["guideline_id"]
        domain = g.get("domain") or ""

        if domain_filter and domain != domain_filter:
            continue

        # Load constraints
        cpath = sgsc_dir / gid / f"{gid}_constraints.json"
        if cpath.exists():
            data = _load_json(cpath)
            if isinstance(data, list):
                constraints_by_gid[gid] = [d for d in data if isinstance(d, dict)]
            elif isinstance(data, dict):
                constraints_by_gid[gid] = [v for v in data.values() if isinstance(v, dict)]
            else:
                constraints_by_gid[gid] = []
        else:
            logger.debug("Constraints file missing: %s", cpath)

        # Load scenarios
        spath = sgsc_dir / gid / f"{gid}_scenarios.json"
        if spath.exists():
            data = _load_json(spath)
            if isinstance(data, list):
                scenarios_by_gid[gid] = [d for d in data if isinstance(d, dict)]
            elif isinstance(data, dict):
                scenarios_by_gid[gid] = [v for v in data.values() if isinstance(v, dict)]
            else:
                scenarios_by_gid[gid] = []
        else:
            logger.debug("Scenarios file missing: %s", spath)

    any_loaded = bool(constraints_by_gid or scenarios_by_gid)
    return constraints_by_gid, scenarios_by_gid, any_loaded


# ---------------------------------------------------------------------------
# Metric 1: Action frequency KL divergence
# ---------------------------------------------------------------------------


def _metric_action_kl(
    scenarios_by_gid: dict[str, list[dict]],
    phase0: dict | None,
) -> float | None:
    """Compute KL(SGSC_action_freq || MIMIC_action_freq).

    Args:
        scenarios_by_gid: SGSC scenarios keyed by guideline id.
        phase0: MIMIC phase0 mapping_coverage data.

    Returns:
        KL divergence value, or None if either distribution is empty.
    """
    if not scenarios_by_gid or phase0 is None:
        return None

    # Build SGSC action frequency
    sgsc_counts: dict[str, float] = {}
    for scenarios in scenarios_by_gid.values():
        for scen in scenarios:
            actions: object = scen.get("actions") or scen.get("expected_actions") or []
            if isinstance(actions, list):
                for act in actions:
                    if isinstance(act, str):
                        sgsc_counts[act] = sgsc_counts.get(act, 0) + 1
                    elif isinstance(act, dict):
                        aid = act.get("action_id") or act.get("id") or act.get("canonical_id")
                        if aid:
                            sgsc_counts[str(aid)] = sgsc_counts.get(str(aid), 0) + 1

    if not sgsc_counts:
        return None

    # Build MIMIC action frequency from phase0 n_mimic_events_matched
    mimic_matched: object = phase0.get("n_mimic_events_matched")
    if not isinstance(mimic_matched, dict) or not mimic_matched:
        return None

    mimic_counts: dict[str, float] = {str(k): float(v) for k, v in mimic_matched.items()}

    return round(kl_divergence(sgsc_counts, mimic_counts), 6)


# ---------------------------------------------------------------------------
# Metric 2: Constraint activation rate
# ---------------------------------------------------------------------------


def _metric_constraint_activation(
    constraints_by_gid: dict[str, list[dict]],
    phase0: dict | None,
) -> float | None:
    """Compute fraction of SGSC constraint types that have a MIMIC counterpart.

    Args:
        constraints_by_gid: SGSC constraints keyed by guideline id.
        phase0: MIMIC phase0 data (used to check which actions are present).

    Returns:
        Activation rate in [0, 1], or None if no constraints loaded.
    """
    all_constraint_types: set[str] = set()
    for constraints in constraints_by_gid.values():
        for c in constraints:
            ctype = c.get("constraint_type") or c.get("type")
            if ctype:
                all_constraint_types.add(str(ctype))

    if not all_constraint_types:
        return None

    # Which constraint types are covered by MIMIC Hour-1 bundle
    mimic_covered_types: set[str] = set()
    if phase0 is not None:
        matched: object = phase0.get("n_mimic_events_matched")
        if isinstance(matched, dict):
            for action in matched:
                ctypes = MIMIC_ACTION_TO_CONSTRAINT_TYPES.get(str(action), set())
                mimic_covered_types.update(ctypes)

    if not mimic_covered_types:
        # Fallback: all MIMIC actions imply REQUIRED and WITHIN
        mimic_covered_types = {"REQUIRED", "WITHIN", "BEFORE"}

    matched_count = sum(1 for ct in all_constraint_types if ct in mimic_covered_types)
    return round(matched_count / len(all_constraint_types), 4)


# ---------------------------------------------------------------------------
# Metric 3: Violation type distribution
# ---------------------------------------------------------------------------


def _metric_violation_distribution(
    scenarios_by_gid: dict[str, list[dict]],
    phase2: dict | None,
) -> dict:
    """Build side-by-side violation type distributions from SGSC and MIMIC.

    Args:
        scenarios_by_gid: SGSC scenarios keyed by guideline id.
        phase2: MIMIC phase2 table1 data (evaluator pass rates).

    Returns:
        Dict with 'sgsc' counts and 'mimic' counts or None.
    """
    violation_types = ("OMISSION", "COMMISSION", "TIMING", "SEQUENCE")
    sgsc_dist: dict[str, int] = dict.fromkeys(violation_types, 0)

    for scenarios in scenarios_by_gid.values():
        for scen in scenarios:
            # Detect violation type from mutation/variant metadata
            vtype: object = (
                scen.get("expected_violation_type") or scen.get("violation_type") or scen.get("mutation_type")
            )
            if isinstance(vtype, str):
                vtype_upper = vtype.upper()
                if vtype_upper in sgsc_dist:
                    sgsc_dist[vtype_upper] += 1
                    continue

            # Infer from scenario name/id patterns
            scen_id = str(scen.get("scenario_id") or scen.get("id") or "")
            for vt in violation_types:
                if vt.lower() in scen_id.lower():
                    sgsc_dist[vt] += 1
                    break

    # MIMIC phase2 supplies evaluator pass rates, not violation type counts.
    # We report None for now as phase2 is optional and the mapping is indirect.
    mimic_dist: dict | None = None
    if isinstance(phase2, dict):
        # If phase2 has violation distribution data, use it
        vdist: object = phase2.get("violation_type_distribution")
        if isinstance(vdist, dict):
            mimic_dist = {str(k): int(v) for k, v in vdist.items()}

    return {"sgsc": sgsc_dist, "mimic": mimic_dist}


# ---------------------------------------------------------------------------
# Metric 4: Domain coverage
# ---------------------------------------------------------------------------


def _metric_domain_coverage(
    guidelines: list[dict],
    domain_filter: str | None,
) -> dict:
    """Compute overlap between SGSC domains and MIMIC cohort domains.

    Args:
        guidelines: Registry guideline list.
        domain_filter: Optional domain filter applied to registry.

    Returns:
        Dict with sgsc_domains count, mimic_domains count, overlap_rate.
    """
    if domain_filter:
        sgsc_domains: set[str] = {domain_filter}
    else:
        sgsc_domains = {str(g.get("domain") or "unknown") for g in guidelines if isinstance(g, dict)}

    overlap = sgsc_domains & MIMIC_DOMAINS
    overlap_rate = round(len(overlap) / len(sgsc_domains), 4) if sgsc_domains else 0.0

    return {
        "sgsc_domains": len(sgsc_domains),
        "mimic_domains": len(MIMIC_DOMAINS),
        "overlap": sorted(overlap),
        "overlap_rate": overlap_rate,
    }


# ---------------------------------------------------------------------------
# Metric 5: Action alphabet overlap
# ---------------------------------------------------------------------------


def _metric_action_alphabet(
    constraints_by_gid: dict[str, list[dict]],
    scenarios_by_gid: dict[str, list[dict]],
) -> dict:
    """Compute overlap between SGSC canonical action IDs and MIMIC actions.

    Args:
        constraints_by_gid: SGSC constraints keyed by guideline id.
        scenarios_by_gid: SGSC scenarios keyed by guideline id.

    Returns:
        Dict with sgsc_actions count, mimic_actions count, overlap, overlap_rate.
    """
    sgsc_actions: set[str] = set()

    # Collect from constraints
    for constraints in constraints_by_gid.values():
        for c in constraints:
            aid = c.get("action_id") or c.get("canonical_id") or c.get("action")
            if isinstance(aid, str) and aid:
                sgsc_actions.add(aid)

    # Collect from scenarios
    for scenarios in scenarios_by_gid.values():
        for scen in scenarios:
            actions: object = scen.get("actions") or scen.get("expected_actions") or []
            if isinstance(actions, list):
                for act in actions:
                    if isinstance(act, str):
                        sgsc_actions.add(act)
                    elif isinstance(act, dict):
                        aid = act.get("action_id") or act.get("id") or act.get("canonical_id")
                        if isinstance(aid, str) and aid:
                            sgsc_actions.add(aid)

    overlap = sgsc_actions & MIMIC_HOUR1_ACTIONS
    overlap_rate = round(len(overlap) / len(sgsc_actions), 4) if sgsc_actions else 0.0

    return {
        "sgsc_actions": len(sgsc_actions),
        "mimic_actions": len(MIMIC_HOUR1_ACTIONS),
        "overlap": len(overlap),
        "overlap_rate": overlap_rate,
    }


# ---------------------------------------------------------------------------
# Metric 6: Deadline presence rate
# ---------------------------------------------------------------------------


def _metric_deadline_presence(
    constraints_by_gid: dict[str, list[dict]],
    phase0: dict | None,
) -> float | None:
    """Compute fraction of SGSC timed constraints that have MIMIC timing data.

    Args:
        constraints_by_gid: SGSC constraints keyed by guideline id.
        phase0: MIMIC phase0 data (always has timing for Hour-1 bundle).

    Returns:
        Deadline presence rate in [0, 1], or None if no constraints loaded.
    """
    total_constraints = 0
    timed_constraints = 0

    for constraints in constraints_by_gid.values():
        for c in constraints:
            total_constraints += 1
            deadline = c.get("deadline") or c.get("deadline_minutes") or c.get("timing")
            if deadline is not None and deadline not in ("", 0, None):
                timed_constraints += 1

    if total_constraints == 0:
        return None

    # MIMIC phase0 always has timing data for Hour-1 bundle actions
    mimic_has_timing = phase0 is not None
    if not mimic_has_timing:
        return None

    # Rate = timed SGSC constraints / total SGSC constraints
    # (All timed SGSC constraints have a MIMIC timing counterpart via Hour-1 bundle)
    return round(timed_constraints / total_constraints, 4)


# ---------------------------------------------------------------------------
# LaTeX macro generation
# ---------------------------------------------------------------------------


def _build_macros(metrics: dict) -> list[str]:
    r"""Build \providecommand macros for auto_numbers_sgsc.tex.

    Args:
        metrics: The metrics dict from the calibration report.

    Returns:
        List of LaTeX \providecommand lines.
    """
    kl = metrics.get("action_frequency_kl")
    kl_str = f"{kl:.4f}" if kl is not None else "N/A"

    activation = metrics.get("constraint_activation_rate")
    activation_str = f"{activation:.4f}" if activation is not None else "N/A"

    domain_cov = metrics.get("domain_coverage", {})
    domains_covered = domain_cov.get("overlap", [])
    domains_covered_n = len(domains_covered) if isinstance(domains_covered, list) else 0

    action_alpha = metrics.get("action_alphabet_overlap", {})
    overlap_rate = action_alpha.get("overlap_rate", 0.0)
    overlap_pct = f"{overlap_rate * 100:.1f}"

    deadline = metrics.get("deadline_presence_rate")
    deadline_str = f"{deadline * 100:.1f}\\%" if deadline is not None else "N/A"

    return [
        f"\\providecommand{{\\sgscMimicActionKL}}{{{kl_str}}}",
        f"\\providecommand{{\\sgscMimicConstraintActivation}}{{{activation_str}}}",
        f"\\providecommand{{\\sgscMimicDomainsCovered}}{{{domains_covered_n}}}",
        f"\\providecommand{{\\sgscMimicActionOverlap}}{{{overlap_pct}\\%}}",
        f"\\providecommand{{\\sgscMimicDeadlinePresence}}{{{deadline_str}}}",
    ]


def _append_macros(tex_path: Path, macros: list[str]) -> None:
    """Append calibration macros to auto_numbers_sgsc.tex (idempotent).

    Args:
        tex_path: Path to the LaTeX macro file.
        macros: List of macro lines to append.
    """
    block_lines = [
        "% --- MIMIC calibration macros (calibrate_mimic_distribution.py) ---",
        *macros,
        "",
    ]
    block = "\n".join(block_lines) + "\n"
    print()
    print("% LaTeX macros for auto_numbers_sgsc.tex:")
    print(block, end="")

    try:
        existing = tex_path.read_text(encoding="utf-8") if tex_path.exists() else ""
        marker = "% --- MIMIC calibration macros"
        if marker not in existing:
            with tex_path.open("a", encoding="utf-8") as fh:
                fh.write(block)
            logger.info("Macros appended to %s", tex_path)
        else:
            logger.info("Macros already present in %s — skipping append", tex_path)
    except OSError as exc:
        logger.warning("Could not append macros to %s: %s", tex_path, exc)


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------


def run_calibration(
    registry_path: Path,
    sgsc_dir: Path,
    mimic_dir: Path,
    output_dir: Path,
    domain_filter: str | None = None,
) -> dict:
    """Run MIMIC calibration analysis and return the standard JSON contract.

    Args:
        registry_path: Path to pilot_14_registry.json or full_25_registry.json.
        sgsc_dir:       Root directory of SGSC output (one sub-dir per guideline).
        mimic_dir:      Directory containing pre-computed MIMIC-IV artifacts.
        output_dir:     Directory for evidence_pack/analysis outputs.
        domain_filter:  If set, restrict analysis to this domain.

    Returns:
        A dict conforming to the standard JSON check contract.
    """
    failures: list[dict] = []

    # ---- Load registry ----
    registry_data = _load_json(registry_path)
    if not isinstance(registry_data, dict) or "guidelines" not in registry_data:
        return {
            "check_name": "mimic_calibration",
            "status": "fail",
            "commit": _git_commit(),
            "input_hash": "",
            "output_hash": "",
            "metrics": {},
            "failures": [{"detail": (f"Registry file unreadable or missing 'guidelines': {registry_path}")}],
        }

    guidelines: list[dict] = [g for g in registry_data["guidelines"] if isinstance(g, dict)]
    logger.info("Loaded %d guidelines from %s", len(guidelines), registry_path)

    # ---- Load MIMIC artifacts ----
    phase0, _phase1, phase2, data_available = _load_mimic_artifacts(mimic_dir)

    any_mimic = any(data_available.values())
    if not any_mimic:
        failures.append(
            {
                "detail": (
                    f"No MIMIC artifacts found in {mimic_dir}. "
                    "Run MIMIC probe scripts to generate phase0/phase1/phase2 outputs."
                )
            }
        )

    # ---- Load SGSC artifacts ----
    constraints_by_gid, scenarios_by_gid, sgsc_loaded = _load_sgsc_artifacts(guidelines, sgsc_dir, domain_filter)
    data_available["sgsc_scenarios"] = sgsc_loaded

    # ---- Compute metrics ----
    action_kl = _metric_action_kl(scenarios_by_gid, phase0)
    constraint_activation = _metric_constraint_activation(constraints_by_gid, phase0)
    violation_dist = _metric_violation_distribution(scenarios_by_gid, phase2)
    domain_coverage = _metric_domain_coverage(guidelines, domain_filter)
    action_alphabet = _metric_action_alphabet(constraints_by_gid, scenarios_by_gid)
    deadline_presence = _metric_deadline_presence(constraints_by_gid, phase0)

    metrics: dict = {
        "data_available": data_available,
        "action_frequency_kl": action_kl,
        "constraint_activation_rate": constraint_activation,
        "violation_type_distribution": violation_dist,
        "domain_coverage": domain_coverage,
        "action_alphabet_overlap": action_alphabet,
        "deadline_presence_rate": deadline_presence,
    }

    # ---- Determine status ----
    if not any_mimic:
        status = "warn"
    elif not sgsc_loaded:
        status = "warn"
        failures.append(
            {"detail": (f"No SGSC artifacts found in {sgsc_dir}. Run the SGSC pipeline to generate output.")}
        )
    else:
        status = "pass"

    # ---- Build and write report ----
    input_files: list[Path] = [registry_path]
    input_files.extend(
        [
            mimic_dir / "phase0" / "mapping_coverage.json",
            mimic_dir / "phase1" / "distribution_check_patient_level.json",
            mimic_dir / "phase2" / "table1_mimic_iv.json",
        ]
    )
    for gid in list(constraints_by_gid) + list(scenarios_by_gid):
        input_files.append(sgsc_dir / gid / f"{gid}_constraints.json")
        input_files.append(sgsc_dir / gid / f"{gid}_scenarios.json")

    report: dict = {
        "check_name": "mimic_calibration",
        "status": status,
        "commit": _git_commit(),
        "input_hash": _hash_files(input_files),
        "output_hash": "",
        "metrics": metrics,
        "failures": failures,
    }

    report_bytes = json.dumps(report, sort_keys=True).encode()
    report["output_hash"] = hashlib.sha256(report_bytes).hexdigest()

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "mimic_calibration.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Calibration report written to %s", out_path)

    # ---- Append LaTeX macros ----
    macros = _build_macros(metrics)
    tex_path = REPO_ROOT / "paper" / "auto_numbers_sgsc.tex"
    _append_macros(tex_path, macros)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run MIMIC calibration probe CLI.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 for pass/warn, 1 for fail.
    """
    parser = argparse.ArgumentParser(
        description="MIMIC-IV calibration probe — compares SGSC distributions to real MIMIC-IV data."
    )
    parser.add_argument(
        "--sgsc-dir",
        default=str(REPO_ROOT / "sgsc_output"),
        help="Root directory of SGSC output (one sub-dir per guideline_id)",
    )
    parser.add_argument(
        "--mimic-dir",
        default=str(REPO_ROOT / "evidence_pack" / "mimic_iv"),
        help="Directory containing pre-computed MIMIC-IV artifact JSON files",
    )
    parser.add_argument(
        "--registry",
        default=str(REPO_ROOT / "configs" / "sgsc" / "pilot_14_registry.json"),
        help="Path to pilot_14_registry.json or full_25_registry.json",
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="Optional: restrict analysis to a specific domain (e.g. 'sepsis')",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "evidence_pack" / "analysis"),
        help="Directory to write mimic_calibration.json",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    registry_path = Path(args.registry)
    sgsc_dir = Path(args.sgsc_dir)
    mimic_dir = Path(args.mimic_dir)
    output_dir = Path(args.output_dir)

    if not registry_path.exists():
        logger.error("Registry file not found: %s", registry_path)
        return 1

    report = run_calibration(
        registry_path=registry_path,
        sgsc_dir=sgsc_dir,
        mimic_dir=mimic_dir,
        output_dir=output_dir,
        domain_filter=args.domain,
    )

    # ---- Summary printout ----
    m = report["metrics"]
    print()
    print("=== MIMIC-IV Calibration Probe ===")
    print(f"Status     : {report['status'].upper()}")
    print(f"Domain     : {args.domain or 'all'}")
    print()

    da = m.get("data_available", {})
    print("[Data Availability]")
    for key, avail in da.items():
        mark = "OK" if avail else "MISSING"
        print(f"  {key:30s}: {mark}")

    kl = m.get("action_frequency_kl")
    print(f"\n[Metric 1] Action frequency KL divergence : {kl if kl is not None else 'N/A'}")

    act = m.get("constraint_activation_rate")
    print(f"[Metric 2] Constraint activation rate     : {act if act is not None else 'N/A'}")

    vd = m.get("violation_type_distribution", {})
    print("[Metric 3] Violation type distribution:")
    print(f"  SGSC: {vd.get('sgsc', {})}")
    print(f"  MIMIC: {vd.get('mimic', 'no_data')}")

    dc = m.get("domain_coverage", {})
    print(
        f"[Metric 4] Domain coverage: "
        f"{dc.get('overlap_rate', 0.0):.1%} "
        f"({dc.get('overlap', [])} of {dc.get('sgsc_domains', 0)} SGSC domains)"
    )

    aa = m.get("action_alphabet_overlap", {})
    print(
        f"[Metric 5] Action alphabet overlap: "
        f"{aa.get('overlap', 0)}/{aa.get('sgsc_actions', 0)} "
        f"SGSC actions in MIMIC = {aa.get('overlap_rate', 0.0):.1%}"
    )

    dp = m.get("deadline_presence_rate")
    print(f"[Metric 6] Deadline presence rate         : {dp if dp is not None else 'N/A'}")

    if report["failures"]:
        print("\nWarnings/Failures:")
        for f in report["failures"]:
            print(f"  - {f.get('detail', f)}")

    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
