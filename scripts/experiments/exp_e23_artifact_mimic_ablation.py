#!/usr/bin/env python3
"""EX-23: Artifact Mimic Ablation — per-mode detection loss analysis.

For each of 4 artifact scoring modes, compute per-violation-type detection
rates on 14,826 canonical episodes.  This extends EX-18 by showing *why*
process-oblivious evaluators miss violations.

Artifact modes (information stripped progressively):
  AC-Artifact:  coverage only (no timestamps, no ordering, no forbidden check)
  MAB-Artifact: F1 only (no timestamps, no ordering)
  HB-Artifact:  coverage + sequence penalty (no precise timestamps)
  TCC:          full constraint checking (baseline, 100% detection by def.)

Violation types mapped to constraint types:
  COMMISSION → FORBIDDEN, TIMING → WITHIN, SEQUENCE → BEFORE, OMISSION → MUST

Output: evidence_pack/ex23_artifact_ablation/
Macros: mimicACDetectionLoss, mimicMABDetectionLoss, etc.

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e23_artifact_mimic_ablation.py
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import save_json, save_markdown

RESULTS_DIR = ROOT / "results" / "full_706_v5"
VM_PATH = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
OUTPUT_DIR = ROOT / "evidence_pack" / "ex23_artifact_ablation"

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

# Hard violation types (trigger TCC FAIL)
HARD_VIOL_TYPES = frozenset({"COMMISSION", "TIMING", "SEQUENCE"})

# All violation types to track detection
ALL_VIOL_TYPES = ("COMMISSION", "TIMING", "SEQUENCE", "OMISSION")

# Constraint-type labels for paper
CONSTRAINT_LABEL = {
    "COMMISSION": "FORBIDDEN",
    "TIMING": "WITHIN",
    "SEQUENCE": "BEFORE",
    "OMISSION": "MUST",
}

# Scoring thresholds
AC_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5
HB_THRESHOLD = 0.5
HB_SEQ_PENALTY = 0.05


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
    upper = raw.upper().strip()
    for canonical in ("OMISSION", "COMMISSION", "TIMING", "SEQUENCE", "DEVIATION"):
        if canonical in upper:
            return canonical
    return "UNKNOWN"


def _extract_violation_counts(ep: dict) -> Counter[str]:
    counts: Counter[str] = Counter()
    for v in ep.get("violation_events", []):
        vt = _classify_violation_type(str(v.get("violation_type", v.get("type", ""))))
        counts[vt] += 1
    return counts


# ---------------------------------------------------------------------------
# Artifact mode scoring functions
# ---------------------------------------------------------------------------


def _ac_artifact(performed: set[str], expected: set[str], viol_counts: Counter[str]) -> bool:
    """AC-Artifact: coverage only — no timing, ordering, or forbidden check."""
    if not expected:
        return True
    coverage = len(performed & expected) / len(expected)
    return coverage >= AC_THRESHOLD


def _mab_artifact(performed: set[str], expected: set[str], viol_counts: Counter[str]) -> bool:
    """MAB-Artifact: F1 only — no timing or ordering."""
    if not expected:
        return True
    tp = len(performed & expected)
    precision = tp / len(performed) if performed else 0.0
    recall = tp / len(expected)
    denom = precision + recall
    if denom == 0:
        return False
    f1 = 2 * precision * recall / denom
    return f1 >= MAB_F1_THRESHOLD


def _hb_artifact(performed: set[str], expected: set[str], viol_counts: Counter[str]) -> bool:
    """HB-Artifact: coverage + sequence penalty (implicit ordering, no timestamps)."""
    if not expected:
        return True
    coverage = len(performed & expected) / len(expected)
    seq_count = viol_counts.get("SEQUENCE", 0)
    score = coverage - seq_count * HB_SEQ_PENALTY
    return score >= HB_THRESHOLD


def _tcc_full(performed: set[str], expected: set[str], viol_counts: Counter[str]) -> bool:
    """TCC: any hard violation → FAIL."""
    return not any(viol_counts.get(t, 0) > 0 for t in HARD_VIOL_TYPES)


MODES: dict[str, tuple[str, callable]] = {
    "AC-Artifact": ("AC", _ac_artifact),
    "MAB-Artifact": ("MAB", _mab_artifact),
    "HB-Artifact": ("HB", _hb_artifact),
    "TCC": ("TCC", _tcc_full),
}


# ---------------------------------------------------------------------------
# Episode loading
# ---------------------------------------------------------------------------


def load_episodes() -> list[dict]:
    """Load canonical episodes with dedup + verdict_matrix filter."""
    canonical_keys: set[str] = set()
    if VM_PATH.exists():
        vm = json.loads(VM_PATH.read_text())
        for rec in vm.get("per_episode", []):
            k = f"{rec.get('scenario_id', '')}_{rec.get('model_dir', '')}_{rec.get('run_index', 0)}"
            canonical_keys.add(k)

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
            episodes.append(ep)

    return episodes


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze(episodes: list[dict]) -> dict:
    """Compute per-mode detection rates and detection loss."""
    n_total = len(episodes)
    n_tcc_fail = 0

    # Per violation type: total episodes containing that type
    viol_type_episode_totals: Counter[str] = Counter()

    # Per mode: pass count, FA count (pass but has hard violation)
    mode_pass: dict[str, int] = dict.fromkeys(MODES, 0)
    mode_fa: dict[str, int] = dict.fromkeys(MODES, 0)

    # Per mode × violation type: detected count
    # "detected" = mode gives FAIL for an episode containing this viol type
    mode_viol_detected: dict[str, Counter[str]] = {m: Counter() for m in MODES}

    for ep in episodes:
        performed, expected = _extract_action_sets(ep)
        viol_counts = _extract_violation_counts(ep)

        # Which hard violation types present in this episode?
        hard_present = {t for t in HARD_VIOL_TYPES if viol_counts.get(t, 0) > 0}
        has_hard = bool(hard_present)

        # All violation types present (including soft)
        all_present = {t for t in ALL_VIOL_TYPES if viol_counts.get(t, 0) > 0}

        if has_hard:
            n_tcc_fail += 1

        for vt in all_present:
            viol_type_episode_totals[vt] += 1

        for mode_name, (_short, score_fn) in MODES.items():
            verdict = score_fn(performed, expected, viol_counts)
            if verdict:
                mode_pass[mode_name] += 1
                if has_hard:
                    mode_fa[mode_name] += 1
            else:
                # Mode flagged FAIL — counts as detection for present types
                for vt in all_present:
                    mode_viol_detected[mode_name][vt] += 1

    # Build results
    mode_results: dict[str, dict] = {}
    for mode_name in MODES:
        pass_count = mode_pass[mode_name]
        fa_count = mode_fa[mode_name]

        # Detection per violation type
        detection_by_type: dict[str, dict] = {}
        for vt in ALL_VIOL_TYPES:
            total = viol_type_episode_totals.get(vt, 0)
            detected = mode_viol_detected[mode_name].get(vt, 0)
            detection_by_type[CONSTRAINT_LABEL.get(vt, vt)] = {
                "total_episodes": total,
                "detected": detected,
                "rate": round(detected / max(total, 1) * 100, 1),
            }

        # Detection loss: % of TCC detections this mode misses
        mode_detections = n_tcc_fail - fa_count
        detection_loss = round(fa_count / max(n_tcc_fail, 1) * 100, 1)

        mode_results[mode_name] = {
            "pass_count": pass_count,
            "pass_rate": round(pass_count / max(n_total, 1) * 100, 1),
            "fa_count": fa_count,
            "fa_rate": round(fa_count / max(n_total, 1) * 100, 1),
            "detection_loss_vs_tcc": detection_loss,
            "detections": mode_detections,
            "detection_by_type": detection_by_type,
        }

    return {
        "n_total_episodes": n_total,
        "n_tcc_fail": n_tcc_fail,
        "tcc_fail_rate": round(n_tcc_fail / max(n_total, 1) * 100, 1),
        "violation_type_episode_totals": {
            CONSTRAINT_LABEL.get(k, k): v for k, v in sorted(viol_type_episode_totals.items())
        },
        "modes": mode_results,
    }


def generate_markdown(results: dict) -> str:
    lines = [
        "# EX-23: Artifact Mimic Ablation",
        "",
        f"**Total episodes:** {results['n_total_episodes']}",
        f"**TCC fail (hard violation):** {results['n_tcc_fail']} ({results['tcc_fail_rate']}%)",
        "",
        "## Mode Overview",
        "",
        "| Mode | Pass Rate | FA Count | FA Rate | Detection Loss |",
        "|------|-----------|----------|---------|----------------|",
    ]
    for mode_name, mr in results["modes"].items():
        lines.append(
            f"| {mode_name} | {mr['pass_rate']}% | {mr['fa_count']} | "
            f"{mr['fa_rate']}% | {mr['detection_loss_vs_tcc']}% |"
        )

    lines.extend(
        [
            "",
            "## Detection by Violation Type (constraint label)",
            "",
            "| Mode | FORBIDDEN | WITHIN | BEFORE | MUST |",
            "|------|-----------|--------|--------|------|",
        ]
    )
    for mode_name, mr in results["modes"].items():
        dbt = mr["detection_by_type"]
        lines.append(
            f"| {mode_name} "
            f"| {dbt.get('FORBIDDEN', {}).get('rate', 0)}% "
            f"| {dbt.get('WITHIN', {}).get('rate', 0)}% "
            f"| {dbt.get('BEFORE', {}).get('rate', 0)}% "
            f"| {dbt.get('MUST', {}).get('rate', 0)}% |"
        )

    lines.extend(
        [
            "",
            "## Violation Type Episode Totals",
            "",
        ]
    )
    for label, count in sorted(results["violation_type_episode_totals"].items()):
        lines.append(f"- {label}: {count} episodes")

    lines.extend(
        [
            "",
            "## Key Finding",
            "",
            "AC-Artifact and MAB-Artifact cannot detect WITHIN (timing) or "
            "BEFORE (sequence) violations by design — their detection of such "
            "episodes is purely incidental (co-occurring OMISSION lowers coverage).",
        ]
    )

    return "\n".join(lines)


def generate_macros(results: dict) -> str:
    modes = results["modes"]
    ac = modes.get("AC-Artifact", {})
    mab = modes.get("MAB-Artifact", {})
    hb = modes.get("HB-Artifact", {})

    ac_dbt = ac.get("detection_by_type", {})
    mab_dbt = mab.get("detection_by_type", {})

    lines = [
        "",
        "% ---------------------------------------------------------------------------",
        "% EX-23: Artifact Mimic Ablation",
        "% ---------------------------------------------------------------------------",
        f"\\newcommand{{\\mimicACDetectionLoss}}{{{ac.get('detection_loss_vs_tcc', 0)}}}",
        f"\\newcommand{{\\mimicMABDetectionLoss}}{{{mab.get('detection_loss_vs_tcc', 0)}}}",
        f"\\newcommand{{\\mimicHBDetectionLoss}}{{{hb.get('detection_loss_vs_tcc', 0)}}}",
        f"\\newcommand{{\\mimicACFA}}{{{ac.get('fa_rate', 0)}}}",
        f"\\newcommand{{\\mimicMABFA}}{{{mab.get('fa_rate', 0)}}}",
        f"\\newcommand{{\\mimicHBFA}}{{{hb.get('fa_rate', 0)}}}",
        f"\\newcommand{{\\mimicACWithinDetect}}{{{ac_dbt.get('WITHIN', {}).get('rate', 0)}}}",
        f"\\newcommand{{\\mimicMABWithinDetect}}{{{mab_dbt.get('WITHIN', {}).get('rate', 0)}}}",
        f"\\newcommand{{\\mimicACBeforeDetect}}{{{ac_dbt.get('BEFORE', {}).get('rate', 0)}}}",
        f"\\newcommand{{\\mimicMABBeforeDetect}}{{{mab_dbt.get('BEFORE', {}).get('rate', 0)}}}",
        f"\\newcommand{{\\mimicACForbidDetect}}{{{ac_dbt.get('FORBIDDEN', {}).get('rate', 0)}}}",
        f"\\newcommand{{\\mimicMABForbidDetect}}{{{mab_dbt.get('FORBIDDEN', {}).get('rate', 0)}}}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("EX-23: ARTIFACT MIMIC ABLATION")
    print("=" * 70)

    episodes = load_episodes()
    print(f"Loaded {len(episodes)} canonical episodes")

    results = analyze(episodes)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(results, OUTPUT_DIR / "artifact_ablation.json")

    md = generate_markdown(results)
    save_markdown(md, OUTPUT_DIR / "artifact_ablation.md")

    macros = generate_macros(results)
    macros_path = OUTPUT_DIR / "macros.tex"
    macros_path.write_text(macros)
    print(f"  Saved: {macros_path}")

    # Print summary
    print(f"\n  TCC fail: {results['n_tcc_fail']}/{results['n_total_episodes']} ({results['tcc_fail_rate']}%)")
    print()
    print("  Mode          | Pass%  | FA%    | DetLoss%")
    print("  " + "-" * 50)
    for mode_name, mr in results["modes"].items():
        print(
            f"  {mode_name:15s} | {mr['pass_rate']:5.1f}% | {mr['fa_rate']:5.1f}% | {mr['detection_loss_vs_tcc']:5.1f}%"
        )

    print()
    print("  Detection by violation type:")
    print("  Mode          | FORBIDDEN | WITHIN | BEFORE | MUST")
    print("  " + "-" * 55)
    for mode_name, mr in results["modes"].items():
        dbt = mr["detection_by_type"]
        print(
            f"  {mode_name:15s} | "
            f"{dbt.get('FORBIDDEN', {}).get('rate', 0):7.1f}% | "
            f"{dbt.get('WITHIN', {}).get('rate', 0):5.1f}% | "
            f"{dbt.get('BEFORE', {}).get('rate', 0):5.1f}% | "
            f"{dbt.get('MUST', {}).get('rate', 0):5.1f}%"
        )

    print("=" * 70)


if __name__ == "__main__":
    main()
