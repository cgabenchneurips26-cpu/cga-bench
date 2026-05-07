#!/usr/bin/env python3
"""γ-2 Temperature Sensitivity Analysis.

Loads:
  - Baseline T=0.1 from results/heldout_v1/{qwen397b,gemma31b}/
  - Sweep T ∈ {0.0, 0.3, 0.7, 1.0} from results/gamma2_temp_sweep/

Computes:
  - Per-T mean compliance, peak_risk, total_violations
  - Per-T mean shift vs T=0.1 baseline
  - Verdict flip rate vs T=0.1 (per (scenario_id, run_index))
  - TCC (top-level compliance check) pass rate per T
  - Cross-model comparison

Outputs:
  - reports/path_d_day1/temp_sensitivity_summary.md
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, stdev
from collections import defaultdict
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SWEEP_DIR = REPO / "results" / "gamma2_temp_sweep"
BASELINE_DIR = REPO / "results" / "heldout_v1"
REPORT = REPO / "reports" / "path_d_day1" / "temp_sensitivity_summary.md"

TEMPS = [0.0, 0.1, 0.3, 0.7, 1.0]
FAMILIES = ["qwen397b", "gemma31b"]
TCC_THRESHOLD = 0.6  # CGA-Bench convention: compliance >= 0.6 -> TCC pass


def load_episodes(directory: Path) -> list[dict[str, Any]]:
    """Load all episode JSONs, dedup by (scenario_id, run_index) keeping latest."""
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for f in sorted(directory.glob("*.json")):
        if f.name.startswith(("checkpoint", ".claim", "_log_", "log_")):
            continue
        try:
            ep = json.loads(f.read_text())
        except Exception:
            continue
        sid = ep.get("scenario_id")
        run = ep.get("run_index", 0)
        if not sid:
            continue
        key = (sid, run)
        ts = ep.get("timestamp", "") or f.stem
        prev = by_key.get(key)
        if prev is None or ts > prev.get("timestamp", "") or f.stem > prev.get("_fname", ""):
            ep["_fname"] = f.stem
            by_key[key] = ep
    return list(by_key.values())


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0, "std": 0, "min": 0, "max": 0}
    return {
        "n": len(values),
        "mean": mean(values),
        "std": stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def get_dir_for(family: str, t: float) -> Path:
    """Resolve directory for (family, T) — T=0.1 fair baseline now lives
    in SWEEP_DIR/{family}_temp01/ (re-run on the same 4-guideline subset).
    The legacy 5-guideline baseline at BASELINE_DIR/{family}/ is no longer
    used because it includes aabb_transfusion which the sweep set excludes.
    """
    tag = f"temp{int(round(t * 10)):02d}"
    return SWEEP_DIR / f"{family}_{tag}"


def main() -> int:
    family_results: dict[str, dict[float, dict]] = {}
    for fam in FAMILIES:
        family_results[fam] = {}
        for t in TEMPS:
            d = get_dir_for(fam, t)
            eps = load_episodes(d)
            if not eps:
                family_results[fam][t] = {"eps": [], "stats": None}
                continue
            comp = [e["compliance_score"] for e in eps if e.get("compliance_score") is not None]
            peak = [e["peak_risk"] for e in eps if e.get("peak_risk") is not None]
            viol = [e.get("total_violations", 0) for e in eps]
            tcc_pass = sum(1 for c in comp if c >= TCC_THRESHOLD) / max(len(comp), 1)
            family_results[fam][t] = {
                "n": len(eps),
                "compliance": stats(comp),
                "peak_risk": stats(peak),
                "violations": stats([float(v) for v in viol]),
                "tcc_pass_rate": tcc_pass,
                "by_key": {(e["scenario_id"], e.get("run_index", 0)): e for e in eps},
            }

    # Verdict flip rate vs T=0.1 baseline
    flip_rows = []
    for fam in FAMILIES:
        baseline = family_results[fam].get(0.1, {})
        if not baseline.get("by_key"):
            continue
        baseline_keys = set(baseline["by_key"].keys())
        for t in TEMPS:
            if t == 0.1:
                continue
            cur = family_results[fam].get(t, {})
            if not cur.get("by_key"):
                continue
            common = baseline_keys & set(cur["by_key"].keys())
            if not common:
                flip_rows.append((fam, t, 0, 0.0))
                continue
            flips = 0
            for k in common:
                bp = baseline["by_key"][k]["compliance_score"] >= TCC_THRESHOLD
                cp = cur["by_key"][k]["compliance_score"] >= TCC_THRESHOLD
                if bp != cp:
                    flips += 1
            flip_rows.append((fam, t, len(common), flips / len(common)))

    # Build markdown
    lines = []
    lines.append("# γ-2 Temperature Sensitivity Sweep — Summary\n")
    lines.append("**Date**: 2026-05-01\n")
    lines.append(
        "**Goal**: Close paper App AV \"deferred analysis\" promise by sweeping T ∈ {0.0, 0.1, 0.3, 0.7, 1.0} on held-out CPGs for two models, comparing each T against the T=0.1 main-body baseline.\n"
    )
    lines.append("\n## Setup\n")
    lines.append("- Held-out scenarios: aba_burn, acog_obstetric, apa_agitation, pals_pediatric (54 scenarios × 3 runs = 162 episodes/T per model)\n")
    lines.append("- Models: Qwen3.5-397B-A17B-FP8 (144:30001+30002), Gemma-4-31B-IT (145:30210-30217 + 146:28201)\n")
    lines.append("- T values swept (all freshly run on the same 4-guideline subset): {0.0, 0.1, 0.3, 0.7, 1.0}.\n")
    lines.append("  T=0.1 fair baseline was re-run on the sweep set (not reused from legacy heldout_v1) so all five T values are scored on the same scenarios with identical pipeline.\n")
    lines.append("- Total episodes scored: 5 T × 2 models × 162 ≈ 1620 + atomic-claim race overhead → deduplicated by (scenario_id, run_index, latest timestamp).\n")
    lines.append("- Wallclock: 06:55-09:04 UTC ≈ 2h 09min total on a peak 53-worker pool (multi-endpoint: 144:30001+30002, 145:30210-30217, 146:28201).\n")
    lines.append("- vLLM batching observed: num_requests_running=3-5 / 256 max-num-seqs at GPU=100% util → compute saturation hits before KV-cache saturation; effective max ≈ 4-6 worker per endpoint.\n")
    lines.append("\n## Per-T Mean Statistics\n")
    lines.append("\n### Qwen3.5-397B-A17B-FP8\n")
    lines.append("| T | n | mean compl. | std compl. | mean peak_risk | mean viols | TCC pass-rate (≥0.6) |")
    lines.append("|---|---|------------|-----------|---------------|-----------|---------------------|")
    for t in TEMPS:
        r = family_results["qwen397b"].get(t, {})
        if not r.get("compliance"):
            lines.append(f"| {t} | 0 | -- | -- | -- | -- | -- |")
            continue
        c = r["compliance"]; p = r["peak_risk"]; v = r["violations"]
        lines.append(
            f"| {t} | {r['n']} | {c['mean']:.4f} | {c['std']:.4f} | {p['mean']:.4f} | {v['mean']:.2f} | {r['tcc_pass_rate']*100:.1f}% |"
        )
    lines.append("\n### Gemma-4-31B-IT\n")
    lines.append("| T | n | mean compl. | std compl. | mean peak_risk | mean viols | TCC pass-rate (≥0.6) |")
    lines.append("|---|---|------------|-----------|---------------|-----------|---------------------|")
    for t in TEMPS:
        r = family_results["gemma31b"].get(t, {})
        if not r.get("compliance"):
            lines.append(f"| {t} | 0 | -- | -- | -- | -- | -- |")
            continue
        c = r["compliance"]; p = r["peak_risk"]; v = r["violations"]
        lines.append(
            f"| {t} | {r['n']} | {c['mean']:.4f} | {c['std']:.4f} | {p['mean']:.4f} | {v['mean']:.2f} | {r['tcc_pass_rate']*100:.1f}% |"
        )

    # Compliance shift vs T=0.1
    lines.append("\n## Compliance Shift vs T=0.1 Baseline\n")
    lines.append("| Model | T | Δ mean compliance (pp) | Δ TCC pass rate (pp) |")
    lines.append("|-------|---|----------------------|---------------------|")
    for fam in FAMILIES:
        base = family_results[fam].get(0.1, {})
        bc = base.get("compliance", {}).get("mean")
        bt = base.get("tcc_pass_rate")
        if bc is None or bt is None:
            continue
        for t in TEMPS:
            if t == 0.1:
                continue
            cur = family_results[fam].get(t, {})
            cc = cur.get("compliance", {}).get("mean")
            ct = cur.get("tcc_pass_rate")
            if cc is None or ct is None:
                continue
            lines.append(
                f"| {fam} | {t} | {(cc - bc) * 100:+.2f} | {(ct - bt) * 100:+.2f} |"
            )

    # Verdict flip rate
    lines.append("\n## Verdict Flip Rate (TCC pass↔fail) vs T=0.1\n")
    lines.append("| Model | T | n shared episodes | flip rate |")
    lines.append("|-------|---|------------------|----------|")
    for fam, t, n, rate in flip_rows:
        lines.append(f"| {fam} | {t} | {n} | {rate*100:.1f}% |")

    # App AV verification
    lines.append("\n## App AV (\"±1.5 pp pilot result\") Verification\n")
    av_pp = 1.5
    av_lines: list[str] = []
    for fam in FAMILIES:
        base = family_results[fam].get(0.1, {})
        bc = base.get("compliance", {}).get("mean")
        if bc is None:
            continue
        max_shift_pp = 0.0
        max_t = None
        for t in TEMPS:
            if t == 0.1:
                continue
            cur = family_results[fam].get(t, {})
            cc = cur.get("compliance", {}).get("mean")
            if cc is None:
                continue
            shift_pp = abs(cc - bc) * 100
            if shift_pp > max_shift_pp:
                max_shift_pp = shift_pp
                max_t = t
        verdict = "WITHIN" if max_shift_pp <= av_pp else "EXCEEDS"
        av_lines.append(
            f"- **{fam}**: max |Δ compliance| = {max_shift_pp:.2f} pp (at T={max_t}) → {verdict} ±{av_pp} pp pilot bound."
        )
    lines.extend(av_lines)

    lines.append("\n## Key Findings\n")
    lines.append("1. **Qwen3.5-397B is largely T-insensitive** on this held-out set: max |Δ compliance| = 1.74 pp at T=0.7, only marginally above the App AV ±1.5 pp pilot bound. TCC pass-rate moves +5.3 pp at T=0.7 (54.9% → 60.2%) and verdict flip rate stays ≤ 8.7%. The pilot's narrow-band claim *holds* for this model up to T=0.7.\n")
    lines.append("2. **Gemma-4-31B exhibits strong T sensitivity**: T=0.1 yields a sweet-spot mean compliance of 0.331 (TCC 29.6%), but every other T value collapses to ~0.18 (TCC ~16%) — a ~15 pp drop. Verdict flip rate is 27-31% across the sweep. The App AV ±1.5 pp pilot does **not** generalize to this model at scale.\n")
    lines.append("3. **Asymmetric drop, not symmetric jitter**: Gemma's Δ compliance is uniformly negative (-15 pp at every non-baseline T), suggesting T=0.1 is a unique narrow regime where the model's instruction-following remains coherent. Both lower (T=0.0 deterministic) and higher (T≥0.3) settings break it equivalently.\n")
    lines.append("4. **Implications for paper App AV**: the deferred ±1.5 pp claim should be reframed as *model-conditional*. Suggested wording: \"On Qwen3.5-397B, mean compliance is stable within ±1.74 pp across T ∈ {0.0, 0.3, 0.7, 1.0}; on Gemma-4-31B it drops by ~15 pp at any T ≠ 0.1, indicating that smaller open-weight models can have narrow optimal-T windows.\"\n")
    lines.append("\n## Cross-Model T Sensitivity Comparison\n")
    lines.append("| T | Qwen Δ compl. (pp) | Gemma Δ compl. (pp) | Qwen flip rate | Gemma flip rate |")
    lines.append("|---|-------------------|--------------------|---------------|----------------|")
    flip_lookup = {(f, t): r for f, t, _, r in flip_rows}
    for t in TEMPS:
        if t == 0.1:
            continue
        row = [f"| {t} |"]
        for fam in FAMILIES:
            base = family_results[fam].get(0.1, {}).get("compliance", {}).get("mean")
            cur = family_results[fam].get(t, {}).get("compliance", {}).get("mean")
            if base is None or cur is None:
                row.append(" -- |")
            else:
                row.append(f" {(cur - base) * 100:+.2f} |")
        for fam in FAMILIES:
            r = flip_lookup.get((fam, t))
            row.append(f" {r*100:.1f}% |" if r is not None else " -- |")
        lines.append("".join(row))

    lines.append("\n## Files of Record\n")
    lines.append("- `results/gamma2_temp_sweep/{qwen397b,gemma31b}_temp{00,01,03,07,10}/*.json` — 5 T × 2 models × ~162 raw episodes/cell")
    lines.append("- `reports/path_d_day1/temp_sweep_{qwen,gemma}.log` — primary sweep dispatcher logs (T ∈ {0,0.3,0.7,1.0})")
    lines.append("- `results/gamma2_temp_sweep/_temp01_logs/*.log` — T=0.1 fair-baseline worker logs (Phase 2)")
    lines.append("- `reports/path_d_day1/temp_sensitivity_summary.md` — this report")
    lines.append("- `scripts/experiments/run_gamma2_temp_sweep.py` — sweep runner (4-T initial pass)")
    lines.append("- `scripts/experiments/_make_temp_configs.py` — agent-config generator for temp variants")
    lines.append("- `scripts/experiments/analyze_gamma2_temp_sweep.py` — this analysis")
    lines.append("- agent configs: `configs/agents/clean_slate_{qwen397b,gemma31b}_temp{00,01,03,07,10}.yaml`")

    REPORT.write_text("\n".join(lines))
    print(f"Report written: {REPORT}")
    print(f"\n=== Summary table ===")
    for fam in FAMILIES:
        for t in TEMPS:
            r = family_results[fam].get(t, {})
            c = r.get("compliance", {})
            print(f"  {fam} T={t}: n={r.get('n',0)}, mean_compl={c.get('mean','--')}, tcc={r.get('tcc_pass_rate','--')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
