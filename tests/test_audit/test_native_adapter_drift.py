"""Schema drift detection for native-adapter bridges and numpy scalar support.

These tests fail loudly (rather than silently returning verdict=False) when:

- An external adapter renames its native_score return key, adds a required
  __init__ argument the bridge does not pass, or changes its scorer's
  signature.
- A numpy-backed adapter returns a np.float32 / np.int64 / np.bool_ and the
  bridge's ``isinstance(v, (int, float))`` check silently drops it — a real
  bug we hit in the first native-bridge wiring.

If any test here fails, the bridge is now producing 0.0 scores for every
trajectory, which looks healthy from the outside (verdict=False) but is
useless for auditing. Treat a failure as drift that must be reconciled
before the bridge can be trusted in a sweep.
"""

from __future__ import annotations

from typing import Any

# Import audit.shims FIRST — it registers all shim classes and breaks the
# audit.wrappers <-> audit.shims circular import that hits on direct
# submodule import. Matches the pattern in test_native_adapter.py.
import audit.shims  # noqa: F401
from audit.wrappers.native_adapter_examples import (
    _NATIVE_SCORE_KEYS,
    _coerce_to_unit_float,
    _extract_score_from_native_dict,
)
import pytest

np = pytest.importorskip("numpy")


# ---------------------------------------------------------------------------
# numpy scalar coercion
# ---------------------------------------------------------------------------


class TestCoerceToUnitFloat:
    """Numeric scalars from any backend must round-trip through the bridge."""

    def test_plain_python_float_passes_through(self) -> None:
        assert _coerce_to_unit_float(0.3) == pytest.approx(0.3)

    def test_plain_python_int_coerces(self) -> None:
        assert _coerce_to_unit_float(1) == 1.0
        assert _coerce_to_unit_float(0) == 0.0

    def test_python_bool_coerces(self) -> None:
        assert _coerce_to_unit_float(True) == 1.0
        assert _coerce_to_unit_float(False) == 0.0

    def test_numpy_float64(self) -> None:
        # The one numpy scalar that Python's `isinstance(v, float)` already accepts.
        assert _coerce_to_unit_float(np.float64(0.5)) == pytest.approx(0.5)

    def test_numpy_float32(self) -> None:
        # np.float32 is NOT a subclass of Python float — the original bridge
        # bug was silently rejecting these and returning 0.0 for every score.
        assert _coerce_to_unit_float(np.float32(0.3)) == pytest.approx(0.3, abs=1e-6)

    def test_numpy_int64(self) -> None:
        assert _coerce_to_unit_float(np.int64(1)) == 1.0
        assert _coerce_to_unit_float(np.int64(0)) == 0.0

    def test_numpy_int32(self) -> None:
        assert _coerce_to_unit_float(np.int32(1)) == 1.0

    def test_numpy_bool_(self) -> None:
        assert _coerce_to_unit_float(np.bool_(True)) == 1.0
        assert _coerce_to_unit_float(np.bool_(False)) == 0.0

    def test_clamps_above_one(self) -> None:
        assert _coerce_to_unit_float(1.7) == 1.0
        assert _coerce_to_unit_float(np.float32(9.9)) == 1.0

    def test_clamps_below_zero(self) -> None:
        assert _coerce_to_unit_float(-0.3) == 0.0
        assert _coerce_to_unit_float(np.float64(-99)) == 0.0

    def test_nan_rejected(self) -> None:
        assert _coerce_to_unit_float(float("nan")) is None
        assert _coerce_to_unit_float(np.float64("nan")) is None

    def test_inf_rejected(self) -> None:
        assert _coerce_to_unit_float(float("inf")) is None
        assert _coerce_to_unit_float(float("-inf")) is None

    def test_none_rejected(self) -> None:
        assert _coerce_to_unit_float(None) is None

    def test_string_rejected(self) -> None:
        assert _coerce_to_unit_float("0.5") is None
        assert _coerce_to_unit_float("hello") is None

    def test_dict_rejected(self) -> None:
        assert _coerce_to_unit_float({"score": 0.5}) is None

    def test_list_rejected(self) -> None:
        assert _coerce_to_unit_float([0.5]) is None


# ---------------------------------------------------------------------------
# _extract_score_from_native_dict: key drift detection
# ---------------------------------------------------------------------------


class TestExtractScoreFromNativeDict:
    """Every key ART / AgentEHR / HealthBench document must be recognised."""

    def test_none_returns_zero(self) -> None:
        # None is the documented "adapter declined to score" sentinel.
        assert _extract_score_from_native_dict(None) == 0.0

    def test_empty_dict_returns_zero(self) -> None:
        assert _extract_score_from_native_dict({}) == 0.0

    def test_native_score_key_recognised(self) -> None:
        # ART and AgentEHR both return ``native_score`` — absence of this
        # key in the lookup list was the original silent-zero bug.
        assert _extract_score_from_native_dict({"native_score": 0.77}) == pytest.approx(0.77)

    def test_normalized_score_key_recognised(self) -> None:
        # HealthBench's compute_native_score documents ``normalized_score``.
        assert _extract_score_from_native_dict({"normalized_score": 0.6}) == pytest.approx(0.6)

    def test_legacy_score_key_still_works(self) -> None:
        assert _extract_score_from_native_dict({"score": 0.25}) == pytest.approx(0.25)

    def test_f1_fallback_used_when_primary_missing(self) -> None:
        # AgentEHR returns native_score, but if the rename ever happens and
        # f1 is still there, we gracefully fall back.
        assert _extract_score_from_native_dict({"f1": 0.42}) == pytest.approx(0.42)

    def test_unknown_key_returns_zero(self) -> None:
        # Drift scenario: adapter returns a key nobody recognises.
        # Zero is the audit-harness convention for "unusable" — and a
        # signal that the key-list needs updating.
        assert _extract_score_from_native_dict({"brand_new_metric": 0.9}) == 0.0

    def test_numpy_float32_value_accepted(self) -> None:
        # The core numpy-scalar drift case.
        got = _extract_score_from_native_dict({"native_score": np.float32(0.42)})
        assert got == pytest.approx(0.42, abs=1e-6)

    def test_numpy_int_value_accepted(self) -> None:
        # Happens when an adapter returns hit-count style outputs.
        got = _extract_score_from_native_dict({"coverage": np.int64(1)})
        assert got == 1.0

    def test_native_score_preferred_over_score(self) -> None:
        # If an adapter supplies both for any reason, the primary key wins.
        got = _extract_score_from_native_dict(
            {"native_score": 0.8, "score": 0.1},
        )
        assert got == pytest.approx(0.8)

    def test_primary_key_listed_first(self) -> None:
        # Invariant test: `native_score` must be the first key tried so
        # adapters using it are never accidentally outranked by a
        # pre-existing key in the same dict.
        assert _NATIVE_SCORE_KEYS[0] == "native_score"


# ---------------------------------------------------------------------------
# Bridge end-to-end: the real adapter must be instantiable and score non-zero
# ---------------------------------------------------------------------------
#
# These tests require the semantic_layer.external.* adapters to be
# importable, which in turn requires PYTHONPATH to include the parent of
# ``cga_bench`` (the adapters use ``from ...cpg_model.schemas.base import ...``
# relative imports that go one level beyond the cga_bench package root).
# When pytest runs with PYTHONPATH=. from inside cga_bench/, the adapter
# imports fail — we skip these tests gracefully instead of polluting the
# failure list. Run from the parent dir (PYTHONPATH=parent) for full
# coverage. See memory: ``CGA-Bench PYTHONPATH``.


def _probe_semantic_adapters() -> bool:
    """Try both import paths — see _LazyAdapterBridge._import_adapter_module."""
    for prefix in ("semantic_layer.external", "cga_bench.semantic_layer.external"):
        try:
            __import__(f"{prefix}.art")
            __import__(f"{prefix}.agentehr")
            __import__(f"{prefix}.healthbench")
            return True
        except Exception:
            continue
    return False


_HAS_SEMANTIC_ADAPTERS = _probe_semantic_adapters()

_adapter_skip = pytest.mark.skipif(
    not _HAS_SEMANTIC_ADAPTERS,
    reason=(
        "semantic_layer.external.* adapters require parent-dir PYTHONPATH "
        "(they use relative imports that cross cga_bench root). Skipping "
        "end-to-end bridge drift tests — coercion + key-drift tests still run."
    ),
)


def _import_bridge_classes() -> dict[str, Any]:
    """Lazy import bridge classes; callers should be gated by _adapter_skip."""
    from audit.wrappers.native_adapter_examples import (
        AgentEHRNativeBridge,
        ARTNativeBridge,
        HealthBenchNativeBridge,
    )

    return {
        "art": ARTNativeBridge,
        "agentehr": AgentEHRNativeBridge,
        "healthbench": HealthBenchNativeBridge,
    }


@_adapter_skip
class TestARTBridgeDrift:
    """Catch drift in ARTAdapter's constructor signature + native_score contract."""

    def test_adapter_instantiates_with_manifest(self) -> None:
        # The lazy bridge must be passing the manifest argument — if ART
        # changes signature or registry lookup fails, _get_adapter returns
        # None and every verdict silently becomes False.
        ART = _import_bridge_classes()["art"]
        bridge = ART()
        adapter = bridge._get_adapter()
        assert adapter is not None, (
            "ARTNativeBridge._get_adapter() returned None — adapter failed to "
            "instantiate. Check ARTAdapter constructor signature, manifest "
            "registry, and the _adapter_manifest_id class var."
        )

    def test_native_score_returns_dict_with_known_key(self) -> None:
        ART = _import_bridge_classes()["art"]
        bridge = ART()
        adapter = bridge._get_adapter()
        res = adapter.native_score(  # type: ignore[union-attr]
            {"checklist": ["Give aspirin"]},
            ["give aspirin"],
        )
        assert res is not None, "ARTAdapter.native_score returned None for a non-empty checklist."
        assert isinstance(res, dict)
        assert any(key in res for key in _NATIVE_SCORE_KEYS), (
            f"ARTAdapter native_score keys {list(res.keys())} do not overlap "
            f"with recognised keys {_NATIVE_SCORE_KEYS}. Update _NATIVE_SCORE_KEYS."
        )

    def test_full_match_produces_nonzero_score(self) -> None:
        # End-to-end: if this returns 0.0, something in the chain is broken.
        ART = _import_bridge_classes()["art"]
        bridge = ART()
        score = bridge._score_from_adapter(
            ({"checklist": ["Give aspirin 325mg"]}, ["give aspirin 325mg now"]),
        )
        assert score > 0.0, (
            "ART bridge scored 0.0 on a trajectory with a checklist hit — "
            "drift in either the native_score key, the coercion helper, or "
            "the ART string-match logic."
        )


@_adapter_skip
class TestAgentEHRBridgeDrift:
    def test_adapter_instantiates_with_manifest(self) -> None:
        EHR = _import_bridge_classes()["agentehr"]
        bridge = EHR()
        adapter = bridge._get_adapter()
        assert adapter is not None, (
            "AgentEHRNativeBridge._get_adapter() returned None — adapter "
            "failed to instantiate. Check AgentEHRAdapter constructor + registry."
        )

    def test_native_score_returns_dict_with_known_key(self) -> None:
        EHR = _import_bridge_classes()["agentehr"]
        bridge = EHR()
        adapter = bridge._get_adapter()
        res = adapter.native_score(  # type: ignore[union-attr]
            {
                "label": [{"name": "pneumonia"}, {"name": "sepsis"}],
                "task": "diagnoses_ccs",
            },
            ["pneumonia"],
        )
        assert res is not None
        assert isinstance(res, dict)
        assert any(key in res for key in _NATIVE_SCORE_KEYS), (
            f"AgentEHRAdapter native_score keys {list(res.keys())} do not "
            f"overlap with recognised keys {_NATIVE_SCORE_KEYS}."
        )

    def test_partial_match_produces_nonzero_f1(self) -> None:
        # 1/2 gold recovered with 1 prediction → precision=1, recall=0.5,
        # f1=~0.667. Any drop to 0 indicates drift.
        EHR = _import_bridge_classes()["agentehr"]
        bridge = EHR()
        score = bridge._score_from_adapter(
            (
                {
                    "label": [{"name": "pneumonia"}, {"name": "sepsis"}],
                    "task": "diagnoses_ccs",
                },
                ["pneumonia"],
            ),
        )
        assert score > 0.0, "AgentEHR bridge scored 0.0 on a known partial match."


@_adapter_skip
class TestHealthBenchBridgeDrift:
    def test_full_hit_scores_one(self) -> None:
        HB = _import_bridge_classes()["healthbench"]
        bridge = HB()
        score = bridge._score_from_adapter(
            ([{"criterion": "expected:a", "points": 1}], [True]),
        )
        assert score == pytest.approx(1.0)

    def test_no_hit_scores_zero(self) -> None:
        HB = _import_bridge_classes()["healthbench"]
        bridge = HB()
        score = bridge._score_from_adapter(
            ([{"criterion": "expected:a", "points": 1}], [False]),
        )
        assert score == pytest.approx(0.0)

    def test_compute_native_score_returns_normalized_score_key(self) -> None:
        # Contract: HealthBench is the only bridge that reads a specific key
        # (normalized_score). If the underlying function renames it, the
        # bridge must still fall back to _extract_score_from_native_dict.
        compute_native_score = None
        for mod_name in (
            "semantic_layer.external.healthbench",
            "cga_bench.semantic_layer.external.healthbench",
        ):
            try:
                mod = __import__(mod_name, fromlist=["compute_native_score"])
                compute_native_score = mod.compute_native_score
                break
            except Exception:
                continue
        assert compute_native_score is not None, "healthbench module not importable"

        res = compute_native_score([{"criterion": "a", "points": 1}], [True])
        assert isinstance(res, dict)
        assert "normalized_score" in res, (
            "compute_native_score no longer returns 'normalized_score' — "
            "update HealthBenchNativeBridge._score_from_adapter fallback order."
        )


@_adapter_skip
class TestNumpyScalarRoundTripThroughBridge:
    """End-to-end: a bridge whose adapter returns numpy scalars must still score."""

    def test_bridge_with_numpy_returning_adapter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ART = _import_bridge_classes()["art"]
        bridge = ART()
        adapter = bridge._get_adapter()
        assert adapter is not None

        # Patch the adapter's native_score to return a numpy float32 —
        # simulating a drift where ART switches to numpy scalars.
        def numpy_scorer(raw: Any, output: Any) -> dict[str, Any]:
            return {"native_score": np.float32(0.73), "satisfied": np.int64(3), "total": np.int64(4)}

        monkeypatch.setattr(adapter, "native_score", numpy_scorer)
        score = bridge._score_from_adapter(
            ({"checklist": ["x"]}, ["x"]),
        )
        assert score == pytest.approx(0.73, abs=1e-6), f"Bridge dropped numpy float32 score (got {score})"
