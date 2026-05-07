#!/usr/bin/env python3
"""Update auto_numbers.tex EX-21 macros from the analysis JSON.

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/update_ex21_macros.py

Workflow:
  1. Re-run exp_e21_model_diversity.py to regenerate JSON
  2. Run this script to update macros in paper/auto_numbers.tex
"""

from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "evidence_pack" / "ex21_model_diversity" / "ex21_model_diversity.json"
TEX_PATH = ROOT / "paper" / "auto_numbers.tex"

MACRO_MAP: dict[str, str] = {
    "diversityNFamilies": "n_diversity_models",
    "diversityTotalModels": "n_total_models",
    "diversityDeepSeekN": "deepseek_n",
    "diversityBiomedN": "biomed_n",
    "diversityDeepSeekFlip": "deepseek_flip",
    "diversityBiomedFlip": "biomed_flip",
    "diversityMeanFlip": "diversity_mean_flip",
    "baselineMeanFlip": "baseline_mean_flip",
    "diversityDeepSeekCGA": "deepseek_cga",
    "diversityBiomedCGA": "biomed_cga",
    "diversityDeepSeekAC": "deepseek_ac",
    "diversityBiomedAC": "biomed_ac",
}


def extract_values(data: dict) -> dict[str, str]:
    """Extract macro values from EX-21 JSON."""
    div = data.get("diversity_models", {})
    base = data.get("baseline_comparison", {})

    ds = div.get("DeepSeek-R1-7B", {})
    bio = div.get("OpenBioLLM-8B", {})

    n_div = sum(1 for v in div.values() if isinstance(v, dict) and v.get("n_episodes", 0) > 0)
    n_base = sum(1 for v in base.values() if isinstance(v, dict) and v.get("n_episodes", 0) > 0)

    return {
        "diversityNFamilies": str(n_div),
        "diversityTotalModels": str(n_div + n_base),
        "diversityDeepSeekN": str(ds.get("n_episodes", 0)),
        "diversityBiomedN": str(bio.get("n_episodes", 0)),
        "diversityDeepSeekFlip": str(ds.get("verdict_flip_rate", 0.0)),
        "diversityBiomedFlip": str(bio.get("verdict_flip_rate", 0.0)),
        "diversityMeanFlip": str(data.get("summary", {}).get("diversity_mean_flip", 0.0)),
        "baselineMeanFlip": str(data.get("summary", {}).get("baseline_mean_flip", 0.0)),
        "diversityDeepSeekCGA": str(ds.get("pass_rates", {}).get("CGA-Bench", 0.0)),
        "diversityBiomedCGA": str(bio.get("pass_rates", {}).get("CGA-Bench", 0.0)),
        "diversityDeepSeekAC": str(ds.get("pass_rates", {}).get("AC-Proxy", 0.0)),
        "diversityBiomedAC": str(bio.get("pass_rates", {}).get("AC-Proxy", 0.0)),
    }


def update_tex(values: dict[str, str]) -> int:
    """Update macro values in auto_numbers.tex. Returns count of updates."""
    content = TEX_PATH.read_text()
    updated = 0

    for macro_name, new_val in values.items():
        pattern = rf"(\\newcommand\{{\\{macro_name}\}}\{{)[^}}]*(}})"
        match = re.search(pattern, content)
        if match:
            old_val = content[match.start(1) + len(match.group(1)) : match.start(2)]
            if old_val != new_val:
                content = (
                    content[: match.start(1)] + match.group(1) + new_val + match.group(2) + content[match.end(2) :]
                )
                print(f"  {macro_name}: {old_val} -> {new_val}")
                updated += 1
            else:
                print(f"  {macro_name}: {old_val} (unchanged)")
        else:
            print(f"  WARNING: macro \\{macro_name} not found in {TEX_PATH.name}")

    if updated:
        TEX_PATH.write_text(content)

    return updated


def main() -> None:
    print("=" * 50)
    print("Updating EX-21 macros in auto_numbers.tex")
    print("=" * 50)

    if not JSON_PATH.exists():
        print(f"ERROR: {JSON_PATH} not found. Run exp_e21_model_diversity.py first.")
        return

    data = json.loads(JSON_PATH.read_text())
    values = extract_values(data)

    print(f"\nSource: {JSON_PATH}")
    print(f"Target: {TEX_PATH}\n")

    n = update_tex(values)
    print(f"\n{n} macros updated.")


if __name__ == "__main__":
    main()
