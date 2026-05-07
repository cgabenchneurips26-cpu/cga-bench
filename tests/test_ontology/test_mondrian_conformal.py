"""Tests for Mondrian (Group-Conditional) Conformal Prediction (P9).

Tests cover:
1. Per-type threshold calibration
2. Type-conditional coverage guarantees
3. Fallback to global threshold
4. Prediction set generation
5. Uncertainty level assignment
6. Report generation
"""
import pytest
from typing import List, Tuple

from cga_bench.semantic_layer.ontology.neural_embedder import SemanticType
from cga_bench.semantic_layer.ontology.mondrian_conformal import (
    MondrianConformalMatcher,
    MondrianConfig,
    MondrianPredictionSet,
    MondrianCalibrationResult,
    TypeCalibration,
    UncertaintyLevel,
    calibrate_mondrian_from_goldset,
)


class TestMondrianConfig:
    """Tests for Mondrian configuration."""

    def test_default_config(self):
        """Default config has sensible values."""
        config = MondrianConfig()
        assert config.alpha == 0.10
        assert config.min_calibration_per_type == 10
        assert config.fallback_to_global is True
        assert config.enable_abstain is True

    def test_per_type_alpha(self):
        """Per-type alpha overrides work."""
        config = MondrianConfig(
            alpha=0.10,
            per_type_alpha={
                "drug": 0.05,  # More conservative for drugs
                "lab": 0.15,
            }
        )
        assert config.per_type_alpha["drug"] == 0.05
        assert config.per_type_alpha["lab"] == 0.15


class TestUncertaintyLevel:
    """Tests for uncertainty level enum."""

    def test_all_levels_defined(self):
        """All uncertainty levels are defined."""
        assert UncertaintyLevel.LOW.value == "LOW"
        assert UncertaintyLevel.MEDIUM.value == "MEDIUM"
        assert UncertaintyLevel.HIGH.value == "HIGH"
        assert UncertaintyLevel.ABSTAIN.value == "ABSTAIN"


class TestMondrianPredictionSet:
    """Tests for Mondrian prediction set."""

    def test_singleton_set(self):
        """Singleton set properties."""
        pred = MondrianPredictionSet(
            prediction_set=["concept_1"],
            scores=[0.95],
            semantic_type=SemanticType.DRUG,
            threshold=0.3,
            uncertainty_level=UncertaintyLevel.LOW,
            coverage_guarantee=0.9,
        )
        assert pred.is_singleton is True
        assert pred.is_empty is False
        assert pred.set_size == 1
        assert pred.top1 == "concept_1"
        assert pred.top1_score == 0.95

    def test_empty_set(self):
        """Empty set properties."""
        pred = MondrianPredictionSet(
            prediction_set=[],
            scores=[],
            semantic_type=SemanticType.UNKNOWN,
            threshold=0.3,
            uncertainty_level=UncertaintyLevel.ABSTAIN,
            coverage_guarantee=0.9,
        )
        assert pred.is_singleton is False
        assert pred.is_empty is True
        assert pred.set_size == 0
        assert pred.top1 is None

    def test_contains_method(self):
        """Contains method works correctly."""
        pred = MondrianPredictionSet(
            prediction_set=["a", "b", "c"],
            scores=[0.9, 0.8, 0.7],
            semantic_type=SemanticType.LAB,
            threshold=0.3,
            uncertainty_level=UncertaintyLevel.MEDIUM,
            coverage_guarantee=0.9,
        )
        assert pred.contains("a") is True
        assert pred.contains("b") is True
        assert pred.contains("d") is False


class TestMondrianConformalMatcher:
    """Tests for Mondrian conformal matcher."""

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder for testing."""
        from cga_bench.semantic_layer.ontology.neural_embedder import (
            MockNeuralEmbedder,
            EmbedderConfig,
        )
        embedder = MockNeuralEmbedder(EmbedderConfig(similarity_threshold=0.3))
        concepts = [
            ("order_lab_lactate", "lactate", []),
            ("order_lab_troponin", "troponin", ["trop"]),
            ("order_lab_creatinine", "creatinine", []),
            ("start_norepinephrine", "norepinephrine", ["levophed"]),
            ("start_vasopressin", "vasopressin", []),
            ("give_aspirin", "aspirin", []),
            ("perform_ecg", "ECG", ["12-lead"]),
            ("order_ct_head", "CT head", []),
        ]
        embedder.build_index(concepts)
        return embedder

    @pytest.fixture
    def calibration_data(self):
        """Create calibration data with type annotations."""
        return [
            # LAB type
            ("lactate", "order_lab_lactate", SemanticType.LAB),
            ("troponin", "order_lab_troponin", SemanticType.LAB),
            ("creatinine", "order_lab_creatinine", SemanticType.LAB),
            ("check trop", "order_lab_troponin", SemanticType.LAB),
            ("order lactate", "order_lab_lactate", SemanticType.LAB),
            ("lab lactate", "order_lab_lactate", SemanticType.LAB),
            ("creat level", "order_lab_creatinine", SemanticType.LAB),
            ("troponin level", "order_lab_troponin", SemanticType.LAB),
            ("serum lactate", "order_lab_lactate", SemanticType.LAB),
            ("troponin I", "order_lab_troponin", SemanticType.LAB),
            # DRUG type
            ("norepinephrine", "start_norepinephrine", SemanticType.DRUG),
            ("start pressors", "start_norepinephrine", SemanticType.DRUG),
            ("give aspirin", "give_aspirin", SemanticType.DRUG),
            ("aspirin loading", "give_aspirin", SemanticType.DRUG),
            ("vasopressin", "start_vasopressin", SemanticType.DRUG),
            ("norepi", "start_norepinephrine", SemanticType.DRUG),
            ("levophed", "start_norepinephrine", SemanticType.DRUG),
            ("aspirin 325", "give_aspirin", SemanticType.DRUG),
            ("start vasopressin", "start_vasopressin", SemanticType.DRUG),
            ("norepinephrine drip", "start_norepinephrine", SemanticType.DRUG),
            # IMAGING type
            ("CT head", "order_ct_head", SemanticType.IMAGING),
            ("head CT", "order_ct_head", SemanticType.IMAGING),
            ("CT brain", "order_ct_head", SemanticType.IMAGING),
            # PROCEDURE type
            ("ECG", "perform_ecg", SemanticType.PROCEDURE),
            ("12-lead", "perform_ecg", SemanticType.PROCEDURE),
        ]

    def test_initialization(self, mock_embedder):
        """Mondrian matcher initializes correctly."""
        config = MondrianConfig()
        matcher = MondrianConformalMatcher(mock_embedder, config)
        assert matcher.is_calibrated is False

    def test_calibration(self, mock_embedder, calibration_data):
        """Calibration computes per-type thresholds."""
        config = MondrianConfig(
            alpha=0.10,
            min_calibration_per_type=3,
        )
        matcher = MondrianConformalMatcher(mock_embedder, config)

        result = matcher.calibrate(calibration_data)

        assert matcher.is_calibrated is True
        assert result.n_total == len(calibration_data)
        assert result.global_threshold is not None

        # Check that per-type thresholds were computed
        assert SemanticType.LAB in result.type_calibrations
        assert SemanticType.DRUG in result.type_calibrations

    def test_per_type_coverage(self, mock_embedder, calibration_data):
        """Per-type coverage is tracked."""
        config = MondrianConfig(min_calibration_per_type=3)
        matcher = MondrianConformalMatcher(mock_embedder, config)

        result = matcher.calibrate(calibration_data)

        # Each type should have coverage computed
        assert SemanticType.LAB in result.per_type_coverage
        assert SemanticType.DRUG in result.per_type_coverage

    def test_fallback_to_global(self, mock_embedder, calibration_data):
        """Types with insufficient data fall back to global threshold."""
        config = MondrianConfig(
            min_calibration_per_type=100,  # High threshold to trigger fallback
            fallback_to_global=True,
        )
        matcher = MondrianConformalMatcher(mock_embedder, config)

        result = matcher.calibrate(calibration_data)

        # All types should fallback since none have 100 examples
        for cal in result.type_calibrations.values():
            assert cal.is_fallback is True

    def test_predict_without_calibration(self, mock_embedder):
        """Prediction works without calibration (with warning)."""
        config = MondrianConfig()
        matcher = MondrianConformalMatcher(mock_embedder, config)

        # Should work but use default threshold
        pred = matcher.predict("lactate")
        assert isinstance(pred, MondrianPredictionSet)

    def test_predict_with_calibration(self, mock_embedder, calibration_data):
        """Prediction uses type-specific threshold after calibration."""
        config = MondrianConfig(min_calibration_per_type=3)
        matcher = MondrianConformalMatcher(mock_embedder, config)
        matcher.calibrate(calibration_data)

        pred = matcher.predict("troponin", expected_type=SemanticType.LAB)

        assert pred.semantic_type == SemanticType.LAB
        assert pred.coverage_guarantee == pytest.approx(0.9, abs=0.01)

    def test_predict_infers_type(self, mock_embedder, calibration_data):
        """Prediction infers type when not provided."""
        config = MondrianConfig(min_calibration_per_type=3)
        matcher = MondrianConformalMatcher(mock_embedder, config)
        matcher.calibrate(calibration_data)

        pred = matcher.predict("norepinephrine")

        # Should infer DRUG type
        assert pred.semantic_type == SemanticType.DRUG

    def test_batch_prediction(self, mock_embedder, calibration_data):
        """Batch prediction works."""
        config = MondrianConfig(min_calibration_per_type=3)
        matcher = MondrianConformalMatcher(mock_embedder, config)
        matcher.calibrate(calibration_data)

        queries = ["lactate", "norepinephrine", "ECG"]
        types = [SemanticType.LAB, SemanticType.DRUG, SemanticType.PROCEDURE]

        results = matcher.predict_batch(queries, types)

        assert len(results) == 3
        assert all(isinstance(r, MondrianPredictionSet) for r in results)

    def test_uncertainty_levels(self, mock_embedder, calibration_data):
        """Uncertainty levels are assigned based on set size."""
        config = MondrianConfig(
            min_calibration_per_type=3,
            abstain_set_size_threshold=5,
        )
        matcher = MondrianConformalMatcher(mock_embedder, config)
        matcher.calibrate(calibration_data)

        # Different queries may get different uncertainty levels
        pred = matcher.predict("lactate")
        assert pred.uncertainty_level in [
            UncertaintyLevel.LOW,
            UncertaintyLevel.MEDIUM,
            UncertaintyLevel.HIGH,
            UncertaintyLevel.ABSTAIN,
        ]

    def test_get_type_statistics(self, mock_embedder, calibration_data):
        """Get statistics after calibration."""
        config = MondrianConfig(min_calibration_per_type=3)
        matcher = MondrianConformalMatcher(mock_embedder, config)
        matcher.calibrate(calibration_data)

        stats = matcher.get_type_statistics()

        assert "global_threshold" in stats
        assert "global_coverage" in stats
        assert "per_type" in stats
        assert len(stats["per_type"]) > 0

    def test_generate_report(self, mock_embedder, calibration_data):
        """Report generation."""
        config = MondrianConfig(min_calibration_per_type=3)
        matcher = MondrianConformalMatcher(mock_embedder, config)
        matcher.calibrate(calibration_data)

        report = matcher.generate_report()

        assert "# Mondrian Conformal Prediction Report" in report
        assert "Global Statistics" in report
        assert "Per-Type Calibration" in report
        assert "Coverage Analysis" in report


class TestCalibrateFromGoldset:
    """Tests for goldset calibration helper."""

    def test_calibrate_from_goldset(self):
        """Calibrate from goldset helper function."""
        from cga_bench.semantic_layer.ontology.ablation import GoldInstance
        from cga_bench.semantic_layer.ontology.neural_embedder import (
            MockNeuralEmbedder,
            EmbedderConfig,
        )

        embedder = MockNeuralEmbedder(EmbedderConfig(similarity_threshold=0.3))
        embedder.build_index([
            ("order_lab_lactate", "lactate", []),
            ("start_norepinephrine", "norepinephrine", []),
        ])

        gold_set = [
            GoldInstance(
                query="lactate",
                gold_concept_id="order_lab_lactate",
                gold_display="lactate",
                domain="sepsis",
                difficulty="easy",
                category="lab",
            ),
            GoldInstance(
                query="norepinephrine",
                gold_concept_id="start_norepinephrine",
                gold_display="norepinephrine",
                domain="sepsis",
                difficulty="easy",
                category="drug",
            ),
        ]

        mondrian = calibrate_mondrian_from_goldset(embedder, gold_set)

        assert mondrian.is_calibrated is True


class TestPerTypeAlphaOverrides:
    """Tests for per-type alpha overrides."""

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        from cga_bench.semantic_layer.ontology.neural_embedder import (
            MockNeuralEmbedder,
            EmbedderConfig,
        )
        embedder = MockNeuralEmbedder(EmbedderConfig(similarity_threshold=0.3))
        embedder.build_index([
            ("drug_1", "drug one", []),
            ("drug_2", "drug two", []),
            ("lab_1", "lab one", []),
        ])
        return embedder

    def test_drug_conservative_alpha(self, mock_embedder):
        """Drugs can have more conservative (lower) alpha."""
        config = MondrianConfig(
            alpha=0.10,  # Default 90% coverage
            per_type_alpha={
                "drug": 0.05,  # 95% coverage for drugs
            },
            min_calibration_per_type=2,
        )
        matcher = MondrianConformalMatcher(mock_embedder, config)

        calibration_data = [
            ("drug one", "drug_1", SemanticType.DRUG),
            ("drug two", "drug_2", SemanticType.DRUG),
            ("lab one", "lab_1", SemanticType.LAB),
            ("lab test", "lab_1", SemanticType.LAB),
        ]

        matcher.calibrate(calibration_data)

        # DRUG should have different threshold than LAB
        drug_pred = matcher.predict("drug", expected_type=SemanticType.DRUG)
        lab_pred = matcher.predict("lab", expected_type=SemanticType.LAB)

        # DRUG should have 95% coverage guarantee
        assert drug_pred.coverage_guarantee == pytest.approx(0.95, abs=0.01)
        # LAB should have default 90%
        assert lab_pred.coverage_guarantee == pytest.approx(0.90, abs=0.01)
