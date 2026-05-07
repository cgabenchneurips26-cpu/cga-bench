"""Evaluation Runner: 실험 실행기"""

from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

from cga_bench.agent_runner.base_agent import BaseAgent
from cga_bench.assessor_core.clinical_interaction_detector import (
    InteractionConfig,
    InteractionPattern,
    InteractionType,
)
from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig, MetricsReporter
from cga_bench.assessor_core.violations import (
    HarmSeverityMapping,
    TimingSeverityThreshold,
    ViolationExtractor,
    ViolationExtractorConfig,
)
from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.constraint_derivation import (
    ConstraintDerivationEngine,
    load_graph as load_cpg_graph,
)
from cga_bench.cpg_model.schemas.base import (
    CGAScore,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    RecommendationClass,
    ViolationType,
    VitalSigns,
)
from cga_bench.eval_harness.pipeline import (
    BatchPipelineResult,
    EpisodePipelineResult,
    PipelineConfig,
    PostScoringPipeline,
)
from cga_bench.scenario_engine.environment import (
    ClinicalEnvironment,
    DeteriorationConfig,
    EnvironmentConfig,
    LabThreshold,
    MedicationEffectConfig,
    TerminationConfig,
)


class BudgetExceededError(RuntimeError):
    """에이전트가 실험 예산 한도를 초과한 경우 발생."""

    pass


@dataclass
class ExperimentConfig:
    """실험 설정 - 예산 한도는 공정한 비교를 위해 실험 수준에서 설정"""

    experiment_id: str
    scenarios: list[str]
    agents: list[str]
    num_runs_per_scenario: int = 1
    output_dir: str = "results"
    save_logs: bool = True
    save_scores: bool = True
    # Budget-matched 실험을 위한 예산 설정 (모든 에이전트에 동일 적용)
    budget_limit_tokens: int | None = None
    budget_limit_tool_calls: int | None = None
    enforce_budget_matching: bool = False  # True면 예산 설정 필수
    # Post-scoring pipeline (opt-in)
    pipeline_config: PipelineConfig | None = None
    # Reproducibility
    random_seed: int | None = None
    # B-cde-rescoring (v1.1): couple CDE-derived constraints into the scoring
    # path. Episode trajectory unchanged; ViolationExtractor emits supplementary
    # OMISSION/COMMISSION/CONFLICT for conditional_rules the runtime engine
    # never evaluates. Default False — opt-in until paper submission.
    enable_cde_rescoring: bool = False

    def __post_init__(self):
        """예산 매칭 강제 검증 및 재현성 시드 설정"""
        if self.enforce_budget_matching:
            if self.budget_limit_tokens is None and self.budget_limit_tool_calls is None:
                raise ValueError(
                    "Budget matching is enforced but no budget limits set. "
                    "Set budget_limit_tokens and/or budget_limit_tool_calls for fair comparison."
                )
        if self.random_seed is not None:
            import random

            random.seed(self.random_seed)
            try:
                import numpy as np

                np.random.seed(self.random_seed)
            except ImportError:
                pass
            logger.info(f"Random seed set to {self.random_seed}")


@dataclass
class ExperimentResult:
    """실험 결과"""

    experiment_id: str
    scenario_id: str
    agent_id: str
    run_number: int
    episode_log: EpisodeLog
    score: CGAScore
    timestamp: str
    pipeline_result: EpisodePipelineResult | None = None


class EvaluationRunner:
    """평가 실행기

    기능:
    - 시나리오 로드
    - 에이전트 실행
    - 위반 추출 및 채점
    - 결과 저장
    """

    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.results: list[ExperimentResult] = []
        self._pipeline: PostScoringPipeline | None = None
        self._last_batch_result: BatchPipelineResult | None = None
        if config.pipeline_config:
            self._pipeline = PostScoringPipeline(config.pipeline_config)
            logger.info("Post-scoring pipeline initialized")

    def load_scenario(self, scenario_path: str) -> dict[str, Any]:
        """시나리오 파일 로드"""
        with open(scenario_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def create_patient_from_config(self, patient_config: dict) -> PatientState:
        """설정에서 PatientState 생성 - 모든 필수 필드는 명시적으로 제공되어야 함"""
        # 필수 필드 검증
        required_fields = ["age", "sex", "chief_complaint", "vitals"]
        for field in required_fields:
            if field not in patient_config:
                raise ValueError(f"Required patient field '{field}' missing in patient_config")

        vitals_config = patient_config["vitals"]
        vitals = VitalSigns(**vitals_config)

        return PatientState(
            state_id=f"patient_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            age=patient_config["age"],
            sex=patient_config["sex"],
            weight_kg=patient_config.get("weight_kg"),  # Optional
            vitals=vitals,
            chief_complaint=patient_config["chief_complaint"],
            working_diagnosis=patient_config.get("working_diagnosis"),  # Optional
            allergies=patient_config.get("allergies", []),  # Optional, defaults to empty list
            comorbidities=patient_config.get("comorbidities", []),  # Optional, defaults to empty list
            contraindications=patient_config.get("contraindications", []),  # Optional, defaults to empty list
        )

    def create_environment(self, patient: PatientState, scenario_config: dict) -> ClinicalEnvironment:
        """환경 생성 - 모든 설정은 시나리오에서 명시적으로 제공되어야 함"""
        # 필수 필드 검증
        required_fields = [
            "max_duration_minutes",
            "time_step_minutes",
            "lab_result_delay_minutes",
            "imaging_result_delay_minutes",
            "enable_state_deterioration",
            "ground_truth",
        ]
        for field in required_fields:
            if field not in scenario_config:
                raise ValueError(f"Required field '{field}' missing in scenario_config")

        # 약물 효과 설정 파싱
        medication_effects = [
            MedicationEffectConfig(**effect) for effect in scenario_config.get("medication_effects", [])
        ]

        # 상태 악화 규칙 파싱
        deterioration_rules = [DeteriorationConfig(**rule) for rule in scenario_config.get("deterioration_rules", [])]

        # 종료 조건 파싱
        termination_conditions = [
            TerminationConfig(**condition) for condition in scenario_config.get("termination_conditions", [])
        ]

        # 검사 임계값 파싱
        lab_thresholds = [LabThreshold(**threshold) for threshold in scenario_config.get("lab_thresholds", [])]

        env_config = EnvironmentConfig(
            max_duration_minutes=scenario_config["max_duration_minutes"],
            time_step_minutes=scenario_config["time_step_minutes"],
            lab_result_delay_minutes=scenario_config["lab_result_delay_minutes"],
            imaging_result_delay_minutes=scenario_config["imaging_result_delay_minutes"],
            enable_state_deterioration=scenario_config["enable_state_deterioration"],
            medication_effects=medication_effects,
            deterioration_rules=deterioration_rules,
            termination_conditions=termination_conditions,
            lab_thresholds=lab_thresholds,
        )

        ground_truth = scenario_config["ground_truth"]
        if not ground_truth:
            raise ValueError("ground_truth is required - no mock simulation supported")

        return ClinicalEnvironment(initial_state=patient, config=env_config, ground_truth=ground_truth)

    def run_episode(
        self,
        agent: BaseAgent,
        environment: ClinicalEnvironment,
        scenario_id: str,
        guideline_graph_path: str,
        total_mandatory_count: int,
        violation_extractor_config: ViolationExtractorConfig,
        harm_scorer_config: HarmScorerConfig,
        scenario_forbidden_actions: list[str] | None = None,
        scenario_expected_actions: list[str] | None = None,
        patient_context_for_cde: dict | None = None,
    ) -> tuple:
        """단일 에피소드 실행 및 채점

        Args:
            agent: 실행할 에이전트
            environment: 임상 환경
            scenario_id: 시나리오 ID
            guideline_graph_path: 가이드라인 그래프 파일 경로
            total_mandatory_count: 필수 행동 수 (시나리오에서 명시적으로 제공)
            violation_extractor_config: ViolationExtractor 설정
            harm_scorer_config: HarmScorer 설정
            scenario_forbidden_actions: 시나리오 레벨 금기 행동 목록 (Optional)
            scenario_expected_actions: 시나리오 expected_actions 목록 — omission 체크 소스 (R2)
        """
        # H1 Fix: 실험 수준 예산 한도를 에이전트에 강제 적용
        if self.config.enforce_budget_matching:
            if self.config.budget_limit_tokens is not None:
                agent.config.budget_limit_tokens = self.config.budget_limit_tokens
            if self.config.budget_limit_tool_calls is not None:
                agent.config.budget_limit_tool_calls = self.config.budget_limit_tool_calls
            logger.info(
                f"Budget enforced: tokens={self.config.budget_limit_tokens}, "
                f"tool_calls={self.config.budget_limit_tool_calls}"
            )

        # 에피소드 실행
        episode_log = agent.run_episode(environment, scenario_id)

        # 예산 사용량 로깅 및 초과 검증
        if self.config.enforce_budget_matching:
            logger.info(
                f"Budget usage: tokens={agent.metrics.total_tokens}, tool_calls={agent.metrics.total_tool_calls}"
            )
            budget_violations = []
            if (
                self.config.budget_limit_tokens is not None
                and agent.metrics.total_tokens > self.config.budget_limit_tokens
            ):
                budget_violations.append(
                    f"Token budget exceeded: {agent.metrics.total_tokens} > {self.config.budget_limit_tokens}"
                )
            if (
                self.config.budget_limit_tool_calls is not None
                and agent.metrics.total_tool_calls > self.config.budget_limit_tool_calls
            ):
                budget_violations.append(
                    f"Tool call budget exceeded: {agent.metrics.total_tool_calls} > "
                    f"{self.config.budget_limit_tool_calls}"
                )
            if budget_violations:
                violation_msg = "; ".join(budget_violations)
                logger.error(f"BUDGET VIOLATION [{scenario_id}]: {violation_msg}")
                raise BudgetExceededError(violation_msg)

        # 가이드라인 엔진 로드
        engine = CPGEngineFactory.load_from_file(guideline_graph_path)

        # 시나리오 레벨 금기 행동 주입 (Issue 1 fix)
        if scenario_forbidden_actions:
            engine.set_scenario_forbidden_actions(scenario_forbidden_actions)

        # 위반 추출 - 설정은 외부에서 제공 (R2: scenario expected_actions 전달)
        extractor = ViolationExtractor(engine, violation_extractor_config)

        # B-cde-rescoring v1.1: derive CDE constraint set when feature is enabled
        derived_constraints = None
        if self.config.enable_cde_rescoring and patient_context_for_cde is not None:
            try:
                cde_engine = ConstraintDerivationEngine()
                graph_dict = load_cpg_graph(guideline_graph_path)
                derived_constraints = cde_engine.derive(
                    graph_dict, patient_context_for_cde, scenario_id=scenario_id
                )
            except Exception as exc:  # noqa: BLE001 — never block legacy scoring
                logger.warning(f"CDE derivation failed for scenario {scenario_id}: {exc}")
                derived_constraints = None

        violations = extractor.extract_violations(
            episode_log,
            scenario_expected_actions=scenario_expected_actions,
            derived_constraints=derived_constraints,
        )

        # 채점 - 설정은 외부에서 제공
        scorer = HarmScorer(total_mandatory_count=total_mandatory_count, config=harm_scorer_config)
        score = scorer.compute_score(violations, episode_log)

        return episode_log, score, violations

    def run_experiment(
        self, agent: BaseAgent, scenarios_config: dict[str, Any], guideline_graph_path: str
    ) -> list[ExperimentResult]:
        """전체 실험 실행"""
        results = []
        batch_data: list[dict[str, Any]] = []  # For batch-level pipeline

        for scenario_id, scenario_config in scenarios_config.get("scenarios", {}).items():
            if self.config.scenarios and scenario_id not in self.config.scenarios:
                continue

            logger.info(f"{'=' * 60}")
            logger.info(f"Running scenario: {scenario_id}")
            logger.info(f"{'=' * 60}")

            # 필수 설정 검증 (total_mandatory_count는 그래프에서 동적 계산 가능)
            required_configs = ["violation_extractor_config", "harm_scorer_config"]
            for field in required_configs:
                if field not in scenario_config:
                    raise ValueError(f"'{field}' is required in scenario '{scenario_id}'")

            # 설정 파싱
            violation_extractor_config = self._parse_violation_extractor_config(
                scenario_config["violation_extractor_config"]
            )
            harm_scorer_config = self._parse_harm_scorer_config(scenario_config["harm_scorer_config"])

            # H6 Fix: total_mandatory_count를 시나리오 설정에서 가져오거나 그래프에서 동적 계산
            total_mandatory_count = scenario_config.get("total_mandatory_count")
            if total_mandatory_count is None:
                total_mandatory_count = self._compute_mandatory_count_from_graph(guideline_graph_path)
                logger.info(f"Computed total_mandatory_count={total_mandatory_count} from graph")

            for run_num in range(self.config.num_runs_per_scenario):
                # 환자 및 환경 생성
                patient = self.create_patient_from_config(scenario_config["patient"])
                environment = self.create_environment(patient, scenario_config)

                # Inject CPG engine for dynamic state progression
                try:
                    cpg_engine_for_env = CPGEngineFactory.load_from_file(guideline_graph_path)
                    environment._cpg_engine = cpg_engine_for_env
                except Exception:
                    pass  # Environment will use hardcoded fallback

                # 시나리오 레벨 금기 행동 추출
                scenario_forbidden = scenario_config.get("forbidden_actions", [])

                # 에피소드 실행 및 채점
                episode_log, score, violations = self.run_episode(
                    agent,
                    environment,
                    scenario_id,
                    guideline_graph_path,
                    total_mandatory_count=total_mandatory_count,
                    violation_extractor_config=violation_extractor_config,
                    harm_scorer_config=harm_scorer_config,
                    scenario_forbidden_actions=scenario_forbidden,
                    patient_context_for_cde=scenario_config.get("patient")
                    if self.config.enable_cde_rescoring
                    else None,
                )

                # Per-episode pipeline (XES, LTL, LLM Judge)
                ep_pipeline_result = None
                if self._pipeline:
                    episode_id = f"{scenario_id}_run{run_num}"
                    raw_events = self._actions_to_raw_events(episode_log)
                    ep_pipeline_result = self._pipeline.process_episode(
                        episode_id=episode_id,
                        raw_events=raw_events,
                        score=score,
                        violations=violations,
                        patient_context=scenario_config.get("patient", {}).get("chief_complaint"),
                    )
                    # Collect for batch-level mining
                    batch_data.append(
                        {
                            "episode_id": episode_id,
                            "raw_events": raw_events,
                            "score": score,
                        }
                    )
                    logger.info(
                        f"Pipeline [{episode_id}]: "
                        f"xes={'OK' if ep_pipeline_result.xes_path else 'skip'}, "
                        f"ltl={ep_pipeline_result.ltl_satisfied}/{ep_pipeline_result.ltl_violated or 0}, "
                        f"judge={'applied' if ep_pipeline_result.llm_judge_applied else 'skip'}"
                    )

                result = ExperimentResult(
                    experiment_id=self.config.experiment_id,
                    scenario_id=scenario_id,
                    agent_id=agent.config.agent_id,
                    run_number=run_num,
                    episode_log=episode_log,
                    score=score,
                    timestamp=datetime.now().isoformat(),
                    pipeline_result=ep_pipeline_result,
                )

                results.append(result)

                # 결과 출력
                logger.info(f"Run {run_num + 1}:")
                logger.info(MetricsReporter.format_score_report(score))

        # Batch-level pipeline (pathway mining)
        batch_pipeline_result = None
        if self._pipeline and batch_data:
            batch_pipeline_result = self._pipeline.process_batch(batch_data)
            if batch_pipeline_result.total_pathways > 0:
                logger.info(
                    f"Batch pipeline: {batch_pipeline_result.total_pathways} pathways, "
                    f"{batch_pipeline_result.num_clusters} clusters, "
                    f"{len(batch_pipeline_result.significant_correlations)} significant correlations"
                )

        self.results.extend(results)
        self._last_batch_result = batch_pipeline_result
        return results

    def _parse_violation_extractor_config(self, config_dict: dict) -> ViolationExtractorConfig:
        """ViolationExtractorConfig 파싱"""
        harm_severity_mappings = [
            HarmSeverityMapping(action_pattern=m["action_pattern"], severity=HarmSeverity(m["severity"]))
            for m in config_dict.get("harm_severity_mappings", [])
        ]

        timing_severity_thresholds = [
            TimingSeverityThreshold(max_delay_minutes=t["max_delay_minutes"], severity=HarmSeverity(t["severity"]))
            for t in config_dict.get("timing_severity_thresholds", [])
        ]

        return ViolationExtractorConfig(
            harm_severity_mappings=harm_severity_mappings,
            timing_severity_thresholds=timing_severity_thresholds,
            default_deviation_severity=HarmSeverity(config_dict["default_deviation_severity"]),
            default_deviation_preventability=config_dict["default_deviation_preventability"],
        )

    def _parse_harm_scorer_config(self, config_dict: dict) -> HarmScorerConfig:
        """HarmScorerConfig 파싱"""
        severity_weights = {HarmSeverity(k): v for k, v in config_dict["severity_weights"].items()}

        guideline_strength_weights: dict[RecommendationClass | None, float] = {}
        for k, v in config_dict["guideline_strength_weights"].items():
            if k == "null" or k is None:
                guideline_strength_weights[None] = v
            else:
                guideline_strength_weights[RecommendationClass(k)] = v

        violation_type_weights = {ViolationType(k): v for k, v in config_dict["violation_type_weights"].items()}

        # Parse optional interaction config
        interaction_config = None
        if "interaction_config" in config_dict:
            interaction_config = self._parse_interaction_config(config_dict["interaction_config"])

        return HarmScorerConfig(
            severity_weights=severity_weights,
            guideline_strength_weights=guideline_strength_weights,
            violation_type_weights=violation_type_weights,
            interaction_config=interaction_config,
        )

    def _parse_interaction_config(self, config_dict: dict) -> InteractionConfig:
        """Parse InteractionConfig from YAML dict"""
        patterns = []
        for p in config_dict.get("interaction_patterns", []):
            patterns.append(
                InteractionPattern(
                    pattern_id=p["pattern_id"],
                    interaction_type=InteractionType(p["interaction_type"]),
                    violation_type_a=ViolationType(p["violation_type_a"]) if p.get("violation_type_a") else None,
                    violation_type_b=ViolationType(p["violation_type_b"]) if p.get("violation_type_b") else None,
                    action_pattern_a=p.get("action_pattern_a"),
                    action_pattern_b=p.get("action_pattern_b"),
                    temporal_window_minutes=p.get("temporal_window_minutes"),
                    require_same_phase=p.get("require_same_phase", False),
                    require_same_node=p.get("require_same_node", False),
                    causal_direction=p.get("causal_direction"),
                    multiplier=p.get("multiplier", 1.5),
                    max_multiplier=p.get("max_multiplier", 3.0),
                    escalated_severity=HarmSeverity(p["escalated_severity"]) if p.get("escalated_severity") else None,
                    clinical_rationale=p.get("clinical_rationale", ""),
                    source_guideline=p.get("source_guideline", ""),
                )
            )

        return InteractionConfig(
            interaction_patterns=patterns,
            enable_temporal_proximity=config_dict.get("enable_temporal_proximity", True),
            enable_causal_chain=config_dict.get("enable_causal_chain", True),
            enable_contraindication_compound=config_dict.get("enable_contraindication_compound", True),
            enable_phase_compounding=config_dict.get("enable_phase_compounding", True),
            enable_severity_escalation=config_dict.get("enable_severity_escalation", True),
            enable_triple_jeopardy=config_dict.get("enable_triple_jeopardy", True),
            triple_jeopardy_multiplier=config_dict.get("triple_jeopardy_multiplier", 2.0),
            max_group_size=config_dict.get("max_group_size", 3),
            phase_definitions=config_dict.get("phase_definitions", {}),
            default_temporal_window_minutes=config_dict.get("default_temporal_window_minutes", 15.0),
        )

    def _compute_mandatory_count_from_graph(self, guideline_graph_path: str) -> int:
        """CPG 그래프에서 전체 필수 행동 수를 동적으로 계산"""
        import yaml as _yaml

        # N5 Fix: 파일 I/O 및 YAML 파싱 에러 처리
        try:
            with open(guideline_graph_path, encoding="utf-8") as f:
                data = _yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Graph file not found: {guideline_graph_path}. Cannot compute mandatory count.")
            raise ValueError(f"Cannot compute mandatory count: file not found '{guideline_graph_path}'")
        except _yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML graph {guideline_graph_path}: {e}")
            raise ValueError(f"Cannot compute mandatory count: YAML parse error in '{guideline_graph_path}'") from e

        if not isinstance(data, dict):
            logger.error(f"Graph file is not a valid dict: {guideline_graph_path}")
            raise ValueError(f"Invalid graph format in '{guideline_graph_path}'")

        mandatory_actions: set = set()
        for node_id, node_data in data.get("nodes", {}).items():
            if isinstance(node_data, dict):
                for action in node_data.get("mandatory_actions", []):
                    mandatory_actions.add(action)

        count = len(mandatory_actions)
        if count == 0:
            logger.warning(
                f"No mandatory_actions found in graph {guideline_graph_path}. "
                f"Defaulting to 1 to avoid division by zero."
            )
            return 1
        return count

    def _actions_to_raw_events(self, episode_log: EpisodeLog) -> list[dict[str, Any]]:
        """Convert EpisodeLog actions to raw event dicts for pipeline.

        Produces the format expected by extract_activity_events:
        - 'activity': action_id uppercased (direct activity mapping)
        - 'timestamp_ms': timestamp in milliseconds
        """
        raw_events = []
        for action in episode_log.actions:
            raw_events.append(
                {
                    "activity": action.action_id.upper(),
                    "timestamp_ms": action.timestamp_minutes * 60000,
                    "action_type": action.type.value if hasattr(action.type, "value") else str(action.type),
                    "args": action.args or {},
                }
            )
        return raw_events

    def _parse_pipeline_config(self, config_dict: dict) -> PipelineConfig:
        """Parse PipelineConfig from YAML dict."""
        return PipelineConfig(
            enable_xes_export=config_dict.get("enable_xes_export", False),
            xes_output_dir=config_dict.get("xes_output_dir"),
            xes_enable_outcome=config_dict.get("xes_enable_outcome", True),
            xes_enable_violation_overlay=config_dict.get("xes_enable_violation_overlay", True),
            enable_ltl_verification=config_dict.get("enable_ltl_verification", False),
            ltl_properties_file=config_dict.get("ltl_properties_file"),
            enable_llm_judge=config_dict.get("enable_llm_judge", False),
            llm_judge_backend=config_dict.get("llm_judge_backend", "mock"),
            llm_judge_model=config_dict.get("llm_judge_model", "gpt-4"),
            llm_judge_api_key=config_dict.get("llm_judge_api_key"),
            enable_pathway_mining=config_dict.get("enable_pathway_mining", False),
            mining_ged_threshold=config_dict.get("mining_ged_threshold", 3.0),
            mining_min_cluster_size=config_dict.get("mining_min_cluster_size", 2),
        )

    def save_results(self, output_path: str | None = None):
        """결과 저장"""
        output_dir = Path(output_path or self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Capture environment snapshot for reproducibility
        try:
            from cga_bench.eval_harness.environment_snapshot import EnvironmentSnapshot

            env_snapshot = EnvironmentSnapshot.capture().to_dict()
        except Exception as e:
            logger.warning(f"Failed to capture environment snapshot: {e}")
            env_snapshot = {}

        # 요약 저장
        results_list: list[dict[str, Any]] = []
        summary: dict[str, Any] = {
            "experiment_id": self.config.experiment_id,
            "timestamp": datetime.now().isoformat(),
            "environment": env_snapshot,
            "config": {
                "random_seed": self.config.random_seed,
                "scenarios": self.config.scenarios,
                "agents": self.config.agents,
                "num_runs_per_scenario": self.config.num_runs_per_scenario,
                "budget_limit_tokens": self.config.budget_limit_tokens,
                "budget_limit_tool_calls": self.config.budget_limit_tool_calls,
            },
            "num_results": len(self.results),
            "results": results_list,
        }

        for result in self.results:
            entry: dict[str, Any] = {
                "scenario_id": result.scenario_id,
                "agent_id": result.agent_id,
                "run_number": result.run_number,
                "compliance_score": result.score.compliance_score,
                "peak_risk": result.score.peak_risk,
                "aggregate_risk": result.score.aggregate_risk,
                "total_violations": result.score.total_violations,
                "sub_scores": result.score.sub_scores,
            }
            if result.pipeline_result:
                pr = result.pipeline_result
                entry["pipeline"] = {
                    "xes_path": pr.xes_path,
                    "ltl_satisfied": pr.ltl_satisfied,
                    "ltl_violated": pr.ltl_violated,
                    "ltl_violations": pr.ltl_violations,
                    "llm_judge_applied": pr.llm_judge_applied,
                    "severity_changes": pr.severity_changes,
                }
            results_list.append(entry)

        # Batch pipeline results
        if hasattr(self, "_last_batch_result") and self._last_batch_result:
            br = self._last_batch_result
            summary["batch_pipeline"] = {
                "total_pathways": br.total_pathways,
                "num_clusters": br.num_clusters,
                "high_performing": br.high_performing,
                "low_performing": br.low_performing,
                "significant_correlations": br.significant_correlations,
            }

        summary_path = output_dir / f"{self.config.experiment_id}_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved to: {summary_path}")

    def generate_report(self) -> str:
        """실험 리포트 생성"""
        lines = [
            "=" * 80,
            "CGA-Bench Experiment Report",
            f"Experiment ID: {self.config.experiment_id}",
            "=" * 80,
            "",
            f"Total runs: {len(self.results)}",
            "",
            "--- Results by Scenario ---",
        ]

        # 시나리오별 집계
        scenario_scores: dict[str, list[float]] = {}
        for result in self.results:
            if result.scenario_id not in scenario_scores:
                scenario_scores[result.scenario_id] = []
            scenario_scores[result.scenario_id].append(result.score.compliance_score)

        for scenario_id, scores in scenario_scores.items():
            avg_score = sum(scores) / len(scores)
            lines.append(f"\n{scenario_id}:")
            lines.append(f"  Average Compliance: {avg_score:.2%}")
            lines.append(f"  Runs: {len(scores)}")

        lines.append("\n" + "=" * 80)

        return "\n".join(lines)
