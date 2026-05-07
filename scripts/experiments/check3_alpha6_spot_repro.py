"""Check 3: α-6 result spot reproducibility.

Samples 5 episodes from FA→pass flips (c2_pass=False, c2_pass_typed=True)
in the verdict matrix, loads their raw result files, recomputes
c2_score_typed from scratch, and compares against stored values.

Usage:
    PYTHONPATH=. python scripts/experiments/check3_alpha6_spot_repro.py
"""
from __future__ import annotations

import glob
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

VERDICT_MATRIX = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6_full_typed.json"
PHASE_A_DIR = ROOT / "results" / "full_v6b"

TYPED_VIOL_TYPES = {"omission", "commission", "timing", "sequence"}
C2_THRESHOLD = 0.7
N_SAMPLES = 5
SEED = 42
TOLERANCE = 1e-4  # stored values rounded to 4 decimal places


def find_result_file(model_dir: str, scenario_id: str, run_index: int) -> Path | None:
    """Find the JSON result file for a given episode."""
    pattern = str(PHASE_A_DIR / model_dir / f"{scenario_id}_{model_dir}_r{run_index}_*.json")
    matches = glob.glob(pattern)
    if matches:
        return Path(matches[0])
    # Try broader pattern (model_dir may differ in name)
    pattern2 = str(PHASE_A_DIR / model_dir / f"{scenario_id}_*_r{run_index}_*.json")
    matches2 = glob.glob(pattern2)
    if matches2:
        return Path(matches2[0])
    return None


def recompute_typed_score(result: dict) -> tuple[float, dict]:
    """Recompute c2_score_typed from raw result file.

    Returns:
        (typed_compliance_score, debug_info)
    """
    viols = result.get("violations_by_type", {})
    n_actions = result.get("actions_count", len(result.get("actions", [])))
    n_mandatory = result.get("n_expected_actions", 5)
    denom = max(n_actions, n_mandatory, 1)
    typed_count = sum(viols.get(t, 0) for t in TYPED_VIOL_TYPES)
    typed_compliance = max(0.0, 1.0 - typed_count / denom)

    debug = {
        "n_actions": n_actions,
        "n_mandatory": n_mandatory,
        "denom": denom,
        "typed_count": typed_count,
        "viols": viols,
    }
    return typed_compliance, debug


def main() -> None:
    if not VERDICT_MATRIX.exists():
        print(f"ERROR: Verdict matrix not found: {VERDICT_MATRIX}")
        sys.exit(1)
    if not PHASE_A_DIR.exists():
        print(f"ERROR: Phase A dir not found: {PHASE_A_DIR}")
        sys.exit(1)

    print(f"Loading verdict matrix: {VERDICT_MATRIX.name}")
    with open(VERDICT_MATRIX) as f:
        vm = json.load(f)

    pe = vm["per_episode"]
    print(f"Total episodes: {len(pe)}")

    # Find FA→pass flips
    flips = [e for e in pe if not e["c2_pass"] and e["c2_pass_typed"]]
    print(f"FA→pass flips (c2_pass=F, c2_pass_typed=T): {len(flips)}")

    # Sample 5
    random.seed(SEED)
    samples = random.sample(flips, min(N_SAMPLES, len(flips)))
    print(f"Sampled {len(samples)} episodes for verification\n")

    pass_count = 0
    fail_count = 0

    for i, ep in enumerate(samples):
        ep_id = ep["episode_id"]
        model_dir = ep["model_dir"]
        scenario_id = ep["scenario_id"]
        run_index = ep["run_index"]
        stored_typed = ep["c2_score_typed"]
        stored_pass = ep["c2_pass_typed"]

        print(f"--- Episode {i + 1}/{len(samples)}: {ep_id} ---")
        print(f"  Model: {model_dir}, Scenario: {scenario_id}, Run: {run_index}")
        print(f"  Stored: c2_score={ep['c2_score']:.4f}, c2_typed={stored_typed:.4f}, c2_pass_typed={stored_pass}")

        result_file = find_result_file(model_dir, scenario_id, run_index)
        if result_file is None:
            print(f"  ERROR: Result file not found")
            fail_count += 1
            continue

        with open(result_file) as f:
            result = json.load(f)

        recomputed, debug = recompute_typed_score(result)
        delta = abs(recomputed - stored_typed)
        match = delta < TOLERANCE

        print(f"  Recomputed: c2_typed={recomputed:.4f} (delta={delta:.6f})")
        print(f"  Debug: {debug}")

        if match:
            print(f"  PASS")
            pass_count += 1
        else:
            print(f"  FAIL — stored={stored_typed:.4f}, recomputed={recomputed:.4f}")
            fail_count += 1

    # Verdict
    print(f"\n=== RESULT ===")
    print(f"Passed: {pass_count}/{len(samples)}")
    print(f"Failed: {fail_count}/{len(samples)}")

    if fail_count == 0:
        print("PASS — all sampled episodes reproduce correctly")
        sys.exit(0)
    else:
        print("FAIL — some episodes do not reproduce")
        sys.exit(1)


if __name__ == "__main__":
    main()
