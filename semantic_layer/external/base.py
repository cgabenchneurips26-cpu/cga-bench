"""Abstract base class for external benchmark adapters.

Full interface per spec: 7 methods covering the complete external benchmark lifecycle.
"""

import warnings
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from .models import NormalizedEpisode


class ExternalBenchmarkAdapter(ABC):
    """Common interface for external benchmark adapters."""

    @abstractmethod
    def load_raw_case(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Load and validate raw case data."""
        ...

    @abstractmethod
    def parse_to_scenario(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw data to scenario dict."""
        ...

    def parse_to_episode_log(self, raw: Dict[str, Any]) -> Any:
        """Deprecated: use parse_to_normalized instead.

        Parse raw data to EpisodeLog (or NormalizedEpisode for backward compat).
        Delegates to parse_to_normalized if not overridden.
        """
        warnings.warn(
            "parse_to_episode_log() is deprecated; use parse_to_normalized() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.parse_to_normalized(raw)

    @abstractmethod
    def parse_to_normalized(self, raw: Dict[str, Any]) -> NormalizedEpisode:
        """Parse raw data to NormalizedEpisode."""
        ...

    @abstractmethod
    def detect_domain(self, raw: Dict[str, Any]) -> str:
        """Detect clinical domain from raw data."""
        ...

    @abstractmethod
    def normalize_actions(self, actions: List[str]) -> List[str]:
        """Normalize action IDs to standard format."""
        ...

    @abstractmethod
    def build_observation(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Build observation dict for agent consumption.

        Returns a dict with input_text, options, structured_fields etc.
        that an agent would see as its environment observation.
        """
        ...

    @abstractmethod
    def parse_agent_output(self, output: Any, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse agent output into structured action events.

        Converts free-text or structured agent response into
        a list of action dicts compatible with the evaluation pipeline.
        """
        ...

    def native_score(self, raw: Dict[str, Any], output: Any) -> Dict[str, Any] | None:
        """Compute benchmark's native score (optional).

        Returns the original benchmark's own scoring if available,
        for comparison with CGA-derived scores. Returns None if not applicable.
        """
        return None
