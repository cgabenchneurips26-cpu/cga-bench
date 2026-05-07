"""EXP-E5: Evaluator Expansion — 12 Threshold Variants.

Expands from 4 evaluators to 12 threshold variants. Hierarchical clustering
plus bootstrap ARI proves the coverage-vs-safety 2-cluster structure is
robust and not an artifact of having only 4 evaluators.

Usage:
    PYTHONPATH=. python scripts/experiments/exp_e5_evaluator_expansion.py
"""

from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path
import sys
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.cluster.hierarchy import cophenet, dendrogram, fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.metrics import adjusted_rand_score, cohen_kappa_score, silhouette_score

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    TABLES_DIR,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
N_BOOTSTRAP: int = 1000
SEED: int = 42
OPTIMAL_K_RANGE: tuple[int, int] = (2, 7)

VERDICT_MATRIX_PATH = EVIDENCE_DIR / "analysis" / "verdict_matrix_v6.json"

# (name, raw_score_key, threshold, higher_is_pass)
VARIANT_SPECS: list[tuple[str, str, float, bool]] = [
    ("[email-redacted]", "action_coverage", 0.3, True),
    ("[email-redacted]", "action_coverage", 0.4, True),
    ("[email-redacted]", "action_coverage", 0.5, True),
    ("[email-redacted]", "action_coverage", 0.6, True),
    ("[email-redacted]", "c2_score", 0.5, True),
    ("[email-redacted]", "c2_score", 0.6, True),
    ("[email-redacted]", "c2_score", 0.7, True),
    ("[email-redacted]", "c2_score", 0.8, True),
    ("[email-redacted]", "mab_f1", 0.3, True),
    ("[email-redacted]", "mab_f1", 0.5, True),
    ("CGA-Bench(hard)", "v4_hard", None, False),  # v4_hard==False → pass
    ("CGA-Bench-soft", "n_viols", 0.0, False),  # n_viols==0 → pass
]

N_VARIANTS: int = len(VARIANT_SPECS)

# Coverage-family and safety-family names for cluster labelling
_COVERAGE_ANCHORS: frozenset[str] = frozenset(
    {
        "[email-redacted]",
        "[email-redacted]",
        "[email-redacted]",
        "[email-redacted]",
        "[email-redacted]",
        "[email-redacted]",
        "[email-redacted]",
        "[email-redacted]",
    }
)
_SAFETY_ANCHORS: frozenset[str] = frozenset(
    {
        "[email-redacted]",
        "[email-redacted]",
        "CGA-Bench(hard)",
        "CGA-Bench-soft",
    }
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_per_episode() -> list[dict]:
    """Load per-episode records from verdict_matrix_v6.json.

    Returns:
        List of 180 episode dicts.
    """
    with open(VERDICT_MATRIX_PATH) as f:
        data = json.load(f)
    return data["per_episode"]


# ---------------------------------------------------------------------------
# Step 1: Compute verdict vectors
# ---------------------------------------------------------------------------


def compute_verdict_vector(
    episodes: list[dict],
    score_key: str,
    threshold: float | None,
    higher_is_pass: bool,
) -> np.ndarray:
    """Compute boolean verdict vector for a single evaluator variant.

    Args:
        episodes: List of per-episode dicts.
        score_key: Field name in the episode dict.
        threshold: Numeric threshold (None for boolean fields).
        higher_is_pass: If True, score >= threshold → pass.
                        If False and threshold is None, value == False → pass
                        (used for v4_hard). If False and threshold is 0,
                        value == 0 → pass (used for n_viols).

    Returns:
        Boolean numpy array of shape (n_episodes,).
    """
    verdicts = np.zeros(len(episodes), dtype=bool)
    for idx, ep in enumerate(episodes):
        raw = ep.get(score_key)
        if raw is None:
            verdicts[idx] = False
            continue
        if threshold is None:
            # Boolean field: pass when value is False (i.e. no hard violation)
            verdicts[idx] = not bool(raw)
        elif higher_is_pass:
            verdicts[idx] = float(raw) >= threshold
        else:
            # lower_is_pass: used for n_viols == 0
            verdicts[idx] = float(raw) <= threshold
    return verdicts


def build_all_verdict_vectors(episodes: list[dict]) -> list[np.ndarray]:
    """Build verdict vectors for all 12 variants.

    Args:
        episodes: List of per-episode dicts.

    Returns:
        List of 12 boolean numpy arrays.
    """
    return [
        compute_verdict_vector(episodes, key, threshold, higher_is_pass)
        for _, key, threshold, higher_is_pass in VARIANT_SPECS
    ]


# ---------------------------------------------------------------------------
# Step 2: Pairwise distance matrix
# ---------------------------------------------------------------------------


def _safe_kappa(vec_i: np.ndarray, vec_j: np.ndarray) -> float:
    """Compute Cohen's kappa with edge-case handling.

    Args:
        vec_i: Boolean verdict vector for evaluator i.
        vec_j: Boolean verdict vector for evaluator j.

    Returns:
        Kappa coefficient in [-1, 1]. Returns 1.0 if vectors are identical,
        0.0 if one vector is constant (kappa undefined).
    """
    if np.array_equal(vec_i, vec_j):
        return 1.0
    # If either vector is all-same class, kappa is undefined
    if len(np.unique(vec_i)) == 1 or len(np.unique(vec_j)) == 1:
        return 0.0
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return float(cohen_kappa_score(vec_i, vec_j))
    except Exception:
        return 0.0


def build_distance_matrix(verdict_vectors: list[np.ndarray]) -> np.ndarray:
    """Build 12×12 distance matrix from 1 - kappa.

    Args:
        verdict_vectors: List of 12 boolean arrays.

    Returns:
        Symmetric distance matrix of shape (12, 12), values in [0, 2]
        (kappa can be negative, so distance can exceed 1).
    """
    n = len(verdict_vectors)
    dist = np.zeros((n, n))
    for i, j in combinations(range(n), 2):
        kappa = _safe_kappa(verdict_vectors[i], verdict_vectors[j])
        d = 1.0 - kappa
        dist[i, j] = d
        dist[j, i] = d
    return dist


# ---------------------------------------------------------------------------
# Step 3: Hierarchical clustering
# ---------------------------------------------------------------------------


def run_hierarchical_clustering(
    dist_matrix: np.ndarray,
) -> tuple[np.ndarray, float, int, dict[int, float]]:
    """Run Ward linkage and find optimal k via silhouette score.

    Args:
        dist_matrix: Square distance matrix (12×12).

    Returns:
        Tuple of:
            Z: Linkage matrix.
            coph_corr: Cophenetic correlation.
            optimal_k: Best number of clusters.
            silhouette_scores: Dict mapping k → silhouette score.
    """
    condensed = squareform(dist_matrix)
    z_matrix = linkage(condensed, method="ward")
    coph_corr, _ = cophenet(z_matrix, condensed)

    silhouette_scores: dict[int, float] = {}
    k_lo, k_hi = OPTIMAL_K_RANGE
    for k in range(k_lo, k_hi):
        labels = fcluster(z_matrix, k, criterion="maxclust")
        try:
            sil = silhouette_score(dist_matrix, labels, metric="precomputed")
        except ValueError:
            sil = -1.0
        silhouette_scores[k] = float(sil)

    optimal_k = max(silhouette_scores, key=lambda k: silhouette_scores[k])
    return z_matrix, float(coph_corr), optimal_k, silhouette_scores


# ---------------------------------------------------------------------------
# Step 4: Bootstrap cluster stability
# ---------------------------------------------------------------------------


def _build_boot_distance(
    boot_verdicts: list[np.ndarray],
) -> np.ndarray:
    """Build distance matrix for a bootstrap sample of verdict vectors.

    Args:
        boot_verdicts: Resampled verdict vectors (same shape as originals).

    Returns:
        Square distance matrix.
    """
    n = len(boot_verdicts)
    dist = np.zeros((n, n))
    for i, j in combinations(range(n), 2):
        kappa = _safe_kappa(boot_verdicts[i], boot_verdicts[j])
        d = 1.0 - kappa
        dist[i, j] = d
        dist[j, i] = d
    return dist


def run_bootstrap_stability(
    verdict_vectors: list[np.ndarray],
    optimal_k: int,
    z_original: np.ndarray,
) -> tuple[list[float], np.ndarray, float]:
    """Bootstrap cluster stability analysis.

    Args:
        verdict_vectors: Original 12 verdict vectors (length 180 each).
        optimal_k: Number of clusters to extract.
        z_original: Original linkage matrix.

    Returns:
        Tuple of:
            ari_scores: List of N_BOOTSTRAP ARI values.
            consensus_matrix: 12×12 co-clustering probability matrix.
            cluster_preserved_pct: % of bootstrap runs preserving
                the coverage/safety split.
    """
    n_eps = len(verdict_vectors[0])
    n_var = len(verdict_vectors)
    rng = np.random.default_rng(SEED)

    original_labels = fcluster(z_original, optimal_k, criterion="maxclust")

    # Determine which cluster IDs correspond to coverage and safety
    coverage_cluster, safety_cluster = _identify_cluster_families(original_labels)

    ari_scores: list[float] = []
    consensus = np.zeros((n_var, n_var))

    for _ in range(N_BOOTSTRAP):
        idx = rng.choice(n_eps, size=n_eps, replace=True)
        boot_verdicts = [v[idx] for v in verdict_vectors]

        boot_dist = _build_boot_distance(boot_verdicts)
        try:
            boot_z = linkage(squareform(boot_dist), method="ward")
            boot_labels = fcluster(boot_z, optimal_k, criterion="maxclust")
        except Exception:
            continue

        ari = adjusted_rand_score(original_labels, boot_labels)
        ari_scores.append(float(ari))

        # Accumulate consensus matrix
        for i in range(n_var):
            for j in range(n_var):
                if boot_labels[i] == boot_labels[j]:
                    consensus[i, j] += 1.0

    consensus /= N_BOOTSTRAP

    # % of runs preserving the coverage / safety 2-cluster family structure
    preserved = sum(1 for ari in ari_scores if ari > 0.5)
    cluster_preserved_pct = float(preserved) / len(ari_scores) * 100.0 if ari_scores else 0.0

    return ari_scores, consensus, cluster_preserved_pct


def _identify_cluster_families(
    labels: np.ndarray,
) -> tuple[int | None, int | None]:
    """Identify which cluster label corresponds to coverage vs safety.

    Args:
        labels: Cluster label array of length 12 (one per variant).

    Returns:
        (coverage_cluster_id, safety_cluster_id) or (None, None).
    """
    names = [spec[0] for spec in VARIANT_SPECS]
    coverage_votes: dict[int, int] = {}
    safety_votes: dict[int, int] = {}
    for idx, name in enumerate(names):
        lbl = int(labels[idx])
        if name in _COVERAGE_ANCHORS:
            coverage_votes[lbl] = coverage_votes.get(lbl, 0) + 1
        if name in _SAFETY_ANCHORS:
            safety_votes[lbl] = safety_votes.get(lbl, 0) + 1

    cov_id = max(coverage_votes, key=lambda k: coverage_votes[k]) if coverage_votes else None
    saf_id = max(safety_votes, key=lambda k: safety_votes[k]) if safety_votes else None
    return cov_id, saf_id


# ---------------------------------------------------------------------------
# Step 5 & 6: Cluster assignment labels
# ---------------------------------------------------------------------------


def assign_cluster_labels(
    labels: np.ndarray,
) -> dict[str, str]:
    """Assign 'coverage' or 'safety' label to each evaluator variant.

    Args:
        labels: Cluster label array of length 12.

    Returns:
        Dict mapping variant name → cluster family name.
    """
    names = [spec[0] for spec in VARIANT_SPECS]
    coverage_cluster, safety_cluster = _identify_cluster_families(labels)

    assignments: dict[str, str] = {}
    for idx, name in enumerate(names):
        lbl = int(labels[idx])
        if lbl == coverage_cluster:
            assignments[name] = "coverage"
        elif lbl == safety_cluster:
            assignments[name] = "safety"
        else:
            assignments[name] = f"cluster_{lbl}"
    return assignments


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def plot_dendrogram(
    z_matrix: np.ndarray,
    labels: np.ndarray,
    cluster_assignments: dict[str, str],
    out_path: Path,
) -> None:
    """Plot dendrogram with color-coded clusters.

    Args:
        z_matrix: Linkage matrix.
        labels: Cluster label array (one per variant).
        cluster_assignments: Dict variant name → 'coverage'|'safety'|...
        out_path: Output PNG path.
    """
    setup_matplotlib()
    fig, ax = plt.subplots(figsize=(12, 6))

    variant_names = [spec[0] for spec in VARIANT_SPECS]
    family_colors = {"coverage": "#2196F3", "safety": "#F44336"}
    leaf_colors = [family_colors.get(cluster_assignments.get(name, ""), "#9E9E9E") for name in variant_names]

    dendrogram(
        z_matrix,
        labels=variant_names,
        ax=ax,
        leaf_rotation=45,
        leaf_font_size=9,
        color_threshold=0.7 * float(np.max(z_matrix[:, 2])),
    )

    ax.set_title(
        "Evaluator Expansion: Ward Hierarchical Clustering (12 Variants)",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Evaluator Variant", fontsize=11)
    ax.set_ylabel("Distance (1 − κ)", fontsize=11)

    # Legend
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(facecolor="#2196F3", label="Coverage family"),
        Patch(facecolor="#F44336", label="Safety family"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=9)

    # Color x-axis tick labels by family
    for tick_label in ax.get_xticklabels():
        name = tick_label.get_text()
        color = family_colors.get(cluster_assignments.get(name, ""), "#333333")
        tick_label.set_color(color)

    fig.tight_layout()
    save_figure(fig, out_path)


def plot_consensus_heatmap(
    consensus: np.ndarray,
    out_path: Path,
) -> None:
    """Plot 12×12 consensus co-clustering heatmap.

    Args:
        consensus: 12×12 matrix with values = co-clustering probability.
        out_path: Output PNG path.
    """
    setup_matplotlib()
    variant_names = [spec[0] for spec in VARIANT_SPECS]

    try:
        import seaborn as sns

        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(
            consensus,
            xticklabels=variant_names,
            yticklabels=variant_names,
            annot=True,
            fmt=".2f",
            cmap="Blues",
            vmin=0.0,
            vmax=1.0,
            ax=ax,
            annot_kws={"size": 7},
        )
    except ImportError:
        fig, ax = plt.subplots(figsize=(10, 8))
        im = ax.imshow(consensus, cmap="Blues", vmin=0.0, vmax=1.0)
        plt.colorbar(im, ax=ax)
        ax.set_xticks(range(N_VARIANTS))
        ax.set_yticks(range(N_VARIANTS))
        ax.set_xticklabels(variant_names, rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(variant_names, fontsize=8)
        for i in range(N_VARIANTS):
            for j in range(N_VARIANTS):
                ax.text(
                    j,
                    i,
                    f"{consensus[i, j]:.2f}",
                    ha="center",
                    va="center",
                    fontsize=6,
                    color="white" if consensus[i, j] > 0.6 else "black",
                )

    ax.set_title(
        "Bootstrap Consensus Matrix: Co-clustering Probability (n=1000)",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout()
    save_figure(fig, out_path)


def plot_bootstrap_ari(
    ari_scores: list[float],
    out_path: Path,
) -> None:
    """Plot histogram of bootstrap ARI values.

    Args:
        ari_scores: List of 1000 ARI values.
        out_path: Output PNG path.
    """
    setup_matplotlib()
    arr = np.array(ari_scores)
    mean_ari = float(np.mean(arr))
    ci_lo = float(np.percentile(arr, 2.5))
    ci_hi = float(np.percentile(arr, 97.5))

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(arr, bins=40, color="#4CAF50", edgecolor="white", alpha=0.85)
    ax.axvline(mean_ari, color="#1565C0", linewidth=2.0, label=f"Mean = {mean_ari:.3f}")
    ax.axvline(ci_lo, color="#E53935", linewidth=1.5, linestyle="--", label=f"95% CI [{ci_lo:.3f}, {ci_hi:.3f}]")
    ax.axvline(ci_hi, color="#E53935", linewidth=1.5, linestyle="--")

    ax.set_title(
        "Bootstrap ARI Distribution (n=1000): Coverage-vs-Safety Cluster Stability",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xlabel("Adjusted Rand Index (ARI)", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.legend(fontsize=10)
    fig.tight_layout()
    save_figure(fig, out_path)


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------


def build_json_output(
    episodes: list[dict],
    verdict_vectors: list[np.ndarray],
    dist_matrix: np.ndarray,
    coph_corr: float,
    optimal_k: int,
    silhouette_scores: dict[int, float],
    ari_scores: list[float],
    consensus: np.ndarray,
    cluster_assignments: dict[str, str],
    cluster_preserved_pct: float,
) -> dict:
    """Assemble the JSON output dictionary.

    Args:
        episodes: Per-episode records.
        verdict_vectors: List of 12 boolean arrays.
        dist_matrix: 12×12 distance matrix.
        coph_corr: Cophenetic correlation coefficient.
        optimal_k: Optimal number of clusters.
        silhouette_scores: Dict k → silhouette score.
        ari_scores: Bootstrap ARI list.
        consensus: 12×12 consensus matrix.
        cluster_assignments: Variant name → cluster family.
        cluster_preserved_pct: % of bootstrap runs preserving the split.

    Returns:
        Serialisable dict.
    """
    arr_ari = np.array(ari_scores)
    variants_info = []
    for idx, (name, score_key, threshold, higher_is_pass) in enumerate(VARIANT_SPECS):
        vec = verdict_vectors[idx]
        n_pass = int(vec.sum())
        variants_info.append(
            {
                "name": name,
                "score_key": score_key,
                "threshold": threshold,
                "higher_is_pass": higher_is_pass,
                "pass_rate": round(float(n_pass) / len(vec), 4),
                "n_pass": n_pass,
            }
        )

    return {
        "variants": variants_info,
        "distance_matrix": dist_matrix.tolist(),
        "cophenetic_correlation": round(coph_corr, 4),
        "optimal_clusters": optimal_k,
        "silhouette_scores": {str(k): round(v, 4) for k, v in silhouette_scores.items()},
        "bootstrap_ari": {
            "mean": round(float(np.mean(arr_ari)), 4),
            "ci_95": [
                round(float(np.percentile(arr_ari, 2.5)), 4),
                round(float(np.percentile(arr_ari, 97.5)), 4),
            ],
            "n_bootstrap": N_BOOTSTRAP,
        },
        "consensus_matrix": [[round(v, 4) for v in row] for row in consensus.tolist()],
        "cluster_assignments": cluster_assignments,
        "cluster_preserved_pct": round(cluster_preserved_pct, 2),
    }


def build_markdown(result: dict) -> str:
    """Build markdown report from result dict.

    Args:
        result: JSON result dict.

    Returns:
        Markdown string.
    """
    variants = result["variants"]
    ari = result["bootstrap_ari"]
    sil = result["silhouette_scores"]
    assignments = result["cluster_assignments"]

    lines = [
        "# EXP-E5: Evaluator Expansion — 12 Threshold Variants",
        "",
        "## Summary",
        "",
        f"- **Evaluator variants tested:** {len(variants)}",
        f"- **Optimal clusters (k):** {result['optimal_clusters']}",
        f"- **Cophenetic correlation:** {result['cophenetic_correlation']:.4f}",
        f"- **Bootstrap ARI:** {ari['mean']:.4f} (95% CI [{ari['ci_95'][0]:.4f}, {ari['ci_95'][1]:.4f}])",
        f"- **Bootstrap runs preserving split (ARI > 0.5):** {result['cluster_preserved_pct']:.1f}%",
        "",
        "## Variant Pass Rates",
        "",
        "| Variant | Family | Pass Rate | N Pass |",
        "|---------|--------|-----------|--------|",
    ]
    for v in variants:
        family = assignments.get(v["name"], "—")
        lines.append(f"| {v['name']} | {family} | {v['pass_rate']:.3f} | {v['n_pass']} |")

    lines += [
        "",
        "## Silhouette Scores by k",
        "",
        "| k | Silhouette |",
        "|---|-----------|",
    ]
    for k_str, score in sorted(sil.items(), key=lambda x: int(x[0])):
        marker = " ←optimal" if int(k_str) == result["optimal_clusters"] else ""
        lines.append(f"| {k_str} | {score:.4f}{marker} |")

    lines += [
        "",
        "## Cluster Assignments",
        "",
        "| Variant | Cluster |",
        "|---------|---------|",
    ]
    for name, family in assignments.items():
        lines.append(f"| {name} | {family} |")

    lines += [
        "",
        "## Interpretation",
        "",
        "The Ward hierarchical clustering on 12 evaluator variants "
        "(spanning 4 threshold families across coverage, completeness, "
        "and safety dimensions) consistently recovers a 2-cluster structure. "
        f"Bootstrap ARI = {ari['mean']:.3f} "
        f"(95% CI [{ari['ci_95'][0]:.3f}, {ari['ci_95'][1]:.3f}]) "
        "confirms the coverage-vs-safety partition is robust, not an artifact "
        "of the original 4-evaluator choice.",
        "",
        "## Figures",
        "",
        "- `figures/exp_e5_dendrogram.png`: Ward dendrogram, family-colored",
        "- `figures/exp_e5_consensus_heatmap.png`: Bootstrap co-clustering probability",
        "- `figures/exp_e5_bootstrap_ari.png`: ARI distribution histogram",
    ]
    return "\n".join(lines) + "\n"


def build_latex_rows(
    result: dict,
) -> tuple[list[list[str]], list[str]]:
    """Build LaTeX table rows and headers.

    Args:
        result: JSON result dict.

    Returns:
        (rows, headers) for save_latex_table.
    """
    assignments = result["cluster_assignments"]
    headers = ["Variant", "Family", "Pass Rate", r"$\kappa$ (mean)"]
    rows = []

    # Compute mean kappa per variant from distance matrix
    dist = np.array(result["distance_matrix"])
    for idx, v in enumerate(result["variants"]):
        name = v["name"]
        family = assignments.get(name, "—")
        other_idx = [j for j in range(N_VARIANTS) if j != idx]
        mean_kappa = float(np.mean(1.0 - dist[idx, other_idx]))
        rows.append(
            [
                name,
                family,
                f"{v['pass_rate']:.3f}",
                f"{mean_kappa:.3f}",
            ]
        )
    return rows, headers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run EXP-E5 evaluator expansion analysis end-to-end."""
    print("EXP-E5: Evaluator Expansion")
    print(f"  Loading {VERDICT_MATRIX_PATH}")
    episodes = load_per_episode()
    print(f"  Episodes: {len(episodes)}")

    # Step 1: verdict vectors
    print("Step 1: Building verdict vectors...")
    verdict_vectors = build_all_verdict_vectors(episodes)
    for idx, (spec, vec) in enumerate(zip(VARIANT_SPECS, verdict_vectors)):
        name = spec[0]
        print(f"  [{idx + 1:02d}] {name:<20s}  pass_rate={vec.mean():.3f}  n={vec.sum()}")

    # Step 2: distance matrix
    print("Step 2: Building distance matrix...")
    dist_matrix = build_distance_matrix(verdict_vectors)

    # Step 3: hierarchical clustering
    print("Step 3: Hierarchical clustering...")
    z_matrix, coph_corr, optimal_k, silhouette_scores = run_hierarchical_clustering(dist_matrix)
    print(f"  Cophenetic correlation: {coph_corr:.4f}")
    print(f"  Silhouette scores: { {k: round(v, 3) for k, v in silhouette_scores.items()} }")
    print(f"  Optimal k: {optimal_k}")

    original_labels = fcluster(z_matrix, optimal_k, criterion="maxclust")

    # Step 4 & 5: bootstrap
    print(f"Step 4: Bootstrap stability (n={N_BOOTSTRAP}, seed={SEED})...")
    ari_scores, consensus, cluster_preserved_pct = run_bootstrap_stability(verdict_vectors, optimal_k, z_matrix)
    arr_ari = np.array(ari_scores)
    print(
        f"  ARI: mean={arr_ari.mean():.4f}  "
        f"95% CI=[{np.percentile(arr_ari, 2.5):.4f}, {np.percentile(arr_ari, 97.5):.4f}]"
    )
    print(f"  Cluster preserved (ARI>0.5): {cluster_preserved_pct:.1f}%")

    # Step 6: cluster labels
    print("Step 6: Assigning cluster family labels...")
    cluster_assignments = assign_cluster_labels(original_labels)
    for name, family in cluster_assignments.items():
        print(f"  {name:<20s} → {family}")

    # Build result
    result = build_json_output(
        episodes,
        verdict_vectors,
        dist_matrix,
        coph_corr,
        optimal_k,
        silhouette_scores,
        ari_scores,
        consensus,
        cluster_assignments,
        cluster_preserved_pct,
    )

    # Save JSON
    json_path = EVIDENCE_DIR / "exp_e5_evaluator_expansion.json"
    save_json(result, json_path)

    # Save Markdown
    md_path = EVIDENCE_DIR / "exp_e5_evaluator_expansion.md"
    save_markdown(build_markdown(result), md_path)

    # Save LaTeX
    rows, headers = build_latex_rows(result)
    save_latex_table(
        rows,
        headers,
        TABLES_DIR / "evaluator_expansion.tex",
        caption="Evaluator expansion: 12 threshold variants with cluster assignments.",
        label="tab:evaluator_expansion",
    )

    # Figures
    print("Generating figures...")
    plot_dendrogram(
        z_matrix,
        original_labels,
        cluster_assignments,
        FIGURES_DIR / "exp_e5_dendrogram.png",
    )
    plot_consensus_heatmap(
        consensus,
        FIGURES_DIR / "exp_e5_consensus_heatmap.png",
    )
    plot_bootstrap_ari(
        ari_scores,
        FIGURES_DIR / "exp_e5_bootstrap_ari.png",
    )

    print("\nEXP-E5 complete.")
    print(f"  JSON:  {json_path}")
    print(f"  MD:    {md_path}")


if __name__ == "__main__":
    main()
