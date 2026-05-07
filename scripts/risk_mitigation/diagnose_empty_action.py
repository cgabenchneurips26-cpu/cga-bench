#!/usr/bin/env python3
"""
v6 Pre-flight Diagnostic: Empty Action Root Cause Analysis
Run BEFORE committing to full 9-model re-execution.

Usage: python diagnose_empty_actions.py --data_dir results/full_706_v5/
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ============================================================
# 1. v5 로그에서 empty action 원인 분류
# ============================================================

def classify_empty_cause(raw_output: str) -> str:
    """Classify why a step produced an empty action."""
    if not raw_output or raw_output.strip() == "":
        return "EMPTY_RESPONSE"  # LLM returned nothing
    
    # Check for <think> block
    has_think = bool(re.search(r'<think>.*?</think>', raw_output, re.DOTALL))
    
    # Check for JSON presence
    has_json = bool(re.search(r'\{[^}]*"action"[^}]*\}', raw_output, re.DOTALL))
    has_any_json = bool(re.search(r'\{.*\}', raw_output, re.DOTALL))
    
    # Strip think and re-check
    stripped = re.sub(r'<think>.*?</think>', '', raw_output, flags=re.DOTALL).strip()
    has_json_after_strip = bool(re.search(r'\{[^}]*"action"[^}]*\}', stripped, re.DOTALL))
    
    if has_think and not has_json and has_json_after_strip:
        return "THINK_BLOCKED_JSON"  # <think> prevented JSON extraction
    elif has_think and not has_json and not has_json_after_strip:
        return "THINK_NO_JSON"  # <think> present but no valid JSON anywhere
    elif not has_think and has_any_json and not has_json:
        return "MALFORMED_JSON"  # JSON present but no "action" field
    elif not has_think and not has_any_json:
        return "NO_JSON_AT_ALL"  # Plain text, no JSON
    elif has_json:
        return "JSON_PRESENT_BUT_EMPTY"  # JSON with "action": "" or null
    else:
        return "OTHER"


def analyze_model_logs(data_dir: str, model: str) -> dict:
    """Analyze empty action causes for a single model."""
    model_dir = Path(data_dir) / model
    if not model_dir.exists():
        return {"error": f"Directory not found: {model_dir}"}
    
    results = {
        "model": model,
        "total_episodes": 0,
        "total_steps": 0,
        "empty_steps": 0,
        "cause_counts": Counter(),
        "episodes_with_empty": 0,
        "consecutive_empty_terminated": 0,
        "sample_outputs": defaultdict(list),  # cause → [first 3 raw outputs]
    }
    
    for ep_file in sorted(model_dir.glob("*.json")):
        try:
            with open(ep_file) as f:
                ep = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        
        results["total_episodes"] += 1
        ep_has_empty = False
        consecutive_empty = 0
        max_consecutive = 0
        
        steps = ep.get("steps", ep.get("trajectory", []))
        for step in steps:
            results["total_steps"] += 1
            
            action = step.get("action", step.get("normalized_action", ""))
            raw = step.get("raw_output", step.get("llm_response", ""))
            
            if not action or action.strip() == "" or action == "NO_ACTION":
                results["empty_steps"] += 1
                ep_has_empty = True
                consecutive_empty += 1
                max_consecutive = max(max_consecutive, consecutive_empty)
                
                cause = classify_empty_cause(raw)
                results["cause_counts"][cause] += 1
                
                # Save first 3 samples per cause (truncated)
                if len(results["sample_outputs"][cause]) < 3:
                    results["sample_outputs"][cause].append(
                        raw[:200] if raw else "(empty)"
                    )
            else:
                consecutive_empty = 0
        
        if ep_has_empty:
            results["episodes_with_empty"] += 1
        
        # Check if episode terminated due to consecutive empties
        if max_consecutive >= 3:  # 3+ consecutive empties = likely premature termination
            results["consecutive_empty_terminated"] += 1
    
    return results


def print_diagnosis(results: dict):
    """Pretty-print diagnosis results."""
    if "error" in results:
        print(f"  ERROR: {results['error']}")
        return
    
    model = results["model"]
    total_ep = results["total_episodes"]
    total_steps = results["total_steps"]
    empty = results["empty_steps"]
    rate = (empty / total_steps * 100) if total_steps > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"  {model}")
    print(f"{'='*60}")
    print(f"  Episodes: {total_ep}")
    print(f"  Total steps: {total_steps}")
    print(f"  Empty steps: {empty} ({rate:.1f}%)")
    print(f"  Episodes with ≥1 empty: {results['episodes_with_empty']} "
          f"({results['episodes_with_empty']/total_ep*100:.1f}%)" if total_ep > 0 else "")
    print(f"  Consecutive-empty terminated: {results['consecutive_empty_terminated']} "
          f"({results['consecutive_empty_terminated']/total_ep*100:.1f}%)" if total_ep > 0 else "")
    
    print(f"\n  Root Cause Breakdown:")
    for cause, count in results["cause_counts"].most_common():
        pct = count / empty * 100 if empty > 0 else 0
        print(f"    {cause:30s}: {count:5d} ({pct:5.1f}%)")
        # Print first sample
        if results["sample_outputs"][cause]:
            sample = results["sample_outputs"][cause][0]
            print(f"      Sample: {sample[:100]}...")
    
    # Diagnosis
    print(f"\n  Diagnosis:")
    causes = results["cause_counts"]
    think_related = causes.get("THINK_BLOCKED_JSON", 0) + causes.get("THINK_NO_JSON", 0)
    json_related = causes.get("MALFORMED_JSON", 0) + causes.get("NO_JSON_AT_ALL", 0)
    
    if think_related > json_related:
        print(f"    → PRIMARY: <think> block interference ({think_related}/{empty})")
        print(f"    → FIX: <think> strip should resolve most issues")
    elif json_related > think_related:
        print(f"    → PRIMARY: JSON generation failure ({json_related}/{empty})")
        print(f"    → FIX: May need structured output enforcement or retry logic")
    else:
        print(f"    → MIXED: Both <think> ({think_related}) and JSON ({json_related}) issues")
    
    if causes.get("EMPTY_RESPONSE", 0) > empty * 0.1:
        print(f"    → WARNING: {causes['EMPTY_RESPONSE']} empty responses — possible vLLM timeout/OOM")


# ============================================================
# 2. v6 첫 에피소드 비교 (fix 효과 확인)
# ============================================================

def compare_v5_v6(v5_dir: str, v6_dir: str, model: str):
    """Compare first few episodes between v5 and v6."""
    v5_results = analyze_model_logs(v5_dir, model)
    v6_results = analyze_model_logs(v6_dir, model)
    
    if "error" in v5_results or "error" in v6_results:
        print(f"  Cannot compare: v5={v5_results.get('error','ok')}, v6={v6_results.get('error','ok')}")
        return
    
    v5_rate = v5_results["empty_steps"] / v5_results["total_steps"] * 100 if v5_results["total_steps"] > 0 else 0
    v6_rate = v6_results["empty_steps"] / v6_results["total_steps"] * 100 if v6_results["total_steps"] > 0 else 0
    
    print(f"\n  v5 vs v6 Comparison for {model}:")
    print(f"    v5: {v5_results['empty_steps']}/{v5_results['total_steps']} empty ({v5_rate:.1f}%)")
    print(f"    v6: {v6_results['empty_steps']}/{v6_results['total_steps']} empty ({v6_rate:.1f}%)")
    print(f"    Δ: {v6_rate - v5_rate:+.1f} pp")


# ============================================================
# 3. enable_thinking 설정 확인
# ============================================================

def check_vllm_config():
    """Check if enable_thinking is set in vLLM config."""
    config_paths = [
        "configs/vllm_config.yaml",
        "configs/model_configs.yaml", 
        "cpg_model/llm_provider.py",
        "run_episodes.py",
    ]
    
    print(f"\n{'='*60}")
    print(f"  enable_thinking Configuration Check")
    print(f"{'='*60}")
    
    for path in config_paths:
        if os.path.exists(path):
            with open(path) as f:
                content = f.read()
            if "enable_thinking" in content or "thinking" in content.lower():
                lines = [l.strip() for l in content.split('\n') 
                         if 'thinking' in l.lower() and not l.strip().startswith('#')]
                for line in lines[:5]:
                    print(f"  {path}: {line}")
            else:
                print(f"  {path}: no 'thinking' setting found")
        else:
            print(f"  {path}: file not found")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--v5_dir", default="results/full_706_v5/", help="v5 episode directory")
    parser.add_argument("--v6_dir", default="results/full_706_v6/", help="v6 episode directory")
    parser.add_argument("--models", nargs="*", 
                        default=["qwen4b", "qwen397b", "qwen27b", "qwen35b", 
                                 "nemotron30b", "gemma31b", "oss120b",
                                 "deepseek_r1_7b", "biomed8b"])
    args = parser.parse_args()
    
    print("=" * 60)
    print("  CGA-Bench v6 Pre-flight Diagnostic")
    print("  Empty Action Root Cause Analysis")
    print("=" * 60)
    
    # Phase 1: v5 root cause analysis
    print("\n\n" + "=" * 60)
    print("  PHASE 1: v5 Root Cause Analysis (per model)")
    print("=" * 60)
    
    all_results = {}
    for model in args.models:
        results = analyze_model_logs(args.v5_dir, model)
        all_results[model] = results
        print_diagnosis(results)
    
    # Phase 2: v6 comparison (if v6 episodes exist)
    if os.path.exists(args.v6_dir):
        print("\n\n" + "=" * 60)
        print("  PHASE 2: v5 vs v6 Comparison")
        print("=" * 60)
        
        for model in args.models:
            v6_model_dir = Path(args.v6_dir) / model
            if v6_model_dir.exists() and any(v6_model_dir.glob("*.json")):
                compare_v5_v6(args.v5_dir, args.v6_dir, model)
            else:
                print(f"\n  {model}: No v6 episodes yet")
    
    # Phase 3: Config check
    check_vllm_config()
    
    # Phase 4: Summary & Recommendation
    print("\n\n" + "=" * 60)
    print("  SUMMARY & RECOMMENDATION")
    print("=" * 60)
    
    for model in args.models:
        r = all_results.get(model, {})
        if "error" in r:
            continue
        causes = r.get("cause_counts", {})
        think = causes.get("THINK_BLOCKED_JSON", 0) + causes.get("THINK_NO_JSON", 0)
        json_fail = causes.get("MALFORMED_JSON", 0) + causes.get("NO_JSON_AT_ALL", 0)
        empty_resp = causes.get("EMPTY_RESPONSE", 0)
        total_empty = r.get("empty_steps", 0)
        
        fix_status = "✅ <think> strip sufficient" if think > json_fail else \
                     "⚠️ JSON failure dominant — may need additional fix" if json_fail > think else \
                     "🟡 Mixed causes"
        
        if empty_resp > total_empty * 0.3:
            fix_status += " + ⚠️ HIGH empty response rate"
        
        print(f"  {model:20s}: {fix_status}")