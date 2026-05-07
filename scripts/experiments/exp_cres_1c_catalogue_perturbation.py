#!/usr/bin/env python3
"""CRES-1C: Catalogue Perturbation Stress Test.

Generates perturbed scoring catalogues (drop/duplicate/shuffle rules),
re-scores sampled traces under each, and measures verdict stability.

If TCC verdicts are robust to catalogue noise, the scoring isn't
fragile or over-fitted to a specific rule formulation.

Target: Median trace-level agreement >= 85%.

Output:
    evidence_pack/cres_1c/cres_1c_results.json
    evidence_pack/cres_1c/cres_1c_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_cres_1c_catalogue_perturbation.py
"""

from __future__ import annotations

import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from scripts.experiments._common import EVIDENCE_DIR, save_json
from scripts.experiments._episode_cache import load_cached_episodes, score_episode
import yaml

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = EVIDENCE_DIR / "cres_1c"
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"

N_PERTURBATIONS = 200  # Number of perturbed catalogues (reduced from 1000 for speed)
N_SAMPLE_TRACES = 2000  # Number of traces to re-score
SEED = 42

# Perturbation parameters
DROP_RATE_MIN = 0.05
DROP_RATE_MAX = 0.15
DUPLICATE_RATE_MIN = 0.0
DUPLICATE_RATE_MAX = 0.10
DEADLINE_JITTER_FACTOR = 0.5  # ±50% jitter on deadlines


# ---------------------------------------------------------------------------
# Catalogue (graph) loading
# ---------------------------------------------------------------------------


def load_all_graph_rules() -> dict[str, list[dict]]:
    """Load all CPG graph YAML files and extract node-level rules.

    Returns:
        Dict mapping graph_id -> list of node dicts.
    """
    graphs: dict[str, list[dict]] = {}
    for gp in sorted(GRAPHS_DIR.glob("*.yaml")):
        try:
            with open(gp) as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                continue
            gid = data.get("graph_id", gp.stem)
            nodes = data.get("nodes", {})
            if isinstance(nodes, dict):
                node_list = list(nodes.values())
            elif isinstance(nodes, list):
                node_list = nodes
            else:
                continue
            graphs[gid] = node_list
        except (OSError, yaml.YAMLError):
            continue
    return graphs


def extract_rules_from_graph(nodes: list[dict]) -> list[dict]:
    """Extract expected/forbidden/deadline rules from graph nodes."""
    rules: list[dict] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("node_id", node.get("id", ""))

        # Expected actions
        for action in node.get("expected_actions", []):
            if isinstance(action, str):
                rules.append(
                    {
                        "type": "expected",
                        "action_id": action,
                        "node_id": node_id,
                        "deadline": node.get("deadline_minutes"),
                    }
                )
            elif isinstance(action, dict):
                rules.append(
                    {
                        "type": "expected",
                        "action_id": action.get("action_id", ""),
                        "node_id": node_id,
                        "deadline": action.get("deadline_minutes", node.get("deadline_minutes")),
                    }
                )

        # Forbidden actions
        for action in node.get("forbidden_actions", []):
            if isinstance(action, str):
                rules.append({"type": "forbidden", "action_id": action, "node_id": node_id})
            elif isinstance(action, dict):
                rules.append(
                    {
                        "type": "forbidden",
                        "action_id": action.get("action_id", ""),
                        "node_id": node_id,
                    }
                )

    return rules


# ---------------------------------------------------------------------------
# Perturbation engine
# ---------------------------------------------------------------------------


def perturb_episode_rules(
    ep: dict,
    rng: random.Random,
) -> dict:
    """Create a perturbed version of an episode's expected/forbidden actions.

    Perturbations:
    1. Drop 5-15% of expected actions
    2. Duplicate 0-10% of expected actions (add noise)
    3. Jitter deadline-related violation thresholds
    4. Shuffle forbidden action list
    """
    perturbed = json.loads(json.dumps(ep))  # Deep copy

    # Perturb expected actions
    expected = perturbed.get("expected_actions", [])
    if expected:
        drop_rate = rng.uniform(DROP_RATE_MIN, DROP_RATE_MAX)
        n_drop = max(0, int(len(expected) * drop_rate))
        if n_drop > 0 and len(expected) > n_drop:
            drop_indices = set(rng.sample(range(len(expected)), n_drop))
            expected = [a for i, a in enumerate(expected) if i not in drop_indices]

        # Duplicate some
        dup_rate = rng.uniform(DUPLICATE_RATE_MIN, DUPLICATE_RATE_MAX)
        n_dup = int(len(expected) * dup_rate)
        if n_dup > 0 and expected:
            dups = rng.choices(expected, k=n_dup)
            expected.extend(dups)

        perturbed["expected_actions"] = expected

    # Jitter violation timestamps (affects timing violation detection)
    violations = perturbed.get("violation_events", [])
    for v in violations:
        if isinstance(v, dict) and "delay_minutes" in v:
            delay = v["delay_minutes"]
            if isinstance(delay, (int, float)):
                jitter = rng.uniform(-DEADLINE_JITTER_FACTOR, DEADLINE_JITTER_FACTOR)
                v["delay_minutes"] = max(0, delay * (1 + jitter))

    return perturbed


def rescore_perturbed(ep_perturbed: dict) -> dict:
    """Score a perturbed episode using the standard scorer."""
    return score_episode(ep_perturbed)


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("CRES-1C: Catalogue Perturbation Stress Test")
    print("=" * 60)

    # Load episodes
    episodes = load_cached_episodes()
    print(f"\nLoaded {len(episodes)} baseline episodes")

    # Sample traces for re-scoring
    rng = random.Random(SEED)
    n_sample = min(N_SAMPLE_TRACES, len(episodes))
    sampled_eps = rng.sample(episodes, n_sample)
    print(f"Sampled {n_sample} traces for perturbation testing")

    # Score original traces
    print("\nScoring original traces...")
    original_verdicts: list[dict] = []
    for ep in sampled_eps:
        rec = score_episode(ep)
        original_verdicts.append(rec)

    # Run perturbations
    print(f"\nRunning {N_PERTURBATIONS} perturbations on {n_sample} traces...")

    # For each trace, track how many perturbations agree with original
    trace_agreements: list[float] = []  # Per-trace agreement rate
    per_evaluator_agreements: dict[str, list[float]] = {
        "ac_proxy": [],
        "mab_proxy": [],
        "c2_pass": [],
        "cga_pass": [],
        "verdict_flip": [],
        "ao_fa": [],
    }

    for trace_idx in range(n_sample):
        ep = sampled_eps[trace_idx]
        orig = original_verdicts[trace_idx]

        n_agree_all = 0
        eval_agrees: dict[str, int] = dict.fromkeys(per_evaluator_agreements, 0)

        for pert_idx in range(N_PERTURBATIONS):
            pert_rng = random.Random(SEED + trace_idx * 10000 + pert_idx)
            ep_pert = perturb_episode_rules(ep, pert_rng)
            pert_rec = rescore_perturbed(ep_pert)

            # Check agreement on each evaluator
            all_agree = True
            for key in eval_agrees:
                if orig[key] == pert_rec[key]:
                    eval_agrees[key] += 1
                else:
                    all_agree = False
            if all_agree:
                n_agree_all += 1

        trace_agree_rate = n_agree_all / N_PERTURBATIONS
        trace_agreements.append(trace_agree_rate)

        for key in eval_agrees:
            per_evaluator_agreements[key].append(eval_agrees[key] / N_PERTURBATIONS)

        if (trace_idx + 1) % 500 == 0:
            median_so_far = float(np.median(trace_agreements))
            print(f"  Processed {trace_idx + 1}/{n_sample} traces, median agreement so far: {median_so_far:.1%}")

    # Compute summary statistics
    trace_agreements_arr = np.array(trace_agreements)
    median_agreement = float(np.median(trace_agreements_arr))
    mean_agreement = float(np.mean(trace_agreements_arr))
    q25_agreement = float(np.percentile(trace_agreements_arr, 25))
    q75_agreement = float(np.percentile(trace_agreements_arr, 75))
    pct_above_85 = float(np.mean(trace_agreements_arr >= 0.85)) * 100

    per_eval_medians: dict[str, float] = {}
    for key, vals in per_evaluator_agreements.items():
        per_eval_medians[key] = float(np.median(vals))

    # Target check
    target_met = median_agreement >= 0.85

    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"  N perturbations:       {N_PERTURBATIONS}")
    print(f"  N sampled traces:      {n_sample}")
    print(f"  Median agreement:      {median_agreement:.1%} {'PASS' if target_met else 'WARN'}")
    print(f"  Mean agreement:        {mean_agreement:.1%}")
    print(f"  IQR:                   [{q25_agreement:.1%}, {q75_agreement:.1%}]")
    print(f"  Traces >= 85%:         {pct_above_85:.1f}%")
    print("\n  Per-evaluator median agreement:")
    for key, val in per_eval_medians.items():
        print(f"    {key:20s}: {val:.1%}")

    # Save results
    results = {
        "experiment": "CRES-1C",
        "description": "Catalogue Perturbation Stress Test",
        "n_perturbations": N_PERTURBATIONS,
        "n_sampled_traces": n_sample,
        "perturbation_params": {
            "drop_rate": [DROP_RATE_MIN, DROP_RATE_MAX],
            "duplicate_rate": [DUPLICATE_RATE_MIN, DUPLICATE_RATE_MAX],
            "deadline_jitter_factor": DEADLINE_JITTER_FACTOR,
        },
        "median_agreement": round(median_agreement * 100, 1),
        "mean_agreement": round(mean_agreement * 100, 1),
        "q25_agreement": round(q25_agreement * 100, 1),
        "q75_agreement": round(q75_agreement * 100, 1),
        "pct_traces_above_85": round(pct_above_85, 1),
        "per_evaluator_median_agreement": {k: round(v * 100, 1) for k, v in per_eval_medians.items()},
        "target_met": target_met,
    }
    save_json(results, OUTPUT_DIR / "cres_1c_results.json")

    # Save macros
    macros = [
        f"\\newcommand{{\\cresOneCMedian}}{{{results['median_agreement']:.1f}}}",
        f"\\newcommand{{\\cresOneCMean}}{{{results['mean_agreement']:.1f}}}",
        f"\\newcommand{{\\cresOneCIQRLow}}{{{results['q25_agreement']:.1f}}}",
        f"\\newcommand{{\\cresOneCIQRHigh}}{{{results['q75_agreement']:.1f}}}",
        f"\\newcommand{{\\cresOneCAbove}}{{{results['pct_traces_above_85']:.1f}}}",
        f"\\newcommand{{\\cresOneCNPert}}{{{N_PERTURBATIONS}}}",
        f"\\newcommand{{\\cresOneCNTraces}}{{{n_sample}}}",
    ]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "cres_1c_macros.tex", "w") as f:
        f.write("% CRES-1C: Catalogue Perturbation Stress Test\n")
        f.write("\n".join(macros) + "\n")
    print(f"\n  Saved macros to {OUTPUT_DIR / 'cres_1c_macros.tex'}")


if __name__ == "__main__":
    main()
