#!/usr/bin/env python3
"""
EX-34: Strict Consensus False-Accept Intersection
===================================================
Computes the strictest non-degenerate false-accept intersection:
  - strictFA3: ASC ∩ PAF ∩ CwT pass, TCC fail
  - strictFA4: TOM ∩ ASC ∩ PAF ∩ CwT pass, TCC fail (= strictFA3 since TOM=100%)

Input:  evidence_pack/analysis/verdict_matrix_v6.json
Output: evidence_pack/ex34_strict_fa/strict_fa.json + macros.tex
"""

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_verdict_matrix(path: str) -> list[dict]:
    """Load verdict matrix JSON."""
    with open(path) as f:
        data = json.load(f)
    # Handle both list format and dict-with-episodes format
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get("episodes", data.get("results", []))
    else:
        raise ValueError(f"Unexpected format in {path}")


def get_verdict(ep: dict, evaluator: str) -> str:
    """Extract pass/fail verdict for an evaluator. Returns 'pass' or 'fail'."""
    # Try multiple possible field structures
    verdicts = ep.get("verdicts", ep.get("evaluator_verdicts", {}))
    
    if isinstance(verdicts, dict):
        v = verdicts.get(evaluator, None)
        if v is None:
            # Try alternate names
            alt_names = {
                "TOM": ["DxEM", "dxem", "terminal", "tom"],
                "ASC": ["AC-Proxy", "ac_proxy", "AC", "asc"],
                "PAF": ["MAB-Proxy", "mab_proxy", "MAB", "paf"],
                "CwT": ["C2", "c2", "cwt", "C2 (>=0.7)"],
                "TCC": ["CGA-Bench", "cga_bench", "CGA", "tcc"],
            }
            for alt in alt_names.get(evaluator, []):
                v = verdicts.get(alt, None)
                if v is not None:
                    break
        
        if v is None:
            return "unknown"
        
        # Normalize to pass/fail
        if isinstance(v, bool):
            return "pass" if v else "fail"
        if isinstance(v, (int, float)):
            return "pass" if v > 0 else "fail"
        if isinstance(v, str):
            return "pass" if v.lower() in ("pass", "true", "1", "yes") else "fail"
    
    return "unknown"


def get_severity(ep: dict) -> str:
    """Extract violation severity."""
    sev = ep.get("severity", ep.get("max_severity", ep.get("violation_severity", "unknown")))
    if isinstance(sev, str):
        return sev.lower()
    return "unknown"


def get_domain(ep: dict) -> str:
    """Extract clinical domain."""
    return ep.get("domain", ep.get("graph", ep.get("guideline", "unknown")))


def get_n_violations(ep: dict) -> int:
    """Extract violation count."""
    return ep.get("n_violations", ep.get("n_hard_violations", 
           ep.get("hard_violation_count", 0)))


def compute_strict_fa(episodes: list[dict]) -> dict:
    """Compute all intersection variants."""
    
    total = len(episodes)
    
    # --- All-oblivious (current hero): TOM ∩ ASC ∩ CwT pass, TCC fail ---
    ao_fa = []
    for ep in episodes:
        tom = get_verdict(ep, "TOM")
        asc = get_verdict(ep, "ASC")
        cwt = get_verdict(ep, "CwT")
        tcc = get_verdict(ep, "TCC")
        
        if tom == "pass" and asc == "pass" and cwt == "pass" and tcc == "fail":
            ao_fa.append(ep)
    
    # --- Strict FA3: ASC ∩ PAF ∩ CwT pass, TCC fail ---
    strict3 = []
    for ep in episodes:
        asc = get_verdict(ep, "ASC")
        paf = get_verdict(ep, "PAF")
        cwt = get_verdict(ep, "CwT")
        tcc = get_verdict(ep, "TCC")
        
        if asc == "pass" and paf == "pass" and cwt == "pass" and tcc == "fail":
            strict3.append(ep)
    
    # --- Strict FA4: TOM ∩ ASC ∩ PAF ∩ CwT pass, TCC fail ---
    strict4 = []
    for ep in episodes:
        tom = get_verdict(ep, "TOM")
        asc = get_verdict(ep, "ASC")
        paf = get_verdict(ep, "PAF")
        cwt = get_verdict(ep, "CwT")
        tcc = get_verdict(ep, "TCC")
        
        if (tom == "pass" and asc == "pass" and paf == "pass" and 
            cwt == "pass" and tcc == "fail"):
            strict4.append(ep)
    
    # --- Analyze each set ---
    def analyze(fa_episodes, label):
        if not fa_episodes:
            return {"count": 0, "rate": 0.0, "critical_count": 0, 
                    "critical_pct": 0.0, "median_viols": 0,
                    "domain_breakdown": {}, "label": label}
        
        n = len(fa_episodes)
        rate = round(n / total * 100, 1)
        
        # Severity
        severities = Counter(get_severity(ep) for ep in fa_episodes)
        critical_count = severities.get("critical", 0)
        critical_pct = round(critical_count / n * 100, 1)
        
        # Violations
        viols = sorted(get_n_violations(ep) for ep in fa_episodes)
        median_viols = viols[len(viols) // 2] if viols else 0
        
        # Domain breakdown
        domains = Counter(get_domain(ep) for ep in fa_episodes)
        top_domains = dict(domains.most_common(5))
        
        return {
            "count": n,
            "rate": rate,
            "critical_count": critical_count,
            "critical_pct": critical_pct,
            "high_count": severities.get("high", 0),
            "medium_count": severities.get("medium", 0),
            "low_count": severities.get("low", 0),
            "median_viols": median_viols,
            "mean_viols": round(sum(viols) / max(len(viols), 1), 1),
            "domain_breakdown": top_domains,
            "severity_breakdown": dict(severities),
            "label": label,
        }
    
    ao_analysis = analyze(ao_fa, "all_oblivious_TOM_ASC_CwT")
    strict3_analysis = analyze(strict3, "strict3_ASC_PAF_CwT")
    strict4_analysis = analyze(strict4, "strict4_TOM_ASC_PAF_CwT")
    
    # --- PAF-only analysis: how many AO episodes does PAF filter? ---
    paf_filter = len(ao_fa) - len(strict4)
    paf_filter_pct = round(paf_filter / max(len(ao_fa), 1) * 100, 1)
    
    return {
        "total_episodes": total,
        "all_oblivious": ao_analysis,
        "strict_fa3": strict3_analysis,
        "strict_fa4": strict4_analysis,
        "paf_filters_out": paf_filter,
        "paf_filter_pct": paf_filter_pct,
        "note": "strict_fa3 == strict_fa4 when TOM pass rate is 100%",
    }


def generate_macros(results: dict) -> str:
    """Generate LaTeX macros."""
    s3 = results["strict_fa3"]
    s4 = results["strict_fa4"]
    
    return f"""% EX-34: Strict Consensus False-Accept Intersection
% Auto-generated by exp_strict_consensus_fa.py

\\newcommand{{\\strictFAThree}}{{{s3['rate']}}}
\\newcommand{{\\strictFAThreeCount}}{{{s3['count']}}}
\\newcommand{{\\strictFAFour}}{{{s4['rate']}}}
\\newcommand{{\\strictFAFourCount}}{{{s4['count']}}}
\\newcommand{{\\strictFACriticalPct}}{{{s3['critical_pct']}}}
\\newcommand{{\\strictFACriticalCount}}{{{s3['critical_count']}}}
\\newcommand{{\\strictFAMedianViols}}{{{s3['median_viols']}}}
\\newcommand{{\\pafFilterCount}}{{{results['paf_filters_out']}}}
\\newcommand{{\\pafFilterPct}}{{{results['paf_filter_pct']}}}
"""


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="evidence_pack/analysis/verdict_matrix_v6.json")
    parser.add_argument("--output-dir", default="evidence_pack/ex34_strict_fa")
    args = parser.parse_args()
    
    print(f"Loading {args.input}...")
    episodes = load_verdict_matrix(args.input)
    print(f"  Loaded {len(episodes)} episodes")
    
    print("\nComputing strict FA intersections...")
    results = compute_strict_fa(episodes)
    
    ao = results["all_oblivious"]
    s3 = results["strict_fa3"]
    s4 = results["strict_fa4"]
    
    print(f"\n  All-oblivious (TOM∩ASC∩CwT): {ao['rate']}% ({ao['count']} episodes)")
    print(f"  Strict FA3 (ASC∩PAF∩CwT):    {s3['rate']}% ({s3['count']} episodes)")
    print(f"  Strict FA4 (all four):        {s4['rate']}% ({s4['count']} episodes)")
    print(f"  PAF filters out:              {results['paf_filters_out']} episodes ({results['paf_filter_pct']}%)")
    print(f"  Critical severity (strict):   {s3['critical_pct']}% ({s3['critical_count']})")
    print(f"  Median violations (strict):   {s3['median_viols']}")
    
    if s3["domain_breakdown"]:
        print(f"\n  Top domains: {s3['domain_breakdown']}")
    
    # Save
    os.makedirs(args.output_dir, exist_ok=True)
    
    with open(os.path.join(args.output_dir, "strict_fa.json"), "w") as f:
        json.dump(results, f, indent=2)
    
    macros = generate_macros(results)
    with open(os.path.join(args.output_dir, "macros.tex"), "w") as f:
        f.write(macros)
    
    print(f"\nSaved to {args.output_dir}/")


if __name__ == "__main__":
    main()