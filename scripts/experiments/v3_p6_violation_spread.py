
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""v3_p6_violation_spread.py

Analyzes violation distribution patterns across domains, scenarios, and models
for CGA-Bench using 180 rescored episodes (4 models × 15 scenarios × 3 runs).

Outputs:
  evidence_pack/analysis/v3_violation_spread.json
  evidence_pack/analysis/v3_violation_spread.md
  evidence_pack/tables/violation_spread_heatmap.tex
  evidence_pack/tables/domain_violation_profile.tex

Run: PYTHONPATH=. python scripts/experiments/v3_p6_violation_spread.py
"""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import random
import sys
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

ROOT = Path(__file__).resolve().parents[2]
RESCORED_DIR = ROOT / "results" / "clean_slate_rescored"
SCENARIOS_DIR = ROOT / "configs" / "scenarios"
ANALYSIS_DIR = ROOT / "evidence_pack" / "analysis"
TABLES_DIR = ROOT / "evidence_pack" / "tables"

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS = {
    "oss120b": "OSS-120B",
    "qwen27b": "Qwen-27B",
    "qwen35b": "Qwen-35B",
    "qwen4b": "Qwen-4B",
}

VIOLATION_TYPES = ["omission", "commission", "timing", "sequence", "deviation"]

# guideline_graph → domain label
GRAPH_TO_DOMAIN: dict[str, str] = {
    "ssc_sepsis_hour1": "Sepsis",
    "aha_chest_pain": "ChestPain",
    "aha_stroke": "Stroke",
    "aha_heart_failure": "HeartFailure",
    "kdigo_aki_full": "AKI",
    "ada_dka_management": "DKA",
    "atrial_fibrillation": "AF",
    "cap_pneumonia": "CAP",
    "copd_exacerbation": "COPD",
    "gi_bleeding": "GIBleed",
    "hypertensive_emergency": "HTNEmergency",
    "kdigo_contrast_aki": "ContrastAKI",
    "pulmonary_embolism": "PE",
    "universal_clinical_safety": "Universal",
}

# Core guidelines (original 6 clinical domains)
CORE_GRAPHS = {
    "ssc_sepsis_hour1",
    "aha_chest_pain",
    "aha_stroke",
    "aha_heart_failure",
    "kdigo_aki_full",
    "ada_dka_management",
}

# Severity buckets
SEVERITY_LABELS = ["minor", "moderate", "major", "severe"]
SEVERITY_NUMERIC_MAP = {
    "minor": 0.1,
    "moderate": 0.4,
    "major": 0.7,
    "severe": 0.9,
    "catastrophic": 1.0,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_mean(values: list[float]) -> float:
    """Return mean or nan if empty."""
    return sum(values) / len(values) if values else float("nan")


def _safe_std(values: list[float]) -> float:
    """Return population std or nan if empty."""
    if len(values) < 2:
        return float("nan")
    mu = _safe_mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / len(values))


def _fmt(v: float, decimals: int = 3) -> str:
    if math.isnan(v):
        return "N/A"
    return f"{v:.{decimals}f}"


def _severity_bucket(severity_str: str | None) -> str:
    """Map string severity to bucket label."""
    if severity_str is None:
        return "unknown"
    s = str(severity_str).lower()
    if s in ("minor",):
        return "minor"
    if s in ("moderate",):
        return "moderate"
    if s in ("major",):
        return "major"
    if s in ("severe", "catastrophic"):
        return "severe"
    # Try numeric fallback
    try:
        val = float(s)
        if val < 0.2:
            return "minor"
        if val < 0.5:
            return "moderate"
        if val < 0.8:
            return "major"
        return "severe"
    except ValueError:
        return "unknown"


# ---------------------------------------------------------------------------
# Step 1: Load scenario → domain mapping from YAML configs
# ---------------------------------------------------------------------------


def load_scenario_domain_map() -> dict[str, str]:
    """Return {scenario_id: domain_label} from all scenario YAML files."""
    mapping: dict[str, str] = {}
    yaml_files = sorted(SCENARIOS_DIR.glob("*.yaml"))
    print(f"[1/7] Loading scenario configs from {len(yaml_files)} YAML files...")
    for yaml_path in yaml_files:
        try:
            with open(yaml_path) as fh:
                data = yaml.safe_load(fh)
            scenarios = data.get("scenarios", {}) if data else {}
            if not isinstance(scenarios, dict):
                continue
            for sid, sconf in scenarios.items():
                if not isinstance(sconf, dict):
                    continue
                graph = sconf.get("guideline_graph", "")
                domain = GRAPH_TO_DOMAIN.get(graph, "Unknown")
                mapping[sid] = domain
        except Exception as exc:
            print(f"  WARNING: could not parse {yaml_path.name}: {exc}")
    print(f"  Mapped {len(mapping)} scenario IDs to domains.")
    return mapping


# ---------------------------------------------------------------------------
# Step 2: Load all 180 rescored episodes
# ---------------------------------------------------------------------------


def load_episodes(scenario_domain_map: dict[str, str]) -> list[dict[str, Any]]:
    """Load all JSON episodes from rescored subdirs."""
    episodes: list[dict[str, Any]] = []
    total_files = 0
    missing_domain = 0

    for model_dir in MODELS:
        model_path = RESCORED_DIR / model_dir
        if not model_path.exists():
            print(f"  WARNING: {model_path} does not exist, skipping.")
            continue
        json_files = sorted(model_path.glob("*.json"))
        print(f"  {model_dir}: {len(json_files)} files")
        for jf in json_files:
            total_files += 1
            try:
                with open(jf) as fh:
                    raw = json.load(fh)
            except Exception as exc:
                print(f"    WARNING: could not load {jf.name}: {exc}")
                continue

            sid = raw.get("scenario_id", "")
            domain = scenario_domain_map.get(sid, "Unknown")
            if domain == "Unknown":
                missing_domain += 1

            # Normalise violation events
            vevents = raw.get("new_violation_events", [])
            if not isinstance(vevents, list):
                vevents = []

            episodes.append(
                {
                    "scenario_id": sid,
                    "model": raw.get("model_name", model_dir),
                    "model_key": model_dir,
                    "run_index": raw.get("run_index", 0),
                    "cga": float(raw.get("new_compliance_score", float("nan"))),
                    "total_violations": int(raw.get("new_total_violations", 0)),
                    "violations_by_type": raw.get("new_violations_by_type", {}),
                    "sub_scores": raw.get("new_sub_scores", {}),
                    "violation_events": vevents,
                    "domain": domain,
                }
            )

    print(f"\n[2/7] Loaded {len(episodes)} episodes from {total_files} files.")
    if missing_domain:
        print(f"  WARNING: {missing_domain} episodes had no domain mapping.")
    return episodes


# ---------------------------------------------------------------------------
# Step 3: Model × Scenario heatmaps
# ---------------------------------------------------------------------------


def compute_heatmaps(
    episodes: list[dict[str, Any]],
    scenarios: list[str],
) -> dict[str, Any]:
    """Build model×scenario CGA and violation-count matrices."""
    print("[3/7] Computing model × scenario heatmaps...")

    # Accumulate per (scenario, model_key)
    cga_acc: dict[tuple[str, str], list[float]] = defaultdict(list)
    viol_acc: dict[tuple[str, str], list[int]] = defaultdict(list)

    for ep in episodes:
        key = (ep["scenario_id"], ep["model_key"])
        if not math.isnan(ep["cga"]):
            cga_acc[key].append(ep["cga"])
        viol_acc[key].append(ep["total_violations"])

    cga_matrix: dict[str, dict[str, float]] = {}
    viol_matrix: dict[str, dict[str, float]] = {}

    for sc in scenarios:
        cga_matrix[sc] = {}
        viol_matrix[sc] = {}
        for mk in MODELS:
            cga_vals = cga_acc.get((sc, mk), [])
            viol_vals = viol_acc.get((sc, mk), [])
            cga_matrix[sc][mk] = _safe_mean(cga_vals)
            viol_matrix[sc][mk] = _safe_mean(viol_vals)

    return {"cga_matrix": cga_matrix, "viol_matrix": viol_matrix}


# ---------------------------------------------------------------------------
# Step 4: Violation type distribution
# ---------------------------------------------------------------------------


def compute_violation_distributions(
    episodes: list[dict[str, Any]],
    scenarios: list[str],
) -> dict[str, Any]:
    """Per-model and per-scenario violation type counts and proportions."""
    print("[4/7] Computing violation type distributions...")

    # Per model
    model_vtype: dict[str, dict[str, int]] = {mk: defaultdict(int) for mk in MODELS}
    model_episodes: dict[str, int] = defaultdict(int)

    # Per scenario
    scen_vtype: dict[str, dict[str, int]] = {sc: defaultdict(int) for sc in scenarios}
    scen_episodes: dict[str, int] = defaultdict(int)

    for ep in episodes:
        mk = ep["model_key"]
        sc = ep["scenario_id"]
        model_episodes[mk] += 1
        scen_episodes[sc] += 1
        vbt = ep["violations_by_type"]
        if isinstance(vbt, dict):
            for vt, cnt in vbt.items():
                vt_lower = vt.lower()
                model_vtype[mk][vt_lower] += int(cnt)
                if sc in scen_vtype:
                    scen_vtype[sc][vt_lower] += int(cnt)

    def _build_distribution(
        raw: dict[str, dict[str, int]],
        ep_counts: dict[str, int],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for key, vtype_counts in raw.items():
            total = sum(vtype_counts.values())
            props: dict[str, float] = {}
            for vt in VIOLATION_TYPES:
                cnt = vtype_counts.get(vt, 0)
                props[vt] = cnt / total if total > 0 else 0.0
            result[key] = {
                "counts": {vt: vtype_counts.get(vt, 0) for vt in VIOLATION_TYPES},
                "proportions": props,
                "total": total,
                "mean_per_episode": total / ep_counts[key] if ep_counts[key] else 0.0,
                "n_episodes": ep_counts[key],
            }
        return result

    return {
        "per_model": _build_distribution(model_vtype, model_episodes),
        "per_scenario": _build_distribution(scen_vtype, scen_episodes),
    }


# ---------------------------------------------------------------------------
# Step 5: Domain aggregation
# ---------------------------------------------------------------------------


def compute_domain_aggregation(
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Per-domain × model CGA and violation profiles."""
    print("[5/7] Computing domain aggregations...")

    # Collect data by domain
    domain_model_cga: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    domain_vtype: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for ep in episodes:
        dom = ep["domain"]
        mk = ep["model_key"]
        if not math.isnan(ep["cga"]):
            domain_model_cga[dom][mk].append(ep["cga"])
        vbt = ep["violations_by_type"]
        if isinstance(vbt, dict):
            for vt, cnt in vbt.items():
                domain_vtype[dom][vt.lower()] += int(cnt)

    domains = sorted(domain_model_cga.keys())

    # Mean CGA per domain per model
    domain_cga_table: dict[str, dict[str, float]] = {}
    for dom in domains:
        domain_cga_table[dom] = {}
        for mk in MODELS:
            vals = domain_model_cga[dom].get(mk, [])
            domain_cga_table[dom][mk] = _safe_mean(vals)

    # Dominant violation type per domain
    dominant_vtype: dict[str, str] = {}
    commission_rank: list[tuple[str, int]] = []
    timing_rank: list[tuple[str, int]] = []

    for dom in domains:
        vtype_counts = domain_vtype[dom]
        total = sum(vtype_counts.values())
        if total == 0:
            dominant_vtype[dom] = "none"
            commission_rank.append((dom, 0))
            timing_rank.append((dom, 0))
            continue
        dom_vt = max(VIOLATION_TYPES, key=lambda v: vtype_counts.get(v, 0))
        dominant_vtype[dom] = dom_vt
        commission_rank.append((dom, vtype_counts.get("commission", 0)))
        timing_rank.append((dom, vtype_counts.get("timing", 0)))

    commission_rank.sort(key=lambda x: x[1], reverse=True)
    timing_rank.sort(key=lambda x: x[1], reverse=True)

    # Full violation profile per domain
    domain_vtype_table: dict[str, dict[str, Any]] = {}
    for dom in domains:
        vtype_counts = domain_vtype[dom]
        total = sum(vtype_counts.values())
        domain_vtype_table[dom] = {
            "counts": {vt: vtype_counts.get(vt, 0) for vt in VIOLATION_TYPES},
            "proportions": {vt: (vtype_counts.get(vt, 0) / total if total > 0 else 0.0) for vt in VIOLATION_TYPES},
            "total": total,
            "dominant": dominant_vtype[dom],
        }

    return {
        "domains": domains,
        "cga_by_domain_model": domain_cga_table,
        "violation_profile_by_domain": domain_vtype_table,
        "dominant_violation_type": dominant_vtype,
        "commission_rank": commission_rank,
        "timing_rank": timing_rank,
    }


# ---------------------------------------------------------------------------
# Step 6: Severity distribution
# ---------------------------------------------------------------------------


def compute_severity_distribution(
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Count violations by harm_severity bucket per model and per domain."""
    print("[6/7] Computing severity distributions...")

    BUCKETS = ["minor", "moderate", "major", "severe", "unknown"]

    model_sev: dict[str, dict[str, int]] = {mk: defaultdict(int) for mk in MODELS}
    domain_sev: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for ep in episodes:
        mk = ep["model_key"]
        dom = ep["domain"]
        for evt in ep["violation_events"]:
            if not isinstance(evt, dict):
                continue
            sev = _severity_bucket(evt.get("harm_severity"))
            model_sev[mk][sev] += 1
            domain_sev[dom][sev] += 1

    def _normalise(
        raw: dict[str, dict[str, int]],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for key, sev_counts in raw.items():
            total = sum(sev_counts.values())
            result[key] = {
                "counts": {b: sev_counts.get(b, 0) for b in BUCKETS},
                "proportions": {b: (sev_counts.get(b, 0) / total if total > 0 else 0.0) for b in BUCKETS},
                "total": total,
            }
        return result

    return {
        "per_model": _normalise(model_sev),
        "per_domain": _normalise(domain_sev),
    }


# ---------------------------------------------------------------------------
# Step 7: Scenario difficulty & model discrimination
# ---------------------------------------------------------------------------


def compute_scenario_difficulty(
    episodes: list[dict[str, Any]],
    scenarios: list[str],
    scenario_domain_map: dict[str, str],
) -> dict[str, Any]:
    """Rank scenarios by mean CGA and compute model discrimination."""
    print("[7/7] Computing scenario difficulty ranking...")

    # Pre-seed with known scenarios so containment check works correctly
    scen_cga_all: dict[str, list[float]] = {sc: [] for sc in scenarios}
    scen_cga_per_model: dict[str, dict[str, list[float]]] = {sc: {mk: [] for mk in MODELS} for sc in scenarios}

    for ep in episodes:
        sc = ep["scenario_id"]
        if sc not in scen_cga_all:
            continue
        if not math.isnan(ep["cga"]):
            scen_cga_all[sc].append(ep["cga"])
            scen_cga_per_model[sc][ep["model_key"]].append(ep["cga"])

    difficulty: list[dict[str, Any]] = []
    for sc in scenarios:
        vals = scen_cga_all[sc]
        mean_cga = _safe_mean(vals)
        # Model discrimination = std of per-model means
        model_means = [_safe_mean(scen_cga_per_model[sc][mk]) for mk in MODELS if scen_cga_per_model[sc][mk]]
        model_means_clean = [v for v in model_means if not math.isnan(v)]
        discrimination = _safe_std(model_means_clean)

        difficulty.append(
            {
                "scenario_id": sc,
                "domain": scenario_domain_map.get(sc, "Unknown"),
                "mean_cga": mean_cga,
                "std_cga": _safe_std(vals),
                "n_episodes": len(vals),
                "model_means": {mk: _safe_mean(scen_cga_per_model[sc][mk]) for mk in MODELS},
                "model_discrimination": discrimination,
            }
        )

    difficulty.sort(key=lambda x: x["mean_cga"] if not math.isnan(x["mean_cga"]) else 1.0)
    return {"scenario_difficulty": difficulty}


# ---------------------------------------------------------------------------
# Step 8: Core vs Expansion split
# ---------------------------------------------------------------------------


def compute_core_vs_expansion(
    episodes: list[dict[str, Any]],
    scenario_domain_map: dict[str, str],
    yaml_scenario_graph_map: dict[str, str],
) -> dict[str, Any]:
    """Compare core 8 vs expansion 7 scenario sets."""

    def _is_core(sid: str) -> bool:
        graph = yaml_scenario_graph_map.get(sid, "")
        return graph in CORE_GRAPHS

    core_eps = [ep for ep in episodes if _is_core(ep["scenario_id"])]
    exp_eps = [ep for ep in episodes if not _is_core(ep["scenario_id"])]

    def _profile(eps: list[dict[str, Any]]) -> dict[str, Any]:
        cga_vals = [ep["cga"] for ep in eps if not math.isnan(ep["cga"])]
        # Violation type totals
        vtype_totals: dict[str, int] = defaultdict(int)
        for ep in eps:
            vbt = ep["violations_by_type"]
            if isinstance(vbt, dict):
                for vt, cnt in vbt.items():
                    vtype_totals[vt.lower()] += int(cnt)
        total_v = sum(vtype_totals.values())
        # Per-model CGA
        model_cga: dict[str, list[float]] = defaultdict(list)
        for ep in eps:
            if not math.isnan(ep["cga"]):
                model_cga[ep["model_key"]].append(ep["cga"])
        model_means = {mk: _safe_mean(model_cga.get(mk, [])) for mk in MODELS}
        # Rank stability: ranking of models by mean CGA
        ranked = sorted(MODELS, key=lambda mk: model_means.get(mk, 0.0), reverse=True)
        return {
            "n_episodes": len(eps),
            "mean_cga": _safe_mean(cga_vals),
            "std_cga": _safe_std(cga_vals),
            "violation_profile": {
                "counts": {vt: vtype_totals.get(vt, 0) for vt in VIOLATION_TYPES},
                "proportions": {
                    vt: (vtype_totals.get(vt, 0) / total_v if total_v > 0 else 0.0) for vt in VIOLATION_TYPES
                },
            },
            "model_mean_cga": model_means,
            "model_ranking": ranked,
        }

    core_profile = _profile(core_eps)
    exp_profile = _profile(exp_eps)

    # Ranking stability: are the orderings the same?
    rank_stable = core_profile["model_ranking"] == exp_profile["model_ranking"]

    return {
        "core": core_profile,
        "expansion": exp_profile,
        "ranking_stable": rank_stable,
        "core_scenarios": sorted(set(ep["scenario_id"] for ep in core_eps)),
        "expansion_scenarios": sorted(set(ep["scenario_id"] for ep in exp_eps)),
    }


# ---------------------------------------------------------------------------
# Report generation helpers
# ---------------------------------------------------------------------------


def _text_table(
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[int] | None = None,
) -> str:
    """Simple fixed-width text table."""
    if col_widths is None:
        col_widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0)) for i, h in enumerate(headers)]
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    def _row(cells: list[str]) -> str:
        parts = []
        for i, cell in enumerate(cells):
            parts.append(f" {cell!s:<{col_widths[i]}} ")
        return "|" + "|".join(parts) + "|"

    lines = [sep, _row(headers), sep]
    for row in rows:
        lines.append(_row(row))
    lines.append(sep)
    return "\n".join(lines)


def build_markdown_report(
    scenarios: list[str],
    scenario_domain_map: dict[str, str],
    heatmaps: dict[str, Any],
    vdist: dict[str, Any],
    domain_agg: dict[str, Any],
    severity: dict[str, Any],
    difficulty: dict[str, Any],
    core_exp: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# V3 Violation Spread Analysis")
    lines.append("")
    lines.append(
        "Analysis of violation distribution patterns across 15 scenarios, "
        "4 models, and 3 runs (180 total episodes) from the CGA-Bench "
        "clean-slate rescored dataset."
    )
    lines.append("")

    # ------------------------------------------------------------------
    # 1. Model × Scenario CGA Heatmap
    # ------------------------------------------------------------------
    lines.append("## 1. Model × Scenario CGA Heatmap (mean across 3 runs)")
    lines.append("")
    cga_mat = heatmaps["cga_matrix"]
    headers = ["Scenario", "Domain"] + [MODEL_LABELS[mk] for mk in MODELS] + ["Mean"]
    col_w = [28, 14] + [10] * len(MODELS) + [7]
    rows = []
    for sc in scenarios:
        dom = scenario_domain_map.get(sc, "?")
        row_vals = [cga_mat[sc].get(mk, float("nan")) for mk in MODELS]
        row_mean = _safe_mean([v for v in row_vals if not math.isnan(v)])
        rows.append([sc[:27], dom[:13]] + [_fmt(v, 3) for v in row_vals] + [_fmt(row_mean, 3)])
    lines.append(_text_table(headers, rows, col_w))
    lines.append("")

    # ------------------------------------------------------------------
    # 2. Model × Scenario Violation Count Heatmap
    # ------------------------------------------------------------------
    lines.append("## 2. Model × Scenario Violation Count Heatmap (mean)")
    lines.append("")
    viol_mat = heatmaps["viol_matrix"]
    headers2 = ["Scenario", "Domain"] + [MODEL_LABELS[mk] for mk in MODELS] + ["Mean"]
    rows2 = []
    for sc in scenarios:
        dom = scenario_domain_map.get(sc, "?")
        row_vals = [viol_mat[sc].get(mk, float("nan")) for mk in MODELS]
        row_mean = _safe_mean([v for v in row_vals if not math.isnan(v)])
        rows2.append([sc[:27], dom[:13]] + [_fmt(v, 1) for v in row_vals] + [_fmt(row_mean, 1)])
    lines.append(_text_table(headers2, rows2, col_w))
    lines.append("")

    # ------------------------------------------------------------------
    # 3. Violation Type Distribution per Model
    # ------------------------------------------------------------------
    lines.append("## 3. Violation Type Distribution per Model")
    lines.append("")
    pm = vdist["per_model"]
    headers3 = ["Model", "Omission%", "Commission%", "Timing%", "Sequence%", "Deviation%", "Mean/Ep"]
    col_w3 = [12, 11, 13, 9, 11, 11, 9]
    rows3 = []
    for mk in MODELS:
        d = pm.get(mk, {})
        props = d.get("proportions", {})
        rows3.append(
            [
                MODEL_LABELS[mk],
                _fmt(props.get("omission", 0.0) * 100, 1) + "%",
                _fmt(props.get("commission", 0.0) * 100, 1) + "%",
                _fmt(props.get("timing", 0.0) * 100, 1) + "%",
                _fmt(props.get("sequence", 0.0) * 100, 1) + "%",
                _fmt(props.get("deviation", 0.0) * 100, 1) + "%",
                _fmt(d.get("mean_per_episode", 0.0), 2),
            ]
        )
    lines.append(_text_table(headers3, rows3, col_w3))
    lines.append("")

    # ------------------------------------------------------------------
    # 4. Domain Aggregation
    # ------------------------------------------------------------------
    lines.append("## 4. Domain Aggregation — Mean CGA per Domain per Model")
    lines.append("")
    dom_cga = domain_agg["cga_by_domain_model"]
    domains = domain_agg["domains"]
    headers4 = ["Domain"] + [MODEL_LABELS[mk] for mk in MODELS] + ["Mean"]
    col_w4 = [14] + [10] * len(MODELS) + [7]
    rows4 = []
    for dom in sorted(domains):
        row_vals = [dom_cga.get(dom, {}).get(mk, float("nan")) for mk in MODELS]
        row_mean = _safe_mean([v for v in row_vals if not math.isnan(v)])
        rows4.append([dom[:13]] + [_fmt(v, 3) for v in row_vals] + [_fmt(row_mean, 3)])
    lines.append(_text_table(headers4, rows4, col_w4))
    lines.append("")

    lines.append("### Dominant Violation Type per Domain")
    lines.append("")
    vp = domain_agg["violation_profile_by_domain"]
    headers5 = ["Domain", "Omission", "Commission", "Timing", "Sequence", "Deviation", "Dominant"]
    col_w5 = [14, 9, 11, 8, 10, 10, 10]
    rows5 = []
    for dom in sorted(domains):
        d = vp.get(dom, {})
        cnts = d.get("counts", {})
        rows5.append(
            [
                dom[:13],
                str(cnts.get("omission", 0)),
                str(cnts.get("commission", 0)),
                str(cnts.get("timing", 0)),
                str(cnts.get("sequence", 0)),
                str(cnts.get("deviation", 0)),
                d.get("dominant", "?"),
            ]
        )
    lines.append(_text_table(headers5, rows5, col_w5))
    lines.append("")

    lines.append("### Domains Ranked by Commission Violations (safety-critical)")
    lines.append("")
    for dom, cnt in domain_agg["commission_rank"]:
        lines.append(f"  - **{dom}**: {cnt} commission violations")
    lines.append("")

    lines.append("### Domains Ranked by Timing Violations")
    lines.append("")
    for dom, cnt in domain_agg["timing_rank"]:
        lines.append(f"  - **{dom}**: {cnt} timing violations")
    lines.append("")

    # ------------------------------------------------------------------
    # 5. Severity Distribution per Model
    # ------------------------------------------------------------------
    lines.append("## 5. Severity Distribution per Model")
    lines.append("")
    sev_pm = severity["per_model"]
    BUCKETS = ["minor", "moderate", "major", "severe"]
    headers6 = ["Model", "Minor", "Moderate", "Major", "Severe", "Total"]
    col_w6 = [12, 7, 9, 7, 7, 7]
    rows6 = []
    for mk in MODELS:
        d = sev_pm.get(mk, {})
        cnts = d.get("counts", {})
        rows6.append(
            [
                MODEL_LABELS[mk],
                str(cnts.get("minor", 0)),
                str(cnts.get("moderate", 0)),
                str(cnts.get("major", 0)),
                str(cnts.get("severe", 0)),
                str(d.get("total", 0)),
            ]
        )
    lines.append(_text_table(headers6, rows6, col_w6))
    lines.append("")

    lines.append("### Severity Distribution per Domain")
    lines.append("")
    sev_dom = severity["per_domain"]
    rows7 = []
    for dom in sorted(sev_dom.keys()):
        d = sev_dom[dom]
        cnts = d.get("counts", {})
        rows7.append(
            [
                dom[:13],
                str(cnts.get("minor", 0)),
                str(cnts.get("moderate", 0)),
                str(cnts.get("major", 0)),
                str(cnts.get("severe", 0)),
                str(d.get("total", 0)),
            ]
        )
    headers7 = ["Domain", "Minor", "Moderate", "Major", "Severe", "Total"]
    col_w7 = [14, 7, 9, 7, 7, 7]
    lines.append(_text_table(headers7, rows7, col_w7))
    lines.append("")

    # ------------------------------------------------------------------
    # 6. Scenario Difficulty Ranking
    # ------------------------------------------------------------------
    lines.append("## 6. Scenario Difficulty Ranking")
    lines.append("")
    diff_list = difficulty["scenario_difficulty"]
    lines.append("### Hardest Scenarios (lowest mean CGA, all models pooled)")
    lines.append("")
    headers8 = ["Rank", "Scenario", "Domain", "Mean CGA", "Std CGA", "Discrimination"]
    col_w8 = [5, 30, 14, 9, 8, 14]
    rows8 = []
    for i, entry in enumerate(diff_list, 1):
        rows8.append(
            [
                str(i),
                entry["scenario_id"][:29],
                entry["domain"][:13],
                _fmt(entry["mean_cga"], 3),
                _fmt(entry["std_cga"], 3),
                _fmt(entry["model_discrimination"], 3),
            ]
        )
    lines.append(_text_table(headers8, rows8, col_w8))
    lines.append("")

    # ------------------------------------------------------------------
    # 7. Core vs Expansion
    # ------------------------------------------------------------------
    lines.append("## 7. Core 8 vs Expansion 7 Scenarios")
    lines.append("")
    core = core_exp["core"]
    exp = core_exp["expansion"]

    lines.append(f"**Core scenarios ({len(core_exp['core_scenarios'])}):** " + ", ".join(core_exp["core_scenarios"]))
    lines.append("")
    lines.append(
        f"**Expansion scenarios ({len(core_exp['expansion_scenarios'])}):** "
        + ", ".join(core_exp["expansion_scenarios"])
    )
    lines.append("")

    comp_headers = ["Metric", "Core", "Expansion"]
    comp_col_w = [30, 10, 10]
    comp_rows = [
        ["N episodes", str(core["n_episodes"]), str(exp["n_episodes"])],
        ["Mean CGA", _fmt(core["mean_cga"], 3), _fmt(exp["mean_cga"], 3)],
        ["Std CGA", _fmt(core["std_cga"], 3), _fmt(exp["std_cga"], 3)],
    ]
    for vt in VIOLATION_TYPES:
        core_p = core["violation_profile"]["proportions"].get(vt, 0.0)
        exp_p = exp["violation_profile"]["proportions"].get(vt, 0.0)
        comp_rows.append(
            [
                f"  {vt.capitalize()} %",
                _fmt(core_p * 100, 1) + "%",
                _fmt(exp_p * 100, 1) + "%",
            ]
        )
    for mk in MODELS:
        comp_rows.append(
            [
                f"  {MODEL_LABELS[mk]} mean CGA",
                _fmt(core["model_mean_cga"].get(mk, float("nan")), 3),
                _fmt(exp["model_mean_cga"].get(mk, float("nan")), 3),
            ]
        )
    comp_rows.append(
        [
            "Model ranking",
            ">".join(MODEL_LABELS[m] for m in core["model_ranking"]),
            ">".join(MODEL_LABELS[m] for m in exp["model_ranking"]),
        ]
    )
    comp_rows.append(
        [
            "Ranking stable?",
            "—",
            "YES" if core_exp["ranking_stable"] else "NO",
        ]
    )
    lines.append(_text_table(comp_headers, comp_rows, comp_col_w))
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LaTeX helpers
# ---------------------------------------------------------------------------


def build_latex_heatmap(
    scenarios: list[str],
    scenario_domain_map: dict[str, str],
    cga_matrix: dict[str, dict[str, float]],
) -> str:
    """LaTeX table: rows = scenarios, cols = models."""
    col_spec = "l l " + " ".join(["r"] * len(MODELS))
    rows: list[str] = []

    for sc in scenarios:
        dom = scenario_domain_map.get(sc, "?")
        cells = [sc.replace("_", "\\_"), dom]
        vals = [cga_matrix[sc].get(mk, float("nan")) for mk in MODELS]
        best_val = max((v for v in vals if not math.isnan(v)), default=float("nan"))
        for v in vals:
            if math.isnan(v):
                cells.append("---")
            elif abs(v - best_val) < 1e-6:
                cells.append(f"\\textbf{{{_fmt(v, 3)}}}")
            else:
                cells.append(_fmt(v, 3))
        rows.append(" & ".join(cells) + " \\\\")

    model_col_headers = " & ".join(
        ["\\textbf{Scenario}", "\\textbf{Domain}"] + [f"\\textbf{{{MODEL_LABELS[mk]}}}" for mk in MODELS]
    )

    lines = (
        [
            "\\begin{table}[htbp]",
            "\\centering",
            "\\caption{Model $\\times$ Scenario CGA Score Heatmap (mean of 3 runs). Best score per row in bold.}",
            "\\label{tab:violation_spread_heatmap}",
            f"\\begin{{tabular}}{{{col_spec}}}",
            "\\toprule",
            model_col_headers + " \\\\",
            "\\midrule",
        ]
        + rows
        + [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
        ]
    )
    return "\n".join(lines)


def build_latex_domain_table(
    domain_agg: dict[str, Any],
) -> str:
    """LaTeX table: domain violation profile."""
    domains = sorted(domain_agg["domains"])
    vp = domain_agg["violation_profile_by_domain"]
    dom_cga = domain_agg["cga_by_domain_model"]

    col_spec = "l r r r r r r l"
    header = (
        "\\textbf{Domain} & \\textbf{Omiss.} & \\textbf{Commiss.} "
        "& \\textbf{Timing} & \\textbf{Seq.} & \\textbf{Deviat.} "
        "& \\textbf{Total} & \\textbf{Dominant} \\\\"
    )

    rows: list[str] = []
    for dom in domains:
        d = vp.get(dom, {})
        cnts = d.get("counts", {})
        dominant = d.get("dominant", "?")
        total = d.get("total", 0)
        cells = [
            dom,
            str(cnts.get("omission", 0)),
            str(cnts.get("commission", 0)),
            str(cnts.get("timing", 0)),
            str(cnts.get("sequence", 0)),
            str(cnts.get("deviation", 0)),
            str(total),
            dominant,
        ]
        rows.append(" & ".join(cells) + " \\\\")

    lines = (
        [
            "\\begin{table}[htbp]",
            "\\centering",
            "\\caption{Domain-level violation profile across all models and runs.}",
            "\\label{tab:domain_violation_profile}",
            f"\\begin{{tabular}}{{{col_spec}}}",
            "\\toprule",
            header,
            "\\midrule",
        ]
        + rows
        + [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("V3 P6 Violation Spread Analysis")
    print("=" * 60)

    # Ensure output dirs exist
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    # Load scenario domain map (also build graph map for core/expansion)
    yaml_files = sorted(SCENARIOS_DIR.glob("*.yaml"))
    scenario_domain_map: dict[str, str] = {}
    yaml_scenario_graph_map: dict[str, str] = {}
    for yaml_path in yaml_files:
        try:
            with open(yaml_path) as fh:
                data = yaml.safe_load(fh)
            scenarios_cfg = data.get("scenarios", {}) if data else {}
            if not isinstance(scenarios_cfg, dict):
                continue
            for sid, sconf in scenarios_cfg.items():
                if not isinstance(sconf, dict):
                    continue
                graph = sconf.get("guideline_graph", "")
                domain = GRAPH_TO_DOMAIN.get(graph, "Unknown")
                scenario_domain_map[sid] = domain
                yaml_scenario_graph_map[sid] = graph
        except Exception as exc:
            print(f"  WARNING: could not parse {yaml_path.name}: {exc}")

    print(f"[1/7] Loaded {len(scenario_domain_map)} scenario→domain mappings.")

    # Load episodes
    episodes = load_episodes(scenario_domain_map)

    if not episodes:
        print("ERROR: No episodes loaded. Check RESCORED_DIR path.")
        sys.exit(1)

    # Determine scenario list from data (preserving a consistent order)
    seen_scenarios: dict[str, None] = {}
    for ep in episodes:
        seen_scenarios[ep["scenario_id"]] = None
    scenarios = list(seen_scenarios.keys())
    print(f"  Found {len(scenarios)} unique scenarios: {scenarios}")

    # Heatmaps
    heatmaps = compute_heatmaps(episodes, scenarios)

    # Violation type distributions
    vdist = compute_violation_distributions(episodes, scenarios)

    # Domain aggregation
    domain_agg = compute_domain_aggregation(episodes)

    # Severity distribution
    severity = compute_severity_distribution(episodes)

    # Scenario difficulty
    difficulty = compute_scenario_difficulty(episodes, scenarios, scenario_domain_map)

    # Core vs Expansion
    core_exp = compute_core_vs_expansion(episodes, scenario_domain_map, yaml_scenario_graph_map)

    # ------------------------------------------------------------------
    # Assemble full JSON output
    # ------------------------------------------------------------------
    output_json: dict[str, Any] = {
        "meta": {
            "description": "V3 violation spread analysis across 15 scenarios, 4 models, 3 runs",
            "n_episodes": len(episodes),
            "n_scenarios": len(scenarios),
            "n_models": len(MODELS),
            "models": MODELS,
            "scenarios": scenarios,
            "random_seed": RANDOM_SEED,
        },
        "heatmaps": heatmaps,
        "violation_distributions": vdist,
        "domain_aggregation": domain_agg,
        "severity_distribution": severity,
        "scenario_difficulty": difficulty,
        "core_vs_expansion": core_exp,
    }

    json_path = ANALYSIS_DIR / "v3_violation_spread.json"
    with open(json_path, "w") as fh:
        json.dump(output_json, fh, indent=2, default=str)
    print(f"\nWrote: {json_path}")

    # ------------------------------------------------------------------
    # Markdown report
    # ------------------------------------------------------------------
    md_report = build_markdown_report(
        scenarios=scenarios,
        scenario_domain_map=scenario_domain_map,
        heatmaps=heatmaps,
        vdist=vdist,
        domain_agg=domain_agg,
        severity=severity,
        difficulty=difficulty,
        core_exp=core_exp,
    )
    md_path = ANALYSIS_DIR / "v3_violation_spread.md"
    with open(md_path, "w") as fh:
        fh.write(md_report)
    print(f"Wrote: {md_path}")

    # ------------------------------------------------------------------
    # LaTeX tables
    # ------------------------------------------------------------------
    latex_heatmap = build_latex_heatmap(
        scenarios=scenarios,
        scenario_domain_map=scenario_domain_map,
        cga_matrix=heatmaps["cga_matrix"],
    )
    heatmap_tex_path = TABLES_DIR / "violation_spread_heatmap.tex"
    with open(heatmap_tex_path, "w") as fh:
        fh.write(latex_heatmap)
    print(f"Wrote: {heatmap_tex_path}")

    latex_domain = build_latex_domain_table(domain_agg)
    domain_tex_path = TABLES_DIR / "domain_violation_profile.tex"
    with open(domain_tex_path, "w") as fh:
        fh.write(latex_domain)
    print(f"Wrote: {domain_tex_path}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Episodes analysed : {len(episodes)}")
    print(f"Scenarios         : {len(scenarios)}")
    print(f"Models            : {len(MODELS)}")

    diff_list = difficulty["scenario_difficulty"]
    if diff_list:
        hardest = diff_list[0]
        easiest = diff_list[-1]
        print(f"\nHardest scenario  : {hardest['scenario_id']}  (mean CGA={_fmt(hardest['mean_cga'], 3)})")
        print(f"Easiest scenario  : {easiest['scenario_id']}  (mean CGA={_fmt(easiest['mean_cga'], 3)})")

    core = core_exp["core"]
    exp = core_exp["expansion"]
    print(f"\nCore mean CGA     : {_fmt(core['mean_cga'], 3)}")
    print(f"Expansion mean CGA: {_fmt(exp['mean_cga'], 3)}")
    print(f"Ranking stable    : {core_exp['ranking_stable']}")

    print("\nModel ranking (overall):")
    all_model_cga = {mk: [] for mk in MODELS}
    for ep in episodes:
        if not math.isnan(ep["cga"]):
            all_model_cga[ep["model_key"]].append(ep["cga"])
    ranked_overall = sorted(MODELS, key=lambda mk: _safe_mean(all_model_cga[mk]), reverse=True)
    for mk in ranked_overall:
        print(f"  {MODEL_LABELS[mk]:12s} : {_fmt(_safe_mean(all_model_cga[mk]), 3)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
