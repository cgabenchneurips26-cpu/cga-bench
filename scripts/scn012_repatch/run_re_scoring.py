"""SCN-012 CDE-rescoring demonstration driver (B-cde-rescoring v1.1).

For each conflict pattern flagged by ``audit_cde_rule_conflicts.py`` (Tier-B
and Tier-C), constructs a minimal episode where the agent skips the
conflict-prone action under a co-satisfied condition, then runs the
ViolationExtractor under both scoring modes:

    Mode 1 (legacy)       — derived_constraints=None
    Mode 2 (cde-coupled)  — derived_constraints from CDE.derive(graph, patient)

Outputs ``results/scn012_repatch/pre_post_diff.json`` with per-pattern deltas
plus aggregate macros consumed by the v1.1 paper appendix.

Per-episode additivity invariant is asserted: ``len(cde_violations) >=
len(legacy_violations)`` (CDE never *removes* violations, only adds).

This driver is the v1.1 paper-evidence pipeline. The scope is the 11 patterns
from the audit (each pattern is one synthesised episode demonstrating the
pre/post delta) — full Phase A 706-episode re-scoring is the v1.2 follow-up
that requires per-episode artifacts to be re-loaded.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml

from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig
from cga_bench.assessor_core.violations import (
    HarmSeverityMapping,
    TimingSeverityThreshold,
    ViolationExtractor,
    ViolationExtractorConfig,
)
from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    RecommendationClass,
    ViolationType,
    VitalSigns,
)

REPO = Path(__file__).resolve().parents[2]
AUDIT_PATH = REPO / "evidence_pack/cde_conflict_audit_v1.json"
OUT_PATH = REPO / "results/scn012_repatch/pre_post_diff.json"
GRAPH_DIR = REPO / "cpg_model/graphs"


def _vitals(sbp: int = 80, map_mmhg: int = 55) -> VitalSigns:
    return VitalSigns(
        heart_rate=120,
        blood_pressure_systolic=sbp,
        blood_pressure_diastolic=max(sbp - 40, 30),
        respiratory_rate=24,
        temperature=37.0,
        oxygen_saturation=92,
        map_mmhg=map_mmhg,
    )


def _patient_dict_for_pattern(pattern: dict[str, Any]) -> dict[str, Any]:
    """Synthesise a patient context that satisfies the FORBIDDEN condition
    of this pattern (and the REQUIRED condition when one exists)."""
    forbidden_cond = " ".join(
        e.get("condition", "")
        for e in pattern.get("forbidden", [])
        if e.get("condition")
    )
    patient: dict[str, Any] = {
        "vitals": {"sbp": 80, "map_mmhg": 55, "temperature": 36.0, "potassium": 5.8},
        "labs": {"potassium": 5.8, "creatinine": 1.2, "ph": 7.32},
        "comorbidities": [
            "recent_surgery",
            "esrd",
            "hemodialysis",
            "active_bleeding",
            "congenital_heart_disease",
            "aortic_dissection_suspected",
        ],
        "allergies": [],
        "history": ["recent_surgery_3_weeks"],
        "presentation": {"time_since_injury_hours": 5},
        "contraindications": ["active_bleeding"],
        "age": 70,
    }
    # Hyperkalemia bias if pattern mentions potassium
    if "potassium" in forbidden_cond:
        patient["labs"]["potassium"] = 6.5
    if "temperature" in forbidden_cond and "<" in forbidden_cond:
        patient["vitals"]["temperature"] = 28.0
    return patient


def _state(t: float, sid: str, vit: VitalSigns) -> PatientState:
    return PatientState(
        state_id=sid,
        time_since_arrival_minutes=t,
        age=70,
        sex="F",
        weight_kg=65,
        vitals=vit,
        chief_complaint="see scenario",
        working_diagnosis="see scenario",
    )


def _episode_skipping(action_to_skip: str, episode_id: str) -> EpisodeLog:
    """Episode where the agent does some neutral action but skips the
    conflict-prone action, mimicking the SCN-012 finding."""
    vit = _vitals()
    actions = [
        Action(type=ActionType.PROCEDURE, action_id="order_imaging_initial", args={}, timestamp_minutes=10),
    ]
    states = [_state(0, f"{episode_id}_s0", vit)]
    for i, a in enumerate(actions, 1):
        states.append(_state(a.timestamp_minutes, f"{episode_id}_s{i}", vit))
    return EpisodeLog(
        episode_id=episode_id,
        scenario_id=episode_id,
        agent_id="cde_rescoring_demo",
        states=states,
        actions=actions,
        observations=[{}],
        total_duration_minutes=60,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=0,
        termination_reason="timeout",
    )


def _violation_extractor_config() -> ViolationExtractorConfig:
    return ViolationExtractorConfig(
        harm_severity_mappings=[
            HarmSeverityMapping(action_pattern="alteplase", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="thrombolytic", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="amiodarone", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="epinephrine", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="potassium", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="anticoagulation", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="ace_or_arb", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="mra", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="ns_bolus", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="crystalloid", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="tranexamic", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="ampicillin", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="", severity=HarmSeverity.MODERATE),
        ],
        timing_severity_thresholds=[
            TimingSeverityThreshold(max_delay_minutes=15, severity=HarmSeverity.MODERATE),
            TimingSeverityThreshold(max_delay_minutes=30, severity=HarmSeverity.MAJOR),
            TimingSeverityThreshold(max_delay_minutes=60, severity=HarmSeverity.SEVERE),
        ],
        default_deviation_severity=HarmSeverity.MINOR,
        default_deviation_preventability=0.5,
    )


def _harm_scorer_config() -> HarmScorerConfig:
    return HarmScorerConfig(
        severity_weights={
            HarmSeverity.MINOR: 0.1,
            HarmSeverity.MODERATE: 0.4,
            HarmSeverity.MAJOR: 0.7,
            HarmSeverity.SEVERE: 0.9,
            HarmSeverity.CATASTROPHIC: 1.0,
        },
        guideline_strength_weights={
            None: 1.0,
            RecommendationClass.CLASS_I: 1.0,
            RecommendationClass.CLASS_IIA: 0.8,
            RecommendationClass.CLASS_IIB: 0.6,
            RecommendationClass.CLASS_III: 0.4,
        },
        violation_type_weights={
            ViolationType.OMISSION: 1.0,
            ViolationType.COMMISSION: 1.5,
            ViolationType.TIMING: 1.0,
            ViolationType.SEQUENCE: 1.0,
            ViolationType.DEVIATION: 0.5,
            # CONFLICT auto-injected by HarmScorerConfig.__post_init__
        },
    )


def _score_one_mode(
    episode: EpisodeLog,
    engine,
    extractor_config: ViolationExtractorConfig,
    scorer_config: HarmScorerConfig,
    derived_constraints,
):
    extractor = ViolationExtractor(engine, extractor_config)
    violations = extractor.extract_violations(
        episode, derived_constraints=derived_constraints
    )
    mandatory_count = max(1, len(engine.global_allowed_actions) // 4)
    scorer = HarmScorer(total_mandatory_count=mandatory_count, config=scorer_config)
    score = scorer.compute_score(violations, episode)
    return violations, score


def re_score_pattern(pattern: dict[str, Any]) -> dict[str, Any] | None:
    """Re-score one conflict pattern under both modes."""
    graph_path = GRAPH_DIR / f"{pattern['graph']}.yaml"
    if not graph_path.exists():
        return None

    graph_dict = load_graph(graph_path)
    patient = _patient_dict_for_pattern(pattern)

    # Build engine + episode (skip the conflict action)
    try:
        engine_legacy = CPGEngineFactory.load_from_dict(copy.deepcopy(graph_dict))
        engine_cde = CPGEngineFactory.load_from_dict(copy.deepcopy(graph_dict))
    except Exception as exc:  # noqa: BLE001
        return {"graph": pattern["graph"], "error": f"engine_load_failed: {exc}"}

    engine_legacy.current_node_id = pattern["node"]
    engine_cde.current_node_id = pattern["node"]

    episode_id = f"{pattern['graph']}__{pattern['node']}__{pattern['action']}"
    episode = _episode_skipping(pattern["action"], episode_id)

    cde = ConstraintDerivationEngine()
    derived = cde.derive(copy.deepcopy(graph_dict), patient, scenario_id=episode_id)

    extractor_cfg = _violation_extractor_config()
    scorer_cfg_legacy = _harm_scorer_config()
    scorer_cfg_cde = _harm_scorer_config()  # separate dataclass instances

    legacy_v, legacy_score = _score_one_mode(
        episode, engine_legacy, extractor_cfg, scorer_cfg_legacy, derived_constraints=None
    )
    cde_v, cde_score = _score_one_mode(
        episode, engine_cde, extractor_cfg, scorer_cfg_cde, derived_constraints=derived
    )

    # Per-episode additivity (CDE never removes violations)
    assert len(cde_v) >= len(legacy_v), (
        f"Additivity violated for {episode_id}: legacy={len(legacy_v)} cde={len(cde_v)}"
    )

    newly_surfaced = []
    legacy_keys = {(v.action_involved or v.expected_action, v.violation_type) for v in legacy_v}
    for v in cde_v:
        key = (v.action_involved or v.expected_action, v.violation_type)
        if key not in legacy_keys:
            newly_surfaced.append(
                {
                    "type": v.violation_type.value,
                    "action": v.action_involved or v.expected_action,
                    "source": v.source,
                    "conflict_provenance": v.conflict_provenance,
                    "description": v.description,
                }
            )

    return {
        "pattern": {
            "graph": pattern["graph"],
            "node": pattern["node"],
            "action": pattern["action"],
            "tier": pattern["tier"],
        },
        "legacy_compliance": legacy_score.compliance_score,
        "cde_compliance": cde_score.compliance_score,
        "delta_compliance": cde_score.compliance_score - legacy_score.compliance_score,
        "legacy_violations": len(legacy_v),
        "cde_violations": len(cde_v),
        "newly_surfaced": newly_surfaced,
        "conflict_count": sum(1 for v in cde_v if v.violation_type == ViolationType.CONFLICT),
    }


def _summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate headline numerics for paper macros."""
    valid = [r for r in records if "error" not in r]
    n = len(valid)
    if n == 0:
        return {"n": 0}

    impacted = [r for r in valid if r["delta_compliance"] != 0.0 or r["newly_surfaced"]]
    total_conflict = sum(r["conflict_count"] for r in valid)
    mean_legacy = sum(r["legacy_compliance"] for r in valid) / n
    mean_cde = sum(r["cde_compliance"] for r in valid) / n

    # Strict-consensus FA proxy: fraction of patterns where legacy says compliance >= 0.8 (passes)
    # but CDE-coupled produces newly surfaced violations -> v1.0 strict FA for these scenarios.
    strict_fa_pre = sum(
        1 for r in valid if r["legacy_compliance"] >= 0.8
    ) / n * 100.0
    strict_fa_post_caught = sum(
        1 for r in valid
        if r["legacy_compliance"] >= 0.8 and r["newly_surfaced"]
    ) / n * 100.0
    strict_fa_post = strict_fa_pre - strict_fa_post_caught

    return {
        "n_patterns": n,
        "n_impacted": len(impacted),
        "total_conflict_violations": total_conflict,
        "mean_compliance_legacy": round(mean_legacy, 4),
        "mean_compliance_cde": round(mean_cde, 4),
        "delta_mean_compliance": round(mean_cde - mean_legacy, 4),
        "strict_fa_pre_pct": round(strict_fa_pre, 2),
        "strict_fa_post_pct": round(strict_fa_post, 2),
        "strict_fa_caught_pct": round(strict_fa_post_caught, 2),
    }


def main() -> int:
    if not AUDIT_PATH.exists():
        print(f"ERROR: missing audit file {AUDIT_PATH}. Run audit_cde_rule_conflicts.py first.", file=sys.stderr)
        return 1

    audit = json.loads(AUDIT_PATH.read_text())
    patterns = audit["conflicts"]
    records: list[dict[str, Any]] = []

    for p in patterns:
        rec = re_score_pattern(p)
        if rec is not None:
            records.append(rec)

    summary = _summarise(records)
    payload = {
        "audit_version": audit.get("audit_version"),
        "n_patterns_in_audit": len(patterns),
        "summary": summary,
        "records": records,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    print(f"Wrote {OUT_PATH}")
    print(f"Patterns scored: {len(records)}")
    print(f"Summary: {json.dumps(summary, indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
