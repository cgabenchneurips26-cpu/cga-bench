"""Verify that the derivation + generation pipeline is deterministic.

Runs ConstraintDerivationEngine and PatientGenerator twice with seed=42,
then diffs outputs to confirm byte-identical results.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
from cpg_model.patient_generator import PatientGenerator

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"
N_RUNS = 3
SEED = 42


def run_pipeline(seed: int) -> str:
    """Run full derive+generate pipeline and return JSON hash."""
    engine = ConstraintDerivationEngine()
    generator = PatientGenerator(engine, seed=seed)

    all_results: list[dict] = []

    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        graph = load_graph(graph_path)
        scenarios = generator.generate_from_graph(graph)

        for s in scenarios:
            all_results.append(
                {
                    "scenario_id": s.scenario_id,
                    "guideline_graph": s.guideline_graph,
                    "trap_scenario": s.trap_scenario,
                    "triggered_rules": sorted(s.triggered_rules),
                    "forbidden_count": len(s.derived_constraints.get("forbidden", [])),
                    "expected_count": len(s.derived_constraints.get("expected", [])),
                }
            )

    # Sort for deterministic ordering
    all_results.sort(key=lambda x: x["scenario_id"])
    content = json.dumps(all_results, sort_keys=True, indent=2)
    return hashlib.sha256(content.encode()).hexdigest()


def main() -> None:
    print(f"Running derivation pipeline {N_RUNS} times with seed={SEED}...")

    hashes: list[str] = []
    for i in range(N_RUNS):
        h = run_pipeline(SEED)
        hashes.append(h)
        print(f"  Run {i + 1}: {h[:16]}...")

    if len(set(hashes)) == 1:
        print(f"\nPASS: All {N_RUNS} runs produced identical output (SHA256: {hashes[0][:32]}...)")
        sys.exit(0)
    else:
        print("\nFAIL: Non-deterministic output detected!")
        for i, h in enumerate(hashes):
            print(f"  Run {i + 1}: {h}")
        sys.exit(1)


if __name__ == "__main__":
    main()
