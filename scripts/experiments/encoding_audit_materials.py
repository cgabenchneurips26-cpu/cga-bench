#!/usr/bin/env python3
"""E-4: Independent Human Encoding Audit — material generation.

Generates materials for a blinded human annotator to independently extract
clinical constraints from CPG text, then compare with our gold-standard
encoding.

Selects 6 scenarios (1 per domain), loads CPG graph YAML and scenario
configs, and produces:
  - Per-scenario study documents with patient presentation + blank template
  - Annotation guide with constraint type definitions
  - Analysis template for post-annotation comparison
  - Gold-standard answer key (researcher-only)

Usage:
    PYTHONPATH=. python scripts/experiments/encoding_audit_materials.py

Output:
    encoding_audit/human/materials/
      septic_shock_basic.md
      stemi_inferior_rv_trap.md
      dka_moderate_basic.md
      aki_stage1_basic.md
      stroke_tpa_eligible.md
      adhf_warm_wet.md
    encoding_audit/human/annotation_guide.md
    encoding_audit/human/template.md
    encoding_audit/human/gold_standard.json
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]  # cga_bench/
OUTPUT_DIR = ROOT / "encoding_audit" / "human"
MATERIALS_DIR = OUTPUT_DIR / "materials"
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"

# ── Domain configuration ─────────────────────────────────────────────

DOMAIN_CONFIG: list[dict[str, str]] = [
    {
        "domain": "sepsis",
        "scenario_id": "septic_shock_basic",
        "graph_file": "ssc_sepsis_hour1_bundle.yaml",
        "scenario_file": "sepsis_scenarios.yaml",
        "guideline_name": "SSC 2021 Hour-1 Bundle",
    },
    {
        "domain": "chest_pain",
        "scenario_id": "stemi_inferior_rv_trap",
        "graph_file": "aha_chest_pain_evaluation.yaml",
        "scenario_file": "aha_chest_pain_scenarios.yaml",
        "guideline_name": "AHA/ACC 2021 Chest Pain Guidelines",
    },
    {
        "domain": "dka",
        "scenario_id": "dka_moderate_basic",
        "graph_file": "ada_dka_management.yaml",
        "scenario_file": "dka_scenarios.yaml",
        "guideline_name": "ADA DKA Management 2024",
    },
    {
        "domain": "aki",
        "scenario_id": "aki_stage1_basic",
        "graph_file": "kdigo_aki_full.yaml",
        "scenario_file": "kdigo_aki_full_scenarios.yaml",
        "guideline_name": "KDIGO AKI 2012",
    },
    {
        "domain": "stroke",
        "scenario_id": "stroke_tpa_eligible",
        "graph_file": "aha_stroke_2019.yaml",
        "scenario_file": "aha_stroke_scenarios.yaml",
        "guideline_name": "AHA/ASA 2019 Acute Ischemic Stroke",
    },
    {
        "domain": "heart_failure",
        "scenario_id": "adhf_warm_wet",
        "graph_file": "aha_heart_failure_2022.yaml",
        "scenario_file": "aha_heart_failure_scenarios.yaml",
        "guideline_name": "AHA/ACC/HFSA 2022 Heart Failure",
    },
]


# ── YAML loading ─────────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_graph(graph_file: str) -> dict[str, Any]:
    """Load a CPG graph YAML."""
    return _load_yaml(GRAPHS_DIR / graph_file)


def _load_scenario(scenario_file: str, scenario_id: str) -> dict[str, Any]:
    """Load a specific scenario from a scenarios YAML file."""
    scenarios_dir = ROOT / "configs" / "scenarios"
    data = _load_yaml(scenarios_dir / scenario_file)
    scenarios = data.get("scenarios", data)
    if scenario_id not in scenarios:
        raise KeyError(f"Scenario '{scenario_id}' not found in {scenario_file}. Available: {list(scenarios.keys())}")
    return scenarios[scenario_id]


# ── Source quote extraction ──────────────────────────────────────────


def _extract_source_quotes(graph: dict[str, Any]) -> list[dict[str, str]]:
    """Extract all source_quote fields from graph nodes, organized by section."""
    quotes: list[dict[str, str]] = []
    nodes = graph.get("nodes", {})

    for node_id, node_data in nodes.items():
        if not isinstance(node_data, dict):
            continue

        entry: dict[str, str] = {
            "node_id": node_id,
            "name": node_data.get("name", node_id),
            "section": node_data.get("source_section", ""),
            "guideline": node_data.get("source_guideline", ""),
            "page": str(node_data.get("source_page", "")),
            "evidence_level": node_data.get("evidence_level", ""),
            "recommendation_class": str(node_data.get("recommendation_class", "")),
        }

        # Single source_quote
        quote = node_data.get("source_quote", "")
        if quote:
            entry["quote"] = str(quote)

        # Additional source_quotes dict
        extra_quotes = node_data.get("source_quotes", {})
        if isinstance(extra_quotes, dict):
            for key, val in extra_quotes.items():
                entry[f"quote_{key}"] = str(val)

        if entry.get("quote") or any(k.startswith("quote_") for k in entry):
            quotes.append(entry)

    return quotes


# ── Constraint extraction for gold standard ──────────────────────────


def _extract_gold_constraints(
    graph: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract all constraints from graph nodes for the gold standard."""
    constraints: list[dict[str, Any]] = []
    nodes = graph.get("nodes", {})
    constraint_num = 0

    for node_id, node_data in nodes.items():
        if not isinstance(node_data, dict):
            continue

        source_info = {
            "source_guideline": node_data.get("source_guideline", ""),
            "source_section": node_data.get("source_section", ""),
            "evidence_level": node_data.get("evidence_level", ""),
            "recommendation_class": str(node_data.get("recommendation_class", "")),
            "node_id": node_id,
        }

        # Forbidden actions -> FORBIDDEN constraints
        forbidden = node_data.get("forbidden_actions", [])
        if isinstance(forbidden, list):
            for action in forbidden:
                constraint_num += 1
                constraints.append(
                    {
                        "id": constraint_num,
                        "action": str(action),
                        "type": "FORBIDDEN",
                        "condition": node_data.get("precondition", ""),
                        "deadline_minutes": None,
                        "hard_soft": "Hard",
                        **source_info,
                    }
                )

        # Mandatory actions with deadlines -> WITHIN constraints
        mandatory = node_data.get("mandatory_actions", [])
        deadlines = node_data.get("deadlines", {})
        if isinstance(deadlines, dict) and isinstance(mandatory, list):
            for action in mandatory:
                action_str = str(action)
                if action_str in deadlines:
                    constraint_num += 1
                    constraints.append(
                        {
                            "id": constraint_num,
                            "action": action_str,
                            "type": "WITHIN",
                            "condition": node_data.get("precondition", ""),
                            "deadline_minutes": deadlines[action_str],
                            "hard_soft": "Hard",
                            **source_info,
                        }
                    )

        # Mandatory actions without deadlines -> MUST constraints
        if isinstance(mandatory, list):
            for action in mandatory:
                action_str = str(action)
                if not isinstance(deadlines, dict) or action_str not in deadlines:
                    constraint_num += 1
                    constraints.append(
                        {
                            "id": constraint_num,
                            "action": action_str,
                            "type": "MUST",
                            "condition": node_data.get("precondition", ""),
                            "deadline_minutes": None,
                            "hard_soft": "Soft",
                            **source_info,
                        }
                    )

        # Required prior actions -> BEFORE constraints
        required_prior = node_data.get("required_prior_actions", {})
        if isinstance(required_prior, dict):
            for after_action, before_list in required_prior.items():
                if isinstance(before_list, list):
                    for before_action in before_list:
                        constraint_num += 1
                        constraints.append(
                            {
                                "id": constraint_num,
                                "action": f"{before_action} -> {after_action}",
                                "type": "BEFORE",
                                "condition": node_data.get("precondition", ""),
                                "deadline_minutes": None,
                                "hard_soft": "Hard",
                                **source_info,
                            }
                        )

    return constraints


# ── Patient presentation formatting ─────────────────────────────────


def _format_patient_presentation(scenario: dict[str, Any]) -> str:
    """Format patient presentation from scenario config."""
    patient = scenario.get("patient", {})
    vitals = patient.get("vitals", {})
    lines: list[str] = []

    lines.append(f"**Age/Sex**: {patient.get('age', 'N/A')} year-old {_sex_label(patient.get('sex', 'U'))}")
    lines.append(f"**Weight**: {patient.get('weight_kg', 'N/A')} kg")
    lines.append(f"**Chief Complaint**: {patient.get('chief_complaint', 'N/A')}")
    lines.append(f"**Working Diagnosis**: {patient.get('working_diagnosis', 'N/A')}")
    lines.append("")

    # Vitals
    lines.append("**Vital Signs**:")
    vital_labels = {
        "heart_rate": "Heart Rate",
        "blood_pressure_systolic": "SBP",
        "blood_pressure_diastolic": "DBP",
        "respiratory_rate": "Respiratory Rate",
        "temperature": "Temperature",
        "oxygen_saturation": "SpO2",
        "map_mmhg": "MAP",
    }
    for key, label in vital_labels.items():
        val = vitals.get(key)
        if val is not None:
            unit = _vital_unit(key)
            lines.append(f"- {label}: {val}{unit}")
    lines.append("")

    # Allergies
    allergies = patient.get("allergies", [])
    if allergies:
        lines.append(f"**Allergies**: {', '.join(str(a) for a in allergies)}")
    else:
        lines.append("**Allergies**: None known")

    # Comorbidities
    comorbidities = patient.get("comorbidities", [])
    if comorbidities:
        lines.append(f"**Comorbidities**: {', '.join(str(c) for c in comorbidities)}")
    else:
        lines.append("**Comorbidities**: None")

    # Contraindications
    contraindications = patient.get("contraindications", [])
    if contraindications:
        lines.append(f"**Contraindications**: {', '.join(str(c) for c in contraindications)}")
    lines.append("")

    # Ground truth data
    ground_truth = scenario.get("ground_truth", {})
    if ground_truth:
        lines.append("**Available Clinical Data**:")
        for key, val in ground_truth.items():
            label = key.replace("_", " ").replace("lab ", "").title()
            lines.append(f"- {label}: {val}")

    return "\n".join(lines)


def _sex_label(sex: str) -> str:
    """Convert sex code to label."""
    mapping = {"M": "Male", "F": "Female", "U": "Unknown"}
    return mapping.get(sex, sex)


def _vital_unit(key: str) -> str:
    """Return unit string for a vital sign key."""
    units = {
        "heart_rate": " bpm",
        "blood_pressure_systolic": " mmHg",
        "blood_pressure_diastolic": " mmHg",
        "respiratory_rate": " breaths/min",
        "temperature": " C",
        "oxygen_saturation": "%",
        "map_mmhg": " mmHg",
    }
    return units.get(key, "")


# ── CPG text formatting ──────────────────────────────────────────────


def _format_cpg_text(
    quotes: list[dict[str, str]],
    guideline_name: str,
) -> str:
    """Format CPG source quotes into readable text for annotators."""
    lines: list[str] = []
    lines.append(f"**Guideline**: {guideline_name}")
    lines.append("")

    seen_sections: set[str] = set()
    for entry in quotes:
        section = entry.get("section", "General")
        if section and section not in seen_sections:
            seen_sections.add(section)
            lines.append(f"### {section}")
            rec_class = entry.get("recommendation_class", "")
            ev_level = entry.get("evidence_level", "")
            if rec_class or ev_level:
                lines.append(f"*Recommendation Class {rec_class}, Level of Evidence {ev_level}*")
            lines.append("")

        # Main quote
        quote = entry.get("quote", "")
        if quote:
            lines.append(f"> {quote}")
            page = entry.get("page", "")
            if page:
                lines.append(f"> -- {entry.get('guideline', '')}, {page}")
            lines.append("")

        # Additional quotes
        for key, val in entry.items():
            if key.startswith("quote_") and val:
                topic = key.replace("quote_", "").replace("_", " ").title()
                lines.append(f"> [{topic}] {val}")
                lines.append("")

    return "\n".join(lines)


# ── Material document generation ─────────────────────────────────────


def _generate_scenario_material(
    domain_cfg: dict[str, str],
) -> str:
    """Generate a single scenario material document."""
    graph = _load_graph(domain_cfg["graph_file"])
    scenario = _load_scenario(
        domain_cfg["scenario_file"],
        domain_cfg["scenario_id"],
    )

    quotes = _extract_source_quotes(graph)
    patient_text = _format_patient_presentation(scenario)
    cpg_text = _format_cpg_text(quotes, domain_cfg["guideline_name"])

    scenario_desc = scenario.get("description", domain_cfg["scenario_id"])

    lines: list[str] = []
    lines.append("# Clinical Constraint Extraction Task")
    lines.append("")
    lines.append(f"**Scenario**: {domain_cfg['scenario_id']}")
    lines.append(f"**Domain**: {domain_cfg['domain']}")
    lines.append(f"**Description**: {scenario_desc}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Patient presentation
    lines.append("## Patient Presentation")
    lines.append("")
    lines.append(patient_text)
    lines.append("")
    lines.append("---")
    lines.append("")

    # CPG text
    lines.append("## Clinical Practice Guideline Text")
    lines.append("")
    lines.append(cpg_text)
    lines.append("")
    lines.append("---")
    lines.append("")

    # Task instructions
    lines.append("## Your Task")
    lines.append("")
    lines.append("Extract all clinical constraints applicable to THIS patient from the CPG text above.")
    lines.append("For each constraint, fill in one row of the template below.")
    lines.append("Refer to the Annotation Guide for definitions of each column.")
    lines.append("")

    # Template
    lines.append("## Constraint Extraction Template")
    lines.append("")
    lines.append(
        "| # | Action | Type (FORBIDDEN/WITHIN/BEFORE/MUST) | Condition | Deadline (min) | Hard/Soft | Evidence Level |"
    )
    lines.append(
        "|---|--------|--------------------------------------|"
        "-----------|----------------|-----------|----------------|"
    )
    # Provide 20 blank rows
    blank_row_count = 20
    for i in range(1, blank_row_count + 1):
        lines.append(f"| {i} | | | | | | |")
    lines.append("")
    lines.append("*Add additional rows as needed. See annotation_guide.md for detailed instructions.*")
    lines.append("")

    return "\n".join(lines)


# ── Annotation guide ─────────────────────────────────────────────────


def _generate_annotation_guide() -> str:
    """Generate the annotation guide document."""
    return """# Annotation Guide: Clinical Constraint Extraction

## Purpose

This guide defines the constraint types, severity levels, and evidence
classifications used in the Clinical Constraint Extraction Task.
Your goal is to independently extract all clinical constraints from
the provided CPG text that apply to the given patient scenario.

---

## Constraint Type Definitions

### FORBIDDEN
An action that must NOT be performed for this patient.

**Examples**:
- Nitroglycerin is FORBIDDEN in suspected right ventricular infarction
  (causes severe hypotension by reducing preload).
- NSAIDs are FORBIDDEN in acute kidney injury (nephrotoxic).
- Insulin is FORBIDDEN when potassium is below 3.3 mEq/L in DKA
  (risk of fatal hypokalemia).
- tPA is FORBIDDEN in hemorrhagic stroke (worsens bleeding).

### WITHIN
An action that must be completed within a specific time deadline.

**Examples**:
- 12-lead ECG must be obtained WITHIN 10 minutes of ED arrival.
- Broad-spectrum antibiotics must be given WITHIN 60 minutes in sepsis.
- IV fluids must be started WITHIN 15 minutes in DKA.
- Door-to-balloon time WITHIN 90 minutes for STEMI.

### BEFORE
Action A must occur before Action B (sequence constraint).

**Examples**:
- Blood cultures BEFORE broad-spectrum antibiotics (to avoid sterilizing
  cultures).
- ECG interpretation BEFORE cath lab activation (to confirm STEMI).
- Potassium check BEFORE insulin in DKA (to prevent fatal hypokalemia).
- CT head BEFORE tPA administration (to rule out hemorrhage).

### MUST
An action that is mandatory but without a specific time deadline.

**Examples**:
- Must assess infection source in sepsis.
- Must order echocardiogram for new heart failure diagnosis.
- Must monitor urine output in AKI.
- Must provide diabetes education before DKA discharge.

---

## Hard vs Soft Classification

### Hard Constraint
Violation causes direct, measurable patient harm or significantly
increases mortality/morbidity risk.

**Indicators**:
- Contraindicated actions (drug-disease interactions)
- Time-critical interventions where delay increases mortality
- Sequence violations that compromise diagnostic accuracy
- Actions with Class I recommendation and Level A evidence

**Examples**:
- Giving nitrates in RV infarct (Hard: causes cardiovascular collapse)
- Starting insulin with K+ < 3.3 (Hard: fatal cardiac arrhythmia)
- Delaying antibiotics >60 min in septic shock (Hard: OR 1.09 mortality
  per hour of delay)

### Soft Constraint
Violation is suboptimal but does not directly endanger the patient.

**Indicators**:
- Monitoring or assessment actions without immediate safety impact
- Class IIa/IIb recommendations
- Actions with Level C evidence
- Documentation or education requirements

**Examples**:
- Missing diabetes education before discharge (Soft: increases
  readmission risk but not immediate harm)
- Not calculating risk score within recommended window (Soft:
  delays decision but patient not immediately harmed)

---

## Evidence Level Definitions

### Recommendation Class (Strength)
| Class | Description | Meaning |
|-------|-------------|---------|
| I | Strong | Benefit >>> Risk; SHOULD be performed |
| IIa | Moderate | Benefit >> Risk; REASONABLE to perform |
| IIb | Weak | Benefit >= Risk; MAY BE CONSIDERED |
| III (No Benefit) | No benefit | Not helpful |
| III (Harm) | Harmful | Causes harm; SHOULD NOT be performed |

### Level of Evidence (Quality)
| Level | Description |
|-------|-------------|
| A | High-quality evidence from multiple RCTs or meta-analyses |
| B | Moderate-quality evidence from single RCT or well-designed non-randomized studies |
| B-NR | Moderate-quality from non-randomized studies |
| C | Consensus of expert opinion, case studies, or standard of care |
| C-LD | Limited data |
| C-EO | Expert opinion |

---

## Extraction Instructions

1. Read the patient presentation carefully. Note age, sex, vitals,
   allergies, comorbidities, and working diagnosis.

2. Read each CPG quote. For each quote, ask:
   - Does this quote specify any FORBIDDEN actions for this patient?
   - Does this quote specify any time-critical (WITHIN) actions?
   - Does this quote specify any sequencing (BEFORE) requirements?
   - Does this quote specify any mandatory (MUST) actions?

3. For each constraint identified, fill in one row:
   - **Action**: The specific clinical action (use lowercase with
     underscores, e.g., "give_broad_spectrum_antibiotics")
   - **Type**: FORBIDDEN, WITHIN, BEFORE, or MUST
   - **Condition**: Under what patient condition this applies
     (e.g., "K+ < 3.3 mEq/L", "RV infarct suspected")
   - **Deadline**: Number of minutes (for WITHIN type only)
   - **Hard/Soft**: Whether violation causes direct harm
   - **Evidence Level**: Class and Level from the guideline
     (e.g., "Class I, Level A")

4. Be exhaustive. Extract ALL constraints you can identify from the
   text, even if some seem obvious or redundant.

5. If a constraint applies conditionally (e.g., only if the patient
   has a certain condition), specify the condition in the Condition
   column.

---

## Common Pitfalls

- **Missing implicit BEFORE constraints**: Many guidelines imply
  sequence without stating it explicitly (e.g., "obtain cultures
  before antibiotics").
- **Overlooking conditional FORBIDDEN actions**: Some actions are
  forbidden only under specific conditions (e.g., nitrates forbidden
  only if RV infarct is suspected).
- **Confusing MUST and WITHIN**: If the guideline specifies a time
  frame, use WITHIN. Use MUST only when the action is mandatory
  but no deadline is stated.
- **Ignoring node-specific constraints**: Constraints may apply only
  in certain clinical pathways (e.g., septic shock vs sepsis without
  shock).

---

*Document version: 1.0*
*Generated: {timestamp}*
""".format(timestamp=datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC"))


# ── Analysis template ────────────────────────────────────────────────


def _generate_analysis_template() -> str:
    """Generate the post-annotation analysis template."""
    return """# Post-Annotation Comparison Template

## Purpose
Compare the independent human annotator's extracted constraints against
the gold-standard encoding to measure inter-rater agreement and identify
encoding gaps.

---

## Comparison Methodology

### Step 1: Align Constraints
For each gold-standard constraint, find the closest matching annotator
constraint. Match on:
1. Action (exact or semantic match)
2. Type (FORBIDDEN/WITHIN/BEFORE/MUST)
3. Condition applicability

### Step 2: Compute Agreement Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| Precision | TP / (TP + FP) | >= 0.80 |
| Recall | TP / (TP + FN) | >= 0.80 |
| F1 Score | 2 * P * R / (P + R) | >= 0.80 |
| Cohen's Kappa | (P_o - P_e) / (1 - P_e) | >= 0.60 |
| Type Agreement | Matching type / Total matched | >= 0.85 |
| Deadline Agreement | Matching deadline / Total WITHIN | >= 0.75 |
| Hard/Soft Agreement | Matching severity / Total matched | >= 0.80 |

Where:
- TP = Constraints found by both annotator and gold standard
- FP = Constraints found by annotator but not in gold standard
- FN = Constraints in gold standard but missed by annotator

### Step 3: Categorize Disagreements

| Category | Description |
|----------|-------------|
| Missing Constraint | Annotator missed a gold-standard constraint |
| Extra Constraint | Annotator found a constraint not in gold standard |
| Type Mismatch | Same action but different constraint type |
| Deadline Mismatch | Same WITHIN constraint but different deadline |
| Severity Mismatch | Same constraint but different Hard/Soft classification |
| Condition Mismatch | Same constraint but different applicability condition |

### Step 4: Per-Domain Summary

| Domain | Precision | Recall | F1 | Kappa | Notes |
|--------|-----------|--------|----|-------|-------|
| Sepsis | | | | | |
| Chest Pain | | | | | |
| DKA | | | | | |
| AKI | | | | | |
| Stroke | | | | | |
| Heart Failure | | | | | |
| **Overall** | | | | | |

### Step 5: Qualitative Analysis
- Which constraint types are most commonly missed?
- Which constraint types are most commonly over-extracted?
- Are there systematic differences in Hard/Soft classification?
- Do domain-specific patterns emerge in disagreements?

---

## Reporting Format

```json
{
  "annotator_id": "ANON_001",
  "date_completed": "YYYY-MM-DD",
  "time_spent_minutes": null,
  "per_domain": {
    "sepsis": {
      "tp": 0, "fp": 0, "fn": 0,
      "precision": 0.0, "recall": 0.0, "f1": 0.0,
      "type_agreement": 0.0,
      "notes": ""
    }
  },
  "overall": {
    "tp": 0, "fp": 0, "fn": 0,
    "precision": 0.0, "recall": 0.0, "f1": 0.0,
    "cohens_kappa": 0.0
  },
  "disagreement_categories": {
    "missing_constraint": 0,
    "extra_constraint": 0,
    "type_mismatch": 0,
    "deadline_mismatch": 0,
    "severity_mismatch": 0,
    "condition_mismatch": 0
  }
}
```

---

*Template version: 1.0*
"""


# ── Main execution ───────────────────────────────────────────────────


def main() -> None:
    """Generate all encoding audit materials."""
    # Create output directories
    MATERIALS_DIR.mkdir(parents=True, exist_ok=True)

    gold_standard: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "description": (
            "Gold-standard constraints extracted from CPG graph YAML files. "
            "RESEARCHER-ONLY — do not share with annotators."
        ),
        "domains": {},
    }

    # Generate per-scenario materials
    for cfg in DOMAIN_CONFIG:
        scenario_id = cfg["scenario_id"]
        domain = cfg["domain"]
        print(f"Generating materials for {scenario_id} ({domain})...")

        # Generate material document
        material = _generate_scenario_material(cfg)
        material_path = MATERIALS_DIR / f"{scenario_id}.md"
        material_path.write_text(material, encoding="utf-8")
        print(f"  -> {material_path.relative_to(ROOT)}")

        # Extract gold-standard constraints
        graph = _load_graph(cfg["graph_file"])
        constraints = _extract_gold_constraints(graph)

        gold_standard["domains"][domain] = {
            "scenario_id": scenario_id,
            "guideline": cfg["guideline_name"],
            "graph_file": cfg["graph_file"],
            "total_constraints": len(constraints),
            "by_type": _count_by_type(constraints),
            "constraints": constraints,
        }

    # Generate annotation guide
    guide_path = OUTPUT_DIR / "annotation_guide.md"
    guide_path.write_text(_generate_annotation_guide(), encoding="utf-8")
    print(f"  -> {guide_path.relative_to(ROOT)}")

    # Generate analysis template
    template_path = OUTPUT_DIR / "template.md"
    template_path.write_text(_generate_analysis_template(), encoding="utf-8")
    print(f"  -> {template_path.relative_to(ROOT)}")

    # Write gold standard
    gold_path = OUTPUT_DIR / "gold_standard.json"
    gold_path.write_text(
        json.dumps(gold_standard, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  -> {gold_path.relative_to(ROOT)}")

    # Summary
    print("\n=== Summary ===")
    total_constraints = 0
    for domain, data in gold_standard["domains"].items():
        count = data["total_constraints"]
        total_constraints += count
        by_type = data["by_type"]
        print(
            f"  {domain}: {count} constraints "
            f"(FORBIDDEN={by_type.get('FORBIDDEN', 0)}, "
            f"WITHIN={by_type.get('WITHIN', 0)}, "
            f"BEFORE={by_type.get('BEFORE', 0)}, "
            f"MUST={by_type.get('MUST', 0)})"
        )
    print(f"  Total: {total_constraints} constraints across 6 domains")
    print(f"\nOutput directory: {OUTPUT_DIR.relative_to(ROOT)}")


def _count_by_type(
    constraints: list[dict[str, Any]],
) -> dict[str, int]:
    """Count constraints by type."""
    counts: dict[str, int] = {}
    for c in constraints:
        ctype = c.get("type", "UNKNOWN")
        counts[ctype] = counts.get(ctype, 0) + 1
    return counts


if __name__ == "__main__":
    main()
