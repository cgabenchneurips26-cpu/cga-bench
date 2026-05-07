"""CPG Engine: 가이드라인 실행 엔진
상태 입력 -> 허용/필수/금기/마감 반환
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING

from ..cpg_model.schemas.base import (
    Action,
    CPGGraph,
    CPGNode,
    GuidelineEngineOutput,
    PatientState,
)
from .node_types import BaseNode, DecisionNode, create_node

if TYPE_CHECKING:
    from ..assessor_core.action_normalizer import ActionNormalizer
    from ..cpg_model.schemas.contracts import ConstraintOutput

logger = logging.getLogger(__name__)

_VALID_EFFECT_TYPES = frozenset({"FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN"})


@dataclass
class GraphValidationResult:
    """Result of load-time graph structure validation."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    @property
    def total_checks(self) -> int:
        return len(self.errors) + len(self.warnings)


@dataclass
class AllergyDrugMapping:
    """알레르기-약물 금기 매핑 - 외부에서 주입"""

    allergy_pattern: str  # 알레르기 패턴 (예: "penicillin")
    forbidden_actions: list[str]  # 금기 행동 목록


@dataclass
class ComorbidityConstraint:
    """동반질환 제약 - 외부에서 주입"""

    comorbidity_pattern: str  # 동반질환 패턴 (예: "ckd", "heart_failure")
    forbidden_actions: list[str]  # 금기 행동 목록


@dataclass
class CPGEngineConfig:
    """CPGEngine 설정 - 모든 값은 외부에서 명시적으로 주입"""

    allergy_drug_mappings: list[AllergyDrugMapping] = field(default_factory=list)
    comorbidity_constraints: list[ComorbidityConstraint] = field(default_factory=list)
    strict_mode: bool = False


class CPGEngine:
    """가이드라인 실행 엔진

    핵심 인터페이스:
    G(s_t) -> (A_G, M_G, F_G, D_G)
    """

    def __init__(self, graph: CPGGraph, config: CPGEngineConfig | None = None):
        """Args:
        graph: CPG 그래프
        config: 엔진 설정 (알레르기-약물 매핑, 동반질환 제약 등)
        """
        self.graph = graph
        self.config = config or CPGEngineConfig()
        self.nodes: dict[str, BaseNode] = {}
        self._build_nodes()

        # Load-time structural validation (v1.1 hardening)
        self._validation_result = self._validate_graph_structure()
        if self._validation_result.warnings:
            for w in self._validation_result.warnings:
                logger.warning("Graph %s: %s", graph.graph_id, w)
        if not self._validation_result.ok and getattr(self.config, "strict_mode", False):
            raise ValueError(
                f"Graph '{graph.graph_id}' failed validation: " + "; ".join(self._validation_result.errors)
            )

        self.current_node_id = graph.entry_node
        # Pre-compute global allowed actions (union of all nodes' allowed + mandatory actions)
        self.global_allowed_actions: set[str] = self._compute_global_allowed_actions()
        # Pre-compute global forbidden actions (union of all nodes' forbidden actions)
        self.global_forbidden_actions: set[str] = self._compute_global_forbidden_actions()
        # Scenario-level forbidden actions injected externally
        self._scenario_forbidden_actions: set[str] = set()

    def _build_nodes(self):
        """그래프 정의로부터 노드 인스턴스 생성"""
        for node_id, node_def in self.graph.nodes.items():
            self.nodes[node_id] = create_node(node_def)

    def _validate_graph_structure(self) -> GraphValidationResult:
        """Load-time structural validation of the CPG graph.

        Checks (6 total):
        1. entry_node exists in nodes
        2. All next_nodes targets exist
        3. All conditional_next targets exist
        4. All deadline keys reference mandatory or allowed actions
        5. All conditional_rules have valid effect.type
        6. All conditional_rules have non-empty effect.actions
        """
        result = GraphValidationResult()
        node_ids = set(self.graph.nodes.keys())

        # Check 1: entry_node exists
        if self.graph.entry_node not in node_ids:
            result.errors.append(f"entry_node '{self.graph.entry_node}' not found in nodes")

        for nid, node_def in self.graph.nodes.items():
            # Check 2: next_nodes targets exist
            for target in getattr(node_def, "next_nodes", None) or []:
                if target not in node_ids:
                    result.errors.append(f"node '{nid}' next_nodes target '{target}' not found")

            # Check 3: conditional_next targets exist
            for cond, target in (getattr(node_def, "conditional_next", None) or {}).items():
                if target not in node_ids:
                    result.errors.append(
                        f"node '{nid}' conditional_next target '{target}' (condition='{cond}') not found"
                    )

            # Check 4: deadline keys reference mandatory or allowed actions
            mandatory = set(getattr(node_def, "mandatory_actions", None) or [])
            allowed = set(getattr(node_def, "allowed_actions", None) or [])
            known_actions = mandatory | allowed
            for action_key in getattr(node_def, "deadlines", None) or {}:
                if action_key not in known_actions:
                    result.warnings.append(
                        f"node '{nid}' deadline for '{action_key}' not in mandatory or allowed actions"
                    )

            # Checks 5 & 6: conditional_rules structure
            for rule in getattr(node_def, "conditional_rules", None) or []:
                effect = rule.effect if hasattr(rule, "effect") else rule.get("effect", {})
                if isinstance(effect, dict):
                    etype = effect.get("type", "")
                    eactions = effect.get("actions", [])
                else:
                    etype = getattr(effect, "type", "")
                    eactions = getattr(effect, "actions", [])

                if etype not in _VALID_EFFECT_TYPES:
                    result.errors.append(
                        f"node '{nid}' rule '{getattr(rule, 'rule_id', '?')}' invalid effect type '{etype}'"
                    )
                if not eactions:
                    result.errors.append(
                        f"node '{nid}' rule '{getattr(rule, 'rule_id', '?')}' has empty effect.actions"
                    )

        return result

    def _compute_global_allowed_actions(self) -> set[str]:
        """모든 노드의 allowed_actions + mandatory_actions를 집계

        이를 통해 가이드라인 전체에서 허용되는 모든 행동을 파악하여
        DEVIATION 위반을 더 정확하게 감지할 수 있음.
        """
        global_actions: set[str] = set()
        for node_def in self.graph.nodes.values():
            # allowed_actions 추가
            if hasattr(node_def, "allowed_actions") and node_def.allowed_actions:
                global_actions.update(node_def.allowed_actions)
            # mandatory_actions도 허용된 것으로 간주
            if hasattr(node_def, "mandatory_actions") and node_def.mandatory_actions:
                global_actions.update(node_def.mandatory_actions)
        return global_actions

    def _compute_global_forbidden_actions(self) -> set[str]:
        """모든 노드의 forbidden_actions를 집계

        노드-게이트 금기가 현재 노드가 아닐 때 누락되는 버그를 방지.
        Commission 체크 시 현재 노드의 forbidden + 전역 forbidden을 합쳐 검사.

        B3 fix: forbidden 행동 ID는 ActionNormalizer로 정규화하여 저장
        (수행 행동은 정규화되지만 graph YAML의 forbidden은 raw였던 비대칭 해소).
        """
        global_forbidden: set[str] = set()
        for node_def in self.graph.nodes.values():
            if hasattr(node_def, "forbidden_actions") and node_def.forbidden_actions:
                for raw in node_def.forbidden_actions:
                    global_forbidden.add(self._normalize_action_key(raw))
        return global_forbidden

    def set_scenario_forbidden_actions(self, forbidden_actions: list[str]) -> None:
        """시나리오 설정에서 정의된 금기 행동을 주입.

        Args:
            forbidden_actions: 시나리오 레벨 금기 행동 목록

        B3 fix: scenario YAML의 raw forbidden 문자열을 ActionNormalizer로 정규화.
        """
        self._scenario_forbidden_actions = {self._normalize_action_key(a) for a in forbidden_actions}

    def evaluate(self, state: PatientState) -> GuidelineEngineOutput:
        """현재 상태에서 가이드라인 제약 집합 반환

        Args:
            state: 현재 환자 상태

        Returns:
            GuidelineEngineOutput: 허용/필수/금기/마감 제약
        """
        # 현재 노드 가져오기
        current_node = self.nodes.get(self.current_node_id)
        if not current_node:
            raise ValueError(f"Unknown node: {self.current_node_id}")

        # DecisionNode인 경우, 상태 조건에 따라 자동 전환 후 평가
        # (A/B 테스트에서 forbidden_actions가 올바르게 적용되도록)
        if isinstance(current_node, DecisionNode):
            next_node_id = current_node.get_next_node(state)
            if next_node_id and next_node_id in self.nodes:
                # 다음 노드로 전환
                self.current_node_id = next_node_id
                next_node = self.nodes.get(next_node_id)
                if next_node is not None:
                    current_node = next_node

        # 노드 평가
        output = current_node.evaluate(state)

        # 환자 특이 조건에 따른 금기 추가 (contraindications, allergies)
        output = self._apply_patient_specific_constraints(state, output)

        return output

    def evaluate_constraints(self, state: PatientState) -> ConstraintOutput:
        output = self.evaluate(state)
        return output.to_constraint_output()

    def _apply_patient_specific_constraints(
        self, state: PatientState, output: GuidelineEngineOutput
    ) -> GuidelineEngineOutput:
        """환자 특이 조건에 따른 추가 제약 적용 - 설정에 정의된 매핑 사용"""
        additional_forbidden = set()

        # 알레르기에 따른 약물 금기 - 설정에서 매핑 가져오기
        for allergy in state.allergies:
            for mapping in self.config.allergy_drug_mappings:
                if mapping.allergy_pattern.lower() in allergy.lower():
                    additional_forbidden.update(mapping.forbidden_actions)

        # 동반질환에 따른 제약 - 설정에서 매핑 가져오기
        for comorbidity in state.comorbidities:
            for constraint in self.config.comorbidity_constraints:
                if constraint.comorbidity_pattern.lower() in comorbidity.lower():
                    additional_forbidden.update(constraint.forbidden_actions)

        # B3 fix: per-node + patient-specific forbidden을 모두 정규화하여 출력.
        # 노드 forbidden은 node_types.py의 node_def.forbidden_actions raw set이고,
        # additional_forbidden 또한 raw config 문자열이므로, 양쪽 모두 통과시켜야
        # downstream stepper.py:101 / violations.py 의 set-membership 체크가
        # 정규화된 performed action_key와 비대칭 없이 매칭된다.
        merged = output.forbidden_actions | additional_forbidden
        output.forbidden_actions = {self._normalize_action_key(a) for a in merged}
        return output

    def advance_node(self, state: PatientState, action: Action) -> str | None:
        """행동 수행 후 다음 노드로 이동

        Returns:
            새로운 노드 ID 또는 None (이동 없음)
        """
        current_node = self.nodes.get(self.current_node_id)
        if current_node is None:
            return None

        # Decision 노드인 경우 조건에 따라 분기
        if isinstance(current_node, DecisionNode):
            next_node_id = current_node.get_next_node(state)
            if next_node_id:
                self.current_node_id = next_node_id
                return next_node_id

        # 일반 노드: 필수 행동 완료시 다음으로
        node_def = current_node.node_def
        if self._mandatory_completed(state, node_def):
            if node_def.next_nodes:
                self.current_node_id = node_def.next_nodes[0]
                return self.current_node_id

        return None

    def _mandatory_completed(self, state: PatientState, node_def: CPGNode) -> bool:
        """필수 행동이 모두 완료되었는지 확인 (정규화 적용)"""
        completed_actions = set()

        # 수행된 검사
        for lab in state.lab_results:
            raw_key = f"order_lab_{lab.test_code}"
            completed_actions.add(self._normalize_action_key(raw_key))

        # 투여된 약물
        for med in state.medications_given:
            if "medication_code" not in med:
                raise ValueError("medication_code is required in medications_given entry")
            raw_key = f"give_{med['medication_code']}"
            completed_actions.add(self._normalize_action_key(raw_key))

        # 수행된 처치
        for proc in state.procedures_done:
            completed_actions.add(self._normalize_action_key(proc))

        # 필수 행동도 정규화하여 비교
        mandatory = set(self._normalize_action_key(a) for a in node_def.mandatory_actions)
        return mandatory.issubset(completed_actions)

    def _normalize_action_key(self, action_key: str) -> str:
        """ActionNormalizer를 사용하여 action key를 표준 형식으로 정규화"""
        if not hasattr(self, "_normalizer"):
            try:
                from ..assessor_core.action_normalizer import ActionNormalizer

                self._normalizer: ActionNormalizer | None = ActionNormalizer()
            except ImportError:
                self._normalizer = None

        if self._normalizer:
            graph_id = getattr(self.graph, "graph_id", None)
            cpg_id = self._resolve_cpg_id(graph_id)
            return self._normalizer.normalize(action_key, cpg_id=cpg_id)
        return action_key.lower().strip()

    # Graph ID → ActionNormalizer domain key mapping
    _GRAPH_ID_TO_DOMAIN = {
        "aha_stroke_2019": "aha_stroke",
        "aha_chest_pain_evaluation": "aha_chest_pain",
        "aha_heart_failure_2022": "aha_heart_failure",
    }

    def _resolve_cpg_id(self, graph_id: str | None) -> str | None:
        """graph_id를 ActionNormalizer의 domain-specific mapping key로 해석"""
        if not graph_id:
            return None
        # 1. Exact match in domain lookup
        if graph_id in self._GRAPH_ID_TO_DOMAIN:
            return self._GRAPH_ID_TO_DOMAIN[graph_id]
        # 2. Fallback: return graph_id as-is (ActionNormalizer will skip if not found)
        return graph_id

    def reset(self):
        """엔진을 초기 상태로 리셋"""
        self.current_node_id = self.graph.entry_node


class CPGEngineFactory:
    """가이드라인별 엔진 팩토리.

    Graph parsing is cached by resolved filepath to avoid redundant YAML/JSON
    I/O.  Each call still returns a fresh CPGEngine instance (no shared mutable
    state) but reuses the parsed CPGGraph object.
    """

    _graph_cache: dict[str, CPGGraph] = {}

    @classmethod
    def load_from_file(cls, filepath: str, config: CPGEngineConfig | None = None) -> CPGEngine:
        import os

        cache_key = os.path.realpath(filepath)

        if cache_key not in cls._graph_cache:
            import json

            import yaml

            with open(filepath, encoding="utf-8") as f:
                if filepath.endswith(".json"):
                    data = json.load(f)
                elif filepath.endswith(".yaml") or filepath.endswith(".yml"):
                    data = yaml.safe_load(f)
                else:
                    raise ValueError(f"Unsupported file format: {filepath}")

            if "nodes" in data:
                nodes_dict = {}
                for node_id, node_data in data["nodes"].items():
                    if isinstance(node_data, dict):
                        nodes_dict[node_id] = CPGNode(**node_data)
                    else:
                        nodes_dict[node_id] = node_data
                data["nodes"] = nodes_dict

            cls._graph_cache[cache_key] = CPGGraph(**data)

        return CPGEngine(cls._graph_cache[cache_key], config)

    @classmethod
    def clear_cache(cls) -> None:
        cls._graph_cache.clear()

    @staticmethod
    def load_from_dict(data: dict, config: CPGEngineConfig | None = None) -> CPGEngine:
        """딕셔너리에서 그래프 로드하여 새 엔진 인스턴스 생성

        Args:
            data: 그래프 정의 딕셔너리
            config: 엔진 설정 (선택)

        Returns:
            새로 생성된 CPGEngine 인스턴스
        """
        if "nodes" in data:
            nodes_dict = {}
            for node_id, node_data in data["nodes"].items():
                if isinstance(node_data, dict):
                    nodes_dict[node_id] = CPGNode(**node_data)
                else:
                    nodes_dict[node_id] = node_data
            data["nodes"] = nodes_dict

        graph = CPGGraph(**data)
        return CPGEngine(graph, config)
