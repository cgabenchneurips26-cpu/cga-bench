#!/usr/bin/env python3
"""S1 ActionNormalizer drift test (Test B-lite).

Test A confirmed HarmScorer.compute_score(violations, episode) is
invariant between Apr 28 and May 4 (delta = 0 for all 706 episodes).
That covers commit 3817bed6.

Test B-lite: Apply current ActionNormalizer to every action_id in S1
traces and check whether N3/N4/N5 alias additions in commit 2fbb3da0
would have changed normalization for any action that S1 actually
emitted. If S1 never emitted `order_imaging_ecg` / `endocrinology_consult`
/ `check_creatinine` / `order_lab_creatinine`, then commit 2fbb3da0
has zero effect on S1 episodes (and would only affect S2/S3/S4 if those
models emit those specific aliases).
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
import time

REPO = Path("/home/anonymous-org/anonymous-project/AnonProject")
sys.path.insert(0, str(REPO))

from cga_bench.assessor_core.action_normalizer import ActionNormalizer

# Aliases added/changed by commit 2fbb3da0 (May 1)
N1_N5_KEYS = {
    "order_imaging_ecg",  # N5: new alias -> order_ecg
    "endocrinology_consult",  # N3: new alias -> consult_endocrinology
    "check_creatinine",  # N4: direction reversed -> order_lab_creatinine
    "order_lab_creatinine",  # N4: was source, now target
    "order_creatinine",  # N4: was target, now intermediate
}


def main() -> int:
    s1_path = REPO / "cga_bench/evidence_pack/frontier/s1_sonnet.json"
    out_path = REPO / "cga_bench/reports/path_d_day3/s1_normalizer_drift.json"

    print(f"Loading S1: {s1_path}")
    with open(s1_path) as f:
        s1 = json.load(f)
    episodes = s1["episodes"]
    print(f"  episodes: {len(episodes)}")

    norm = ActionNormalizer()
    direct_mappings = norm.config.direct_mappings
    print(f"  current ActionNormalizer.config.direct_mappings: {len(direct_mappings)} entries")
    print()
    print("=== N1-N5 key check in current code ===")
    for k in sorted(N1_N5_KEYS):
        v = direct_mappings.get(k, "(not in mappings)")
        print(f"  '{k}' -> {v}")
    print()

    t0 = time.monotonic()
    total_actions = 0
    raw_action_id_counts: Counter[str] = Counter()
    affected_actions: list[dict] = []

    for ep in episodes:
        for a in ep["actions"]:
            aid = a["action_id"]
            total_actions += 1
            raw_action_id_counts[aid] += 1
            if aid in N1_N5_KEYS:
                affected_actions.append(
                    {
                        "scenario_id": ep["scenario_id"],
                        "action_id": aid,
                        "canonical_under_current": direct_mappings.get(aid, "(no mapping)"),
                    }
                )

    elapsed = time.monotonic() - t0

    # Among the top-100 most-emitted action_ids, how many are in N1-N5 keys?
    top_actions = raw_action_id_counts.most_common(100)
    top_affected = [(aid, n) for aid, n in top_actions if aid in N1_N5_KEYS]

    summary = {
        "test": "S1 ActionNormalizer drift (Test B-lite, commit 2fbb3da0 N1-N5)",
        "n_episodes": len(episodes),
        "total_actions_emitted": total_actions,
        "n_unique_action_ids": len(raw_action_id_counts),
        "n_actions_affected_by_N1_N5": len(affected_actions),
        "pct_actions_affected": round(100 * len(affected_actions) / total_actions, 4),
        "current_code_n1_n5_mappings": {k: direct_mappings.get(k, "(missing)") for k in sorted(N1_N5_KEYS)},
        "top_30_emitted_action_ids": top_actions[:30],
        "top_actions_affected_by_N1_N5": top_affected,
        "all_affected_action_records": affected_actions[:50],
        "interpretation": (
            f"DRIFT: {len(affected_actions)} action(s) ({100 * len(affected_actions) / total_actions:.4f}%) "
            f"would normalize differently under current code"
            if affected_actions
            else "NO DRIFT: zero S1 actions match N1-N5 alias keys"
        ),
        "elapsed_seconds": round(elapsed, 3),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Report: {out_path}\n")

    print("=== ActionNormalizer DRIFT SUMMARY ===")
    print(f"  total actions emitted across 706 ep: {total_actions:,}")
    print(f"  unique action_ids: {len(raw_action_id_counts):,}")
    print(f"  actions matching N1-N5 keys: {len(affected_actions)}")
    print(f"  pct affected: {100 * len(affected_actions) / total_actions:.4f}%")
    print(f"  verdict: {summary['interpretation']}")
    if affected_actions:
        print()
        print("  affected breakdown:")
        c = Counter(a["action_id"] for a in affected_actions)
        for aid, n in c.most_common():
            print(f"    {aid}: {n} occurrence(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
