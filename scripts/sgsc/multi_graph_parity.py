#!/usr/bin/env python3
"""Multi-graph v7 vs v6 parity diagnosis (5 sample graphs + 25-graph table).

Compares v6 manual + auto/ scenario YAMLs against v7 SGSC-compiled scenarios
across the 25 active core CPGs. Emits a CSV distribution table and a
markdown report with multiplicity decomposition for B-4 sizing.

Usage:
    PYTHONPATH=. python scripts/sgsc/multi_graph_parity.py
"""

from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
from pathlib import Path
import statistics
from typing import Any

from scripts.sgsc.extract_v6_profiles import categorize
import yaml

# 25 active core graphs (from B-1 + v7 sgsc_output/v7_e3_combined_overnight/)
ACTIVE_CORE_GRAPHS: list[str] = [
    "aabb_transfusion",
    "aba_burn_resuscitation",
    "acls_cardiac_arrest",
    "acog_obstetric_hemorrhage",
    "ada_dka_management",
    "aha_chest_pain_evaluation",
    "aha_heart_failure_2022",
    "aha_stroke_2019",
    "anaphylaxis_management",
    "apa_agitation_management",
    "atrial_fibrillation",
    "cap_pneumonia",
    "copd_exacerbation",
    "gi_bleeding",
    "gina_asthma_exacerbation",
    "hypertensive_emergency",
    "idsa_meningitis",
    "kdigo_aki_full",
    "kdigo_contrast_aki",
    "pals_pediatric_emergency",
    "pulmonary_embolism",
    "ssc_sepsis_hour1_bundle",
    "status_epilepticus",
    "toxicology_management",
    "universal_clinical_safety",
]

# Sample graphs requested by user for deep-dive
SAMPLE_GRAPHS: list[str] = [
    "kdigo_aki_full",
    "aha_heart_failure_2022",
    "kdigo_contrast_aki",
    "ada_dka_management",
    "ssc_sepsis_hour1_bundle",
]

# Rare profile dimensions used in multiplicity decomposition
RARE_PREGNANCY = {"pregnant", "breastfeeding", "postpartum"}
RARE_SPECIAL = {"anticoagulated", "septic_shock", "intubated", "on_steroids"}
RARE_COMORBIDITY = {"ckd", "immunocompromised", "pregnancy_related"}


def _load_v6_entries(scenarios_glob: str, exclude_glob: str) -> list[dict[str, Any]]:
    """Walk v6 YAMLs, return entries with action counts attached."""
    files: list[str] = []
    for pat in scenarios_glob.split(","):
        files.extend(sorted(glob.glob(pat.strip())))
    excludes: set[str] = set()
    for pat in exclude_glob.split(","):
        if pat.strip():
            excludes.update(glob.glob(pat.strip()))
    entries: list[dict[str, Any]] = []
    for f in sorted(set(files)):
        if f in excludes:
            continue
        with open(f, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        scenarios = doc.get("scenarios", {}) if isinstance(doc, dict) else {}
        if not isinstance(scenarios, dict):
            continue
        for sid, s in scenarios.items():
            if not isinstance(s, dict):
                continue
            entries.append(
                {
                    "scenario_id": sid,
                    "guideline_graph": s.get("guideline_graph", "<unknown>"),
                    "expected_actions": list(s.get("expected_actions") or []),
                    "forbidden_actions": list(s.get("forbidden_actions") or []),
                    "deadlines": dict(s.get("deadlines") or {}),
                    "profile": categorize(s),
                }
            )
    return entries


def _load_v7_entries(v7_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Load v7 scenario JSON for each of the 25 core graphs."""
    out: dict[str, list[dict[str, Any]]] = {}
    for graph in ACTIVE_CORE_GRAPHS:
        path = v7_root / graph / f"{graph}_scenarios.json"
        if not path.exists():
            out[graph] = []
            continue
        doc = json.loads(path.read_text())
        # v7 schema: top-level dict keyed by scenario_id
        if not isinstance(doc, dict):
            out[graph] = []
            continue
        ents: list[dict[str, Any]] = []
        for sid, s in doc.items():
            if not isinstance(s, dict):
                continue
            ents.append(
                {
                    "scenario_id": sid,
                    "guideline_graph": graph,
                    "expected_actions": list(s.get("expected_actions") or []),
                    "forbidden_actions": list(s.get("forbidden_actions") or []),
                    "deadlines": dict(s.get("deadlines") or {}),
                    "patient": s.get("patient") or {},
                }
            )
        out[graph] = ents
    return out


def _safe_mean(xs: list[float]) -> float:
    return float(statistics.mean(xs)) if xs else 0.0


def _per_graph_metrics(entries: list[dict[str, Any]]) -> dict[str, float]:
    """Mean expected/forbidden/total constraints per scenario."""
    if not entries:
        return {"n": 0, "mean_expected": 0.0, "mean_forbidden": 0.0, "mean_total": 0.0}
    expected = [len(e["expected_actions"]) for e in entries]
    forbidden = [len(e["forbidden_actions"]) for e in entries]
    deadlines = [len(e.get("deadlines") or {}) for e in entries]
    totals = [a + b + c for a, b, c in zip(expected, forbidden, deadlines, strict=True)]
    return {
        "n": len(entries),
        "mean_expected": round(_safe_mean(expected), 2),
        "mean_forbidden": round(_safe_mean(forbidden), 2),
        "mean_total": round(_safe_mean(totals), 2),
    }


def _profile_dim_coverage(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Count distinct values seen per profile dimension across the entry set."""
    dims = ["age_group", "pregnancy", "comorbidity", "allergy", "severity", "special_state"]
    out: dict[str, int] = {}
    for d in dims:
        values: set[str] = set()
        for e in entries:
            prof = e.get("profile")
            if prof:
                values.add(prof[d])
        out[d] = len(values)
    return out


def _decompose_multiplicity(v6_entries: list[dict[str, Any]]) -> dict[str, float]:
    """Decompose v6 multiplicity into profile-driver buckets.

    Each scenario is assigned to the FIRST matching driver:
    - rare_special (anticoagulated, septic_shock, ...)
    - rare_pregnancy (pregnant, breastfeeding, ...)
    - rare_comorbidity (ckd, immunocompromised, ...)
    - common_comorbidity (diabetes/htn/asthma/cad/chf/copd)
    - severity_only (severity != unspecified, comorbidity == none)
    - age_only (age_group != adult, otherwise default)
    - default (everything unspecified)
    """
    buckets: dict[str, int] = collections.Counter()
    for e in v6_entries:
        p = e.get("profile") or {}
        if p.get("special_state") in RARE_SPECIAL:
            buckets["rare_special"] += 1
        elif p.get("pregnancy") in RARE_PREGNANCY:
            buckets["rare_pregnancy"] += 1
        elif p.get("comorbidity") in RARE_COMORBIDITY:
            buckets["rare_comorbidity"] += 1
        elif p.get("comorbidity") not in {"none", None}:
            buckets["common_comorbidity"] += 1
        elif p.get("severity") not in {"unspecified", None}:
            buckets["severity_only"] += 1
        elif p.get("age_group") not in {"adult", None}:
            buckets["age_only"] += 1
        else:
            buckets["default"] += 1
    total = sum(buckets.values())
    if not total:
        return dict.fromkeys(
            [
                "rare_special",
                "rare_pregnancy",
                "rare_comorbidity",
                "common_comorbidity",
                "severity_only",
                "age_only",
                "default",
            ],
            0.0,
        )
    return {k: round(v / total * 100.0, 2) for k, v in buckets.items()}


def _build_distribution_table(
    v6_by_graph: dict[str, list[dict[str, Any]]],
    v7_by_graph: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """One row per active core graph with v6/v7 counts + ratio."""
    rows: list[dict[str, Any]] = []
    for graph in ACTIVE_CORE_GRAPHS:
        v6 = v6_by_graph.get(graph, [])
        v7 = v7_by_graph.get(graph, [])
        v6_m = _per_graph_metrics(v6)
        v7_m = _per_graph_metrics(v7)
        v6_n = v6_m["n"]
        v7_n = v7_m["n"]
        ratio = round(v6_n / v7_n, 2) if v7_n else float("inf") if v6_n else 0.0
        rows.append(
            {
                "graph": graph,
                "v6_n": v6_n,
                "v7_n": v7_n,
                "ratio_v6_v7": ratio,
                "v6_mean_expected": v6_m["mean_expected"],
                "v7_mean_expected": v7_m["mean_expected"],
                "v6_mean_forbidden": v6_m["mean_forbidden"],
                "v7_mean_forbidden": v7_m["mean_forbidden"],
                "v6_mean_total": v6_m["mean_total"],
                "v7_mean_total": v7_m["mean_total"],
            }
        )
    return rows


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Persist 25-graph distribution table as CSV."""
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_report(
    rows: list[dict[str, Any]],
    sample_deepdive: dict[str, dict[str, Any]],
    decomposition: dict[str, float],
    catalog: dict[str, Any],
    path: Path,
) -> None:
    """Write the human-readable multi-graph parity markdown."""
    md: list[str] = []
    md += [
        "# v7 vs v6 Multi-Graph Parity Diagnosis",
        "",
        "## Snapshot reconciliation (vs prompt assumptions)",
        "",
        "| Metric | Prompt | Measured |",
        "|---|---|---|",
        (
            f"| Total v6 entries (manual + auto/) | 706 | "
            f"{sum(r['v6_n'] for r in rows)} (across 25 core; "
            f"total all = {catalog['metadata']['n_scenarios']}) |"
        ),
        (f"| kdigo_contrast_aki v6 | 28 | {next(r['v6_n'] for r in rows if r['graph'] == 'kdigo_contrast_aki')} |"),
        (f"| kdigo_contrast_aki v7 | 12 | {next(r['v7_n'] for r in rows if r['graph'] == 'kdigo_contrast_aki')} |"),
        f"| Total v7 entries (25 core) | 142 | {sum(r['v7_n'] for r in rows)} |",
        "",
        "All counts below are measured.",
        "",
        "## Sample 5-graph deep-dive",
        "",
        (
            "| Graph | v6 n | v7 n | Ratio | v6 mean exp | v7 mean exp | "
            "v6 mean forb | v7 mean forb | v6 dim cov | v7 dim cov |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for graph in SAMPLE_GRAPHS:
        d = sample_deepdive[graph]
        v6_cov = d["v6_dim_coverage"]
        v7_cov = d["v7_dim_coverage"]
        cov_v6 = "/".join(
            str(v6_cov[k]) for k in ["age_group", "pregnancy", "comorbidity", "allergy", "severity", "special_state"]
        )
        cov_v7 = "/".join(
            str(v7_cov[k]) for k in ["age_group", "pregnancy", "comorbidity", "allergy", "severity", "special_state"]
        )
        md.append(
            f"| `{graph}` | {d['v6_n']} | {d['v7_n']} | {d['ratio']} | "
            f"{d['v6_mean_expected']} | {d['v7_mean_expected']} | "
            f"{d['v6_mean_forbidden']} | {d['v7_mean_forbidden']} | "
            f"{cov_v6} | {cov_v7} |"
        )
    md += [
        "",
        "_dim coverage = age/preg/com/all/sev/special distinct value count_",
        "",
    ]
    md += [
        "## v6 multiplicity decomposition (across 25 core)",
        "",
        "| Driver | % of v6 entries |",
        "|---|---:|",
    ]
    for k in [
        "rare_special",
        "rare_pregnancy",
        "rare_comorbidity",
        "common_comorbidity",
        "severity_only",
        "age_only",
        "default",
    ]:
        md.append(f"| {k} | {decomposition.get(k, 0.0)}% |")
    md += [
        "",
        "_Each scenario assigned to first matching bucket; default = no profile cues._",
        "",
    ]
    sum_v6 = sum(r["v6_n"] for r in rows)
    sum_v7 = sum(r["v7_n"] for r in rows)
    avg_ratio = round(sum_v6 / sum_v7, 2) if sum_v7 else 0.0
    target_count = round(sum_v7 * avg_ratio)
    residual_factor = round(avg_ratio / 1.7, 2)
    cc = decomposition.get("common_comorbidity", 0.0)
    rs = decomposition.get("rare_special", 0.0)
    so = decomposition.get("severity_only", 0.0)
    rp = decomposition.get("rare_pregnancy", 0.0)
    rco = decomposition.get("rare_comorbidity", 0.0)
    df = decomposition.get("default", 0.0)
    md += [
        "## B-4 size target",
        "",
        f"- Total v6 (25 core): **{sum_v6}**",
        f"- Total v7 (25 core): **{sum_v7}**",
        f"- Aggregate ratio v6/v7: **{avg_ratio}x**",
        "",
        (
            "To match v6 multiplicity, B-4 patient profile expansion "
            f"should multiply {sum_v7} v7 scenarios by ~{avg_ratio} -> "
            f"**target ~{target_count} scenarios**."
        ),
        "",
        (f"After B-3 cluster loosening (expected ~1.7x), residual expansion factor for B-4: ~{residual_factor}x."),
        "",
        "Decomposition guidance:",
        (
            f"- ~{cc}% of v6 multiplicity = common comorbidity "
            "(diabetes/htn/asthma/cad/chf/copd) -- broad coverage required"
        ),
        (
            f"- ~{rs}% = rare special state "
            "(anticoagulated/septic_shock/intubated/on_steroids) "
            "-- high-value safety scenarios"
        ),
        (f"- ~{so}% = pure severity tiers (mild/mod/severe/critical) -- orthogonal to comorbidity axis"),
        (f"- ~{rp + rco}% = rare pregnancy + rare comorbidity (CKD/immunocomp/pregnancy)"),
        (
            f"- ~{df}% = default (no patient-state cue) -- dominated by "
            "simple atom-driven scenarios; v7 already covers this well"
        ),
        "",
        "## Full 25-core distribution",
        "",
        "| Graph | v6 n | v7 n | Ratio | v6 mean exp | v7 mean exp | v6 mean forb | v7 mean forb |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(rows, key=lambda x: -x["v6_n"]):
        md.append(
            f"| `{r['graph']}` | {r['v6_n']} | {r['v7_n']} | {r['ratio_v6_v7']} | "
            f"{r['v6_mean_expected']} | {r['v7_mean_expected']} | "
            f"{r['v6_mean_forbidden']} | {r['v7_mean_forbidden']} |"
        )
    # v7 >= v6 cases
    inversion_cases = [r for r in rows if r["v7_n"] and r["v7_n"] >= r["v6_n"]]
    md += [
        "",
        "### Cases where v7 ≥ v6 (atom proposer recall outpacing manual authoring)",
        "",
    ]
    if inversion_cases:
        for r in sorted(inversion_cases, key=lambda x: -(x["v7_n"] - x["v6_n"])):
            md.append(f"- `{r['graph']}`: v6={r['v6_n']} v7={r['v7_n']}")
    else:
        md.append("- (none)")
    md += [
        "",
        "### Cases where v6 ≫ v7 (gap concentrated)",
        "",
    ]
    big_gap = sorted(
        [r for r in rows if r["v6_n"] > r["v7_n"]],
        key=lambda x: -(x["v6_n"] - x["v7_n"]),
    )[:5]
    for r in big_gap:
        md.append(
            f"- `{r['graph']}`: v6={r['v6_n']} v7={r['v7_n']} gap={r['v6_n'] - r['v7_n']} ratio={r['ratio_v6_v7']}x"
        )
    md.append("")
    path.write_text("\n".join(md))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios-glob",
        default="configs/scenarios/*.yaml,configs/scenarios/auto/*.yaml",
    )
    parser.add_argument("--exclude-glob", default="configs/scenarios/auto_v2/*.yaml")
    parser.add_argument("--v7-root", default="sgsc_output/v7_e3_combined_overnight")
    parser.add_argument("--catalog", default="data/v6_patient_profile_catalog.json")
    parser.add_argument("--output-csv", default="reports/path_d_day2/v7_v6_per_graph_distribution.csv")
    parser.add_argument("--output-md", default="reports/path_d_day2/v7_v6_multi_graph_parity.md")
    args = parser.parse_args(argv)

    catalog = json.loads(Path(args.catalog).read_text())
    v6_entries = _load_v6_entries(args.scenarios_glob, args.exclude_glob)
    v6_by_graph: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for e in v6_entries:
        v6_by_graph[e["guideline_graph"]].append(e)
    v7_by_graph = _load_v7_entries(Path(args.v7_root))

    rows = _build_distribution_table(v6_by_graph, v7_by_graph)

    sample_deepdive: dict[str, dict[str, Any]] = {}
    for graph in SAMPLE_GRAPHS:
        v6 = v6_by_graph.get(graph, [])
        v7 = v7_by_graph.get(graph, [])
        v6_m = _per_graph_metrics(v6)
        v7_m = _per_graph_metrics(v7)
        v6_n = v6_m["n"]
        v7_n = v7_m["n"]
        sample_deepdive[graph] = {
            "v6_n": v6_n,
            "v7_n": v7_n,
            "ratio": round(v6_n / v7_n, 2) if v7_n else float("inf") if v6_n else 0.0,
            "v6_mean_expected": v6_m["mean_expected"],
            "v7_mean_expected": v7_m["mean_expected"],
            "v6_mean_forbidden": v6_m["mean_forbidden"],
            "v7_mean_forbidden": v7_m["mean_forbidden"],
            "v6_dim_coverage": _profile_dim_coverage(v6),
            "v7_dim_coverage": _profile_dim_coverage(
                [{"profile": categorize((e.get("patient") and {"patient": e.get("patient")}) or {})} for e in v7]
            ),
        }
    # Decompose multiplicity over v6 entries belonging to 25 core graphs only
    core_v6: list[dict[str, Any]] = []
    for graph in ACTIVE_CORE_GRAPHS:
        core_v6.extend(v6_by_graph.get(graph, []))
    decomposition = _decompose_multiplicity(core_v6)

    Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, Path(args.output_csv))
    _write_report(rows, sample_deepdive, decomposition, catalog, Path(args.output_md))

    sum_v6 = sum(r["v6_n"] for r in rows)
    sum_v7 = sum(r["v7_n"] for r in rows)
    avg_ratio = round(sum_v6 / sum_v7, 2) if sum_v7 else 0.0
    inversion = [r["graph"] for r in rows if r["v7_n"] and r["v7_n"] >= r["v6_n"]]
    print(f"B-2 PARITY -- 25 core: v6={sum_v6} v7={sum_v7} ratio={avg_ratio}x; v7>=v6 graphs: {inversion or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
