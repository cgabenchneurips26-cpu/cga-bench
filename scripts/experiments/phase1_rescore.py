"""Phase 1.B — Re-score 16,944 episodes with typed verdict definitions.

Produces:
  1. evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json
     Same schema as verdict_matrix_v6.json + new columns:
       cwt_typed_pass: bool   (cwt_typed_verdict from verdict_definitions)
       cwt_typed_score: float (typed compliance score)
       dg_typed: float        (dg_typed_cost weighted sum)

  2. evidence_pack/dg/dg_typed_v1.parquet
     episode_id, model, scenario_id, dg_typed, dg_proxy

Usage:
    PYTHONPATH=. python scripts/experiments/phase1_rescore.py
    PYTHONPATH=. python scripts/experiments/phase1_rescore.py --dry-run  # first 100
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_V5 = REPO_ROOT / "results" / "full_706_v5"
VM_PATH = REPO_ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
OUTPUT_VM = REPO_ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_v6_typed_phase1.json"
OUTPUT_DG = REPO_ROOT / "evidence_pack" / "dg" / "dg_typed_v1.parquet"

SKIP_PREFIXES = ("checkpoint", "model_summary", ".claim", "log_")


def load_raw_episodes(results_dir: Path, limit: int = 0) -> dict[str, dict[str, Any]]:
    """Load raw episode JSON files from v5 results, keyed by composite ID."""
    episodes: dict[str, dict[str, Any]] = {}
    count = 0
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
            count += 1
            if limit and count >= limit:
                return episodes
    return episodes


def main() -> int:
    from assessor_core.spec.verdict_definitions import (
        CWT_TYPED_THRESHOLD,
        DG_TYPED_WEIGHTS,
        cwt_typed_verdict,
        dg_proxy,
        dg_typed_cost,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Process first 100 episodes only")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_V5)
    parser.add_argument("--vm-path", type=Path, default=VM_PATH)
    parser.add_argument("--output-vm", type=Path, default=OUTPUT_VM)
    parser.add_argument("--output-dg", type=Path, default=OUTPUT_DG)
    args = parser.parse_args()

    t0 = time.time()
    limit = 100 if args.dry_run else 0

    # --- Load verdict matrix ---
    print(f"[{time.strftime('%H:%M:%S')}] Loading verdict matrix: {args.vm_path}")
    with open(args.vm_path) as f:
        vm = json.load(f)
    pe = vm["per_episode"]
    print(f"  per_episode entries: {len(pe)}")

    # --- Load raw episodes ---
    print(f"[{time.strftime('%H:%M:%S')}] Loading raw episodes: {args.results_dir}")
    raw_eps = load_raw_episodes(args.results_dir, limit=limit)
    print(f"  loaded: {len(raw_eps)}")

    # --- Build join key from verdict matrix entries ---
    matched = 0
    unmatched = 0
    dg_rows: list[dict[str, Any]] = []

    for ep_entry in pe:
        sid = ep_entry.get("scenario_id", "")
        ri = ep_entry.get("run_index", 0)
        model_dir = ep_entry.get("model_dir", "")
        key = f"{sid}_{model_dir}_{ri}"

        raw = raw_eps.get(key)
        if raw is None:
            unmatched += 1
            # Fallback: keep original c2_pass as typed
            ep_entry["cwt_typed_pass"] = ep_entry.get("c2_pass", False)
            ep_entry["cwt_typed_score"] = ep_entry.get("c2_score", 0.0)
            ep_entry["dg_typed"] = 0.0
            continue

        matched += 1

        # Compute cwt_typed_verdict
        typed_pass = cwt_typed_verdict(raw)
        ep_entry["cwt_typed_pass"] = typed_pass

        # Also store the typed compliance score for sensitivity analysis
        # (replicate the internal computation)
        viol_events = raw.get("violation_events") or []
        typed_types = {"commission", "timing", "sequence"}
        typed_count = 0
        for v in viol_events:
            if not isinstance(v, dict):
                continue
            raw_type = str(v.get("violation_type", v.get("type", ""))).lower().strip()
            for canon in typed_types:
                if canon in raw_type:
                    typed_count += 1
                    break
        n_actions = len(raw.get("actions") or [])
        n_mandatory = raw.get("n_expected_actions", 5)
        denom = max(n_actions, n_mandatory, 1)
        typed_score = max(0.0, 1.0 - typed_count / denom)
        ep_entry["cwt_typed_score"] = round(typed_score, 4)

        # Compute dg_typed_cost
        dg_t = dg_typed_cost(raw)
        ep_entry["dg_typed"] = round(dg_t, 4)

        # Also compute original dg_proxy for comparison
        dg_p = dg_proxy(raw)
        ep_entry["dg_proxy"] = dg_p

        # Collect for parquet
        dg_rows.append(
            {
                "episode_id": ep_entry.get("episode_id", key),
                "model": ep_entry.get("model", model_dir),
                "scenario_id": sid,
                "run_index": ri,
                "dg_typed": round(dg_t, 4),
                "dg_proxy": dg_p,
            }
        )

    print(f"  matched={matched} unmatched={unmatched}")

    if args.dry_run and limit:
        # In dry-run, only process matched episodes
        pe = [ep for ep in pe if "cwt_typed_pass" in ep and ep.get("cwt_typed_score") is not None]
        print(f"  dry-run: {len(pe)} entries after filtering")

    # --- Summary stats ---
    total = len([ep for ep in pe if "cwt_typed_pass" in ep])
    orig_c2_pass = sum(1 for ep in pe if ep.get("c2_pass"))
    typed_pass_count = sum(1 for ep in pe if ep.get("cwt_typed_pass"))
    v4_hard_pass = sum(1 for ep in pe if ep.get("v4_hard"))

    print(f"\n=== Phase 1.B Re-scoring Summary (N={total}) ===")
    print(f"  CwT original pass:  {orig_c2_pass} ({100 * orig_c2_pass / max(total, 1):.1f}%)")
    print(f"  CwT-typed pass:     {typed_pass_count} ({100 * typed_pass_count / max(total, 1):.1f}%)")
    print(f"  TCC (v4_hard) pass: {v4_hard_pass} ({100 * v4_hard_pass / max(total, 1):.1f}%)")

    # Sensitivity: how many changed?
    changed = sum(1 for ep in pe if ep.get("c2_pass") != ep.get("cwt_typed_pass") and "cwt_typed_pass" in ep)
    print(f"  CwT→CwT-typed changed: {changed} ({100 * changed / max(total, 1):.1f}%)")

    mean_dg_typed = 0.0
    if dg_rows:
        mean_dg_typed = sum(r["dg_typed"] for r in dg_rows) / len(dg_rows)
    print(f"  Mean dg_typed: {mean_dg_typed:.3f}")

    # --- Update metadata ---
    if "metadata" not in vm:
        vm["metadata"] = {}
    vm["metadata"]["phase1_rescore"] = {
        "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "definition": "cwt_typed_pass: compliance over {commission,timing,sequence} only (DEVIATION+OMISSION excluded)",
        "cwt_typed_threshold": CWT_TYPED_THRESHOLD,
        "dg_typed_weights": DG_TYPED_WEIGHTS,
        "source": str(args.results_dir),
        "matched": matched,
        "unmatched": unmatched,
    }

    # --- Save verdict matrix ---
    args.output_vm.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_vm, "w") as f:
        json.dump(vm, f, indent=2, default=str)
    print(f"\n[{time.strftime('%H:%M:%S')}] Saved verdict matrix: {args.output_vm}")

    # --- Save dg parquet ---
    if dg_rows:
        try:
            import pandas as pd

            df = pd.DataFrame(dg_rows)
            args.output_dg.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(args.output_dg, index=False)
            print(f"[{time.strftime('%H:%M:%S')}] Saved dg parquet: {args.output_dg} ({len(df)} rows)")
        except ImportError:
            # Fallback to JSON if pandas not available
            fallback = args.output_dg.with_suffix(".json")
            with open(fallback, "w") as f:
                json.dump(dg_rows, f, indent=2)
            print(f"[{time.strftime('%H:%M:%S')}] Saved dg JSON (pandas unavailable): {fallback}")

    elapsed = time.time() - t0
    print(f"\n[{time.strftime('%H:%M:%S')}] Done in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
