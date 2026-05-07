#!/usr/bin/env python3
"""Apply corrected B1 renames to graph YAML files.
   4 renames with similarity >= 0.85"""

import sys
from pathlib import Path

RENAMES = {
    "delay_defibrillation": "deliver_defibrillation",
    "discontinue_eeg_monitoring": "continuous_eeg_monitoring",
    "give_diuretics": "iv_diuretics",
    "use_high_osmolar_contrast": "use_iso_osmolar_contrast",
}

def apply(graphs_dir):
    changed_total = 0
    for yf in sorted(Path(graphs_dir).glob("*.yaml")):
        with open(yf) as fh:
            content = fh.read()
        original = content
        for old, new in RENAMES.items():
            if old in content:
                content = content.replace(old, new)
                print(f"  {yf.name}: {old} → {new}")
                changed_total += 1
        if content != original:
            with open(yf, "w") as fh:
                fh.write(content)
    print(f"\nTotal renames applied: {changed_total}")

if __name__ == "__main__":
    apply(sys.argv[1] if len(sys.argv) > 1 else "cpg_model/graphs")
