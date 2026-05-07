"""Shared domain keyword registry loaded from configs/domain_registry.yaml.

Provides DOMAIN_KEYWORDS dict: {domain_name: [keyword, ...]} for domain detection.
Falls back to a minimal hardcoded dict if YAML is not found.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_REGISTRY_YAML = Path(__file__).resolve().parent.parent / "configs" / "domain_registry.yaml"

_DOMAIN_KEYWORDS_FALLBACK: dict[str, list[str]] = {
    "sepsis": ["sepsis", "septic", "bacteremia"],
    "chest_pain": ["chest pain", "stemi", "nstemi", "mi ", "acs", "myocardial"],
    "aki": ["aki", "renal", "kidney", "creatinine", "dialysis"],
    "dka": ["dka", "ketoacid", "diabetic emergency"],
    "stroke": ["stroke", "tpa", "alteplase", "thrombo", "nihss"],
    "heart_failure": ["heart failure", "hf ", "ejection fraction", "hfref"],
    "oncology": ["cancer", "tumor", "oncolog", "nccn", "chemotherapy", "nsclc"],
}


def load_domain_keywords() -> dict[str, list[str]]:
    """Load domain keywords from configs/domain_registry.yaml.

    Returns a dict mapping domain name -> list of EN + CN keywords.
    Falls back to hardcoded dict if YAML not found or malformed.
    """
    if not _REGISTRY_YAML.is_file():
        return _DOMAIN_KEYWORDS_FALLBACK
    try:
        with open(_REGISTRY_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        domains = data.get("domains", {})
        result: dict[str, list[str]] = {}
        for domain_name, domain_data in domains.items():
            if isinstance(domain_data, dict):
                en_kw = domain_data.get("en_keywords", [])
                cn_kw = domain_data.get("cn_keywords", [])
                keywords: list[str] = []
                if isinstance(en_kw, list):
                    keywords.extend(str(k) for k in en_kw)
                if isinstance(cn_kw, list):
                    keywords.extend(str(k) for k in cn_kw)
                if keywords:
                    result[domain_name] = keywords
        return result if result else _DOMAIN_KEYWORDS_FALLBACK
    except Exception:
        logger.warning("Failed to load domain_registry.yaml; using fallback keywords.")
        return _DOMAIN_KEYWORDS_FALLBACK


DOMAIN_KEYWORDS: dict[str, list[str]] = load_domain_keywords()
