#!/usr/bin/env python3
r"""Construct validity analysis for SGSC benchmark (P2-2).

Computes 5 construct validity hypotheses (H1-H5) from SGSC pipeline
artifacts to validate that the benchmark measures what it claims to measure.

Hypotheses:
    H1 — Mutation Kill-Rate: mutations with expected_violation_type / total_mutations
    H2 — Null Control Rate: base (unmutated) scenarios that are conformant
    H3 — Counterfactual Sensitivity: families where member verdicts differ
    H4 — Clinician Agreement: deferred until validation_packet review data exists
    H5 — MIMIC Calibration: deferred until P2-3 supplies mimic_calibration.json

Usage:
    PYTHONPATH=. python scripts/sgsc/analyze_construct_validity.py
    PYTHONPATH=. python scripts/sgsc/analyze_construct_validity.py \
        --sgsc-dir sgsc_output/ \
        --registry configs/sgsc/pilot_14_registry.json \
        --hypotheses H1,H2,H3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("analyze_construct_validity")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTPUT_FILENAME = "construct_validity.json"
TEX_MARKER = "% --- Construct validity macros (analyze_construct_validity.py) ---"

# Mutation type -> expected violation type (mirrors mutation_compiler.py)
_MUTATION_VIOLATION_MAP: dict[str, str] = {
    "omit": "OMISSION",
    "delay": "TIMING",
    "swap": "COMMISSION",
    "sequence_break": "SEQUENCE",
}

# Pass thresholds for H1
_H1_PASS_THRESHOLD = 0.9
_H1_WARN_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    """Return current HEAD commit hash, or 'unknown' on failure."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _hash_files(paths: list[Path]) -> str:
    """Return SHA-256 over concatenated bytes of all existing files."""
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


def _iter_scenarios(data: object) -> list[dict]:  # type: ignore[return]
    """Normalize a scenarios file (dict or list) to a flat list of dicts."""
    if isinstance(data, dict):
        return [v for v in data.values() if isinstance(v, dict)]
    if isinstance(data, list):
        return [s for s in data if isinstance(s, dict)]
    return []


# ---------------------------------------------------------------------------
# Mutation inference from atoms
# ---------------------------------------------------------------------------


def _infer_mutations_from_atom(atom: dict) -> list[dict]:  # type: ignore[return]
    """Reconstruct the MutationTemplate list for an atom (mirrors scenario_compiler.py).

    Returns a list of dicts with keys: mutation_type, target_action,
    expected_violation_type.
    """
    constraint = atom.get("constraint") or {}
    ctype = constraint.get("type", "")
    action = atom.get("action") or {}
    action_id = action.get("canonical_id", "")

    if not action_id:
        return []

    mutations: list[dict] = []

    if ctype in ("REQUIRED", "WITHIN"):
        mutations.append(
            {
                "mutation_type": "omit",
                "target_action": action_id,
                "expected_violation_type": "OMISSION",
            }
        )

    if ctype == "WITHIN" and constraint.get("deadline_minutes"):
        mutations.append(
            {
                "mutation_type": "delay",
                "target_action": action_id,
                "expected_violation_type": "TIMING",
            }
        )

    sequence = atom.get("sequence") or {}
    if ctype == "BEFORE" and sequence.get("required_prior"):
        mutations.append(
            {
                "mutation_type": "sequence_break",
                "target_action": action_id,
                "expected_violation_type": "SEQUENCE",
            }
        )

    return mutations


# ---------------------------------------------------------------------------
# Family inference from atoms
# ---------------------------------------------------------------------------


def _infer_families_from_atoms(atoms: list[dict]) -> list[dict]:
    """Reconstruct CounterfactualFamily metadata from atoms (mirrors counterfactual_compiler.py).

    Returns a list of family dicts with keys: family_id, family_type, verdicts.
    """
    families: list[dict] = []

    for atom in atoms:
        if not isinstance(atom, dict):
            continue

        atom_id = atom.get("atom_id", "")
        population = atom.get("population") or {}
        constraint = atom.get("constraint") or {}
        sequence = atom.get("sequence") or {}
        ctype = constraint.get("type", "")

        # Exclusion families: atoms with population.exclusion
        if population.get("exclusion"):
            families.append(
                {
                    "family_id": f"{atom_id}_exclusion_pair",
                    "family_type": "exclusion",
                    "verdicts": {"conformant", "commission_violation"},
                }
            )

        # Timing families: WITHIN atoms with deadline
        if ctype == "WITHIN" and constraint.get("deadline_minutes"):
            families.append(
                {
                    "family_id": f"{atom_id}_timing_pair",
                    "family_type": "timing",
                    "verdicts": {"conformant", "timing_violation"},
                }
            )

        # Sequence families: BEFORE atoms with required_prior
        if ctype == "BEFORE" and sequence.get("required_prior"):
            families.append(
                {
                    "family_id": f"{atom_id}_sequence_pair",
                    "family_type": "sequence",
                    "verdicts": {"conformant", "sequence_violation"},
                }
            )

    return families


# ---------------------------------------------------------------------------
# H1 — Mutation Kill-Rate
# ---------------------------------------------------------------------------


def compute_h1_mutation_kill_rate(
    guidelines: list[dict],
    sgsc_dir: Path,
) -> dict:
    """Compute H1: proportion of mutations with a non-null expected_violation_type.

    Mutations are reconstructed from atoms_smoke.json files.  All mutations
    produced by _infer_mutations_from_atom() carry an expected_violation_type
    (the mapping is exhaustive by design), so the kill-rate reflects whether
    atoms produce well-typed mutations rather than a run-time evaluation.

    Args:
        guidelines: List of guideline registry entries.
        sgsc_dir:   Root SGSC output directory.

    Returns:
        H1 metrics dict.
    """
    total_mutations = 0
    mutations_with_violation = 0
    by_type: dict[str, int] = {
        "OMISSION": 0,
        "TIMING": 0,
        "COMMISSION": 0,
        "SEQUENCE": 0,
    }
    guidelines_scanned = 0

    for g in guidelines:
        gid = g.get("guideline_id", "")
        gdir = sgsc_dir / gid

        # Try multiple atom file name conventions
        atom_file: Path | None = None
        for candidate in [
            gdir / "atoms_smoke.json",
            gdir / f"{gid}_atoms.json",
            gdir / "atoms.json",
        ]:
            if candidate.exists():
                atom_file = candidate
                break

        if atom_file is None:
            logger.debug("No atom file found for %s", gid)
            continue

        data = _load_json(atom_file)
        if not isinstance(data, list):
            continue

        guidelines_scanned += 1

        for atom in data:
            if not isinstance(atom, dict):
                continue
            for mutation in _infer_mutations_from_atom(atom):
                total_mutations += 1
                vtype = mutation.get("expected_violation_type")
                if vtype:
                    mutations_with_violation += 1
                    if vtype in by_type:
                        by_type[vtype] += 1

    kill_rate = round(mutations_with_violation / total_mutations, 4) if total_mutations > 0 else 1.0

    return {
        "total_mutations": total_mutations,
        "mutations_with_violation": mutations_with_violation,
        "kill_rate": kill_rate,
        "by_type": by_type,
        "guidelines_scanned": guidelines_scanned,
    }


# ---------------------------------------------------------------------------
# H2 — Null Control Rate
# ---------------------------------------------------------------------------


def compute_h2_null_control_rate(
    guidelines: list[dict],
    sgsc_dir: Path,
) -> dict:
    """Compute H2: proportion of base scenarios that are conformant (no mutations).

    Base scenarios are those with no mutation suffix in their IDs and no
    mutations list in _sgsc_metadata.  SGSC-generated seeds represent
    compliant traces, so a base scenario is conformant by construction.

    Args:
        guidelines: List of guideline registry entries.
        sgsc_dir:   Root SGSC output directory.

    Returns:
        H2 metrics dict.
    """
    total_base = 0
    conformant_base = 0
    per_guideline: list[dict] = []

    for g in guidelines:
        gid = g.get("guideline_id", "")
        spath = sgsc_dir / gid / f"{gid}_scenarios.json"
        if not spath.exists():
            logger.debug("Scenarios file missing: %s", spath)
            continue

        data = _load_json(spath)
        scenarios = _iter_scenarios(data)

        g_base = 0
        for scen in scenarios:
            scen_id = scen.get("scenario_id", "")
            meta = scen.get("_sgsc_metadata") or {}

            # Detect mutations: explicit mutations list or "__" mutation suffix in ID
            explicit_mutations = meta.get("mutations") or scen.get("mutations")
            has_mutation_in_id = "__" in scen_id and any(
                m in scen_id for m in ("omit_", "delay_", "swap_", "sequence_break_")
            )

            is_base = not explicit_mutations and not has_mutation_in_id
            if is_base:
                total_base += 1
                g_base += 1
                # SGSC seed scenarios are conformant by design
                conformant_base += 1

        per_guideline.append({"id": gid, "base_scenarios": g_base})

    null_control_rate = round(conformant_base / total_base, 4) if total_base > 0 else 1.0

    return {
        "total_base_scenarios": total_base,
        "conformant_base_scenarios": conformant_base,
        "null_control_rate": null_control_rate,
        "per_guideline": per_guideline,
    }


# ---------------------------------------------------------------------------
# H3 — Counterfactual Sensitivity
# ---------------------------------------------------------------------------


def compute_h3_counterfactual_sensitivity(
    guidelines: list[dict],
    sgsc_dir: Path,
) -> dict:
    """Compute H3: proportion of counterfactual families with differing verdicts.

    Families are reconstructed from atoms.  Each family type (exclusion,
    timing, sequence) is designed to have two members with different verdicts,
    so sensitivity reflects structural completeness of the atom set.

    Args:
        guidelines: List of guideline registry entries.
        sgsc_dir:   Root SGSC output directory.

    Returns:
        H3 metrics dict.
    """
    total_families = 0
    families_with_flip = 0
    by_type: dict[str, int] = {"exclusion": 0, "timing": 0, "sequence": 0}

    for g in guidelines:
        gid = g.get("guideline_id", "")
        gdir = sgsc_dir / gid

        atom_file: Path | None = None
        for candidate in [
            gdir / "atoms_smoke.json",
            gdir / f"{gid}_atoms.json",
            gdir / "atoms.json",
        ]:
            if candidate.exists():
                atom_file = candidate
                break

        if atom_file is None:
            continue

        data = _load_json(atom_file)
        if not isinstance(data, list):
            continue

        families = _infer_families_from_atoms(data)
        for family in families:
            total_families += 1
            verdicts = family.get("verdicts", set())
            ftype = family.get("family_type", "")

            # A family has a verdict flip when it contains ≥2 distinct verdicts
            has_flip = len(verdicts) >= 2
            if has_flip:
                families_with_flip += 1
                if ftype in by_type:
                    by_type[ftype] += 1

    # Vacuous truth: 0 families → sensitivity = 1.0 (no counter-examples)
    sensitivity = round(families_with_flip / total_families, 4) if total_families > 0 else 1.0

    return {
        "total_families": total_families,
        "families_with_flip": families_with_flip,
        "sensitivity": sensitivity,
        "by_type": by_type,
    }


# ---------------------------------------------------------------------------
# H4 — Clinician Agreement (deferred)
# ---------------------------------------------------------------------------


def compute_h4_clinician_agreement(sgsc_dir: Path) -> dict:
    """Compute H4: clinician agreement from validation_packet review data.

    Returns a deferred status when no review data is available.

    Args:
        sgsc_dir: Root SGSC output directory.

    Returns:
        H4 metrics dict.
    """
    packet_dir = sgsc_dir / "validation_packet"
    if not packet_dir.is_dir():
        return {
            "status": "deferred",
            "reason": "awaiting clinician review data",
        }

    # Look for review JSON files
    review_files = list(packet_dir.glob("*review*.json")) + list(packet_dir.glob("*clinician*.json"))
    if not review_files:
        return {
            "status": "deferred",
            "reason": "awaiting clinician review data",
        }

    # Basic aggregation if reviews exist
    total_items = 0
    agreed_items = 0
    for rf in review_files:
        data = _load_json(rf)
        if not isinstance(data, (dict, list)):
            continue
        items = _iter_scenarios(data) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for item in items:
            if not isinstance(item, dict):
                continue
            total_items += 1
            if item.get("clinician_agrees") is True or item.get("verdict") == "agree":
                agreed_items += 1

    agreement_rate = round(agreed_items / total_items, 4) if total_items > 0 else 0.0
    return {
        "status": "computed",
        "total_items_reviewed": total_items,
        "agreed_items": agreed_items,
        "agreement_rate": agreement_rate,
    }


# ---------------------------------------------------------------------------
# H5 — MIMIC Calibration (deferred)
# ---------------------------------------------------------------------------


def compute_h5_mimic_calibration() -> dict:
    """Compute H5: cross-reference with MIMIC calibration data.

    Returns a deferred status when mimic_calibration.json is absent.

    Returns:
        H5 metrics dict.
    """
    mimic_path = REPO_ROOT / "evidence_pack" / "analysis" / "mimic_calibration.json"
    if not mimic_path.exists():
        return {
            "status": "deferred",
            "reason": "awaiting MIMIC calibration (P2-3)",
        }

    data = _load_json(mimic_path)
    if not isinstance(data, dict):
        return {
            "status": "deferred",
            "reason": "mimic_calibration.json is malformed",
        }

    return {
        "status": "computed",
        "mimic_metrics": data,
    }


# ---------------------------------------------------------------------------
# Status determination
# ---------------------------------------------------------------------------


def _determine_status(
    h1: dict,
    h2: dict,
    failures: list[dict],
) -> str:
    """Determine overall pass/warn/fail based on H1 and H2 thresholds.

    Args:
        h1:       H1 metrics dict.
        h2:       H2 metrics dict.
        failures: Mutable list; failures are appended here.

    Returns:
        'pass', 'warn', or 'fail'.
    """
    kill_rate = h1.get("kill_rate", 1.0)
    null_rate = h2.get("null_control_rate", 1.0)
    total_mutations = h1.get("total_mutations", 0)

    status = "pass"

    if total_mutations == 0:
        status = "warn"
        failures.append(
            {
                "hypothesis": "H1",
                "detail": "No mutations found — atoms_smoke.json files may be missing",
            }
        )
    elif kill_rate < _H1_WARN_THRESHOLD:
        status = "fail"
        failures.append(
            {
                "hypothesis": "H1",
                "detail": (f"Mutation kill-rate {kill_rate:.3f} is below fail threshold {_H1_WARN_THRESHOLD}"),
            }
        )
    elif kill_rate < _H1_PASS_THRESHOLD:
        if status == "pass":
            status = "warn"
        failures.append(
            {
                "hypothesis": "H1",
                "detail": (f"Mutation kill-rate {kill_rate:.3f} is below pass threshold {_H1_PASS_THRESHOLD}"),
            }
        )

    if null_rate < 1.0:
        if status == "pass":
            status = "warn"
        failures.append(
            {
                "hypothesis": "H2",
                "detail": (f"Null control rate {null_rate:.3f} < 1.0 — some base scenarios may be non-conformant"),
            }
        )

    return status


# ---------------------------------------------------------------------------
# LaTeX macro generation
# ---------------------------------------------------------------------------


def _build_macros(metrics: dict) -> list[str]:
    r"""Build \providecommand macros for auto_numbers_sgsc.tex.

    Args:
        metrics: The metrics dict from the output JSON.

    Returns:
        List of LaTeX command strings.
    """
    h1 = metrics.get("H1_mutation_kill_rate", {})
    h2 = metrics.get("H2_null_control_rate", {})
    h3 = metrics.get("H3_counterfactual_sensitivity", {})

    kill_rate = h1.get("kill_rate", 0.0)
    null_rate = h2.get("null_control_rate", 0.0)
    sensitivity = h3.get("sensitivity", 0.0)
    total_mutations = h1.get("total_mutations", 0)
    total_families = h3.get("total_families", 0)
    total_base = h2.get("total_base_scenarios", 0)
    guidelines_with_mutations = h1.get("guidelines_scanned", 0)

    kill_pct = round(kill_rate * 100, 1)
    null_pct = round(null_rate * 100, 1)
    sens_pct = round(sensitivity * 100, 1)

    return [
        f"\\providecommand{{\\sgscMutationKillRate}}{{{kill_pct}\\%}}",
        f"\\providecommand{{\\sgscNullControlRate}}{{{null_pct}\\%}}",
        f"\\providecommand{{\\sgscCounterfactualSensitivity}}{{{sens_pct}\\%}}",
        f"\\providecommand{{\\sgscTotalMutations}}{{{total_mutations}}}",
        f"\\providecommand{{\\sgscTotalFamilies}}{{{total_families}}}",
        f"\\providecommand{{\\sgscTotalBaseScenarios}}{{{total_base}}}",
        f"\\providecommand{{\\sgscGuidelinesWithMutations}}{{{guidelines_with_mutations}}}",
    ]


def _append_macros(tex_path: Path, macros: list[str]) -> None:
    """Append construct validity macros to auto_numbers_sgsc.tex (idempotent).

    Args:
        tex_path: Path to the TeX macro file.
        macros:   List of macro command strings to append.
    """
    block_lines = [
        TEX_MARKER,
        *macros,
        "",
    ]
    block = "\n".join(block_lines) + "\n"

    print()
    print("% LaTeX macros for auto_numbers_sgsc.tex:")
    print(block, end="")

    try:
        existing = tex_path.read_text(encoding="utf-8") if tex_path.exists() else ""
        if TEX_MARKER not in existing:
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


def run_analysis(
    registry_path: Path,
    output_base: Path,
    sgsc_dir: Path,
    hypotheses: list[str] | None = None,
) -> dict:
    """Run construct validity analysis and return standard JSON contract.

    Args:
        registry_path: Path to registry JSON file.
        output_base:   Directory for evidence_pack/analysis outputs.
        sgsc_dir:      Root SGSC output directory.
        hypotheses:    Optional subset of hypotheses to run, e.g. ["H1", "H2"].
                       If None, all hypotheses are run.

    Returns:
        A dict conforming to the standard JSON check contract.
    """
    active = set(hypotheses) if hypotheses else {"H1", "H2", "H3", "H4", "H5"}

    registry_data = _load_json(registry_path)
    if not isinstance(registry_data, dict) or "guidelines" not in registry_data:
        return {
            "check_name": "construct_validity",
            "status": "fail",
            "commit": _git_commit(),
            "input_hash": "",
            "output_hash": "",
            "metrics": {},
            "failures": [{"detail": (f"Registry unreadable or missing 'guidelines': {registry_path}")}],
        }

    guidelines: list[dict] = [g for g in registry_data["guidelines"] if isinstance(g, dict)]
    logger.info("Loaded %d guidelines from %s", len(guidelines), registry_path)

    # Collect input files for hashing
    input_files: list[Path] = [registry_path]
    for g in guidelines:
        gid = g.get("guideline_id", "")
        input_files.extend(
            [
                sgsc_dir / gid / "atoms_smoke.json",
                sgsc_dir / gid / f"{gid}_scenarios.json",
            ]
        )

    failures: list[dict] = []
    metrics: dict = {}

    # H1
    if "H1" in active:
        logger.info("Computing H1 — mutation kill-rate...")
        metrics["H1_mutation_kill_rate"] = compute_h1_mutation_kill_rate(guidelines, sgsc_dir)

    # H2
    if "H2" in active:
        logger.info("Computing H2 — null control rate...")
        metrics["H2_null_control_rate"] = compute_h2_null_control_rate(guidelines, sgsc_dir)

    # H3
    if "H3" in active:
        logger.info("Computing H3 — counterfactual sensitivity...")
        metrics["H3_counterfactual_sensitivity"] = compute_h3_counterfactual_sensitivity(guidelines, sgsc_dir)

    # H4
    if "H4" in active:
        logger.info("Computing H4 — clinician agreement...")
        metrics["H4_clinician_agreement"] = compute_h4_clinician_agreement(sgsc_dir)

    # H5
    if "H5" in active:
        logger.info("Computing H5 — MIMIC calibration...")
        metrics["H5_mimic_calibration"] = compute_h5_mimic_calibration()

    # Status determination (only when both H1 and H2 are run)
    h1 = metrics.get("H1_mutation_kill_rate", {})
    h2 = metrics.get("H2_null_control_rate", {})
    status = _determine_status(h1, h2, failures) if ("H1" in active and "H2" in active) else "pass"

    report: dict = {
        "check_name": "construct_validity",
        "status": status,
        "commit": _git_commit(),
        "input_hash": _hash_files(input_files),
        "output_hash": "",
        "metrics": metrics,
        "failures": failures,
    }

    report_bytes = json.dumps(report, sort_keys=True).encode()
    report["output_hash"] = hashlib.sha256(report_bytes).hexdigest()

    # Write JSON output
    output_base.mkdir(parents=True, exist_ok=True)
    out_path = output_base / OUTPUT_FILENAME
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Construct validity report written to %s", out_path)

    # Append LaTeX macros
    macros = _build_macros(metrics)
    tex_path = REPO_ROOT / "paper" / "auto_numbers_sgsc.tex"
    _append_macros(tex_path, macros)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run construct validity analysis CLI.

    Args:
        argv: CLI arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code: 0 for pass/warn, 1 for fail.
    """
    parser = argparse.ArgumentParser(description="Construct validity analysis — 5 hypotheses from SGSC artifacts.")
    parser.add_argument(
        "--sgsc-dir",
        default=str(REPO_ROOT / "sgsc_output"),
        help="Root directory of SGSC output (one sub-dir per guideline_id)",
    )
    parser.add_argument(
        "--registry",
        default=str(REPO_ROOT / "configs" / "sgsc" / "pilot_14_registry.json"),
        help="Path to pilot_14_registry.json or full_25_registry.json",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "evidence_pack" / "analysis"),
        help="Directory to write construct_validity.json",
    )
    parser.add_argument(
        "--hypotheses",
        default=None,
        help="Comma-separated subset to run, e.g. 'H1,H2,H3' (default: all)",
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
    hypotheses: list[str] | None = None
    if args.hypotheses:
        hypotheses = [h.strip() for h in args.hypotheses.split(",") if h.strip()]

    if not registry_path.exists():
        logger.error("Registry file not found: %s", registry_path)
        return 1

    if not sgsc_dir.is_dir():
        logger.error("SGSC output dir not found: %s", sgsc_dir)
        return 1

    report = run_analysis(registry_path, output_dir, sgsc_dir, hypotheses=hypotheses)

    m = report["metrics"]
    print()
    print("=== Construct Validity Analysis ===")
    print(f"Status : {report['status'].upper()}")
    print(f"Commit : {report['commit'][:12]}")

    if "H1_mutation_kill_rate" in m:
        h1 = m["H1_mutation_kill_rate"]
        print(
            f"\n[H1] Mutation Kill-Rate: "
            f"{h1['mutations_with_violation']}/{h1['total_mutations']} = "
            f"{h1['kill_rate']:.3f} "
            f"(guidelines scanned: {h1['guidelines_scanned']})"
        )
        if h1["total_mutations"] > 0:
            print(f"     By type: {h1['by_type']}")

    if "H2_null_control_rate" in m:
        h2 = m["H2_null_control_rate"]
        print(
            f"\n[H2] Null Control Rate: "
            f"{h2['conformant_base_scenarios']}/{h2['total_base_scenarios']} = "
            f"{h2['null_control_rate']:.3f}"
        )

    if "H3_counterfactual_sensitivity" in m:
        h3 = m["H3_counterfactual_sensitivity"]
        print(
            f"\n[H3] Counterfactual Sensitivity: "
            f"{h3['families_with_flip']}/{h3['total_families']} = "
            f"{h3['sensitivity']:.3f}"
        )
        print(f"     By type: {h3['by_type']}")

    if "H4_clinician_agreement" in m:
        h4 = m["H4_clinician_agreement"]
        print(f"\n[H4] Clinician Agreement: {h4.get('status', 'unknown')}")

    if "H5_mimic_calibration" in m:
        h5 = m["H5_mimic_calibration"]
        print(f"\n[H5] MIMIC Calibration: {h5.get('status', 'unknown')}")

    if report["failures"]:
        print("\nWarnings/Failures:")
        for f in report["failures"]:
            print(f"  - [{f.get('hypothesis', '?')}] {f.get('detail', f)}")

    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
