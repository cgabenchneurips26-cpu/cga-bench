"""
UCUM (Unified Code for Units of Measure) normalizer.

Normalizes variant unit strings to canonical UCUM codes per
http://unitsofmeasure.org/ and ISO 11240.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
import logging

import yaml

logger = logging.getLogger(__name__)

_UCUM_CACHE: Optional[Dict[str, str]] = None


def _load_ucum_mappings() -> Dict[str, str]:
    """Load UCUM mappings from YAML file, with built-in fallback."""
    global _UCUM_CACHE
    if _UCUM_CACHE is not None:
        return _UCUM_CACHE

    yaml_path = Path(__file__).parent.parent.parent / "env" / "adapters" / "mappings" / "ucum.yaml"
    if yaml_path.exists():
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            flat: Dict[str, str] = {}
            for category, mappings in data.items():
                if isinstance(mappings, dict):
                    for raw, ucum in mappings.items():
                        flat[str(raw).lower().strip()] = ucum
            _UCUM_CACHE = flat
            logger.info(f"Loaded {len(flat)} UCUM mappings from {yaml_path}")
            return flat
        except Exception as e:
            logger.warning(f"Failed to load UCUM YAML: {e}, using built-in mappings")

    # Built-in fallback mappings
    _UCUM_CACHE = _BUILTIN_UCUM_MAP.copy()
    return _UCUM_CACHE


# Built-in UCUM normalization mappings (case-insensitive keys)
_BUILTIN_UCUM_MAP: Dict[str, str] = {
    # Concentration units
    "mg/dl": "mg/dL",
    "mg/l": "mg/L",
    "g/dl": "g/dL",
    "g/l": "g/L",
    "ug/dl": "ug/dL",
    "ug/l": "ug/L",
    "ng/dl": "ng/dL",
    "ng/l": "ng/L",
    "ng/ml": "ng/mL",
    "pg/ml": "pg/mL",
    "ug/ml": "ug/mL",
    "mg/ml": "mg/mL",
    "mmol/l": "mmol/L",
    "umol/l": "umol/L",
    "nmol/l": "nmol/L",
    "meq/l": "meq/L",
    "mEq/l": "meq/L",
    "meq/L": "meq/L",
    "mEq/L": "meq/L",
    "iu/l": "U/L",
    "u/l": "U/L",
    "iu/ml": "U/mL",
    "u/ml": "U/mL",

    # Cell counts
    "cells/ul": "10*3/uL",
    "cells/mcl": "10*3/uL",
    "10^3/ul": "10*3/uL",
    "10^3/mcl": "10*3/uL",
    "10^6/ul": "10*6/uL",
    "10^6/mcl": "10*6/uL",
    "k/ul": "10*3/uL",
    "k/mcl": "10*3/uL",
    "m/ul": "10*6/uL",
    "/ul": "/uL",
    "/mcl": "/uL",

    # Percentages
    "%": "%",
    "percent": "%",

    # Temperature
    "degc": "Cel",
    "celsius": "Cel",
    "deg c": "Cel",
    "degf": "[degF]",
    "fahrenheit": "[degF]",

    # Pressure
    "mmhg": "mm[Hg]",
    "mm hg": "mm[Hg]",
    "cmh2o": "cm[H2O]",
    "cm h2o": "cm[H2O]",

    # Time
    "sec": "s",
    "seconds": "s",
    "min": "min",
    "minutes": "min",
    "hr": "h",
    "hours": "h",
    "h": "h",

    # Rate / flow
    "ml/hr": "mL/h",
    "ml/h": "mL/h",
    "ml/min": "mL/min",
    "l/min": "L/min",
    "mcg/kg/min": "ug/kg/min",
    "mg/kg/hr": "mg/kg/h",
    "units/hr": "U/h",
    "units/h": "U/h",

    # Volume
    "ml": "mL",
    "l": "L",
    "dl": "dL",
    "ul": "uL",
    "mcl": "uL",

    # Mass
    "mg": "mg",
    "g": "g",
    "kg": "kg",
    "mcg": "ug",
    "ug": "ug",
    "ng": "ng",
    "pg": "pg",

    # Moles
    "mmol": "mmol",
    "umol": "umol",
    "nmol": "nmol",
    "mol": "mol",
    "meq": "meq",

    # Special
    "mosm/kg": "mosm/kg",
    "mosm/l": "mosm/L",
    "ph": "[pH]",
    "beats/min": "/min",
    "bpm": "/min",
    "breaths/min": "/min",
    "/min": "/min",
    "inr": "{INR}",
    "ratio": "{ratio}",
    "titer": "{titer}",
    "copies/ml": "{copies}/mL",
    "miu/ml": "m[IU]/mL",
}


def normalize_ucum(unit_raw: str) -> str:
    """Normalize a unit string to UCUM canonical form.

    Args:
        unit_raw: Raw unit string (e.g., "mg/dL", "meq/l", "10^3/uL")

    Returns:
        UCUM-normalized unit string (e.g., "mg/dL", "meq/L", "10*3/uL")
    """
    if not unit_raw:
        return unit_raw

    mappings = _load_ucum_mappings()
    key = unit_raw.lower().strip()

    if key in mappings:
        return mappings[key]

    # Try without spaces
    key_nospace = key.replace(" ", "")
    if key_nospace in mappings:
        return mappings[key_nospace]

    # Return original if no mapping found
    return unit_raw


def clear_cache():
    """Clear the UCUM mapping cache (for testing)."""
    global _UCUM_CACHE
    _UCUM_CACHE = None
