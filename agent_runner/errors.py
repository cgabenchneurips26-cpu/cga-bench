"""Agent-runner exceptions.

`EndpointDeadError` is raised when the LLM endpoint has failed enough
consecutive HTTP/connection requests that the worker should exit cleanly
rather than continue producing rule-fallback episodes (which silently
contaminate the dataset, see phase_a_critical_review.md).
"""

from __future__ import annotations


class EndpointDeadError(RuntimeError):
    """LLM endpoint is presumed dead — worker should exit, not fallback."""
