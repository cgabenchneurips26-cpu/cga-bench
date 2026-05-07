"""Section E: 기존 Episode와의 호환성."""

from __future__ import annotations

import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"

# Directories to scan for episode JSON files
SCAN_DIRS: list[str] = [
    "clean_slate_rescored",
    "",  # results root
]


def _collect_json_files(base: Path) -> list[Path]:
    """Recursively collect all .json files under a directory."""
    if not base.exists():
        return []
    return sorted(base.rglob("*.json"))


def _show_episode(path: Path, label: str) -> dict | None:
    """Load and display summary of a single episode JSON."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  {label} LOAD ERROR: {path.name}: {exc}")
        return None

    keys = list(data.keys())
    print(f"  {label} File: {path.relative_to(RESULTS_DIR)}")
    print(f"    Top-level keys ({len(keys)}): {keys[:15]}")
    if len(keys) > 15:
        print(f"    ... and {len(keys) - 15} more")

    scenario_id = data.get("scenario_id", "<missing>")
    model_name = data.get("model_name", data.get("model", "<missing>"))
    print(f"    scenario_id: {scenario_id}")
    print(f"    model_name:  {model_name}")

    # Action count — try both field names
    actions = data.get("agent_actions", data.get("actions", []))
    actions_count = data.get("actions_count", len(actions) if isinstance(actions, list) else 0)
    print(f"    actions_count: {actions_count}")

    return data


def run_e1_episode_check() -> None:
    """E.1: Scan episode directories and verify compatibility."""
    print("=" * 60)
    print("E.1  Existing Episode JSON Check")
    print("=" * 60)

    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    loader = ScenarioLoader()
    all_scenarios = loader.load_all_scenarios()
    known_ids = set(all_scenarios.keys())
    print(f"  Known scenario IDs from ScenarioLoader: {len(known_ids)}")

    # --- Per-directory scan ---
    all_episode_paths: list[Path] = []

    for subdir in SCAN_DIRS:
        scan_path = RESULTS_DIR / subdir if subdir else RESULTS_DIR
        if not scan_path.exists():
            print(f"\n  Directory not found: {scan_path}")
            continue

        # Recursive for subdirs, root-level-only for "" to avoid double-counting
        json_files = (
            _collect_json_files(scan_path) if subdir else sorted(scan_path.glob("*.json"))
        )

        print(f"\n  Directory: {scan_path.relative_to(ROOT)}")
        print(f"    JSON files: {len(json_files)}")

        if json_files:
            all_episode_paths.extend(json_files)
            # Show first episode
            _show_episode(json_files[0], "First")

    # --- Scenario ID cross-check on first episode ---
    if all_episode_paths:
        first_data = None
        try:
            with open(all_episode_paths[0], encoding="utf-8") as f:
                first_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            first_data = None

        if first_data and "scenario_id" in first_data:
            sid = first_data["scenario_id"]
            found = sid in known_ids
            print(f"\n  Cross-check: scenario_id '{sid}' in ScenarioLoader? {'YES' if found else 'NO'}")

    # --- Random sample of 5 episodes across different models ---
    print("\n  --- Random Sample (up to 5 episodes) ---")

    # Filter to likely episode files (exclude summary/combined files)
    candidate_paths = [
        p for p in all_episode_paths
        if "summary" not in p.name and "combined" not in p.name and "rescore" not in p.name
    ]

    if not candidate_paths:
        print("  No candidate episode files found for sampling")
        return

    sample_size = min(5, len(candidate_paths))
    random.seed(42)
    sample = random.sample(candidate_paths, sample_size)

    missing_scenarios: list[str] = []
    for i, ep_path in enumerate(sample):
        print()
        data = _show_episode(ep_path, f"Sample[{i}]")
        if data and "scenario_id" in data:
            sid = data["scenario_id"]
            if sid not in known_ids:
                missing_scenarios.append(sid)

    if missing_scenarios:
        print(f"\n  WARNING: {len(missing_scenarios)} sampled episodes reference unknown scenario IDs:")
        for sid in missing_scenarios:
            print(f"    - {sid}")
    else:
        print(f"\n  All {sample_size} sampled episodes reference valid scenario IDs")


def main() -> None:
    """Run all Section E audits."""
    print("Section E: Existing Episode Compatibility")
    print("=" * 60)
    run_e1_episode_check()
    print("\n" + "=" * 60)
    print("Section E complete.")


if __name__ == "__main__":
    main()
