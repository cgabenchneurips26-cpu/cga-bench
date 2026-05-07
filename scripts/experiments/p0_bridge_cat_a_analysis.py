#!/usr/bin/env python3
"""P0 Bridge Analysis: V6 Cat A subset + V7.3 Cat A mab_proxy.

Computes:
  P0-1: V6 Cat A 5 bridge numbers vs V6 Full
  P0-2: V7.3 Cat A mab_proxy pass rate
  P0-3: mab_proxy/ac_proxy definition audit

Outputs:
  reports/path_d_day3/v6_cat_a_bridge.json
  reports/path_d_day3/v73_cat_a_mab_analysis.json
  reports/path_d_day3/p0_bridge_comparison_matrix.json
  paper/auto_numbers_v6_cat_a_bridge.tex
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
import json
import os
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""

    def default(self, o: object) -> object:
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)


# ─────────────────────────────────────────────────────────────────────
# 1. Build Cat A/B/M scenario classification (from graph node matching)
# ─────────────────────────────────────────────────────────────────────


def load_graph_action_ids(graph_path: str) -> set[str]:
    """Extract all action IDs from a CPG graph YAML."""
    with open(graph_path) as f:
        g = yaml.safe_load(f)

    actions: set[str] = set()
    nodes = g.get("nodes", {})
    if isinstance(nodes, dict):
        node_list = nodes.values()
    else:
        node_list = nodes

    for node in node_list:
        if not isinstance(node, dict):
            continue
        # Collect from all action-bearing fields
        for field in ("actions", "mandatory_actions", "forbidden_actions"):
            val = node.get(field, [])
            if isinstance(val, list):
                actions.update(str(a) for a in val)
            elif isinstance(val, dict):
                actions.update(str(k) for k in val.keys())
        # conditional_next keys
        cn = node.get("conditional_next", {})
        if isinstance(cn, dict):
            for targets in cn.values():
                if isinstance(targets, list):
                    actions.update(str(t) for t in targets)
    return actions


def classify_scenarios() -> dict[str, str]:
    """Classify each scenario as Cat A / B / M based on orphan analysis."""
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    # Load all scenarios from manual + auto
    loader = ScenarioLoader(scenarios_dir=str(ROOT / "configs" / "scenarios"))
    scenarios = loader.load_all_scenarios()
    if isinstance(scenarios, dict):
        scenario_dict = scenarios
    else:
        scenario_dict = {s.scenario_id: s for s in scenarios}

    # Also load SGSC scenarios from configs/scenarios/sgsc/
    sgsc_dir = ROOT / "configs" / "scenarios" / "sgsc"
    if sgsc_dir.exists():
        for yf in sgsc_dir.glob("*_scenarios.yaml"):
            with open(yf) as f:
                data = yaml.safe_load(f)
            if not data or "scenarios" not in data:
                continue
            for sid, sdata in data["scenarios"].items():
                if sid not in scenario_dict:
                    scenario_dict[sid] = sdata

    # Also load SGSC capped scenarios
    sgsc_capped_dir = ROOT / "configs" / "scenarios" / "sgsc_capped"
    if sgsc_capped_dir.exists():
        for yf in sgsc_capped_dir.glob("*_scenarios.yaml"):
            with open(yf) as f:
                data = yaml.safe_load(f)
            if not data or "scenarios" not in data:
                continue
            for sid, sdata in data["scenarios"].items():
                if sid not in scenario_dict:
                    scenario_dict[sid] = sdata

    # Load all graphs
    graph_dir = ROOT / "cpg_model" / "graphs"
    graph_actions: dict[str, set[str]] = {}
    for gf in graph_dir.glob("*.yaml"):
        graph_actions[gf.stem] = load_graph_action_ids(str(gf))
    # Also auto graphs
    auto_dir = graph_dir / "auto"
    if auto_dir.exists():
        for gf in auto_dir.glob("*.yaml"):
            graph_actions[gf.stem] = load_graph_action_ids(str(gf))

    cat_map: dict[str, str] = {}
    for sid, scen in scenario_dict.items():
        # Get graph reference
        graph_id = None
        if hasattr(scen, "guideline_graph"):
            graph_id = scen.guideline_graph
        elif hasattr(scen, "graph"):
            graph_id = scen.graph
        elif isinstance(scen, dict):
            graph_id = scen.get("guideline_graph") or scen.get("graph")

        if not graph_id or graph_id not in graph_actions:
            cat_map[sid] = "M"  # unknown graph → mixed
            continue

        g_actions = graph_actions[graph_id]
        expected = []
        if hasattr(scen, "expected_actions"):
            expected = scen.expected_actions or []
        elif isinstance(scen, dict):
            expected = scen.get("expected_actions", [])

        if not expected:
            cat_map[sid] = "A"  # no expected → trivially anchored
            continue

        in_graph = sum(1 for a in expected if a in g_actions)
        if in_graph == len(expected):
            cat_map[sid] = "A"
        elif in_graph == 0:
            cat_map[sid] = "B"
        else:
            cat_map[sid] = "M"

    return cat_map


# ─────────────────────────────────────────────────────────────────────
# 2. Bridge number computations
# ─────────────────────────────────────────────────────────────────────


def compute_eta_squared(
    episodes: list[dict],
) -> dict:
    """STEP 1: η² variance decomposition."""
    evaluators = ["dxem", "ac_proxy", "mab_proxy", "c2_pass", "v4_hard"]

    # Build score matrix: each episode gets a "CGA proxy" per evaluator
    # CGA proxy = mean of binary verdicts
    scores = []
    run_labels = []
    eval_labels = []

    for ep in episodes:
        for ev in evaluators:
            val = 1.0 if ep.get(ev, False) else 0.0
            scores.append(val)
            run_labels.append(ep.get("run_index", 0))
            eval_labels.append(ev)

    scores = np.array(scores)
    grand_mean = scores.mean()
    ss_total = np.sum((scores - grand_mean) ** 2)

    if ss_total == 0:
        return {"eta_eval_proxy": 0, "eta_run_proxy": 0, "ratio": 0, "order_preserved": True}

    # SS for evaluator factor
    eval_means = {}
    for ev in evaluators:
        mask = [i for i, e in enumerate(eval_labels) if e == ev]
        eval_means[ev] = np.mean(scores[mask])
    ss_eval = sum(sum(1 for e in eval_labels if e == ev) * (eval_means[ev] - grand_mean) ** 2 for ev in evaluators)

    # SS for run factor
    run_ids = sorted(set(run_labels))
    run_means = {}
    for r in run_ids:
        mask = [i for i, rl in enumerate(run_labels) if rl == r]
        run_means[r] = np.mean(scores[mask])
    ss_run = sum(sum(1 for rl in run_labels if rl == r) * (run_means[r] - grand_mean) ** 2 for r in run_ids)

    eta_eval = ss_eval / ss_total
    eta_run = ss_run / ss_total
    ratio = eta_eval / eta_run if eta_run > 0 else float("inf")

    return {
        "eta_eval_proxy": round(eta_eval, 6),
        "eta_run_proxy": round(eta_run, 6),
        "ratio": round(ratio, 2),
        "order_preserved": eta_eval > eta_run,
    }


def compute_strict_fa(episodes: list[dict]) -> dict:
    """STEP 2: Strict consensus FA rate."""
    three_way_pass = [e for e in episodes if e.get("ac_proxy") and e.get("mab_proxy") and e.get("c2_pass")]
    two_way_pass = [e for e in episodes if e.get("ac_proxy") and e.get("c2_pass")]

    three_fa = sum(1 for e in three_way_pass if e.get("v4_hard"))
    two_fa = sum(1 for e in two_way_pass if e.get("v4_hard"))

    return {
        "strict_3way_pass": len(three_way_pass),
        "strict_3way_fa_count": three_fa,
        "strict_3way_fa_rate_pct": round(100 * three_fa / max(len(three_way_pass), 1), 2),
        "loose_2way_pass": len(two_way_pass),
        "loose_2way_fa_count": two_fa,
        "loose_2way_fa_rate_pct": round(100 * two_fa / max(len(two_way_pass), 1), 2),
    }


def compute_rank_reversal(episodes: list[dict]) -> dict:
    """STEP 3: Pairwise rank reversal across evaluators."""
    evaluators = ["dxem", "ac_proxy", "mab_proxy", "c2_pass", "acov_pass", "v4_hard"]
    models = sorted(set(e.get("model_dir", e.get("model", "")) for e in episodes))

    if len(models) < 2:
        return {"reversal_rate_pct": 0, "kendall_W": 0, "models": len(models)}

    # Per-model per-evaluator mean score
    model_eval_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    model_eval_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for ep in episodes:
        m = ep.get("model_dir", ep.get("model", ""))
        for ev in evaluators:
            val = 1.0 if ep.get(ev, False) else 0.0
            model_eval_scores[m][ev] += val
            model_eval_counts[m][ev] += 1

    # Normalize
    for m in models:
        for ev in evaluators:
            cnt = model_eval_counts[m][ev]
            if cnt > 0:
                model_eval_scores[m][ev] /= cnt

    # Count reversals
    total_pairs = 0
    reversed_pairs = 0
    for ev1, ev2 in combinations(evaluators, 2):
        for m1, m2 in combinations(models, 2):
            s1_ev1 = model_eval_scores[m1][ev1]
            s2_ev1 = model_eval_scores[m2][ev1]
            s1_ev2 = model_eval_scores[m1][ev2]
            s2_ev2 = model_eval_scores[m2][ev2]
            if (s1_ev1 - s2_ev1) * (s1_ev2 - s2_ev2) < 0:
                reversed_pairs += 1
            total_pairs += 1

    # Kendall W
    n_models = len(models)
    k_eval = len(evaluators)
    ranks_matrix = []
    for ev in evaluators:
        scores = [(model_eval_scores[m][ev], m) for m in models]
        scores.sort(reverse=True)
        rank_map = {m: i + 1 for i, (_, m) in enumerate(scores)}
        ranks_matrix.append([rank_map[m] for m in models])

    ranks_np = np.array(ranks_matrix)  # k × n
    R = ranks_np.sum(axis=0)  # sum of ranks per model
    R_bar = R.mean()
    S = np.sum((R - R_bar) ** 2)
    W = 12 * S / (k_eval**2 * (n_models**3 - n_models))

    return {
        "models": n_models,
        "evaluators": k_eval,
        "total_pairs": total_pairs,
        "reversed_pairs": reversed_pairs,
        "reversal_rate_pct": round(100 * reversed_pairs / max(total_pairs, 1), 1),
        "kendall_W": round(W, 4),
    }


def compute_bayes_floor(episodes: list[dict]) -> dict:
    """STEP 4: Bayes error floor magnitude ordering."""
    # Pi-class ground truth mapping
    pi_class = {
        "dxem": "term",
        "ac_proxy": "nctx",
        "mab_proxy": "term",
        "c2_pass": "aset",  # using c2_shim→aset
        "acov_pass": "nctx",
        "v4_hard": "nctx",
    }

    gt_classes = ["term", "aset", "nord", "nctx"]

    # For each gt class, compute cross-prediction error
    # eps* = min over evaluators of error rate when predicting that gt class
    eps_star: dict[str, float] = {}

    for gt in gt_classes:
        # Find evaluators whose pi-class is this gt
        gt_evals = [ev for ev, gc in pi_class.items() if gc == gt]
        if not gt_evals:
            eps_star[gt] = 0.0
            continue

        # Other evaluators predict this gt class
        other_evals = [ev for ev in pi_class if pi_class[ev] != gt]

        min_err = 1.0
        for predictor in pi_class:
            for target in gt_evals:
                # Error = disagreement rate
                disagree = sum(1 for e in episodes if bool(e.get(predictor, False)) != bool(e.get(target, False)))
                err = disagree / max(len(episodes), 1)
                min_err = min(min_err, err)

        eps_star[gt] = round(min_err, 4)

    # Check ordering
    order = sorted(gt_classes, key=lambda g: -eps_star[g])
    order_preserved = eps_star.get("term", 0) >= eps_star.get("aset", 0) >= eps_star.get("nord", 0)

    return {
        "eps_term": eps_star.get("term", 0),
        "eps_aset": eps_star.get("aset", 0),
        "eps_nord": eps_star.get("nord", 0),
        "eps_nctx": eps_star.get("nctx", 0),
        "order_preserved": order_preserved,
    }


def compute_replay_loss(episodes: list[dict]) -> dict:
    """STEP 5: Replay scorer detection loss."""
    # TCC = episodes with v4_hard=True (hard violation present)
    tcc = [e for e in episodes if e.get("v4_hard")]
    n_tcc = len(tcc)
    if n_tcc == 0:
        return {"mab_replay_miss_pct": 0, "ac_replay_miss_pct": 0, "tcc_count": 0}

    # MAB miss: TCC episodes where mab_proxy=True (would have been "passed" despite violation)
    mab_miss = sum(1 for e in tcc if e.get("mab_proxy"))
    ac_miss = sum(1 for e in tcc if e.get("ac_proxy"))
    dxem_miss = sum(1 for e in tcc if e.get("dxem"))

    return {
        "tcc_count": n_tcc,
        "mab_replay_miss_count": mab_miss,
        "mab_replay_miss_pct": round(100 * mab_miss / n_tcc, 1),
        "ac_replay_miss_count": ac_miss,
        "ac_replay_miss_pct": round(100 * ac_miss / n_tcc, 1),
        "dxem_replay_miss_pct": round(100 * dxem_miss / n_tcc, 1),
    }


# ─────────────────────────────────────────────────────────────────────
# 3. Main execution
# ─────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 80)
    print("P0 BRIDGE ANALYSIS: V6 Cat A + V7.3 Cat A")
    print("=" * 80)

    # ── Load data ──
    print("\n[1/6] Loading verdict matrices...")
    with open("evidence_pack/analysis/verdict_matrix_v6_full.json") as f:
        v6_data = json.load(f)
    v6_all = v6_data["per_episode"]
    print(f"  V6 full: {len(v6_all)} episodes")

    with open("evidence_pack/analysis/verdict_matrix_v7_3.json") as f:
        v73_data = json.load(f)
    v73_all = v73_data.get("per_episode", v73_data.get("episodes", []))
    print(f"  V7.3 full: {len(v73_all)} episodes")

    # ── Filter V6 to W8 subset (8 models × 706 × 3 = 16,944) ──
    print("\n[2/6] Filtering V6 to W8 subset...")
    # W8 = the 8 model_dirs used in v6 paper
    v6_models = sorted(set(e["model_dir"] for e in v6_all))
    print(f"  V6 models ({len(v6_models)}): {v6_models}")

    # Use checklist scaffold (the primary one in v6 paper)
    # Filter: keep only episodes matching the 8 canonical models
    w8_models = {"oss120b", "qwen27b", "qwen35b", "qwen4b", "qwen397b", "gemma31b", "nemotron30b", "deepseek_r1_7b"}
    v6_w8 = [e for e in v6_all if e.get("model_dir", "") in w8_models]
    print(f"  V6 W8 filtered: {len(v6_w8)} episodes")

    # If too many (multiple scaffolds), deduplicate by scenario+model+run
    seen = set()
    v6_w8_dedup = []
    for e in v6_w8:
        key = (e["scenario_id"], e["model_dir"], e["run_index"])
        if key not in seen:
            seen.add(key)
            v6_w8_dedup.append(e)
    v6_w8 = v6_w8_dedup
    print(f"  V6 W8 deduped: {len(v6_w8)} episodes")

    # ── Classify scenarios ──
    print("\n[3/6] Classifying scenarios into Cat A/B/M...")
    cat_map = classify_scenarios()
    counts = defaultdict(int)
    for c in cat_map.values():
        counts[c] += 1
    print(f"  Cat A: {counts['A']}, Cat B: {counts['B']}, Cat M: {counts['M']}")

    # Filter episodes
    v6_cat_a = [e for e in v6_w8 if cat_map.get(e["scenario_id"]) == "A"]
    v73_cat_a = [e for e in v73_all if cat_map.get(e["scenario_id"]) == "A"]
    print(f"  V6 Cat A episodes: {len(v6_cat_a)}")
    print(f"  V7.3 Cat A episodes: {len(v73_cat_a)}")

    # ── P0-1: V6 bridge numbers (Full vs Cat A) ──
    print("\n[4/6] Computing V6 bridge numbers...")

    print("  V6 Full:")
    v6_full_eta = compute_eta_squared(v6_w8)
    v6_full_fa = compute_strict_fa(v6_w8)
    v6_full_rev = compute_rank_reversal(v6_w8)
    v6_full_bayes = compute_bayes_floor(v6_w8)
    v6_full_replay = compute_replay_loss(v6_w8)
    print(f"    η²(eval)={v6_full_eta['eta_eval_proxy']}, η²(run)={v6_full_eta['eta_run_proxy']}")
    print(f"    3-way FA={v6_full_fa['strict_3way_fa_rate_pct']}%, 2-way FA={v6_full_fa['loose_2way_fa_rate_pct']}%")
    print(f"    Reversal={v6_full_rev['reversal_rate_pct']}%, W={v6_full_rev['kendall_W']}")
    print(f"    Bayes: term={v6_full_bayes['eps_term']}, aset={v6_full_bayes['eps_aset']}")
    print(f"    Replay MAB={v6_full_replay['mab_replay_miss_pct']}%, AC={v6_full_replay['ac_replay_miss_pct']}%")

    print("  V6 Cat A:")
    v6_a_eta = compute_eta_squared(v6_cat_a)
    v6_a_fa = compute_strict_fa(v6_cat_a)
    v6_a_rev = compute_rank_reversal(v6_cat_a)
    v6_a_bayes = compute_bayes_floor(v6_cat_a)
    v6_a_replay = compute_replay_loss(v6_cat_a)
    print(f"    η²(eval)={v6_a_eta['eta_eval_proxy']}, η²(run)={v6_a_eta['eta_run_proxy']}")
    print(f"    3-way FA={v6_a_fa['strict_3way_fa_rate_pct']}%, 2-way FA={v6_a_fa['loose_2way_fa_rate_pct']}%")
    print(f"    Reversal={v6_a_rev['reversal_rate_pct']}%, W={v6_a_rev['kendall_W']}")
    print(f"    Bayes: term={v6_a_bayes['eps_term']}, aset={v6_a_bayes['eps_aset']}")
    print(f"    Replay MAB={v6_a_replay['mab_replay_miss_pct']}%, AC={v6_a_replay['ac_replay_miss_pct']}%")

    # ── P0-2: V7.3 Cat A mab_proxy ──
    print("\n[5/6] Computing V7.3 Cat A evaluator pass rates...")

    v73_a_mab = sum(1 for e in v73_cat_a if e.get("mab_proxy"))
    v73_a_ac = sum(1 for e in v73_cat_a if e.get("ac_proxy"))
    v73_a_c2 = sum(1 for e in v73_cat_a if e.get("c2_pass"))
    v73_a_n = len(v73_cat_a) or 1

    v73_all_mab = sum(1 for e in v73_all if e.get("mab_proxy"))
    v73_all_ac = sum(1 for e in v73_all if e.get("ac_proxy"))
    v73_all_c2 = sum(1 for e in v73_all if e.get("c2_pass"))
    v73_all_n = len(v73_all) or 1

    print(
        f"  V7.3 Full: mab={100 * v73_all_mab / v73_all_n:.2f}%, ac={100 * v73_all_ac / v73_all_n:.2f}%, c2={100 * v73_all_c2 / v73_all_n:.2f}%"
    )
    print(
        f"  V7.3 Cat A: mab={100 * v73_a_mab / v73_a_n:.2f}%, ac={100 * v73_a_ac / v73_a_n:.2f}%, c2={100 * v73_a_c2 / v73_a_n:.2f}%"
    )

    # V7.3 Cat A bridge numbers
    print("\n  V7.3 Cat A bridge numbers:")
    v73_a_eta = compute_eta_squared(v73_cat_a)
    v73_a_fa = compute_strict_fa(v73_cat_a)
    v73_a_rev = compute_rank_reversal(v73_cat_a)
    v73_a_bayes = compute_bayes_floor(v73_cat_a)
    v73_a_replay = compute_replay_loss(v73_cat_a)
    print(f"    η²(eval)={v73_a_eta['eta_eval_proxy']}, η²(run)={v73_a_eta['eta_run_proxy']}")
    print(f"    3-way FA={v73_a_fa['strict_3way_fa_rate_pct']}%, 2-way FA={v73_a_fa['loose_2way_fa_rate_pct']}%")
    print(f"    Reversal={v73_a_rev['reversal_rate_pct']}%, W={v73_a_rev['kendall_W']}")
    print(f"    Bayes: term={v73_a_bayes['eps_term']}, aset={v73_a_bayes['eps_aset']}")
    print(f"    Replay MAB={v73_a_replay['mab_replay_miss_pct']}%, AC={v73_a_replay['ac_replay_miss_pct']}%")

    # ── Save outputs ──
    print("\n[6/6] Saving outputs...")

    out_dir = Path("reports/path_d_day3")
    out_dir.mkdir(parents=True, exist_ok=True)

    # V6 Cat A bridge
    v6_cat_a_result = {
        "corpus": "v6_w8_cat_a",
        "n_episodes": len(v6_cat_a),
        "n_scenarios_cat_a": counts["A"],
        "eta": v6_a_eta,
        "fa": v6_a_fa,
        "reversal": v6_a_rev,
        "bayes": v6_a_bayes,
        "replay": v6_a_replay,
    }
    with open(out_dir / "v6_cat_a_bridge.json", "w") as f:
        json.dump(v6_cat_a_result, f, indent=2, cls=NumpyEncoder)

    # V6 Full bridge (recomputed with our code for consistency)
    v6_full_result = {
        "corpus": "v6_w8_full",
        "n_episodes": len(v6_w8),
        "eta": v6_full_eta,
        "fa": v6_full_fa,
        "reversal": v6_full_rev,
        "bayes": v6_full_bayes,
        "replay": v6_full_replay,
    }
    with open(out_dir / "v6_full_bridge_recomputed.json", "w") as f:
        json.dump(v6_full_result, f, indent=2, cls=NumpyEncoder)

    # V7.3 Cat A mab analysis
    v73_cat_a_result = {
        "corpus": "v7.3_cat_a",
        "n_episodes": len(v73_cat_a),
        "mab_proxy_true": v73_a_mab,
        "mab_proxy_pct": round(100 * v73_a_mab / v73_a_n, 2),
        "ac_proxy_true": v73_a_ac,
        "ac_proxy_pct": round(100 * v73_a_ac / v73_a_n, 2),
        "c2_pass_true": v73_a_c2,
        "c2_pass_pct": round(100 * v73_a_c2 / v73_a_n, 2),
        "eta": v73_a_eta,
        "fa": v73_a_fa,
        "reversal": v73_a_rev,
        "bayes": v73_a_bayes,
        "replay": v73_a_replay,
    }
    with open(out_dir / "v73_cat_a_mab_analysis.json", "w") as f:
        json.dump(v73_cat_a_result, f, indent=2, cls=NumpyEncoder)

    # Comparison matrix
    matrix = {
        "comparison": "v6_full vs v6_cat_a vs v7.3_full vs v7.3_cat_a",
        "episode_counts": {
            "v6_full": len(v6_w8),
            "v6_cat_a": len(v6_cat_a),
            "v7.3_full": len(v73_all),
            "v7.3_cat_a": len(v73_cat_a),
        },
        "eta_eval": {
            "v6_full": v6_full_eta["eta_eval_proxy"],
            "v6_cat_a": v6_a_eta["eta_eval_proxy"],
            "v7.3_full": 0.2491,  # from earlier STEP 1
            "v7.3_cat_a": v73_a_eta["eta_eval_proxy"],
        },
        "eta_run": {
            "v6_full": v6_full_eta["eta_run_proxy"],
            "v6_cat_a": v6_a_eta["eta_run_proxy"],
            "v7.3_full": 0.0175,
            "v7.3_cat_a": v73_a_eta["eta_run_proxy"],
        },
        "strict_3way_fa_pct": {
            "v6_full": v6_full_fa["strict_3way_fa_rate_pct"],
            "v6_cat_a": v6_a_fa["strict_3way_fa_rate_pct"],
            "v7.3_full": 0.0,
            "v7.3_cat_a": v73_a_fa["strict_3way_fa_rate_pct"],
        },
        "loose_2way_fa_pct": {
            "v6_full": v6_full_fa["loose_2way_fa_rate_pct"],
            "v6_cat_a": v6_a_fa["loose_2way_fa_rate_pct"],
            "v7.3_full": 5.35,
            "v7.3_cat_a": v73_a_fa["loose_2way_fa_rate_pct"],
        },
        "reversal_pct": {
            "v6_full": v6_full_rev["reversal_rate_pct"],
            "v6_cat_a": v6_a_rev["reversal_rate_pct"],
            "v7.3_full": 34.3,
            "v7.3_cat_a": v73_a_rev["reversal_rate_pct"],
        },
        "kendall_W": {
            "v6_full": v6_full_rev["kendall_W"],
            "v6_cat_a": v6_a_rev["kendall_W"],
            "v7.3_full": 0.418,
            "v7.3_cat_a": v73_a_rev["kendall_W"],
        },
        "eps_term": {
            "v6_full": v6_full_bayes["eps_term"],
            "v6_cat_a": v6_a_bayes["eps_term"],
            "v7.3_full": 0.2999,
            "v7.3_cat_a": v73_a_bayes["eps_term"],
        },
        "mab_replay_miss_pct": {
            "v6_full": v6_full_replay["mab_replay_miss_pct"],
            "v6_cat_a": v6_a_replay["mab_replay_miss_pct"],
            "v7.3_full": 0.0,
            "v7.3_cat_a": v73_a_replay["mab_replay_miss_pct"],
        },
        "ac_replay_miss_pct": {
            "v6_full": v6_full_replay["ac_replay_miss_pct"],
            "v6_cat_a": v6_a_replay["ac_replay_miss_pct"],
            "v7.3_full": 16.9,
            "v7.3_cat_a": v73_a_replay["ac_replay_miss_pct"],
        },
        "mab_proxy_pass_pct": {
            "v6_full": round(100 * sum(1 for e in v6_w8 if e.get("mab_proxy")) / max(len(v6_w8), 1), 2),
            "v6_cat_a": round(100 * sum(1 for e in v6_cat_a if e.get("mab_proxy")) / max(len(v6_cat_a), 1), 2),
            "v7.3_full": round(100 * v73_all_mab / v73_all_n, 2),
            "v7.3_cat_a": round(100 * v73_a_mab / v73_a_n, 2),
        },
    }
    with open(out_dir / "p0_bridge_comparison_matrix.json", "w") as f:
        json.dump(matrix, f, indent=2, cls=NumpyEncoder)

    # LaTeX macros
    macros = [
        "% V6 Cat A Bridge Macros (P0-1)",
        f"\\providecommand{{\\vSixCatAEpisodes}}{{{len(v6_cat_a)}}}",
        f"\\providecommand{{\\vSixCatAEtaEval}}{{{v6_a_eta['eta_eval_proxy']:.4f}}}",
        f"\\providecommand{{\\vSixCatAEtaRun}}{{{v6_a_eta['eta_run_proxy']:.4f}}}",
        f"\\providecommand{{\\vSixCatAStrictFA}}{{{v6_a_fa['strict_3way_fa_rate_pct']:.2f}}}",
        f"\\providecommand{{\\vSixCatALooseFA}}{{{v6_a_fa['loose_2way_fa_rate_pct']:.2f}}}",
        f"\\providecommand{{\\vSixCatAReversal}}{{{v6_a_rev['reversal_rate_pct']:.1f}}}",
        f"\\providecommand{{\\vSixCatAKendallW}}{{{v6_a_rev['kendall_W']:.4f}}}",
        f"\\providecommand{{\\vSixCatAEpsTerm}}{{{v6_a_bayes['eps_term']:.4f}}}",
        f"\\providecommand{{\\vSixCatAEpsAset}}{{{v6_a_bayes['eps_aset']:.4f}}}",
        f"\\providecommand{{\\vSixCatAMabMiss}}{{{v6_a_replay['mab_replay_miss_pct']:.1f}}}",
        f"\\providecommand{{\\vSixCatAAcMiss}}{{{v6_a_replay['ac_replay_miss_pct']:.1f}}}",
        "",
        "% V6 Full Bridge Macros (recomputed)",
        f"\\providecommand{{\\vSixFullEpisodes}}{{{len(v6_w8)}}}",
        f"\\providecommand{{\\vSixFullEtaEval}}{{{v6_full_eta['eta_eval_proxy']:.4f}}}",
        f"\\providecommand{{\\vSixFullStrictFA}}{{{v6_full_fa['strict_3way_fa_rate_pct']:.2f}}}",
        f"\\providecommand{{\\vSixFullReversal}}{{{v6_full_rev['reversal_rate_pct']:.1f}}}",
        f"\\providecommand{{\\vSixFullMabMiss}}{{{v6_full_replay['mab_replay_miss_pct']:.1f}}}",
        f"\\providecommand{{\\vSixFullAcMiss}}{{{v6_full_replay['ac_replay_miss_pct']:.1f}}}",
        f"\\providecommand{{\\vSixFullMabPassPct}}{{{matrix['mab_proxy_pass_pct']['v6_full']:.1f}}}",
        "",
        "% V7.3 Cat A Bridge Macros",
        f"\\providecommand{{\\vSevenThreeCatAEpisodes}}{{{len(v73_cat_a)}}}",
        f"\\providecommand{{\\vSevenThreeCatAMabPassPct}}{{{matrix['mab_proxy_pass_pct']['v7.3_cat_a']:.2f}}}",
        f"\\providecommand{{\\vSevenThreeCatAEtaEval}}{{{v73_a_eta['eta_eval_proxy']:.4f}}}",
        f"\\providecommand{{\\vSevenThreeCatAStrictFA}}{{{v73_a_fa['strict_3way_fa_rate_pct']:.2f}}}",
        f"\\providecommand{{\\vSevenThreeCatAReversal}}{{{v73_a_rev['reversal_rate_pct']:.1f}}}",
        f"\\providecommand{{\\vSevenThreeCatAMabMiss}}{{{v73_a_replay['mab_replay_miss_pct']:.1f}}}",
        f"\\providecommand{{\\vSevenThreeCatAAcMiss}}{{{v73_a_replay['ac_replay_miss_pct']:.1f}}}",
    ]
    with open("paper/auto_numbers_v6_cat_a_bridge.tex", "w") as f:
        f.write("\n".join(macros) + "\n")

    # ── Print comparison matrix ──
    print("\n" + "=" * 100)
    print("COMPARISON MATRIX: v6 Full / v6 Cat A / v7.3 Full / v7.3 Cat A")
    print("=" * 100)
    header = f"{'Metric':<30} {'v6 Full':>12} {'v6 Cat A':>12} {'v7.3 Full':>12} {'v7.3 Cat A':>12}"
    print(header)
    print("-" * 100)

    rows = [
        ("Episodes", "episode_counts"),
        ("η²(eval)", "eta_eval"),
        ("η²(run)", "eta_run"),
        ("3-way FA %", "strict_3way_fa_pct"),
        ("2-way FA %", "loose_2way_fa_pct"),
        ("Reversal %", "reversal_pct"),
        ("Kendall W", "kendall_W"),
        ("ε* term", "eps_term"),
        ("MAB replay miss %", "mab_replay_miss_pct"),
        ("AC replay miss %", "ac_replay_miss_pct"),
        ("mab_proxy pass %", "mab_proxy_pass_pct"),
    ]
    for label, key in rows:
        vals = matrix[key]
        v6f = vals.get("v6_full", "—")
        v6a = vals.get("v6_cat_a", "—")
        v73f = vals.get("v7.3_full", "—")
        v73a = vals.get("v7.3_cat_a", "—")
        print(f"{label:<30} {v6f!s:>12} {v6a!s:>12} {v73f!s:>12} {v73a!s:>12}")

    # ── Decision analysis ──
    print("\n" + "=" * 80)
    print("DECISION ANALYSIS")
    print("=" * 80)

    # Delta between v6 Full and v6 Cat A
    delta_eta = abs(v6_full_eta["eta_eval_proxy"] - v6_a_eta["eta_eval_proxy"])
    delta_fa = abs(v6_full_fa["strict_3way_fa_rate_pct"] - v6_a_fa["strict_3way_fa_rate_pct"])
    delta_rev = abs(v6_full_rev["reversal_rate_pct"] - v6_a_rev["reversal_rate_pct"])
    delta_mab = abs(v6_full_replay["mab_replay_miss_pct"] - v6_a_replay["mab_replay_miss_pct"])

    print("\nV6 Full vs Cat A deltas:")
    print(f"  Δη²(eval): {delta_eta:.4f}")
    print(f"  Δ3-way FA: {delta_fa:.2f}pp")
    print(f"  ΔReversal: {delta_rev:.1f}pp")
    print(f"  ΔMAB miss: {delta_mab:.1f}pp")

    small_threshold = 3.0  # pp
    if all(d < small_threshold for d in [delta_fa, delta_rev, delta_mab]) and delta_eta < 0.03:
        print("\n→ V6 Cat A ≈ V6 Full: Paper headline integrity PRESERVED")
        print("  B6 orphans are measurement noise level in V6")
    else:
        print("\n→ V6 Cat A ≠ V6 Full: Paper §5.3 disclosure NEEDED")
        if delta_fa >= small_threshold:
            print(f"  FA delta {delta_fa:.2f}pp exceeds threshold")
        if delta_rev >= small_threshold:
            print(f"  Reversal delta {delta_rev:.1f}pp exceeds threshold")

    # V7.3 Cat A mab decision
    v73_a_mab_pct = 100 * v73_a_mab / v73_a_n
    print(f"\nV7.3 Cat A mab_proxy pass rate: {v73_a_mab_pct:.2f}%")
    if v73_a_mab_pct >= 30:
        print("→ Cat A mab ~30%+: 3-way consensus VIABLE, Option B unnecessary")
    elif v73_a_mab_pct >= 5:
        print("→ Cat A mab 5-30%: 3-way consensus MARGINAL, consider Option B")
    else:
        print("→ Cat A mab < 5%: SGSC mandatory inflation confirmed, Option B justified")

    print("\nDone. Outputs:")
    print("  reports/path_d_day3/v6_cat_a_bridge.json")
    print("  reports/path_d_day3/v6_full_bridge_recomputed.json")
    print("  reports/path_d_day3/v73_cat_a_mab_analysis.json")
    print("  reports/path_d_day3/p0_bridge_comparison_matrix.json")
    print("  paper/auto_numbers_v6_cat_a_bridge.tex")


if __name__ == "__main__":
    main()
