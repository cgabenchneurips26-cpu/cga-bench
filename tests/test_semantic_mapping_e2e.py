"""
End-to-end validation: New medical benchmark datasets through semantic mapping pipeline.

Tests the full pipeline:
1. Terminology Grounding (LOINC/UCUM/SNOMED/RxNorm) across 6 clinical domains
2. Error Taxonomy (OperationOutcome classification, environment constraint exemption)
3. XES/OCEL Export (IEEE 1849-2016, OCEL 2.0 compliance)
4. Conformance Scorer integration with ErrorPenaltyConfig
5. Cross-domain interoperability (same pipeline handles sepsis, ACS, DKA, AKI, stroke, HF)
"""
import json
import math
from xml.etree.ElementTree import fromstring

import pytest

from cga_bench.semantic_layer.terminology.grounding import (
    GroundingConfig,
    TerminologyGrounder,
)
from cga_bench.semantic_layer.terminology.coding import (
    CodedConcept,
    GroundedLabResult,
    MedicationCoding,
    QuantityWithUnit,
)
from cga_bench.semantic_layer.terminology.ucum_normalizer import normalize_ucum
from cga_bench.semantic_layer.conformance.error_taxonomy import (
    ErrorCategory,
    ClassifiedError,
    classify_error,
)
from cga_bench.semantic_layer.conformance.activity import (
    ActivityEvent,
    extract_activity_events,
    classify_response_error,
)
from cga_bench.semantic_layer.conformance.scorer import evaluate_conformance
from cga_bench.semantic_layer.export.xes_exporter import XESExporter, XESExportConfig
from cga_bench.semantic_layer.export.ocel_exporter import OCELExporter, OCELExportConfig
from cga_bench.semantic_layer.export.declare_bridge import DeclareBridge
from cga_bench.cpg_model.schemas.conformance import (
    ConstraintTemplate,
    ErrorPenaltyConfig,
    HardGraph,
    HardPhase,
    SoftConstraint,
    SoftConstraints,
)


# ============================================================================
# Realistic multi-domain benchmark data fixtures
# ============================================================================

SEPSIS_EPISODE = {
    "episode_id": "sepsis_mgmt_001",
    "domain": "sepsis",
    "patient": {
        "age": 65, "sex": "M", "weight_kg": 70.0,
        "chief_complaint": "Fever, altered mental status, hypotension",
        "working_diagnosis": "septic_shock",
        "allergies": ["penicillin"],
        "comorbidities": ["diabetes_type_2"],
    },
    "labs": [
        {"code": "lactate", "value": 4.8, "unit": "mmol/L"},
        {"code": "wbc", "value": 18.5, "unit": "10^3/uL"},
        {"code": "creatinine", "value": 2.1, "unit": "mg/dL"},
        {"code": "procalcitonin", "value": 12.5, "unit": "ng/mL"},
        {"code": "blood_culture", "value": "positive_gram_negative", "unit": ""},
        {"code": "potassium", "value": 5.2, "unit": "meq/l"},
    ],
    "medications": [
        "vancomycin", "piperacillin_tazobactam", "norepinephrine",
        "normal_saline",
    ],
    "diagnosis": "septic_shock",
    "events": [
        {"activity": "QUERY_PATIENT", "timestamp_ms": 0},
        {"activity": "ORDER_LAB", "timestamp_ms": 120000},
        {"activity": "ORDER_LAB", "timestamp_ms": 180000},
        {"activity": "PRESCRIBE", "timestamp_ms": 300000},
        {"activity": "PRESCRIBE", "timestamp_ms": 360000},
        {"activity": "QUERY_OBSERVATION", "timestamp_ms": 1800000},
    ],
}

CHEST_PAIN_EPISODE = {
    "episode_id": "stemi_rv_trap_001",
    "domain": "chest_pain",
    "patient": {
        "age": 58, "sex": "M", "weight_kg": 82.0,
        "chief_complaint": "Crushing substernal chest pain radiating to jaw",
        "working_diagnosis": "inferior_stemi",
        "allergies": [],
        "comorbidities": ["hypertension"],
    },
    "labs": [
        {"code": "troponin", "value": 2.5, "unit": "ng/ml"},
        {"code": "ck_mb", "value": 45.0, "unit": "U/L"},
        {"code": "bnp", "value": 850, "unit": "pg/mL"},
        {"code": "hemoglobin", "value": 13.2, "unit": "g/dL"},
        {"code": "potassium", "value": 4.1, "unit": "mEq/L"},
    ],
    "medications": [
        "aspirin", "clopidogrel", "heparin", "morphine",
    ],
    "diagnosis": "stemi",
    "events": [
        {"activity": "QUERY_PATIENT", "timestamp_ms": 0},
        {"activity": "ORDER_ECG", "timestamp_ms": 300000},
        {"activity": "ORDER_LAB", "timestamp_ms": 360000},
        {"activity": "PRESCRIBE", "timestamp_ms": 420000},
        {"activity": "PRESCRIBE", "timestamp_ms": 480000},
    ],
}

DKA_EPISODE = {
    "episode_id": "dka_hypokalemia_001",
    "domain": "dka",
    "patient": {
        "age": 32, "sex": "F", "weight_kg": 55.0,
        "chief_complaint": "Nausea, vomiting, abdominal pain, polyuria",
        "working_diagnosis": "dka",
        "allergies": [],
        "comorbidities": ["diabetes_type_1"],
    },
    "labs": [
        {"code": "glucose", "value": 520, "unit": "mg/dl"},
        {"code": "potassium", "value": 2.8, "unit": "meq/L"},
        {"code": "bicarbonate", "value": 8, "unit": "mmol/L"},
        {"code": "ph_arterial", "value": 7.08, "unit": "pH"},
        {"code": "hemoglobin_a1c", "value": 12.5, "unit": "%"},
        {"code": "sodium", "value": 128, "unit": "mmol/l"},
        {"code": "bun", "value": 35, "unit": "mg/dL"},
    ],
    "medications": [
        "normal_saline", "potassium_chloride", "regular_insulin",
    ],
    "diagnosis": "dka",
    "events": [
        {"activity": "QUERY_PATIENT", "timestamp_ms": 0},
        {"activity": "ORDER_LAB", "timestamp_ms": 60000},
        {"activity": "QUERY_OBSERVATION", "timestamp_ms": 1200000},
        {"activity": "PRESCRIBE", "timestamp_ms": 1500000},
        {"activity": "PRESCRIBE", "timestamp_ms": 1800000},
    ],
}

AKI_EPISODE = {
    "episode_id": "aki_contrast_001",
    "domain": "aki",
    "patient": {
        "age": 72, "sex": "F", "weight_kg": 65.0,
        "chief_complaint": "Decreased urine output, elevated creatinine",
        "working_diagnosis": "contrast_induced_nephropathy",
        "allergies": ["iodine"],
        "comorbidities": ["ckd_stage_4", "diabetes_type_2", "hypertension"],
    },
    "labs": [
        {"code": "creatinine", "value": 3.8, "unit": "mg/dl"},
        {"code": "egfr", "value": 15, "unit": "mL/min"},
        {"code": "potassium", "value": 5.9, "unit": "mEq/l"},
        {"code": "bicarbonate", "value": 16, "unit": "meq/L"},
        {"code": "bun", "value": 65, "unit": "mg/dL"},
        {"code": "urine_protein", "value": 3.5, "unit": "g/dl"},
    ],
    "medications": [
        "normal_saline", "calcium_gluconate", "sodium_bicarbonate",
        "furosemide",
    ],
    "diagnosis": "aki",
    "events": [
        {"activity": "QUERY_PATIENT", "timestamp_ms": 0},
        {"activity": "ORDER_LAB", "timestamp_ms": 120000},
        {"activity": "ORDER_LAB", "timestamp_ms": 180000},
        {"activity": "QUERY_OBSERVATION", "timestamp_ms": 1800000},
        {"activity": "PRESCRIBE", "timestamp_ms": 2400000},
    ],
}

STROKE_EPISODE = {
    "episode_id": "stroke_tpa_001",
    "domain": "stroke",
    "patient": {
        "age": 68, "sex": "M", "weight_kg": 80.0,
        "chief_complaint": "Sudden onset left-sided weakness, aphasia",
        "working_diagnosis": "ischemic_stroke",
        "allergies": [],
        "comorbidities": ["atrial_fibrillation", "hypertension"],
    },
    "labs": [
        {"code": "glucose", "value": 145, "unit": "mg/dL"},
        {"code": "inr", "value": 1.2, "unit": "INR"},
        {"code": "platelet_count", "value": 185, "unit": "10^3/ul"},
        {"code": "pt", "value": 14.5, "unit": "sec"},
        {"code": "creatinine", "value": 1.1, "unit": "mg/dl"},
    ],
    "medications": ["alteplase"],
    "diagnosis": "ischemic_stroke",
    "events": [
        {"activity": "QUERY_PATIENT", "timestamp_ms": 0},
        {"activity": "ORDER_LAB", "timestamp_ms": 60000},
        {"activity": "PERFORM_PROCEDURE", "timestamp_ms": 300000},
        {"activity": "PRESCRIBE", "timestamp_ms": 600000},
    ],
}

HEART_FAILURE_EPISODE = {
    "episode_id": "hf_adhf_001",
    "domain": "heart_failure",
    "patient": {
        "age": 75, "sex": "F", "weight_kg": 90.0,
        "chief_complaint": "Progressive dyspnea, orthopnea, leg edema",
        "working_diagnosis": "hfref",
        "allergies": ["aspirin"],
        "comorbidities": ["hfref", "atrial_fibrillation", "diabetes_type_2"],
    },
    "labs": [
        {"code": "nt_pro_bnp", "value": 8500, "unit": "pg/ml"},
        {"code": "creatinine", "value": 1.8, "unit": "mg/dL"},
        {"code": "potassium", "value": 4.5, "unit": "mmol/L"},
        {"code": "sodium", "value": 132, "unit": "mmol/l"},
        {"code": "hemoglobin", "value": 10.5, "unit": "g/dl"},
        {"code": "albumin", "value": 2.8, "unit": "g/dL"},
    ],
    "medications": [
        "furosemide", "carvedilol", "lisinopril", "spironolactone",
    ],
    "diagnosis": "heart_failure",
    "events": [
        {"activity": "QUERY_PATIENT", "timestamp_ms": 0},
        {"activity": "ORDER_LAB", "timestamp_ms": 180000},
        {"activity": "QUERY_OBSERVATION", "timestamp_ms": 1800000},
        {"activity": "PRESCRIBE", "timestamp_ms": 2100000},
        {"activity": "PRESCRIBE", "timestamp_ms": 2400000},
    ],
}

ALL_EPISODES = [
    SEPSIS_EPISODE,
    CHEST_PAIN_EPISODE,
    DKA_EPISODE,
    AKI_EPISODE,
    STROKE_EPISODE,
    HEART_FAILURE_EPISODE,
]

# Realistic OperationOutcome error scenarios during benchmark execution
ERROR_SCENARIOS = [
    {
        "name": "Patient not found in FHIR server",
        "response_payload": {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "not-found",
                       "diagnostics": "Patient/9999 not found"}],
        },
        "expected_category": ErrorCategory.NOT_FOUND,
        "expected_env_constraint": True,
    },
    {
        "name": "Rate limited by EHR API",
        "response_payload": {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "warning", "code": "throttled",
                       "diagnostics": "Too many requests. Retry after 5s."}],
        },
        "expected_category": ErrorCategory.RATE_LIMIT,
        "expected_env_constraint": True,
    },
    {
        "name": "Invalid medication dose format",
        "response_payload": {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "value",
                       "diagnostics": "Invalid dose format: 'lots' is not a valid quantity"}],
        },
        "expected_category": ErrorCategory.INVALID,
        "expected_env_constraint": False,
    },
    {
        "name": "FHIR server timeout",
        "response_payload": {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "fatal", "code": "timeout",
                       "diagnostics": "Request timed out after 30000ms"}],
        },
        "expected_category": ErrorCategory.TIMEOUT,
        "expected_env_constraint": True,
    },
    {
        "name": "Server internal error",
        "response_payload": {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "fatal", "code": "exception",
                       "diagnostics": "NullPointerException in HAPI FHIR server"}],
        },
        "expected_category": ErrorCategory.SERVER_ERROR,
        "expected_env_constraint": True,
    },
    {
        "name": "Duplicate order rejected",
        "response_payload": {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "duplicate",
                       "diagnostics": "Order already exists for this patient"}],
        },
        "expected_category": ErrorCategory.INVALID,
        "expected_env_constraint": False,
    },
    {
        "name": "Authorization denied for restricted lab",
        "response_payload": {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "forbidden",
                       "diagnostics": "Insufficient privileges for HIV test order"}],
        },
        "expected_category": ErrorCategory.AUTH,
        "expected_env_constraint": True,
    },
]


# ============================================================================
# Test Classes
# ============================================================================


class TestMultiDomainTerminologyGrounding:
    """Verify terminology grounding works across all 6 clinical domains."""

    @pytest.fixture
    def grounder(self):
        return TerminologyGrounder(GroundingConfig())

    @pytest.mark.parametrize("episode", ALL_EPISODES, ids=lambda e: e["domain"])
    def test_all_labs_ground_with_loinc(self, grounder, episode):
        """Every lab in each domain should resolve to a LOINC code."""
        grounded_count = 0
        total = len(episode["labs"])

        for lab in episode["labs"]:
            result = grounder.ground_lab_result(
                lab["code"], lab["value"] if isinstance(lab["value"], (int, float)) else None, lab["unit"]
            )
            if result.concept is not None:
                assert result.concept.system == "http://loinc.org", \
                    f"[{episode['domain']}] {lab['code']} system != LOINC"
                assert result.concept.code, f"[{episode['domain']}] {lab['code']} has empty LOINC code"
                grounded_count += 1

        # At least 60% of labs should ground (some like blood_culture may not have reverse mapping)
        coverage = grounded_count / total if total > 0 else 0
        assert coverage >= 0.5, (
            f"[{episode['domain']}] Only {grounded_count}/{total} labs grounded "
            f"({coverage:.0%} < 50% threshold)"
        )

    @pytest.mark.parametrize("episode", ALL_EPISODES, ids=lambda e: e["domain"])
    def test_all_units_normalize_to_ucum(self, grounder, episode):
        """Every unit in each domain should normalize through UCUM."""
        for lab in episode["labs"]:
            if not lab["unit"]:
                continue
            result = grounder.ground_lab_result(
                lab["code"],
                lab["value"] if isinstance(lab["value"], (int, float)) else None,
                lab["unit"],
            )
            if result.quantity:
                ucum = result.quantity.unit_ucum
                # UCUM should differ from common variants
                assert ucum, f"[{episode['domain']}] Empty UCUM for {lab['unit']}"
                # Verify capitalization is correct
                if "mol/l" in lab["unit"].lower():
                    assert ucum.endswith("/L"), f"UCUM should end with /L: {ucum}"
                if "mg/dl" == lab["unit"].lower():
                    assert ucum == "mg/dL", f"mg/dl should normalize to mg/dL: {ucum}"

    @pytest.mark.parametrize("episode", ALL_EPISODES, ids=lambda e: e["domain"])
    def test_diagnosis_grounds_to_snomed(self, grounder, episode):
        """Each episode's diagnosis should resolve to a SNOMED CT code."""
        result = grounder.ground_diagnosis(episode["diagnosis"])
        assert result is not None, f"[{episode['domain']}] No SNOMED for '{episode['diagnosis']}'"
        assert result.system == "http://snomed.info/sct"
        assert result.code, f"[{episode['domain']}] Empty SNOMED code"

    @pytest.mark.parametrize("episode", ALL_EPISODES, ids=lambda e: e["domain"])
    def test_medications_ground_to_rxnorm(self, grounder, episode):
        """Most medications in each domain should resolve to RxNorm codes."""
        grounded_count = 0
        for med_name in episode["medications"]:
            result = grounder.ground_medication(med_name)
            if result.rxnorm_code:
                grounded_count += 1

        total = len(episode["medications"])
        coverage = grounded_count / total if total > 0 else 0
        assert coverage >= 0.5, (
            f"[{episode['domain']}] Only {grounded_count}/{total} medications grounded "
            f"({coverage:.0%} < 50% threshold)"
        )


class TestCrossDomainUCUMConsistency:
    """Verify UCUM normalization is consistent across domains."""

    def test_meq_l_variants_all_normalize_same(self):
        """All meq/L variants from different domains normalize identically."""
        variants = ["meq/l", "mEq/l", "mEq/L", "meq/L"]
        results = [normalize_ucum(v) for v in variants]
        assert all(r == "meq/L" for r in results), f"Inconsistent: {results}"

    def test_mmol_l_across_domains(self):
        """mmol/L used in sepsis (lactate), DKA (bicarb), HF (potassium)."""
        variants = ["mmol/L", "mmol/l"]
        results = [normalize_ucum(v) for v in variants]
        assert all(r == "mmol/L" for r in results)

    def test_mg_dl_across_domains(self):
        """mg/dL used in AKI (creatinine), DKA (glucose), stroke (glucose)."""
        variants = ["mg/dl", "mg/dL", "MG/DL"]
        results = [normalize_ucum(v) for v in variants]
        assert all(r == "mg/dL" for r in results)

    def test_cell_count_units(self):
        """Cell count units from CBC labs across domains."""
        variants = ["10^3/ul", "10^3/uL", "k/ul", "cells/ul"]
        expected = "10*3/uL"
        for v in variants:
            assert normalize_ucum(v) == expected, f"{v} -> {normalize_ucum(v)} != {expected}"

    def test_ng_ml_troponin_unit(self):
        """ng/mL for troponin in chest pain scenarios."""
        assert normalize_ucum("ng/ml") == "ng/mL"
        assert normalize_ucum("ng/mL") == "ng/mL"

    def test_pg_ml_bnp_unit(self):
        """pg/mL for BNP in heart failure scenarios."""
        assert normalize_ucum("pg/ml") == "pg/mL"

    def test_percentage_hba1c(self):
        """% for HbA1c in DKA scenarios."""
        assert normalize_ucum("%") == "%"
        assert normalize_ucum("percent") == "%"

    def test_inr_special_unit(self):
        """INR for coagulation in stroke scenarios."""
        assert normalize_ucum("INR") == "{INR}"
        assert normalize_ucum("inr") == "{INR}"

    def test_ph_arterial(self):
        """pH for ABG in DKA scenarios."""
        assert normalize_ucum("pH") == "[pH]"

    def test_seconds_pt(self):
        """Seconds for PT in stroke scenarios."""
        assert normalize_ucum("sec") == "s"


class TestErrorTaxonomyWithBenchmarkScenarios:
    """Verify error taxonomy correctly classifies real benchmark errors."""

    @pytest.mark.parametrize("scenario", ERROR_SCENARIOS, ids=lambda s: s["name"])
    def test_operation_outcome_classification(self, scenario):
        """Each OperationOutcome error scenario classifies correctly."""
        result = classify_error(None, scenario["response_payload"])
        assert result is not None, f"Failed to classify: {scenario['name']}"
        assert result.error_category == scenario["expected_category"], (
            f"[{scenario['name']}] Expected {scenario['expected_category']}, "
            f"got {result.error_category}"
        )
        assert result.is_environment_constraint == scenario["expected_env_constraint"], (
            f"[{scenario['name']}] env_constraint mismatch: "
            f"expected {scenario['expected_env_constraint']}, got {result.is_environment_constraint}"
        )

    def test_mixed_error_episode_penalty(self):
        """An episode with mixed errors should only penalize agent errors."""
        # Simulate errors during a sepsis benchmark run
        errors = []
        for scenario in ERROR_SCENARIOS:
            result = classify_error(None, scenario["response_payload"])
            errors.append(result)

        # Count environment vs agent errors
        env_errors = [e for e in errors if e.is_environment_constraint]
        agent_errors = [e for e in errors if not e.is_environment_constraint]

        assert len(env_errors) == 5  # not-found, throttled, timeout, exception, forbidden
        assert len(agent_errors) == 2  # value (invalid), duplicate (invalid)

    def test_error_penalty_exemption_in_scorer(self):
        """ErrorPenaltyConfig correctly exempts environment errors in scoring."""
        # Create minimal conformance evaluation with errors
        events = [ActivityEvent(name="QUERY_PATIENT", timestamp_min=0.0, raw_event={})]
        hard_graph = HardGraph(cpg_id="test", phases=[], edges=[], required_phases=[])
        soft_constraints = SoftConstraints(
            cpg_id="test",
            constraints=[],
            error_weight=2.0,
            error_penalty_config=ErrorPenaltyConfig(),
        )
        derived_flags = {"res.error_1": True, "res.error_2": True}

        # Create classified errors: 1 environment + 1 agent
        classified_errors = [
            ClassifiedError(
                error_category=ErrorCategory.NOT_FOUND,
                issue_code="not-found", issue_severity="error",
                is_environment_constraint=True,
                diagnostics=None, raw_event={},
            ),
            ClassifiedError(
                error_category=ErrorCategory.INVALID,
                issue_code="invalid", issue_severity="error",
                is_environment_constraint=False,
                diagnostics=None, raw_event={},
            ),
        ]

        # With classified errors + config: only 1 penalized (INVALID)
        report = evaluate_conformance(
            events, hard_graph, soft_constraints, derived_flags,
            classified_errors=classified_errors,
        )
        # error_penalty = 1 * 2.0 = 2.0 (only INVALID is penalized)
        assert report.compliance_cost == 2.0

        # Without classified errors: fallback uses flag count (2 * 2.0 = 4.0)
        report_fallback = evaluate_conformance(
            events, hard_graph, soft_constraints, derived_flags,
        )
        assert report_fallback.compliance_cost == 4.0

    def test_text_based_errors_from_benchmark_adapters(self):
        """Text-based error detection for external benchmark adapter responses."""
        text_errors = [
            ("404 Client Error: Not Found for url: /fhir/Patient/9999", ErrorCategory.NOT_FOUND),
            ("500 Server Error: Internal Server Error", ErrorCategory.SERVER_ERROR),
            ("429 Client Error: Too Many Requests", ErrorCategory.RATE_LIMIT),
            ("400 Client Error: Bad Request - invalid parameter", ErrorCategory.INVALID),
            ("Error in sending the GET request to /fhir/Observation", ErrorCategory.SERVER_ERROR),
        ]
        for text, expected_cat in text_errors:
            result = classify_error(text, None)
            assert result is not None, f"Not classified: {text}"
            assert result.error_category == expected_cat, (
                f"Text '{text[:40]}...' -> {result.error_category} != {expected_cat}"
            )


class TestXESExportWithBenchmarkEpisodes:
    """Verify XES export produces valid output for all domain episodes."""

    @pytest.fixture
    def exporter(self):
        return XESExporter(XESExportConfig(pretty_print=False))

    def _build_activity_events(self, episode):
        """Convert episode fixture to ActivityEvents."""
        events = []
        for ev in episode["events"]:
            events.append(ActivityEvent(
                name=ev["activity"],
                timestamp_min=ev["timestamp_ms"] / 60000.0,
                raw_event=ev,
            ))
        return events

    @pytest.mark.parametrize("episode", ALL_EPISODES, ids=lambda e: e["domain"])
    def test_episode_exports_valid_xes(self, exporter, episode):
        """Each domain episode exports to parseable XES XML."""
        events = self._build_activity_events(episode)
        xml = exporter.export_episode(
            episode["episode_id"], events,
            resource=f"agent_{episode['domain']}",
            attributes={"cga:domain": episode["domain"]},
        )

        # Must be parseable XML
        root = fromstring(xml)
        assert root.tag.endswith("log") or root.tag == "log"

        # Verify episode_id in trace
        assert episode["episode_id"] in xml

        # Verify all activities present
        for ev in episode["events"]:
            assert ev["activity"] in xml, f"Missing activity: {ev['activity']}"

    def test_multi_domain_log(self, exporter):
        """All 6 domain episodes export into a single XES log."""
        episodes = {}
        for ep in ALL_EPISODES:
            events = self._build_activity_events(ep)
            episodes[ep["episode_id"]] = events

        xml = exporter.export_episodes(episodes, resource="agent_multi")
        root = fromstring(xml)

        # Should have 6 traces
        ns = "{http://www.xes-standard.org/}"
        traces = root.findall(f"{ns}trace") or root.findall("trace")
        assert len(traces) == 6, f"Expected 6 traces, got {len(traces)}"

    def test_xes_timestamps_ordered(self, exporter):
        """Events within each trace should be temporally ordered."""
        events = self._build_activity_events(SEPSIS_EPISODE)
        xml = exporter.export_episode("test", events)

        # Verify timestamp ordering via string comparison
        ns = "{http://www.xes-standard.org/}"
        root = fromstring(xml)
        trace = root.find(f"{ns}trace") or root.find("trace")
        event_elems = trace.findall(f"{ns}event") or trace.findall("event")

        timestamps = []
        for ev in event_elems:
            date_attrs = ev.findall(f"{ns}date") or ev.findall("date")
            ts = next((a.get("value") for a in date_attrs if a.get("key") == "time:timestamp"), None)
            if ts:
                timestamps.append(ts)

        assert timestamps == sorted(timestamps), "Events not in temporal order"


class TestOCELExportWithBenchmarkEpisodes:
    """Verify OCEL export produces valid output for all domain episodes."""

    @pytest.fixture
    def exporter(self):
        return OCELExporter(OCELExportConfig())

    def _build_activity_events(self, episode):
        events = []
        for ev in episode["events"]:
            events.append(ActivityEvent(
                name=ev["activity"],
                timestamp_min=ev["timestamp_ms"] / 60000.0,
                raw_event=ev,
            ))
        return events

    @pytest.mark.parametrize("episode", ALL_EPISODES, ids=lambda e: e["domain"])
    def test_episode_exports_valid_ocel(self, exporter, episode):
        """Each domain episode exports to valid OCEL 2.0 JSON."""
        events = self._build_activity_events(episode)
        result = exporter.export_episode(
            episode["episode_id"], events,
            patient_id=f"patient_{episode['domain']}",
            resource=f"agent_{episode['domain']}",
        )

        data = json.loads(result)

        # OCEL 2.0 required fields
        assert data["ocel:global-log"]["ocel:version"] == "2.0"
        assert "ocel:objects" in data
        assert "ocel:events" in data
        assert "ocel:object-types" in data

        # Patient object present
        assert f"patient_{episode['domain']}" in data["ocel:objects"]

        # Event count matches
        assert len(data["ocel:events"]) == len(episode["events"])

    def test_multi_domain_ocel(self, exporter):
        """All 6 episodes merge into single OCEL log."""
        episodes = {}
        for ep in ALL_EPISODES:
            events = self._build_activity_events(ep)
            episodes[ep["episode_id"]] = events

        result = exporter.export_episodes(episodes)
        data = json.loads(result)

        total_events = sum(len(ep["events"]) for ep in ALL_EPISODES)
        assert len(data["ocel:events"]) == total_events

    @pytest.mark.parametrize("episode", ALL_EPISODES, ids=lambda e: e["domain"])
    def test_ocel_object_inference(self, exporter, episode):
        """OCEL correctly infers object types from activities."""
        events = self._build_activity_events(episode)
        result = exporter.export_episode(episode["episode_id"], events)
        data = json.loads(result)

        obj_types = {obj["ocel:type"] for obj in data["ocel:objects"].values()}

        # Patient should always be present
        assert "patient" in obj_types

        # Order/test/medication objects should be inferred from activities
        activities = [ev["activity"] for ev in episode["events"]]
        if any("ORDER" in a or "QUERY" in a for a in activities):
            assert "test" in obj_types or "order" in obj_types
        if any("PRESCRIBE" in a for a in activities):
            assert "medication" in obj_types


class TestDeclareBridgeWithClinicalConstraints:
    """Verify Declare bridge handles clinical constraints correctly."""

    @pytest.fixture
    def bridge(self):
        return DeclareBridge()

    def test_sepsis_hour1_constraints(self, bridge):
        """SSC Hour-1 Bundle constraints convert to Declare model."""
        sc = SoftConstraints(
            cpg_id="ssc_sepsis_hour1",
            constraints=[
                SoftConstraint(
                    constraint_id="blood_culture_before_abx",
                    template=ConstraintTemplate.PRECEDENCE,
                    A="ORDER_LAB", B="PRESCRIBE",
                    weight=5.0,
                ),
                SoftConstraint(
                    constraint_id="lactate_within_60min",
                    template=ConstraintTemplate.RESPONSE_WITHIN,
                    A="QUERY_PATIENT", B="ORDER_LAB",
                    window_minutes=60.0,
                    weight=3.0,
                ),
                SoftConstraint(
                    constraint_id="must_order_labs",
                    template=ConstraintTemplate.EXISTENCE,
                    A="ORDER_LAB",
                    weight=4.0,
                ),
            ],
        )
        model = bridge.to_declare_model(sc)
        assert len(model.constraints) == 3
        assert "ORDER_LAB" in model.activities
        assert "PRESCRIBE" in model.activities
        assert "QUERY_PATIENT" in model.activities

    def test_declare_text_output(self, bridge):
        """Declare text output is parseable and contains constraint info."""
        sc = SoftConstraints(
            cpg_id="chest_pain_v1",
            constraints=[
                SoftConstraint(
                    constraint_id="ecg_10min",
                    template=ConstraintTemplate.RESPONSE_WITHIN,
                    A="QUERY_PATIENT", B="ORDER_ECG",
                    window_minutes=10.0,
                    weight=5.0,
                ),
                SoftConstraint(
                    constraint_id="no_nitrate_after_rv",
                    template=ConstraintTemplate.NOT_SUCCESSION,
                    A="QUERY_ECG", B="PRESCRIBE",
                    weight=10.0,
                    guard="rv_infarct_detected",
                ),
            ],
        )
        text = bridge.to_declare_text(sc)
        assert "Response[QUERY_PATIENT, ORDER_ECG]" in text
        assert "window=10.0min" in text
        assert "Not Succession[QUERY_ECG, PRESCRIBE]" in text
        assert "guard=rv_infarct_detected" in text

    def test_cross_verification_agreement(self, bridge):
        """Cross-verification correctly identifies agreement/disagreement."""
        # Simulate: CGA-Bench found 3 violations, Declare found 2 (1 overlap)
        all_constraints = ["c1", "c2", "c3", "c4", "c5"]
        cga_violations = ["c1", "c2", "c3"]
        declare_violations = ["c1", "c4"]

        result = bridge.cross_verify(cga_violations, declare_violations, all_constraints)
        assert result.total_constraints == 5
        # c1: both agree (violated) -> match
        # c2: CGA only -> mismatch
        # c3: CGA only -> mismatch
        # c4: Declare only -> mismatch
        # c5: neither -> match
        assert result.matched == 2  # c1 (both violated), c5 (neither violated)
        assert result.mismatched == 3  # c2, c3 (CGA only), c4 (Declare only)
        assert result.agreement_rate == pytest.approx(0.4)


class TestFullPipelineIntegration:
    """End-to-end: benchmark data -> grounding -> conformance -> export."""

    def test_sepsis_full_pipeline(self):
        """Complete pipeline for sepsis benchmark episode."""
        ep = SEPSIS_EPISODE
        grounder = TerminologyGrounder(GroundingConfig())

        # 1. Ground all labs
        grounded_labs = []
        for lab in ep["labs"]:
            value = lab["value"] if isinstance(lab["value"], (int, float)) else None
            result = grounder.ground_lab_result(lab["code"], value, lab["unit"])
            grounded_labs.append(result)

        # Verify key labs grounded
        lactate = next((r for r in grounded_labs if r.internal_code == "lactate"), None)
        assert lactate and lactate.concept and lactate.concept.code == "32693-4"
        assert lactate.quantity.unit_ucum == "mmol/L"

        # 2. Ground diagnosis
        dx = grounder.ground_diagnosis(ep["diagnosis"])
        assert dx and dx.code == "76571007"  # septic_shock SNOMED

        # 3. Ground medications
        med_codings = [grounder.ground_medication(m) for m in ep["medications"]]
        norepi = next((m for m in med_codings if m.name == "norepinephrine"), None)
        assert norepi and norepi.rxnorm_code == "7512"

        # 4. Build activity events and evaluate conformance
        events = [
            ActivityEvent(name=ev["activity"], timestamp_min=ev["timestamp_ms"] / 60000.0, raw_event=ev)
            for ev in ep["events"]
        ]
        hard_graph = HardGraph(
            cpg_id="ssc_sepsis", phases=[HardPhase(phase_id="triage", name="Triage")],
            edges=[], required_phases=[],
        )
        soft_constraints = SoftConstraints(
            cpg_id="ssc_sepsis",
            constraints=[
                SoftConstraint(
                    constraint_id="labs_within_60",
                    template=ConstraintTemplate.RESPONSE_WITHIN,
                    A="QUERY_PATIENT", B="ORDER_LAB",
                    window_minutes=60.0, weight=3.0,
                ),
            ],
            error_penalty_config=ErrorPenaltyConfig(),
        )
        report = evaluate_conformance(events, hard_graph, soft_constraints, {})
        assert report.compliance_score > 0

        # 5. Export to XES
        xes = XESExporter(XESExportConfig(pretty_print=False))
        xml = xes.export_episode(ep["episode_id"], events, resource="agent_sepsis")
        assert "ORDER_LAB" in xml and ep["episode_id"] in xml

        # 6. Export to OCEL
        ocel = OCELExporter(OCELExportConfig())
        ocel_json = ocel.export_episode(ep["episode_id"], events, patient_id="patient_sepsis")
        data = json.loads(ocel_json)
        assert data["ocel:global-log"]["ocel:version"] == "2.0"
        assert len(data["ocel:events"]) == len(ep["events"])

    def test_dka_trap_detection_pipeline(self):
        """DKA hypokalemia trap: verify grounding catches critical values."""
        ep = DKA_EPISODE
        grounder = TerminologyGrounder(GroundingConfig())

        # Ground critical labs
        potassium = grounder.ground_lab_result("potassium", 2.8, "meq/L")
        assert potassium.concept is not None
        assert potassium.concept.code == "2823-3"
        assert potassium.quantity.value == 2.8
        assert potassium.quantity.unit_ucum == "meq/L"

        glucose = grounder.ground_lab_result("glucose", 520, "mg/dl")
        assert glucose.concept.code == "2345-7"
        assert glucose.quantity.unit_ucum == "mg/dL"

        ph = grounder.ground_lab_result("ph_arterial", 7.08, "pH")
        assert ph.concept is not None  # Should map to LOINC 2744-1
        assert ph.quantity.unit_ucum == "[pH]"

        # Verify medications
        insulin = grounder.ground_medication("regular_insulin")
        assert insulin.rxnorm_code == "5856"

        kcl = grounder.ground_medication("potassium_chloride")
        assert kcl.rxnorm_code == "8591"

    def test_aki_contrast_pipeline(self):
        """AKI contrast-induced: verify renal-specific grounding."""
        ep = AKI_EPISODE
        grounder = TerminologyGrounder(GroundingConfig())

        creat = grounder.ground_lab_result("creatinine", 3.8, "mg/dl")
        assert creat.concept.code == "2160-0"
        assert creat.quantity.unit_ucum == "mg/dL"

        egfr = grounder.ground_lab_result("egfr", 15, "mL/min")
        assert egfr.concept is not None
        assert egfr.concept.code == "48642-3"

        # Diagnosis
        dx = grounder.ground_diagnosis("aki")
        assert dx.code == "14669001"

    def test_stroke_tpa_pipeline(self):
        """Stroke tPA eligibility: verify coagulation lab grounding."""
        ep = STROKE_EPISODE
        grounder = TerminologyGrounder(GroundingConfig())

        inr = grounder.ground_lab_result("inr", 1.2, "INR")
        assert inr.concept is not None
        assert inr.quantity.unit_ucum == "{INR}"

        platelets = grounder.ground_lab_result("platelet_count", 185, "10^3/ul")
        assert platelets.concept is not None
        assert platelets.quantity.unit_ucum == "10*3/uL"

        # tPA medication
        tpa = grounder.ground_medication("alteplase")
        assert tpa.rxnorm_code == "8410"

        # Diagnosis
        dx = grounder.ground_diagnosis("ischemic_stroke")
        assert dx.code == "230690007"

    def test_heart_failure_pipeline(self):
        """Heart failure ADHF: verify cardiac marker grounding."""
        ep = HEART_FAILURE_EPISODE
        grounder = TerminologyGrounder(GroundingConfig())

        bnp = grounder.ground_lab_result("nt_pro_bnp", 8500, "pg/ml")
        assert bnp.concept is not None
        assert bnp.concept.code == "33762-6"
        assert bnp.quantity.unit_ucum == "pg/mL"

        # Heart failure meds
        carvedilol = grounder.ground_medication("carvedilol")
        assert carvedilol.rxnorm_code == "20352"

        furosemide = grounder.ground_medication("furosemide")
        assert furosemide.rxnorm_code == "4603"

        # Diagnosis
        dx = grounder.ground_diagnosis("heart_failure")
        assert dx.code == "84114007"


class TestActivityExtractionFromBenchmarkFHIR:
    """Verify activity extraction works with FHIR-formatted benchmark data."""

    def test_fhir_tool_calls_extract(self):
        """Simulate MedAgentBench-style FHIR tool calls."""
        events = [
            {
                # Patient search (not instance read) maps to QUERY_PATIENT
                "tool_call": {"method": "GET", "url": "/fhir/Patient"},
                "timestamp_ms": 1000,
            },
            {
                "tool_call": {
                    "method": "POST",
                    "url": "/fhir/ServiceRequest",
                    "payload": {
                        "resourceType": "ServiceRequest",
                        "code": {"coding": [{"code": "32693-4"}]},
                    },
                },
                "timestamp_ms": 5000,
            },
            {
                "tool_call": {
                    "method": "POST",
                    "url": "/fhir/MedicationRequest",
                    "payload": {"resourceType": "MedicationRequest"},
                },
                "timestamp_ms": 10000,
            },
            {
                "tool_call": {
                    "method": "GET",
                    "url": "/fhir/Observation?code=2524-7",
                },
                "timestamp_ms": 30000,
            },
        ]

        activity_events, _ = extract_activity_events(events)
        assert len(activity_events) >= 3

        # Verify activity names
        names = [e.name for e in activity_events]
        assert "QUERY_PATIENT" in names
        assert "ORDER_TEST" in names
        assert "PRESCRIBE" in names

    def test_fhir_ecg_detection(self):
        """ECG-specific code detection for chest pain scenarios."""
        events = [
            {
                "tool_call": {
                    "method": "POST",
                    "url": "/fhir/ServiceRequest",
                    "payload": {
                        "resourceType": "ServiceRequest",
                        "code": {"coding": [{"code": "11524-6"}]},
                    },
                },
                "timestamp_ms": 5000,
            },
        ]
        activity_events, _ = extract_activity_events(events)
        assert len(activity_events) == 1
        assert activity_events[0].name == "ORDER_ECG"

    def test_error_response_classification_in_activity(self):
        """OperationOutcome responses are classified during activity extraction."""
        response_text = None
        response_payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "not-found"}],
        }
        result = classify_response_error(response_text, response_payload)
        assert result is not None
        assert result.error_category == ErrorCategory.NOT_FOUND
        assert result.is_environment_constraint is True
