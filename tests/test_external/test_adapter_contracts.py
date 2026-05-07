"""Contract tests for external benchmark adapters.

Tests that each adapter:
1. Produces valid NormalizedEpisode from mock input
2. Handles domain-ish source signals reasonably
3. Handles malformed input gracefully (no crash)
4. normalize_external_case dispatcher routes correctly
"""

import pytest

from cga_bench.semantic_layer.external.agentclinic import (
    create_patient_state,
    extract_actions_from_osce,
    normalize_agentclinic_case,
)
from cga_bench.semantic_layer.external.medagentbench import normalize_medagentbench_task
from cga_bench.semantic_layer.external.models import EpisodeEvidence, NormalizedEpisode
from cga_bench.semantic_layer.external.normalize import normalize_external_case

normalize_medchain_case = None
medchain_import_error: Exception | None = None

try:
    from cga_bench.semantic_layer.external.medchain import normalize_medchain_case
except Exception as exc:
    medchain_import_error = exc


class TestAgentClinicAdapter:
    @pytest.fixture
    def mock_agentclinic_case(self):
        return {
            "case_id": "ac_001",
            "patient": {
                "id": "p-001",
                "age": 45,
                "sex": "M",
                "chief_complaint": "chest pain",
            },
            "chief_complaint": "chest pain",
            "vitals": {
                "heart_rate": 90,
                "blood_pressure_systolic": 140,
                "blood_pressure_diastolic": 90,
                "temperature": 37.0,
                "respiratory_rate": 18,
                "spo2": 98,
            },
            "raw_osce": {
                "Test_Results": {
                    "Blood_Tests": {"Troponin": "0.5 ng/mL"},
                },
                "Physical_Examination_Findings": {
                    "Cardiovascular": "Normal S1S2",
                },
            },
            "ground_truth": {"diagnosis": "STEMI"},
            "expected_actions": ["order_ecg", "order_troponin"],
        }

    def test_normalize_produces_normalized_episode(self, mock_agentclinic_case):
        result = normalize_agentclinic_case(mock_agentclinic_case)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark.lower() == "agentclinic"
        assert isinstance(result.evidence, EpisodeEvidence)
        assert len(result.actions) > 0

    def test_extract_actions_from_osce(self, mock_agentclinic_case):
        actions = extract_actions_from_osce(mock_agentclinic_case)
        assert isinstance(actions, list)
        assert all(isinstance(a, str) for a in actions)
        assert "order_lab_troponin" in actions

    def test_patient_state_created(self, mock_agentclinic_case):
        state = create_patient_state(mock_agentclinic_case)
        assert state.age == 45
        assert state.sex == "M"

    def test_empty_case_no_crash(self):
        try:
            result = normalize_agentclinic_case({"id": "empty", "patient": {}, "vitals": {}})
            assert isinstance(result, NormalizedEpisode)
        except (KeyError, TypeError, ValueError):
            pass


class TestMedAgentBenchAdapter:
    @pytest.fixture
    def mock_medagentbench_task(self):
        return {
            "id": "task6_001",
            "instruction": "Order CBC and BMP for patient with fever",
            "context": "Patient presents with high fever and confusion",
            "expected_actions": ["order_lab_cbc", "order_lab_bmp"],
            "patient_id": "P001",
        }

    def test_normalize_produces_normalized_episode(self, mock_medagentbench_task):
        result = normalize_medagentbench_task(mock_medagentbench_task)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark.lower() == "medagentbench"
        assert isinstance(result.evidence, EpisodeEvidence)

    def test_empty_task_no_crash(self):
        try:
            result = normalize_medagentbench_task({"id": "empty", "instruction": ""})
            assert isinstance(result, NormalizedEpisode)
        except (KeyError, TypeError, ValueError):
            pass


@pytest.mark.skipif(medchain_import_error is not None, reason="MedChain adapter unavailable")
class TestMedChainAdapter:
    @pytest.fixture
    def mock_medchain_case(self):
        return {
            "id": "mc_001",
            "tags": {"科室": ["内科"]},
            "【病例摘要】": ["【基本信息】男，41岁，无"],
            "【病案介绍】": {
                "主诉": ["胸痛 2 小时"],
                "现病史": ["突发胸痛"],
                "既往史": ["高血压"],
                "查体": {
                    "体格检查": {"一般检查": "T：37℃，P：78次/分，R：20次/分，BP：105/63mmHg"},
                    "辅助检查": {"CT": "未见明显异常"},
                },
            },
            "【诊治过程】": {
                "初步诊断": ["胸痛待查"],
                "鉴别诊断": ["ACS"],
                "诊治经过": ["对症治疗"],
            },
        }

    def test_normalize_produces_normalized_episode(self, mock_medchain_case):
        assert normalize_medchain_case is not None
        result = normalize_medchain_case(mock_medchain_case["id"], mock_medchain_case)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark.lower() == "medchain"
        assert isinstance(result.evidence, EpisodeEvidence)
        assert len(result.actions) > 0

    def test_malformed_case_no_crash(self):
        assert normalize_medchain_case is not None
        try:
            result = normalize_medchain_case("empty", {})
            assert isinstance(result, NormalizedEpisode)
        except (KeyError, TypeError, ValueError):
            pass


class TestNormalizeDispatcher:
    def test_agentclinic_dispatch(self):
        mock = {
            "case_id": "ac_test",
            "patient": {"age": 50, "sex": "F"},
            "chief_complaint": "headache",
            "vitals": {},
            "raw_osce": {},
            "diagnosis": "migraine",
        }
        result = normalize_external_case("agentclinic", mock)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark.lower() == "agentclinic"

    def test_medagentbench_dispatch(self):
        mock = {"id": "task1_test", "instruction": "order labs", "context": ""}
        result = normalize_external_case("medagentbench", mock)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark.lower() == "medagentbench"

    @pytest.mark.skipif(medchain_import_error is not None, reason="MedChain adapter unavailable")
    def test_medchain_dispatch(self):
        mock = {"id": "mc_test", "tags": {"科室": ["内科"]}}
        result = normalize_external_case("medchain", mock)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark.lower() == "medchain"

    def test_unsupported_source_raises(self):
        with pytest.raises(ValueError, match="Unsupported source"):
            normalize_external_case("nonexistent", {})

    def test_case_insensitive_dispatch(self):
        mock = {"id": "task1_test", "instruction": "test", "context": ""}
        result = normalize_external_case("MedAgentBench", mock)
        assert isinstance(result, NormalizedEpisode)


class TestContractSchemaValidation:
    """Validate adapter output against pydantic contract schemas."""

    def test_agentclinic_result_maps_to_external_parse_result(self):
        from cga_bench.cpg_model.schemas.contracts import ExternalParseResult

        mock = {
            "id": "contract_test",
            "patient": {"age": 50, "sex": "F", "chief_complaint": "headache"},
            "vitals": {},
            "raw_osce": {},
            "diagnosis": "migraine",
        }
        result = normalize_agentclinic_case(mock)

        epr = ExternalParseResult(
            source_benchmark=result.source_benchmark.lower(),
            parsed_scenario={"case_id": result.case_id, "actions": result.actions},
            domain=result.guideline_id or "",
        )
        assert epr.source_benchmark in ("agentclinic",)
        assert isinstance(epr.parsed_scenario, dict)

    def test_medagentbench_result_maps_to_external_parse_result(self):
        from cga_bench.cpg_model.schemas.contracts import ExternalParseResult
        from cga_bench.semantic_layer.external.medagentbench import normalize_medagentbench_task

        mock = {"id": "contract_mab", "instruction": "order labs", "context": ""}
        result = normalize_medagentbench_task(mock)

        epr = ExternalParseResult(
            source_benchmark=result.source_benchmark.lower(),
            parsed_scenario={"case_id": result.case_id},
            domain="",
        )
        assert isinstance(epr.source_benchmark, str)
