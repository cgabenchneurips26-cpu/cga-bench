#!/usr/bin/env python3
"""Extract patient profile catalog from v6 manual scenario YAMLs.

Walks ``configs/scenarios/*.yaml`` and ``configs/scenarios/auto/*.yaml``,
parses ``scenarios.<id>`` entries, categorizes each into 6 profile
dimensions, and emits a JSON catalog plus a markdown report.

Skips ``configs/scenarios/auto_v2/`` per Track-B prompt constraints.

Usage:
    PYTHONPATH=. python scripts/sgsc/extract_v6_profiles.py \
        --output-json data/v6_patient_profile_catalog.json \
        --output-md reports/path_d_day2/v6_profile_extraction.md
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
from pathlib import Path
import re
from typing import Any

import yaml

# Dimension thresholds
NEONATE_DAYS = 28
PEDIATRIC_AGE_MAX = 18
ADULT_AGE_MAX = 64
SEVERE_MAP_THRESHOLD = 65
CRITICAL_MAP_THRESHOLD = 60
SEVERE_SBP_THRESHOLD = 90
CRITICAL_SBP_THRESHOLD = 80
CRITICAL_SPO2_THRESHOLD = 88
TOP_15 = 15
TOP_15_COVERAGE_GATE = 60.0
PER_GRAPH_TOP_PROFILES = 5

# Comorbidity / context patterns
CKD_PAT = re.compile(r"\b(ckd|chronic[\s_]kidney|esrd|end[\s_-]stage[\s_-]renal)\b", re.I)
DIABETES_PAT = re.compile(r"\b(diabetes|t2dm|t1dm|dka)\b", re.I)
HYPERTENSION_PAT = re.compile(r"\b(hypertension|htn)\b", re.I)
CAD_PAT = re.compile(r"\b(cad|coronary[\s_]artery|prior[\s_]mi|post[\s_]mi)\b", re.I)
CHF_PAT = re.compile(r"\b(chf|heart[\s_]failure|hfref|hfpef|cardiomyopathy)\b", re.I)
COPD_PAT = re.compile(r"\b(copd|emphysema|chronic[\s_]bronchitis)\b", re.I)
ASTHMA_PAT = re.compile(r"\basthma\b", re.I)
IMMUNOCOMP_PAT = re.compile(r"\b(immunocomp|hiv|aids|chemo|transplant|neutropenic|leukemia|lymphoma)\b", re.I)
PREGNANCY_RELATED_PAT = re.compile(r"\b(pregnan|gestation|antepartum|postpartum|peripartum|eclampsia|hellp)\b", re.I)

# Pregnancy patterns
PREGNANT_PAT = re.compile(r"\b(pregnan(t|cy)|gestation(al)?|antepartum|gravid)\b", re.I)
BREASTFEEDING_PAT = re.compile(r"\b(breastfeed|lactating|nursing)\b", re.I)
POSTPARTUM_PAT = re.compile(r"\b(postpartum|puerper)\b", re.I)

# Allergy patterns
PENICILLIN_PAT = re.compile(r"\b(penicillin|pcn|amoxicil|ampicil|cephalosporin)\b", re.I)
SULFA_PAT = re.compile(r"\b(sulfa|sulfonamide|tmp[-_/]?smx|bactrim)\b", re.I)
CONTRAST_PAT = re.compile(r"\b(contrast|iodinated)\b", re.I)
ASPIRIN_PAT = re.compile(r"\b(aspirin|asa)[-_\s]allerg", re.I)
LATEX_PAT = re.compile(r"\blatex\b", re.I)

# Special-state patterns
ANTICOAG_PAT = re.compile(
    r"\b(warfarin|coumadin|apixaban|rivaroxaban|dabigatran|edoxaban|"
    r"heparin|enoxaparin|lovenox|noac|doac|anticoagul)\b",
    re.I,
)
STEROID_PAT = re.compile(
    r"\b(prednisone|prednisolone|methylpred|dexamethasone|hydrocortisone|"
    r"chronic[\s_]steroid|long[\s_-]term[\s_-]steroid)\b",
    re.I,
)
INTUBATED_PAT = re.compile(r"\b(intubated|ventilator|mechanical[\s_]ventilation)\b", re.I)
SEPTIC_SHOCK_PAT = re.compile(r"\bseptic[\s_]shock\b", re.I)

# Severity patterns
LIFE_THREAT_PAT = re.compile(r"life[\s_-]threatening|catastrophic|fulminant", re.I)
CRITICAL_KW_PAT = re.compile(r"\b(critical|septic[\s_]shock|cardiogenic[\s_]shock)\b", re.I)
SEVERE_KW_PAT = re.compile(r"\b(severe|status[\s_]epilepticus)\b", re.I)
MODERATE_KW_PAT = re.compile(r"\bmoderate\b", re.I)
MILD_KW_PAT = re.compile(r"\bmild\b", re.I)


def _categorize_age(age: int | float | str | None) -> str:
    """Bucket age (years) into neonate/pediatric/adult/elderly/unspecified."""
    if age is None:
        return "unspecified"
    try:
        a = float(age)
    except (TypeError, ValueError):
        return "unspecified"
    if a < 1 and a * 365 < NEONATE_DAYS:
        return "neonate"
    if a < PEDIATRIC_AGE_MAX:
        return "pediatric"
    if a <= ADULT_AGE_MAX:
        return "adult"
    return "elderly"


def _categorize_pregnancy(blob: str) -> str:
    """Detect pregnancy state from narrative blob (priority order)."""
    if BREASTFEEDING_PAT.search(blob):
        return "breastfeeding"
    if POSTPARTUM_PAT.search(blob):
        return "postpartum"
    if PREGNANT_PAT.search(blob):
        return "pregnant"
    return "none"


def _categorize_comorbidity(blob: str) -> str:
    """Return dominant comorbidity bucket (priority-ordered)."""
    if PREGNANCY_RELATED_PAT.search(blob):
        return "pregnancy_related"
    if IMMUNOCOMP_PAT.search(blob):
        return "immunocompromised"
    if CKD_PAT.search(blob):
        return "ckd"
    if CHF_PAT.search(blob):
        return "chf"
    if CAD_PAT.search(blob):
        return "cad"
    if COPD_PAT.search(blob):
        return "copd"
    if ASTHMA_PAT.search(blob):
        return "asthma"
    if DIABETES_PAT.search(blob):
        return "diabetes"
    if HYPERTENSION_PAT.search(blob):
        return "hypertension"
    return "none"


def _categorize_allergy(allergies: list[Any], blob: str) -> str:
    """Detect allergy from explicit ``allergies`` list + narrative blob."""
    haystack = " ".join(str(x) for x in (allergies or [])) + " " + blob
    matches: list[str] = []
    if PENICILLIN_PAT.search(haystack):
        matches.append("penicillin")
    if SULFA_PAT.search(haystack):
        matches.append("sulfa")
    if CONTRAST_PAT.search(haystack):
        matches.append("contrast")
    if ASPIRIN_PAT.search(haystack):
        matches.append("aspirin")
    if LATEX_PAT.search(haystack):
        matches.append("latex")
    if not matches:
        return "none"
    if len(matches) >= 2:
        return "multiple"
    return matches[0]


def _vital_severity(vitals: dict[str, Any]) -> str | None:
    """Classify severity from vital signs alone, returning None if uninformative."""
    if not isinstance(vitals, dict):
        return None
    map_ = vitals.get("map_mmhg")
    sbp = vitals.get("blood_pressure_systolic") or vitals.get("sbp")
    spo2 = vitals.get("oxygen_saturation") or vitals.get("spo2")
    try:
        if map_ is not None and float(map_) < CRITICAL_MAP_THRESHOLD:
            return "critical"
        if sbp is not None and float(sbp) < CRITICAL_SBP_THRESHOLD:
            return "critical"
        if spo2 is not None and float(spo2) < CRITICAL_SPO2_THRESHOLD:
            return "critical"
        if map_ is not None and float(map_) < SEVERE_MAP_THRESHOLD:
            return "severe"
        if sbp is not None and float(sbp) < SEVERE_SBP_THRESHOLD:
            return "severe"
    except (TypeError, ValueError):
        return None
    return None


def _categorize_severity(vitals: dict[str, Any], blob: str) -> str:
    """Combine narrative keywords + vital-sign thresholds."""
    if LIFE_THREAT_PAT.search(blob):
        return "life_threatening"
    if CRITICAL_KW_PAT.search(blob):
        return "critical"
    vital_class = _vital_severity(vitals)
    if vital_class:
        return vital_class
    if SEVERE_KW_PAT.search(blob):
        return "severe"
    if MODERATE_KW_PAT.search(blob):
        return "moderate"
    if MILD_KW_PAT.search(blob):
        return "mild"
    return "unspecified"


def _categorize_special_state(blob: str, medications: list[Any]) -> str:
    """Detect special clinical state (anticoag/steroids/intubated/septic_shock)."""
    haystack = blob + " " + " ".join(str(m) for m in (medications or []))
    if SEPTIC_SHOCK_PAT.search(haystack):
        return "septic_shock"
    if INTUBATED_PAT.search(haystack):
        return "intubated"
    if ANTICOAG_PAT.search(haystack):
        return "anticoagulated"
    if STEROID_PAT.search(haystack):
        return "on_steroids"
    return "none"


def _build_blob(scenario: dict[str, Any]) -> str:
    """Concatenate all profile-relevant text for keyword scanning."""
    p = scenario.get("patient") or {}
    parts = [
        scenario.get("description") or "",
        scenario.get("scenario_id") or "",
        p.get("chief_complaint") or "",
        p.get("working_diagnosis") or "",
        " ".join(str(c) for c in (p.get("comorbidities") or [])),
        " ".join(str(a) for a in (p.get("allergies") or [])),
        " ".join(str(c) for c in (p.get("contraindications") or [])),
        " ".join(str(m) for m in (p.get("current_medications") or p.get("medications") or [])),
        " ".join(str(h) for h in (p.get("history") or [])),
    ]
    return " ".join(parts)


def categorize(scenario: dict[str, Any]) -> dict[str, str]:
    """Categorize a single scenario into the 6-dimension profile."""
    p = scenario.get("patient") or {}
    blob = _build_blob(scenario)
    vitals = p.get("vitals") or {}
    medications = p.get("current_medications") or p.get("medications") or []
    return {
        "age_group": _categorize_age(p.get("age")),
        "pregnancy": _categorize_pregnancy(blob),
        "comorbidity": _categorize_comorbidity(blob),
        "allergy": _categorize_allergy(p.get("allergies") or [], blob),
        "severity": _categorize_severity(vitals, blob),
        "special_state": _categorize_special_state(blob, medications),
    }


def _gather_files(scenarios_glob: str, exclude_glob: str) -> list[str]:
    """Resolve include/exclude globs (comma-separated) to a deterministic file list."""
    files: list[str] = []
    for pat in scenarios_glob.split(","):
        files.extend(sorted(glob.glob(pat.strip())))
    excludes: set[str] = set()
    for pat in exclude_glob.split(","):
        if pat.strip():
            excludes.update(glob.glob(pat.strip()))
    seen: set[str] = set()
    out: list[str] = []
    for f in files:
        if f in excludes or f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


def _walk_entries(files: list[str]) -> list[dict[str, Any]]:
    """Walk YAMLs and emit one entry per ``scenarios.<id>`` element."""
    entries: list[dict[str, Any]] = []
    for f in files:
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
                    "file": f,
                    "guideline_graph": s.get("guideline_graph", "<unknown>"),
                    "profile": categorize(s),
                }
            )
    return entries


def _combo_name(age: str, preg: str, com: str, sev: str) -> str:
    """Build a stable, readable name from a 4-tuple combination."""
    parts = [age]
    if preg != "none":
        parts.append(preg)
    if com != "none":
        parts.append(com)
    if sev != "unspecified":
        parts.append(sev)
    return "_".join(parts) if parts else "uncategorized"


def _build_combinations(entries: list[dict[str, Any]], top_n: int) -> tuple[list[dict[str, Any]], collections.Counter]:
    """Rank profile combinations by frequency; return top-N entries + full counter."""
    counter: collections.Counter[tuple[str, str, str, str]] = collections.Counter()
    examples: dict[tuple[str, str, str, str], list[str]] = {}
    for e in entries:
        p = e["profile"]
        key = (p["age_group"], p["pregnancy"], p["comorbidity"], p["severity"])
        counter[key] += 1
        examples.setdefault(key, []).append(e["scenario_id"])
    out: list[dict[str, Any]] = []
    for key, n in counter.most_common(top_n):
        age, preg, com, sev = key
        out.append(
            {
                "name": _combo_name(age, preg, com, sev),
                "n_scenarios": n,
                "dimensions": {
                    "age_group": age,
                    "pregnancy": preg,
                    "comorbidity": com,
                    "severity": sev,
                },
                "example_scenario_ids": examples.get(key, [])[:3],
            }
        )
    return out, counter


def _build_graph_distribution(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-graph scenario count + top-5 profile combinations within each graph."""
    per_graph: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for e in entries:
        per_graph[e["guideline_graph"]].append(e)
    out: dict[str, dict[str, Any]] = {}
    for graph_id, ents in per_graph.items():
        local: collections.Counter[tuple[str, str, str, str]] = collections.Counter()
        for e in ents:
            p = e["profile"]
            local[(p["age_group"], p["pregnancy"], p["comorbidity"], p["severity"])] += 1
        top_profiles = [{"name": _combo_name(*key), "n": n} for key, n in local.most_common(PER_GRAPH_TOP_PROFILES)]
        out[graph_id] = {"n_scenarios": len(ents), "top_profiles": top_profiles}
    return out


def _build_dimensions(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per-dimension frequency table sorted by count desc."""
    dims = ["age_group", "pregnancy", "comorbidity", "allergy", "severity", "special_state"]
    out: dict[str, dict[str, int]] = {}
    for d in dims:
        c = collections.Counter(e["profile"][d] for e in entries)
        out[d] = dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))
    return out


def _format_report(
    catalog: dict[str, Any],
    counter: collections.Counter,
    top15_pct: float,
    top_n: int,
) -> str:
    """Render markdown report from catalog dict."""
    md: list[str] = ["# v6 Patient Profile Catalog Extraction", ""]
    meta = catalog["metadata"]
    md += [
        "## Snapshot reconciliation",
        "",
        "| Metric | Prompt assumption | Measured |",
        "|---|---|---|",
        f"| YAML files (excl. auto_v2) | 706 (file count) | {meta['n_yaml_files']} |",
        f"| `scenarios.*` entries | 706 | {meta['n_scenarios']} |",
        "",
        "> Prompt assumed n=706. Measured entry count is reported above; "
        "the underlying YAML pool grew between prompt drafting and now. "
        "All downstream tasks use measured counts.",
        "",
        "## Dimensions",
        "",
    ]
    for d, freq in catalog["dimensions"].items():
        md.append(f"### {d}")
        md.append("")
        md.append("| Value | Count |")
        md.append("|---|---|")
        for v, c in freq.items():
            md.append(f"| {v} | {c} |")
        md.append("")
    gate_status = "PASS" if top15_pct >= TOP_15_COVERAGE_GATE else f"WARNING (< {TOP_15_COVERAGE_GATE}%)"
    md.append(f"## Top {top_n} profile combinations")
    md.append("")
    md.append(f"Top-15 coverage: **{top15_pct:.1f}%** of {meta['n_scenarios']} scenarios — {gate_status}")
    md.append("")
    md.append("| # | Name | Count | Examples |")
    md.append("|---|---|---|---|")
    for i, c in enumerate(catalog["profile_combinations"], 1):
        examples = ", ".join(c["example_scenario_ids"][:2])
        md.append(f"| {i} | `{c['name']}` | {c['n_scenarios']} | {examples} |")
    md.append("")
    md.append("## Per-graph distribution (top 30 by count)")
    md.append("")
    md.append("| Graph | n | Top profile |")
    md.append("|---|---|---|")
    sorted_graphs = sorted(
        catalog["graph_distribution"].items(),
        key=lambda x: -x[1]["n_scenarios"],
    )[:30]
    for g, info in sorted_graphs:
        top_name = info["top_profiles"][0]["name"] if info["top_profiles"] else "—"
        md.append(f"| {g} | {info['n_scenarios']} | `{top_name}` |")
    md.append("")
    md.append(f"_Total distinct guideline_graph values: {len(catalog['graph_distribution'])}_")
    md.append("")
    return "\n".join(md)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios-glob",
        default="configs/scenarios/*.yaml,configs/scenarios/auto/*.yaml",
        help="comma-separated glob patterns for input YAMLs",
    )
    parser.add_argument(
        "--exclude-glob",
        default="configs/scenarios/auto_v2/*.yaml",
        help="comma-separated glob patterns to exclude",
    )
    parser.add_argument(
        "--output-json",
        default="data/v6_patient_profile_catalog.json",
        help="output catalog JSON path",
    )
    parser.add_argument(
        "--output-md",
        default="reports/path_d_day2/v6_profile_extraction.md",
        help="output markdown report path",
    )
    parser.add_argument("--top-n", type=int, default=20, help="top-N profile combinations to emit")
    args = parser.parse_args(argv)

    files = _gather_files(args.scenarios_glob, args.exclude_glob)
    entries = _walk_entries(files)
    if not entries:
        print("ERROR: no scenarios.* entries found")
        return 1
    dimensions = _build_dimensions(entries)
    profile_combinations, counter = _build_combinations(entries, args.top_n)
    graph_distribution = _build_graph_distribution(entries)
    top15_count = sum(c for _, c in counter.most_common(TOP_15))
    top15_pct = top15_count / len(entries) * 100.0
    catalog = {
        "metadata": {
            "n_yaml_files": len(files),
            "n_scenarios": len(entries),
            "extraction_date": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "scenarios_glob": args.scenarios_glob,
            "exclude_glob": args.exclude_glob,
            "top_15_coverage_pct": round(top15_pct, 2),
            "prompt_expectation_note": "Prompt assumed n=706; measured value reported above.",
        },
        "dimensions": dimensions,
        "profile_combinations": profile_combinations,
        "graph_distribution": graph_distribution,
    }
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(json.dumps(catalog, indent=2, sort_keys=True))
    Path(args.output_md).write_text(_format_report(catalog, counter, top15_pct, args.top_n))
    print(
        f"B-1 EXTRACT — {len(entries)} entries from {len(files)} files; "
        f"6 dimensions; top-15 covers {top15_pct:.1f}% "
        f"({'PASS' if top15_pct >= TOP_15_COVERAGE_GATE else 'WARNING'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
