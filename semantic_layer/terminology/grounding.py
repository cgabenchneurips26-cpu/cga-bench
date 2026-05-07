"""
Terminology Grounder - integrates LOINC, UCUM, SNOMED CT, and RxNorm
for full medical code grounding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import logging

import yaml

from .coding import (
    CodedConcept,
    ConceptPivot,
    GroundedLabResult,
    MedicationCoding,
    QuantityWithUnit,
)
from .ucum_normalizer import normalize_ucum

logger = logging.getLogger(__name__)

_MAPPINGS_DIR = Path(__file__).parent.parent.parent / "env" / "adapters" / "mappings"


@dataclass
class GroundingConfig:
    """Configuration for terminology grounding.

    All fields are optional for backward compatibility.
    """
    enable_loinc: bool = True
    enable_snomed: bool = True
    enable_rxnorm: bool = True
    enable_ucum: bool = True
    loinc_mapping_path: Optional[str] = None
    snomed_mapping_path: Optional[str] = None
    rxnorm_mapping_path: Optional[str] = None
    # Neural fallback (opt-in)
    enable_neural_fallback: bool = False
    neural_config: Optional[Any] = None  # NeuralGroundingConfig (lazy import)


@dataclass
class GroundingResult:
    """Result of grounding a clinical concept."""
    concept: Optional[CodedConcept] = None
    quantity: Optional[QuantityWithUnit] = None
    medication: Optional[MedicationCoding] = None
    grounded: bool = False
    warnings: List[str] = field(default_factory=list)


class TerminologyGrounder:
    """Integrates LOINC, UCUM, SNOMED CT, and RxNorm for terminology grounding.

    Provides methods to ground lab results, diagnoses, and medications
    to standard terminology codes.
    """

    def __init__(self, config: Optional[GroundingConfig] = None):
        self._config = config or GroundingConfig()
        self._loinc_reverse: Optional[Dict[str, str]] = None  # internal_code -> loinc_code
        self._loinc_forward: Optional[Dict[str, str]] = None  # loinc_code -> internal_code
        self._snomed_reverse: Optional[Dict[str, str]] = None  # internal_code -> snomed_code
        self._rxnorm: Optional[Dict[str, Dict[str, str]]] = None  # name -> {code, display}
        self._unknown_labs: Set[str] = set()
        self._unknown_meds: Set[str] = set()
        self._neural_backend: Optional[Any] = None
        self._neural_backend_checked: bool = False
        self._last_neural_match: Optional[Any] = None  # Track last neural match

    def ground_lab_result(
        self,
        internal_code: str,
        value: Optional[float] = None,
        unit: Optional[str] = None,
    ) -> GroundedLabResult:
        """Ground a lab result to LOINC code and UCUM unit.

        Args:
            internal_code: CGA-Bench internal code (e.g., "lactate", "potassium")
            value: Numeric result value
            unit: Raw unit string

        Returns:
            GroundedLabResult with LOINC coding and UCUM-normalized quantity
        """
        self._last_neural_match = None
        result = GroundedLabResult(internal_code=internal_code)

        # LOINC grounding
        if self._config.enable_loinc:
            loinc_code = self._get_loinc_for_internal(internal_code)
            if loinc_code:
                display = internal_code.replace("_", " ").title()
                # Use neural match display if available
                if self._last_neural_match and self._last_neural_match.code == loinc_code:
                    display = self._last_neural_match.display
                    result.neural_match_used = True
                    result.neural_confidence = self._last_neural_match.confidence
                result.concept = CodedConcept(
                    system="http://loinc.org",
                    code=loinc_code,
                    display=display,
                )

        # UCUM grounding
        if self._config.enable_ucum and value is not None and unit:
            ucum_unit = normalize_ucum(unit)
            result.quantity = QuantityWithUnit(
                value=value,
                unit_raw=unit,
                unit_ucum=ucum_unit,
            )

        return result

    def ground_diagnosis(
        self,
        internal_code: str,
    ) -> Optional[CodedConcept]:
        """Ground a diagnosis to SNOMED CT code.

        Args:
            internal_code: CGA-Bench internal diagnosis code (e.g., "sepsis", "aki")

        Returns:
            CodedConcept with SNOMED CT coding, or None if not found
        """
        if not self._config.enable_snomed:
            return None

        snomed_code = self._get_snomed_for_internal(internal_code)
        if snomed_code:
            return CodedConcept(
                system="http://snomed.info/sct",
                code=snomed_code,
                display=internal_code.replace("_", " ").title(),
            )
        return None

    def ground_medication(
        self,
        medication_name: str,
    ) -> MedicationCoding:
        """Ground a medication to RxNorm code.

        Args:
            medication_name: Medication name (e.g., "norepinephrine", "aspirin")

        Returns:
            MedicationCoding with RxNorm code if found
        """
        coding = MedicationCoding(name=medication_name)

        if not self._config.enable_rxnorm:
            return coding

        rxnorm_data = self._get_rxnorm(medication_name)
        if rxnorm_data:
            coding.rxnorm_code = rxnorm_data.get("code")
            coding.rxnorm_display = rxnorm_data.get("display", medication_name)

        return coding

    def ground_full(
        self,
        internal_code: str,
        value: Optional[float] = None,
        unit: Optional[str] = None,
    ) -> GroundingResult:
        """Attempt full grounding across all terminology systems.

        Tries LOINC first (for labs), then SNOMED (for diagnoses).
        """
        result = GroundingResult()

        # Try as lab result (LOINC)
        lab_result = self.ground_lab_result(internal_code, value, unit)
        if lab_result.concept:
            result.concept = lab_result.concept
            result.quantity = lab_result.quantity
            result.grounded = True
            return result

        # Try as diagnosis (SNOMED)
        snomed_concept = self.ground_diagnosis(internal_code)
        if snomed_concept:
            result.concept = snomed_concept
            result.grounded = True
            return result

        result.warnings.append(f"No grounding found for: {internal_code}")
        return result

    def _get_loinc_for_internal(self, internal_code: str) -> Optional[str]:
        """Reverse-lookup: internal_code -> LOINC code."""
        if self._loinc_reverse is None:
            self._build_loinc_reverse()

        key = internal_code.lower().strip()
        code = self._loinc_reverse.get(key)
        if code:
            return code

        # Neural fallback
        if self._config.enable_neural_fallback:
            match = self._neural_fallback(key, system="loinc")
            if match:
                return match.code

        if key not in self._unknown_labs:
            self._unknown_labs.add(key)
            logger.debug(f"No LOINC code for internal: {key}")
        return None

    def _get_snomed_for_internal(self, internal_code: str) -> Optional[str]:
        """Reverse-lookup: internal_code -> SNOMED code."""
        if self._snomed_reverse is None:
            self._build_snomed_reverse()

        key = internal_code.lower().strip()
        code = self._snomed_reverse.get(key)
        if code:
            return code

        # Neural fallback
        if self._config.enable_neural_fallback:
            match = self._neural_fallback(key, system="snomed")
            if match:
                return match.code

        return None

    def _get_rxnorm(self, medication_name: str) -> Optional[Dict[str, str]]:
        """Lookup medication in RxNorm mappings."""
        if self._rxnorm is None:
            self._load_rxnorm()

        key = medication_name.lower().strip()
        data = self._rxnorm.get(key)
        if data:
            return data

        # Neural fallback
        if self._config.enable_neural_fallback:
            match = self._neural_fallback(key, system="rxnorm")
            if match:
                return {"code": match.code, "display": match.display}

        if key not in self._unknown_meds:
            self._unknown_meds.add(key)
            logger.debug(f"No RxNorm code for medication: {key}")
        return None

    def _build_loinc_reverse(self):
        """Build reverse mapping: internal_code -> first LOINC code."""
        self._loinc_reverse = {}
        path = Path(self._config.loinc_mapping_path) if self._config.loinc_mapping_path else _MAPPINGS_DIR / "loinc.yaml"

        if not path.exists():
            logger.warning(f"LOINC mapping not found: {path}")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for category, mappings in data.items():
                if isinstance(mappings, dict):
                    for loinc_code, internal_code in mappings.items():
                        key = internal_code.lower().strip()
                        # First occurrence wins (most specific code)
                        if key not in self._loinc_reverse:
                            self._loinc_reverse[key] = str(loinc_code)
        except Exception as e:
            logger.warning(f"Failed to load LOINC mappings: {e}")

    def _build_snomed_reverse(self):
        """Build reverse mapping: internal_code -> first SNOMED code."""
        self._snomed_reverse = {}
        path = Path(self._config.snomed_mapping_path) if self._config.snomed_mapping_path else _MAPPINGS_DIR / "snomed.yaml"

        if not path.exists():
            logger.warning(f"SNOMED mapping not found: {path}")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for category, mappings in data.items():
                if isinstance(mappings, dict):
                    for snomed_code, internal_code in mappings.items():
                        key = internal_code.lower().strip()
                        if key not in self._snomed_reverse:
                            self._snomed_reverse[key] = str(snomed_code)
        except Exception as e:
            logger.warning(f"Failed to load SNOMED mappings: {e}")

    def _load_rxnorm(self):
        """Load RxNorm mappings from YAML."""
        self._rxnorm = {}
        path = Path(self._config.rxnorm_mapping_path) if self._config.rxnorm_mapping_path else _MAPPINGS_DIR / "rxnorm.yaml"

        if not path.exists():
            logger.info(f"RxNorm mapping not found: {path}, using empty")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for category, mappings in data.items():
                if isinstance(mappings, dict):
                    for name, entry in mappings.items():
                        key = str(name).lower().strip()
                        if isinstance(entry, dict):
                            self._rxnorm[key] = entry
                        elif isinstance(entry, str):
                            self._rxnorm[key] = {"code": entry, "display": name}
        except Exception as e:
            logger.warning(f"Failed to load RxNorm mappings: {e}")

    def _neural_fallback(self, query: str, system: str) -> Optional[Any]:
        """Attempt neural embedding-based match as fallback.

        Lazy-initializes NeuralGroundingBackend on first call.
        Returns NeuralMatch or None. Stores result in _last_neural_match.
        """
        self._last_neural_match = None

        if not self._neural_backend_checked:
            self._neural_backend_checked = True
            self._neural_backend = self._init_neural_backend()

        if self._neural_backend is None:
            return None

        match = self._neural_backend.find_best_match(query, system=system)
        if match:
            self._last_neural_match = match
            logger.info(
                f"Neural fallback: '{query}' -> {match.system}:{match.code} "
                f"({match.display}, confidence={match.confidence:.3f})"
            )
        return match

    def _init_neural_backend(self) -> Optional[Any]:
        """Initialize neural backend, returning None if unavailable."""
        try:
            from .neural_backend import (
                NeuralGroundingBackend,
                NeuralGroundingConfig,
            )
            config = self._config.neural_config
            if config is None:
                config = NeuralGroundingConfig()
            backend = NeuralGroundingBackend(config)
            if backend.is_available():
                return backend
            logger.debug("Neural grounding embeddings not found, skipping fallback")
            return None
        except ImportError as e:
            logger.debug(f"Neural grounding dependencies not available: {e}")
            return None
