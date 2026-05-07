"""
Load Hard Graph + Soft Constraints guidelines.
"""
from pathlib import Path
from typing import Tuple

import yaml

from cga_bench.cpg_model.schemas.conformance import HardGraph, SoftConstraints


def load_guideline_bundle(guideline_dir: Path) -> Tuple[HardGraph, SoftConstraints]:
    hard_path = guideline_dir / "hard_graph.yaml"
    soft_path = guideline_dir / "constraints.yaml"
    if not hard_path.exists():
        raise FileNotFoundError(f"Missing hard_graph.yaml: {hard_path}")
    if not soft_path.exists():
        raise FileNotFoundError(f"Missing constraints.yaml: {soft_path}")

    hard_graph = HardGraph(**_load_yaml(hard_path))
    soft_constraints = SoftConstraints(**_load_yaml(soft_path))

    if hard_graph.cpg_id != soft_constraints.cpg_id:
        raise ValueError(
            f"CPG ID mismatch: {hard_graph.cpg_id} vs {soft_constraints.cpg_id}"
        )

    return hard_graph, soft_constraints


def _load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)
