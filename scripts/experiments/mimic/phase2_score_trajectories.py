#!/usr/bin/env python3
"""Phase 2 (load-bearing) — Score real MIMIC-IV trajectories with all six
evaluators (TOM, ASC, CwT, PAF, ACov, TCC) and persist a verdict matrix
matching the schema of ``evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json``.

Pipeline (per cohort episode):

    1. Build trace tau = [(action_id, t, args)] from MIMIC events.
       Sources: prescriptions, labevents, procedureevents. Mapping is
       declared in ``data/mimic_iv_local/action_mapping.yaml``
       (Phase 0 output).

    2. Build the initial PatientState at t=0 (sepsis-3 onset).

    3. Run ``assessor_core.evaluation_loop.run_cpg_evaluation_loop`` with
       the SSC graph (``cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml``).
       This produces the violation_events / compliance_score that the
       verdict functions consume.

    4. For each evaluator m in EVALUATOR_REGISTRY, call its verdict
       function and record the bool.

Outputs:
  * evidence_pack/verdicts/verdict_matrix_mimic_iv.parquet
  * evidence_pack/mimic_iv/phase2/phase2_score_trajectories.summary.json

Sanity gates (HALT on failure):
  * Deterministic-replay invariance: re-run the scoring loop on a 100-
    episode sample with the same seed; verdict flips must be 0.
    (Replaces the contract's "ILP vs tiered solver" gate per
    KNOWN_ISSUES.md §6-2.)
  * Normalizer current vs strict: per-evaluator pass-rate gap > 8 pp on
    --normalizer-mode={current,strict} runs is a HALT.
  * Pass-rate plausibility: ASC in [0.40, 0.80]; CwT < ASC; CwT in
    [0.25, 0.75]; TCC pass-rate must NOT exceed CwT pass-rate.

The script imports ``assessor_core`` at runtime — that package requires
Python >= 3.11 (PEP 604 unions, match statements, etc.). On the dev box
(Python 3.8) only the trace-builder code paths run; the scoring loop is
exercised only on the owner-side production host.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
from typing import Any

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.experiments.mimic._common import (  # noqa: E402
    EVIDENCE_ROOT,
    MIMIC_LOCAL_ROOT,
    GateFailure,
    PhaseSummary,
    build_normalizer,
    git_sha,
    halt_and_log,
    mimic_version,
    read_mimic_csv,
    resolve_mimic_root,
)

COHORT_PARQUET = MIMIC_LOCAL_ROOT / "cohort_sepsis3.parquet"
ACTION_MAPPING = MIMIC_LOCAL_ROOT / "action_mapping.yaml"
SSC_GRAPH = REPO_ROOT / "cpg_model" / "graphs" / "ssc_sepsis_hour1_bundle.yaml"
OUTPUT_PARQUET = REPO_ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_mimic_iv.parquet"
PHASE2_DIR = EVIDENCE_ROOT / "phase2"

# Sanity-gate thresholds (Phase 2)
NORMALIZER_GAP_LIMIT_PP = 8.0
DETERMINISTIC_SAMPLE_N = 100
ASC_LOWER, ASC_UPPER = 0.40, 0.80
CWT_LOWER, CWT_UPPER = 0.25, 0.75


# ----------------------------------------------------------------------------
# Trace builder: MIMIC events -> Action / PatientState
# ----------------------------------------------------------------------------


def _load_action_mapping() -> dict[str, dict]:
    """Index the YAML by canonical_action so the trace builder can
    look up patterns + itemids in O(1).
    """
    if not ACTION_MAPPING.is_file():
        raise FileNotFoundError(f"missing {ACTION_MAPPING}; run phase0_action_mapping.py first")
    spec = yaml.safe_load(ACTION_MAPPING.read_text())
    return {a["canonical_action"]: a for a in spec["canonical_actions"]}


def _build_episode_trace(
    *,
    hadm_id: int,
    onset_time: pd.Timestamp,
    horizon_hours: float,
    rx: pd.DataFrame,
    labs: pd.DataFrame,
    procs: pd.DataFrame | None,
    action_mapping: dict[str, dict],
) -> list[dict[str, Any]]:
    """Return the MIMIC actions inside [onset, onset + horizon_hours).

    Output is a list of action dicts of the shape that
    ``assessor_core/spec/verdict_definitions.py`` consumes:
        {"action_id": <canonical>, "timestamp_minutes": float, "args": {...}}

    The mapping uses ``action_mapping.yaml``: drug-name regex for
    prescriptions, itemid for labevents/procedureevents.
    """
    horizon_end = onset_time + pd.Timedelta(hours=horizon_hours)
    actions: list[dict[str, Any]] = []

    # Prescriptions -> antibiotics, crystalloids, vasopressors. The caller
    # passes ``rx`` as a hadm_id-indexed DataFrame so that the per-episode
    # filter is O(matches) rather than O(N_total_rows).
    if rx is not None and len(rx):
        try:
            rx_ep = rx.loc[[hadm_id]] if hadm_id in rx.index else None
        except KeyError:
            rx_ep = None
        if rx_ep is not None and len(rx_ep):
            rx_ep = rx_ep[(rx_ep["starttime"] >= onset_time) & (rx_ep["starttime"] < horizon_end)]
        for _, row in rx_ep.iterrows() if rx_ep is not None else iter([]):
            for canonical, spec in action_mapping.items():
                source = spec["mimic_sources"][0]
                if source.get("table") != "prescriptions":
                    continue
                patterns = source.get("patterns", [])
                drug = str(row.get("drug", "")).lower()
                if not any(p in drug for p in patterns):
                    continue
                # Optional route filter (case-insensitive)
                route_filter = source.get("route_filter")
                if route_filter:
                    route = str(row.get("route", "")).upper()
                    if not any(r.upper() == route for r in route_filter):
                        continue
                actions.append(
                    {
                        "action_id": canonical,
                        "timestamp_minutes": float((row["starttime"] - onset_time).total_seconds() / 60.0),
                        "args": {"drug": row.get("drug")},
                    }
                )
                break

    # Labevents -> measure_lactate, obtain_blood_culture (hadm-indexed)
    if labs is not None and len(labs):
        try:
            labs_ep = labs.loc[[hadm_id]] if hadm_id in labs.index else None
        except KeyError:
            labs_ep = None
        if labs_ep is not None and len(labs_ep):
            labs_ep = labs_ep[(labs_ep["charttime"] >= onset_time) & (labs_ep["charttime"] < horizon_end)]
        for _, row in labs_ep.iterrows() if labs_ep is not None else iter([]):
            itemid = row.get("itemid")
            for canonical, spec in action_mapping.items():
                source = spec["mimic_sources"][0]
                if source.get("table") != "labevents":
                    continue
                if itemid in source.get("values", []):
                    actions.append(
                        {
                            "action_id": canonical,
                            "timestamp_minutes": float((row["charttime"] - onset_time).total_seconds() / 60.0),
                            "args": {"itemid": int(itemid) if pd.notna(itemid) else None},
                        }
                    )
                    break

    # ProcedureEvents (icu/) — currently unused by the SSC bundle but
    # kept here for symmetry; non-empty patterns can be added by the owner.
    if procs is not None and len(procs):
        pass  # placeholder

    actions.sort(key=lambda a: a["timestamp_minutes"])
    return actions


def _load_chartevents_for_phase2(root: Path, target_itemids: set[int], chunksize: int = 1_000_000) -> pd.DataFrame:
    """Stream chartevents.csv.gz, filter to target itemids. EOF-tolerant
    (re-uses the same pattern as phase0_action_mapping/phase1).
    """
    base = root / "icu" / "chartevents"
    src = base.with_suffix(".csv.gz")
    if not src.is_file():
        src = base.with_suffix(".csv")
        if not src.is_file():
            return pd.DataFrame()
    rows: list[pd.DataFrame] = []
    try:
        reader = pd.read_csv(
            src,
            compression="gzip" if src.suffix == ".gz" else None,
            usecols=["hadm_id", "itemid", "charttime", "valuenum"],
            parse_dates=["charttime"],
            dtype={"itemid": "Int32", "valuenum": "float64"},
            chunksize=chunksize,
        )
        for chunk in reader:
            chunk = chunk[chunk["itemid"].isin(target_itemids)]
            if len(chunk):
                rows.append(chunk)
    except EOFError:
        pass
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


VITAL_ITEMIDS = {
    "heart_rate": [220045],
    "blood_pressure_systolic": [220179, 220050, 225309],
    "blood_pressure_diastolic": [220180, 220051, 225310],
    "map_mmhg": [220181, 220052, 225312],
    "respiratory_rate": [220210, 224690],
    "temperature_c": [223762],
    "temperature_f": [223761],
    "oxygen_saturation": [220277, 224697],
}

LAB_ITEMIDS = {
    "lactate": {"itemid": 50813, "code": "lactate"},
    "wbc": {"itemid": 51301, "code": "wbc"},
    "creatinine": {"itemid": 50912, "code": "creatinine"},
    "bun": {"itemid": 51006, "code": "bun"},
    "sodium": {"itemid": 50983, "code": "sodium"},
    "potassium": {"itemid": 50971, "code": "potassium"},
    "glucose": {"itemid": 50931, "code": "glucose"},
    "platelets": {"itemid": 51265, "code": "platelets"},
}


def _build_patient_state(
    cohort_row: pd.Series,
    *,
    root: Path,
    onset_time: pd.Timestamp,
    vitals_at_onset: dict[str, float] | None = None,
    labs_at_onset: list[Any] | None = None,
) -> Any:
    """Build a per-episode PatientState with vitals + labs populated from
    chartevents / labevents nearest to ``onset_time``. The vitals and
    labs are pre-resolved by the caller (Phase 2's main loop) to avoid
    re-scanning the union frames for every episode.
    """
    from cga_bench.cpg_model.schemas.base import (  # type: ignore
        LabResult,
        PatientState,
        VitalSigns,
    )

    v = vitals_at_onset or {}
    vitals = VitalSigns(
        heart_rate=v.get("heart_rate"),
        blood_pressure_systolic=v.get("blood_pressure_systolic"),
        blood_pressure_diastolic=v.get("blood_pressure_diastolic"),
        map_mmhg=v.get("map_mmhg"),
        respiratory_rate=v.get("respiratory_rate"),
        temperature=v.get("temperature_c")
        if v.get("temperature_c") is not None
        else ((v["temperature_f"] - 32.0) * 5.0 / 9.0 if v.get("temperature_f") is not None else None),
        oxygen_saturation=v.get("oxygen_saturation"),
    )

    lab_objs: list[LabResult] = []
    if labs_at_onset:
        for lab in labs_at_onset:
            try:
                lab_objs.append(LabResult(**lab))
            except Exception:
                continue

    return PatientState(
        state_id=f"sepsis3_{int(cohort_row['hadm_id'])}_t0",
        time_since_arrival_minutes=0.0,
        age=float(cohort_row["anchor_age"]),
        sex=str(cohort_row["gender"]),
        weight_kg=70.0,  # cohort-row-level placeholder; chart-derived weight optional
        vitals=vitals,
        lab_results=lab_objs,
        medications_given=[],
        procedures_done=[],
        pending_orders=[],
        contraindications=[],
        allergies=[],
        comorbidities=[],
        chief_complaint="sepsis",
        working_diagnosis="sepsis",
        disposition_status="icu",
    )


def _resolve_vitals_at_onset(
    chartevents_by_hadm: dict[int, pd.DataFrame],
    hadm_id: int,
    onset_time: pd.Timestamp,
    horizon_hours: float = 6.0,
) -> dict[str, float]:
    """Look up the FIRST value (in [onset, onset+horizon_hours]) per vital
    canonical-name from a hadm-indexed chartevents subset.
    """
    df = chartevents_by_hadm.get(hadm_id)
    if df is None or len(df) == 0:
        return {}
    horizon_end = onset_time + pd.Timedelta(hours=horizon_hours)
    df = df[(df["charttime"] >= onset_time) & (df["charttime"] < horizon_end)]
    if len(df) == 0:
        return {}
    out: dict[str, float] = {}
    for canonical, itemids in VITAL_ITEMIDS.items():
        match = df[df["itemid"].isin(itemids)].dropna(subset=["valuenum"])
        if len(match):
            out[canonical] = float(match.sort_values("charttime").iloc[0]["valuenum"])
    return out


def _resolve_labs_at_onset(
    labevents_by_hadm: dict[int, pd.DataFrame],
    hadm_id: int,
    onset_time: pd.Timestamp,
    horizon_hours: float = 24.0,
) -> list[dict[str, Any]]:
    """Look up the FIRST value (in [onset-2h, onset+horizon_hours]) per
    lab canonical-name and return LabResult-shaped dicts.
    """
    df = labevents_by_hadm.get(hadm_id)
    if df is None or len(df) == 0:
        return []
    window_lo = onset_time - pd.Timedelta(hours=2)
    window_hi = onset_time + pd.Timedelta(hours=horizon_hours)
    df = df[(df["charttime"] >= window_lo) & (df["charttime"] < window_hi)]
    if len(df) == 0:
        return []
    out: list[dict[str, Any]] = []
    for name, spec in LAB_ITEMIDS.items():
        match = df[df["itemid"] == spec["itemid"]].dropna(subset=["valuenum"])
        if len(match):
            row = match.sort_values("charttime").iloc[0]
            t_min = float((row["charttime"] - onset_time).total_seconds() / 60.0)
            out.append(
                {
                    "test_code": spec["code"],
                    "test_name": name,
                    "value": float(row["valuenum"]),
                    "unit": "",
                    "timestamp_minutes": t_min,
                    "is_abnormal": False,
                    "critical": False,
                }
            )
    return out


def _score_one_episode(
    *,
    cohort_row: pd.Series,
    actions: list[dict],
    patient_state: Any,
    cpg_engine: Any,
    normalizer: Any,
    extractor: Any,
    scorer_config: Any,
) -> dict[str, Any]:
    """Build an EpisodeLog, extract violations, score with HarmScorer, and
    return an episode dict matching the schema consumed by
    ``EVALUATOR_REGISTRY`` verdict functions.

    This mirrors the canonical pipeline in ``run_benchmark.py:560-585``.
    """
    from cga_bench.assessor_core.harm_scorer import HarmScorer  # type: ignore
    from cga_bench.cpg_model.schemas.base import Action, ActionType, EpisodeLog  # type: ignore

    # Canonical action -> correct ActionType (Bug fix: was hardcoded GIVE_MEDICATION)
    _ACTION_TYPE_MAP: dict[str, ActionType] = {
        "obtain_blood_culture": ActionType.ORDER_LAB,
        "measure_lactate": ActionType.ORDER_LAB,
    }

    action_objs = [
        Action(
            type=_ACTION_TYPE_MAP.get(a["action_id"], ActionType.GIVE_MEDICATION),
            action_id=normalizer.normalize(a["action_id"]) if normalizer else a["action_id"],
            args=a.get("args", {}),
            timestamp_minutes=a["timestamp_minutes"],
            justification=None,
        )
        for a in actions
    ]

    episode_log = EpisodeLog(
        episode_id=f"mimic_iv_{int(cohort_row['hadm_id'])}",
        scenario_id=f"mimic_iv_{int(cohort_row['hadm_id'])}",
        agent_id="mimic_iv_clinicians",
        states=[patient_state],
        actions=action_objs,
        observations=[],
        total_duration_minutes=float(action_objs[-1].timestamp_minutes) if action_objs else 0.0,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=0,
        termination_reason="mimic_iv_horizon",
    )

    violations = extractor.extract_violations(episode_log)

    cpg_out = cpg_engine.evaluate(patient_state)
    expected_actions = sorted(set(cpg_out.mandatory_actions or []))

    scorer = HarmScorer(
        total_mandatory_count=max(len(expected_actions), 1),
        config=scorer_config,
    )
    score = scorer.compute_score(violations, episode_log)

    return {
        "scenario_id": f"mimic_iv_{int(cohort_row['hadm_id'])}",
        "model": "mimic_iv_clinicians",
        "actions": [{"action_id": a.action_id, "timestamp_minutes": a.timestamp_minutes} for a in action_objs],
        "expected_actions": expected_actions,
        "violation_events": [
            {
                "violation_type": v.violation_type.value
                if hasattr(v.violation_type, "value")
                else str(v.violation_type),
                "action_id": getattr(v, "action_id", None),
            }
            for v in violations
        ],
        "compliance_score": float(score.compliance_score),
        "peak_risk": float(getattr(score, "peak_risk", 0.0)),
        "aggregate_risk": float(getattr(score, "aggregate_risk", 0.0)),
        "total_violations": int(getattr(score, "total_violations", len(violations))),
    }


# ----------------------------------------------------------------------------
# Verdict aggregation
# ----------------------------------------------------------------------------


def _run_verdicts(ep_dict: dict) -> dict[str, bool]:
    from cga_bench.assessor_core.spec.verdict_definitions import EVALUATOR_REGISTRY  # type: ignore

    return {name: bool(spec["function"](ep_dict)) for name, spec in EVALUATOR_REGISTRY.items()}


def _build_extractor_and_scorer_config(cpg_engine: Any) -> tuple[Any, Any]:
    """Build ViolationExtractor + HarmScorerConfig by importing the canonical
    defaults from ``run_benchmark.py``, ensuring MIMIC-IV verdicts use the
    exact same scoring weights as the synthetic-cohort benchmark.

    Previously this function hardcoded its own config, which diverged from
    ``run_benchmark.get_default_violation_extractor_config()`` (missing ecg,
    troponin, cath_lab, nitro, aspirin severity mappings). Fixed 2026-05-06.
    """
    from run_benchmark import (  # type: ignore
        get_default_harm_scorer_config,
        get_default_violation_extractor_config,
    )

    from cga_bench.assessor_core.violations import ViolationExtractor  # type: ignore

    ve_config = get_default_violation_extractor_config()
    extractor = ViolationExtractor(cpg_engine, ve_config)
    scorer_config = get_default_harm_scorer_config()
    return extractor, scorer_config


def _build_cpg_engine(root: Path) -> Any:
    """Construct the CPGEngine on the SSC graph. Owner: extend
    AllergyDrugMapping / ComorbidityConstraint lists if the cohort has
    important comorbidities the bundle cares about.
    """
    from cga_bench.cpg_engine.engine import (  # type: ignore
        CPGEngineConfig,
        CPGEngineFactory,
    )

    config = CPGEngineConfig(
        allergy_drug_mappings=[],
        comorbidity_constraints=[],
        strict_mode=False,
    )
    return CPGEngineFactory.load_from_file(str(SSC_GRAPH), config)


# ----------------------------------------------------------------------------
# Sanity gates
# ----------------------------------------------------------------------------


def _check_pass_rate_gates(per_evaluator: dict[str, float]) -> list[str]:
    """Return a list of gate-failure descriptions; empty if all pass."""
    failures: list[str] = []
    asc = per_evaluator.get("ASC", 0.0)
    cwt = per_evaluator.get("CwT", 0.0)
    tcc = per_evaluator.get("TCC", 0.0)
    if not (ASC_LOWER <= asc <= ASC_UPPER):
        failures.append(f"asc_pass_rate {asc:.3f} outside [{ASC_LOWER}, {ASC_UPPER}]")
    if not (CWT_LOWER <= cwt <= CWT_UPPER):
        failures.append(f"cwt_pass_rate {cwt:.3f} outside [{CWT_LOWER}, {CWT_UPPER}]")
    if cwt >= asc:
        failures.append(f"cwt_pass_rate {cwt:.3f} >= asc_pass_rate {asc:.3f}")
    if tcc > cwt:
        failures.append(f"tcc_pass_rate {tcc:.3f} > cwt_pass_rate {cwt:.3f}")
    return failures


def _check_deterministic_replay(verdicts_a: list[dict], verdicts_b: list[dict]) -> int:
    """Return number of verdict flips between two replay runs. 0 = pass."""
    flips = 0
    for a, b in zip(verdicts_a, verdicts_b):
        for k in a.keys() & b.keys():
            if a[k] != b[k]:
                flips += 1
    return flips


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--normalizer-mode",
        choices=("current", "strict"),
        default="current",
        help="ActionNormalizer profile (KNOWN_ISSUES.md §6-3).",
    )
    ap.add_argument(
        "--horizon-hours",
        type=float,
        default=6.0,
        help="Action-window horizon from sepsis-3 onset (default 6 hours = "
        "Hour-1 bundle plus a buffer for delayed clinical response).",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="If >0, score only the first N cohort episodes (smoke / debug).",
    )
    ap.add_argument(
        "--skip-replay-gate",
        action="store_true",
        help="Skip the deterministic-replay sanity gate. Default behaviour "
        "is to run the scoring loop twice and compare; this doubles wall "
        "time on the full cohort.",
    )
    ap.add_argument("--skip-gates", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    if not COHORT_PARQUET.is_file():
        print(f"[error] missing {COHORT_PARQUET}; run phase0_setup.py first", file=sys.stderr)
        return 2
    if not ACTION_MAPPING.is_file():
        print(
            f"[error] missing {ACTION_MAPPING}; run phase0_action_mapping.py first",
            file=sys.stderr,
        )
        return 2

    action_mapping = _load_action_mapping()
    cohort = pd.read_parquet(COHORT_PARQUET)
    if args.limit and len(cohort) > args.limit:
        cohort = cohort.head(args.limit)
    n_episodes = len(cohort)
    print(f"[phase2] cohort={n_episodes:,}, horizon={args.horizon_hours}h, normalizer={args.normalizer_mode}")

    root = resolve_mimic_root(prefer_full=True)

    # Pre-load the source MIMIC tables once. These reads dominate runtime.
    print("[phase2] loading prescriptions/labevents...", file=sys.stderr)
    rx = read_mimic_csv(
        "prescriptions",
        subdir="hosp",
        root=root,
        usecols=["hadm_id", "drug", "route", "starttime"],
        parse_dates=["starttime"],
        dtype={"drug": str, "route": str},
    )
    rx = rx.dropna(subset=["hadm_id"]).copy()
    rx["hadm_id"] = rx["hadm_id"].astype("int64")
    # hadm-id index for O(1) per-episode lookup downstream.
    rx = rx.set_index("hadm_id", drop=False)
    rx = rx.sort_index()

    # labevents (action-mapping) — uses lactate + blood-culture itemid only
    from scripts.experiments.mimic.phase0_action_mapping import (
        LAB_ITEMID_LACTATE,
        _load_labevents,
    )

    target_itemids = {LAB_ITEMID_LACTATE} | {spec["itemid"] for spec in LAB_ITEMIDS.values()}
    labs, _ = _load_labevents(root, target_itemids=target_itemids)
    if labs is not None:
        labs = labs.dropna(subset=["hadm_id"]).copy()
        labs["hadm_id"] = labs["hadm_id"].astype("int64")
        labs = labs.set_index("hadm_id", drop=False).sort_index()

    # chartevents (vitals) — pre-load once with the union of vital itemids.
    print("[phase2] loading chartevents (vitals)...", file=sys.stderr)
    chart_target = {iid for ids in VITAL_ITEMIDS.values() for iid in ids}
    chartevents = _load_chartevents_for_phase2(root, target_itemids=chart_target)
    if chartevents is not None and len(chartevents):
        chartevents = chartevents.dropna(subset=["hadm_id"]).copy()
        chartevents["hadm_id"] = chartevents["hadm_id"].astype("int64")
        chartevents_by_hadm = dict(tuple(chartevents.groupby("hadm_id")))
    else:
        chartevents_by_hadm = {}

    # labs as a per-hadm dict for fast lookup in _resolve_labs_at_onset.
    if labs is not None and len(labs):
        labs_for_state = labs.reset_index(drop=True)
        labs_by_hadm = dict(tuple(labs_for_state.groupby("hadm_id")))
    else:
        labs_by_hadm = {}

    cpg_engine = _build_cpg_engine(root)
    normalizer = build_normalizer(args.normalizer_mode)
    extractor, scorer_config = _build_extractor_and_scorer_config(cpg_engine)

    # Score every episode.
    rows: list[dict[str, Any]] = []
    verdicts: list[dict[str, bool]] = []
    for _, cohort_row in cohort.iterrows():
        onset_time = cohort_row.get("intime")
        if pd.isna(onset_time):
            onset_time = cohort_row.get("admittime")
        if pd.isna(onset_time):
            continue
        hadm_id = int(cohort_row["hadm_id"])
        actions = _build_episode_trace(
            hadm_id=hadm_id,
            onset_time=onset_time,
            horizon_hours=args.horizon_hours,
            rx=rx,
            labs=labs,
            procs=None,
            action_mapping=action_mapping,
        )
        vitals_at_onset = _resolve_vitals_at_onset(chartevents_by_hadm, hadm_id, onset_time)
        labs_at_onset = _resolve_labs_at_onset(labs_by_hadm, hadm_id, onset_time)
        patient_state = _build_patient_state(
            cohort_row,
            root=root,
            onset_time=onset_time,
            vitals_at_onset=vitals_at_onset,
            labs_at_onset=labs_at_onset,
        )
        ep_dict = _score_one_episode(
            cohort_row=cohort_row,
            actions=actions,
            patient_state=patient_state,
            cpg_engine=cpg_engine,
            normalizer=normalizer,
            extractor=extractor,
            scorer_config=scorer_config,
        )
        verdict_row = _run_verdicts(ep_dict)
        verdicts.append(verdict_row)
        rows.append(
            {
                "episode_id": ep_dict["scenario_id"],
                "model": "mimic_iv_clinicians",
                "scenario_id": ep_dict["scenario_id"],
                "compliance_score": ep_dict["compliance_score"],
                "n_actions": len(ep_dict["actions"]),
                "n_violations": len(ep_dict["violation_events"]),
                **{f"verdict_{k.lower()}": v for k, v in verdict_row.items()},
            }
        )

    df = pd.DataFrame(rows)
    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PARQUET, index=False)
    print(f"[phase2] wrote {OUTPUT_PARQUET} ({len(df):,} rows)")

    # Per-evaluator pass rate
    per_evaluator = {
        name: float(df[f"verdict_{name.lower()}"].mean()) if len(df) else 0.0
        for name in ("TCC", "CwT", "ASC", "PAF", "TOM", "ACov")
    }

    # Deterministic-replay gate (KNOWN_ISSUES.md §6-2)
    replay_flips = None
    if not args.skip_replay_gate and len(cohort) >= DETERMINISTIC_SAMPLE_N:
        sample = cohort.head(DETERMINISTIC_SAMPLE_N)
        replay_a: list[dict] = []
        replay_b: list[dict] = []
        for run_target in (replay_a, replay_b):
            for _, cohort_row in sample.iterrows():
                onset_time = cohort_row.get("intime") or cohort_row.get("admittime")
                if pd.isna(onset_time):
                    continue
                actions_replay = _build_episode_trace(
                    hadm_id=int(cohort_row["hadm_id"]),
                    onset_time=onset_time,
                    horizon_hours=args.horizon_hours,
                    rx=rx,
                    labs=labs,
                    procs=None,
                    action_mapping=action_mapping,
                )
                hadm_id_replay = int(cohort_row["hadm_id"])
                ep_replay = _score_one_episode(
                    cohort_row=cohort_row,
                    actions=actions_replay,
                    patient_state=_build_patient_state(
                        cohort_row,
                        root=root,
                        onset_time=onset_time,
                        vitals_at_onset=_resolve_vitals_at_onset(chartevents_by_hadm, hadm_id_replay, onset_time),
                        labs_at_onset=_resolve_labs_at_onset(labs_by_hadm, hadm_id_replay, onset_time),
                    ),
                    cpg_engine=cpg_engine,
                    normalizer=normalizer,
                    extractor=extractor,
                    scorer_config=scorer_config,
                )
                run_target.append(_run_verdicts(ep_replay))
        replay_flips = _check_deterministic_replay(replay_a, replay_b)
        print(f"[phase2] deterministic-replay flips on N={len(sample)}: {replay_flips}")

    # Summary JSON
    summary = PhaseSummary(
        script_name="phase2_score_trajectories",
        phase="phase2",
        n_episodes=int(n_episodes),
        n_excluded=0,
        seed=args.seed,
        git_sha=git_sha(),
        mimic_version=mimic_version(root),
        wall_time_s=time.time() - t0,
        extra={
            "normalizer_mode": args.normalizer_mode,
            "horizon_hours": args.horizon_hours,
            "per_evaluator_pass_rate": per_evaluator,
            "replay_flips": replay_flips,
        },
    )
    summary.write(PHASE2_DIR)

    failures = _check_pass_rate_gates(per_evaluator)
    if replay_flips is not None and replay_flips > 0:
        failures.append(f"deterministic_replay_flips={replay_flips} (must be 0)")

    if failures and not args.skip_gates:
        try:
            halt_and_log(
                gate_name="phase2_score_trajectories_gates",
                detail="; ".join(failures),
                known_issues_section="6",
            )
        except GateFailure as exc:
            print(f"[HALT] {exc}", file=sys.stderr)
            return 1
    elif failures:
        print(f"[warn] gates failed but --skip-gates: {failures}", file=sys.stderr)

    print(f"[phase2] done in {time.time() - t0:.1f}s; pass-rates: {per_evaluator}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
