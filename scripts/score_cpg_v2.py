"""CPG Selection Criteria v2 — C1-C12 Source-Document Scoring Script.

Scores all CPG graphs against the 12-criterion 3-Axis framework.
All criteria measure properties of the PUBLISHED CPG source document,
NOT properties of our YAML encoding. This eliminates circular reasoning.

Axis 1 — Trustworthiness (C1-C5, max 7):
  C1  Tier-1 society (0/1)
  C2  Evidence grading system (0/1/2)
  C3  Systematic review (0/1)
  C4  Recency (0/1/2)
  C5  DOI/URL/ISBN (0/1)

Axis 2 — Clinical Significance (C6-C8, max 6):
  C6  GBD disease burden (0/1/2)
  C7  Time-to-harm severity (0/1/2)
  C8  Contraindication rules explicit in source (0/1/2)

Axis 3 — Formalizability (C9-C12, max 6):
  C9  Algorithm/flowchart in source document (0/1/2)
  C10 Time constraints explicit in source text (0/1/2)
  C11 Sequence dependency explicit in source text (0/1)
  C12 Conditional branching explicit in source text (0/1)

Usage:
    PYTHONPATH=. python scripts/score_cpg_v2.py
    PYTHONPATH=. python scripts/score_cpg_v2.py --graphs-dir cpg_model/graphs --output-dir reports
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIER_1_SOCIETIES: set[str] = {
    # Cardiology
    "AHA",
    "ACC",
    "HRS",
    "ESC",
    "ESVS",
    "ERC",
    # Nephrology
    "KDIGO",
    "UKKA",
    "ERA",
    # Infectious / Global
    "IDSA",
    "WHO",
    "CDC",
    "SSC",
    # Pulmonary
    "ATS",
    "ERS",
    "GOLD",
    "GINA",
    "BTS",
    "DAS",
    # GI / Hepatology
    "ACG",
    "AGA",
    "AASLD",
    # Surgery / Trauma
    "ACS",
    "EAST",
    "WSES",
    "ABA",
    "ISBI",
    # Endocrinology
    "ADA",
    "ATA",
    "AACE",
    "ISPAD",
    "EASD",
    "JTA",
    "JES",
    # Obstetrics
    "ACOG",
    "SMFM",
    "RCOG",
    # Pediatrics
    "AAP",
    # Psychiatry
    "APA",
    # Hematology / Transfusion
    "AABB",
    "ASH",
    # Neurology
    "AAN",
    "ILAE",
    "NCS",
    "AES",
    # Resuscitation
    "ILCOR",
    # Allergy
    "WAO",
    "AAAAI",
    "EAACI",
    # Toxicology
    "AACT",
    "ACMT",
    "EAPCCT",
}

# Recognized formal evidence grading systems (score=2)
FORMAL_EVIDENCE_SYSTEMS: set[str] = {
    "GRADE",
    "SIGN",
    "OCEBM",
    "OXFORD CEBM",
    "ILCOR",
    "COCHRANE",
    "NHMRC",
}

# Society-specific grading systems that are structured but not GRADE (score=1)
SOCIETY_EVIDENCE_SYSTEMS: set[str] = {
    "AHA CLASS/LOE",
    "ESC CLASS/LOE",
    "ADA EVIDENCE GRADING",
    "ACOG LOE",
    "GINA EVIDENCE LEVELS",
    "GOLD EVIDENCE LEVELS",
}

# Time-to-harm severity for all 25 graphs (expert-assigned from source text)
TIME_TO_HARM_MAP: dict[str, str] = {
    "ssc_sepsis_hour1_bundle": "critical",
    "aha_chest_pain_evaluation": "critical",
    "aha_stroke_2019": "critical",
    "acls_cardiac_arrest": "critical",
    "status_epilepticus": "critical",
    "anaphylaxis_management": "critical",
    "gi_bleeding": "critical",
    "hypertensive_emergency": "critical",
    "pulmonary_embolism": "critical",
    "idsa_meningitis": "critical",
    "aba_burn_resuscitation": "critical",
    "acog_obstetric_hemorrhage": "critical",
    "pals_pediatric_emergency": "critical",
    "toxicology_management": "critical",
    "aha_heart_failure_2022": "moderate",
    "ada_dka_management": "moderate",
    "cap_pneumonia": "moderate",
    "kdigo_aki_full": "moderate",
    "kdigo_contrast_aki": "moderate",
    "copd_exacerbation": "moderate",
    "gina_asthma_exacerbation": "moderate",
    "aabb_transfusion": "moderate",
    "apa_agitation_management": "moderate",
    "atrial_fibrillation": "mild",
    "universal_clinical_safety": "mild",
}

# Tier classification thresholds (total 0-19)
TIER_S_MIN = 15
TIER_A_MIN = 11
TIER_B_MIN = 7


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_graph(path: Path) -> dict[str, Any]:
    """Load a single CPG YAML graph."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_gbd_table(path: Path) -> dict[str, Any]:
    """Load the GBD lookup table."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_source_properties(path: Path) -> dict[str, Any]:
    """Load the expert-annotated source-document properties table."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("graphs", {})


# ---------------------------------------------------------------------------
# Year extraction (5-level cascade for C4)
# ---------------------------------------------------------------------------

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def extract_year(graph: dict[str, Any]) -> int | None:
    """Extract publication year from graph metadata using 5-level cascade.

    Priority:
    1. metadata.publication_year
    2. metadata.primary_source.year
    3. version field regex
    4. guideline_name regex
    5. metadata.source regex
    """
    meta = graph.get("metadata", {}) or {}

    # Level 1: explicit publication_year
    pub_year = meta.get("publication_year")
    if pub_year is not None:
        return int(pub_year)

    # Level 2: primary_source.year
    primary = meta.get("primary_source") or {}
    if isinstance(primary, dict):
        src_year = primary.get("year")
        if src_year is not None:
            return int(src_year)

    # Level 3: version field regex
    version = str(graph.get("version", ""))
    m = _YEAR_RE.search(version)
    if m:
        return int(m.group(0))

    # Level 4: guideline_name regex
    name = graph.get("guideline_name", "")
    m = _YEAR_RE.search(str(name))
    if m:
        return int(m.group(0))

    # Level 5: metadata.source regex
    source = meta.get("source", "")
    m = _YEAR_RE.search(str(source))
    if m:
        return int(m.group(0))

    return None


# ---------------------------------------------------------------------------
# C1-C5: Axis 1 — Trustworthiness (max 7)
# ---------------------------------------------------------------------------


def score_c1(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C1: Tier-1 society issuance (0/1).

    Source: CPG cover page / publisher field.
    """
    # Priority 1: source properties lookup
    if props and props.get("c1_tier1_society") is not None:
        return 1 if props["c1_tier1_society"] else 0

    # Fallback: check YAML metadata text for known society names
    meta = graph.get("metadata", {}) or {}
    name = graph.get("guideline_name", "")
    source = meta.get("source", "")
    publisher = meta.get("publisher", "")
    text = f"{name} {source} {publisher}".upper()
    return 1 if any(s in text for s in TIER_1_SOCIETIES) else 0


def score_c2(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C2: Evidence grading system used (0/1/2).

    Source: CPG Methods section.
    2 = formal system (GRADE, SIGN, OCEBM, ILCOR, Cochrane, NHMRC)
    1 = society-specific system (AHA Class/LOE, ADA A/B/C/E, etc.)
    0 = none / unknown
    """
    # Priority 1: source properties lookup (pre-computed score)
    if props and props.get("c2_evidence_system_score") is not None:
        return int(props["c2_evidence_system_score"])

    # Priority 2: source properties with system name
    if props and props.get("c2_evidence_system"):
        sys_name = str(props["c2_evidence_system"]).upper()
        if any(fs in sys_name for fs in FORMAL_EVIDENCE_SYSTEMS):
            return 2
        if any(ss in sys_name for ss in SOCIETY_EVIDENCE_SYSTEMS):
            return 1
        return 1  # has a named system -> at least 1

    # Fallback: check YAML metadata
    meta = graph.get("metadata", {}) or {}
    rec_sys = str(meta.get("recommendation_system", "")).upper()
    meta_text = json.dumps(meta).upper()

    if any(fs in rec_sys or fs in meta_text for fs in FORMAL_EVIDENCE_SYSTEMS):
        return 2
    if any(ss in rec_sys or ss in meta_text for ss in SOCIETY_EVIDENCE_SYSTEMS):
        return 1
    return 0


def score_c3(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C3: Systematic review performed (0/1).

    Source: CPG Methods section.
    """
    # Priority 1: source properties lookup
    if props and props.get("c3_systematic_review") is not None:
        return 1 if props["c3_systematic_review"] else 0

    # Fallback: YAML metadata
    meta = graph.get("metadata", {}) or {}
    has_sr = meta.get("has_systematic_review")
    if has_sr is not None:
        return 1 if has_sr else 0

    return 0


def score_c4(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C4: Recency (0/1/2).

    Source: Publication year from CPG document.
    2 = year >= 2020
    1 = 2015-2019
    0 = < 2015 or unknown
    """
    year = None

    # Priority 1: source properties
    if props:
        y = props.get("c4_recency_year") or props.get("publication_year")
        if y is not None:
            year = int(y)

    # Priority 2: YAML metadata last_update_year
    if year is None:
        meta = graph.get("metadata", {}) or {}
        last_update = meta.get("last_update_year")
        if last_update is not None:
            year = int(last_update)

    # Priority 3: year extraction cascade
    if year is None:
        year = extract_year(graph)

    if year is None:
        return 0
    if year >= 2020:
        return 2
    if year >= 2015:
        return 1
    return 0


def score_c5(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C5: DOI/URL/ISBN exists (0/1).

    Source: CPG bibliography / reference.
    """
    # Priority 1: source properties
    if props and props.get("c5_has_doi") is not None:
        return 1 if props["c5_has_doi"] else 0

    # Fallback: YAML metadata
    meta = graph.get("metadata", {}) or {}
    has_doi = bool(meta.get("doi"))
    has_url = bool(meta.get("source_url"))
    has_isbn = bool(meta.get("isbn"))
    primary = meta.get("primary_source") or {}
    if isinstance(primary, dict):
        has_doi = has_doi or bool(primary.get("doi"))
    return 1 if (has_doi or has_url or has_isbn) else 0


# ---------------------------------------------------------------------------
# C6-C8: Axis 2 — Clinical Significance (max 6)
# ---------------------------------------------------------------------------


def score_c6(graph: dict[str, Any], gbd_table: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C6: GBD disease burden (0/1/2).

    Source: WHO GBD 2021 + ICD-10 mapping.
    2 = GBD Top-15 death OR emergency condition
    1 = GBD Top-16-30
    0 = not ranked

    Priority order:
    1. ``props.c6_score`` (explicit reviewer-annotated value)
    2. GBD table lookup by graph_id
    3. Metadata fallback (is_emergency_condition)
    """
    # Priority 1: explicit annotation
    if props and props.get("c6_score") is not None:
        return int(props["c6_score"])

    # Priority 2: GBD table lookup
    graph_id = graph.get("graph_id", "")
    mapping = gbd_table.get("graph_id_mapping", {})
    entry = mapping.get(graph_id)
    if entry is not None:
        # GBD table uses m10_score key (legacy name); same semantics as c6
        return entry.get("m10_score", 0)

    # Fallback: metadata
    meta = graph.get("metadata", {}) or {}
    if meta.get("is_emergency_condition"):
        return 2
    death_rank = meta.get("gbd_rank_death")
    if death_rank is not None and int(death_rank) <= 15:
        return 2
    daly_rank = meta.get("gbd_rank_daly")
    if daly_rank is not None and int(daly_rank) <= 15:
        return 2
    if (death_rank is not None and int(death_rank) <= 30) or (daly_rank is not None and int(daly_rank) <= 30):
        return 1
    return 0


def score_c7(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C7: Time-to-harm severity (0/1/2).

    Source: CPG recommendation text describing urgency.
    2 = critical (minutes-to-hours; delay causes death/permanent disability)
    1 = moderate (hours-to-days; delay increases morbidity)
    0 = mild (days-to-weeks; limited acute impact)
    """
    graph_id = graph.get("graph_id", "")

    # Priority 1: source properties
    if props and props.get("c7_time_to_harm"):
        severity = props["c7_time_to_harm"]
    else:
        # Priority 2: YAML metadata
        meta = graph.get("metadata", {}) or {}
        severity = meta.get("time_to_harm_severity")
        # Priority 3: hardcoded map
        if severity is None:
            severity = TIME_TO_HARM_MAP.get(graph_id, "mild")

    return {"critical": 2, "moderate": 1, "mild": 0}.get(str(severity).lower(), 0)


def score_c8(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C8: Contraindication/safety rules explicit in source text (0/1/2).

    Source: CPG text (contraindication sections, safety warnings).
    2 = multiple explicit contraindications documented (>=5 distinct rules)
    1 = some contraindications (2-4 rules)
    0 = minimal or none
    """
    # Priority 1: source properties (expert-annotated)
    if props and props.get("c8_contraindication_explicit") is not None:
        return int(props["c8_contraindication_explicit"])

    # No YAML fallback — this criterion deliberately avoids counting
    # YAML forbidden_actions to prevent circular reasoning.
    return 0


# ---------------------------------------------------------------------------
# C9-C12: Axis 3 — Formalizability (max 6)
# ---------------------------------------------------------------------------


def score_c9(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C9: Algorithm/flowchart in source document (0/1/2).

    Source: CPG figures/appendices.
    2 = formal algorithm figure with >=3 decision points
    1 = simple flowchart or table-based algorithm
    0 = no algorithm/flowchart
    """
    if props and props.get("c9_score") is not None:
        return int(props["c9_score"])

    if props and props.get("c9_has_algorithm_figure") is not None:
        if not props["c9_has_algorithm_figure"]:
            return 0
        fig_count = props.get("c9_figure_count", 1)
        return 2 if fig_count >= 3 else 1

    # No YAML fallback — source-document property only
    return 0


def score_c10(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C10: Time constraints explicit in source text (0/1/2).

    Source: CPG recommendation text ("within X minutes/hours").
    2 = >=3 distinct time-bound statements
    1 = 1-2 time-bound statements
    0 = no explicit time constraints
    """
    if props and props.get("c10_score") is not None:
        return int(props["c10_score"])

    if props and props.get("c10_time_constraints_explicit") is not None:
        if not props["c10_time_constraints_explicit"]:
            return 0
        count = props.get("c10_time_statements_count", 1)
        return 2 if count >= 3 else 1

    # No YAML fallback — source-document property only
    return 0


def score_c11(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C11: Sequence dependency explicit in source text (0/1).

    Source: CPG text stating "X before Y" or "X prior to Y".
    """
    if props and props.get("c11_sequence_dependency_explicit") is not None:
        return 1 if props["c11_sequence_dependency_explicit"] else 0

    # No YAML fallback — source-document property only
    return 0


def score_c12(graph: dict[str, Any], props: dict[str, Any] | None = None) -> int:
    """C12: Conditional branching explicit in source text (0/1).

    Source: CPG text stating "if X then Y" or pathway divergence.
    """
    if props and props.get("c12_conditional_branching_explicit") is not None:
        return 1 if props["c12_conditional_branching_explicit"] else 0

    # No YAML fallback — source-document property only
    return 0


# ---------------------------------------------------------------------------
# Score aggregation and tier classification
# ---------------------------------------------------------------------------


def compute_all_scores(
    graph: dict[str, Any],
    gbd_table: dict[str, Any],
    props: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Compute all 12 criterion scores for a graph."""
    return {
        "C1": score_c1(graph, props),
        "C2": score_c2(graph, props),
        "C3": score_c3(graph, props),
        "C4": score_c4(graph, props),
        "C5": score_c5(graph, props),
        "C6": score_c6(graph, gbd_table, props),
        "C7": score_c7(graph, props),
        "C8": score_c8(graph, props),
        "C9": score_c9(graph, props),
        "C10": score_c10(graph, props),
        "C11": score_c11(graph, props),
        "C12": score_c12(graph, props),
    }


def compute_axes(scores: dict[str, int]) -> dict[str, Any]:
    """Compute 3-axis breakdown and total.

    Axis 1 Trustworthiness:       C1 + C2 + C3 + C4 + C5  (max 7)
    Axis 2 Clinical Significance: C6 + C7 + C8             (max 6)
    Axis 3 Formalizability:       C9 + C10 + C11 + C12     (max 6)
    Total: 0-19
    """
    axis1 = scores["C1"] + scores["C2"] + scores["C3"] + scores["C4"] + scores["C5"]
    axis2 = scores["C6"] + scores["C7"] + scores["C8"]
    axis3 = scores["C9"] + scores["C10"] + scores["C11"] + scores["C12"]
    total = axis1 + axis2 + axis3
    return {
        "axis1_trustworthiness": axis1,
        "axis1_max": 7,
        "axis2_clinical": axis2,
        "axis2_max": 6,
        "axis3_formalizability": axis3,
        "axis3_max": 6,
        "total": total,
        "total_max": 19,
    }


def classify_tier(total: int) -> str:
    """Classify into tier based on total score."""
    if total >= TIER_S_MIN:
        return "S"
    if total >= TIER_A_MIN:
        return "A"
    if total >= TIER_B_MIN:
        return "B"
    return "Excluded"


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def score_all_graphs(
    graphs_dir: Path,
    gbd_path: Path,
    source_props_path: Path | None = None,
    candidate_props_paths: list[Path] | None = None,
) -> list[dict[str, Any]]:
    """Score all YAML graphs in the directory.

    When ``candidate_props_paths`` are supplied, additional source-only
    candidates (entries with no corresponding YAML graph) are also scored
    using a minimal ``{graph_id, guideline_name, metadata}`` stub. These
    entries are flagged with ``"source": "candidate"`` in the output.
    """
    gbd_table = load_gbd_table(gbd_path)
    all_props: dict[str, Any] = {}
    if source_props_path and source_props_path.exists():
        all_props = load_source_properties(source_props_path)

    candidate_props: dict[str, Any] = {}
    for cp in candidate_props_paths or []:
        if cp and cp.exists():
            candidate_props.update(load_source_properties(cp))

    results = []
    seen_graph_ids: set[str] = set()

    yaml_files = sorted(graphs_dir.glob("*.yaml"))
    for yf in yaml_files:
        graph = load_graph(yf)
        graph_id = graph.get("graph_id", yf.stem)
        props = all_props.get(graph_id) or candidate_props.get(graph_id)
        scores = compute_all_scores(graph, gbd_table, props)
        axes = compute_axes(scores)
        tier = classify_tier(axes["total"])

        results.append(
            {
                "graph_id": graph_id,
                "guideline_name": graph.get("guideline_name", ""),
                "file": yf.name,
                "source": "yaml_graph",
                "scores": scores,
                "axes": axes,
                "tier": tier,
            }
        )
        seen_graph_ids.add(graph_id)

    # Source-only candidates (no YAML graph yet)
    for cand_id, cand_props in sorted(candidate_props.items()):
        if cand_id in seen_graph_ids:
            continue
        stub_graph = {
            "graph_id": cand_id,
            "guideline_name": cand_props.get("guideline_name", cand_id),
            "metadata": {
                "publisher": cand_props.get("publisher", ""),
                "publication_year": cand_props.get("publication_year"),
            },
        }
        scores = compute_all_scores(stub_graph, gbd_table, cand_props)
        axes = compute_axes(scores)
        tier = classify_tier(axes["total"])

        results.append(
            {
                "graph_id": cand_id,
                "guideline_name": cand_props.get("guideline_name", cand_id),
                "file": None,
                "source": "candidate",
                "scores": scores,
                "axes": axes,
                "tier": tier,
            }
        )

    results.sort(key=lambda r: (-r["axes"]["total"], r["graph_id"]))
    return results


def generate_report_json(results: list[dict[str, Any]], output_path: Path) -> None:
    """Write JSON report."""
    report = {
        "_metadata": {
            "version": "v2",
            "framework": "C1-C12 Source-Document Criteria (3-Axis)",
            "total_graphs": len(results),
            "tier_distribution": _tier_distribution(results),
            "axes": {
                "axis1": "Trustworthiness (C1-C5, max 7)",
                "axis2": "Clinical Significance (C6-C8, max 6)",
                "axis3": "Formalizability (C9-C12, max 6)",
            },
        },
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_report_md(results: list[dict[str, Any]], output_path: Path) -> None:
    """Write Markdown report."""
    dist = _tier_distribution(results)
    lines = [
        "# CPG Selection Criteria v2 — Scoring Report",
        "",
        "**Framework**: C1-C12 Source-Document Criteria (3-Axis, max 19)",
        f"**Total CPGs scored**: {len(results)}",
        f"**Score range**: {_score_range(results)}",
        "",
        "## Tier Distribution",
        "",
        f"- **Tier S** (>={TIER_S_MIN}): {dist.get('S', 0)} graphs",
        f"- **Tier A** ({TIER_A_MIN}-{TIER_S_MIN - 1}): {dist.get('A', 0)} graphs",
        f"- **Tier B** ({TIER_B_MIN}-{TIER_A_MIN - 1}): {dist.get('B', 0)} graphs",
        f"- **Excluded** (<{TIER_B_MIN}): {dist.get('Excluded', 0)} graphs",
        "",
        "## Per-Axis Summary",
        "",
    ]

    if results:
        for axis_key, axis_name, axis_max in [
            ("axis1_trustworthiness", "Trustworthiness (C1+C2+C3+C4+C5)", 7),
            ("axis2_clinical", "Clinical Significance (C6+C7+C8)", 6),
            ("axis3_formalizability", "Formalizability (C9+C10+C11+C12)", 6),
        ]:
            vals = [r["axes"][axis_key] for r in results]
            mean = sum(vals) / len(vals)
            lines.append(f"- **{axis_name}**: mean={mean:.1f}/{axis_max}")

    lines.extend(
        [
            "",
            "## Detailed Scores",
            "",
            "| Graph ID | Name "
            "| C1 | C2 | C3 | C4 | C5 "
            "| C6 | C7 | C8 "
            "| C9 | C10 | C11 | C12 "
            "| Ax1 | Ax2 | Ax3 | Total | Tier |",
            "| --- | --- "
            "| :---: | :---: | :---: | :---: | :---: "
            "| :---: | :---: | :---: "
            "| :---: | :---: | :---: | :---: "
            "| :---: | :---: | :---: | :---: | :---: |",
        ]
    )

    for r in results:
        s = r["scores"]
        ax = r["axes"]
        name = r["guideline_name"]
        if len(name) > 40:
            name = name[:37] + "..."
        row = (
            f"| {r['graph_id']} | {name} "
            f"| {s['C1']} | {s['C2']} | {s['C3']} | {s['C4']} | {s['C5']} "
            f"| {s['C6']} | {s['C7']} | {s['C8']} "
            f"| {s['C9']} | {s['C10']} | {s['C11']} | {s['C12']} "
            f"| {ax['axis1_trustworthiness']} | {ax['axis2_clinical']} | {ax['axis3_formalizability']} "
            f"| **{ax['total']}** | **{r['tier']}** |"
        )
        lines.append(row)

    lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _tier_distribution(results: list[dict[str, Any]]) -> dict[str, int]:
    """Count graphs per tier."""
    dist: dict[str, int] = defaultdict(int)
    for r in results:
        dist[r["tier"]] += 1
    return dict(dist)


def _score_range(results: list[dict[str, Any]]) -> str:
    """Format score range string."""
    if not results:
        return "N/A"
    totals = [r["axes"]["total"] for r in results]
    mean = sum(totals) / len(totals)
    return f"min={min(totals)}, max={max(totals)}, mean={mean:.1f}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Score CPG graphs against C1-C12 source-document criteria (v2)")
    parser.add_argument(
        "--graphs-dir",
        type=Path,
        default=REPO_ROOT / "cpg_model" / "graphs",
        help="Directory containing CPG YAML files",
    )
    parser.add_argument(
        "--gbd-path",
        type=Path,
        default=REPO_ROOT / "data" / "gbd_top30_causes.json",
        help="Path to GBD lookup table",
    )
    parser.add_argument(
        "--source-props-path",
        type=Path,
        default=REPO_ROOT / "data" / "cpg_source_properties.json",
        help="Path to expert-annotated source-document properties",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "reports",
        help="Output directory for reports",
    )
    parser.add_argument(
        "--candidate-props-path",
        type=Path,
        action="append",
        default=None,
        help=(
            "Optional path to a source-properties file of candidate CPGs with no "
            "YAML encoding yet. May be supplied multiple times."
        ),
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="cpg_scores_v2",
        help="Basename prefix for output reports (without extension)",
    )
    args = parser.parse_args()

    print(f"Scanning: {args.graphs_dir}")
    results = score_all_graphs(
        args.graphs_dir,
        args.gbd_path,
        args.source_props_path,
        candidate_props_paths=args.candidate_props_path,
    )

    json_path = args.output_dir / f"{args.output_prefix}.json"
    md_path = args.output_dir / f"{args.output_prefix}.md"

    generate_report_json(results, json_path)
    generate_report_md(results, md_path)

    # Print summary
    dist = _tier_distribution(results)
    print("\n=== CPG Selection Criteria v2 — Source-Document Scoring ===")
    print(f"Total CPGs scored: {len(results)}")
    print(f"Score distribution: {_score_range(results)}")
    print()
    print(f"Tier S (>={TIER_S_MIN}): {dist.get('S', 0)}")
    print(f"Tier A ({TIER_A_MIN}-{TIER_S_MIN - 1}): {dist.get('A', 0)}")
    print(f"Tier B ({TIER_B_MIN}-{TIER_A_MIN - 1}): {dist.get('B', 0)}")
    print(f"Excluded (<{TIER_B_MIN}): {dist.get('Excluded', 0)}")

    print("\nReports written to:")
    print(f"  {json_path}")
    print(f"  {md_path}")


if __name__ == "__main__":
    main()
