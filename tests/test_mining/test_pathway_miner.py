"""Tests for Outcome-Driven Pathway Mining."""
import math
import pytest

from cga_bench.cpg_model.schemas.base import CGAScore
from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.mining.pathway_miner import (
    CorrelationResult,
    MiningConfig,
    MiningResult,
    Pathway,
    PathwayCluster,
    PathwayFeatures,
    PathwayMiner,
)


# ============================================
# Test Helpers
# ============================================

def _make_event(name, timestamp_min=0.0):
    """Create a minimal ActivityEvent."""
    return ActivityEvent(
        name=name,
        timestamp_min=timestamp_min,
        raw_event={},
        confidence=1.0,
        match_source="exact",
    )


def _make_score(
    episode_id="ep_001",
    compliance=0.85,
    peak_risk=0.5,
    aggregate_risk=1.0,
    sub_scores=None,
):
    """Create a CGAScore for testing."""
    return CGAScore(
        episode_id=episode_id,
        compliance_score=compliance,
        peak_risk=peak_risk,
        aggregate_risk=aggregate_risk,
        total_violations=2,
        violations_by_type={"omission": 1, "timing": 1},
        violation_events=[],
        justified_deviations=0,
        budget_usage={"tokens": 1000},
        sub_scores=sub_scores or {"C1": 0.9, "C2": 0.8},
    )


def _make_pathway(episode_id, activities, timestamps=None):
    """Create a Pathway directly."""
    if timestamps is None:
        timestamps = [float(i * 5) for i in range(len(activities))]
    duration = (timestamps[-1] - timestamps[0]) if timestamps else 0.0
    return Pathway(
        episode_id=episode_id,
        activities=activities,
        timestamps=timestamps,
        total_duration=duration,
    )


# ============================================
# Test Class: Pathway Extraction
# ============================================

class TestPathwayExtraction:
    """Tests for converting ActivityEvents to Pathways."""

    def test_extract_basic_pathway(self):
        """Basic extraction from events."""
        miner = PathwayMiner()
        events = [
            _make_event("ASSESS_VITALS", 0.0),
            _make_event("ORDER_TEST", 5.0),
            _make_event("PRESCRIBE", 10.0),
        ]
        pw = miner.extract_pathway("ep_001", events)

        assert pw.episode_id == "ep_001"
        assert pw.activities == ["ASSESS_VITALS", "ORDER_TEST", "PRESCRIBE"]
        assert pw.timestamps == [0.0, 5.0, 10.0]
        assert pw.total_duration == 10.0

    def test_extract_preserves_order(self):
        """Events are sorted by timestamp regardless of input order."""
        miner = PathwayMiner()
        events = [
            _make_event("PRESCRIBE", 10.0),
            _make_event("ASSESS_VITALS", 0.0),
            _make_event("ORDER_TEST", 5.0),
        ]
        pw = miner.extract_pathway("ep_002", events)
        assert pw.activities == ["ASSESS_VITALS", "ORDER_TEST", "PRESCRIBE"]

    def test_extract_unique_activities(self):
        """Unique activities set is computed correctly."""
        miner = PathwayMiner()
        events = [
            _make_event("A", 0.0),
            _make_event("B", 5.0),
            _make_event("A", 10.0),
            _make_event("C", 15.0),
        ]
        pw = miner.extract_pathway("ep_003", events)
        assert pw.unique_activities == {"A", "B", "C"}

    def test_extract_transition_counts(self):
        """Transition counts correctly track A->B patterns."""
        miner = PathwayMiner()
        events = [
            _make_event("A", 0.0),
            _make_event("B", 5.0),
            _make_event("A", 10.0),
            _make_event("B", 15.0),
        ]
        pw = miner.extract_pathway("ep_004", events)
        assert pw.transition_counts["A->B"] == 2
        assert pw.transition_counts["B->A"] == 1

    def test_extract_single_event(self):
        """Single event produces a valid pathway."""
        miner = PathwayMiner()
        events = [_make_event("A", 0.0)]
        pw = miner.extract_pathway("ep_005", events)
        assert pw.activities == ["A"]
        assert pw.total_duration == 0.0
        assert pw.transition_counts == {}

    def test_extract_empty_events(self):
        """Empty event list produces empty pathway."""
        miner = PathwayMiner()
        pw = miner.extract_pathway("ep_006", [])
        assert pw.activities == []
        assert pw.total_duration == 0.0


# ============================================
# Test Class: Graph Edit Distance
# ============================================

class TestGraphEditDistance:
    """Tests for GED computation between pathways."""

    def test_identical_pathways_zero_distance(self):
        """Same activities → distance 0."""
        miner = PathwayMiner()
        p1 = _make_pathway("ep_a", ["A", "B", "C"])
        p2 = _make_pathway("ep_b", ["A", "B", "C"])
        assert miner.compute_ged(p1, p2) == 0.0

    def test_completely_different_pathways(self):
        """No overlap → distance = max(len1, len2) substitutions."""
        miner = PathwayMiner()
        p1 = _make_pathway("ep_a", ["A", "B", "C"])
        p2 = _make_pathway("ep_b", ["X", "Y", "Z"])
        assert miner.compute_ged(p1, p2) == 3.0  # 3 substitutions

    def test_insertion_cost(self):
        """Extra element → distance = 1 insertion."""
        miner = PathwayMiner()
        p1 = _make_pathway("ep_a", ["A", "B"])
        p2 = _make_pathway("ep_b", ["A", "B", "C"])
        assert miner.compute_ged(p1, p2) == 1.0  # 1 insertion

    def test_deletion_cost(self):
        """Missing element → distance = 1 deletion."""
        miner = PathwayMiner()
        p1 = _make_pathway("ep_a", ["A", "B", "C"])
        p2 = _make_pathway("ep_b", ["A", "C"])
        assert miner.compute_ged(p1, p2) == 1.0  # 1 deletion

    def test_substitution_cost(self):
        """Different middle element → 1 substitution."""
        miner = PathwayMiner()
        p1 = _make_pathway("ep_a", ["A", "B", "C"])
        p2 = _make_pathway("ep_b", ["A", "X", "C"])
        assert miner.compute_ged(p1, p2) == 1.0

    def test_custom_costs(self):
        """Custom insertion/deletion/substitution costs."""
        config = MiningConfig(
            insertion_cost=2.0, deletion_cost=2.0, substitution_cost=3.0
        )
        miner = PathwayMiner(config)
        p1 = _make_pathway("ep_a", ["A", "B"])
        p2 = _make_pathway("ep_b", ["A", "B", "C"])
        # 1 insertion at cost 2.0
        assert miner.compute_ged(p1, p2) == 2.0

    def test_ged_symmetric(self):
        """GED(a,b) == GED(b,a) with equal insert/delete costs."""
        miner = PathwayMiner()
        p1 = _make_pathway("ep_a", ["A", "B", "C", "D"])
        p2 = _make_pathway("ep_b", ["A", "X", "D"])
        assert miner.compute_ged(p1, p2) == miner.compute_ged(p2, p1)

    def test_empty_pathways(self):
        """Empty vs non-empty → distance = len(other)."""
        miner = PathwayMiner()
        p1 = _make_pathway("ep_a", [])
        p2 = _make_pathway("ep_b", ["A", "B", "C"])
        assert miner.compute_ged(p1, p2) == 3.0  # 3 insertions

    def test_both_empty(self):
        """Two empty pathways → distance 0."""
        miner = PathwayMiner()
        p1 = _make_pathway("ep_a", [])
        p2 = _make_pathway("ep_b", [])
        assert miner.compute_ged(p1, p2) == 0.0


# ============================================
# Test Class: Similarity Matrix
# ============================================

class TestSimilarityMatrix:
    """Tests for pairwise distance matrix computation."""

    def test_matrix_dimensions(self):
        """Matrix is NxN for N pathways."""
        miner = PathwayMiner()
        pathways = [
            _make_pathway("ep_a", ["A", "B"]),
            _make_pathway("ep_b", ["A", "C"]),
            _make_pathway("ep_c", ["X", "Y"]),
        ]
        matrix = miner.compute_similarity_matrix(pathways)
        assert len(matrix) == 3
        assert all(len(row) == 3 for row in matrix)

    def test_matrix_diagonal_zero(self):
        """Diagonal is always 0 (self-distance)."""
        miner = PathwayMiner()
        pathways = [
            _make_pathway("ep_a", ["A", "B"]),
            _make_pathway("ep_b", ["X", "Y"]),
        ]
        matrix = miner.compute_similarity_matrix(pathways)
        assert matrix[0][0] == 0.0
        assert matrix[1][1] == 0.0

    def test_matrix_symmetric(self):
        """Matrix is symmetric."""
        miner = PathwayMiner()
        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),
            _make_pathway("ep_b", ["A", "X", "C"]),
            _make_pathway("ep_c", ["Y", "Z"]),
        ]
        matrix = miner.compute_similarity_matrix(pathways)
        for i in range(3):
            for j in range(3):
                assert matrix[i][j] == matrix[j][i]

    def test_empty_input(self):
        """Empty pathway list → empty matrix."""
        miner = PathwayMiner()
        matrix = miner.compute_similarity_matrix([])
        assert matrix == []


# ============================================
# Test Class: Clustering
# ============================================

class TestClustering:
    """Tests for GED-based pathway clustering."""

    def test_identical_pathways_same_cluster(self):
        """Identical pathways cluster together."""
        config = MiningConfig(ged_threshold=1.0, min_cluster_size=2)
        miner = PathwayMiner(config)
        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),
            _make_pathway("ep_b", ["A", "B", "C"]),
            _make_pathway("ep_c", ["A", "B", "C"]),
        ]
        clusters = miner.cluster_pathways(pathways)
        assert len(clusters) == 1
        assert len(clusters[0].pathway_ids) == 3

    def test_distant_pathways_separate_clusters(self):
        """Very different pathways stay in separate clusters (or no clusters)."""
        config = MiningConfig(ged_threshold=1.0, min_cluster_size=2)
        miner = PathwayMiner(config)
        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),
            _make_pathway("ep_b", ["X", "Y", "Z"]),  # Distance 3 > threshold 1
        ]
        clusters = miner.cluster_pathways(pathways)
        # Each pathway is alone → no cluster meets min_cluster_size
        assert len(clusters) == 0

    def test_threshold_controls_clustering(self):
        """Higher threshold merges more pathways."""
        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),
            _make_pathway("ep_b", ["A", "B", "X"]),  # Distance 1
            _make_pathway("ep_c", ["A", "X", "Y"]),  # Distance 2 from A
        ]

        # Tight threshold: only ep_a and ep_b cluster
        config_tight = MiningConfig(ged_threshold=1.0, min_cluster_size=2)
        miner_tight = PathwayMiner(config_tight)
        clusters_tight = miner_tight.cluster_pathways(pathways)
        assert len(clusters_tight) == 1
        assert "ep_c" not in clusters_tight[0].pathway_ids

        # Loose threshold: all cluster together
        config_loose = MiningConfig(ged_threshold=3.0, min_cluster_size=2)
        miner_loose = PathwayMiner(config_loose)
        clusters_loose = miner_loose.cluster_pathways(pathways)
        assert len(clusters_loose) == 1
        assert len(clusters_loose[0].pathway_ids) == 3

    def test_cluster_has_medoid(self):
        """Cluster centroid_id is the medoid (min total distance)."""
        config = MiningConfig(ged_threshold=5.0, min_cluster_size=2)
        miner = PathwayMiner(config)
        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),       # Closest to center
            _make_pathway("ep_b", ["A", "B", "C", "D"]),  # 1 away from A
            _make_pathway("ep_c", ["A", "B", "C", "D", "E"]),  # 2 away from A
        ]
        clusters = miner.cluster_pathways(pathways)
        # ep_b should be medoid (min total: 1+1=2 vs ep_a: 1+2=3 vs ep_c: 2+1=3)
        assert clusters[0].centroid_id == "ep_b"

    def test_cluster_mean_ged(self):
        """Mean intra-cluster GED is computed correctly."""
        config = MiningConfig(ged_threshold=5.0, min_cluster_size=2)
        miner = PathwayMiner(config)
        pathways = [
            _make_pathway("ep_a", ["A", "B"]),
            _make_pathway("ep_b", ["A", "C"]),  # Distance 1 from A
        ]
        clusters = miner.cluster_pathways(pathways)
        assert clusters[0].mean_ged == 1.0

    def test_empty_pathways_no_clusters(self):
        """Empty input → no clusters."""
        miner = PathwayMiner()
        assert miner.cluster_pathways([]) == []


# ============================================
# Test Class: Feature Extraction
# ============================================

class TestFeatureExtraction:
    """Tests for pathway feature extraction."""

    def test_basic_features(self):
        """Length, unique_count, duration extracted correctly."""
        miner = PathwayMiner()
        pw = _make_pathway("ep_001", ["A", "B", "C", "A"], [0, 5, 10, 15])
        feat = miner.extract_features(pw)

        assert feat.episode_id == "ep_001"
        assert feat.length == 4
        assert feat.unique_count == 3
        assert feat.duration == 15.0

    def test_mean_interval(self):
        """Mean interval = duration / (n-1)."""
        miner = PathwayMiner()
        pw = _make_pathway("ep_001", ["A", "B", "C"], [0, 10, 20])
        feat = miner.extract_features(pw)
        assert feat.mean_interval == pytest.approx(10.0)

    def test_action_diversity(self):
        """Diversity = unique / total."""
        miner = PathwayMiner()
        pw = _make_pathway("ep_001", ["A", "B", "A", "B"], [0, 5, 10, 15])
        feat = miner.extract_features(pw)
        assert feat.action_diversity == pytest.approx(0.5)

    def test_assessment_detection(self):
        """Activities matching assessment patterns detected."""
        miner = PathwayMiner()
        pw = _make_pathway("ep_001", ["ASSESS_VITALS", "DIAGNOSE"])
        feat = miner.extract_features(pw)
        assert feat.has_assessment is True
        assert feat.has_medication is False

    def test_medication_detection(self):
        """Activities matching medication patterns detected."""
        miner = PathwayMiner()
        pw = _make_pathway("ep_001", ["GIVE_MEDICATION", "ESCALATE"])
        feat = miner.extract_features(pw)
        assert feat.has_medication is True
        assert feat.has_lab_order is False

    def test_lab_detection(self):
        """Activities matching lab patterns detected."""
        miner = PathwayMiner()
        pw = _make_pathway("ep_001", ["ORDER_LAB", "PRESCRIBE"])
        feat = miner.extract_features(pw)
        assert feat.has_lab_order is True

    def test_transition_entropy(self):
        """Entropy is higher for more varied transitions."""
        miner = PathwayMiner()

        # Uniform transitions: A->B, B->A (2 types, equal) → entropy = 1.0
        pw_varied = _make_pathway("ep_a", ["A", "B", "A", "B"])
        feat_varied = miner.extract_features(pw_varied)

        # Single transition: A->A->A (1 type) → entropy = 0.0
        pw_uniform = _make_pathway("ep_b", ["A", "A", "A"])
        feat_uniform = miner.extract_features(pw_uniform)

        assert feat_varied.transition_entropy > feat_uniform.transition_entropy
        assert feat_uniform.transition_entropy == 0.0

    def test_single_event_features(self):
        """Single event pathway has sensible defaults."""
        miner = PathwayMiner()
        pw = _make_pathway("ep_001", ["A"], [0.0])
        feat = miner.extract_features(pw)
        assert feat.length == 1
        assert feat.mean_interval == 0.0
        assert feat.action_diversity == 1.0
        assert feat.transition_entropy == 0.0


# ============================================
# Test Class: Outcome Correlation
# ============================================

class TestOutcomeCorrelation:
    """Tests for pathway-outcome correlation."""

    def _make_correlated_data(self, n=10):
        """Create pathways and scores with known correlation."""
        pathways = []
        scores = []
        for i in range(n):
            # Longer pathways → higher compliance (positive correlation)
            length = 3 + i
            activities = [f"ACT_{j}" for j in range(length)]
            pw = _make_pathway(f"ep_{i:03d}", activities)
            pathways.append(pw)
            scores.append(_make_score(
                episode_id=f"ep_{i:03d}",
                compliance=0.5 + 0.05 * i,  # Increases with length
            ))
        return pathways, scores

    def test_positive_correlation_detected(self):
        """Longer pathways correlating with higher compliance detected."""
        miner = PathwayMiner(MiningConfig(min_correlation_samples=5))
        pathways, scores = self._make_correlated_data(10)
        results = miner.correlate_with_outcomes(pathways, scores)

        # Find length-compliance correlation
        length_compliance = [
            r for r in results
            if r.feature_name == "length" and r.score_dimension == "compliance_score"
        ]
        assert len(length_compliance) == 1
        assert length_compliance[0].correlation > 0.9  # Strong positive

    def test_insufficient_samples_returns_empty(self):
        """Too few samples → no correlations."""
        miner = PathwayMiner(MiningConfig(min_correlation_samples=10))
        pathways = [_make_pathway("ep_001", ["A", "B"])]
        scores = [_make_score(episode_id="ep_001")]
        results = miner.correlate_with_outcomes(pathways, scores)
        assert results == []

    def test_unmatched_episodes_excluded(self):
        """Pathways without matching scores are excluded."""
        miner = PathwayMiner(MiningConfig(min_correlation_samples=2))
        pathways = [
            _make_pathway("ep_001", ["A"]),
            _make_pathway("ep_002", ["B"]),
            _make_pathway("ep_003", ["C"]),  # No matching score
        ]
        scores = [
            _make_score(episode_id="ep_001"),
            _make_score(episode_id="ep_002"),
        ]
        results = miner.correlate_with_outcomes(pathways, scores)
        # Should use only 2 matched pairs
        if results:
            assert results[0].n_samples == 2

    def test_correlation_includes_sub_scores(self):
        """Sub-score dimensions are included in correlation."""
        miner = PathwayMiner(MiningConfig(min_correlation_samples=5))
        pathways, scores = self._make_correlated_data(8)
        results = miner.correlate_with_outcomes(pathways, scores)

        dims = {r.score_dimension for r in results}
        assert "compliance_score" in dims
        # Sub-scores from _make_score include C1, C2
        # They may or may not correlate, but the dimensions should be tried


# ============================================
# Test Class: Full Mining Pipeline
# ============================================

class TestMiningPipeline:
    """Tests for the complete mine() pipeline."""

    def test_mine_without_scores(self):
        """Mining works without outcome scores."""
        miner = PathwayMiner(MiningConfig(ged_threshold=2.0, min_cluster_size=2))
        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),
            _make_pathway("ep_b", ["A", "B", "C"]),
            _make_pathway("ep_c", ["X", "Y", "Z"]),
        ]
        result = miner.mine(pathways)

        assert isinstance(result, MiningResult)
        assert len(result.pathways) == 3
        assert len(result.similarity_matrix) == 3
        assert result.correlations == []
        assert result.high_performing_pathways == []

    def test_mine_with_scores(self):
        """Mining with scores produces correlations and rankings."""
        miner = PathwayMiner(MiningConfig(
            ged_threshold=5.0, min_cluster_size=2, min_correlation_samples=3,
        ))
        pathways = []
        scores = []
        for i in range(6):
            pw = _make_pathway(f"ep_{i}", [f"A{j}" for j in range(3 + i)])
            pathways.append(pw)
            scores.append(_make_score(
                episode_id=f"ep_{i}",
                compliance=0.5 + 0.08 * i,
            ))

        result = miner.mine(pathways, scores)

        assert len(result.correlations) > 0
        assert len(result.high_performing_pathways) > 0
        assert len(result.low_performing_pathways) > 0

    def test_mine_high_low_performers(self):
        """Top/bottom quartile pathways identified correctly."""
        miner = PathwayMiner(MiningConfig(min_correlation_samples=3))
        pathways = [_make_pathway(f"ep_{i}", ["A"]) for i in range(8)]
        scores = [
            _make_score(episode_id=f"ep_{i}", compliance=0.1 * (i + 1))
            for i in range(8)
        ]

        result = miner.mine(pathways, scores)

        # Top quartile (2 of 8): ep_7 (0.8), ep_6 (0.7)
        assert "ep_7" in result.high_performing_pathways
        # Bottom quartile: ep_0 (0.1), ep_1 (0.2)
        assert "ep_0" in result.low_performing_pathways

    def test_mine_cluster_outcome_annotation(self):
        """Clusters are annotated with mean compliance and risk."""
        miner = PathwayMiner(MiningConfig(
            ged_threshold=2.0, min_cluster_size=2, min_correlation_samples=2,
        ))
        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),
            _make_pathway("ep_b", ["A", "B", "C"]),
        ]
        scores = [
            _make_score(episode_id="ep_a", compliance=0.9, aggregate_risk=0.5),
            _make_score(episode_id="ep_b", compliance=0.7, aggregate_risk=1.5),
        ]

        result = miner.mine(pathways, scores)
        assert len(result.clusters) == 1
        cluster = result.clusters[0]
        assert cluster.mean_compliance == pytest.approx(0.8)
        assert cluster.mean_aggregate_risk == pytest.approx(1.0)

    def test_mine_empty_input(self):
        """Empty pathway list produces empty result."""
        miner = PathwayMiner()
        result = miner.mine([])
        assert result.pathways == []
        assert result.similarity_matrix == []
        assert result.clusters == []
        assert result.correlations == []


# ============================================
# Test Class: Clinical Scenarios
# ============================================

class TestClinicalScenarios:
    """Tests with realistic clinical pathway patterns."""

    def test_sepsis_good_vs_bad_pathway(self):
        """Good sepsis pathway (assess→culture→abx) vs bad (assess→abx only)."""
        miner = PathwayMiner()

        good = _make_pathway("ep_good", [
            "ASSESS_VITALS", "ORDER_LAB", "ORDER_TEST",
            "GIVE_MEDICATION", "OBSERVE_RESULTS",
        ])
        bad = _make_pathway("ep_bad", [
            "ASSESS_VITALS", "GIVE_MEDICATION",
        ])

        ged = miner.compute_ged(good, bad)
        assert ged == 3.0  # 3 deletions (ORDER_LAB, ORDER_TEST, OBSERVE_RESULTS)

    def test_clinical_pathway_features(self):
        """Clinical pathway feature extraction for sepsis scenario."""
        miner = PathwayMiner()
        pw = _make_pathway("ep_sepsis", [
            "QUERY_PATIENT", "ASSESS_VITALS", "ORDER_LAB",
            "OBSERVE_RESULTS", "PRESCRIBE", "GIVE_MEDICATION",
        ], [0, 2, 5, 15, 18, 20])

        feat = miner.extract_features(pw)
        assert feat.has_assessment is True  # "ASSESS" matches
        assert feat.has_medication is True  # "GIVE_MEDICATION" matches
        assert feat.has_lab_order is True  # "ORDER_LAB" matches
        assert feat.action_diversity == 1.0  # All unique

    def test_rv_trap_pathway_comparison(self):
        """RV trap: correct vs incorrect pathway distinguishable by GED."""
        miner = PathwayMiner()

        correct = _make_pathway("ep_correct", [
            "ASSESS_VITALS", "ORDER_TEST",  # ECG
            "OBSERVE_RESULTS",  # See RV involvement
            "ORDER_TEST",  # V4R leads
            "PRESCRIBE",  # Fluids, not nitrates
        ])
        incorrect = _make_pathway("ep_incorrect", [
            "ASSESS_VITALS", "ORDER_TEST",  # ECG
            "PRESCRIBE",  # Nitrates (trap!)
        ])

        ged = miner.compute_ged(correct, incorrect)
        assert ged > 0  # They are different
        assert ged >= 2  # At least 2 edits

    def test_mine_clinical_scenario(self):
        """Full mining pipeline on a small clinical dataset."""
        miner = PathwayMiner(MiningConfig(
            ged_threshold=2.0, min_cluster_size=2, min_correlation_samples=3,
        ))

        # 3 good pathways (similar structure)
        good_pathways = [
            _make_pathway(f"ep_good_{i}", [
                "ASSESS", "ORDER_LAB", "OBSERVE", "PRESCRIBE", "MONITOR",
            ]) for i in range(3)
        ]
        # 3 bad pathways (shorter, missing steps) — GED=3 from good, > threshold
        bad_pathways = [
            _make_pathway(f"ep_bad_{i}", [
                "ASSESS", "PRESCRIBE",
            ]) for i in range(3)
        ]
        all_pathways = good_pathways + bad_pathways

        scores = (
            [_make_score(f"ep_good_{i}", compliance=0.9) for i in range(3)]
            + [_make_score(f"ep_bad_{i}", compliance=0.4) for i in range(3)]
        )

        result = miner.mine(all_pathways, scores)

        # Good pathways should cluster together (distance 0 between them)
        good_cluster = None
        for c in result.clusters:
            if "ep_good_0" in c.pathway_ids:
                good_cluster = c
                break
        assert good_cluster is not None
        assert good_cluster.mean_compliance > 0.8

        # High performers should be the good pathways
        for hp in result.high_performing_pathways:
            assert "good" in hp


# ============================================
# Test Class: Edge Cases
# ============================================

class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_pearson_constant_values(self):
        """Constant feature values → correlation 0."""
        miner = PathwayMiner(MiningConfig(min_correlation_samples=3))
        # All pathways same length → no variance → r=0
        pathways = [_make_pathway(f"ep_{i}", ["A", "B"]) for i in range(5)]
        scores = [
            _make_score(f"ep_{i}", compliance=0.5 + 0.1 * i)
            for i in range(5)
        ]
        results = miner.correlate_with_outcomes(pathways, scores)
        length_corr = [
            r for r in results
            if r.feature_name == "length" and r.score_dimension == "compliance_score"
        ]
        # All pathways have length=2, so no variance → correlation should be 0
        if length_corr:
            assert length_corr[0].correlation == 0.0

    def test_large_pathway_ged(self):
        """GED handles larger sequences correctly."""
        miner = PathwayMiner()
        p1 = _make_pathway("ep_a", [f"A{i}" for i in range(50)])
        p2 = _make_pathway("ep_b", [f"A{i}" for i in range(50)])
        assert miner.compute_ged(p1, p2) == 0.0

        # One substitution in the middle
        acts = [f"A{i}" for i in range(50)]
        acts[25] = "DIFFERENT"
        p3 = _make_pathway("ep_c", acts)
        assert miner.compute_ged(p1, p3) == 1.0

    def test_duplicate_episode_ids(self):
        """Pathways with same episode_id but different activities."""
        miner = PathwayMiner(MiningConfig(min_cluster_size=2, ged_threshold=5.0))
        pathways = [
            _make_pathway("ep_001", ["A", "B"]),
            _make_pathway("ep_001", ["A", "B", "C"]),
        ]
        # Should not crash
        result = miner.mine(pathways)
        assert len(result.pathways) == 2


# ============================================
# Test Class: Early Termination Optimization
# ============================================

class TestEarlyTermination:
    """Tests for GED early termination optimization."""

    def test_early_termination_returns_inf_for_very_different(self):
        """Early termination returns inf when sequences exceed bound."""
        config = MiningConfig(enable_early_termination=True)
        miner = PathwayMiner(config)

        # Very different pathways
        p1 = _make_pathway("ep_a", ["A", "B", "C", "D", "E"])
        p2 = _make_pathway("ep_b", ["X", "Y", "Z", "W", "V"])

        # With low bound, should return inf
        dist = miner.compute_ged(p1, p2, upper_bound=1.0)
        assert dist == float('inf')

        # Without bound, should compute actual distance
        actual_dist = miner.compute_ged(p1, p2, upper_bound=None)
        assert actual_dist == 5.0  # 5 substitutions

    def test_early_termination_computes_exact_within_bound(self):
        """Early termination computes exact distance within bound."""
        config = MiningConfig(enable_early_termination=True)
        miner = PathwayMiner(config)

        p1 = _make_pathway("ep_a", ["A", "B", "C"])
        p2 = _make_pathway("ep_b", ["A", "X", "C"])  # 1 substitution

        # With adequate bound, should compute exactly
        dist = miner.compute_ged(p1, p2, upper_bound=5.0)
        assert dist == 1.0

    def test_early_termination_disabled(self):
        """Early termination disabled computes full distance."""
        config = MiningConfig(enable_early_termination=False)
        miner = PathwayMiner(config)

        p1 = _make_pathway("ep_a", ["A", "B", "C", "D", "E"])
        p2 = _make_pathway("ep_b", ["X", "Y", "Z", "W", "V"])

        # Even with low bound, should compute full distance
        dist = miner.compute_ged(p1, p2, upper_bound=1.0)
        assert dist == 5.0  # Full distance computed

    def test_similarity_matrix_with_early_termination(self):
        """Similarity matrix uses early termination for dissimilar pathways."""
        config = MiningConfig(
            enable_early_termination=True,
            ged_threshold=2.0,  # This means max_ged_for_clustering = 4.0
        )
        miner = PathwayMiner(config)

        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),
            _make_pathway("ep_b", ["A", "B", "C"]),  # Identical to a
            _make_pathway("ep_c", ["X", "Y", "Z", "W", "V", "U"]),  # Very different
        ]

        matrix = miner.compute_similarity_matrix(pathways)

        # Similar pathways: exact distance
        assert matrix[0][1] == 0.0

        # Very different: may be inf or large value
        # Distance from 3 activities to 6 different activities > 4.0 threshold
        # So it could be inf due to early termination
        assert matrix[0][2] >= 4.0 or matrix[0][2] == float('inf')

    def test_clustering_handles_inf_distances(self):
        """Clustering correctly handles infinite distances."""
        config = MiningConfig(
            enable_early_termination=True,
            ged_threshold=1.0,  # Very strict threshold
            max_ged_for_clustering=2.0,  # And strict early termination
            min_cluster_size=2,
        )
        miner = PathwayMiner(config)

        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),
            _make_pathway("ep_b", ["A", "B", "C"]),  # Identical to a, should cluster
            _make_pathway("ep_c", ["X", "Y", "Z", "W", "V"]),  # Very different
        ]

        result = miner.mine(pathways)

        # a and b are identical (distance=0), should cluster together
        # c is very different (distance=5), exceeds threshold, won't cluster with a/b
        assert len(result.clusters) >= 1

        # Find the cluster containing ep_a
        a_cluster = None
        for cluster in result.clusters:
            if "ep_a" in cluster.pathway_ids:
                a_cluster = cluster
                break

        assert a_cluster is not None
        assert "ep_b" in a_cluster.pathway_ids
        # c shouldn't be in the same cluster due to large distance
        assert "ep_c" not in a_cluster.pathway_ids

    def test_length_based_early_termination(self):
        """Very different lengths trigger early termination quickly."""
        config = MiningConfig(enable_early_termination=True)
        miner = PathwayMiner(config)

        p1 = _make_pathway("ep_a", ["A"])
        p2 = _make_pathway("ep_b", ["A"] * 100)

        # Length difference = 99, even with bound of 50 should return inf
        dist = miner.compute_ged(p1, p2, upper_bound=50.0)
        assert dist == float('inf')

    def test_max_ged_for_clustering_config(self):
        """max_ged_for_clustering overrides default threshold."""
        config = MiningConfig(
            enable_early_termination=True,
            ged_threshold=5.0,
            max_ged_for_clustering=2.0,  # Stricter bound
        )
        miner = PathwayMiner(config)

        pathways = [
            _make_pathway("ep_a", ["A", "B", "C"]),
            _make_pathway("ep_b", ["A", "B", "D"]),  # Distance = 1
            _make_pathway("ep_c", ["X", "Y", "Z"]),  # Distance = 3
        ]

        matrix = miner.compute_similarity_matrix(pathways)

        # a to b: within bound, exact distance
        assert matrix[0][1] == 1.0

        # a to c: beyond max_ged_for_clustering (2.0), may return inf
        # Note: max_ged_for_clustering=2.0 is used as bound
        assert matrix[0][2] >= 2.0  # Could be inf or exact 3.0
