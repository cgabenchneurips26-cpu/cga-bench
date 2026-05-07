"""Section D: Config & 실행 스크립트 검증."""

from __future__ import annotations

from pathlib import Path
import subprocess
import traceback

import yaml

ROOT = Path(__file__).resolve().parents[2]

CONFIGS_DIR = ROOT / "configs"
MODELS_DIR = CONFIGS_DIR / "models"


def run_d1_model_config_validation() -> None:
    """D.1: Model config YAML validation."""
    print("=" * 60)
    print("D.1  Model Config Validation")
    print("=" * 60)

    if not MODELS_DIR.exists():
        print(f"  Directory not found: {MODELS_DIR}")
        print("  (No model configs to validate — this is informational)")
        return

    yaml_files = sorted(MODELS_DIR.glob("*.yaml")) + sorted(MODELS_DIR.glob("*.yml"))
    if not yaml_files:
        print(f"  No YAML files found in {MODELS_DIR}")
        return

    for yf in yaml_files:
        try:
            with open(yf, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data is None:
                print(f"  WARN  {yf.name}: file is empty")
            else:
                print(f"  OK    {yf.name}  (top keys: {list(data.keys())[:5]})")
        except Exception as exc:
            print(f"  FAIL  {yf.name}: {exc}")


def run_d2_scenario_loader_validation() -> None:
    """D.2: ScenarioLoader validation and full scenario list dump."""
    print("\n" + "=" * 60)
    print("D.2  ScenarioLoader Validation")
    print("=" * 60)

    try:
        from cga_bench.eval_harness.scenario_loader import ScenarioLoader

        loader = ScenarioLoader()
        all_scenarios = loader.load_all_scenarios()
        ids = sorted(all_scenarios.keys())
        total = len(ids)

        print(f"  Total scenarios: {total}")
        print(f"  First 5: {ids[:5]}")
        print(f"  Last 5:  {ids[-5:]}")

        out_path = CONFIGS_DIR / "scenario_list_full.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            for sid in ids:
                f.write(sid + "\n")
        print(f"  Written: {out_path}  ({total} lines)")

    except Exception:
        traceback.print_exc()


def run_d3_vllm_gpu_check() -> None:
    """D.3: vLLM + GPU availability check (informational)."""
    print("\n" + "=" * 60)
    print("D.3  vLLM + GPU Check (informational)")
    print("=" * 60)

    # vLLM import check
    try:
        import vllm  # type: ignore[import-untyped]

        print(f"  vllm version: {vllm.__version__}")
    except ImportError:
        print("  vllm: not installed (expected on CPU-only machines)")
    except Exception:
        traceback.print_exc()

    # nvidia-smi check
    try:
        result = subprocess.run(
            ["nvidia-smi"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        for line in lines[:10]:
            print(f"  {line}")
        if len(lines) > 10:
            print(f"  ... ({len(lines) - 10} more lines)")
    except FileNotFoundError:
        print("  nvidia-smi: not found (expected on CPU-only machines)")
    except subprocess.TimeoutExpired:
        print("  nvidia-smi: timed out")
    except Exception:
        traceback.print_exc()


def main() -> None:
    """Run all Section D audits."""
    print("Section D: Config & Execution Script Verification")
    print("=" * 60)
    run_d1_model_config_validation()
    run_d2_scenario_loader_validation()
    run_d3_vllm_gpu_check()
    print("\n" + "=" * 60)
    print("Section D complete.")


if __name__ == "__main__":
    main()
