#!/usr/bin/env python3
"""One-shot script: inject target_population metadata into all CPG graph YAMLs.

Run once then delete. Idempotent: skips files that already have target_population.

Usage:
    PYTHONPATH=. python scripts/ci/_inject_target_population.py
    PYTHONPATH=. python scripts/ci/_inject_target_population.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent.parent
GRAPHS_CORE = BASE / "cpg_model" / "graphs"
GRAPHS_AUTO = GRAPHS_CORE / "auto"

# ── Classification rules ──────────────────────────────────────────────
# Each entry: (filename_substring, population_dict)
# Checked in order; first match wins.

_NEONATAL = {
    "age_group": "neonatal",
    "min_age": 0,
    "max_age": 0.08,
    "sex": "any",
    "special_conditions": [],
}
_PEDIATRIC = {
    "age_group": "pediatric",
    "min_age": 0,
    "max_age": 17,
    "sex": "any",
    "special_conditions": [],
}
_MATERNAL = {
    "age_group": "adult",
    "min_age": 15,
    "max_age": 50,
    "sex": "female_only",
    "special_conditions": ["pregnant"],
}
_ADULT = {
    "age_group": "adult",
    "min_age": 18,
    "max_age": 120,
    "sex": "any",
    "special_conditions": [],
}
_ADULT_FEMALE = {
    "age_group": "adult",
    "min_age": 18,
    "max_age": 120,
    "sex": "female_only",
    "special_conditions": [],
}
_ALL_AGES = {
    "age_group": "all",
    "min_age": 0,
    "max_age": 120,
    "sex": "any",
    "special_conditions": [],
}

CLASSIFICATION_RULES: list[tuple[str, dict]] = [
    # Neonatal
    ("nrp_neonatal", _NEONATAL),
    ("ilcor_neonatal", _NEONATAL),
    # Pediatric
    ("pals_pediatric", _PEDIATRIC),
    ("sccm_pediatric", _PEDIATRIC),
    ("ispad_pediatric", _PEDIATRIC),
    ("gina_pediatric", _PEDIATRIC),
    # Maternal / Obstetric
    ("smfm_maternal", _MATERNAL),
    ("acog_obstetric", _MATERNAL),
    # Female-predominant
    ("asco_breast_cancer", _ADULT_FEMALE),
    # Universal / all-ages
    ("universal_clinical_safety", _ALL_AGES),
    ("anaphylaxis", _ALL_AGES),
    ("toxicology", _ALL_AGES),
]


def classify(stem: str) -> dict:
    """Return target_population dict for a graph file stem."""
    for pattern, pop in CLASSIFICATION_RULES:
        if pattern in stem:
            return dict(pop)  # copy
    return dict(_ADULT)


def inject_metadata(path: Path, dry_run: bool) -> str:
    """Add target_population to a graph YAML. Returns status string."""
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return f"SKIP (not a dict): {path.name}"

    meta = data.get("metadata")
    if isinstance(meta, dict) and "target_population" in meta:
        return f"SKIP (already has target_population): {path.name}"

    pop = classify(path.stem)

    # Build the YAML block to inject
    pop_yaml = yaml.dump(
        {"target_population": pop},
        default_flow_style=False,
        allow_unicode=True,
    ).rstrip()
    # Indent by 2 spaces (nested under metadata:)
    pop_lines = "\n".join(f"  {line}" for line in pop_yaml.splitlines())

    # Strategy: find the "metadata:" line and insert after the last
    # metadata sub-key before the next top-level key.
    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    in_metadata = False
    injected = False

    for i, line in enumerate(lines):
        stripped = line.rstrip()

        # Detect start of metadata block
        if stripped == "metadata:" or stripped.startswith("metadata:"):
            in_metadata = True
            new_lines.append(line)
            continue

        # If we're in metadata, detect exit (next top-level key)
        if in_metadata and not injected:
            # A top-level key starts at column 0 and is not empty
            if stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                # Insert target_population before this line
                new_lines.append(pop_lines + "\n")
                injected = True
                in_metadata = False

        new_lines.append(line)

    # If metadata was the last block, append at end
    if in_metadata and not injected:
        new_lines.append(pop_lines + "\n")
        injected = True

    # If no metadata block exists, create one at top (after first line if comment)
    if not injected:
        insert_idx = 0
        for j, line in enumerate(new_lines):
            if line.strip() and not line.strip().startswith("#"):
                insert_idx = j
                break
        meta_block = f"metadata:\n{pop_lines}\n"
        new_lines.insert(insert_idx, meta_block)
        injected = True

    result = "".join(new_lines)

    if dry_run:
        return f"DRY-RUN: {path.name} -> {pop['age_group']}/{pop['sex']}"

    path.write_text(result, encoding="utf-8")
    return f"INJECTED: {path.name} -> {pop['age_group']}/{pop['sex']}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    all_yamls: list[Path] = []
    all_yamls.extend(sorted(GRAPHS_CORE.glob("*.yaml")))
    all_yamls.extend(sorted(GRAPHS_AUTO.glob("*.yaml")))

    stats = {"injected": 0, "skipped": 0, "error": 0}
    for path in all_yamls:
        try:
            result = inject_metadata(path, args.dry_run)
            print(result)
            if result.startswith("INJECT") or result.startswith("DRY"):
                stats["injected"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            print(f"ERROR: {path.name}: {e}")
            stats["error"] += 1

    print(
        f"\nTotal: {len(all_yamls)} files | "
        f"Injected: {stats['injected']} | "
        f"Skipped: {stats['skipped']} | "
        f"Errors: {stats['error']}"
    )


if __name__ == "__main__":
    main()
