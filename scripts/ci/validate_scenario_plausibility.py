"""Clinical plausibility validator for auto-generated scenarios.

Validates all loaded scenarios against 6 rule categories:
  A. Cohort x CPG match (age/sex vs graph target_population)
  B. Vitals physiological range (age-stratified bounds)
  C. Working diagnosis x CPG relevance
  D. Chief complaint clinical relevance
  E. Provenance completeness (auto-generated only)
  F. FA-to-graph traceability (auto-generated only)

Usage:
    # Validate all scenarios (auto/ directory)
    PYTHONPATH=. python scripts/ci/validate_scenario_plausibility.py

    # Validate specific directory
    PYTHONPATH=. python scripts/ci/validate_scenario_plausibility.py \
        --scenarios-dir configs/scenarios/auto/

    # Output JSON report
    PYTHONPATH=. python scripts/ci/validate_scenario_plausibility.py --json

Exit codes:
    0 - All scenarios pass (0 ERRORs)
    1 - One or more ERRORs found
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("validate_scenario_plausibility")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_SCENARIOS_DIR = BASE_DIR / "configs" / "scenarios" / "auto"
DEFAULT_GRAPHS_DIR = BASE_DIR / "cpg_model" / "graphs"

# -------------------------------------------------------------------------
# Severity levels
# -------------------------------------------------------------------------

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"


# -------------------------------------------------------------------------
# Data classes
# -------------------------------------------------------------------------


@dataclass
class Finding:
    """A single plausibility finding."""

    scenario_id: str
    rule: str
    severity: str
    message: str


@dataclass
class ValidationReport:
    """Aggregated validation report."""

    findings: list[Finding] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_WARNING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_findings": len(self.findings),
            "errors": self.error_count,
            "warnings": self.warning_count,
            "findings": [
                {
                    "scenario_id": f.scenario_id,
                    "rule": f.rule,
                    "severity": f.severity,
                    "message": f.message,
                }
                for f in self.findings
            ],
        }


# -------------------------------------------------------------------------
# Vitals physiological bounds (age-stratified)
# -------------------------------------------------------------------------

_VITALS_BOUNDS: dict[str, dict[str, tuple[float, float]]] = {
    "adult": {
        "heart_rate": (30, 220),
        "blood_pressure_systolic": (40, 300),
        "blood_pressure_diastolic": (20, 200),
        "respiratory_rate": (4, 60),
        "temperature": (32.0, 43.0),
        "oxygen_saturation": (30, 100),
    },
    "pediatric": {
        "heart_rate": (60, 220),
        "blood_pressure_systolic": (50, 180),
        "blood_pressure_diastolic": (20, 120),
        "respiratory_rate": (12, 70),
        "temperature": (32.0, 42.0),
        "oxygen_saturation": (40, 100),
    },
    "neonatal": {
        "heart_rate": (50, 220),
        "blood_pressure_systolic": (25, 100),
        "blood_pressure_diastolic": (10, 70),
        "respiratory_rate": (15, 80),
        "temperature": (32.0, 40.0),
        "oxygen_saturation": (40, 100),
    },
}

# Weight bounds by population (kg). Values outside these are data errors.
_WEIGHT_BOUNDS: dict[str, tuple[float, float]] = {
    "neonatal": (0.5, 6.0),
    "pediatric": (3.0, 80.0),
    "adult": (25.0, 300.0),
}

# Generic chief complaints that signal generator fallback
_GENERIC_COMPLAINTS: frozenset[str] = frozenset(
    {
        "presenting symptoms",
        "general complaint",
        "unknown",
        "",
    }
)

# Chief complaints clinically impossible for neonates
_NEONATAL_IMPOSSIBLE_COMPLAINTS: frozenset[str] = frozenset(
    {
        "chest pain",
        "headache",
        "abdominal pain",
        "dizziness",
        "palpitations",
    }
)


# -------------------------------------------------------------------------
# Graph loading
# -------------------------------------------------------------------------


def load_graph(path: Path) -> dict[str, Any] | None:
    """Load a CPG graph YAML. Returns None on error."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "nodes" in data:
            return data
        return None
    except Exception as e:
        logger.warning("Failed to load graph %s: %s", path.name, e)
        return None


def build_graph_index(graphs_dirs: list[Path]) -> dict[str, dict[str, Any]]:
    """Build graph_id -> graph dict index from one or more directories."""
    index: dict[str, dict[str, Any]] = {}
    for graphs_dir in graphs_dirs:
        if not graphs_dir.is_dir():
            continue
        for path in sorted(graphs_dir.glob("*.yaml")):
            graph = load_graph(path)
            if graph and "graph_id" in graph:
                index[graph["graph_id"]] = graph
    # Also index auto/ subdirectory
    for graphs_dir in graphs_dirs:
        auto_dir = graphs_dir / "auto"
        if auto_dir.is_dir():
            for path in sorted(auto_dir.glob("*.yaml")):
                graph = load_graph(path)
                if graph and "graph_id" in graph:
                    index[graph["graph_id"]] = graph
    return index


def load_scenarios_from_dir(scenarios_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all scenario YAML files from a directory (flat or nested)."""
    scenarios: dict[str, dict[str, Any]] = {}
    patterns = ["*_scenarios.yaml", "**/*_scenarios.yaml"]
    seen_files: set[Path] = set()
    for pattern in patterns:
        for fpath in sorted(scenarios_dir.glob(pattern)):
            if fpath in seen_files:
                continue
            seen_files.add(fpath)
            try:
                data = yaml.safe_load(fpath.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                for sid, sconfig in (data.get("scenarios") or {}).items():
                    scenarios[sid] = sconfig
            except Exception as e:
                logger.warning("Failed to load %s: %s", fpath.name, e)
    return scenarios


# -------------------------------------------------------------------------
# Rule implementations
# -------------------------------------------------------------------------


def check_cohort_cpg_match(
    scenario_id: str,
    scenario: dict[str, Any],
    graph: dict[str, Any] | None,
) -> list[Finding]:
    """Rule A: Verify patient demographics match graph target_population."""
    if graph is None:
        return [
            Finding(
                scenario_id=scenario_id,
                rule="A_cohort_cpg",
                severity=SEVERITY_WARNING,
                message=f"Graph '{scenario.get('guideline_graph', '?')}' not found in index.",
            )
        ]

    pop = (graph.get("metadata") or {}).get("target_population") or {}
    if not pop:
        return []  # No population metadata — skip

    findings: list[Finding] = []
    patient = scenario.get("patient") or {}
    patient_age = patient.get("age")
    patient_sex = patient.get("sex", "").upper()

    # Age check
    min_age = pop.get("min_age")
    max_age = pop.get("max_age")
    if patient_age is not None:
        if min_age is not None and patient_age < min_age:
            findings.append(
                Finding(
                    scenario_id=scenario_id,
                    rule="A_cohort_cpg",
                    severity=SEVERITY_ERROR,
                    message=(
                        f"Patient age {patient_age} below graph min_age {min_age} "
                        f"(population: {pop.get('age_group', '?')})."
                    ),
                )
            )
        if max_age is not None and patient_age > max_age:
            findings.append(
                Finding(
                    scenario_id=scenario_id,
                    rule="A_cohort_cpg",
                    severity=SEVERITY_ERROR,
                    message=(
                        f"Patient age {patient_age} above graph max_age {max_age} "
                        f"(population: {pop.get('age_group', '?')})."
                    ),
                )
            )
    elif min_age is not None or max_age is not None:
        # Age-constrained graph but patient age is missing
        findings.append(
            Finding(
                scenario_id=scenario_id,
                rule="A_cohort_cpg",
                severity=SEVERITY_WARNING,
                message=(f"Patient age missing on age-constrained graph (min={min_age}, max={max_age})."),
            )
        )

    # Sex check
    required_sex = pop.get("sex", "any")
    if required_sex and required_sex != "any":
        if not patient_sex:
            findings.append(
                Finding(
                    scenario_id=scenario_id,
                    rule="A_cohort_cpg",
                    severity=SEVERITY_WARNING,
                    message=f"Patient sex missing but graph requires '{required_sex}'.",
                )
            )
        else:
            expected_char = "F" if required_sex == "female_only" else "M"
            if patient_sex != expected_char:
                findings.append(
                    Finding(
                        scenario_id=scenario_id,
                        rule="A_cohort_cpg",
                        severity=SEVERITY_ERROR,
                        message=(f"Patient sex '{patient_sex}' incompatible with graph constraint '{required_sex}'."),
                    )
                )

    return findings


def check_vitals_range(
    scenario_id: str,
    scenario: dict[str, Any],
    graph: dict[str, Any] | None,
) -> list[Finding]:
    """Rule B: Verify vitals fall within physiological bounds."""
    patient = scenario.get("patient") or {}
    vitals = patient.get("vitals") or {}
    if not vitals:
        return []

    # Determine age group for bounds
    age_group = "adult"
    if graph:
        pop = (graph.get("metadata") or {}).get("target_population") or {}
        age_group = pop.get("age_group", "adult")

    bounds = _VITALS_BOUNDS.get(age_group, _VITALS_BOUNDS["adult"])

    # Normalize short keys for checking
    _ALIASES = {
        "hr": "heart_rate",
        "sbp": "blood_pressure_systolic",
        "dbp": "blood_pressure_diastolic",
        "rr": "respiratory_rate",
        "spo2": "oxygen_saturation",
        "temp": "temperature",
    }

    findings: list[Finding] = []
    for raw_key, value in vitals.items():
        key = _ALIASES.get(raw_key, raw_key)
        if key not in bounds:
            continue
        if not isinstance(value, (int, float)):
            continue
        lo, hi = bounds[key]
        if value < lo or value > hi:
            # Escalate to ERROR if value is catastrophically far from range
            # (more than 2x beyond the nearest bound)
            dist_lo = max(0, lo - value)
            dist_hi = max(0, value - hi)
            range_span = hi - lo
            catastrophic = range_span > 0 and max(dist_lo, dist_hi) > range_span
            severity = SEVERITY_ERROR if catastrophic else SEVERITY_WARNING
            findings.append(
                Finding(
                    scenario_id=scenario_id,
                    rule="B_vitals_range",
                    severity=severity,
                    message=(f"Vitals '{key}' = {value} outside {age_group} physiological range [{lo}, {hi}]."),
                )
            )

    # DBP >= SBP check (physiologically impossible)
    sbp = vitals.get("blood_pressure_systolic") or vitals.get("sbp")
    dbp = vitals.get("blood_pressure_diastolic") or vitals.get("dbp")
    if (
        sbp is not None
        and dbp is not None
        and isinstance(sbp, (int, float))
        and isinstance(dbp, (int, float))
        and dbp >= sbp
    ):
        findings.append(
            Finding(
                scenario_id=scenario_id,
                rule="B_vitals_range",
                severity=SEVERITY_ERROR,
                message=f"DBP ({dbp}) >= SBP ({sbp}) is physiologically impossible.",
            )
        )

    # MAP consistency check
    given_map = vitals.get("map_mmhg")
    if (
        sbp is not None
        and dbp is not None
        and given_map is not None
        and isinstance(sbp, (int, float))
        and isinstance(dbp, (int, float))
        and isinstance(given_map, (int, float))
        and sbp > dbp  # only check if SBP/DBP are valid
    ):
        expected_map = dbp + (sbp - dbp) / 3.0
        if abs(given_map - expected_map) > 5:
            findings.append(
                Finding(
                    scenario_id=scenario_id,
                    rule="B_vitals_range",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"MAP inconsistency: given {given_map}, expected ~{expected_map:.1f} from SBP={sbp}/DBP={dbp}."
                    ),
                )
            )

    # Weight plausibility check
    weight = patient.get("weight_kg")
    if weight is not None and isinstance(weight, (int, float)):
        weight_bounds = _WEIGHT_BOUNDS.get(age_group, _WEIGHT_BOUNDS["adult"])
        wlo, whi = weight_bounds
        if weight < wlo or weight > whi:
            findings.append(
                Finding(
                    scenario_id=scenario_id,
                    rule="B_vitals_range",
                    severity=SEVERITY_ERROR,
                    message=(f"Weight {weight} kg outside {age_group} plausible range [{wlo}, {whi}]."),
                )
            )

    return findings


def check_diagnosis_relevance(
    scenario_id: str,
    scenario: dict[str, Any],
    graph: dict[str, Any] | None,
) -> list[Finding]:
    """Rule C: Verify working_diagnosis matches the CPG domain."""
    findings: list[Finding] = []
    working_dx = (scenario.get("patient") or {}).get("working_diagnosis", "")
    if not working_dx:
        working_dx = scenario.get("working_diagnosis", "")

    if not working_dx or working_dx.lower() == "general":
        findings.append(
            Finding(
                scenario_id=scenario_id,
                rule="C_diagnosis",
                severity=SEVERITY_WARNING,
                message="Working diagnosis is generic or missing.",
            )
        )
        return findings

    # Cross-domain mismatch detection
    if graph:
        # Normalize underscores to spaces so "pulmonary_embolism" matches
        # the fragment "pulmonary embolism" and vice versa.
        gid = graph.get("graph_id", "").lower().replace("_", " ")
        dx_lower = working_dx.lower().replace("_", " ")

        # Catastrophic mismatches: diagnosis from domain X on graph for domain Y.
        # (domain_token, gid_fragment, dx_fragment)
        # (domain_token, gid_fragments, dx_fragment)
        # gid_fragments: any of these in gid means the graph belongs to this domain
        _MISMATCH_RULES: list[tuple[str, list[str], str]] = [
            ("pulmonary embolism", ["pe", "pulmonary"], "pulmonary embolism"),
            ("sepsis", ["sepsis"], "sepsis"),
            ("stroke", ["stroke"], "stroke"),
            ("dka", ["dka"], "diabetic ketoacidosis"),
            ("anaphylaxis", ["anaphylaxis"], "anaphylaxis"),
            ("meningitis", ["meningitis"], "meningitis"),
            ("heart failure", ["heart failure"], "heart failure"),
            ("acute coronary", ["coronary"], "acute coronary syndrome"),
            ("chest pain", ["chest pain"], "chest pain"),
            ("aki", ["aki"], "acute kidney injury"),
            ("copd", ["copd"], "copd"),
            ("gi bleed", ["bleed", "varic", "gi", "baveno"], "gi bleed"),
            ("burn", ["burn"], "burn"),
        ]
        for domain_token, gid_fragments, dx_fragment in _MISMATCH_RULES:
            if dx_fragment in dx_lower and not any(f in gid for f in gid_fragments):
                # Only flag if the graph is clearly about a different domain
                if domain_token not in gid:
                    findings.append(
                        Finding(
                            scenario_id=scenario_id,
                            rule="C_diagnosis",
                            severity=SEVERITY_ERROR,
                            message=(
                                f"Cross-domain mismatch: working_diagnosis "
                                f"'{working_dx}' vs graph '{graph.get('graph_id', '?')}'."
                            ),
                        )
                    )

    return findings


def check_chief_complaint(
    scenario_id: str,
    scenario: dict[str, Any],
    graph: dict[str, Any] | None,
) -> list[Finding]:
    """Rule D: Verify chief complaint is clinically appropriate."""
    findings: list[Finding] = []
    patient = scenario.get("patient") or {}
    complaint = patient.get("chief_complaint", "")
    if not complaint:
        complaint = scenario.get("chief_complaint", "")

    complaint_lower = complaint.lower().strip()

    if complaint_lower in _GENERIC_COMPLAINTS:
        findings.append(
            Finding(
                scenario_id=scenario_id,
                rule="D_chief_complaint",
                severity=SEVERITY_WARNING,
                message=f"Chief complaint is generic: '{complaint}'.",
            )
        )

    # Neonatal age-inappropriate complaints
    if graph:
        pop = (graph.get("metadata") or {}).get("target_population") or {}
        if pop.get("age_group") == "neonatal":
            if complaint_lower in _NEONATAL_IMPOSSIBLE_COMPLAINTS:
                findings.append(
                    Finding(
                        scenario_id=scenario_id,
                        rule="D_chief_complaint",
                        severity=SEVERITY_ERROR,
                        message=(f"Age-inappropriate complaint for neonatal: '{complaint}'."),
                    )
                )

    return findings


# -------------------------------------------------------------------------
# Rule E: Provenance completeness (auto-generated scenarios only)
# -------------------------------------------------------------------------

_VALID_GENERATION_PHASES = frozenset({"branch", "conditional_rule", "universal_trap", "baseline"})


def check_provenance(
    scenario_id: str,
    scenario: dict[str, Any],
    graph: dict[str, Any] | None,
) -> list[Finding]:
    """Rule E: Verify auto-generated scenarios have valid provenance metadata."""
    meta = scenario.get("_generation_metadata")
    if meta is None:
        return []  # Manual scenario — rule not applicable

    findings: list[Finding] = []

    # E1: Must have graph_id
    if not meta.get("graph_id"):
        findings.append(
            Finding(
                scenario_id=scenario_id,
                rule="E_provenance",
                severity=SEVERITY_ERROR,
                message="Missing graph_id in _generation_metadata.",
            )
        )

    # E2: Must have valid generation_phase
    phase = meta.get("generation_phase")
    if phase not in _VALID_GENERATION_PHASES:
        findings.append(
            Finding(
                scenario_id=scenario_id,
                rule="E_provenance",
                severity=SEVERITY_ERROR,
                message=f"Invalid generation_phase: '{phase}'. Expected one of {sorted(_VALID_GENERATION_PHASES)}.",
            )
        )

    # E3: Must have source_node_ids (at least for non-baseline)
    if not meta.get("source_node_ids") and phase != "baseline":
        findings.append(
            Finding(
                scenario_id=scenario_id,
                rule="E_provenance",
                severity=SEVERITY_WARNING,
                message="Empty source_node_ids in _generation_metadata.",
            )
        )

    # E4: forbidden_action_provenance must cover all FA
    fa_list = scenario.get("forbidden_actions", [])
    fa_prov = meta.get("forbidden_action_provenance") or {}
    for fa in fa_list:
        if fa not in fa_prov:
            findings.append(
                Finding(
                    scenario_id=scenario_id,
                    rule="E_provenance",
                    severity=SEVERITY_ERROR,
                    message=f"Forbidden action '{fa}' has no provenance entry.",
                )
            )

    return findings


# -------------------------------------------------------------------------
# Rule F: FA-to-graph traceability (auto-generated scenarios only)
# -------------------------------------------------------------------------


def check_fa_traceability(
    scenario_id: str,
    scenario: dict[str, Any],
    graph: dict[str, Any] | None,
) -> list[Finding]:
    """Rule F: Verify every forbidden_action traces to a real graph node or trap."""
    meta = scenario.get("_generation_metadata")
    if meta is None:
        return []  # Manual scenario

    if graph is None:
        return []

    findings: list[Finding] = []
    fa_prov = meta.get("forbidden_action_provenance") or {}
    graph_nodes = graph.get("nodes") or {}

    for fa, source in fa_prov.items():
        if source.startswith("node:"):
            node_id = source.split(":", 1)[1]
            node = graph_nodes.get(node_id)
            if node is None:
                findings.append(
                    Finding(
                        scenario_id=scenario_id,
                        rule="F_fa_traceability",
                        severity=SEVERITY_ERROR,
                        message=f"FA '{fa}' claims source node '{node_id}' which doesn't exist in graph.",
                    )
                )
            elif fa not in (node.get("forbidden_actions") or []):
                findings.append(
                    Finding(
                        scenario_id=scenario_id,
                        rule="F_fa_traceability",
                        severity=SEVERITY_ERROR,
                        message=f"FA '{fa}' not found in node '{node_id}' forbidden_actions list.",
                    )
                )
        # "rule:XXX" and "trap:XXX" sources are validated by membership
        # in conditional_rules / _UNIVERSAL_TRAPS respectively.
        # We only validate node-level traceability here.

    return findings


# -------------------------------------------------------------------------
# Main validation entry point
# -------------------------------------------------------------------------


def validate_scenarios(
    scenarios: dict[str, dict[str, Any]],
    graph_index: dict[str, dict[str, Any]],
) -> ValidationReport:
    """Run all plausibility rules on a set of scenarios."""
    report = ValidationReport()

    for scenario_id, scenario in sorted(scenarios.items()):
        graph_key = scenario.get("guideline_graph", "")
        graph = graph_index.get(graph_key)

        report.findings.extend(check_cohort_cpg_match(scenario_id, scenario, graph))
        report.findings.extend(check_vitals_range(scenario_id, scenario, graph))
        report.findings.extend(check_diagnosis_relevance(scenario_id, scenario, graph))
        report.findings.extend(check_chief_complaint(scenario_id, scenario, graph))
        report.findings.extend(check_provenance(scenario_id, scenario, graph))
        report.findings.extend(check_fa_traceability(scenario_id, scenario, graph))

    return report


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Clinical plausibility validator for auto-generated scenarios.")
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=DEFAULT_SCENARIOS_DIR,
        help="Directory containing scenario YAML files.",
    )
    parser.add_argument(
        "--graphs-dir",
        type=Path,
        default=DEFAULT_GRAPHS_DIR,
        help="Directory containing CPG graph YAML files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON report instead of text.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write JSON report to file.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Load graphs from main + auto subdirectory
    graph_index = build_graph_index([args.graphs_dir])
    logger.info("Loaded %d graphs.", len(graph_index))

    # Load scenarios
    scenarios = load_scenarios_from_dir(args.scenarios_dir)
    logger.info("Loaded %d scenarios from %s.", len(scenarios), args.scenarios_dir)

    if not scenarios:
        logger.warning("No scenarios found. Nothing to validate.")
        return 0

    report = validate_scenarios(scenarios, graph_index)

    if args.json or args.json_out:
        report_dict = report.to_dict()
        if args.json:
            print(json.dumps(report_dict, indent=2))
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")
            logger.info("JSON report written to %s", args.json_out)
    else:
        # Text output
        for f in report.findings:
            tag = "ERROR" if f.severity == SEVERITY_ERROR else "WARN "
            print(f"[{tag}] {f.scenario_id} ({f.rule}): {f.message}")

        print(
            f"\n--- Summary: {report.error_count} ERROR(s), "
            f"{report.warning_count} WARNING(s) across {len(scenarios)} scenarios ---"
        )

    return 1 if report.error_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
