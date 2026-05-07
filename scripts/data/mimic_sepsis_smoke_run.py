#!/usr/bin/env python3
"""Mimic-only focused smoke run — exercises the full pipeline end-to-end on
the demo MIMIC-Sepsis scenarios across N open-weight models without
running the entire 10K-scenario corpus.

Useful as a Phase-B end-to-end validation BEFORE Phase C full 35k cohort.

Usage:
    PYTHONPATH=.. python scripts/data/mimic_sepsis_smoke_run.py \\
        --models qwen4b,gemma31b,llama4scout \\
        --output-dir results/mimic_sepsis_smoke
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models", default="qwen4b,gemma31b,llama4scout",
                   help="Comma-separated model_keys from full_690_runner.MODELS")
    p.add_argument("--host-overrides",
                   default="qwen4b=127.0.0.1
                           "gemma31b=127.0.0.1
                           "llama4scout=127.0.0.1
                   help="Comma-list of model=host:port overrides")
    p.add_argument("--output-dir", default="results/mimic_sepsis_smoke")
    p.add_argument("--runs", type=int, default=1)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    os.environ["CGA_BENCH_INCLUDE_AUTO_V2"] = "1"
    sys.path.insert(0, str(REPO_ROOT.parent))

    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    sl = ScenarioLoader(include_auto_v2=True)
    mimic_ids = sorted(s for s in sl.list_scenarios() if "mimic_sepsis" in s)
    if not mimic_ids:
        print("[error] no mimic_sepsis scenarios found", file=sys.stderr)
        return 1
    print(f"[info] found {len(mimic_ids)} mimic_sepsis scenarios")

    overrides = {}
    for kv in args.host_overrides.split(","):
        m, hp = kv.split("=", 1)
        h, p_ = hp.split(":")
        overrides[m.strip()] = (h.strip(), int(p_))

    models = [m.strip() for m in args.models.split(",")]

    out_dir = REPO_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    from cga_bench.scripts.experiments.full_690_runner import run_single_episode  # type: ignore

    summary = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_scenarios": len(mimic_ids),
        "models": models,
        "results": [],
    }

    for model_key in models:
        host, port = overrides.get(model_key, (None, None))
        model_dir = out_dir / model_key
        model_dir.mkdir(parents=True, exist_ok=True)
        n_ok, n_fail = 0, 0
        cgas: list[float] = []
        for sid in mimic_ids:
            for run_idx in range(args.runs):
                print(f"  [{model_key}] {sid} r{run_idx} ...", flush=True)
                try:
                    res = run_single_episode(
                        model_key, sid, run_idx, out_dir,
                        host_override=host, port_override=port,
                    )
                except Exception as exc:
                    n_fail += 1
                    print(f"    FAIL {type(exc).__name__}: {exc}")
                    continue
                if res is None:
                    n_fail += 1
                    print("    FAIL (None)")
                else:
                    n_ok += 1
                    cga = res.get("compliance_score") or 0
                    cgas.append(float(cga))
                    print(f"    ok CGA={cga:.3f} actions={res.get('actions_count')}")
        avg = sum(cgas) / max(len(cgas), 1)
        summary["results"].append({
            "model": model_key, "ok": n_ok, "fail": n_fail,
            "host": host, "port": port,
            "mean_cga": round(avg, 4),
            "n_with_cga": len(cgas),
        })
    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    (out_dir / "smoke_summary.json").write_text(
        json.dumps(summary, indent=2, default=str))
    print("\n[ok] summary written", out_dir / "smoke_summary.json")
    for r in summary["results"]:
        print(f"  {r['model']}: ok={r['ok']} fail={r['fail']} mean_cga={r['mean_cga']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
