"""
AgentClinic Adapter
JSONL case 기반 AgentClinic과의 연동
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import logging
import re
import json

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
    MedicationAdministration,
    DispositionStatus,
)
from cga_bench.env.core.actions import (
    Action2,
    ActionType2,
    ActionStatus,
)
from cga_bench.env.adapters.normalizers import ActionTargetNormalizer

logger = logging.getLogger(__name__)


class AgentClinicAdapter(BaseAdapter):
    """
    AgentClinic 어댑터

    JSONL case → CGA-Bench 내부 상태 변환
    대화 + tool interaction → Action list 변환
    """

    # AgentClinic action patterns
    # Supports: order, ordered, ordering, obtain, obtained, obtaining
    # Patterns must be specific to avoid capturing vague words like "some", "a", "the"
    ACTION_PATTERNS = {
        # Lab orders - require specific lab names or minimum 3 chars (avoid 'some', 'a', etc.)
        r'order(?:ed|ing)?\s+(?:a\s+)?(?:an\s+)?([\w-]{3,}(?:\s+[\w-]+)*?)\s+(?:lab|test|level)s?': ('ORDER_LAB', 1),
        # Direct lab name patterns (more reliable)
        r'order(?:ed|ing)?\s+(troponin|cbc|bmp|cmp|lactate|bnp|crp|pt|ptt|inr|d-dimer|abg)': ('ORDER_LAB', 1),
        # Imaging orders
        r'(?:order|obtain)(?:ed|ing)?\s+(.+?)\s+(?:imaging|scan|xray|ct|mri)': ('ORDER_IMAGING', 1),
        r'(?:order|obtain)(?:ed|ing)?\s+(?:an?\s+)?ecg': ('ORDER_IMAGING', 'ecg'),
        # Medications
        r'(?:prescrib(?:e|ed|ing)|giv(?:e|ing|en)|administer(?:ed|ing)?)\s+(.+)': ('GIVE_MEDICATION', 1),
        # Consults
        r'consult(?:ed|ing)?\s+(.+)': ('CONSULT', 1),
        # Disposition
        r'admit(?:ted|ting)?\s+(?:to\s+)?(.+)?': ('ADMIT', 1),
        r'discharge(?:d|ing)?': ('DISCHARGE', 'home'),
        # Physical exam
        r'physical\s+exam': ('PHYSICAL_EXAM', 'general'),
    }

    def __init__(self):
        super().__init__("AgentClinic")

        # Task → Guideline 매핑 (chief complaint keywords → guideline file)
        # Official CPG sources: AAN, ACC/AHA, GINA, GOLD, NCCN, AAD, ACR
        self.guideline_mappings = {
            # Cardiopulmonary
            "chest_pain": "cpg/runtime_dsl/agentclinic/chest_pain.yaml",
            "shortness_of_breath": "cpg/runtime_dsl/agentclinic/dyspnea.yaml",
            "dyspnea": "cpg/runtime_dsl/agentclinic/dyspnea.yaml",
            "breathing": "cpg/runtime_dsl/agentclinic/dyspnea.yaml",

            # Respiratory - GINA Asthma 2024, GOLD COPD 2024
            "cough": "cpg/runtime_dsl/agentclinic/gold_copd_2024.yaml",  # GOLD 2024
            "wheezing": "cpg/runtime_dsl/agentclinic/gina_asthma_2024.yaml",  # GINA 2024
            "asthma": "cpg/runtime_dsl/agentclinic/gina_asthma_2024.yaml",  # GINA 2024
            "copd": "cpg/runtime_dsl/agentclinic/gold_copd_2024.yaml",  # GOLD 2024
            "bronchitis": "cpg/runtime_dsl/agentclinic/gold_copd_2024.yaml",  # GOLD 2024
            "hemoptysis": "cpg/runtime_dsl/agentclinic/respiratory.yaml",

            # Gastrointestinal
            "abdominal_pain": "cpg/runtime_dsl/agentclinic/abdominal_pain.yaml",
            "nausea": "cpg/runtime_dsl/agentclinic/abdominal_pain.yaml",
            "vomiting": "cpg/runtime_dsl/agentclinic/abdominal_pain.yaml",
            "diarrhea": "cpg/runtime_dsl/agentclinic/abdominal_pain.yaml",

            # Infectious/General
            "fever": "cpg/runtime_dsl/agentclinic/fever.yaml",
            "chills": "cpg/runtime_dsl/agentclinic/fever.yaml",
            "infection": "cpg/runtime_dsl/agentclinic/fever.yaml",

            # Neurological - AAN Guidelines
            "weakness": "cpg/runtime_dsl/agentclinic/aan_myasthenia_gravis.yaml",  # AAN/MGFA 2020
            "myasthenia": "cpg/runtime_dsl/agentclinic/aan_myasthenia_gravis.yaml",  # AAN/MGFA 2020
            "ptosis": "cpg/runtime_dsl/agentclinic/aan_myasthenia_gravis.yaml",  # AAN/MGFA 2020
            "diplopia": "cpg/runtime_dsl/agentclinic/aan_myasthenia_gravis.yaml",  # AAN/MGFA 2020
            "numbness": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "headache": "cpg/runtime_dsl/agentclinic/aan_headache_migraine_2021.yaml",  # AAN/AHS 2021
            "migraine": "cpg/runtime_dsl/agentclinic/aan_headache_migraine_2021.yaml",  # AAN/AHS 2021
            "seizure": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "dizziness": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "vertigo": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "tremor": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "ataxia": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "vision": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "confusion": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "memory": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "difficulty walking": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "gait": "cpg/runtime_dsl/agentclinic/neurological.yaml",

            # Oncological - NCCN Lymphoma 2024
            "mass": "cpg/runtime_dsl/agentclinic/nccn_lymphoma_2024.yaml",  # NCCN 2024
            "lump": "cpg/runtime_dsl/agentclinic/nccn_lymphoma_2024.yaml",  # NCCN 2024
            "lymph_node": "cpg/runtime_dsl/agentclinic/nccn_lymphoma_2024.yaml",  # NCCN 2024
            "lymphadenopathy": "cpg/runtime_dsl/agentclinic/nccn_lymphoma_2024.yaml",  # NCCN 2024
            "lymphoma": "cpg/runtime_dsl/agentclinic/nccn_lymphoma_2024.yaml",  # NCCN 2024
            "weight_loss": "cpg/runtime_dsl/agentclinic/oncological.yaml",
            "swelling": "cpg/runtime_dsl/agentclinic/oncological.yaml",
            "fatigue": "cpg/runtime_dsl/agentclinic/oncological.yaml",
            "night_sweats": "cpg/runtime_dsl/agentclinic/nccn_lymphoma_2024.yaml",  # NCCN 2024

            # Dermatological - AAD Atopic Dermatitis 2024
            "rash": "cpg/runtime_dsl/agentclinic/aad_atopic_dermatitis_2024.yaml",  # AAD 2024
            "skin": "cpg/runtime_dsl/agentclinic/aad_atopic_dermatitis_2024.yaml",  # AAD 2024
            "itching": "cpg/runtime_dsl/agentclinic/aad_atopic_dermatitis_2024.yaml",  # AAD 2024
            "pruritus": "cpg/runtime_dsl/agentclinic/aad_atopic_dermatitis_2024.yaml",  # AAD 2024
            "eczema": "cpg/runtime_dsl/agentclinic/aad_atopic_dermatitis_2024.yaml",  # AAD 2024
            "atopic_dermatitis": "cpg/runtime_dsl/agentclinic/aad_atopic_dermatitis_2024.yaml",  # AAD 2024
            "lesion": "cpg/runtime_dsl/agentclinic/dermatological.yaml",
            "jaundice": "cpg/runtime_dsl/agentclinic/dermatological.yaml",
            "yellow": "cpg/runtime_dsl/agentclinic/dermatological.yaml",

            # Musculoskeletal - ACR Gout 2020, ACR RA 2021
            "joint_pain": "cpg/runtime_dsl/agentclinic/acr_rheumatoid_arthritis_2021.yaml",  # ACR 2021
            "gout": "cpg/runtime_dsl/agentclinic/acr_gout_2020.yaml",  # ACR 2020
            "podagra": "cpg/runtime_dsl/agentclinic/acr_gout_2020.yaml",  # ACR 2020
            "uric_acid": "cpg/runtime_dsl/agentclinic/acr_gout_2020.yaml",  # ACR 2020
            "tophus": "cpg/runtime_dsl/agentclinic/acr_gout_2020.yaml",  # ACR 2020
            "rheumatoid": "cpg/runtime_dsl/agentclinic/acr_rheumatoid_arthritis_2021.yaml",  # ACR 2021
            "arthritis": "cpg/runtime_dsl/agentclinic/acr_rheumatoid_arthritis_2021.yaml",  # ACR 2021
            "back_pain": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",
            "knee": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",
            "hip": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",
            "shoulder": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",
            "fracture": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",
            "injury": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",

            # Syncope - ACC/AHA/HRS 2017
            "syncope": "cpg/runtime_dsl/agentclinic/accaha_syncope_2017.yaml",  # ACC/AHA/HRS 2017
            "fainting": "cpg/runtime_dsl/agentclinic/accaha_syncope_2017.yaml",  # ACC/AHA/HRS 2017
            "passed_out": "cpg/runtime_dsl/agentclinic/accaha_syncope_2017.yaml",  # ACC/AHA/HRS 2017
            "loss_of_consciousness": "cpg/runtime_dsl/agentclinic/accaha_syncope_2017.yaml",  # ACC/AHA/HRS 2017

            # Genitourinary
            "urinary": "cpg/runtime_dsl/agentclinic/genitourinary.yaml",
            "dysuria": "cpg/runtime_dsl/agentclinic/genitourinary.yaml",
            "pelvic_pain": "cpg/runtime_dsl/agentclinic/genitourinary.yaml",
            "vaginal": "cpg/runtime_dsl/agentclinic/genitourinary.yaml",
            "discharge": "cpg/runtime_dsl/agentclinic/genitourinary.yaml",
            "flank_pain": "cpg/runtime_dsl/agentclinic/genitourinary.yaml",
            "bladder": "cpg/runtime_dsl/agentclinic/genitourinary.yaml",
            "cystitis": "cpg/runtime_dsl/agentclinic/genitourinary.yaml",

            # Additional Respiratory
            "respiratory_distress": "cpg/runtime_dsl/agentclinic/dyspnea.yaml",
            "respiratory distress": "cpg/runtime_dsl/agentclinic/dyspnea.yaml",

            # Psychiatry - APA Guidelines
            "sadness": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "depression": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "agitation": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "behavior": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "behavioral": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "aggressive": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "irritability": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "inappropriate": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "telepathic": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "schizo": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "psychosis": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "delusion": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "hallucination": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",

            # Additional Neurological
            "mental status": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "dementia": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "spinning": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "labyrinthitis": "cpg/runtime_dsl/agentclinic/neurological.yaml",
            "neuralgia": "cpg/runtime_dsl/agentclinic/neurological.yaml",

            # Hematology - ASH Guidelines
            "bleeding": "cpg/runtime_dsl/agentclinic/ash_hematology.yaml",
            "epistaxis": "cpg/runtime_dsl/agentclinic/ash_hematology.yaml",
            "hemophilia": "cpg/runtime_dsl/agentclinic/ash_hematology.yaml",
            "thrombasthenia": "cpg/runtime_dsl/agentclinic/ash_hematology.yaml",
            "coagulation": "cpg/runtime_dsl/agentclinic/ash_hematology.yaml",
            "bruising": "cpg/runtime_dsl/agentclinic/ash_hematology.yaml",
            "petechiae": "cpg/runtime_dsl/agentclinic/ash_hematology.yaml",

            # OB/GYN - ACOG Guidelines
            "uterine": "cpg/runtime_dsl/agentclinic/acog_obgyn.yaml",
            "endometritis": "cpg/runtime_dsl/agentclinic/acog_obgyn.yaml",
            "menarche": "cpg/runtime_dsl/agentclinic/acog_obgyn.yaml",
            "menstrual": "cpg/runtime_dsl/agentclinic/acog_obgyn.yaml",
            "pregnancy": "cpg/runtime_dsl/agentclinic/acog_obgyn.yaml",
            "ovarian": "cpg/runtime_dsl/agentclinic/acog_obgyn.yaml",
            "granulosa": "cpg/runtime_dsl/agentclinic/acog_obgyn.yaml",

            # Pediatric GI
            "crying": "cpg/runtime_dsl/agentclinic/pediatric_gi.yaml",
            "hirschsprung": "cpg/runtime_dsl/agentclinic/pediatric_gi.yaml",

            # Additional Cardiology
            "blood pressure": "cpg/runtime_dsl/agentclinic/cardiology.yaml",
            "hypertension": "cpg/runtime_dsl/agentclinic/cardiology.yaml",
            "coarctation": "cpg/runtime_dsl/agentclinic/cardiology.yaml",

            # Additional Oncology
            "cancer": "cpg/runtime_dsl/agentclinic/oncological.yaml",
            "tumor": "cpg/runtime_dsl/agentclinic/oncological.yaml",
            "malignancy": "cpg/runtime_dsl/agentclinic/oncological.yaml",

            # GI - Rectal/Hemorrhoids
            "rectal": "cpg/runtime_dsl/agentclinic/abdominal_pain.yaml",
            "hemorrhoid": "cpg/runtime_dsl/agentclinic/abdominal_pain.yaml",
            "hepatic": "cpg/runtime_dsl/agentclinic/abdominal_pain.yaml",

            # Additional MSK
            "thumb": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",
            "wrist": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",
            "tenosynovitis": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",
            "de quervain": "cpg/runtime_dsl/agentclinic/musculoskeletal.yaml",

            # ENT
            "ear": "cpg/runtime_dsl/agentclinic/ent.yaml",
            "hearing": "cpg/runtime_dsl/agentclinic/ent.yaml",
            "tinnitus": "cpg/runtime_dsl/agentclinic/ent.yaml",

            # Additional Psychiatry - Sleep disorders
            "sleep": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "insomnia": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "nightmare": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "restless": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",
            "akathisia": "cpg/runtime_dsl/agentclinic/apa_psychiatry.yaml",

            # Additional Dermatology
            "plaque": "cpg/runtime_dsl/agentclinic/dermatological.yaml",
            "scaly": "cpg/runtime_dsl/agentclinic/dermatological.yaml",
            "keratosis": "cpg/runtime_dsl/agentclinic/dermatological.yaml",

            # Wound/Vascular
            "wound": "cpg/runtime_dsl/agentclinic/wound_care.yaml",
            "ulcer": "cpg/runtime_dsl/agentclinic/wound_care.yaml",
            "venous": "cpg/runtime_dsl/agentclinic/wound_care.yaml",
        }

    def load_case(self, case_data: Dict) -> Tuple[PatientState2, Optional[str]]:
        """
        AgentClinic case에서 환자 상태 및 가이드라인 ID 로드

        Args:
            case_data: AgentClinic case JSONL entry

        Returns:
            (PatientState2, guideline_id)
        """
        state = self.load_patient(case_data)

        # 가이드라인 결정 - chief complaint, diagnosis 모두 확인
        chief_complaint = case_data.get('chief_complaint', '').lower()

        # Ground truth diagnosis도 확인
        ground_truth = case_data.get('ground_truth', {})
        if isinstance(ground_truth, dict):
            diagnosis = ground_truth.get('diagnosis', '').lower()
        else:
            diagnosis = ''

        # 검색할 텍스트 조합
        search_text = f"{chief_complaint} {diagnosis}"

        guideline_id = None

        for pattern, gid in self.guideline_mappings.items():
            # underscore를 space로 변환하여 매칭
            pattern_with_spaces = pattern.replace('_', ' ')
            if pattern_with_spaces in search_text or pattern in search_text:
                guideline_id = gid
                break

        return state, guideline_id

    def load_patient(self, case_data: Dict) -> PatientState2:
        """
        AgentClinic case에서 환자 상태 로드

        Args:
            case_data: AgentClinic case 데이터

        Returns:
            PatientState2 객체
        """
        state = PatientState2(state_id="initial")

        # Demographics
        patient_info = case_data.get('patient', case_data)
        state.patient_id = patient_info.get('id', '')
        state.age = self._parse_age(patient_info.get('age', ''))
        state.sex = self._normalize_sex(patient_info.get('sex', patient_info.get('gender', 'U')))

        # Chief complaint
        state.chief_complaint = case_data.get('chief_complaint', '')

        # Vitals (if present)
        vitals = case_data.get('vitals', {})
        state.vitals = VitalSigns2(
            heart_rate=vitals.get('heart_rate', vitals.get('hr')),
            blood_pressure_systolic=vitals.get('sbp', vitals.get('blood_pressure_systolic')),
            blood_pressure_diastolic=vitals.get('dbp', vitals.get('blood_pressure_diastolic')),
            respiratory_rate=vitals.get('rr', vitals.get('respiratory_rate')),
            temperature_celsius=vitals.get('temp', vitals.get('temperature')),
            oxygen_saturation=vitals.get('spo2', vitals.get('oxygen_saturation')),
        )

        # Medical history
        history = case_data.get('medical_history', case_data.get('history', {}))
        state.comorbidities = history.get('conditions', [])
        state.allergies = history.get('allergies', [])

        # Working diagnosis (if provided)
        state.working_diagnosis = case_data.get('diagnosis', case_data.get('ground_truth', {}).get('diagnosis'))

        # Ground truth (hidden)
        state._ground_truth = case_data.get('ground_truth', {})

        return state

    def _parse_age(self, age_str: Any) -> int:
        """나이 파싱"""
        if isinstance(age_str, int):
            return age_str
        if isinstance(age_str, str):
            match = re.search(r'\d+', age_str)
            if match:
                return int(match.group())
        return 0

    def _normalize_sex(self, sex_value: Any) -> str:
        """성별 정규화: male/female -> M/F (fallback 없음)"""
        if not sex_value:
            raise ValueError("Sex value is required but was empty/None")
        sex_lower = str(sex_value).lower().strip()
        if sex_lower in ('m', 'male'):
            return 'M'
        elif sex_lower in ('f', 'female'):
            return 'F'
        elif sex_lower == 'u':
            return 'U'  # Explicit unknown is allowed
        raise ValueError(f"Cannot normalize sex value: '{sex_value}'")

    def convert_action(self, interaction: Dict) -> Optional[AdaptedAction]:
        """
        AgentClinic interaction을 Action2로 변환

        Args:
            interaction: {"role": str, "content": str, "tool_call": dict, ...}

        Returns:
            AdaptedAction if action found, None if no action in this interaction
        """
        # Tool call이 있으면 우선 처리
        if 'tool_call' in interaction:
            return self._convert_tool_call(interaction['tool_call'])

        # 텍스트에서 행동 추출 (may return None)
        content = interaction.get('content', '')
        return self._extract_action_from_text(content)

    def _convert_tool_call(self, tool_call: Dict) -> AdaptedAction:
        """Tool call 변환 (fallback 없음)"""
        tool_name = tool_call.get('name') or tool_call.get('function')
        if not tool_name:
            raise ValueError(f"Tool call missing name/function: {tool_call}")

        args = tool_call.get('arguments', {})
        tool_lower = tool_name.lower()

        # 매핑 with normalization
        if 'order_lab' in tool_lower:
            raw_target = args.get('test') or args.get('lab_name')
            if not raw_target:
                raise ValueError(f"Lab order tool call missing target: {tool_call}")
            target = ActionTargetNormalizer.normalize_lab(raw_target)
            action_type = ActionType2.ORDER_LAB
        elif 'order_imaging' in tool_lower or 'ecg' in tool_lower:
            raw_target = args.get('study') or args.get('modality')
            if not raw_target:
                # ECG는 target 없어도 됨
                if 'ecg' in tool_lower:
                    target = 'ecg'
                else:
                    raise ValueError(f"Imaging order tool call missing target: {tool_call}")
            else:
                target = ActionTargetNormalizer.normalize_imaging(raw_target)
            action_type = ActionType2.ORDER_IMAGING
        elif any(x in tool_lower for x in ['prescribe', 'give', 'administer']):
            raw_target = args.get('medication') or args.get('drug')
            if not raw_target:
                raise ValueError(f"Medication tool call missing target: {tool_call}")
            target = ActionTargetNormalizer.normalize_medication(raw_target)
            action_type = ActionType2.GIVE_MEDICATION
        elif 'consult' in tool_lower:
            raw_target = args.get('specialty')
            if not raw_target:
                raise ValueError(f"Consult tool call missing specialty: {tool_call}")
            target = ActionTargetNormalizer.normalize_specialty(raw_target)
            action_type = ActionType2.CONSULT
        elif 'admit' in tool_lower:
            location = args.get('location')
            if not location:
                raise ValueError(f"Admit tool call missing location: {tool_call}")
            target = location
            action_type = ActionType2.ADMIT
        elif 'discharge' in tool_lower:
            target = 'home'
            action_type = ActionType2.DISCHARGE
        else:
            raise ValueError(f"Unknown tool call type: '{tool_name}' with args: {args}")

        cga_action = Action2(
            action_type=action_type,
            action_id=f"{tool_name}_{hash(str(args)) % 10000}",
            target=target,
            parameters=args,
            status=ActionStatus.COMPLETED,
        )

        return AdaptedAction(
            original_action=tool_call,
            cga_action=cga_action,
            mapping_confidence=0.9,
        )

    def _extract_action_from_text(self, text: str) -> Optional[AdaptedAction]:
        """
        텍스트에서 행동 추출

        Returns:
            AdaptedAction if action found, None if no action pattern matched
        """
        if not text or not text.strip():
            return None  # Empty text has no action

        text_lower = text.lower()

        for pattern, (action_type_str, target_group) in self.ACTION_PATTERNS.items():
            match = re.search(pattern, text_lower)
            if match:
                action_type = ActionType2[action_type_str]

                if isinstance(target_group, int):
                    raw_target = match.group(target_group) if match.lastindex is not None and match.lastindex >= target_group else None
                    if not raw_target:
                        raise ValueError(f"Pattern matched but no target captured from text: '{text}'")
                else:
                    raw_target = target_group

                # Normalize target based on action type
                # Use try_normalize for text extraction - if fails, continue to next pattern
                target = raw_target.strip()
                if action_type == ActionType2.ORDER_LAB:
                    normalized = ActionTargetNormalizer.try_normalize_lab(target)
                    if normalized is None:
                        continue  # Try next pattern
                    target = normalized
                elif action_type == ActionType2.ORDER_IMAGING:
                    normalized = ActionTargetNormalizer.try_normalize_imaging(target)
                    if normalized is None:
                        continue
                    target = normalized
                elif action_type == ActionType2.GIVE_MEDICATION:
                    normalized = ActionTargetNormalizer.try_normalize_medication(target)
                    if normalized is None:
                        continue
                    target = normalized
                elif action_type == ActionType2.CONSULT:
                    normalized = ActionTargetNormalizer.try_normalize_specialty(target)
                    if normalized is None:
                        continue
                    target = normalized

                cga_action = Action2(
                    action_type=action_type,
                    action_id=f"text_action_{hash(text) % 10000}",
                    target=target,
                    parameters={},
                    status=ActionStatus.COMPLETED,
                )

                return AdaptedAction(
                    original_action={"text": text},
                    cga_action=cga_action,
                    mapping_confidence=0.7,
                    notes="Extracted from text",
                )

        # No action pattern matched - this is valid for non-action text in conversations
        return None

    def convert_interaction_log(self, interactions: List[Dict]) -> List[AdaptedAction]:
        """
        대화 + tool interaction을 Action list로 변환

        Args:
            interactions: AgentClinic 대화 로그
        """
        actions = []

        for interaction in interactions:
            role = interaction.get('role', '')

            # 에이전트 메시지만 처리
            if role in ['assistant', 'agent', 'doctor']:
                adapted = self.convert_action(interaction)

                # None이 아닌 액션만 추가 (None = 액션 패턴 없음)
                if adapted is not None:
                    actions.append(adapted)

        return actions

    def convert_action_log(self, action_log: List[Dict]) -> List[AdaptedAction]:
        """BaseAdapter 인터페이스 구현"""
        return self.convert_interaction_log(action_log)

    def adapt_episode(self, case_data: Dict) -> AdaptedEpisode:
        """
        AgentClinic case 전체 변환

        Args:
            case_data: {
                "case_id": str,
                "patient": dict,
                "chief_complaint": str,
                "interactions": list,
                "ground_truth": dict,
                ...
            }
        """
        case_id = case_data.get('case_id', case_data.get('id', ''))

        # 환자 상태 및 가이드라인 로드
        initial_state, guideline_id = self.load_case(case_data)

        # 대화 로그에서 행동 추출
        interactions = case_data.get('interactions', case_data.get('conversation', []))
        actions = self.convert_interaction_log(interactions)

        # Task success 판단
        ground_truth = case_data.get('ground_truth', {})
        agent_diagnosis = case_data.get('agent_diagnosis', '')
        true_diagnosis = ground_truth.get('diagnosis', '')

        task_success = self._check_diagnosis_match(agent_diagnosis, true_diagnosis)

        episode = AdaptedEpisode(
            episode_id=f"ac_{case_id}",
            source_benchmark="AgentClinic",
            original_task_id=case_id,
            initial_state=initial_state,
            actions=actions,
            guideline_id=guideline_id,
            task_success=task_success,
            original_metrics=case_data.get('metrics', {}),
        )

        episode.adaptation_warnings = self.validate_adaptation(episode)

        return episode

    # Related diagnosis groups - diagnoses in the same group are considered matches
    DIAGNOSIS_GROUPS = [
        # Sepsis spectrum
        {"sepsis", "septic shock", "severe sepsis", "septicemia"},
        # Cardiac events
        {"stemi", "nstemi", "mi", "myocardial infarction", "heart attack", "acs", "acute coronary syndrome"},
        {"unstable angina", "ua", "nste-acs"},
        # Respiratory
        {"pneumonia", "cap", "community acquired pneumonia", "hospital acquired pneumonia"},
        {"pe", "pulmonary embolism", "pulmonary embolus"},
        # Stroke
        {"stroke", "cva", "cerebrovascular accident", "ischemic stroke"},
        {"tia", "transient ischemic attack", "mini-stroke"},
        # GI
        {"gerd", "acid reflux", "gastroesophageal reflux"},
        {"gi bleed", "gastrointestinal bleeding", "upper gi bleed", "lower gi bleed"},
        # Cardiac rhythm
        {"afib", "atrial fibrillation", "a-fib"},
        {"svt", "supraventricular tachycardia"},
        # Inflammatory
        {"pericarditis", "acute pericarditis"},
        # Infectious
        {"strep throat", "streptococcal pharyngitis", "strep pharyngitis", "group a strep"},
        {"uti", "urinary tract infection", "bladder infection", "cystitis"},
    ]

    @staticmethod
    def _normalize_diagnosis(diag: str) -> str:
        """
        진단명 정규화: 괄호 내용 제거, 특수문자 제거, 소문자 변환

        Examples:
            "Sepsis (source: UTI)" -> "sepsis"
            "STEMI (inferior)" -> "stemi"
            "Acute MI - anterior" -> "acute mi anterior"
        """
        if not diag:
            return ""

        # 괄호와 그 내용 제거
        normalized = re.sub(r'\([^)]*\)', '', diag)
        # 대괄호와 그 내용 제거
        normalized = re.sub(r'\[[^\]]*\]', '', normalized)
        # 특수문자를 공백으로 변환 (하이픈, 슬래시 등)
        normalized = re.sub(r'[-/,;:]', ' ', normalized)
        # 여러 공백을 하나로
        normalized = re.sub(r'\s+', ' ', normalized)
        # 소문자 변환 및 trim
        return normalized.lower().strip()

    def _check_diagnosis_match(self, agent_diag: str, true_diag: str) -> bool:
        """진단 일치 여부 확인 (semantic matching + normalization)"""
        if not agent_diag or not true_diag:
            return False

        # 원본 소문자 변환
        agent_lower = agent_diag.lower().strip()
        true_lower = true_diag.lower().strip()

        # 정확한 일치
        if agent_lower == true_lower:
            return True

        # 부분 일치 (원본)
        if true_lower in agent_lower or agent_lower in true_lower:
            return True

        # 정규화된 버전으로 매칭
        agent_norm = self._normalize_diagnosis(agent_diag)
        true_norm = self._normalize_diagnosis(true_diag)

        if agent_norm and true_norm:
            # 정규화된 정확한 일치
            if agent_norm == true_norm:
                return True

            # 정규화된 부분 일치
            if true_norm in agent_norm or agent_norm in true_norm:
                return True

        # Semantic matching via diagnosis groups
        for group in self.DIAGNOSIS_GROUPS:
            # 원본으로 매칭
            agent_in_group = any(term in agent_lower or agent_lower in term for term in group)
            true_in_group = any(term in true_lower or true_lower in term for term in group)
            if agent_in_group and true_in_group:
                return True

            # 정규화된 버전으로도 매칭
            if agent_norm and true_norm:
                agent_in_group_norm = any(term in agent_norm or agent_norm in term for term in group)
                true_in_group_norm = any(term in true_norm or true_norm in term for term in group)
                if agent_in_group_norm and true_in_group_norm:
                    return True

        return False

    def load_from_file(self, filepath: Path) -> List[AdaptedEpisode]:
        """JSONL 파일에서 에피소드 로드"""
        episodes = []
        filepath = Path(filepath)

        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    case_data = json.loads(line)
                    episodes.append(self.adapt_episode(case_data))

        return episodes

    def load_from_directory(self, directory: Path) -> List[AdaptedEpisode]:
        """디렉토리의 모든 JSONL 파일 로드"""
        episodes = []
        directory = Path(directory)

        for filepath in directory.glob("*.jsonl"):
            episodes.extend(self.load_from_file(filepath))

        for filepath in directory.glob("*.json"):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    for case in data:
                        episodes.append(self.adapt_episode(case))
                else:
                    episodes.append(self.adapt_episode(data))

        return episodes
