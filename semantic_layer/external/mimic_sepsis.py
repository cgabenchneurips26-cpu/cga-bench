"""MIMIC-IV Sepsis-3 cohort adapter.

Wraps real ICU sepsis admissions from MIMIC-IV v3.1 (or the 100-patient demo)
as ``ExternalBenchmarkAdapter`` cases scored against the SSC 2021 Hour-1
Bundle (``cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml``).

Each case is one ICU admission with sepsis ICD codes (A41.* / R65.2*
ICD-10; 995.91/92, 785.52 ICD-9). Per case, the adapter exposes:

  * ``input_text``: a clinical narrative summarising demographics, vitals
    snapshot at sepsis onset (t0), comorbidities, and labs in the
    24-hour window before t0
  * ``structured_fields``: same data in machine-readable form
    (``patient.vitals``, ``ground_truth``)
  * ``timeline_events``: the actual MIMIC interventions in the 0-180 min
    post-t0 window (antibiotics, fluids, vasopressors, lab orders),
    used by ``native_score`` to grade SSC Hour-1 compliance
  * ``gold_path``: the 5 SSC mandatory actions (order_lab_lactate,
    order_lab_blood_culture, give_broad_spectrum_antibiotics,
    give_crystalloid_30ml_kg, start_vasopressor_if_hypotensive)
  * ``checklist``: comorbidity-derived forbidden actions (e.g.
    cephalosporin if penicillin-allergic; aggressive_fluid_bolus if HF)

Usage::

    from cga_bench.semantic_layer.external.mimic_sepsis import (
        MimicSepsisAdapter, load_mimic_sepsis_cohort,
    )
    from cga_bench.semantic_layer.external.registry import get_manifest

    cases = load_mimic_sepsis_cohort(
        data_dir="data/mimic-iv-demo", limit=50,
    )
    adapter = MimicSepsisAdapter(get_manifest("mimic_sepsis"))
    for raw in cases:
        scenario = adapter.parse_to_scenario(raw)        # YAML-shaped dict
        normalized = adapter.parse_to_normalized(raw)    # NormalizedEpisode
        agent_actions = ["order_lab_lactate", ...]
        result = adapter.native_score(raw, agent_actions)  # SSC compliance
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from cga_bench.cpg_model.schemas.base import (
    LabResult,
    PatientState,
    VitalSigns,
)

from .models import (
    CanonicalCase,
    DatasetManifest,
    EpisodeEvidence,
    EvalMode,
    NormalizedEpisode,
    SubScoreMask,
    TaskType,
)
from .pipeline import (
    UniversalExternalAdapter,
    normalize_action_id,
)


logger = logging.getLogger(__name__)


# Re-use the scenario-builder logic from the offline generator without
# introducing a circular import. The generator lives at
# ``scripts/data/generate_mimic_sepsis_scenarios.py``; we lazy-import its
# helpers so the module doesn't fail to load when the generator's MIMIC
# data path isn't on sys.path yet.

SSC_HOUR1_BUNDLE: List[str] = [
    "order_lab_lactate",
    "order_lab_blood_culture",
    "give_broad_spectrum_antibiotics",
    "give_crystalloid_30ml_kg",
    "start_vasopressor_if_hypotensive",
]


# Antibiotic ItemIDs in MIMIC-IV inputevents. Sepsis hour-1 antibiotics
# are typically broad-spectrum: piperacillin-tazobactam, cefepime,
# meropenem, vancomycin, ceftriaxone. We tag any of these as
# "broad_spectrum_antibiotic" for the native scorer.
BROAD_SPECTRUM_ABX_ITEMIDS = {
    225798,  # Piperacillin-Tazobactam
    225837,  # Cefepime
    225850,  # Meropenem
    225855,  # Vancomycin
    225851,  # Ceftriaxone
    225853,  # Cefazolin (less broad but commonly first-line)
    225840,  # Imipenem-Cilastatin
    225862,  # Levofloxacin
    225865,  # Ciprofloxacin
}
NOREPINEPHRINE_ITEMID = 221906
VASOPRESSIN_ITEMID = 222315
EPINEPHRINE_ITEMID = 221289
CRYSTALLOID_ITEMIDS = {225158, 225159}  # Normal saline, Lactated Ringers


@dataclass
class MimicSepsisRaw:
    """Raw case payload — opaque to consumers; consumed by the adapter."""

    subject_id: int
    hadm_id: int
    stay_id: int
    t0: datetime
    age: int
    sex: str
    weight_kg: float | None
    icd_codes: List[tuple[str, int]]
    interventions: List[Dict[str, Any]]   # list of {timestamp, kind, itemid, value}
    vitals_snapshot: Dict[str, float]
    ground_truth: Dict[str, Any]
    comorbidities: List[str]
    forbidden_actions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "hadm_id": self.hadm_id,
            "stay_id": self.stay_id,
            "t0": self.t0.isoformat(),
            "age": self.age,
            "sex": self.sex,
            "weight_kg": self.weight_kg,
            "icd_codes": self.icd_codes,
            "interventions": self.interventions,
            "vitals_snapshot": self.vitals_snapshot,
            "ground_truth": self.ground_truth,
            "comorbidities": self.comorbidities,
            "forbidden_actions": self.forbidden_actions,
        }


def _ensure_generator_on_path() -> None:
    """Make the offline generator's helpers importable inside this module."""
    repo_root = Path(__file__).resolve().parents[2]
    cga_src = repo_root.parent / "cga-bench" / "src"
    for p in (str(repo_root), str(cga_src)):
        if Path(p).is_dir() and p not in sys.path:
            sys.path.insert(0, p)


def load_mimic_sepsis_cohort(
    data_dir: str = "data/mimic-iv-demo", limit: int = 100
) -> List[Dict[str, Any]]:
    """Load Sepsis-3 cohort and return per-case raw payloads.

    Each raw payload is a dict (JSON-serialisable) so it can be cached or
    passed through the standard pipeline. Internally re-uses the
    ``MIMICDataLoader.extract_sepsis_cohort`` plus the offline generator's
    helpers for vitals snapshot / ground-truth extraction.
    """
    _ensure_generator_on_path()
    from data.mimic.data_loader import MIMICDataLoader  # type: ignore
    from data.mimic.schema import InputItemIDs  # type: ignore

    # Lazy imports of the offline generator's helper functions so this
    # module stays usable in environments without the generator script
    # path on sys.path.
    sys.path.insert(0,
        str(Path(__file__).resolve().parents[2] / "scripts" / "data"))
    from generate_mimic_sepsis_scenarios import (  # type: ignore
        load_cohort, _vital_snapshot_at, _ground_truth_at,
        _icd_to_comorbidities, _comorbidity_forbidden,
    )

    loader = MIMICDataLoader(data_dir=data_dir)
    cohort_rows = load_cohort(loader, limit=limit)

    raw_cases: List[Dict[str, Any]] = []
    for row in cohort_rows:
        try:
            comorbidities = _icd_to_comorbidities(row.icd_codes)
            forbidden = _comorbidity_forbidden(comorbidities, allergies=[])
            vitals = _vital_snapshot_at(loader, row.stay_id, row.t0)
            gt = _ground_truth_at(loader, row.subject_id, row.hadm_id, row.t0)
            interventions = _intervention_timeline(
                loader, row.stay_id, row.subject_id, row.hadm_id, row.t0
            )
            raw_cases.append(MimicSepsisRaw(
                subject_id=row.subject_id, hadm_id=row.hadm_id,
                stay_id=row.stay_id, t0=row.t0, age=row.age, sex=row.sex,
                weight_kg=row.weight_kg, icd_codes=row.icd_codes,
                interventions=interventions, vitals_snapshot=vitals,
                ground_truth=gt, comorbidities=comorbidities,
                forbidden_actions=forbidden,
            ).to_dict())
        except Exception as exc:
            logger.warning("skipped %s: %s", row, exc)
            continue
    return raw_cases


def _intervention_timeline(
    loader: Any, stay_id: int, subject_id: int, hadm_id: int, t0: datetime,
) -> List[Dict[str, Any]]:
    """Return MIMIC interventions in the [t0, t0+180min] window.

    Demo MIMIC-IV only ships ``chartevents.csv`` + ``icustays.csv`` under
    ``icu/`` — no ``inputevents.csv`` or ``microbiologyevents.csv``. We
    tolerate any missing CSV (FileNotFoundError) and return whatever
    intervention events the available files yield. The full v3.1
    download has all four files.
    """
    end = t0 + timedelta(minutes=180)
    events: List[Dict[str, Any]] = []

    # Antibiotics + fluids + vasopressors from inputevents (skip on demo)
    try:
        for ev in loader.get_input_events(
            stay_id=stay_id, start_time=t0, end_time=end,
            item_ids=list(BROAD_SPECTRUM_ABX_ITEMIDS) + list(CRYSTALLOID_ITEMIDS) + [
                NOREPINEPHRINE_ITEMID, VASOPRESSIN_ITEMID, EPINEPHRINE_ITEMID,
            ],
        ):
            kind, action_id = _categorise_input_event(ev.itemid)
            events.append({
                "timestamp_minutes": (ev.starttime - t0).total_seconds() / 60.0,
                "kind": kind,
                "action_id": action_id,
                "itemid": ev.itemid,
                "amount": ev.amount,
                "amountuom": ev.amountuom,
            })
    except FileNotFoundError as exc:
        logger.debug("inputevents.csv missing (likely demo data): %s", exc)

    # Lab orders (we use lab event charttime as proxy for "ordered")
    try:
        from data.mimic.schema import LabItemIDs as L  # type: ignore
        lab_orders = loader.get_lab_events(
            subject_id=subject_id, hadm_id=hadm_id,
            start_time=t0, end_time=end,
            item_ids=[L.LACTATE, L.WBC, L.CREATININE],
        )
        for lab in lab_orders:
            kind, action_id = _categorise_lab_event(lab.itemid)
            events.append({
                "timestamp_minutes": (lab.charttime - t0).total_seconds() / 60.0,
                "kind": kind,
                "action_id": action_id,
                "itemid": lab.itemid,
            })
    except Exception:
        pass

    return sorted(events, key=lambda e: e["timestamp_minutes"])


def _categorise_input_event(itemid: int) -> tuple[str, str]:
    if itemid in BROAD_SPECTRUM_ABX_ITEMIDS:
        return "medication", "give_broad_spectrum_antibiotics"
    if itemid in CRYSTALLOID_ITEMIDS:
        return "medication", "give_crystalloid_30ml_kg"
    if itemid == NOREPINEPHRINE_ITEMID:
        return "medication", "start_vasopressor_norepinephrine"
    if itemid == VASOPRESSIN_ITEMID:
        return "medication", "start_vasopressor_vasopressin"
    if itemid == EPINEPHRINE_ITEMID:
        return "medication", "start_vasopressor_epinephrine"
    return "medication", f"unknown_input_{itemid}"


def _categorise_lab_event(itemid: int) -> tuple[str, str]:
    from data.mimic.schema import LabItemIDs as L  # type: ignore
    if itemid == L.LACTATE:
        return "lab", "order_lab_lactate"
    if itemid == L.WBC:
        return "lab", "order_lab_cbc"
    if itemid == L.CREATININE:
        return "lab", "order_lab_creatinine"
    return "lab", f"order_lab_{itemid}"


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class MimicSepsisAdapter(UniversalExternalAdapter):
    """ExternalBenchmarkAdapter for MIMIC-IV Sepsis-3 cohort."""

    def parse_to_scenario(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Return a CGA-Bench scenario YAML dict (compat with sepsis_scenarios.yaml)."""
        sid = self._scenario_id(raw)
        vitals = raw["vitals_snapshot"]
        gt = raw["ground_truth"]
        in_septic_shock = (
            vitals.get("map_mmhg", 70) < 65
            or (gt.get("lab_lactate") is not None and gt["lab_lactate"] > 4)
        )
        return {
            "scenario_id": sid,
            "description": (
                f"MIMIC-IV Sepsis-3 cohort patient — subject {raw['subject_id']}, "
                f"admission {raw['hadm_id']}, stay {raw['stay_id']}, t0={raw['t0']}"
            ),
            "guideline_graph": "ssc_sepsis_hour1_bundle",
            "patient": {
                "age": int(raw["age"]),
                "sex": raw["sex"],
                "weight_kg": float(raw["weight_kg"])
                if raw.get("weight_kg") is not None and raw["weight_kg"] > 0
                else 70.0,
                "chief_complaint": "fever, hypotension, suspected sepsis (MIMIC-IV)",
                "working_diagnosis": "septic_shock" if in_septic_shock else "sepsis",
                "vitals": {k: float(v) for k, v in vitals.items()},
                "allergies": [],
                "comorbidities": list(raw["comorbidities"]),
                "contraindications": [],
            },
            "ground_truth": gt,
            "expected_actions": list(SSC_HOUR1_BUNDLE),
            "forbidden_actions": list(raw["forbidden_actions"]),
            "max_duration_minutes": 180,
            "passing_compliance_threshold": 0.7,
            "trap_scenario": False,
            "trap_description": None,
            "source": "mimic_iv_v3_1_sepsis3",
        }

    def parse_to_normalized(self, raw: Dict[str, Any]) -> NormalizedEpisode:
        """Build NormalizedEpisode from the raw payload + observed timeline.

        The PatientState reflects the t0 snapshot. The actions list captures
        the agent's *expected* output (not what MIMIC actually did — that's
        scored separately in ``native_score``).
        """
        sid = self._scenario_id(raw)
        vitals_snap = raw["vitals_snapshot"]
        patient_state = PatientState(
            state_id=sid,
            time_since_arrival_minutes=0.0,
            age=int(raw["age"]),
            sex=raw["sex"],
            weight_kg=raw.get("weight_kg") or 70.0,
            vitals=VitalSigns(
                heart_rate=int(vitals_snap.get("heart_rate", 100)),
                blood_pressure_systolic=int(vitals_snap.get("blood_pressure_systolic", 100)),
                blood_pressure_diastolic=int(vitals_snap.get("blood_pressure_diastolic", 60)),
                respiratory_rate=int(vitals_snap.get("respiratory_rate", 18)),
                temperature=float(vitals_snap.get("temperature", 37.0)),
                oxygen_saturation=int(vitals_snap.get("oxygen_saturation", 95)),
                map_mmhg=int(vitals_snap.get("map_mmhg", 75)),
            ),
            lab_results=_lab_results_from_gt(raw["ground_truth"]),
            imaging_results=[],
            medications_given=[],
            procedures_done=[],
            pending_orders=[],
            contraindications=[],
            allergies=[],
            comorbidities=list(raw["comorbidities"]),
            chief_complaint="suspected sepsis",
            working_diagnosis="septic_shock"
            if vitals_snap.get("map_mmhg", 70) < 65
            else "sepsis",
            disposition_status=None,
        )
        evidence = EpisodeEvidence(
            has_vitals=bool(vitals_snap),
            has_test_results=bool(raw["ground_truth"]),
            has_imaging_results=False,
            has_medications=any(
                ev.get("kind") == "medication" for ev in raw["interventions"]
            ),
            has_physical_exam=False,
            has_history=True,
            has_diagnosis=True,
            has_timestamps=True,
            action_catalog=set(SSC_HOUR1_BUNDLE) | set(raw["forbidden_actions"]),
            notes=[
                f"MIMIC subject_id={raw['subject_id']}",
                f"interventions_observed={len(raw['interventions'])}",
            ],
        )
        return NormalizedEpisode(
            case_id=sid,
            source_benchmark="mimic_sepsis",
            patient_state=patient_state,
            actions=list(SSC_HOUR1_BUNDLE),
            evidence=evidence,
            guideline_id="ssc_sepsis_hour1_bundle",
            required_actions=list(SSC_HOUR1_BUNDLE),
            warnings=[],
        )

    def detect_domain(self, raw: Dict[str, Any]) -> str:
        return "sepsis"

    def normalize_actions(self, actions: List[str]) -> List[str]:
        # Defer to project-wide normaliser via UniversalExternalAdapter base.
        return [normalize_action_id(a) for a in actions]

    def build_observation(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        sc = self.parse_to_scenario(raw)
        v = sc["patient"]["vitals"]
        gt = sc["ground_truth"]
        narrative_lines = [
            f"Patient {raw['subject_id']}, {raw['age']}-yo {raw['sex']}, "
            f"presenting with suspected sepsis (MIMIC-IV).",
            (f"Vitals at sepsis onset: HR {v.get('heart_rate'):.0f}, "
             f"BP {v.get('blood_pressure_systolic'):.0f}/"
             f"{v.get('blood_pressure_diastolic'):.0f} (MAP "
             f"{v.get('map_mmhg'):.0f}), RR {v.get('respiratory_rate'):.0f}, "
             f"SpO2 {v.get('oxygen_saturation'):.0f}%, Temp "
             f"{v.get('temperature'):.1f} C."),
        ]
        if gt:
            lab_str = ", ".join(f"{k}={v}" for k, v in gt.items() if v is not None)
            narrative_lines.append(f"Recent labs: {lab_str}.")
        if raw["comorbidities"]:
            narrative_lines.append(
                f"Comorbidities: {', '.join(raw['comorbidities'])}.")
        return {
            "input_text": " ".join(narrative_lines),
            "options": [],   # open-ended
            "structured_fields": {
                "patient": sc["patient"],
                "ground_truth": gt,
                "expected_actions": sc["expected_actions"],
                "forbidden_actions": sc["forbidden_actions"],
                "guideline_graph": sc["guideline_graph"],
            },
        }

    def parse_agent_output(
        self, output: Any, raw: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Convert agent's free-text or structured response into action events.

        Accepts:
            * list[str]  — list of action_id strings
            * list[dict] — list of {action_id, timestamp_minutes?, args?}
            * str        — free-text; we extract canonical action_ids by
                            simple regex matching against SSC + forbidden lists
        """
        if isinstance(output, list):
            events: List[Dict[str, Any]] = []
            for i, item in enumerate(output):
                if isinstance(item, dict):
                    aid = item.get("action_id") or item.get("name") or ""
                    if aid:
                        events.append({
                            "action_id": normalize_action_id(aid),
                            "timestamp_minutes": float(item.get(
                                "timestamp_minutes", i * 15)),
                            "kind": item.get("kind", "agent_action"),
                            "args": item.get("args", {}),
                        })
                else:
                    events.append({
                        "action_id": normalize_action_id(str(item)),
                        "timestamp_minutes": float(i * 15),
                        "kind": "agent_action",
                        "args": {},
                    })
            return events
        if isinstance(output, str):
            text = output.lower()
            events = []
            for i, action in enumerate(SSC_HOUR1_BUNDLE + raw["forbidden_actions"]):
                if action in text:
                    events.append({
                        "action_id": action,
                        "timestamp_minutes": float(i * 15),
                        "kind": "agent_action_freetext",
                        "args": {},
                    })
            return events
        return []

    def native_score(
        self, raw: Dict[str, Any], output: Any,
    ) -> Dict[str, Any] | None:
        """SSC 2021 Hour-1 Bundle compliance — five checkpoints.

        Compares agent's action set against the SSC mandates AND against
        the *actual* MIMIC-recorded interventions to give two scores:

            * agent_compliance:  fraction of SSC mandates the agent emitted
            * mimic_compliance:  fraction of SSC mandates that MIMIC's
                                  real intervention timeline satisfied
                                  (within the SSC deadlines)

        Returns a dict with both, plus per-checkpoint detail.
        """
        agent_events = self.parse_agent_output(output, raw)
        agent_actions = {ev["action_id"] for ev in agent_events}

        # SSC checkpoints with deadlines
        checkpoints = {
            "lactate_within_60min": (
                "order_lab_lactate", 60.0,
                lambda evs: any(
                    e["action_id"] == "order_lab_lactate"
                    and e["timestamp_minutes"] <= 60.0
                    for e in evs)),
            "blood_culture_within_60min": (
                "order_lab_blood_culture", 60.0,
                lambda evs: any(
                    e["action_id"] == "order_lab_blood_culture"
                    and e["timestamp_minutes"] <= 60.0
                    for e in evs)),
            "antibiotic_within_60min": (
                "give_broad_spectrum_antibiotics", 60.0,
                lambda evs: any(
                    e["action_id"] == "give_broad_spectrum_antibiotics"
                    and e["timestamp_minutes"] <= 60.0
                    for e in evs)),
            "fluid_30ml_kg_within_180min": (
                "give_crystalloid_30ml_kg", 180.0,
                lambda evs: any(
                    e["action_id"] == "give_crystalloid_30ml_kg"
                    and e["timestamp_minutes"] <= 180.0
                    for e in evs)),
            "vasopressor_within_60min_if_hypotensive": (
                "start_vasopressor_if_hypotensive", 60.0,
                lambda evs: any(
                    "vasopressor" in e["action_id"]
                    and e["timestamp_minutes"] <= 60.0
                    for e in evs)),
        }

        # Score agent (assumed all actions at ≤60 or ≤180 min — the agent's
        # expected behaviour). For the agent, presence in action set counts.
        agent_detail = {
            name: aid in agent_actions for name, (aid, _, _) in checkpoints.items()
        }
        agent_compliance = sum(agent_detail.values()) / len(checkpoints)

        # Score MIMIC actual intervention timeline
        mimic_detail = {
            name: check(raw["interventions"])
            for name, (_, _, check) in checkpoints.items()
        }
        mimic_compliance = sum(mimic_detail.values()) / len(checkpoints)

        # Sequence: blood culture before antibiotic
        bc_event = next(
            (e for e in raw["interventions"]
             if e["action_id"] == "order_lab_blood_culture"), None)
        abx_event = next(
            (e for e in raw["interventions"]
             if e["action_id"] == "give_broad_spectrum_antibiotics"), None)
        bc_before_abx = (
            bc_event is not None and abx_event is not None
            and bc_event["timestamp_minutes"] <= abx_event["timestamp_minutes"]
        )

        # Forbidden-action commission by agent
        forbidden_committed = sorted(set(agent_actions) & set(raw["forbidden_actions"]))

        return {
            "native_score": agent_compliance,
            "agent_compliance": round(agent_compliance, 4),
            "mimic_compliance": round(mimic_compliance, 4),
            "agent_detail": agent_detail,
            "mimic_detail": mimic_detail,
            "blood_culture_before_antibiotic_in_mimic": bc_before_abx,
            "forbidden_committed_by_agent": forbidden_committed,
            "n_mimic_interventions_observed": len(raw["interventions"]),
            "comorbidities": list(raw["comorbidities"]),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _scenario_id(self, raw: Dict[str, Any]) -> str:
        return f"mimic_sepsis_{raw['subject_id']}_{raw['hadm_id']}_{raw['stay_id']}"


def _lab_results_from_gt(gt: Dict[str, Any]) -> List[LabResult]:
    """Map ground_truth dict (lab_lactate=2.5, ...) into LabResult[]."""
    results: List[LabResult] = []
    name_map = {
        "lab_lactate": ("lactate", "mmol/L", 2.0),
        "lab_wbc": ("wbc", "K/uL", 11.0),
        "lab_creatinine": ("creatinine", "mg/dL", 1.2),
        "lab_hemoglobin": ("hemoglobin", "g/dL", 12.0),
        "lab_platelets": ("platelets", "K/uL", 150.0),
        "lab_potassium": ("potassium", "mEq/L", 5.0),
        "lab_sodium": ("sodium", "mEq/L", 145.0),
        "lab_glucose": ("glucose", "mg/dL", 140.0),
        "lab_bicarbonate": ("bicarbonate", "mEq/L", 22.0),
    }
    for k, v in gt.items():
        if not isinstance(v, (int, float)):
            continue
        meta = name_map.get(k)
        if meta is None:
            continue
        test_code, unit, upper_normal = meta
        results.append(LabResult(
            test_code=test_code,
            value=float(v),
            unit=unit,
            timestamp_minutes=0.0,
            is_abnormal=float(v) > upper_normal,
            critical=False,
        ))
    return results


__all__ = [
    "MimicSepsisAdapter",
    "MimicSepsisRaw",
    "load_mimic_sepsis_cohort",
    "SSC_HOUR1_BUNDLE",
]
