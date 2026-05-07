"""Runner: Execute all pipeline audit scripts (A-G) sequentially.

Collects output from each section and prints a final summary with
OK/FAIL/WARNING/ERROR/MISMATCH/MISSING keyword counts.
"""

from __future__ import annotations

import importlib
from io import StringIO
from pathlib import Path
import re
import sys
import time
import traceback
from typing import Any

# cga_bench __init__.py files use `from cga_bench.xxx` imports,
# which requires the parent of cga_bench/ on sys.path.
_CGA_ROOT = Path(__file__).resolve().parents[2]
_PARENT = str(_CGA_ROOT.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

SECTIONS = [
    ("A", "audit.pipeline.audit_a_engine"),
    ("B", "audit.pipeline.audit_b_normalizer"),
    ("C", "audit.pipeline.audit_c_scorer"),
    ("D", "audit.pipeline.audit_d_config"),
    ("E", "audit.pipeline.audit_e_episodes"),
    ("F", "audit.pipeline.audit_f_temporal"),
    ("G", "audit.pipeline.audit_g_numbers"),
]

KEYWORDS = ["FAIL", "ERROR", "MISSING", "MISMATCH", "WARNING", "SKIP"]


def run_section(label: str, module_name: str) -> dict[str, Any]:
    """Run a single audit section and capture output.

    Returns:
        Dict with label, output text, elapsed time, keyword counts, success flag.
    """
    captured = StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    start = time.time()
    success = True

    try:
        sys.stdout = captured
        sys.stderr = captured
        mod = importlib.import_module(module_name)
        if hasattr(mod, "main"):
            mod.main()
        else:
            print(f"WARNING: {module_name} has no main() function")
    except Exception:
        success = False
        traceback.print_exc(file=captured)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    elapsed = time.time() - start
    output = captured.getvalue()

    # Count keywords
    counts: dict[str, int] = {}
    for kw in KEYWORDS:
        counts[kw] = len(re.findall(rf"\b{kw}\b", output, re.IGNORECASE))

    return {
        "label": label,
        "module": module_name,
        "output": output,
        "elapsed": elapsed,
        "success": success,
        "keyword_counts": counts,
    }


def main() -> None:
    """Run all audit sections and print summary."""
    print("=" * 70)
    print("CGA-Bench Pipeline Verification Audit")
    print("=" * 70)
    print()

    results: list[dict[str, Any]] = []
    total_start = time.time()

    for label, module_name in SECTIONS:
        print(f"--- Running Section {label} ---")
        result = run_section(label, module_name)
        results.append(result)

        # Print captured output
        print(result["output"])

        status = "OK" if result["success"] else "CRASHED"
        print(f"  [{status}] Section {label} completed in {result['elapsed']:.1f}s")
        print()

    total_elapsed = time.time() - total_start

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total time: {total_elapsed:.1f}s\n")

    total_keywords: dict[str, int] = dict.fromkeys(KEYWORDS, 0)
    for r in results:
        status = "OK" if r["success"] else "CRASHED"
        kw_str = ", ".join(
            f"{kw}={r['keyword_counts'][kw]}"
            for kw in KEYWORDS
            if r["keyword_counts"][kw] > 0
        )
        extra = f"  ({kw_str})" if kw_str else ""
        print(f"  Section {r['label']}: {status} [{r['elapsed']:.1f}s]{extra}")
        for kw in KEYWORDS:
            total_keywords[kw] += r["keyword_counts"][kw]

    print()
    print("Keyword totals:")
    for kw in KEYWORDS:
        if total_keywords[kw] > 0:
            print(f"  {kw}: {total_keywords[kw]}")

    n_crashed = sum(1 for r in results if not r["success"])
    n_with_fails = sum(
        1 for r in results
        if r["keyword_counts"]["FAIL"] > 0 or r["keyword_counts"]["ERROR"] > 0
    )

    if n_crashed > 0:
        print(f"\n  {n_crashed} section(s) CRASHED")
    if n_with_fails > 0:
        print(f"  {n_with_fails} section(s) have FAIL/ERROR keywords")
    if n_crashed == 0 and n_with_fails == 0:
        print("\n  All sections clean.")


if __name__ == "__main__":
    main()
