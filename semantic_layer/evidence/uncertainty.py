from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypedDict, cast


class DiagnosisCandidate(TypedDict):
    name: str
    probability: float


class UncertaintyOutput(TypedDict):
    diagnoses: list[DiagnosisCandidate]
    action_confidence: float
    abstain_recommendation: bool
    abstain_reason: str


@dataclass
class CalibrationConfig:
    temperature: float = 1.0
    n_bins: int = 10

    @classmethod
    def default(cls) -> CalibrationConfig:
        return cls()


def validate_uncertainty_output(output: object) -> list[str]:
    """Validate uncertainty fields."""
    errors: list[str] = []

    if not isinstance(output, dict):
        return ["output:not_dict"]

    data = cast(dict[str, object], output)

    required = {"diagnoses", "action_confidence", "abstain_recommendation", "abstain_reason"}
    missing = required - set(data.keys())
    if missing:
        errors.append(f"missing_fields:{','.join(sorted(missing))}")
        return errors

    diagnoses = data.get("diagnoses")
    if not isinstance(diagnoses, list):
        errors.append("diagnoses:not_list")
    else:
        diagnosis_items = cast(list[object], diagnoses)
        total_probability = 0.0
        for i, candidate in enumerate(diagnosis_items):
            if not isinstance(candidate, dict):
                errors.append(f"diagnoses[{i}]:not_dict")
                continue

            candidate_data = cast(dict[str, object], candidate)

            name = candidate_data.get("name")
            probability = candidate_data.get("probability")

            if not isinstance(name, str) or not name.strip():
                errors.append(f"diagnoses[{i}].name:empty_or_invalid")

            if not isinstance(probability, (int, float)):
                errors.append(f"diagnoses[{i}].probability:not_numeric")
            else:
                if probability < 0.0 or probability > 1.0:
                    errors.append(f"diagnoses[{i}].probability:out_of_range:{probability}")
                total_probability += float(probability)

        if diagnoses and abs(total_probability - 1.0) > 1e-6:
            errors.append(f"diagnoses:probabilities_not_normalized:{round(total_probability, 6)}")

    action_confidence = data.get("action_confidence")
    if not isinstance(action_confidence, (int, float)):
        errors.append("action_confidence:not_numeric")
    elif action_confidence < 0.0 or action_confidence > 1.0:
        errors.append(f"action_confidence:out_of_range:{action_confidence}")

    abstain_recommendation = data.get("abstain_recommendation")
    if not isinstance(abstain_recommendation, bool):
        errors.append("abstain_recommendation:not_bool")

    abstain_reason = data.get("abstain_reason")
    if not isinstance(abstain_reason, str):
        errors.append("abstain_reason:not_string")
    elif bool(abstain_recommendation) and not abstain_reason.strip():
        errors.append("abstain_reason:required_when_abstaining")

    return errors


def apply_temperature_scaling(confidences: list[float], temperature: float) -> list[float]:
    """Apply temperature scaling to calibrate confidence values."""
    if temperature <= 0:
        raise ValueError("temperature must be > 0")

    if not confidences:
        return []

    if temperature == 1.0:
        return [float(c) for c in confidences]

    epsilon = 1e-12
    scaled: list[float] = []
    for confidence in confidences:
        clipped = min(1.0 - epsilon, max(epsilon, float(confidence)))
        logit = math.log(clipped / (1.0 - clipped))
        calibrated = 1.0 / (1.0 + math.exp(-(logit / temperature)))
        scaled.append(calibrated)
    return scaled


def compute_ece(confidences: list[float], correctness: list[bool], n_bins: int = 10) -> float:
    """Expected Calibration Error."""
    if len(confidences) != len(correctness):
        raise ValueError("confidences and correctness must have same length")
    if not confidences:
        return 0.0
    if n_bins <= 0:
        raise ValueError("n_bins must be > 0")

    total = len(confidences)
    ece = 0.0
    for bin_idx in range(n_bins):
        bin_start = bin_idx / n_bins
        bin_end = (bin_idx + 1) / n_bins
        if bin_idx == n_bins - 1:
            in_bin = [i for i, c in enumerate(confidences) if bin_start <= c <= bin_end]
        else:
            in_bin = [i for i, c in enumerate(confidences) if bin_start <= c < bin_end]

        if not in_bin:
            continue

        bin_conf = sum(confidences[i] for i in in_bin) / len(in_bin)
        bin_acc = sum(1.0 if correctness[i] else 0.0 for i in in_bin) / len(in_bin)
        ece += (len(in_bin) / total) * abs(bin_acc - bin_conf)

    return ece


def compute_brier_score(confidences: list[float], correctness: list[bool]) -> float:
    """Brier score (mean squared error of probabilities)."""
    if len(confidences) != len(correctness):
        raise ValueError("confidences and correctness must have same length")
    if not confidences:
        return 0.0

    total_error = 0.0
    for confidence, is_correct in zip(confidences, correctness, strict=True):
        target = 1.0 if is_correct else 0.0
        total_error += (float(confidence) - target) ** 2
    return total_error / len(confidences)


def compute_overconfidence_rate(
    confidences: list[float],
    correctness: list[bool],
    threshold: float = 0.8,
) -> float:
    """Fraction of cases where confidence > threshold but answer is wrong."""
    if len(confidences) != len(correctness):
        raise ValueError("confidences and correctness must have same length")
    if not confidences:
        return 0.0

    overconfident_wrong = sum(
        1
        for confidence, is_correct in zip(confidences, correctness, strict=True)
        if confidence > threshold and not is_correct
    )
    return overconfident_wrong / len(confidences)


@dataclass
class CalibrationReport:
    ece: float = 0.0
    brier_score: float = 0.0
    overconfidence_rate: float = 0.0
    n_samples: int = 0
    temperature: float = 1.0

    def summary(self) -> dict[str, object]:
        return {
            "ece": round(self.ece, 6),
            "brier_score": round(self.brier_score, 6),
            "overconfidence_rate": round(self.overconfidence_rate, 6),
            "n_samples": self.n_samples,
            "temperature": self.temperature,
        }


def compute_calibration_report(
    confidences: list[float],
    correctness: list[bool],
    config: CalibrationConfig | None = None,
) -> CalibrationReport:
    """Full calibration analysis."""
    if len(confidences) != len(correctness):
        raise ValueError("confidences and correctness must have same length")

    cfg = config or CalibrationConfig.default()
    if not confidences:
        return CalibrationReport(n_samples=0, temperature=cfg.temperature)

    scaled_confidences = apply_temperature_scaling(confidences, cfg.temperature)
    return CalibrationReport(
        ece=compute_ece(scaled_confidences, correctness, n_bins=cfg.n_bins),
        brier_score=compute_brier_score(scaled_confidences, correctness),
        overconfidence_rate=compute_overconfidence_rate(scaled_confidences, correctness),
        n_samples=len(confidences),
        temperature=cfg.temperature,
    )
