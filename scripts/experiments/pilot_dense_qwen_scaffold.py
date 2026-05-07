"""Pilot: dense-Qwen scaffold sweep for prompt-sensitivity recovery.

Compares scaffold variants (react / direct / checklist) on a small random
slice of the v6 scenario pool (5662). Goal: identify a scaffold that
brings dense Qwen rule-fallback rate from ~80% (current react) down to a
defensible level (<10%).

Usage::

    PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject \\
        python scripts/experiments/pilot_dense_qwen_scaffold.py \\
            --model qwen4b \\
            --base-url http://localhost:28010/v1 \\
            --hf-id Qwen/Qwen3-4B-Instruct-2507 \\
            --scaffolds react,direct,checklist \\
            --n-scenarios 30 \\
            --seed 42 \\
            --out reports/pilot_qwen4b_scaffold/

Outputs per (model, scaffold): per-episode JSON + summary table.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import random
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

# Force include auto_v2 — pilot must reflect v6 scenario distribution
os.environ.setdefault("CGA_BENCH_INCLUDE_AUTO_V2", "1")

from cga_bench.agent_runner.rag_agent import RAGAgent, RAGAgentConfig  # noqa: E402
from cga_bench.eval_harness.scenario_loader import ScenarioLoader  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _make_agent_config(model_id: str, base_url: str, scaffold: str, hf_id: str) -> RAGAgentConfig:
    """Build a minimal RAGAgentConfig for the pilot."""
    return RAGAgentConfig(
        agent_id=f"pilot_{model_id}_{scaffold}",
        llm_backend="vllm",
        llm_model=hf_id,
        temperature=0.1,
        use_llm=True,
        base_url=base_url,
        api_key="sk-no-key-required",
        top_k=5,
        use_bm25=True,
        cpg_sources_path=None,
        scaffold=scaffold,
        max_actions_per_step=10 if scaffold == "direct" else 3,
        budget_limit_tokens=100000,
        budget_limit_tool_calls=50,
    )


def _classify_episode(episode_log, score, violations) -> tuple[bool, bool, int]:
    """Return (has_fallback, is_empty, n_actions).

    has_fallback: any action's justification contains 'Initial diagnostic workup'.
    is_empty: actions_count == 0.
    """
    actions = getattr(episode_log, "actions", None) or []
    n_actions = len(actions)
    has_fallback = False
    for a in actions:
        j = getattr(a, "justification", "") or ""
        if "Initial diagnostic workup" in j:
            has_fallback = True
            break
    return has_fallback, n_actions == 0, n_actions


def run_pilot(
    model_id: str,
    base_url: str,
    hf_id: str,
    scaffold: str,
    scenario_ids: list[str],
    out_dir: Path,
) -> dict:
    """Run pilot for one (model, scaffold) pair. Returns summary dict."""
    from cga_bench.eval_harness.runner import EpisodeRunner

    cfg = _make_agent_config(model_id, base_url, scaffold, hf_id)
    agent = RAGAgent(cfg)
    loader = ScenarioLoader()

    summary = {
        "model": model_id,
        "scaffold": scaffold,
        "n_scenarios": len(scenario_ids),
        "n_completed": 0,
        "n_fallback": 0,
        "n_empty": 0,
        "actions_total": 0,
        "compliance_total": 0.0,
        "errors": [],
    }
    episodes: list[dict] = []

    for sid in scenario_ids:
        scenario = loader.get_scenario(sid)
        if scenario is None:
            summary["errors"].append(f"missing:{sid}")
            continue
        try:
            env = loader.create_environment(sid)
            graph_path = str(loader.get_cpg_graph_path(sid))
        except Exception as exc:
            summary["errors"].append(f"env:{sid}:{exc}")
            continue

        try:
            from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig
            from cga_bench.assessor_core.violations import (
                TimingSeverityThreshold,
                ViolationExtractor,
                ViolationExtractorConfig,
            )
            from cga_bench.cpg_engine.engine import CPGEngineConfig, CPGEngineFactory
            from cga_bench.cpg_model.schemas.base import HarmSeverity

            cpg_engine = CPGEngineFactory.load_from_file(
                graph_path,
                CPGEngineConfig(
                    graph_path=graph_path,
                    allergy_mappings=[],
                    comorbidity_constraints=[],
                ),
            )
            ve_cfg = ViolationExtractorConfig(
                harm_severity_mappings=[],
                timing_severity_thresholds=[
                    TimingSeverityThreshold(0, 30, HarmSeverity.MINOR),
                    TimingSeverityThreshold(30, 120, HarmSeverity.MODERATE),
                    TimingSeverityThreshold(120, 1e9, HarmSeverity.MAJOR),
                ],
            )
            ve = ViolationExtractor(ve_cfg)
            hs_cfg = HarmScorerConfig(
                violation_type_weights={
                    "OMISSION": 1.0,
                    "COMMISSION": 1.5,
                    "TIMING": 0.5,
                    "SEQUENCE": 0.7,
                    "DEVIATION": 0.4,
                },
                severity_weights={
                    "MINOR": 0.1,
                    "MODERATE": 0.4,
                    "MAJOR": 0.7,
                    "SEVERE": 0.9,
                    "CATASTROPHIC": 1.0,
                },
            )
            hs = HarmScorer(hs_cfg)

            runner = EpisodeRunner(agent, env, cpg_engine, ve, hs)
            ep_log, score, viols = runner.run_episode(scenario)
        except Exception as exc:
            summary["errors"].append(f"run:{sid}:{exc}")
            continue

        fb, empty, n_act = _classify_episode(ep_log, score, viols)
        summary["n_completed"] += 1
        if fb:
            summary["n_fallback"] += 1
        if empty:
            summary["n_empty"] += 1
        summary["actions_total"] += n_act
        cs = getattr(score, "compliance_score", 0.0) or 0.0
        summary["compliance_total"] += cs
        episodes.append(
            {
                "scenario_id": sid,
                "n_actions": n_act,
                "fallback": fb,
                "empty": empty,
                "compliance": cs,
                "n_violations": getattr(score, "total_violations", 0),
            }
        )

    # Derived
    n = max(summary["n_completed"], 1)
    summary["fallback_pct"] = round(100 * summary["n_fallback"] / n, 1)
    summary["empty_pct"] = round(100 * summary["n_empty"] / n, 1)
    summary["mean_actions"] = round(summary["actions_total"] / n, 1)
    summary["mean_compliance"] = round(summary["compliance_total"] / n, 3)

    # Write
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{model_id}_{scaffold}.json"
    out_path.write_text(json.dumps({"summary": summary, "episodes": episodes}, indent=2))
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", required=True, help="Display id e.g. qwen4b")
    p.add_argument("--hf-id", required=True, help="HF model id e.g. Qwen/Qwen3-4B-Instruct-2507")
    p.add_argument("--base-url", required=True, help="vLLM endpoint /v1 base URL")
    p.add_argument("--scaffolds", default="react,direct,checklist")
    p.add_argument("--n-scenarios", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="reports/pilot_dense_qwen/")
    args = p.parse_args()

    out_dir = Path(args.out)
    rng = random.Random(args.seed)
    loader = ScenarioLoader()
    all_ids = sorted(loader.list_scenarios())
    if len(all_ids) < args.n_scenarios:
        print(f"Only {len(all_ids)} scenarios available; using all")
        sample = all_ids
    else:
        sample = rng.sample(all_ids, args.n_scenarios)
    print(f"Pilot on {len(sample)} scenarios from pool of {len(all_ids)}")

    print("\n=== Pilot Summary ===")
    print(f"{'scaffold':12s} {'n':>4} {'fb%':>6} {'empty%':>7} {'avg_act':>8} {'comp':>6}")
    print("-" * 50)
    rows = []
    for sc in args.scaffolds.split(","):
        sc = sc.strip()
        t0 = time.time()
        s = run_pilot(args.model, args.base_url, args.hf_id, sc, sample, out_dir)
        dt = time.time() - t0
        print(
            f"{sc:12s} {s['n_completed']:>4} {s['fallback_pct']:>5.1f}% "
            f"{s['empty_pct']:>6.1f}% {s['mean_actions']:>7.1f} {s['mean_compliance']:>5.3f}  ({dt:.0f}s)"
        )
        rows.append(s)

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(rows, indent=2))
    print(f"\nWrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
