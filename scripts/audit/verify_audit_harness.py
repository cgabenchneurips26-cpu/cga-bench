#!/usr/bin/env python3
"""End-to-end smoke test of the Option B / Option C audit harness.

Runs `scripts/audit/evaluator_audit.py` on every shim registered in
`SHIM_REGISTRY` and asserts each run produces a report.json with the
expected keys. Exit 0 iff every shim completes successfully.

This answers the question: "Do the Option B/C components actually work
end-to-end on the current v6 canonical corpus?"

Usage:
    PYTHONPATH=. python scripts/audit/verify_audit_harness.py
    PYTHONPATH=. python scripts/audit/verify_audit_harness.py --fast   # skip top-K witnesses
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audit.shims import SHIM_REGISTRY  # noqa: E402

REQUIRED_KEYS = {
    "evaluator",
    "step1_pi_class",
    "step2_bsr",
    "step3_bayes_floor",
    "step6_blindspot_grid",
}

SKIP_SHIMS = {
    # llm_judge requires precomputed cache and is optional for smoke
    "llm_judge",
}


def _run_one(shim: str, out_dir: Path, top_k: int) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "audit" / "evaluator_audit.py"),
        "--shim",
        shim,
        "--out-dir",
        str(out_dir),
        "--top-k",
        str(top_k),
    ]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    elapsed = time.time() - t0
    if proc.returncode != 0:
        return {
            "shim": shim,
            "status": "FAIL",
            "elapsed_s": round(elapsed, 1),
            "error": proc.stderr[-400:] or proc.stdout[-400:],
        }
    # Each runner writes to <out_dir>/<evaluator_slug>/report.json
    # the slug matches the evaluator name lowercased — inspect directly
    reports = list(out_dir.glob("*/report.json"))
    if not reports:
        return {
            "shim": shim,
            "status": "FAIL",
            "elapsed_s": round(elapsed, 1),
            "error": f"no report.json under {out_dir}",
        }
    report = json.loads(reports[-1].read_text())
    missing = REQUIRED_KEYS - set(report.keys())
    if missing:
        return {
            "shim": shim,
            "status": "FAIL",
            "elapsed_s": round(elapsed, 1),
            "error": f"missing keys: {missing}",
        }
    return {
        "shim": shim,
        "status": "OK",
        "elapsed_s": round(elapsed, 1),
        "pi_class": report["step1_pi_class"].get("pi_class"),
        "bsr": report["step2_bsr"].get("bsr"),
        "bayes_floor": report["step3_bayes_floor"].get("epsilon_star"),
        "red_cells": report["step6_blindspot_grid"].get("n_red_cells"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify audit harness end-to-end")
    parser.add_argument("--out-dir", default="/tmp/cga_audit_verify")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--fast", action="store_true", help="top_k=0 for speed")
    args = parser.parse_args()

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    top_k = 0 if args.fast else args.top_k

    all_shims = sorted(set(SHIM_REGISTRY.keys()) - SKIP_SHIMS)
    print(f"Verifying {len(all_shims)} shims (skipping: {sorted(SKIP_SHIMS)})")
    print(f"Output dir: {out_root}")
    print(f"{'shim':<22s} {'status':<6s} {'pi_class':<8s} {'BSR':>7s} {'floor':>7s} {'red':>4s}  time")
    print("-" * 78)

    results = []
    for shim in all_shims:
        shim_out = out_root / shim
        shim_out.mkdir(exist_ok=True)
        r = _run_one(shim, shim_out, top_k)
        results.append(r)
        if r["status"] == "OK":
            print(
                f"{shim:<22s} {r['status']:<6s} {str(r.get('pi_class', '?')):<8s} "
                f"{r.get('bsr', 0):>7.4f} {r.get('bayes_floor', 0):>7.3f} "
                f"{str(r.get('red_cells', '?')):>4s}  {r['elapsed_s']}s"
            )
        else:
            print(f"{shim:<22s} {r['status']:<6s}  error: {r.get('error', '')[:40]}")

    n_ok = sum(1 for r in results if r["status"] == "OK")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    print("-" * 78)
    print(f"Summary: {n_ok}/{len(all_shims)} OK, {n_fail} FAIL")

    summary_path = out_root / "verify_summary.json"
    summary_path.write_text(json.dumps({"results": results, "n_ok": n_ok, "n_fail": n_fail}, indent=2))
    print(f"Saved: {summary_path}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
