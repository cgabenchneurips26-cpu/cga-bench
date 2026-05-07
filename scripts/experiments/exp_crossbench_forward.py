#!/usr/bin/env python3
"""X.3: TCC forward-direction re-score of MedAgentBench released trajectories.

Loads the 300 MAB observed episodes from
``data/episodes/medagentbench_observed_safety3_audit.jsonl``, maps each
episode's integer ``task_id`` (0-299) to one of 10 MAB task types
(``task_id // 30 + 1``), pulls the corresponding CGA-CPG mandatory
action set from ``MEDAGENTBENCH_TASK_MAPPINGS``, and re-scores each
episode with a TCC-style mandatory-completion rule. We then compare
against MAB's native "completed" status for a forward-vs-backward
confusion matrix and FA rate per task type.

This is the X track of the attack-gap plan. Method is intentionally
lightweight: we are answering "does TCC scoring on released MAB
trajectories reproduce E8's backward 20-35% FA band?", not
replicating MAB's full evaluation pipeline.

Usage
-----
    PYTHONPATH=. python scripts/experiments/exp_crossbench_forward.py
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
# Two insertions: repo root (for PYTHONPATH=.) and repo parent (so
# ``cga_bench.semantic_layer`` imports resolve — some modules in
# semantic_layer/ hard-code the ``cga_bench.`` namespace).
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from cga_bench.semantic_layer.external.medagentbench_mappings import (  # noqa: E402
    MEDAGENTBENCH_TASK_MAPPINGS,
)

DEFAULT_INPUT = "data/episodes/medagentbench_observed_safety3_audit.jsonl"
DEFAULT_OUT = "evidence_pack/cross_benchmark_forward/mab"

# MAB released fixtures: 300 episodes split into 10 task types of 30 each
MAB_INSTANCES_PER_TASK = 30


def task_id_to_type(tid: int) -> str:
    """Map MAB integer task_id to task<N> string key."""
    return f"task{tid // MAB_INSTANCES_PER_TASK + 1}"


def extract_performed_actions(events: list) -> set[str]:
    """Heuristic: FHIR method + resource type → canonical action token.

    We deliberately keep this loose — the question is whether the
    *set* of actions overlaps the mandatory list, not whether we
    perfectly replicate MAB's own action vocabulary.
    """
    out: set[str] = set()
    resource_types = (
        "Patient",
        "Observation",
        "Condition",
        "MedicationRequest",
        "MedicationStatement",
        "Procedure",
        "DiagnosticReport",
        "ServiceRequest",
        "Encounter",
    )
    for ev in events or []:
        tc = ev.get("tool_call") or {}
        method = (tc.get("method") or "").lower()
        url = tc.get("url") or ""
        for rt in resource_types:
            if f"/{rt}" in url or f"{rt}?" in url:
                out.add(f"{method}_{rt.lower()}")
        if method == "post":
            out.add("create_resource")
        if method == "get":
            out.add("query_fhir")
    return out


def _action_token_hits(mandatory_phrase: str, performed: set[str]) -> bool:
    """Fuzzy normalise and check if any performed token overlaps the mandatory."""
    target = mandatory_phrase.lower().replace("_", "").replace(" ", "")
    for p in performed:
        if not target or not p:
            continue
        p_norm = p.lower().replace("_", "").replace(" ", "")
        if target in p_norm or p_norm in target:
            return True
    return False


def tcc_verdict(performed: set[str], cpg_mandatory: list[str]) -> bool:
    """Pass iff every mandatory action has some fuzzy-match in performed."""
    if not cpg_mandatory:
        return True
    return all(_action_token_hits(m, performed) for m in cpg_mandatory)


def score_episodes(path: Path) -> dict:
    per_task: dict[str, dict] = {}
    native_counts: Counter = Counter()
    tcc_counts: Counter = Counter()
    confusion: Counter = Counter()
    skipped = 0

    with open(path) as f:
        for line in f:
            r = json.loads(line)
            tid = r.get("task_id")
            if tid is None:
                skipped += 1
                continue
            tt = task_id_to_type(int(tid))
            mapping = MEDAGENTBENCH_TASK_MAPPINGS.get(tt)
            if not mapping:
                skipped += 1
                continue
            native_pass = r.get("status") == "completed"
            performed = extract_performed_actions(r.get("events") or [])
            tcc_pass = tcc_verdict(performed, mapping["cpg_mandatory"])

            bucket = per_task.setdefault(
                tt,
                {
                    "n": 0,
                    "native_pass": 0,
                    "tcc_pass": 0,
                    "fa": 0,
                    "fr": 0,
                    "agree_pass": 0,
                    "agree_fail": 0,
                    "cpg_mandatory": list(mapping["cpg_mandatory"]),
                    "guideline": mapping.get("guideline"),
                },
            )
            bucket["n"] += 1
            bucket["native_pass"] += int(native_pass)
            bucket["tcc_pass"] += int(tcc_pass)
            if native_pass and not tcc_pass:
                bucket["fa"] += 1
            if not native_pass and tcc_pass:
                bucket["fr"] += 1
            if native_pass and tcc_pass:
                bucket["agree_pass"] += 1
            if not native_pass and not tcc_pass:
                bucket["agree_fail"] += 1
            native_counts[native_pass] += 1
            tcc_counts[tcc_pass] += 1
            confusion[(native_pass, tcc_pass)] += 1

    total = sum(p["n"] for p in per_task.values())
    fa_total = sum(p["fa"] for p in per_task.values())
    fr_total = sum(p["fr"] for p in per_task.values())
    agree_pass_total = sum(p["agree_pass"] for p in per_task.values())
    agree_fail_total = sum(p["agree_fail"] for p in per_task.values())

    # Per-task FA rates
    for p in per_task.values():
        p["fa_rate"] = round(p["fa"] / p["n"], 4) if p["n"] else 0.0

    return {
        "total_episodes": total,
        "skipped": skipped,
        "native_pass_total": sum(1 for k, v in native_counts.items() if k for _ in range(v)),
        "native_pass": dict(native_counts),
        "tcc_pass": dict(tcc_counts),
        "confusion_matrix": {
            f"native={k[0]}_tcc={k[1]}": v for k, v in confusion.items()
        },
        "fa_total": fa_total,
        "fr_total": fr_total,
        "agree_pass_total": agree_pass_total,
        "agree_fail_total": agree_fail_total,
        "fa_rate": round(fa_total / total, 4) if total else 0.0,
        "fr_rate": round(fr_total / total, 4) if total else 0.0,
        "agreement_rate": round(
            (agree_pass_total + agree_fail_total) / total, 4
        )
        if total
        else 0.0,
        "per_task_type": per_task,
    }


def _emit_macros(res: dict, path: Path) -> None:
    lines = [
        "% Auto-generated by scripts/experiments/exp_crossbench_forward.py",
        f"\\providecommand{{\\crossBenchMabTotal}}{{{res['total_episodes']}}}",
        f"\\providecommand{{\\crossBenchMabFA}}{{{res['fa_total']}}}",
        f"\\providecommand{{\\crossBenchMabFARate}}{{{res['fa_rate']:.4f}}}",
        f"\\providecommand{{\\crossBenchMabFAPct}}{{{res['fa_rate'] * 100:.1f}}}",
        f"\\providecommand{{\\crossBenchMabFR}}{{{res['fr_total']}}}",
        f"\\providecommand{{\\crossBenchMabFRPct}}{{{res['fr_rate'] * 100:.1f}}}",
        f"\\providecommand{{\\crossBenchMabAgreePct}}{{{res['agreement_rate'] * 100:.1f}}}",
        f"\\providecommand{{\\crossBenchMabNTaskTypes}}{{{len(res['per_task_type'])}}}",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="X.3 MAB forward-direction TCC re-score")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", default=DEFAULT_OUT)
    args = parser.parse_args()

    input_path = ROOT / args.input
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    print(f"Reading {input_path}")
    res = score_episodes(input_path)
    res["timestamp"] = datetime.now(UTC).isoformat()
    res["input_path"] = str(input_path.relative_to(ROOT))

    print(f"\nTotal: {res['total_episodes']} (skipped {res['skipped']})")
    print(f"Native pass: {res['native_pass']}  TCC pass: {res['tcc_pass']}")
    print(f"Confusion: {res['confusion_matrix']}")
    print(
        f"FA={res['fa_total']} ({res['fa_rate'] * 100:.2f}%)  "
        f"FR={res['fr_total']} ({res['fr_rate'] * 100:.2f}%)  "
        f"agreement={res['agreement_rate'] * 100:.2f}%"
    )
    print("\nPer task:")
    for tt, p in sorted(res["per_task_type"].items()):
        print(
            f"  {tt:>7s}: n={p['n']:>3d}  FA={p['fa']:>3d}  FR={p['fr']:>3d}  "
            f"agree_pass={p['agree_pass']:>3d}  agree_fail={p['agree_fail']:>3d}  "
            f"FA_rate={p['fa_rate'] * 100:5.1f}%"
        )

    (out_dir / "results.json").write_text(json.dumps(res, indent=2) + "\n")
    _emit_macros(res, out_dir / "macros.tex")
    print(f"\nSaved: {out_dir}/(results.json, macros.tex)")


if __name__ == "__main__":
    main()
