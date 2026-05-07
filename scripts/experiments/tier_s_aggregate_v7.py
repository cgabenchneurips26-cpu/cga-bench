"""Tier S Phase B-2 — aggregate expansion_v7 raw episodes per endpoint.

Reads raw episode JSON files from results/expansion_v7/{endpoint}/, applies
the Phase 1-frozen verdict definitions (verdict_definitions.py), and emits
per-endpoint aggregate metrics + a regression diff vs the Apr 23 baseline
(tier_s_robustness.json).

Each raw episode contains compliance_score + violation_events but NOT the
canonical evaluator verdicts. We recompute them with the locked definitions
to keep this aggregation aligned with the rest of the Phase 1 pipeline.

Output
------
    evidence_pack/tier_s/expansion_v7_aggregated.json
        per-endpoint pass/FA rates, compliance distribution, episode counts
    evidence_pack/tier_s/tier_s_regression_diff.md
        markdown diff vs Apr 23 baseline; flags |Δ| ≥ 5pp on key metrics

Usage
-----
    PYTHONPATH=..:. /home/anonymous-org/anaconda3/bin/python3.13 \
        scripts/experiments/tier_s_aggregate_v7.py
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent))  # for cga_bench package

from assessor_core.spec.verdict_definitions import (  # noqa: E402
    asc_verdict,
    cwt_typed_4type_verdict,
    cwt_typed_verdict,
    cwt_verdict,
    paf_verdict,
    tcc_verdict,
)

EXPANSION_DIR = REPO_ROOT / "results" / "expansion_v7"
BASELINE = REPO_ROOT / "evidence_pack" / "tier_s" / "tier_s_robustness.json"
OUTPUT_JSON = REPO_ROOT / "evidence_pack" / "tier_s" / "expansion_v7_aggregated.json"
OUTPUT_MD = REPO_ROOT / "evidence_pack" / "tier_s" / "tier_s_regression_diff.md"

REGRESSION_PP_THRESHOLD = 5.0  # |Δ| ≥ 5pp flagged


def aggregate_endpoint(endpoint_dir: Path) -> dict[str, Any]:
    """Read every episode JSON in endpoint_dir and compute aggregate metrics."""
    files = sorted(endpoint_dir.glob("*.json"))
    n_total = 0
    n_passed_each: dict[str, int] = defaultdict(int)
    fa_each: dict[str, int] = defaultdict(int)  # eval pass + TCC fail
    compliance_values: list[float] = []
    violation_type_counts: dict[str, int] = defaultdict(int)

    for fp in files:
        try:
            ep = json.loads(fp.read_text())
        except Exception:
            continue
        if not isinstance(ep, dict):
            continue
        if "scenario_id" not in ep or "actions" not in ep:
            continue
        n_total += 1

        tcc_pass = tcc_verdict(ep)
        cwt_pass = cwt_verdict(ep)
        cwt_3type = cwt_typed_verdict(ep)
        cwt_4type = cwt_typed_4type_verdict(ep)
        asc_pass = asc_verdict(ep)
        paf_pass = paf_verdict(ep)

        if tcc_pass:
            n_passed_each["TCC"] += 1
        if cwt_pass:
            n_passed_each["CwT"] += 1
        if cwt_3type:
            n_passed_each["CwT-3type"] += 1
        if cwt_4type:
            n_passed_each["CwT-4type"] += 1
        if asc_pass:
            n_passed_each["ASC"] += 1
        if paf_pass:
            n_passed_each["PAF"] += 1

        # FA = evaluator passes BUT TCC fails (i.e., agent had hard violations)
        if not tcc_pass:
            if cwt_pass:
                fa_each["CwT"] += 1
            if cwt_3type:
                fa_each["CwT-3type"] += 1
            if cwt_4type:
                fa_each["CwT-4type"] += 1
            if asc_pass:
                fa_each["ASC"] += 1
            if paf_pass:
                fa_each["PAF"] += 1

        c = ep.get("compliance_score")
        if isinstance(c, (int, float)):
            compliance_values.append(float(c))

        for v in ep.get("violation_events") or []:
            if not isinstance(v, dict):
                continue
            vt = str(v.get("violation_type", v.get("type", ""))).lower()
            for canon in ("omission", "commission", "timing", "sequence", "deviation"):
                if canon in vt:
                    violation_type_counts[canon] += 1
                    break

    pass_rates = {k: round(100 * v / max(n_total, 1), 2) for k, v in n_passed_each.items()}
    fa_rates = {k: round(100 * v / max(n_total, 1), 2) for k, v in fa_each.items()}

    return {
        "endpoint": endpoint_dir.name,
        "n_episodes": n_total,
        "pass_counts": dict(n_passed_each),
        "pass_rates_pct": pass_rates,
        "fa_counts": dict(fa_each),
        "fa_rates_pct": fa_rates,
        "mean_compliance": round(sum(compliance_values) / len(compliance_values), 4) if compliance_values else None,
        "min_compliance": round(min(compliance_values), 4) if compliance_values else None,
        "max_compliance": round(max(compliance_values), 4) if compliance_values else None,
        "violation_type_counts": dict(violation_type_counts),
    }


def consolidate_by_base_model(per_endpoint: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group endpoints by base model (e.g., oss120b, oss120b_exp2 -> oss120b)."""
    base_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ep in per_endpoint:
        name = ep["endpoint"]
        # Strip _exp1, _exp2, _local1, _react_s2 etc. Keep base model.
        for suffix in ("_react_s2", "_local1", "_local2", "_local", "_exp1", "_exp2", "_exp3"):
            if name.endswith(suffix):
                base = name[: -len(suffix)]
                break
        else:
            base = name
        base_groups[base].append(ep)

    consolidated: dict[str, dict[str, Any]] = {}
    for base, members in base_groups.items():
        n_eps = sum(m["n_episodes"] for m in members)
        merged_pass: dict[str, int] = defaultdict(int)
        merged_fa: dict[str, int] = defaultdict(int)
        merged_viol: dict[str, int] = defaultdict(int)
        compliances: list[float] = []
        for m in members:
            for k, v in m["pass_counts"].items():
                merged_pass[k] += v
            for k, v in m["fa_counts"].items():
                merged_fa[k] += v
            for k, v in m["violation_type_counts"].items():
                merged_viol[k] += v
            if m["mean_compliance"] is not None:
                compliances.append(m["mean_compliance"])
        consolidated[base] = {
            "base_model": base,
            "n_endpoints": len(members),
            "endpoints": [m["endpoint"] for m in members],
            "n_episodes_total": n_eps,
            "pass_rates_pct": {k: round(100 * v / max(n_eps, 1), 2) for k, v in merged_pass.items()},
            "fa_rates_pct": {k: round(100 * v / max(n_eps, 1), 2) for k, v in merged_fa.items()},
            "mean_compliance_avg": round(sum(compliances) / len(compliances), 4) if compliances else None,
            "violation_type_counts": dict(merged_viol),
        }
    return consolidated


def regression_diff(
    consolidated: dict[str, dict[str, Any]],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """Compare aggregated metrics against tier_s_robustness.json baseline.

    Baseline reports global metrics on 14,826 W8 episodes (full subset, not
    per-model). The diff is therefore at the aggregate level, comparing
    expansion_v7 totals to baseline['full'].
    """
    base_full = baseline.get("full", {})
    base_pass = base_full.get("eval_pass_rates", {})
    base_fa = base_full.get("eval_fa_rates", {})

    # Aggregate across all base models
    n_total = sum(m["n_episodes_total"] for m in consolidated.values())
    pass_sums: dict[str, float] = defaultdict(float)
    fa_sums: dict[str, float] = defaultdict(float)
    for m in consolidated.values():
        for k, pct in m["pass_rates_pct"].items():
            pass_sums[k] += pct * m["n_episodes_total"] / 100
        for k, pct in m["fa_rates_pct"].items():
            fa_sums[k] += pct * m["n_episodes_total"] / 100

    agg_pass_pct = {k: round(100 * v / max(n_total, 1), 2) for k, v in pass_sums.items()}
    agg_fa_pct = {k: round(100 * v / max(n_total, 1), 2) for k, v in fa_sums.items()}

    # Baseline keys: AC-Proxy (=ASC), MAB-Proxy (=PAF), C2 (=CwT), CGA-Bench (=TCC)
    key_map_pass = {"ASC": "AC-Proxy", "PAF": "MAB-Proxy", "CwT": "C2", "TCC": "CGA-Bench"}

    rows: list[dict[str, Any]] = []
    for ours, base_key in key_map_pass.items():
        b_pass = base_pass.get(base_key)
        b_fa = base_fa.get(base_key)
        cur_pass = agg_pass_pct.get(ours)
        cur_fa = agg_fa_pct.get(ours)
        delta_pass = round(cur_pass - b_pass, 2) if cur_pass is not None and b_pass is not None else None
        delta_fa = round(cur_fa - b_fa, 2) if cur_fa is not None and b_fa is not None else None
        flag = ""
        if delta_pass is not None and abs(delta_pass) >= REGRESSION_PP_THRESHOLD:
            flag += " [PASS-REGRESSION]"
        if delta_fa is not None and abs(delta_fa) >= REGRESSION_PP_THRESHOLD:
            flag += " [FA-REGRESSION]"
        rows.append(
            {
                "evaluator": ours,
                "baseline_key": base_key,
                "baseline_pass_pct": b_pass,
                "current_pass_pct": cur_pass,
                "delta_pass_pp": delta_pass,
                "baseline_fa_pct": b_fa,
                "current_fa_pct": cur_fa,
                "delta_fa_pp": delta_fa,
                "flag": flag.strip(),
            }
        )
    return {
        "aggregate_n_episodes": n_total,
        "baseline_n_episodes": base_full.get("n_episodes"),
        "baseline_n_hard": base_full.get("n_hard"),
        "rows": rows,
    }


def write_md_diff(diff: dict[str, Any], consolidated: dict[str, dict[str, Any]], out: Path) -> None:
    lines = [
        "# Tier S Regression Diff — expansion_v7 vs Apr 23 baseline",
        "",
        f"_Generated: {time.strftime('%Y-%m-%dT%H:%M:%S')}_",
        "",
        "## Episode counts",
        f"- expansion_v7 aggregate: **{diff['aggregate_n_episodes']:,}** episodes across {len(consolidated)} base models",
        f"- Apr 23 baseline (`tier_s_robustness.json` full): {diff.get('baseline_n_episodes')} episodes",
        "",
        "## Per-endpoint episode counts (consolidated by base model)",
        "",
        "| Base model | Endpoints | n_episodes | mean_compliance |",
        "|---|---|---|---|",
    ]
    for base, m in sorted(consolidated.items()):
        lines.append(
            f"| {base} | {m['n_endpoints']} ({', '.join(m['endpoints'])}) | "
            f"{m['n_episodes_total']:,} | {m['mean_compliance_avg']} |"
        )
    lines.append("")
    lines.append("## Evaluator pass-rate / FA diff vs Apr 23 baseline (W8 full)")
    lines.append("")
    lines.append("| Evaluator | Baseline pass% | v7 pass% | Δpass | Baseline FA% | v7 FA% | ΔFA | Flag |")
    lines.append("|---|---|---|---|---|---|---|---|")
    def _fmt_d(v: float | None) -> str:
        return f"{v:+.2f}" if isinstance(v, (int, float)) else "n/a"

    def _fmt_p(v: float | None) -> str:
        return f"{v}" if v is not None else "n/a"

    for r in diff["rows"]:
        lines.append(
            f"| {r['evaluator']} | {_fmt_p(r['baseline_pass_pct'])} | {_fmt_p(r['current_pass_pct'])} | "
            f"{_fmt_d(r['delta_pass_pp'])} | {_fmt_p(r['baseline_fa_pct'])} | {_fmt_p(r['current_fa_pct'])} | "
            f"{_fmt_d(r['delta_fa_pp'])} | {r['flag'] or '—'} |"
        )
    lines.append("")
    lines.append(f"**Threshold for regression flag**: |Δ| ≥ {REGRESSION_PP_THRESHOLD}pp.")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- Comparison is across different scenario sets: baseline=14,826 W8 episodes, "
        "expansion_v7=mixed Tier S coverage. Exact numerical equivalence is NOT expected — "
        "regression flags catch large directional shifts only."
    )
    lines.append(
        "- Tier S scenarios have grown from 535 (Apr 23, 17 CPGs subset) to 2,480 (current, 31 CPGs). "
        "Verdict definitions are frozen via `verdict_definitions.py`."
    )
    out.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expansion-dir", type=Path, default=EXPANSION_DIR)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    t0 = time.time()
    if not args.expansion_dir.exists():
        print(f"ERROR: expansion dir not found: {args.expansion_dir}", file=sys.stderr)
        return 2
    endpoints = sorted(d for d in args.expansion_dir.iterdir() if d.is_dir())
    print(f"[{time.strftime('%H:%M:%S')}] Aggregating {len(endpoints)} endpoints from {args.expansion_dir}")

    per_endpoint: list[dict[str, Any]] = []
    for d in endpoints:
        rec = aggregate_endpoint(d)
        per_endpoint.append(rec)
        print(
            f"  {d.name:<28s}  n={rec['n_episodes']:>4d}  "
            f"TCC={rec['pass_rates_pct'].get('TCC', 0):>5.1f}%  "
            f"CwT={rec['pass_rates_pct'].get('CwT', 0):>5.1f}%  "
            f"4type={rec['pass_rates_pct'].get('CwT-4type', 0):>5.1f}%  "
            f"3type={rec['pass_rates_pct'].get('CwT-3type', 0):>5.1f}%"
        )

    consolidated = consolidate_by_base_model(per_endpoint)
    print(f"\n[{time.strftime('%H:%M:%S')}] Consolidated to {len(consolidated)} base models")

    baseline = json.loads(args.baseline.read_text())
    diff = regression_diff(consolidated, baseline)

    print(f"\n=== Regression diff (|Δ| ≥ {REGRESSION_PP_THRESHOLD}pp flagged) ===")

    def _fmt_delta(v: float | None) -> str:
        return f"{v:+.2f}" if isinstance(v, (int, float)) else "n/a"

    def _fmt_pct(v: float | None) -> str:
        return f"{v}" if v is not None else "n/a"

    for r in diff["rows"]:
        marker = r["flag"] or "OK"
        print(
            f"  {r['evaluator']:<6s}  pass: {_fmt_pct(r['baseline_pass_pct'])} → {_fmt_pct(r['current_pass_pct'])} "
            f"(Δ={_fmt_delta(r['delta_pass_pp'])}pp)   "
            f"FA: {_fmt_pct(r['baseline_fa_pct'])} → {_fmt_pct(r['current_fa_pct'])} "
            f"(Δ={_fmt_delta(r['delta_fa_pp'])}pp)   {marker}"
        )

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "expansion_dir": str(args.expansion_dir.relative_to(REPO_ROOT)),
        "baseline_path": str(args.baseline.relative_to(REPO_ROOT)),
        "regression_pp_threshold": REGRESSION_PP_THRESHOLD,
        "per_endpoint": per_endpoint,
        "consolidated_by_base_model": consolidated,
        "regression_diff": diff,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, default=str) + "\n")
    write_md_diff(diff, consolidated, args.output_md)

    elapsed = time.time() - t0
    print(f"\n[{time.strftime('%H:%M:%S')}] Saved:")
    print(f"  {args.output_json}")
    print(f"  {args.output_md}")
    print(f"  ({elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
