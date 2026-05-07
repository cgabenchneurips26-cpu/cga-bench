#!/usr/bin/env python3
"""G1 / E9 Follow-up — Safety-Core Overlay (S1-pivot, S2 collapse).

Restricts the 1,124 S1 strict-FA episodes (ASC ∩ CwT ∩ PAF pass, TCC fail)
to those whose violation types include FORBIDDEN or BEFORE (the "safety-core"
subset), and repeats for S2 to expose the S1→S2 collapse gradient.

Pre-flight numbers (must reproduce):
  S1 strict-FA total : 1124  (matches \\strictFAThreeCount)
  S2 strict-FA total :  548  (matches F1 published)
  S1 safety-core     :  144  (FORBIDDEN ∪ BEFORE in viol_types)
  S1 MUST-only       :  980
  S2 safety-core     :    4  (mixed FORBIDDEN+WITHIN only)
  S2 MUST-only       :  544
  S1->S2 collapse    : 144->4  (-97.2%)

Inputs:
  evidence_pack/analysis/verdict_matrix_v6.json          (ASC/CwT/PAF/viol_types)
  evidence_pack/analysis/verdict_matrix_v6_high_S1.json  (v4_hard_high per episode)
  evidence_pack/analysis/verdict_matrix_v6_high_S2.json  (v4_hard_high per episode)

Outputs:
  evidence_pack/analysis/exp_e9_safety_core.json
  evidence_pack/analysis/exp_e9_safety_core.md
  evidence_pack/analysis/exp_e9_safety_core.tex

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (§A)
Convention: filename exp_e39e_* slots into exp_eN_* numbering; outputs keep
the exp_e9_ prefix to match in-paper citations.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.experiments._common import EVIDENCE_DIR, save_json, save_markdown  # noqa: E402

# -------------------------------------------------------------------- paths
ANALYSIS_DIR = EVIDENCE_DIR / "analysis"
VERDICT_MATRIX_PATH = ANALYSIS_DIR / "verdict_matrix_v6.json"
VERDICT_MATRIX_S1_PATH = ANALYSIS_DIR / "verdict_matrix_v6_high_S1.json"
VERDICT_MATRIX_S2_PATH = ANALYSIS_DIR / "verdict_matrix_v6_high_S2.json"

OUT_JSON = ANALYSIS_DIR / "exp_e9_safety_core.json"
OUT_MD = ANALYSIS_DIR / "exp_e9_safety_core.md"
OUT_TEX = ANALYSIS_DIR / "exp_e9_safety_core.tex"


# =====================================================================
# Wilson 95% CI for a proportion
# =====================================================================
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Return Wilson score 95% CI (lo, hi) for k successes in n trials."""
    if n == 0:
        return (0.0, 0.0)
    p_hat = k / n
    denom = 1.0 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


# =====================================================================
# Data loading helpers
# =====================================================================
def load_json(path: Path) -> Any:
    """Load JSON from path, raise with clear message on failure."""
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    with open(path) as f:
        return json.load(f)


def build_high_map(high_matrix: dict[str, Any]) -> dict[str, bool]:
    """Return episode_id -> v4_hard_high (True=pass, False=fail) from a high matrix."""
    return {
        ep["episode_id"]: ep.get("v4_hard_high", True)
        for ep in (high_matrix.get("per_episode") or [])
    }


# =====================================================================
# Core classification logic
# =====================================================================
def classify_family(viol_types: list[str]) -> str:
    """Classify safety-core episode into a family label.

    Families (non-overlapping, exhaustive within safety-core):
      forbid_only         -- FORBIDDEN present, no BEFORE, no WITHIN
      before_only         -- BEFORE present, no FORBIDDEN, no WITHIN
      forbid_within       -- FORBIDDEN + WITHIN, no BEFORE
      before_within       -- BEFORE + WITHIN, no FORBIDDEN
      forbid_before       -- FORBIDDEN + BEFORE, no WITHIN
      forbid_before_within -- FORBIDDEN + BEFORE + WITHIN
    """
    vt = set(viol_types)
    has_f = "FORBIDDEN" in vt
    has_b = "BEFORE" in vt
    has_w = "WITHIN" in vt
    if has_f and has_b and has_w:
        return "forbid_before_within"
    if has_f and has_b:
        return "forbid_before"
    if has_f and has_w:
        return "forbid_within"
    if has_b and has_w:
        return "before_within"
    if has_f:
        return "forbid_only"
    if has_b:
        return "before_only"
    return "other"  # should never be reached for safety-core episodes


def is_safety_core(viol_types: list[str]) -> bool:
    """Return True when the episode contains FORBIDDEN or BEFORE violations."""
    vt = set(viol_types)
    return "FORBIDDEN" in vt or "BEFORE" in vt


# =====================================================================
# Per-stratum aggregation
# =====================================================================
_FAMILY_LABELS: list[str] = [
    "forbid_only",
    "before_only",
    "forbid_within",
    "before_within",
    "forbid_before",
    "forbid_before_within",
]


def compute_stratum(
    base_episodes: list[dict[str, Any]],
    high_map: dict[str, bool],
) -> dict[str, Any]:
    """Compute all metrics for one authority stratum (S1 or S2).

    Args:
        base_episodes: Per-episode records from verdict_matrix_v6.json.
        high_map:      episode_id -> v4_hard_high (True=pass, False=fail).

    Returns:
        Dict with n_strict_fa, safety_core, must_only, family_breakdown,
        mab_replay_loss, ac_replay_loss.
    """
    n_strict_fa = 0
    n_safety_core = 0
    n_must_only = 0
    family_counts: dict[str, int] = {label: 0 for label in _FAMILY_LABELS}

    # For replay-loss: all TCC-fail safety-core episodes (not just strict-FA)
    tcc_fail_safety_core_total = 0
    tcc_fail_safety_core_mab_pass = 0
    tcc_fail_safety_core_ac_pass = 0

    for ep in base_episodes:
        eid = ep["episode_id"]
        asc = ep.get("ac_proxy") is True
        cwt = ep.get("c2_pass") is True
        paf = ep.get("mab_proxy") is True
        tcc_full_fail = ep.get("v4_hard") is True  # True => TCC rejected

        if not tcc_full_fail:
            continue

        vt = ep.get("viol_types") or []
        ep_safety_core = is_safety_core(vt)

        # TCC-fail safety-core (wider population for replay-loss)
        if ep_safety_core and eid in high_map:
            tcc_fail_safety_core_total += 1
            if ep.get("mab_proxy") is True:
                tcc_fail_safety_core_mab_pass += 1
            if ep.get("ac_proxy") is True:
                tcc_fail_safety_core_ac_pass += 1

        # Strict-FA gate: ASC ∩ CwT ∩ PAF
        if not (asc and cwt and paf):
            continue

        # High-authority TCC must also fail
        h_pass = high_map.get(eid)
        if h_pass is None or h_pass is True:
            continue  # episode not in high matrix or passed high TCC

        n_strict_fa += 1
        if ep_safety_core:
            n_safety_core += 1
            family_counts[classify_family(vt)] += 1
        else:
            n_must_only += 1

    mab_loss = (
        tcc_fail_safety_core_mab_pass / tcc_fail_safety_core_total
        if tcc_fail_safety_core_total > 0
        else 0.0
    )
    ac_loss = (
        tcc_fail_safety_core_ac_pass / tcc_fail_safety_core_total
        if tcc_fail_safety_core_total > 0
        else 0.0
    )

    ci_lo, ci_hi = wilson_ci(n_safety_core, n_strict_fa)

    return {
        "n_strict_fa": n_strict_fa,
        "safety_core": n_safety_core,
        "must_only": n_must_only,
        "family_breakdown": family_counts,
        "tcc_fail_safety_core_total": tcc_fail_safety_core_total,
        "mab_replay_loss_safety_core": round(mab_loss, 6),
        "ac_replay_loss_safety_core": round(ac_loss, 6),
        "wilson_ci_lo": round(ci_lo, 6),
        "wilson_ci_hi": round(ci_hi, 6),
        "safety_core_pct": round(n_safety_core / n_strict_fa * 100, 2) if n_strict_fa else 0.0,
    }


# =====================================================================
# Rendering
# =====================================================================
def render_markdown(s1: dict[str, Any], s2: dict[str, Any]) -> str:
    """Render paper-ready markdown report."""
    collapse_delta = s2["safety_core"] - s1["safety_core"]
    collapse_pct = (
        collapse_delta / s1["safety_core"] * 100
        if s1["safety_core"] > 0
        else 0.0
    )

    lines: list[str] = []
    lines.append("# E9 Follow-up G1 -- Safety-Core Overlay")
    lines.append("")
    lines.append("Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (SS A)")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(
        f"Of the **{s1['n_strict_fa']}** S1 strict-FA episodes, "
        f"**{s1['safety_core']}** ({s1['safety_core_pct']:.1f}%) "
        f"contain at least one FORBIDDEN or BEFORE violation "
        f"(safety-core; Wilson 95% CI "
        f"[{s1['wilson_ci_lo'] * 100:.1f}%, {s1['wilson_ci_hi'] * 100:.1f}%]). "
        f"Under the strictest taxonomy (S2) this collapses to "
        f"**{s2['safety_core']}** episodes "
        f"({collapse_delta:+d}, {collapse_pct:.1f}%)."
    )
    lines.append("")
    lines.append("## S1 / S2 side-by-side")
    lines.append("")
    lines.append("| Metric | S1 (default high-authority) | S2 (strictest, Class I+A) |")
    lines.append("|---|---|---|")
    lines.append(f"| Strict-FA total | {s1['n_strict_fa']} | {s2['n_strict_fa']} |")
    lines.append(f"| Safety-core (FORBIDDEN or BEFORE) | **{s1['safety_core']}** | **{s2['safety_core']}** |")
    lines.append(f"| MUST-only (WITHIN / empty) | {s1['must_only']} | {s2['must_only']} |")
    lines.append(
        f"| Safety-core % | {s1['safety_core_pct']:.1f}% | "
        f"{s2['safety_core_pct']:.1f}% |"
    )
    lines.append(
        f"| Wilson 95% CI | "
        f"[{s1['wilson_ci_lo'] * 100:.1f}%, {s1['wilson_ci_hi'] * 100:.1f}%] | "
        f"[{s2['wilson_ci_lo'] * 100:.1f}%, {s2['wilson_ci_hi'] * 100:.1f}%] |"
    )
    lines.append(
        f"| MAB replay-loss (safety-core) | "
        f"{s1['mab_replay_loss_safety_core'] * 100:.1f}% | "
        f"{s2['mab_replay_loss_safety_core'] * 100:.1f}% |"
    )
    lines.append(
        f"| AC replay-loss (safety-core) | "
        f"{s1['ac_replay_loss_safety_core'] * 100:.1f}% | "
        f"{s2['ac_replay_loss_safety_core'] * 100:.1f}% |"
    )
    lines.append("")
    lines.append("## S1 Family breakdown (safety-core only)")
    lines.append("")
    lines.append("| Family | Count | Description |")
    lines.append("|---|---|---|")
    fb = s1["family_breakdown"]
    lines.append(f"| forbid_only | {fb['forbid_only']} | FORBIDDEN only, no BEFORE, no WITHIN |")
    lines.append(f"| before_only | {fb['before_only']} | BEFORE only, no FORBIDDEN, no WITHIN |")
    lines.append(f"| forbid_within | {fb['forbid_within']} | FORBIDDEN + WITHIN (mixed) |")
    lines.append(f"| before_within | {fb['before_within']} | BEFORE + WITHIN (mixed) |")
    lines.append(f"| forbid_before | {fb['forbid_before']} | FORBIDDEN + BEFORE, no WITHIN |")
    lines.append(f"| forbid_before_within | {fb['forbid_before_within']} | FORBIDDEN + BEFORE + WITHIN |")
    lines.append("")
    lines.append("## S2 Family breakdown (safety-core only)")
    lines.append("")
    lines.append("| Family | Count |")
    lines.append("|---|---|")
    fb2 = s2["family_breakdown"]
    for label in _FAMILY_LABELS:
        lines.append(f"| {label} | {fb2[label]} |")
    lines.append("")
    lines.append("## Replay-loss detail (S1)")
    lines.append("")
    lines.append(
        "Among all TCC-fail safety-core episodes under S1 "
        f"(n={s1['tcc_fail_safety_core_total']}), "
        f"the MAB proxy still called PASS in "
        f"**{s1['mab_replay_loss_safety_core'] * 100:.1f}%** of cases "
        f"and the AC proxy in "
        f"**{s1['ac_replay_loss_safety_core'] * 100:.1f}%** of cases."
    )
    lines.append("")
    lines.append("## S1->S2 Collapse (strictness gradient)")
    lines.append("")
    lines.append(
        f"S1 safety-core: {s1['safety_core']} -> S2: {s2['safety_core']} "
        f"({collapse_delta:+d}, **{collapse_pct:.1f}%**). "
        "Reported as strictness-gradient meta-finding; S2 n=4 is below the "
        "n>=30 per-stratum threshold and is cited as a boundary note only."
    )
    lines.append("")
    lines.append("## Gate verdict")
    lines.append("")
    gate = "PASS" if s1["safety_core"] >= 30 else "FAIL"
    lines.append(
        f"S1 safety-core n={s1['safety_core']} >= 30 threshold: **{gate}**"
    )
    lines.append(
        f"S2 safety-core n={s2['safety_core']} < 30: boundary note only (not primary claim)."
    )
    lines.append("")

    return "\n".join(lines)


def render_tex(s1: dict[str, Any], s2: dict[str, Any]) -> str:
    """Render LaTeX macro definitions."""
    collapse_delta = s2["safety_core"] - s1["safety_core"]
    collapse_pct = (
        collapse_delta / s1["safety_core"] * 100
        if s1["safety_core"] > 0
        else 0.0
    )

    def macro(name: str, value: str) -> str:
        return f"\\newcommand{{\\{name}}}{{{value}}}"

    lines: list[str] = [
        "% G1 Safety-Core Overlay macros",
        "% Auto-generated by scripts/experiments/exp_e39e_safety_core_overlay.py",
        "% DO NOT EDIT BY HAND",
        "",
        macro("GoneSafetyCoreS1Count", str(s1["safety_core"])),
        macro("GoneSafetyCoreS1Pct", f"{s1['safety_core_pct']:.1f}"),
        macro(
            "GoneSafetyCoreS1WilsonLo",
            f"{s1['wilson_ci_lo'] * 100:.1f}",
        ),
        macro(
            "GoneSafetyCoreS1WilsonHi",
            f"{s1['wilson_ci_hi'] * 100:.1f}",
        ),
        macro("GoneSafetyCoreS2Count", str(s2["safety_core"])),
        macro("GoneCollapseDelta", str(abs(collapse_delta))),
        macro("GoneCollapsePct", f"{abs(collapse_pct):.1f}"),
        macro("GoneStrictFAS1Count", str(s1["n_strict_fa"])),
        macro("GoneStrictFAS2Count", str(s2["n_strict_fa"])),
        macro("GoneMustOnlyS1Count", str(s1["must_only"])),
        macro("GoneMustOnlyS2Count", str(s2["must_only"])),
        macro(
            "GoneMABReplayLossSafetyCoreS1",
            f"{s1['mab_replay_loss_safety_core'] * 100:.1f}",
        ),
        macro(
            "GoneACReplayLossSafetyCoreS1",
            f"{s1['ac_replay_loss_safety_core'] * 100:.1f}",
        ),
        macro("GoneFamilyForbidOnlyS1", str(s1["family_breakdown"]["forbid_only"])),
        macro("GoneFamilyForbidWithinS1", str(s1["family_breakdown"]["forbid_within"])),
        macro("GoneFamilyBeforeOnlyS1", str(s1["family_breakdown"]["before_only"])),
        "",
    ]
    return "\n".join(lines)


# =====================================================================
# Main
# =====================================================================
def main() -> None:
    """Load verdict matrices, compute safety-core overlay, write outputs."""
    print("Loading verdict matrices...")
    base = load_json(VERDICT_MATRIX_PATH)
    s1_matrix = load_json(VERDICT_MATRIX_S1_PATH)
    s2_matrix = load_json(VERDICT_MATRIX_S2_PATH)

    base_episodes: list[dict[str, Any]] = base.get("per_episode") or []
    s1_high_map = build_high_map(s1_matrix)
    s2_high_map = build_high_map(s2_matrix)

    print(f"Base episodes: {len(base_episodes)}")
    print(f"S1 high map entries: {len(s1_high_map)}")
    print(f"S2 high map entries: {len(s2_high_map)}")

    print("Computing S1 stratum...")
    s1_metrics = compute_stratum(base_episodes, s1_high_map)

    print("Computing S2 stratum...")
    s2_metrics = compute_stratum(base_episodes, s2_high_map)

    collapse_delta = s2_metrics["safety_core"] - s1_metrics["safety_core"]
    collapse_pct = (
        collapse_delta / s1_metrics["safety_core"] * 100
        if s1_metrics["safety_core"] > 0
        else 0.0
    )

    # Verify pre-flight numbers
    assert s1_metrics["n_strict_fa"] == 1124, (
        f"S1 strict-FA mismatch: got {s1_metrics['n_strict_fa']}, expected 1124"
    )
    assert s2_metrics["n_strict_fa"] == 548, (
        f"S2 strict-FA mismatch: got {s2_metrics['n_strict_fa']}, expected 548"
    )
    assert s1_metrics["safety_core"] == 144, (
        f"S1 safety-core mismatch: got {s1_metrics['safety_core']}, expected 144"
    )
    assert s2_metrics["safety_core"] == 4, (
        f"S2 safety-core mismatch: got {s2_metrics['safety_core']}, expected 4"
    )

    print(f"  S1 strict-FA:    {s1_metrics['n_strict_fa']}")
    print(f"  S2 strict-FA:    {s2_metrics['n_strict_fa']}")
    print(f"  S1 safety-core:  {s1_metrics['safety_core']}")
    print(f"  S2 safety-core:  {s2_metrics['safety_core']}")
    print(f"  S1 must-only:    {s1_metrics['must_only']}")
    print(f"  S2 must-only:    {s2_metrics['must_only']}")
    print(f"  Collapse:        {collapse_delta:+d} ({collapse_pct:.1f}%)")

    # Build output JSON
    result: dict[str, Any] = {
        "n_total": len(base_episodes),
        "n_strict_fa_S1": s1_metrics["n_strict_fa"],
        "n_strict_fa_S2": s2_metrics["n_strict_fa"],
        "safety_core_S1": s1_metrics["safety_core"],
        "safety_core_S2": s2_metrics["safety_core"],
        "must_only_S1": s1_metrics["must_only"],
        "must_only_S2": s2_metrics["must_only"],
        "family_breakdown_S1": s1_metrics["family_breakdown"],
        "family_breakdown_S2": s2_metrics["family_breakdown"],
        "mab_replay_loss_safety_core_S1": s1_metrics["mab_replay_loss_safety_core"],
        "ac_replay_loss_safety_core_S1": s1_metrics["ac_replay_loss_safety_core"],
        "mab_replay_loss_safety_core_S2": s2_metrics["mab_replay_loss_safety_core"],
        "ac_replay_loss_safety_core_S2": s2_metrics["ac_replay_loss_safety_core"],
        "wilson_ci_lo_S1": s1_metrics["wilson_ci_lo"],
        "wilson_ci_hi_S1": s1_metrics["wilson_ci_hi"],
        "wilson_ci_lo_S2": s2_metrics["wilson_ci_lo"],
        "wilson_ci_hi_S2": s2_metrics["wilson_ci_hi"],
        "safety_core_pct_S1": s1_metrics["safety_core_pct"],
        "safety_core_pct_S2": s2_metrics["safety_core_pct"],
        "collapse_delta": collapse_delta,
        "collapse_pct": round(collapse_pct, 2),
        "tcc_fail_safety_core_total_S1": s1_metrics["tcc_fail_safety_core_total"],
        "tcc_fail_safety_core_total_S2": s2_metrics["tcc_fail_safety_core_total"],
        "_meta": {
            "script": "scripts/experiments/exp_e39e_safety_core_overlay.py",
            "spec": "docs/attack_gap_exp_exp/260430_add_contribution_exp.md SS A",
            "base_matrix": str(VERDICT_MATRIX_PATH),
            "s1_matrix": str(VERDICT_MATRIX_S1_PATH),
            "s2_matrix": str(VERDICT_MATRIX_S2_PATH),
            "safety_core_definition": "FORBIDDEN in viol_types OR BEFORE in viol_types",
            "strict_fa_definition": "ac_proxy=T AND c2_pass=T AND mab_proxy=T AND v4_hard=T AND v4_hard_high=F",
        },
    }

    save_json(result, OUT_JSON)

    md_text = render_markdown(s1_metrics, s2_metrics)
    save_markdown(md_text, OUT_MD)

    tex_text = render_tex(s1_metrics, s2_metrics)
    save_markdown(tex_text, OUT_TEX)

    print("Done.")


if __name__ == "__main__":
    main()
