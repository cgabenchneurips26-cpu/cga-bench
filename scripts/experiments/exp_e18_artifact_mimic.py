#!/usr/bin/env python3
"""EX-18: Artifact Mimic — Does TCC add value over existing evaluators?

For each episode, compute:
  - AC-Proxy verdict (coverage >= 0.5)
  - MAB-Proxy verdict (F1 >= 0.5)
  - C2 verdict (coverage - timing_penalty >= 0.7)
  - TCC verdict (any hard violation → FAIL)

Then show:
  - AC+TCC catches X% more than AC alone
  - MAB+TCC catches X% more than MAB alone
  - Episodes where proxy=PASS but TCC=FAIL (blind spots)

Output: evidence_pack/analysis/exp_e18_artifact_mimic.json
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results" / "full_706_v5"

# Canonical model set (must match verdict_matrix_v5.py)
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
OUTPUT_JSON = ROOT / "evidence_pack" / "analysis" / "exp_e18_artifact_mimic.json"
OUTPUT_MD = ROOT / "evidence_pack" / "analysis" / "exp_e18_artifact_mimic.md"

AC_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5
C2_THRESHOLD = 0.7
C2_TIMING_PENALTY = 0.05


def _normalize_action_id(action_id: str) -> str:
    """Basic normalization for action ID comparison."""
    return action_id.strip().lower().replace("-", "_").replace(" ", "_")


def _extract_action_sets(ep: dict) -> tuple[set[str], set[str], set[str]]:
    """Extract performed, expected, forbidden action sets from episode."""
    performed = set()
    for a in ep.get("actions", []):
        aid = a.get("action_id", "") if isinstance(a, dict) else str(a)
        if aid:
            performed.add(_normalize_action_id(aid))

    expected = set()
    for a in ep.get("expected_actions", []):
        if isinstance(a, dict):
            aid = a.get("action_id", "")
        else:
            aid = str(a)
        if aid:
            expected.add(_normalize_action_id(aid))

    forbidden = set()
    for a in ep.get("forbidden_actions", []):
        if isinstance(a, dict):
            aid = a.get("action_id", "")
        else:
            aid = str(a)
        if aid:
            forbidden.add(_normalize_action_id(aid))

    return performed, expected, forbidden


def _extract_violation_types(ep: dict) -> dict[str, int]:
    """Extract violation counts by type."""
    counts: dict[str, int] = Counter()
    for v in ep.get("violation_events", []):
        if isinstance(v, dict):
            vtype = v.get("violation_type", v.get("type", "unknown"))
        else:
            vtype = "unknown"
        vtype_upper = str(vtype).upper().strip()
        # Normalize
        for canonical in ("OMISSION", "COMMISSION", "TIMING", "SEQUENCE", "DEVIATION"):
            if canonical in vtype_upper:
                counts[canonical] += 1
                break
        else:
            counts["OTHER"] += 1
    return dict(counts)


def _has_hard_violation(ep: dict) -> bool:
    """TCC: any hard violation → FAIL.

    Hard violations map to hard graph constraints:
      COMMISSION ← FORBIDDEN constraint
      TIMING     ← WITHIN constraint
      SEQUENCE   ← BEFORE constraint

    OMISSION (from MUST) and DEVIATION are soft — excluded per
    verdict_matrix_v4.py canonical definition.
    """
    viol_types = _extract_violation_types(ep)
    hard_types = {"COMMISSION", "TIMING", "SEQUENCE"}
    return any(viol_types.get(t, 0) > 0 for t in hard_types)


def _ac_verdict(performed: set[str], expected: set[str]) -> bool:
    """AC-Proxy: coverage >= 0.5."""
    if not expected:
        return True
    coverage = len(performed & expected) / len(expected)
    return coverage >= AC_THRESHOLD


def _mab_verdict(performed: set[str], expected: set[str]) -> bool:
    """MAB-Proxy: F1 >= 0.5 (pure F1, no forbidden penalty).

    Matches canonical definition in verdict_matrix_v4.py:_mab_verdict().
    """
    if not expected:
        return True
    tp = len(performed & expected)
    precision = tp / len(performed) if performed else 0.0
    recall = tp / len(expected)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return f1 >= MAB_F1_THRESHOLD


def _c2_verdict(performed: set[str], expected: set[str], viol_types: dict[str, int]) -> bool:
    """C2: coverage - timing_penalty >= 0.7."""
    if not expected:
        return True
    coverage = len(performed & expected) / len(expected)
    timing_count = viol_types.get("TIMING", 0)
    score = coverage - timing_count * C2_TIMING_PENALTY
    return score >= C2_THRESHOLD


def load_episodes() -> list[dict]:
    """Load all episode JSONs from results dir, deduplicated."""
    episodes = []
    seen = set()

    if not RESULTS_DIR.exists():
        logger.error(f"Results dir not found: {RESULTS_DIR}")
        return []

    for model_dir in sorted(RESULTS_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        if model_name not in MODEL_LABELS:
            continue
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

            ep["_model"] = model_name
            ep["_file"] = f.name
            episodes.append(ep)

    # --- Canonical-set filter: match verdict_matrix_v6.json exactly ---
    vm_path = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
    if vm_path.exists():
        vm = json.loads(vm_path.read_text())
        canonical_keys: set[str] = set()
        for rec in vm.get("per_episode", []):
            k = f"{rec.get('scenario_id', '')}_{rec.get('model_dir', '')}_{rec.get('run_index', 0)}"
            canonical_keys.add(k)
        kept = []
        for ep in episodes:
            k = f"{ep.get('scenario_id', '')}_{ep['_model']}_{ep.get('run_index', 0)}"
            if k in canonical_keys:
                kept.append(ep)
        logger.info(f"  Canonical filter: {len(episodes)} -> {len(kept)} episodes (from verdict_matrix_v6.json)")
        return kept
    else:
        logger.warning("verdict_matrix_v6.json not found — returning all episodes unfiltered")
        return episodes


def compute_artifact_mimic(episodes: list[dict]) -> dict:
    """Main analysis: compute all evaluator verdicts and cross-tabulate."""
    results = {
        "n_episodes": len(episodes),
        "per_evaluator": {},
        "cross_tab": {},
        "blind_spot_examples": [],
        "per_model": {},
    }

    # Counters
    ac_pass = 0
    mab_pass = 0
    c2_pass = 0
    tcc_pass = 0

    ac_pass_tcc_fail = 0
    mab_pass_tcc_fail = 0
    c2_pass_tcc_fail = 0

    # Per-model tracking
    model_stats: dict[str, dict] = defaultdict(
        lambda: {
            "n": 0,
            "ac_pass": 0,
            "mab_pass": 0,
            "c2_pass": 0,
            "tcc_pass": 0,
            "ac_tcc_gain": 0,
            "mab_tcc_gain": 0,
            "c2_tcc_gain": 0,
        }
    )

    # Violation type breakdown for blind spots
    blind_spot_viol_types: dict[str, int] = Counter()

    for ep in episodes:
        performed, expected, forbidden = _extract_action_sets(ep)
        viol_types = _extract_violation_types(ep)
        has_hard = _has_hard_violation(ep)

        v_ac = _ac_verdict(performed, expected)
        v_mab = _mab_verdict(performed, expected)
        v_c2 = _c2_verdict(performed, expected, viol_types)
        v_tcc = not has_hard

        model = ep.get("_model", "unknown")
        ms = model_stats[model]
        ms["n"] += 1

        if v_ac:
            ac_pass += 1
            ms["ac_pass"] += 1
        if v_mab:
            mab_pass += 1
            ms["mab_pass"] += 1
        if v_c2:
            c2_pass += 1
            ms["c2_pass"] += 1
        if v_tcc:
            tcc_pass += 1
            ms["tcc_pass"] += 1

        # Blind spots: proxy says PASS but TCC says FAIL
        if v_ac and not v_tcc:
            ac_pass_tcc_fail += 1
            ms["ac_tcc_gain"] += 1
            for vt, cnt in viol_types.items():
                blind_spot_viol_types[vt] += cnt

            if len(results["blind_spot_examples"]) < 10:
                results["blind_spot_examples"].append(
                    {
                        "scenario_id": ep.get("scenario_id"),
                        "model": model,
                        "run_index": ep.get("run_index"),
                        "ac_coverage": round(len(performed & expected) / max(len(expected), 1), 3),
                        "violations": viol_types,
                        "n_actions": len(ep.get("actions", [])),
                    }
                )

        if v_mab and not v_tcc:
            mab_pass_tcc_fail += 1
            ms["mab_tcc_gain"] += 1

        if v_c2 and not v_tcc:
            c2_pass_tcc_fail += 1
            ms["c2_tcc_gain"] += 1

    n = len(episodes)

    # Per-evaluator pass rates
    results["per_evaluator"] = {
        "AC": {"pass": ac_pass, "rate": round(ac_pass / n * 100, 1) if n else 0},
        "MAB": {"pass": mab_pass, "rate": round(mab_pass / n * 100, 1) if n else 0},
        "C2": {"pass": c2_pass, "rate": round(c2_pass / n * 100, 1) if n else 0},
        "TCC": {"pass": tcc_pass, "rate": round(tcc_pass / n * 100, 1) if n else 0},
    }

    # Cross-tabulation: "X+TCC catches Y% more than X alone"
    ac_gain_pct = round(ac_pass_tcc_fail / ac_pass * 100, 1) if ac_pass else 0
    mab_gain_pct = round(mab_pass_tcc_fail / mab_pass * 100, 1) if mab_pass else 0
    c2_gain_pct = round(c2_pass_tcc_fail / c2_pass * 100, 1) if c2_pass else 0

    results["cross_tab"] = {
        "AC_pass_TCC_fail": ac_pass_tcc_fail,
        "AC_gain_pct": ac_gain_pct,
        "MAB_pass_TCC_fail": mab_pass_tcc_fail,
        "MAB_gain_pct": mab_gain_pct,
        "C2_pass_TCC_fail": c2_pass_tcc_fail,
        "C2_gain_pct": c2_gain_pct,
    }

    # Blind spot violation type breakdown
    results["blind_spot_violation_types"] = dict(blind_spot_viol_types)

    # Per-model breakdown
    for model, ms in sorted(model_stats.items()):
        mn = ms["n"]
        results["per_model"][model] = {
            "n": mn,
            "ac_pass_rate": round(ms["ac_pass"] / mn * 100, 1) if mn else 0,
            "mab_pass_rate": round(ms["mab_pass"] / mn * 100, 1) if mn else 0,
            "c2_pass_rate": round(ms["c2_pass"] / mn * 100, 1) if mn else 0,
            "tcc_pass_rate": round(ms["tcc_pass"] / mn * 100, 1) if mn else 0,
            "ac_tcc_gain": ms["ac_tcc_gain"],
            "ac_tcc_gain_pct": round(ms["ac_tcc_gain"] / ms["ac_pass"] * 100, 1) if ms["ac_pass"] else 0,
        }

    # Headline: "Adding TCC to AC catches X% more failures"
    results["headline"] = (
        f"AC+TCC catches {ac_gain_pct}% more failures than AC alone "
        f"({ac_pass_tcc_fail}/{ac_pass} AC-passing episodes have hard violations). "
        f"MAB+TCC: {mab_gain_pct}% gain. C2+TCC: {c2_gain_pct}% gain."
    )

    return results


def generate_markdown(results: dict) -> str:
    """Generate human-readable markdown report."""
    lines = [
        "# EX-18: Artifact Mimic — TCC Value-Add Over Existing Evaluators",
        "",
        f"**Episodes analyzed:** {results['n_episodes']}",
        "",
        f"**Headline:** {results['headline']}",
        "",
        "## Pass Rates by Evaluator",
        "",
        "| Evaluator | Pass | Rate |",
        "|-----------|------|------|",
    ]
    for name, data in results["per_evaluator"].items():
        lines.append(f"| {name} | {data['pass']} | {data['rate']}% |")

    lines += [
        "",
        "## TCC Gain (Blind Spots Exposed)",
        "",
        "| Proxy | Proxy=PASS & TCC=FAIL | Gain (%) |",
        "|-------|----------------------|----------|",
    ]
    ct = results["cross_tab"]
    lines.append(f"| AC-Proxy | {ct['AC_pass_TCC_fail']} | {ct['AC_gain_pct']}% |")
    lines.append(f"| MAB-Proxy | {ct['MAB_pass_TCC_fail']} | {ct['MAB_gain_pct']}% |")
    lines.append(f"| C2 | {ct['C2_pass_TCC_fail']} | {ct['C2_gain_pct']}% |")

    lines += [
        "",
        "## Blind Spot Violation Types",
        "",
        "Among AC-passing episodes that TCC catches:",
        "",
    ]
    for vt, cnt in sorted(results.get("blind_spot_violation_types", {}).items()):
        lines.append(f"- {vt}: {cnt}")

    lines += [
        "",
        "## Per-Model Breakdown",
        "",
        "| Model | N | AC Pass% | TCC Pass% | AC+TCC Gain | Gain% |",
        "|-------|---|----------|-----------|-------------|-------|",
    ]
    for model, ms in results.get("per_model", {}).items():
        lines.append(
            f"| {model} | {ms['n']} | {ms['ac_pass_rate']}% | "
            f"{ms['tcc_pass_rate']}% | {ms['ac_tcc_gain']} | {ms['ac_tcc_gain_pct']}% |"
        )

    lines += [
        "",
        "## Example Blind Spots",
        "",
    ]
    for ex in results.get("blind_spot_examples", []):
        lines.append(
            f"- **{ex['scenario_id']}** ({ex['model']} r{ex['run_index']}): "
            f"coverage={ex['ac_coverage']}, violations={ex['violations']}"
        )

    return "\n".join(lines)


def main() -> None:
    logger.info("Loading episodes...")
    episodes = load_episodes()
    logger.info(f"  Loaded {len(episodes)} deduplicated episodes")

    if not episodes:
        logger.error("No episodes found!")
        return

    logger.info("Computing artifact mimic analysis...")
    results = compute_artifact_mimic(episodes)

    # Save JSON
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"  Saved: {OUTPUT_JSON}")

    # Save markdown
    md = generate_markdown(results)
    with open(OUTPUT_MD, "w") as f:
        f.write(md)
    logger.info(f"  Saved: {OUTPUT_MD}")

    # Print summary
    print("\n" + "=" * 60)
    print("EX-18 ARTIFACT MIMIC RESULTS")
    print("=" * 60)
    print(f"  Episodes: {results['n_episodes']}")
    print()
    print("  Pass rates:")
    for name, data in results["per_evaluator"].items():
        print(f"    {name:8s}: {data['pass']:6d} ({data['rate']}%)")
    print()
    ct = results["cross_tab"]
    print(f"  AC+TCC gain:  {ct['AC_pass_TCC_fail']:5d} episodes ({ct['AC_gain_pct']}%)")
    print(f"  MAB+TCC gain: {ct['MAB_pass_TCC_fail']:5d} episodes ({ct['MAB_gain_pct']}%)")
    print(f"  C2+TCC gain:  {ct['C2_pass_TCC_fail']:5d} episodes ({ct['C2_gain_pct']}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
