#!/usr/bin/env python3
"""F2 — Node-level authority spot-check.

Sanity-checks the E9 limitation that node-level authority might over-promote
edge-level (rule-level) low-authority recommendations. Stratify-samples 60 of
the 1,124 strict-FA episodes and dumps, for each, the responsible hard
violation event together with its node-level *and* rule-level authority. A
"promotion" case is one where the **node** is high-authority but the
**triggered conditional_rule** has its own lower class/LOE override.

Output:
  evidence_pack/analysis/exp_e9_node_authority_spotcheck.csv
  evidence_pack/analysis/exp_e9_node_authority_spotcheck.md

Manual review pass: read the MD, count promotion rows. The agreed appendix
sentence (post-review) reports the count.

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (§5.2)
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cpg_model.constraint_derivation import _classify_authority  # noqa: E402

from scripts.experiments.exp_e39_high_authority_core import (  # noqa: E402
    ANALYSIS_DIR,
    GRAPHS_DIR,
    HARD_VIOLATION_TYPES,
    RESULTS_DIRS_DEFAULT,
    VERDICT_MATRIX_PATH,
    build_episode_index,
    build_node_authority_map,
    build_scenario_to_graph_map,
)

# Re-use the domain-extraction prefix table already used by audit/metrics/blindspot.
_DOMAIN_PREFIXES: dict[str, str] = {
    "septic_shock": "sepsis",
    "sepsis": "sepsis",
    "stemi": "chest_pain",
    "nstemi": "chest_pain",
    "chest_pain": "chest_pain",
    "acs": "chest_pain",
    "stroke": "stroke",
    "tpa": "stroke",
    "hfref": "heart_failure",
    "adhf": "heart_failure",
    "aki": "aki",
    "contrast_aki": "aki",
    "dka": "dka",
    "af_": "atrial_fibrillation",
    "copd": "copd",
    "pe_": "pulmonary_embolism",
    "gi_bleed": "gi_bleeding",
    "cap_": "pneumonia",
    "hypertensive": "hypertensive_emergency",
    "anaphylaxis": "anaphylaxis",
    "asthma": "asthma",
    "meningitis": "meningitis",
    "acls": "acls",
    "status_epilepticus": "epilepticus",
    "toxicology": "toxicology",
    "aabb": "transfusion",
    "aabb_t": "transfusion",
    "aba_burn": "burn",
    "acog": "obstetric",
    "apa_agitation": "agitation",
    "pals": "pediatric",
}

VIOLATION_PRIORITY = {"commission": 0, "sequence": 1, "timing": 2}


def extract_domain(scenario_id: str) -> str:
    s = scenario_id.lower()
    for prefix, dom in _DOMAIN_PREFIXES.items():
        if s.startswith(prefix):
            return dom
    return "other"


# =====================================================================
# Strict-FA filter
# =====================================================================
def find_strict_fa_episodes(verdict_matrix: dict) -> list[dict]:
    """Return per_episode rows that are strict-3-way false accepts."""
    out: list[dict] = []
    for ep in verdict_matrix.get("per_episode", []) or []:
        # ASC ∩ CwT ∩ PAF pass + TCC fail
        # cached v4_hard True == FAIL in this corpus
        if (
            ep.get("ac_proxy") is True
            and ep.get("c2_pass") is True
            and ep.get("mab_proxy") is True
            and ep.get("v4_hard") is True
        ):
            out.append(ep)
    return out


# =====================================================================
# Stratified sampling
# =====================================================================
def primary_violation_type(viol_types: list | str | None) -> str:
    """Mirrors audit.metrics.blindspot.primary_constraint_type but for raw v_types."""
    if not viol_types:
        return "NONE"
    if isinstance(viol_types, str):
        types = [t.strip() for t in viol_types.split(",") if t.strip()]
    else:
        types = list(viol_types)
    if not types:
        return "NONE"
    priority = {"FORBIDDEN": 0, "WITHIN": 1, "BEFORE": 2}
    best = "NONE"
    best_prio = 999
    for t in types:
        t_upper = t.upper()
        prio = priority.get(t_upper, 998)
        if prio < best_prio:
            best_prio = prio
            best = t_upper
    return best


def stratified_sample(
    episodes: list[dict], n: int, seed: int = 42
) -> list[dict]:
    """Stratify across (model_dir, domain, primary_viol_type), draw round-robin."""
    rng = random.Random(seed)
    buckets: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for ep in episodes:
        key = (
            ep.get("model_dir") or "unknown",
            extract_domain(ep.get("scenario_id", "")),
            primary_violation_type(ep.get("viol_types")),
        )
        buckets[key].append(ep)
    for v in buckets.values():
        rng.shuffle(v)

    bucket_iter = list(buckets.values())
    rng.shuffle(bucket_iter)

    sampled: list[dict] = []
    while len(sampled) < n and any(bucket_iter):
        next_round = []
        for b in bucket_iter:
            if not b:
                continue
            sampled.append(b.pop())
            if b:
                next_round.append(b)
            if len(sampled) >= n:
                break
        bucket_iter = next_round
    return sampled[:n]


# =====================================================================
# Per-episode rule-level lookup
# =====================================================================
def _node_block_for(graph_yaml: dict, node_id: str) -> dict | None:
    nodes = graph_yaml.get("nodes") or {}
    if isinstance(nodes, dict):
        return nodes.get(node_id)
    return None


def _find_responsible_rule(
    node: dict, action_involved: str
) -> dict | None:
    """Return the conditional_rule whose effect.actions contains the violated action.

    Falls back to ``None`` if no matching rule (e.g. unconditional forbidden /
    sequence rule). The caller treats that as "node-level only".
    """
    if not isinstance(node, dict):
        return None
    rules = node.get("conditional_rules") or []
    if not isinstance(rules, list):
        return None
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        effect = rule.get("effect") or {}
        actions = effect.get("actions") or []
        if action_involved in actions:
            return rule
    return None


def _pick_responsible_violation(violation_events: list[dict]) -> dict | None:
    """Pick one hard violation in priority commission > sequence > timing."""
    hard = [
        v for v in violation_events
        if (v.get("violation_type") or "").lower() in HARD_VIOLATION_TYPES
    ]
    if not hard:
        return None
    hard.sort(
        key=lambda v: VIOLATION_PRIORITY.get(
            (v.get("violation_type") or "").lower(), 99
        )
    )
    return hard[0]


def inspect_episode(
    ep: dict,
    raw_path: Path,
    scenario_to_graph: dict,
    graph_cache: dict[str, dict],
) -> dict | None:
    """Open raw JSON, find responsible violation, return spot-check row."""
    try:
        with open(raw_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    events = data.get("violation_events") or []
    chosen = _pick_responsible_violation(events)
    if chosen is None:
        return None

    sid = ep.get("scenario_id", "")
    graph_id = scenario_to_graph.get(sid)
    if graph_id is None:
        return None

    # Cache the loaded graph YAML to avoid re-parsing the same file
    if graph_id not in graph_cache:
        candidate_paths = [
            GRAPHS_DIR / f"{graph_id}.yaml",
            *GRAPHS_DIR.rglob(f"{graph_id}.yaml"),
        ]
        graph_yaml = {}
        for p in candidate_paths:
            if p.exists():
                with open(p) as f:
                    loaded = yaml.safe_load(f) or {}
                if isinstance(loaded, dict):
                    graph_yaml = loaded
                    break
        graph_cache[graph_id] = graph_yaml
    graph_yaml = graph_cache[graph_id]

    node_id = chosen.get("node_at_violation", "") or ""
    node = _node_block_for(graph_yaml, node_id) or {}
    node_rc = node.get("recommendation_class")
    node_el = node.get("evidence_level")
    node_sg = node.get("source_guideline")
    node_tier = _classify_authority(node_rc, node_el, node_sg)

    rule = _find_responsible_rule(node, chosen.get("action_involved", "") or "")
    if rule is not None:
        rule_rc = rule.get("recommendation_class") or node_rc
        rule_el = rule.get("evidence_level") or node_el
        rule_sg = rule.get("source_guideline") or node_sg
    else:
        rule_rc, rule_el, rule_sg = node_rc, node_el, node_sg
    rule_tier = _classify_authority(rule_rc, rule_el, rule_sg)

    promotion_case = (node_tier == "high") and (rule_tier != "high")

    return {
        "episode_id": ep.get("episode_id"),
        "scenario_id": sid,
        "model_dir": ep.get("model_dir"),
        "run_index": ep.get("run_index"),
        "domain": extract_domain(sid),
        "graph_id": graph_id,
        "node_id": node_id,
        "violation_type": chosen.get("violation_type"),
        "action_involved": chosen.get("action_involved"),
        "harm_severity": chosen.get("harm_severity"),
        "node_rc": node_rc,
        "node_el": node_el,
        "node_sg": node_sg,
        "node_tier": node_tier,
        "rule_rc": rule_rc,
        "rule_el": rule_el,
        "rule_sg": rule_sg,
        "rule_tier": rule_tier,
        "match": "yes" if node_tier == rule_tier else "NO",
        "promotion_case": "PROMOTION" if promotion_case else "ok",
    }


# =====================================================================
# CSV + MD render
# =====================================================================
CSV_COLUMNS = [
    "episode_id",
    "scenario_id",
    "model_dir",
    "run_index",
    "domain",
    "graph_id",
    "node_id",
    "violation_type",
    "action_involved",
    "harm_severity",
    "node_rc",
    "node_el",
    "node_sg",
    "node_tier",
    "rule_rc",
    "rule_el",
    "rule_sg",
    "rule_tier",
    "match",
    "promotion_case",
]


def render_md(rows: list[dict]) -> str:
    n = len(rows)
    n_match = sum(1 for r in rows if r["match"] == "yes")
    n_promotion = sum(1 for r in rows if r["promotion_case"] == "PROMOTION")
    by_model = defaultdict(int)
    by_domain = defaultdict(int)
    by_vtype = defaultdict(int)
    for r in rows:
        by_model[r["model_dir"]] += 1
        by_domain[r["domain"]] += 1
        by_vtype[r["violation_type"]] += 1

    lines: list[str] = []
    lines.append("# E9 Follow-up F2 — Node-level Authority Spot-Check")
    lines.append("")
    lines.append("Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (§5.2)")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Sampled episodes: **{n}**")
    lines.append(f"- node_tier == rule_tier: **{n_match} / {n} ({n_match / n * 100:.1f}%)**")
    lines.append(
        f"- Promotion cases (node=high, rule!=high): **{n_promotion} / {n} "
        f"({n_promotion / n * 100:.1f}%)**"
    )
    lines.append("")
    lines.append("## Stratification spread")
    lines.append("")
    lines.append("| Stratum | Count |")
    lines.append("|---|---|")
    for m, c in sorted(by_model.items()):
        lines.append(f"| model={m} | {c} |")
    for d, c in sorted(by_domain.items()):
        lines.append(f"| domain={d} | {c} |")
    for t, c in sorted(by_vtype.items()):
        lines.append(f"| viol_type={t} | {c} |")
    lines.append("")
    lines.append("## Per-episode detail")
    lines.append("")
    lines.append(
        "| # | episode | model | domain | node_id | viol | action | "
        "node (rc/el/sg→tier) | rule (rc/el/sg→tier) | match | promo |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | "
            f"`{r['episode_id']}` | "
            f"{r['model_dir']} | "
            f"{r['domain']} | "
            f"`{r['node_id']}` | "
            f"{r['violation_type']} | "
            f"`{r['action_involved']}` | "
            f"{r['node_rc']}/{r['node_el']}/{r['node_sg']}→**{r['node_tier']}** | "
            f"{r['rule_rc']}/{r['rule_el']}/{r['rule_sg']}→**{r['rule_tier']}** | "
            f"{r['match']} | "
            f"{r['promotion_case']} |"
        )
    lines.append("")
    lines.append("## Drop-in appendix sentence (paste once manual review confirms)")
    lines.append("")
    lines.append(
        f"> A manual spot-check of {n} strict-FA episodes found "
        f"**{n_promotion} cases ({n_promotion / n * 100:.1f}%)** in which "
        f"node-level authority promoted a low-authority edge into the "
        f"high-authority subset; full per-episode evidence is in Appendix Z.4."
    )
    return "\n".join(lines)


# =====================================================================
# main
# =====================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n-samples",
        type=int,
        default=60,
        help="Number of strict-FA episodes to inspect (default: 60).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for stratified sampling.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ANALYSIS_DIR,
    )
    args = parser.parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[1/4] Loading verdict matrix", flush=True)
    with open(VERDICT_MATRIX_PATH) as f:
        vmatrix = json.load(f)

    print("[2/4] Filtering to strict-FA episodes", flush=True)
    strict_fa = find_strict_fa_episodes(vmatrix)
    print(f"      {len(strict_fa)} strict-FA episodes found", flush=True)
    if not strict_fa:
        print("WARNING: zero strict-FA episodes; nothing to spot-check.", flush=True)
        return 0

    print(f"[3/4] Stratified-sampling {args.n_samples} (seed={args.seed})", flush=True)
    sampled = stratified_sample(strict_fa, args.n_samples, args.seed)
    print(f"      sampled {len(sampled)} episodes", flush=True)

    print("[4/4] Building per-episode authority comparison", flush=True)
    episode_index = build_episode_index(RESULTS_DIRS_DEFAULT)
    scenario_to_graph = build_scenario_to_graph_map()
    graph_cache: dict[str, dict] = {}

    rows: list[dict] = []
    for ep in sampled:
        sid = ep.get("scenario_id", "")
        m = ep.get("model_dir", "")
        r = ep.get("run_index", -1)
        path = episode_index.get((sid, m, r))
        if path is None:
            continue
        row = inspect_episode(ep, path, scenario_to_graph, graph_cache)
        if row is not None:
            rows.append(row)
    print(f"      {len(rows)} valid spot-check rows", flush=True)

    csv_out = out_dir / "exp_e9_node_authority_spotcheck.csv"
    md_out = out_dir / "exp_e9_node_authority_spotcheck.md"
    with open(csv_out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with open(md_out, "w") as f:
        f.write(render_md(rows))
    print(f"      csv: {csv_out}")
    print(f"      md:  {md_out}")

    n_promotion = sum(1 for r in rows if r["promotion_case"] == "PROMOTION")
    print()
    print(f"Promotion cases: {n_promotion} / {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
