"""Tests for scripts/ci/validate_scenario_plausibility.py — clinical plausibility validator."""

from __future__ import annotations

from scripts.ci.validate_scenario_plausibility import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    Finding,
    ValidationReport,
    check_chief_complaint,
    check_cohort_cpg_match,
    check_diagnosis_relevance,
    check_vitals_range,
    validate_scenarios,
)

# ---------------------------------------------------------------------------
# Fixtures: minimal builders
# ---------------------------------------------------------------------------


def _graph(
    graph_id: str = "test_graph",
    age_group: str = "adult",
    min_age: int = 18,
    max_age: int = 120,
    sex: str = "any",
    special_conditions: list[str] | None = None,
) -> dict:
    """Build a minimal CPG graph dict with target_population."""
    return {
        "graph_id": graph_id,
        "guideline_name": f"Test Guideline {graph_id}",
        "entry_node": "n1",
        "metadata": {
            "target_population": {
                "age_group": age_group,
                "min_age": min_age,
                "max_age": max_age,
                "sex": sex,
                "special_conditions": special_conditions or [],
            },
        },
        "nodes": {
            "n1": {
                "node_id": "n1",
                "node_type": "plan",
                "mandatory_actions": [],
                "allowed_actions": [],
                "forbidden_actions": [],
                "deadlines": {},
                "next_nodes": [],
                "conditional_next": {},
            }
        },
    }


def _scenario(
    age: int = 45,
    sex: str = "M",
    guideline_graph: str = "test_graph",
    vitals: dict | None = None,
    chief_complaint: str = "chest pain",
    working_diagnosis: str = "acute coronary syndrome",
) -> dict:
    """Build a minimal scenario dict."""
    return {
        "guideline_graph": guideline_graph,
        "patient": {
            "age": age,
            "sex": sex,
            "chief_complaint": chief_complaint,
            "working_diagnosis": working_diagnosis,
            "vitals": vitals
            or {
                "heart_rate": 90,
                "blood_pressure_systolic": 130,
                "blood_pressure_diastolic": 80,
                "respiratory_rate": 18,
                "temperature": 37.0,
                "oxygen_saturation": 97,
            },
        },
    }


# ---------------------------------------------------------------------------
# Rule A: Cohort x CPG match
# ---------------------------------------------------------------------------


class TestCohortCPGMatch:
    """Tests for check_cohort_cpg_match (Rule A)."""

    def test_adult_in_adult_graph_passes(self) -> None:
        graph = _graph(age_group="adult", min_age=18, max_age=120)
        scenario = _scenario(age=45, sex="M")
        findings = check_cohort_cpg_match("s1", scenario, graph)
        assert not any(f.severity == SEVERITY_ERROR for f in findings)

    def test_neonate_in_neonatal_graph_passes(self) -> None:
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(age=0, sex="F")
        findings = check_cohort_cpg_match("s1", scenario, graph)
        assert not any(f.severity == SEVERITY_ERROR for f in findings)

    def test_adult_in_neonatal_graph_fails(self) -> None:
        """72yo male in neonatal resuscitation = catastrophic mismatch."""
        graph = _graph(graph_id="ilcor_neonatal", age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(age=72, sex="M")
        findings = check_cohort_cpg_match("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert "above graph max_age" in errors[0].message

    def test_child_in_adult_graph_fails(self) -> None:
        graph = _graph(age_group="adult", min_age=18, max_age=120)
        scenario = _scenario(age=8, sex="M")
        findings = check_cohort_cpg_match("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert "below graph min_age" in errors[0].message

    def test_male_in_female_only_graph_fails(self) -> None:
        """Male patient in maternal sepsis protocol = catastrophic."""
        graph = _graph(graph_id="smfm_maternal", sex="female_only", min_age=15, max_age=50)
        scenario = _scenario(age=30, sex="M")
        findings = check_cohort_cpg_match("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert "female_only" in errors[0].message

    def test_female_in_female_only_graph_passes(self) -> None:
        graph = _graph(sex="female_only", min_age=15, max_age=50)
        scenario = _scenario(age=30, sex="F")
        findings = check_cohort_cpg_match("s1", scenario, graph)
        assert not any(f.severity == SEVERITY_ERROR for f in findings)

    def test_any_sex_passes_both(self) -> None:
        graph = _graph(sex="any")
        for sex in ("M", "F"):
            findings = check_cohort_cpg_match("s1", _scenario(sex=sex), graph)
            assert not any(f.severity == SEVERITY_ERROR for f in findings)

    def test_missing_graph_returns_warning(self) -> None:
        scenario = _scenario()
        findings = check_cohort_cpg_match("s1", scenario, None)
        assert len(findings) == 1
        assert findings[0].severity == SEVERITY_WARNING
        assert "not found" in findings[0].message

    def test_no_population_metadata_skips(self) -> None:
        graph = {"graph_id": "test", "metadata": {}, "nodes": {}}
        findings = check_cohort_cpg_match("s1", _scenario(), graph)
        assert len(findings) == 0

    def test_pediatric_age_boundary(self) -> None:
        """17yo should pass pediatric (max_age=17), 18yo should fail."""
        graph = _graph(age_group="pediatric", min_age=0, max_age=17)
        f17 = check_cohort_cpg_match("s1", _scenario(age=17), graph)
        assert not any(f.severity == SEVERITY_ERROR for f in f17)

        f18 = check_cohort_cpg_match("s1", _scenario(age=18), graph)
        errors = [f for f in f18 if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1

    def test_empty_sex_on_female_only_graph_warns(self) -> None:
        """Empty sex string on sex-constrained graph must not silently pass."""
        graph = _graph(sex="female_only", min_age=15, max_age=50)
        scenario = _scenario(age=30, sex="")
        findings = check_cohort_cpg_match("s1", scenario, graph)
        warnings = [f for f in findings if f.severity == SEVERITY_WARNING]
        assert any("missing" in w.message for w in warnings)

    def test_missing_sex_key_on_female_only_graph_warns(self) -> None:
        """Scenario with no sex key at all on sex-constrained graph."""
        graph = _graph(sex="female_only")
        scenario = {"guideline_graph": "test", "patient": {"age": 30}}
        findings = check_cohort_cpg_match("s1", scenario, graph)
        warnings = [f for f in findings if f.severity == SEVERITY_WARNING]
        assert any("missing" in w.message for w in warnings)

    def test_missing_age_on_age_constrained_graph_warns(self) -> None:
        """Scenario with no age on neonatal graph should warn."""
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        scenario = {"guideline_graph": "test", "patient": {"sex": "F"}}
        findings = check_cohort_cpg_match("s1", scenario, graph)
        warnings = [f for f in findings if f.severity == SEVERITY_WARNING]
        assert any("age missing" in w.message.lower() for w in warnings)

    def test_female_in_male_only_graph_fails(self) -> None:
        graph = _graph(sex="male_only")
        scenario = _scenario(age=45, sex="F")
        findings = check_cohort_cpg_match("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# Rule B: Vitals physiological range
# ---------------------------------------------------------------------------


class TestVitalsRange:
    """Tests for check_vitals_range (Rule B)."""

    def test_normal_adult_vitals_pass(self) -> None:
        graph = _graph(age_group="adult")
        scenario = _scenario(
            vitals={
                "heart_rate": 80,
                "blood_pressure_systolic": 120,
                "blood_pressure_diastolic": 80,
                "respiratory_rate": 16,
                "temperature": 37.0,
                "oxygen_saturation": 98,
            }
        )
        findings = check_vitals_range("s1", scenario, graph)
        assert len(findings) == 0

    def test_adult_hr_too_low(self) -> None:
        graph = _graph(age_group="adult")
        scenario = _scenario(vitals={"heart_rate": 25})
        findings = check_vitals_range("s1", scenario, graph)
        warnings = [f for f in findings if "heart_rate" in f.message]
        assert len(warnings) == 1
        assert "outside" in warnings[0].message

    def test_adult_hr_too_high(self) -> None:
        graph = _graph(age_group="adult")
        scenario = _scenario(vitals={"heart_rate": 250})
        findings = check_vitals_range("s1", scenario, graph)
        warnings = [f for f in findings if "heart_rate" in f.message]
        assert len(warnings) == 1

    def test_neonatal_hr_140_passes(self) -> None:
        """HR=140 is normal for neonates but would be abnormal for adults."""
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(vitals={"heart_rate": 140})
        findings = check_vitals_range("s1", scenario, graph)
        assert not any("heart_rate" in f.message for f in findings)

    def test_neonatal_sbp_120_fails(self) -> None:
        """SBP=120 is way too high for a neonate."""
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(vitals={"blood_pressure_systolic": 120})
        findings = check_vitals_range("s1", scenario, graph)
        warnings = [f for f in findings if "blood_pressure_systolic" in f.message]
        assert len(warnings) == 1

    def test_short_vitals_keys_work(self) -> None:
        """Validator should handle both 'hr' and 'heart_rate' aliases."""
        graph = _graph(age_group="adult")
        scenario = _scenario(vitals={"hr": 25})
        findings = check_vitals_range("s1", scenario, graph)
        warnings = [f for f in findings if "heart_rate" in f.message]
        assert len(warnings) == 1

    def test_map_consistency_pass(self) -> None:
        """MAP = DBP + (SBP-DBP)/3 = 80 + 40/3 ~ 93.3"""
        graph = _graph()
        scenario = _scenario(
            vitals={
                "blood_pressure_systolic": 120,
                "blood_pressure_diastolic": 80,
                "map_mmhg": 93,
            }
        )
        findings = check_vitals_range("s1", scenario, graph)
        assert not any("MAP" in f.message for f in findings)

    def test_map_consistency_fail(self) -> None:
        """MAP should be ~93, but given as 60 -> inconsistency."""
        graph = _graph()
        scenario = _scenario(
            vitals={
                "blood_pressure_systolic": 120,
                "blood_pressure_diastolic": 80,
                "map_mmhg": 60,
            }
        )
        findings = check_vitals_range("s1", scenario, graph)
        warnings = [f for f in findings if "MAP" in f.message]
        assert len(warnings) == 1

    def test_empty_vitals_no_findings(self) -> None:
        scenario = _scenario(vitals={})
        findings = check_vitals_range("s1", scenario, None)
        assert len(findings) == 0

    def test_pediatric_bounds_used(self) -> None:
        """Pediatric SBP upper bound is 180; 200 should flag."""
        graph = _graph(age_group="pediatric", min_age=0, max_age=17)
        scenario = _scenario(vitals={"blood_pressure_systolic": 200})
        findings = check_vitals_range("s1", scenario, graph)
        warnings = [f for f in findings if "blood_pressure_systolic" in f.message]
        assert len(warnings) == 1

    def test_dbp_above_sbp_error(self) -> None:
        """DBP >= SBP is physiologically impossible."""
        graph = _graph(age_group="adult")
        scenario = _scenario(
            vitals={
                "blood_pressure_systolic": 80,
                "blood_pressure_diastolic": 120,
            }
        )
        findings = check_vitals_range("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR and "DBP" in f.message]
        assert len(errors) == 1

    def test_dbp_equals_sbp_error(self) -> None:
        graph = _graph(age_group="adult")
        scenario = _scenario(
            vitals={
                "blood_pressure_systolic": 100,
                "blood_pressure_diastolic": 100,
            }
        )
        findings = check_vitals_range("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR and "DBP" in f.message]
        assert len(errors) == 1

    def test_catastrophic_vitals_escalated_to_error(self) -> None:
        """Value far beyond range (more than 1x range span) -> ERROR not WARNING."""
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        # Neonatal SBP range is [25, 100], span=75. SBP=300 is 200 beyond -> catastrophic
        scenario = _scenario(vitals={"blood_pressure_systolic": 300})
        findings = check_vitals_range("s1", scenario, graph)
        sbp_findings = [f for f in findings if "blood_pressure_systolic" in f.message]
        assert len(sbp_findings) == 1
        assert sbp_findings[0].severity == SEVERITY_ERROR

    def test_mild_out_of_range_stays_warning(self) -> None:
        """Value slightly outside range -> WARNING."""
        graph = _graph(age_group="adult")
        # Adult HR range [30, 220]. HR=25 is only 5 below in a range of 190 -> not catastrophic
        scenario = _scenario(vitals={"heart_rate": 25})
        findings = check_vitals_range("s1", scenario, graph)
        hr_findings = [f for f in findings if "heart_rate" in f.message]
        assert len(hr_findings) == 1
        assert hr_findings[0].severity == SEVERITY_WARNING

    def test_neonatal_weight_85kg_error(self) -> None:
        """85kg neonate is physiologically impossible."""
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(age=0, vitals={})
        scenario["patient"]["weight_kg"] = 85
        findings = check_vitals_range("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR and "Weight" in f.message]
        assert len(errors) == 1

    def test_adult_weight_75kg_passes(self) -> None:
        """75kg adult is normal."""
        graph = _graph(age_group="adult")
        scenario = _scenario(vitals={})
        scenario["patient"]["weight_kg"] = 75
        findings = check_vitals_range("s1", scenario, graph)
        assert not any("Weight" in f.message for f in findings)

    def test_neonatal_weight_3kg_passes(self) -> None:
        """3kg neonate is normal."""
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(age=0, vitals={})
        scenario["patient"]["weight_kg"] = 3.0
        findings = check_vitals_range("s1", scenario, graph)
        assert not any("Weight" in f.message for f in findings)


# ---------------------------------------------------------------------------
# Rule C: Working diagnosis relevance
# ---------------------------------------------------------------------------


class TestDiagnosisRelevance:
    """Tests for check_diagnosis_relevance (Rule C)."""

    def test_generic_diagnosis_warns(self) -> None:
        scenario = _scenario(working_diagnosis="general")
        findings = check_diagnosis_relevance("s1", scenario, None)
        assert len(findings) == 1
        assert findings[0].severity == SEVERITY_WARNING
        assert "generic" in findings[0].message

    def test_missing_diagnosis_warns(self) -> None:
        scenario = _scenario(working_diagnosis="")
        findings = check_diagnosis_relevance("s1", scenario, None)
        assert len(findings) == 1
        assert findings[0].severity == SEVERITY_WARNING

    def test_specific_diagnosis_no_mismatch(self) -> None:
        graph = _graph(graph_id="ssc_sepsis_hour1")
        scenario = _scenario(working_diagnosis="sepsis")
        findings = check_diagnosis_relevance("s1", scenario, graph)
        assert not any(f.severity == SEVERITY_ERROR for f in findings)

    def test_cross_domain_mismatch_sepsis_on_stroke(self) -> None:
        graph = _graph(graph_id="aha_stroke")
        scenario = _scenario(working_diagnosis="sepsis with shock")
        findings = check_diagnosis_relevance("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert "Cross-domain" in errors[0].message

    def test_pe_on_sepsis_graph_flags_error(self) -> None:
        graph = _graph(graph_id="ssc_sepsis_hour1")
        scenario = _scenario(working_diagnosis="pulmonary embolism")
        findings = check_diagnosis_relevance("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1

    def test_normal_match_no_error(self) -> None:
        """DKA on DKA graph should not flag."""
        graph = _graph(graph_id="ada_dka_management")
        scenario = _scenario(working_diagnosis="diabetic ketoacidosis")
        findings = check_diagnosis_relevance("s1", scenario, graph)
        assert not any(f.severity == SEVERITY_ERROR for f in findings)

    def test_underscore_diagnosis_pe_on_sepsis_flags(self) -> None:
        """CRITICAL-1 fix: underscore-format 'pulmonary_embolism' must be caught."""
        graph = _graph(graph_id="ssc_sepsis_hour1")
        scenario = _scenario(working_diagnosis="pulmonary_embolism")
        findings = check_diagnosis_relevance("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1

    def test_underscore_diagnosis_sepsis_on_stroke_flags(self) -> None:
        graph = _graph(graph_id="aha_stroke")
        scenario = _scenario(working_diagnosis="sepsis_with_shock")
        findings = check_diagnosis_relevance("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1

    def test_anaphylaxis_on_stroke_graph_flags(self) -> None:
        """Expanded domain coverage: anaphylaxis on stroke graph."""
        graph = _graph(graph_id="aha_stroke")
        scenario = _scenario(working_diagnosis="anaphylaxis")
        findings = check_diagnosis_relevance("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1

    def test_heart_failure_on_own_graph_no_error(self) -> None:
        graph = _graph(graph_id="aha_heart_failure")
        scenario = _scenario(working_diagnosis="heart failure")
        findings = check_diagnosis_relevance("s1", scenario, graph)
        assert not any(f.severity == SEVERITY_ERROR for f in findings)


# ---------------------------------------------------------------------------
# Rule D: Chief complaint
# ---------------------------------------------------------------------------


class TestChiefComplaint:
    """Tests for check_chief_complaint (Rule D)."""

    def test_specific_complaint_passes(self) -> None:
        scenario = _scenario(chief_complaint="chest pain radiating to left arm")
        findings = check_chief_complaint("s1", scenario, None)
        assert len(findings) == 0

    def test_generic_complaint_warns(self) -> None:
        scenario = _scenario(chief_complaint="presenting symptoms")
        findings = check_chief_complaint("s1", scenario, None)
        assert len(findings) == 1
        assert findings[0].severity == SEVERITY_WARNING

    def test_empty_complaint_warns(self) -> None:
        scenario = _scenario(chief_complaint="")
        findings = check_chief_complaint("s1", scenario, None)
        assert len(findings) == 1
        assert findings[0].severity == SEVERITY_WARNING

    def test_neonatal_chest_pain_error(self) -> None:
        """Chest pain is impossible for neonates."""
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(chief_complaint="chest pain")
        findings = check_chief_complaint("s1", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) == 1
        assert "neonatal" in errors[0].message

    def test_neonatal_respiratory_distress_passes(self) -> None:
        """Respiratory distress is a valid neonatal complaint."""
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(chief_complaint="respiratory distress at birth")
        findings = check_chief_complaint("s1", scenario, graph)
        assert not any(f.severity == SEVERITY_ERROR for f in findings)

    def test_adult_chest_pain_no_error(self) -> None:
        graph = _graph(age_group="adult")
        scenario = _scenario(chief_complaint="chest pain")
        findings = check_chief_complaint("s1", scenario, graph)
        assert not any(f.severity == SEVERITY_ERROR for f in findings)


# ---------------------------------------------------------------------------
# Catastrophic scenario detection (integration-like)
# ---------------------------------------------------------------------------


class TestCatastrophicScenarios:
    """Verify the 8 known catastrophic scenario patterns are caught."""

    def test_72yo_male_in_neonatal_resuscitation(self) -> None:
        graph = _graph(graph_id="ilcor_neonatal_resuscitation_2020", age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(age=72, sex="M")
        findings = check_cohort_cpg_match("neo_001", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1

    def test_65yo_male_in_maternal_sepsis(self) -> None:
        graph = _graph(
            graph_id="smfm_maternal_sepsis_2019",
            age_group="adult",
            sex="female_only",
            min_age=15,
            max_age=50,
        )
        scenario = _scenario(age=65, sex="M")
        findings = check_cohort_cpg_match("mat_001", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        # Should flag: sex=M vs female_only AND age=65 vs max_age=50
        assert len(errors) >= 2

    def test_78yo_male_in_pediatric_sepsis(self) -> None:
        graph = _graph(
            graph_id="sccm_pediatric_septic_shock_2020",
            age_group="pediatric",
            min_age=0,
            max_age=17,
        )
        scenario = _scenario(age=78, sex="M")
        findings = check_cohort_cpg_match("ped_001", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1

    def test_adult_vitals_on_neonatal_scenario(self) -> None:
        """Adult SBP=130 on neonatal graph should flag vitals warning."""
        graph = _graph(age_group="neonatal", min_age=0, max_age=1)
        scenario = _scenario(
            age=0,
            vitals={
                "blood_pressure_systolic": 130,
                "heart_rate": 80,
            },
        )
        findings = check_vitals_range("neo_vitals", scenario, graph)
        warnings = [f for f in findings if "blood_pressure_systolic" in f.message]
        assert len(warnings) >= 1

    def test_male_in_breast_cancer_graph(self) -> None:
        graph = _graph(
            graph_id="asco_breast_cancer_adjuvant_2024",
            sex="female_only",
            min_age=18,
            max_age=120,
        )
        scenario = _scenario(age=55, sex="M")
        findings = check_cohort_cpg_match("onco_001", scenario, graph)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert "female_only" in errors[0].message


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------


class TestValidationReport:
    """Tests for ValidationReport aggregation."""

    def test_empty_report(self) -> None:
        report = ValidationReport()
        assert report.error_count == 0
        assert report.warning_count == 0
        d = report.to_dict()
        assert d["total_findings"] == 0

    def test_mixed_findings(self) -> None:
        report = ValidationReport(
            findings=[
                Finding("s1", "A_cohort_cpg", SEVERITY_ERROR, "age mismatch"),
                Finding("s1", "B_vitals_range", SEVERITY_WARNING, "HR high"),
                Finding("s2", "A_cohort_cpg", SEVERITY_ERROR, "sex mismatch"),
            ]
        )
        assert report.error_count == 2
        assert report.warning_count == 1
        d = report.to_dict()
        assert d["errors"] == 2
        assert d["warnings"] == 1
        assert d["total_findings"] == 3


# ---------------------------------------------------------------------------
# validate_scenarios integration
# ---------------------------------------------------------------------------


class TestValidateScenarios:
    """Tests for the top-level validate_scenarios function."""

    def test_clean_scenarios_zero_errors(self) -> None:
        """Well-formed scenarios should produce 0 ERRORs."""
        graph_index = {
            "ssc_sepsis_hour1": _graph(graph_id="ssc_sepsis_hour1"),
        }
        scenarios = {
            "sepsis_001": _scenario(
                age=55,
                sex="M",
                guideline_graph="ssc_sepsis_hour1",
                chief_complaint="fever and hypotension",
                working_diagnosis="sepsis",
            ),
        }
        report = validate_scenarios(scenarios, graph_index)
        assert report.error_count == 0

    def test_catastrophic_mismatch_flagged(self) -> None:
        """72yo male on neonatal graph -> at least 1 ERROR."""
        graph_index = {
            "ilcor_neonatal": _graph(
                graph_id="ilcor_neonatal",
                age_group="neonatal",
                min_age=0,
                max_age=1,
            ),
        }
        scenarios = {
            "neo_bad": _scenario(
                age=72,
                sex="M",
                guideline_graph="ilcor_neonatal",
                chief_complaint="chest pain",
            ),
        }
        report = validate_scenarios(scenarios, graph_index)
        assert report.error_count >= 1

    def test_multiple_scenarios_accumulated(self) -> None:
        graph_index = {
            "g1": _graph(graph_id="g1", sex="female_only"),
            "g2": _graph(graph_id="g2_coronary_unit"),
        }
        scenarios = {
            "s1": _scenario(sex="M", guideline_graph="g1"),  # ERROR: male on female_only
            "s2": _scenario(sex="F", guideline_graph="g2_coronary_unit"),  # OK
        }
        report = validate_scenarios(scenarios, graph_index)
        assert report.error_count >= 1
        error_ids = {f.scenario_id for f in report.findings if f.severity == SEVERITY_ERROR}
        assert "s1" in error_ids
        assert "s2" not in error_ids
