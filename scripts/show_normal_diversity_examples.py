"""Graph 3개를 골라서 pathway-based normal 시나리오가 얼마나 다른지 보여준다."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from cpg_model.constraint_derivation import ConstraintDerivationEngine

engine = ConstraintDerivationEngine()

# ── Example 1: aha_stroke ──
print("=" * 80)
print("EXAMPLE: aha_stroke — Pathway-based Normal Diversity")
print("=" * 80)

with open("cpg_model/graphs/aha_stroke_2019.yaml") as f:
    stroke_graph = yaml.safe_load(f)

stroke_normals = [
    {
        "name": "Ischemic + tPA eligible",
        "patient": {
            "age": 65,
            "sex": "M",
            "comorbidities": ["acute_ischemic_stroke", "ischemic_stroke", "hypertension"],
            "imaging": ["no_hemorrhage"],
            "presentation": {"symptom_onset_hours": 2, "nihss": 14},
            "vitals": {"sbp": 170, "dbp": 95, "hr": 88},
            "labs": {},
            "allergies": [],
            "medications": [],
            "history": [],
            "exam_findings": [],
        },
    },
    {
        "name": "Ischemic + thrombectomy (LVO)",
        "patient": {
            "age": 58,
            "sex": "F",
            "comorbidities": [
                "acute_ischemic_stroke",
                "ischemic_stroke",
                "large_vessel_occlusion",
                "atrial_fibrillation",
            ],
            "imaging": ["lvo_on_cta"],
            "presentation": {"symptom_onset_hours": 8, "nihss": 18},
            "vitals": {"sbp": 160, "dbp": 90, "hr": 95},
            "labs": {},
            "allergies": [],
            "medications": [],
            "history": [],
            "exam_findings": [],
        },
    },
    {
        "name": "Hemorrhagic stroke (ICH)",
        "patient": {
            "age": 72,
            "sex": "M",
            "comorbidities": ["hemorrhagic_stroke", "intracerebral_hemorrhage", "hypertension"],
            "imaging": ["intracerebral_hemorrhage"],
            "presentation": {"nihss": 20},
            "vitals": {"sbp": 210, "dbp": 120, "hr": 75},
            "labs": {},
            "allergies": [],
            "medications": ["warfarin"],
            "history": [],
            "exam_findings": [],
        },
    },
    {
        "name": "Wake-up stroke (extended window)",
        "patient": {
            "age": 60,
            "sex": "F",
            "comorbidities": ["acute_ischemic_stroke", "ischemic_stroke"],
            "imaging": ["favorable_perfusion_mismatch"],
            "presentation": {"symptom_onset_hours": 14, "nihss": 12},
            "vitals": {"sbp": 155, "dbp": 85, "hr": 80},
            "labs": {},
            "allergies": [],
            "medications": [],
            "history": [],
            "exam_findings": [],
        },
    },
]

for normal in stroke_normals:
    result = engine.derive(stroke_graph, normal["patient"], f"stroke_normal_{normal['name']}")

    expected: list[str] = []
    for c in result.expected:
        expected.extend(c.actions)
    for c in result.required:
        expected.extend(c.actions)
    expected = list(dict.fromkeys(expected))

    forbidden = list(dict.fromkeys(a for c in result.forbidden for a in c.actions))

    print(f"\n--- {normal['name']} ---")
    print(f"  Expected ({len(expected)}): {expected[:8]}{'...' if len(expected) > 8 else ''}")
    print(f"  Forbidden ({len(forbidden)}): {forbidden[:5]}{'...' if len(forbidden) > 5 else ''}")

# ── Example 2: ada_dka_management ──
print(f"\n{'=' * 80}")
print("EXAMPLE: ada_dka_management — Pathway-based Normal Diversity")
print("=" * 80)

with open("cpg_model/graphs/ada_dka_management.yaml") as f:
    dka_graph = yaml.safe_load(f)

dka_normals = [
    {
        "name": "Moderate DKA, normal K+",
        "patient": {
            "age": 35,
            "sex": "M",
            "labs": {"potassium": 4.2, "glucose": 450, "ph": 7.15, "bicarbonate": 10},
            "comorbidities": ["type_1_diabetes"],
            "allergies": [],
            "medications": [],
            "vitals": {"hr": 110, "sbp": 100},
            "presentation": {},
            "history": [],
            "exam_findings": [],
        },
    },
    {
        "name": "Severe DKA, pH < 7.0",
        "patient": {
            "age": 28,
            "sex": "F",
            "labs": {"potassium": 4.5, "glucose": 680, "ph": 6.85, "bicarbonate": 3},
            "comorbidities": ["type_1_diabetes"],
            "allergies": [],
            "medications": [],
            "vitals": {"hr": 130, "sbp": 85},
            "presentation": {},
            "history": [],
            "exam_findings": [],
        },
    },
    {
        "name": "DKA + pneumonia trigger",
        "patient": {
            "age": 55,
            "sex": "M",
            "labs": {"potassium": 3.8, "glucose": 520, "ph": 7.20, "bicarbonate": 12},
            "comorbidities": ["type_2_diabetes"],
            "allergies": [],
            "medications": [],
            "vitals": {"hr": 105, "sbp": 110, "temp": 39.2, "spo2": 92},
            "presentation": {"has_fever": True},
            "history": [],
            "exam_findings": ["bilateral_crackles"],
        },
    },
]

for normal in dka_normals:
    result = engine.derive(dka_graph, normal["patient"], f"dka_normal_{normal['name']}")
    expected = []
    for c in result.expected:
        expected.extend(c.actions)
    for c in result.required:
        expected.extend(c.actions)
    expected = list(dict.fromkeys(expected))

    print(f"\n--- {normal['name']} ---")
    print(f"  Expected ({len(expected)}): {expected[:8]}{'...' if len(expected) > 8 else ''}")

# ── Example 3: aha_heart_failure ──
print(f"\n{'=' * 80}")
print("EXAMPLE: aha_heart_failure — Pathway-based Normal Diversity")
print("=" * 80)

with open("cpg_model/graphs/aha_heart_failure_2022.yaml") as f:
    hf_graph = yaml.safe_load(f)

hf_normals = [
    {
        "name": "HFrEF stable",
        "patient": {
            "age": 65,
            "sex": "M",
            "comorbidities": ["hfref", "ef_below_40", "hypertension"],
            "allergies": [],
            "medications": [],
            "vitals": {"hr": 75, "sbp": 120, "spo2": 96},
            "labs": {"bnp": 800, "potassium": 4.0, "creatinine": 1.2},
            "presentation": {},
            "history": [],
            "exam_findings": [],
        },
    },
    {
        "name": "HFpEF with fluid overload",
        "patient": {
            "age": 72,
            "sex": "F",
            "comorbidities": ["hfpef", "ef_above_50", "hypertension", "diabetes"],
            "allergies": [],
            "medications": [],
            "vitals": {"hr": 88, "sbp": 150, "spo2": 93},
            "labs": {"bnp": 500, "potassium": 4.5},
            "presentation": {},
            "history": [],
            "exam_findings": [],
        },
    },
    {
        "name": "Cardiogenic shock",
        "patient": {
            "age": 58,
            "sex": "M",
            "comorbidities": ["hfref", "cardiogenic_shock", "acute_decompensated"],
            "allergies": [],
            "medications": [],
            "vitals": {"hr": 120, "sbp": 75, "spo2": 85},
            "labs": {"bnp": 3000, "lactate": 5.5, "creatinine": 2.8},
            "presentation": {},
            "history": [],
            "exam_findings": [],
        },
    },
]

for normal in hf_normals:
    result = engine.derive(hf_graph, normal["patient"], f"hf_normal_{normal['name']}")
    expected = []
    for c in result.expected:
        expected.extend(c.actions)
    for c in result.required:
        expected.extend(c.actions)
    expected = list(dict.fromkeys(expected))

    forbidden = list(dict.fromkeys(a for c in result.forbidden for a in c.actions))

    print(f"\n--- {normal['name']} ---")
    print(f"  Expected ({len(expected)}): {expected[:8]}{'...' if len(expected) > 8 else ''}")
    print(f"  Forbidden ({len(forbidden)}): {forbidden[:5]}{'...' if len(forbidden) > 5 else ''}")
