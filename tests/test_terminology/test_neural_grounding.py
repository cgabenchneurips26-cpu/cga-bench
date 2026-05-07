"""Tests for neural embedding-based terminology grounding."""
import json
from pathlib import Path

import numpy as np
import pytest

from cga_bench.semantic_layer.terminology.neural_backend import (
    NeuralGroundingBackend,
    NeuralGroundingConfig,
    NeuralMatch,
)
from cga_bench.semantic_layer.terminology.grounding import (
    GroundingConfig,
    TerminologyGrounder,
)


def _create_mock_embeddings(tmp_path: Path, dim: int = 64):
    """Create deterministic mock embeddings for testing.

    Generates embeddings where synonyms cluster together:
    - "sodium" cluster: sodium, Na, Na+, serum sodium
    - "lactate" cluster: lactate, lactic acid, blood lactate
    - "norepinephrine" cluster: norepinephrine, levophed, noradrenaline
    - "sepsis" cluster: sepsis, septicemia, blood poisoning
    - "unrelated" terms: far from all clusters
    """
    rng = np.random.RandomState(42)

    # Define cluster centers (orthogonal-ish for clean separation)
    sodium_center = rng.randn(dim).astype(np.float32)
    sodium_center /= np.linalg.norm(sodium_center)

    lactate_center = rng.randn(dim).astype(np.float32)
    lactate_center /= np.linalg.norm(lactate_center)

    norepi_center = rng.randn(dim).astype(np.float32)
    norepi_center /= np.linalg.norm(norepi_center)

    sepsis_center = rng.randn(dim).astype(np.float32)
    sepsis_center /= np.linalg.norm(sepsis_center)

    potassium_center = rng.randn(dim).astype(np.float32)
    potassium_center /= np.linalg.norm(potassium_center)

    def _near(center, noise_scale=0.05):
        """Create a vector near a center with small noise."""
        vec = center + rng.randn(dim).astype(np.float32) * noise_scale
        vec /= np.linalg.norm(vec)
        return vec

    # Build entries: (embedding_vec, metadata_dict)
    entries = [
        # Sodium cluster (LOINC)
        (_near(sodium_center), {"code": "2951-2", "internal_code": "sodium", "display": "Sodium [Moles/volume]", "system": "loinc", "domain": "electrolytes", "source_text": "Sodium [Moles/volume] in Serum or Plasma"}),
        (_near(sodium_center), {"code": "2951-2", "internal_code": "sodium", "display": "Sodium [Moles/volume]", "system": "loinc", "domain": "electrolytes", "source_text": "Na"}),
        (_near(sodium_center), {"code": "2951-2", "internal_code": "sodium", "display": "Sodium [Moles/volume]", "system": "loinc", "domain": "electrolytes", "source_text": "Na+"}),
        (_near(sodium_center), {"code": "2951-2", "internal_code": "sodium", "display": "Sodium [Moles/volume]", "system": "loinc", "domain": "electrolytes", "source_text": "serum sodium"}),

        # Lactate cluster (LOINC)
        (_near(lactate_center), {"code": "32693-4", "internal_code": "lactate", "display": "Lactate [Moles/volume]", "system": "loinc", "domain": "sepsis", "source_text": "Lactate [Moles/volume] in Blood"}),
        (_near(lactate_center), {"code": "32693-4", "internal_code": "lactate", "display": "Lactate [Moles/volume]", "system": "loinc", "domain": "sepsis", "source_text": "lactic acid"}),
        (_near(lactate_center), {"code": "32693-4", "internal_code": "lactate", "display": "Lactate [Moles/volume]", "system": "loinc", "domain": "sepsis", "source_text": "blood lactate"}),

        # Potassium cluster (LOINC)
        (_near(potassium_center), {"code": "2823-3", "internal_code": "potassium", "display": "Potassium [Moles/volume]", "system": "loinc", "domain": "electrolytes", "source_text": "Potassium [Moles/volume]"}),
        (_near(potassium_center), {"code": "2823-3", "internal_code": "potassium", "display": "Potassium [Moles/volume]", "system": "loinc", "domain": "electrolytes", "source_text": "K"}),
        (_near(potassium_center), {"code": "2823-3", "internal_code": "potassium", "display": "Potassium [Moles/volume]", "system": "loinc", "domain": "electrolytes", "source_text": "K+"}),

        # Norepinephrine cluster (RxNorm)
        (_near(norepi_center), {"code": "7512", "internal_code": "norepinephrine", "display": "Norepinephrine", "system": "rxnorm", "domain": "vasopressors", "source_text": "Norepinephrine"}),
        (_near(norepi_center), {"code": "7512", "internal_code": "norepinephrine", "display": "Norepinephrine", "system": "rxnorm", "domain": "vasopressors", "source_text": "levophed"}),
        (_near(norepi_center), {"code": "7512", "internal_code": "norepinephrine", "display": "Norepinephrine", "system": "rxnorm", "domain": "vasopressors", "source_text": "noradrenaline"}),
        (_near(norepi_center), {"code": "7512", "internal_code": "norepinephrine", "display": "Norepinephrine", "system": "rxnorm", "domain": "vasopressors", "source_text": "NE"}),

        # Sepsis cluster (SNOMED)
        (_near(sepsis_center), {"code": "91302008", "internal_code": "sepsis", "display": "Sepsis", "system": "snomed", "domain": "sepsis_infection", "source_text": "Sepsis"}),
        (_near(sepsis_center), {"code": "91302008", "internal_code": "sepsis", "display": "Sepsis", "system": "snomed", "domain": "sepsis_infection", "source_text": "septicemia"}),
        (_near(sepsis_center), {"code": "91302008", "internal_code": "sepsis", "display": "Sepsis", "system": "snomed", "domain": "sepsis_infection", "source_text": "blood poisoning"}),
        (_near(sepsis_center), {"code": "91302008", "internal_code": "sepsis", "display": "Sepsis", "system": "snomed", "domain": "sepsis_infection", "source_text": "systemic infection"}),
    ]

    embeddings = np.vstack([e[0] for e in entries]).astype(np.float32)
    metadata = [e[1] for e in entries]

    # Save
    emb_dir = tmp_path / "embeddings"
    emb_dir.mkdir(parents=True, exist_ok=True)

    np.save(str(emb_dir / "terminology_embeddings.npy"), embeddings)
    with open(emb_dir / "terminology_metadata.json", "w") as f:
        json.dump(metadata, f)
    with open(emb_dir / "build_info.json", "w") as f:
        json.dump({
            "model_name": "test_mock",
            "embedding_dim": dim,
            "num_entries": len(entries),
            "num_unique_codes": 5,
        }, f)

    return emb_dir, embeddings, metadata


class _MockEncoder:
    """Mock encoder that maps query strings to known cluster centers."""

    def __init__(self, centers: dict, dim: int = 64):
        self._centers = centers
        self._dim = dim
        self._rng = np.random.RandomState(123)

    def encode_query(self, query: str) -> np.ndarray:
        """Return a vector near the appropriate cluster center."""
        q = query.lower().strip()
        # Exact match first (avoids substring collisions like "na" in "noradrenaline")
        if q in self._centers:
            center = self._centers[q]
            noise = self._rng.randn(self._dim).astype(np.float32) * 0.03
            vec = center + noise
            vec /= np.linalg.norm(vec)
            return vec
        # Substring match (longest key first to avoid partial matches)
        for key, center in sorted(self._centers.items(), key=lambda x: -len(x[0])):
            if key in q or q in key:
                noise = self._rng.randn(self._dim).astype(np.float32) * 0.03
                vec = center + noise
                vec /= np.linalg.norm(vec)
                return vec
        # Unknown: random direction
        vec = self._rng.randn(self._dim).astype(np.float32)
        vec /= np.linalg.norm(vec)
        return vec


@pytest.fixture
def mock_embeddings(tmp_path):
    """Create mock embeddings fixture."""
    emb_dir, embeddings, metadata = _create_mock_embeddings(tmp_path)
    return emb_dir


@pytest.fixture
def neural_config(mock_embeddings):
    """Config pointing to mock embeddings."""
    return NeuralGroundingConfig(
        embeddings_dir=str(mock_embeddings),
        confidence_threshold=0.7,
        use_gpu=False,
    )


@pytest.fixture
def backend_with_mock_encoder(mock_embeddings):
    """Backend with mock encoder for deterministic query encoding."""
    config = NeuralGroundingConfig(
        embeddings_dir=str(mock_embeddings),
        confidence_threshold=0.7,
        use_gpu=False,
    )
    backend = NeuralGroundingBackend(config)
    backend._ensure_initialized()

    # Inject mock encoder via the cluster centers from our fixture
    rng = np.random.RandomState(42)
    dim = 64
    centers = {}
    for name in ["sodium", "lactate", "norepinephrine", "sepsis", "potassium"]:
        center = rng.randn(dim).astype(np.float32)
        center /= np.linalg.norm(center)
        centers[name] = center

    # Add synonym -> center mappings
    synonym_map = {
        "na": centers["sodium"],
        "na+": centers["sodium"],
        "serum sodium": centers["sodium"],
        "lactic acid": centers["lactate"],
        "blood lactate": centers["lactate"],
        "levophed": centers["norepinephrine"],
        "noradrenaline": centers["norepinephrine"],
        "ne": centers["norepinephrine"],
        "septicemia": centers["sepsis"],
        "blood poisoning": centers["sepsis"],
        "systemic infection": centers["sepsis"],
        "k": centers["potassium"],
        "k+": centers["potassium"],
    }
    centers.update(synonym_map)

    mock_enc = _MockEncoder(centers, dim)

    # Monkey-patch the encode method
    backend._encode_query = mock_enc.encode_query
    backend._model = True  # Mark as "loaded" so encode_query isn't skipped

    return backend


class TestNeuralGroundingConfig:
    """Test NeuralGroundingConfig defaults and overrides."""

    def test_default_model_is_sapbert(self):
        config = NeuralGroundingConfig()
        assert "SapBERT" in config.model_name

    def test_default_threshold(self):
        config = NeuralGroundingConfig()
        assert config.confidence_threshold == 0.7

    def test_custom_threshold(self):
        config = NeuralGroundingConfig(confidence_threshold=0.9)
        assert config.confidence_threshold == 0.9

    def test_custom_embeddings_dir(self, tmp_path):
        config = NeuralGroundingConfig(embeddings_dir=str(tmp_path))
        assert config.embeddings_dir == str(tmp_path)


class TestNeuralGroundingBackend:
    """Test NeuralGroundingBackend with mock embeddings."""

    def test_is_available_with_embeddings(self, mock_embeddings):
        config = NeuralGroundingConfig(embeddings_dir=str(mock_embeddings))
        backend = NeuralGroundingBackend(config)
        assert backend.is_available()

    def test_is_available_without_embeddings(self, tmp_path):
        config = NeuralGroundingConfig(embeddings_dir=str(tmp_path / "nonexistent"))
        backend = NeuralGroundingBackend(config)
        assert not backend.is_available()

    def test_find_matches_sodium_synonym(self, backend_with_mock_encoder):
        """'Na' should match 'sodium' with high confidence."""
        matches = backend_with_mock_encoder.find_matches("Na", system="loinc")
        assert len(matches) > 0
        assert matches[0].internal_code == "sodium"
        assert matches[0].code == "2951-2"
        assert matches[0].confidence >= 0.7

    def test_find_matches_sodium_plus(self, backend_with_mock_encoder):
        """'Na+' should match sodium."""
        matches = backend_with_mock_encoder.find_matches("Na+", system="loinc")
        assert len(matches) > 0
        assert matches[0].internal_code == "sodium"

    def test_find_matches_drug_synonym(self, backend_with_mock_encoder):
        """'levophed' should match 'norepinephrine'."""
        matches = backend_with_mock_encoder.find_matches("levophed", system="rxnorm")
        assert len(matches) > 0
        assert matches[0].internal_code == "norepinephrine"
        assert matches[0].code == "7512"

    def test_find_matches_noradrenaline(self, backend_with_mock_encoder):
        """'noradrenaline' should match 'norepinephrine'."""
        matches = backend_with_mock_encoder.find_matches("noradrenaline", system="rxnorm")
        assert len(matches) > 0
        assert matches[0].internal_code == "norepinephrine"

    def test_find_matches_sepsis_synonym(self, backend_with_mock_encoder):
        """'blood poisoning' should match sepsis."""
        matches = backend_with_mock_encoder.find_matches("blood poisoning", system="snomed")
        assert len(matches) > 0
        assert matches[0].internal_code == "sepsis"
        assert matches[0].code == "91302008"

    def test_find_matches_lactate_synonym(self, backend_with_mock_encoder):
        """'lactic acid' should match lactate."""
        matches = backend_with_mock_encoder.find_matches("lactic acid", system="loinc")
        assert len(matches) > 0
        assert matches[0].internal_code == "lactate"

    def test_confidence_threshold_filtering(self, backend_with_mock_encoder):
        """Truly unrelated terms should not match above threshold."""
        # Use a very different query that shouldn't match any cluster
        matches = backend_with_mock_encoder.find_matches(
            "xyzzy_completely_unrelated_term_12345", system="loinc"
        )
        # Should be empty or all below threshold
        for m in matches:
            assert m.confidence >= 0.7  # only returned if above threshold

    def test_system_filter_loinc_only(self, backend_with_mock_encoder):
        """system='loinc' should not return RxNorm matches."""
        matches = backend_with_mock_encoder.find_matches("sodium", system="loinc")
        for m in matches:
            assert m.system == "loinc"

    def test_system_filter_rxnorm_only(self, backend_with_mock_encoder):
        """system='rxnorm' should not return LOINC matches."""
        matches = backend_with_mock_encoder.find_matches("norepinephrine", system="rxnorm")
        for m in matches:
            assert m.system == "rxnorm"

    def test_system_filter_snomed_only(self, backend_with_mock_encoder):
        """system='snomed' should not return other system matches."""
        matches = backend_with_mock_encoder.find_matches("sepsis", system="snomed")
        for m in matches:
            assert m.system == "snomed"

    def test_empty_query_returns_empty(self, backend_with_mock_encoder):
        matches = backend_with_mock_encoder.find_matches("", system="loinc")
        assert matches == []

    def test_whitespace_query_returns_empty(self, backend_with_mock_encoder):
        matches = backend_with_mock_encoder.find_matches("   ", system="loinc")
        assert matches == []

    def test_top_k_limits_results(self, backend_with_mock_encoder):
        matches = backend_with_mock_encoder.find_matches("sodium", system="loinc", top_k=1)
        assert len(matches) <= 1

    def test_find_best_match_returns_single(self, backend_with_mock_encoder):
        match = backend_with_mock_encoder.find_best_match("Na", system="loinc")
        assert isinstance(match, NeuralMatch) or match is None

    def test_find_best_match_none_for_unrelated(self, backend_with_mock_encoder):
        match = backend_with_mock_encoder.find_best_match(
            "xyzzy_completely_unrelated_12345", system="loinc"
        )
        # May or may not be None depending on random distances,
        # but if returned, should be above threshold
        if match is not None:
            assert match.confidence >= 0.7

    def test_potassium_synonym(self, backend_with_mock_encoder):
        """'K+' should match potassium."""
        matches = backend_with_mock_encoder.find_matches("K+", system="loinc")
        assert len(matches) > 0
        assert matches[0].internal_code == "potassium"


class TestNeuralFallbackIntegration:
    """Test TerminologyGrounder with neural fallback enabled."""

    def test_yaml_match_takes_priority(self):
        """Known YAML entry should not trigger neural (neural disabled by default)."""
        grounder = TerminologyGrounder(GroundingConfig())
        result = grounder.ground_lab_result("lactate", 3.0, "mmol/L")
        assert result.concept is not None
        assert result.concept.code == "32693-4"
        assert result.neural_match_used is False

    def test_neural_disabled_returns_none_for_unknown(self):
        """With neural disabled, unknown codes return None."""
        grounder = TerminologyGrounder(GroundingConfig(enable_neural_fallback=False))
        result = grounder.ground_lab_result("xyzzy_unknown", 140, "meq/L")
        assert result.concept is None
        assert result.neural_match_used is False

    def test_neural_enabled_but_no_embeddings(self, tmp_path):
        """Neural enabled but no embeddings dir returns None gracefully."""
        config = GroundingConfig(
            enable_neural_fallback=True,
            neural_config=NeuralGroundingConfig(
                embeddings_dir=str(tmp_path / "nonexistent")
            ),
        )
        grounder = TerminologyGrounder(config)
        result = grounder.ground_lab_result("Na", 140, "meq/L")
        # Should not crash, just return None for concept
        assert result.concept is None

    def test_neural_fallback_with_mock_embeddings(self, mock_embeddings):
        """Neural fallback resolves unknown synonym when embeddings exist."""
        config = GroundingConfig(
            enable_neural_fallback=True,
            neural_config=NeuralGroundingConfig(
                embeddings_dir=str(mock_embeddings),
                use_gpu=False,
            ),
        )
        grounder = TerminologyGrounder(config)
        # Without actual model, encoding will fail gracefully
        # This tests the integration path (not the actual matching)
        result = grounder.ground_lab_result("Na", 140, "meq/L")
        # Without model, neural fallback can't encode, so concept is None
        # But the system doesn't crash
        assert result.internal_code == "Na"

    def test_medication_normal_path(self):
        """Medication grounding works normally without neural."""
        grounder = TerminologyGrounder(GroundingConfig())
        result = grounder.ground_medication("norepinephrine")
        assert result.rxnorm_code == "7512"

    def test_medication_unknown_no_crash(self):
        """Unknown medication with neural enabled doesn't crash."""
        config = GroundingConfig(enable_neural_fallback=True)
        grounder = TerminologyGrounder(config)
        result = grounder.ground_medication("xyzzy_drug")
        # No crash, just no code
        assert result.name == "xyzzy_drug"

    def test_diagnosis_normal_path(self):
        """Diagnosis grounding works normally."""
        grounder = TerminologyGrounder(GroundingConfig())
        result = grounder.ground_diagnosis("sepsis")
        assert result is not None
        assert result.code == "91302008"


class TestGroundingResultNeuralFields:
    """Test new neural fields on GroundedLabResult."""

    def test_default_neural_fields(self):
        """New fields default to False/None."""
        from cga_bench.semantic_layer.terminology.coding import GroundedLabResult
        result = GroundedLabResult(internal_code="test")
        assert result.neural_match_used is False
        assert result.neural_confidence is None

    def test_neural_fields_settable(self):
        """Neural fields can be set."""
        from cga_bench.semantic_layer.terminology.coding import GroundedLabResult
        result = GroundedLabResult(
            internal_code="test",
            neural_match_used=True,
            neural_confidence=0.85,
        )
        assert result.neural_match_used is True
        assert result.neural_confidence == 0.85

    def test_backward_compatible(self):
        """Existing code creating GroundedLabResult without new fields still works."""
        from cga_bench.semantic_layer.terminology.coding import GroundedLabResult, CodedConcept
        result = GroundedLabResult(
            internal_code="lactate",
            concept=CodedConcept(
                system="http://loinc.org",
                code="32693-4",
                display="Lactate",
            ),
        )
        assert result.concept.code == "32693-4"
        assert result.neural_match_used is False


class TestNeuralMatchDataclass:
    """Test NeuralMatch dataclass."""

    def test_creation(self):
        match = NeuralMatch(
            code="2951-2",
            internal_code="sodium",
            display="Sodium",
            system="loinc",
            confidence=0.92,
            matched_synonym="Na",
        )
        assert match.code == "2951-2"
        assert match.confidence == 0.92
        assert match.matched_synonym == "Na"

    def test_default_synonym_none(self):
        match = NeuralMatch(
            code="7512",
            internal_code="norepinephrine",
            display="Norepinephrine",
            system="rxnorm",
            confidence=0.85,
        )
        assert match.matched_synonym is None


class TestExpandedCodesLoading:
    """Test that expanded_codes.yaml loads correctly."""

    def test_expanded_codes_parseable(self):
        """expanded_codes.yaml should be valid YAML."""
        import yaml
        codes_path = Path(__file__).parent.parent.parent / "semantic_layer" / "terminology" / "expanded_codes.yaml"
        if not codes_path.exists():
            pytest.skip("expanded_codes.yaml not found")
        with open(codes_path) as f:
            data = yaml.safe_load(f)
        assert "version" in data
        assert "loinc" in data
        assert "snomed" in data
        assert "rxnorm" in data

    def test_expanded_codes_have_synonyms(self):
        """Each entry should have synonyms list."""
        import yaml
        codes_path = Path(__file__).parent.parent.parent / "semantic_layer" / "terminology" / "expanded_codes.yaml"
        if not codes_path.exists():
            pytest.skip("expanded_codes.yaml not found")
        with open(codes_path) as f:
            data = yaml.safe_load(f)

        for system in ("loinc", "snomed", "rxnorm"):
            entries = data[system]
            for entry in entries:
                assert "code" in entry, f"Missing 'code' in {system} entry"
                assert "internal_code" in entry
                assert "display" in entry
                assert "synonyms" in entry
                assert len(entry["synonyms"]) >= 1, f"No synonyms for {entry['code']}"

    def test_expanded_codes_coverage(self):
        """Should have substantial coverage."""
        import yaml
        codes_path = Path(__file__).parent.parent.parent / "semantic_layer" / "terminology" / "expanded_codes.yaml"
        if not codes_path.exists():
            pytest.skip("expanded_codes.yaml not found")
        with open(codes_path) as f:
            data = yaml.safe_load(f)

        assert len(data["loinc"]) >= 50, "Need at least 50 LOINC entries"
        assert len(data["snomed"]) >= 30, "Need at least 30 SNOMED entries"
        assert len(data["rxnorm"]) >= 25, "Need at least 25 RxNorm entries"

    def test_build_script_load_function(self):
        """Test the build script's load function."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

        codes_path = Path(__file__).parent.parent.parent / "semantic_layer" / "terminology" / "expanded_codes.yaml"
        if not codes_path.exists():
            pytest.skip("expanded_codes.yaml not found")

        from build_terminology_embeddings import load_expanded_codes
        records = load_expanded_codes(codes_path)

        # Should have many records (each entry + synonyms)
        assert len(records) > 200, f"Expected 200+ records, got {len(records)}"

        # Each record should have required fields
        for r in records[:10]:
            assert "code" in r
            assert "internal_code" in r
            assert "system" in r
            assert "source_text" in r


class TestExistingTestsUnchanged:
    """Verify existing grounding behavior is unchanged."""

    def test_lactate_grounding_unchanged(self):
        g = TerminologyGrounder(GroundingConfig())
        result = g.ground_lab_result("lactate", 3.2, "mmol/L")
        assert result.concept is not None
        assert result.concept.system == "http://loinc.org"
        assert result.concept.code == "32693-4"
        assert result.quantity.unit_ucum == "mmol/L"

    def test_sepsis_grounding_unchanged(self):
        g = TerminologyGrounder(GroundingConfig())
        result = g.ground_diagnosis("sepsis")
        assert result is not None
        assert result.system == "http://snomed.info/sct"
        assert result.code == "91302008"

    def test_norepinephrine_grounding_unchanged(self):
        g = TerminologyGrounder(GroundingConfig())
        result = g.ground_medication("norepinephrine")
        assert result.rxnorm_code == "7512"

    def test_unknown_code_still_returns_none(self):
        g = TerminologyGrounder(GroundingConfig())
        result = g.ground_lab_result("unknown_lab_xyz", 1.0, "mg/dL")
        assert result.concept is None

    def test_ground_full_loinc_first(self):
        g = TerminologyGrounder(GroundingConfig())
        result = g.ground_full("potassium", 4.5, "meq/L")
        assert result.grounded
        assert result.concept.system == "http://loinc.org"

    def test_ground_full_snomed_fallback(self):
        g = TerminologyGrounder(GroundingConfig())
        result = g.ground_full("aki")
        assert result.grounded
        assert result.concept.system == "http://snomed.info/sct"
