"""Private-field leakage detection for generated scenarios.

Scans scenario YAML outputs to ensure private fields (activated constraint IDs,
expected trace families) are not exposed in agent-visible fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

# ------------------------------------------------------------------
# Canary patterns
# ------------------------------------------------------------------

_PRIVATE_TOKENS = (
    "activated_constraint_id",
    "expected_trace_family",
    "_sgsc_private",
    "private_fields",
    "expected_actions",
    "forbidden_actions",
    "mandatory_actions",
    "ground_truth",
    "trap_description",
    "passing_compliance_threshold",
    "coverage_targets",
)

# Each entry pairs a compiled word-boundary regex with the human-readable token
# name used in leak reports (kept stable for downstream consumers).
_PRIVATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b{re.escape(t)}\b"), t) for t in _PRIVATE_TOKENS
]


# ------------------------------------------------------------------
# Result
# ------------------------------------------------------------------


@dataclass
class LeakageResult:
    """Result of leakage scan."""

    passed: bool
    """True if no leakage detected."""

    leaks: list[dict[str, str]] = field(default_factory=list)
    """Details of each leak found."""

    scenarios_scanned: int = 0


# Alias for clarity — same type, surfaced under the public-scan name
LeakageReport = LeakageResult


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def scan_scenario_for_leakage(
    scenario: dict[str, Any],
    scenario_id: str = "",
) -> list[dict[str, str]]:
    """Scan a single scenario dict for private field leakage.

    Checks all string values in the scenario (recursively) against
    canary patterns. Skips the ``_sgsc_metadata`` top-level key
    (which is server-side only).
    """
    leaks: list[dict[str, str]] = []

    def _scan(obj: Any, path: str) -> None:
        if isinstance(obj, str):
            for pattern, token in _PRIVATE_PATTERNS:
                if pattern.search(obj):
                    leaks.append(
                        {
                            "scenario_id": scenario_id,
                            "path": path,
                            "pattern": token,
                            "value_preview": obj[:100],
                        }
                    )
        elif isinstance(obj, dict):
            for key, val in obj.items():
                if key == "_sgsc_metadata":
                    continue  # Server-side only, not agent-visible
                _scan(val, f"{path}.{key}")
        elif isinstance(obj, list):
            for i, val in enumerate(obj):
                _scan(val, f"{path}[{i}]")

    _scan(scenario, "root")
    return leaks


def scan_public_scenarios(scenarios_public: dict[str, dict[str, Any]]) -> LeakageReport:
    """Scan public-only scenarios for any private field leakage.

    Checks both key names and string values for private patterns.
    Any key matching _PRIVATE_PATTERNS in a public scenario is a leak.
    """
    all_leaks: list[dict[str, str]] = []

    for sid, scenario in scenarios_public.items():
        # Check key names directly (exact match against the private-token list:
        # we deliberately avoid substring matching here so that benign keys like
        # ``unexpected_actions_count`` do not trigger a false positive).
        for key in scenario:
            if key in _PRIVATE_TOKENS:
                all_leaks.append(
                    {
                        "scenario_id": sid,
                        "path": f"root.{key}",
                        "pattern": key,
                        "value_preview": f"<key: {key}>",
                    }
                )
        # Check string values recursively (reuse existing per-scenario scanner)
        all_leaks.extend(scan_scenario_for_leakage(scenario, sid))

    return LeakageReport(
        passed=len(all_leaks) == 0,
        leaks=all_leaks,
        scenarios_scanned=len(scenarios_public),
    )


def scan_scenarios(
    scenarios: dict[str, dict[str, Any]],
) -> LeakageResult:
    """Scan all scenarios for private field leakage.

    Args:
        scenarios: Dict of scenario_id -> scenario dict.

    Returns:
        LeakageResult with pass/fail and leak details.
    """
    all_leaks: list[dict[str, str]] = []
    for sid, scenario in scenarios.items():
        all_leaks.extend(scan_scenario_for_leakage(scenario, sid))

    return LeakageResult(
        passed=len(all_leaks) == 0,
        leaks=all_leaks,
        scenarios_scanned=len(scenarios),
    )
