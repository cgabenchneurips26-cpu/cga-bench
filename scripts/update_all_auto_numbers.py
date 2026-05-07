#!/usr/bin/env python3
"""Unified Auto-Numbers Pipeline.

Runs all analysis scripts in dependency order and updates auto_numbers.tex.
Each script writes its own JSON to evidence_pack/analysis/; the final pass
(extract_auto_numbers.py) reads those JSONs and writes TeX macros.

Usage:
    # Full run (requires completed episodes)
    PYTHONPATH=. python scripts/update_all_auto_numbers.py --episodes-dir results/full_706_v5

    # Dry-run (list what would be executed)
    PYTHONPATH=. python scripts/update_all_auto_numbers.py --dry-run

    # Skip vLLM-dependent scripts
    PYTHONPATH=. python scripts/update_all_auto_numbers.py --skip-vllm
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


@dataclass
class ScriptStep:
    """A single pipeline step."""

    name: str
    command: list[str]
    requires_episodes: bool = True
    requires_vllm: bool = False
    critical: bool = True  # If True, pipeline stops on failure


STEPS: list[ScriptStep] = [
    # Phase 1: No episode dependency
    ScriptStep(
        name="Constraint counts",
        command=[
            PYTHON,
            str(REPO / "scripts" / "extract_constraint_counts.py"),
            "--graphs-dir",
            str(REPO / "cpg_model" / "graphs"),
            "--scenarios-dir",
            str(REPO / "configs" / "scenarios"),
            "--auto-generated",
            str(REPO / "configs" / "scenarios" / "auto_generated_scenarios.yaml"),
            "--output",
            str(REPO / "paper" / "auto_numbers.tex"),
        ],
        requires_episodes=False,
    ),
    ScriptStep(
        name="Clinician review packet",
        command=[PYTHON, str(REPO / "scripts" / "generate_clinician_review_packet.py")],
        requires_episodes=False,
        critical=False,
    ),
    # Phase 2: Episode-dependent scripts
    ScriptStep(
        name="E8 AgentClinic replay",
        command=[PYTHON, str(REPO / "scripts" / "experiments" / "v3_p1a_agentclinic_replay.py")],
    ),
    ScriptStep(
        name="E8 MedAgentBench replay",
        command=[PYTHON, str(REPO / "scripts" / "experiments" / "v3_p1b_medagentbench_replay.py")],
    ),
    ScriptStep(
        name="Instrumentation mimic ablation",
        command=[PYTHON, str(REPO / "scripts" / "experiments" / "instrumentation_mimic_ablation.py")],
    ),
    ScriptStep(
        name="E7 Paired delta analysis",
        command=[
            PYTHON,
            str(REPO / "scripts" / "experiments" / "run_paired_delta_analysis.py"),
        ],
    ),
    ScriptStep(
        name="Held-out episode analysis",
        command=[
            PYTHON,
            str(REPO / "scripts" / "experiments" / "run_heldout_episode_analysis.py"),
        ],
    ),
    ScriptStep(
        name="Timing validity audit",
        command=[
            PYTHON,
            str(REPO / "scripts" / "experiments" / "run_timing_validity_audit.py"),
        ],
    ),
    ScriptStep(
        name="Post-episode stats",
        command=[
            PYTHON,
            str(REPO / "scripts" / "experiments" / "run_post_episode_stats.py"),
        ],
    ),
    ScriptStep(
        name="Exact d_G audit",
        command=[
            PYTHON,
            str(REPO / "scripts" / "experiments" / "exp_exact_dg.py"),
        ],
        critical=False,
    ),
    # Phase 3: vLLM-dependent
    ScriptStep(
        name="Terminal LLM judge",
        command=[
            PYTHON,
            str(REPO / "scripts" / "experiments" / "terminal_output_baselines.py"),
        ],
        requires_vllm=True,
        critical=False,
    ),
    # Phase 4: Final TeX extraction
    ScriptStep(
        name="Extract auto numbers (E1-E5)",
        command=[PYTHON, str(REPO / "scripts" / "experiments" / "extract_auto_numbers.py")],
        critical=False,
    ),
]


def run_step(
    step: ScriptStep,
    episodes_dir: Path | None,
    dry_run: bool = False,
    skip_vllm: bool = False,
) -> bool:
    """Run a single pipeline step.

    Returns:
        True if step succeeded or was skipped, False if failed.
    """
    if skip_vllm and step.requires_vllm:
        print(f"  SKIP (--skip-vllm): {step.name}")
        return True

    if step.requires_episodes and episodes_dir is None:
        print(f"  SKIP (no episodes): {step.name}")
        return True

    # Inject --episodes-dir for scripts that accept it
    cmd = list(step.command)
    if step.requires_episodes and episodes_dir:
        # Check if script accepts --episodes-dir
        script_path = cmd[1] if len(cmd) > 1 else ""
        if Path(script_path).exists():
            try:
                help_out = subprocess.run(
                    [cmd[0], script_path, "--help"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/usr/local/bin"},
                )
                if "--episodes-dir" in help_out.stdout:
                    cmd.extend(["--episodes-dir", str(episodes_dir)])
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    if dry_run:
        print(f"  DRY-RUN: {step.name}")
        print(f"    CMD: {' '.join(cmd)}")
        return True

    print(f"  RUNNING: {step.name}...")
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,
            cwd=str(REPO),
            env={
                **dict(__import__("os").environ),
                "PYTHONPATH": f"{REPO.parent}:{REPO}",
            },
        )
        elapsed = time.time() - t0

        if result.returncode == 0:
            print(f"  OK ({elapsed:.1f}s): {step.name}")
            # Print last 3 lines of stdout for context
            lines = result.stdout.strip().split("\n")
            for line in lines[-3:]:
                print(f"    {line}")
            return True
        else:
            print(f"  FAIL (rc={result.returncode}, {elapsed:.1f}s): {step.name}")
            # Print last 5 lines of stderr
            err_lines = result.stderr.strip().split("\n")
            for line in err_lines[-5:]:
                print(f"    ERR: {line}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT (600s): {step.name}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified auto-numbers pipeline")
    parser.add_argument(
        "--episodes-dir",
        type=Path,
        default=REPO / "results" / "full_706_v5",
        help="Directory with model subdirs of episode JSONs",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running")
    parser.add_argument("--skip-vllm", action="store_true", help="Skip vLLM-dependent scripts")
    parser.add_argument("--skip-episodes", action="store_true", help="Only run non-episode scripts")
    args = parser.parse_args()

    episodes_dir = None if args.skip_episodes else args.episodes_dir

    print("=" * 60)
    print("  CGA-Bench Auto-Numbers Pipeline")
    print("=" * 60)
    print(f"Episodes dir: {episodes_dir or '(skipped)'}")
    print(f"Dry run: {args.dry_run}")
    print(f"Skip vLLM: {args.skip_vllm}")
    print(f"Total steps: {len(STEPS)}")
    print()

    passed = 0
    failed = 0
    skipped = 0

    for i, step in enumerate(STEPS, 1):
        print(f"[{i}/{len(STEPS)}] {step.name}")
        ok = run_step(step, episodes_dir, args.dry_run, args.skip_vllm)

        if ok:
            passed += 1
        elif step.critical:
            failed += 1
            print(f"\n  CRITICAL FAILURE: {step.name} — stopping pipeline.")
            break
        else:
            failed += 1
            print("  (non-critical, continuing)")

    print()
    print("=" * 60)
    print(f"  Results: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
