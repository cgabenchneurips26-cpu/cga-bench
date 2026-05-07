#!/usr/bin/env python3
"""Full Normalizer Gap Quantification
====================================
전체 9,500+ 에피소드에서 performed↔expected 매칭 실패를 정량화.

출력:
  1. (performed, expected) 쌍 빈도순 완전 목록
  2. 각 쌍이 수정되면 제거되는 OMISSION 수
  3. Similarity tier별 분포 (0.9+, 0.8-0.9, 0.7-0.8, 0.6-0.7, 0.5-0.6)
  4. 수정 후 예상 OMISSION rate
  5. Normalizer에 추가할 alias 목록 (JSON)

Usage:
    python quantify_normalizer_gap.py --episodes-dir results/full_706_v5
"""

import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import json
from pathlib import Path


def load_episodes(episodes_dir: str) -> list:
    episodes = []
    for model_dir in sorted(Path(episodes_dir).iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                ep["_model"] = model_dir.name
                episodes.append(ep)
            except Exception:
                pass
    return episodes


def extract_sets(ep: dict) -> tuple:
    """Extract performed and expected action sets from episode."""
    performed = set()
    actions = ep.get("actions", [])
    if isinstance(actions, list):
        for a in actions:
            if isinstance(a, dict):
                name = a.get("action_id", a.get("action", "")).lower().strip()
                if name:
                    performed.add(name)
            elif isinstance(a, str):
                performed.add(a.lower().strip())

    expected = set()
    exp_list = ep.get("expected_actions", ep.get("mandatory_actions", []))
    if isinstance(exp_list, list):
        for a in exp_list:
            if isinstance(a, str):
                expected.add(a.lower().strip())
            elif isinstance(a, dict):
                name = a.get("action_id", a.get("action", "")).lower().strip()
                if name:
                    expected.add(name)

    return performed, expected


def find_best_match(action: str, candidates: set, min_sim: float = 0.5) -> tuple:
    """Find best matching candidate for an action."""
    best_name = None
    best_sim = 0.0
    for c in candidates:
        sim = SequenceMatcher(None, action, c).ratio()
        if sim > best_sim and sim >= min_sim:
            best_sim = sim
            best_name = c
    return best_name, best_sim


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes-dir", default="results/full_706_v5")
    parser.add_argument("--output-dir", default="evidence_pack/normalizer_gap")
    parser.add_argument("--min-sim", type=float, default=0.5)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("FULL NORMALIZER GAP QUANTIFICATION")
    print("=" * 70)

    episodes = load_episodes(args.episodes_dir)
    print(f"[INFO] {len(episodes)} episodes loaded")

    if not episodes:
        print("[ERROR] No episodes")
        return

    # ── Phase 1: Collect all (performed, expected) near-miss pairs ──
    print("\n[STEP 1] Scanning all episodes for near-miss pairs...")

    # pair_counts: (performed, expected) -> episode count
    pair_counts = Counter()
    # pair_models: (performed, expected) -> set of models
    pair_models = defaultdict(set)
    # pair_sims: (performed, expected) -> max similarity
    pair_sims = {}
    # Per-episode stats
    total_omissions = 0
    total_near_miss_omissions = 0
    total_expected = 0
    total_episodes = 0
    episodes_with_near_miss = 0

    # Per-model stats
    model_omissions = Counter()
    model_near_miss = Counter()
    model_episodes = Counter()

    for i, ep in enumerate(episodes):
        if i % 1000 == 0 and i > 0:
            print(f"  ... processed {i}/{len(episodes)} episodes")

        performed, expected = extract_sets(ep)
        model = ep.get("_model", "unknown")
        model_episodes[model] += 1

        matched = expected & performed
        omitted = expected - performed
        extra = performed - expected

        total_expected += len(expected)
        total_omissions += len(omitted)
        total_episodes += 1

        ep_near_miss = 0

        for om_action in omitted:
            # Find best match in performed (extra) actions
            best_name, best_sim = find_best_match(om_action, extra, args.min_sim)
            if best_name is not None:
                pair = (best_name, om_action)
                pair_counts[pair] += 1
                pair_models[pair].add(model)
                if pair not in pair_sims or best_sim > pair_sims[pair]:
                    pair_sims[pair] = best_sim
                ep_near_miss += 1
                total_near_miss_omissions += 1

        model_omissions[model] += len(omitted)
        model_near_miss[model] += ep_near_miss

        if ep_near_miss > 0:
            episodes_with_near_miss += 1

    print(f"  Done. {total_episodes} episodes processed.\n")

    # ── Phase 2: Analyze and rank pairs ──
    print("[STEP 2] Ranking near-miss pairs by frequency...")

    ranked_pairs = []
    for (performed, expected), count in pair_counts.most_common():
        sim = pair_sims[(performed, expected)]
        models = sorted(pair_models[(performed, expected)])
        ranked_pairs.append(
            {
                "performed": performed,
                "expected": expected,
                "similarity": round(sim, 3),
                "episode_count": count,
                "model_count": len(models),
                "models": models,
            }
        )

    # ── Phase 3: Similarity tier analysis ──
    tiers = {
        "0.90+": {"min": 0.90, "max": 1.01, "pairs": 0, "episodes": 0},
        "0.80-0.90": {"min": 0.80, "max": 0.90, "pairs": 0, "episodes": 0},
        "0.70-0.80": {"min": 0.70, "max": 0.80, "pairs": 0, "episodes": 0},
        "0.60-0.70": {"min": 0.60, "max": 0.70, "pairs": 0, "episodes": 0},
        "0.50-0.60": {"min": 0.50, "max": 0.60, "pairs": 0, "episodes": 0},
    }

    for rp in ranked_pairs:
        for tier_name, tier in tiers.items():
            if tier["min"] <= rp["similarity"] < tier["max"]:
                tier["pairs"] += 1
                tier["episodes"] += rp["episode_count"]
                break

    # ── Phase 4: Projected impact ──
    # If we fix all pairs with sim >= threshold, how many omissions removed?
    thresholds = [0.9, 0.8, 0.7, 0.6, 0.5]
    impact = {}
    for thresh in thresholds:
        removable = sum(rp["episode_count"] for rp in ranked_pairs if rp["similarity"] >= thresh)
        impact[str(thresh)] = {
            "removable_omissions": removable,
            "remaining_omissions": total_omissions - removable,
            "omission_rate_before": round(total_omissions / total_expected, 4) if total_expected > 0 else 0,
            "omission_rate_after": round((total_omissions - removable) / total_expected, 4)
            if total_expected > 0
            else 0,
            "reduction_pct": round(removable / total_omissions * 100, 1) if total_omissions > 0 else 0,
            "pairs_to_fix": sum(1 for rp in ranked_pairs if rp["similarity"] >= thresh),
        }

    # ── Phase 5: Generate normalizer alias suggestions ──
    # High-confidence pairs (sim >= 0.7) sorted by impact
    aliases = []
    for rp in ranked_pairs:
        if rp["similarity"] >= 0.7:
            aliases.append(
                {
                    "from": rp["performed"],
                    "to": rp["expected"],
                    "similarity": rp["similarity"],
                    "impact": rp["episode_count"],
                }
            )

    # ── Report ──
    lines = []
    lines.append("=" * 80)
    lines.append("FULL NORMALIZER GAP QUANTIFICATION")
    lines.append("=" * 80)

    lines.append("\n## Overview")
    lines.append(f"  Episodes analyzed: {total_episodes}")
    lines.append(f"  Total expected actions: {total_expected}")
    lines.append(f"  Total omitted actions: {total_omissions}")
    lines.append(f"  Near-miss omissions (sim>={args.min_sim}): {total_near_miss_omissions}")
    lines.append(
        f"  Near-miss rate: {total_near_miss_omissions / total_omissions * 100:.1f}%" if total_omissions > 0 else ""
    )
    lines.append(
        f"  Episodes with near-miss: {episodes_with_near_miss}/{total_episodes} ({episodes_with_near_miss / total_episodes * 100:.1f}%)"
    )
    lines.append(f"  Unique (performed, expected) pairs: {len(ranked_pairs)}")

    lines.append("\n## Similarity Tier Distribution")
    lines.append(f"  {'Tier':<12} {'Pairs':>6} {'Episodes':>10} {'% of near-miss':>15}")
    lines.append(f"  {'-' * 12} {'-' * 6} {'-' * 10} {'-' * 15}")
    for tier_name, tier in tiers.items():
        pct = tier["episodes"] / total_near_miss_omissions * 100 if total_near_miss_omissions > 0 else 0
        lines.append(f"  {tier_name:<12} {tier['pairs']:>6} {tier['episodes']:>10} {pct:>14.1f}%")

    lines.append("\n## Projected Impact by Fix Threshold")
    lines.append(
        f"  {'Threshold':>10} {'Pairs':>6} {'Remove':>8} {'Remain':>8} {'Rate Before':>12} {'Rate After':>11} {'Reduction':>10}"
    )
    lines.append(f"  {'-' * 10} {'-' * 6} {'-' * 8} {'-' * 8} {'-' * 12} {'-' * 11} {'-' * 10}")
    for thresh in thresholds:
        d = impact[str(thresh)]
        lines.append(
            f"  {thresh:>10.1f} {d['pairs_to_fix']:>6} {d['removable_omissions']:>8} "
            f"{d['remaining_omissions']:>8} {d['omission_rate_before']:>11.1%} "
            f"{d['omission_rate_after']:>10.1%} {d['reduction_pct']:>9.1f}%"
        )

    lines.append("\n## Per-Model Breakdown")
    lines.append(f"  {'Model':<15} {'Episodes':>8} {'Omissions':>10} {'Near-miss':>10} {'NM rate':>8}")
    lines.append(f"  {'-' * 15} {'-' * 8} {'-' * 10} {'-' * 10} {'-' * 8}")
    for model in sorted(model_episodes.keys()):
        nm_rate = model_near_miss[model] / model_omissions[model] * 100 if model_omissions[model] > 0 else 0
        lines.append(
            f"  {model:<15} {model_episodes[model]:>8} {model_omissions[model]:>10} "
            f"{model_near_miss[model]:>10} {nm_rate:>7.1f}%"
        )

    lines.append("\n## Top 50 Near-Miss Pairs (by episode count)")
    lines.append(f"  {'#':>3} {'Performed':<45} {'Expected':<45} {'Sim':>5} {'Count':>6} {'Models':>3}")
    lines.append(f"  {'-' * 3} {'-' * 45} {'-' * 45} {'-' * 5} {'-' * 6} {'-' * 3}")
    for i, rp in enumerate(ranked_pairs[:50]):
        lines.append(
            f"  {i + 1:>3} {rp['performed']:<45} {rp['expected']:<45} "
            f"{rp['similarity']:>5.2f} {rp['episode_count']:>6} {rp['model_count']:>3}"
        )

    lines.append(f"\n## High-Confidence Aliases to Add (sim >= 0.7, {len(aliases)} pairs)")
    for a in aliases[:40]:
        lines.append(f'  "{a["from"]}" → "{a["to"]}"  (sim={a["similarity"]:.2f}, impact={a["impact"]} episodes)')

    report_text = "\n".join(lines)
    print(report_text)

    # Save outputs
    report_path = output_dir / "normalizer_gap_full.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"\n[SAVED] {report_path}")

    results = {
        "overview": {
            "total_episodes": total_episodes,
            "total_expected": total_expected,
            "total_omissions": total_omissions,
            "near_miss_omissions": total_near_miss_omissions,
            "near_miss_rate": round(total_near_miss_omissions / total_omissions, 4) if total_omissions > 0 else 0,
            "unique_pairs": len(ranked_pairs),
        },
        "tiers": {k: {"pairs": v["pairs"], "episodes": v["episodes"]} for k, v in tiers.items()},
        "impact_by_threshold": impact,
        "per_model": {
            model: {
                "episodes": model_episodes[model],
                "omissions": model_omissions[model],
                "near_miss": model_near_miss[model],
            }
            for model in sorted(model_episodes.keys())
        },
        "all_pairs": ranked_pairs,
        "high_confidence_aliases": aliases,
    }
    with open(output_dir / "normalizer_gap_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"[SAVED] {output_dir / 'normalizer_gap_results.json'}")

    # Save alias list for direct use in normalizer fix
    with open(output_dir / "aliases_to_add.json", "w") as f:
        json.dump(aliases, f, indent=2)
    print(f"[SAVED] {output_dir / 'aliases_to_add.json'}")


if __name__ == "__main__":
    main()
