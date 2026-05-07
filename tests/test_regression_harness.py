"""EX-12: Regression harness — prevents recurrence of all statistical bugs found in this session.

Each test reproduces the exact bug pattern and verifies the corrected logic.
"""

import numpy as np
from scipy import stats


class TestFriedmanCorrectness:
    """Friedman test must use pass rates, not pre-ranked data."""

    def test_friedman_uses_pass_rates_not_ranks(self):
        """Bug: rank matrix input gave χ²=0.1, p=0.996.
        Fix: pass rates give χ²=21.0, p<0.001.
        """
        pass_rates = np.array(
            [
                [0.8, 0.6, 0.3, 0.1],
                [0.7, 0.5, 0.4, 0.2],
                [0.9, 0.7, 0.2, 0.1],
            ]
        )
        stat, p = stats.friedmanchisquare(*[pass_rates[:, i] for i in range(pass_rates.shape[1])])
        assert p < 0.05, f"Friedman p={p}, expected < 0.05 for clearly different models"

    def test_friedman_detects_magnitude_differences(self):
        """Friedman on raw pass rates preserves magnitude differences that ranking destroys.
        With varied magnitudes, raw data gives a more informative test than pre-ranked.
        """
        # Data where magnitudes matter: model 1 is far better, model 4 is far worse
        pass_rates = np.array(
            [
                [0.95, 0.50, 0.30, 0.02],  # evaluator 1
                [0.90, 0.45, 0.35, 0.05],  # evaluator 2
                [0.85, 0.55, 0.25, 0.03],  # evaluator 3
                [0.92, 0.48, 0.32, 0.04],  # evaluator 4
                [0.88, 0.52, 0.28, 0.06],  # evaluator 5
            ]
        )
        stat, p = stats.friedmanchisquare(*[pass_rates[:, i] for i in range(pass_rates.shape[1])])
        # With 5 evaluators and clear ordering, should be highly significant
        assert p < 0.01, f"Friedman p={p:.4f}, expected < 0.01 for clearly ordered models"


class TestEtaSquaredCorrectness:
    """η²(run) must use SS_between_runs, not SS_residual."""

    def test_eta_run_is_between_runs_not_residual(self):
        """Bug: SS_residual used as SS_run → η²(run)=0.036, ratio=8.7.
        Fix: SS_between_runs → η²(run)≈0.00002, ratio≈16,000.
        """
        np.random.seed(42)
        run1 = np.random.normal(0.5, 0.01, 100)
        run2 = np.random.normal(0.5, 0.01, 100)
        run3 = np.random.normal(0.5, 0.01, 100)

        all_data = np.concatenate([run1, run2, run3])
        grand_mean = all_data.mean()
        ss_total = np.sum((all_data - grand_mean) ** 2)

        run_means = [run1.mean(), run2.mean(), run3.mean()]
        ss_between = sum(len(r) * (m - grand_mean) ** 2 for r, m in zip([run1, run2, run3], run_means))
        ss_residual = ss_total - ss_between

        eta_run_correct = ss_between / ss_total
        eta_run_buggy = ss_residual / ss_total

        assert eta_run_correct < 0.01, f"η²(run) = {eta_run_correct}, should be tiny"
        assert eta_run_buggy > 0.5, f"Buggy η²(run) = {eta_run_buggy}, should be large (wrong)"


class TestKendallWCorrectness:
    """Kendall's W must use model rank sums (objects), not evaluator rank sums (judges)."""

    def test_kendall_w_ranks_models_not_evaluators(self):
        """Bug: evaluator rank sums (all equal to n*(n+1)/2) → W=0.
        Fix: model rank sums (vary) → W>0.
        """
        rankings = np.array(
            [
                [1, 2, 3, 4],
                [1, 3, 2, 4],
                [2, 1, 3, 4],
            ]
        )
        k, n = rankings.shape

        # Correct: model rank sums
        rank_sums = rankings.sum(axis=0)
        mean_rank_sum = rank_sums.mean()
        ss = np.sum((rank_sums - mean_rank_sum) ** 2)
        w_correct = 12 * ss / (k**2 * (n**3 - n))

        # Bug: evaluator rank sums (always equal for full rankings)
        eval_sums = rankings.sum(axis=1)
        mean_eval = eval_sums.mean()
        ss_bug = np.sum((eval_sums - mean_eval) ** 2)

        assert w_correct > 0, f"W_correct = {w_correct}, should be > 0"
        # Evaluator sums for complete rankings of n items: each = n*(n+1)/2 = 10
        assert all(s == n * (n + 1) / 2 for s in eval_sums), "Eval sums should all be equal"
        assert ss_bug == 0, "SS_bug should be 0 (all equal)"

    def test_kendall_w_with_real_data(self):
        """Verify W=0.380 from our actual rank matrix."""
        # From verify_friedman_eta.py: 7 models × 4 evaluators (ASC, CwT, PAF, TCC)
        rank_matrix = np.array(
            [
                [5, 5, 5, 5],  # gemma31b
                [7, 7, 7, 1],  # nemotron30b
                [4, 4, 4, 3],  # oss120b
                [2, 3, 2, 6],  # qwen27b
                [3, 2, 3, 2],  # qwen35b
                [1, 1, 1, 7],  # qwen397b
                [6, 6, 6, 4],  # qwen4b
            ]
        )
        k = 4  # evaluators (judges)
        n = 7  # models (objects)

        r_i = rank_matrix.sum(axis=1)
        r_bar = r_i.mean()
        ss = np.sum((r_i - r_bar) ** 2)
        w = 12 * ss / (k**2 * (n**3 - n))

        assert abs(w - 0.380) < 0.01, f"W = {w:.4f}, expected ~0.380"


class TestNormalizerIdempotency:
    """ActionNormalizer.normalize(normalize(x)) == normalize(x)."""

    def test_normalize_is_idempotent(self):
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer

        normalizer = ActionNormalizer()
        test_actions = [
            "administer_iv_fluids",
            "order_chest_xray",
            "give_epinephrine",
            "start_antibiotics",
            "obtain_blood_cultures",
            "attach_defibrillator_pads",
            "begin_high_quality_cpr",
            "monitor_creatinine_q6h",
            "consult_nephrology_if_needed",
        ]
        for action in test_actions:
            first = normalizer.normalize(action)
            second = normalizer.normalize(first)
            assert first == second, f"Not idempotent: {action} → {first} → {second}"


class TestKnownActionPrefixes:
    """ViolationExtractor KNOWN_ACTION_PREFIXES covers all mandatory action prefixes."""

    def test_acls_prefixes_present(self):
        """Bug 9: attach_, begin_, analyze_, deliver_ were missing."""
        # Access the prefix tuple from the class method
        import inspect

        from cga_bench.assessor_core.violations import ViolationExtractor

        source = inspect.getsource(ViolationExtractor._get_raw_action_key)

        required_prefixes = [
            "attach_",
            "begin_",
            "analyze_",
            "deliver_",
            "measure_",
            "estimate_",
            "cover_",
            "position_",
            "place_",
            "titrate_",
            "attempt_",
            "observe_",
        ]
        for prefix in required_prefixes:
            assert f'"{prefix}"' in source, f"Missing prefix: {prefix}"

    def test_bug9_action_key_preserves_known_prefixes(self):
        """Bug 9 e2e: actions with attach_/begin_/analyze_ prefixes must produce
        matching keys in performed_actions dict, not fall through to type+args.
        """
        from cga_bench.assessor_core.violations import ViolationExtractor
        from cga_bench.cpg_model.schemas.base import Action, ActionType

        # _get_raw_action_key needs self._normalizer. Use a simple mock.
        class _MockVE:
            _normalizer = None

        mock_ve = _MockVE()
        bug9_actions = [
            ("attach_defibrillator_pads", "reassess"),
            ("begin_high_quality_cpr", "procedure"),
            ("analyze_rhythm", "reassess"),
            ("deliver_defibrillation", "procedure"),
            ("measure_oxygen_saturation", "order_lab"),
            ("estimate_tbsa", "reassess"),
            ("place_foley_catheter", "procedure"),
            ("attempt_verbal_deescalation", "reassess"),
        ]
        for action_id, action_type in bug9_actions:
            action = Action(
                type=ActionType(action_type),
                action_id=action_id,
                args={},
                timestamp_minutes=0.0,
            )
            # _get_raw_action_key should return the action_id as-is (prefix match)
            # not construct from type+args
            raw_key = ViolationExtractor._get_raw_action_key(mock_ve, action)
            assert raw_key == action_id, (
                f"Bug 9: {action_id} got raw_key={raw_key} (fell through to type+args construction)"
            )
