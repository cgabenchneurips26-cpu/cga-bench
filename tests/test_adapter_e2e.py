"""
External Benchmark Adapter E2E Tests
실제 데이터 형식의 샘플 파일을 사용한 종단간 테스트
"""
import pytest
import json
from pathlib import Path
from typing import List, Dict, Any

import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from cga_bench.env.adapters.medagentbench_adapter import (
    MedAgentBenchAdapter,
    FHIRResourceMapper,
)
from cga_bench.env.adapters.agentclinic_adapter import AgentClinicAdapter
from cga_bench.env.adapters.base_adapter import AdaptedEpisode, AdaptedAction
from cga_bench.env.core.actions import ActionType2
from cga_bench.env.core.state import PatientState2


# Fixtures path
FIXTURES_DIR = Path(__file__).parent / "fixtures"
MEDAGENTBENCH_DIR = FIXTURES_DIR / "medagentbench"
AGENTCLINIC_DIR = FIXTURES_DIR / "agentclinic"


class TestMedAgentBenchE2E:
    """MedAgentBench 실제 데이터 E2E 테스트"""

    @pytest.fixture
    def adapter(self):
        return MedAgentBenchAdapter()

    @pytest.fixture
    def sepsis_cases(self) -> List[Dict]:
        """Sepsis 케이스 로드"""
        cases = []
        filepath = MEDAGENTBENCH_DIR / "sepsis_cases.jsonl"
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    cases.append(json.loads(line))
        return cases

    @pytest.fixture
    def chest_pain_cases(self) -> List[Dict]:
        """Chest pain 케이스 로드"""
        cases = []
        filepath = MEDAGENTBENCH_DIR / "chest_pain_cases.jsonl"
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    cases.append(json.loads(line))
        return cases

    def test_load_sepsis_cases_from_file(self, adapter):
        """파일에서 Sepsis 케이스 로드 테스트"""
        filepath = MEDAGENTBENCH_DIR / "sepsis_cases.jsonl"
        episodes = adapter.load_from_file(filepath)

        assert len(episodes) == 3
        assert all(isinstance(ep, AdaptedEpisode) for ep in episodes)
        assert episodes[0].original_task_id == "sepsis_management_001"
        assert episodes[1].original_task_id == "sepsis_management_002"
        assert episodes[2].original_task_id == "sepsis_management_003_failed"

    def test_sepsis_case_patient_state_extraction(self, adapter, sepsis_cases):
        """Sepsis 케이스에서 환자 상태 추출 테스트"""
        case = sepsis_cases[0]  # sepsis_management_001
        state = adapter.load_patient(case['patient_bundle'])

        # Demographics
        assert state.patient_id == "sepsis-pt-001"
        assert state.sex == "M"
        assert state.age > 60  # Born 1958

        # Vitals
        assert state.vitals.heart_rate == 112
        assert state.vitals.blood_pressure_systolic == 85
        assert state.vitals.blood_pressure_diastolic == 52
        assert state.vitals.temperature_celsius == 39.2
        assert state.vitals.respiratory_rate == 24
        assert state.vitals.oxygen_saturation == 91

        # Labs
        lab_codes = [lab.test_code for lab in state.lab_results]
        assert "lactate" in lab_codes
        assert "creatinine" in lab_codes

        lactate_lab = next(l for l in state.lab_results if l.test_code == "lactate")
        assert lactate_lab.value == 4.8

        # Diagnoses
        assert "sepsis" in state.diagnoses

        # Allergies
        assert "Penicillin" in state.allergies

    def test_sepsis_case_action_conversion(self, adapter, sepsis_cases):
        """Sepsis 케이스 액션 변환 테스트"""
        case = sepsis_cases[0]
        actions = adapter.convert_action_log(case['tool_calls'])

        assert len(actions) == 6

        # Lab orders
        lab_actions = [a for a in actions if a.cga_action.action_type == ActionType2.ORDER_LAB]
        assert len(lab_actions) == 2
        assert any("lactate" in a.cga_action.target.lower() for a in lab_actions)
        assert any("blood_culture" in a.cga_action.target.lower() for a in lab_actions)

        # Medications
        med_actions = [a for a in actions if a.cga_action.action_type == ActionType2.GIVE_MEDICATION]
        assert len(med_actions) >= 2  # antibiotics + fluids

        # Admission
        admit_actions = [a for a in actions if a.cga_action.action_type == ActionType2.ADMIT]
        assert len(admit_actions) == 1
        assert admit_actions[0].cga_action.target == "ICU"

    def test_sepsis_episode_full_adaptation(self, adapter, sepsis_cases):
        """Sepsis 에피소드 전체 변환 테스트"""
        case = sepsis_cases[0]
        episode = adapter.adapt_episode(case)

        # Episode metadata
        assert episode.source_benchmark == "MedAgentBench"
        assert episode.original_task_id == "sepsis_management_001"
        assert episode.task_success == True

        # Guideline mapping
        assert episode.guideline_id is not None
        assert "sepsis" in episode.guideline_id.lower()

        # Original metrics preserved
        assert episode.original_metrics['time_to_antibiotics_minutes'] == 42
        assert episode.original_metrics['time_to_fluids_minutes'] == 25

        # Warnings
        assert len(episode.adaptation_warnings) == 0  # No warnings for valid data

    def test_sepsis_failed_case(self, adapter, sepsis_cases):
        """실패한 Sepsis 케이스 테스트"""
        case = sepsis_cases[2]  # Failed case
        episode = adapter.adapt_episode(case)

        assert episode.task_success == False
        assert episode.original_metrics.get('missed_sepsis_bundle') == True

        # Only discharge action
        assert len(episode.actions) == 1
        assert episode.actions[0].cga_action.action_type == ActionType2.DISCHARGE

    def test_chest_pain_stemi_case(self, adapter, chest_pain_cases):
        """STEMI 케이스 테스트"""
        case = chest_pain_cases[0]  # STEMI case
        episode = adapter.adapt_episode(case)

        assert episode.task_success == True

        # Patient state
        assert episode.initial_state.vitals.heart_rate == 95
        assert "stemi" in episode.initial_state.diagnoses

        # Actions - should include ECG, troponin, aspirin, anticoagulation
        action_types = [a.cga_action.action_type for a in episode.actions]
        assert ActionType2.ORDER_IMAGING in action_types  # ECG
        assert ActionType2.ORDER_LAB in action_types  # troponin
        assert ActionType2.GIVE_MEDICATION in action_types
        assert ActionType2.CONSULT in action_types

    def test_chest_pain_aspirin_allergy_case(self, adapter, chest_pain_cases):
        """아스피린 알레르기 NSTEMI 케이스 테스트"""
        case = chest_pain_cases[1]
        state = adapter.load_patient(case['patient_bundle'])

        # Allergy recognized
        assert "Aspirin" in state.allergies

        # Diagnosis
        assert "nstemi" in state.diagnoses

        # Metrics
        episode = adapter.adapt_episode(case)
        assert episode.original_metrics.get('aspirin_contraindication_recognized') == True

    def test_load_chest_pain_cases_from_file(self, adapter):
        """파일에서 Chest Pain 케이스 로드 테스트"""
        filepath = MEDAGENTBENCH_DIR / "chest_pain_cases.jsonl"
        episodes = adapter.load_from_file(filepath)

        assert len(episodes) == 3

        # Check variety of outcomes
        success_count = sum(1 for ep in episodes if ep.task_success)
        assert success_count == 3  # All successful in this set

    def test_fhir_code_coverage(self, adapter, sepsis_cases, chest_pain_cases):
        """FHIR 코드 매핑 커버리지 테스트"""
        all_cases = sepsis_cases + chest_pain_cases

        unmapped_codes = set()
        mapped_codes = set()

        for case in all_cases:
            bundle = case['patient_bundle']
            for entry in bundle.get('entry', []):
                resource = entry.get('resource', {})
                resource_type = resource.get('resourceType')

                if resource_type == 'Observation':
                    code = resource.get('code', {}).get('coding', [{}])[0].get('code')
                    if code:
                        if code in FHIRResourceMapper.LOINC_TO_INTERNAL:
                            mapped_codes.add(code)
                        else:
                            unmapped_codes.add(code)

                elif resource_type == 'Condition':
                    code = resource.get('code', {}).get('coding', [{}])[0].get('code')
                    if code:
                        if code in FHIRResourceMapper.SNOMED_TO_DIAGNOSIS:
                            mapped_codes.add(code)
                        else:
                            unmapped_codes.add(code)

        # Report coverage
        print(f"\nMapped codes: {mapped_codes}")
        print(f"Unmapped codes: {unmapped_codes}")

        # At least some codes should be mapped
        assert len(mapped_codes) > 0


class TestAgentClinicE2E:
    """AgentClinic 실제 데이터 E2E 테스트"""

    @pytest.fixture
    def adapter(self):
        return AgentClinicAdapter()

    @pytest.fixture
    def chest_pain_cases(self) -> List[Dict]:
        """Chest pain 대화 케이스 로드"""
        cases = []
        filepath = AGENTCLINIC_DIR / "chest_pain_conversations.jsonl"
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    cases.append(json.loads(line))
        return cases

    @pytest.fixture
    def fever_cases(self) -> List[Dict]:
        """Fever 케이스 로드"""
        cases = []
        filepath = AGENTCLINIC_DIR / "fever_cases.jsonl"
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    cases.append(json.loads(line))
        return cases

    def test_load_chest_pain_cases_from_file(self, adapter):
        """파일에서 Chest Pain 케이스 로드 테스트"""
        filepath = AGENTCLINIC_DIR / "chest_pain_conversations.jsonl"
        episodes = adapter.load_from_file(filepath)

        assert len(episodes) == 3
        assert all(isinstance(ep, AdaptedEpisode) for ep in episodes)

    def test_stemi_conversation_patient_state(self, adapter, chest_pain_cases):
        """STEMI 대화에서 환자 상태 추출 테스트"""
        case = chest_pain_cases[0]  # STEMI case
        state = adapter.load_patient(case)

        # Demographics
        assert state.patient_id == "ac-pt-001"
        assert state.age == 62
        assert state.sex == "M"

        # Chief complaint
        assert "chest pain" in state.chief_complaint.lower()

        # Vitals
        assert state.vitals.heart_rate == 98
        assert state.vitals.blood_pressure_systolic == 155
        assert state.vitals.blood_pressure_diastolic == 95

        # Medical history
        assert "Hypertension" in state.comorbidities
        assert "Diabetes" in state.comorbidities or "Type 2 Diabetes" in state.comorbidities

    def test_stemi_conversation_action_extraction(self, adapter, chest_pain_cases):
        """STEMI 대화에서 액션 추출 테스트"""
        case = chest_pain_cases[0]
        interactions = case.get('interactions', [])
        actions = adapter.convert_interaction_log(interactions)

        # Should extract meaningful actions
        assert len(actions) > 0

        action_types = [a.cga_action.action_type for a in actions]

        # Expected actions from STEMI management
        assert ActionType2.ORDER_IMAGING in action_types  # ECG
        assert ActionType2.ORDER_LAB in action_types  # troponin
        assert ActionType2.GIVE_MEDICATION in action_types  # aspirin, heparin
        assert ActionType2.CONSULT in action_types  # cardiology
        assert ActionType2.ADMIT in action_types  # CCU admission

    def test_stemi_episode_full_adaptation(self, adapter, chest_pain_cases):
        """STEMI 에피소드 전체 변환 테스트"""
        case = chest_pain_cases[0]
        episode = adapter.adapt_episode(case)

        # Metadata
        assert episode.source_benchmark == "AgentClinic"
        assert episode.original_task_id == "ac_chest_pain_001"

        # Guideline mapping
        assert episode.guideline_id is not None
        assert "chest_pain" in episode.guideline_id

        # Task success (diagnosis match)
        assert episode.task_success == True  # "Inferior STEMI" contains "STEMI"

    def test_pericarditis_case(self, adapter, chest_pain_cases):
        """Pericarditis 케이스 테스트"""
        case = chest_pain_cases[1]
        episode = adapter.adapt_episode(case)

        # Correct diagnosis
        assert episode.task_success == True
        assert "pericarditis" in case['agent_diagnosis'].lower()

        # Allergies recognized
        assert "Sulfa" in episode.initial_state.allergies

    def test_missed_diagnosis_case(self, adapter, chest_pain_cases):
        """놓친 진단 케이스 테스트"""
        case = chest_pain_cases[2]  # Missed unstable angina
        episode = adapter.adapt_episode(case)

        # Diagnosis mismatch
        assert episode.task_success == False

        # Only discharge action
        discharge_actions = [a for a in episode.actions
                           if a.cga_action.action_type == ActionType2.DISCHARGE]
        assert len(discharge_actions) == 1

    def test_fever_sepsis_case(self, adapter, fever_cases):
        """Sepsis 발열 케이스 테스트"""
        case = fever_cases[0]  # Septic shock case
        episode = adapter.adapt_episode(case)

        # Patient state
        assert episode.initial_state.vitals.heart_rate == 110
        assert episode.initial_state.vitals.blood_pressure_systolic == 88
        assert episode.initial_state.vitals.temperature_celsius == 39.5

        # Allergies
        assert "Penicillin" in episode.initial_state.allergies

        # Actions should include sepsis bundle
        action_types = [a.cga_action.action_type for a in episode.actions]
        assert ActionType2.ORDER_LAB in action_types  # lactate, blood culture
        assert ActionType2.GIVE_MEDICATION in action_types  # antibiotics
        assert ActionType2.ADMIT in action_types  # ICU

        # Correct diagnosis
        assert episode.task_success == True

    def test_strep_pharyngitis_case(self, adapter, fever_cases):
        """단순 인후통 케이스 테스트"""
        case = fever_cases[1]
        episode = adapter.adapt_episode(case)

        # Appropriate discharge
        discharge_actions = [a for a in episode.actions
                           if a.cga_action.action_type == ActionType2.DISCHARGE]
        assert len(discharge_actions) == 1

        # Correct diagnosis
        assert episode.task_success == True

    def test_text_action_extraction_accuracy(self, adapter, chest_pain_cases):
        """텍스트에서 액션 추출 정확도 테스트"""
        case = chest_pain_cases[0]
        interactions = case.get('interactions', [])

        # Count tool calls vs text extractions
        tool_call_count = sum(1 for i in interactions if 'tool_call' in i)

        actions = adapter.convert_interaction_log(interactions)

        # Check that tool calls are higher confidence
        tool_call_actions = [a for a in actions if a.mapping_confidence >= 0.9]
        text_extracted_actions = [a for a in actions if a.mapping_confidence < 0.9]

        print(f"\nTool call actions: {len(tool_call_actions)}")
        print(f"Text extracted actions: {len(text_extracted_actions)}")

        # Tool calls should be high confidence
        assert len(tool_call_actions) > 0

    def test_guideline_mapping_coverage(self, adapter):
        """가이드라인 매핑 커버리지 테스트"""
        test_complaints = [
            ("severe chest pain", "chest_pain"),
            ("high fever and chills", "fever"),
            ("shortness of breath", "dyspnea"),
            ("abdominal pain", "abdominal_pain"),
            ("headache and dizziness", "headache"),  # Now maps to aan_headache_migraine_2021
            ("unusual dental problem", None),  # No mapping expected
        ]

        for complaint, expected_partial in test_complaints:
            case = {"patient": {}, "chief_complaint": complaint}
            _, guideline_id = adapter.load_case(case)

            if expected_partial:
                assert guideline_id is not None, f"Expected mapping for: {complaint}"
                assert expected_partial in guideline_id, f"Expected {expected_partial} in {guideline_id}"
            else:
                assert guideline_id is None, f"Unexpected mapping for: {complaint}"

    def test_alternative_vitals_keys(self, adapter, fever_cases):
        """대체 활력징후 키 처리 테스트"""
        case = fever_cases[1]  # Uses 'hr' instead of 'heart_rate'
        state = adapter.load_patient(case)

        # Should handle alternative keys
        assert state.vitals.heart_rate == 92


class TestCrossAdapterConsistency:
    """어댑터 간 일관성 테스트"""

    def test_same_patient_different_formats(self):
        """동일 환자 다른 형식 변환 일관성 테스트"""
        mab_adapter = MedAgentBenchAdapter()
        ac_adapter = AgentClinicAdapter()

        # MedAgentBench format (FHIR)
        mab_bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "test-001", "gender": "male", "birthDate": "1960-01-01"}},
                {"resource": {"resourceType": "Observation", "code": {"coding": [{"code": "8867-4"}]}, "valueQuantity": {"value": 95}}},
                {"resource": {"resourceType": "Observation", "code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": 140}}},
            ]
        }

        # AgentClinic format (JSONL)
        ac_case = {
            "patient": {"id": "test-001", "age": 64, "sex": "M"},
            "vitals": {"heart_rate": 95, "sbp": 140}
        }

        mab_state = mab_adapter.load_patient(mab_bundle)
        ac_state = ac_adapter.load_patient(ac_case)

        # Core fields should match
        assert mab_state.patient_id == ac_state.patient_id
        assert mab_state.sex == ac_state.sex
        assert mab_state.vitals.heart_rate == ac_state.vitals.heart_rate
        assert mab_state.vitals.blood_pressure_systolic == ac_state.vitals.blood_pressure_systolic

    def test_action_type_consistency(self):
        """액션 타입 매핑 일관성 테스트"""
        mab_adapter = MedAgentBenchAdapter()
        ac_adapter = AgentClinicAdapter()

        # Same action in different formats
        mab_tool_call = {"tool_name": "order_lab_test", "arguments": {"test_name": "troponin"}}
        ac_tool_call = {"tool_call": {"name": "order_lab", "arguments": {"test": "troponin"}}}

        mab_action = mab_adapter.convert_action(mab_tool_call)
        ac_action = ac_adapter.convert_action(ac_tool_call)

        # Same action type
        assert mab_action.cga_action.action_type == ac_action.cga_action.action_type == ActionType2.ORDER_LAB


class TestEdgeCasesE2E:
    """엣지 케이스 E2E 테스트"""

    def test_empty_bundle(self):
        """빈 Bundle 처리"""
        adapter = MedAgentBenchAdapter()
        episode = adapter.adapt_episode({
            "task_id": "empty_001",
            "patient_bundle": {"resourceType": "Bundle", "entry": []},
            "tool_calls": []
        })

        assert episode.initial_state.patient_id == ""
        assert len(episode.actions) == 0
        assert "Missing initial state" not in episode.adaptation_warnings or \
               "No actions in episode" in episode.adaptation_warnings

    def test_missing_vitals(self):
        """활력징후 누락 처리"""
        adapter = AgentClinicAdapter()
        case = {
            "case_id": "no_vitals",
            "patient": {"id": "p1", "age": 50},
            "chief_complaint": "chest pain",
            "interactions": []
        }

        episode = adapter.adapt_episode(case)

        # Should handle gracefully
        assert episode.initial_state.vitals.heart_rate is None or episode.initial_state.vitals.heart_rate == 0

    def test_malformed_tool_call(self):
        """잘못된 형식 tool call 처리 - ValueError 발생"""
        adapter = MedAgentBenchAdapter()

        # Missing required fields
        tool_call = {"arguments": {}}  # No tool_name

        # No fallback - should raise ValueError for malformed input
        with pytest.raises(ValueError, match="Unknown tool type"):
            adapter.convert_action(tool_call)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
