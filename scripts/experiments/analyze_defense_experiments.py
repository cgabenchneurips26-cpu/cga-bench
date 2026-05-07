"""Analyze post-AMEGA defense experiment results.

Phase 1 (C3 Defense): AgentClinic / MedAgentBench × 3 models
Phase 3 (Temp Sweep): AgentClinic × T={0.0, 0.3, 0.7} on Qwen3.5

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/analyze_defense_experiments.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

C3_DIR = REPO_ROOT / "results" / "defense_c3"
TEMP_DIR = REPO_ROOT / "results" / "defense_temp"
OUT_DIR = REPO_ROOT / "evidence_pack" / "analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_result(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def extract_metrics(data: dict[str, Any]) -> dict[str, float]:
    """Extract key metrics from a benchmark result file."""
    summary = data.get("summary", {})
    cpg = data.get("cpg_summary", {})
    modular = data.get("modular_summary", {})
    results = data.get("results", [])

    # Per-episode CGA scores
    cga_scores = []
    for r in results:
        score = r.get("cpg_score", {}).get("compliance_score")
        if score is None:
            score = r.get("cpg_evaluation", {}).get("compliance_score")
        if score is not None:
            cga_scores.append(score)

    return {
        "n_episodes": summary.get("completed", len(results)),
        "avg_action_coverage": summary.get("avg_action_coverage", 0),
        "avg_final_score": summary.get("avg_final_score", 0),
        "avg_cpg_compliance": cpg.get("avg_compliance_score", 0),
        "avg_violations": cpg.get("avg_violations_per_scenario", 0),
        "avg_modular_overall": modular.get("avg_overall_score", 0),
        "safety_score": modular.get("avg_safety_score", 0),
        "sequence_score": modular.get("avg_sequence_score", 0),
        "diagnosis_rate": summary.get("correct_diagnosis_rate", 0),
        "avg_actions": summary.get("avg_actions_per_scenario", 0),
        "cga_scores": cga_scores,
        "cga_mean": float(np.mean(cga_scores)) if cga_scores else 0.0,
        "cga_std": float(np.std(cga_scores)) if cga_scores else 0.0,
    }


def analyze_c3_defense() -> dict[str, Any]:
    """Phase 1: Cross-benchmark native replay defense."""
    print("=" * 60)
    print("  Phase 1: C3 Defense (AgentClinic / MedAgentBench × 3 models)")
    print("=" * 60)

    results = {}
    for path in sorted(C3_DIR.glob("*.json")):
        name = path.stem
        data = load_result(path)
        metrics = extract_metrics(data)
        results[name] = metrics

        print(f"\n  {name}:")
        print(f"    Episodes: {metrics['n_episodes']}")
        print(f"    Action Coverage: {metrics['avg_action_coverage']:.4f}")
        print(f"    CPG Compliance: {metrics['avg_cpg_compliance']:.4f}")
        print(f"    Modular Overall: {metrics['avg_modular_overall']:.4f}")
        print(f"    Safety: {metrics['safety_score']:.4f}")
        print(f"    Avg Actions: {metrics['avg_actions']:.2f}")
        print(f"    CGA: {metrics['cga_mean']:.4f} +/- {metrics['cga_std']:.4f}")

    if not results:
        print("\n  No C3 results found yet.")
        return {}

    # Cross-benchmark comparison
    benchmarks = set()
    models = set()
    for name in results:
        parts = name.split("_")
        benchmarks.add(parts[0])
        models.add("_".join(parts[1:]))

    print(f"\n  Benchmarks: {sorted(benchmarks)}")
    print(f"  Models: {sorted(models)}")

    # Model-level consistency
    for model in sorted(models):
        model_results = {k: v for k, v in results.items() if k.endswith(model)}
        if len(model_results) >= 2:
            coverages = [v["avg_action_coverage"] for v in model_results.values()]
            print(f"\n  {model} cross-benchmark coverage: {[f'{c:.4f}' for c in coverages]}")

    return results


def analyze_temp_sweep() -> dict[str, Any]:
    """Phase 3: Temperature sensitivity defense."""
    print("\n" + "=" * 60)
    print("  Phase 3: Temperature Sweep (T=0.0, 0.3, 0.7)")
    print("=" * 60)

    results = {}
    for path in sorted(TEMP_DIR.glob("*.json")):
        name = path.stem
        data = load_result(path)
        metrics = extract_metrics(data)
        results[name] = metrics

        print(f"\n  {name}:")
        print(f"    Episodes: {metrics['n_episodes']}")
        print(f"    CGA: {metrics['cga_mean']:.4f} +/- {metrics['cga_std']:.4f}")
        print(f"    Action Coverage: {metrics['avg_action_coverage']:.4f}")
        print(f"    Modular Overall: {metrics['avg_modular_overall']:.4f}")
        print(f"    Avg Actions: {metrics['avg_actions']:.2f}")

    if not results:
        print("\n  No temperature sweep results found yet.")
        return {}

    # Variance decomposition
    all_scores = {}
    for name, m in results.items():
        if m["cga_scores"]:
            all_scores[name] = m["cga_scores"]

    if len(all_scores) >= 2:
        # Between-temperature variance
        means = [np.mean(s) for s in all_scores.values()]
        grand_mean = np.mean(means)
        ss_between = sum(len(s) * (np.mean(s) - grand_mean) ** 2 for s in all_scores.values())

        # Within-temperature variance
        ss_within = sum(sum((x - np.mean(s)) ** 2 for x in s) for s in all_scores.values())

        ss_total = ss_between + ss_within
        eta_sq = ss_between / ss_total if ss_total > 0 else 0

        print("\n  Variance Decomposition:")
        print(f"    SS_between (temperature): {ss_between:.4f}")
        print(f"    SS_within (scenario): {ss_within:.4f}")
        print(f"    eta^2 (temperature): {eta_sq:.4f}")
        print(f"    Interpretation: Temperature explains {eta_sq * 100:.1f}% of variance")

        results["_variance_decomposition"] = {
            "ss_between": float(ss_between),
            "ss_within": float(ss_within),
            "eta_squared": float(eta_sq),
            "n_temperatures": len(all_scores),
        }

    return results


def generate_latex_macros(c3: dict[str, Any], temp: dict[str, Any]) -> str:
    """Generate LaTeX macros for the paper."""
    lines = [
        "% Defense experiment macros",
        "% Auto-generated by analyze_defense_experiments.py",
        "",
    ]

    # C3 macros
    for name, m in c3.items():
        safe_name = name.replace("_", "")
        lines.append(f"\\newcommand{{\\defCthreeN{safe_name}}}{{{m['n_episodes']}}}")
        lines.append(f"\\newcommand{{\\defCthreeCGA{safe_name}}}{{{m['cga_mean']:.3f}}}")
        lines.append(f"\\newcommand{{\\defCthreeCov{safe_name}}}{{{m['avg_action_coverage']:.3f}}}")

    # Temp macros
    vd = temp.get("_variance_decomposition", {})
    if vd:
        lines.append(f"\\newcommand{{\\defTempEtaSq}}{{{vd['eta_squared']:.4f}}}")

    for name, m in temp.items():
        if name.startswith("_"):
            continue
        safe_name = name.replace("_", "").replace(".", "")
        lines.append(f"\\newcommand{{\\defTempCGA{safe_name}}}{{{m['cga_mean']:.3f}}}")

    return "\n".join(lines)


def main() -> None:
    c3_results = analyze_c3_defense()
    temp_results = analyze_temp_sweep()

    # Save combined results
    combined = {
        "c3_defense": {k: {kk: vv for kk, vv in v.items() if kk != "cga_scores"} for k, v in c3_results.items()},
        "temp_sweep": {k: {kk: vv for kk, vv in v.items() if kk != "cga_scores"} for k, v in temp_results.items()},
    }

    out_json = OUT_DIR / "defense_experiments_analysis.json"
    with open(out_json, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"\nSaved: {out_json}")

    # LaTeX macros
    tex = generate_latex_macros(c3_results, temp_results)
    out_tex = REPO_ROOT / "paper" / "auto_numbers_defense.tex"
    with open(out_tex, "w") as f:
        f.write(tex)
    print(f"Saved: {out_tex}")

    print("\nDone.")


if __name__ == "__main__":
    main()
