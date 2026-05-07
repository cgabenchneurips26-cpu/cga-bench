#!/usr/bin/env python3
"""RAG corpus quality verification across 5 dimensions.

Covers:
  V1: parsed.json ↔ YAML graph consistency (25 domains)
  V2: RAG retrieval accuracy (25 domains) — separate script
  V3: parsed.json content quality (5 always-empty domains)
  V4: Original CPG coverage (3 domains deep dive)
  V5: End-to-end dry run — separate script

Usage:
    PYTHONPATH=. python scripts/verify_rag_corpus.py
"""

import json
from pathlib import Path
import re
from typing import Any

import yaml

GRAPH_DIR = Path("cpg_model/graphs")
PARSED_DIR = Path("cpg_sources")

# Graph ID → parsed.json filename mapping (must match generate_rag_from_graphs.py)
GRAPH_TO_FILENAME: dict[str, str] = {
    "ssc_sepsis_hour1_bundle": "SSC-2021-Sepsis-Hour1-Bundle.parsed.json",
    "aha_chest_pain_evaluation": "AHA-2021-Chest-Pain-Guidelines.parsed.json",
    "kdigo_aki_full": "KDIGO-2012-AKI-Guidelines.parsed.json",
    "aha_heart_failure_2022": "AHA-2022-Heart-Failure-Guidelines.parsed.json",
    "aha_stroke_2019": "AHA-2019-Stroke-Guidelines.parsed.json",
    "ada_dka_management": "ADA-2009-DKA-Management.parsed.json",
    "atrial_fibrillation": "ESC-2020-AF-Guidelines.parsed.json",
    "cap_pneumonia": "ATS-IDSA-2019-CAP-Guidelines.parsed.json",
    "copd_exacerbation": "GOLD-2024-COPD-Report.parsed.json",
    "gi_bleeding": "ACG-2021-GI-Bleeding-Guidelines.parsed.json",
    "hypertensive_emergency": "AHA-2017-Hypertensive-Emergency.parsed.json",
    "kdigo_contrast_aki": "KDIGO-2012-Contrast-AKI.parsed.json",
    "pulmonary_embolism": "ESC-2019-PE-Guidelines.parsed.json",
    "anaphylaxis_management": "WAO-2020-Anaphylaxis-Guidelines.parsed.json",
    "acls_cardiac_arrest": "AHA-2020-ACLS-Guidelines.parsed.json",
    "status_epilepticus": "AES-2016-Status-Epilepticus.parsed.json",
    "gina_asthma_exacerbation": "GINA-2024-Asthma-Exacerbation.parsed.json",
    "idsa_meningitis": "IDSA-2004-Meningitis-Guidelines.parsed.json",
    "toxicology_management": "AACT-Toxicology-Management.parsed.json",
    "aba_burn_resuscitation": "ABA-2018-Burn-Resuscitation.parsed.json",
    "aabb_transfusion": "AABB-2016-Transfusion-Guidelines.parsed.json",
    "acog_obstetric_hemorrhage": "ACOG-2017-Obstetric-Hemorrhage.parsed.json",
    "pals_pediatric_emergency": "AHA-2020-PALS-Guidelines.parsed.json",
    "apa_agitation_management": "APA-2024-Agitation-Management.parsed.json",
    "universal_clinical_safety": "Universal-Clinical-Safety.parsed.json",
}

# Domain-specific key concepts that MUST appear in parsed.json
DOMAIN_KEY_CONCEPTS: dict[str, list[str]] = {
    "ssc_sepsis_hour1_bundle": [
        "blood culture",
        "antibiotic",
        "lactate",
        "crystalloid",
        "vasopressor",
    ],
    "aha_chest_pain_evaluation": [
        "troponin",
        "ecg",
        "aspirin",
        "cath",
        "stemi",
    ],
    "kdigo_aki_full": [
        "creatinine",
        "urine output",
        "fluid",
        "nephrotoxic",
        "renal",
    ],
    "aha_heart_failure_2022": [
        "ejection fraction",
        "diuretic",
        "ace",
        "beta blocker",
        "bnp",
    ],
    "aha_stroke_2019": [
        "alteplase",
        "nihss",
        "ct",
        "blood pressure",
        "thrombectomy",
    ],
    "ada_dka_management": [
        "insulin",
        "potassium",
        "bicarbonate",
        "glucose",
        "fluid",
    ],
    "atrial_fibrillation": [
        "rate control",
        "rhythm",
        "anticoagul",
        "chadsvasc",
        "cardioversion",
    ],
    "cap_pneumonia": [
        "sputum",
        "antibiotic",
        "oxygen",
        "procalcitonin",
        "respiratory",
    ],
    "copd_exacerbation": [
        "bronchodilator",
        "steroid",
        "oxygen",
        "ventilat",
        "antibiotic",
    ],
    "gi_bleeding": [
        "endoscopy",
        "transfus",
        "hemoglobin",
        "ppi",
        "resuscitat",
    ],
    "hypertensive_emergency": [
        "blood pressure",
        "iv",
        "nicardipine",
        "organ damage",
        "target",
    ],
    "kdigo_contrast_aki": [
        "contrast",
        "creatinine",
        "hydrat",
        "egfr",
        "volume",
    ],
    "pulmonary_embolism": [
        "anticoagul",
        "heparin",
        "ct angiograph",
        "thrombolys",
        "risk stratif",
    ],
    "anaphylaxis_management": [
        "epinephrine",
        "airway",
        "iv fluid",
        "antihistamine",
        "allergic",
    ],
    "acls_cardiac_arrest": [
        "cpr",
        "defibrillat",
        "epinephrine",
        "rhythm",
        "rosc",
    ],
    "status_epilepticus": [
        "benzodiazepine",
        "seizure",
        "lorazepam",
        "phenytoin",
        "airway",
    ],
    "gina_asthma_exacerbation": [
        "salbutamol",
        "corticosteroid",
        "oxygen",
        "peak flow",
        "nebuliz",
    ],
    "idsa_meningitis": [
        "lumbar puncture",
        "ceftriaxone",
        "vancomycin",
        "dexamethasone",
        "csf",
    ],
    "toxicology_management": [
        "decontaminat",
        "antidote",
        "activated charcoal",
        "toxicology",
        "naloxone",
    ],
    "aba_burn_resuscitation": [
        "parkland",
        "lactated ringer",
        "tbsa",
        "urine output",
        "fluid",
    ],
    "aabb_transfusion": [
        "hemoglobin",
        "transfus",
        "crossmatch",
        "red blood cell",
        "platelet",
    ],
    "acog_obstetric_hemorrhage": [
        "oxytocin",
        "hemorrhage",
        "transfus",
        "uterine",
        "blood loss",
    ],
    "pals_pediatric_emergency": [
        "pediatric",
        "weight",
        "epinephrine",
        "defibrillat",
        "airway",
    ],
    "apa_agitation_management": [
        "agitat",
        "de-escalat",
        "haloperidol",
        "lorazepam",
        "restraint",
    ],
    "universal_clinical_safety": [
        "allergy",
        "vital sign",
        "identity",
        "handoff",
        "safety",
    ],
}

# V4: Key CPG recommendations for deep-dive domains
CPG_KEY_RECOMMENDATIONS: dict[str, list[str]] = {
    "ssc_sepsis_hour1_bundle": [
        "Obtain blood cultures before starting antibiotics",
        "Administer broad-spectrum antibiotics within 1 hour",
        "Measure serum lactate; remeasure if initial lactate >2 mmol/L",
        "Begin rapid infusion of 30 mL/kg crystalloid for hypotension or lactate >=4",
        "Start vasopressors if hypotensive after fluid resuscitation to target MAP >=65",
        "Reassess volume status and tissue perfusion",
        "Obtain source control (e.g., drain abscess, remove infected device)",
    ],
    "kdigo_aki_full": [
        "Stage AKI based on creatinine rise and urine output criteria",
        "Identify and correct reversible causes of AKI",
        "Discontinue nephrotoxic agents when possible",
        "Ensure adequate volume status and hemodynamic support",
        "Monitor serum creatinine and urine output closely",
        "Avoid hyperglycemia; use insulin to target glucose 110-149 mg/dL",
        "Consider renal replacement therapy for refractory complications",
        "Avoid radiocontrast agents when possible; use iso-osmolar agents if needed",
    ],
    "gina_asthma_exacerbation": [
        "Administer inhaled SABA (salbutamol) as first-line bronchodilator",
        "Give systemic corticosteroids within 1 hour for moderate-severe exacerbation",
        "Provide supplemental oxygen to maintain SpO2 93-95%",
        "Assess severity using peak expiratory flow or FEV1",
        "Add ipratropium bromide for severe exacerbation",
        "Consider IV magnesium sulfate for life-threatening exacerbation",
        "Reassess response to treatment at 1 hour",
        "Admit to ICU if severe/life-threatening or poor response",
    ],
}


def load_yaml_graph(path: Path) -> dict[str, Any]:
    """Load a YAML graph file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_parsed_json(path: Path) -> dict[str, Any]:
    """Load a parsed.json file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_graph_actions(graph: dict[str, Any]) -> dict[str, Any]:
    """Extract all actions and key info from a YAML graph."""
    nodes = graph.get("nodes", {})
    if isinstance(nodes, dict):
        nodes_list = list(nodes.values())
    else:
        nodes_list = list(nodes)

    mandatory_actions: list[str] = []
    forbidden_actions: list[str] = []
    deadlines: dict[str, int] = {}
    source_quotes: list[str] = []
    conditional_rules: list[dict] = []

    for node in nodes_list:
        if not isinstance(node, dict):
            continue
        mandatory_actions.extend(node.get("mandatory_actions", []) or [])
        forbidden_actions.extend(node.get("forbidden_actions", []) or [])
        dl = node.get("deadlines", {})
        if isinstance(dl, dict):
            deadlines.update(dl)
        sq = node.get("source_quote", "")
        if sq and len(sq) > 20:
            source_quotes.append(sq)
        for rule in node.get("conditional_rules", []) or []:
            if isinstance(rule, dict):
                conditional_rules.append(rule)

    return {
        "n_nodes": len(nodes_list),
        "mandatory_actions": mandatory_actions,
        "forbidden_actions": forbidden_actions,
        "deadlines": deadlines,
        "source_quotes": source_quotes,
        "conditional_rules": conditional_rules,
        "n_mandatory": len(mandatory_actions),
        "n_forbidden": len(forbidden_actions),
        "n_deadlines": len(deadlines),
        "n_source_quotes": len(source_quotes),
        "n_conditional_rules": len(conditional_rules),
    }


def get_all_text(parsed: dict[str, Any]) -> str:
    """Concatenate all text from a parsed.json for keyword search."""
    parts: list[str] = []
    for rec in parsed.get("recommendations", []):
        parts.append(rec.get("text", ""))
    for table in parsed.get("tables", []):
        for row in table.get("data", []):
            parts.extend(str(cell) for cell in row)
    for section_text in parsed.get("key_sections", {}).values():
        parts.append(section_text)
    return " ".join(parts).lower()


def verify_v1_consistency() -> list[dict[str, Any]]:
    """V1: parsed.json ↔ YAML graph consistency for all 25 domains."""
    print("=" * 70)
    print("VERIFICATION 1: parsed.json ↔ YAML graph consistency")
    print("=" * 70)

    results: list[dict[str, Any]] = []
    yaml_files = sorted(GRAPH_DIR.glob("*.yaml"))

    for yaml_file in yaml_files:
        graph = load_yaml_graph(yaml_file)
        graph_id = graph.get("graph_id", yaml_file.stem)
        filename = GRAPH_TO_FILENAME.get(graph_id)

        if filename is None:
            print(f"  WARN: No mapping for {graph_id}")
            continue

        parsed_path = PARSED_DIR / filename
        if not parsed_path.exists():
            print(f"  MISSING: {filename}")
            results.append({"graph_id": graph_id, "status": "MISSING", "coverage_score": 0.0})
            continue

        parsed = load_parsed_json(parsed_path)
        graph_info = extract_graph_actions(graph)
        all_text = get_all_text(parsed)

        n_recs = len(parsed.get("recommendations", []))
        n_tables = len(parsed.get("tables", []))
        n_sections = len(parsed.get("key_sections", {}))

        # Check 1: Action coverage — do mandatory/forbidden actions appear in parsed text?
        actions_found = 0
        actions_total = 0
        missing_actions: list[str] = []
        for action in graph_info["mandatory_actions"] + graph_info["forbidden_actions"]:
            actions_total += 1
            action_readable = action.replace("_", " ").lower()
            # Check both underscore and readable forms
            if action.lower() in all_text or action_readable in all_text:
                actions_found += 1
            else:
                # Try partial match (at least 2 key words)
                words = [w for w in action_readable.split() if len(w) > 3]
                if words and sum(1 for w in words if w in all_text) >= max(1, len(words) // 2):
                    actions_found += 1
                else:
                    missing_actions.append(action)

        action_coverage = actions_found / max(actions_total, 1)

        # Check 2: Key concept coverage
        key_concepts = DOMAIN_KEY_CONCEPTS.get(graph_id, [])
        concepts_found = 0
        missing_concepts: list[str] = []
        for concept in key_concepts:
            if concept.lower() in all_text:
                concepts_found += 1
            else:
                missing_concepts.append(concept)
        concept_coverage = concepts_found / max(len(key_concepts), 1)

        # Check 3: Source quote preservation
        quotes_found = 0
        for quote in graph_info["source_quotes"]:
            # Check if first 40 chars of quote appear in parsed text
            snippet = quote[:40].lower()
            if snippet in all_text:
                quotes_found += 1
        quote_coverage = quotes_found / max(len(graph_info["source_quotes"]), 1)

        # Combined coverage score
        coverage_score = 0.4 * action_coverage + 0.4 * concept_coverage + 0.2 * quote_coverage

        status = "OK" if coverage_score >= 0.7 else "WARN" if coverage_score >= 0.5 else "FAIL"

        result = {
            "graph_id": graph_id,
            "filename": filename,
            "status": status,
            "coverage_score": round(coverage_score, 3),
            "action_coverage": round(action_coverage, 3),
            "concept_coverage": round(concept_coverage, 3),
            "quote_coverage": round(quote_coverage, 3),
            "n_recs": n_recs,
            "n_tables": n_tables,
            "n_sections": n_sections,
            "graph_mandatory": graph_info["n_mandatory"],
            "graph_forbidden": graph_info["n_forbidden"],
            "graph_source_quotes": graph_info["n_source_quotes"],
            "graph_conditional_rules": graph_info["n_conditional_rules"],
            "missing_actions": missing_actions[:5],
            "missing_concepts": missing_concepts,
        }
        results.append(result)

        flag = "  " if status == "OK" else " *" if status == "WARN" else "**"
        print(
            f"{flag} {graph_id:40s} cov={coverage_score:.2f} "
            f"(act={action_coverage:.2f} con={concept_coverage:.2f} "
            f"quo={quote_coverage:.2f}) "
            f"recs={n_recs} tbl={n_tables} sec={n_sections}"
        )
        if missing_concepts:
            print(f"     missing concepts: {', '.join(missing_concepts)}")

    # Summary
    ok_count = sum(1 for r in results if r.get("status") == "OK")
    warn_count = sum(1 for r in results if r.get("status") == "WARN")
    fail_count = sum(1 for r in results if r.get("status") in ("FAIL", "MISSING"))
    avg_score = sum(r.get("coverage_score", 0) for r in results) / max(len(results), 1)

    print(f"\nSummary: {ok_count} OK, {warn_count} WARN, {fail_count} FAIL")
    print(f"Average coverage score: {avg_score:.3f}")

    return results


def verify_v3_content_quality() -> list[dict[str, Any]]:
    """V3: Content quality deep review for 5 always-empty domains."""
    print("\n" + "=" * 70)
    print("VERIFICATION 3: Content quality for always-empty domains")
    print("=" * 70)

    target_domains = {
        "kdigo_aki_full": "KDIGO-2012-AKI-Guidelines.parsed.json",
        "gina_asthma_exacerbation": "GINA-2024-Asthma-Exacerbation.parsed.json",
        "kdigo_contrast_aki": "KDIGO-2012-Contrast-AKI.parsed.json",
        "idsa_meningitis": "IDSA-2004-Meningitis-Guidelines.parsed.json",
        "ada_dka_management": "ADA-2009-DKA-Management.parsed.json",
    }

    results: list[dict[str, Any]] = []

    for graph_id, filename in target_domains.items():
        parsed_path = PARSED_DIR / filename
        if not parsed_path.exists():
            print(f"  MISSING: {filename}")
            results.append({"graph_id": graph_id, "grade": "F", "reason": "file missing"})
            continue

        parsed = load_parsed_json(parsed_path)
        recs = parsed.get("recommendations", [])
        sections = parsed.get("key_sections", {})
        all_text = get_all_text(parsed)

        # Quality criteria
        has_clinical_actions = False
        has_dosage_or_specifics = False
        has_source_quotes = False
        has_meaningful_sections = False
        avg_rec_length = 0
        structural_only_count = 0

        # Check recommendation quality
        rec_lengths: list[int] = []
        for rec in recs:
            text = rec.get("text", "")
            rec_lengths.append(len(text))

            # Is this clinical guidance or just structure?
            if any(
                kw in text.lower()
                for kw in [
                    "administer",
                    "give",
                    "order",
                    "monitor",
                    "assess",
                    "initiate",
                    "start",
                    "perform",
                    "evaluate",
                    "measure",
                    "within",
                    "mg",
                    "ml",
                    "dose",
                    "infusion",
                ]
            ):
                has_clinical_actions = True

            # Does it have specifics (doses, times, thresholds)?
            if re.search(r"\d+\s*(mg|ml|mmol|mm\s*hg|minutes|hours|%|mcg)", text.lower()):
                has_dosage_or_specifics = True

            # Is this just "node_name: action_name" structure?
            if len(text) < 50 and "_" in text and " " not in text.strip():
                structural_only_count += 1

        if rec_lengths:
            avg_rec_length = sum(rec_lengths) / len(rec_lengths)

        # Check if source quotes are present
        for rec in recs:
            if rec.get("source_section") or rec.get("source_guideline"):
                has_source_quotes = True
                break

        # Check section quality
        for sec_name, sec_text in sections.items():
            if len(sec_text) > 100 and any(
                kw in sec_text.lower() for kw in ["recommend", "should", "must", "guideline", "evidence"]
            ):
                has_meaningful_sections = True
                break

        # Grade assignment
        score = 0
        if has_clinical_actions:
            score += 2
        if has_dosage_or_specifics:
            score += 2
        if has_source_quotes:
            score += 1
        if has_meaningful_sections:
            score += 2
        if avg_rec_length > 80:
            score += 1
        if len(recs) >= 10:
            score += 1
        if structural_only_count > len(recs) * 0.5:
            score -= 2

        if score >= 7:
            grade = "A"
        elif score >= 5:
            grade = "B"
        elif score >= 3:
            grade = "C"
        else:
            grade = "F"

        result = {
            "graph_id": graph_id,
            "filename": filename,
            "grade": grade,
            "score": score,
            "n_recs": len(recs),
            "avg_rec_length": round(avg_rec_length, 0),
            "has_clinical_actions": has_clinical_actions,
            "has_dosage_or_specifics": has_dosage_or_specifics,
            "has_source_quotes": has_source_quotes,
            "has_meaningful_sections": has_meaningful_sections,
            "structural_only_count": structural_only_count,
            "file_size_kb": round(parsed_path.stat().st_size / 1024, 1),
        }
        results.append(result)

        print(f"\n  {graph_id} -> Grade {grade} (score={score}/9)")
        print(f"    Recs: {len(recs)}, avg length: {avg_rec_length:.0f} chars")
        print(f"    Clinical actions: {has_clinical_actions}")
        print(f"    Dosage/specifics: {has_dosage_or_specifics}")
        print(f"    Source quotes: {has_source_quotes}")
        print(f"    Meaningful sections: {has_meaningful_sections}")
        print(f"    Structural-only recs: {structural_only_count}/{len(recs)}")

        # Show sample recommendation
        if recs:
            sample = recs[0].get("text", "")[:200]
            print(f"    Sample rec: {sample}...")

    # Summary
    grades = [r["grade"] for r in results]
    f_count = grades.count("F")
    print(f"\nSummary: grades = {', '.join(grades)}")
    print(f"F-grade count: {f_count}")
    print(f"PASS criteria (0 F grades): {'PASS' if f_count == 0 else 'FAIL'}")

    return results


def verify_v4_cpg_coverage() -> list[dict[str, Any]]:
    """V4: Original CPG recommendation coverage for 3 deep-dive domains."""
    print("\n" + "=" * 70)
    print("VERIFICATION 4: Original CPG recommendation coverage")
    print("=" * 70)

    results: list[dict[str, Any]] = []

    for graph_id, expected_recs in CPG_KEY_RECOMMENDATIONS.items():
        filename = GRAPH_TO_FILENAME.get(graph_id, "")
        parsed_path = PARSED_DIR / filename
        if not parsed_path.exists():
            print(f"  MISSING: {filename}")
            results.append(
                {
                    "graph_id": graph_id,
                    "found": 0,
                    "total": len(expected_recs),
                    "omission_rate": 1.0,
                }
            )
            continue

        parsed = load_parsed_json(parsed_path)
        all_text = get_all_text(parsed)

        found_recs: list[str] = []
        missing_recs: list[str] = []

        for rec_text in expected_recs:
            # Extract key clinical terms from the recommendation
            words = re.findall(r"[a-z]+", rec_text.lower())
            # Remove common stop words
            stop = {
                "the",
                "and",
                "for",
                "with",
                "from",
                "should",
                "must",
                "may",
                "can",
                "use",
                "when",
                "after",
                "before",
                "within",
                "based",
                "using",
                "ensure",
                "consider",
                "begin",
                "start",
                "obtain",
                "avoid",
                "provide",
                "give",
                "administer",
            }
            key_terms = [w for w in words if w not in stop and len(w) > 3]

            # Check if enough key terms appear in parsed text
            matched = sum(1 for t in key_terms if t in all_text)
            threshold = max(2, len(key_terms) // 3)

            if matched >= threshold:
                found_recs.append(rec_text)
            else:
                missing_recs.append(rec_text)

        omission_rate = len(missing_recs) / max(len(expected_recs), 1)

        result = {
            "graph_id": graph_id,
            "filename": filename,
            "found": len(found_recs),
            "total": len(expected_recs),
            "omission_rate": round(omission_rate, 3),
            "missing": missing_recs,
        }
        results.append(result)

        status = "OK" if omission_rate <= 0.2 else "WARN" if omission_rate <= 0.4 else "FAIL"
        print(f"\n  {graph_id}: {len(found_recs)}/{len(expected_recs)} found (omission={omission_rate:.0%}) [{status}]")
        if missing_recs:
            print("    Missing recommendations:")
            for m in missing_recs:
                print(f"      - {m[:80]}")

    return results


def main() -> None:
    """Run all verification checks and output summary."""
    v1_results = verify_v1_consistency()
    v3_results = verify_v3_content_quality()
    v4_results = verify_v4_cpg_coverage()

    # Final summary
    print("\n" + "=" * 70)
    print("OVERALL VERIFICATION SUMMARY")
    print("=" * 70)

    # V1 pass: avg coverage >= 0.7, no FAIL
    v1_avg = sum(r.get("coverage_score", 0) for r in v1_results) / max(len(v1_results), 1)
    v1_fails = sum(1 for r in v1_results if r.get("status") in ("FAIL", "MISSING"))
    v1_pass = v1_avg >= 0.7 and v1_fails == 0
    print(f"V1 (Graph consistency): avg={v1_avg:.3f}, fails={v1_fails} -> {'PASS' if v1_pass else 'FAIL'}")

    # V3 pass: no F grades
    v3_f_count = sum(1 for r in v3_results if r.get("grade") == "F")
    v3_pass = v3_f_count == 0
    print(f"V3 (Content quality):   F-grades={v3_f_count} -> {'PASS' if v3_pass else 'FAIL'}")

    # V4 pass: avg omission rate <= 30%
    v4_avg_omission = sum(r.get("omission_rate", 1) for r in v4_results) / max(len(v4_results), 1)
    v4_pass = v4_avg_omission <= 0.3
    print(f"V4 (CPG coverage):      avg_omission={v4_avg_omission:.0%} -> {'PASS' if v4_pass else 'FAIL'}")

    all_pass = v1_pass and v3_pass and v4_pass
    print(f"\nOverall: {'ALL PASS' if all_pass else 'NEEDS ATTENTION'}")

    # Save JSON results
    output = {
        "v1_graph_consistency": v1_results,
        "v3_content_quality": v3_results,
        "v4_cpg_coverage": v4_results,
        "summary": {
            "v1_avg_coverage": round(v1_avg, 3),
            "v1_fails": v1_fails,
            "v1_pass": v1_pass,
            "v3_f_grades": v3_f_count,
            "v3_pass": v3_pass,
            "v4_avg_omission": round(v4_avg_omission, 3),
            "v4_pass": v4_pass,
            "all_pass": all_pass,
        },
    }

    out_dir = Path("evidence_pack/analysis")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rag_corpus_verification.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
