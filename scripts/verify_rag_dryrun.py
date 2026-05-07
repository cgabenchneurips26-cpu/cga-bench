#!/usr/bin/env python3
"""V5: End-to-end dry run — 5 domains x 1 model.

Mirrors full_690_runner.py pattern exactly.
3 previously-empty domains + 2 previously-normal domains.

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python cga_bench/scripts/verify_rag_dryrun.py
"""

from datetime import datetime
import json
from pathlib import Path
import sys
import time
from typing import Any

import yaml

_CGA_BENCH_DIR = Path(__file__).resolve().parent.parent
_AGENTBEATS_DIR = _CGA_BENCH_DIR.parent
_ab_str = str(_AGENTBEATS_DIR)
if _ab_str not in sys.path:
    sys.path.insert(0, _ab_str)

AGENT_CONFIG_PATH = _CGA_BENCH_DIR / "configs/agents/clean_slate_qwen35b.yaml"

# 3 previously-empty + 2 previously-normal scenarios
DRY_RUN_SCENARIOS: list[tuple[str, str, str]] = [
    # (scenario_id, domain, category)
    ("aki_basic_hyperkalemia_urgent", "aki", "previously_empty"),
    ("dka_cerebral_edema_pediatric_trap", "dka", "previously_empty"),
    ("asthma_basic_initial_no_mucolytics", "asthma", "previously_empty"),
    ("sepsis_aki_contrast_dilemma", "sepsis", "previously_normal"),
    ("acls_basic_shockable_defib_first", "acls", "previously_normal"),
]


def run_single_episode(scenario_id: str) -> dict[str, Any]:
    """Run a single episode using the exact full_690_runner pattern."""
    from cga_bench.agent_runner.rag_agent import RAGAgent, RAGConfig
    from cga_bench.assessor_core.harm_scorer import HarmScorerConfig
    from cga_bench.assessor_core.violations import (
        HarmSeverityMapping,
        TimingSeverityThreshold,
        ViolationExtractorConfig,
    )
    from cga_bench.cpg_model.schemas.base import (
        HarmSeverity,
        RecommendationClass,
        ViolationType,
    )
    from cga_bench.eval_harness.runner import EvaluationRunner, ExperimentConfig
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    # Load agent config from YAML (same as full_690_runner)
    agent_yaml = yaml.safe_load(AGENT_CONFIG_PATH.read_text())["agent"]

    agent_config = RAGConfig(
        agent_id=f"{agent_yaml['agent_id']}_dryrun",
        llm_backend=agent_yaml["llm_backend"],
        llm_model=agent_yaml["llm_model"],
        temperature=agent_yaml.get("temperature", 0.1),
        use_llm=agent_yaml.get("use_llm", True),
        base_url=agent_yaml["base_url"],
        api_key=agent_yaml.get("api_key", "sk-no-key-required"),
        top_k=agent_yaml.get("top_k", 5),
        use_bm25=agent_yaml.get("use_bm25", True),
        max_actions_per_step=agent_yaml.get("max_actions_per_step", 3),
        budget_limit_tokens=agent_yaml.get("budget_limit_tokens", 100000),
        budget_limit_tool_calls=agent_yaml.get("budget_limit_tool_calls", 50),
    )
    agent = RAGAgent(agent_config)

    # Load scenario
    loader = ScenarioLoader()
    scenario_def = loader.get_scenario(scenario_id)
    if scenario_def is None:
        return {"scenario_id": scenario_id, "error": "scenario not found", "actions_count": 0}

    env = loader.create_environment(scenario_id)
    graph_path = str(loader.get_cpg_graph_path(scenario_id))

    # Configs (same as full_690_runner)
    ve_config = ViolationExtractorConfig(
        harm_severity_mappings=[
            HarmSeverityMapping(action_pattern="", severity=HarmSeverity.MODERATE),
        ],
        timing_severity_thresholds=[
            TimingSeverityThreshold(max_delay_minutes=15.0, severity=HarmSeverity.MINOR),
            TimingSeverityThreshold(max_delay_minutes=30.0, severity=HarmSeverity.MODERATE),
            TimingSeverityThreshold(max_delay_minutes=60.0, severity=HarmSeverity.MAJOR),
            TimingSeverityThreshold(max_delay_minutes=120.0, severity=HarmSeverity.SEVERE),
        ],
        default_deviation_severity=HarmSeverity.MODERATE,
        default_deviation_preventability=0.8,
    )

    hs_config = HarmScorerConfig(
        severity_weights={
            HarmSeverity.MINOR: 0.1,
            HarmSeverity.MODERATE: 0.3,
            HarmSeverity.MAJOR: 0.6,
            HarmSeverity.SEVERE: 0.85,
            HarmSeverity.CATASTROPHIC: 1.0,
        },
        guideline_strength_weights={
            RecommendationClass.CLASS_I: 1.0,
            RecommendationClass.CLASS_IIA: 0.75,
            RecommendationClass.CLASS_IIB: 0.5,
            RecommendationClass.CLASS_III: 0.25,
            None: 0.5,
        },
        violation_type_weights={
            ViolationType.OMISSION: 0.8,
            ViolationType.COMMISSION: 1.0,
            ViolationType.TIMING: 0.7,
            ViolationType.SEQUENCE: 0.6,
            ViolationType.DEVIATION: 0.4,
        },
    )

    total_mandatory = len(scenario_def.expected_actions) if scenario_def.expected_actions else 5
    forbidden_actions = scenario_def.forbidden_actions or []
    expected_actions = scenario_def.expected_actions or []

    runner = EvaluationRunner(
        ExperimentConfig(
            experiment_id="rag_dryrun",
            scenarios=[scenario_id],
            agents=["qwen35b"],
            num_runs_per_scenario=1,
        )
    )

    episode_log, score, violations = runner.run_episode(
        agent=agent,
        environment=env,
        scenario_id=scenario_id,
        guideline_graph_path=graph_path,
        total_mandatory_count=total_mandatory,
        violation_extractor_config=ve_config,
        harm_scorer_config=hs_config,
        scenario_forbidden_actions=forbidden_actions if forbidden_actions else None,
        scenario_expected_actions=expected_actions if expected_actions else None,
    )

    action_ids = [a.action_id for a in episode_log.actions] if episode_log.actions else []

    return {
        "scenario_id": scenario_id,
        "actions_count": len(episode_log.actions),
        "action_ids": action_ids[:10],
        "compliance_score": score.compliance_score,
        "total_violations": score.total_violations,
        "sub_scores": score.sub_scores,
        "error": None,
    }


def main() -> None:
    """Run V5 dry run."""
    print("=" * 70)
    print("VERIFICATION 5: End-to-end dry run (5 domains x 1 model)")
    print("=" * 70)
    print(f"Agent config: {AGENT_CONFIG_PATH}")
    print(f"CPG sources: {_CGA_BENCH_DIR / 'cpg_sources'}")

    results: list[dict[str, Any]] = []
    prev_empty_improved = 0
    prev_empty_total = 0
    prev_normal_ok = 0
    prev_normal_total = 0

    for scenario_id, domain, category in DRY_RUN_SCENARIOS:
        print(f"\n--- {scenario_id} ({category}) ---")
        start = time.time()

        try:
            result = run_single_episode(scenario_id)
        except Exception as e:
            result = {
                "scenario_id": scenario_id,
                "error": str(e)[:300],
                "actions_count": 0,
            }

        elapsed = time.time() - start
        result["domain"] = domain
        result["category"] = category
        result["elapsed_seconds"] = round(elapsed, 1)

        actions = result.get("actions_count", 0)
        error = result.get("error")

        if error:
            status = "ERROR"
        elif actions > 0:
            status = "OK"
        else:
            status = "EMPTY"

        result["status"] = status
        results.append(result)

        print(f"  Status: {status}")
        print(f"  Actions: {actions}")
        print(f"  Time: {elapsed:.1f}s")
        if error:
            print(f"  Error: {error}")
        if actions > 0:
            print(f"  Action IDs: {result.get('action_ids', [])}")
            print(f"  Compliance: {result.get('compliance_score', 'N/A')}")
            print(f"  Violations: {result.get('total_violations', 'N/A')}")

        if category == "previously_empty":
            prev_empty_total += 1
            if actions > 0:
                prev_empty_improved += 1
        else:
            prev_normal_total += 1
            if actions > 0:
                prev_normal_ok += 1

    # Summary
    print(f"\n{'=' * 70}")
    print("DRY RUN SUMMARY")
    print(f"{'=' * 70}")
    print(
        f"Previously empty: {prev_empty_improved}/{prev_empty_total} "
        f"now have actions {'PASS' if prev_empty_improved > 0 else 'FAIL'}"
    )
    print(
        f"Previously normal: {prev_normal_ok}/{prev_normal_total} "
        f"still have actions {'PASS' if prev_normal_ok == prev_normal_total else 'FAIL'}"
    )

    overall_pass = prev_empty_improved > 0 and prev_normal_ok == prev_normal_total
    print(f"\nOverall: {'PASS' if overall_pass else 'FAIL'}")

    # Save
    output = {
        "v5_dryrun": results,
        "summary": {
            "model": "qwen35b",
            "timestamp": datetime.now().isoformat(),
            "prev_empty_improved": prev_empty_improved,
            "prev_empty_total": prev_empty_total,
            "prev_normal_ok": prev_normal_ok,
            "prev_normal_total": prev_normal_total,
            "overall_pass": overall_pass,
        },
    }

    out_dir = _CGA_BENCH_DIR / "evidence_pack" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rag_dryrun_verification.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
