"""Cross-domain clinical relationships for unified ontology.

Addresses NeurIPS D&B reviewer concern:
"현실 임상은 교차질환인데 왜 분리냐?"

This module defines relationships between clinical domains that reflect
real-world comorbidity patterns, shared mechanisms, and clinical workflows.

References:
- Sepsis → AKI: ~35% incidence (Bagshaw et al., 2008)
- STEMI → Cardiogenic Shock: ~5-8% (Goldberg et al., 2016)
- DKA → AKI: Dehydration-induced (Kitabchi et al., 2009)
- Stroke → AF → HF: Cardioembolic pathway

Version: 1.0 (2026-01-25)
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Tuple


class CrossDomainRelationType(Enum):
    """Types of cross-domain clinical relationships."""
    COMORBIDITY = "comorbidity"           # Condition often co-occurs
    COMPLICATION = "complication"         # One can cause the other
    SHARED_MECHANISM = "shared_mechanism" # Common pathophysiology
    SHARED_TREATMENT = "shared_treatment" # Same intervention used
    CONTRAINDICATION = "contraindication" # Treatment conflict
    MONITORING = "monitoring"             # Need to monitor for
    PROGRESSION = "progression"           # Can progress to


@dataclass
class CrossDomainEdge:
    """A relationship between concepts in different domains."""
    source_domain: str
    source_concept: str
    relation: CrossDomainRelationType
    target_domain: str
    target_concept: str
    evidence_basis: str
    incidence_rate: Optional[float] = None  # 0.0-1.0 if known
    bidirectional: bool = False
    clinical_notes: Optional[str] = None


# =============================================================================
# SEPSIS ↔ AKI CROSS-DOMAIN LINKS
# =============================================================================

SEPSIS_AKI_LINKS = [
    # Sepsis causing AKI
    CrossDomainEdge(
        source_domain="sepsis",
        source_concept="SEPTIC_SHOCK",
        relation=CrossDomainRelationType.COMPLICATION,
        target_domain="aki",
        target_concept="AKI_STAGE_2",
        evidence_basis="Bagshaw et al., Crit Care 2008",
        incidence_rate=0.35,
        clinical_notes="Sepsis-associated AKI occurs in ~35% of septic shock patients",
    ),
    CrossDomainEdge(
        source_domain="sepsis",
        source_concept="HYPOPERFUSION",
        relation=CrossDomainRelationType.SHARED_MECHANISM,
        target_domain="aki",
        target_concept="PRERENAL_AKI",
        evidence_basis="Kellum et al., Nat Rev Nephrol 2021",
        clinical_notes="Hypoperfusion is common mechanism for prerenal AKI in sepsis",
    ),
    # Shared treatments
    CrossDomainEdge(
        source_domain="sepsis",
        source_concept="GIVE_CRYSTALLOID",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="aki",
        target_concept="GIVE_CRYSTALLOID",
        evidence_basis="SSC 2021, KDIGO AKI 2012",
        bidirectional=True,
        clinical_notes="Fluid resuscitation central to both conditions",
    ),
    # Monitoring
    CrossDomainEdge(
        source_domain="sepsis",
        source_concept="SEPSIS_RESUSCITATION",
        relation=CrossDomainRelationType.MONITORING,
        target_domain="aki",
        target_concept="ORDER_CREATININE",
        evidence_basis="SSC 2021",
        clinical_notes="Monitor renal function during sepsis resuscitation",
    ),
    # Contraindication
    CrossDomainEdge(
        source_domain="aki",
        source_concept="AKI_STAGE_3",
        relation=CrossDomainRelationType.CONTRAINDICATION,
        target_domain="sepsis",
        target_concept="GIVE_AMINOGLYCOSIDE",
        evidence_basis="KDIGO AKI 2012",
        clinical_notes="Avoid nephrotoxic antibiotics in AKI",
    ),
]


# =============================================================================
# CHEST PAIN ↔ HEART FAILURE CROSS-DOMAIN LINKS
# =============================================================================

CHEST_PAIN_HF_LINKS = [
    # STEMI → Cardiogenic Shock → HF
    CrossDomainEdge(
        source_domain="chest_pain",
        source_concept="STEMI",
        relation=CrossDomainRelationType.COMPLICATION,
        target_domain="heart_failure",
        target_concept="CARDIOGENIC_SHOCK",
        evidence_basis="Goldberg et al., JACC 2016",
        incidence_rate=0.08,
        clinical_notes="~5-8% of STEMI patients develop cardiogenic shock",
    ),
    CrossDomainEdge(
        source_domain="chest_pain",
        source_concept="STEMI",
        relation=CrossDomainRelationType.PROGRESSION,
        target_domain="heart_failure",
        target_concept="ACUTE_HF",
        evidence_basis="Yeh et al., NEJM 2010",
        incidence_rate=0.15,
        clinical_notes="Post-MI heart failure common complication",
    ),
    # Shared biomarkers
    CrossDomainEdge(
        source_domain="chest_pain",
        source_concept="ORDER_BNP",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="heart_failure",
        target_concept="ORDER_BNP",
        evidence_basis="AHA 2021",
        bidirectional=True,
        clinical_notes="BNP elevated in both ACS and HF",
    ),
    CrossDomainEdge(
        source_domain="chest_pain",
        source_concept="ORDER_TROPONIN",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="heart_failure",
        target_concept="ORDER_TROPONIN",
        evidence_basis="AHA 2022",
        bidirectional=True,
        clinical_notes="Troponin can be elevated in acute HF",
    ),
    # Beta-blocker shared
    CrossDomainEdge(
        source_domain="chest_pain",
        source_concept="GIVE_METOPROLOL",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="heart_failure",
        target_concept="GIVE_METOPROLOL",
        evidence_basis="AHA GDMT",
        bidirectional=True,
        clinical_notes="Beta-blockers used in both ACS and HFrEF",
    ),
]


# =============================================================================
# DKA ↔ AKI CROSS-DOMAIN LINKS
# =============================================================================

DKA_AKI_LINKS = [
    # DKA → Prerenal AKI
    CrossDomainEdge(
        source_domain="dka",
        source_concept="DKA_SEVERE",
        relation=CrossDomainRelationType.COMPLICATION,
        target_domain="aki",
        target_concept="PRERENAL_AKI",
        evidence_basis="Kitabchi et al., Diabetes Care 2009",
        incidence_rate=0.25,
        clinical_notes="Dehydration in DKA causes prerenal AKI",
    ),
    # Shared treatment: fluids
    CrossDomainEdge(
        source_domain="dka",
        source_concept="GIVE_CRYSTALLOID",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="aki",
        target_concept="GIVE_CRYSTALLOID",
        evidence_basis="ADA DKA Guidelines",
        bidirectional=True,
    ),
    # Monitoring overlap
    CrossDomainEdge(
        source_domain="dka",
        source_concept="ORDER_BMP",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="aki",
        target_concept="ORDER_BMP",
        evidence_basis="ADA, KDIGO",
        bidirectional=True,
        clinical_notes="Both require electrolyte monitoring",
    ),
    CrossDomainEdge(
        source_domain="dka",
        source_concept="ORDER_POTASSIUM",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="aki",
        target_concept="ORDER_POTASSIUM",
        evidence_basis="ADA, KDIGO",
        bidirectional=True,
    ),
]


# =============================================================================
# STROKE ↔ CHEST PAIN CROSS-DOMAIN LINKS
# =============================================================================

STROKE_CHEST_PAIN_LINKS = [
    # AF → Cardioembolic stroke
    CrossDomainEdge(
        source_domain="chest_pain",
        source_concept="ATRIAL_FIBRILLATION",
        relation=CrossDomainRelationType.COMPLICATION,
        target_domain="stroke",
        target_concept="ISCHEMIC_STROKE",
        evidence_basis="Wolf et al., Stroke 1991",
        incidence_rate=0.05,
        clinical_notes="AF increases stroke risk 5x",
    ),
    # Anticoagulation shared
    CrossDomainEdge(
        source_domain="stroke",
        source_concept="GIVE_APIXABAN",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="chest_pain",
        target_concept="GIVE_APIXABAN",
        evidence_basis="ARISTOTLE trial",
        bidirectional=True,
        clinical_notes="DOACs for stroke prevention in AF",
    ),
    # BP management shared
    CrossDomainEdge(
        source_domain="stroke",
        source_concept="CONTROL_BLOOD_PRESSURE",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="chest_pain",
        target_concept="CONTROL_BLOOD_PRESSURE",
        evidence_basis="AHA Stroke, AHA Hypertension",
        bidirectional=True,
    ),
]


# =============================================================================
# SEPSIS ↔ DKA CROSS-DOMAIN LINKS
# =============================================================================

SEPSIS_DKA_LINKS = [
    # Infection triggering DKA
    CrossDomainEdge(
        source_domain="sepsis",
        source_concept="INFECTION",
        relation=CrossDomainRelationType.COMPLICATION,
        target_domain="dka",
        target_concept="DKA",
        evidence_basis="Kitabchi et al., Diabetes Care 2009",
        incidence_rate=0.30,
        clinical_notes="Infection is leading precipitant of DKA",
    ),
    # Shared: blood cultures
    CrossDomainEdge(
        source_domain="sepsis",
        source_concept="ORDER_BLOOD_CULTURE",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="dka",
        target_concept="ORDER_BLOOD_CULTURE",
        evidence_basis="ADA DKA Guidelines",
        bidirectional=True,
        clinical_notes="Rule out infection as DKA precipitant",
    ),
    # Shared: lactate
    CrossDomainEdge(
        source_domain="sepsis",
        source_concept="ORDER_LACTATE",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="dka",
        target_concept="ORDER_LACTATE",
        evidence_basis="SSC 2021, ADA",
        bidirectional=True,
        clinical_notes="Lactate elevated in both conditions",
    ),
]


# =============================================================================
# HEART FAILURE ↔ AKI CROSS-DOMAIN LINKS (Cardiorenal Syndrome)
# =============================================================================

HF_AKI_LINKS = [
    # Cardiorenal syndrome
    CrossDomainEdge(
        source_domain="heart_failure",
        source_concept="ACUTE_HF",
        relation=CrossDomainRelationType.COMPLICATION,
        target_domain="aki",
        target_concept="AKI_STAGE_1",
        evidence_basis="Ronco et al., JACC 2008",
        incidence_rate=0.30,
        clinical_notes="Cardiorenal syndrome type 1: acute HF → AKI",
    ),
    CrossDomainEdge(
        source_domain="aki",
        source_concept="AKI_STAGE_3",
        relation=CrossDomainRelationType.COMPLICATION,
        target_domain="heart_failure",
        target_concept="VOLUME_OVERLOAD",
        evidence_basis="Ronco et al., JACC 2008",
        clinical_notes="Cardiorenal syndrome type 3: AKI → fluid overload",
    ),
    # Diuretic shared
    CrossDomainEdge(
        source_domain="heart_failure",
        source_concept="GIVE_FUROSEMIDE",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="aki",
        target_concept="GIVE_FUROSEMIDE",
        evidence_basis="AHA HF, KDIGO",
        bidirectional=True,
        clinical_notes="Diuretics in both, but caution in AKI",
    ),
    # Contraindication: nephrotoxins in HF with renal dysfunction
    CrossDomainEdge(
        source_domain="aki",
        source_concept="AKI_STAGE_2",
        relation=CrossDomainRelationType.CONTRAINDICATION,
        target_domain="heart_failure",
        target_concept="GIVE_NSAID",
        evidence_basis="KDIGO, AHA",
        clinical_notes="Avoid NSAIDs in cardiorenal syndrome",
    ),
]


# =============================================================================
# UNIVERSAL CROSS-DOMAIN LINKS
# =============================================================================

UNIVERSAL_LINKS = [
    # Vital signs monitoring across all domains
    CrossDomainEdge(
        source_domain="universal",
        source_concept="ASSESS_VITAL_SIGNS",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="sepsis",
        target_concept="ASSESS_VITAL_SIGNS",
        evidence_basis="Standard of care",
        bidirectional=True,
    ),
    CrossDomainEdge(
        source_domain="universal",
        source_concept="ASSESS_VITAL_SIGNS",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="chest_pain",
        target_concept="ASSESS_VITAL_SIGNS",
        evidence_basis="Standard of care",
        bidirectional=True,
    ),
    # Central line for multiple conditions
    CrossDomainEdge(
        source_domain="sepsis",
        source_concept="PLACE_CENTRAL_LINE",
        relation=CrossDomainRelationType.SHARED_TREATMENT,
        target_domain="heart_failure",
        target_concept="PLACE_CENTRAL_LINE",
        evidence_basis="ICU protocols",
        bidirectional=True,
        clinical_notes="Central access for vasopressors/inotropes",
    ),
]


# =============================================================================
# AGGREGATION
# =============================================================================

def get_all_cross_domain_edges() -> List[CrossDomainEdge]:
    """Get all cross-domain edges."""
    all_edges = []
    all_edges.extend(SEPSIS_AKI_LINKS)
    all_edges.extend(CHEST_PAIN_HF_LINKS)
    all_edges.extend(DKA_AKI_LINKS)
    all_edges.extend(STROKE_CHEST_PAIN_LINKS)
    all_edges.extend(SEPSIS_DKA_LINKS)
    all_edges.extend(HF_AKI_LINKS)
    all_edges.extend(UNIVERSAL_LINKS)
    return all_edges


def get_cross_domain_stats() -> Dict:
    """Get statistics about cross-domain edges."""
    edges = get_all_cross_domain_edges()

    by_relation = {}
    by_source_domain = {}
    by_target_domain = {}

    for edge in edges:
        # By relation type
        rel = edge.relation.value
        by_relation[rel] = by_relation.get(rel, 0) + 1

        # By source domain
        by_source_domain[edge.source_domain] = by_source_domain.get(edge.source_domain, 0) + 1

        # By target domain
        by_target_domain[edge.target_domain] = by_target_domain.get(edge.target_domain, 0) + 1

    # Domain pairs
    domain_pairs = set()
    for edge in edges:
        pair = tuple(sorted([edge.source_domain, edge.target_domain]))
        domain_pairs.add(pair)

    return {
        "total_edges": len(edges),
        "by_relation_type": by_relation,
        "by_source_domain": by_source_domain,
        "by_target_domain": by_target_domain,
        "unique_domain_pairs": len(domain_pairs),
        "domain_pairs": list(domain_pairs),
    }


def export_to_jsonl(filepath: str):
    """Export cross-domain edges to JSONL."""
    import json

    edges = get_all_cross_domain_edges()
    with open(filepath, "w") as f:
        for edge in edges:
            f.write(json.dumps({
                "source_domain": edge.source_domain,
                "source_concept": edge.source_concept,
                "relation": edge.relation.value,
                "target_domain": edge.target_domain,
                "target_concept": edge.target_concept,
                "evidence_basis": edge.evidence_basis,
                "incidence_rate": edge.incidence_rate,
                "bidirectional": edge.bidirectional,
                "clinical_notes": edge.clinical_notes,
            }) + "\n")


if __name__ == "__main__":
    stats = get_cross_domain_stats()
    print("=" * 60)
    print("CROSS-DOMAIN LINKING STATISTICS")
    print("=" * 60)
    print(f"Total Edges: {stats['total_edges']}")
    print(f"Unique Domain Pairs: {stats['unique_domain_pairs']}")
    print("-" * 60)
    print("By Relation Type:")
    for rel, count in sorted(stats['by_relation_type'].items()):
        print(f"  {rel:<20}: {count}")
    print("-" * 60)
    print("Domain Pairs Connected:")
    for pair in sorted(stats['domain_pairs']):
        print(f"  {pair[0]} ↔ {pair[1]}")
    print("=" * 60)
