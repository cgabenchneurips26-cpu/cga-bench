"""Context-aware cross-encoder reranking for entity linking.

Addresses NeurIPS D&B reviewer concern:
"환자 컨텍스트가 EL에 어떻게 반영되는지 불명확"

This module injects patient context into the cross-encoder reranking
pipeline to improve disambiguation accuracy.

Key concepts:
- PatientContext: Encapsulates patient-specific information
- ContextualCandidate: Candidate with context-adjusted score
- ContextAwareReranker: Cross-encoder wrapper with context injection

Version: 1.0 (2026-01-25)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum


class ContextSignal(Enum):
    """Types of context signals for reranking."""
    DOMAIN_MATCH = "domain_match"        # Action matches patient's primary domain
    COMORBIDITY_RELEVANT = "comorbidity" # Action relevant to comorbidity
    ALLERGY_CONTRAINDICATED = "allergy"  # Drug contraindicated by allergy
    DRUG_INTERACTION = "interaction"     # Potential drug interaction
    RECENT_LAB_RELEVANT = "lab_context"  # Action relevant to recent lab


@dataclass
class PatientContext:
    """Patient-specific context for cross-encoder injection.

    This context is used to adjust cross-encoder scores during
    candidate reranking for entity linking.

    Attributes:
        patient_id: Unique patient identifier
        primary_domain: Primary clinical domain (e.g., "sepsis", "chest_pain")
        active_conditions: Set of active ICD-10 or SNOMED codes
        allergies: Set of known drug allergies (normalized)
        current_medications: Set of current medication concept IDs
        recent_labs: Dict of recent lab results (concept_id -> value)
        recent_vitals: Dict of recent vital signs
        scenario_phase: Current treatment phase (e.g., "initial", "resuscitation")
    """
    patient_id: str
    primary_domain: str
    active_conditions: Set[str] = field(default_factory=set)
    allergies: Set[str] = field(default_factory=set)
    current_medications: Set[str] = field(default_factory=set)
    recent_labs: Dict[str, float] = field(default_factory=dict)
    recent_vitals: Dict[str, float] = field(default_factory=dict)
    scenario_phase: str = "initial"

    # Cross-domain relationships (populated from cross_domain_links)
    comorbidity_domains: Set[str] = field(default_factory=set)

    def get_context_string(self) -> str:
        """Generate a context string for cross-encoder prompt injection.

        Returns:
            Human-readable context string for prompt augmentation.
        """
        parts = [f"Domain: {self.primary_domain}"]

        if self.active_conditions:
            parts.append(f"Conditions: {', '.join(sorted(self.active_conditions)[:5])}")

        if self.allergies:
            parts.append(f"Allergies: {', '.join(sorted(self.allergies))}")

        if self.current_medications:
            parts.append(f"Current meds: {', '.join(sorted(self.current_medications)[:5])}")

        if self.recent_labs:
            lab_str = ", ".join(f"{k}={v:.1f}" for k, v in sorted(self.recent_labs.items())[:5])
            parts.append(f"Recent labs: {lab_str}")

        if self.recent_vitals:
            vital_str = ", ".join(f"{k}={v:.0f}" for k, v in sorted(self.recent_vitals.items()))
            parts.append(f"Vitals: {vital_str}")

        parts.append(f"Phase: {self.scenario_phase}")

        return "; ".join(parts)


@dataclass
class ContextualCandidate:
    """A candidate concept with context-adjusted scoring.

    Attributes:
        concept_id: The candidate concept ID
        base_score: Original cross-encoder score (0.0-1.0)
        context_signals: List of context signals that affected scoring
        context_adjustment: Score adjustment from context (-0.5 to +0.5)
        final_score: base_score + context_adjustment (clamped 0-1)
        explanation: Human-readable explanation of adjustment
    """
    concept_id: str
    base_score: float
    context_signals: List[Tuple[ContextSignal, str]] = field(default_factory=list)
    context_adjustment: float = 0.0

    @property
    def final_score(self) -> float:
        return max(0.0, min(1.0, self.base_score + self.context_adjustment))

    @property
    def explanation(self) -> str:
        if not self.context_signals:
            return "No context adjustment"
        signals = [f"{s[0].value}: {s[1]}" for s in self.context_signals]
        return f"Adjustment {self.context_adjustment:+.2f} from: {'; '.join(signals)}"


@dataclass
class RerankerConfig:
    """Configuration for context-aware reranking.

    Attributes:
        domain_match_boost: Boost for domain-matching candidates
        comorbidity_boost: Boost for comorbidity-relevant candidates
        allergy_penalty: Penalty for allergy-contraindicated drugs
        interaction_penalty: Penalty for potential drug interactions
        lab_relevance_boost: Boost for lab-relevant actions
        max_adjustment: Maximum total adjustment (positive or negative)
    """
    domain_match_boost: float = 0.15
    comorbidity_boost: float = 0.10
    allergy_penalty: float = -0.40
    interaction_penalty: float = -0.25
    lab_relevance_boost: float = 0.05
    max_adjustment: float = 0.50


class ContextAwareReranker:
    """Cross-encoder wrapper with patient context injection.

    This class wraps a cross-encoder and adjusts scores based on
    patient context to improve disambiguation accuracy.

    The reranking formula:
        final_score = base_score + Σ(context_adjustments)

    Context adjustments:
    1. Domain match: +0.15 if candidate domain matches patient's primary domain
    2. Comorbidity relevance: +0.10 if action is relevant to known comorbidity
    3. Allergy contraindication: -0.40 if drug is contraindicated by allergy
    4. Drug interaction: -0.25 if potential interaction with current meds
    5. Lab relevance: +0.05 if action is relevant to abnormal lab
    """

    def __init__(
        self,
        config: Optional[RerankerConfig] = None,
        allergy_drug_mappings: Optional[Dict[str, Set[str]]] = None,
        drug_interaction_pairs: Optional[Set[Tuple[str, str]]] = None,
    ):
        """Initialize the context-aware reranker.

        Args:
            config: Reranker configuration (uses defaults if None)
            allergy_drug_mappings: Mapping from allergy to contraindicated drugs
            drug_interaction_pairs: Set of (drug1, drug2) interaction pairs
        """
        self.config = config or RerankerConfig()
        self._allergy_mappings = allergy_drug_mappings or self._default_allergy_mappings()
        self._interaction_pairs = drug_interaction_pairs or self._default_interaction_pairs()

        # Domain to relevant concept prefixes
        self._domain_concept_prefixes: Dict[str, Set[str]] = {
            "sepsis": {"ORDER_BLOOD_CULTURE", "ORDER_LACTATE", "GIVE_BROAD_SPECTRUM",
                       "START_VASOPRESSOR", "GIVE_CRYSTALLOID"},
            "chest_pain": {"ORDER_TROPONIN", "ORDER_ECG", "GIVE_ASPIRIN", "GIVE_HEPARIN",
                           "ACTIVATE_CATH", "GIVE_NITROGLYCERIN"},
            "aki": {"ORDER_CREATININE", "ORDER_BMP", "ORDER_URINALYSIS", "DISCONTINUE",
                    "AVOID_NEPHROTOXIC"},
            "dka": {"ORDER_GLUCOSE", "START_INSULIN", "ORDER_BMP", "ORDER_ABG",
                    "GIVE_POTASSIUM"},
            "stroke": {"ORDER_CT_HEAD", "GIVE_ALTEPLASE", "ASSESS_NIHSS",
                       "ACTIVATE_STROKE", "CONTROL_BLOOD_PRESSURE"},
            "heart_failure": {"ORDER_BNP", "GIVE_FUROSEMIDE", "ORDER_ECHOCARDIOGRAM",
                              "INITIATE_ACE", "INITIATE_BETA"},
        }

        # Lab to relevant action prefixes
        self._lab_action_relevance: Dict[str, Set[str]] = {
            "lactate": {"ORDER_LACTATE", "GIVE_CRYSTALLOID", "START_VASOPRESSOR"},
            "creatinine": {"ORDER_CREATININE", "AVOID_NEPHROTOXIC", "CONSULT_NEPHROLOGY"},
            "troponin": {"ORDER_TROPONIN", "GIVE_HEPARIN", "ACTIVATE_CATH"},
            "bnp": {"ORDER_BNP", "GIVE_FUROSEMIDE", "ORDER_ECHOCARDIOGRAM"},
            "glucose": {"ORDER_GLUCOSE", "START_INSULIN", "GIVE_DEXTROSE"},
            "potassium": {"ORDER_POTASSIUM", "GIVE_POTASSIUM", "GIVE_CALCIUM"},
        }

    def _default_allergy_mappings(self) -> Dict[str, Set[str]]:
        """Default allergy to contraindicated drug mappings."""
        return {
            "penicillin": {"GIVE_PIPERACILLIN", "GIVE_AMPICILLIN", "GIVE_AMOXICILLIN"},
            "sulfa": {"GIVE_SULFAMETHOXAZOLE", "GIVE_BACTRIM", "GIVE_FUROSEMIDE"},
            "cephalosporin": {"GIVE_CEFTRIAXONE", "GIVE_CEFEPIME", "GIVE_CEFAZOLIN"},
            "nsaid": {"GIVE_IBUPROFEN", "GIVE_KETOROLAC", "GIVE_NAPROXEN"},
            "aspirin": {"GIVE_ASPIRIN"},
            "contrast": {"ORDER_CT_CONTRAST", "ORDER_CTA", "ORDER_ANGIOGRAM"},
            "ace_inhibitor": {"GIVE_LISINOPRIL", "GIVE_ENALAPRIL", "INITIATE_ACE"},
            "beta_blocker": {"GIVE_METOPROLOL", "GIVE_CARVEDILOL", "INITIATE_BETA"},
        }

    def _default_interaction_pairs(self) -> Set[Tuple[str, str]]:
        """Default drug interaction pairs."""
        return {
            # Anticoagulant interactions
            ("GIVE_HEPARIN", "GIVE_ENOXAPARIN"),
            ("GIVE_WARFARIN", "GIVE_APIXABAN"),
            ("GIVE_APIXABAN", "GIVE_RIVAROXABAN"),
            # Dual antiplatelet
            ("GIVE_ASPIRIN", "GIVE_IBUPROFEN"),  # Ibuprofen blocks aspirin
            # Vasopressor conflicts
            ("START_VASOPRESSOR_NOREPINEPHRINE", "START_VASOPRESSOR_DOPAMINE"),
            # Potassium-affecting drugs
            ("GIVE_POTASSIUM", "GIVE_SPIRONOLACTONE"),
            # QT-prolonging combinations
            ("GIVE_AMIODARONE", "GIVE_HALOPERIDOL"),
            ("GIVE_AZITHROMYCIN", "GIVE_AMIODARONE"),
        }

    def rerank(
        self,
        candidates: List[Tuple[str, float]],  # [(concept_id, base_score), ...]
        context: PatientContext,
    ) -> List[ContextualCandidate]:
        """Rerank candidates based on patient context.

        Args:
            candidates: List of (concept_id, base_score) tuples
            context: Patient context for scoring adjustment

        Returns:
            List of ContextualCandidate sorted by final_score descending
        """
        results = []

        for concept_id, base_score in candidates:
            signals = []
            adjustment = 0.0

            # 1. Domain match check
            domain_boost = self._check_domain_match(concept_id, context.primary_domain)
            if domain_boost > 0:
                signals.append((ContextSignal.DOMAIN_MATCH, context.primary_domain))
                adjustment += domain_boost

            # 2. Comorbidity relevance
            for comorbid_domain in context.comorbidity_domains:
                comorbid_boost = self._check_domain_match(concept_id, comorbid_domain)
                if comorbid_boost > 0:
                    signals.append((ContextSignal.COMORBIDITY_RELEVANT, comorbid_domain))
                    adjustment += self.config.comorbidity_boost
                    break  # Only count once

            # 3. Allergy contraindication
            allergy_penalty = self._check_allergy_contraindication(concept_id, context.allergies)
            if allergy_penalty < 0:
                signals.append((ContextSignal.ALLERGY_CONTRAINDICATED,
                               f"contraindicated by allergy"))
                adjustment += allergy_penalty

            # 4. Drug interaction
            interaction_penalty = self._check_drug_interaction(concept_id, context.current_medications)
            if interaction_penalty < 0:
                signals.append((ContextSignal.DRUG_INTERACTION,
                               "potential drug interaction"))
                adjustment += interaction_penalty

            # 5. Lab relevance
            lab_boost = self._check_lab_relevance(concept_id, context.recent_labs)
            if lab_boost > 0:
                signals.append((ContextSignal.RECENT_LAB_RELEVANT, "relevant to recent lab"))
                adjustment += lab_boost

            # Clamp total adjustment
            adjustment = max(-self.config.max_adjustment,
                            min(self.config.max_adjustment, adjustment))

            results.append(ContextualCandidate(
                concept_id=concept_id,
                base_score=base_score,
                context_signals=signals,
                context_adjustment=adjustment,
            ))

        # Sort by final score descending
        results.sort(key=lambda c: c.final_score, reverse=True)
        return results

    def _check_domain_match(self, concept_id: str, domain: str) -> float:
        """Check if concept matches domain prefixes."""
        if domain not in self._domain_concept_prefixes:
            return 0.0

        prefixes = self._domain_concept_prefixes[domain]
        concept_upper = concept_id.upper()

        for prefix in prefixes:
            if concept_upper.startswith(prefix):
                return self.config.domain_match_boost

        return 0.0

    def _check_allergy_contraindication(
        self,
        concept_id: str,
        allergies: Set[str],
    ) -> float:
        """Check if concept is contraindicated by any allergy."""
        concept_upper = concept_id.upper()

        for allergy in allergies:
            allergy_lower = allergy.lower()
            if allergy_lower in self._allergy_mappings:
                contraindicated = self._allergy_mappings[allergy_lower]
                for drug_prefix in contraindicated:
                    if concept_upper.startswith(drug_prefix):
                        return self.config.allergy_penalty

        return 0.0

    def _check_drug_interaction(
        self,
        concept_id: str,
        current_meds: Set[str],
    ) -> float:
        """Check for potential drug interactions."""
        concept_upper = concept_id.upper()

        for med in current_meds:
            med_upper = med.upper()
            # Check both orderings
            if (concept_upper, med_upper) in self._interaction_pairs:
                return self.config.interaction_penalty
            if (med_upper, concept_upper) in self._interaction_pairs:
                return self.config.interaction_penalty

        return 0.0

    def _check_lab_relevance(
        self,
        concept_id: str,
        recent_labs: Dict[str, float],
    ) -> float:
        """Check if concept is relevant to abnormal labs."""
        concept_upper = concept_id.upper()

        for lab_name in recent_labs.keys():
            lab_lower = lab_name.lower()
            if lab_lower in self._lab_action_relevance:
                relevant_prefixes = self._lab_action_relevance[lab_lower]
                for prefix in relevant_prefixes:
                    if concept_upper.startswith(prefix):
                        return self.config.lab_relevance_boost

        return 0.0

    def create_augmented_prompt(
        self,
        query: str,
        candidate: str,
        context: PatientContext,
    ) -> str:
        """Create an augmented prompt for cross-encoder scoring.

        This method generates a prompt that includes patient context
        for more accurate relevance scoring.

        Args:
            query: The action query string
            candidate: The candidate concept ID
            context: Patient context

        Returns:
            Augmented prompt string for cross-encoder
        """
        context_str = context.get_context_string()

        return f"""Given the patient context and action query, rate the relevance of the candidate concept.

Patient Context: {context_str}

Query: "{query}"
Candidate: {candidate}

Rate relevance from 0.0 (completely irrelevant) to 1.0 (perfect match).
Consider domain appropriateness, contraindications, and clinical relevance."""


def create_context_from_patient_state(
    patient_state: Dict[str, Any],
    domain: str,
    scenario_phase: str = "initial",
) -> PatientContext:
    """Factory function to create PatientContext from patient state dict.

    Args:
        patient_state: Dictionary containing patient data
        domain: Primary clinical domain
        scenario_phase: Current treatment phase

    Returns:
        PatientContext instance
    """
    # Extract vitals
    vitals = {}
    if "vital_signs" in patient_state:
        vs = patient_state["vital_signs"]
        if isinstance(vs, dict):
            vitals = {
                "map_mmhg": vs.get("map_mmhg", vs.get("mean_arterial_pressure")),
                "hr_bpm": vs.get("hr_bpm", vs.get("heart_rate")),
                "rr_rpm": vs.get("rr_rpm", vs.get("respiratory_rate")),
                "spo2_pct": vs.get("spo2_pct", vs.get("oxygen_saturation")),
                "temp_c": vs.get("temp_c", vs.get("temperature")),
            }
            vitals = {k: v for k, v in vitals.items() if v is not None}

    # Extract labs
    labs = {}
    if "lab_results" in patient_state:
        for lab in patient_state["lab_results"]:
            if isinstance(lab, dict):
                name = lab.get("name", lab.get("test_name", ""))
                value = lab.get("value")
                if name and value is not None:
                    labs[name.lower()] = float(value)

    # Extract allergies
    allergies = set()
    if "allergies" in patient_state:
        allergies = set(a.lower() for a in patient_state["allergies"] if a)

    # Extract current medications
    medications = set()
    if "current_medications" in patient_state:
        for med in patient_state["current_medications"]:
            if isinstance(med, dict):
                medications.add(med.get("medication_id", "").upper())
            elif isinstance(med, str):
                medications.add(med.upper())

    # Extract conditions
    conditions = set()
    if "active_conditions" in patient_state:
        conditions = set(patient_state["active_conditions"])
    elif "diagnoses" in patient_state:
        conditions = set(patient_state["diagnoses"])

    return PatientContext(
        patient_id=patient_state.get("patient_id", "unknown"),
        primary_domain=domain,
        active_conditions=conditions,
        allergies=allergies,
        current_medications=medications,
        recent_labs=labs,
        recent_vitals=vitals,
        scenario_phase=scenario_phase,
    )


if __name__ == "__main__":
    # Test the context-aware reranker
    print("=" * 60)
    print("CONTEXT-AWARE RERANKER TEST")
    print("=" * 60)

    # Create a test patient context
    context = PatientContext(
        patient_id="TEST001",
        primary_domain="sepsis",
        active_conditions={"septic_shock", "pneumonia"},
        allergies={"penicillin"},
        current_medications={"GIVE_VANCOMYCIN", "START_VASOPRESSOR_NOREPINEPHRINE"},
        recent_labs={"lactate": 4.2, "creatinine": 1.8},
        recent_vitals={"map_mmhg": 58, "hr_bpm": 110},
        scenario_phase="resuscitation",
        comorbidity_domains={"aki"},
    )

    print(f"\nPatient Context:\n{context.get_context_string()}")

    # Create reranker
    reranker = ContextAwareReranker()

    # Test candidates
    candidates = [
        ("ORDER_LACTATE", 0.85),
        ("GIVE_PIPERACILLIN_TAZOBACTAM", 0.80),  # Contraindicated (penicillin allergy)
        ("GIVE_CRYSTALLOID", 0.75),
        ("ORDER_CT_HEAD", 0.70),  # Wrong domain
        ("START_VASOPRESSOR_DOPAMINE", 0.65),  # Interaction with norepinephrine
        ("ORDER_CREATININE", 0.60),  # Relevant to comorbid AKI
    ]

    print(f"\n{'Original Candidates:':<30}")
    for cid, score in candidates:
        print(f"  {cid:<40} {score:.2f}")

    # Rerank
    results = reranker.rerank(candidates, context)

    print(f"\n{'Reranked Results:':<30}")
    print("-" * 60)
    for r in results:
        print(f"  {r.concept_id:<40} {r.base_score:.2f} → {r.final_score:.2f}")
        if r.context_signals:
            print(f"    → {r.explanation}")

    print("=" * 60)
