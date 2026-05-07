"""
MedAgentBench Adapter
FHIR 리소스 기반 MedAgentBench와의 연동
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import logging
import re

from cga_bench.env.adapters.base_adapter import (
    BaseAdapter,
    AdaptedEpisode,
    AdaptedAction,
)
from cga_bench.env.adapters.mappings import (
    MappingLoader,
    get_all_loinc_mappings,
    get_all_snomed_mappings,
)
from cga_bench.env.adapters.normalizers import ActionTargetNormalizer
from cga_bench.env.core.state import (
    PatientState2,
    VitalSigns2,
    LabResult2,
    ImagingResult,
    MedicationAdministration,
    DispositionStatus,
)
from cga_bench.env.core.actions import (
    Action2,
    ActionType2,
    ActionStatus,
)

logger = logging.getLogger(__name__)


class FHIRResourceMapper:
    """
    FHIR 리소스를 CGA-Bench 내부 상태로 매핑

    지원 리소스:
    - Patient → demographics
    - Observation → vitals, labs
    - Condition → diagnoses
    - MedicationRequest → prescriptions
    - Procedure → procedures
    - AllergyIntolerance → allergies

    매핑 데이터는 env/adapters/mappings/ 디렉토리의 YAML 파일에서 로드
    """

    # Lazy-loaded class variables for backwards compatibility
    _loinc_cache: Optional[Dict[str, str]] = None
    _snomed_cache: Optional[Dict[str, str]] = None

    @classmethod
    def _get_loinc_mappings(cls) -> Dict[str, str]:
        """Get LOINC mappings (lazy loaded)"""
        if cls._loinc_cache is None:
            cls._loinc_cache = get_all_loinc_mappings()
        return cls._loinc_cache

    @classmethod
    def _get_snomed_mappings(cls) -> Dict[str, str]:
        """Get SNOMED mappings (lazy loaded)"""
        if cls._snomed_cache is None:
            cls._snomed_cache = get_all_snomed_mappings()
        return cls._snomed_cache

    # Class-level properties using __class_getitem__ pattern
    # For backwards compatibility: FHIRResourceMapper.LOINC_TO_INTERNAL[code]

    # Vitals codes for internal categorization
    VITAL_CODES = {
        'heart_rate', 'blood_pressure_systolic', 'blood_pressure_diastolic',
        'respiratory_rate', 'temperature', 'oxygen_saturation',
        'mean_arterial_pressure', 'oral_temperature', 'rectal_temperature',
        'tympanic_temperature', 'axillary_temperature',
        'gcs_total', 'gcs_eye', 'gcs_motor', 'gcs_verbal',
    }

    @classmethod
    def parse_patient(cls, patient_resource: Dict) -> Dict[str, Any]:
        """Patient 리소스 파싱"""
        result = {}

        result['patient_id'] = patient_resource.get('id', '')

        # Gender
        gender = patient_resource.get('gender', 'unknown')
        result['sex'] = 'M' if gender == 'male' else 'F' if gender == 'female' else 'U'

        # Age (from birthDate)
        birth_date = patient_resource.get('birthDate')
        if birth_date:
            from datetime import date
            try:
                birth_year = int(birth_date[:4])
                result['age'] = date.today().year - birth_year
            except (ValueError, IndexError):
                result['age'] = 0

        return result

    @classmethod
    def parse_observation(cls, obs_resource: Dict) -> Optional[Dict[str, Any]]:
        """Observation 리소스 파싱 (vitals/labs)"""
        code = cls._extract_code(obs_resource.get('code', {}))
        if not code:
            return None

        # Use MappingLoader for logging of unknown codes
        internal_code = MappingLoader.get_loinc(code)

        value = None
        unit = ""

        # valueQuantity
        if 'valueQuantity' in obs_resource:
            vq = obs_resource['valueQuantity']
            value = vq.get('value')
            unit = vq.get('unit', '')

        # valueString
        elif 'valueString' in obs_resource:
            value = obs_resource['valueString']

        # valueCodeableConcept
        elif 'valueCodeableConcept' in obs_resource:
            value = cls._extract_code(obs_resource['valueCodeableConcept'])

        return {
            'code': internal_code,
            'original_code': code,
            'value': value,
            'unit': unit,
            'timestamp': obs_resource.get('effectiveDateTime'),
        }

    @classmethod
    def parse_condition(cls, condition_resource: Dict) -> Optional[str]:
        """Condition 리소스 파싱"""
        code = cls._extract_code(condition_resource.get('code', {}))
        if not code:
            return None

        # Use MappingLoader for logging of unknown codes
        return MappingLoader.get_snomed(code)

    @classmethod
    def parse_medication_request(cls, med_resource: Dict) -> Optional[Dict[str, Any]]:
        """MedicationRequest 리소스 파싱"""
        medication = med_resource.get('medicationCodeableConcept', {})
        code = cls._extract_code(medication)

        return {
            'medication_code': code,
            'medication_name': medication.get('text', code),
            'status': med_resource.get('status'),
            'intent': med_resource.get('intent'),
        }

    @classmethod
    def parse_procedure(cls, procedure_resource: Dict) -> Optional[str]:
        """Procedure 리소스 파싱"""
        code = cls._extract_code(procedure_resource.get('code', {}))
        return code

    @classmethod
    def parse_allergy(cls, allergy_resource: Dict) -> Optional[str]:
        """AllergyIntolerance 리소스 파싱"""
        code = allergy_resource.get('code', {})
        return code.get('text') or cls._extract_code(code)

    @classmethod
    def _extract_code(cls, codeable_concept: Dict) -> Optional[str]:
        """CodeableConcept에서 코드 추출"""
        codings = codeable_concept.get('coding', [])
        if codings:
            return codings[0].get('code')
        return codeable_concept.get('text')


# Backwards compatibility: Create module-level proxy to class methods
# This allows FHIRResourceMapper.LOINC_TO_INTERNAL to work as a dict
class _MappingProxy:
    """Proxy class to provide dict-like access to YAML-loaded mappings"""

    def __init__(self, getter_func):
        self._getter = getter_func

    def __getitem__(self, key):
        return self._getter()[key]

    def __contains__(self, key):
        return key in self._getter()

    def __len__(self):
        return len(self._getter())

    def get(self, key, default=None):
        return self._getter().get(key, default)

    def keys(self):
        return self._getter().keys()

    def values(self):
        return self._getter().values()

    def items(self):
        return self._getter().items()

    def __iter__(self):
        return iter(self._getter())


# Attach proxies to FHIRResourceMapper for backwards compatibility
FHIRResourceMapper.LOINC_TO_INTERNAL = _MappingProxy(FHIRResourceMapper._get_loinc_mappings)
FHIRResourceMapper.SNOMED_TO_DIAGNOSIS = _MappingProxy(FHIRResourceMapper._get_snomed_mappings)


class MedAgentBenchAdapter(BaseAdapter):
    """
    MedAgentBench 어댑터

    FHIR Bundle → CGA-Bench 내부 상태 변환
    Tool call sequence → Action list 변환
    """

    def __init__(self):
        super().__init__("MedAgentBench")
        self.mapper = FHIRResourceMapper()

        # Task → Guideline 매핑
        # Official CPG sources: KDIGO, ADA, ACR, AAOS, Joint Commission
        self.guideline_mappings = {
            # Clinical management tasks
            "sepsis_management": "cpg/runtime_dsl/medagentbench/sepsis.yaml",
            "chest_pain_evaluation": "cpg/runtime_dsl/medagentbench/chest_pain.yaml",
            "aki_management": "cpg/runtime_dsl/medagentbench/aki.yaml",

            # Electrolyte replacement tasks (task5, task9) - KDIGO/ESPEN
            "task5": "cpg/runtime_dsl/medagentbench/electrolyte_replacement.yaml",  # Magnesium
            "task9": "cpg/runtime_dsl/medagentbench/electrolyte_replacement.yaml",  # Potassium
            "electrolyte": "cpg/runtime_dsl/medagentbench/electrolyte_replacement.yaml",
            "magnesium": "cpg/runtime_dsl/medagentbench/electrolyte_replacement.yaml",
            "potassium": "cpg/runtime_dsl/medagentbench/electrolyte_replacement.yaml",

            # Glycemic management tasks (task6, task7, task10) - ADA 2024
            "task6": "cpg/runtime_dsl/medagentbench/ada_glycemic_management_2024.yaml",  # CBG average
            "task7": "cpg/runtime_dsl/medagentbench/ada_glycemic_management_2024.yaml",  # CBG recent
            "task10": "cpg/runtime_dsl/medagentbench/ada_glycemic_management_2024.yaml",  # HbA1c
            "glucose": "cpg/runtime_dsl/medagentbench/ada_glycemic_management_2024.yaml",
            "hba1c": "cpg/runtime_dsl/medagentbench/ada_glycemic_management_2024.yaml",
            "diabetes": "cpg/runtime_dsl/medagentbench/ada_glycemic_management_2024.yaml",

            # Referral tasks (task8) - AAOS/AHRQ
            "task8": "cpg/runtime_dsl/medagentbench/clinical_referral.yaml",  # Orthopedic referral
            "referral": "cpg/runtime_dsl/medagentbench/clinical_referral.yaml",
            "consult": "cpg/runtime_dsl/medagentbench/clinical_referral.yaml",
            "orthopedic": "cpg/runtime_dsl/medagentbench/clinical_referral.yaml",

            # EHR operations (task1, task2, task3, task4) - Joint Commission/ONC
            "task1": "cpg/runtime_dsl/medagentbench/ehr_operations.yaml",  # Patient lookup
            "task2": "cpg/runtime_dsl/medagentbench/ehr_operations.yaml",  # Patient age
            "task3": "cpg/runtime_dsl/medagentbench/ehr_operations.yaml",  # BP documentation
            "task4": "cpg/runtime_dsl/medagentbench/ehr_operations.yaml",  # Lab result lookup
            "patient_lookup": "cpg/runtime_dsl/medagentbench/ehr_operations.yaml",
            "vital_signs": "cpg/runtime_dsl/medagentbench/ehr_operations.yaml",
            "documentation": "cpg/runtime_dsl/medagentbench/ehr_operations.yaml",

            # Imaging orders - ACR Appropriateness Criteria
            "imaging": "cpg/runtime_dsl/medagentbench/acr_imaging_appropriateness.yaml",
            "xray": "cpg/runtime_dsl/medagentbench/acr_imaging_appropriateness.yaml",
            "ct": "cpg/runtime_dsl/medagentbench/acr_imaging_appropriateness.yaml",
            "mri": "cpg/runtime_dsl/medagentbench/acr_imaging_appropriateness.yaml",
        }

    def map_task_to_guideline(self, task_id: str) -> Optional[str]:
        """
        Task ID를 Runtime DSL 파일 경로로 매핑 (부분 매칭 지원)

        Args:
            task_id: 원본 벤치마크의 task ID (예: "sepsis_management_001")

        Returns:
            Runtime DSL 파일 경로 또는 None
        """
        # 정확한 매칭 먼저 시도
        if task_id in self.guideline_mappings:
            return self.guideline_mappings[task_id]

        # 부분 매칭 시도 (task_id가 key로 시작하는 경우)
        for key, path in self.guideline_mappings.items():
            if task_id.startswith(key):
                return path

        return None

    def load_patient(self, fhir_bundle: Dict) -> PatientState2:
        """
        FHIR Bundle에서 환자 상태 로드

        Args:
            fhir_bundle: FHIR Bundle 리소스

        Returns:
            PatientState2 객체
        """
        state = PatientState2(state_id="initial")

        entries = fhir_bundle.get('entry', [])

        vitals_data = {}
        labs = []
        diagnoses = []
        allergies = []
        medications = []
        procedures = []

        for entry in entries:
            resource = entry.get('resource', {})
            resource_type = resource.get('resourceType')

            if resource_type == 'Patient':
                patient_data = FHIRResourceMapper.parse_patient(resource)
                state.patient_id = patient_data.get('patient_id', '')
                state.age = patient_data.get('age', 0)
                state.sex = patient_data.get('sex', '')

            elif resource_type == 'Observation':
                obs = FHIRResourceMapper.parse_observation(resource)
                if obs:
                    code = obs['code']
                    # Vitals (use VITAL_CODES set for categorization)
                    if code in FHIRResourceMapper.VITAL_CODES:
                        vitals_data[code] = obs['value']
                    else:
                        # Labs
                        labs.append(LabResult2(
                            test_code=code,
                            test_name=obs.get('original_code', code),
                            value=obs['value'],
                            unit=obs['unit'],
                            timestamp_minutes=0,  # 나중에 계산
                        ))

            elif resource_type == 'Condition':
                diag = FHIRResourceMapper.parse_condition(resource)
                if diag:
                    diagnoses.append(diag)

            elif resource_type == 'AllergyIntolerance':
                allergy = FHIRResourceMapper.parse_allergy(resource)
                if allergy:
                    allergies.append(allergy)

            elif resource_type == 'MedicationRequest':
                med = FHIRResourceMapper.parse_medication_request(resource)
                if med:
                    medications.append(MedicationAdministration(
                        medication_code=med['medication_code'],
                        medication_name=med['medication_name'],
                        dose=0,
                        dose_unit='',
                        route='',
                        timestamp_minutes=0,
                    ))

            elif resource_type == 'Procedure':
                proc = FHIRResourceMapper.parse_procedure(resource)
                if proc:
                    procedures.append(proc)

        # Vitals 설정
        state.vitals = VitalSigns2(
            heart_rate=vitals_data.get('heart_rate'),
            blood_pressure_systolic=vitals_data.get('blood_pressure_systolic'),
            blood_pressure_diastolic=vitals_data.get('blood_pressure_diastolic'),
            respiratory_rate=vitals_data.get('respiratory_rate'),
            temperature_celsius=vitals_data.get('temperature'),
            oxygen_saturation=vitals_data.get('oxygen_saturation'),
        )

        state.lab_results = labs
        state.diagnoses = diagnoses
        state.allergies = allergies
        state.medications_given = medications
        state.procedures_done = procedures

        return state

    def convert_action(self, tool_call: Dict) -> AdaptedAction:
        """
        MedAgentBench tool call을 Action2로 변환

        Args:
            tool_call: {"tool_name": str, "arguments": dict, "result": dict}
        """
        tool_name = tool_call.get('tool_name', tool_call.get('function', {}).get('name', ''))
        arguments = tool_call.get('arguments', tool_call.get('function', {}).get('arguments', {}))

        # Tool name → ActionType2 매핑
        action_type, target = self._map_tool_to_action(tool_name, arguments)

        cga_action = Action2(
            action_type=action_type,
            action_id=f"{tool_name}_{hash(str(arguments)) % 10000}",
            target=target,
            parameters=arguments,
            status=ActionStatus.COMPLETED,
        )

        confidence = 1.0 if action_type != ActionType2.PROCEDURE else 0.8

        return AdaptedAction(
            original_action=tool_call,
            cga_action=cga_action,
            mapping_confidence=confidence,
        )

    def _map_tool_to_action(
        self,
        tool_name: str,
        arguments: Dict
    ) -> Tuple[ActionType2, str]:
        """Tool name을 ActionType2와 target으로 매핑 (fallback 없음)"""
        tool_lower = tool_name.lower()

        # Lab orders
        if 'order' in tool_lower and 'lab' in tool_lower:
            raw_target = arguments.get('test_name') or arguments.get('lab_name')
            if not raw_target:
                raise ValueError(f"Lab order missing target in arguments: {arguments}")
            target = ActionTargetNormalizer.normalize_lab(raw_target)
            return ActionType2.ORDER_LAB, target

        # Imaging
        if 'order' in tool_lower and any(x in tool_lower for x in ['imaging', 'xray', 'ct', 'mri', 'ecg']):
            raw_target = arguments.get('study_name') or arguments.get('modality')
            # Extract imaging type from tool name if not in arguments
            if not raw_target:
                if 'ecg' in tool_lower or 'ekg' in tool_lower:
                    raw_target = 'ecg'
                elif 'xray' in tool_lower or 'x_ray' in tool_lower or 'cxr' in tool_lower:
                    raw_target = 'chest_xray'
                elif 'ct' in tool_lower:
                    raw_target = 'chest_ct'
                elif 'mri' in tool_lower:
                    raw_target = 'mri_brain'
                else:
                    raise ValueError(f"Imaging order missing target in arguments: {arguments}")
            target = ActionTargetNormalizer.normalize_imaging(raw_target)
            return ActionType2.ORDER_IMAGING, target

        # Medications (including fluids)
        if any(x in tool_lower for x in ['prescribe', 'administer', 'give_med', 'fluid']):
            raw_target = arguments.get('medication') or arguments.get('drug_name')
            if not raw_target:
                raise ValueError(f"Medication action missing target in arguments: {arguments}")
            target = ActionTargetNormalizer.normalize_medication(raw_target)
            return ActionType2.GIVE_MEDICATION, target

        # Consult
        if 'consult' in tool_lower:
            raw_target = arguments.get('specialty') or arguments.get('service')
            if not raw_target:
                raise ValueError(f"Consult action missing target in arguments: {arguments}")
            target = ActionTargetNormalizer.normalize_specialty(raw_target)
            return ActionType2.CONSULT, target

        # Procedures (cath lab, intubation, CPR, etc.)
        if any(x in tool_lower for x in ['cath_lab', 'cathlab', 'cath lab']):
            return ActionType2.PROCEDURE, 'cath_lab_activation'
        if any(x in tool_lower for x in ['intubat', 'ventilat']):
            return ActionType2.PROCEDURE, 'intubation'
        if 'cpr' in tool_lower or 'resuscitat' in tool_lower:
            return ActionType2.PROCEDURE, 'cpr'

        # Disposition
        if 'admit' in tool_lower:
            location = arguments.get('location')
            if not location:
                raise ValueError(f"Admit action missing location in arguments: {arguments}")
            return ActionType2.ADMIT, location
        if 'discharge' in tool_lower:
            return ActionType2.DISCHARGE, 'home'

        # No fallback - raise error for unknown tool
        raise ValueError(f"Unknown tool type: '{tool_name}' with arguments: {arguments}")

    def convert_action_log(self, tool_calls: List[Dict]) -> List[AdaptedAction]:
        """Tool call sequence를 Action list로 변환"""
        return [self.convert_action(tc) for tc in tool_calls]

    def adapt_episode(self, episode_data: Dict) -> AdaptedEpisode:
        """
        MedAgentBench 에피소드 전체 변환

        Args:
            episode_data: {
                "task_id": str,
                "patient_bundle": dict,  # FHIR Bundle
                "tool_calls": list,
                "task_success": bool,
                "metrics": dict
            }
        """
        task_id = episode_data.get('task_id', '')
        patient_bundle = episode_data.get('patient_bundle', {})
        tool_calls = episode_data.get('tool_calls', [])

        # 환자 상태 로드
        initial_state = self.load_patient(patient_bundle)

        # 행동 변환
        actions = self.convert_action_log(tool_calls)

        # 가이드라인 매핑
        guideline_id = self.map_task_to_guideline(task_id)

        episode = AdaptedEpisode(
            episode_id=f"mab_{task_id}_{hash(str(episode_data)) % 10000}",
            source_benchmark="MedAgentBench",
            original_task_id=task_id,
            initial_state=initial_state,
            actions=actions,
            guideline_id=guideline_id,
            task_success=episode_data.get('task_success', False),
            original_metrics=episode_data.get('metrics', {}),
        )

        # 검증
        episode.adaptation_warnings = self.validate_adaptation(episode)

        return episode

    def load_from_file(self, filepath: Path) -> List[AdaptedEpisode]:
        """파일에서 에피소드 로드"""
        import json

        episodes = []

        with open(filepath, 'r', encoding='utf-8') as f:
            if filepath.suffix == '.jsonl':
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        episodes.append(self.adapt_episode(data))
            else:
                data = json.load(f)
                if isinstance(data, list):
                    for ep in data:
                        episodes.append(self.adapt_episode(ep))
                else:
                    episodes.append(self.adapt_episode(data))

        return episodes
