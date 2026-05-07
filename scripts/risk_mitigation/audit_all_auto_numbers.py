#!/usr/bin/env python3
"""auto_numbers.tex 전수 검증
===========================
모든 매크로 값을 raw data에서 재계산하고 기존 값과 대조.

3단계 검증:
  Level A: Raw에서 직접 재계산 가능 → 불일치 시 🔴
  Level B: 다른 매크로에서 산술 도출 → 불일치 시 🟡
  Level C: Old data(180 ep) 또는 외부 의존 → 검증 불가, 🔵 표시

Usage:
    python audit_all_auto_numbers.py \
        --auto-numbers paper/auto_numbers.tex \
        --episodes-dir results/full_706_v5 \
        --graphs-dir cpg_model/graphs \
        [--output-dir evidence_pack/auto_numbers_audit]
"""

import argparse
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
import re

import numpy as np
import yaml

# ═══════════════════════════════════════════════════════════════════
# PARSE auto_numbers.tex
# ═══════════════════════════════════════════════════════════════════


def parse_auto_numbers(path):
    """auto_numbers.tex에서 모든 \newcommand 파싱"""
    macros = {}
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            # Match \newcommand{\name}{value}
            m = re.match(r"\\(?:new|renew)command\{\\(\w+)\}\{([^}]*)\}", line.strip())
            if m:
                name = m.group(1)
                value = m.group(2)
                comment = ""
                # Extract comment
                cm = re.search(r"%\s*(.*)", line)
                if cm:
                    comment = cm.group(1).strip()
                macros[name] = {
                    "value": value,
                    "line": line_num,
                    "comment": comment,
                }
    return macros


# ═══════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════


def load_episodes(episodes_dir):
    episodes = []
    ep_dir = Path(episodes_dir)
    if not ep_dir.exists():
        return []
    for model_dir in sorted(ep_dir.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                ep["_model"] = model_dir.name
                episodes.append(ep)
            except:
                pass
    return episodes


def load_graphs(graphs_dir):
    graphs = {}
    gdir = Path(graphs_dir)
    if not gdir.exists():
        return {}
    for f in sorted(gdir.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        try:
            with open(f) as fh:
                graphs[f.stem] = yaml.safe_load(fh)
        except:
            pass
    return graphs


def get_action_name(a):
    if isinstance(a, str):
        return a.lower().strip()
    if isinstance(a, dict):
        return a.get("action_id", a.get("action", a.get("name", str(a)))).lower().strip()
    return str(a).lower().strip()


def compute_verdicts(ep):
    """Evaluator verdicts 계산"""
    performed = set()
    for a in ep.get("actions", []):
        n = get_action_name(a)
        if n:
            performed.add(n)

    expected = set()
    for a in ep.get("expected_actions", ep.get("mandatory_actions", [])):
        n = get_action_name(a)
        if n:
            expected.add(n)

    violations = ep.get("violation_events", [])
    has_hard = bool(violations) if isinstance(violations, list) else False
    if not has_hard and ep.get("compliance_score", 1.0) < 1.0:
        has_hard = True

    coverage = len(performed & expected) / len(expected) if expected else 1.0

    return {
        "TOM": True,
        "ASC": coverage >= 0.5,
        "CwT": coverage >= 0.7,
        "PAF": coverage >= 0.5,
        "TCC": not has_hard,
        "_coverage": coverage,
        "_n_violations": len(violations) if isinstance(violations, list) else 0,
    }


# ═══════════════════════════════════════════════════════════════════
# VERIFICATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════


def verify_system_numbers(macros, graphs):
    """Episode-independent system numbers from graph YAMLs"""
    results = {}

    # Count graphs
    main_graphs = [
        g
        for g in graphs
        if not any(
            h in g for h in ["aba_burn", "aabb_transfusion", "acog_obstetric", "pals_pediatric", "apa_agitation"]
        )
    ]
    heldout_graphs = [g for g in graphs if g not in main_graphs]

    results["numGraphsMain"] = len(main_graphs)
    results["numGraphsHeldout"] = len(heldout_graphs)
    results["numGraphsTotal"] = len(graphs)
    results["numDomains"] = len(graphs)

    # Count nodes
    total_nodes = 0
    for gid, graph in graphs.items():
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        total_nodes += len([n for n in nodes if isinstance(n, dict)])
    results["numNodes"] = total_nodes

    # Count conditional rules
    total_rules = 0
    for gid, graph in graphs.items():
        rules = graph.get("conditional_rules", [])
        if isinstance(rules, list):
            total_rules += len(rules)
    results["numConditionalRules"] = total_rules

    # Count constraints by type
    counts = Counter()
    for gid, graph in graphs.items():
        nodes = graph.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for field in ["mandatory_actions", "expected_actions", "required_actions"]:
                acts = node.get(field, [])
                if isinstance(acts, list):
                    counts["MUST"] += len(acts)
            for field in ["forbidden_actions", "prohibited_actions"]:
                acts = node.get(field, [])
                if isinstance(acts, list):
                    counts["FORBIDDEN"] += len(acts)
            deadlines = node.get("deadlines", [])
            if isinstance(deadlines, list) or isinstance(deadlines, dict):
                counts["WITHIN"] += len(deadlines)
            seq = node.get("sequence_rules", [])
            if isinstance(seq, list):
                counts["BEFORE"] += len(seq)

    results["numForbidden"] = counts["FORBIDDEN"]
    results["numMust"] = counts["MUST"]
    results["numBefore"] = counts["BEFORE"]
    results["numWithin"] = counts["WITHIN"]
    results["numHardConstraints"] = sum(counts.values())

    return results


def verify_verdict_stats(macros, episodes):
    """E1/E2 verdict-related macros from episodes"""
    results = {}
    n = len(episodes)
    results["numEpisodes"] = n

    all_verdicts = []
    for ep in episodes:
        v = compute_verdicts(ep)
        v["_model"] = ep.get("_model", "unknown")
        v["_scenario"] = ep.get("scenario_id", "")
        all_verdicts.append(v)

    evaluators = ["TOM", "ASC", "CwT", "PAF", "TCC"]

    # Pass rates
    for ev in evaluators:
        n_pass = sum(1 for v in all_verdicts if v[ev])
        macro_map = {
            "TOM": "passrateDxEM",
            "ASC": "passtrateACProxy",
            "CwT": "passrateCTwo",
            "PAF": "passtrateMABProxy",
            "TCC": "passrateCGABench",
        }
        results[macro_map[ev]] = round(n_pass / n * 100, 1)

    # FA rates
    fa_map = {"TOM": "bsrDxEM", "ASC": "bsrAC", "CwT": "bsrCTwo", "PAF": "bsrMAB"}
    for ev, macro in fa_map.items():
        n_fa = sum(1 for v in all_verdicts if v[ev] and not v["TCC"])
        results[macro] = round(n_fa / n * 100, 1)

    # FA counts
    fa_count_map = {"TOM": "bsrNDxEM", "ASC": "bsrNAC", "CwT": "bsrNCTwo", "PAF": "bsrNMAB"}
    for ev, macro in fa_count_map.items():
        results[macro] = sum(1 for v in all_verdicts if v[ev] and not v["TCC"])

    # All-oblivious FA
    n_all_fa = sum(1 for v in all_verdicts if v["TOM"] and v["ASC"] and v["CwT"] and not v["TCC"])
    results["faAllOblivious"] = round(n_all_fa / n * 100, 1)
    results["faAllObliviousCount"] = n_all_fa

    # Verdict-flip
    n_flip = 0
    for v in all_verdicts:
        for e1, e2 in combinations(evaluators, 2):
            if v[e1] != v[e2]:
                n_flip += 1
                break
    results["verdictFlipRate"] = round(n_flip / n * 100, 1)
    results["verdictFlipCount"] = n_flip

    # Pairwise disagreement
    pair_keys = {
        ("ASC", "TCC"): ("vfACvsCGA", "vfACvsCGAPct"),
        ("ASC", "CwT"): ("vfACvsCTwo", "vfACvsCTwoPct"),
        ("ASC", "PAF"): ("vfACvsMAB", "vfACvsMABPct"),
        ("PAF", "TCC"): ("vfMABvsCGA", "vfMABvsCGAPct"),
        ("PAF", "CwT"): ("vfMABvsCTwo", "vfMABvsCTwoPct"),
        ("CwT", "TCC"): ("vfCTwovsCGA", "vfCTwovsCGAPct"),
    }
    for (e1, e2), (count_macro, pct_macro) in pair_keys.items():
        n_dis = sum(1 for v in all_verdicts if v[e1] != v[e2])
        results[count_macro] = n_dis
        results[pct_macro] = round(n_dis / n * 100, 1)

    # BSR conditional
    bsr_cond_map = {"TOM": "bsrCondDxEM", "ASC": "bsrCondAC", "CwT": "bsrCondCTwo", "PAF": "bsrCondMAB"}
    for ev, macro in bsr_cond_map.items():
        n_pass = sum(1 for v in all_verdicts if v[ev])
        n_fa = sum(1 for v in all_verdicts if v[ev] and not v["TCC"])
        results[macro] = round(n_fa / n_pass * 100, 1) if n_pass > 0 else 0.0

    return results


def verify_variance(macros, episodes):
    """η² verification"""
    results = {}
    evaluators = ["ASC", "CwT", "PAF", "TCC"]

    data = []
    for ep in episodes:
        v = compute_verdicts(ep)
        run = ep.get("run_index", ep.get("run", ep.get("run_id", 0)))
        for ev in evaluators:
            data.append(
                {
                    "verdict": 1 if v[ev] else 0,
                    "evaluator": ev,
                    "run": run,
                }
            )

    verdicts = np.array([d["verdict"] for d in data])
    grand_mean = verdicts.mean()
    ss_total = np.sum((verdicts - grand_mean) ** 2)

    # SS_evaluator
    eval_means = {}
    for ev in evaluators:
        ev_v = [d["verdict"] for d in data if d["evaluator"] == ev]
        eval_means[ev] = np.mean(ev_v)

    ss_eval = sum(
        sum(1 for d in data if d["evaluator"] == ev) * (eval_means[ev] - grand_mean) ** 2 for ev in evaluators
    )

    # SS_run
    runs = sorted(set(d["run"] for d in data))
    run_means = {}
    for r in runs:
        r_v = [d["verdict"] for d in data if d["run"] == r]
        run_means[r] = np.mean(r_v)

    ss_run = sum(sum(1 for d in data if d["run"] == r) * (run_means[r] - grand_mean) ** 2 for r in runs)

    eta_eval = ss_eval / ss_total if ss_total > 0 else 0
    eta_run = ss_run / ss_total if ss_total > 0 else 0
    eta_ratio = eta_eval / eta_run if eta_run > 0 else float("inf")

    results["etaEvaluator"] = round(eta_eval, 4)
    results["etaRun"] = round(eta_run, 6)
    results["etaRatio"] = round(eta_ratio, 1) if eta_ratio < 100000 else int(eta_ratio)

    results["_debug_ss_total"] = round(ss_total, 2)
    results["_debug_ss_eval"] = round(ss_eval, 2)
    results["_debug_ss_run"] = round(ss_run, 2)
    results["_debug_eval_means"] = {ev: round(m, 4) for ev, m in eval_means.items()}
    results["_debug_run_means"] = {str(r): round(m, 4) for r, m in run_means.items()}

    return results


def verify_ranking(macros, episodes):
    """Friedman + ranking verification"""
    results = {}
    evaluators = ["ASC", "CwT", "PAF", "TCC"]

    # Model pass rates per evaluator
    model_eval = defaultdict(lambda: defaultdict(lambda: {"pass": 0, "total": 0}))
    for ep in episodes:
        model = ep.get("_model", "unknown")
        v = compute_verdicts(ep)
        for ev in evaluators:
            model_eval[model][ev]["total"] += 1
            if v[ev]:
                model_eval[model][ev]["pass"] += 1

    models = sorted(model_eval.keys())

    # Pass rate matrix
    pr_matrix = np.zeros((len(models), len(evaluators)))
    for i, m in enumerate(models):
        for j, ev in enumerate(evaluators):
            d = model_eval[m][ev]
            pr_matrix[i, j] = d["pass"] / d["total"] if d["total"] > 0 else 0

    # Rank matrix (per evaluator column, rank models by pass rate, 1=best)
    rank_matrix = np.zeros_like(pr_matrix)
    for j in range(len(evaluators)):
        order = np.argsort(-pr_matrix[:, j])
        for rank_val, idx in enumerate(order):
            rank_matrix[idx, j] = rank_val + 1

    # Friedman on PASS RATES (not ranks!)
    try:
        from scipy.stats import friedmanchisquare

        result = friedmanchisquare(*[pr_matrix[:, j] for j in range(len(evaluators))])
        results["friedmanChi"] = round(result.statistic, 1)
        results["friedmanP"] = f"{result.pvalue:.6f}" if result.pvalue > 0.0001 else "<0.001"
    except ImportError:
        results["friedmanChi"] = "??_scipy_missing"
        results["friedmanP"] = "??_scipy_missing"

    # Kendall's W on PASS RATES
    # W = 12 * sum((R_j - R_mean)^2) / (k^2 * n * (n^2 - 1))
    # But this should be computed on ranks, not rates
    # Actually Kendall's W measures agreement of rankings
    n_models = len(models)
    k_evals = len(evaluators)
    R_j = rank_matrix.sum(axis=0)
    R_mean = R_j.mean()
    W = (12 * np.sum((R_j - R_mean) ** 2)) / (n_models**2 * k_evals * (k_evals**2 - 1))
    # Note: standard Kendall's W formula: 12*S / (k^2 * n * (n^2 - 1))
    # where S = sum of squared deviations of rank sums from mean
    # k = number of judges (evaluators), n = number of objects (models)
    # Actually the formula is: W = 12*S / (k^2 * n * (n^2 - 1))
    # where S = Σ(R_j - R̄)² and R_j = sum of ranks for model j across evaluators
    # k = evaluators, n = models
    R_model = rank_matrix.sum(axis=1)  # sum of ranks per model across evaluators
    R_model_mean = R_model.mean()
    S = np.sum((R_model - R_model_mean) ** 2)
    W_correct = (12 * S) / (k_evals**2 * n_models * (n_models**2 - 1))
    results["kendallW"] = round(W_correct, 3)

    # Reversal rate
    n_pairs = 0
    n_reversals = 0
    for i, j_idx in combinations(range(n_models), 2):
        n_pairs += 1
        has_reversal = False
        for e1, e2 in combinations(range(k_evals), 2):
            if (rank_matrix[i, e1] < rank_matrix[j_idx, e1] and rank_matrix[i, e2] > rank_matrix[j_idx, e2]) or (
                rank_matrix[i, e1] > rank_matrix[j_idx, e1] and rank_matrix[i, e2] < rank_matrix[j_idx, e2]
            ):
                has_reversal = True
                break
        if has_reversal:
            n_reversals += 1
    results["reversalRate"] = round(n_reversals / n_pairs * 100, 1) if n_pairs > 0 else 0

    # Top-1 flip
    top1 = set()
    for j in range(k_evals):
        best_idx = np.argmin(rank_matrix[:, j])
        top1.add(models[best_idx])
    results["topOneFlip"] = "yes" if len(top1) > 1 else "no"

    # Debug info
    results["_debug_models"] = models
    results["_debug_pass_rates"] = {
        m: {ev: round(pr_matrix[i, j] * 100, 1) for j, ev in enumerate(evaluators)} for i, m in enumerate(models)
    }
    results["_debug_ranks"] = {
        m: {ev: int(rank_matrix[i, j]) for j, ev in enumerate(evaluators)} for i, m in enumerate(models)
    }

    return results


def verify_engine_vs_manual(macros, episodes):
    """E7 engine vs manual"""
    results = {}

    manual_eps = []
    auto_eps = []
    for ep in episodes:
        sid = ep.get("scenario_id", "")
        is_auto = any(
            marker in sid for marker in ["_combo_", "_pathway_", "_trap_", "_single_trigger_", "_value_", "_time_sin_"]
        )
        if is_auto:
            auto_eps.append(ep)
        else:
            manual_eps.append(ep)

    for source, eps, prefix in [("manual", manual_eps, "Manual"), ("auto", auto_eps, "Auto")]:
        if not eps:
            continue
        verdicts = [compute_verdicts(ep) for ep in eps]
        n = len(eps)

        # Verdict-flip
        n_flip = 0
        evaluators = ["TOM", "ASC", "CwT", "PAF", "TCC"]
        for v in verdicts:
            for e1, e2 in combinations(evaluators, 2):
                if v[e1] != v[e2]:
                    n_flip += 1
                    break

        macro_vf = "vfManual" if source == "manual" else "vfAuto"
        results[macro_vf] = round(n_flip / n * 100, 1)

        # BSR(ASC)
        n_bsr = sum(1 for v in verdicts if v["ASC"] and not v["TCC"])
        macro_bsr = "bsrManualAC" if source == "manual" else "bsrAutoAC"
        results[macro_bsr] = round(n_bsr / n * 100, 1)

        # Mean violations
        viols = [v["_n_violations"] for v in verdicts]
        macro_viol = "violManual" if source == "manual" else "violAuto"
        results[macro_viol] = round(np.mean(viols), 1)

    return results


def verify_timing(macros, episodes):
    """Timing audit verification"""
    results = {}

    within_violations = []
    for ep in episodes:
        violations = ep.get("violation_events", [])
        if not isinstance(violations, list):
            continue
        for v in violations:
            if not isinstance(v, dict):
                continue
            vtype = v.get("violation_type", v.get("type", "")).upper()
            if "WITHIN" in vtype or "TIMING" in vtype:
                margin = v.get("margin", v.get("delay", v.get("minutes_past", None)))
                if margin is not None and isinstance(margin, (int, float)):
                    within_violations.append(margin)

    if within_violations:
        results["timingNWithinViols"] = len(within_violations)
        results["timingMeanMargin"] = round(np.mean(within_violations), 1)
        results["timingMedianMargin"] = round(np.median(within_violations), 1)
        results["timingPctBoundary"] = round(
            sum(1 for m in within_violations if m <= 5) / len(within_violations) * 100, 1
        )
        results["timingPctOver60"] = round(
            sum(1 for m in within_violations if m > 60) / len(within_violations) * 100, 1
        )
    else:
        results["_timing_note"] = "No margin data in violation_events"

    return results


def verify_arithmetic(macros):
    """매크로 간 산술 일관성 검증"""
    issues = []

    def get_num(name):
        v = macros.get(name, {}).get("value", "??")
        try:
            return float(v)
        except:
            return None

    # numHardConstraints = numForbidden + numMust + numBefore + numWithin
    f, m, b, w = get_num("numForbidden"), get_num("numMust"), get_num("numBefore"), get_num("numWithin")
    h = get_num("numHardConstraints")
    if all(x is not None for x in [f, m, b, w, h]):
        expected = f + m + b + w
        if abs(expected - h) > 0.1:
            issues.append(f"numHardConstraints: {h} ≠ {f}+{m}+{b}+{w} = {expected}")

    # numTotalScenarios = numManualScenarios + numAutoScenarios
    man, auto, total = get_num("numManualScenarios"), get_num("numAutoScenarios"), get_num("numTotalScenarios")
    if all(x is not None for x in [man, auto, total]):
        if abs(man + auto - total) > 0.1:
            issues.append(f"numTotalScenarios: {total} ≠ {man}+{auto} = {man + auto}")

    # expansionRatio = avgEngineConstraints / avgManualConstraints
    avg_e, avg_m, ratio = get_num("avgEngineConstraints"), get_num("avgManualConstraints"), get_num("expansionRatio")
    if all(x is not None for x in [avg_e, avg_m, ratio]) and avg_m > 0:
        expected_ratio = round(avg_e / avg_m, 1)
        if abs(expected_ratio - ratio) > 0.2:
            issues.append(f"expansionRatio: {ratio} ≠ {avg_e}/{avg_m} = {expected_ratio}")

    # FA counts vs rates
    n_ep = get_num("numEpisodes")
    if n_ep:
        for ev, rate_m, count_m in [
            ("AC", "faAC", "faNAC"),
            ("CTwo", "faCTwo", "faNCTwo"),
            ("MAB", "faMAB", "faNMAB"),
        ]:
            rate = get_num(rate_m)
            count = get_num(count_m)
            if rate is not None and count is not None:
                expected_rate = round(count / n_ep * 100, 1)
                if abs(expected_rate - rate) > 1.0:
                    issues.append(f"{rate_m}: {rate}% but {count_m}/{n_ep} = {expected_rate}%")

    return issues


# ═══════════════════════════════════════════════════════════════════
# MAIN AUDIT
# ═══════════════════════════════════════════════════════════════════


def run_audit(macros, episodes, graphs, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("=" * 80)
    lines.append("auto_numbers.tex 전수 검증 보고서")
    lines.append(f"매크로 수: {len(macros)}")
    lines.append(f"에피소드 수: {len(episodes)}")
    lines.append(f"그래프 수: {len(graphs)}")
    lines.append("=" * 80)

    all_discrepancies = []

    def compare(category, computed, level="A"):
        """Computed dict를 macros와 비교"""
        cat_issues = []
        for macro_name, computed_value in sorted(computed.items()):
            if macro_name.startswith("_"):
                continue  # debug info
            if macro_name not in macros:
                continue  # macro not in file

            stated = macros[macro_name]["value"]
            if stated == "??":
                continue  # placeholder

            # Compare
            try:
                stated_num = float(stated.replace("<", "").replace(">", ""))
                if isinstance(computed_value, str):
                    match = stated == computed_value
                else:
                    computed_num = float(str(computed_value).replace("<", "").replace(">", ""))
                    # Allow small tolerance
                    if abs(stated_num) > 100:
                        match = abs(stated_num - computed_num) / max(abs(stated_num), 1) < 0.05
                    else:
                        match = abs(stated_num - computed_num) < 1.5
            except (ValueError, TypeError):
                match = str(stated).strip() == str(computed_value).strip()

            marker = "✅" if match else f"🔴[{level}]"
            if not match:
                cat_issues.append(
                    {
                        "macro": macro_name,
                        "stated": stated,
                        "computed": computed_value,
                        "line": macros[macro_name]["line"],
                        "level": level,
                    }
                )
                all_discrepancies.append(cat_issues[-1])

            lines.append(f"  {marker} {macro_name:30s}: stated={stated:>12s}  computed={computed_value!s:>12s}")

        return cat_issues

    # 1. System numbers
    lines.append(f"\n{'─' * 70}")
    lines.append("## Level A: System Numbers (from graph YAMLs)")
    sys_computed = verify_system_numbers(macros, graphs)
    compare("System", sys_computed, "A")

    # 2. Verdict stats
    if episodes:
        lines.append(f"\n{'─' * 70}")
        lines.append("## Level A: Verdict Stats (from episodes)")
        verdict_computed = verify_verdict_stats(macros, episodes)
        compare("Verdict", verdict_computed, "A")

    # 3. Variance decomposition
    if episodes:
        lines.append(f"\n{'─' * 70}")
        lines.append("## Level A: Variance Decomposition (η²)")
        var_computed = verify_variance(macros, episodes)
        compare("Variance", var_computed, "A")
        # Show debug
        for k, v in sorted(var_computed.items()):
            if k.startswith("_debug"):
                lines.append(f"    {k}: {v}")

    # 4. Ranking
    if episodes:
        lines.append(f"\n{'─' * 70}")
        lines.append("## Level A: Ranking (Friedman)")
        rank_computed = verify_ranking(macros, episodes)
        compare("Ranking", rank_computed, "A")
        for k, v in sorted(rank_computed.items()):
            if k.startswith("_debug"):
                lines.append(f"    {k}: {v}")

    # 5. Engine vs Manual
    if episodes:
        lines.append(f"\n{'─' * 70}")
        lines.append("## Level A: Engine vs Manual")
        evm_computed = verify_engine_vs_manual(macros, episodes)
        compare("E7", evm_computed, "A")

    # 6. Timing
    if episodes:
        lines.append(f"\n{'─' * 70}")
        lines.append("## Level A: Timing Audit")
        timing_computed = verify_timing(macros, episodes)
        compare("Timing", timing_computed, "A")

    # 7. Arithmetic consistency
    lines.append(f"\n{'─' * 70}")
    lines.append("## Level B: Arithmetic Consistency")
    arith_issues = verify_arithmetic(macros)
    for issue in arith_issues:
        lines.append(f"  🟡 {issue}")
        all_discrepancies.append({"macro": "arithmetic", "detail": issue, "level": "B"})
    if not arith_issues:
        lines.append("  ✅ All arithmetic checks pass")

    # 8. Unverifiable (old data)
    lines.append(f"\n{'─' * 70}")
    lines.append("## Level C: Old Data (180 episodes) — Cannot Verify")
    old_data_macros = [
        "instrFullHard",
        "instrNoTimestampsHard",
        "instrTimingLoss",
        "fleissKappaMatchedThirty",
        "fleissKappaMatchedForty",
        "fleissKappaMatchedFifty",
        "verdictFlipRateMatchedThirty",
        "verdictFlipRateMatchedForty",
        "verdictFlipRateMatchedFifty",
        "numEvaluatorsExpanded",
        "numClusters",
        "cophenetic",
        "silhouetteScore",
        "bootstrapARI",
        "bootstrapARILow",
        "bootstrapARIHigh",
    ]
    for m in old_data_macros:
        if m in macros:
            lines.append(f"  🔵 {m:30s}: {macros[m]['value']:>12s}  (from old 180-ep data, re-run needed)")

    # Summary
    lines.append(f"\n{'=' * 70}")
    lines.append("## SUMMARY")
    lines.append(f"  Total macros: {len(macros)}")
    lines.append(f"  Discrepancies found: {len(all_discrepancies)}")
    n_level_a = sum(1 for d in all_discrepancies if d.get("level") == "A")
    n_level_b = sum(1 for d in all_discrepancies if d.get("level") == "B")
    lines.append(f"    Level A (raw mismatch): {n_level_a}")
    lines.append(f"    Level B (arithmetic):   {n_level_b}")

    if all_discrepancies:
        lines.append("\n  🔴 DISCREPANCIES:")
        for d in all_discrepancies:
            if "macro" in d and "stated" in d:
                lines.append(f"    L{d['line']:3d} {d['macro']:30s}: stated={d['stated']} → should be {d['computed']}")
            elif "detail" in d:
                lines.append(f"    {d['detail']}")
    else:
        lines.append("\n  ✅ ALL CHECKS PASS")

    report_text = "\n".join(lines)

    report_path = output_dir / "auto_numbers_audit.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"[SAVED] {report_path}")

    disc_path = output_dir / "discrepancies.json"
    with open(disc_path, "w") as f:
        json.dump(all_discrepancies, f, indent=2, default=str)
    print(f"[SAVED] {disc_path}")

    print(report_text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-numbers", default="paper/auto_numbers.tex")
    parser.add_argument("--episodes-dir", default="results/full_706_v5")
    parser.add_argument("--graphs-dir", default="cpg_model/graphs")
    parser.add_argument("--output-dir", default="evidence_pack/auto_numbers_audit")
    args = parser.parse_args()

    macros = parse_auto_numbers(args.auto_numbers)
    print(f"Parsed {len(macros)} macros from {args.auto_numbers}")

    episodes = load_episodes(args.episodes_dir)
    graphs = load_graphs(args.graphs_dir)

    run_audit(macros, episodes, graphs, args.output_dir)


if __name__ == "__main__":
    main()
