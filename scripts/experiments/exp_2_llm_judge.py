#!/usr/bin/env python3
"""EXP-2: LLM Judge Pipeline -- WS-3 Evaluator Agreement Analysis.

Evaluates whether an LLM judge (via 3 prompt variants) agrees with
CGA-Bench evaluators by computing Cohen's kappa between each judge
variant and each evaluator from the verdict matrix.

Prompt variants:
  - rubric_free: No rubric, pure clinical judgment
  - rubric_aware: Constraints provided as rubric
  - cot_judge: Chain-of-thought per-constraint evaluation

Outputs:
  evidence_pack/exp_2_llm_judge.json
  evidence_pack/exp_2_llm_judge.md
  evidence_pack/tables/llm_judge_agreement.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_2_llm_judge.py --mode dry-run --mock-llm
    PYTHONPATH=. python scripts/experiments/exp_2_llm_judge.py --mode full --backend vllm --endpoint http://localhost:8013/v1
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import sys

import numpy as np
import yaml

_CGA_BENCH_ROOT = Path(__file__).resolve().parents[2]
# Add both cga_bench dir (for scripts.*) and its parent (for cga_bench.*)
sys.path.insert(0, str(_CGA_BENCH_ROOT))
sys.path.insert(0, str(_CGA_BENCH_ROOT.parent))

from scripts.evaluator_agreement import (
    EVALUATOR_KEYS,
    EVALUATOR_LABELS,
    cohens_kappa,
    interpret_kappa,
    load_per_episode,
)
from scripts.experiments._common import (
    EVIDENCE_DIR,
    SEED,
    TABLES_DIR,
    bootstrap_ci,
    fmt_f,
    save_json,
    save_latex_table,
    save_markdown,
)

from cga_bench.agent_runner.llm_provider import (
    LLMBackend,
    LLMConfig,
    LLMMessage,
    LLMProviderFactory,
    safe_json_parse,
)

try:
    import jinja2
except ImportError:
    jinja2 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "configs" / "llm_judge_prompts"
JUDGE_CONFIG_PATH = PROMPTS_DIR / "judge_config.yaml"
SCENARIOS_DIR = ROOT / "configs" / "scenarios"

PROMPT_VARIANTS = ["rubric_free", "rubric_aware", "cot_judge"]
DRY_RUN_EPISODE_LIMIT = 10


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


@dataclass
class EpisodeBundle:
    """Episode data combining verdict info with action traces and scenario context."""

    episode_id: str
    scenario_id: str
    model: str
    evaluator_verdicts: dict[str, bool]
    actions: list[dict]
    scenario_config: dict
    compliance_score: float


def _load_judge_config() -> dict:
    """Load judge configuration YAML."""
    with open(JUDGE_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _load_all_scenario_configs() -> dict[str, dict]:
    """Load all scenario configurations keyed by scenario_id."""
    configs: dict[str, dict] = {}
    for yf in sorted(SCENARIOS_DIR.glob("*.yaml")):
        try:
            with open(yf) as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
            continue
        if not data:
            continue
        items = data.get("scenarios", {})
        if isinstance(items, dict):
            for sid, sc in items.items():
                sc.setdefault("scenario_id", sid)
                configs[sid] = sc
    return configs


def _load_action_traces() -> dict[str, list[dict]]:
    """Load action traces from eval_science results.

    Returns:
        Mapping of (scenario_id, model_tag) -> list of action dicts.
        Key format: "{scenario_id}_{model_tag}" to match verdict episode_ids.
    """
    traces: dict[str, list[dict]] = {}
    results_base = ROOT / "results"

    # Map eval_science directory names to model tags used in verdict matrix
    dir_model_map = {
        "eval_science_rag_oss120b": "120B",
        "eval_science_rag_qwen35": "35B",
        "eval_science_qwen35": "35B",
        "eval_science_rag_qwen8b": "8B",
        "eval_science_rag_qwen3_4b": "4B",
        "eval_science_rag_oss20b": "20B",
        "eval_science_rag_deepseek_r1": "deepseek",
    }

    for dirname, model_tag in dir_model_map.items():
        dirpath = results_base / dirname
        if not dirpath.exists():
            continue
        for jf in sorted(dirpath.glob("*.json")):
            try:
                with open(jf) as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            results = data.get("results", [])
            for r in results:
                sid = r.get("scenario_id", "")
                actions = r.get("actions", [])
                if sid and actions:
                    key = f"{sid}_{model_tag}"
                    # Keep first occurrence (run 0)
                    if key not in traces:
                        traces[key] = actions
    return traces


def _build_trace_key(episode_id: str) -> str:
    """Build trace lookup key from episode_id.

    Episode IDs look like: 'adhf_warm_wet_120B_0'
    We need to extract scenario_id and model_tag.
    """
    parts = episode_id.rsplit("_", 2)
    if len(parts) >= 3:
        # scenario_id = everything before last 2 parts
        # model_tag = second-to-last, run_index = last
        scenario_id = "_".join(parts[:-2])
        model_tag = parts[-2]
        return f"{scenario_id}_{model_tag}"
    return episode_id


def load_episode_bundles(
    max_episodes: int | None = None,
) -> list[EpisodeBundle]:
    """Load episodes with verdict data, action traces, and scenario configs.

    Args:
        max_episodes: If set, limit to this many episodes.

    Returns:
        List of EpisodeBundle objects with all data merged.
    """
    verdict_episodes = load_per_episode()
    scenario_configs = _load_all_scenario_configs()
    action_traces = _load_action_traces()

    bundles: list[EpisodeBundle] = []
    for ep in verdict_episodes:
        episode_id = ep["episode_id"]
        scenario_id = ep["scenario_id"]

        # Look up action trace
        trace_key = _build_trace_key(episode_id)
        actions = action_traces.get(trace_key, [])

        # Normalize action format (eval_science uses 'timestamp', templates use 'timestamp_minutes')
        normalized_actions = []
        for a in actions:
            normalized_actions.append(
                {
                    "action_id": a.get("action_id", "unknown"),
                    "timestamp_minutes": a.get("timestamp_minutes", a.get("timestamp", 0.0)),
                    "type": a.get("type", "unknown"),
                    "justification": a.get("justification"),
                }
            )

        # Look up scenario config
        sc = scenario_configs.get(scenario_id, {})

        # Extract evaluator verdicts
        verdicts = {k: bool(ep.get(k, False)) for k in EVALUATOR_KEYS}

        bundles.append(
            EpisodeBundle(
                episode_id=episode_id,
                scenario_id=scenario_id,
                model=ep.get("model", ""),
                evaluator_verdicts=verdicts,
                actions=normalized_actions,
                scenario_config=sc,
                compliance_score=ep.get("c2_score", 0.0),
            )
        )

        if max_episodes and len(bundles) >= max_episodes:
            break

    return bundles


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def _get_jinja_env() -> jinja2.Environment:
    """Create Jinja2 environment pointing at the prompts directory."""
    if jinja2 is None:
        raise ImportError("jinja2 is required. Run: pip install jinja2")
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
        undefined=jinja2.StrictUndefined,
    )


def render_prompt(
    variant: str,
    bundle: EpisodeBundle,
) -> str:
    """Render a prompt template for a given episode.

    Args:
        variant: One of PROMPT_VARIANTS.
        bundle: Episode data bundle.

    Returns:
        Rendered prompt string.
    """
    env = _get_jinja_env()
    template = env.get_template(f"{variant}.jinja2")

    sc = bundle.scenario_config
    patient = sc.get("patient", {})

    context = {
        "scenario_description": sc.get("description", f"Scenario: {bundle.scenario_id}"),
        "patient": {
            "age": patient.get("age", "unknown"),
            "sex": patient.get("sex", "unknown"),
            "chief_complaint": patient.get("chief_complaint", "unknown"),
            "comorbidities": patient.get("comorbidities", []),
            "allergies": patient.get("allergies", []),
        },
        "actions": bundle.actions,
        # For rubric_aware and cot_judge
        "forbidden_actions": sc.get("forbidden_actions", []),
        "expected_actions": sc.get("expected_actions", []),
        "sequence_constraints": sc.get("sequence_constraints", []),
    }

    return template.render(**context)


# ---------------------------------------------------------------------------
# LLM Judge
# ---------------------------------------------------------------------------


def _parse_verdict(raw_response: str) -> dict:
    """Parse LLM judge response into structured verdict.

    Returns:
        Dict with at least 'verdict' key ('PASS' or 'FAIL').
    """
    try:
        parsed = safe_json_parse(raw_response)
        verdict = str(parsed.get("verdict", "")).upper()
        if verdict not in ("PASS", "FAIL"):
            verdict = "FAIL"
        parsed["verdict"] = verdict
        return parsed
    except (json.JSONDecodeError, ValueError):
        # Fallback: search for PASS/FAIL in raw text
        upper = raw_response.upper()
        if "PASS" in upper and "FAIL" not in upper:
            return {"verdict": "PASS", "reasoning": "parsed from raw text"}
        return {"verdict": "FAIL", "reasoning": "parse failure, defaulting to FAIL"}


def _mock_verdict(
    episode_id: str,
    variant: str,
    seed: int,
) -> dict:
    """Generate deterministic mock verdict for testing.

    Uses a hash of episode_id + variant + seed for reproducibility.
    """
    hash_input = f"{episode_id}:{variant}:{seed}"
    h = hashlib.md5(hash_input.encode()).hexdigest()
    # Use first 8 hex chars as integer, then threshold
    val = int(h[:8], 16) / 0xFFFFFFFF
    verdict = "PASS" if val > 0.4 else "FAIL"
    return {
        "verdict": verdict,
        "reasoning": f"mock verdict (hash-based, val={val:.3f})",
    }


def run_judge_on_episode(
    provider: object,
    variant: str,
    bundle: EpisodeBundle,
    mock: bool = False,
    seed: int = SEED,
) -> dict:
    """Run a single LLM judge call on one episode.

    Args:
        provider: LLM provider instance (BaseLLMProvider).
        variant: Prompt variant name.
        bundle: Episode data.
        mock: If True, return mock verdict without LLM call.
        seed: Random seed for mock mode.

    Returns:
        Dict with verdict and metadata.
    """
    if mock:
        return _mock_verdict(bundle.episode_id, variant, seed)

    prompt = render_prompt(variant, bundle)
    messages = [
        LLMMessage(role="system", content="You are a clinical evaluation expert. Respond only with valid JSON."),
        LLMMessage(role="user", content=prompt),
    ]

    try:
        response = provider.complete(messages)  # type: ignore[union-attr]
        return _parse_verdict(response.content)
    except Exception as e:
        logger.warning(f"LLM call failed for {bundle.episode_id}/{variant}: {e}")
        return {"verdict": "FAIL", "reasoning": f"LLM call error: {e}"}


# ---------------------------------------------------------------------------
# Agreement computation
# ---------------------------------------------------------------------------


def compute_agreement(
    judge_verdicts: dict[str, list[int]],
    evaluator_verdicts: dict[str, list[int]],
) -> dict:
    """Compute Cohen's kappa between each judge variant and each evaluator.

    Args:
        judge_verdicts: {variant_name: [0/1 verdicts]}.
        evaluator_verdicts: {evaluator_key: [0/1 verdicts]}.

    Returns:
        Nested dict of kappa values and summary statistics.
    """
    results: dict[str, dict] = {}

    for variant in judge_verdicts:
        results[variant] = {}
        j_vec = judge_verdicts[variant]

        for eval_key, eval_label in zip(EVALUATOR_KEYS, EVALUATOR_LABELS):
            e_vec = evaluator_verdicts[eval_key]
            kappa = cohens_kappa(j_vec, e_vec)
            agree_count = sum(a == b for a, b in zip(j_vec, e_vec))
            n = len(j_vec)

            results[variant][eval_label] = {
                "kappa": round(kappa, 4),
                "interpretation": interpret_kappa(kappa),
                "agreement_pct": round(agree_count / n * 100, 1) if n > 0 else 0.0,
                "n": n,
            }

    return results


def compute_judge_pass_rates(
    judge_verdicts: dict[str, list[int]],
) -> dict[str, float]:
    """Compute pass rate for each judge variant."""
    rates: dict[str, float] = {}
    for variant, vec in judge_verdicts.items():
        rates[variant] = round(sum(vec) / len(vec), 4) if vec else 0.0
    return rates


def compute_inter_judge_kappa(
    judge_verdicts: dict[str, list[int]],
) -> dict[str, float]:
    """Compute pairwise Cohen's kappa between judge variants."""
    from itertools import combinations

    pairwise: dict[str, float] = {}
    for v1, v2 in combinations(judge_verdicts.keys(), 2):
        kappa = cohens_kappa(judge_verdicts[v1], judge_verdicts[v2])
        pairwise[f"{v1}_vs_{v2}"] = round(kappa, 4)
    return pairwise


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------


def generate_markdown_report(
    agreement: dict,
    judge_pass_rates: dict[str, float],
    inter_judge: dict[str, float],
    n_episodes: int,
    mode: str,
    model_name: str,
) -> str:
    """Generate markdown summary report."""
    lines = [
        "# EXP-2: LLM Judge Pipeline Agreement Analysis",
        "",
        f"**Mode**: {mode}",
        f"**Model**: {model_name}",
        f"**Episodes evaluated**: {n_episodes}",
        "",
        "## Judge Variant Pass Rates",
        "",
        "| Variant | Pass Rate |",
        "|---------|-----------|",
    ]
    for variant, rate in judge_pass_rates.items():
        lines.append(f"| {variant} | {rate:.1%} |")

    lines += [
        "",
        "## Inter-Judge Agreement (between prompt variants)",
        "",
        "| Pair | Cohen's Kappa | Interpretation |",
        "|------|---------------|----------------|",
    ]
    for pair, kappa in inter_judge.items():
        lines.append(f"| {pair} | {kappa:.4f} | {interpret_kappa(kappa)} |")

    lines += [
        "",
        "## Judge vs CGA-Bench Evaluator Agreement",
        "",
    ]

    for variant in PROMPT_VARIANTS:
        if variant not in agreement:
            continue
        lines += [
            f"### {variant}",
            "",
            "| Evaluator | Kappa | Agreement % | Interpretation |",
            "|-----------|-------|-------------|----------------|",
        ]
        for eval_label in EVALUATOR_LABELS:
            entry = agreement[variant].get(eval_label, {})
            lines.append(
                f"| {eval_label} | {entry.get('kappa', 0):.4f} | "
                f"{entry.get('agreement_pct', 0):.1f}% | "
                f"{entry.get('interpretation', 'N/A')} |"
            )
        lines.append("")

    return "\n".join(lines)


def generate_latex_rows(
    agreement: dict,
) -> tuple[list[list[str]], list[str]]:
    """Generate LaTeX table rows for judge-evaluator agreement.

    Returns:
        (rows, headers) for save_latex_table.
    """
    headers = ["Variant"] + EVALUATOR_LABELS
    rows: list[list[str]] = []

    for variant in PROMPT_VARIANTS:
        if variant not in agreement:
            continue
        row = [variant.replace("_", r"\_")]
        for label in EVALUATOR_LABELS:
            entry = agreement[variant].get(label, {})
            kappa = entry.get("kappa", 0.0)
            row.append(fmt_f(kappa, 3))
        rows.append(row)

    return rows, headers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="EXP-2: LLM Judge Pipeline for CGA-Bench",
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "full"],
        default="dry-run",
        help="Run mode: dry-run (10 episodes) or full",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM responses (no API calls)",
    )
    parser.add_argument(
        "--backend",
        choices=["vllm", "openai", "anthropic", "mock"],
        default=None,
        help="LLM backend (default: from judge_config.yaml)",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=None,
        help="LLM endpoint URL (for vLLM backend)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: from judge_config.yaml)",
    )
    return parser.parse_args()


def main() -> None:
    """Run the LLM judge experiment."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    # Load config
    judge_config = _load_judge_config()
    backend_str = args.backend or judge_config.get("default_backend", "mock")
    model_name = args.model or judge_config.get("default_model", "mock")
    endpoint = args.endpoint or judge_config.get("default_endpoint")

    # Determine episode limit
    max_episodes: int | None = None
    if args.mode == "dry-run":
        max_episodes = judge_config.get("dry_run", {}).get("n_episodes", DRY_RUN_EPISODE_LIMIT)

    # If mock-llm flag is set, override backend
    if args.mock_llm:
        backend_str = "mock"

    print("=== EXP-2: LLM Judge Pipeline ===")
    print(f"Mode: {args.mode}")
    print(f"Backend: {backend_str}")
    print(f"Model: {model_name}")
    print(f"Mock LLM: {args.mock_llm}")
    print()

    # Load episodes
    print("Loading episodes...")
    bundles = load_episode_bundles(max_episodes=max_episodes)
    n_episodes = len(bundles)
    print(f"Loaded {n_episodes} episodes")

    if n_episodes == 0:
        print("ERROR: No episodes loaded. Check verdict matrix and results directories.")
        sys.exit(1)

    # Create LLM provider (only needed for non-mock mode)
    provider = None
    if not args.mock_llm:
        backend_enum = LLMBackend(backend_str)
        llm_config = LLMConfig(
            backend=backend_enum,
            model=model_name,
            temperature=judge_config.get("temperature", 0.1),
            max_tokens=judge_config.get("max_tokens", 2048),
            base_url=endpoint if backend_enum == LLMBackend.VLLM else None,
        )
        provider = LLMProviderFactory.create(llm_config)

    # Run judge on each episode for each prompt variant
    judge_results: dict[str, list[dict]] = {v: [] for v in PROMPT_VARIANTS}
    judge_verdicts: dict[str, list[int]] = {v: [] for v in PROMPT_VARIANTS}
    evaluator_verdicts: dict[str, list[int]] = {k: [] for k in EVALUATOR_KEYS}

    for i, bundle in enumerate(bundles):
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  Processing episode {i + 1}/{n_episodes}: {bundle.episode_id}")

        # Collect evaluator verdicts
        for key in EVALUATOR_KEYS:
            evaluator_verdicts[key].append(1 if bundle.evaluator_verdicts.get(key, False) else 0)

        # Run each judge variant
        for variant in PROMPT_VARIANTS:
            result = run_judge_on_episode(
                provider=provider,
                variant=variant,
                bundle=bundle,
                mock=args.mock_llm,
                seed=SEED,
            )
            result["episode_id"] = bundle.episode_id
            result["scenario_id"] = bundle.scenario_id
            result["model"] = bundle.model
            result["variant"] = variant

            judge_results[variant].append(result)
            judge_verdicts[variant].append(1 if result["verdict"] == "PASS" else 0)

    # Compute agreement metrics
    print("\nComputing agreement metrics...")
    agreement = compute_agreement(judge_verdicts, evaluator_verdicts)
    judge_pass_rates = compute_judge_pass_rates(judge_verdicts)
    inter_judge = compute_inter_judge_kappa(judge_verdicts)

    # Bootstrap CI for kappa values
    kappa_cis: dict[str, dict[str, tuple[float, float]]] = {}
    for variant in PROMPT_VARIANTS:
        kappa_cis[variant] = {}
        j_arr = np.array(judge_verdicts[variant])
        for eval_key, eval_label in zip(EVALUATOR_KEYS, EVALUATOR_LABELS):
            e_arr = np.array(evaluator_verdicts[eval_key])
            paired = np.column_stack([j_arr, e_arr])

            def kappa_statistic(sample: np.ndarray) -> float:
                return cohens_kappa(sample[:, 0].tolist(), sample[:, 1].tolist())

            ci = bootstrap_ci(paired, kappa_statistic, n_bootstrap=1000, seed=SEED)
            kappa_cis[variant][eval_label] = ci

    # Print summary
    print("\n=== Judge Pass Rates ===")
    for variant, rate in judge_pass_rates.items():
        print(f"  {variant}: {rate:.1%}")

    print("\n=== Inter-Judge Agreement ===")
    for pair, kappa in inter_judge.items():
        print(f"  {pair}: kappa={kappa:.4f} ({interpret_kappa(kappa)})")

    print("\n=== Judge vs Evaluator Agreement ===")
    for variant in PROMPT_VARIANTS:
        print(f"\n  --- {variant} ---")
        for label in EVALUATOR_LABELS:
            entry = agreement[variant].get(label, {})
            ci = kappa_cis.get(variant, {}).get(label, (0.0, 0.0))
            print(
                f"    vs {label}: kappa={entry.get('kappa', 0):.4f} "
                f"[{ci[0]:.3f}, {ci[1]:.3f}] "
                f"({entry.get('interpretation', 'N/A')})"
            )

    # Save outputs
    print("\nSaving outputs...")

    # JSON output
    output_data = {
        "experiment": "exp_2_llm_judge",
        "mode": args.mode,
        "model": model_name,
        "backend": backend_str,
        "mock_llm": args.mock_llm,
        "n_episodes": n_episodes,
        "judge_pass_rates": judge_pass_rates,
        "inter_judge_kappa": inter_judge,
        "agreement": agreement,
        "bootstrap_ci": {
            variant: {label: {"lower": ci[0], "upper": ci[1]} for label, ci in variant_cis.items()}
            for variant, variant_cis in kappa_cis.items()
        },
        "per_episode_verdicts": {
            variant: [
                {
                    "episode_id": r["episode_id"],
                    "verdict": r["verdict"],
                    "reasoning": r.get("reasoning", ""),
                }
                for r in results
            ]
            for variant, results in judge_results.items()
        },
    }
    save_json(output_data, EVIDENCE_DIR / "exp_2_llm_judge.json")

    # Markdown report
    md_report = generate_markdown_report(
        agreement=agreement,
        judge_pass_rates=judge_pass_rates,
        inter_judge=inter_judge,
        n_episodes=n_episodes,
        mode=args.mode,
        model_name=model_name,
    )
    save_markdown(md_report, EVIDENCE_DIR / "exp_2_llm_judge.md")

    # LaTeX table
    rows, headers = generate_latex_rows(agreement)
    save_latex_table(
        rows=rows,
        headers=headers,
        path=TABLES_DIR / "llm_judge_agreement.tex",
        caption="LLM Judge vs CGA-Bench Evaluator Agreement (Cohen's $\\kappa$)",
        label="tab:llm_judge_agreement",
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
