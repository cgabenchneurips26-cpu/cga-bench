#!/usr/bin/env python3
"""Convert SGSC v7.3 JSON scenarios to ScenarioLoader-compatible YAML.

Reads scenarios from sgsc_output/v7_e3_combined_v3/ (core 25) and
sgsc_output/v7_2_atoms_v3/ (expansion 25), writes per-graph YAML files
to configs/scenarios/sgsc/ in the format expected by ScenarioLoader.

Usage::

    PYTHONPATH=. python scripts/sgsc/sgsc_to_yaml.py

Verify::

    PYTHONPATH=. python -c "
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader
    L = ScenarioLoader(scenarios_dir='configs/scenarios/sgsc')
    s = L.load_all_scenarios()
    print(f'Loaded {len(s)} scenarios')
    "
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Input directories
CORE_DIR = _ROOT / "sgsc_output" / "v7_e3_combined_v3"
EXPANSION_DIR = _ROOT / "sgsc_output" / "v7_2_atoms_v3"

# Output directory
OUTPUT_DIR = _ROOT / "configs" / "scenarios" / "sgsc"

# Fields to strip from YAML output (internal SGSC metadata)
_STRIP_KEYS = {"_sgsc_metadata", "_sgsc_profile_tier"}


def _clean_scenario(scn: dict) -> dict:
    """Remove SGSC-internal metadata and normalize for ScenarioLoader."""
    cleaned: dict = {}
    for k, v in scn.items():
        if k in _STRIP_KEYS:
            continue
        cleaned[k] = v

    # ScenarioLoader expects ground_truth as a dict with lab results etc.
    # v7.3 ground_truth contains {expected_actions, forbidden_actions} which
    # is redundant with top-level fields. Convert to lab-result style if needed.
    gt = cleaned.get("ground_truth", {})
    if isinstance(gt, dict) and "expected_actions" in gt:
        # Replace with empty ground truth — the environment will use defaults
        cleaned["ground_truth"] = {}

    # Ensure forbidden_actions is always present (ScenarioLoader expects it)
    if "forbidden_actions" not in cleaned:
        cleaned["forbidden_actions"] = []

    # Ensure optional_actions is present
    if "optional_actions" not in cleaned:
        cleaned["optional_actions"] = []

    # Patient normalization: ScenarioLoader expects these fields
    patient = cleaned.get("patient", {})
    if "weight_kg" not in patient:
        patient["weight_kg"] = 70  # default
    if "working_diagnosis" not in patient:
        patient["working_diagnosis"] = None
    if "comorbidities" not in patient:
        patient["comorbidities"] = []
    if "contraindications" not in patient:
        patient["contraindications"] = []
    if "allergies" not in patient:
        patient["allergies"] = []
    cleaned["patient"] = patient

    return cleaned


def convert_graph_scenarios(graph_dir: Path, output_dir: Path) -> int:
    """Convert one graph's scenarios JSON to YAML."""
    graph_id = graph_dir.name

    # Find the scenarios JSON (not _private or _public variants)
    scn_file = graph_dir / f"{graph_id}_scenarios.json"
    if not scn_file.exists():
        # Try alternative naming
        candidates = [
            f for f in graph_dir.glob("*_scenarios.json")
            if "_scenarios_p" not in f.name
        ]
        if not candidates:
            logger.warning(f"No scenarios JSON in {graph_dir}")
            return 0
        scn_file = candidates[0]

    raw = json.loads(scn_file.read_text())
    if not isinstance(raw, dict) or not raw:
        logger.warning(f"Empty or non-dict scenarios in {scn_file}")
        return 0

    # Build YAML structure
    scenarios_block: dict = {}
    for scn_id, scn_data in raw.items():
        cleaned = _clean_scenario(scn_data)
        scenarios_block[scn_id] = cleaned

    yaml_data = {"scenarios": scenarios_block}

    # Write YAML
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{graph_id}_scenarios.yaml"
    with open(out_file, "w", encoding="utf-8") as f:
        yaml.dump(
            yaml_data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )

    return len(scenarios_block)


def main() -> None:
    """Convert all v7.3 SGSC scenarios to YAML."""
    total = 0
    graph_count = 0

    for label, base_dir in [("core", CORE_DIR), ("expansion", EXPANSION_DIR)]:
        if not base_dir.exists():
            logger.warning(f"{label} dir not found: {base_dir}")
            continue

        for graph_dir in sorted(base_dir.iterdir()):
            if not graph_dir.is_dir():
                continue
            n = convert_graph_scenarios(graph_dir, OUTPUT_DIR)
            if n > 0:
                graph_count += 1
                total += n
                logger.info(f"  {graph_dir.name}: {n} scenarios ({label})")

    logger.info(f"\nTotal: {total} scenarios from {graph_count} graphs")
    logger.info(f"Output: {OUTPUT_DIR}")

    # Quick verification
    yaml_files = list(OUTPUT_DIR.glob("*_scenarios.yaml"))
    logger.info(f"YAML files written: {len(yaml_files)}")

    # Count scenarios in YAML
    yaml_count = 0
    for yf in yaml_files:
        data = yaml.safe_load(yf.read_text())
        if data and "scenarios" in data:
            yaml_count += len(data["scenarios"])
    logger.info(f"Scenarios in YAML: {yaml_count}")

    if yaml_count != total:
        logger.error(f"MISMATCH: wrote {total} but YAML contains {yaml_count}")
        sys.exit(1)

    logger.info("PASS: JSON → YAML conversion complete")


if __name__ == "__main__":
    main()
