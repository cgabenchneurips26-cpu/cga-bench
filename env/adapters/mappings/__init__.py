"""
Medical Code Mappings Loader

LOINC 및 SNOMED CT 코드 매핑을 YAML 파일에서 로드하여 제공
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Set
import logging
import yaml

logger = logging.getLogger(__name__)

_MAPPINGS_DIR = Path(__file__).parent


class MappingLoader:
    """Medical code mapping loader with caching and logging"""

    _loinc_cache: Optional[Dict[str, str]] = None
    _snomed_cache: Optional[Dict[str, str]] = None
    _unknown_loinc: Set[str] = set()
    _unknown_snomed: Set[str] = set()

    @classmethod
    def load_loinc_mappings(cls) -> Dict[str, str]:
        """Load LOINC code mappings from YAML file"""
        if cls._loinc_cache is not None:
            return cls._loinc_cache

        loinc_file = _MAPPINGS_DIR / "loinc.yaml"
        cls._loinc_cache = cls._load_flat_mapping(loinc_file)
        logger.info(f"Loaded {len(cls._loinc_cache)} LOINC code mappings")
        return cls._loinc_cache

    @classmethod
    def load_snomed_mappings(cls) -> Dict[str, str]:
        """Load SNOMED CT code mappings from YAML file"""
        if cls._snomed_cache is not None:
            return cls._snomed_cache

        snomed_file = _MAPPINGS_DIR / "snomed.yaml"
        cls._snomed_cache = cls._load_flat_mapping(snomed_file)
        logger.info(f"Loaded {len(cls._snomed_cache)} SNOMED CT code mappings")
        return cls._snomed_cache

    @classmethod
    def _load_flat_mapping(cls, filepath: Path) -> Dict[str, str]:
        """Load YAML file and flatten nested categories into single dict"""
        if not filepath.exists():
            logger.warning(f"Mapping file not found: {filepath}")
            return {}

        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Flatten nested structure (category -> {code: value})
        flat = {}
        for category, mappings in data.items():
            if isinstance(mappings, dict):
                for code, value in mappings.items():
                    flat[str(code)] = value

        return flat

    @classmethod
    def get_loinc(cls, code: str, default: Optional[str] = None) -> str:
        """
        Get internal code for LOINC code with logging for unknown codes

        Args:
            code: LOINC code (e.g., "8867-4")
            default: Default value if not found (defaults to original code)

        Returns:
            Internal code (e.g., "heart_rate") or default/original code
        """
        mappings = cls.load_loinc_mappings()

        if code in mappings:
            return mappings[code]

        # Log unknown code (only once per code)
        if code not in cls._unknown_loinc:
            cls._unknown_loinc.add(code)
            logger.warning(f"Unknown LOINC code: {code}, using as-is")

        return default if default is not None else code

    @classmethod
    def get_snomed(cls, code: str, default: Optional[str] = None) -> str:
        """
        Get internal diagnosis for SNOMED CT code with logging for unknown codes

        Args:
            code: SNOMED CT code (e.g., "91302008")
            default: Default value if not found (defaults to original code)

        Returns:
            Internal diagnosis code (e.g., "sepsis") or default/original code
        """
        mappings = cls.load_snomed_mappings()

        if code in mappings:
            return mappings[code]

        # Log unknown code (only once per code)
        if code not in cls._unknown_snomed:
            cls._unknown_snomed.add(code)
            logger.warning(f"Unknown SNOMED CT code: {code}, using as-is")

        return default if default is not None else code

    @classmethod
    def get_unknown_codes(cls) -> Dict[str, Set[str]]:
        """Get all unknown codes encountered during processing"""
        return {
            "loinc": cls._unknown_loinc.copy(),
            "snomed": cls._unknown_snomed.copy(),
        }

    @classmethod
    def clear_cache(cls):
        """Clear all cached mappings (useful for testing)"""
        cls._loinc_cache = None
        cls._snomed_cache = None
        cls._unknown_loinc.clear()
        cls._unknown_snomed.clear()


# Convenience functions
def get_loinc_mapping(code: str, default: Optional[str] = None) -> str:
    """Get internal code for LOINC code"""
    return MappingLoader.get_loinc(code, default)


def get_snomed_mapping(code: str, default: Optional[str] = None) -> str:
    """Get internal diagnosis for SNOMED CT code"""
    return MappingLoader.get_snomed(code, default)


# Direct access to full mappings (for backwards compatibility)
def get_all_loinc_mappings() -> Dict[str, str]:
    """Get all LOINC mappings"""
    return MappingLoader.load_loinc_mappings()


def get_all_snomed_mappings() -> Dict[str, str]:
    """Get all SNOMED mappings"""
    return MappingLoader.load_snomed_mappings()


class UCUMMappingLoader:
    """UCUM unit mapping loader with caching."""

    _cache: Optional[Dict[str, str]] = None

    @classmethod
    def load_mappings(cls) -> Dict[str, str]:
        """Load UCUM mappings from YAML file."""
        if cls._cache is not None:
            return cls._cache

        ucum_file = _MAPPINGS_DIR / "ucum.yaml"
        if not ucum_file.exists():
            logger.warning(f"UCUM mapping file not found: {ucum_file}")
            cls._cache = {}
            return cls._cache

        with open(ucum_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        flat: Dict[str, str] = {}
        for category, mappings in data.items():
            if isinstance(mappings, dict):
                for raw, ucum in mappings.items():
                    flat[str(raw).lower().strip()] = ucum

        cls._cache = flat
        logger.info(f"Loaded {len(flat)} UCUM unit mappings")
        return cls._cache

    @classmethod
    def get_ucum(cls, unit_raw: str, default: Optional[str] = None) -> str:
        """Get UCUM canonical form for a unit string."""
        mappings = cls.load_mappings()
        key = unit_raw.lower().strip()
        if key in mappings:
            return mappings[key]
        return default if default is not None else unit_raw

    @classmethod
    def clear_cache(cls):
        """Clear cached mappings."""
        cls._cache = None


class RxNormMappingLoader:
    """RxNorm medication code mapping loader with caching."""

    _cache: Optional[Dict[str, Dict[str, str]]] = None
    _unknown: Set[str] = set()

    @classmethod
    def load_mappings(cls) -> Dict[str, Dict[str, str]]:
        """Load RxNorm mappings from YAML file."""
        if cls._cache is not None:
            return cls._cache

        rxnorm_file = _MAPPINGS_DIR / "rxnorm.yaml"
        if not rxnorm_file.exists():
            logger.warning(f"RxNorm mapping file not found: {rxnorm_file}")
            cls._cache = {}
            return cls._cache

        with open(rxnorm_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        flat: Dict[str, Dict[str, str]] = {}
        for category, mappings in data.items():
            if isinstance(mappings, dict):
                for name, entry in mappings.items():
                    key = str(name).lower().strip()
                    if isinstance(entry, dict):
                        flat[key] = entry
                    elif isinstance(entry, str):
                        flat[key] = {"code": entry, "display": name}

        cls._cache = flat
        logger.info(f"Loaded {len(flat)} RxNorm medication mappings")
        return cls._cache

    @classmethod
    def get_rxnorm(cls, medication_name: str) -> Optional[Dict[str, str]]:
        """Get RxNorm code and display for a medication name."""
        mappings = cls.load_mappings()
        key = medication_name.lower().strip()
        if key in mappings:
            return mappings[key]
        if key not in cls._unknown:
            cls._unknown.add(key)
            logger.debug(f"Unknown medication for RxNorm: {key}")
        return None

    @classmethod
    def clear_cache(cls):
        """Clear cached mappings."""
        cls._cache = None
        cls._unknown.clear()


# Convenience functions for new mappings
def get_ucum_mapping(unit_raw: str, default: Optional[str] = None) -> str:
    """Get UCUM canonical form for a unit string."""
    return UCUMMappingLoader.get_ucum(unit_raw, default)


def get_rxnorm_mapping(medication_name: str) -> Optional[Dict[str, str]]:
    """Get RxNorm code and display for a medication name."""
    return RxNormMappingLoader.get_rxnorm(medication_name)
