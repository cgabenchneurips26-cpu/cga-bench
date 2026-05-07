"""
Synthetic patient state generator for external benchmarks.

Generates realistic patient state trajectories (vitals, lab results)
from static external scenario descriptions, enabling dynamic
simulation for AgentClinic/MedAgentBench/MedChain evaluation.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import random
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class SyntheticVitals:
    """Synthetic vital signs at a single time step."""
    heart_rate: float = 75.0
    blood_pressure_systolic: float = 120.0
    blood_pressure_diastolic: float = 80.0
    respiratory_rate: float = 16.0
    temperature: float = 37.0
    oxygen_saturation: float = 98.0
    map_mmhg: float = 93.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "heart_rate": round(self.heart_rate, 1),
            "blood_pressure_systolic": round(self.blood_pressure_systolic, 1),
            "blood_pressure_diastolic": round(self.blood_pressure_diastolic, 1),
            "respiratory_rate": round(self.respiratory_rate, 1),
            "temperature": round(self.temperature, 1),
            "oxygen_saturation": round(self.oxygen_saturation, 1),
            "map_mmhg": round(self.map_mmhg, 1),
        }


@dataclass
class SyntheticLabResult:
    """A single lab result with ordering and result timestamps."""
    test_code: str
    value: float
    unit: str
    ordered_time_minutes: float
    result_time_minutes: float
    is_abnormal: bool = False


# ------------------------------------------------------------------
# Normal ranges for common labs
# ------------------------------------------------------------------

LAB_NORMAL_RANGES: Dict[str, Tuple[float, float, str]] = {
    "lactate": (0.5, 2.0, "mmol/L"),
    "wbc": (4.0, 11.0, "x10^9/L"),
    "creatinine": (0.6, 1.2, "mg/dL"),
    "troponin": (0.0, 0.04, "ng/mL"),
    "bnp": (0, 100, "pg/mL"),
    "glucose": (70, 100, "mg/dL"),
    "sodium": (135, 145, "mEq/L"),
    "potassium": (3.5, 5.0, "mEq/L"),
    "hemoglobin": (12.0, 17.5, "g/dL"),
    "platelets": (150, 400, "x10^9/L"),
    "inr": (0.8, 1.2, ""),
    "ph": (7.35, 7.45, ""),
    "bicarbonate": (22, 28, "mEq/L"),
    "bun": (7, 20, "mg/dL"),
}


class SyntheticPatientGenerator:
    """Generate realistic patient state trajectories for external scenarios.

    Given static external benchmark data, synthesises:
    - Initial vitals inferred from clinical description
    - Vitals trajectory over time (stable / improving / deteriorating)
    - Lab result values contextualised to the scenario
    """

    def __init__(self, random_seed: Optional[int] = None):
        self._rng = random.Random(random_seed)

    # ------------------------------------------------------------------
    # Vitals inference
    # ------------------------------------------------------------------

    def infer_vitals_from_description(
        self,
        description: str,
        patient_state: Dict[str, Any],
    ) -> SyntheticVitals:
        """Infer initial vitals from scenario description + explicit state."""
        text = description.lower()
        vitals = SyntheticVitals()

        # Hemodynamic patterns
        if any(kw in text for kw in ["hypotension", "shock", "hypotensive"]):
            vitals.blood_pressure_systolic = 85
            vitals.blood_pressure_diastolic = 55
            vitals.map_mmhg = 65
            vitals.heart_rate = 110
        elif any(kw in text for kw in ["hypertension", "hypertensive", "elevated bp"]):
            vitals.blood_pressure_systolic = 165
            vitals.blood_pressure_diastolic = 95
            vitals.map_mmhg = 118

        # Heart rate
        if "tachycardia" in text:
            vitals.heart_rate = 120
        elif "bradycardia" in text:
            vitals.heart_rate = 45

        # Temperature
        if any(kw in text for kw in ["fever", "febrile", "pyrexia"]):
            vitals.temperature = 38.5 + self._rng.uniform(0, 1.0)
        elif "hypothermia" in text:
            vitals.temperature = 35.0 - self._rng.uniform(0, 0.5)

        # Respiratory
        if any(kw in text for kw in ["tachypnea", "respiratory distress", "dyspnea"]):
            vitals.respiratory_rate = 28

        # Oxygenation
        if any(kw in text for kw in ["hypoxia", "desaturation", "hypoxic"]):
            vitals.oxygen_saturation = 88

        # Override with explicit values from patient state
        explicit_vitals = patient_state.get("vitals", {})
        for attr in vars(vitals):
            if attr in explicit_vitals and explicit_vitals[attr] is not None:
                setattr(vitals, attr, float(explicit_vitals[attr]))

        # Recalculate MAP if SBP/DBP were overridden
        vitals.map_mmhg = round(
            vitals.blood_pressure_diastolic
            + (vitals.blood_pressure_systolic - vitals.blood_pressure_diastolic) / 3,
            1,
        )

        return vitals

    # ------------------------------------------------------------------
    # Vitals trajectory
    # ------------------------------------------------------------------

    _VITAL_RANGES = {
        "heart_rate": (40, 180),
        "blood_pressure_systolic": (50, 220),
        "blood_pressure_diastolic": (30, 130),
        "respiratory_rate": (8, 40),
        "temperature": (34.0, 42.0),
        "oxygen_saturation": (70, 100),
        "map_mmhg": (40, 150),
    }

    def generate_vitals_trajectory(
        self,
        initial: SyntheticVitals,
        num_steps: int,
        trend: str = "stable",
    ) -> List[SyntheticVitals]:
        """Generate vitals trajectory.

        Args:
            initial: Starting vitals.
            trend: "stable", "improving", or "deteriorating".
        """
        rates = {"stable": 0.0, "improving": 0.005, "deteriorating": -0.01}
        rate = rates.get(trend, 0.0)

        trajectory = [initial]
        current = initial.to_dict()

        for _ in range(1, num_steps):
            new = {}
            for vital, val in current.items():
                delta = val * rate
                noise = self._rng.uniform(-0.02, 0.02) * abs(val) if val else 0
                lo, hi = self._VITAL_RANGES.get(vital, (0, 999))
                new[vital] = max(lo, min(hi, val + delta + noise))
            current = new
            trajectory.append(SyntheticVitals(**current))

        return trajectory

    # ------------------------------------------------------------------
    # Lab results
    # ------------------------------------------------------------------

    def generate_lab_results(
        self,
        test_codes: List[str],
        description: str,
        ordered_step: int = 0,
        time_step_minutes: float = 5.0,
        result_delay_minutes: float = 30.0,
    ) -> List[SyntheticLabResult]:
        """Generate contextual lab results for ordered tests."""
        text = description.lower()
        results: List[SyntheticLabResult] = []

        for code in test_codes:
            if code not in LAB_NORMAL_RANGES:
                continue
            lo, hi, unit = LAB_NORMAL_RANGES[code]
            value = self._rng.uniform(lo, hi)
            is_abnormal = False

            # Context-dependent abnormal values
            if code == "lactate" and any(k in text for k in ["sepsis", "shock", "lactate"]):
                value = self._rng.uniform(2.5, 6.0)
                is_abnormal = True
            elif code == "wbc" and any(k in text for k in ["infection", "sepsis", "leukocytosis"]):
                value = self._rng.uniform(12.0, 22.0)
                is_abnormal = True
            elif code == "creatinine" and any(k in text for k in ["aki", "renal", "kidney"]):
                value = self._rng.uniform(1.5, 4.0)
                is_abnormal = True
            elif code == "troponin" and any(k in text for k in ["mi", "stemi", "nstemi", "infarction"]):
                value = self._rng.uniform(0.5, 10.0)
                is_abnormal = True
            elif code == "bnp" and any(k in text for k in ["heart failure", "hf", "pulmonary edema"]):
                value = self._rng.uniform(300, 2000)
                is_abnormal = True
            elif code == "glucose" and any(k in text for k in ["dka", "diabetic ketoacidosis", "hyperglycemia"]):
                value = self._rng.uniform(300, 600)
                is_abnormal = True
            elif code == "ph" and any(k in text for k in ["acidosis", "dka"]):
                value = self._rng.uniform(7.10, 7.30)
                is_abnormal = True
            elif code == "potassium" and any(k in text for k in ["hyperkalemia"]):
                value = self._rng.uniform(5.5, 7.0)
                is_abnormal = True

            ordered_time = ordered_step * time_step_minutes
            results.append(SyntheticLabResult(
                test_code=code,
                value=round(value, 2),
                unit=unit,
                ordered_time_minutes=ordered_time,
                result_time_minutes=ordered_time + result_delay_minutes,
                is_abnormal=is_abnormal,
            ))

        return results

    # ------------------------------------------------------------------
    # Full trajectory synthesis
    # ------------------------------------------------------------------

    def synthesize_patient_trajectory(
        self,
        description: str,
        patient_state: Dict[str, Any],
        num_steps: int = 10,
        time_step_minutes: float = 5.0,
        lab_delay_minutes: float = 30.0,
    ) -> Dict[str, Any]:
        """Synthesize complete patient trajectory from external scenario data.

        Returns dict with:
        - vitals_trajectory: List[SyntheticVitals]
        - lab_results: List[SyntheticLabResult]
        - time_step_minutes: float
        """
        initial = self.infer_vitals_from_description(description, patient_state)

        # Determine trend
        text = description.lower()
        if any(k in text for k in ["improving", "recovering", "stable"]):
            trend = "stable"
        elif any(k in text for k in ["deteriorating", "worsening", "declining", "shock"]):
            trend = "deteriorating"
        else:
            trend = "stable"

        trajectory = self.generate_vitals_trajectory(initial, num_steps, trend)

        # Generate labs for common tests
        common_labs = ["lactate", "wbc", "creatinine", "glucose", "potassium"]
        lab_results = self.generate_lab_results(
            common_labs, description,
            ordered_step=0,
            time_step_minutes=time_step_minutes,
            result_delay_minutes=lab_delay_minutes,
        )

        return {
            "vitals_trajectory": trajectory,
            "lab_results": lab_results,
            "time_step_minutes": time_step_minutes,
        }
