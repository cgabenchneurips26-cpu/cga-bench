"""
MedChain Adapter
Sequential Clinical Decision Workflow (5 stages) to EpisodeNorm conversion

MedChain 5 Stages:
1. Specialty Referral (分诊/Triage) - 科室 selection
2. History-taking (问诊) - 主诉, 现病史, 既往史
3. Examination (检查) - 体格检查 + 辅助检查
4. Diagnosis (诊断) - 诊断结果
5. Treatment (治疗) - 治疗方案

Episode Structure:
- episode = 1 clinical case
- event = action at each stage (ASK_HISTORY, ORDER_EXAM, DIAGNOSE, TREAT)
- state = patient profile/symptoms/findings/diagnosis/treatment plan snapshots
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum
import logging
import json
import re

from cga_bench.env.adapters.base_adapter import (
    BaseAdapter,
    AdaptedEpisode,
    AdaptedAction,
)
from cga_bench.env.core.state import (
    PatientState2,
    VitalSigns2,
    LabResult2,
    ImagingResult,
)
from cga_bench.env.core.actions import (
    Action2,
    ActionType2,
    ActionStatus,
)

logger = logging.getLogger(__name__)


class MedChainStage(Enum):
    """MedChain 5-stage workflow"""
    REFERRAL = "referral"           # Stage 1: Specialty Referral (分诊)
    HISTORY_TAKING = "history"      # Stage 2: History-taking (问诊)
    EXAMINATION = "examination"     # Stage 3: Examination (检查)
    DIAGNOSIS = "diagnosis"         # Stage 4: Diagnosis (诊断)
    TREATMENT = "treatment"         # Stage 5: Treatment (治疗)


@dataclass
class MedChainStageState:
    """State snapshot at each MedChain stage"""
    stage: MedChainStage
    timestamp: int = 0  # Stage index (0-4)

    # Stage-specific data
    department_primary: Optional[str] = None      # 一级科室
    department_secondary: Optional[str] = None    # 二级科室
    chief_complaint: Optional[str] = None         # 主诉
    present_illness: Optional[str] = None         # 现病史
    past_history: Optional[str] = None            # 既往史
    physical_exam: Dict[str, str] = field(default_factory=dict)    # 体格检查
    auxiliary_exam: Dict[str, str] = field(default_factory=dict)   # 辅助检查
    diagnosis: Optional[str] = None               # 诊断结果
    differential_diagnosis: List[str] = field(default_factory=list)  # 鉴别诊断
    treatment_plan: Optional[str] = None          # 治疗方案
    treatment_result: Optional[str] = None        # 治疗结果


@dataclass
class MedChainEpisode:
    """MedChain episode with stage-by-stage tracking"""
    case_id: str
    stages: List[MedChainStageState] = field(default_factory=list)
    ground_truth: Dict[str, Any] = field(default_factory=dict)

    # Compliance tracking
    stage_completion: Dict[MedChainStage, bool] = field(default_factory=dict)
    stage_errors: Dict[MedChainStage, List[str]] = field(default_factory=dict)
    error_propagation: List[Tuple[MedChainStage, MedChainStage, str]] = field(default_factory=list)


class MedChainAdapter(BaseAdapter):
    """
    MedChain Adapter for Sequential Clinical Decision Workflow

    Converts MedChain 5-stage cases to CGA-Bench EpisodeNorm format.
    Tracks:
    - Stage completion (OMISSION detection)
    - Stage order (SEQUENCE violation)
    - Error propagation (misdiagnosis → wrong treatment)
    """

    # Physical examination categories (Chinese)
    PHYSICAL_EXAM_CATEGORIES = [
        "一般检查", "头颅眼耳鼻喉检查", "颈部检查", "胸部检查",
        "腹部检查", "脊柱和四肢检查", "皮肤检查", "神经系统检查", "泌尿生殖系统检查"
    ]

    # Auxiliary examination categories
    AUXILIARY_EXAM_CATEGORIES = [
        "X-ray", "MRI", "CT", "超声", "核医学成像",
        "血液学检查", "尿液检查", "粪便检查", "内镜检查", "病理检查", "X线片"
    ]

    # Treatment categories
    TREATMENT_CATEGORIES = [
        "手术", "介入治疗", "药物治疗", "化学治疗", "抗生素治疗",
        "放射治疗", "物理疗法", "免疫疗法", "心理治疗", "中医治疗", "基因治疗"
    ]

    # Department to CPG guideline mapping
    DEPARTMENT_GUIDELINE_MAPPING = {
        "内科": "cpg/runtime_dsl/medchain/internal_medicine.yaml",
        "外科": "cpg/runtime_dsl/medchain/surgery.yaml",
        "儿科": "cpg/runtime_dsl/medchain/pediatrics.yaml",
        "妇产科": "cpg/runtime_dsl/medchain/obstetrics_gynecology.yaml",
        "急诊科": "cpg/runtime_dsl/medchain/emergency.yaml",
        "肿瘤科": "cpg/runtime_dsl/medchain/oncology.yaml",
        "神经科": "cpg/runtime_dsl/medchain/neurology.yaml",
        "心血管内科": "cpg/runtime_dsl/medchain/cardiology.yaml",
        "呼吸内科": "cpg/runtime_dsl/medchain/pulmonology.yaml",
        "消化内科": "cpg/runtime_dsl/medchain/gastroenterology.yaml",
        "皮肤性病科": "cpg/runtime_dsl/medchain/dermatology.yaml",
        "精神科": "cpg/runtime_dsl/medchain/psychiatry.yaml",
        "骨科": "cpg/runtime_dsl/medchain/orthopedics.yaml",
        "眼科": "cpg/runtime_dsl/medchain/ophthalmology.yaml",
        "耳鼻咽喉科": "cpg/runtime_dsl/medchain/ent.yaml",
    }

    def __init__(self):
        super().__init__("MedChain")
        self.data_path: Optional[Path] = None
        self.cases: Dict[str, Dict] = {}

    def load_data(self, data_path: Path) -> int:
        """Load MedChain dataset from JSON file"""
        self.data_path = Path(data_path)

        with open(self.data_path, 'r', encoding='utf-8') as f:
            self.cases = json.load(f)

        logger.info(f"Loaded {len(self.cases)} MedChain cases")
        return len(self.cases)

    def parse_case(self, case_id: str, case_data: Dict) -> MedChainEpisode:
        """
        Parse a MedChain case into structured episode format

        Args:
            case_id: Case identifier
            case_data: Raw case data with tags, 病例摘要, 病案介绍, 诊治过程
        """
        episode = MedChainEpisode(case_id=case_id)

        # Extract tags (ground truth)
        tags = case_data.get('tags', {})
        episode.ground_truth = {
            'department': tags.get('科室', []),
            'disease': tags.get('病种', []),
        }

        # Parse case summary (病例摘要)
        summary = case_data.get('【病例摘要】', [])
        summary_dict = self._parse_summary(summary)

        # Parse case introduction (病案介绍)
        intro = case_data.get('【病案介绍】', {})

        # Parse treatment process (诊治过程)
        treatment_process = case_data.get('【诊治过程】', {})

        # Stage 1: Referral
        stage1 = MedChainStageState(
            stage=MedChainStage.REFERRAL,
            timestamp=0,
            department_primary=tags.get('科室', [''])[0] if tags.get('科室') else None,
            department_secondary=tags.get('科室', ['', ''])[1] if len(tags.get('科室', [])) > 1 else None,
        )
        episode.stages.append(stage1)

        # Stage 2: History-taking
        chief_complaint = intro.get('主诉', [''])[0] if isinstance(intro.get('主诉'), list) else intro.get('主诉', '')
        present_illness = intro.get('现病史', [''])[0] if isinstance(intro.get('现病史'), list) else intro.get('现病史', '')
        past_history = intro.get('既往史', [''])[0] if isinstance(intro.get('既往史'), list) else intro.get('既往史', '')

        stage2 = MedChainStageState(
            stage=MedChainStage.HISTORY_TAKING,
            timestamp=1,
            chief_complaint=chief_complaint if isinstance(chief_complaint, str) else str(chief_complaint),
            present_illness=present_illness if isinstance(present_illness, str) else str(present_illness),
            past_history=past_history if isinstance(past_history, str) else str(past_history),
        )
        episode.stages.append(stage2)

        # Stage 3: Examination
        exam_data = intro.get('查体', {})
        physical_exam = {}
        auxiliary_exam = {}

        if isinstance(exam_data, dict):
            physical_exam = exam_data.get('体格检查', {})
            auxiliary_exam = exam_data.get('辅助检查', {})

        stage3 = MedChainStageState(
            stage=MedChainStage.EXAMINATION,
            timestamp=2,
            physical_exam=physical_exam if isinstance(physical_exam, dict) else {},
            auxiliary_exam=auxiliary_exam if isinstance(auxiliary_exam, dict) else {},
        )
        episode.stages.append(stage3)

        # Stage 4: Diagnosis
        initial_diag = treatment_process.get('初步诊断', [''])
        diff_diag = treatment_process.get('鉴别诊断', [])

        stage4 = MedChainStageState(
            stage=MedChainStage.DIAGNOSIS,
            timestamp=3,
            diagnosis=initial_diag[0] if isinstance(initial_diag, list) and initial_diag else str(initial_diag),
            differential_diagnosis=diff_diag if isinstance(diff_diag, list) else [str(diff_diag)],
        )
        episode.stages.append(stage4)

        # Stage 5: Treatment
        treatment_plan = treatment_process.get('诊治经过', [''])

        stage5 = MedChainStageState(
            stage=MedChainStage.TREATMENT,
            timestamp=4,
            treatment_plan=treatment_plan[0] if isinstance(treatment_plan, list) and treatment_plan else str(treatment_plan),
            treatment_result=summary_dict.get('治疗结果'),
        )
        episode.stages.append(stage5)

        return episode

    def _parse_summary(self, summary: List[str]) -> Dict[str, str]:
        """Parse case summary list into structured dict"""
        result = {}
        for item in summary:
            if isinstance(item, str):
                if '【基本信息】' in item:
                    result['basic_info'] = item.replace('【基本信息】', '').strip()
                elif '【发病原因】' in item:
                    result['cause'] = item.replace('【发病原因】', '').strip()
                elif '【临床诊断】' in item:
                    result['clinical_diagnosis'] = item.replace('【临床诊断】', '').strip()
                elif '【治疗方案】' in item:
                    result['treatment_plan'] = item.replace('【治疗方案】', '').strip()
                elif '【治疗结果】' in item:
                    result['治疗结果'] = item.replace('【治疗结果】', '').strip()
                elif '【病案重点】' in item:
                    result['focus'] = item.replace('【病案重点】', '').strip()
        return result

    def load_patient(self, case_data: Dict) -> PatientState2:
        """Convert MedChain case to PatientState2"""
        state = PatientState2(state_id="initial")

        # Extract from 病案介绍
        intro = case_data.get('【病案介绍】', {})
        summary = case_data.get('【病例摘要】', [])

        # Parse basic info from summary
        for item in summary:
            if isinstance(item, str) and '【基本信息】' in item:
                info = item.replace('【基本信息】', '').strip()
                # Parse "男，41岁，无" format
                parts = info.split('，')
                if parts:
                    if '男' in parts[0]:
                        state.sex = 'M'
                    elif '女' in parts[0]:
                        state.sex = 'F'
                    if len(parts) > 1:
                        age_match = re.search(r'(\d+)', parts[1])
                        if age_match:
                            state.age = int(age_match.group(1))

        # Chief complaint
        chief = intro.get('主诉', [])
        if chief:
            state.chief_complaint = chief[-1] if isinstance(chief, list) else str(chief)

        # Parse vitals from physical exam
        exam = intro.get('查体', {})
        if isinstance(exam, dict):
            physical = exam.get('体格检查', {})
            if isinstance(physical, dict):
                general = physical.get('一般检查', '')
                state.vitals = self._parse_vitals(general)

        # Comorbidities from past history
        past = intro.get('既往史', [])
        if past and past[0] != '不详':
            state.comorbidities = past if isinstance(past, list) else [str(past)]

        return state

    def _parse_vitals(self, vital_str: str) -> VitalSigns2:
        """Parse vital signs from Chinese format"""
        vitals = VitalSigns2()

        if not vital_str:
            return vitals

        # T：37℃，P：78次/分，R：20次/分，BP：105/63mmHg
        temp_match = re.search(r'T[：:]\s*(\d+\.?\d*)℃', vital_str)
        if temp_match:
            vitals.temperature_celsius = float(temp_match.group(1))

        pulse_match = re.search(r'P[：:]\s*(\d+)次/分', vital_str)
        if pulse_match:
            vitals.heart_rate = int(pulse_match.group(1))

        rr_match = re.search(r'R[：:]\s*(\d+)次/分', vital_str)
        if rr_match:
            vitals.respiratory_rate = int(rr_match.group(1))

        bp_match = re.search(r'BP[：:]\s*(\d+)/(\d+)mmHg', vital_str)
        if bp_match:
            vitals.blood_pressure_systolic = int(bp_match.group(1))
            vitals.blood_pressure_diastolic = int(bp_match.group(2))

        return vitals

    def convert_to_actions(self, episode: MedChainEpisode) -> List[AdaptedAction]:
        """Convert MedChain stages to CGA-Bench actions"""
        actions = []

        for stage_state in episode.stages:
            stage = stage_state.stage

            if stage == MedChainStage.REFERRAL:
                # Triage action
                if stage_state.department_primary:
                    action = Action2(
                        action_type=ActionType2.CONSULT,
                        action_id=f"triage_{hash(stage_state.department_primary) % 10000}",
                        target=stage_state.department_primary,
                        parameters={
                            'primary_department': stage_state.department_primary,
                            'secondary_department': stage_state.department_secondary,
                        },
                        timestamp_minutes=0,
                        status=ActionStatus.COMPLETED,
                    )
                    actions.append(AdaptedAction(
                        original_action={'stage': 'referral', 'department': stage_state.department_primary},
                        cga_action=action,
                        mapping_confidence=0.9,
                    ))

            elif stage == MedChainStage.HISTORY_TAKING:
                # History collection action
                action = Action2(
                    action_type=ActionType2.HISTORY,
                    action_id=f"history_{hash(stage_state.chief_complaint or '') % 10000}",
                    target="patient_history",
                    parameters={
                        'chief_complaint': stage_state.chief_complaint,
                        'present_illness': stage_state.present_illness,
                        'past_history': stage_state.past_history,
                    },
                    timestamp_minutes=5,
                    status=ActionStatus.COMPLETED,
                )
                actions.append(AdaptedAction(
                    original_action={'stage': 'history', 'data': stage_state.__dict__},
                    cga_action=action,
                    mapping_confidence=0.9,
                ))

            elif stage == MedChainStage.EXAMINATION:
                # Physical exam actions
                for exam_type, finding in stage_state.physical_exam.items():
                    action = Action2(
                        action_type=ActionType2.PHYSICAL_EXAM,
                        action_id=f"pe_{hash(exam_type) % 10000}",
                        target=exam_type,
                        parameters={'finding': finding},
                        timestamp_minutes=10,
                        status=ActionStatus.COMPLETED,
                    )
                    actions.append(AdaptedAction(
                        original_action={'stage': 'examination', 'type': 'physical', 'exam': exam_type},
                        cga_action=action,
                        mapping_confidence=0.85,
                    ))

                # Auxiliary exam actions (labs, imaging)
                for exam_type, result in stage_state.auxiliary_exam.items():
                    if any(img in exam_type for img in ['X-ray', 'CT', 'MRI', '超声', 'X线片']):
                        action_type = ActionType2.ORDER_IMAGING
                    else:
                        action_type = ActionType2.ORDER_LAB

                    action = Action2(
                        action_type=action_type,
                        action_id=f"aux_{hash(exam_type) % 10000}",
                        target=exam_type,
                        parameters={'result': result},
                        timestamp_minutes=15,
                        status=ActionStatus.COMPLETED,
                    )
                    actions.append(AdaptedAction(
                        original_action={'stage': 'examination', 'type': 'auxiliary', 'exam': exam_type},
                        cga_action=action,
                        mapping_confidence=0.85,
                    ))

            elif stage == MedChainStage.DIAGNOSIS:
                # Diagnosis action
                if stage_state.diagnosis:
                    action = Action2(
                        action_type=ActionType2.DIAGNOSE,
                        action_id=f"diag_{hash(stage_state.diagnosis) % 10000}",
                        target=stage_state.diagnosis,
                        parameters={
                            'differential': stage_state.differential_diagnosis,
                        },
                        timestamp_minutes=30,
                        status=ActionStatus.COMPLETED,
                    )
                    actions.append(AdaptedAction(
                        original_action={'stage': 'diagnosis', 'diagnosis': stage_state.diagnosis},
                        cga_action=action,
                        mapping_confidence=0.9,
                    ))

            elif stage == MedChainStage.TREATMENT:
                # Treatment action
                if stage_state.treatment_plan:
                    # Determine treatment type
                    treatment_types = []
                    for tx_type in self.TREATMENT_CATEGORIES:
                        if tx_type in str(stage_state.treatment_plan):
                            treatment_types.append(tx_type)

                    action = Action2(
                        action_type=ActionType2.TREAT,
                        action_id=f"treat_{hash(stage_state.treatment_plan) % 10000}",
                        target=','.join(treatment_types) if treatment_types else 'treatment',
                        parameters={
                            'plan': stage_state.treatment_plan,
                            'result': stage_state.treatment_result,
                        },
                        timestamp_minutes=45,
                        status=ActionStatus.COMPLETED,
                    )
                    actions.append(AdaptedAction(
                        original_action={'stage': 'treatment', 'plan': stage_state.treatment_plan},
                        cga_action=action,
                        mapping_confidence=0.85,
                    ))

        return actions

    def adapt_episode(self, case_data: Dict, case_id: str = None) -> AdaptedEpisode:
        """Convert MedChain case to CGA-Bench AdaptedEpisode"""
        if case_id is None:
            case_id = case_data.get('id', 'unknown')

        # Parse case into MedChain format
        medchain_episode = self.parse_case(case_id, case_data)

        # Convert to patient state
        initial_state = self.load_patient(case_data)

        # Convert stages to actions
        actions = self.convert_to_actions(medchain_episode)

        # Determine guideline based on department
        guideline_id = None
        if medchain_episode.stages:
            primary_dept = medchain_episode.stages[0].department_primary
            if primary_dept:
                guideline_id = self.DEPARTMENT_GUIDELINE_MAPPING.get(
                    primary_dept,
                    "cpg/runtime_dsl/medchain/general.yaml"
                )

        # Check task success (diagnosis match)
        task_success = self._check_diagnosis_match(
            medchain_episode.stages[3].diagnosis if len(medchain_episode.stages) > 3 else None,
            medchain_episode.ground_truth.get('disease', [])
        )

        episode = AdaptedEpisode(
            episode_id=f"mc_{case_id}",
            source_benchmark="MedChain",
            original_task_id=case_id,
            initial_state=initial_state,
            actions=actions,
            guideline_id=guideline_id,
            task_success=task_success,
            original_metrics={
                'stages_completed': len(medchain_episode.stages),
                'department': medchain_episode.ground_truth.get('department', []),
                'disease': medchain_episode.ground_truth.get('disease', []),
            },
        )

        episode.adaptation_warnings = self.validate_adaptation(episode)

        return episode

    def _check_diagnosis_match(self, diagnosis: Optional[str], ground_truth: List[str]) -> bool:
        """Check if diagnosis matches ground truth"""
        if not diagnosis or not ground_truth:
            return False

        diag_lower = diagnosis.lower()
        for gt in ground_truth:
            if gt.lower() in diag_lower or diag_lower in gt.lower():
                return True
        return False

    def convert_action(self, action_data: Dict) -> Optional[AdaptedAction]:
        """Convert single action (not used in MedChain - uses stages)"""
        return None

    def convert_action_log(self, action_log: List[Dict]) -> List[AdaptedAction]:
        """Convert action log (not used in MedChain)"""
        return []

    def load_from_file(self, filepath: Path) -> List[AdaptedEpisode]:
        """Load episodes from MedChain JSON file"""
        episodes = []
        filepath = Path(filepath)

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for case_id, case_data in data.items():
            try:
                episode = self.adapt_episode(case_data, case_id)
                episodes.append(episode)
            except Exception as e:
                logger.warning(f"Failed to adapt case {case_id}: {e}")

        return episodes

    def analyze_stage_compliance(self, episode: MedChainEpisode) -> Dict[str, Any]:
        """
        Analyze stage-level compliance for MedChain episode

        Returns metrics for:
        - Stage completion (OMISSION detection)
        - Stage order (SEQUENCE violation)
        - Error propagation tracking
        """
        analysis = {
            'stages_completed': {},
            'sequence_violations': [],
            'omissions': [],
            'error_propagation': [],
        }

        expected_order = [
            MedChainStage.REFERRAL,
            MedChainStage.HISTORY_TAKING,
            MedChainStage.EXAMINATION,
            MedChainStage.DIAGNOSIS,
            MedChainStage.TREATMENT,
        ]

        # Check stage completion
        for i, expected_stage in enumerate(expected_order):
            if i < len(episode.stages):
                actual_stage = episode.stages[i].stage
                analysis['stages_completed'][expected_stage.value] = True

                # Check sequence
                if actual_stage != expected_stage:
                    analysis['sequence_violations'].append({
                        'expected': expected_stage.value,
                        'actual': actual_stage.value,
                        'position': i,
                    })
            else:
                analysis['stages_completed'][expected_stage.value] = False
                analysis['omissions'].append(expected_stage.value)

        return analysis

    def get_statistics(self) -> Dict[str, Any]:
        """Get MedChain dataset statistics"""
        if not self.cases:
            return {'error': 'No data loaded'}

        departments = {}
        diseases = {}

        for case_id, case_data in self.cases.items():
            tags = case_data.get('tags', {})

            for dept in tags.get('科室', []):
                departments[dept] = departments.get(dept, 0) + 1

            for disease in tags.get('病种', []):
                diseases[disease] = diseases.get(disease, 0) + 1

        return {
            'total_cases': len(self.cases),
            'unique_departments': len(departments),
            'unique_diseases': len(diseases),
            'top_departments': sorted(departments.items(), key=lambda x: -x[1])[:10],
            'top_diseases': sorted(diseases.items(), key=lambda x: -x[1])[:10],
        }
