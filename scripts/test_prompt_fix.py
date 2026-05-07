"""Test: does moving completed list to end fix Qwen repeat problem?"""

import sys
import time

sys.path.insert(0, "${CGA_BENCH_ROOT}")
sys.path.insert(0, "${CGA_BENCH_ROOT}/cga_bench")

from pathlib import Path

from scripts.experiments.clean_slate_runner import health_check, run_single_episode

outdir = Path("results/prompt_fix_test")
outdir.mkdir(parents=True, exist_ok=True)

for model in ["qwen35b", "oss120b"]:
    port = 8013 if model == "qwen35b" else 28000
    if not health_check(port):
        print(f"{model} DOWN")
        continue

    (outdir / model).mkdir(exist_ok=True)
    print(f"\n=== {model} ===")
    for sid in ["septic_shock_basic", "stemi_inferior_rv_trap"]:
        t0 = time.time()
        result = run_single_episode(model, sid, 0, outdir)
        elapsed = time.time() - t0
        if result:
            print(
                f"  {sid}: actions={result['actions_count']} compliance={result['compliance_score']:.3f} ({elapsed:.0f}s)"
            )
        else:
            print(f"  {sid}: FAILED ({elapsed:.0f}s)")
