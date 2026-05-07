from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, cast

from cga_bench.assessor_core.action_normalizer import ActionNormalizer
from cga_bench.assessor_core.state_reducer import StateReducer
from cga_bench.cpg_engine.engine import CPGEngine, CPGEngineFactory
from cga_bench.cpg_model.schemas.base import Action, ActionType, PatientState, VitalSigns

from .agentclinic import normalize_action_id
from .models import EvaluableComplianceReport, NormalizedEpisode

logger = logging.getLogger(__name__)


@dataclass
class StepRecord:
    step: int
    action_id: str
    normalized_action: str
    timestamp_minutes: float
    mandatory_at_step: list[str]
    forbidden_at_step: list[str]
    was_mandatory: bool
    was_forbidden: bool
    new_mandatory_emerged: list[str]
    state_changes: dict[str, object]


@dataclass
class ClosedLoopResult:
    case_id: str
    guideline_id: str | None
    steps: list[StepRecord]
    final_state: dict[str, object]
    omissions: list[dict[str, object]]
    commissions: list[dict[str, object]]
    timing_violations: list[dict[str, object]]
    sequence_violations: list[dict[str, object]]
    total_mandatory_seen: int
    total_mandatory_completed: int
    total_forbidden_performed: int
    compliance_score: float

    def to_compliance_report(self) -> EvaluableComplianceReport:
        all_violations = (
            self.omissions
            + self.commissions
            + self.timing_violations
            + self.sequence_violations
        )
        performed = [s.action_id for s in self.steps]
        mandatory = sorted({m for s in self.steps for m in s.mandatory_at_step})
        forbidden = sorted({f for s in self.steps for f in s.forbidden_at_step})
        satisfied = [s.action_id for s in self.steps if s.was_mandatory]

        return EvaluableComplianceReport(
            case_id=self.case_id,
            guideline_id=self.guideline_id,
            mandatory_actions=mandatory,
            performed_actions=performed,
            evaluable_actions=mandatory,
            not_observable_actions=[],
            satisfied_actions=satisfied,
            violations=all_violations,
            observability_index=1.0,
            compliance_score=self.compliance_score,
            evidence_summary={"closed_loop": True, "steps": len(self.steps)},
            forbidden_actions=forbidden,
            notes=[f"closed_loop_evaluation:steps={len(self.steps)}"],
        )


@dataclass
class ClosedLoopConfig:
    time_step_minutes: float = 5.0
    enable_timing_check: bool = True
    enable_sequence_check: bool = True
    max_steps: int = 100
    project_root: str | Path = ""

    @classmethod
    def default(cls) -> "ClosedLoopConfig":
        return cls()


class ClosedLoopEvaluator:
    def __init__(self, config: ClosedLoopConfig | None = None):
        self._config: ClosedLoopConfig = config or ClosedLoopConfig.default()
        self._reducer: StateReducer = StateReducer()
        self._normalizer: ActionNormalizer = ActionNormalizer()
        self._engine_cache: dict[str, CPGEngine | None] = {}

    def evaluate(
        self,
        episode: NormalizedEpisode | Mapping[str, object],
        agent_actions: list[str],
    ) -> ClosedLoopResult:
        case_id, guideline_id, initial_state = self._extract_metadata(episode)

        engine = self._load_engine(guideline_id)
        if engine is None:
            return self._empty_result(case_id, guideline_id, "engine_load_failed")

        steps: list[StepRecord] = []
        current_state = initial_state
        all_mandatory_seen: set[str] = set()
        all_mandatory_completed: set[str] = set()
        commissions: list[dict[str, object]] = []
        timing_violations: list[dict[str, object]] = []
        sequence_violations: list[dict[str, object]] = []
        performed_so_far: list[str] = []

        initial_constraints = engine.evaluate(current_state)
        all_mandatory_seen.update(initial_constraints.mandatory_actions)

        for i, raw_action in enumerate(agent_actions[: self._config.max_steps]):
            normalized = self._normalize_for_compare(raw_action, guideline_id)
            timestamp = i * self._config.time_step_minutes

            constraints = engine.evaluate(current_state)
            mandatory_now = set(constraints.mandatory_actions)
            forbidden_now = set(constraints.forbidden_actions)
            deadlines = self._coerce_deadlines(getattr(constraints, "deadlines", None))
            required_prior = self._coerce_required_prior(
                getattr(constraints, "required_prior_actions", None)
            )

            mandatory_now_norm = {
                self._normalize_for_compare(mandatory, guideline_id)
                for mandatory in mandatory_now
            }
            forbidden_now_norm = {
                self._normalize_for_compare(forbidden, guideline_id)
                for forbidden in forbidden_now
            }

            all_mandatory_seen.update(mandatory_now)

            was_mandatory = normalized in mandatory_now_norm
            was_forbidden = normalized in forbidden_now_norm

            if was_mandatory:
                all_mandatory_completed.add(normalized)

            if was_forbidden:
                commissions.append(
                    {
                        "type": "COMMISSION",
                        "action": raw_action,
                        "step": i,
                        "timestamp_minutes": timestamp,
                        "description": f"forbidden_action_at_step_{i}:{raw_action}",
                    }
                )

            if self._config.enable_timing_check and deadlines:
                for action_id, deadline in deadlines.items():
                    deadline_action = self._normalize_for_compare(action_id, guideline_id)
                    if deadline_action == normalized and timestamp > float(deadline):
                        timing_violations.append(
                            {
                                "type": "TIMING",
                                "action": raw_action,
                                "step": i,
                                "deadline_minutes": float(deadline),
                                "actual_minutes": timestamp,
                                "delay_minutes": timestamp - float(deadline),
                            }
                        )

            if self._config.enable_sequence_check and required_prior:
                norm_performed = {normalize_action_id(p) for p in performed_so_far}
                for action_id, priors in required_prior.items():
                    if self._normalize_for_compare(action_id, guideline_id) != normalized:
                        continue
                    missing = [
                        prior
                        for prior in priors
                        if self._normalize_for_compare(prior, guideline_id)
                        not in norm_performed
                    ]
                    if missing:
                        sequence_violations.append(
                            {
                                "type": "SEQUENCE",
                                "action": raw_action,
                                "step": i,
                                "missing_priors": missing,
                            }
                        )

            action_obj = Action(
                type=self._infer_action_type(normalized),
                action_id=normalized,
                args={},
                timestamp_minutes=timestamp,
                justification=None,
            )
            apply_fn = cast(
                Callable[[PatientState, Action, object | None], PatientState],
                self._reducer.apply,
            )
            new_state = apply_fn(current_state, action_obj, None)

            state_changes = self._diff_states(current_state, new_state)

            new_constraints = engine.evaluate(new_state)
            new_mandatory = set(new_constraints.mandatory_actions) - mandatory_now
            all_mandatory_seen.update(new_constraints.mandatory_actions)

            steps.append(
                StepRecord(
                    step=i,
                    action_id=raw_action,
                    normalized_action=normalized,
                    timestamp_minutes=timestamp,
                    mandatory_at_step=sorted(mandatory_now),
                    forbidden_at_step=sorted(forbidden_now),
                    was_mandatory=was_mandatory,
                    was_forbidden=was_forbidden,
                    new_mandatory_emerged=sorted(new_mandatory),
                    state_changes=state_changes,
                )
            )

            performed_so_far.append(normalized)
            current_state = new_state

        omissions: list[dict[str, object]] = []
        for mandatory in all_mandatory_seen:
            if self._normalize_for_compare(mandatory, guideline_id) not in all_mandatory_completed:
                omissions.append(
                    {
                        "type": "OMISSION",
                        "action": mandatory,
                        "description": f"mandatory_never_completed:{mandatory}",
                    }
                )

        total_mandatory = len(all_mandatory_seen)
        total_completed = len(all_mandatory_completed)
        compliance = total_completed / max(total_mandatory, 1)

        return ClosedLoopResult(
            case_id=case_id,
            guideline_id=guideline_id,
            steps=steps,
            final_state=self._state_to_dict(current_state),
            omissions=omissions,
            commissions=commissions,
            timing_violations=timing_violations,
            sequence_violations=sequence_violations,
            total_mandatory_seen=total_mandatory,
            total_mandatory_completed=total_completed,
            total_forbidden_performed=len(commissions),
            compliance_score=compliance,
        )

    def _extract_metadata(
        self,
        episode: NormalizedEpisode | Mapping[str, object],
    ) -> tuple[str, str | None, PatientState]:
        if isinstance(episode, Mapping):
            case_id = str(episode.get("case_id", "unknown"))
            guideline_raw = episode.get("guideline_id")
            guideline_id = guideline_raw if isinstance(guideline_raw, str) else None
            patient_state = episode.get("patient_state")
            if isinstance(patient_state, PatientState):
                return case_id, guideline_id, patient_state
            if isinstance(patient_state, dict):
                return case_id, guideline_id, PatientState.model_validate(patient_state)
            return case_id, guideline_id, PatientState(
                state_id=case_id,
                age=50,
                sex="U",
                vitals=VitalSigns(map_mmhg=None),
                chief_complaint="",
            )

        return episode.case_id, episode.guideline_id, episode.patient_state

    def _load_engine(self, guideline_id: str | None) -> CPGEngine | None:
        if not guideline_id:
            return None

        if guideline_id in self._engine_cache:
            return self._engine_cache[guideline_id]

        root = Path(self._config.project_root) if self._config.project_root else Path(".")
        candidates = [
            root / guideline_id,
            root / f"{guideline_id}.yaml",
            root / f"{guideline_id}.yml",
            root / "cpg_model" / "graphs" / guideline_id,
            root / "cpg_model" / "graphs" / f"{guideline_id}.yaml",
            root / "cpg_model" / "graphs" / f"{guideline_id}.yml",
        ]

        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                engine = CPGEngineFactory.load_from_file(str(candidate))
                self._engine_cache[guideline_id] = engine
                return engine
            except Exception as exc:
                logger.debug("Failed to load CPG %s: %s", candidate, exc)

        self._engine_cache[guideline_id] = None
        return None

    def _diff_states(self, old: PatientState, new: PatientState) -> dict[str, object]:
        changes: dict[str, object] = {}
        if len(new.lab_results) > len(old.lab_results):
            changes["new_labs"] = len(new.lab_results) - len(old.lab_results)
        if len(new.medications_given) > len(old.medications_given):
            changes["new_medications"] = len(new.medications_given) - len(old.medications_given)
        if len(new.procedures_done) > len(old.procedures_done):
            changes["new_procedures"] = len(new.procedures_done) - len(old.procedures_done)
        if new.time_since_arrival_minutes != old.time_since_arrival_minutes:
            changes["time_minutes"] = new.time_since_arrival_minutes
        return changes

    def _state_to_dict(self, state: PatientState) -> dict[str, object]:
        return {
            "labs": len(state.lab_results),
            "medications": len(state.medications_given),
            "procedures": len(state.procedures_done),
            "time_minutes": state.time_since_arrival_minutes,
        }

    def _empty_result(
        self,
        case_id: str,
        guideline_id: str | None,
        reason: str,
    ) -> ClosedLoopResult:
        logger.debug("Closed-loop empty result for %s: %s", case_id, reason)
        return ClosedLoopResult(
            case_id=case_id,
            guideline_id=guideline_id,
            steps=[],
            final_state={},
            omissions=[],
            commissions=[],
            timing_violations=[],
            sequence_violations=[],
            total_mandatory_seen=0,
            total_mandatory_completed=0,
            total_forbidden_performed=0,
            compliance_score=0.0,
        )

    def _infer_action_type(self, action_id: str) -> ActionType:
        if action_id.startswith("order_lab_"):
            return ActionType.ORDER_LAB
        if action_id.startswith("order_imaging_"):
            return ActionType.ORDER_IMAGING
        if action_id.startswith("give_"):
            return ActionType.GIVE_MEDICATION
        if action_id.startswith("consult_"):
            return ActionType.CONSULT
        if action_id.startswith("admit_") or action_id.startswith("discharge_"):
            return ActionType.DISPOSITION
        if action_id.startswith("reassess_"):
            return ActionType.REASSESS
        return ActionType.PROCEDURE

    def _normalize_for_compare(self, action_id: str, guideline_id: str | None) -> str:
        normalized = self._normalizer.normalize(action_id, cpg_id=guideline_id)
        return normalize_action_id(normalized)

    def _coerce_deadlines(self, raw: object) -> dict[str, float]:
        if not isinstance(raw, dict):
            return {}
        raw_dict = cast(dict[object, object], raw)
        cleaned: dict[str, float] = {}
        for key, value in raw_dict.items():
            if not isinstance(key, str):
                continue
            if not isinstance(value, (int, float, str)):
                continue
            try:
                cleaned[key] = float(value)
            except (TypeError, ValueError):
                continue
        return cleaned

    def _coerce_required_prior(self, raw: object) -> dict[str, list[str]]:
        if not isinstance(raw, dict):
            return {}
        raw_dict = cast(dict[object, object], raw)
        cleaned: dict[str, list[str]] = {}
        for key, value in raw_dict.items():
            if not isinstance(key, str) or not isinstance(value, list):
                continue
            values = cast(list[object], value)
            priors = [item for item in values if isinstance(item, str)]
            if priors:
                cleaned[key] = priors
        return cleaned
