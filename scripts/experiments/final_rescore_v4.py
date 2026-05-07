#!/usr/bin/env python3
"""Final rescore v4: all downstream metrics with corrected evidence pipeline."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.experiments.gap_experiments import (
    MODEL_LABELS,
    MODELS,
    OUT_BASE,
    SCENARIO_DOMAIN,
    SCENARIO_GRAPH,
    _check_event_level_constraints,
    _load_cpg_graph_constraints,
    _load_original_action_traces,
    load_episodes,
)

CORE_SCENARIOS = {
    "septic_shock_basic", "septic_shock_penicillin_allergy",
    "stemi_inferior_rv_trap",
    "stroke_tpa_eligible", "hemorrhagic_stroke",
    "dka_moderate_basic", "dka_hypokalemia_trap",
    "aki_stage1_basic", "contrast_aki_prevention_basic",
}
EXPANSION_SCENARIOS = {
    "adhf_warm_wet", "htn_emergency_basic", "pe_submassive_basic",
    "af_new_onset_basic", "copd_moderate_exacerbation", "gi_bleeding_upper_basic",
}

# Alternative evaluator thresholds
ACOV_THRESHOLD = 0.5


def _compute_episode_hardviol(episodes, all_graphs, action_traces):
    """Compute per-episode hard violation data."""
    results = []
    for ep in episodes:
        graph_name = SCENARIO_GRAPH.get(ep.scenario_id, "")
        gdata = all_graphs.get(graph_name, {})
        trace_raw = action_traces.get(ep.source_file, [])
        viols = _check_event_level_constraints(ep, gdata, trace_raw)
        strong_viols = [v for v in viols if v["evidence_level"] == "STRONG"]
        has_crit = any(v["severity"] == "CRITICAL" for v in viols)
        results.append({
            "ep": ep,
            "viols": viols,
            "has_any": len(viols) > 0,
            "has_strong": len(strong_viols) > 0,
            "has_crit": has_crit,
            "n_viols": len(viols),
            "viol_types": {v["constraint_type"] for v in viols},
        })
    return results


def main():
    print("=" * 70)
    print("FINAL RESCORE v4 — All Downstream Metrics")
    print("=" * 70)

    episodes = load_episodes()
    all_graphs = _load_cpg_graph_constraints()
    action_traces = _load_original_action_traces()
    ep_data = _compute_episode_hardviol(episodes, all_graphs, action_traces)

    passing = [d for d in ep_data if d["ep"].c2 >= 0.7]
    n_pass = len(passing)

    # === 1. Per-Model Table ===
    print(f"\n{'='*60}")
    print("1. Per-Model Table")
    print(f"{'='*60}")
    print(f"{'Model':<8}{'N_pass':>7}{'UP_crit':>12}{'UP_any':>12}")
    print("-" * 40)
    model_table = {}
    for m in MODELS:
        mp = [d for d in passing if d["ep"].model == m]
        n = len(mp)
        n_crit = sum(1 for d in mp if d["has_crit"])
        n_any = sum(1 for d in mp if d["has_any"])
        model_table[m] = {"n": n, "crit": n_crit, "any": n_any}
        print(f"{MODEL_LABELS[m]:<8}{n:>7}{n_crit:>5}/{n} ({n_crit/n:.0%})"
              f"{n_any:>5}/{n} ({n_any/n:.0%})")
    n_crit_all = sum(1 for d in passing if d["has_crit"])
    n_any_all = sum(1 for d in passing if d["has_any"])
    print(f"{'All':<8}{n_pass:>7}{n_crit_all:>5}/{n_pass} ({n_crit_all/n_pass:.1%})"
          f"{n_any_all:>5}/{n_pass} ({n_any_all/n_pass:.1%})")

    # === 2. Scenario-Clustered Bootstrap CI ===
    print(f"\n{'='*60}")
    print("2. Scenario-Clustered Bootstrap CI (B=10000)")
    print(f"{'='*60}")
    scenarios = sorted({d["ep"].scenario_id for d in passing})
    rng = np.random.default_rng(42)

    for tier_name, tier_key in [("UP_any", "has_any"), ("UP_crit", "has_crit")]:
        # Group by scenario
        scen_rates = {}
        for s in scenarios:
            sp = [d for d in passing if d["ep"].scenario_id == s]
            if sp:
                scen_rates[s] = sum(1 for d in sp if d[tier_key]) / len(sp)

        scen_list = list(scen_rates.keys())
        scen_vals = np.array([scen_rates[s] for s in scen_list])
        observed = scen_vals.mean()

        boot = np.zeros(10000)
        for b in range(10000):
            idx = rng.integers(0, len(scen_list), size=len(scen_list))
            boot[b] = scen_vals[idx].mean()

        ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
        print(f"  {tier_name}: {observed:.1%} [{ci_lo:.1%}, {ci_hi:.1%}]")

    # === 3. Verdict Matrix ===
    print(f"\n{'='*60}")
    print("3. Verdict Matrix")
    print(f"{'='*60}")

    # Compute action coverage for ACov evaluator
    from scripts.experiments.gap_experiments import _load_original_episodes_full
    orig_data = _load_original_episodes_full()

    evaluators = []

    # C2>=0.7
    c2_pass = [d for d in ep_data if d["ep"].c2 >= 0.7]
    c2_hard = sum(1 for d in c2_pass if d["has_any"])
    evaluators.append(("C2>=0.7", len(c2_pass), c2_hard))

    # ACov>=0.5
    acov_pass = []
    for d in ep_data:
        orig = orig_data.get(d["ep"].source_file, {})
        expected = set(orig.get("expected_actions", []))
        raw_actions = orig.get("actions", [])
        agent_actions = {a["action_id"] for a in raw_actions if isinstance(a, dict)}
        cov = len(agent_actions & expected) / len(expected) if expected else 0
        if cov >= ACOV_THRESHOLD:
            acov_pass.append(d)
    acov_hard = sum(1 for d in acov_pass if d["has_any"])
    evaluators.append(("ACov>=0.5", len(acov_pass), acov_hard))

    # DxEM (all episodes)
    dxem_hard = sum(1 for d in ep_data if d["has_any"])
    evaluators.append(("DxEM(all)", len(ep_data), dxem_hard))

    print(f"{'Evaluator':<15}{'N_pass':>8}{'Hard':>8}{'Mis-cert':>10}")
    print("-" * 42)
    for name, n, h in evaluators:
        rate = h / n if n else 0
        print(f"{name:<15}{n:>8}{h:>8}{rate:>10.1%}")

    # === 4. Stratification ===
    print(f"\n{'='*60}")
    print("4. Core/Expansion Stratification")
    print(f"{'='*60}")
    for subset_name, scen_set in [("Core", CORE_SCENARIOS), ("Expansion", EXPANSION_SCENARIOS), ("All", CORE_SCENARIOS | EXPANSION_SCENARIOS)]:
        sub = [d for d in ep_data if d["ep"].scenario_id in scen_set]
        sub_pass = [d for d in sub if d["ep"].c2 >= 0.7]
        n_sub = len(sub)
        n_cp = len(sub_pass)
        n_crit = sum(1 for d in sub_pass if d["has_crit"])
        n_any = sum(1 for d in sub_pass if d["has_any"])
        print(f"  {subset_name:<12} Ep={n_sub:<4} CP={n_cp:<4} "
              f"UP_crit={n_crit}/{n_cp} UP_any={n_any}/{n_cp}")

    # === 5. Instrumentation Ablation ===
    print(f"\n{'='*60}")
    print("5. Instrumentation Ablation (B-1)")
    print(f"{'='*60}")

    conditions = [
        ("Full", lambda v: True),
        ("No timing", lambda v: v["constraint_type"] != "WITHIN"),
        ("No ordering", lambda v: v["constraint_type"] != "BEFORE"),
        ("No forbidden", lambda v: v["constraint_type"] != "FORBIDDEN"),
        ("Timing only", lambda v: v["constraint_type"] == "WITHIN"),
        ("Forbidden only", lambda v: v["constraint_type"] == "FORBIDDEN"),
        ("Ordering only", lambda v: v["constraint_type"] == "BEFORE"),
    ]
    print(f"{'Condition':<18}{'UP_any':>10}{'UP_crit':>10}")
    print("-" * 38)

    for cond_name, filt in conditions:
        n_any_c = 0
        n_crit_c = 0
        for d in passing:
            filtered = [v for v in d["viols"] if filt(v)]
            if filtered:
                n_any_c += 1
            if any(v["severity"] == "CRITICAL" for v in filtered):
                n_crit_c += 1
        print(f"{cond_name:<18}{n_any_c:>4}/{n_pass} ({n_any_c/n_pass:.1%})"
              f"{n_crit_c:>4}/{n_pass} ({n_crit_c/n_pass:.1%})")

    # === 6. Domain Spread ===
    print(f"\n{'='*60}")
    print("6. Domain Spread")
    print(f"{'='*60}")
    domains = sorted({SCENARIO_DOMAIN.get(d["ep"].scenario_id, "?") for d in ep_data})
    domains_with_viols = 0
    scens_with_viols = set()
    print(f"{'Domain':<15}{'Scen':>5}{'CP':>5}{'UP_crit':>10}{'UP_any':>10}{'Types'}")
    print("-" * 65)
    for dom in domains:
        dom_eps = [d for d in ep_data if SCENARIO_DOMAIN.get(d["ep"].scenario_id) == dom]
        dom_pass = [d for d in dom_eps if d["ep"].c2 >= 0.7]
        n_cp = len(dom_pass)
        n_any = sum(1 for d in dom_pass if d["has_any"])
        n_crit = sum(1 for d in dom_pass if d["has_crit"])
        vtypes = set()
        for d in dom_pass:
            vtypes.update(d["viol_types"])
            if d["has_any"]:
                scens_with_viols.add(d["ep"].scenario_id)
        if n_any > 0:
            domains_with_viols += 1
        n_scen = len({d["ep"].scenario_id for d in dom_eps})
        vt_str = ",".join(sorted(vtypes)) if vtypes else "-"
        crit_str = f"{n_crit}/{n_cp}" if n_cp else "0/0"
        any_str = f"{n_any}/{n_cp}" if n_cp else "0/0"
        print(f"{dom:<15}{n_scen:>5}{n_cp:>5}{crit_str:>10}{any_str:>10}  {vt_str}")

    print(f"\nHard violations in {domains_with_viols}/{len(domains)} domains "
          f"and {len(scens_with_viols)}/15 scenarios")

    # === 7. Domain-Removal Robustness ===
    print(f"\n{'='*60}")
    print("7. Domain-Removal Robustness")
    print(f"{'='*60}")
    print(f"{'Removed':<15}{'CP':>5}{'UP_any':>10}{'Rate':>8}")
    print("-" * 40)
    for dom in domains:
        sub = [d for d in passing if SCENARIO_DOMAIN.get(d["ep"].scenario_id) != dom]
        n = len(sub)
        h = sum(1 for d in sub if d["has_any"])
        rate = h / n if n else 0
        print(f"{dom:<15}{n:>5}{h:>10}{rate:>8.1%}")

    # === 8. Absolute Prevalence ===
    print(f"\n{'='*60}")
    print("8. Absolute Prevalence (all 180 episodes)")
    print(f"{'='*60}")
    all_hard = sum(1 for d in ep_data if d["has_any"])
    cp_hard = sum(1 for d in passing if d["has_any"])
    print(f"  Any hard violation: {all_hard}/180 = {all_hard/180:.1%}")
    print(f"  CP AND hard: {cp_hard}/180 = {cp_hard/180:.1%}")

    # === 9. Poster-Child Count ===
    print(f"\n{'='*60}")
    print("9. Poster-Child Episodes")
    print(f"{'='*60}")
    # Episodes where C2>=0.7 AND hard violation AND C3=1 AND C4>=0.7
    # (would pass all process-oblivious evaluators)
    poster = [d for d in passing if d["has_any"]
              and d["ep"].c3 >= 1.0 and d["ep"].c4 >= 0.7]
    print(f"  C2>=0.7 + hard + C3=1 + C4>=0.7: {len(poster)}/{n_pass}")
    # Also: high CGA but hard violation
    high_cga_hard = [d for d in passing if d["has_any"] and d["ep"].cga >= 0.7]
    print(f"  C2>=0.7 + hard + CGA>=0.7: {len(high_cga_hard)}/{n_pass}")

    # === 10. z1-only Subset ===
    print(f"\n{'='*60}")
    print("10. z1-only Subset")
    print(f"{'='*60}")
    # z1-determined: constraints from entry node only
    z1_count = 0
    z1_crit = 0
    for d in passing:
        graph_name = SCENARIO_GRAPH.get(d["ep"].scenario_id, "")
        gdata = all_graphs.get(graph_name, {})
        # Entry node is typically the first node in deadlines/forbidden
        entry_nodes = set()
        for nid in list(gdata.get("deadlines", {}).keys())[:1]:
            entry_nodes.add(nid)
        for nid in list(gdata.get("forbidden", {}).keys())[:1]:
            entry_nodes.add(nid)
        z1_viols = [v for v in d["viols"] if v["node"] in entry_nodes]
        if z1_viols:
            z1_count += 1
            if any(v["severity"] == "CRITICAL" for v in z1_viols):
                z1_crit += 1
    print(f"  UP_any (z1-only): {z1_count}/{n_pass} = {z1_count/n_pass:.1%}")
    print(f"  UP_crit (z1-only): {z1_crit}/{n_pass} = {z1_crit/n_pass:.1%}")

    # Save results
    out_dir = OUT_BASE / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "final_rescore_v4.json"

    results = {
        "per_model": {MODEL_LABELS[m]: model_table[m] for m in MODELS},
        "totals": {"n_pass": n_pass, "up_any": n_any_all, "up_crit": n_crit_all},
        "absolute": {"all_hard": all_hard, "cp_hard": cp_hard},
    }
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()
