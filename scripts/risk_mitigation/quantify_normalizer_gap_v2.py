#!/usr/bin/env python3
"""Normalizer Gap v2: Post-Normalization Residual
================================================
v1은 raw action_id를 비교했지만, 실제 ViolationExtractor는
양쪽을 ActionNormalizer로 정규화한 뒤 비교한다.

이 스크립트는 normalizer를 적용한 후에도 남는 진짜 gap만 측정한다.

Usage:
    PYTHONPATH=. python scripts/risk_mitigation/quantify_normalizer_gap_v2.py
"""

import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import json
from pathlib import Path

from cga_bench.assessor_core.action_normalizer import get_default_normalizer


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


def extract_sets_normalized(ep: dict, normalizer) -> tuple:
    """Extract performed and expected, both normalized."""
    performed_raw = set()
    performed_norm = set()
    actions = ep.get("actions", [])
    if isinstance(actions, list):
        for a in actions:
            if isinstance(a, dict):
                name = a.get("action_id", a.get("action", "")).lower().strip()
                if name:
                    performed_raw.add(name)
                    performed_norm.add(normalizer.normalize(name))

    expected_raw = set()
    expected_norm = set()
    exp_list = ep.get("expected_actions", ep.get("mandatory_actions", []))
    if isinstance(exp_list, list):
        for a in exp_list:
            if isinstance(a, str):
                name = a.lower().strip()
            elif isinstance(a, dict):
                name = a.get("action_id", a.get("action", "")).lower().strip()
            else:
                continue
            if name:
                expected_raw.add(name)
                expected_norm.add(normalizer.normalize(name))

    return performed_raw, performed_norm, expected_raw, expected_norm


def find_best_match(action: str, candidates: set, min_sim: float = 0.5) -> tuple:
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
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    normalizer = get_default_normalizer()

    print("=" * 70)
    print("NORMALIZER GAP v2: POST-NORMALIZATION RESIDUAL")
    print("=" * 70)

    episodes = load_episodes(args.episodes_dir)
    print(f"[INFO] {len(episodes)} episodes loaded")

    # ── Compare raw vs normalized gaps ──
    print("\n[STEP 1] Scanning with normalization...")

    raw_total_omissions = 0
    norm_total_omissions = 0
    total_expected = 0
    resolved_by_normalizer = 0

    # Residual near-miss pairs (post-normalization)
    residual_pair_counts = Counter()
    residual_pair_sims = {}
    residual_pair_models = defaultdict(set)

    # Per-model stats
    model_raw_omissions = Counter()
    model_norm_omissions = Counter()
    model_episodes = Counter()

    for i, ep in enumerate(episodes):
        if i % 2000 == 0 and i > 0:
            print(f"  ... processed {i}/{len(episodes)}")

        performed_raw, performed_norm, expected_raw, expected_norm = extract_sets_normalized(ep, normalizer)
        model = ep.get("_model", "unknown")
        model_episodes[model] += 1

        # Raw comparison (what v1 measured)
        raw_omitted = expected_raw - performed_raw
        raw_total_omissions += len(raw_omitted)

        # Normalized comparison (what ViolationExtractor does)
        norm_omitted_set = expected_norm - performed_norm
        # Map back: which raw expected actions remain omitted after normalization?
        norm_omitted_raw = set()
        for exp_r in expected_raw:
            exp_n = normalizer.normalize(exp_r)
            if exp_n not in performed_norm:
                norm_omitted_raw.add(exp_r)

        norm_total_omissions += len(norm_omitted_raw)
        total_expected += len(expected_raw)

        resolved = len(raw_omitted) - len(norm_omitted_raw)
        resolved_by_normalizer += max(0, resolved)

        model_raw_omissions[model] += len(raw_omitted)
        model_norm_omissions[model] += len(norm_omitted_raw)

        # Find residual near-misses (post-normalization)
        extra_norm = performed_norm - expected_norm
        for om_action in norm_omitted_raw:
            om_norm = normalizer.normalize(om_action)
            best_name, best_sim = find_best_match(om_norm, extra_norm, 0.5)
            if best_name is not None:
                pair = (best_name, om_norm)
                residual_pair_counts[pair] += 1
                residual_pair_models[pair].add(model)
                if pair not in residual_pair_sims or best_sim > residual_pair_sims[pair]:
                    residual_pair_sims[pair] = best_sim

    print("  Done.\n")

    # ── Report ──
    lines = []
    lines.append("=" * 80)
    lines.append("NORMALIZER GAP v2: POST-NORMALIZATION RESIDUAL")
    lines.append("=" * 80)

    lines.append("\n## Normalization Impact")
    lines.append(f"  Total expected actions: {total_expected}")
    lines.append(f"  Raw omissions (before normalizer): {raw_total_omissions}")
    lines.append(f"  Norm omissions (after normalizer): {norm_total_omissions}")
    lines.append(f"  Resolved by normalizer: {resolved_by_normalizer}")
    raw_rate = raw_total_omissions / total_expected if total_expected else 0
    norm_rate = norm_total_omissions / total_expected if total_expected else 0
    lines.append(f"  Raw omission rate: {raw_rate:.1%}")
    lines.append(f"  Norm omission rate: {norm_rate:.1%}")
    lines.append(f"  Reduction: {raw_rate - norm_rate:.1%} ({resolved_by_normalizer} actions)")

    # Residual near-misses
    ranked_residual = []
    for (perf_norm, exp_norm), count in residual_pair_counts.most_common():
        sim = residual_pair_sims[(perf_norm, exp_norm)]
        models = sorted(residual_pair_models[(perf_norm, exp_norm)])
        ranked_residual.append(
            {
                "performed_norm": perf_norm,
                "expected_norm": exp_norm,
                "similarity": round(sim, 3),
                "episode_count": count,
                "model_count": len(models),
                "models": models,
            }
        )

    total_residual_nm = sum(r["episode_count"] for r in ranked_residual)
    lines.append("\n## Residual Near-Misses (post-normalization, sim>=0.5)")
    lines.append(f"  Unique pairs: {len(ranked_residual)}")
    lines.append(f"  Total episode-actions: {total_residual_nm}")
    lines.append(
        f"  Residual NM rate: {total_residual_nm / norm_total_omissions * 100:.1f}%"
        if norm_total_omissions
        else "  N/A"
    )

    # Tier distribution
    tiers = {"0.90+": 0, "0.80-0.90": 0, "0.70-0.80": 0, "0.60-0.70": 0, "0.50-0.60": 0}
    for r in ranked_residual:
        s = r["similarity"]
        if s >= 0.9:
            tiers["0.90+"] += r["episode_count"]
        elif s >= 0.8:
            tiers["0.80-0.90"] += r["episode_count"]
        elif s >= 0.7:
            tiers["0.70-0.80"] += r["episode_count"]
        elif s >= 0.6:
            tiers["0.60-0.70"] += r["episode_count"]
        else:
            tiers["0.50-0.60"] += r["episode_count"]

    lines.append("\n  Similarity tier distribution:")
    for tier, count in tiers.items():
        lines.append(f"    {tier}: {count} episode-actions")

    # Per-model
    lines.append("\n## Per-Model Comparison (Raw vs Normalized Omissions)")
    lines.append(
        f"  {'Model':<15} {'Episodes':>8} {'Raw Om':>8} {'Norm Om':>8} {'Resolved':>9} {'Raw Rate':>9} {'Norm Rate':>10}"
    )
    lines.append(f"  {'-' * 15} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 9} {'-' * 9} {'-' * 10}")
    for model in sorted(model_episodes.keys()):
        raw_om = model_raw_omissions[model]
        norm_om = model_norm_omissions[model]
        resolved = raw_om - norm_om
        # Approximate per-model expected (assume uniform)
        lines.append(
            f"  {model:<15} {model_episodes[model]:>8} {raw_om:>8} {norm_om:>8} {resolved:>9} {'':>9} {'':>10}"
        )

    # Top 50 residual pairs
    lines.append("\n## Top 50 Residual Near-Miss Pairs (THESE are the real normalizer gaps)")
    lines.append(f"  {'#':>3} {'Performed (normalized)':<45} {'Expected (normalized)':<45} {'Sim':>5} {'Count':>6}")
    lines.append(f"  {'-' * 3} {'-' * 45} {'-' * 45} {'-' * 5} {'-' * 6}")
    for i, r in enumerate(ranked_residual[:50]):
        lines.append(
            f"  {i + 1:>3} {r['performed_norm']:<45} {r['expected_norm']:<45} "
            f"{r['similarity']:>5.2f} {r['episode_count']:>6}"
        )

    # High-confidence residual aliases (>= 0.7)
    high_conf = [r for r in ranked_residual if r["similarity"] >= 0.7]
    lines.append(f"\n## High-Confidence Residual Aliases (sim >= 0.7, {len(high_conf)} pairs)")
    for r in high_conf[:30]:
        lines.append(
            f'  "{r["performed_norm"]}" → "{r["expected_norm"]}"  (sim={r["similarity"]:.2f}, {r["episode_count"]} episodes)'
        )

    report_text = "\n".join(lines)
    print(report_text)

    # Save
    report_path = output_dir / "normalizer_gap_v2_residual.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"\n[SAVED] {report_path}")

    results = {
        "normalization_impact": {
            "total_expected": total_expected,
            "raw_omissions": raw_total_omissions,
            "norm_omissions": norm_total_omissions,
            "resolved_by_normalizer": resolved_by_normalizer,
            "raw_rate": round(raw_rate, 4),
            "norm_rate": round(norm_rate, 4),
        },
        "residual_near_misses": {
            "unique_pairs": len(ranked_residual),
            "total_episode_actions": total_residual_nm,
            "tiers": tiers,
        },
        "all_residual_pairs": ranked_residual,
        "high_confidence_aliases": high_conf,
    }
    with open(output_dir / "normalizer_gap_v2_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"[SAVED] {output_dir / 'normalizer_gap_v2_results.json'}")


if __name__ == "__main__":
    main()
