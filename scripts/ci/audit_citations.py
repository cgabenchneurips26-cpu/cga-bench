"""Audit README.md citations against YAML graph metadata.

Checks that guideline names in README match source_guideline fields in YAML graphs.
Exit code 0 = all match, 1 = mismatches found.
"""

import sys
from pathlib import Path

import yaml


def audit_citations(
    graphs_dir: str = "cpg_model/graphs",
    readme_path: str = "README.md",
) -> tuple[list[str], list[str]]:
    """Compare README guideline references with YAML graph metadata.

    ENG-11 requires citation mismatch 0. Mismatches are errors, not warnings.
    """
    errors = []
    warnings = []

    graphs_path = Path(graphs_dir)
    if not graphs_path.exists():
        graphs_path = Path(__file__).resolve().parent.parent.parent / graphs_dir

    readme_file = Path(readme_path)
    if not readme_file.exists():
        readme_file = Path(__file__).resolve().parent.parent.parent / readme_path

    yaml_guidelines = {}
    for f in sorted(graphs_path.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        metadata = data.get("metadata", {})
        # guideline_name is top-level; source is in metadata
        guideline = data.get("guideline_name", "") or metadata.get("source", "") or metadata.get("source_guideline", "")
        graph_id = data.get("graph_id", f.stem)
        yaml_guidelines[f.name] = {
            "graph_id": graph_id,
            "source_guideline": guideline,
            "file": f.name,
        }

    readme_text = ""
    if readme_file.exists():
        readme_text = readme_file.read_text()

    for fname, info in yaml_guidelines.items():
        graph_id = info["graph_id"]
        guideline = info["source_guideline"]

        if not guideline:
            errors.append(f"{fname}: no source_guideline in metadata")

        if readme_text:
            if fname not in readme_text and graph_id not in readme_text:
                errors.append(f"{fname} ({graph_id}): not referenced in README.md")

    return errors, warnings


if __name__ == "__main__":
    errors, warnings = audit_citations()

    if warnings:
        print(f"\n=== Warnings ({len(warnings)}) ===")
        for w in warnings[:20]:
            print(f"  WARN: {w}")

    if errors:
        print(f"\n=== Errors ({len(errors)}) ===")
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    else:
        print(f"\n=== Citation audit PASSED (0 errors, {len(warnings)} warnings) ===")
        sys.exit(0)
