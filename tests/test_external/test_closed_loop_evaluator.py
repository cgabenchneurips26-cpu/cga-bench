from pathlib import Path

from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns
from cga_bench.semantic_layer.external.closed_loop_evaluator import (
    ClosedLoopConfig,
    ClosedLoopEvaluator,
)
from cga_bench.semantic_layer.external.evaluator import evaluate_normalized_episode


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sepsis_state(case_id: str = "t") -> PatientState:
    return PatientState(
        state_id=case_id,
        age=50,
        sex="M",
        vitals=VitalSigns(map_mmhg=60.0),
        chief_complaint="sepsis",
        working_diagnosis="sepsis",
    )


class TestClosedLoopEvaluator:
    def test_basic_sepsis_loop(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "test_1",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state("test_1"),
        }
        actions = [
            "order_lab_lactate",
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
            "give_crystalloid_30ml_kg",
        ]
        result = evaluator.evaluate(episode, actions)
        assert result.total_mandatory_completed > 0
        assert result.compliance_score > 0
        assert len(result.steps) == 4

    def test_state_changes_tracked(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "t",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state(),
        }
        result = evaluator.evaluate(episode, ["order_lab_lactate"])
        assert len(result.steps) == 1
        new_labs = result.steps[0].state_changes.get("new_labs", 0)
        assert isinstance(new_labs, int)
        assert new_labs > 0

    def test_forbidden_action_detected(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "cp_1",
            "guideline_id": "aha_chest_pain",
            "patient_state": PatientState(
                state_id="cp_1",
                age=64,
                sex="F",
                vitals=VitalSigns(map_mmhg=None),
                chief_complaint="chest pain",
            ),
        }
        result = evaluator.evaluate(episode, ["discharge_without_ecg"])
        assert len(result.commissions) >= 1
        assert result.commissions[0]["type"] == "COMMISSION"

    def test_omission_detected(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "t",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state(),
        }
        result = evaluator.evaluate(episode, ["order_lab_lactate"])
        assert len(result.omissions) > 0

    def test_to_compliance_report(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "t",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state(),
        }
        result = evaluator.evaluate(
            episode,
            ["order_lab_lactate", "give_broad_spectrum_antibiotics"],
        )
        report = result.to_compliance_report()
        assert report.case_id == "t"
        assert isinstance(report.compliance_score, float)
        assert "closed_loop_evaluation" in str(report.notes)

    def test_empty_actions(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "t",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state(),
        }
        result = evaluator.evaluate(episode, [])
        assert result.compliance_score == 0.0
        assert len(result.steps) == 0
        assert len(result.omissions) > 0

    def test_no_guideline(self):
        evaluator = ClosedLoopEvaluator()
        result = evaluator.evaluate({"case_id": "t"}, ["order_lab_lactate"])
        assert result.compliance_score == 0.0
        assert result.guideline_id is None

    def test_timing_violation(self):
        config = ClosedLoopConfig(project_root=_project_root(), time_step_minutes=30.0)
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "t",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state(),
        }
        result = evaluator.evaluate(
            episode,
            ["noop", "noop", "noop", "order_lab_lactate"],
        )
        assert len(result.timing_violations) >= 1

    def test_new_mandatory_emerges_field_exists(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "t",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state(),
        }
        result = evaluator.evaluate(episode, ["order_lab_lactate", "order_lab_blood_culture"])
        assert all(isinstance(step.new_mandatory_emerged, list) for step in result.steps)

    def test_config_defaults(self):
        config = ClosedLoopConfig.default()
        assert config.time_step_minutes == 5.0
        assert config.max_steps == 100

    def test_multiple_datasets_work(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        for gid in ["ssc_sepsis_hour1", "aha_chest_pain", "ada_dka_management"]:
            episode = {
                "case_id": f"test_{gid}",
                "guideline_id": gid,
                "patient_state": PatientState(
                    state_id=f"s_{gid}",
                    age=50,
                    sex="M",
                    vitals=VitalSigns(map_mmhg=None),
                    chief_complaint="",
                ),
            }
            result = evaluator.evaluate(episode, ["assess_vital_signs"])
            assert isinstance(result.compliance_score, float)

    def test_max_steps_enforced(self):
        config = ClosedLoopConfig(project_root=_project_root(), max_steps=2)
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "t",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state(),
        }
        result = evaluator.evaluate(episode, ["a", "b", "c", "d"])
        assert len(result.steps) == 2

    def test_sequence_violation_detected(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "seq_1",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state("seq_1"),
        }
        result = evaluator.evaluate(
            episode,
            ["give_broad_spectrum_antibiotics", "order_lab_blood_culture"],
        )
        assert len(result.sequence_violations) >= 1

    def test_disable_sequence_check(self):
        config = ClosedLoopConfig(
            project_root=_project_root(),
            enable_sequence_check=False,
        )
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "seq_off",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state("seq_off"),
        }
        result = evaluator.evaluate(
            episode,
            ["give_broad_spectrum_antibiotics", "order_lab_blood_culture"],
        )
        assert len(result.sequence_violations) == 0

    def test_disable_timing_check(self):
        config = ClosedLoopConfig(
            project_root=_project_root(),
            time_step_minutes=30.0,
            enable_timing_check=False,
        )
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "timing_off",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state("timing_off"),
        }
        result = evaluator.evaluate(
            episode,
            ["noop", "noop", "noop", "order_lab_lactate"],
        )
        assert len(result.timing_violations) == 0


class TestClosedLoopCaching:
    def test_engine_cached_across_evaluate_calls(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "cache_1",
            "guideline_id": "ssc_sepsis_hour1",
            "patient_state": _sepsis_state("cache_1"),
        }
        evaluator.evaluate(episode, ["order_lab_lactate"])
        assert "ssc_sepsis_hour1" in evaluator._engine_cache
        engine_first = evaluator._engine_cache["ssc_sepsis_hour1"]

        evaluator.evaluate(episode, ["order_lab_blood_culture"])
        engine_second = evaluator._engine_cache["ssc_sepsis_hour1"]
        assert engine_first is engine_second

    def test_different_guidelines_cached_separately(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        for gid in ["ssc_sepsis_hour1", "aha_chest_pain"]:
            episode = {
                "case_id": f"cache_{gid}",
                "guideline_id": gid,
                "patient_state": _sepsis_state(f"cache_{gid}"),
            }
            evaluator.evaluate(episode, ["assess_vital_signs"])
        assert len(evaluator._engine_cache) == 2
        assert evaluator._engine_cache["ssc_sepsis_hour1"] is not evaluator._engine_cache["aha_chest_pain"]

    def test_invalid_guideline_cached_as_none(self):
        config = ClosedLoopConfig(project_root=_project_root())
        evaluator = ClosedLoopEvaluator(config)
        episode = {
            "case_id": "bad",
            "guideline_id": "nonexistent_guideline_xyz",
            "patient_state": _sepsis_state("bad"),
        }
        evaluator.evaluate(episode, ["order_lab_lactate"])
        assert "nonexistent_guideline_xyz" in evaluator._engine_cache
        assert evaluator._engine_cache["nonexistent_guideline_xyz"] is None


class TestClosedLoopVsOneShot:
    def test_closed_loop_finds_more_violations(self):
        episode = {
            "case_id": "cmp_1",
            "guideline_id": "cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml",
            "patient_state": _sepsis_state("cmp_1"),
            "actions": [
                "give_broad_spectrum_antibiotics",
                "order_lab_blood_culture",
            ],
            "evidence": {
                "has_vitals": True,
                "has_test_results": True,
                "has_imaging_results": False,
                "has_medications": True,
                "has_physical_exam": True,
                "has_history": True,
                "has_diagnosis": True,
                "has_timestamps": True,
            },
        }

        one_shot = evaluate_normalized_episode(episode, _project_root())

        config = ClosedLoopConfig(project_root=_project_root())
        closed_loop = ClosedLoopEvaluator(config).evaluate(
            episode,
            ["give_broad_spectrum_antibiotics", "order_lab_blood_culture"],
        )

        assert len(closed_loop.sequence_violations) >= 1
        one_shot_sequence = [
            v for v in one_shot.violations if v.get("type") == "SEQUENCE"
        ]
        assert len(one_shot_sequence) == 0
