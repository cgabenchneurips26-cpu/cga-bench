"""
Tool API Base: 에이전트 도구 인터페이스 기본 클래스
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from cga_bench.cpg_model.schemas.base import Action, ActionType, PatientState


@dataclass
class ToolResult:
    """도구 실행 결과"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BaseTool(ABC):
    """도구 기본 클래스"""

    @property
    @abstractmethod
    def name(self) -> str:
        """도구 이름"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """도구 설명"""
        pass

    @property
    @abstractmethod
    def action_type(self) -> ActionType:
        """대응하는 행동 타입"""
        pass

    @abstractmethod
    def execute(self, args: Dict[str, Any], state: PatientState) -> ToolResult:
        """도구 실행"""
        pass

    def validate_args(self, args: Dict[str, Any]) -> bool:
        """인자 검증"""
        return True

    def to_action(self, args: Dict[str, Any], timestamp: float, action_id: str) -> Action:
        """도구 호출을 Action으로 변환"""
        return Action(
            type=self.action_type,
            action_id=action_id,
            args=args,
            timestamp_minutes=timestamp,
            justification=None
        )


class LabTool(BaseTool):
    """검사 오더 도구"""

    @property
    def name(self) -> str:
        return "order_lab"

    @property
    def description(self) -> str:
        return "Order laboratory tests (e.g., lactate, blood culture, CBC)"

    @property
    def action_type(self) -> ActionType:
        return ActionType.ORDER_LAB

    def execute(self, args: Dict[str, Any], state: PatientState) -> ToolResult:
        test_code = args.get("test_code", "")
        if not test_code:
            return ToolResult(
                success=False,
                message="Test code is required",
                error="Missing test_code"
            )

        return ToolResult(
            success=True,
            message=f"Lab test {test_code} ordered successfully",
            data={"test_code": test_code, "status": "ordered"}
        )


class ImagingTool(BaseTool):
    """영상 검사 도구"""

    @property
    def name(self) -> str:
        return "order_imaging"

    @property
    def description(self) -> str:
        return "Order imaging studies (e.g., chest X-ray, CT)"

    @property
    def action_type(self) -> ActionType:
        return ActionType.ORDER_IMAGING

    def execute(self, args: Dict[str, Any], state: PatientState) -> ToolResult:
        imaging_type = args.get("imaging_type", "")
        if not imaging_type:
            return ToolResult(
                success=False,
                message="Imaging type is required",
                error="Missing imaging_type"
            )

        return ToolResult(
            success=True,
            message=f"Imaging {imaging_type} ordered successfully",
            data={"imaging_type": imaging_type, "status": "ordered"}
        )


class MedicationTool(BaseTool):
    """약물 투여 도구"""

    @property
    def name(self) -> str:
        return "give_medication"

    @property
    def description(self) -> str:
        return "Administer medication (e.g., antibiotics, vasopressors, fluids)"

    @property
    def action_type(self) -> ActionType:
        return ActionType.GIVE_MEDICATION

    def execute(self, args: Dict[str, Any], state: PatientState) -> ToolResult:
        medication_code = args.get("medication_code", "")
        dose = args.get("dose")

        if not medication_code:
            return ToolResult(
                success=False,
                message="Medication code is required",
                error="Missing medication_code"
            )

        if not dose:
            return ToolResult(
                success=False,
                message="Dose is required - no default value",
                error="Missing dose"
            )

        # 알레르기 체크
        for allergy in state.allergies:
            if allergy.lower() in medication_code.lower():
                return ToolResult(
                    success=False,
                    message=f"Medication {medication_code} contraindicated due to allergy: {allergy}",
                    error="Allergy contraindication"
                )

        return ToolResult(
            success=True,
            message=f"Medication {medication_code} administered at dose {dose}",
            data={"medication_code": medication_code, "dose": dose, "status": "administered"}
        )


class DispositionTool(BaseTool):
    """배치 결정 도구"""

    def __init__(self, valid_dispositions: List[str]):
        """
        Args:
            valid_dispositions: 유효한 disposition 목록 (외부에서 명시적으로 주입)
        """
        if not valid_dispositions:
            raise ValueError("valid_dispositions is required - no default values")
        self._valid_dispositions = valid_dispositions

    @property
    def name(self) -> str:
        return "disposition"

    @property
    def description(self) -> str:
        return "Determine patient disposition (admit to ICU, ward, or discharge)"

    @property
    def action_type(self) -> ActionType:
        return ActionType.DISPOSITION

    def execute(self, args: Dict[str, Any], state: PatientState) -> ToolResult:
        disposition = args.get("disposition", "")

        if disposition not in self._valid_dispositions:
            return ToolResult(
                success=False,
                message=f"Invalid disposition. Must be one of: {self._valid_dispositions}",
                error="Invalid disposition"
            )

        return ToolResult(
            success=True,
            message=f"Patient disposition set to: {disposition}",
            data={"disposition": disposition, "status": "decided"}
        )


class ToolRegistry:
    """도구 레지스트리"""

    def __init__(self, valid_dispositions: Optional[List[str]] = None):
        """
        Args:
            valid_dispositions: DispositionTool에 사용할 유효한 disposition 목록
                               None이면 기본 도구만 등록 (DispositionTool 제외)
        """
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools(valid_dispositions)

    def _register_default_tools(self, valid_dispositions: Optional[List[str]] = None):
        """기본 도구 등록"""
        self.register(LabTool())
        self.register(ImagingTool())
        self.register(MedicationTool())
        if valid_dispositions:
            self.register(DispositionTool(valid_dispositions))

    def register(self, tool: BaseTool):
        """도구 등록"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """도구 가져오기"""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """등록된 도구 목록"""
        return list(self._tools.keys())

    def get_tool_descriptions(self) -> List[Dict[str, str]]:
        """도구 설명 목록"""
        return [
            {"name": tool.name, "description": tool.description}
            for tool in self._tools.values()
        ]
