#!/usr/bin/env python3
"""C6: Audit-guided evaluator selection experiment.

Demonstrates that pi-class diversity (from step1) predicts evaluator
independence (Kendall tau-b), making the audit harness actionable.

Addresses reviewer attack: "evaluator audit is just descriptive, not useful."

Usage:
    PYTHONPATH=. python scripts/experiments/exp_audit_guided_selection.py
    PYTHONPATH=. python scripts/experiments/exp_audit_guided_selection.py --out-dir evidence_pack/audit
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audit.metrics.selection import audit_guided_selection  # noqa: E402
from audit.shims import SHIM_REGISTRY  # noqa: E402
from scripts.audit.evaluator_audit import step1_pi_class  # noqa: E402

CORE_SHIMS = ["dxem", "ac_proxy", "mab_proxy", "c2_shim", "acov_shim", "v4_hard"]


def main() -> None:
    parser = argparse.ArgumentParser(description="C6: Audit-guided evaluator selection")
    parser.add_argument("--out-dir", type=str, default="evidence_pack/audit", help="Output directory")
    parser.add_argument(
        "--shims",
        type=str,
        nargs="+",
        default=CORE_SHIMS,
        help="Shim names to include",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Instantiate evaluators and classify pi-classes
    print("Step 1: Classifying evaluator pi-classes...")
    evaluators = {}
    pi_classes = {}
    for name in args.shims:
        ev = SHIM_REGISTRY[name]()
        evaluators[name] = ev
        s1 = step1_pi_class(ev)
        pi_classes[name] = s1["pi_class"]
        print(f"  {name}: pi_class = {s1['pi_class']}")

    # Run experiment
    print(f"\nStep 2: Computing {len(evaluators)} x {len(evaluators)} pairwise tau...")
    result = audit_guided_selection(evaluators, pi_classes)

    # Print summary
    ag = result["audit_guided_pair"]
    sc = result["same_class_stats"]
    cc = result["cross_class_stats"]
    print(f"\nResults ({result['n_pairs']} pairs):")
    print(
        f"  Audit-guided pair: {ag['evaluators'][0]} ({ag['pi_classes'][0]}) "
        f"vs {ag['evaluators'][1]} ({ag['pi_classes'][1]})"
    )
    print(f"  Audit-guided tau:  {ag['tau']:.4f} (pi_distance={ag['pi_distance']})")
    print(f"  Same-class mean:   {sc['mean_tau_nondegen']:.4f} ({sc['n_pairs']} pairs)")
    print(f"  Cross-class mean:  {cc['mean_tau_nondegen']:.4f} ({cc['n_pairs']} pairs)")
    print(f"  Separation confirmed: {result['separation_confirmed']}")
    print(f"  Degenerate pairs:  {result['degenerate_pairs']['n_pairs']}")

    # Save results
    result["timestamp"] = datetime.now(UTC).isoformat()
    json_path = out_dir / "c6_audit_guided_selection.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved: {json_path}")

    # Emit LaTeX macros
    macros_path = out_dir / "c6_selection_macros.tex"

    def _tex_escape(s: str) -> str:
        return s.replace("_", r"\_")

    macros = [
        f"\\providecommand{{\\cSixNPairs}}{{{result['n_pairs']}}}",
        f"\\providecommand{{\\cSixAuditTau}}{{{ag['tau']:.4f}}}",
        f"\\providecommand{{\\cSixAuditDist}}{{{ag['pi_distance']}}}",
        f"\\providecommand{{\\cSixAuditPairA}}{{{_tex_escape(ag['evaluators'][0])}}}",
        f"\\providecommand{{\\cSixAuditPairB}}{{{_tex_escape(ag['evaluators'][1])}}}",
        f"\\providecommand{{\\cSixSameClassMean}}{{{sc['mean_tau_nondegen']:.4f}}}",
        f"\\providecommand{{\\cSixCrossClassMean}}{{{cc['mean_tau_nondegen']:.4f}}}",
        f"\\providecommand{{\\cSixSeparation}}{{{str(result['separation_confirmed']).lower()}}}",
    ]
    macros_path.write_text("\n".join(macros) + "\n")
    print(f"Saved: {macros_path}")


if __name__ == "__main__":
    main()
