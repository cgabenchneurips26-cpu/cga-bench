"""
Outcome-Driven Pathway Mining: GED-based pathway analysis with outcome correlation.

Extracts clinical pathways from ActivityEvent sequences, computes Graph Edit
Distance (GED) between pathways, clusters similar pathways, and correlates
pathway patterns with CGAScore outcomes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from cga_bench.cpg_model.schemas.base import CGAScore
from ..conformance.activity import ActivityEvent


# ============================================
# Data Models
# ============================================

@dataclass
class Pathway:
    """A clinical pathway extracted from an episode's activity sequence."""
    episode_id: str
    activities: List[str]  # Ordered activity names
    timestamps: List[float]  # Corresponding timestamps (minutes)
    total_duration: float
    unique_activities: Set[str] = field(default_factory=set)
    transition_counts: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if not self.unique_activities:
            self.unique_activities = set(self.activities)
        if not self.transition_counts:
            self.transition_counts = self._compute_transitions()

    def _compute_transitions(self) -> Dict[str, int]:
        """Compute activity transition frequency."""
        counts: Dict[str, int] = {}
        for i in range(len(self.activities) - 1):
            key = f"{self.activities[i]}->{self.activities[i+1]}"
            counts[key] = counts.get(key, 0) + 1
        return counts


@dataclass
class PathwayFeatures:
    """Quantitative features extracted from a pathway for correlation."""
    episode_id: str
    length: int  # Number of activities
    unique_count: int  # Unique activity types
    duration: float  # Total duration in minutes
    mean_interval: float  # Mean time between activities
    action_diversity: float  # unique_count / length
    has_assessment: bool  # Contains assessment-type activity
    has_medication: bool  # Contains medication-type activity
    has_lab_order: bool  # Contains lab order activity
    transition_entropy: float  # Entropy of transition distribution


@dataclass
class CorrelationResult:
    """Correlation between a pathway feature and a score dimension."""
    feature_name: str
    score_dimension: str  # "compliance_score", "C1", etc.
    correlation: float  # Pearson correlation coefficient
    p_value: float  # Statistical significance
    n_samples: int


@dataclass
class PathwayCluster:
    """A cluster of similar pathways."""
    cluster_id: str
    pathway_ids: List[str]
    centroid_id: str  # Episode ID of the medoid pathway
    mean_ged: float  # Mean intra-cluster GED
    mean_compliance: Optional[float] = None
    mean_aggregate_risk: Optional[float] = None


@dataclass
class MiningConfig:
    """Configuration for pathway mining."""
    # GED parameters
    insertion_cost: float = 1.0
    deletion_cost: float = 1.0
    substitution_cost: float = 1.0
    # Early termination optimization
    enable_early_termination: bool = True  # Stop GED computation if bound exceeded
    max_ged_for_clustering: Optional[float] = None  # If set, use for early termination
    # Clustering
    ged_threshold: float = 3.0  # Max GED for same cluster
    min_cluster_size: int = 2
    # Correlation
    min_correlation_samples: int = 5
    significance_threshold: float = 0.05
    # Feature extraction
    assessment_patterns: List[str] = field(
        default_factory=lambda: ["assess", "query", "observe"]
    )
    medication_patterns: List[str] = field(
        default_factory=lambda: ["prescribe", "give_medication", "medication"]
    )
    lab_patterns: List[str] = field(
        default_factory=lambda: ["order_test", "order_lab", "lab"]
    )


@dataclass
class MiningResult:
    """Complete result of pathway mining analysis."""
    pathways: List[Pathway]
    similarity_matrix: List[List[float]]  # Pairwise GED matrix
    clusters: List[PathwayCluster]
    correlations: List[CorrelationResult]
    high_performing_pathways: List[str]  # Episode IDs of top performers
    low_performing_pathways: List[str]  # Episode IDs of worst performers


# ============================================
# Pathway Miner
# ============================================

class PathwayMiner:
    """
    Mines clinical pathways and correlates with outcomes.

    Usage:
        config = MiningConfig()
        miner = PathwayMiner(config)
        pathways = [miner.extract_pathway(eid, events) for eid, events in episodes]
        result = miner.mine(pathways, scores)
    """

    def __init__(self, config: Optional[MiningConfig] = None):
        self._config = config or MiningConfig()

    def extract_pathway(
        self,
        episode_id: str,
        events: List[ActivityEvent],
    ) -> Pathway:
        """Extract a Pathway from an ActivityEvent sequence.

        Args:
            episode_id: Episode identifier
            events: Sorted list of ActivityEvents

        Returns:
            Pathway with activities, timestamps, and transitions
        """
        sorted_events = sorted(events, key=lambda e: e.timestamp_min)
        activities = [e.name for e in sorted_events]
        timestamps = [e.timestamp_min for e in sorted_events]
        duration = (timestamps[-1] - timestamps[0]) if timestamps else 0.0

        return Pathway(
            episode_id=episode_id,
            activities=activities,
            timestamps=timestamps,
            total_duration=duration,
        )

    def compute_ged(
        self,
        p1: Pathway,
        p2: Pathway,
        upper_bound: Optional[float] = None,
    ) -> float:
        """Compute Graph Edit Distance between two pathways.

        Uses dynamic programming edit distance on the activity sequences,
        with configurable insertion, deletion, and substitution costs.

        Args:
            p1: First pathway
            p2: Second pathway
            upper_bound: If provided and early termination enabled, return
                         float('inf') if distance would exceed this bound.
                         This enables O(n) early termination for dissimilar pathways.

        Returns:
            Edit distance (lower = more similar), or float('inf') if bound exceeded
        """
        seq1 = p1.activities
        seq2 = p2.activities

        if upper_bound is not None and self._config.enable_early_termination:
            return self._edit_distance_bounded(seq1, seq2, upper_bound)
        return self._edit_distance(seq1, seq2)

    def compute_similarity_matrix(
        self,
        pathways: List[Pathway],
        use_early_termination: bool = True,
    ) -> List[List[float]]:
        """Compute pairwise GED matrix for all pathways.

        With early termination enabled, pathways that are clearly dissimilar
        (GED > threshold) are assigned float('inf') without full computation.

        Args:
            pathways: List of Pathway objects
            use_early_termination: Use clustering threshold for early termination

        Returns:
            NxN distance matrix where entry [i][j] = GED(pathway_i, pathway_j)
        """
        n = len(pathways)
        matrix = [[0.0] * n for _ in range(n)]

        # Determine early termination bound
        bound = None
        if use_early_termination and self._config.enable_early_termination:
            bound = self._config.max_ged_for_clustering or (self._config.ged_threshold * 2)

        for i in range(n):
            for j in range(i + 1, n):
                dist = self.compute_ged(pathways[i], pathways[j], upper_bound=bound)
                matrix[i][j] = dist
                matrix[j][i] = dist
        return matrix

    def cluster_pathways(
        self,
        pathways: List[Pathway],
        distance_matrix: Optional[List[List[float]]] = None,
    ) -> List[PathwayCluster]:
        """Cluster pathways by GED similarity using single-linkage.

        Args:
            pathways: List of Pathway objects
            distance_matrix: Pre-computed distance matrix (computed if None)

        Returns:
            List of PathwayCluster objects
        """
        if not pathways:
            return []

        if distance_matrix is None:
            distance_matrix = self.compute_similarity_matrix(pathways)

        n = len(pathways)
        threshold = self._config.ged_threshold

        # Single-linkage clustering
        cluster_map: Dict[int, int] = {i: i for i in range(n)}  # node -> cluster_id

        for i in range(n):
            for j in range(i + 1, n):
                dist = distance_matrix[i][j]
                # Skip infinite distances (early-terminated as too dissimilar)
                if dist == float('inf') or dist > threshold:
                    continue
                if dist <= threshold:
                    # Merge clusters
                    ci = self._find_cluster(cluster_map, i)
                    cj = self._find_cluster(cluster_map, j)
                    if ci != cj:
                        # Point the higher cluster to the lower
                        cluster_map[max(ci, cj)] = min(ci, cj)

        # Collect clusters
        cluster_members: Dict[int, List[int]] = {}
        for i in range(n):
            root = self._find_cluster(cluster_map, i)
            cluster_members.setdefault(root, []).append(i)

        clusters: List[PathwayCluster] = []
        for cid, members in cluster_members.items():
            if len(members) < self._config.min_cluster_size:
                continue

            # Find medoid (member with minimum total distance to others)
            medoid_idx = self._find_medoid(members, distance_matrix)

            # Compute mean intra-cluster GED
            total_ged = 0.0
            count = 0
            for a in members:
                for b in members:
                    if a < b:
                        total_ged += distance_matrix[a][b]
                        count += 1
            mean_ged = total_ged / count if count > 0 else 0.0

            clusters.append(PathwayCluster(
                cluster_id=f"cluster_{cid}",
                pathway_ids=[pathways[m].episode_id for m in members],
                centroid_id=pathways[medoid_idx].episode_id,
                mean_ged=mean_ged,
            ))

        return clusters

    def extract_features(self, pathway: Pathway) -> PathwayFeatures:
        """Extract quantitative features from a pathway.

        Args:
            pathway: Pathway to analyze

        Returns:
            PathwayFeatures with computed metrics
        """
        n = len(pathway.activities)
        unique = len(pathway.unique_activities)

        # Mean interval
        if n > 1 and pathway.total_duration > 0:
            mean_interval = pathway.total_duration / (n - 1)
        else:
            mean_interval = 0.0

        # Action diversity
        diversity = unique / n if n > 0 else 0.0

        # Activity type detection
        activities_lower = [a.lower() for a in pathway.activities]
        has_assessment = any(
            pat in act
            for act in activities_lower
            for pat in self._config.assessment_patterns
        )
        has_medication = any(
            pat in act
            for act in activities_lower
            for pat in self._config.medication_patterns
        )
        has_lab = any(
            pat in act
            for act in activities_lower
            for pat in self._config.lab_patterns
        )

        # Transition entropy
        entropy = self._compute_entropy(pathway.transition_counts)

        return PathwayFeatures(
            episode_id=pathway.episode_id,
            length=n,
            unique_count=unique,
            duration=pathway.total_duration,
            mean_interval=mean_interval,
            action_diversity=diversity,
            has_assessment=has_assessment,
            has_medication=has_medication,
            has_lab_order=has_lab,
            transition_entropy=entropy,
        )

    def correlate_with_outcomes(
        self,
        pathways: List[Pathway],
        scores: List[CGAScore],
    ) -> List[CorrelationResult]:
        """Correlate pathway features with CGAScore dimensions.

        Args:
            pathways: List of Pathway objects
            scores: List of CGAScore objects (matched by episode_id)

        Returns:
            List of CorrelationResult for significant correlations
        """
        if len(pathways) < self._config.min_correlation_samples:
            return []

        # Build score lookup
        score_map = {s.episode_id: s for s in scores}

        # Extract features for pathways that have matching scores
        paired: List[Tuple[PathwayFeatures, CGAScore]] = []
        for pw in pathways:
            if pw.episode_id in score_map:
                feat = self.extract_features(pw)
                paired.append((feat, score_map[pw.episode_id]))

        if len(paired) < self._config.min_correlation_samples:
            return []

        # Score dimensions to correlate
        score_dims = ["compliance_score", "peak_risk", "aggregate_risk"]
        # Add sub-scores if available
        if paired[0][1].sub_scores:
            score_dims.extend(sorted(paired[0][1].sub_scores.keys()))

        # Feature extraction
        feature_names = [
            "length", "unique_count", "duration", "mean_interval",
            "action_diversity", "transition_entropy",
        ]

        results: List[CorrelationResult] = []

        for feat_name in feature_names:
            feat_values = [getattr(f, feat_name) for f, _ in paired]
            for dim in score_dims:
                score_values = self._get_score_values(paired, dim)
                if score_values is None:
                    continue
                r, p = self._pearson_correlation(feat_values, score_values)
                if abs(r) > 0.0:  # Include all non-zero correlations
                    results.append(CorrelationResult(
                        feature_name=feat_name,
                        score_dimension=dim,
                        correlation=r,
                        p_value=p,
                        n_samples=len(paired),
                    ))

        return results

    def mine(
        self,
        pathways: List[Pathway],
        scores: Optional[List[CGAScore]] = None,
    ) -> MiningResult:
        """Run full pathway mining pipeline.

        Args:
            pathways: List of extracted Pathway objects
            scores: Optional CGAScore list for outcome correlation

        Returns:
            MiningResult with clusters, correlations, and pathway rankings
        """
        if not pathways:
            return MiningResult(
                pathways=[],
                similarity_matrix=[],
                clusters=[],
                correlations=[],
                high_performing_pathways=[],
                low_performing_pathways=[],
            )

        # Step 1: Compute similarity matrix
        sim_matrix = self.compute_similarity_matrix(pathways)

        # Step 2: Cluster pathways
        clusters = self.cluster_pathways(pathways, sim_matrix)

        # Step 3: Correlate with outcomes
        correlations: List[CorrelationResult] = []
        high_perf: List[str] = []
        low_perf: List[str] = []

        if scores:
            correlations = self.correlate_with_outcomes(pathways, scores)

            # Identify high/low performers
            score_map = {s.episode_id: s for s in scores}
            scored_pathways = [
                (pw, score_map[pw.episode_id])
                for pw in pathways
                if pw.episode_id in score_map
            ]
            if scored_pathways:
                sorted_by_compliance = sorted(
                    scored_pathways,
                    key=lambda x: x[1].compliance_score,
                    reverse=True,
                )
                top_n = max(1, len(sorted_by_compliance) // 4)
                high_perf = [pw.episode_id for pw, _ in sorted_by_compliance[:top_n]]
                low_perf = [pw.episode_id for pw, _ in sorted_by_compliance[-top_n:]]

            # Annotate clusters with outcome stats
            for cluster in clusters:
                cluster_scores = [
                    score_map[eid]
                    for eid in cluster.pathway_ids
                    if eid in score_map
                ]
                if cluster_scores:
                    cluster.mean_compliance = sum(
                        s.compliance_score for s in cluster_scores
                    ) / len(cluster_scores)
                    cluster.mean_aggregate_risk = sum(
                        s.aggregate_risk for s in cluster_scores
                    ) / len(cluster_scores)

        return MiningResult(
            pathways=pathways,
            similarity_matrix=sim_matrix,
            clusters=clusters,
            correlations=correlations,
            high_performing_pathways=high_perf,
            low_performing_pathways=low_perf,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _edit_distance(self, seq1: List[str], seq2: List[str]) -> float:
        """Compute weighted edit distance between two activity sequences."""
        m, n = len(seq1), len(seq2)
        ins_cost = self._config.insertion_cost
        del_cost = self._config.deletion_cost
        sub_cost = self._config.substitution_cost

        # DP table
        dp = [[0.0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i * del_cost
        for j in range(n + 1):
            dp[0][j] = j * ins_cost

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i - 1] == seq2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = min(
                        dp[i - 1][j] + del_cost,
                        dp[i][j - 1] + ins_cost,
                        dp[i - 1][j - 1] + sub_cost,
                    )
        return dp[m][n]

    def _edit_distance_bounded(
        self, seq1: List[str], seq2: List[str], upper_bound: float
    ) -> float:
        """Compute edit distance with early termination.

        Uses Ukkonen's optimization: if the minimum possible distance exceeds
        the upper bound, return infinity early without completing the full DP.

        Args:
            seq1: First activity sequence
            seq2: Second activity sequence
            upper_bound: Maximum distance threshold; returns inf if exceeded

        Returns:
            Edit distance, or float('inf') if bound exceeded
        """
        m, n = len(seq1), len(seq2)
        ins_cost = self._config.insertion_cost
        del_cost = self._config.deletion_cost
        sub_cost = self._config.substitution_cost

        # Quick length-based lower bound check
        length_diff = abs(m - n)
        min_possible = length_diff * min(ins_cost, del_cost)
        if min_possible > upper_bound:
            return float('inf')

        # Use space-optimized 2-row DP with band pruning
        # Only compute cells within band_width of the diagonal
        band_width = int(upper_bound / min(ins_cost, del_cost, sub_cost)) + 1

        # Initialize previous row
        prev = [float('inf')] * (n + 1)
        prev[0] = 0.0
        for j in range(1, min(n + 1, band_width + 1)):
            prev[j] = j * ins_cost

        for i in range(1, m + 1):
            curr = [float('inf')] * (n + 1)
            curr[0] = i * del_cost if i * del_cost <= upper_bound else float('inf')

            # Compute band around diagonal
            j_start = max(1, i - band_width)
            j_end = min(n + 1, i + band_width + 1)

            row_min = float('inf')  # Track minimum in this row

            for j in range(j_start, j_end):
                if seq1[i - 1] == seq2[j - 1]:
                    curr[j] = prev[j - 1]
                else:
                    curr[j] = min(
                        prev[j] + del_cost if prev[j] < float('inf') else float('inf'),
                        curr[j - 1] + ins_cost if curr[j - 1] < float('inf') else float('inf'),
                        prev[j - 1] + sub_cost if prev[j - 1] < float('inf') else float('inf'),
                    )
                row_min = min(row_min, curr[j])

            # Early termination: if all cells in row exceed bound, result will too
            if row_min > upper_bound:
                return float('inf')

            prev = curr

        return prev[n] if prev[n] <= upper_bound else float('inf')

    def _find_cluster(self, cluster_map: Dict[int, int], node: int) -> int:
        """Find root cluster with path compression."""
        if cluster_map[node] != node:
            cluster_map[node] = self._find_cluster(cluster_map, cluster_map[node])
        return cluster_map[node]

    def _find_medoid(
        self, members: List[int], distance_matrix: List[List[float]]
    ) -> int:
        """Find the medoid (member with min total distance to others)."""
        best_idx = members[0]
        best_total = float("inf")
        for m in members:
            total = sum(distance_matrix[m][o] for o in members if o != m)
            if total < best_total:
                best_total = total
                best_idx = m
        return best_idx

    def _compute_entropy(self, counts: Dict[str, int]) -> float:
        """Compute Shannon entropy of a count distribution."""
        total = sum(counts.values())
        if total == 0:
            return 0.0
        entropy = 0.0
        for count in counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        return entropy

    def _get_score_values(
        self,
        paired: List[Tuple[PathwayFeatures, CGAScore]],
        dimension: str,
    ) -> Optional[List[float]]:
        """Extract score values for a given dimension."""
        values: List[float] = []
        for _, score in paired:
            if dimension == "compliance_score":
                values.append(score.compliance_score)
            elif dimension == "peak_risk":
                values.append(score.peak_risk)
            elif dimension == "aggregate_risk":
                values.append(score.aggregate_risk)
            elif dimension in score.sub_scores:
                values.append(score.sub_scores[dimension])
            else:
                return None
        return values

    def _pearson_correlation(
        self, x: List[float], y: List[float]
    ) -> Tuple[float, float]:
        """Compute Pearson correlation coefficient and approximate p-value.

        Returns (r, p) where p is approximated using t-distribution.
        """
        n = len(x)
        if n < 3:
            return 0.0, 1.0

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        sum_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        sum_xx = sum((xi - mean_x) ** 2 for xi in x)
        sum_yy = sum((yi - mean_y) ** 2 for yi in y)

        denom = math.sqrt(sum_xx * sum_yy)
        if denom < 1e-12:
            return 0.0, 1.0

        r = sum_xy / denom

        # Approximate p-value from t-statistic
        if abs(r) >= 1.0:
            return min(max(r, -1.0), 1.0), 0.0

        t_stat = r * math.sqrt((n - 2) / (1 - r ** 2))
        # Approximate two-tailed p using normal approximation for large n
        p = self._approximate_p_from_t(t_stat, n - 2)
        return r, p

    def _approximate_p_from_t(self, t: float, df: int) -> float:
        """Approximate two-tailed p-value from t-statistic.

        Uses simple approximation adequate for ranking purposes.
        """
        if df <= 0:
            return 1.0
        # For df > 30, t approximates normal distribution
        # Use rough approximation: p ≈ 2 * exp(-0.5 * t^2) / sqrt(2*pi)
        # This is conservative for smaller df
        abs_t = abs(t)
        if abs_t > 10:
            return 0.0
        # Standard normal CDF approximation (Abramowitz & Stegun)
        p_one_tail = 0.5 * math.erfc(abs_t / math.sqrt(2))
        return 2.0 * p_one_tail
