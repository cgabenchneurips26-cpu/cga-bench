"""
Cross-Benchmark Compatibility Tests

서로 다른 벤치마크에서 변환된 데이터가 동일한 semantic으로 호환되는지 테스트:
1. 동일 환자 상태가 같은 내부 표현으로 변환되는가?
2. 동일 액션이 같은 ActionType2로 매핑되는가?
3. 변환된 에피소드가 동일한 평가 파이프라인에서 처리 가능한가?
"""
import pytest
from dataclasses import asdict

from cga_bench.env.adapters.medagentbench_adapter import MedAgentBenchAdapter
from cga_bench.env.adapters.agentclinic_adapter import AgentClinicAdapter
from cga_bench.env.adapters.mappings import MappingLoader
from cga_bench.env.core.actions import ActionType2


class TestCrossBenchmarkPatientState:
    """동일 환자 상태의 cross-benchmark 호환성"""

    def setup_method(self):
        self.mab_adapter = MedAgentBenchAdapter()
        self.ac_adapter = AgentClinicAdapter()
        MappingLoader.clear_cache()

    def test_vitals_semantic_equivalence(self):
        """
        동일한 바이탈 → 동일한 내부 표현
        MedAgentBench: FHIR Observation with LOINC codes
        AgentClinic: JSON with field names
        """
        # MedAgentBench: FHIR 형식 (LOINC codes)
        mab_bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "8867-4"}]},  # LOINC: Heart rate
                        "valueQuantity": {"value": 95}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "8480-6"}]},  # LOINC: Systolic BP
                        "valueQuantity": {"value": 85}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "8462-4"}]},  # LOINC: Diastolic BP
                        "valueQuantity": {"value": 55}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "9279-1"}]},  # LOINC: Respiratory rate
                        "valueQuantity": {"value": 22}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "8310-5"}]},  # LOINC: Temperature
                        "valueQuantity": {"value": 38.5}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "2708-6"}]},  # LOINC: SpO2
                        "valueQuantity": {"value": 94}
                    }
                },
            ]
        }

        # AgentClinic: JSON 형식 (field names)
        ac_case = {
            "vitals": {
                "hr": 95,       # Same values
                "sbp": 85,
                "dbp": 55,
                "rr": 22,
                "temp": 38.5,
                "spo2": 94
            }
        }

        mab_state = self.mab_adapter.load_patient(mab_bundle)
        ac_state, _ = self.ac_adapter.load_case(ac_case)

        # 동일한 내부 표현으로 변환되어야 함
        assert mab_state.vitals.heart_rate == ac_state.vitals.heart_rate == 95
        assert mab_state.vitals.blood_pressure_systolic == ac_state.vitals.blood_pressure_systolic == 85
        assert mab_state.vitals.blood_pressure_diastolic == ac_state.vitals.blood_pressure_diastolic == 55
        assert mab_state.vitals.respiratory_rate == ac_state.vitals.respiratory_rate == 22
        assert mab_state.vitals.temperature_celsius == ac_state.vitals.temperature_celsius == 38.5
        assert mab_state.vitals.oxygen_saturation == ac_state.vitals.oxygen_saturation == 94

    def test_demographics_semantic_equivalence(self):
        """동일한 demographics → 동일한 내부 표현"""
        # MedAgentBench: FHIR Patient
        mab_bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "patient-001",
                        "gender": "male",
                        "birthDate": "1959-01-01"  # ~65 years old
                    }
                }
            ]
        }

        # AgentClinic: JSON patient
        ac_case = {
            "patient": {
                "id": "patient-001",
                "age": 65,
                "sex": "M"
            }
        }

        mab_state = self.mab_adapter.load_patient(mab_bundle)
        ac_state, _ = self.ac_adapter.load_case(ac_case)

        assert mab_state.patient_id == ac_state.patient_id
        assert mab_state.sex == ac_state.sex == "M"
        # Age는 FHIR에서 birthDate 기준 계산이므로 연도에 따라 차이 가능
        assert abs(mab_state.age - ac_state.age) <= 3

    def test_lab_results_semantic_mapping(self):
        """Lab results LOINC → internal code 매핑 확인"""
        mab_bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "2160-0"}]},  # Creatinine
                        "valueQuantity": {"value": 2.5, "unit": "mg/dL"}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "6598-7"}]},  # Troponin
                        "valueQuantity": {"value": 0.5, "unit": "ng/mL"}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "1988-5"}]},  # CRP
                        "valueQuantity": {"value": 150, "unit": "mg/L"}
                    }
                }
            ]
        }

        state = self.mab_adapter.load_patient(mab_bundle)

        # Internal code로 변환되어야 함
        lab_codes = {lab.test_code for lab in state.lab_results}
        assert "creatinine" in lab_codes
        assert "troponin" in lab_codes
        assert "crp" in lab_codes

    def test_diagnosis_semantic_mapping(self):
        """Diagnosis SNOMED → internal code 매핑 확인"""
        mab_bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Condition",
                        "code": {"coding": [{"code": "91302008"}]}  # Sepsis
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "code": {"coding": [{"code": "401303003"}]}  # STEMI (correct code)
                    }
                }
            ]
        }

        state = self.mab_adapter.load_patient(mab_bundle)

        # Internal diagnosis로 변환되어야 함
        assert "sepsis" in state.diagnoses
        assert "stemi" in state.diagnoses


class TestCrossBenchmarkActions:
    """동일 액션의 cross-benchmark 호환성"""

    def setup_method(self):
        self.mab_adapter = MedAgentBenchAdapter()
        self.ac_adapter = AgentClinicAdapter()

    def test_order_lab_semantic_equivalence(self):
        """ORDER_LAB 액션 동일 변환"""
        # MedAgentBench: tool call
        mab_action = {
            "tool_name": "order_lab_test",
            "arguments": {"test_name": "troponin"}
        }

        # AgentClinic: tool call
        ac_interaction = {
            "role": "assistant",
            "tool_call": {
                "name": "order_lab",
                "arguments": {"test": "troponin"}
            }
        }

        mab_result = self.mab_adapter.convert_action(mab_action)
        ac_result = self.ac_adapter.convert_action(ac_interaction)

        assert mab_result.cga_action.action_type == ActionType2.ORDER_LAB
        assert ac_result.cga_action.action_type == ActionType2.ORDER_LAB
        assert mab_result.cga_action.target == ac_result.cga_action.target == "troponin"

    def test_medication_semantic_equivalence(self):
        """GIVE_MEDICATION 액션 동일 변환"""
        # MedAgentBench
        mab_action = {
            "tool_name": "administer_medication",
            "arguments": {"medication": "aspirin"}
        }

        # AgentClinic: text-based
        ac_interaction = {
            "role": "assistant",
            "content": "I prescribed aspirin 325mg"
        }

        mab_result = self.mab_adapter.convert_action(mab_action)
        ac_result = self.ac_adapter.convert_action(ac_interaction)

        assert mab_result.cga_action.action_type == ActionType2.GIVE_MEDICATION
        assert ac_result.cga_action.action_type == ActionType2.GIVE_MEDICATION
        # Target에 aspirin 포함
        assert "aspirin" in mab_result.cga_action.target.lower()
        assert "aspirin" in ac_result.cga_action.target.lower()

    def test_imaging_semantic_equivalence(self):
        """ORDER_IMAGING 액션 동일 변환"""
        # MedAgentBench
        mab_action = {
            "tool_name": "order_imaging_ct",
            "arguments": {"study_name": "chest CT"}
        }

        # AgentClinic
        ac_interaction = {
            "role": "assistant",
            "tool_call": {
                "name": "order_imaging",
                "arguments": {"study": "chest CT"}
            }
        }

        mab_result = self.mab_adapter.convert_action(mab_action)
        ac_result = self.ac_adapter.convert_action(ac_interaction)

        assert mab_result.cga_action.action_type == ActionType2.ORDER_IMAGING
        assert ac_result.cga_action.action_type == ActionType2.ORDER_IMAGING

    def test_consult_semantic_equivalence(self):
        """CONSULT 액션 동일 변환"""
        # MedAgentBench
        mab_action = {
            "tool_name": "consult_specialty",
            "arguments": {"specialty": "cardiology"}
        }

        # AgentClinic
        ac_interaction = {
            "role": "assistant",
            "content": "I consulted cardiology for further evaluation"
        }

        mab_result = self.mab_adapter.convert_action(mab_action)
        ac_result = self.ac_adapter.convert_action(ac_interaction)

        assert mab_result.cga_action.action_type == ActionType2.CONSULT
        assert ac_result.cga_action.action_type == ActionType2.CONSULT
        assert "cardiology" in mab_result.cga_action.target.lower()
        assert "cardiology" in ac_result.cga_action.target.lower()

    def test_disposition_semantic_equivalence(self):
        """ADMIT/DISCHARGE 액션 동일 변환"""
        # Admit
        mab_admit = {"tool_name": "admit_patient", "arguments": {"location": "ICU"}}
        ac_admit = {"role": "assistant", "content": "Patient admitted to ICU"}

        mab_result = self.mab_adapter.convert_action(mab_admit)
        ac_result = self.ac_adapter.convert_action(ac_admit)

        assert mab_result.cga_action.action_type == ActionType2.ADMIT
        assert ac_result.cga_action.action_type == ActionType2.ADMIT

        # Discharge
        mab_discharge = {"tool_name": "discharge_patient", "arguments": {}}
        ac_discharge = {"role": "assistant", "content": "Discharged home"}

        mab_result = self.mab_adapter.convert_action(mab_discharge)
        ac_result = self.ac_adapter.convert_action(ac_discharge)

        assert mab_result.cga_action.action_type == ActionType2.DISCHARGE
        assert ac_result.cga_action.action_type == ActionType2.DISCHARGE


class TestCrossBenchmarkEpisode:
    """전체 에피소드의 cross-benchmark 호환성"""

    def setup_method(self):
        self.mab_adapter = MedAgentBenchAdapter()
        self.ac_adapter = AgentClinicAdapter()
        MappingLoader.clear_cache()

    def test_episode_structure_compatibility(self):
        """변환된 에피소드 구조 호환성"""
        # MedAgentBench episode
        mab_episode_data = {
            "task_id": "sepsis_001",
            "patient_bundle": {
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Patient",
                            "id": "p001",
                            "gender": "female",
                            "birthDate": "1960-01-01"
                        }
                    },
                    {
                        "resource": {
                            "resourceType": "Observation",
                            "code": {"coding": [{"code": "8867-4"}]},
                            "valueQuantity": {"value": 110}
                        }
                    }
                ]
            },
            "tool_calls": [
                {"tool_name": "order_lab_test", "arguments": {"test_name": "lactate"}},
                {"tool_name": "administer_medication", "arguments": {"medication": "antibiotics"}}
            ],
            "task_success": True
        }

        # AgentClinic episode
        ac_episode_data = {
            "case_id": "sepsis_001",
            "patient": {
                "id": "p001",
                "age": 64,
                "gender": "female"
            },
            "vitals": {"hr": 110},
            "chief_complaint": "fever",
            "interactions": [
                {"role": "assistant", "tool_call": {"name": "order_lab", "arguments": {"test": "lactate"}}},
                {"role": "assistant", "content": "Administered antibiotics"}
            ],
            "agent_diagnosis": "sepsis",
            "ground_truth": {"diagnosis": "sepsis"}
        }

        mab_episode = self.mab_adapter.adapt_episode(mab_episode_data)
        ac_episode = self.ac_adapter.adapt_episode(ac_episode_data)

        # 둘 다 AdaptedEpisode 구조를 가짐
        assert hasattr(mab_episode, 'episode_id')
        assert hasattr(ac_episode, 'episode_id')
        assert hasattr(mab_episode, 'initial_state')
        assert hasattr(ac_episode, 'initial_state')
        assert hasattr(mab_episode, 'actions')
        assert hasattr(ac_episode, 'actions')

        # 소스 벤치마크 구분 가능
        assert mab_episode.source_benchmark == "MedAgentBench"
        assert ac_episode.source_benchmark == "AgentClinic"

        # 환자 상태 동일 매핑
        assert mab_episode.initial_state.sex == ac_episode.initial_state.sex == "F"
        assert mab_episode.initial_state.vitals.heart_rate == ac_episode.initial_state.vitals.heart_rate == 110

        # 액션 타입 동일 매핑
        mab_action_types = [a.cga_action.action_type for a in mab_episode.actions]
        ac_action_types = [a.cga_action.action_type for a in ac_episode.actions]

        assert ActionType2.ORDER_LAB in mab_action_types
        assert ActionType2.ORDER_LAB in ac_action_types
        assert ActionType2.GIVE_MEDICATION in mab_action_types
        assert ActionType2.GIVE_MEDICATION in ac_action_types

    def test_unified_evaluation_pipeline(self):
        """
        변환된 에피소드가 동일한 평가 파이프라인에서 처리 가능한지 확인
        (AdaptedEpisode 인터페이스 일관성)
        """
        mab_episode = self.mab_adapter.adapt_episode({
            "task_id": "test_001",
            "patient_bundle": {"entry": []},
            "tool_calls": [{"tool_name": "order_lab_test", "arguments": {"test_name": "CBC"}}]
        })

        ac_episode = self.ac_adapter.adapt_episode({
            "case_id": "test_001",
            "interactions": [{"role": "assistant", "content": "Ordered CBC lab test"}]
        })

        # 동일한 인터페이스로 평가 가능해야 함
        def evaluate_episode(episode):
            """Mock evaluation function"""
            results = {
                "episode_id": episode.episode_id,
                "source": episode.source_benchmark,
                "num_actions": len(episode.actions),
                "action_types": [a.cga_action.action_type.value for a in episode.actions],
                "patient_sex": episode.initial_state.sex,
                "guideline_id": episode.guideline_id,
                "task_success": episode.task_success,
            }
            return results

        mab_result = evaluate_episode(mab_episode)
        ac_result = evaluate_episode(ac_episode)

        # 동일한 구조의 결과 반환
        assert set(mab_result.keys()) == set(ac_result.keys())
        assert isinstance(mab_result["num_actions"], int)
        assert isinstance(ac_result["num_actions"], int)


class TestSemanticMappingGaps:
    """Semantic 매핑 갭 탐지 - 호환되지 않는 케이스 확인"""

    def setup_method(self):
        self.mab_adapter = MedAgentBenchAdapter()
        self.ac_adapter = AgentClinicAdapter()
        MappingLoader.clear_cache()

    def test_unknown_loinc_still_usable(self):
        """Unknown LOINC도 원본 코드로 사용 가능"""
        bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "PROPRIETARY-123", "display": "Custom Lab"}]},
                        "valueQuantity": {"value": 42}
                    }
                }
            ]
        }

        state = self.mab_adapter.load_patient(bundle)
        # Unknown이어도 lab result로 저장됨
        assert len(state.lab_results) == 1
        assert state.lab_results[0].test_code == "PROPRIETARY-123"
        assert state.lab_results[0].value == 42

    def test_agentclinic_text_action_may_miss(self):
        """AgentClinic 텍스트 액션 추출 실패 시 OBSERVE로 폴백"""
        ac_interaction = {
            "role": "assistant",
            "content": "I'm thinking about the differential diagnosis..."
        }

        result = self.ac_adapter.convert_action(ac_interaction)

        # 액션 추출 실패 → None (no OBSERVE fallback)
        assert result is None

    def test_action_target_normalization_works(self):
        """액션 target 정규화로 cross-benchmark 호환성 확보"""
        # MedAgentBench: 구조화된 argument
        mab_action = {
            "tool_name": "order_lab_test",
            "arguments": {"test_name": "Complete Blood Count"}
        }

        # AgentClinic: 자연어에서 추출
        ac_interaction = {
            "role": "assistant",
            "content": "I ordered a CBC lab test"
        }

        mab_result = self.mab_adapter.convert_action(mab_action)
        ac_result = self.ac_adapter.convert_action(ac_interaction)

        # 둘 다 ORDER_LAB
        assert mab_result.cga_action.action_type == ActionType2.ORDER_LAB
        assert ac_result.cga_action.action_type == ActionType2.ORDER_LAB

        # 정규화로 동일한 target으로 변환됨!
        # "Complete Blood Count" → "cbc"
        # "a CBC" → "cbc"
        assert mab_result.cga_action.target == "cbc"
        assert ac_result.cga_action.target == "cbc"
        assert mab_result.cga_action.target == ac_result.cga_action.target

    def test_cross_benchmark_diagnosis_comparison(self):
        """Cross-benchmark 진단 비교 가능성"""
        # MedAgentBench: SNOMED 기반
        mab_bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Condition",
                        "code": {"coding": [{"code": "91302008"}]}  # SNOMED: Sepsis
                    }
                }
            ]
        }

        # AgentClinic: 텍스트 기반
        ac_case = {
            "agent_diagnosis": "Sepsis (source: UTI)",
            "ground_truth": {"diagnosis": "sepsis"}
        }

        mab_state = self.mab_adapter.load_patient(mab_bundle)
        ac_episode = self.ac_adapter.adapt_episode(ac_case)

        # MedAgentBench에서 변환된 진단
        mab_diagnoses = mab_state.diagnoses
        assert "sepsis" in mab_diagnoses

        # AgentClinic에서 task_success로 진단 일치 확인
        assert ac_episode.task_success is True  # 정규화 후 매칭됨


class TestMergedDatasetScenario:
    """두 벤치마크 데이터 병합 시나리오"""

    def setup_method(self):
        self.mab_adapter = MedAgentBenchAdapter()
        self.ac_adapter = AgentClinicAdapter()
        MappingLoader.clear_cache()

    def test_combined_episode_list(self):
        """두 벤치마크 에피소드 병합 처리"""
        mab_episodes = [
            self.mab_adapter.adapt_episode({
                "task_id": f"mab_{i}",
                "patient_bundle": {"entry": []},
                "tool_calls": []
            })
            for i in range(3)
        ]

        ac_episodes = [
            self.ac_adapter.adapt_episode({
                "case_id": f"ac_{i}",
                "interactions": []
            })
            for i in range(3)
        ]

        # 병합
        all_episodes = mab_episodes + ac_episodes

        # 동일한 인터페이스로 처리 가능
        for episode in all_episodes:
            assert hasattr(episode, 'episode_id')
            assert hasattr(episode, 'initial_state')
            assert hasattr(episode, 'actions')
            assert hasattr(episode, 'source_benchmark')

        # 소스별 그룹화 가능
        by_source = {}
        for ep in all_episodes:
            source = ep.source_benchmark
            by_source.setdefault(source, []).append(ep)

        assert len(by_source["MedAgentBench"]) == 3
        assert len(by_source["AgentClinic"]) == 3

    def test_cross_benchmark_statistics(self):
        """Cross-benchmark 통계 집계"""
        episodes = [
            self.mab_adapter.adapt_episode({
                "task_id": "mab_1",
                "patient_bundle": {"entry": []},
                "tool_calls": [
                    {"tool_name": "order_lab_test", "arguments": {"test_name": "CBC"}},
                    {"tool_name": "administer_medication", "arguments": {"medication": "aspirin"}}
                ],
                "task_success": True
            }),
            self.ac_adapter.adapt_episode({
                "case_id": "ac_1",
                "interactions": [
                    {"role": "assistant", "content": "Ordered CBC lab test"},
                    {"role": "assistant", "content": "Prescribed aspirin"}
                ],
                "agent_diagnosis": "ACS",
                "ground_truth": {"diagnosis": "ACS"}
            })
        ]

        # 통합 통계
        total_actions = sum(len(ep.actions) for ep in episodes)
        action_type_counts = {}

        for ep in episodes:
            for action in ep.actions:
                atype = action.cga_action.action_type.value
                action_type_counts[atype] = action_type_counts.get(atype, 0) + 1

        assert total_actions == 4
        assert action_type_counts.get("order_lab", 0) == 2
        assert action_type_counts.get("give_medication", 0) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
