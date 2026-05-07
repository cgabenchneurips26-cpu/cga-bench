"""Shared episode loading and verdict caching for CRES experiments.

Provides:
- load_cached_episodes(): Load 19,062 baseline episodes (v5, 9 models) with dedup
- load_cached_verdicts(): Load episodes + compute verdicts (cached to disk)
- load_w8_episodes(): Load 8,472 W8 cross-model episodes
- score_episode(): Unified scoring (mirrors exp_e21 / verdict_matrix_v5)

All CRES experiment scripts should import from here instead of
duplicating episode loading logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

RESULTS_DIR_V5 = ROOT / "results" / "full_706_v5"
W8_RESULTS_DIR = ROOT / "results" / "ex_w8_crossmodel"
EVIDENCE_DIR = ROOT / "evidence_pack"
CACHE_DIR = EVIDENCE_DIR / "cres_cache"

# 9 complete models — matches verdict_matrix_v5.py COMPLETE_MODELS
# (706 scenarios × 3 runs × 9 models = 19,062 episodes)
COMPLETE_MODELS: frozenset[str] = frozenset(
    {
        "oss120b",
        "qwen27b",
        "qwen35b",
        "qwen4b",
        "qwen397b",
        "gemma31b",
        "nemotron30b",
        "deepseek_r1_7b",
        "llama4scout",
    }
)

W8_MODELS: list[str] = ["oss120b", "qwen35b", "gemma31b"]
W8_SCAFFOLDS: list[str] = ["react", "direct", "checklist", "tooluse"]

# Evaluator thresholds
AC_COVERAGE_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5
C2_THRESHOLD = 0.7

HARD_VIOL_TYPES: frozenset[str] = frozenset({"commission", "timing", "sequence"})

EVALUATOR_NAMES: list[str] = ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _normalize_action(action_id: str) -> str:
    """Normalize action ID for matching."""
    return action_id.strip().lower().replace("-", "_").replace(" ", "_")


def _classify_violation_type(raw_type: str) -> str:
    """Map raw violation type string to canonical form."""
    lower = raw_type.lower().strip()
    for canonical in ("omission", "commission", "timing", "sequence", "deviation"):
        if canonical in lower:
            return canonical
    return "unknown"


def _action_coverage(performed: set[str], expected: set[str]) -> float:
    """Fraction of expected actions covered by performed."""
    if not expected:
        return 1.0
    return len(performed & expected) / len(expected)


def _mab_f1(performed: set[str], expected: set[str]) -> float:
    """MedAgentBench-style F1 between performed and expected."""
    if not expected:
        return 0.0
    tp = len(performed & expected)
    precision = tp / len(performed) if performed else 0.0
    recall = tp / len(expected)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


# ---------------------------------------------------------------------------
# Episode scoring
# ---------------------------------------------------------------------------


def score_episode(ep: dict[str, Any]) -> dict[str, Any]:
    """Compute evaluator verdicts and violation data for one episode.

    Returns dict with keys:
        scenario_id, run_index, model, v4_hard,
        ac_proxy, mab_proxy, c2_pass, cga_pass,
        coverage, f1, c2_score,
        verdict_flip, ao_fa,
        n_violations, violation_types
    """
    # Extract action sets
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

    coverage = _action_coverage(performed, expected)
    f1 = _mab_f1(performed, expected)
    c2_score = ep.get("compliance_score", 0.0) or 0.0

    # Violation analysis
    has_hard = False
    violation_types: list[str] = []
    n_timing = 0
    n_forbidden = 0
    for v in ep.get("violation_events", []):
        if not isinstance(v, dict):
            continue
        raw_type = str(v.get("violation_type", v.get("type", "")))
        vtype = _classify_violation_type(raw_type)
        violation_types.append(vtype)
        if vtype in HARD_VIOL_TYPES:
            has_hard = True
        if vtype == "timing":
            n_timing += 1
        if vtype == "commission":
            n_forbidden += 1

    # Evaluator verdicts
    ac_proxy = coverage >= AC_COVERAGE_THRESHOLD
    mab_proxy = f1 >= MAB_F1_THRESHOLD
    c2_pass = c2_score >= C2_THRESHOLD
    cga_pass = not has_hard

    # Verdict flip: at least one evaluator pair disagrees
    verdicts = [ac_proxy, mab_proxy, c2_pass, cga_pass]
    verdict_flip = len(set(verdicts)) > 1

    # All-oblivious FA: AC + C2 both pass AND has hard violations
    ao_fa = has_hard and ac_proxy and c2_pass

    return {
        "scenario_id": ep.get("scenario_id", ""),
        "run_index": ep.get("run_index", 0),
        "model": ep.get("_model", ""),
        "v4_hard": has_hard,
        "ac_proxy": ac_proxy,
        "mab_proxy": mab_proxy,
        "c2_pass": c2_pass,
        "cga_pass": cga_pass,
        "coverage": round(coverage, 4),
        "f1": round(f1, 4),
        "c2_score": round(c2_score, 4),
        "verdict_flip": verdict_flip,
        "ao_fa": ao_fa,
        "n_violations": len(violation_types),
        "violation_types": violation_types,
        "n_timing": n_timing,
        "n_forbidden": n_forbidden,
        "n_actions": len(performed),
        "n_expected": len(expected),
        "performed_actions": sorted(performed),
        "expected_actions": sorted(expected),
    }


# ---------------------------------------------------------------------------
# Baseline episode loading (19,062 episodes from full_706_v5, 9 models)
# ---------------------------------------------------------------------------


def load_cached_episodes(
    results_dir: Path | None = None,
    models: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Load all baseline episodes with dedup.

    Args:
        results_dir: Override results directory (default: full_706_v5).
        models: Override model filter (default: COMPLETE_MODELS).

    Returns:
        List of episode dicts with _model tag.
    """
    rdir = results_dir or RESULTS_DIR_V5
    model_filter = models or COMPLETE_MODELS

    episodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    for model_dir in sorted(rdir.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        if model_dir.name not in model_filter:
            continue

        for ep_file in sorted(model_dir.glob("*.json")):
            if ep_file.name.startswith(("checkpoint", ".claim", "log_", "model_summary")):
                continue
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                if not isinstance(ep, dict):
                    continue
                sid = ep.get("scenario_id", "")
                if not sid:
                    continue
                key = f"{model_dir.name}_{sid}_{ep.get('run_index', 0)}"
                if key in seen:
                    continue
                seen.add(key)
                ep["_model"] = model_dir.name
                episodes.append(ep)
            except Exception:
                pass

    return episodes


def load_cached_verdicts(
    results_dir: Path | None = None,
    models: frozenset[str] | None = None,
    use_disk_cache: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load episodes and compute verdicts, with optional disk caching.

    Returns:
        (episodes, scored_records) where each scored_record is
        the output of score_episode().
    """
    cache_file = CACHE_DIR / "verdicts_v5.json"

    if use_disk_cache and cache_file.exists():
        try:
            with open(cache_file) as f:
                cached = json.load(f)
            if len(cached) > 10000:
                print(f"  Loaded {len(cached)} cached verdicts from {cache_file}")
                # Reconstruct minimal episodes for compatibility
                episodes = [
                    {
                        "scenario_id": r["scenario_id"],
                        "run_index": r["run_index"],
                        "_model": r["model"],
                    }
                    for r in cached
                ]
                return episodes, cached
        except Exception:
            pass

    episodes = load_cached_episodes(results_dir, models)
    print(f"  Loaded {len(episodes)} episodes, scoring...")

    scored = [score_episode(ep) for ep in episodes]

    # Cache to disk
    if use_disk_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(scored, f, indent=1, ensure_ascii=False, default=str)
        print(f"  Cached {len(scored)} verdicts to {cache_file}")

    return episodes, scored


# ---------------------------------------------------------------------------
# W8 episode loading (8,472 episodes from ex_w8_crossmodel)
# ---------------------------------------------------------------------------


def load_w8_episodes(
    models: list[str] | None = None,
    scaffolds: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Load W8 cross-model episodes with dedup.

    Returns list of episode dicts with _model, _scaffold tags.
    """
    model_list = models or W8_MODELS
    scaffold_list = scaffolds or W8_SCAFFOLDS

    episodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    for model in model_list:
        for scaffold in scaffold_list:
            cell_dir = W8_RESULTS_DIR / f"{model}_{scaffold}"
            if not cell_dir.exists():
                print(f"  WARNING: Dir not found: {cell_dir}")
                continue

            for ep_file in sorted(cell_dir.glob("*.json")):
                if ep_file.name.startswith(("checkpoint", ".claim", "log_", "model_summary")):
                    continue
                try:
                    with open(ep_file) as f:
                        ep = json.load(f)
                    if not isinstance(ep, dict):
                        continue
                    sid = ep.get("scenario_id", "")
                    if not sid:
                        continue
                    run_idx = ep.get("run_index", 0)
                    key = f"{model}_{scaffold}_{sid}_{run_idx}"
                    if key in seen:
                        continue
                    seen.add(key)
                    ep["_model"] = model
                    ep["_scaffold"] = scaffold
                    episodes.append(ep)
                except Exception:
                    pass

    return episodes


def load_w8_verdicts(
    models: list[str] | None = None,
    scaffolds: list[str] | None = None,
    use_disk_cache: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load W8 episodes and compute verdicts."""
    cache_file = CACHE_DIR / "verdicts_w8.json"

    if use_disk_cache and cache_file.exists():
        try:
            with open(cache_file) as f:
                cached = json.load(f)
            if len(cached) > 5000:
                print(f"  Loaded {len(cached)} cached W8 verdicts from {cache_file}")
                episodes = [
                    {
                        "scenario_id": r["scenario_id"],
                        "run_index": r["run_index"],
                        "_model": r["model"],
                        "_scaffold": r.get("scaffold", ""),
                    }
                    for r in cached
                ]
                return episodes, cached
        except Exception:
            pass

    episodes = load_w8_episodes(models, scaffolds)
    print(f"  Loaded {len(episodes)} W8 episodes, scoring...")

    scored = []
    for ep in episodes:
        rec = score_episode(ep)
        rec["scaffold"] = ep.get("_scaffold", "")
        scored.append(rec)

    if use_disk_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(scored, f, indent=1, ensure_ascii=False, default=str)
        print(f"  Cached {len(scored)} W8 verdicts to {cache_file}")

    return episodes, scored


# ---------------------------------------------------------------------------
# Convenience: verdict summary stats
# ---------------------------------------------------------------------------


def verdict_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics from scored records."""
    n = len(records)
    if n == 0:
        return {"n": 0}

    ac_pass = sum(1 for r in records if r["ac_proxy"]) / n * 100
    mab_pass = sum(1 for r in records if r["mab_proxy"]) / n * 100
    c2_pass = sum(1 for r in records if r["c2_pass"]) / n * 100
    cga_pass = sum(1 for r in records if r["cga_pass"]) / n * 100
    flip_rate = sum(1 for r in records if r["verdict_flip"]) / n * 100
    ao_fa_rate = sum(1 for r in records if r["ao_fa"]) / n * 100

    n_hard = sum(1 for r in records if r["v4_hard"])
    pct_hard = n_hard / n * 100

    return {
        "n": n,
        "ac_pass_pct": round(ac_pass, 1),
        "mab_pass_pct": round(mab_pass, 1),
        "c2_pass_pct": round(c2_pass, 1),
        "cga_pass_pct": round(cga_pass, 1),
        "flip_rate_pct": round(flip_rate, 1),
        "ao_fa_rate_pct": round(ao_fa_rate, 1),
        "n_hard": n_hard,
        "pct_hard": round(pct_hard, 1),
    }
