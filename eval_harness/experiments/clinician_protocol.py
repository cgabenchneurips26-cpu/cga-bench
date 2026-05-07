"""
Experiment B: Clinician Pairwise Preference Protocol

Designs the protocol for clinician preference alignment study.
Execution requires clinician recruitment (future work).

Outputs:
- Protocol document
- Trace pair selection
- Survey templates
- Analysis plan (Kendall's tau)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TracePair:
    """A pair of traces for clinician comparison."""
    pair_id: str
    scenario_id: str
    trace_a_id: str
    trace_b_id: str
    trace_a_agent: str
    trace_b_agent: str
    trace_a_compliance: float
    trace_b_compliance: float
    compliance_gap: float
    trace_a_task_pass: bool
    trace_b_task_pass: bool
    trace_a_sub_scores: Dict[str, float]
    trace_b_sub_scores: Dict[str, float]
    is_perturbed: bool = False
    perturbation_type: Optional[str] = None


@dataclass
class ClinicianSurveyQuestion:
    """A question in the clinician survey."""
    question_id: str
    text: str
    response_options: List[str]


@dataclass
class SurveyTemplate:
    """Survey template for a single trace pair."""
    pair_id: str
    patient_summary: str
    trace_a_timeline: List[Dict[str, str]]
    trace_b_timeline: List[Dict[str, str]]
    questions: List[ClinicianSurveyQuestion]


SURVEY_QUESTIONS: List[ClinicianSurveyQuestion] = [
    ClinicianSurveyQuestion(
        question_id="Q1_guideline_adherence",
        text="Which trace better adheres to the relevant clinical guideline?",
        response_options=["Trace A", "Trace B", "Equal"],
    ),
    ClinicianSurveyQuestion(
        question_id="Q2_patient_safety",
        text="Which trace is safer for the patient?",
        response_options=["Trace A", "Trace B", "Equal"],
    ),
    ClinicianSurveyQuestion(
        question_id="Q3_supervisory_acceptance",
        text="As an attending physician, which trace would you approve?",
        response_options=["Trace A", "Trace B", "Both", "Neither"],
    ),
]


class ClinicianProtocolDesigner:
    """Designs the clinician preference alignment protocol.

    Selects trace pairs from existing results, generates survey
    materials, and defines the analysis plan.
    """

    MIN_COMPLIANCE_GAP = 0.15  # Minimum >15%p difference for pair selection
    TARGET_PAIRS = 25          # Target number of pairs

    def __init__(
        self,
        output_dir: str = "evidence_pack/experiments",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.pairs: List[TracePair] = []
        self.results: List[dict] = []  # Raw result dicts

    def load_results(self, results_dirs: List[str]) -> int:
        """Load result files for pair selection."""
        count = 0
        for rdir_path in results_dirs:
            rdir = Path(rdir_path)
            if not rdir.exists():
                continue
            for json_file in sorted(rdir.glob("*.json")):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["_file"] = str(json_file)
                    data["_episode_id"] = json_file.stem
                    self.results.append(data)
                    count += 1
                except (json.JSONDecodeError, KeyError):
                    pass
        logger.info(f"Loaded {count} results for pair selection")
        return count

    def select_pairs(
        self,
        include_perturbed: Optional[List[dict]] = None,
    ) -> List[TracePair]:
        """Select trace pairs meeting criteria.

        Criteria:
        - Same scenario
        - Both Task Completion PASS (C2 == 1.0)
        - CGA compliance gap > 15%p
        """
        self.pairs = []

        # Group by scenario
        by_scenario: Dict[str, List[dict]] = {}
        for r in self.results:
            sid = r.get("scenario_id", "")
            by_scenario.setdefault(sid, []).append(r)

        pair_count = 0
        for scenario_id, episodes in sorted(by_scenario.items()):
            # Only Task-PASS episodes
            task_pass_eps = [
                ep for ep in episodes
                if ep.get("sub_scores", {}).get("C2_mandatory_completion", 0) >= 1.0
            ]

            # Generate pairs from different agents/runs
            for i in range(len(task_pass_eps)):
                for j in range(i + 1, len(task_pass_eps)):
                    a = task_pass_eps[i]
                    b = task_pass_eps[j]

                    comp_a = a.get("compliance_score", 0.0)
                    comp_b = b.get("compliance_score", 0.0)
                    gap = abs(comp_a - comp_b)

                    if gap < self.MIN_COMPLIANCE_GAP:
                        continue

                    # Ensure A has higher compliance
                    if comp_a < comp_b:
                        a, b = b, a
                        comp_a, comp_b = comp_b, comp_a

                    pair_count += 1
                    self.pairs.append(
                        TracePair(
                            pair_id=f"pair_{pair_count:03d}",
                            scenario_id=scenario_id,
                            trace_a_id=a.get("_episode_id", f"ep_{i}"),
                            trace_b_id=b.get("_episode_id", f"ep_{j}"),
                            trace_a_agent=a.get("agent_id", "unknown"),
                            trace_b_agent=b.get("agent_id", "unknown"),
                            trace_a_compliance=comp_a,
                            trace_b_compliance=comp_b,
                            compliance_gap=gap,
                            trace_a_task_pass=True,
                            trace_b_task_pass=True,
                            trace_a_sub_scores=a.get("sub_scores", {}),
                            trace_b_sub_scores=b.get("sub_scores", {}),
                        )
                    )

        # Add perturbed pairs (original vs perturbed)
        if include_perturbed:
            for pr in include_perturbed:
                if pr.get("description") == "Baseline (no perturbation)":
                    continue
                if not pr.get("task_completion_pass", False):
                    continue

                pair_count += 1
                self.pairs.append(
                    TracePair(
                        pair_id=f"pair_{pair_count:03d}",
                        scenario_id=pr["scenario_id"],
                        trace_a_id=f"baseline_{pr['scenario_id']}",
                        trace_b_id=f"perturbed_{pr['scenario_id']}_{pr['perturbation_type']}",
                        trace_a_agent="baseline",
                        trace_b_agent="perturbed",
                        trace_a_compliance=1.0,  # baseline assumed high
                        trace_b_compliance=pr.get("cga_compliance", 0.0),
                        compliance_gap=abs(1.0 - pr.get("cga_compliance", 0.0)),
                        trace_a_task_pass=True,
                        trace_b_task_pass=True,
                        trace_a_sub_scores={},
                        trace_b_sub_scores=pr.get("cga_sub_scores", {}),
                        is_perturbed=True,
                        perturbation_type=pr.get("perturbation_type"),
                    )
                )

        # Sort by compliance gap (most informative first)
        self.pairs.sort(key=lambda p: p.compliance_gap, reverse=True)

        # Trim to target count
        if len(self.pairs) > self.TARGET_PAIRS:
            self.pairs = self.pairs[: self.TARGET_PAIRS]

        logger.info(f"Selected {len(self.pairs)} trace pairs")
        return self.pairs

    def generate_protocol(self) -> None:
        """Generate the full clinician protocol package."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Protocol document
        protocol_path = self.output_dir / "clinician_protocol.md"
        with open(protocol_path, "w", encoding="utf-8") as f:
            f.write(self._generate_protocol_document())

        # Pair details JSON
        pairs_path = self.output_dir / "clinician_pairs.json"
        pairs_data = {
            "experiment": "B_clinician_preference",
            "description": "Clinician Pairwise Preference Alignment Study",
            "total_pairs": len(self.pairs),
            "selection_criteria": {
                "min_compliance_gap": self.MIN_COMPLIANCE_GAP,
                "both_task_pass": True,
                "same_scenario": True,
            },
            "pairs": [
                {
                    "pair_id": p.pair_id,
                    "scenario_id": p.scenario_id,
                    "trace_a_id": p.trace_a_id,
                    "trace_b_id": p.trace_b_id,
                    "trace_a_agent": p.trace_a_agent,
                    "trace_b_agent": p.trace_b_agent,
                    "trace_a_compliance": p.trace_a_compliance,
                    "trace_b_compliance": p.trace_b_compliance,
                    "compliance_gap": p.compliance_gap,
                    "is_perturbed": p.is_perturbed,
                    "perturbation_type": p.perturbation_type,
                }
                for p in self.pairs
            ],
        }

        with open(pairs_path, "w", encoding="utf-8") as f:
            json.dump(pairs_data, f, indent=2, ensure_ascii=False)

        # Survey response template
        template_path = self.output_dir / "clinician_response_template.json"
        template = {
            "rater_id": "",
            "specialty": "",
            "years_experience": 0,
            "responses": [
                {
                    "pair_id": p.pair_id,
                    "Q1_guideline_adherence": "",
                    "Q2_patient_safety": "",
                    "Q3_supervisory_acceptance": "",
                    "comments": "",
                }
                for p in self.pairs
            ],
        }

        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)

        logger.info(
            f"Protocol generated: {protocol_path}, {pairs_path}, {template_path}"
        )

    def _generate_protocol_document(self) -> str:
        """Generate the clinician study protocol document."""
        perturbed_count = sum(1 for p in self.pairs if p.is_perturbed)
        natural_count = len(self.pairs) - perturbed_count

        return f"""# Clinician Pairwise Preference Alignment Study Protocol

## Study Objective

Determine whether CGA ranking better aligns with clinician preference
than task-completion ranking for evaluating medical AI agent trajectories.

## Hypothesis

CGA-based ranking of agent trajectories correlates more strongly with
clinician preference (Kendall's τ) than task-completion ranking.

## Study Design

### Participants
- **Required**: 5-10 clinicians
- **Specialties**: Emergency Medicine, Internal Medicine, Critical Care
- **Experience**: Minimum 3 years post-residency
- **Blinding**: CGA scores NOT shown to clinicians (blind evaluation)

### Trace Pairs
- **Total pairs**: {len(self.pairs)}
  - Natural pairs (different agents/runs): {natural_count}
  - Perturbed pairs (original vs. perturbation): {perturbed_count}
- **Selection criteria**:
  - Same clinical scenario
  - Both traces achieve Task Completion PASS
  - CGA compliance gap > {self.MIN_COMPLIANCE_GAP:.0%}

### Materials per Pair
1. Patient case summary (anonymized)
2. Trace A: Action sequence with timestamps (timeline format)
3. Trace B: Action sequence with timestamps (timeline format)
4. CGA scores are HIDDEN from the clinician

### Questions (per pair)
1. **Q1 (Guideline Adherence)**: "Which trace better adheres to the relevant clinical guideline?" [A / B / Equal]
2. **Q2 (Patient Safety)**: "Which trace is safer for the patient?" [A / B / Equal]
3. **Q3 (Supervisory Acceptance)**: "As an attending physician, which trace would you approve?" [A / B / Both / Neither]

## Analysis Plan

### Primary Analysis
- **CGA vs. clinician preference**: Kendall's τ between CGA ranking and clinician majority vote
- **Task completion vs. clinician preference**: Kendall's τ between task-completion ranking and clinician majority vote
- **Comparison**: If τ(CGA) > τ(Task), CGA aligns better with clinical judgment

### Inter-Rater Reliability
- **Cohen's κ** between all rater pairs
- **Fleiss' κ** for overall agreement

### Secondary Analyses
- Per-scenario agreement rates
- Per-question agreement rates
- Agreement on perturbed vs. natural pairs
- Qualitative analysis of comments

## Ethical Considerations

### IRB
- No real patient data is exposed (synthetic/anonymized scenarios)
- Clinician participation is voluntary
- No identifying information collected beyond specialty and experience

### Informed Consent
- Participants informed of study purpose (after completion to avoid bias)
- Participants may withdraw at any time

## Timeline

1. **Protocol review**: 1 week
2. **Clinician recruitment**: 2-3 weeks
3. **Data collection**: 1-2 weeks
4. **Analysis**: 1 week

## Pair Details

| Pair | Scenario | Gap | Type |
|------|----------|-----|------|
"""  + "\n".join(
            f"| {p.pair_id} | {p.scenario_id} | {p.compliance_gap:.1%} | "
            f"{'Perturbed' if p.is_perturbed else 'Natural'} |"
            for p in self.pairs
        )
