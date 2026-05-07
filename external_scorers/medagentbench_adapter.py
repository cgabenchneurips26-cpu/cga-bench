"""MedAgentBench native-scorer adapter (CRES-3).

Converts CGA-Bench cached verdict records into the input schema expected
by MedAgentBench's own scorer. The target schema is inferred from the
MedAgentBench paper (Jiang et al. 2025) + the public repo layout; the
exact call signature for `run_native_scorer` is a stub until the repo
has been cloned and wired up (see external_scorers/README.md for the
anonymity-safe clone protocol).

The adapter is deliberately tolerant: any cached record that can't be
represented gets rejected with a clear reason string, and the runner
aggregates rejection reasons so we don't silently drop traces.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Expected top-level keys in MedAgentBench "TraceRecord" (inferred from paper):
#   - scenario_id: str
#   - ground_truth_actions: list[str]    # aka `expected_actions`
#   - predicted_actions:    list[str]    # aka `performed_actions`
#   - trace_metadata:       dict[str, Any]

MEDAGENTBENCH_REQUIRED_FIELDS: tuple[str, ...] = (
    "scenario_id",
    "ground_truth_actions",
    "predicted_actions",
)


@dataclass(frozen=True)
class MedAgentBenchRecord:
    """One record in the format MedAgentBench's scorer consumes."""

    scenario_id: str
    ground_truth_actions: list[str]
    predicted_actions: list[str]
    trace_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "ground_truth_actions": list(self.ground_truth_actions),
            "predicted_actions": list(self.predicted_actions),
            "trace_metadata": dict(self.trace_metadata),
        }


@dataclass
class MedAgentBenchScoreRow:
    """A single (record, native_score) output row."""

    scenario_id: str
    run_index: int
    model: str
    native_pass: bool
    native_score: float
    proxy_pass: bool  # our AC-Proxy pass/fail for comparison
    error: str | None = None


class MedAgentBenchAdapter:
    """Translate cached verdict records <-> MedAgentBench native scorer.

    The `native_scorer` callable is injected so tests (and the runner's
    --dry-run mode) can plug in a stub. At real-run time the runner
    binds this to the scorer imported from the cloned repo.
    """

    def __init__(
        self,
        native_scorer: Callable[[MedAgentBenchRecord], tuple[bool, float]] | None = None,
    ) -> None:
        self._native_scorer = native_scorer or _unwired_scorer

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def record_to_medagentbench(
        self,
        record: dict[str, Any],
    ) -> MedAgentBenchRecord:
        """Convert one cached verdict record to a MedAgentBenchRecord.

        Raises ValueError if required fields are missing.

        FAITHFULNESS NOTE: action IDs in the cached verdicts have already
        been lowercased and underscore-normalized by
        ``_episode_cache._normalize_action``. If MedAgentBench's native
        scorer is case/underscore-sensitive, verdicts may disagree with
        ours purely because of this pipeline-level normalization rather
        than any genuine scoring difference. Before publishing the defense
        result, spot-check 10-20 scenarios where native verdict != proxy
        verdict and confirm the disagreement is substantive, not a
        normalization artefact. Ideally extend the verdict cache to carry
        raw unnormalized action IDs alongside normalized ones.
        """
        missing = [k for k in ("scenario_id",) if not record.get(k)]
        if missing:
            raise ValueError(f"record missing required keys: {missing}")

        performed = record.get("performed_actions") or []
        expected = record.get("expected_actions") or []
        if not isinstance(performed, list) or not isinstance(expected, list):
            raise ValueError("performed_actions / expected_actions must be list[str]")

        metadata = {
            "run_index": int(record.get("run_index", 0) or 0),
            "model": record.get("model", "unknown"),
            "n_actions": int(record.get("n_actions", len(performed)) or 0),
            "n_expected": int(record.get("n_expected", len(expected)) or 0),
        }
        return MedAgentBenchRecord(
            scenario_id=str(record["scenario_id"]),
            ground_truth_actions=[str(a) for a in expected],
            predicted_actions=[str(a) for a in performed],
            trace_metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Batch scoring
    # ------------------------------------------------------------------

    def score_batch(
        self,
        records: list[dict[str, Any]],
    ) -> tuple[list[MedAgentBenchScoreRow], list[dict[str, Any]]]:
        """Convert + score a batch; return (rows, rejections).

        Each rejection is a dict with {scenario_id, reason} so the runner
        can report per-reason counts.
        """
        rows: list[MedAgentBenchScoreRow] = []
        rejections: list[dict[str, Any]] = []
        for rec in records:
            sid = rec.get("scenario_id", "<unknown>")
            try:
                mab_rec = self.record_to_medagentbench(rec)
            except ValueError as exc:
                rejections.append({"scenario_id": sid, "reason": str(exc)})
                continue
            try:
                native_pass, native_score = self._native_scorer(mab_rec)
            except NotImplementedError as exc:
                rejections.append(
                    {
                        "scenario_id": sid,
                        "reason": f"native scorer not wired: {exc}",
                    }
                )
                continue
            except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
                # Narrow catch: lets KeyboardInterrupt / MemoryError / SystemExit
                # bubble so operators can abort, and so genuine bugs in the
                # native scorer surface. Schema-drift failures show up as
                # KeyError / TypeError — we want those loudly rejected with
                # the type name visible for post-run triage.
                rejections.append(
                    {
                        "scenario_id": sid,
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            rows.append(
                MedAgentBenchScoreRow(
                    scenario_id=mab_rec.scenario_id,
                    run_index=int(mab_rec.trace_metadata["run_index"]),
                    model=str(mab_rec.trace_metadata["model"]),
                    native_pass=bool(native_pass),
                    native_score=float(native_score),
                    proxy_pass=bool(rec.get("ac_proxy", False)),
                )
            )
        return rows, rejections


# ---------------------------------------------------------------------------
# Default (unwired) scorer
# ---------------------------------------------------------------------------


def _unwired_scorer(_: MedAgentBenchRecord) -> tuple[bool, float]:
    """Placeholder that forces the runner into dry-run mode until the
    MedAgentBench repo is cloned and a real scorer is bound.
    """
    raise NotImplementedError(
        "MedAgentBench native scorer is not bound. See external_scorers/README.md for the clone protocol."
    )


def bind_native_scorer_from_clone(
    clone_dir: Path,
) -> Callable[[MedAgentBenchRecord], tuple[bool, float]]:
    """Attempt to import MedAgentBench's native scorer from a local clone.

    Returns the bound scorer callable, or raises FileNotFoundError if the
    clone layout is unexpected. The exact module path is a guess and will
    need to be updated once the repo has been inspected — intentionally
    not wired to real code this session.
    """
    if not clone_dir.is_dir():
        raise FileNotFoundError(f"MedAgentBench clone not found at {clone_dir}")

    # Intentionally unbound — next session must replace this with
    # `from medagentbench.scorer import score_trace` or whatever the real
    # import path turns out to be.
    raise NotImplementedError(
        "Real scorer binding deferred to next session: inspect the clone "
        "layout at %s and wire the native scorer module here." % clone_dir
    )
