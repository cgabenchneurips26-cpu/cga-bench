"""Anchor-based action normalizer for extensible action mapping.

Replaces hardcoded DIRECT_MAPPINGS with dynamic anchor-based matching.

Problem solved:
- DIRECT_MAPPINGS has 1400+ hardcoded entries
- Duplicate keys cause silent overwrites
- No domain-aware normalization
- Adding new actions requires code changes

Solution:
- Use Gold Set v2 synonyms as learned mappings
- Use Standard Anchors for external code resolution
- Domain-partitioned normalization
- Extensible via JSONL files (no code changes)

Version: 1.0 (2026-01-25)
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict


@dataclass
class NormalizationResult:
    """Result of action normalization."""
    original: str
    normalized: Optional[str]
    confidence: float  # 0.0 - 1.0
    strategy: str  # "exact", "synonym", "anchor", "fuzzy", "pattern"
    domain: Optional[str] = None
    alternatives: List[Tuple[str, float]] = field(default_factory=list)


class AnchorBasedNormalizer:
    """Domain-aware action normalizer using anchors and learned synonyms.

    Normalization cascade:
    1. Exact match in domain-specific synonyms
    2. Exact match in universal synonyms
    3. Anchor-based resolution (external code lookup)
    4. Pattern-based normalization (regex rules)
    5. Fuzzy matching (Jaccard similarity)
    """

    def __init__(
        self,
        gold_set_path: Optional[Path] = None,
        anchors_path: Optional[Path] = None,
        fuzzy_threshold: float = 0.7,
    ):
        """Initialize normalizer.

        Args:
            gold_set_path: Path to gold_set_v2.jsonl (learns synonyms)
            anchors_path: Path to standard_anchors.jsonl (external codes)
            fuzzy_threshold: Minimum Jaccard similarity for fuzzy match
        """
        self._fuzzy_threshold = fuzzy_threshold

        # Domain-partitioned synonym maps: domain -> {synonym: concept_id}
        self._domain_synonyms: Dict[str, Dict[str, str]] = defaultdict(dict)

        # Universal synonyms (no domain constraint)
        self._universal_synonyms: Dict[str, str] = {}

        # Anchor-based reverse index: external_code -> concept_id
        self._anchor_index: Dict[str, str] = {}

        # All known concept IDs (for fuzzy matching)
        self._all_concepts: Set[str] = set()

        # Pattern rules: (regex, replacement_template)
        self._pattern_rules: List[Tuple[re.Pattern, str]] = []

        # Load data
        self._load_gold_set(gold_set_path)
        self._load_anchors(anchors_path)
        self._init_pattern_rules()

    def _load_gold_set(self, path: Optional[Path]):
        """Load synonyms from gold set."""
        if path is None:
            # Try default path
            default_path = Path(__file__).parent.parent.parent / "data_release" / "v1.0" / "gold_set" / "gold_set_v2.jsonl"
            if default_path.exists():
                path = default_path
            else:
                return

        with open(path) as f:
            for line in f:
                inst = json.loads(line)
                query = inst["query"].lower().strip()
                concept_id = inst.get("gold_concept_id")
                domain = inst.get("domain", "universal")

                if concept_id:
                    # Add to domain-specific synonyms
                    self._domain_synonyms[domain][query] = concept_id

                    # Add to universal if not domain-specific
                    if domain == "universal":
                        self._universal_synonyms[query] = concept_id

                    self._all_concepts.add(concept_id)

    def _load_anchors(self, path: Optional[Path]):
        """Load external code anchors."""
        if path is None:
            default_path = Path(__file__).parent.parent.parent / "data_release" / "v1.0" / "anchors" / "standard_anchors.jsonl"
            if default_path.exists():
                path = default_path
            else:
                return

        with open(path) as f:
            for line in f:
                anchor = json.loads(line)
                concept_id = anchor["concept_id"]
                self._all_concepts.add(concept_id)

                # Index by external codes
                for code_type in ["umls_cui", "rxcui", "loinc", "snomed_ct", "icd10"]:
                    code = anchor.get(code_type)
                    if code and code != "None":
                        self._anchor_index[code.lower()] = concept_id
                        self._anchor_index[code.upper()] = concept_id

    def _init_pattern_rules(self):
        """Initialize pattern-based normalization rules."""
        self._pattern_rules = [
            # === SPECIFIC CLINICAL PATTERNS (higher priority) ===

            # Aspirin with dose → GIVE_ASPIRIN_LOADING
            (re.compile(r"^aspirin[_\s]*(\d+)?.*$", re.I), lambda m: "GIVE_ASPIRIN_LOADING"),

            # CT/imaging patterns → ORDER_CT_*
            (re.compile(r"^ct[_\s]+(head|brain|stroke).*$", re.I), lambda m: "ORDER_CT_HEAD"),
            (re.compile(r"^ct[_\s]+(chest|thorax|pe).*$", re.I), lambda m: "ORDER_CT_CHEST"),
            (re.compile(r"^ct[_\s]+(abdomen|abd).*$", re.I), lambda m: "ORDER_CT_ABDOMEN"),
            (re.compile(r"^(head|brain)[_\s]*ct.*$", re.I), lambda m: "ORDER_CT_HEAD"),

            # Insulin patterns → START_INSULIN_INFUSION
            (re.compile(r"^insulin[_\s]*(drip|infusion|gtt|iv).*$", re.I), lambda m: "START_INSULIN_INFUSION"),
            (re.compile(r"^(start|begin)[_\s]*insulin.*$", re.I), lambda m: "START_INSULIN_INFUSION"),
            (re.compile(r"^(regular|iv)[_\s]*insulin.*$", re.I), lambda m: "START_INSULIN_INFUSION"),

            # Fluid patterns
            (re.compile(r"^(crystalloid|ns|lr|saline)[_\s]*(bolus|fluid)?.*$", re.I),
             lambda m: "GIVE_CRYSTALLOID"),
            (re.compile(r"^(fluid|iv)[_\s]*(bolus|resuscitation).*$", re.I),
             lambda m: "GIVE_CRYSTALLOID"),

            # Vasopressor patterns
            (re.compile(r"^(norepinephrine|levophed|norepi|ne)[_\s]*(drip|infusion)?.*$", re.I),
             lambda m: "START_VASOPRESSOR_NOREPINEPHRINE"),
            (re.compile(r"^(vasopressin|pitressin).*$", re.I),
             lambda m: "START_VASOPRESSOR_VASOPRESSIN"),
            (re.compile(r"^(epinephrine|epi)[_\s]*(drip|infusion)?.*$", re.I),
             lambda m: "START_VASOPRESSOR_EPINEPHRINE"),
            (re.compile(r"^(dopamine|dopa).*$", re.I),
             lambda m: "START_VASOPRESSOR_DOPAMINE"),
            (re.compile(r"^(phenylephrine|neosynephrine).*$", re.I),
             lambda m: "START_VASOPRESSOR_PHENYLEPHRINE"),

            # tPA/alteplase patterns
            (re.compile(r"^(tpa|alteplase|activase|thrombolytic).*$", re.I),
             lambda m: "GIVE_ALTEPLASE"),

            # Antibiotic patterns
            (re.compile(r"^(zosyn|pip.?tazo?).*$", re.I),
             lambda m: "GIVE_PIPERACILLIN_TAZOBACTAM"),
            (re.compile(r"^(vanco|vancomycin).*$", re.I),
             lambda m: "GIVE_VANCOMYCIN"),
            (re.compile(r"^(ceftriaxone|rocephin).*$", re.I),
             lambda m: "GIVE_CEFTRIAXONE"),
            (re.compile(r"^broad[_\s]*spectrum[_\s]*(antibiotic)?s?.*$", re.I),
             lambda m: "GIVE_BROAD_SPECTRUM_ANTIBIOTICS"),

            # Cardiac medications
            (re.compile(r"^(heparin|ufh)[_\s]*(bolus|drip|infusion)?.*$", re.I),
             lambda m: "GIVE_HEPARIN"),
            (re.compile(r"^(nitroglycerin|ntg|nitro)[_\s]*(drip|sl|sublingual)?.*$", re.I),
             lambda m: "GIVE_NITROGLYCERIN"),
            (re.compile(r"^(metoprolol|lopressor).*$", re.I),
             lambda m: "GIVE_METOPROLOL"),
            (re.compile(r"^(atorvastatin|lipitor|statin).*$", re.I),
             lambda m: "GIVE_ATORVASTATIN"),
            (re.compile(r"^(clopidogrel|plavix).*$", re.I),
             lambda m: "GIVE_CLOPIDOGREL"),
            (re.compile(r"^(ticagrelor|brilinta).*$", re.I),
             lambda m: "GIVE_TICAGRELOR"),

            # Diuretics
            (re.compile(r"^(furosemide|lasix).*$", re.I),
             lambda m: "GIVE_FUROSEMIDE"),
            (re.compile(r"^(bumetanide|bumex).*$", re.I),
             lambda m: "GIVE_BUMETANIDE"),

            # Lab order patterns
            (re.compile(r"^(blood[_\s]*culture|bcx|bc)s?.*$", re.I),
             lambda m: "ORDER_BLOOD_CULTURE"),
            (re.compile(r"^(lactate|lactic[_\s]*acid).*$", re.I),
             lambda m: "ORDER_LACTATE"),
            (re.compile(r"^(troponin|trop)[_\s]*(i|t)?.*$", re.I),
             lambda m: "ORDER_TROPONIN"),
            (re.compile(r"^(bnp|pro.?bnp|nt.?pro.?bnp).*$", re.I),
             lambda m: "ORDER_BNP"),
            (re.compile(r"^(creatinine|cr|scr)$", re.I),
             lambda m: "ORDER_CREATININE"),
            (re.compile(r"^(bmp|chem7|chem.?7|basic[_\s]*metabolic).*$", re.I),
             lambda m: "ORDER_BMP"),
            (re.compile(r"^(cmp|chem14|comprehensive[_\s]*metabolic).*$", re.I),
             lambda m: "ORDER_CMP"),
            (re.compile(r"^(cbc|complete[_\s]*blood[_\s]*count).*$", re.I),
             lambda m: "ORDER_CBC"),
            (re.compile(r"^(abg|arterial[_\s]*blood[_\s]*gas).*$", re.I),
             lambda m: "ORDER_ABG"),
            (re.compile(r"^(vbg|venous[_\s]*blood[_\s]*gas).*$", re.I),
             lambda m: "ORDER_VBG"),
            (re.compile(r"^(pt.?inr|inr|coags|coagulation).*$", re.I),
             lambda m: "ORDER_COAGULATION_PANEL"),
            (re.compile(r"^(hba1c|a1c|hemoglobin[_\s]*a1c).*$", re.I),
             lambda m: "ORDER_HBA1C"),
            (re.compile(r"^(potassium|k\+?)$", re.I),
             lambda m: "ORDER_POTASSIUM"),
            (re.compile(r"^(glucose|blood[_\s]*sugar|fingerstick).*$", re.I),
             lambda m: "ORDER_GLUCOSE"),
            (re.compile(r"^(urinalysis|ua|urine[_\s]*analysis).*$", re.I),
             lambda m: "ORDER_URINALYSIS"),

            # ECG patterns
            (re.compile(r"^(ecg|ekg|electrocardiogram|12[_\s]*lead).*$", re.I),
             lambda m: "ORDER_ECG"),
            (re.compile(r"^(right.?sided|v4r|rv)[_\s]*(ecg|ekg|leads)?.*$", re.I),
             lambda m: "ORDER_RIGHT_SIDED_ECG"),

            # Imaging patterns
            (re.compile(r"^(cxr|chest[_\s]*x.?ray|chest[_\s]*radiograph).*$", re.I),
             lambda m: "ORDER_CHEST_XRAY"),
            (re.compile(r"^(echo|echocardiogram|tte|transthoracic).*$", re.I),
             lambda m: "ORDER_ECHOCARDIOGRAM"),
            (re.compile(r"^(mri|mr)[_\s]*(brain|head|stroke)?.*$", re.I),
             lambda m: "ORDER_MRI_BRAIN"),
            (re.compile(r"^(cta|ct[_\s]*angio|angiogram)[_\s]*(head|neck)?.*$", re.I),
             lambda m: "ORDER_CTA_HEAD_NECK"),

            # Assessment patterns
            (re.compile(r"^(nihss|nih[_\s]*stroke[_\s]*scale).*$", re.I),
             lambda m: "ASSESS_NIHSS"),
            (re.compile(r"^(gcs|glasgow[_\s]*coma[_\s]*scale).*$", re.I),
             lambda m: "ASSESS_GCS"),
            (re.compile(r"^(vital[_\s]*signs?|vitals|vs).*$", re.I),
             lambda m: "ASSESS_VITAL_SIGNS"),

            # Procedure patterns
            (re.compile(r"^(intubat|rsi|rapid[_\s]*sequence).*$", re.I),
             lambda m: "PERFORM_INTUBATION"),
            (re.compile(r"^(central[_\s]*line|cvc|central[_\s]*venous).*$", re.I),
             lambda m: "PLACE_CENTRAL_LINE"),
            (re.compile(r"^(arterial[_\s]*line|a.?line|art[_\s]*line).*$", re.I),
             lambda m: "PLACE_ARTERIAL_LINE"),
            (re.compile(r"^(foley|urinary[_\s]*catheter|bladder[_\s]*catheter).*$", re.I),
             lambda m: "PLACE_FOLEY_CATHETER"),

            # Consult patterns
            (re.compile(r"^consult[_\s]*(cardiology|cards?).*$", re.I),
             lambda m: "CONSULT_CARDIOLOGY"),
            (re.compile(r"^consult[_\s]*(neurology|neuro).*$", re.I),
             lambda m: "CONSULT_NEUROLOGY"),
            (re.compile(r"^consult[_\s]*(nephrology|renal).*$", re.I),
             lambda m: "CONSULT_NEPHROLOGY"),
            (re.compile(r"^consult[_\s]*(icu|critical[_\s]*care|intensivist).*$", re.I),
             lambda m: "CONSULT_ICU"),

            # Activation patterns
            (re.compile(r"^(cath[_\s]*lab|cardiac[_\s]*cath|pci).*$", re.I),
             lambda m: "ACTIVATE_CATH_LAB"),
            (re.compile(r"^(stroke[_\s]*team|code[_\s]*stroke|stroke[_\s]*alert).*$", re.I),
             lambda m: "ACTIVATE_STROKE_TEAM"),

            # === GENERIC PATTERNS (lower priority) ===

            # order_X → ORDER_X (normalize case)
            (re.compile(r"^order[_\s]+(.+)$", re.I), lambda m: f"ORDER_{m.group(1).upper().replace(' ', '_')}"),

            # give_X → GIVE_X
            (re.compile(r"^give[_\s]+(.+)$", re.I), lambda m: f"GIVE_{m.group(1).upper().replace(' ', '_')}"),

            # start_X → START_X
            (re.compile(r"^start[_\s]+(.+)$", re.I), lambda m: f"START_{m.group(1).upper().replace(' ', '_')}"),

            # assess_X → ASSESS_X
            (re.compile(r"^assess[_\s]+(.+)$", re.I), lambda m: f"ASSESS_{m.group(1).upper().replace(' ', '_')}"),

            # perform_X → PERFORM_X
            (re.compile(r"^perform[_\s]+(.+)$", re.I), lambda m: f"PERFORM_{m.group(1).upper().replace(' ', '_')}"),

            # initiate_X → INITIATE_X
            (re.compile(r"^initiate[_\s]+(.+)$", re.I), lambda m: f"INITIATE_{m.group(1).upper().replace(' ', '_')}"),

            # consult_X → CONSULT_X
            (re.compile(r"^consult[_\s]+(.+)$", re.I), lambda m: f"CONSULT_{m.group(1).upper().replace(' ', '_')}"),

            # place_X → PLACE_X
            (re.compile(r"^place[_\s]+(.+)$", re.I), lambda m: f"PLACE_{m.group(1).upper().replace(' ', '_')}"),

            # activate_X → ACTIVATE_X
            (re.compile(r"^activate[_\s]+(.+)$", re.I), lambda m: f"ACTIVATE_{m.group(1).upper().replace(' ', '_')}"),

            # control_X → CONTROL_X
            (re.compile(r"^control[_\s]+(.+)$", re.I), lambda m: f"CONTROL_{m.group(1).upper().replace(' ', '_')}"),
        ]

    def _jaccard_similarity(self, a: str, b: str) -> float:
        """Compute Jaccard similarity between two strings."""
        set_a = set(a.lower().replace("_", " ").split())
        set_b = set(b.lower().replace("_", " ").split())
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def normalize(
        self,
        action: str,
        domain: Optional[str] = None,
    ) -> NormalizationResult:
        """Normalize an action string to a concept ID.

        Args:
            action: Raw action string (e.g., "levophed", "order lactate")
            domain: Optional domain hint for disambiguation

        Returns:
            NormalizationResult with normalized concept ID and metadata
        """
        original = action
        query = action.lower().strip().replace("-", "_").replace(" ", "_")

        # 1. Exact match in domain-specific synonyms
        if domain and domain in self._domain_synonyms:
            if query in self._domain_synonyms[domain]:
                return NormalizationResult(
                    original=original,
                    normalized=self._domain_synonyms[domain][query],
                    confidence=1.0,
                    strategy="domain_synonym",
                    domain=domain,
                )

        # 2. Exact match in universal synonyms
        if query in self._universal_synonyms:
            return NormalizationResult(
                original=original,
                normalized=self._universal_synonyms[query],
                confidence=1.0,
                strategy="universal_synonym",
            )

        # 3. Check all domain synonyms (without domain hint)
        for dom, synonyms in self._domain_synonyms.items():
            if query in synonyms:
                return NormalizationResult(
                    original=original,
                    normalized=synonyms[query],
                    confidence=0.95,
                    strategy="cross_domain_synonym",
                    domain=dom,
                )

        # 4. Anchor-based resolution (external code lookup)
        if query in self._anchor_index:
            return NormalizationResult(
                original=original,
                normalized=self._anchor_index[query],
                confidence=0.9,
                strategy="anchor",
            )

        # 5. Pattern-based normalization
        for pattern, replacement in self._pattern_rules:
            match = pattern.match(action)
            if match:
                if callable(replacement):
                    normalized = replacement(match)
                else:
                    normalized = pattern.sub(replacement, action)

                normalized_upper = normalized.upper()

                # Known concept → high confidence
                if normalized_upper in self._all_concepts:
                    return NormalizationResult(
                        original=original,
                        normalized=normalized_upper,
                        confidence=0.85,
                        strategy="pattern",
                    )
                # Pattern-generated canonical form → accept with moderate confidence
                # Patterns produce valid canonical IDs by design
                return NormalizationResult(
                    original=original,
                    normalized=normalized_upper,
                    confidence=0.75,
                    strategy="pattern_inferred",
                )

        # 6. Fuzzy matching against all concepts
        best_match = None
        best_score = self._fuzzy_threshold
        alternatives = []

        for concept in self._all_concepts:
            score = self._jaccard_similarity(query, concept)
            if score > best_score:
                if best_match:
                    alternatives.append((best_match, best_score))
                best_match = concept
                best_score = score
            elif score >= self._fuzzy_threshold:
                alternatives.append((concept, score))

        if best_match:
            return NormalizationResult(
                original=original,
                normalized=best_match,
                confidence=best_score,
                strategy="fuzzy",
                alternatives=sorted(alternatives, key=lambda x: -x[1])[:3],
            )

        # 7. No match found - try uppercase normalization as last resort
        upper_query = query.upper()
        if upper_query in self._all_concepts:
            return NormalizationResult(
                original=original,
                normalized=upper_query,
                confidence=0.7,
                strategy="uppercase",
            )

        # No match
        return NormalizationResult(
            original=original,
            normalized=None,
            confidence=0.0,
            strategy="none",
        )

    def add_synonym(self, synonym: str, concept_id: str, domain: str = "universal"):
        """Add a new synonym mapping dynamically.

        Args:
            synonym: The synonym string
            concept_id: The target concept ID
            domain: Domain for the mapping
        """
        query = synonym.lower().strip().replace("-", "_").replace(" ", "_")
        self._domain_synonyms[domain][query] = concept_id
        self._all_concepts.add(concept_id)

        if domain == "universal":
            self._universal_synonyms[query] = concept_id

    def get_stats(self) -> Dict:
        """Get normalizer statistics."""
        total_synonyms = sum(len(s) for s in self._domain_synonyms.values())
        return {
            "total_synonyms": total_synonyms,
            "domains": list(self._domain_synonyms.keys()),
            "synonyms_by_domain": {d: len(s) for d, s in self._domain_synonyms.items()},
            "anchor_index_size": len(self._anchor_index),
            "known_concepts": len(self._all_concepts),
            "pattern_rules": len(self._pattern_rules),
        }


# Singleton instance for convenience
_default_normalizer: Optional[AnchorBasedNormalizer] = None


def get_normalizer() -> AnchorBasedNormalizer:
    """Get or create the default anchor-based normalizer."""
    global _default_normalizer
    if _default_normalizer is None:
        _default_normalizer = AnchorBasedNormalizer()
    return _default_normalizer


def normalize_action(action: str, domain: Optional[str] = None) -> NormalizationResult:
    """Convenience function for action normalization.

    Args:
        action: Raw action string
        domain: Optional domain hint

    Returns:
        NormalizationResult
    """
    return get_normalizer().normalize(action, domain)


if __name__ == "__main__":
    # Test the normalizer
    normalizer = AnchorBasedNormalizer()
    stats = normalizer.get_stats()

    print("=" * 60)
    print("ANCHOR-BASED NORMALIZER STATISTICS")
    print("=" * 60)
    print(f"Total Synonyms: {stats['total_synonyms']}")
    print(f"Known Concepts: {stats['known_concepts']}")
    print(f"Anchor Index Size: {stats['anchor_index_size']}")
    print(f"Pattern Rules: {stats['pattern_rules']}")
    print("-" * 60)
    print("Synonyms by Domain:")
    for domain, count in sorted(stats['synonyms_by_domain'].items()):
        print(f"  {domain:<20}: {count}")
    print("=" * 60)

    # Test cases
    test_cases = [
        ("levophed", "sepsis"),
        ("order lactate", "sepsis"),
        ("zosyn", "sepsis"),
        ("aspirin 325", "chest_pain"),
        ("EKG", "chest_pain"),
        ("lasix", "heart_failure"),
        ("CT head", "stroke"),
        ("tPA", "stroke"),
        ("creatinine", "aki"),
        ("insulin drip", "dka"),
    ]

    print("\nNORMALIZATION TESTS:")
    print("-" * 60)
    for action, domain in test_cases:
        result = normalizer.normalize(action, domain)
        status = "✓" if result.normalized else "✗"
        print(f"{status} '{action}' ({domain}) → {result.normalized} "
              f"[{result.strategy}, {result.confidence:.2f}]")
