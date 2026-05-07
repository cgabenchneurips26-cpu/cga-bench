#!/usr/bin/env python3
"""V2: RAG retrieval accuracy test across all 25 domains.

For each domain, creates a representative clinical query and verifies
the RAG system returns documents from the correct domain.

Usage:
    python scripts/verify_rag_retrieval.py
"""

import json
from pathlib import Path
import sys
from typing import Any

_CGA_BENCH_DIR = Path(__file__).resolve().parent.parent
_AGENTBEATS_DIR = _CGA_BENCH_DIR.parent  # AnonProject/ (contains cga_bench package)
PARSED_DIR = _CGA_BENCH_DIR / "cpg_sources"

# Add AnonProject dir so 'cga_bench.*' imports resolve
_ab_str = str(_AGENTBEATS_DIR)
if _ab_str not in sys.path:
    sys.path.insert(0, _ab_str)

# Domain -> representative clinical query mapping
DOMAIN_QUERIES: dict[str, str] = {
    "ssc_sepsis": (
        "Patient with fever 39.2C, heart rate 120, blood pressure 80/50, "
        "suspected sepsis. Lactate 4.2 mmol/L. What initial management steps?"
    ),
    "aha_chest_pain": (
        "55-year-old male with acute chest pain, ST elevation in leads II III aVF, "
        "troponin elevated. Suspected STEMI with inferior wall involvement."
    ),
    "kdigo_aki": (
        "Patient with creatinine rising from 1.0 to 2.5 mg/dL over 48 hours, "
        "urine output decreased to 0.3 mL/kg/hr. Acute kidney injury management."
    ),
    "aha_heart_failure": (
        "Patient with ejection fraction 25%, BNP 1200, dyspnea at rest, "
        "bilateral pulmonary edema. Heart failure with reduced ejection fraction."
    ),
    "aha_stroke": (
        "Patient with acute onset left-sided weakness, NIHSS 14, last known well "
        "90 minutes ago. CT shows no hemorrhage. Acute ischemic stroke evaluation."
    ),
    "ada_dka": (
        "Patient with blood glucose 450 mg/dL, pH 7.15, bicarbonate 8 mEq/L, "
        "positive ketones. Diabetic ketoacidosis management with insulin and fluids."
    ),
    "esc_af": (
        "Patient with new-onset atrial fibrillation, ventricular rate 140/min, "
        "CHA2DS2-VASc score 4. Rate control and anticoagulation decisions."
    ),
    "ats_idsa_cap": (
        "Patient with community-acquired pneumonia, productive cough, fever 38.8C, "
        "bilateral infiltrates on chest x-ray. Empiric antibiotic selection."
    ),
    "gold_copd": (
        "COPD patient with acute exacerbation, increased dyspnea, purulent sputum, "
        "SpO2 88% on room air. Bronchodilator and steroid management."
    ),
    "acg_gi_bleeding": (
        "Patient with hematemesis, melena, hemoglobin 7.2, heart rate 110, "
        "blood pressure 90/60. Upper GI bleeding with hemodynamic instability."
    ),
    "aha_hypertensive": (
        "Patient with blood pressure 220/130 mmHg, headache, chest pain, "
        "creatinine rising. Hypertensive emergency with end-organ damage."
    ),
    "kdigo_contrast_aki": (
        "Patient with eGFR 35 mL/min needs contrast CT. Pre-hydration protocol "
        "for contrast-induced acute kidney injury prevention."
    ),
    "esc_pe": (
        "Patient with acute dyspnea, tachycardia, D-dimer elevated, "
        "CT pulmonary angiography shows bilateral pulmonary embolism."
    ),
    "wao_anaphylaxis": (
        "Patient with sudden onset urticaria, tongue swelling, wheezing, "
        "blood pressure 70/40 after bee sting. Anaphylaxis with epinephrine."
    ),
    "aha_acls": (
        "Patient found unresponsive, no pulse, monitor shows ventricular "
        "fibrillation. CPR initiated, defibrillator ready. ACLS cardiac arrest."
    ),
    "aes_status_epilepticus": (
        "Patient with continuous seizure activity lasting 10 minutes, "
        "not responding to initial benzodiazepine. Status epilepticus management."
    ),
    "gina_asthma": (
        "Patient with severe asthma exacerbation, unable to speak full sentences, "
        "SpO2 90%, peak flow 40% predicted. Salbutamol and corticosteroid treatment."
    ),
    "idsa_meningitis": (
        "Patient with fever, neck stiffness, altered mental status. "
        "CSF shows pleocytosis. Bacterial meningitis empiric antibiotics ceftriaxone."
    ),
    "aact_toxicology": (
        "Patient with suspected opioid overdose, respiratory rate 6, "
        "pinpoint pupils. Naloxone administration and decontamination protocol."
    ),
    "aba_burn": (
        "Patient with 40% TBSA burn, Parkland formula fluid resuscitation, "
        "lactated Ringer's solution, urine output monitoring."
    ),
    "aabb_transfusion": (
        "Patient with hemoglobin 6.5 g/dL, active bleeding, requires "
        "red blood cell transfusion with crossmatch and platelet assessment."
    ),
    "acog_obstetric": (
        "Postpartum patient with estimated blood loss 1500 mL, uterine atony, "
        "obstetric hemorrhage management with oxytocin and transfusion."
    ),
    "aha_pals": (
        "Pediatric patient, 8 kg infant, unresponsive with bradycardia 40/min, "
        "poor perfusion. Pediatric advanced life support with epinephrine dosing."
    ),
    "apa_agitation": (
        "Patient in emergency department with severe psychomotor agitation, "
        "verbal de-escalation failed. Haloperidol and lorazepam for acute management."
    ),
    "universal_safety": (
        "Patient identification verification, allergy check before medication "
        "administration, vital sign monitoring, clinical safety protocols."
    ),
}

# Source name -> expected keywords in doc_id or source field
EXPECTED_DOMAINS: dict[str, list[str]] = {
    "ssc_sepsis": ["ssc", "sepsis"],
    "aha_chest_pain": ["chest", "pain", "aha-2021"],
    "kdigo_aki": ["aki", "kdigo", "kidney"],
    "aha_heart_failure": ["heart", "failure"],
    "aha_stroke": ["stroke", "aha-2019"],
    "ada_dka": ["dka", "ada"],
    "esc_af": ["af", "fibrillation", "esc-2020"],
    "ats_idsa_cap": ["cap", "pneumonia", "ats"],
    "gold_copd": ["copd", "gold"],
    "acg_gi_bleeding": ["gi", "bleeding", "acg"],
    "aha_hypertensive": ["hypertensive", "aha-2017"],
    "kdigo_contrast_aki": ["contrast", "kdigo"],
    "esc_pe": ["pe", "pulmonary", "esc-2019"],
    "wao_anaphylaxis": ["anaphylaxis", "wao"],
    "aha_acls": ["acls", "cardiac", "aha-2020"],
    "aes_status_epilepticus": ["epilepticus", "aes", "status"],
    "gina_asthma": ["asthma", "gina"],
    "idsa_meningitis": ["meningitis", "idsa"],
    "aact_toxicology": ["toxicology", "aact"],
    "aba_burn": ["burn", "aba"],
    "aabb_transfusion": ["transfusion", "aabb"],
    "acog_obstetric": ["obstetric", "acog"],
    "aha_pals": ["pals", "pediatric"],
    "apa_agitation": ["agitation", "apa"],
    "universal_safety": ["universal", "safety"],
}


def check_domain_match(retrieved_docs: list[Any], expected_keywords: list[str]) -> tuple[bool, str]:
    """Check if top results contain the expected domain.

    Args:
        retrieved_docs: list of RetrievedDocument objects (have .doc_id, .source, .score)
        expected_keywords: keywords that should appear in doc_id or source
    """
    if not retrieved_docs:
        return False, "no results"

    # Check top-3 results for domain match
    for i, doc in enumerate(retrieved_docs[:3]):
        doc_id = (doc.doc_id or "").lower()
        source = (doc.source or "").lower()

        for kw in expected_keywords:
            if kw in doc_id or kw in source:
                return True, f"rank_{i + 1}_doc_id"

    # Fallback: check if ANY top-5 result matches
    for i, doc in enumerate(retrieved_docs[:5]):
        doc_id = (doc.doc_id or "").lower()
        source = (doc.source or "").lower()
        for kw in expected_keywords:
            if kw in doc_id or kw in source:
                return True, f"rank_{i + 1}_fallback"

    # Report what was actually returned
    top_sources = [(d.source or "?")[:30] for d in retrieved_docs[:3]]
    return False, f"wrong_domain: {top_sources}"


def main() -> None:
    """Run RAG retrieval accuracy test for all 25 domains."""
    print("=" * 70)
    print("VERIFICATION 2: RAG retrieval accuracy (25 domains)")
    print("=" * 70)

    from cga_bench.agent_runner.rag_agent import CPGDocumentStore

    store = CPGDocumentStore(cpg_sources_path=str(PARSED_DIR))
    store.load()
    print(f"Document store loaded: {len(store.documents)} documents\n")

    results: list[dict[str, Any]] = []
    correct = 0
    total = 0

    for domain, query in DOMAIN_QUERIES.items():
        total += 1
        expected_kws = EXPECTED_DOMAINS.get(domain, [])

        # Run retrieval (returns list[RetrievedDocument])
        retrieved = store.retrieve(query, top_k=5)

        # Check if correct domain is returned
        matched, match_detail = check_domain_match(retrieved, expected_kws)

        if matched:
            correct += 1
            status = "OK"
        else:
            status = "MISS"

        # Collect top-3 doc info for reporting
        top_docs = []
        for doc in retrieved[:3]:
            top_docs.append(f"{doc.source}:{doc.doc_id}({doc.score:.3f})")

        result = {
            "domain": domain,
            "status": status,
            "match_detail": match_detail,
            "top_3_docs": top_docs,
            "n_results": len(retrieved),
        }
        results.append(result)

        flag = "  " if status == "OK" else "**"
        print(f"{flag} {domain:30s} {status:4s} | {match_detail}")
        if status == "MISS":
            print(f"     top-3: {', '.join(top_docs)}")

    # Summary
    accuracy = correct / max(total, 1)
    print(f"\n{'=' * 70}")
    print(f"Accuracy: {correct}/{total} ({accuracy:.0%})")
    print(f"PASS criteria (25/25): {'PASS' if correct == total else 'FAIL'}")

    # Save results
    output = {
        "v2_retrieval_accuracy": results,
        "summary": {
            "correct": correct,
            "total": total,
            "accuracy": round(accuracy, 3),
            "pass": correct == total,
        },
    }

    out_dir = _CGA_BENCH_DIR / "evidence_pack" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rag_retrieval_verification.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
