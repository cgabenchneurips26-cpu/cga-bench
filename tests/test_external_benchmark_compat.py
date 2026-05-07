"""
External Benchmark Compatibility Tests

외부 벤치마크 데이터 형식 호환성 테스트:
1. Unknown LOINC/SNOMED codes
2. Different field naming conventions
3. Missing/partial data
4. Non-standard data structures
5. Real-world edge cases
"""
import pytest
from pathlib import Path
import tempfile
import json

from cga_bench.env.adapters.medagentbench_adapter import (
    MedAgentBenchAdapter,
    FHIRResourceMapper,
)
from cga_bench.env.adapters.agentclinic_adapter import AgentClinicAdapter
from cga_bench.env.adapters.mappings import MappingLoader
from cga_bench.env.core.actions import ActionType2


class TestUnknownCodeHandling:
    """Unknown LOINC/SNOMED code graceful fallback"""

    def setup_method(self):
        MappingLoader.clear_cache()

    def test_unknown_loinc_returns_original(self):
        """알 수 없는 LOINC 코드는 원본 반환"""
        unknown_code = "99999-9"
        result = MappingLoader.get_loinc(unknown_code)
        assert result == unknown_code

    def test_unknown_snomed_returns_original(self):
        """알 수 없는 SNOMED 코드는 원본 반환"""
        unknown_code = "999999999"
        result = MappingLoader.get_snomed(unknown_code)
        assert result == unknown_code

    def test_fhir_observation_unknown_loinc(self):
        """Unknown LOINC in FHIR Observation - 파싱 실패 없이 처리"""
        obs = {
            "code": {
                "coding": [{"code": "UNKNOWN-123", "display": "Some Test"}]
            },
            "valueQuantity": {"value": 42, "unit": "mg/dL"}
        }
        result = FHIRResourceMapper.parse_observation(obs)
        assert result is not None
        assert result["code"] == "UNKNOWN-123"  # Falls back to original
        assert result["value"] == 42

    def test_fhir_condition_unknown_snomed(self):
        """Unknown SNOMED in FHIR Condition - 파싱 실패 없이 처리"""
        condition = {
            "code": {
                "coding": [{"code": "UNKNOWN-SNOMED", "display": "Some Condition"}]
            }
        }
        result = FHIRResourceMapper.parse_condition(condition)
        assert result == "UNKNOWN-SNOMED"

    def test_multiple_unknown_codes_logged_once(self):
        """같은 unknown code는 한 번만 로깅"""
        MappingLoader.clear_cache()

        # 같은 코드 여러 번 호출
        for _ in range(5):
            MappingLoader.get_loinc("REPEAT-CODE-1")
            MappingLoader.get_snomed("REPEAT-CODE-2")

        unknown = MappingLoader.get_unknown_codes()
        assert "REPEAT-CODE-1" in unknown["loinc"]
        assert "REPEAT-CODE-2" in unknown["snomed"]
        # Set이므로 중복 없음
        assert len([c for c in unknown["loinc"] if c == "REPEAT-CODE-1"]) == 1


class TestMedAgentBenchVariants:
    """MedAgentBench 다양한 데이터 형식 테스트"""

    def setup_method(self):
        self.adapter = MedAgentBenchAdapter()
        MappingLoader.clear_cache()

    def test_fhir_bundle_minimal(self):
        """최소한의 FHIR Bundle 처리"""
        bundle = {
            "resourceType": "Bundle",
            "entry": []
        }
        state = self.adapter.load_patient(bundle)
        assert state is not None
        assert state.patient_id == ""

    def test_fhir_bundle_patient_only(self):
        """Patient 리소스만 있는 Bundle"""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "test-123",
                        "gender": "male",
                        "birthDate": "1980-01-01"
                    }
                }
            ]
        }
        state = self.adapter.load_patient(bundle)
        assert state.patient_id == "test-123"
        assert state.sex == "M"
        assert state.age > 0

    def test_fhir_observation_various_value_types(self):
        """다양한 Observation value 유형 처리"""
        # valueQuantity
        obs1 = {
            "code": {"coding": [{"code": "8867-4"}]},  # heart rate
            "valueQuantity": {"value": 80, "unit": "bpm"}
        }
        result1 = FHIRResourceMapper.parse_observation(obs1)
        assert result1["value"] == 80
        assert result1["unit"] == "bpm"

        # valueString
        obs2 = {
            "code": {"coding": [{"code": "TEST-1"}]},
            "valueString": "positive"
        }
        result2 = FHIRResourceMapper.parse_observation(obs2)
        assert result2["value"] == "positive"

        # valueCodeableConcept
        obs3 = {
            "code": {"coding": [{"code": "TEST-2"}]},
            "valueCodeableConcept": {
                "coding": [{"code": "abnormal"}],
                "text": "Abnormal Result"
            }
        }
        result3 = FHIRResourceMapper.parse_observation(obs3)
        assert result3["value"] == "abnormal"

    def test_tool_call_various_formats(self):
        """다양한 tool call 형식 처리"""
        # Format 1: tool_name + arguments
        tc1 = {
            "tool_name": "order_lab_test",
            "arguments": {"test_name": "CBC"}
        }
        result1 = self.adapter.convert_action(tc1)
        assert result1.cga_action.action_type == ActionType2.ORDER_LAB
        # Target is normalized
        assert result1.cga_action.target == "cbc"

        # Format 2: function.name + function.arguments
        tc2 = {
            "function": {
                "name": "order_lab_test",
                "arguments": {"lab_name": "BMP"}
            }
        }
        result2 = self.adapter.convert_action(tc2)
        assert result2.cga_action.action_type == ActionType2.ORDER_LAB
        # Target is normalized
        assert result2.cga_action.target == "bmp"

    def test_episode_with_partial_data(self):
        """부분적인 데이터만 있는 에피소드"""
        episode_data = {
            "task_id": "partial_001",
            # patient_bundle 없음
            "tool_calls": [
                {"tool_name": "consult_specialty", "arguments": {"specialty": "cardiology"}}
            ]
        }
        episode = self.adapter.adapt_episode(episode_data)
        assert episode is not None
        assert episode.original_task_id == "partial_001"
        assert len(episode.actions) == 1

    def test_mixed_known_unknown_codes(self):
        """알려진 코드와 모르는 코드 혼합"""
        bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "8867-4"}]},  # Known: heart_rate
                        "valueQuantity": {"value": 90}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "PROPRIETARY-LAB-123"}]},  # Unknown
                        "valueQuantity": {"value": 5.5}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "code": {"coding": [{"code": "91302008"}]}  # Known: sepsis
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "code": {"coding": [{"code": "CUSTOM-DIAGNOSIS-456"}]}  # Unknown
                    }
                }
            ]
        }
        state = self.adapter.load_patient(bundle)

        # Known codes 정상 처리
        assert state.vitals.heart_rate == 90
        assert "sepsis" in state.diagnoses

        # Unknown codes도 저장됨 (원본 코드로)
        assert any("PROPRIETARY-LAB-123" in str(lab.test_code) for lab in state.lab_results)
        assert "CUSTOM-DIAGNOSIS-456" in state.diagnoses


class TestAgentClinicVariants:
    """AgentClinic 다양한 데이터 형식 테스트"""

    def setup_method(self):
        self.adapter = AgentClinicAdapter()

    def test_minimal_case(self):
        """최소한의 case 데이터"""
        case = {"id": "min-001"}
        state, guideline = self.adapter.load_case(case)
        assert state is not None
        # id가 있으면 patient_id로 사용됨
        assert state.patient_id == "min-001"

    def test_alternative_field_names(self):
        """대체 필드명 처리"""
        case = {
            "case_id": "alt-001",
            "patient": {
                "id": "patient-xyz",
                "age": "45 years old",
                "gender": "female"  # sex 대신 gender
            },
            "vitals": {
                "hr": 88,           # heart_rate 대신 hr
                "sbp": 120,         # blood_pressure_systolic 대신 sbp
                "dbp": 80,
                "rr": 16,           # respiratory_rate 대신 rr
                "temp": 37.2,       # temperature 대신 temp
                "spo2": 98          # oxygen_saturation 대신 spo2
            },
            "history": {            # medical_history 대신 history
                "conditions": ["hypertension"],
                "allergies": ["penicillin"]
            }
        }
        state, _ = self.adapter.load_case(case)

        assert state.patient_id == "patient-xyz"
        assert state.age == 45
        assert state.sex == "F"
        assert state.vitals.heart_rate == 88
        assert state.vitals.blood_pressure_systolic == 120
        assert state.vitals.respiratory_rate == 16
        assert state.vitals.temperature_celsius == 37.2
        assert state.vitals.oxygen_saturation == 98
        assert "hypertension" in state.comorbidities
        assert "penicillin" in state.allergies

    def test_interaction_various_roles(self):
        """다양한 role 처리"""
        interactions = [
            {"role": "user", "content": "I have chest pain"},
            {"role": "assistant", "content": "I'll order an ECG"},
            {"role": "agent", "content": "Prescribing aspirin"},
            {"role": "doctor", "content": "Admit to CCU"},
            {"role": "system", "content": "System message"},
        ]
        actions = self.adapter.convert_interaction_log(interactions)

        # assistant, agent, doctor만 처리됨
        assert len(actions) >= 2  # ECG, aspirin, admit

    def test_tool_call_variations(self):
        """다양한 tool call 형식"""
        # name 키
        tc1 = {
            "role": "assistant",
            "tool_call": {
                "name": "order_lab",
                "arguments": {"test": "troponin"}
            }
        }
        result1 = self.adapter.convert_action(tc1)
        assert result1.cga_action.action_type == ActionType2.ORDER_LAB

        # function 키
        tc2 = {
            "role": "assistant",
            "tool_call": {
                "function": "administer_medication",
                "arguments": {"medication": "morphine"}
            }
        }
        result2 = self.adapter.convert_action(tc2)
        assert result2.cga_action.action_type == ActionType2.GIVE_MEDICATION

    def test_diagnosis_matching_various_formats(self):
        """다양한 진단 형식 매칭"""
        test_cases = [
            # (agent_diag, true_diag, expected_match)
            ("Sepsis", "sepsis", True),
            ("STEMI (inferior wall)", "STEMI", True),
            ("Acute MI - anterior", "myocardial infarction", True),
            ("PE [confirmed by CT]", "pulmonary embolism", True),
            ("Community-acquired pneumonia", "CAP", True),
            ("Atrial Fibrillation, paroxysmal", "afib", True),
            ("Unstable Angina/NSTEMI", "UA", True),
            ("GI Bleed (upper)", "gi bleed", True),
            ("Something completely different", "sepsis", False),
        ]

        for agent_diag, true_diag, expected in test_cases:
            result = self.adapter._check_diagnosis_match(agent_diag, true_diag)
            assert result == expected, f"Failed: {agent_diag} vs {true_diag} (expected {expected})"

    def test_text_action_extraction_variations(self):
        """다양한 텍스트에서 액션 추출"""
        test_cases = [
            ("I ordered a CBC lab test", ActionType2.ORDER_LAB),
            ("Let's obtain a chest CT imaging", ActionType2.ORDER_IMAGING),
            ("Ordering an ECG", ActionType2.ORDER_IMAGING),  # ECG = imaging
            ("I prescribed metoprolol", ActionType2.GIVE_MEDICATION),
            ("Administered IV fluids", ActionType2.GIVE_MEDICATION),
            ("Consulted cardiology", ActionType2.CONSULT),
            ("Patient admitted to ICU", ActionType2.ADMIT),
            ("Discharged home with instructions", ActionType2.DISCHARGE),
            ("Performed physical exam", ActionType2.PHYSICAL_EXAM),
        ]

        for text, expected_type in test_cases:
            result = self.adapter._extract_action_from_text(text)
            assert result.cga_action.action_type == expected_type, \
                f"Failed for '{text}': got {result.cga_action.action_type}"


class TestFileLoading:
    """파일 로딩 테스트"""

    def test_medagentbench_jsonl_loading(self):
        """MedAgentBench JSONL 로딩"""
        adapter = MedAgentBenchAdapter()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # 여러 줄의 JSONL
            json.dump({"task_id": "task1", "patient_bundle": {"entry": []}}, f)
            f.write('\n')
            json.dump({"task_id": "task2", "patient_bundle": {"entry": []}}, f)
            f.write('\n')
            f.flush()

            episodes = adapter.load_from_file(Path(f.name))
            assert len(episodes) == 2
            assert episodes[0].original_task_id == "task1"
            assert episodes[1].original_task_id == "task2"

    def test_agentclinic_json_array_loading(self):
        """AgentClinic JSON 배열 로딩"""
        adapter = AgentClinicAdapter()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            data = [
                {"case_id": "case1", "chief_complaint": "chest pain"},
                {"case_id": "case2", "chief_complaint": "fever"},
            ]
            json.dump(data, f)
            f.flush()

            with tempfile.TemporaryDirectory() as tmpdir:
                # Copy file to directory
                import shutil
                shutil.copy(f.name, Path(tmpdir) / "cases.json")

                episodes = adapter.load_from_directory(Path(tmpdir))
                assert len(episodes) == 2

    def test_empty_lines_in_jsonl(self):
        """JSONL에서 빈 줄 처리"""
        adapter = MedAgentBenchAdapter()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"task_id": "task1", "patient_bundle": {"entry": []}}\n')
            f.write('\n')  # 빈 줄
            f.write('   \n')  # 공백만 있는 줄
            f.write('{"task_id": "task2", "patient_bundle": {"entry": []}}\n')
            f.flush()

            episodes = adapter.load_from_file(Path(f.name))
            assert len(episodes) == 2


class TestRealWorldScenarios:
    """실제 벤치마크에서 발생할 수 있는 시나리오"""

    def setup_method(self):
        MappingLoader.clear_cache()

    def test_synthea_style_fhir(self):
        """Synthea 생성 FHIR 스타일 데이터"""
        adapter = MedAgentBenchAdapter()

        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "fullUrl": "urn:uuid:patient-123",
                    "resource": {
                        "resourceType": "Patient",
                        "id": "patient-123",
                        "gender": "male",
                        "birthDate": "1955-03-15",
                        "name": [{"family": "Smith", "given": ["John"]}]
                    }
                },
                {
                    "fullUrl": "urn:uuid:obs-hr",
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-hr",
                        "status": "final",
                        "category": [{"coding": [{"code": "vital-signs"}]}],
                        "code": {
                            "coding": [
                                {"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}
                            ]
                        },
                        "valueQuantity": {
                            "value": 72,
                            "unit": "/min",
                            "system": "http://unitsofmeasure.org",
                            "code": "/min"
                        },
                        "effectiveDateTime": "2024-01-15T10:30:00Z"
                    }
                }
            ]
        }

        state = adapter.load_patient(bundle)
        assert state.patient_id == "patient-123"
        assert state.sex == "M"
        assert state.vitals.heart_rate == 72

    def test_mimic_style_observations(self):
        """MIMIC 스타일 다중 관찰값"""
        adapter = MedAgentBenchAdapter()

        # MIMIC에서는 같은 환자의 여러 시점 데이터가 있음
        bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "8867-4"}]},  # HR
                        "valueQuantity": {"value": 90},
                        "effectiveDateTime": "2024-01-15T08:00:00Z"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "8867-4"}]},  # HR (later)
                        "valueQuantity": {"value": 85},
                        "effectiveDateTime": "2024-01-15T12:00:00Z"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "2160-0"}]},  # Creatinine
                        "valueQuantity": {"value": 1.2, "unit": "mg/dL"}
                    }
                }
            ]
        }

        state = adapter.load_patient(bundle)
        # 마지막 HR 값이 사용됨 (85)
        assert state.vitals.heart_rate == 85
        # Lab result 존재
        assert any(lab.test_code == "creatinine" for lab in state.lab_results)

    def test_agentclinic_llm_response_style(self):
        """AgentClinic LLM 응답 스타일"""
        adapter = AgentClinicAdapter()

        interactions = [
            {
                "role": "assistant",
                "content": "Based on the patient's presentation with chest pain and elevated troponin, "
                          "I would like to:\n"
                          "1. Order an ECG to evaluate for STEMI\n"
                          "2. Consult cardiology for urgent evaluation\n"
                          "3. Give aspirin 325mg"
            }
        ]

        actions = adapter.convert_interaction_log(interactions)

        # 텍스트에서 여러 액션 추출 (현재는 첫 매칭만)
        assert len(actions) >= 1
        # ECG가 첫 번째로 매칭됨
        assert any(a.cga_action.action_type == ActionType2.ORDER_IMAGING for a in actions)

    def test_medication_various_formats(self):
        """다양한 약물 처방 형식"""
        adapter = MedAgentBenchAdapter()

        test_cases = [
            {"tool_name": "prescribe_medication", "arguments": {"medication": "aspirin"}},
            {"tool_name": "administer_drug", "arguments": {"drug_name": "metoprolol"}},
            {"tool_name": "give_medication", "arguments": {"medication": "heparin"}},
            {"tool_name": "give_med_iv", "arguments": {"drug_name": "norepinephrine"}},
        ]

        for tc in test_cases:
            result = adapter.convert_action(tc)
            assert result.cga_action.action_type == ActionType2.GIVE_MEDICATION

    def test_guideline_mapping_partial_match(self):
        """가이드라인 매핑 부분 일치"""
        adapter = MedAgentBenchAdapter()

        # Exact match
        assert adapter.map_task_to_guideline("sepsis_management") is not None

        # Partial match (prefix)
        assert adapter.map_task_to_guideline("sepsis_management_001") is not None
        assert adapter.map_task_to_guideline("sepsis_management_advanced_v2") is not None

        # No match
        assert adapter.map_task_to_guideline("unknown_task") is None


class TestErrorRecovery:
    """에러 복구 테스트"""

    def test_malformed_fhir_resource(self):
        """잘못된 FHIR 리소스 처리"""
        adapter = MedAgentBenchAdapter()

        bundle = {
            "entry": [
                {"resource": {}},  # resourceType 없음
                {"resource": {"resourceType": "Unknown"}},  # 알 수 없는 타입
                {},  # resource 없음
            ]
        }

        # 에러 없이 처리
        state = adapter.load_patient(bundle)
        assert state is not None

    def test_none_values_in_data(self):
        """None 값 처리 - sex=None은 ValueError 발생"""
        import pytest
        adapter = AgentClinicAdapter()

        case = {
            "case_id": None,
            "patient": {
                "age": None,
                "sex": None  # This should raise ValueError (no fallback)
            },
            "vitals": {
                "hr": None,
                "sbp": None
            }
        }

        # sex=None raises ValueError (no fallback to 'U')
        with pytest.raises(ValueError, match="Sex value is required"):
            adapter.load_case(case)

    def test_type_coercion(self):
        """타입 강제 변환"""
        adapter = AgentClinicAdapter()

        case = {
            "patient": {
                "age": "55",  # 문자열
            },
            "vitals": {
                "hr": "80",  # 문자열 (일부 벤치마크에서 발생)
            }
        }

        state, _ = adapter.load_case(case)
        assert state.age == 55
        # vitals는 그대로 저장됨 (타입 변환 없음)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
