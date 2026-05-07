#!/usr/bin/env python3
"""F3 / E10 — Severity Overlay on E9 Strict-FA Episodes.

Stratifies the 1,124 strict-FA episodes (the headline E9 high-authority blind
spot) by the maximum harm severity of their hard violation events. Defends
against the reviewer attack "high-authority does not imply harm-relevant".

Promotion rule (from spec §5.3):
- If (catastrophic + severe + major) / 1124 >= 20% --> promote a sentence
  to main paper §5.5.
- Else --> appendix-only.

Output:
  evidence_pack/analysis/exp_e9_severity_overlay.json
  evidence_pack/analysis/exp_e9_severity_overlay.md
  evidence_pack/analysis/exp_e9_severity_macros.tex

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (§5.3)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.experiments.exp_e39_high_authority_core import (  # noqa: E402
    ANALYSIS_DIR,
    HARD_VIOLATION_TYPES,
    RESULTS_DIRS_DEFAULT,
    VERDICT_MATRIX_PATH,
    build_episode_index,
)


# Severity ordering (highest first). Matches HarmSeverity enum buckets used
# elsewhere in the project, but accept any case the violation_event uses.
_SEVERITY_ORDER = [
    "catastrophic",
    "severe",
    "major",
    "moderate",
    "minor",
    "none",
]
_SEVERITY_RANK = {s: i for i, s in enumerate(_SEVERITY_ORDER)}

CRITICAL_MAJOR = {"catastrophic", "severe", "major"}
PROMOTION_THRESHOLD = 0.20  # 20%


def find_strict_fa_episodes(verdict_matrix: dict) -> list[dict]:
    out: list[dict] = []
    for ep in verdict_matrix.get("per_episode", []) or []:
        if (
            ep.get("ac_proxy") is True
            and ep.get("c2_pass") is True
            and ep.get("mab_proxy") is True
            and ep.get("v4_hard") is True
        ):
            out.append(ep)
    return out


def max_hard_severity(violation_events: list[dict]) -> str:
    """Return the highest-severity hard violation, or 'none' if all soft."""
    best = "none"
    best_rank = _SEVERITY_RANK["none"]
    for ev in violation_events:
        vt = (ev.get("violation_type") or "").lower()
        if vt not in HARD_VIOLATION_TYPES:
            continue
        sev = (ev.get("harm_severity") or "none").lower()
        rank = _SEVERITY_RANK.get(sev, _SEVERITY_RANK["none"])
        if rank < best_rank:
            best_rank = rank
            best = sev
    return best


def aggregate(rows: list[dict]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    by_model: dict[str, Counter] = defaultdict(Counter)
    by_domain_severity: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        s = r["max_severity"]
        counter[s] += 1
        by_model[r["model_dir"]][s] += 1
        by_domain_severity[r.get("domain", "other")][s] += 1

    n = len(rows)
    crit_major = sum(counter.get(s, 0) for s in CRITICAL_MAJOR)
    moderate = counter.get("moderate", 0)
    minor = counter.get("minor", 0)
    none = counter.get("none", 0)

    crit_share = crit_major / n if n else 0.0

    return {
        "n_episodes": n,
        "severity_counts": dict(counter),
        "shares": {
            "critical_major": crit_share,
            "moderate": moderate / n if n else 0.0,
            "minor": minor / n if n else 0.0,
            "none": none / n if n else 0.0,
        },
        "by_model": {m: dict(c) for m, c in by_model.items()},
        "promotion": {
            "threshold": PROMOTION_THRESHOLD,
            "promote_to_main": crit_share >= PROMOTION_THRESHOLD,
            "decision_reason": (
                f"critical_major share = {crit_share:.4f}; "
                f"threshold = {PROMOTION_THRESHOLD:.2f}"
            ),
        },
    }


def render_md(metrics: dict[str, Any]) -> str:
    n = metrics["n_episodes"]
    counts = metrics["severity_counts"]
    shares = metrics["shares"]
    promo = metrics["promotion"]

    lines: list[str] = []
    lines.append("# E9 Follow-up F3 — Severity Overlay on Strict-FA Episodes")
    lines.append("")
    lines.append("Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (§5.3)")
    lines.append("")
    lines.append(f"**Strict-FA episodes**: {n}")
    lines.append("")
    lines.append("## Severity distribution (max harm per episode)")
    lines.append("")
    lines.append("| Severity | Count | Share |")
    lines.append("|---|---|---|")
    for s in _SEVERITY_ORDER:
        c = counts.get(s, 0)
        lines.append(f"| {s} | {c} | {c / n * 100 if n else 0:.2f}% |")
    lines.append("")
    lines.append("## Aggregate shares")
    lines.append("")
    lines.append(
        f"- Critical / Severe / Major (combined): "
        f"**{shares['critical_major'] * 100:.2f}%**"
    )
    lines.append(f"- Moderate: {shares['moderate'] * 100:.2f}%")
    lines.append(f"- Minor: {shares['minor'] * 100:.2f}%")
    lines.append(f"- None / soft only: {shares['none'] * 100:.2f}%")
    lines.append("")
    lines.append("## Promotion decision")
    lines.append("")
    lines.append(
        f"- Threshold for promotion to main §5.5: "
        f"**critical_major share >= {PROMOTION_THRESHOLD * 100:.0f}%**"
    )
    lines.append(
        f"- Result: **{'PROMOTE TO MAIN' if promo['promote_to_main'] else 'APPENDIX-ONLY'}**"
    )
    lines.append(f"- Reason: {promo['decision_reason']}")
    lines.append("")
    lines.append("## Per-model severity distribution")
    lines.append("")
    lines.append(
        "| Model | catastrophic | severe | major | moderate | minor | none |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for m in sorted(metrics["by_model"]):
        c = metrics["by_model"][m]
        lines.append(
            f"| {m} | "
            f"{c.get('catastrophic', 0)} | "
            f"{c.get('severe', 0)} | "
            f"{c.get('major', 0)} | "
            f"{c.get('moderate', 0)} | "
            f"{c.get('minor', 0)} | "
            f"{c.get('none', 0)} |"
        )
    lines.append("")
    lines.append("## Drop-in paper sentences")
    lines.append("")
    if promo["promote_to_main"]:
        lines.append(
            f"> Of the {n} strict-3-way false-accept episodes that survive the "
            f"high-authority filter, {shares['critical_major'] * 100:.1f}\\% "
            f"carry at least one *critical, severe, or major* harm violation "
            f"(\\Eninecriticalshare\\%); the high-authority blind spot is "
            f"therefore not only guideline-authoritative but also "
            f"harm-relevant."
        )
    else:
        lines.append(
            f"> Severity overlay (Appendix Z.5) reports a "
            f"{shares['critical_major'] * 100:.1f}\\% critical+major share "
            f"across the {n} strict-FA episodes; the share falls below the "
            f"pre-registered {PROMOTION_THRESHOLD * 100:.0f}\\% threshold for "
            f"main-text promotion."
        )
    return "\n".join(lines)


def render_macros(metrics: dict[str, Any]) -> str:
    s = metrics["shares"]
    n = metrics["n_episodes"]
    counts = metrics["severity_counts"]
    cat = counts.get("catastrophic", 0)
    sev = counts.get("severe", 0)
    maj = counts.get("major", 0)
    mod = counts.get("moderate", 0)
    minor_n = counts.get("minor", 0)
    none_n = counts.get("none", 0)

    return (
        "% Auto-generated by scripts/experiments/exp_e39d_severity_overlay.py\n"
        "% E9 Follow-up F3 -- severity overlay on strict-FA episodes\n"
        f"\\newcommand{{\\Eninesevn}}{{{n}}}\n"
        f"\\newcommand{{\\Eninecriticalshare}}{{{s['critical_major'] * 100:.2f}}}\n"
        f"\\newcommand{{\\Eninemoderateshare}}{{{s['moderate'] * 100:.2f}}}\n"
        f"\\newcommand{{\\Enineminorshare}}{{{s['minor'] * 100:.2f}}}\n"
        f"\\newcommand{{\\Eninenoneshare}}{{{s['none'] * 100:.2f}}}\n"
        f"\\newcommand{{\\Eninecatcount}}{{{cat}}}\n"
        f"\\newcommand{{\\Eninesevcount}}{{{sev}}}\n"
        f"\\newcommand{{\\Eninemajcount}}{{{maj}}}\n"
        f"\\newcommand{{\\Eninemodcount}}{{{mod}}}\n"
        f"\\newcommand{{\\Eninemincount}}{{{minor_n}}}\n"
        f"\\newcommand{{\\Eninenoncount}}{{{none_n}}}\n"
    )


def domain_for(sid: str) -> str:
    """Lightweight domain extraction (subset of the blindspot prefix table)."""
    s = (sid or "").lower()
    for prefix, dom in (
        ("septic_shock", "sepsis"), ("sepsis", "sepsis"),
        ("stemi", "chest_pain"), ("nstemi", "chest_pain"),
        ("chest_pain", "chest_pain"), ("acs", "chest_pain"),
        ("stroke", "stroke"), ("tpa", "stroke"),
        ("hfref", "heart_failure"), ("adhf", "heart_failure"),
        ("aki", "aki"), ("contrast_aki", "aki"),
        ("dka", "dka"), ("af_", "atrial_fibrillation"),
        ("copd", "copd"), ("pe_", "pulmonary_embolism"),
        ("gi_bleed", "gi_bleeding"), ("cap_", "pneumonia"),
        ("hypertensive", "hypertensive_emergency"),
        ("anaphylaxis", "anaphylaxis"), ("asthma", "asthma"),
        ("meningitis", "meningitis"), ("acls", "acls"),
        ("status_epilepticus", "epilepticus"),
        ("toxicology", "toxicology"),
        ("aabb_t", "transfusion"), ("aabb", "transfusion"),
        ("aba_burn", "burn"), ("acog", "obstetric"),
        ("apa_agitation", "agitation"), ("pals", "pediatric"),
    ):
        if s.startswith(prefix):
            return dom
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ANALYSIS_DIR)
    args = parser.parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[1/3] Loading verdict matrix", flush=True)
    with open(VERDICT_MATRIX_PATH) as f:
        vmatrix = json.load(f)

    print("[2/3] Filtering to strict-FA episodes + indexing raw JSONs", flush=True)
    strict_fa = find_strict_fa_episodes(vmatrix)
    print(f"      {len(strict_fa)} strict-FA episodes", flush=True)
    episode_index = build_episode_index(RESULTS_DIRS_DEFAULT)

    print("[3/3] Reading violation events + computing max severity", flush=True)
    rows: list[dict] = []
    n_skipped = 0
    for ep in strict_fa:
        sid = ep.get("scenario_id", "")
        m = ep.get("model_dir", "")
        r = ep.get("run_index", -1)
        path = episode_index.get((sid, m, r))
        if path is None:
            n_skipped += 1
            continue
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            n_skipped += 1
            continue
        sev = max_hard_severity(data.get("violation_events") or [])
        rows.append({
            "episode_id": ep.get("episode_id"),
            "scenario_id": sid,
            "model_dir": m,
            "run_index": r,
            "domain": domain_for(sid),
            "max_severity": sev,
        })
    print(f"      {len(rows)} episodes inspected, {n_skipped} skipped", flush=True)

    metrics = aggregate(rows)
    metrics["_meta"] = {
        "spec": "docs/attack_gap_exp_exp/260430_add_contribution_exp.md",
        "verdict_matrix": str(VERDICT_MATRIX_PATH),
        "n_strict_fa_input": len(strict_fa),
        "n_skipped": n_skipped,
    }

    json_out = out_dir / "exp_e9_severity_overlay.json"
    md_out = out_dir / "exp_e9_severity_overlay.md"
    macros_out = out_dir / "exp_e9_severity_macros.tex"
    with open(json_out, "w") as f:
        json.dump(metrics, f, indent=2)
    with open(md_out, "w") as f:
        f.write(render_md(metrics))
    with open(macros_out, "w") as f:
        f.write(render_macros(metrics))
    print(f"      json:    {json_out}")
    print(f"      md:      {md_out}")
    print(f"      macros:  {macros_out}")

    s = metrics["shares"]
    print()
    print(f"Critical+Severe+Major share: {s['critical_major'] * 100:.2f}%")
    print(
        f"Promotion: {'PROMOTE' if metrics['promotion']['promote_to_main'] else 'appendix-only'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
