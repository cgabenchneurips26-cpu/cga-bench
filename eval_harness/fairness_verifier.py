"""
Fairness Verifier: NeurIPS 비판 1 대응 - 평가 누수/치팅 방지

원칙: 어떤 에이전트도 채점용 CPG-Engine(그래프/노드/메타데이터)에 접근 불가
구현: assessor를 서버사이드로 분리하고, 에이전트 런타임은 tool API만 접근

이 모듈은 런타임에서 다음을 검증합니다:
1. 금지된 모듈 임포트 감지
2. 채점 엔진 접근 시도 감지
3. 에이전트 독립성 검증
"""

import sys
import importlib
import ast
import inspect
import builtins
from typing import Dict, Any, List, Set, Optional
from dataclasses import dataclass, field
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class IsolationConfig:
    """격리 설정"""
    # 접근 금지 모듈
    forbidden_imports: List[str] = field(default_factory=lambda: [
        "cga_bench.cpg_engine",
        "cga_bench.assessor_core",
        "cga_bench.cpg_model.graphs",
    ])

    # 허용된 모듈
    allowed_imports: List[str] = field(default_factory=lambda: [
        "cga_bench.agent_rules",
        "cga_bench.tool_api",
        "cga_bench.scenario_engine",
    ])

    # 런타임 검증 활성화
    enforce_at_runtime: bool = True

    # 위반 로깅
    log_violations: bool = True


@dataclass
class ViolationRecord:
    """위반 기록"""
    violation_type: str  # "import" | "access" | "method_call"
    module_name: str
    location: str  # 파일:라인
    agent_id: str
    timestamp: float
    details: Dict[str, Any] = field(default_factory=dict)


class ImportMonitor:
    """
    임포트 모니터

    금지된 모듈의 임포트를 감지합니다.
    """

    def __init__(self, config: IsolationConfig):
        self.config = config
        self.violations: List[ViolationRecord] = []
        self._original_import: Any = None
        self._is_active = False

    def start(self):
        """모니터링 시작"""
        if self._is_active:
            return

        self._original_import = builtins.__import__
        builtins.__import__ = self._monitored_import
        self._is_active = True
        logger.info("Import monitor started")

    def stop(self):
        """모니터링 중지"""
        if not self._is_active:
            return

        if self._original_import:
            builtins.__import__ = self._original_import
        self._is_active = False
        logger.info("Import monitor stopped")

    def _monitored_import(self, name, *args, **kwargs):
        """모니터링되는 임포트"""
        # 금지된 모듈 확인
        for forbidden in self.config.forbidden_imports:
            if name == forbidden or name.startswith(forbidden + "."):
                # 호출 위치 추적
                frame = inspect.currentframe()
                if frame and frame.f_back:
                    caller = frame.f_back
                    location = f"{caller.f_code.co_filename}:{caller.f_lineno}"
                else:
                    location = "unknown"

                violation = ViolationRecord(
                    violation_type="import",
                    module_name=name,
                    location=location,
                    agent_id="unknown",  # 나중에 설정
                    timestamp=0,  # 나중에 설정
                    details={"forbidden_pattern": forbidden}
                )
                self.violations.append(violation)

                if self.config.log_violations:
                    logger.warning(
                        f"[FAIRNESS VIOLATION] Attempted import of forbidden module: "
                        f"{name} at {location}"
                    )

                if self.config.enforce_at_runtime:
                    raise ImportError(
                        f"Import of '{name}' is forbidden. "
                        f"Agents cannot access scoring engine modules. "
                        f"Use 'cga_bench.agent_rules' instead."
                    )

        return self._original_import(name, *args, **kwargs)


class StaticAnalyzer:
    """
    정적 분석기

    에이전트 코드를 정적 분석하여 금지된 접근을 감지합니다.
    """

    def __init__(self, config: IsolationConfig):
        self.config = config
        self.violations: List[ViolationRecord] = []

    def analyze_file(self, file_path: Path) -> List[ViolationRecord]:
        """파일 분석"""
        violations = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            tree = ast.parse(source, filename=str(file_path))
            violations.extend(self._analyze_ast(tree, file_path))

        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")

        return violations

    def _analyze_ast(self, tree: ast.AST, file_path: Path) -> List[ViolationRecord]:
        """AST 분석"""
        violations = []

        for node in ast.walk(tree):
            # Import 문 분석
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if self._is_forbidden_import(alias.name):
                        violations.append(ViolationRecord(
                            violation_type="import",
                            module_name=alias.name,
                            location=f"{file_path}:{node.lineno}",
                            agent_id="static_analysis",
                            timestamp=0,
                            details={"import_type": "direct"}
                        ))

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if self._is_forbidden_import(module):
                    violations.append(ViolationRecord(
                        violation_type="import",
                        module_name=module,
                        location=f"{file_path}:{node.lineno}",
                        agent_id="static_analysis",
                        timestamp=0,
                        details={
                            "import_type": "from",
                            "names": [a.name for a in node.names]
                        }
                    ))

            # 속성 접근 분석 (cpg_engine.xxx 같은 패턴)
            elif isinstance(node, ast.Attribute):
                attr_chain = self._get_attribute_chain(node)
                if self._is_forbidden_access(attr_chain):
                    violations.append(ViolationRecord(
                        violation_type="access",
                        module_name=attr_chain,
                        location=f"{file_path}:{node.lineno}",
                        agent_id="static_analysis",
                        timestamp=0,
                        details={"access_type": "attribute"}
                    ))

        return violations

    def _is_forbidden_import(self, module_name: str) -> bool:
        """금지된 임포트인지 확인"""
        for forbidden in self.config.forbidden_imports:
            if module_name == forbidden or module_name.startswith(forbidden + "."):
                return True
        return False

    def _is_forbidden_access(self, attr_chain: str) -> bool:
        """금지된 접근인지 확인"""
        forbidden_patterns = [
            "cpg_engine",
            "assessor_core",
            "cpg_model.graphs",
        ]
        for pattern in forbidden_patterns:
            if pattern in attr_chain:
                return True
        return False

    def _get_attribute_chain(self, node: ast.Attribute) -> str:
        """속성 접근 체인 추출"""
        parts = []
        current = node

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value  # type: ignore[assignment]

        if isinstance(current, ast.Name):
            parts.append(current.id)

        return ".".join(reversed(parts))


class FairnessVerifier:
    """
    공정성 검증기

    NeurIPS 비판 1 대응을 위한 통합 검증 시스템
    """

    def __init__(self, config: Optional[IsolationConfig] = None):
        self.config = config or IsolationConfig()
        self.import_monitor = ImportMonitor(self.config)
        self.static_analyzer = StaticAnalyzer(self.config)
        self.violations: List[ViolationRecord] = []
        self._verified_agents: Set[str] = set()

    def start_monitoring(self):
        """런타임 모니터링 시작"""
        if self.config.enforce_at_runtime:
            self.import_monitor.start()

    def stop_monitoring(self):
        """런타임 모니터링 중지"""
        self.import_monitor.stop()
        self.violations.extend(self.import_monitor.violations)

    def verify_agent_module(self, module_path: Path) -> bool:
        """
        에이전트 모듈 검증

        Returns:
            True if module is clean, False if violations found
        """
        violations = self.static_analyzer.analyze_file(module_path)
        self.violations.extend(violations)

        if violations:
            logger.error(
                f"[FAIRNESS CHECK FAILED] Found {len(violations)} violations in {module_path}"
            )
            for v in violations:
                logger.error(f"  - {v.violation_type}: {v.module_name} at {v.location}")
            return False

        logger.info(f"[FAIRNESS CHECK PASSED] {module_path}")
        return True

    def verify_agent_independence(self, agent) -> Dict[str, Any]:
        """
        에이전트 독립성 검증

        에이전트가 채점 엔진에 접근하지 않는지 확인합니다.
        """
        result: Dict[str, Any] = {
            "agent_id": getattr(
                getattr(agent, 'config', None), 'agent_id',
                getattr(agent, 'agent_id', 'unknown')
            ),
            "is_independent": True,
            "violations": [],
            "verification_details": {},
        }

        # 1. get_independence_verification() 메서드 확인
        if hasattr(agent, 'get_independence_verification'):
            verification = agent.get_independence_verification()
            result["verification_details"] = verification

            # 채점 엔진 사용 여부 확인
            if verification.get("uses_cpg_engine", False):
                result["is_independent"] = False
                result["violations"].append("Agent declares use of cpg_engine")

            if verification.get("uses_assessor_core", False):
                result["is_independent"] = False
                result["violations"].append("Agent declares use of assessor_core")

        # 2. 실제 임포트 확인
        agent_module = inspect.getmodule(agent)
        if agent_module:
            module_file = getattr(agent_module, '__file__', None)
            if module_file:
                file_violations = self.static_analyzer.analyze_file(Path(module_file))
                if file_violations:
                    result["is_independent"] = False
                    result["violations"].extend([
                        f"{v.violation_type}: {v.module_name}"
                        for v in file_violations
                    ])

        # 3. 런타임 속성 확인
        forbidden_attrs = ['cpg_engine', 'assessor', '_cpg_graph', '_scoring_engine']
        for attr in forbidden_attrs:
            if hasattr(agent, attr) and getattr(agent, attr) is not None:
                result["is_independent"] = False
                result["violations"].append(f"Agent has forbidden attribute: {attr}")

        self._verified_agents.add(str(result["agent_id"]))

        if result["is_independent"]:
            logger.info(f"[INDEPENDENCE VERIFIED] Agent: {result['agent_id']}")
        else:
            logger.error(
                f"[INDEPENDENCE FAILED] Agent: {result['agent_id']} - "
                f"Violations: {result['violations']}"
            )

        return result

    def verify_experiment_fairness(
        self,
        agents: Dict[str, Any],
        experiment_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        전체 실험 공정성 검증
        """
        results = {
            "experiment_id": experiment_config.get("experiment", {}).get("experiment_id"),
            "is_fair": True,
            "agent_results": {},
            "budget_matched": True,
            "isolation_enforced": True,
        }

        # 1. 각 에이전트 독립성 검증
        for agent_name, agent in agents.items():
            agent_result = self.verify_agent_independence(agent)
            results["agent_results"][agent_name] = agent_result

            if not agent_result["is_independent"]:
                results["is_fair"] = False

        # 2. Budget 설정 일관성 확인
        budget_config = experiment_config.get("budget", {})
        if budget_config.get("enforce_budget_matching", True):
            token_limit = budget_config.get("budget_limit_tokens")
            call_limit = budget_config.get("budget_limit_calls")

            for agent_name, agent in agents.items():
                agent_config = getattr(agent, 'config', None)
                if agent_config:
                    agent_token_limit = getattr(agent_config, 'budget_limit_tokens', None)
                    agent_call_limit = getattr(agent_config, 'budget_limit_tool_calls', None)

                    if agent_token_limit and agent_token_limit != token_limit:
                        results["budget_matched"] = False
                        results["is_fair"] = False
                        logger.warning(
                            f"Budget mismatch for {agent_name}: "
                            f"tokens {agent_token_limit} vs {token_limit}"
                        )

        # 3. 격리 설정 확인
        isolation_config = experiment_config.get("isolation", {})
        if isolation_config.get("enforce_at_runtime", True):
            results["isolation_enforced"] = True
        else:
            results["isolation_enforced"] = False
            logger.warning("Runtime isolation is NOT enforced")

        return results

    def get_summary(self) -> Dict[str, Any]:
        """검증 요약"""
        return {
            "total_violations": len(self.violations),
            "violations_by_type": self._count_by_type(),
            "verified_agents": list(self._verified_agents),
            "runtime_monitoring_active": self.import_monitor._is_active,
        }

    def _count_by_type(self) -> Dict[str, int]:
        """위반 유형별 카운트"""
        counts: Dict[str, int] = {}
        for v in self.violations:
            counts[v.violation_type] = counts.get(v.violation_type, 0) + 1
        return counts


def verify_agent_source_files(agent_dir: Path, config: Optional[IsolationConfig] = None) -> bool:
    """
    에이전트 소스 파일들을 일괄 검증

    Args:
        agent_dir: 에이전트 소스 디렉토리
        config: 격리 설정

    Returns:
        True if all files pass, False otherwise
    """
    verifier = FairnessVerifier(config)
    all_passed = True

    for py_file in agent_dir.glob("**/*.py"):
        if not verifier.verify_agent_module(py_file):
            all_passed = False

    summary = verifier.get_summary()
    logger.info(f"Verification summary: {summary}")

    return all_passed
