"""Clinical Policy / Conformance Layer.

Responsible for answering: "Is this concept allowed/forbidden/required in this context?"

This module is SEPARATE from Concept Mapping. It takes normalized concepts
and makes clinical policy decisions based on patient context, guidelines,
and safety constraints.

Architecture:
    MappingResult (from Mapper)
           ↓
    ┌─────────────────────────────────────────┐
    │          ClinicalPolicy                  │
    │  ┌───────────────────────────────────┐  │
    │  │ Patient Context                    │  │
    │  │ - Allergies                        │  │
    │  │ - Comorbidities                    │  │
    │  │ - Current medications              │  │
    │  │ - Vital signs / Labs               │  │
    │  └───────────────────────────────────┘  │
    │           ↓                              │
    │  ┌───────────────────────────────────┐  │
    │  │ Constraint Evaluation             │  │
    │  │ - Allergy contraindications       │  │
    │  │ - Drug-drug interactions          │  │
    │  │ - Comorbidity restrictions        │  │
    │  │ - Clinical state requirements     │  │
    │  └───────────────────────────────────┘  │
    │           ↓                              │
    │  ┌───────────────────────────────────┐  │
    │  │ Guideline Compliance              │  │
    │  │ - Mandatory actions               │  │
    │  │ - Timing requirements             │  │
    │  │ - Sequence constraints            │  │
    │  └───────────────────────────────────┘  │
    └─────────────────────────────────────────┘
           ↓
    PolicyDecision (status, rationale, severity)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class PolicyStatus(str, Enum):
    """Policy decision status for an action."""
    ALLOWED = "allowed"       # Action is permitted
    FORBIDDEN = "forbidden"   # Action is contraindicated
    MANDATORY = "mandatory"   # Action is required
    CAUTIONED = "cautioned"   # Action allowed with warnings
    UNKNOWN = "unknown"       # Cannot determine (insufficient context)


class ConstraintType(str, Enum):
    """Type of constraint that triggered a policy decision."""
    ALLERGY = "allergy"                    # Patient allergy
    DRUG_INTERACTION = "drug_interaction"  # Drug-drug interaction
    COMORBIDITY = "comorbidity"            # Comorbidity restriction
    CLINICAL_STATE = "clinical_state"      # Current clinical state
    GUIDELINE = "guideline"                # CPG recommendation
    TIMING = "timing"                      # Time-sensitive requirement
    SEQUENCE = "sequence"                  # Action ordering requirement
    SAFETY = "safety"                      # General safety constraint


class Severity(str, Enum):
    """Severity level of policy constraint."""
    MINOR = "minor"           # Informational
    MODERATE = "moderate"     # Warning level
    MAJOR = "major"           # Significant risk
    SEVERE = "severe"         # Serious harm potential
    CATASTROPHIC = "catastrophic"  # Life-threatening

    @property
    def rank(self) -> int:
        """Numeric rank for severity comparison (higher = more severe)."""
        return {
            "minor": 1,
            "moderate": 2,
            "major": 3,
            "severe": 4,
            "catastrophic": 5,
        }[self.value]

    def __gt__(self, other: "Severity") -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank > other.rank

    def __ge__(self, other: "Severity") -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank >= other.rank

    def __lt__(self, other: "Severity") -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: "Severity") -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank <= other.rank


@dataclass
class PolicyConstraint:
    """A constraint that affects policy decisions.

    Attributes:
        constraint_type: Type of constraint
        concept_pattern: Pattern matching affected concepts
        condition: Condition that triggers constraint
        status: Resulting policy status when constraint applies
        severity: Severity level of the constraint
        rationale: Clinical rationale for the constraint
        source: Source of the constraint (guideline, EHR, etc.)
    """
    constraint_type: ConstraintType
    concept_pattern: str  # Regex pattern for concept_id matching
    condition: str        # Human-readable condition description
    status: PolicyStatus
    severity: Severity
    rationale: str
    source: str = ""

    def matches(self, concept_id: str) -> bool:
        """Check if concept matches this constraint's pattern."""
        if not concept_id:
            return False
        return bool(re.match(self.concept_pattern, concept_id, re.IGNORECASE))


@dataclass
class PolicyDecision:
    """Result of policy evaluation for a concept.

    Attributes:
        concept_id: The concept being evaluated
        status: Policy decision status
        severity: Overall severity (max of triggered constraints)
        triggered_constraints: List of constraints that applied
        rationale: Combined rationale for the decision
        alternatives: Suggested alternative concepts if forbidden
        metadata: Additional context
    """
    concept_id: str
    status: PolicyStatus
    severity: Severity = Severity.MINOR
    triggered_constraints: List[PolicyConstraint] = field(default_factory=list)
    rationale: str = ""
    alternatives: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        """Whether the action is permitted."""
        return self.status in [PolicyStatus.ALLOWED, PolicyStatus.CAUTIONED]

    @property
    def is_forbidden(self) -> bool:
        """Whether the action is contraindicated."""
        return self.status == PolicyStatus.FORBIDDEN

    @property
    def is_mandatory(self) -> bool:
        """Whether the action is required."""
        return self.status == PolicyStatus.MANDATORY

    @property
    def has_warnings(self) -> bool:
        """Whether there are caution/warning constraints."""
        return self.status == PolicyStatus.CAUTIONED or len(self.triggered_constraints) > 0


@dataclass
class PatientContext:
    """Patient-specific context for policy evaluation.

    Attributes:
        allergies: Set of known allergies
        comorbidities: Set of comorbidities/conditions
        current_medications: Set of current medications
        vitals: Current vital signs
        labs: Recent lab values
        clinical_state: Current clinical state identifier
        completed_actions: Actions already performed
        phase: Current treatment phase
    """
    allergies: Set[str] = field(default_factory=set)
    comorbidities: Set[str] = field(default_factory=set)
    current_medications: Set[str] = field(default_factory=set)
    vitals: Dict[str, float] = field(default_factory=dict)
    labs: Dict[str, float] = field(default_factory=dict)
    clinical_state: str = ""
    completed_actions: Set[str] = field(default_factory=set)
    phase: str = ""

    def has_allergy(self, allergy: str) -> bool:
        """Check if patient has specific allergy."""
        allergy_lower = allergy.lower()
        return any(a.lower() == allergy_lower for a in self.allergies)

    def has_comorbidity(self, comorbidity: str) -> bool:
        """Check if patient has specific comorbidity."""
        comorb_lower = comorbidity.lower()
        return any(c.lower() == comorb_lower for c in self.comorbidities)

    def is_on_medication(self, medication: str) -> bool:
        """Check if patient is on specific medication."""
        med_lower = medication.lower()
        return any(m.lower() == med_lower or med_lower in m.lower()
                   for m in self.current_medications)


@dataclass
class PolicyConfig:
    """Configuration for ClinicalPolicy.

    Attributes:
        allergy_mappings: Map allergies to forbidden concepts
        comorbidity_mappings: Map comorbidities to forbidden concepts
        drug_interactions: Drug-drug interaction rules
        clinical_state_rules: State-specific mandatory/forbidden actions
        default_constraints: Default safety constraints
        enable_cross_reactivity: Enable allergy cross-reactivity
        conservative_mode: Err on side of caution for uncertain cases
    """
    allergy_mappings: List[AllergyMapping] = field(default_factory=list)
    comorbidity_mappings: List[ComorbidityMapping] = field(default_factory=list)
    drug_interactions: List[DrugInteraction] = field(default_factory=list)
    clinical_state_rules: List[ClinicalStateRule] = field(default_factory=list)
    default_constraints: List[PolicyConstraint] = field(default_factory=list)
    enable_cross_reactivity: bool = True
    conservative_mode: bool = True


@dataclass
class AllergyMapping:
    """Maps allergy to forbidden medications/concepts."""
    allergy: str
    forbidden_concepts: List[str]  # Concept ID patterns
    cross_reactivity: List[str] = field(default_factory=list)
    severity: Severity = Severity.SEVERE
    source: str = ""


@dataclass
class ComorbidityMapping:
    """Maps comorbidity to contraindicated concepts."""
    comorbidity: str
    forbidden_concepts: List[str] = field(default_factory=list)  # Concept ID patterns
    cautioned_concepts: List[str] = field(default_factory=list)
    severity: Severity = Severity.MAJOR
    source: str = ""


@dataclass
class DrugInteraction:
    """Drug-drug interaction rule."""
    drug_a_pattern: str  # Concept ID pattern for drug A
    drug_b_pattern: str  # Concept ID pattern for drug B
    interaction_type: str  # e.g., "contraindication", "potentiation"
    severity: Severity
    description: str
    source: str = ""


@dataclass
class ClinicalStateRule:
    """Clinical state-specific action rules."""
    state_pattern: str  # Pattern for clinical_state
    mandatory_concepts: List[str] = field(default_factory=list)
    forbidden_concepts: List[str] = field(default_factory=list)
    deadline_minutes: Optional[int] = None
    source: str = ""


class ClinicalPolicy:
    """Clinical Policy / Conformance Evaluation Layer.

    Takes normalized concepts (from Mapper) and evaluates them
    against patient context and clinical guidelines.

    Example:
        context = PatientContext(
            allergies={"penicillin"},
            comorbidities={"rv_infarction"},
            clinical_state="stemi_inferior",
        )

        policy = ClinicalPolicy(config)

        # Evaluate a normalized concept
        decision = policy.evaluate("ANTIBIOTIC_AMOXICILLIN", context)
        # decision.status = PolicyStatus.FORBIDDEN
        # decision.rationale = "Penicillin allergy"

        decision = policy.evaluate("NITRATE_NITROGLYCERIN", context)
        # decision.status = PolicyStatus.FORBIDDEN
        # decision.rationale = "Contraindicated in RV infarction"
    """

    def __init__(self, config: Optional[PolicyConfig] = None):
        self._config = config or PolicyConfig()
        self._constraints: List[PolicyConstraint] = []
        self._build_constraints()

    def _build_constraints(self) -> None:
        """Build constraint list from config."""
        # Add allergy constraints
        for am in self._config.allergy_mappings:
            for pattern in am.forbidden_concepts:
                self._constraints.append(PolicyConstraint(
                    constraint_type=ConstraintType.ALLERGY,
                    concept_pattern=pattern,
                    condition=f"patient_allergy:{am.allergy}",
                    status=PolicyStatus.FORBIDDEN,
                    severity=am.severity,
                    rationale=f"Contraindicated due to {am.allergy} allergy",
                    source=am.source,
                ))
            # Cross-reactivity
            if self._config.enable_cross_reactivity:
                for cross in am.cross_reactivity:
                    self._constraints.append(PolicyConstraint(
                        constraint_type=ConstraintType.ALLERGY,
                        concept_pattern=cross,
                        condition=f"patient_allergy:{am.allergy}",
                        status=PolicyStatus.CAUTIONED,
                        severity=Severity.MAJOR,
                        rationale=f"Potential cross-reactivity with {am.allergy}",
                        source=am.source,
                    ))

        # Add comorbidity constraints
        for cm in self._config.comorbidity_mappings:
            for pattern in cm.forbidden_concepts:
                self._constraints.append(PolicyConstraint(
                    constraint_type=ConstraintType.COMORBIDITY,
                    concept_pattern=pattern,
                    condition=f"patient_comorbidity:{cm.comorbidity}",
                    status=PolicyStatus.FORBIDDEN,
                    severity=cm.severity,
                    rationale=f"Contraindicated with {cm.comorbidity}",
                    source=cm.source,
                ))
            for pattern in cm.cautioned_concepts:
                self._constraints.append(PolicyConstraint(
                    constraint_type=ConstraintType.COMORBIDITY,
                    concept_pattern=pattern,
                    condition=f"patient_comorbidity:{cm.comorbidity}",
                    status=PolicyStatus.CAUTIONED,
                    severity=Severity.MODERATE,
                    rationale=f"Use with caution in {cm.comorbidity}",
                    source=cm.source,
                ))

        # Add default constraints
        self._constraints.extend(self._config.default_constraints)

    def evaluate(
        self,
        concept_id: str,
        context: PatientContext,
    ) -> PolicyDecision:
        """Evaluate a concept against patient context.

        Args:
            concept_id: Normalized concept ID (from Mapper)
            context: Patient context with allergies, comorbidities, etc.

        Returns:
            PolicyDecision with status, rationale, and constraints
        """
        if not concept_id:
            return PolicyDecision(
                concept_id=concept_id or "",
                status=PolicyStatus.UNKNOWN,
                rationale="No concept ID provided",
            )

        triggered = []
        max_severity = Severity.MINOR

        # Check all constraints
        for constraint in self._constraints:
            if not constraint.matches(concept_id):
                continue

            # Check if condition is met
            if self._check_condition(constraint.condition, context):
                triggered.append(constraint)
                if constraint.severity > max_severity:
                    max_severity = constraint.severity

        # Check drug interactions
        interaction_constraints = self._check_drug_interactions(concept_id, context)
        triggered.extend(interaction_constraints)
        for ic in interaction_constraints:
            if ic.severity > max_severity:
                max_severity = ic.severity

        # Check clinical state rules
        state_result = self._check_clinical_state(concept_id, context)
        if state_result:
            triggered.append(state_result)
            if state_result.severity > max_severity:
                max_severity = state_result.severity

        # Determine final status
        if not triggered:
            status = PolicyStatus.ALLOWED
        else:
            # Take the most restrictive status
            statuses = [c.status for c in triggered]
            if PolicyStatus.FORBIDDEN in statuses:
                status = PolicyStatus.FORBIDDEN
            elif PolicyStatus.MANDATORY in statuses:
                status = PolicyStatus.MANDATORY
            elif PolicyStatus.CAUTIONED in statuses:
                status = PolicyStatus.CAUTIONED
            else:
                status = PolicyStatus.ALLOWED

        # Build rationale
        rationale = "; ".join(c.rationale for c in triggered) if triggered else "No constraints triggered"

        # Get alternatives if forbidden
        alternatives = []
        if status == PolicyStatus.FORBIDDEN:
            alternatives = self._get_alternatives(concept_id, context)

        return PolicyDecision(
            concept_id=concept_id,
            status=status,
            severity=max_severity,
            triggered_constraints=triggered,
            rationale=rationale,
            alternatives=alternatives,
        )

    def evaluate_batch(
        self,
        concept_ids: List[str],
        context: PatientContext,
    ) -> List[PolicyDecision]:
        """Evaluate multiple concepts.

        Args:
            concept_ids: List of normalized concept IDs
            context: Patient context

        Returns:
            List of PolicyDecision
        """
        return [self.evaluate(cid, context) for cid in concept_ids]

    def get_mandatory_actions(
        self,
        context: PatientContext,
    ) -> List[Tuple[str, Optional[int]]]:
        """Get mandatory actions for current clinical state.

        Returns:
            List of (concept_id, deadline_minutes) tuples
        """
        mandatory = []

        for rule in self._config.clinical_state_rules:
            if not re.match(rule.state_pattern, context.clinical_state, re.IGNORECASE):
                continue

            for concept_id in rule.mandatory_concepts:
                if concept_id not in context.completed_actions:
                    mandatory.append((concept_id, rule.deadline_minutes))

        return mandatory

    def get_forbidden_actions(
        self,
        context: PatientContext,
    ) -> List[str]:
        """Get all forbidden actions for current context.

        Returns:
            List of forbidden concept IDs/patterns
        """
        forbidden = set()

        # From allergy mappings
        for am in self._config.allergy_mappings:
            if context.has_allergy(am.allergy):
                forbidden.update(am.forbidden_concepts)

        # From comorbidity mappings
        for cm in self._config.comorbidity_mappings:
            if context.has_comorbidity(cm.comorbidity):
                forbidden.update(cm.forbidden_concepts)

        # From clinical state rules
        for rule in self._config.clinical_state_rules:
            if re.match(rule.state_pattern, context.clinical_state, re.IGNORECASE):
                forbidden.update(rule.forbidden_concepts)

        return list(forbidden)

    def _check_condition(
        self,
        condition: str,
        context: PatientContext,
    ) -> bool:
        """Check if a condition is met by the patient context."""
        if not condition:
            return True

        # Parse condition format: "type:value"
        if ":" not in condition:
            return False

        cond_type, cond_value = condition.split(":", 1)

        if cond_type == "patient_allergy":
            return context.has_allergy(cond_value)

        elif cond_type == "patient_comorbidity":
            return context.has_comorbidity(cond_value)

        elif cond_type == "on_medication":
            return context.is_on_medication(cond_value)

        elif cond_type == "clinical_state":
            return bool(re.match(cond_value, context.clinical_state, re.IGNORECASE))

        elif cond_type == "vital_gt":
            vital, threshold = cond_value.split(",")
            return context.vitals.get(vital, 0) > float(threshold)

        elif cond_type == "vital_lt":
            vital, threshold = cond_value.split(",")
            return context.vitals.get(vital, float('inf')) < float(threshold)

        elif cond_type == "lab_gt":
            lab, threshold = cond_value.split(",")
            return context.labs.get(lab, 0) > float(threshold)

        elif cond_type == "lab_lt":
            lab, threshold = cond_value.split(",")
            return context.labs.get(lab, float('inf')) < float(threshold)

        return False

    def _check_drug_interactions(
        self,
        concept_id: str,
        context: PatientContext,
    ) -> List[PolicyConstraint]:
        """Check for drug-drug interactions."""
        interactions = []

        for di in self._config.drug_interactions:
            # Check if concept matches drug A
            if re.match(di.drug_a_pattern, concept_id, re.IGNORECASE):
                # Check if patient is on drug B
                for med in context.current_medications:
                    if re.match(di.drug_b_pattern, med, re.IGNORECASE):
                        interactions.append(PolicyConstraint(
                            constraint_type=ConstraintType.DRUG_INTERACTION,
                            concept_pattern=di.drug_a_pattern,
                            condition=f"on_medication:{med}",
                            status=PolicyStatus.FORBIDDEN if di.interaction_type == "contraindication" else PolicyStatus.CAUTIONED,
                            severity=di.severity,
                            rationale=f"Interaction with {med}: {di.description}",
                            source=di.source,
                        ))

            # Check reverse: concept matches drug B
            elif re.match(di.drug_b_pattern, concept_id, re.IGNORECASE):
                for med in context.current_medications:
                    if re.match(di.drug_a_pattern, med, re.IGNORECASE):
                        interactions.append(PolicyConstraint(
                            constraint_type=ConstraintType.DRUG_INTERACTION,
                            concept_pattern=di.drug_b_pattern,
                            condition=f"on_medication:{med}",
                            status=PolicyStatus.FORBIDDEN if di.interaction_type == "contraindication" else PolicyStatus.CAUTIONED,
                            severity=di.severity,
                            rationale=f"Interaction with {med}: {di.description}",
                            source=di.source,
                        ))

        return interactions

    def _check_clinical_state(
        self,
        concept_id: str,
        context: PatientContext,
    ) -> Optional[PolicyConstraint]:
        """Check clinical state-specific rules."""
        for rule in self._config.clinical_state_rules:
            if not re.match(rule.state_pattern, context.clinical_state, re.IGNORECASE):
                continue

            # Check if forbidden in this state
            for pattern in rule.forbidden_concepts:
                if re.match(pattern, concept_id, re.IGNORECASE):
                    return PolicyConstraint(
                        constraint_type=ConstraintType.CLINICAL_STATE,
                        concept_pattern=pattern,
                        condition=f"clinical_state:{context.clinical_state}",
                        status=PolicyStatus.FORBIDDEN,
                        severity=Severity.SEVERE,
                        rationale=f"Contraindicated in {context.clinical_state}",
                        source=rule.source,
                    )

            # Check if mandatory in this state
            for pattern in rule.mandatory_concepts:
                if re.match(pattern, concept_id, re.IGNORECASE):
                    if concept_id not in context.completed_actions:
                        return PolicyConstraint(
                            constraint_type=ConstraintType.GUIDELINE,
                            concept_pattern=pattern,
                            condition=f"clinical_state:{context.clinical_state}",
                            status=PolicyStatus.MANDATORY,
                            severity=Severity.MAJOR,
                            rationale=f"Required action for {context.clinical_state}",
                            source=rule.source,
                        )

        return None

    def _get_alternatives(
        self,
        forbidden_concept: str,
        context: PatientContext,
    ) -> List[str]:
        """Get alternative concepts when one is forbidden.

        This is a simple implementation. In practice, would use
        ontology relationships to find therapeutic alternatives.
        """
        # Basic alternative suggestions based on concept type
        alternatives = []

        # Example: If penicillin allergic, suggest alternatives
        if "penicillin" in forbidden_concept.lower() or "amoxicillin" in forbidden_concept.lower():
            alternatives = [
                "ANTIBIOTIC_AZITHROMYCIN",
                "ANTIBIOTIC_FLUOROQUINOLONE",
                "ANTIBIOTIC_CEPHALOSPORIN",  # Note: may have cross-reactivity
            ]

        # Example: If nitrates forbidden (RV infarct), suggest alternatives
        if "nitrate" in forbidden_concept.lower() or "nitroglycerin" in forbidden_concept.lower():
            alternatives = [
                "ANALGESIC_MORPHINE",  # For chest pain
            ]

        # Filter out any that are also forbidden
        forbidden_set = set(self.get_forbidden_actions(context))
        return [a for a in alternatives if a not in forbidden_set]


# ============================================================
# Factory and Utilities
# ============================================================

def create_default_policy() -> ClinicalPolicy:
    """Create a policy with sensible clinical defaults.

    Includes common allergy mappings and safety rules.
    """
    config = PolicyConfig(
        allergy_mappings=[
            AllergyMapping(
                allergy="penicillin",
                forbidden_concepts=[
                    r".*PENICILLIN.*",
                    r".*AMOXICILLIN.*",
                    r".*AMPICILLIN.*",
                ],
                cross_reactivity=[
                    r".*CEPHALOSPORIN.*",  # ~1-2% cross-reactivity
                ],
                severity=Severity.SEVERE,
                source="Drug Allergy Guidelines",
            ),
            AllergyMapping(
                allergy="sulfa",
                forbidden_concepts=[
                    r".*SULFAMETHOXAZOLE.*",
                    r".*BACTRIM.*",
                    r".*SULFASALAZINE.*",
                ],
                severity=Severity.SEVERE,
                source="Drug Allergy Guidelines",
            ),
        ],
        comorbidity_mappings=[
            ComorbidityMapping(
                comorbidity="rv_infarction",
                forbidden_concepts=[
                    r".*NITRATE.*",
                    r".*NITROGLYCERIN.*",
                    r".*ISOSORBIDE.*",
                ],
                severity=Severity.CATASTROPHIC,
                source="AHA STEMI Guidelines 2013",
            ),
            ComorbidityMapping(
                comorbidity="renal_failure",
                cautioned_concepts=[
                    r".*NSAID.*",
                    r".*IBUPROFEN.*",
                    r".*KETOROLAC.*",
                ],
                forbidden_concepts=[
                    r".*CONTRAST.*",  # Without pre-hydration
                ],
                severity=Severity.MAJOR,
                source="KDIGO AKI Guidelines",
            ),
            ComorbidityMapping(
                comorbidity="asthma",
                forbidden_concepts=[
                    r".*BETA.*BLOCKER.*",  # Non-selective
                ],
                cautioned_concepts=[
                    r".*ASPIRIN.*",
                ],
                severity=Severity.MAJOR,
                source="Asthma Guidelines",
            ),
        ],
        drug_interactions=[
            DrugInteraction(
                drug_a_pattern=r".*WARFARIN.*",
                drug_b_pattern=r".*ASPIRIN.*",
                interaction_type="potentiation",
                severity=Severity.MAJOR,
                description="Increased bleeding risk",
                source="Drug Interaction Database",
            ),
        ],
        conservative_mode=True,
    )

    return ClinicalPolicy(config)


def create_rv_trap_policy() -> ClinicalPolicy:
    """Create policy specifically for RV infarct trap scenario.

    The RV trap: Giving nitrates to a patient with RV infarction
    causes severe hypotension because nitrates reduce preload,
    which the RV-dependent patient cannot tolerate.
    """
    config = PolicyConfig(
        comorbidity_mappings=[
            ComorbidityMapping(
                comorbidity="rv_infarction",
                forbidden_concepts=[
                    r".*NITRATE.*",
                    r".*NITROGLYCERIN.*",
                    r".*NTG.*",
                    r".*ISOSORBIDE.*",
                    r".*IMDUR.*",
                ],
                severity=Severity.CATASTROPHIC,
                source="AHA STEMI Guidelines 2013 - RV Infarction",
            ),
            ComorbidityMapping(
                comorbidity="rv_infarction",
                cautioned_concepts=[
                    r".*DIURETIC.*",
                    r".*FUROSEMIDE.*",
                    r".*LASIX.*",
                ],
                severity=Severity.MAJOR,
                source="AHA STEMI Guidelines 2013 - RV Infarction",
            ),
        ],
        clinical_state_rules=[
            ClinicalStateRule(
                state_pattern=r"stemi.*rv.*|rv.*infarct.*",
                mandatory_concepts=[
                    "ECG_V4R",  # Right-sided ECG
                    "FLUID_BOLUS",  # Volume expansion
                ],
                forbidden_concepts=[
                    r".*NITRATE.*",
                    r".*NITROGLYCERIN.*",
                ],
                deadline_minutes=30,
                source="AHA STEMI Guidelines 2013",
            ),
        ],
        conservative_mode=True,
    )

    return ClinicalPolicy(config)
