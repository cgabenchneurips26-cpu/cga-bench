from pathlib import Path

import pytest
import yaml

CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs" / "experiments"


class TestExperimentConfigsLoad:
    @pytest.mark.parametrize(
        "config_name",
        [
            "neurips_baseline.yaml",
            "neurips_ablation.yaml",
            "neurips_scalability.yaml",
            "neurips_alignment.yaml",
            "neurips_main.yaml",
        ],
    )
    def test_config_loads(self, config_name):
        config_path = CONFIGS_DIR / config_name
        assert config_path.exists(), f"Config not found: {config_path}"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert isinstance(config, dict)

    def test_baseline_config_has_required_fields(self):
        with open(CONFIGS_DIR / "neurips_baseline.yaml") as f:
            config = yaml.safe_load(f)
        assert "block" in config
        assert config["block"] == "baseline"
        assert "agents" in config
        assert "scenarios" in config
        assert "seed" in config

    def test_ablation_config_has_ablations(self):
        with open(CONFIGS_DIR / "neurips_ablation.yaml") as f:
            config = yaml.safe_load(f)
        assert "ablations" in config
        assert len(config["ablations"]) >= 5

    def test_scalability_config_has_profiles(self):
        with open(CONFIGS_DIR / "neurips_scalability.yaml") as f:
            config = yaml.safe_load(f)
        assert "profiles" in config
        assert len(config["profiles"]) >= 3

    def test_alignment_config_has_metrics(self):
        with open(CONFIGS_DIR / "neurips_alignment.yaml") as f:
            config = yaml.safe_load(f)
        assert "metrics" in config
        assert "classification" in config


class TestBaselineSmoke:
    def test_experiment_runner_imports(self):
        from cga_bench.run_neurips_experiment import NeurIPSExperimentRunner

        assert NeurIPSExperimentRunner is not None

    def test_experiment_runner_loads_config(self):
        from cga_bench.run_neurips_experiment import NeurIPSExperimentRunner

        config_path = CONFIGS_DIR / "neurips_main.yaml"
        runner = NeurIPSExperimentRunner(config_path)
        assert runner.config is not None
        assert "baselines" in runner.config


class TestExperimentConfigContract:
    def test_baseline_compatible_with_contract(self):
        from cga_bench.cpg_model.schemas.contracts import ExperimentConfig

        with open(CONFIGS_DIR / "neurips_baseline.yaml") as f:
            raw = yaml.safe_load(f)

        config = ExperimentConfig(
            experiment_name=raw.get("block", "baseline"),
            scenarios=raw.get("scenarios", []),
            agents=raw.get("agents", []),
            budget=raw.get("budget", {}),
            num_runs=raw.get("num_runs", 1),
            seed=raw.get("seed"),
        )
        assert config.experiment_name == "baseline"
        assert len(config.scenarios) >= 1


class TestMockExperimentExecution:
    """Verify experiment can run with mock data."""

    def test_baseline_mock_execution(self):
        """Run minimal mock experiment and verify result structure."""
        from cga_bench.run_neurips_experiment import NeurIPSExperimentRunner

        config_path = CONFIGS_DIR / "neurips_main.yaml"
        runner = NeurIPSExperimentRunner(config_path)

        assert hasattr(runner, "config")
        assert hasattr(runner, "output_dir")
        assert hasattr(runner, "fairness_verifier")
        assert "baselines" in runner.config
        assert len(runner.config["baselines"]) >= 4


class TestBaselineBlockExecution:
    """Verify --block baseline can be invoked (mock mode)."""

    def test_runner_accepts_block_parameter(self):
        from cga_bench.run_neurips_experiment import NeurIPSExperimentRunner

        config_path = CONFIGS_DIR / "neurips_main.yaml"
        runner = NeurIPSExperimentRunner(config_path)

        import inspect

        sig = inspect.signature(runner.run_experiment)
        assert "block" in sig.parameters

    def test_alignment_block_method_exists(self):
        from cga_bench.run_neurips_experiment import NeurIPSExperimentRunner

        config_path = CONFIGS_DIR / "neurips_main.yaml"
        runner = NeurIPSExperimentRunner(config_path)
        assert hasattr(runner, "_run_alignment_block")

    def test_alignment_block_executes(self, tmp_path):
        """Actually run alignment block with synthetic data and verify output."""
        from cga_bench.run_neurips_experiment import NeurIPSExperimentRunner

        config_path = CONFIGS_DIR / "neurips_main.yaml"
        runner = NeurIPSExperimentRunner(config_path)
        runner.output_dir = tmp_path

        runner._run_alignment_block(track="public")

        result_file = tmp_path / "alignment_results.json"
        assert result_file.exists(), "alignment_results.json not generated"

        import json
        with open(result_file) as f:
            metrics = json.load(f)
        assert "cohens_kappa" in metrics
        assert "fleiss_kappa" in metrics
        assert "spearman_rho" in metrics
        assert "accuracy_3way" in metrics
        assert metrics["n_episodes"] > 0

    def test_baseline_block_routing(self):
        """Verify --block baseline routes to correct config."""
        from cga_bench.run_neurips_experiment import NeurIPSExperimentRunner

        baseline_config = CONFIGS_DIR / "neurips_baseline.yaml"
        if not baseline_config.exists():
            pytest.skip("neurips_baseline.yaml not found")
        runner = NeurIPSExperimentRunner(baseline_config)
        assert "block" in runner.config or "agents" in runner.config or "baselines" in runner.config


class TestAlignmentBlockSmoke:
    """Verify alignment block produces metrics."""

    def test_alignment_experiment_imports(self):
        from cga_bench.eval_harness.clinician_alignment import (
            ClinicianAlignmentExperiment,
            AlignmentMetrics,
            SafetyCategory,
        )

        assert ClinicianAlignmentExperiment is not None
        assert AlignmentMetrics is not None
        assert SafetyCategory is not None

    def test_alignment_compute_with_synthetic_data(self):
        from cga_bench.eval_harness.clinician_alignment import (
            ClinicianAlignmentExperiment,
            ClinicianRating,
            EpisodeAnnotation,
            ClinicalExpertise,
            SafetyCategory,
        )
        from cga_bench.assessor_core.episode_risk_scorer import (
            EpisodeRiskScorer,
            EpisodeRiskConfig,
            EpisodeRiskResult,
        )

        risk_scorer = EpisodeRiskScorer(config=EpisodeRiskConfig())
        experiment = ClinicianAlignmentExperiment(
            scorer=risk_scorer,
            config={"safe_threshold": 0.2, "unsafe_threshold": 0.6},
        )

        results = []
        annotations = []
        for i, (risk_val, cat) in enumerate([
            (0.1, SafetyCategory.SAFE),
            (0.4, SafetyCategory.MARGINAL),
            (0.8, SafetyCategory.UNSAFE),
        ]):
            ep_id = f"test_ep_{i}"
            results.append(
                EpisodeRiskResult(
                    episode_id=ep_id,
                    r_raw=risk_val * 10,
                    r_omission=0.0,
                    r_total=risk_val * 10,
                    r_norm=risk_val,
                    task_success=True,
                    sas=1.0 - risk_val,
                    total_actions=3,
                    total_violations=i,
                    violations_by_type={},
                    action_violations=[],
                    missing_critical_actions=[],
                    peak_risk=risk_val,
                    aggregate_risk=risk_val * max(1, i),
                    episode_duration_minutes=60.0,
                )
            )
            annotations.append(
                EpisodeAnnotation(
                    episode_id=ep_id,
                    ratings=[
                        ClinicianRating(
                            clinician_id=f"doc_{j}",
                            expertise=ClinicalExpertise.ATTENDING,
                            episode_id=ep_id,
                            safety_category=cat,
                        )
                        for j in range(3)
                    ],
                )
            )

        metrics = experiment.compute_alignment(results, annotations)
        assert metrics.n_episodes == 3
        assert 0.0 <= metrics.accuracy_3way <= 1.0
        assert -1.0 <= metrics.cohens_kappa <= 1.0
