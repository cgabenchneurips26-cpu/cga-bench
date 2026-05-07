#!/usr/bin/env python3
"""EX-D1: Projection Operator Ablation

Measures the marginal contribution of each of the 4 projection operators
(pi_term, pi_aset, pi_nctx, pi_ntim) to violation detection by sweeping
all 2^4 = 16 ProjectionConfig combinations over a stratified sample of
episodes from the V6 dataset.

For each config, "detected" means the episode has at least one violation
event of the given type recorded in the stored results.  When a projection
operator is disabled we simulate its absence by filtering the stored
violation_events according to the operator's semantic:

  pi_term  (apply_terminology) : gates SEQUENCE violations that rely on
           terminology normalisation.  Without it, sequence violations that
           only match via alias are no longer detected.  Approximated by
           masking sequence violations whose description contains "alias".
           Since the stored events don't carry that flag we use a
           conservative proxy: when disabled, SEQUENCE detection rate is
           reduced proportionally to the fraction of actions whose IDs
           required normalisation (estimated from actions list).

  pi_aset  (apply_action_set)  : gates DEVIATION violations.  Without
           domain detection, all actions look off-protocol → DEVIATION
           detection is trivially 1.0.  When disabled, we mask all
           DEVIATION violations (domain context absent ⇒ no deviation
           signal).

  pi_nctx  (apply_numeric_context) : gates the CPG_OVERSPECIFIC guard.
           When disabled, OMISSION violations from over-specific conditions
           are suppressed.  Proxy: mask OMISSION events that have
           "overspecific" or "modular" in their description, otherwise keep.

  pi_ntim  (apply_numeric_timing) : consumed-set 1:1 matching.
           When disabled, a single performed action can satisfy multiple
           mandatory requirements, reducing OMISSION count.  Proxy: when
           disabled, keep only the first OMISSION violation per episode
           (conservative lower-bound).

NOTE: This is a post-hoc replay analysis over stored episode results.
It does NOT re-run the full LLM inference pipeline.  The projection config
effects are approximated by filtering the stored violation_events — which
gives a faithful lower/upper bound on the true ablation because the stored
events were produced with all operators active (the full-config baseline).

Outputs:
  evidence_pack/ex_d1_projection_ablation/
    sweep_results.json      -- per-(config, episode, violation_type) rows
    shapley_values.json     -- per-operator Shapley values
    interaction_terms.json  -- pairwise interaction ΔΦ
    macros.tex              -- LaTeX macros

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_d1_projection_ablation.py \\
      --results-dir results/full_706_v5 \\
      --n-episodes 500 \\
      --output-dir evidence_pack/ex_d1_projection_ablation
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
import json
import logging
from pathlib import Path
import random
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT.parent))

from cga_bench.assessor_core.action_normalizer import ActionNormalizer  # noqa: E402
from cga_bench.assessor_core.projection_config import ProjectionConfig  # noqa: E402

logger = logging.getLogger(__name__)

# Shared normalizer instance (stateless, safe to reuse)
_NORMALIZER = ActionNormalizer()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIOLATION_TYPES = ["omission", "commission", "timing", "sequence", "deviation"]

OPERATORS = ["apply_terminology", "apply_action_set", "apply_numeric_context", "apply_numeric_timing"]

OPERATOR_SHORT = {
    "apply_terminology": "pi_term",
    "apply_action_set": "pi_aset",
    "apply_numeric_context": "pi_nctx",
    "apply_numeric_timing": "pi_ntim",
}

SEED = 42

# ---------------------------------------------------------------------------
# Episode loading
# ---------------------------------------------------------------------------


def _iter_episode_files(results_dir: Path) -> list[Path]:
    """Return all per-episode JSON files under results_dir/{model}/*.json."""
    files: list[Path] = []
    for model_dir in sorted(results_dir.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith((".", "_", "log")):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            files.append(ep_file)
    return files


def _load_episode(path: Path) -> dict[str, Any] | None:
    """Load a single episode JSON, returning None on parse failure."""
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict) or not data.get("scenario_id"):
            return None
        return data
    except Exception as exc:
        logger.debug("Failed to load %s: %s", path, exc)
        return None


def _domain_of(episode: dict[str, Any]) -> str:
    """Best-effort domain label from episode fields."""
    # Use stored domain if present
    if episode.get("domain"):
        return str(episode["domain"])
    # Infer from scenario_id prefix
    sid: str = episode.get("scenario_id", "")
    for prefix, domain in [
        ("aabb", "aabb_transfusion"),
        ("acls", "acls_cardiac_arrest"),
        ("aha_cp", "aha_chest_pain_evaluation"),
        ("stemi", "aha_chest_pain_evaluation"),
        ("nstemi", "aha_chest_pain_evaluation"),
        ("rv_trap", "aha_chest_pain_evaluation"),
        ("aha_hf", "aha_heart_failure_2022"),
        ("aha_stroke", "aha_stroke_2019"),
        ("aki", "kdigo_aki"),
        ("anaphylaxis", "anaphylaxis"),
        ("asthma", "asthma_exacerbation"),
        ("atrial", "atrial_fibrillation"),
        ("cap", "cap_pneumonia"),
        ("copd", "copd_exacerbation"),
        ("dka", "ada_dka_management"),
        ("gi_bleed", "gi_bleeding"),
        ("hypertensive", "hypertensive_emergency"),
        ("meningitis", "meningitis"),
        ("pe", "pulmonary_embolism"),
        ("sepsis", "ssc_sepsis_hour1_bundle"),
        ("septic", "ssc_sepsis_hour1_bundle"),
    ]:
        if sid.startswith(prefix):
            return domain
    return "general"


def _violation_types_present(episode: dict[str, Any]) -> set[str]:
    """Return the set of violation types that appear in a stored episode."""
    result: set[str] = set()
    for v in episode.get("violation_events") or []:
        vt = v.get("violation_type", "")
        if isinstance(vt, str) and vt:
            result.add(vt.lower())
    return result


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------


def _stratify_and_sample(
    episodes: list[dict[str, Any]],
    n: int,
    seed: int = SEED,
) -> list[dict[str, Any]]:
    """Return up to n episodes stratified by (domain, primary_violation_type).

    Stratification key = (domain, first-occurring violation type) or
    (domain, "none") for violation-free episodes.
    """
    rng = random.Random(seed)

    # Group by stratum
    strata: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for ep in episodes:
        domain = _domain_of(ep)
        vtypes = _violation_types_present(ep)
        primary_vtype = sorted(vtypes)[0] if vtypes else "none"
        strata[(domain, primary_vtype)].append(ep)

    # Proportional allocation
    total = len(episodes)
    sampled: list[dict[str, Any]] = []
    remainder: list[dict[str, Any]] = []

    for key, group in strata.items():
        alloc = max(1, round(n * len(group) / total))
        chosen = rng.sample(group, min(alloc, len(group)))
        sampled.extend(chosen)
        chosen_ids = {id(x) for x in chosen}
        remainder.extend(g for g in group if id(g) not in chosen_ids)

    # Trim or top-up
    if len(sampled) > n:
        sampled = rng.sample(sampled, n)
    elif len(sampled) < n and remainder:
        extra = rng.sample(remainder, min(n - len(sampled), len(remainder)))
        sampled.extend(extra)

    rng.shuffle(sampled)
    return sampled[:n]


# ---------------------------------------------------------------------------
# Projection operator simulation
# ---------------------------------------------------------------------------


def _action_normalisation_ratio(episode: dict[str, Any]) -> float:
    """Estimate the fraction of action IDs that would benefit from terminology
    normalisation.  Uses a heuristic: actions whose ID contains common
    non-canonical tokens (abbreviations, spaces, mixed case).
    """
    actions = episode.get("actions") or []
    if not actions:
        return 0.0
    needs_norm = 0
    for a in actions:
        aid = (a.get("action_id") or "").strip()
        if not aid:
            continue
        # Heuristics for IDs that require normalisation
        if (
            " " in aid
            or aid != aid.lower()
            or any(abbr in aid for abbr in ["tpa", "txa", "ns_", "lr_", "norepi", "levo"])
        ):
            needs_norm += 1
    return needs_norm / len(actions)


def _simulate_detection(
    episode: dict[str, Any],
    config: ProjectionConfig,
) -> dict[str, bool]:
    """Simulate per-violation-type detection under a given ProjectionConfig.

    Returns a dict mapping violation_type (lowercase) -> detected (bool).
    We start from the stored violation_events (produced under the full
    all-operators-active config) and apply operator-disabling filters.
    """
    stored_vtypes = _violation_types_present(episode)
    violation_events: list[dict[str, Any]] = list(episode.get("violation_events") or [])

    # Working set of violations after projection filtering
    active_violations: list[dict[str, Any]] = list(violation_events)

    # --- pi_aset disabled: mask DEVIATION violations ---
    # Without domain detection, we cannot know which actions are off-protocol,
    # so DEVIATION detection is lost (conservative: zero out deviation signal).
    if not config.apply_action_set:
        active_violations = [v for v in active_violations if v.get("violation_type", "").lower() != "deviation"]

    # --- pi_nctx disabled: mask OMISSION violations from over-specific guards ---
    # Proxy: mask OMISSION events whose description suggests CPG_OVERSPECIFIC
    # guard was responsible (contains "overspecific", "modular", or "CPG").
    if not config.apply_numeric_context:
        filtered: list[dict[str, Any]] = []
        for v in active_violations:
            vt = v.get("violation_type", "").lower()
            if vt == "omission":
                desc = (v.get("description") or "").lower()
                if any(kw in desc for kw in ["overspecific", "modular", "cpg_overspecific"]):
                    continue  # suppress this violation
            filtered.append(v)
        active_violations = filtered

    # --- pi_ntim disabled: consumed-set 1:1 matching disabled ---
    # Without the consumed set, one performed action can satisfy multiple
    # mandatory requirements.  Proxy: keep only the first OMISSION per episode.
    if not config.apply_numeric_timing:
        seen_omission = False
        filtered = []
        for v in active_violations:
            if v.get("violation_type", "").lower() == "omission":
                if seen_omission:
                    continue  # second+ OMISSION suppressed
                seen_omission = True
            filtered.append(v)
        active_violations = filtered

    # --- pi_term disabled: SEQUENCE violations that relied on alias matching ---
    # Proxy: when terminology normalisation is off, reduce sequence detection
    # probability proportional to the normalisation ratio of the episode's
    # action IDs.  Use a deterministic threshold (SEED-derived per episode)
    # rather than stochastic to ensure reproducibility.
    if not config.apply_terminology:
        norm_ratio = _action_normalisation_ratio(episode)
        filtered = []
        for v in active_violations:
            if v.get("violation_type", "").lower() == "sequence":
                # Suppress this sequence violation if the normalisation ratio
                # exceeds 0.5 (most IDs in this episode needed normalisation).
                if norm_ratio > 0.5:
                    continue
            filtered.append(v)
        active_violations = filtered

    # Build detection dict from surviving violations
    surviving_types: set[str] = {
        v.get("violation_type", "").lower() for v in active_violations if v.get("violation_type")
    }

    return {vt: (vt in surviving_types) for vt in VIOLATION_TYPES}


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------


def run_sweep(
    episodes: list[dict[str, Any]],
    configs: list[ProjectionConfig],
) -> list[dict[str, Any]]:
    """Run the 16-config × N-episode sweep.

    Returns a list of row dicts:
      {config_id, episode_id, scenario_id, domain, violation_type, detected}
    """
    rows: list[dict[str, Any]] = []

    for ep in episodes:
        ep_id = _episode_id(ep)
        domain = _domain_of(ep)
        for cfg in configs:
            detection = _simulate_detection(ep, cfg)
            for vtype, detected in detection.items():
                rows.append(
                    {
                        "config_id": cfg.config_id,
                        "episode_id": ep_id,
                        "scenario_id": ep.get("scenario_id", ""),
                        "domain": domain,
                        "violation_type": vtype,
                        "detected": detected,
                    }
                )

    return rows


def _episode_id(ep: dict[str, Any]) -> str:
    """Stable episode identifier from scenario_id + run_index."""
    sid = ep.get("scenario_id", "unknown")
    run = ep.get("run_index", ep.get("run_id", 0))
    model = ep.get("model_name", ep.get("agent_id", "unknown"))
    return f"{sid}__{model}__r{run}"


# ---------------------------------------------------------------------------
# Detection-rate helper
# ---------------------------------------------------------------------------


def _detection_rate(
    rows: list[dict[str, Any]],
    config_id: str,
    violation_type: str | None = None,
) -> float:
    """Fraction of episodes where at least one violation is detected under config."""
    # Group rows by (config_id, episode_id)
    per_episode: dict[str, bool] = {}
    for row in rows:
        if row["config_id"] != config_id:
            continue
        if violation_type is not None and row["violation_type"] != violation_type:
            continue
        eid = row["episode_id"]
        per_episode[eid] = per_episode.get(eid, False) or row["detected"]

    if not per_episode:
        return 0.0
    return sum(per_episode.values()) / len(per_episode)


def _config_from_id(config_id: str, configs: list[ProjectionConfig]) -> ProjectionConfig | None:
    """Look up a ProjectionConfig by its config_id string."""
    for c in configs:
        if c.config_id == config_id:
            return c
    return None


def _subset_config_id(operator_subset: frozenset[str]) -> str:
    """Return the config_id string for a subset of active operators.

    Operators not in the subset are disabled (False).
    """
    t = "apply_terminology" in operator_subset
    a = "apply_action_set" in operator_subset
    c = "apply_numeric_context" in operator_subset
    n = "apply_numeric_timing" in operator_subset
    cfg = ProjectionConfig(
        apply_terminology=t,
        apply_action_set=a,
        apply_numeric_context=c,
        apply_numeric_timing=n,
    )
    return cfg.config_id


# ---------------------------------------------------------------------------
# Shapley value computation
# ---------------------------------------------------------------------------


def compute_shapley_values(
    rows: list[dict[str, Any]],
    configs: list[ProjectionConfig],
) -> dict[str, dict[str, float]]:
    """Compute per-operator Shapley values overall and per-violation-type.

    Shapley(pi_x) = (1/4) * Σ_{S ⊆ {others}} [C(|S|,3)]^{-1} *
                    [v(S ∪ {pi_x}) - v(S)]

    where v(S) = detection_rate under the config with exactly the operators
    in S active, and the sum is over all 2^3 = 8 subsets of the other 3.

    Returns: {operator_name: {violation_type|"overall": shapley_value}}
    """
    shapley: dict[str, dict[str, float]] = {op: {} for op in OPERATORS}
    all_vtypes = VIOLATION_TYPES + ["overall"]

    for op in OPERATORS:
        others = [o for o in OPERATORS if o != op]
        for vtype_key in all_vtypes:
            vt = None if vtype_key == "overall" else vtype_key
            total_contrib = 0.0
            # Enumerate all 2^3 = 8 subsets of the other 3 operators
            for r in range(len(others) + 1):
                for subset in _subsets_of_size(others, r):
                    s_set = frozenset(subset)
                    s_plus_x = s_set | {op}
                    # detection rate for S
                    cid_s = _subset_config_id(s_set)
                    cid_sx = _subset_config_id(s_plus_x)
                    dr_s = _detection_rate(rows, cid_s, vt)
                    dr_sx = _detection_rate(rows, cid_sx, vt)
                    marginal = dr_sx - dr_s
                    # Shapley weight: |S|! * (n-|S|-1)! / n!  with n=4
                    # = (r! * (4-r-1)!) / 4!
                    weight = _shapley_weight(r, total_operators=4)
                    total_contrib += weight * marginal
            shapley[op][vtype_key] = round(total_contrib, 6)

    return shapley


def _subsets_of_size(elements: list[str], size: int) -> list[list[str]]:
    """Return all subsets of `elements` with exactly `size` elements."""
    if size == 0:
        return [[]]
    return [list(c) for c in combinations(elements, size)]


def _shapley_weight(subset_size: int, total_operators: int) -> float:
    """Shapley weight for a subset of size subset_size with total_operators operators.

    weight = |S|! * (n - |S| - 1)! / n!
    """
    import math

    n = total_operators
    r = subset_size
    return math.factorial(r) * math.factorial(n - r - 1) / math.factorial(n)


# ---------------------------------------------------------------------------
# Interaction terms
# ---------------------------------------------------------------------------


def compute_interaction_terms(
    rows: list[dict[str, Any]],
    configs: list[ProjectionConfig],
) -> dict[str, dict[str, float]]:
    """Compute pairwise interaction terms for all operator pairs.

    Interaction(pi_x, pi_y) = v({pi_x, pi_y}) - v({pi_x}) - v({pi_y}) + v({})

    Returns: {"{op_x}&{op_y}": {violation_type|"overall": interaction_value}}
    """
    interaction: dict[str, dict[str, float]] = {}

    for op_x, op_y in combinations(OPERATORS, 2):
        key = f"{OPERATOR_SHORT[op_x]}&{OPERATOR_SHORT[op_y]}"
        interaction[key] = {}

        for vtype_key in VIOLATION_TYPES + ["overall"]:
            vt = None if vtype_key == "overall" else vtype_key

            cid_empty = _subset_config_id(frozenset())
            cid_x = _subset_config_id(frozenset({op_x}))
            cid_y = _subset_config_id(frozenset({op_y}))
            cid_xy = _subset_config_id(frozenset({op_x, op_y}))

            v_empty = _detection_rate(rows, cid_empty, vt)
            v_x = _detection_rate(rows, cid_x, vt)
            v_y = _detection_rate(rows, cid_y, vt)
            v_xy = _detection_rate(rows, cid_xy, vt)

            delta = v_xy - v_x - v_y + v_empty
            interaction[key][vtype_key] = round(delta, 6)

    return interaction


# ---------------------------------------------------------------------------
# LaTeX macros
# ---------------------------------------------------------------------------


def write_latex_macros(
    shapley: dict[str, dict[str, float]],
    interaction: dict[str, dict[str, float]],
    rows: list[dict[str, Any]],
    configs: list[ProjectionConfig],
    output_path: Path,
) -> None:
    """Write LaTeX newcommand macros for the paper."""
    lines: list[str] = [
        "% EX-D1 Projection Operator Ablation — auto-generated macros",
        "% DO NOT EDIT — regenerate with exp_d1_projection_ablation.py",
        "",
    ]

    # Full config detection rate (all operators on)
    full_cid = ProjectionConfig(True, True, True, True).config_id
    full_dr = _detection_rate(rows, full_cid)
    lines.append(f"\\newcommand{{\\exDoneFullDetectionRate}}{{{full_dr:.3f}}}")

    # Null config detection rate (all operators off)
    null_cid = ProjectionConfig(False, False, False, False).config_id
    null_dr = _detection_rate(rows, null_cid)
    lines.append(f"\\newcommand{{\\exDoneNullDetectionRate}}{{{null_dr:.3f}}}")
    lines.append("")

    # Per-operator Shapley values (overall)
    op_latex_names = {
        "apply_terminology": "PiTerm",
        "apply_action_set": "PiAset",
        "apply_numeric_context": "PiNctx",
        "apply_numeric_timing": "PiNtim",
    }
    for op, latex_name in op_latex_names.items():
        sv = shapley.get(op, {}).get("overall", 0.0)
        lines.append(f"\\newcommand{{\\shapley{latex_name}}}{{{sv:.4f}}}")

    lines.append("")

    # Largest interaction term
    best_pair = max(interaction, key=lambda k: abs(interaction[k].get("overall", 0.0)))
    best_val = interaction[best_pair]["overall"]
    # Sanitise pair name for LaTeX macro (replace & and _)
    pair_macro = best_pair.replace("&", "And").replace("_", "")
    lines.append(f"\\newcommand{{\\exDoneLargestInteractionPair}}{{{best_pair}}}")
    lines.append(f"\\newcommand{{\\exDoneLargestInteractionVal}}{{{best_val:.4f}}}")
    lines.append("")

    # N episodes
    n_eps = len({row["episode_id"] for row in rows})
    lines.append(f"\\newcommand{{\\exDoneNEpisodes}}{{{n_eps}}}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Saved macros: %s", output_path)


# ---------------------------------------------------------------------------
# Summary table printer
# ---------------------------------------------------------------------------


def print_summary_table(
    shapley: dict[str, dict[str, float]],
    rows: list[dict[str, Any]],
    configs: list[ProjectionConfig],
) -> None:
    """Print a summary of Shapley values and per-config detection rates."""
    print("\n" + "=" * 70)
    print("EX-D1: PROJECTION OPERATOR ABLATION — RESULTS SUMMARY")
    print("=" * 70)

    # Per-config detection rate (overall)
    print("\n--- Detection Rate by Config (overall) ---")
    print(f"{'Config':<20} {'Detection Rate':>16}")
    print("-" * 38)
    for cfg in sorted(configs, key=lambda c: c.config_id):
        dr = _detection_rate(rows, cfg.config_id)
        markers = []
        if cfg == ProjectionConfig(True, True, True, True):
            markers.append("← FULL")
        if cfg == ProjectionConfig(False, False, False, False):
            markers.append("← NULL")
        print(f"{cfg.config_id:<20} {dr:>16.4f}  {'  '.join(markers)}")

    print("\n--- Shapley Values (overall) ---")
    print(f"{'Operator':<30} {'Short':<10} {'Shapley':>10}")
    print("-" * 52)
    for op in OPERATORS:
        sv = shapley[op].get("overall", 0.0)
        print(f"{op:<30} {OPERATOR_SHORT[op]:<10} {sv:>10.4f}")

    print("\n--- Shapley Values by Violation Type ---")
    header = f"{'Operator':<16}" + "".join(f"{vt[:7]:>9}" for vt in VIOLATION_TYPES)
    print(header)
    print("-" * (16 + 9 * len(VIOLATION_TYPES)))
    for op in OPERATORS:
        row_str = f"{OPERATOR_SHORT[op]:<16}" + "".join(f"{shapley[op].get(vt, 0.0):>9.4f}" for vt in VIOLATION_TYPES)
        print(row_str)

    print("=" * 70)


# ---------------------------------------------------------------------------
# Re-scoring approach (proper action matching, not proxy-based)
# ---------------------------------------------------------------------------


def _action_matches(performed_id: str, required_id: str, use_norm: bool) -> bool:
    """Check whether a performed action satisfies a required action.

    When use_norm=True, both IDs are normalised via ActionNormalizer before
    comparison (emulating pi_term ON).  When False, only exact string match.
    """
    if performed_id == required_id:
        return True
    if not use_norm:
        return False
    # Normalise both sides
    norm_p = _NORMALIZER.normalize(performed_id)
    norm_r = _NORMALIZER.normalize(required_id)
    return norm_p == norm_r


def _count_omissions(
    performed: list[str],
    expected: list[str],
    use_norm: bool,
    use_consumed: bool,
) -> int:
    """Count unmatched mandatory actions.

    Args:
        performed: List of performed action IDs.
        expected: List of mandatory action IDs.
        use_norm: If True, normalise both sides (pi_term ON).
        use_consumed: If True, 1:1 matching via consumed set (pi_ntim ON).
                      If False, 1:N matching (same action can satisfy multiple).
    """
    if use_consumed:
        consumed_indices: set[int] = set()
        matched = 0
        for req in expected:
            for i, act in enumerate(performed):
                if i in consumed_indices:
                    continue
                if _action_matches(act, req, use_norm):
                    consumed_indices.add(i)
                    matched += 1
                    break
    else:
        # 1:N — each requirement independently checks all performed
        matched = sum(1 for req in expected if any(_action_matches(act, req, use_norm) for act in performed))
    return len(expected) - matched


def _count_commissions(
    performed: list[str],
    forbidden: list[str],
    use_norm: bool,
) -> int:
    """Count performed actions that match forbidden actions."""
    count = 0
    for act in performed:
        for fb in forbidden:
            if _action_matches(act, fb, use_norm):
                count += 1
                break  # count each performed action at most once
    return count


def _rescore_episode(
    episode: dict[str, Any],
    config: ProjectionConfig,
) -> dict[str, Any]:
    """Re-compute violation counts from stored actions/expected/forbidden.

    This is the proper re-scoring approach: instead of filtering stored
    violation events, we redo the action-requirement matching under each
    ProjectionConfig setting.

    Returns dict with per-type counts and simulated CGA score.
    """
    performed = [a.get("action_id", "") for a in (episode.get("actions") or [])]
    expected = episode.get("expected_actions") or []
    forbidden = episode.get("forbidden_actions") or []

    use_norm = config.apply_terminology
    use_consumed = config.apply_numeric_timing

    # OMISSION: expected not matched by performed
    omissions = _count_omissions(performed, expected, use_norm, use_consumed)

    # COMMISSION: performed matches forbidden
    commissions = _count_commissions(performed, forbidden, use_norm)

    # DEVIATION: from stored count, toggled by pi_aset
    # Without domain detection, deviation signal is lost
    stored_dev = (episode.get("violations_by_type") or {}).get("deviation", 0)
    deviations = stored_dev if config.apply_action_set else 0

    # TIMING / SEQUENCE: from stored (these are temporal, not affected by matching)
    timing = (episode.get("violations_by_type") or {}).get("timing", 0)
    sequence = (episode.get("violations_by_type") or {}).get("sequence", 0)

    total = omissions + commissions + deviations + timing + sequence

    # CGA score: 1 - n_violations / max(n_actions, n_expected, 1)
    n_actions = len(performed)
    n_expected = len(expected)
    denom = max(n_actions, n_expected, 1)
    cga = max(0.0, min(1.0, 1.0 - total / denom))

    return {
        "omission": omissions,
        "commission": commissions,
        "deviation": deviations,
        "timing": timing,
        "sequence": sequence,
        "total_violations": total,
        "cga_score": cga,
    }


def run_rescore_sweep(
    episodes: list[dict[str, Any]],
    configs: list[ProjectionConfig],
) -> list[dict[str, Any]]:
    """Run the 16-config × N-episode re-scoring sweep.

    Returns rows with per-type violation counts and CGA scores.
    """
    rows: list[dict[str, Any]] = []
    for ep in episodes:
        ep_id = _episode_id(ep)
        domain = _domain_of(ep)
        for cfg in configs:
            scores = _rescore_episode(ep, cfg)
            rows.append(
                {
                    "config_id": cfg.config_id,
                    "episode_id": ep_id,
                    "scenario_id": ep.get("scenario_id", ""),
                    "domain": domain,
                    **scores,
                }
            )
    return rows


def _mean_metric(
    rows: list[dict[str, Any]],
    config_id: str,
    metric: str = "cga_score",
) -> float:
    """Compute mean of a continuous metric for a given config."""
    vals = [r[metric] for r in rows if r["config_id"] == config_id]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def compute_shapley_continuous(
    rows: list[dict[str, Any]],
    configs: list[ProjectionConfig],
    metric: str = "cga_score",
) -> dict[str, float]:
    """Compute per-operator Shapley values on a continuous metric (e.g. CGA score).

    Returns: {operator_name: shapley_value}
    """
    shapley: dict[str, float] = {}

    for op in OPERATORS:
        others = [o for o in OPERATORS if o != op]
        total_contrib = 0.0
        for r in range(len(others) + 1):
            for subset in _subsets_of_size(others, r):
                s_set = frozenset(subset)
                s_plus_x = s_set | {op}
                cid_s = _subset_config_id(s_set)
                cid_sx = _subset_config_id(s_plus_x)
                v_s = _mean_metric(rows, cid_s, metric)
                v_sx = _mean_metric(rows, cid_sx, metric)
                marginal = v_sx - v_s
                weight = _shapley_weight(r, total_operators=4)
                total_contrib += weight * marginal
        shapley[op] = round(total_contrib, 6)

    return shapley


def print_rescore_summary(
    rescore_rows: list[dict[str, Any]],
    shapley_cga: dict[str, float],
    shapley_viol: dict[str, float],
    configs: list[ProjectionConfig],
) -> None:
    """Print summary of re-scoring analysis."""
    print("\n" + "=" * 70)
    print("EX-D1: RE-SCORING ANALYSIS (proper action matching)")
    print("=" * 70)

    print("\n--- Mean CGA Score by Config ---")
    print(f"{'Config':<20} {'CGA Score':>12} {'Violations':>12}")
    print("-" * 46)
    for cfg in sorted(configs, key=lambda c: c.config_id):
        cga = _mean_metric(rescore_rows, cfg.config_id, "cga_score")
        viol = _mean_metric(rescore_rows, cfg.config_id, "total_violations")
        markers = []
        if cfg == ProjectionConfig(True, True, True, True):
            markers.append("FULL")
        if cfg == ProjectionConfig(False, False, False, False):
            markers.append("NULL")
        m = f"  <- {' '.join(markers)}" if markers else ""
        print(f"{cfg.config_id:<20} {cga:>12.4f} {viol:>12.2f}{m}")

    print("\n--- Shapley Values (CGA Score) ---")
    print(f"{'Operator':<30} {'Short':<10} {'Shapley':>10}")
    print("-" * 52)
    for op in OPERATORS:
        print(f"{op:<30} {OPERATOR_SHORT[op]:<10} {shapley_cga[op]:>10.4f}")

    print("\n--- Shapley Values (Violation Count, negative = reduces violations) ---")
    print(f"{'Operator':<30} {'Short':<10} {'Shapley':>10}")
    print("-" * 52)
    for op in OPERATORS:
        print(f"{op:<30} {OPERATOR_SHORT[op]:<10} {shapley_viol[op]:>10.4f}")

    # Efficiency ratio (sum of |Shapley| / total gap)
    full_cga = _mean_metric(rescore_rows, ProjectionConfig(True, True, True, True).config_id, "cga_score")
    null_cga = _mean_metric(rescore_rows, ProjectionConfig(False, False, False, False).config_id, "cga_score")
    gap = full_cga - null_cga
    shapley_sum = sum(shapley_cga.values())
    print(f"\nFull CGA: {full_cga:.4f}, Null CGA: {null_cga:.4f}, Gap: {gap:.4f}")
    print(f"Sum of Shapley (CGA): {shapley_sum:.4f} (should ≈ gap)")

    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EX-D1: Projection Operator Ablation over V6 episode results")
    parser.add_argument(
        "--results-dir",
        default="results/full_706_v5",
        help="Root directory containing per-model episode JSON files (default: results/full_706_v5)",
    )
    parser.add_argument(
        "--n-episodes",
        type=int,
        default=500,
        help="Number of episodes to sample (stratified, default: 500)",
    )
    parser.add_argument(
        "--output-dir",
        default="evidence_pack/ex_d1_projection_ablation",
        help="Output directory for results (default: evidence_pack/ex_d1_projection_ablation)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help="Random seed for stratified sampling (default: 42)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    results_dir = REPO_ROOT / args.results_dir
    output_dir = REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("EX-D1 Projection Operator Ablation")
    logger.info("  results_dir : %s", results_dir)
    logger.info("  n_episodes  : %d", args.n_episodes)
    logger.info("  output_dir  : %s", output_dir)
    logger.info("  seed        : %d", args.seed)

    # -----------------------------------------------------------------
    # 1. Load all episode files
    # -----------------------------------------------------------------
    logger.info("Scanning episode files...")
    ep_files = _iter_episode_files(results_dir)
    logger.info("  Found %d files", len(ep_files))

    all_episodes: list[dict[str, Any]] = []
    for fp in ep_files:
        ep = _load_episode(fp)
        if ep is not None:
            all_episodes.append(ep)
    logger.info("  Loaded %d valid episodes", len(all_episodes))

    if not all_episodes:
        logger.error("No episodes found under %s — aborting", results_dir)
        sys.exit(1)

    # -----------------------------------------------------------------
    # 2. Stratified sample
    # -----------------------------------------------------------------
    logger.info("Stratified sampling %d episodes...", args.n_episodes)
    episodes = _stratify_and_sample(all_episodes, args.n_episodes, seed=args.seed)
    logger.info("  Sampled %d episodes", len(episodes))

    # Summarise stratum coverage
    domains = {_domain_of(ep) for ep in episodes}
    logger.info("  Domains covered: %d (%s)", len(domains), ", ".join(sorted(domains)[:6]) + "...")

    vtypes_seen: set[str] = set()
    for ep in episodes:
        vtypes_seen |= _violation_types_present(ep)
    logger.info("  Violation types present: %s", sorted(vtypes_seen))

    # -----------------------------------------------------------------
    # 3. Build 16 ProjectionConfigs
    # -----------------------------------------------------------------
    configs = ProjectionConfig.all_configs()
    logger.info("Sweeping %d projection configs × %d episodes...", len(configs), len(episodes))

    # -----------------------------------------------------------------
    # 4. Run sweep
    # -----------------------------------------------------------------
    rows = run_sweep(episodes, configs)
    logger.info("  Generated %d (config, episode, violation_type) rows", len(rows))

    # -----------------------------------------------------------------
    # 5. Compute Shapley values
    # -----------------------------------------------------------------
    logger.info("Computing Shapley values...")
    shapley = compute_shapley_values(rows, configs)

    # -----------------------------------------------------------------
    # 6. Compute interaction terms
    # -----------------------------------------------------------------
    logger.info("Computing pairwise interaction terms...")
    interaction = compute_interaction_terms(rows, configs)

    # -----------------------------------------------------------------
    # 7. Print summary
    # -----------------------------------------------------------------
    print_summary_table(shapley, rows, configs)

    # -----------------------------------------------------------------
    # 8. Save outputs
    # -----------------------------------------------------------------
    logger.info("Saving outputs to %s", output_dir)

    # sweep_results.json
    sweep_path = output_dir / "sweep_results.json"
    with open(sweep_path, "w") as f:
        json.dump(
            {
                "meta": {
                    "n_episodes": len(episodes),
                    "n_configs": len(configs),
                    "seed": args.seed,
                    "results_dir": str(args.results_dir),
                    "operators": OPERATORS,
                    "violation_types": VIOLATION_TYPES,
                },
                "rows": rows,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info("  Saved: %s", sweep_path)

    # shapley_values.json
    shapley_path = output_dir / "shapley_values.json"
    with open(shapley_path, "w") as f:
        json.dump(
            {
                "meta": {
                    "method": "exact_shapley_4_operators",
                    "n_episodes": len(episodes),
                    "description": (
                        "Shapley value = average marginal contribution of each operator "
                        "over all 2^3 subsets of the other 3 operators"
                    ),
                },
                "shapley_values": {OPERATOR_SHORT[op]: shapley[op] for op in OPERATORS},
                "shapley_values_raw": shapley,
            },
            f,
            indent=2,
        )
    logger.info("  Saved: %s", shapley_path)

    # interaction_terms.json
    interaction_path = output_dir / "interaction_terms.json"
    with open(interaction_path, "w") as f:
        json.dump(
            {
                "meta": {
                    "method": "pairwise_interaction_delta",
                    "formula": "v({pi_x, pi_y}) - v({pi_x}) - v({pi_y}) + v({})",
                    "n_episodes": len(episodes),
                },
                "interaction_terms": interaction,
            },
            f,
            indent=2,
        )
    logger.info("  Saved: %s", interaction_path)

    # macros.tex (detection-based, will be updated below with rescore)
    macros_path = output_dir / "macros.tex"
    write_latex_macros(shapley, interaction, rows, configs, macros_path)

    # -----------------------------------------------------------------
    # 9. Re-scoring analysis (proper action matching)
    # -----------------------------------------------------------------
    logger.info("Running re-scoring sweep (proper action matching)...")
    rescore_rows = run_rescore_sweep(episodes, configs)
    logger.info("  Generated %d rescore rows", len(rescore_rows))

    # Shapley on CGA score (continuous)
    logger.info("Computing Shapley values on CGA score...")
    shapley_cga = compute_shapley_continuous(rescore_rows, configs, "cga_score")

    # Shapley on violation count (continuous, negative = reduces violations)
    shapley_viol = compute_shapley_continuous(rescore_rows, configs, "total_violations")

    # Print rescore summary
    print_rescore_summary(rescore_rows, shapley_cga, shapley_viol, configs)

    # -----------------------------------------------------------------
    # 10. Save rescore outputs
    # -----------------------------------------------------------------
    rescore_path = output_dir / "rescore_results.json"
    with open(rescore_path, "w") as f:
        json.dump(
            {
                "meta": {
                    "method": "proper_action_matching_rescore",
                    "n_episodes": len(episodes),
                    "description": (
                        "Re-scoring with ActionNormalizer: violation counts and CGA scores "
                        "computed from stored actions/expected/forbidden under each config"
                    ),
                },
                "rows": rescore_rows,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info("  Saved: %s", rescore_path)

    # Updated shapley with both detection and CGA metrics
    shapley_combined_path = output_dir / "shapley_values.json"
    with open(shapley_combined_path, "w") as f:
        json.dump(
            {
                "meta": {
                    "method": "exact_shapley_4_operators",
                    "n_episodes": len(episodes),
                    "description": (
                        "Shapley values computed on two metrics: "
                        "(1) binary detection rate (proxy-based), "
                        "(2) CGA score (proper action-matching rescore)"
                    ),
                },
                "shapley_detection": {OPERATOR_SHORT[op]: shapley[op] for op in OPERATORS},
                "shapley_cga_score": {OPERATOR_SHORT[op]: shapley_cga[op] for op in OPERATORS},
                "shapley_violation_count": {OPERATOR_SHORT[op]: shapley_viol[op] for op in OPERATORS},
                "shapley_detection_raw": shapley,
            },
            f,
            indent=2,
        )
    logger.info("  Saved: %s", shapley_combined_path)

    # Updated macros with rescore Shapley values
    full_cga = _mean_metric(rescore_rows, ProjectionConfig(True, True, True, True).config_id, "cga_score")
    null_cga = _mean_metric(rescore_rows, ProjectionConfig(False, False, False, False).config_id, "cga_score")
    full_viol = _mean_metric(rescore_rows, ProjectionConfig(True, True, True, True).config_id, "total_violations")
    null_viol = _mean_metric(rescore_rows, ProjectionConfig(False, False, False, False).config_id, "total_violations")

    # Append rescore macros to existing macros file
    rescore_macros = [
        "",
        "% --- Re-scoring analysis (proper action matching) ---",
        f"\\newcommand{{\\exDoneFullCGA}}{{{full_cga:.4f}}}",
        f"\\newcommand{{\\exDoneNullCGA}}{{{null_cga:.4f}}}",
        f"\\newcommand{{\\exDoneCGAGap}}{{{full_cga - null_cga:.4f}}}",
        f"\\newcommand{{\\exDoneFullViol}}{{{full_viol:.2f}}}",
        f"\\newcommand{{\\exDoneNullViol}}{{{null_viol:.2f}}}",
        f"\\newcommand{{\\shapleyCGAPiTerm}}{{{shapley_cga.get('apply_terminology', 0.0):.4f}}}",
        f"\\newcommand{{\\shapleyCGAPiAset}}{{{shapley_cga.get('apply_action_set', 0.0):.4f}}}",
        f"\\newcommand{{\\shapleyCGAPiNctx}}{{{shapley_cga.get('apply_numeric_context', 0.0):.4f}}}",
        f"\\newcommand{{\\shapleyCGAPiNtim}}{{{shapley_cga.get('apply_numeric_timing', 0.0):.4f}}}",
    ]
    with open(macros_path, "a") as f:
        f.write("\n".join(rescore_macros) + "\n")
    logger.info("  Updated macros: %s", macros_path)

    logger.info("EX-D1 complete.")


if __name__ == "__main__":
    main()
