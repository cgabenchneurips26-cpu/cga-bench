"""Test LLM empty rate after max_tokens fix."""

import sys
import time

sys.path.insert(0, "${CGA_BENCH_ROOT}")
sys.path.insert(0, "${CGA_BENCH_ROOT}/cga_bench")

from pathlib import Path

from scripts.experiments.clean_slate_runner import health_check, run_single_episode

outdir = Path("results/empty_rate_test")
outdir.mkdir(parents=True, exist_ok=True)

SCENARIOS = ["septic_shock_basic", "stemi_inferior_rv_trap", "dka_hypokalemia_trap"]

for model in ["qwen35b"]:
    port = 8013
    if not health_check(port):
        print(f"{model} DOWN on port {port}")
        continue

    print(f"=== {model} (max_tokens=4096) ===")
    (outdir / model).mkdir(exist_ok=True)

    for sid in SCENARIOS:
        t0 = time.time()
        result = run_single_episode(model, sid, 0, outdir)
        elapsed = time.time() - t0
        if result:
            cs = result["compliance_score"]
            ac = result["actions_count"]
            print(f"  {sid}: compliance={cs:.3f} actions={ac} ({elapsed:.0f}s)")
        else:
            print(f"  {sid}: FAILED ({elapsed:.0f}s)")

print("\nCheck log for empty rate:")
print("  grep -c 'empty' results/empty_rate_test/log_*.txt 2>/dev/null")
