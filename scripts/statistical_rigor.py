#!/usr/bin/env python3
"""Statistical rigor fixes: difficulty calibration, CGA vs MedQA, inflation diagnosis."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

OUT = Path(__file__).parent.parent / "reports" / "evidence_pack"

# ── Data ──
SCENARIOS = [
    "sepsis_basic", "sepsis_allergy", "stemi_rv_trap", "dka_moderate",
    "dka_hypokalemia", "contrast_aki", "aki_stage1", "stroke_tpa",
]
SHORT = {
    "sepsis_basic": "Sepsis", "sepsis_allergy": "Sepsis-A",
    "stemi_rv_trap": "STEMI", "dka_moderate": "DKA",
    "dka_hypokalemia": "DKA-K", "contrast_aki": "C-AKI",
    "aki_stage1": "AKI", "stroke_tpa": "Stroke",
}

# oss-120b 3-run means
OSS = [93.1, 95.8, 82.6, 62.8, 61.3, 61.1, 56.1, 75.9]
ORACLE = [100, 100, 100, 70, 70, 100, 40, 100]

# Structural complexity from CPG graphs
COMPLEXITY = json.load(open(OUT / "analysis" / "structural_complexity.json"))


# ── Fix 4: CGA vs MedQA — rank-based comparison (N=3, no correlation) ──
def fix4_rank_comparison():
    print("\n=== Fix 4: CGA vs MedQA Rank Comparison (N=3, no correlation) ===")

    # Published MedQA scores (will be marked verified/unverified)
    models = {
        "oss-120b": {"medqa": "~90 (est.)", "medqa_verified": False, "cga": 73.6},
        "Qwen2.5-72B": {"medqa": "~82 (est.)", "medqa_verified": False, "cga": 70.2},
        "Qwen3.5-35B": {"medqa": "~72 (est.)", "medqa_verified": False, "cga": 73.4},
    }

    # Rank comparison
    medqa_rank = ["oss-120b", "Qwen2.5-72B", "Qwen3.5-35B"]  # assumed
    cga_rank = sorted(models.keys(), key=lambda m: -models[m]["cga"])

    print(f"  MedQA rank (estimated): {medqa_rank}")
    print(f"  CGA rank (measured): {cga_rank}")
    print(f"  Rank match: {'YES' if medqa_rank == cga_rank else 'NO — rank inversion observed'}")

    result = {
        "note": "N=3 is insufficient for correlation analysis. Reporting rank comparison only.",
        "medqa_rank": medqa_rank,
        "cga_rank": cga_rank,
        "rank_match": medqa_rank == cga_rank,
        "medqa_scores_verified": False,
        "paper_statement": (
            "With N=3 models, statistical correlation analysis is not feasible. "
            "However, we observe a rank inversion: the MoE model (Qwen3.5-35B) "
            "outperforms the larger dense model (Qwen2.5-72B) on CGA-Bench despite "
            "lower estimated MedQA scores, suggesting CGA measures a dimension "
            "distinct from medical knowledge tests. Systematic verification with "
            "N≥7 models is left to future work."
        ),
    }

    d = OUT / "analysis"
    with open(d / "cga_vs_medqa_rank.json", "w") as f:
        json.dump(result, f, indent=2)

    # Update the figure — remove misleading correlation line
    fig, ax = plt.subplots(figsize=(5, 4))
    names = ["oss-120b", "Qwen2.5-72B", "Qwen3.5-35B"]
    medqa_est = [90, 82, 72]
    cga_vals = [models[m]["cga"] for m in names]
    for i, name in enumerate(names):
        ax.scatter(medqa_est[i], cga_vals[i], s=100, zorder=3)
        ax.annotate(name, (medqa_est[i] + 0.5, cga_vals[i] + 0.5), fontsize=8)
    ax.set_xlabel("MedQA Accuracy (%, estimated)")
    ax.set_ylabel("CGA-Bench Compliance (%)")
    ax.set_title("CGA vs MedQA: Rank Inversion (N=3, no correlation)")
    ax.text(0.05, 0.05, "N=3: correlation analysis\nnot statistically valid",
            transform=ax.transAxes, fontsize=7, color='red', style='italic')
    fig.tight_layout()
    fig.savefig(OUT / "figures" / "cga_vs_medqa.png", dpi=300)
    plt.close()
    print("  Saved: analysis/cga_vs_medqa_rank.json + figures/cga_vs_medqa.png")


# ── Fix 5: Difficulty calibration with structural complexity ──
def fix5_structural_difficulty():
    print("\n=== Fix 5: Difficulty Calibration (Structural Complexity) ===")

    complexities = []
    avg_compliances = []
    oracle_scores = []
    labels = []

    for i, s in enumerate(SCENARIOS):
        c = COMPLEXITY[s]["complexity"]
        avg = np.mean(OSS[i])  # will be updated with 3-model mean later
        complexities.append(c)
        avg_compliances.append(avg)
        oracle_scores.append(ORACLE[i])
        labels.append(SHORT[s])

    rho, p = stats.spearmanr(complexities, avg_compliances)
    print(f"  Complexity vs Compliance: Spearman rho={rho:.3f}, p={p:.4f}")

    # Oracle as difficulty proxy
    rho_oracle, p_oracle = stats.spearmanr(oracle_scores, avg_compliances)
    print(f"  Oracle vs RAG: Spearman rho={rho_oracle:.3f}, p={p_oracle:.4f}")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    # Left: structural complexity vs compliance
    ax1.scatter(complexities, avg_compliances, s=80, c='#1f77b4', zorder=3)
    for i in range(len(SCENARIOS)):
        ax1.annotate(labels[i], (complexities[i] + 1, avg_compliances[i] + 0.5), fontsize=7)
    z = np.polyfit(complexities, avg_compliances, 1)
    x_fit = np.linspace(50, 160, 100)
    ax1.plot(x_fit, z[0] * x_fit + z[1], '--', color='gray', alpha=0.5)
    ax1.set_xlabel("Structural Complexity (CPG graph)")
    ax1.set_ylabel("oss-120b Compliance (%)")
    ax1.set_title(f"Structural Difficulty (ρ={rho:.2f}, p={p:.3f})")

    # Right: Oracle score vs RAG compliance
    ax2.scatter(oracle_scores, avg_compliances, s=80, c='#ff7f0e', zorder=3)
    for i in range(len(SCENARIOS)):
        ax2.annotate(labels[i], (oracle_scores[i] + 1, avg_compliances[i] + 0.5), fontsize=7)
    ax2.plot([30, 105], [30, 105], '--', color='gray', alpha=0.3, label='y=x')
    ax2.set_xlabel("Oracle Compliance (%)")
    ax2.set_ylabel("oss-120b Compliance (%)")
    ax2.set_title(f"Oracle as Difficulty Proxy (ρ={rho_oracle:.2f})")
    ax2.legend()

    fig.tight_layout()
    fig.savefig(OUT / "figures" / "difficulty_calibration.png", dpi=300)
    plt.close()

    result = {
        "structural_complexity_correlation": {"spearman_rho": rho, "p_value": p},
        "oracle_proxy_correlation": {"spearman_rho": rho_oracle, "p_value": p_oracle},
        "scenarios": {s: {"complexity": COMPLEXITY[s]["complexity"],
                          "compliance_oss": OSS[i], "oracle": ORACLE[i]}
                      for i, s in enumerate(SCENARIOS)},
        "note": "Complexity derived from CPG graph structure (mandatory+forbidden+timing+nodes), independent of scores."
    }
    with open(OUT / "analysis" / "difficulty_calibration.json", "w") as f:
        json.dump(result, f, indent=2)
    print("  Saved: figures/difficulty_calibration.png + analysis/difficulty_calibration.json")


# ── Fix 7: External benchmark inflation diagnosis ──
def fix7_inflation_diagnosis():
    print("\n=== Fix 7: External Benchmark Inflation Diagnosis ===")

    benchmarks = {
        "MedAgentBench": {
            "score": 96.7, "n": 20,
            "domain_specific": 0, "universal_fallback": 20,
            "note": "All 20 cases evaluated with universal_clinical_safety CPG (no domain match)"
        },
        "AgentClinic": {
            "score": 62.0, "n": 20,
            "domain_specific": 0, "universal_fallback": 20,
            "note": "All cases use universal CPG. 62% reflects action coverage, not domain CPG."
        },
        "MedChain": {
            "score": 10.0, "n": 20,
            "domain_specific": 2, "universal_fallback": 18,
            "note": "2/20 matched specific CPGs (DKA, general), rest universal fallback."
        },
    }

    print(f"  {'Benchmark':<18} {'Score':>6} {'Specific CPG':>13} {'Universal FB':>13} {'FB %':>6}")
    print("  " + "-" * 60)
    for name, info in benchmarks.items():
        fb_pct = info["universal_fallback"] / info["n"] * 100
        print(f"  {name:<18} {info['score']:>5.1f}% {info['domain_specific']:>13} {info['universal_fallback']:>13} {fb_pct:>5.0f}%")

    print("\n  ⚠️ MedAgentBench 96.7% is INFLATED: 100% universal fallback")
    print("  ⚠️ AgentClinic 62.0% may be partially inflated: 100% universal fallback")
    print("  MedChain 10.0% is the most honest: low coverage reflects actual domain gap")

    result = {
        "diagnosis": "MedAgentBench and AgentClinic scores are inflated due to universal_clinical_safety fallback.",
        "benchmarks": benchmarks,
        "recommendation": (
            "Report external benchmark scores with CPG coverage annotation. "
            "Scores under universal fallback indicate pipeline operability, "
            "not genuine CPG compliance. Only HealthBench (rubric-based) and "
            "domain-matched cases provide meaningful compliance measures."
        ),
    }
    with open(OUT / "analysis" / "inflation_diagnosis.json", "w") as f:
        json.dump(result, f, indent=2)
    print("  Saved: analysis/inflation_diagnosis.json")


if __name__ == "__main__":
    (OUT / "analysis").mkdir(parents=True, exist_ok=True)
    (OUT / "figures").mkdir(parents=True, exist_ok=True)

    fix4_rank_comparison()
    fix5_structural_difficulty()
    fix7_inflation_diagnosis()

    print("\n=== Fixes 4, 5, 7 COMPLETE ===")
