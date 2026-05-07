"""
Pytest configuration and shared fixtures for CGA-Bench.
"""

import pytest
from pathlib import Path
import json


# ============================================================
# Shared Fixtures
# ============================================================

@pytest.fixture
def temp_results_dir(tmp_path):
    """Temporary directory for test results."""
    d = tmp_path / "test_results"
    d.mkdir()
    return d


@pytest.fixture
def sample_experiment_summary(temp_results_dir):
    """Sample experiment summary JSON for testing comparison tools."""
    summary = {
        "experiment_id": "test_experiment",
        "timestamp": "2025-01-01T00:00:00",
        "config": {
            "scenarios": ["septic_shock_basic", "stemi_basic"],
            "agents": ["rag_gpt4", "oracle"],
            "random_seed": 42,
        },
        "results": [
            # rag_gpt4 on septic_shock_basic: 5 runs
            {"agent_id": "rag_gpt4", "scenario_id": "septic_shock_basic",
             "run_number": i, "compliance_score": 0.80 + i * 0.02,
             "peak_risk": 0.3, "aggregate_risk": 0.15, "total_tokens": 5000}
            for i in range(5)
        ] + [
            # oracle on septic_shock_basic: 5 runs
            {"agent_id": "oracle", "scenario_id": "septic_shock_basic",
             "run_number": i, "compliance_score": 0.92 + i * 0.01,
             "peak_risk": 0.1, "aggregate_risk": 0.05, "total_tokens": 0}
            for i in range(5)
        ] + [
            # rag_gpt4 on stemi_basic: 5 runs
            {"agent_id": "rag_gpt4", "scenario_id": "stemi_basic",
             "run_number": i, "compliance_score": 0.75 + i * 0.03,
             "peak_risk": 0.4, "aggregate_risk": 0.2, "total_tokens": 6000}
            for i in range(5)
        ] + [
            # oracle on stemi_basic: 5 runs
            {"agent_id": "oracle", "scenario_id": "stemi_basic",
             "run_number": i, "compliance_score": 0.95 + i * 0.005,
             "peak_risk": 0.05, "aggregate_risk": 0.02, "total_tokens": 0}
            for i in range(5)
        ],
        "statistics": {
            "rag_gpt4": {
                "overall_mean": 0.82,
                "overall_std": 0.05,
                "by_scenario": {
                    "septic_shock_basic": {"mean": 0.84, "std": 0.03, "min": 0.80, "max": 0.88, "n": 5},
                    "stemi_basic": {"mean": 0.81, "std": 0.04, "min": 0.75, "max": 0.87, "n": 5},
                },
            },
            "oracle": {
                "overall_mean": 0.95,
                "overall_std": 0.02,
                "by_scenario": {
                    "septic_shock_basic": {"mean": 0.94, "std": 0.01, "min": 0.92, "max": 0.96, "n": 5},
                    "stemi_basic": {"mean": 0.96, "std": 0.01, "min": 0.95, "max": 0.97, "n": 5},
                },
            },
        },
    }

    path = temp_results_dir / "test_summary.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def sample_patient_state():
    """Sample patient state dict for testing."""
    return {
        "state_id": "test_state_001",
        "time_since_arrival_minutes": 0.0,
        "age": 65,
        "sex": "M",
        "vitals": {
            "heart_rate": 110,
            "blood_pressure_systolic": 85,
            "blood_pressure_diastolic": 55,
            "respiratory_rate": 22,
            "temperature": 38.9,
            "oxygen_saturation": 94,
        },
        "chief_complaint": "fever and altered mental status",
        "allergies": [],
        "comorbidities": ["diabetes", "hypertension"],
    }


@pytest.fixture
def sample_scenario_config():
    """Sample scenario configuration dict for testing."""
    return {
        "scenario_id": "test_sepsis_001",
        "scenario_type": "septic_shock",
        "description": "Septic shock requiring hour-1 bundle",
        "cpg_graph": "ssc_sepsis_hour1.yaml",
        "max_duration_minutes": 60,
        "time_step_minutes": 5.0,
        "initial_patient_state": {
            "age": 65,
            "sex": "M",
            "chief_complaint": "fever and hypotension",
        },
    }


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for testing without API calls."""
    from cga_bench.agent_runner.llm_provider import LLMConfig, LLMBackend, MockLLMProvider

    config = LLMConfig(backend=LLMBackend.MOCK)
    return MockLLMProvider(config)
