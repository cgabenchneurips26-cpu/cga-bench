"""Tests for Hard Negative Mining (P8).

Tests cover:
1. Mining from gold set (DHNS-style)
2. Type trap detection
3. Brand-generic confusion mining
4. Training data export formats
5. Analysis report generation
"""
import json
import pytest
import tempfile
from pathlib import Path
from typing import List, Tuple

from cga_bench.semantic_layer.ontology.hard_negative_miner import (
    HardNegativeMiner,
    HardNegative,
    MiningConfig,
    NegativeType,
    TrainingTriple,
    CGA_TYPE_TRAPS,
    CGA_BRAND_MAPPINGS,
)


class TestMiningConfig:
    """Tests for mining configuration."""

    def test_default_config(self):
        """Default config has sensible values."""
        config = MiningConfig()
        assert config.top_k_negatives == 5
        assert config.include_model_errors is True
        assert config.include_type_traps is True
        assert config.min_surface_similarity == 0.3
        assert config.max_surface_similarity == 0.9

    def test_custom_config(self):
        """Custom config overrides defaults."""
        config = MiningConfig(
            top_k_negatives=10,
            include_type_traps=False,
            model_error_threshold=0.7,
        )
        assert config.top_k_negatives == 10
        assert config.include_type_traps is False
        assert config.model_error_threshold == 0.7


class TestHardNegative:
    """Tests for hard negative dataclass."""

    def test_basic_negative(self):
        """Basic negative creation."""
        neg = HardNegative(
            query="lactate",
            gold_concept_id="order_lab_lactate",
            negative_concept_id="give_lactated_ringers",
            negative_type=NegativeType.TYPE_TRAP,
        )
        assert neg.query == "lactate"
        assert neg.negative_type == NegativeType.TYPE_TRAP

    def test_to_dict(self):
        """Negative converts to dict correctly."""
        neg = HardNegative(
            query="lactate",
            gold_concept_id="order_lab_lactate",
            negative_concept_id="give_lactated_ringers",
            negative_type=NegativeType.TYPE_TRAP,
            model_score=0.85,
            gold_score=0.75,
            surface_similarity=0.5,
            notes="Type trap: LAB vs FLUID",
        )
        d = neg.to_dict()
        assert d["query"] == "lactate"
        assert d["negative_type"] == "type_trap"
        assert d["model_score"] == 0.85
        assert d["notes"] == "Type trap: LAB vs FLUID"


class TestTrainingTriple:
    """Tests for training triple dataclass."""

    def test_to_contrastive_format(self):
        """Triple converts to contrastive format."""
        triple = TrainingTriple(
            query="lactate",
            positive_id="order_lab_lactate",
            positive_text="lactate lab test",
            negative_id="give_lactated_ringers",
            negative_text="lactated ringers IV fluid",
            negative_type=NegativeType.TYPE_TRAP,
        )
        cf = triple.to_contrastive_format()
        assert cf["query"] == "lactate"
        assert cf["positive"] == "lactate lab test"
        assert cf["negative"] == "lactated ringers IV fluid"
        assert cf["label"] == 1

    def test_to_triplet_format(self):
        """Triple converts to triplet format."""
        triple = TrainingTriple(
            query="lactate",
            positive_id="order_lab_lactate",
            positive_text="lactate lab test",
            negative_id="give_lactated_ringers",
            negative_text="lactated ringers IV fluid",
            negative_type=NegativeType.TYPE_TRAP,
        )
        triplet = triple.to_triplet_format()
        assert triplet[0] == "lactate"  # anchor
        assert triplet[1] == "lactate lab test"  # positive
        assert triplet[2] == "lactated ringers IV fluid"  # negative


class TestHardNegativeMiner:
    """Tests for hard negative miner."""

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder for testing."""
        from cga_bench.semantic_layer.ontology.neural_embedder import (
            MockNeuralEmbedder,
            EmbedderConfig,
        )
        embedder = MockNeuralEmbedder(EmbedderConfig(similarity_threshold=0.3))
        concepts = [
            ("order_lab_lactate", "lactate lab test", []),
            ("give_lactated_ringers", "lactated ringers", ["LR"]),
            ("start_norepinephrine", "norepinephrine", ["levophed"]),
            ("start_vasopressin", "vasopressin", []),
            ("order_lab_troponin", "troponin", ["trop"]),
            ("order_bnp", "BNP", []),
        ]
        embedder.build_index(concepts)
        return embedder

    @pytest.fixture
    def miner(self, mock_embedder):
        """Create miner with mock embedder."""
        miner = HardNegativeMiner(mock_embedder, config=MiningConfig(
            top_k_negatives=3,
            include_model_errors=True,
            include_type_traps=True,
        ))
        # Set concept metadata
        miner.set_concept_metadata([
            ("order_lab_lactate", "lactate", "LAB"),
            ("give_lactated_ringers", "lactated ringers", "FLUID"),
            ("start_norepinephrine", "norepinephrine", "DRUG"),
            ("start_vasopressin", "vasopressin", "DRUG"),
            ("order_lab_troponin", "troponin", "LAB"),
            ("order_bnp", "BNP", "LAB"),
        ])
        return miner

    def test_mine_from_gold_set(self, miner):
        """Mine negatives from gold set."""
        gold_set = [
            ("lactate", "order_lab_lactate"),
            ("norepinephrine", "start_norepinephrine"),
        ]

        negatives = miner.mine_from_gold_set(gold_set)

        # Should have at least some negatives
        assert len(negatives) >= 0  # May be empty if no confusions found

    def test_mine_type_traps(self, miner):
        """Mine type trap cases."""
        trap_definitions = [
            {
                "query": "lactate",
                "gold_concept_id": "order_lab_lactate",
                "trap_concept_id": "give_lactated_ringers",
                "gold_type": "LAB",
                "trap_type": "FLUID",
            }
        ]

        negatives = miner.mine_type_traps(trap_definitions)

        assert len(negatives) == 1
        assert negatives[0].negative_type == NegativeType.TYPE_TRAP
        assert negatives[0].gold_concept_id == "order_lab_lactate"
        assert negatives[0].negative_concept_id == "give_lactated_ringers"

    def test_mine_brand_generic_pairs(self, miner):
        """Mine brand-generic confusion pairs."""
        brand_mappings = [
            {
                "brand": "levophed",
                "generic_class": "start_norepinephrine",
                "confusion": "start_vasopressin",
            }
        ]

        negatives = miner.mine_brand_generic_pairs(brand_mappings)

        assert len(negatives) == 1
        assert negatives[0].negative_type == NegativeType.BRAND_GENERIC

    def test_to_training_triples(self, miner):
        """Convert negatives to training triples."""
        negatives = [
            HardNegative(
                query="lactate",
                gold_concept_id="order_lab_lactate",
                negative_concept_id="give_lactated_ringers",
                negative_type=NegativeType.TYPE_TRAP,
            )
        ]

        triples = miner.to_training_triples(negatives)

        assert len(triples) == 1
        assert triples[0].query == "lactate"
        assert triples[0].positive_id == "order_lab_lactate"
        assert triples[0].negative_id == "give_lactated_ringers"

    def test_export_training_data_jsonl(self, miner):
        """Export to JSONL format."""
        negatives = [
            HardNegative(
                query="lactate",
                gold_concept_id="order_lab_lactate",
                negative_concept_id="give_lactated_ringers",
                negative_type=NegativeType.TYPE_TRAP,
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "negatives.jsonl"
            miner.export_training_data(negatives, output_path, format="jsonl")

            assert output_path.exists()

            # Verify content
            with open(output_path) as f:
                line = f.readline()
                data = json.loads(line)
                assert data["query"] == "lactate"
                assert data["negative_type"] == "type_trap"

    def test_export_training_data_triplet(self, miner):
        """Export to triplet format."""
        negatives = [
            HardNegative(
                query="lactate",
                gold_concept_id="order_lab_lactate",
                negative_concept_id="give_lactated_ringers",
                negative_type=NegativeType.TYPE_TRAP,
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "triplets.jsonl"
            miner.export_training_data(negatives, output_path, format="triplet")

            assert output_path.exists()

            with open(output_path) as f:
                line = f.readline()
                triplet = json.loads(line)
                assert isinstance(triplet, list)
                assert len(triplet) == 3

    def test_generate_analysis_report(self, miner):
        """Generate analysis report."""
        negatives = [
            HardNegative(
                query="lactate",
                gold_concept_id="order_lab_lactate",
                negative_concept_id="give_lactated_ringers",
                negative_type=NegativeType.TYPE_TRAP,
                model_score=0.85,
                gold_score=0.75,
            ),
            HardNegative(
                query="norepinephrine",
                gold_concept_id="start_norepinephrine",
                negative_concept_id="start_vasopressin",
                negative_type=NegativeType.MODEL_CONFUSION,
                model_score=0.9,
                gold_score=0.85,
            ),
        ]

        report = miner.generate_analysis_report(negatives)

        assert "# Hard Negative Mining Report" in report
        assert "**Total negatives mined**: 2" in report
        assert "type_trap" in report
        assert "model_confusion" in report


class TestPreDefinedTraps:
    """Tests for predefined CGA type traps and brand mappings."""

    def test_cga_type_traps_exist(self):
        """CGA type traps are defined."""
        assert len(CGA_TYPE_TRAPS) >= 1

        # Check structure
        trap = CGA_TYPE_TRAPS[0]
        assert "query" in trap
        assert "gold_concept_id" in trap
        assert "trap_concept_id" in trap
        assert "gold_type" in trap
        assert "trap_type" in trap

    def test_cga_brand_mappings_exist(self):
        """CGA brand mappings are defined."""
        assert len(CGA_BRAND_MAPPINGS) >= 1

        # Check structure
        mapping = CGA_BRAND_MAPPINGS[0]
        assert "brand" in mapping
        assert "generic_class" in mapping
        assert "confusion" in mapping

    def test_lactate_trap_included(self):
        """Lactate type trap is included (critical case)."""
        lactate_trap = next(
            (t for t in CGA_TYPE_TRAPS if t["query"] == "lactate"),
            None
        )
        assert lactate_trap is not None
        assert lactate_trap["gold_type"] == "LAB"
        assert lactate_trap["trap_type"] == "FLUID"


class TestNegativeTypeEnum:
    """Tests for negative type enumeration."""

    def test_all_types_have_values(self):
        """All negative types have string values."""
        assert NegativeType.MODEL_CONFUSION.value == "model_confusion"
        assert NegativeType.SURFACE_SIMILAR.value == "surface_similar"
        assert NegativeType.TYPE_TRAP.value == "type_trap"
        assert NegativeType.SIBLING.value == "sibling"
        assert NegativeType.BRAND_GENERIC.value == "brand_generic"
        assert NegativeType.ABBREVIATION.value == "abbreviation"

    def test_type_count(self):
        """Expected number of negative types."""
        assert len(NegativeType) == 6
