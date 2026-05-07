"""Scenario Loader: YAML 시나리오 파일 로드 및 환경 생성

configs/scenarios/ 디렉토리의 시나리오 파일을 로드하여
ClinicalEnvironment를 생성할 수 있도록 합니다.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any

import yaml

from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns
from cga_bench.scenario_engine.environment import (
    ClinicalEnvironment,
    DeteriorationConfig,
    EnvironmentConfig,
    LabThreshold,
    MedicationEffectConfig,
    TerminationConfig,
)

logger = logging.getLogger(__name__)

# Alias map for short vitals keys used by some auto-generated scenario files.
# Canonical names match VitalSigns field names in cpg_model/schemas/base.py.
_VITALS_KEY_ALIASES: dict[str, str] = {
    "hr": "heart_rate",
    "sbp": "blood_pressure_systolic",
    "dbp": "blood_pressure_diastolic",
    "rr": "respiratory_rate",
    "spo2": "oxygen_saturation",
    "temp": "temperature",
}


def _normalize_vitals_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Translate short vitals key aliases to canonical VitalSigns field names."""
    normalized: dict[str, Any] = {}
    for k, v in raw.items():
        canonical = _VITALS_KEY_ALIASES.get(k)
        if canonical is not None:
            logger.warning(
                "Vitals key alias used: '%s' -> '%s' (value=%s). "
                "Consider updating the YAML to use canonical key names.",
                k,
                canonical,
                v,
            )
            # Canonical key from the raw dict takes precedence over alias
            if canonical not in raw:
                normalized[canonical] = v
        else:
            normalized[k] = v
    return normalized


@dataclass
class ScenarioDefinition:
    """시나리오 정의"""

    scenario_id: str
    description: str
    guideline_graph: str
    patient: PatientState
    ground_truth: dict[str, Any]
    expected_actions: list[str]
    forbidden_actions: list[str]
    optional_actions: list[str]
    max_duration_minutes: int
    passing_compliance_threshold: float
    trap_scenario: bool = False
    trap_description: str | None = None
    special_considerations: list[str] | None = None
    environment_config: dict[str, Any] = None

    def __post_init__(self):
        if self.environment_config is None:
            self.environment_config = {}


class ScenarioLoader:
    """시나리오 로더"""

    def __init__(
        self,
        scenarios_dir: str | None = None,
        include_auto_v2: bool | None = None,
        exclude_auto: bool | None = None,
        include_sgsc: bool | None = None,
    ):
        """Args:
        scenarios_dir: 시나리오 파일 디렉토리 경로.
        include_auto_v2: include configs/scenarios/auto_v2/*.yaml (clinical-axes set).
            None (default) reads CGA_BENCH_INCLUDE_AUTO_V2 env var (truthy → include).
            False explicitly disables. Off by default to preserve 942-scenario
            reproducibility of pre-2026-04-25 runs.
        exclude_auto: if True, skip configs/scenarios/auto/*.yaml (236 pilot scenarios).
            None (default) reads CGA_BENCH_EXCLUDE_AUTO env var (truthy → exclude).
            Combined: exclude_auto=True with include_auto_v2=False yields the pure
            706 v5 manual set. exclude_auto=True with include_auto_v2=True yields
            706 + 4720 = 5426 (no pilot CPGs). Default False = legacy behaviour.
        include_sgsc: include configs/scenarios/sgsc/*.yaml (SGSC v7.3 scenarios).
            None (default) reads CGA_BENCH_INCLUDE_SGSC env var (truthy → include).
            Off by default to preserve existing run reproducibility.
        """
        import os

        if scenarios_dir:
            self.scenarios_dir = Path(scenarios_dir)
        else:
            self.scenarios_dir = Path(__file__).parent.parent / "configs" / "scenarios"

        if include_auto_v2 is None:
            env_val = os.environ.get("CGA_BENCH_INCLUDE_AUTO_V2", "").lower()
            include_auto_v2 = env_val in {"1", "true", "yes", "on"}
        if exclude_auto is None:
            env_val = os.environ.get("CGA_BENCH_EXCLUDE_AUTO", "").lower()
            exclude_auto = env_val in {"1", "true", "yes", "on"}
        if include_sgsc is None:
            env_val = os.environ.get("CGA_BENCH_INCLUDE_SGSC", "").lower()
            include_sgsc = env_val in {"1", "true", "yes", "on"}
        self.include_auto_v2 = include_auto_v2
        self.exclude_auto = exclude_auto
        self.include_sgsc = include_sgsc
        self._scenarios_cache: dict[str, ScenarioDefinition] = {}
        self._loaded_files: set = set()

    def _load_yaml_file(self, file_path: Path) -> dict[str, Any]:
        """YAML 파일 로드"""
        with open(file_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_all_scenarios(self) -> dict[str, ScenarioDefinition]:
        """모든 시나리오 파일 로드 (auto/ 서브디렉토리 포함; auto_v2/, sgsc/ optional)"""
        scenario_files = list(self.scenarios_dir.glob("*_scenarios.yaml"))
        if not self.exclude_auto:
            scenario_files.extend(self.scenarios_dir.glob("auto/*_scenarios.yaml"))
        if self.include_auto_v2:
            scenario_files.extend(self.scenarios_dir.glob("auto_v2/*_scenarios.yaml"))
        if self.include_sgsc:
            scenario_files.extend(self.scenarios_dir.glob("sgsc/*_scenarios.yaml"))

        for file_path in scenario_files:
            file_key = str(file_path.relative_to(self.scenarios_dir))
            if file_key not in self._loaded_files:
                self._load_scenarios_from_file(file_path)
                self._loaded_files.add(file_key)

        return self._scenarios_cache

    def _load_scenarios_from_file(self, file_path: Path):
        """단일 시나리오 파일에서 시나리오들 로드"""
        data = self._load_yaml_file(file_path)

        scenarios_data = data.get("scenarios", {})
        defaults = data.get("defaults", {})

        for scenario_id, scenario_config in scenarios_data.items():
            scenario_def = self._parse_scenario(scenario_id, scenario_config, defaults)
            self._scenarios_cache[scenario_id] = scenario_def

    def _parse_scenario(self, scenario_id: str, config: dict[str, Any], defaults: dict[str, Any]) -> ScenarioDefinition:
        """시나리오 설정 파싱"""
        # 환자 상태 생성
        patient_config = config.get("patient", {})
        vitals_config = _normalize_vitals_keys(patient_config.get("vitals", {}))

        vitals = VitalSigns(
            heart_rate=vitals_config.get("heart_rate", 80),
            blood_pressure_systolic=vitals_config.get("blood_pressure_systolic", 120),
            blood_pressure_diastolic=vitals_config.get("blood_pressure_diastolic", 80),
            respiratory_rate=vitals_config.get("respiratory_rate", 16),
            temperature=vitals_config.get("temperature", 37.0),
            oxygen_saturation=vitals_config.get("oxygen_saturation", 98),
            map_mmhg=vitals_config.get("map_mmhg"),
        )

        # Sanitize fields that may have wrong types in YAML
        raw_age = patient_config.get("age", 50)
        raw_contraindications = patient_config.get("contraindications", [])
        if isinstance(raw_contraindications, str):
            raw_contraindications = [raw_contraindications]

        patient = PatientState(
            state_id=f"patient_{scenario_id}",
            age=int(raw_age),
            sex=patient_config.get("sex", "M"),
            weight_kg=patient_config.get("weight_kg"),
            vitals=vitals,
            chief_complaint=patient_config.get("chief_complaint", ""),
            working_diagnosis=patient_config.get("working_diagnosis"),
            allergies=patient_config.get("allergies", []),
            comorbidities=patient_config.get("comorbidities", []),
            contraindications=raw_contraindications,
        )

        # 환경 설정 캡처 (동적 효과 포함)
        environment_config = {
            "medication_effects": config.get("medication_effects", []),
            "deterioration_rules": config.get("deterioration_rules", []),
            "termination_conditions": config.get("termination_conditions", []),
            "lab_thresholds": config.get("lab_thresholds", []),
            "time_step_minutes": config.get("time_step_minutes", defaults.get("time_step_minutes", 5)),
            "lab_result_delay_minutes": config.get(
                "lab_result_delay_minutes", defaults.get("lab_result_delay_minutes", 30)
            ),
            "imaging_result_delay_minutes": config.get(
                "imaging_result_delay_minutes", defaults.get("imaging_result_delay_minutes", 15)
            ),
            "enable_state_deterioration": config.get(
                "enable_state_deterioration", defaults.get("enable_state_deterioration", True)
            ),
        }

        ground_truth = config.get("ground_truth", {}) or {}
        return ScenarioDefinition(
            scenario_id=scenario_id,
            description=config.get("description", ""),
            guideline_graph=config.get("guideline_graph", ""),
            patient=patient,
            ground_truth=ground_truth,
            expected_actions=(config.get("expected_actions") or ground_truth.get("expected_actions", [])),
            forbidden_actions=(config.get("forbidden_actions") or ground_truth.get("forbidden_actions", [])),
            optional_actions=config.get("optional_actions", []),
            max_duration_minutes=config.get("max_duration_minutes", defaults.get("max_duration_minutes", 120)),
            passing_compliance_threshold=config.get("passing_compliance_threshold", 0.8),
            trap_scenario=config.get("trap_scenario", False),
            trap_description=config.get("trap_description"),
            special_considerations=config.get("special_considerations", []),
            environment_config=environment_config,
        )

    def get_scenario(self, scenario_id: str) -> ScenarioDefinition | None:
        """특정 시나리오 가져오기"""
        if not self._scenarios_cache:
            self.load_all_scenarios()

        return self._scenarios_cache.get(scenario_id)

    def list_scenarios(self) -> list[str]:
        """사용 가능한 시나리오 목록"""
        if not self._scenarios_cache:
            self.load_all_scenarios()

        return list(self._scenarios_cache.keys())

    def list_trap_scenarios(self) -> list[str]:
        """트랩 시나리오 목록"""
        if not self._scenarios_cache:
            self.load_all_scenarios()

        return [sid for sid, s in self._scenarios_cache.items() if s.trap_scenario]

    def create_environment(
        self, scenario_id: str, env_config_overrides: dict[str, Any] | None = None
    ) -> ClinicalEnvironment:
        """시나리오에서 환경 생성 (동적 효과 포함)"""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise ValueError(f"Scenario not found: {scenario_id}")

        # 환경 설정 (시나리오 environment_config 포함)
        defaults = {
            "time_step_minutes": 5,
            "lab_result_delay_minutes": 30,
            "imaging_result_delay_minutes": 15,
            "enable_state_deterioration": True,
        }

        # 시나리오에서 파싱된 환경 설정 머지 (동적 효과 포함)
        defaults.update(scenario.environment_config)

        if env_config_overrides:
            defaults.update(env_config_overrides)

        # 동적 효과 파싱 (시나리오 ground_truth에서 가져옴)
        medication_effects = [MedicationEffectConfig(**effect) for effect in defaults.get("medication_effects", [])]
        deterioration_rules = [DeteriorationConfig(**rule) for rule in defaults.get("deterioration_rules", [])]
        termination_conditions = [TerminationConfig(**cond) for cond in defaults.get("termination_conditions", [])]
        lab_thresholds = [LabThreshold(**threshold) for threshold in defaults.get("lab_thresholds", [])]

        env_config = EnvironmentConfig(
            max_duration_minutes=scenario.max_duration_minutes,
            time_step_minutes=defaults["time_step_minutes"],
            lab_result_delay_minutes=defaults["lab_result_delay_minutes"],
            imaging_result_delay_minutes=defaults["imaging_result_delay_minutes"],
            enable_state_deterioration=bool(defaults["enable_state_deterioration"]),
            medication_effects=medication_effects,
            deterioration_rules=deterioration_rules,
            termination_conditions=termination_conditions,
            lab_thresholds=lab_thresholds,
        )

        # Load CPG engine for dynamic state progression (Option B)
        cpg_engine = None
        try:
            graph_path = self.get_cpg_graph_path(scenario_id)
            if graph_path and graph_path.exists():
                from cga_bench.cpg_engine.engine import CPGEngineFactory

                cpg_engine = CPGEngineFactory.load_from_file(str(graph_path))
        except Exception:
            pass  # Fall back to hardcoded actions in environment

        return ClinicalEnvironment(
            initial_state=scenario.patient,
            config=env_config,
            ground_truth=scenario.ground_truth,
            cpg_engine=cpg_engine,
        )

    def get_cpg_graph_path(self, scenario_id: str) -> Path | None:
        """시나리오에 해당하는 CPG 그래프 파일 경로 반환"""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            return None

        graph_name = scenario.guideline_graph
        graphs_dir = Path(__file__).parent.parent / "cpg_model" / "graphs"

        # 그래프 이름 매핑 (모든 지원 가이드라인 포함)
        graph_map = {
            # SSC Sepsis (canonical: ssc_sepsis_hour1_bundle)
            "ssc_sepsis_hour1_bundle": "ssc_sepsis_hour1_bundle.yaml",
            "ssc_sepsis_hour1": "ssc_sepsis_hour1_bundle.yaml",
            "ssc_sepsis": "ssc_sepsis_hour1_bundle.yaml",
            "sepsis": "ssc_sepsis_hour1_bundle.yaml",
            # AHA Chest Pain (canonical: aha_chest_pain_evaluation)
            "aha_chest_pain_evaluation": "aha_chest_pain_evaluation.yaml",
            "aha_chest_pain": "aha_chest_pain_evaluation.yaml",
            "aha_chest_pain_stemi": "aha_chest_pain_evaluation.yaml",
            "aha_chest_pain_nstemi": "aha_chest_pain_evaluation.yaml",
            # AHA Stroke (canonical: aha_stroke_2019)
            "aha_stroke_2019": "aha_stroke_2019.yaml",
            "aha_stroke": "aha_stroke_2019.yaml",
            "aha_stroke_ischemic": "aha_stroke_2019.yaml",
            "aha_stroke_hemorrhagic": "aha_stroke_2019.yaml",
            # AHA Heart Failure (canonical: aha_heart_failure_2022)
            "aha_heart_failure_2022": "aha_heart_failure_2022.yaml",
            "aha_heart_failure": "aha_heart_failure_2022.yaml",
            "aha_heart_failure_hfref": "aha_heart_failure_2022.yaml",
            "aha_heart_failure_adhf": "aha_heart_failure_2022.yaml",
            # KDIGO AKI
            "kdigo_contrast_aki": "kdigo_contrast_aki.yaml",
            "kdigo_aki": "kdigo_contrast_aki.yaml",
            # ADA DKA
            "ada_dka_management": "ada_dka_management.yaml",
            "ada_dka": "ada_dka_management.yaml",
            "dka": "ada_dka_management.yaml",
        }

        graph_file = graph_map.get(graph_name)
        if graph_file:
            return graphs_dir / graph_file

        # 직접 파일 검색 (core + auto 디렉토리)
        for yaml_file in graphs_dir.glob("*.yaml"):
            if graph_name in yaml_file.stem:
                return yaml_file

        auto_dir = graphs_dir / "auto"
        if auto_dir.exists():
            for yaml_file in auto_dir.glob("*.yaml"):
                if graph_name in yaml_file.stem:
                    return yaml_file

        return None


class ExperimentLoader:
    """실험 설정 로더"""

    def __init__(self, experiments_dir: str | None = None):
        if experiments_dir:
            self.experiments_dir = Path(experiments_dir)
        else:
            self.experiments_dir = Path(__file__).parent.parent / "configs" / "experiments"

    def load_experiment(self, experiment_name: str) -> dict[str, Any]:
        """실험 설정 로드"""
        file_path = self.experiments_dir / f"{experiment_name}.yaml"
        if not file_path.exists():
            raise FileNotFoundError(f"Experiment config not found: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def list_experiments(self) -> list[str]:
        """사용 가능한 실험 목록"""
        return [f.stem for f in self.experiments_dir.glob("*.yaml")]


class AgentConfigLoader:
    """에이전트 설정 로더"""

    def __init__(self, agents_dir: str | None = None):
        if agents_dir:
            self.agents_dir = Path(agents_dir)
        else:
            self.agents_dir = Path(__file__).parent.parent / "configs" / "agents"

    def load_agent_config(self, agent_name: str) -> dict[str, Any]:
        """에이전트 설정 로드"""
        file_path = self.agents_dir / f"{agent_name}.yaml"
        if not file_path.exists():
            raise FileNotFoundError(f"Agent config not found: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def list_agents(self) -> list[str]:
        """사용 가능한 에이전트 목록"""
        return [f.stem for f in self.agents_dir.glob("*.yaml")]
