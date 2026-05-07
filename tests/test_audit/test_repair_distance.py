"""Tests for C2: repair distance d_G as audit column.

Validates:
1. d_G proxy loading and count consistency
2. Proxy statistics (n_viols vs v4_hard distribution)
3. Correlation sign: rho(v4_hard, n_viols) is POSITIVE (agents that act more
   accumulate commissions but also complete mandatory actions → pass)
4. Monotonicity: V4Hard has low violation rate under positive-correlation model
5. Pearson helper correctness
"""

from __future__ import annotations

from audit.metrics.repair import (
    _pearson_r,
    compliance_check,
    dg_correlation,
    load_dg_cache,
    load_dg_proxy,
    monotonicity_violations,
)
from audit.shims import SHIM_REGISTRY
from audit.shims._verdict_cache import load_w8_episodes


class TestDGProxy:
    """Test d_G proxy loading from verdict_matrix."""

    def test_proxy_count(self) -> None:
        proxy = load_dg_proxy()
        assert len(proxy) == 14826

    def test_proxy_values_non_negative(self) -> None:
        proxy = load_dg_proxy()
        for ep_id, val in list(proxy.items())[:500]:
            assert val >= 0.0, f"{ep_id}: d_G proxy = {val}"

    def test_proxy_matches_n_viols(self) -> None:
        proxy = load_dg_proxy()
        episodes = load_w8_episodes()
        for ep_id in list(episodes.keys())[:100]:
            expected = float(episodes[ep_id].get("n_viols") or 0)
            assert proxy[ep_id] == expected

    def test_cache_fallback_to_proxy(self) -> None:
        """load_dg_cache with no path falls back to n_viols proxy."""
        cache = load_dg_cache()
        proxy = load_dg_proxy()
        assert len(cache) == len(proxy)

    def test_cache_nonexistent_path(self) -> None:
        """load_dg_cache with nonexistent path falls back to proxy."""
        cache = load_dg_cache("/nonexistent/path/foo.jsonl")
        assert len(cache) == 14826


class TestProxyStatistics:
    """n_viols proxy vs v4_hard distribution statistics.

    n_viols counts commission/timing violations only, NOT omissions.
    This means n_viols=0 episodes often FAIL v4_hard (from omissions)
    while n_viols>0 episodes often PASS (active agents complete mandatory
    actions but accumulate some commission violations).
    """

    def test_proxy_statistics_structure(self) -> None:
        """compliance_check returns all expected keys."""
        proxy = load_dg_proxy()
        result = compliance_check(proxy)
        expected_keys = {
            "zero_dg_but_harmful",
            "zero_dg_and_safe",
            "nonzero_dg_and_safe",
            "nonzero_dg_but_harmful",
            "zero_dg_total",
            "harmful_total",
            "total",
            "positive_correlation",
            "pass",
        }
        assert set(result.keys()) == expected_keys

    def test_total_count(self) -> None:
        """Total episodes must be 14,826."""
        proxy = load_dg_proxy()
        result = compliance_check(proxy)
        assert result["total"] == 14826

    def test_positive_correlation_confirmed(self) -> None:
        """n_viols proxy has positive correlation with v4_hard."""
        proxy = load_dg_proxy()
        result = compliance_check(proxy)
        assert result["positive_correlation"], (
            f"Expected positive correlation: "
            f"nonzero_safe={result['nonzero_dg_and_safe']} "
            f"vs zero_safe={result['zero_dg_and_safe']}"
        )

    def test_always_passes(self) -> None:
        """Proxy statistics are informational, always pass."""
        proxy = load_dg_proxy()
        result = compliance_check(proxy)
        assert result["pass"]

    def test_distribution_sums(self) -> None:
        """Quadrant counts must sum to total."""
        proxy = load_dg_proxy()
        result = compliance_check(proxy)
        quadrant_sum = (
            result["zero_dg_but_harmful"]
            + result["zero_dg_and_safe"]
            + result["nonzero_dg_and_safe"]
            + result["nonzero_dg_but_harmful"]
        )
        assert quadrant_sum == result["total"]


class TestCorrelation:
    """Correlation between evaluator verdicts and d_G proxy."""

    def test_v4_hard_positive_correlation(self) -> None:
        """V4Hard should have strong POSITIVE rho with n_viols proxy.

        Active agents (n_viols > 0 from commissions) tend to PASS v4_hard
        because they also complete mandatory actions. Inactive agents
        (n_viols = 0) tend to FAIL from omissions.
        """
        shim = SHIM_REGISTRY["v4_hard"]()
        proxy = load_dg_proxy()
        rho = dg_correlation(shim, proxy)
        assert rho > 0.5, f"V4Hard rho = {rho:.4f}, expected > 0.5"

    def test_dxem_near_zero(self) -> None:
        """DxEM always returns True → constant → rho = 0."""
        shim = SHIM_REGISTRY["dxem"]()
        proxy = load_dg_proxy()
        rho = dg_correlation(shim, proxy)
        assert abs(rho) < 0.01, f"DxEM rho = {rho:.4f}, expected ~0 (constant evaluator)"

    def test_always_true_near_zero(self) -> None:
        """AlwaysTrue should have rho near 0 (no discrimination)."""
        from audit.wrappers.metric_evaluators import AlwaysTrueEvaluator

        shim = AlwaysTrueEvaluator()
        proxy = load_dg_proxy()
        rho = dg_correlation(shim, proxy)
        assert abs(rho) < 0.01, f"AlwaysTrue rho = {rho:.4f}, expected ~0"

    def test_correlation_range(self) -> None:
        """All evaluators should produce rho in [-1, 1]."""
        proxy = load_dg_proxy()
        for name, cls in SHIM_REGISTRY.items():
            shim = cls()
            rho = dg_correlation(shim, proxy)
            assert -1.0 <= rho <= 1.0, f"{name}: rho = {rho}"


class TestMonotonicity:
    """Monotonicity violations in d_G-verdict relationship."""

    def test_v4_hard_low_violation_rate(self) -> None:
        """V4Hard should have low violation rate under positive-correlation model.

        With rho ≈ +0.74, most informative pairs should be concordant.
        """
        shim = SHIM_REGISTRY["v4_hard"]()
        proxy = load_dg_proxy()
        viols, checked = monotonicity_violations(shim, proxy)
        if checked > 0:
            rate = viols / checked
            assert rate < 0.25, f"V4Hard violation rate = {rate:.4f}, expected < 0.25"

    def test_dxem_no_informative_pairs(self) -> None:
        """DxEM always returns True → no informative pairs (all same verdict)."""
        shim = SHIM_REGISTRY["dxem"]()
        proxy = load_dg_proxy()
        viols, checked = monotonicity_violations(shim, proxy)
        assert checked == 0, f"DxEM has {checked} informative pairs, expected 0"

    def test_seed_reproducibility(self) -> None:
        """Same seed must produce identical results."""
        shim = SHIM_REGISTRY["v4_hard"]()
        proxy = load_dg_proxy()
        r1 = monotonicity_violations(shim, proxy, seed=123)
        r2 = monotonicity_violations(shim, proxy, seed=123)
        assert r1 == r2


class TestPearsonHelper:
    """Unit tests for the Pearson correlation helper."""

    def test_perfect_positive(self) -> None:
        r = _pearson_r([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        assert abs(r - 1.0) < 1e-10

    def test_perfect_negative(self) -> None:
        r = _pearson_r([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
        assert abs(r - (-1.0)) < 1e-10

    def test_zero_variance(self) -> None:
        r = _pearson_r([1, 1, 1], [2, 4, 6])
        assert r == 0.0

    def test_empty(self) -> None:
        r = _pearson_r([], [])
        assert r == 0.0

    def test_single_element(self) -> None:
        r = _pearson_r([1], [2])
        assert r == 0.0
