#!/usr/bin/env python3
"""W8 Cross-Model Verdict Matrix Generator.
Reads results from results/ex_w8_crossmodel/ and produces
a comprehensive verdict matrix for 3 models × 4 scaffolds.

Output: evidence_pack/ex_w8_crossmodel/w8_verdict_matrix.json
"""

from collections import defaultdict
import json
from pathlib import Path
from typing import Any

RESULTS_DIR = Path("results/ex_w8_crossmodel")
OUTPUT_DIR = Path("evidence_pack/ex_w8_crossmodel")
TARGET = 706

MODELS = ["oss120b", "qwen35b", "gemma31b"]
SCAFFOLDS = ["react", "direct", "checklist", "tooluse"]

# qwen35b_react has split dirs
SPLIT_DIRS: dict[str, list[str]] = {
    "qwen35b_react": ["qwen35b_react", "qwen35b_react_s2"],
}


def load_episodes(model: str, scaffold: str) -> list[dict[str, Any]]:
    """Load deduplicated episodes for a model-scaffold pair."""
    key = f"{model}_{scaffold}"
    dirs = SPLIT_DIRS.get(key, [key])

    seen: dict[str, dict[str, Any]] = {}  # scenario_id → best episode
    for subdir in dirs:
        d = RESULTS_DIR / subdir
        if not d.is_dir():
            continue
        for fp in d.glob("*.json"):
            if fp.name.startswith("checkpoint") or fp.name == "model_summary.json":
                continue
            try:
                data = json.loads(fp.read_text())
                sid = data.get("scenario_id", "")
                if not sid:
                    continue
                # Keep first seen per scenario (dedup)
                if sid not in seen:
                    seen[sid] = data
            except Exception:
                continue

    return list(seen.values())


def compute_cell_stats(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute stats for a single model-scaffold cell."""
    if not episodes:
        return {"n": 0, "comply": 0.0, "pass50": 0.0}

    n = len(episodes)
    compliances = []
    passes = 0
    sub_scores: dict[str, list[float]] = defaultdict(list)
    violations: dict[str, int] = defaultdict(int)
    total_actions = 0
    total_tokens = 0
    total_llm_calls = 0

    for ep in episodes:
        c = ep.get("compliance_score", 0.0)
        compliances.append(c)
        if c >= 0.5:
            passes += 1

        ss = ep.get("sub_scores", {})
        for k, v in ss.items():
            sub_scores[k].append(v)

        vbt = ep.get("violations_by_type", {})
        for vtype, count in vbt.items():
            violations[vtype] += count

        total_actions += ep.get("actions_count", 0)
        total_tokens += ep.get("total_tokens", 0)
        total_llm_calls += ep.get("total_llm_calls", 0)

    avg_comply = sum(compliances) / n
    pass_rate = (passes / n) * 100

    # Sub-score averages
    avg_sub = {}
    for k, vals in sub_scores.items():
        avg_sub[k] = round(sum(vals) / len(vals), 4)

    # Compliance distribution
    bins = [0, 0.25, 0.5, 0.75, 1.01]
    hist = [0] * (len(bins) - 1)
    for c in compliances:
        for i in range(len(bins) - 1):
            if bins[i] <= c < bins[i + 1]:
                hist[i] += 1
                break

    return {
        "n": n,
        "comply": round(avg_comply, 4),
        "pass50": round(pass_rate, 1),
        "sub_scores": avg_sub,
        "violations": dict(violations),
        "avg_actions": round(total_actions / n, 1),
        "avg_tokens": round(total_tokens / n, 0),
        "avg_llm_calls": round(total_llm_calls / n, 1),
        "compliance_hist": {
            "[0.00-0.25)": hist[0],
            "[0.25-0.50)": hist[1],
            "[0.50-0.75)": hist[2],
            "[0.75-1.00]": hist[3],
        },
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    matrix: dict[str, dict[str, Any]] = {}
    summary_table = []

    print("W8 Verdict Matrix Generator")
    print("=" * 60)

    for model in MODELS:
        for scaffold in SCAFFOLDS:
            key = f"{model}_{scaffold}"
            episodes = load_episodes(model, scaffold)
            stats = compute_cell_stats(episodes)
            matrix[key] = stats

            status = "COMPLETE" if stats["n"] >= TARGET else f"INCOMPLETE ({stats['n']}/{TARGET})"
            print(f"  {key}: {stats['n']} ep, comply={stats['comply']:.3f}, pass={stats['pass50']:.1f}% [{status}]")

            summary_table.append(
                {
                    "model": model,
                    "scaffold": scaffold,
                    "n": stats["n"],
                    "comply": stats["comply"],
                    "pass50": stats["pass50"],
                    "status": status,
                }
            )

    # Aggregate by model
    print("\n--- By Model ---")
    for model in MODELS:
        cells = [matrix[f"{model}_{s}"] for s in SCAFFOLDS]
        avg_c = sum(c["comply"] for c in cells) / len(cells)
        avg_p = sum(c["pass50"] for c in cells) / len(cells)
        best = max(SCAFFOLDS, key=lambda s: matrix[f"{model}_{s}"]["comply"])
        print(f"  {model}: avg_comply={avg_c:.3f}, avg_pass={avg_p:.1f}%, best={best}")

    # Aggregate by scaffold
    print("\n--- By Scaffold ---")
    for scaffold in SCAFFOLDS:
        cells = [matrix[f"{m}_{scaffold}"] for m in MODELS]
        avg_c = sum(c["comply"] for c in cells) / len(cells)
        avg_p = sum(c["pass50"] for c in cells) / len(cells)
        print(f"  {scaffold}: avg_comply={avg_c:.3f}, avg_pass={avg_p:.1f}%")

    # Save
    output = {
        "experiment": "W8_cross_model_scaffold",
        "models": MODELS,
        "scaffolds": SCAFFOLDS,
        "target_scenarios": TARGET,
        "matrix": matrix,
        "summary": summary_table,
    }

    out_path = OUTPUT_DIR / "w8_verdict_matrix.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
