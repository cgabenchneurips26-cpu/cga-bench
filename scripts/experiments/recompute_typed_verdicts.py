"""Recompute CwT verdicts using typed_compliance_score (DEVIATION excluded).

Per evaluator_audit_VII finding: CwT (C2) verdict reads OVERALL compliance
which counts DEVIATION → observer-dependent on allowed_actions. Option C
defines CwT as "compliance over typed violations only" (OMISSION,
COMMISSION, TIMING, SEQUENCE — the source-grounded constraint types).

Output:
  evidence_pack/analysis/verdict_matrix_v6_typed.json
    same schema as v6 + new fields:
      c2_pass_typed: bool         (compliance ≥ 0.7 with DEV excluded)
      c2_score_typed: float
    other verdicts (dxem, ac_proxy, mab_proxy, v4_hard) unchanged.

Usage:
    PYTHONPATH=. python scripts/experiments/recompute_typed_verdicts.py
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))


TYPED_VIOL_TYPES = {"omission", "commission", "timing", "sequence"}
C2_THRESHOLD = 0.7


def index_phase_a_episodes(phase_a_dir: str) -> dict:
    """Build (scenario_id, run_index, model_dir) → episode_data map."""
    out = {}
    for m in os.listdir(phase_a_dir):
        md = f"{phase_a_dir}/{m}"
        if not os.path.isdir(md) or m.startswith("_"):
            continue
        for f in glob.glob(f"{md}/*.json"):
            base = os.path.basename(f)
            if base.startswith(("checkpoint", "model_summary", ".claim")):
                continue
            try:
                d = json.load(open(f))
            except Exception:
                continue
            sid = d.get("scenario_id")
            ri = d.get("run_index")
            if sid is None or ri is None:
                continue
            viols = d.get("violations_by_type") or {}
            n_actions = d.get("actions_count", len(d.get("actions") or []))
            n_mandatory = d.get("n_expected_actions", 5)
            denom = max(n_actions, n_mandatory, 1)
            typed_count = sum(viols.get(t, 0) for t in TYPED_VIOL_TYPES)
            typed_compliance = max(0.0, 1.0 - typed_count / denom)
            out[(sid, ri, m)] = {
                "comp": d.get("compliance_score", 0),
                "typed_comp": typed_compliance,
                "viols": viols,
                "n_actions": n_actions,
                "n_mandatory": n_mandatory,
            }
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vmatrix", default="evidence_pack/analysis/verdict_matrix_v6.json")
    p.add_argument("--phase-a-dir", default="results/full_v6a_706")
    p.add_argument("--output", default="evidence_pack/analysis/verdict_matrix_v6_typed.json")
    args = p.parse_args()

    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] loading {args.vmatrix}")
    vm = json.load(open(args.vmatrix))
    pe = vm["per_episode"]
    print(f"  per_episode: {len(pe)}")

    print(f"[{time.strftime('%H:%M:%S')}] indexing {args.phase_a_dir}")
    eps_idx = index_phase_a_episodes(args.phase_a_dir)
    print(f"  indexed: {len(eps_idx)}")

    print(f"[{time.strftime('%H:%M:%S')}] joining + recomputing typed CwT")
    matched = 0
    unmatched = 0
    for ep in pe:
        key = (ep["scenario_id"], ep["run_index"], ep["model_dir"])
        if key not in eps_idx:
            unmatched += 1
            ep["c2_pass_typed"] = ep["c2_pass"]  # fallback
            ep["c2_score_typed"] = ep["c2_score"]
            continue
        e = eps_idx[key]
        ep["c2_score_typed"] = round(e["typed_comp"], 4)
        ep["c2_pass_typed"] = e["typed_comp"] >= C2_THRESHOLD
        matched += 1
    print(f"  matched={matched} unmatched={unmatched}")

    # Update metadata
    if "metadata" in vm:
        vm["metadata"]["typed_recompute"] = {
            "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "definition": "CwT pass iff typed_compliance_score >= 0.7; typed_compliance excludes DEVIATION",
            "typed_viol_types": sorted(TYPED_VIOL_TYPES),
            "c2_threshold": C2_THRESHOLD,
            "phase_a_source": args.phase_a_dir,
            "doc_ref": "docs/critical_review/evaluator_audit_VII.md",
        }

    # Sanity counts
    orig_pass = sum(1 for ep in pe if ep["c2_pass"])
    typed_pass = sum(1 for ep in pe if ep["c2_pass_typed"])
    print("\n=== CwT pass rate ===")
    print(f"  Original (overall comp): {orig_pass}/{len(pe)} = {100 * orig_pass / len(pe):.2f}%")
    print(f"  Typed (no DEV):          {typed_pass}/{len(pe)} = {100 * typed_pass / len(pe):.2f}%")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    open(args.output, "w").write(json.dumps(vm, indent=2, default=str))
    print(f"\n[{time.strftime('%H:%M:%S')}] saved → {args.output}  ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
