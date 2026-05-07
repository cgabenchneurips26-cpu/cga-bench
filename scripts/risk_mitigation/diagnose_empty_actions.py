#!/usr/bin/env python3
"""Diagnose empty action root causes across all models.

Analyzes both episode JSON files and runner log files to classify
empty action causes into categories:

  1. THINK_BLOCK   — <think> tags confused JSON parser (DeepSeek-R1)
  2. JSON_MALFORM  — LLM produced malformed JSON (no <think>)
  3. EMPTY_RESPONSE — LLM returned empty/whitespace content
  4. RULE_FALLBACK  — LLM failed, rule-based also returned empty
  5. CLOCK_WASTE    — Empty actions that advanced simulated clock (old bug)

Usage:
    python diagnose_empty_actions.py --results_dir results/full_706_v5
    python diagnose_empty_actions.py --results_dir results/full_706_v5 --models qwen4b deepseek_r1_7b
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path


def analyze_logs(results_dir: Path, model: str) -> dict:
    """Analyze runner log files for a model."""
    stats = {
        "llm_empty_warns": 0,
        "json_repair_fails": 0,
        "json_parse_fails": 0,
        "http_200_ok": 0,
        "think_block_detected": 0,
        "rule_based_fallback": 0,
        "llm_stuck": 0,
    }

    # Collect all log files for this model
    log_files = list(results_dir.glob(f"log_{model}*.txt"))
    if not log_files:
        return stats

    for log_file in log_files:
        try:
            content = log_file.read_text(errors="replace")
        except OSError:
            continue

        for line in content.splitlines():
            if "LLM returned empty actions" in line:
                stats["llm_empty_warns"] += 1
            elif "JSON repair failed" in line:
                stats["json_repair_fails"] += 1
            elif "JSON parse attempt" in line and "failed" in line:
                stats["json_parse_fails"] += 1
            elif "HTTP/1.1 200 OK" in line:
                stats["http_200_ok"] += 1
            elif "<think>" in line.lower() or "think block" in line.lower():
                stats["think_block_detected"] += 1
            elif "falling back to rule-based" in line or "rule-based" in line.lower():
                stats["rule_based_fallback"] += 1
            elif "LLM stuck" in line:
                stats["llm_stuck"] += 1

    return stats


def analyze_episodes(model_dir: Path) -> dict:
    """Analyze episode JSON files for a model."""
    stats = {
        "total_episodes": 0,
        "consec_empty_term": 0,
        "agent_exhausted_term": 0,
        "agent_completed_term": 0,
        "timeout_term": 0,
        "completed_term": 0,
        "other_term": 0,
        "zero_action_episodes": 0,
        "low_action_episodes": 0,  # <= 3 actions
        "total_actions": 0,
        "total_llm_calls": 0,
        "total_tokens": 0,
        "avg_actions": 0.0,
        "avg_llm_calls": 0.0,
        "avg_tokens_per_call": 0.0,
        "avg_duration": 0.0,
        "total_duration": 0.0,
        "action_distribution": defaultdict(int),
    }

    files = [f for f in model_dir.glob("*.json") if not f.name.startswith(("checkpoint", "."))]
    if not files:
        return stats

    for f in files:
        try:
            ep = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        stats["total_episodes"] += 1
        actions_count = ep.get("actions_count", len(ep.get("actions", [])))
        llm_calls = ep.get("total_llm_calls", 0)
        tokens = ep.get("total_tokens", 0)
        duration = ep.get("total_duration_minutes", 0)
        term = ep.get("termination_reason", "unknown")

        stats["total_actions"] += actions_count
        stats["total_llm_calls"] += llm_calls
        stats["total_tokens"] += tokens
        stats["total_duration"] += duration

        if term == "consecutive_empty_actions":
            stats["consec_empty_term"] += 1
        elif term == "agent_exhausted":
            stats["agent_exhausted_term"] += 1
        elif term == "agent_completed":
            stats["agent_completed_term"] += 1
        elif term == "timeout":
            stats["timeout_term"] += 1
        elif term == "completed":
            stats["completed_term"] += 1
        else:
            stats["other_term"] += 1

        if actions_count == 0:
            stats["zero_action_episodes"] += 1
        elif actions_count <= 3:
            stats["low_action_episodes"] += 1

        # Bucket actions count
        bucket = f"{(actions_count // 5) * 5}-{(actions_count // 5) * 5 + 4}"
        stats["action_distribution"][bucket] += 1

    n = stats["total_episodes"]
    if n > 0:
        stats["avg_actions"] = stats["total_actions"] / n
        stats["avg_llm_calls"] = stats["total_llm_calls"] / n
        stats["avg_duration"] = stats["total_duration"] / n
        total_calls = stats["total_llm_calls"]
        if total_calls > 0:
            stats["avg_tokens_per_call"] = stats["total_tokens"] / total_calls

    return stats


def classify_empty_cause(log_stats: dict, ep_stats: dict, model: str) -> dict:
    """Classify the primary cause of empty actions for a model."""
    causes = {
        "primary_cause": "UNKNOWN",
        "confidence": "low",
        "details": "",
        "severity": "low",
        "fix_needed": "none",
    }

    total = ep_stats["total_episodes"]
    if total == 0:
        causes["primary_cause"] = "NO_DATA"
        return causes

    empty_rate = ep_stats["consec_empty_term"] / total
    zero_rate = ep_stats["zero_action_episodes"] / total
    json_fail_rate = log_stats["json_parse_fails"] / max(log_stats["http_200_ok"], 1)
    empty_warn_rate = log_stats["llm_empty_warns"] / max(log_stats["http_200_ok"], 1)

    # Classification logic
    is_reasoning_model = "deepseek" in model.lower() or "r1" in model.lower()

    if empty_rate > 0.9:
        causes["severity"] = "critical"
        if zero_rate > 0.8:
            causes["primary_cause"] = "EMPTY_RESPONSE"
            causes["confidence"] = "high"
            causes["details"] = (
                f"Model returns empty/unparseable content in {zero_rate:.0%} of episodes. "
                f"LLM empty warns: {log_stats['llm_empty_warns']}, "
                f"JSON fails: {log_stats['json_parse_fails']}"
            )
            causes["fix_needed"] = "simpler_prompt_or_model_replacement"
        else:
            causes["primary_cause"] = "RULE_FALLBACK"
            causes["confidence"] = "medium"
            causes["details"] = (
                f"LLM produces some actions but rule-based fallback returns empty. "
                f"Avg actions: {ep_stats['avg_actions']:.1f}"
            )
            causes["fix_needed"] = "improve_rule_based_fallback"

    elif empty_rate > 0.15:
        causes["severity"] = "high"
        if json_fail_rate > 0.1:
            if is_reasoning_model:
                causes["primary_cause"] = "THINK_BLOCK"
                causes["confidence"] = "high"
                causes["details"] = (
                    f"Reasoning model with {json_fail_rate:.1%} JSON parse failure rate. "
                    f"<think> blocks confuse brace matching."
                )
                causes["fix_needed"] = "think_strip (APPLIED)"
            else:
                causes["primary_cause"] = "JSON_MALFORM"
                causes["confidence"] = "high"
                causes["details"] = (
                    f"Non-reasoning model with {json_fail_rate:.1%} JSON parse failure rate. "
                    f"Model produces malformed JSON output."
                )
                causes["fix_needed"] = "stronger_json_enforcement_or_guided_decoding"
        elif empty_warn_rate > 0.1:
            causes["primary_cause"] = "EMPTY_RESPONSE"
            causes["confidence"] = "medium"
            causes["details"] = (
                f"LLM returns empty actions in {empty_warn_rate:.1%} of calls. "
                f"Likely model too weak for structured output."
            )
            causes["fix_needed"] = "prompt_simplification"
        else:
            causes["primary_cause"] = "RULE_FALLBACK"
            causes["confidence"] = "medium"
            causes["details"] = (
                f"Empty rate {empty_rate:.1%} but low JSON/empty warn rates. Rule-based fallback returning empty."
            )
            causes["fix_needed"] = "improve_rule_based_fallback"

    elif empty_rate > 0.01:
        causes["severity"] = "moderate"
        causes["primary_cause"] = "INTERMITTENT"
        causes["confidence"] = "medium"
        causes["details"] = f"Low empty rate ({empty_rate:.1%}). Likely edge-case scenarios or transient LLM failures."
        causes["fix_needed"] = "clock_fix_sufficient"

    else:
        causes["severity"] = "none"
        causes["primary_cause"] = "HEALTHY"
        causes["confidence"] = "high"
        causes["details"] = f"Empty rate {empty_rate:.1%}. No fix needed."
        causes["fix_needed"] = "none"

    # Clock waste analysis (all non-zero empty rates affected by old clock bug)
    if empty_rate > 0:
        wasted_min = ep_stats["consec_empty_term"] * 25  # 5 empties × 5 min each
        causes["clock_waste_minutes"] = wasted_min
        causes["clock_waste_per_episode"] = wasted_min / total

    return causes


def print_report(results_dir: Path, models: list[str] | None = None) -> dict:
    """Generate and print full diagnostic report."""
    if models is None:
        models = sorted([d.name for d in results_dir.iterdir() if d.is_dir() and not d.name.startswith(".")])

    report = {}

    # Header
    print("=" * 90)
    print("EMPTY ACTION DIAGNOSTIC REPORT")
    print(f"Results: {results_dir}")
    print("=" * 90)

    # Summary table
    print(
        f"\n{'Model':<18} {'Episodes':>8} {'Empty%':>7} {'Zero%':>6} "
        f"{'AvgAct':>7} {'JSONFail':>9} {'EmptyWarn':>10} {'Cause':<18} {'Severity':<10}"
    )
    print("-" * 105)

    for model in models:
        model_dir = results_dir / model
        if not model_dir.is_dir():
            continue

        log_stats = analyze_logs(results_dir, model)
        ep_stats = analyze_episodes(model_dir)
        cause = classify_empty_cause(log_stats, ep_stats, model)

        n = ep_stats["total_episodes"]
        if n == 0:
            continue

        empty_pct = ep_stats["consec_empty_term"] / n * 100
        zero_pct = ep_stats["zero_action_episodes"] / n * 100

        print(
            f"{model:<18} {n:>8} {empty_pct:>6.1f}% {zero_pct:>5.1f}% "
            f"{ep_stats['avg_actions']:>7.1f} {log_stats['json_parse_fails']:>9} "
            f"{log_stats['llm_empty_warns']:>10} {cause['primary_cause']:<18} {cause['severity']:<10}"
        )

        report[model] = {
            "log_stats": log_stats,
            "episode_stats": {k: v for k, v in ep_stats.items() if k != "action_distribution"},
            "action_distribution": dict(ep_stats["action_distribution"]),
            "diagnosis": cause,
        }

    # Detailed per-model analysis
    print("\n" + "=" * 90)
    print("DETAILED DIAGNOSIS")
    print("=" * 90)

    for model, data in report.items():
        diag = data["diagnosis"]
        ep = data["episode_stats"]
        log = data["log_stats"]

        print(f"\n--- {model} ---")
        print(f"  Primary cause:  {diag['primary_cause']} (confidence: {diag['confidence']})")
        print(f"  Severity:       {diag['severity']}")
        print(f"  Fix needed:     {diag['fix_needed']}")
        print(f"  Details:        {diag['details']}")
        print(
            f"  Episodes:       {ep['total_episodes']} (timeout: {ep['timeout_term']}, "
            f"consec_empty: {ep['consec_empty_term']}, completed: {ep['completed_term']})"
        )
        print(
            f"  Avg actions:    {ep['avg_actions']:.1f} | Avg LLM calls: {ep['avg_llm_calls']:.1f} "
            f"| Avg tok/call: {ep['avg_tokens_per_call']:.0f}"
        )
        print(f"  Avg duration:   {ep['avg_duration']:.1f} min")
        print(
            f"  Log signals:    HTTP 200={log['http_200_ok']}, empty_warn={log['llm_empty_warns']}, "
            f"json_fail={log['json_parse_fails']}, json_repair_fail={log['json_repair_fails']}, "
            f"rule_fallback={log['rule_based_fallback']}, llm_stuck={log['llm_stuck']}"
        )
        if "clock_waste_minutes" in diag:
            print(
                f"  Clock waste:    {diag['clock_waste_minutes']:.0f} total min "
                f"({diag['clock_waste_per_episode']:.1f} min/episode avg)"
            )

    # Action plan
    print("\n" + "=" * 90)
    print("ACTION PLAN")
    print("=" * 90)

    fix_groups = defaultdict(list)
    for model, data in report.items():
        fix = data["diagnosis"]["fix_needed"]
        sev = data["diagnosis"]["severity"]
        fix_groups[(fix, sev)].append(model)

    for (fix, sev), model_list in sorted(
        fix_groups.items(), key=lambda x: {"critical": 0, "high": 1, "moderate": 2, "low": 3, "none": 4}.get(x[0][1], 5)
    ):
        models_str = ", ".join(model_list)
        print(f"\n  [{sev.upper()}] {fix}")
        print(f"    Models: {models_str}")
        if fix == "think_strip (APPLIED)":
            print("    → Already fixed in current code. Re-run will resolve.")
        elif fix == "clock_fix_sufficient":
            print("    → Clock fix (no time advance on empty) is sufficient.")
        elif fix == "simpler_prompt_or_model_replacement":
            print("    → Model fundamentally too weak for structured output.")
            print("    → Options: (a) drastically simplified prompt, (b) guided decoding, (c) drop model")
        elif fix == "stronger_json_enforcement_or_guided_decoding":
            print("    → Consider vLLM guided_decoding_backend='outlines' for JSON schema enforcement")
        elif fix == "prompt_simplification":
            print("    → Reduce prompt complexity for small models")
        elif fix == "improve_rule_based_fallback":
            print("    → Rule-based fallback returns empty too often; add conservative default actions")
        elif fix == "none":
            print("    → No action needed.")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose empty action root causes")
    parser.add_argument(
        "--results_dir",
        type=Path,
        default=Path("results/full_706_v5"),
        help="Results directory",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        help="Specific models to analyze (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Save JSON report to file",
    )
    args = parser.parse_args()

    report = print_report(args.results_dir, args.models)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, default=str))
        print(f"\nJSON report saved to {args.output}")


if __name__ == "__main__":
    main()
