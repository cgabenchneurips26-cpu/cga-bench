#!/usr/bin/env python3
"""Apply B1 name renames to graph YAML files."""
import yaml, sys
from pathlib import Path

RENAMES = [
]

def apply_renames(graphs_dir):
    for yaml_file in sorted(Path(graphs_dir).glob("*.yaml")):
        with open(yaml_file) as fh:
            content = fh.read()
        changed = False
        for old, new in RENAMES:
            if old in content:
                content = content.replace(old, new)
                changed = True
                print(f"  {yaml_file.name}: {old} → {new}")
        if changed:
            with open(yaml_file, "w") as fh:
                fh.write(content)

if __name__ == "__main__":
    graphs_dir = sys.argv[1] if len(sys.argv) > 1 else "cpg_model/graphs"
    apply_renames(graphs_dir)
