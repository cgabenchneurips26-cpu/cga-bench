#!/usr/bin/env python3
"""EX-24: Consensus FA Severity Breakdown — clinical severity of false accepts.

For consensus false-accept episodes (AC_pass AND C2_pass AND has_hard_violation),
classify severity by worst violation:
  Critical: COMMISSION (FORBIDDEN) violations
  High:     TIMING (WITHIN) with margin > 60 min
  Medium:   TIMING (WITHIN) with margin 5-60 min
  Low:      SEQUENCE (BEFORE) violations only

Breakdowns by domain, model, and scenario source (manual/auto).

Output: evidence_pack/ex24_fa_severity/
Macros: consensusFACritical, consensusFACriticalPct, etc.

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e24_fa_severity.py
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import (
    load_all_scenarios,
    save_json,
    save_markdown,
)

RESULTS_DIR = ROOT / "results" / "full_706_v5"
VM_PATH = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
OUTPUT_DIR = ROOT / "evidence_pack" / "ex24_fa_severity"

MODEL_LABELS: set[str] = {
    "oss120b",
    "qwen27b",
    "qwen35b",
    "qwen4b",
    "qwen397b",
    "gemma31b",
    "nemotron30b",
    "deepseek_r1_7b",
}

HARD_VIOL_TYPES = frozenset({"COMMISSION", "TIMING", "SEQUENCE"})
AC_THRESHOLD = 0.5
C2_THRESHOLD = 0.7
C2_TIMING_PENALTY = 0.05

SEVERITY_ORDER = ["critical", "high", "medium", "low"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_action(aid: str) -> str:
    return aid.strip().lower().replace("-", "_").replace(" ", "_")


def _extract_action_sets(ep: dict) -> tuple[set[str], set[str]]:
    performed: set[str] = set()
    for a in ep.get("actions", []):
        aid = a.get("action_id", "") if isinstance(a, dict) else str(a)
        if aid:
            performed.add(_normalize_action(aid))
    expected: set[str] = set()
    for a in ep.get("expected_actions", []):
        aid = a.get("action_id", "") if isinstance(a, dict) else str(a)
        if aid:
            expected.add(_normalize_action(aid))
    return performed, expected


def _classify_violation_type(raw: str) -> str:
    lower = raw.upper().strip()
    for canonical in ("OMISSION", "COMMISSION", "TIMING", "SEQUENCE", "DEVIATION"):
        if canonical in lower:
            return canonical
    return "UNKNOWN"


def _has_hard_violation(ep: dict) -> bool:
    for v in ep.get("violation_events", []):
        vt = _classify_violation_type(str(v.get("violation_type", v.get("type", ""))))
        if vt in HARD_VIOL_TYPES:
            return True
    return False


def _is_consensus_fa(ep: dict) -> bool:
    """Consensus false accept: AC pass AND C2 pass AND has hard violation.

    Uses pre-computed verdicts from verdict_matrix (attached by load_episodes)
    to ensure consistency with the canonical verdict definitions.
    """
    return bool(ep.get("_vm_ac_pass") and ep.get("_vm_c2_pass") and ep.get("_vm_has_hard"))


def _classify_severity(ep: dict) -> str:
    """Classify episode severity by worst hard violation.

    Severity tiers (descending):
      critical: any COMMISSION (FORBIDDEN) violation
      high:     any TIMING with margin > 60 min
      medium:   any TIMING with margin 5-60 min (or margin unknown)
      low:      SEQUENCE (BEFORE) only
    """
    has_commission = False
    max_timing_margin = -1.0
    has_timing = False
    has_sequence = False

    for v in ep.get("violation_events", []):
        vt = _classify_violation_type(str(v.get("violation_type", v.get("type", ""))))

        if vt == "COMMISSION":
            has_commission = True
        elif vt == "TIMING":
            has_timing = True
            deadline = v.get("expected_deadline")
            actual = v.get("actual_time") or v.get("timestamp_minutes")
            if deadline is not None and actual is not None:
                try:
                    margin = float(actual) - float(deadline)
                    if margin > max_timing_margin:
                        max_timing_margin = margin
                except (TypeError, ValueError):
                    pass
        elif vt == "SEQUENCE":
            has_sequence = True

    if has_commission:
        return "critical"
    if has_timing:
        if max_timing_margin > 60:
            return "high"
        return "medium"
    if has_sequence:
        return "low"
    return "low"  # fallback


# ---------------------------------------------------------------------------
# Episode loading
# ---------------------------------------------------------------------------


def _load_verdict_matrix() -> dict[str, dict]:
    """Load verdict_matrix and build lookup by canonical key."""
    if not VM_PATH.exists():
        return {}
    vm = json.loads(VM_PATH.read_text())
    lookup: dict[str, dict] = {}
    for rec in vm.get("per_episode", []):
        k = f"{rec.get('scenario_id', '')}_{rec.get('model_dir', '')}_{rec.get('run_index', 0)}"
        lookup[k] = rec
    return lookup


def load_episodes() -> list[dict]:
    """Load canonical episodes with metadata and verdict_matrix verdicts."""
    scenarios = load_all_scenarios(tag_source=True)
    sid_to_graph: dict[str, str] = {}
    sid_to_source: dict[str, str] = {}
    for s in scenarios:
        sid = s.get("scenario_id", "")
        sid_to_graph[sid] = s.get("_canonical_graph_id", "")
        sid_to_source[sid] = s.get("source_type", "unknown")

    vm_lookup = _load_verdict_matrix()
    canonical_keys: set[str] = set(vm_lookup.keys())

    episodes: list[dict] = []
    seen: set[str] = set()

    for model_dir in sorted(RESULTS_DIR.iterdir()):
        if not model_dir.is_dir() or model_dir.name not in MODEL_LABELS:
            continue
        model_name = model_dir.name
        for f in sorted(model_dir.glob("*.json")):
            if f.name.startswith(("checkpoint", ".claim", "log_")):
                continue
            try:
                ep = json.loads(f.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(ep, dict):
                continue
            sid = ep.get("scenario_id", "")
            if not sid:
                continue
            run_idx = ep.get("run_index", 0)
            dedup_key = f"{sid}_{model_name}_r{run_idx}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            canon_key = f"{sid}_{model_name}_{run_idx}"
            if canonical_keys and canon_key not in canonical_keys:
                continue

            ep["_model"] = model_name
            ep["_graph_id"] = sid_to_graph.get(sid, "")
            ep["_source_type"] = sid_to_source.get(sid, "unknown")

            # Attach pre-computed verdicts from verdict_matrix
            vm_rec = vm_lookup.get(canon_key, {})
            ep["_vm_ac_pass"] = vm_rec.get("ac_proxy", False)
            ep["_vm_c2_pass"] = vm_rec.get("c2_pass", False)
            ep["_vm_has_hard"] = vm_rec.get("v4_hard", False)
            episodes.append(ep)

    return episodes


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_consensus_fa(episodes: list[dict]) -> dict:
    """Main analysis: severity breakdown of consensus false accepts."""
    n_total = len(episodes)

    # Find consensus FA episodes
    fa_episodes: list[dict] = []
    for ep in episodes:
        if _is_consensus_fa(ep):
            ep["_severity"] = _classify_severity(ep)
            fa_episodes.append(ep)

    n_fa = len(fa_episodes)
    print(f"  Consensus FA episodes: {n_fa}/{n_total} ({n_fa / n_total * 100:.1f}%)")

    # Overall severity breakdown
    severity_counts: Counter[str] = Counter()
    for ep in fa_episodes:
        severity_counts[ep["_severity"]] += 1

    severity_breakdown: dict[str, dict] = {}
    for sev in SEVERITY_ORDER:
        cnt = severity_counts.get(sev, 0)
        severity_breakdown[sev] = {
            "count": cnt,
            "pct": round(cnt / max(n_fa, 1) * 100, 1),
            "pct_of_total": round(cnt / max(n_total, 1) * 100, 1),
        }

    # By domain
    domain_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    for ep in fa_episodes:
        domain_breakdown[ep["_graph_id"]][ep["_severity"]] += 1

    domain_results: dict[str, dict] = {}
    for gid in sorted(domain_breakdown):
        domain_results[gid] = {
            "total_fa": sum(domain_breakdown[gid].values()),
            "by_severity": dict(domain_breakdown[gid]),
        }

    # Find domain with max FA
    max_domain = ""
    max_fa = 0
    for gid, dr in domain_results.items():
        if dr["total_fa"] > max_fa:
            max_fa = dr["total_fa"]
            max_domain = gid

    # By model
    model_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    model_total: Counter[str] = Counter()
    for ep in episodes:
        model_total[ep["_model"]] += 1
    for ep in fa_episodes:
        model_breakdown[ep["_model"]][ep["_severity"]] += 1

    model_results: dict[str, dict] = {}
    for model in sorted(MODEL_LABELS):
        fa_count = sum(model_breakdown[model].values())
        total = model_total.get(model, 0)
        model_results[model] = {
            "total_fa": fa_count,
            "fa_rate": round(fa_count / max(total, 1) * 100, 1),
            "n_total": total,
            "by_severity": dict(model_breakdown[model]),
        }

    model_fa_rates = [model_results[m]["fa_rate"] for m in sorted(model_results)]
    model_fa_range_str = f"{min(model_fa_rates):.1f}--{max(model_fa_rates):.1f}" if model_fa_rates else "N/A"

    # By source
    source_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    for ep in fa_episodes:
        source_breakdown[ep["_source_type"]][ep["_severity"]] += 1

    source_results: dict[str, dict] = {}
    for src in sorted(source_breakdown):
        source_results[src] = {
            "total_fa": sum(source_breakdown[src].values()),
            "by_severity": dict(source_breakdown[src]),
        }

    return {
        "n_total_episodes": n_total,
        "n_consensus_fa": n_fa,
        "consensus_fa_rate": round(n_fa / max(n_total, 1) * 100, 1),
        "severity_breakdown": severity_breakdown,
        "by_domain": domain_results,
        "domain_max_fa": max_domain,
        "domain_max_fa_count": max_fa,
        "by_model": model_results,
        "model_fa_range": model_fa_range_str,
        "by_source": source_results,
    }


def generate_markdown(results: dict) -> str:
    lines = [
        "# EX-24: Consensus FA Severity Breakdown",
        "",
        f"**Total episodes:** {results['n_total_episodes']}",
        f"**Consensus FA:** {results['n_consensus_fa']} ({results['consensus_fa_rate']}%)",
        "",
        "## Severity Breakdown",
        "",
        "| Severity | Count | % of FA | % of Total |",
        "|----------|-------|---------|------------|",
    ]
    for sev in SEVERITY_ORDER:
        sb = results["severity_breakdown"].get(sev, {})
        lines.append(
            f"| {sev.capitalize()} | {sb.get('count', 0)} | {sb.get('pct', 0)}% | {sb.get('pct_of_total', 0)}% |"
        )

    lines.extend(
        [
            "",
            "## By Domain (top 10)",
            "",
            "| Domain | Total FA | Critical | High | Medium | Low |",
            "|--------|----------|----------|------|--------|-----|",
        ]
    )
    sorted_domains = sorted(results["by_domain"].items(), key=lambda x: x[1]["total_fa"], reverse=True)
    for gid, dr in sorted_domains[:10]:
        bs = dr["by_severity"]
        lines.append(
            f"| {gid} | {dr['total_fa']} | "
            f"{bs.get('critical', 0)} | {bs.get('high', 0)} | "
            f"{bs.get('medium', 0)} | {bs.get('low', 0)} |"
        )

    lines.extend(
        [
            "",
            "## By Model",
            "",
            "| Model | Total FA | FA Rate | Critical | High | Medium | Low |",
            "|-------|----------|---------|----------|------|--------|-----|",
        ]
    )
    for model, mr in sorted(results["by_model"].items()):
        bs = mr["by_severity"]
        lines.append(
            f"| {model} | {mr['total_fa']} | {mr['fa_rate']}% | "
            f"{bs.get('critical', 0)} | {bs.get('high', 0)} | "
            f"{bs.get('medium', 0)} | {bs.get('low', 0)} |"
        )

    lines.extend(
        [
            "",
            "## By Source",
            "",
            "| Source | Total FA | Critical | High | Medium | Low |",
            "|--------|----------|----------|------|--------|-----|",
        ]
    )
    for src, sr in sorted(results["by_source"].items()):
        bs = sr["by_severity"]
        lines.append(
            f"| {src} | {sr['total_fa']} | "
            f"{bs.get('critical', 0)} | {bs.get('high', 0)} | "
            f"{bs.get('medium', 0)} | {bs.get('low', 0)} |"
        )

    lines.extend(
        [
            "",
            "## Key Findings",
            "",
            f"- Domain with most FA: **{results['domain_max_fa']}** ({results['domain_max_fa_count']})",
            f"- Model FA range: {results['model_fa_range']}%",
        ]
    )

    return "\n".join(lines)


def generate_macros(results: dict) -> str:
    sb = results["severity_breakdown"]
    lines = [
        "",
        "% ---------------------------------------------------------------------------",
        "% EX-24: Consensus FA Severity Breakdown",
        "% ---------------------------------------------------------------------------",
        f"\\newcommand{{\\consensusFATotal}}{{{results['n_consensus_fa']}}}",
        f"\\newcommand{{\\consensusFARate}}{{{results['consensus_fa_rate']}}}",
        f"\\newcommand{{\\consensusFACritical}}{{{sb.get('critical', {}).get('count', 0)}}}",
        f"\\newcommand{{\\consensusFACriticalPct}}{{{sb.get('critical', {}).get('pct', 0)}}}",
        f"\\newcommand{{\\consensusFAHigh}}{{{sb.get('high', {}).get('count', 0)}}}",
        f"\\newcommand{{\\consensusFAMedium}}{{{sb.get('medium', {}).get('count', 0)}}}",
        f"\\newcommand{{\\consensusFALow}}{{{sb.get('low', {}).get('count', 0)}}}",
        f"\\newcommand{{\\consensusFADomainMaxName}}{{{results['domain_max_fa']}}}",
        f"\\newcommand{{\\consensusFADomainMax}}{{{results['domain_max_fa_count']}}}",
        f"\\newcommand{{\\consensusFAModelRange}}{{{results['model_fa_range']}}}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("EX-24: CONSENSUS FA SEVERITY BREAKDOWN")
    print("=" * 70)

    episodes = load_episodes()
    print(f"Loaded {len(episodes)} canonical episodes")

    results = analyze_consensus_fa(episodes)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(results, OUTPUT_DIR / "consensus_fa_severity.json")

    md = generate_markdown(results)
    save_markdown(md, OUTPUT_DIR / "consensus_fa_severity.md")

    macros = generate_macros(results)
    macros_path = OUTPUT_DIR / "macros.tex"
    macros_path.write_text(macros)
    print(f"  Saved: {macros_path}")

    # Print summary
    sb = results["severity_breakdown"]
    print(
        f"\n  Consensus FA: {results['n_consensus_fa']}/{results['n_total_episodes']} ({results['consensus_fa_rate']}%)"
    )
    for sev in SEVERITY_ORDER:
        s = sb.get(sev, {})
        print(f"    {sev.capitalize():10s}: {s.get('count', 0):5d} ({s.get('pct', 0)}%)")
    print(f"  Domain max: {results['domain_max_fa']} ({results['domain_max_fa_count']})")
    print(f"  Model FA range: {results['model_fa_range']}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
