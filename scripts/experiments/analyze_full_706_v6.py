#!/usr/bin/env python3
"""Final aggregate over the post-aliasfix full_706 re-sweep (v6).

Produces per-model termination_reason breakdown + mean CS / mean actions,
plus the v5→v6 comparison table the paper needs (the labelling split +
alias-map fix jointly shift the numbers; we need both deltas on record).
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path


MODELS = [
    "qwen4b_react",
    "qwen27b_react",
    "qwen35b_react",
    "gemma31b_react",
    "oss120b_react",
    "deepseek_r1_7b",
    "nemotron30b_react",
    "qwen397b_react",
]


def iter_episodes(model_dir: Path):
    for p in model_dir.glob("*.json"):
        if p.name.startswith("checkpoint") or p.name.startswith("model_summary"):
            continue
        try:
            yield json.loads(p.read_text())
        except Exception:
            continue


def analyse(results_root: Path) -> dict:
    summary = {}
    for m in MODELS:
        d = results_root / m
        if not d.is_dir():
            continue
        terms = Counter()
        cs = []
        actions = []
        tokens = []
        uniq_ids = set()
        duration = []
        for ep in iter_episodes(d):
            terms[ep.get("termination_reason", "?")] += 1
            cs.append(ep.get("compliance_score", 0))
            actions.append(ep.get("actions_count", 0))
            tokens.append(ep.get("total_tokens", 0))
            duration.append(ep.get("total_duration_minutes", 0))
            uniq_ids.add(f'{ep.get("scenario_id")}_r{ep.get("run_index", 0)}')
        n = len(cs)
        if n == 0:
            continue
        summary[m] = {
            "n": n,
            "unique_scenarios_x_runs": len(uniq_ids),
            "duplicate_count": n - len(uniq_ids),
            "mean_compliance_score": sum(cs) / n,
            "mean_actions": sum(actions) / n,
            "mean_tokens": sum(tokens) / n,
            "mean_duration_min": sum(duration) / n,
            "terminations": dict(terms),
            "termination_pct": {k: v / n * 100 for k, v in terms.items()},
        }
    return summary


def print_table(summary: dict) -> None:
    print(
        f'{"model":22s} | {"n":>5s} | {"dup":>4s} | '
        f'{"agent_exh%":>10s} | {"agent_com%":>10s} | {"consec_e%":>9s} | '
        f'{"timeout%":>9s} | {"disp%":>7s} | {"other%":>7s} | '
        f'{"CS":>6s} | {"acts":>5s}'
    )
    print("-" * 132)
    for m, s in summary.items():
        pct = s["termination_pct"]
        ae = pct.get("agent_exhausted", 0)
        ac = pct.get("agent_completed", 0)
        ce = pct.get("consecutive_empty_actions", 0)
        to = pct.get("timeout", 0)
        dp = pct.get("disposition_decided", 0)
        other = 100.0 - (ae + ac + ce + to + dp)
        print(
            f'{m:22s} | {s["n"]:5d} | {s["duplicate_count"]:4d} | '
            f'{ae:9.1f}% | {ac:9.1f}% | {ce:8.1f}% | '
            f'{to:8.1f}% | {dp:6.1f}% | {other:6.1f}% | '
            f'{s["mean_compliance_score"]:.3f} | {s["mean_actions"]:5.1f}'
        )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("results_dir", type=Path, help="e.g. results/full_706_v6_aliasfix_...")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args()
    summary = analyse(args.results_dir)
    print_table(summary)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True))
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
