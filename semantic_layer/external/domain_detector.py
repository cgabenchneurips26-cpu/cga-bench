"""Enhanced multilingual domain detection for external benchmarks.

Maps clinical text (English + Chinese) to CGA-Bench CPG guideline domains.
Supports 12 domains (6 original + 6 expanded).

Domain registry is loaded from configs/domain_registry.yaml at module import.
Falls back to a hardcoded minimal registry if the YAML file is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DOMAIN_REGISTRY_YAML = Path(__file__).resolve().parents[2] / "configs" / "domain_registry.yaml"


def _load_domain_registry(yaml_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load domain registry from YAML config file.

    Falls back to an empty dict (with warning) if the file is missing or
    cannot be parsed.  The YAML structure is::

        domains:
          sepsis:
            guideline_id: "cpg_model/graphs/ssc_sepsis_hour1.yaml"
            en_keywords: [...]
            cn_keywords: [...]
            action_keywords_cn: {...}
    """
    path = yaml_path or _DOMAIN_REGISTRY_YAML
    if not path.exists():
        logger.warning("Domain registry YAML not found at %s; using empty registry", path)
        return {}

    try:
        import yaml  # noqa: PLC0415 — lazy import to avoid hard dependency at module level

        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        if not isinstance(raw, dict) or "domains" not in raw:
            logger.warning("Invalid domain registry format in %s", path)
            return {}
        domains = raw["domains"]
        if not isinstance(domains, dict):
            return {}
        return {str(k): v for k, v in domains.items() if isinstance(v, dict)}
    except Exception as exc:
        logger.warning("Failed to load domain registry from %s: %s", path, exc)
        return {}


DOMAIN_REGISTRY: dict[str, dict[str, Any]] = _load_domain_registry()


@dataclass
class DomainMatch:
    domain: str
    guideline_id: str
    confidence: float
    matched_keywords: list[str]


@dataclass
class DomainDetectorConfig:
    min_confidence: float = 0.3

    @classmethod
    def default(cls) -> DomainDetectorConfig:
        return cls()


def detect_domain(
    text: str, config: DomainDetectorConfig | None = None,
) -> DomainMatch | None:
    if config is None:
        config = DomainDetectorConfig.default()
    if not text:
        return None

    lower = text.lower()
    best: DomainMatch | None = None

    for domain, info in DOMAIN_REGISTRY.items():
        matched: list[str] = []
        score = 0.0

        for kw in info["en_keywords"]:
            if kw in lower:
                matched.append(kw)
                score += 1.0

        for kw in info["cn_keywords"]:
            if kw in text:
                matched.append(kw)
                score += 1.0

        if not matched:
            continue

        total_kw = len(info["en_keywords"]) + len(info["cn_keywords"])
        confidence = min(1.0, score / max(total_kw * 0.3, 1))

        if confidence >= config.min_confidence and (
            best is None or confidence > best.confidence
        ):
            best = DomainMatch(
                domain=domain,
                guideline_id=info["guideline_id"],
                confidence=confidence,
                matched_keywords=matched,
            )

    return best


def extract_actions_from_text(text: str, domain: str) -> list[str]:
    actions = ["take_history", "assess_vital_signs", "assess_chief_complaint"]
    info = DOMAIN_REGISTRY.get(domain)
    if not info:
        return actions
    action_map = info.get("action_keywords_cn", {})
    for kw, action_id in action_map.items():
        if kw in text and action_id not in actions:
            actions.append(action_id)
    return actions


def list_supported_domains() -> list[str]:
    return sorted(DOMAIN_REGISTRY.keys())
