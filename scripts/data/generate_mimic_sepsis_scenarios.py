#!/usr/bin/env python3
"""Generate CGA-Bench scenario YAMLs from MIMIC-IV sepsis-3 cohort.

Each Sepsis-3 ICU admission is materialised as a CGA-Bench scenario keyed by
``mimic_{subject_id}_{hadm_id}_{stay_id}``, with:
  * ``patient`` block: demographics + vitals snapshot at sepsis onset (t0)
  * ``ground_truth`` block: lactate/WBC/creatinine/blood-culture/imaging
    drawn from the closest pre-t0 result
  * ``expected_actions``: SSC 2021 Hour-1 Bundle (5 mandatory)
  * ``forbidden_actions``: derived from ICD-10 comorbidities + allergies
  * ``guideline_graph``: ssc_sepsis_hour1_bundle (always)

Default output is a SINGLE combined ``mimic_sepsis_scenarios.yaml`` placed
1-deep at ``configs/scenarios/auto_v2/`` so the existing ScenarioLoader
glob (``auto_v2/*_scenarios.yaml``) picks them up. Pass ``--per-file`` to
write one YAML per scenario instead.

Usage:
    PYTHONPATH=.. python scripts/data/generate_mimic_sepsis_scenarios.py \\
        --data-dir data/mimic-iv-demo \\
        --cohort-limit 100
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
from pathlib import Path
import sys
from typing import Any

import yaml

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]


# ICD-10 → CGA-Bench comorbidity tag (only those that gate SSC forbidden
# actions; see ssc_sepsis_hour1_bundle.yaml lines 188-420).
ICD10_TO_COMORBIDITY: dict[str, str] = {
    "I50":   "heart_failure",            # I50.* HF
    "K70":   "cirrhosis",                # K70.* alcoholic liver disease
    "K74":   "cirrhosis",                # K74.* fibrosis/cirrhosis
    "N18.3": "ckd_stage3",
    "N18.4": "ckd_stage4",
    "N18.5": "ckd_stage5",
    "N18.6": "esrd",
    "Z99.2": "esrd",                     # dependence on dialysis
}
ICD9_TO_COMORBIDITY: dict[str, str] = {
    "428":    "heart_failure",
    "571.5":  "cirrhosis",
    "585.3":  "ckd_stage3",
    "585.4":  "ckd_stage4",
    "585.5":  "ckd_stage5",
    "585.6":  "esrd",
    "V45.11": "esrd",
}


SSC_HOUR1_BUNDLE = [
    "order_lab_lactate",
    "order_lab_blood_culture",
    "give_broad_spectrum_antibiotics",
    "give_crystalloid_30ml_kg",
    "start_vasopressor_if_hypotensive",
]


@dataclass
class CohortRow:
    subject_id: int
    hadm_id: int
    stay_id: int
    t0: datetime
    age: int
    sex: str
    weight_kg: float | None
    icd_codes: list[tuple[str, int]]      # (icd_code, icd_version)


def _icd_to_comorbidities(codes: list[tuple[str, int]]) -> list[str]:
    found: set[str] = set()
    for code, version in codes:
        table = ICD10_TO_COMORBIDITY if version == 10 else ICD9_TO_COMORBIDITY
        for prefix, tag in table.items():
            if code.startswith(prefix):
                found.add(tag)
                break
    return sorted(found)


def _comorbidity_forbidden(tags: list[str], allergies: list[str]) -> list[str]:
    """Map comorbidities + allergies to ssc_sepsis_hour1_bundle forbidden ids."""
    forbidden: set[str] = set()
    for allergy in allergies:
        a = allergy.lower()
        if "penicillin" in a or "amoxicillin" in a or "ampicillin" in a:
            forbidden.update([
                "give_cephalosporin", "give_ceftriaxone",
                "give_cefepime", "give_piperacillin_tazobactam",
                "give_ampicillin", "give_amoxicillin", "give_penicillin",
            ])
    for tag in tags:
        if tag == "heart_failure":
            forbidden.add("give_aggressive_fluid_bolus")
        elif tag == "cirrhosis":
            forbidden.add("give_lactated_ringer_in_liver_failure")
        elif tag in ("ckd_stage3", "ckd_stage4", "ckd_stage5"):
            forbidden.update([
                "give_aminoglycoside_high_dose", "give_nsaid",
                "give_contrast_without_precaution",
            ])
        elif tag == "esrd":
            forbidden.update([
                "give_crystalloid_30ml_kg", "give_large_volume_fluid",
            ])
    return sorted(forbidden)


def _vital_snapshot_at(loader: Any, stay_id: int, t0: datetime) -> dict[str, Any]:
    """Most-recent vital reading per item in the 60 min before t0."""
    from data.mimic.schema import VitalSignItemIDs as V  # type: ignore

    item_ids = [
        V.HEART_RATE, V.SYSTOLIC_BP_NBP, V.SYSTOLIC_BP_ABP,
        V.DIASTOLIC_BP_NBP, V.DIASTOLIC_BP_ABP,
        V.MEAN_BP_NBP, V.MEAN_BP_ABP,
        V.RESPIRATORY_RATE, V.SPO2,
        V.TEMPERATURE_F, V.TEMPERATURE_C,
    ]
    events = loader.get_chart_events(
        stay_id=stay_id,
        start_time=t0 - timedelta(minutes=60),
        end_time=t0,
        item_ids=item_ids,
    )
    out: dict[str, float] = {}
    for ev in sorted(events, key=lambda e: e.charttime):
        if ev.valuenum is None:
            continue
        v = float(ev.valuenum)
        i = ev.itemid
        if i == V.HEART_RATE:
            out["heart_rate"] = v
        elif i in (V.SYSTOLIC_BP_NBP, V.SYSTOLIC_BP_ABP):
            out["blood_pressure_systolic"] = v
        elif i in (V.DIASTOLIC_BP_NBP, V.DIASTOLIC_BP_ABP):
            out["blood_pressure_diastolic"] = v
        elif i in (V.MEAN_BP_NBP, V.MEAN_BP_ABP):
            out["map_mmhg"] = v
        elif i == V.RESPIRATORY_RATE:
            out["respiratory_rate"] = v
        elif i == V.SPO2:
            out["oxygen_saturation"] = v
        elif i == V.TEMPERATURE_C:
            out["temperature"] = v
        elif i == V.TEMPERATURE_F and "temperature" not in out:
            out["temperature"] = round((v - 32) * 5 / 9, 1)

    # Default fillers — required by patient YAML schema if missing
    out.setdefault("heart_rate", 100)
    out.setdefault("blood_pressure_systolic", 100)
    out.setdefault("blood_pressure_diastolic", 60)
    out.setdefault("map_mmhg", out["blood_pressure_diastolic"]
                   + (out["blood_pressure_systolic"] - out["blood_pressure_diastolic"]) / 3)
    out.setdefault("respiratory_rate", 18)
    out.setdefault("oxygen_saturation", 95)
    out.setdefault("temperature", 37.0)
    return out


def _ground_truth_at(loader: Any, subject_id: int, hadm_id: int, t0: datetime) -> dict[str, Any]:
    from data.mimic.schema import LabItemIDs as L  # type: ignore

    item_ids = [L.LACTATE, L.WBC, L.CREATININE, L.HEMOGLOBIN, L.PLATELETS,
                L.POTASSIUM, L.SODIUM, L.GLUCOSE, L.BICARBONATE]
    labs = loader.get_lab_events(
        subject_id=subject_id, hadm_id=hadm_id,
        start_time=t0 - timedelta(hours=24), end_time=t0,
        item_ids=item_ids,
    )
    gt: dict[str, Any] = {}
    for ev in sorted(labs, key=lambda e: e.charttime):
        if ev.valuenum is None:
            continue
        v = float(ev.valuenum)
        if ev.itemid == L.LACTATE:
            gt["lab_lactate"] = v
        elif ev.itemid == L.WBC:
            gt["lab_wbc"] = v
        elif ev.itemid == L.CREATININE:
            gt["lab_creatinine"] = v
        elif ev.itemid == L.HEMOGLOBIN:
            gt["lab_hemoglobin"] = v
        elif ev.itemid == L.PLATELETS:
            gt["lab_platelets"] = v
        elif ev.itemid == L.POTASSIUM:
            gt["lab_potassium"] = v
        elif ev.itemid == L.SODIUM:
            gt["lab_sodium"] = v
        elif ev.itemid == L.GLUCOSE:
            gt["lab_glucose"] = v
        elif ev.itemid == L.BICARBONATE:
            gt["lab_bicarbonate"] = v

    # Microbiology — best-effort, demo may lack the file
    micro = loader.get_microbiology_events(hadm_id=hadm_id,
                                           start_time=t0 - timedelta(hours=24),
                                           end_time=t0)
    if micro:
        positives = [m for m in micro if m.is_positive]
        if positives:
            gt["lab_blood_culture"] = "positive"
        else:
            gt["lab_blood_culture"] = "negative"
    else:
        gt["lab_blood_culture"] = "pending"
    return gt


def build_scenario(loader: Any, row: CohortRow, allergies: list[str]) -> dict[str, Any]:
    comorbidities = _icd_to_comorbidities(row.icd_codes)
    forbidden = _comorbidity_forbidden(comorbidities, allergies)
    vitals = _vital_snapshot_at(loader, row.stay_id, row.t0)
    gt = _ground_truth_at(loader, row.subject_id, row.hadm_id, row.t0)

    sid = f"mimic_sepsis_{row.subject_id}_{row.hadm_id}_{row.stay_id}"
    map_value = vitals.get("map_mmhg", 70)
    lactate = gt.get("lab_lactate")
    in_septic_shock = (map_value < 65) or (lactate is not None and lactate > 4)
    return {
        "scenario_id": sid,
        "description": (f"MIMIC-IV Sepsis-3 cohort patient — subject {row.subject_id}, "
                        f"admission {row.hadm_id}, stay {row.stay_id}, "
                        f"t0={row.t0.isoformat()}"),
        "guideline_graph": "ssc_sepsis_hour1_bundle",
        "patient": {
            "age": int(row.age),
            "sex": row.sex,
            # Use `is not None` rather than truthiness so weight_kg=0.0 (rare
            # but possible during admission) still falls to the default.
            "weight_kg": float(row.weight_kg) if row.weight_kg is not None and row.weight_kg > 0 else 70.0,
            "chief_complaint": "fever, hypotension, suspected sepsis (MIMIC-IV)",
            "working_diagnosis": "septic_shock" if in_septic_shock else "sepsis",
            "vitals": {k: float(v) for k, v in vitals.items()},
            "allergies": list(allergies),
            "comorbidities": comorbidities,
            "contraindications": [],
        },
        "ground_truth": gt,
        "expected_actions": list(SSC_HOUR1_BUNDLE),
        "forbidden_actions": forbidden,
        "max_duration_minutes": 180,
        "passing_compliance_threshold": 0.7,
        "trap_scenario": False,
        "trap_description": None,
        "source": "mimic_iv_v3_1_sepsis3",
    }


def load_cohort(loader: Any, limit: int) -> list[CohortRow]:
    """Reuse MIMICDataLoader.extract_sepsis_cohort if available; else build a
    minimal sepsis-3 cohort from diagnoses_icd + icustays."""
    if hasattr(loader, "extract_sepsis_cohort"):
        try:
            raw = loader.extract_sepsis_cohort()
            if raw:
                return _normalize_cohort(loader, raw, limit)
        except Exception as exc:
            logger.warning("extract_sepsis_cohort failed (%s); falling back to manual scan", exc)
    return _manual_cohort(loader, limit)


def _normalize_cohort(loader: Any, raw: list[dict], limit: int) -> list[CohortRow]:
    out: list[CohortRow] = []
    for entry in raw[:limit]:
        sid = entry.get("subject_id")
        hid = entry.get("hadm_id")
        stay = entry.get("stay_id") or entry.get("icustay_id")
        t0 = entry.get("t0") or entry.get("sepsis_onset")
        if isinstance(t0, str):
            t0 = datetime.fromisoformat(t0)
        if sid is None or hid is None or stay is None or t0 is None:
            continue
        pat = loader.get_patient(int(sid))
        if pat is None:
            continue
        diagnoses = loader.get_diagnoses(int(hid))
        out.append(CohortRow(
            subject_id=int(sid), hadm_id=int(hid), stay_id=int(stay), t0=t0,
            age=int(pat.anchor_age),
            # MIMIC-IV `gender` is M or F; if anything else slips through
            # (legacy data / null), default to "U" (unknown) rather than
            # silently coercing to "M".
            sex={"F": "F", "M": "M"}.get(str(pat.gender).upper(), "U"),
            weight_kg=entry.get("weight_kg"),
            icd_codes=[(d.icd_code, d.icd_version) for d in diagnoses],
        ))
    return out


def _manual_cohort(loader: Any, limit: int) -> list[CohortRow]:
    """Sepsis-3 cohort fallback: any admission with ICD-10 A41.* / R65.2* or
    ICD-9 995.91/92, 785.52, with at least one ICU stay."""
    rows: list[CohortRow] = []
    seen: set[tuple[int, int]] = set()
    for sid in loader.list_all_patients()[: max(limit * 5, 200)]:
        pat = loader.get_patient(int(sid))
        if pat is None:
            continue
        stays = loader.get_icu_stays(int(sid))
        for stay in stays:
            key = (int(sid), int(stay.hadm_id))
            if key in seen:
                continue
            diagnoses = loader.get_diagnoses(int(stay.hadm_id))
            if not any(d.is_sepsis for d in diagnoses):
                continue
            seen.add(key)
            rows.append(CohortRow(
                subject_id=int(sid), hadm_id=int(stay.hadm_id),
                stay_id=int(stay.stay_id),
                t0=stay.intime,
                age=int(pat.anchor_age),
                # MIMIC-IV `gender` is M or F; if anything else slips through
            # (legacy data / null), default to "U" (unknown) rather than
            # silently coercing to "M".
            sex={"F": "F", "M": "M"}.get(str(pat.gender).upper(), "U"),
                weight_kg=None,
                icd_codes=[(d.icd_code, d.icd_version) for d in diagnoses],
            ))
            if len(rows) >= limit:
                return rows
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default="data/mimic-iv-demo",
                   help="MIMIC-IV directory (demo or full v3.1)")
    p.add_argument("--cohort-limit", type=int, default=100)
    p.add_argument("--output-dir", default="configs/scenarios/auto_v2",
                   help="Default writes a single mimic_sepsis_scenarios.yaml at "
                        "auto_v2/ (1-deep) — matches ScenarioLoader glob pattern")
    p.add_argument("--output-name", default="mimic_sepsis_scenarios.yaml",
                   help="Combined yaml filename (must end with _scenarios.yaml "
                        "for ScenarioLoader to pick it up)")
    p.add_argument("--manifest",
                   default="evidence_pack/frontier/mimic_sepsis_manifest.json")
    p.add_argument("--per-file", action="store_true",
                   help="Write one yaml per scenario (default: combined yaml)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parent_of_repo = REPO_ROOT.parent
    if str(parent_of_repo) not in sys.path:
        sys.path.insert(0, str(parent_of_repo))
    # cga-bench/ uses a hyphenated dirname; importing requires path
    cga_bench_src = REPO_ROOT.parent / "cga-bench" / "src"
    if cga_bench_src.exists() and str(cga_bench_src) not in sys.path:
        sys.path.insert(0, str(cga_bench_src))

    from data.mimic.data_loader import MIMICDataLoader  # type: ignore

    loader = MIMICDataLoader(data_dir=args.data_dir)

    print(f"[cohort] loading sepsis cohort, limit={args.cohort_limit}")
    cohort = load_cohort(loader, limit=args.cohort_limit)
    print(f"[cohort] loaded {len(cohort)} sepsis-3 admissions")
    if not cohort:
        print("[error] empty cohort — check data dir / sepsis ICD codes", file=sys.stderr)
        return 1

    out_dir = REPO_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios: dict[str, dict[str, Any]] = {}
    for row in cohort:
        try:
            scenario = build_scenario(loader, row, allergies=[])
        except Exception as exc:
            logger.warning("scenario build failed for %s: %s", row, exc)
            continue
        sid = scenario["scenario_id"]
        scenarios[sid] = scenario
        if args.per_file:
            (out_dir / f"{sid}.yaml").write_text(
                yaml.safe_dump({"scenarios": {sid: scenario}}, sort_keys=False))

    if not args.per_file:
        combined = out_dir / args.output_name
        combined.write_text(yaml.safe_dump({"scenarios": scenarios}, sort_keys=False))
        print(f"[ok] wrote combined {combined}")

    fingerprint = sha256(json.dumps(sorted(scenarios), sort_keys=True).encode()).hexdigest()
    manifest = {
        "metadata": {
            "source": str(args.data_dir),
            "n_scenarios": len(scenarios),
            "fingerprint_sha256": fingerprint,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "cohort_limit": args.cohort_limit,
            "guideline_graph": "ssc_sepsis_hour1_bundle",
        },
        "scenarios": [{
            "scenario_id": s["scenario_id"],
            "subject_id": int(s["scenario_id"].split("_")[2]),
            "comorbidities": s["patient"]["comorbidities"],
            "forbidden_actions": s["forbidden_actions"],
        } for s in scenarios.values()],
    }
    manifest_path = REPO_ROOT / args.manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"[ok] wrote manifest {manifest_path}")
    print(f"  n_scenarios = {len(scenarios)}")
    print(f"  fingerprint = {fingerprint[:16]}…")
    print(f"  output_dir  = {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
