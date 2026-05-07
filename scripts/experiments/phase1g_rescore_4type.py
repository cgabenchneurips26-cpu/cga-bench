"""Phase 1.G — Augment typed verdict matrix with 4-type CwT column.

Reads the existing Phase 1.B output (verdict_matrix_v6_typed_phase1.json) which
already has cwt_typed_pass (3-type), reloads raw episodes for the 4-type
recompute, and writes a new column cwt_typed_4type_pass alongside.

4-type CwT excludes ONLY OMISSION (keeps commission, timing, sequence,
deviation). It is the principled middle between Original (5-type) and
Typed (3-type).

Output: evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json (same file,
augmented in place — preserves all existing columns and adds:
    cwt_typed_4type_pass: bool
    cwt_typed_4type_score: float

Usage:
    PYTHONPATH=..:. /home/anonymous-org/anaconda3/bin/python3.13 \
        scripts/experiments/phase1g_rescore_4type.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_V5 = REPO_ROOT / "results" / "full_706_v5"
TYPED_VM = REPO_ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_v6_typed_phase1.json"

SKIP_PREFIXES = ("checkpoint", "model_summary", ".claim", "log_")


def load_raw_episodes(results_dir: Path) -> dict[str, dict[str, Any]]:
    """Load raw v5 episodes keyed by '{scenario_id}_{model_dir}_{run_index}'."""
    episodes: dict[str, dict[str, Any]] = {}
    for model_dir in sorted(results_dir.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("_"):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            if ep_file.name.startswith(SKIP_PREFIXES):
                continue
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
            except Exception:
                continue
            sid = ep.get("scenario_id", "")
            ri = ep.get("run_index")
            if not sid or ri is None:
                continue
            key = f"{sid}_{model_dir.name}_{ri}"
            ep["_model_dir"] = model_dir.name
            episodes[key] = ep
    return episodes


def main() -> int:
    from assessor_core.spec.verdict_definitions import (
        CWT_TYPED_THRESHOLD,
        cwt_typed_4type_verdict,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--typed-vm", type=Path, default=TYPED_VM)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_V5)
    args = parser.parse_args()

    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Loading typed VM: {args.typed_vm}")
    with open(args.typed_vm) as f:
        vm = json.load(f)
    pe = vm["per_episode"]
    print(f"  per_episode entries: {len(pe)}")

    print(f"[{time.strftime('%H:%M:%S')}] Loading raw episodes: {args.results_dir}")
    raw_eps = load_raw_episodes(args.results_dir)
    print(f"  raw loaded: {len(raw_eps)}")

    matched = 0
    unmatched = 0
    four_pass = 0
    three_pass = 0

    for ep in pe:
        sid = ep.get("scenario_id", "")
        ri = ep.get("run_index", 0)
        model_dir = ep.get("model_dir", "")
        key = f"{sid}_{model_dir}_{ri}"
        raw = raw_eps.get(key)
        if raw is None:
            unmatched += 1
            ep["cwt_typed_4type_pass"] = ep.get("cwt_typed_pass", False)
            ep["cwt_typed_4type_score"] = ep.get("cwt_typed_score", 0.0)
            continue
        matched += 1
        passes = cwt_typed_4type_verdict(raw)
        ep["cwt_typed_4type_pass"] = passes
        if passes:
            four_pass += 1
        if ep.get("cwt_typed_pass"):
            three_pass += 1

        # Replicate score computation for transparency.
        viol_events = raw.get("violation_events") or []
        four_types = {"commission", "timing", "sequence", "deviation"}
        four_count = 0
        for v in viol_events:
            if not isinstance(v, dict):
                continue
            raw_type = str(v.get("violation_type", v.get("type", ""))).lower().strip()
            for canon in four_types:
                if canon in raw_type:
                    four_count += 1
                    break
        n_actions = len(raw.get("actions") or [])
        denom = max(n_actions, 1)
        four_score = max(0.0, 1.0 - four_count / denom)
        ep["cwt_typed_4type_score"] = round(four_score, 4)

    n = len(pe)
    print(f"\n=== Phase 1.G 4-type Augmentation Summary ===")
    print(f"  matched={matched} unmatched={unmatched} total={n}")
    print(f"  CwT 3-type pass:  {three_pass} ({100 * three_pass / max(n, 1):.1f}%)")
    print(f"  CwT 4-type pass:  {four_pass} ({100 * four_pass / max(n, 1):.1f}%)")

    # Update metadata
    if "metadata" not in vm:
        vm["metadata"] = {}
    vm["metadata"]["phase1g_4type"] = {
        "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "definition": "cwt_typed_4type_pass: compliance over {commission,timing,sequence,deviation} (only OMISSION excluded)",
        "threshold": CWT_TYPED_THRESHOLD,
        "matched": matched,
        "unmatched": unmatched,
    }

    args.typed_vm.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.typed_vm.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(vm, f, indent=2, default=str)
    tmp.replace(args.typed_vm)
    print(f"\n[{time.strftime('%H:%M:%S')}] Saved (in-place): {args.typed_vm}")

    elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] Done in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
