#!/usr/bin/env python3
"""CRES-4: Oracle-Fair Comparison — 4-variant information x reasoning factorial.

Runs V1 (Oracle), V2 (OracleRAG), V3 (RAGTable), V4 (RAG) across
scenarios x runs and aggregates per-domain deltas.

V1: Full table + rule-based   (upper bound)
V2: BM25 retrieval + rule-based (information-access cost)
V3: Full table + LLM reasoning (reasoning-modality cost)
V4: BM25 retrieval + LLM reasoning (current RAG agent)

Key deltas:
  V1 vs V2  -> cost of imperfect retrieval on rule-based reasoner
  V3 vs V4  -> cost of imperfect retrieval on LLM reasoner
  V2 vs V3  -> rule-based vs LLM reasoning with matched BM25 info
  V1 vs V3  -> rule-based vs LLM reasoning with full table info

Usage:
    # CPU-only pilot: V1,V2 x 10 scenarios x 1 run
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_cres_4_oracle_fair.py \
        --variants V1,V2 --pilot

    # Full 4-variant with vLLM:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_cres_4_oracle_fair.py \
        --variants V1,V2,V3,V4 --runs 3 \
        --vllm-endpoints http://localhost:8013,http://localhost:8013 \
        --output-dir results/cres_4/
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT.parent))
sys.path.insert(0, str(_ROOT))

from scripts.experiments._common import EVIDENCE_DIR, save_json  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"/tmp/cres4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUNS_PER_SCENARIO = 3
PILOT_N = 10
BUDGET_TOKENS = 100_000
BUDGET_TOOL_CALLS = 50
MAX_ACTIONS_PER_STEP = 3
TEMPERATURE = 0.1
LLM_MODEL = "Qwen/Qwen3.5-35B-A3B-FP8"

OUTPUT_DIR = EVIDENCE_DIR / "cres_4"

# Domains where Oracle has a decision table (V1/V2 only work on these)
ORACLE_SUPPORTED_DOMAINS: set[str] = {
    "sepsis",
    "chest_pain",
    "aki",
    "kdigo_contrast_aki",
    "heart_failure",
    "stroke",
    "dka",
    "pulmonary_embolism",
    "atrial_fibrillation",
    "copd",
    "gi_bleeding",
    "hypertensive_emergency",
}

# Domain detection from guideline_graph field
_GRAPH_TO_DOMAIN: dict[str, str] = {
    "ssc_sepsis_hour1": "sepsis",
    "ssc_sepsis_hour1_bundle": "sepsis",
    "aha_chest_pain": "chest_pain",
    "aha_chest_pain_evaluation": "chest_pain",
    "aha_heart_failure": "heart_failure",
    "aha_heart_failure_2022": "heart_failure",
    "aha_stroke": "stroke",
    "aha_stroke_2019": "stroke",
    "kdigo_aki_full": "aki",
    "kdigo_aki": "aki",
    "kdigo_contrast_aki": "kdigo_contrast_aki",
    "ada_dka_management": "dka",
    "atrial_fibrillation": "atrial_fibrillation",
    "cap_pneumonia": "cap",
    "copd_exacerbation": "copd",
    "gi_bleeding": "gi_bleeding",
    "hypertensive_emergency": "hypertensive_emergency",
    "pulmonary_embolism": "pulmonary_embolism",
    "acls_cardiac_arrest": "acls",
    "anaphylaxis": "anaphylaxis",
    "aabb_transfusion": "aabb_transfusion",
    "asthma_exacerbation": "asthma",
    "meningitis": "meningitis",
    "status_epilepticus": "status_epilepticus",
    "universal_clinical_safety": "universal",
    # Held-out
    "agitation_delirium": "agitation_delirium",
    "ards": "ards",
    "dic": "dic",
    "hyperkalemia": "hyperkalemia",
    "thyroid_storm": "thyroid_storm",
}


def detect_domain(guideline_graph: str) -> str:
    """Detect CPG domain from scenario's guideline_graph field."""
    if guideline_graph in _GRAPH_TO_DOMAIN:
        return _GRAPH_TO_DOMAIN[guideline_graph]
    # Try prefix matching
    for key, domain in _GRAPH_TO_DOMAIN.items():
        if guideline_graph.startswith(key) or key.startswith(guideline_graph):
            return domain
    return "unknown"


# ---------------------------------------------------------------------------
# Agent creation
# ---------------------------------------------------------------------------


def create_agent(
    variant: str,
    domain: str,
    vllm_endpoint: str | None = None,
) -> Any:
    """Create agent instance for the given variant and domain.

    Returns:
        Agent instance (OracleAgent, OracleRAGAgent, RAGTableAgent, or RAGAgent).
    """
    if variant == "V1":
        from cga_bench.agent_runner.oracle_agent import OracleAgent, OracleConfig

        config = OracleConfig(
            agent_id=f"cres4_v1_oracle_{domain}",
            guideline_domain=domain,
            max_actions_per_step=MAX_ACTIONS_PER_STEP,
        )
        return OracleAgent(config)

    if variant == "V2":
        from cga_bench.agent_runner.oracle_rag_agent import (
            OracleRAGAgent,
            OracleRAGConfig,
        )

        config = OracleRAGConfig(
            agent_id=f"cres4_v2_oracle_rag_{domain}",
            guideline_domain=domain,
            top_k=5,  # Must match V4's retrieval budget for factorial design
            max_actions_per_step=MAX_ACTIONS_PER_STEP,
        )
        return OracleRAGAgent(config)

    if variant == "V3":
        from cga_bench.agent_runner.rag_table_agent import (
            RAGTableAgent,
            RAGTableConfig,
        )

        if not vllm_endpoint:
            raise ValueError("V3 (RAGTable) requires --vllm-endpoints")

        config = RAGTableConfig(
            agent_id=f"cres4_v3_rag_table_{domain}",
            guideline_domain=domain,
            llm_backend="vllm",
            llm_model=LLM_MODEL,
            temperature=TEMPERATURE,
            use_llm=True,
            base_url=vllm_endpoint,
            api_key="sk-no-key-required",
            top_k=5,
            use_bm25=True,
            max_actions_per_step=MAX_ACTIONS_PER_STEP,
            budget_limit_tokens=BUDGET_TOKENS,
            budget_limit_tool_calls=BUDGET_TOOL_CALLS,
        )
        return RAGTableAgent(config)

    if variant == "V4":
        from cga_bench.agent_runner.rag_agent import RAGAgent, RAGConfig

        if not vllm_endpoint:
            raise ValueError("V4 (RAG) requires --vllm-endpoints")

        config = RAGConfig(
            agent_id=f"cres4_v4_rag_{domain}",
            llm_backend="vllm",
            llm_model=LLM_MODEL,
            temperature=TEMPERATURE,
            use_llm=True,
            base_url=vllm_endpoint,
            api_key="sk-no-key-required",
            top_k=5,
            use_bm25=True,
            max_actions_per_step=MAX_ACTIONS_PER_STEP,
            budget_limit_tokens=BUDGET_TOKENS,
            budget_limit_tool_calls=BUDGET_TOOL_CALLS,
        )
        return RAGAgent(config)

    raise ValueError(f"Unknown variant: {variant}")


def variant_needs_llm(variant: str) -> bool:
    """Return True if variant requires a vLLM endpoint."""
    return variant in ("V3", "V4")


# ---------------------------------------------------------------------------
# Scoring config (matches full_690_runner)
# ---------------------------------------------------------------------------


def get_scoring_configs() -> tuple[Any, Any]:
    """Return (ViolationExtractorConfig, HarmScorerConfig) matching main experiment."""
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

    return ve_config, hs_config


# ---------------------------------------------------------------------------
# Episode runner
# ---------------------------------------------------------------------------


def run_single_episode(
    variant: str,
    scenario_id: str,
    run_index: int,
    domain: str,
    output_dir: Path,
    vllm_endpoint: str | None = None,
) -> dict[str, Any] | None:
    """Run a single CRES-4 episode for one variant."""
    from cga_bench.eval_harness.runner import EvaluationRunner, ExperimentConfig
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    try:
        agent = create_agent(variant, domain, vllm_endpoint)
    except ValueError as e:
        logger.warning(f"Skip {variant}/{scenario_id}: {e}")
        return None

    loader = ScenarioLoader()
    scenario_def = loader.get_scenario(scenario_id)
    if scenario_def is None:
        logger.error(f"Scenario {scenario_id} not found")
        return None

    env = loader.create_environment(scenario_id)
    graph_path = str(loader.get_cpg_graph_path(scenario_id))

    ve_config, hs_config = get_scoring_configs()

    expected_actions = scenario_def.expected_actions or []
    forbidden_actions = scenario_def.forbidden_actions or []
    total_mandatory = len(expected_actions) if expected_actions else 5

    try:
        runner = EvaluationRunner(
            ExperimentConfig(
                experiment_id=f"cres_4_{variant}",
                scenarios=[scenario_id],
                agents=[f"cres4_{variant}"],
                num_runs_per_scenario=1,
            )
        )
        episode_log, score, _violations = runner.run_episode(
            agent=agent,
            environment=env,
            scenario_id=scenario_id,
            guideline_graph_path=graph_path,
            total_mandatory_count=total_mandatory,
            violation_extractor_config=ve_config,
            harm_scorer_config=hs_config,
            scenario_forbidden_actions=(forbidden_actions if forbidden_actions else None),
            scenario_expected_actions=(expected_actions if expected_actions else None),
        )

        result = {
            "scenario_id": scenario_id,
            "variant": variant,
            "domain": domain,
            "run_index": run_index,
            "actions_count": len(episode_log.actions),
            "actions": [
                {
                    "action_id": a.action_id,
                    "timestamp_minutes": a.timestamp_minutes,
                    "type": (a.type.value if hasattr(a.type, "value") else str(a.type)),
                }
                for a in episode_log.actions
            ],
            "compliance_score": score.compliance_score,
            "peak_risk": score.peak_risk,
            "aggregate_risk": score.aggregate_risk,
            "total_violations": score.total_violations,
            "violations_by_type": score.violations_by_type,
            "sub_scores": score.sub_scores,
            "expected_actions": expected_actions,
            "forbidden_actions": forbidden_actions,
            "n_expected_actions": len(expected_actions),
            "total_duration_minutes": episode_log.total_duration_minutes,
            "termination_reason": episode_log.termination_reason,
            "total_llm_calls": getattr(agent.metrics, "total_llm_calls", 0),
            "total_tokens": getattr(agent.metrics, "total_tokens", 0),
            "timestamp": datetime.now().isoformat(),
        }

        # Save per-episode JSON
        var_dir = output_dir / variant
        var_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{scenario_id}_{variant}_r{run_index}_{ts}.json"
        with open(var_dir / fname, "w") as f:
            json.dump(result, f, indent=2, default=str)

        return result

    except Exception as e:
        logger.error(f"FAIL {variant}/{scenario_id} r{run_index}: {e}")
        return None


# ---------------------------------------------------------------------------
# Checkpoint management
# ---------------------------------------------------------------------------


def load_checkpoint(path: Path) -> set[str]:
    """Load completed episode keys."""
    if not path.exists():
        return set()
    with open(path) as f:
        data = json.load(f)
    return set(data.get("completed", []))


def save_checkpoint(path: Path, completed: set[str]) -> None:
    """Save completed episode keys."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"completed": sorted(completed), "count": len(completed)}, f)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_results(
    output_dir: Path,
    variants: list[str],
) -> dict[str, Any]:
    """Aggregate per-variant results and compute deltas."""
    # Collect all episodes per variant — dedup by episode key, keep latest
    variant_episodes: dict[str, list[dict]] = defaultdict(list)
    for v in variants:
        var_dir = output_dir / v
        if not var_dir.exists():
            continue
        # First pass: group by episode key, keep file with latest timestamp
        keyed: dict[str, tuple[str, dict]] = {}  # key -> (filename, data)
        for f in var_dir.glob("*.json"):
            if f.name.startswith(("checkpoint", ".")):
                continue
            try:
                ep = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            sid = ep.get("scenario_id", "")
            ridx = ep.get("run_index", 0)
            if not sid:
                continue
            ep_key = f"{sid}_{v}_r{ridx}"
            # Keep latest file (lexicographic sort on timestamp suffix)
            if ep_key not in keyed or f.name > keyed[ep_key][0]:
                keyed[ep_key] = (f.name, ep)
        variant_episodes[v] = [data for _, data in keyed.values()]
        n_raw = sum(1 for f in var_dir.glob("*.json") if not f.name.startswith(("checkpoint", ".")))
        n_dedup = len(variant_episodes[v])
        if n_raw != n_dedup:
            logger.warning(f"  {v}: deduped {n_raw} files → {n_dedup} unique episodes")

    # Per-variant summary
    variant_summaries: dict[str, dict[str, Any]] = {}
    for v, episodes in variant_episodes.items():
        if not episodes:
            continue
        scores = [e["compliance_score"] for e in episodes]
        viols = [e["total_violations"] for e in episodes]
        acts = [e["actions_count"] for e in episodes]
        variant_summaries[v] = {
            "n_episodes": len(episodes),
            "mean_compliance": round(sum(scores) / len(scores), 4),
            "mean_violations": round(sum(viols) / len(viols), 2),
            "mean_actions": round(sum(acts) / len(acts), 2),
            "mean_tokens": round(
                sum(e.get("total_tokens", 0) for e in episodes) / len(episodes),
                0,
            ),
        }

    # Per-domain breakdown
    domain_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for v, episodes in variant_episodes.items():
        for ep in episodes:
            domain = ep.get("domain", "unknown")
            domain_scores[domain][v].append(ep["compliance_score"])

    domain_means: dict[str, dict[str, float]] = {}
    for domain, var_scores in domain_scores.items():
        domain_means[domain] = {v: round(sum(s) / len(s), 4) for v, s in var_scores.items() if s}

    # Compute deltas for key comparisons.
    # V3 vs V4 delta MUST be restricted to Oracle-supported domains only:
    # RAGTableAgent silently falls back to plain BM25 for unsupported domains,
    # making V3 ≡ V4 there — including them inflates the delta toward zero.
    delta_pairs = [
        ("V1", "V2", "retrieval_cost_rulebased"),
        ("V3", "V4", "retrieval_cost_llm"),
        ("V2", "V3", "reasoning_modality_bm25"),
        ("V1", "V3", "reasoning_modality_full"),
    ]

    # Pre-compute Oracle-filtered per-variant compliance lists for V3/V4 delta.
    _oracle_scores: dict[str, list[float]] = {}
    for v in ("V3", "V4"):
        if v not in variant_episodes:
            continue
        filtered = [
            ep["compliance_score"]
            for ep in variant_episodes[v]
            if ep.get("domain", "unknown") in ORACLE_SUPPORTED_DOMAINS
        ]
        excluded = len(variant_episodes[v]) - len(filtered)
        if excluded > 0:
            logger.warning(
                "V3/V4 delta: excluding %d %s episodes from unsupported domains "
                "(RAGTableAgent falls back to BM25 there — delta would be meaningless).",
                excluded,
                v,
            )
        _oracle_scores[v] = filtered

    deltas: dict[str, dict[str, Any]] = {}
    for va, vb, label in delta_pairs:
        if label == "retrieval_cost_llm":
            # Use Oracle-domain-filtered scores for V3 vs V4
            scores_a = _oracle_scores.get(va, [])
            scores_b = _oracle_scores.get(vb, [])
            if not scores_a or not scores_b:
                continue
            mean_a = sum(scores_a) / len(scores_a)
            mean_b = sum(scores_b) / len(scores_b)
            delta = mean_a - mean_b
            deltas[label] = {
                "pair": f"{va}-{vb}",
                "domain_filter": "oracle_supported_only",
                "n_episodes_filtered": {va: len(scores_a), vb: len(scores_b)},
                "delta_compliance": round(delta, 4),
                "delta_pct": round(delta * 100, 2),
                f"{va}_mean": round(mean_a, 4),
                f"{vb}_mean": round(mean_b, 4),
            }
            # Per-domain deltas (only Oracle-supported domains)
            per_domain: dict[str, float] = {}
            for domain, means in domain_means.items():
                if domain not in ORACLE_SUPPORTED_DOMAINS:
                    continue
                if va in means and vb in means:
                    per_domain[domain] = round(means[va] - means[vb], 4)
            deltas[label]["per_domain"] = per_domain
        else:
            if va in variant_summaries and vb in variant_summaries:
                delta = variant_summaries[va]["mean_compliance"] - variant_summaries[vb]["mean_compliance"]
                deltas[label] = {
                    "pair": f"{va}-{vb}",
                    "delta_compliance": round(delta, 4),
                    "delta_pct": round(delta * 100, 2),
                    f"{va}_mean": variant_summaries[va]["mean_compliance"],
                    f"{vb}_mean": variant_summaries[vb]["mean_compliance"],
                }

                # Per-domain deltas
                per_domain = {}
                for domain, means in domain_means.items():
                    if va in means and vb in means:
                        per_domain[domain] = round(means[va] - means[vb], 4)
                deltas[label]["per_domain"] = per_domain

    return {
        "experiment": "CRES-4",
        "description": "Oracle-Fair 4-variant factorial comparison",
        "variants_run": variants,
        "variant_summaries": variant_summaries,
        "domain_means": domain_means,
        "deltas": deltas,
        "timestamp": datetime.now().isoformat(),
    }


def write_macros(agg: dict[str, Any], output_dir: Path) -> None:
    """Write LaTeX macros for CRES-4 results."""
    lines = [
        "% CRES-4: Oracle-Fair Comparison Macros",
        "% Auto-generated by exp_cres_4_oracle_fair.py",
    ]

    for v, summary in agg.get("variant_summaries", {}).items():
        tag = v.lower()
        lines.append(f"\\newcommand{{\\cresFour{tag}N}}{{{summary['n_episodes']}}}")
        lines.append(f"\\newcommand{{\\cresFour{tag}Compliance}}{{{summary['mean_compliance']:.3f}}}")
        lines.append(f"\\newcommand{{\\cresFour{tag}Violations}}{{{summary['mean_violations']:.1f}}}")

    for label, delta in agg.get("deltas", {}).items():
        tag = label.replace("_", "")
        lines.append(f"\\newcommand{{\\cresFourDelta{tag}}}{{{delta['delta_pct']:+.1f}}}")

    macros_path = output_dir / "cres_4_macros.tex"
    macros_path.parent.mkdir(parents=True, exist_ok=True)
    macros_path.write_text("\n".join(lines) + "\n")
    logger.info(f"Saved macros to {macros_path}")


# ---------------------------------------------------------------------------
# vLLM health check
# ---------------------------------------------------------------------------


def health_check(endpoint: str) -> bool:
    """Check if a vLLM endpoint is responding.

    Handles both http://host:port and http://host:port/v1 formats.
    """
    import urllib.request

    # Normalize: ensure /v1 suffix for the models API
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        models_url = f"{base}/models"
    else:
        models_url = f"{base}/v1/models"

    try:
        req = urllib.request.Request(
            models_url,
            headers={"Authorization": "Bearer sk-no-key-required"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            model_id = data.get("data", [{}])[0].get("id", "?")
            logger.info(f"  Health OK: {endpoint} -> {model_id}")
            return True
    except Exception as e:
        logger.error(f"  Health FAIL: {endpoint} -> {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CRES-4: Oracle-Fair 4-variant comparison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--variants",
        default="V1,V2,V3,V4",
        help="Comma-separated subset of {V1,V2,V3,V4}.",
    )
    parser.add_argument(
        "--scenarios",
        type=int,
        default=706,
        help="Max scenarios to run (default: all 706).",
    )
    parser.add_argument("--runs", type=int, default=RUNS_PER_SCENARIO)
    parser.add_argument(
        "--vllm-endpoints",
        default="",
        help="Comma-separated vLLM base URLs for V3/V4.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_ROOT / "results" / "cres_4",
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help=f"Quick test: {PILOT_N} scenarios x 1 run.",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Skip execution, just aggregate existing results.",
    )
    parser.add_argument(
        "--shard",
        metavar="N/M",
        help="Run Nth chunk of M total scenarios.",
    )
    parser.add_argument(
        "--oracle-domain-filter",
        action="store_true",
        help="Force Oracle-supported domain filtering even for V3/V4-only runs.",
    )
    args = parser.parse_args()

    selected = [v.strip() for v in args.variants.split(",") if v.strip()]
    for v in selected:
        if v not in ("V1", "V2", "V3", "V4"):
            print(f"ERROR: Unknown variant {v!r}", file=sys.stderr)
            return 1

    # Parse vLLM endpoints
    # Normalize endpoints: ensure /v1 suffix for OpenAI-compatible API
    raw_endpoints = [e.strip() for e in args.vllm_endpoints.split(",") if e.strip()]
    endpoints = [ep if ep.rstrip("/").endswith("/v1") else f"{ep.rstrip('/')}/v1" for ep in raw_endpoints]

    # Check if LLM variants need endpoints
    llm_variants = [v for v in selected if variant_needs_llm(v)]
    if llm_variants and not endpoints:
        print(
            f"ERROR: Variants {llm_variants} require --vllm-endpoints.",
            file=sys.stderr,
        )
        return 2

    print("=" * 70)
    print("CRES-4: Oracle-Fair 4-Variant Comparison")
    print("=" * 70)
    print(f"  Variants: {selected}")
    print(f"  vLLM endpoints: {endpoints or '(none - CPU only)'}")

    # Aggregate-only mode
    if args.aggregate_only:
        print("\n--- Aggregate-only mode ---")
        agg = aggregate_results(args.output_dir, selected)
        save_json(agg, OUTPUT_DIR / "cres_4_results.json")
        write_macros(agg, OUTPUT_DIR)
        _print_summary(agg)
        return 0

    # Health check vLLM endpoints
    if endpoints:
        print("\n--- vLLM health check ---")
        healthy = [e for e in endpoints if health_check(e)]
        if not healthy and llm_variants:
            print("ERROR: No healthy vLLM endpoints.", file=sys.stderr)
            return 3
        endpoints = healthy
        print(f"  Healthy endpoints: {len(endpoints)}")

    # Load scenarios
    print("\n--- Loading scenarios ---")
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    loader = ScenarioLoader()
    all_scenarios = loader.load_all_scenarios()
    if isinstance(all_scenarios, dict):
        scenario_ids = sorted(all_scenarios.keys())
    else:
        scenario_ids = sorted(s.scenario_id for s in all_scenarios if hasattr(s, "scenario_id"))

    # Pre-detect domains for all scenarios (needed for pilot filtering)
    all_scenario_domains: dict[str, str] = {}
    for sid in scenario_ids:
        sdef = loader.get_scenario(sid)
        if sdef:
            gg = getattr(sdef, "guideline_graph", "") or ""
            all_scenario_domains[sid] = detect_domain(gg)
        else:
            all_scenario_domains[sid] = "unknown"

    # Filter to Oracle-supported domains if ANY variant is V1/V2
    # or if --oracle-domain-filter is explicitly set (for V3/V4-only comparability)
    oracle_variants = [v for v in selected if v in ("V1", "V2")]
    if oracle_variants or args.oracle_domain_filter:
        supported_ids = [
            sid for sid in scenario_ids if all_scenario_domains.get(sid, "unknown") in ORACLE_SUPPORTED_DOMAINS
        ]
        unsupported_count = len(scenario_ids) - len(supported_ids)
        if unsupported_count > 0:
            print(f"  Filtering: {unsupported_count} scenarios with unsupported Oracle domains removed")
        scenario_ids = supported_ids

    # Apply limits
    if args.pilot:
        # Sample across diverse domains instead of taking first N alphabetically
        from collections import OrderedDict

        domain_buckets: dict[str, list[str]] = OrderedDict()
        for sid in scenario_ids:
            d = all_scenario_domains.get(sid, "unknown")
            domain_buckets.setdefault(d, []).append(sid)
        pilot_ids: list[str] = []
        # Round-robin across domains until we reach PILOT_N
        bucket_iters = {d: iter(sids) for d, sids in domain_buckets.items()}
        while len(pilot_ids) < PILOT_N and bucket_iters:
            exhausted = []
            for d, it in bucket_iters.items():
                if len(pilot_ids) >= PILOT_N:
                    break
                try:
                    pilot_ids.append(next(it))
                except StopIteration:
                    exhausted.append(d)
            for d in exhausted:
                del bucket_iters[d]
        scenario_ids = pilot_ids
        runs = 1
        print(f"  PILOT MODE: {len(scenario_ids)} scenarios x {runs} run (domain-diverse)")
    else:
        scenario_ids = scenario_ids[: args.scenarios]
        runs = args.runs
        print(f"  Scenarios: {len(scenario_ids)}, Runs: {runs}")

    # Apply sharding
    if args.shard:
        parts = args.shard.split("/")
        idx, total = int(parts[0]), int(parts[1])
        chunk = len(scenario_ids) // total
        remainder = len(scenario_ids) % total
        start = min(idx - 1, remainder) * (chunk + 1) + max(0, idx - 1 - remainder) * chunk
        end = start + chunk + (1 if idx <= remainder else 0)
        scenario_ids = scenario_ids[start:end]
        print(f"  Shard {args.shard}: {len(scenario_ids)} scenarios")

    # Use pre-computed domains, filtered to final scenario_ids
    scenario_domains: dict[str, str] = {sid: all_scenario_domains.get(sid, "unknown") for sid in scenario_ids}

    domain_counts: dict[str, int] = defaultdict(int)
    for d in scenario_domains.values():
        domain_counts[d] += 1
    print(f"  Domains: {dict(domain_counts)}")

    total_episodes = len(selected) * len(scenario_ids) * runs
    print(f"  Total episodes: {total_episodes}")

    # Run episodes
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[dict] = []
    failures = 0
    endpoint_idx = 0

    for variant in selected:
        print(f"\n{'=' * 60}")
        print(f"Variant: {variant}")
        print(f"{'=' * 60}")

        # Checkpoint per variant+shard (avoids race condition between parallel shards)
        shard_suffix = f"_shard{args.shard.replace('/', 'of')}" if args.shard else ""
        cp_path = args.output_dir / variant / f"checkpoint{shard_suffix}.json"
        completed = load_checkpoint(cp_path)
        logger.info(f"  Checkpoint ({cp_path.name}): {len(completed)} episodes already done")

        needs_llm = variant_needs_llm(variant)

        for _sc_idx, scenario_id in enumerate(scenario_ids):
            domain = scenario_domains[scenario_id]

            for run_idx in range(runs):
                episode_key = f"{scenario_id}_{variant}_r{run_idx}"
                if episode_key in completed:
                    continue

                # Round-robin across endpoints for LLM variants
                vllm_ep = None
                if needs_llm and endpoints:
                    vllm_ep = endpoints[endpoint_idx % len(endpoints)]
                    endpoint_idx += 1

                progress = len(completed) + len([r for r in all_results if r["variant"] == variant])
                total_for_variant = len(scenario_ids) * runs
                logger.info(f"  [{progress + 1}/{total_for_variant}] {variant}/{scenario_id} r{run_idx} ({domain})")

                result = run_single_episode(
                    variant=variant,
                    scenario_id=scenario_id,
                    run_index=run_idx,
                    domain=domain,
                    output_dir=args.output_dir,
                    vllm_endpoint=vllm_ep,
                )

                if result is None:
                    failures += 1
                    # Retry once
                    time.sleep(1)
                    result = run_single_episode(
                        variant=variant,
                        scenario_id=scenario_id,
                        run_index=run_idx,
                        domain=domain,
                        output_dir=args.output_dir,
                        vllm_endpoint=vllm_ep,
                    )
                    if result is None:
                        failures += 1
                        continue

                all_results.append(result)
                completed.add(episode_key)

                # Checkpoint every 20 episodes
                if len(all_results) % 20 == 0:
                    save_checkpoint(cp_path, completed)

        save_checkpoint(cp_path, completed)
        logger.info(f"  {variant} complete: {sum(1 for r in all_results if r['variant'] == variant)} episodes")

    # Aggregate
    print(f"\n{'=' * 70}")
    print("Aggregation")
    print(f"{'=' * 70}")

    agg = aggregate_results(args.output_dir, selected)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(agg, OUTPUT_DIR / "cres_4_results.json")
    write_macros(agg, OUTPUT_DIR)
    _print_summary(agg)

    print(f"\nTotal episodes: {len(all_results)}, Failures: {failures}")
    print(f"Results: {args.output_dir}")
    print(f"Evidence: {OUTPUT_DIR}")

    return 0


def _print_summary(agg: dict[str, Any]) -> None:
    """Print human-readable summary."""
    print("\n--- Variant Summaries ---")
    for v, s in agg.get("variant_summaries", {}).items():
        print(
            f"  {v}: n={s['n_episodes']}, "
            f"compliance={s['mean_compliance']:.3f}, "
            f"violations={s['mean_violations']:.1f}, "
            f"tokens={s['mean_tokens']:.0f}"
        )

    print("\n--- Key Deltas ---")
    for label, d in agg.get("deltas", {}).items():
        print(f"  {d['pair']} ({label}): {d['delta_pct']:+.1f}pp compliance")

    domains = agg.get("domain_means", {})
    if domains:
        print(f"\n--- Domain Coverage: {len(domains)} domains ---")
        for domain in sorted(domains.keys())[:5]:
            means = domains[domain]
            parts = [f"{v}={m:.3f}" for v, m in sorted(means.items())]
            print(f"  {domain}: {', '.join(parts)}")
        if len(domains) > 5:
            print(f"  ... and {len(domains) - 5} more")


if __name__ == "__main__":
    sys.exit(main())
