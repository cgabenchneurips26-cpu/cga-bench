"""Worked native-adapter bridges.

Each bridge subclass wires a CGA-Bench trajectory into an external
benchmark's own native scoring function, producing a [0, 1] score that
the audit harness then thresholds into a verdict. Registered bridges:

  - ``ext_medagent_native``   → MedAgentBench ``evaluate_medagentbench_task``
  - ``ext_art_native``        → ARTAdapter ``native_score`` (checklist
                                 satisfaction fraction)
  - ``ext_agentehr_native``   → AgentEHRAdapter ``native_score`` (label
                                 recall / F1)
  - ``ext_healthbench_native`` → HealthBench ``compute_native_score``
                                 (rubric normalized score)

These bridges are deliberately thin: they demonstrate the pattern end-to-
end on the audit CLI and respect scorer-agent isolation (no imports of
cpg_engine or assessor_core). They do NOT claim fidelity to the
external benchmarks' evaluation on the benchmarks' own datasets — the
input shapes differ by construction. For faithful native scoring on the
benchmark's own data, use ``run_external_benchmark.py`` (the runner side).
"""

from __future__ import annotations

from typing import Any

from audit.wrappers.external import register_external_benchmark
from audit.wrappers.native_adapter import NativeAdapterEvaluator


def _coerce_to_unit_float(v: object) -> float | None:
    """Coerce a value to a float clamped to [0, 1], or None if non-numeric.

    Accepts Python ``int``/``float``/``bool`` and numpy scalars
    (``np.float32``, ``np.float64``, ``np.int64``, ``np.bool_``, …) — anything
    with a working ``__float__``. Rejects ``NaN`` and non-numeric inputs so
    callers can distinguish "key missing" from "key present but unusable".

    Use this everywhere a native adapter's return dict feeds the bridge,
    because ``isinstance(v, (int, float))`` silently drops np.float32 /
    np.int64 / np.bool_ (numpy.float64 is the only scalar that inherits
    from Python float).
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return float(v)
    # Explicitly reject strings even if they parse — an adapter returning
    # `"0.5"` instead of `0.5` is schema drift that should fail loudly
    # rather than silently succeed.
    if isinstance(v, (str, bytes, bytearray)):
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    if f == float("inf") or f == float("-inf"):
        return None
    return max(0.0, min(1.0, f))


@register_external_benchmark("medagent_native")
class MedAgentBenchNativeBridge(NativeAdapterEvaluator):
    """Routes CGA-Bench trajectories through MedAgentBench's native scorer.

    The native scorer (``evaluate_medagentbench_task`` in
    ``semantic_layer/external/medagentbench.py``) expects a task dict
    with ``case_id``, ``instruction``, and optional ``observed`` actions.
    We build this from the CGA-Bench trajectory's scenario_id (used as
    case_id), the combined expected_actions + forbidden_actions as the
    task description, and the ordered taken actions as ``observed``.
    """

    benchmark_name = "MedAgentBench-native"
    pass_threshold = 0.5
    pi_family_hypothesis = "aset"
    source_url = "https://arxiv.org/abs/2501.14654"

    def _build_adapter_input(self, trajectory: dict[str, Any]) -> dict:
        scenario_id = trajectory.get("scenario_id", "unknown")
        taken = [a.get("action_id") for a in (trajectory.get("actions") or []) if a.get("action_id")]
        expected = trajectory.get("expected_actions") or []
        forbidden = trajectory.get("forbidden_actions") or []
        instruction = f"Expected actions: {', '.join(expected)}. Forbidden: {', '.join(forbidden)}."
        return {
            "case_id": scenario_id,
            "instruction": instruction,
            "context": "",
            "observed": {
                "actions": taken,
                "event_count": len(taken),
                "observed_source": "cga_bench_trajectory",
            },
        }

    def _score_from_adapter(self, adapter_input: dict) -> float:
        # Import lazily so we don't trigger heavy dependencies at registration.
        from semantic_layer.external.medagentbench import evaluate_medagentbench_task

        task = {
            "case_id": adapter_input["case_id"],
            "instruction": adapter_input["instruction"],
            "context": adapter_input.get("context", ""),
        }
        observed = adapter_input.get("observed")
        report = evaluate_medagentbench_task(task=task, observed=observed)

        # Extract a [0, 1] score from the report. The report's shape is
        # adapter-specific; we prefer `compliance_score` if present, else
        # derive from mandatory completion coverage.
        score = getattr(report, "compliance_score", None)
        if score is not None:
            return max(0.0, min(1.0, float(score)))

        mandatory = list(getattr(report, "mandatory_actions", []) or [])
        performed = list(getattr(report, "performed_actions", []) or [])
        if not mandatory:
            return 1.0
        hit = len(set(performed) & set(mandatory))
        return hit / len(mandatory)


# Ordered list of keys the bridge will try on an adapter's native_score
# return dict. `native_score` comes first because the ART and AgentEHR
# adapters name their primary score that way; if you rename this key in a
# new adapter, add the new name here (or the drift tests will flag it).
_NATIVE_SCORE_KEYS: tuple[str, ...] = (
    "native_score",
    "score",
    "normalized_score",
    "satisfied_fraction",
    "accuracy",
    "f1",
    "recall",
    "coverage",
)


def _extract_score_from_native_dict(res: dict | None) -> float:
    """Defensive extraction — different adapters return different key names.

    Returns 0.0 when ``res`` is ``None`` (adapter declined to score) or when
    no recognised key holds a numeric value. Accepts numpy scalars because
    adapters backed by numpy often return np.float32 / np.int64 / np.bool_,
    which ``isinstance(v, (int, float))`` silently rejects.
    """
    if res is None:
        return 0.0
    for key in _NATIVE_SCORE_KEYS:
        v = res.get(key)
        coerced = _coerce_to_unit_float(v)
        if coerced is not None:
            return coerced
    return 0.0


class _LazyAdapterBridge(NativeAdapterEvaluator):
    """Helper: bridges with adapters that may require optional deps.

    Subclass sets ``_adapter_module``, ``_adapter_class_name``, and
    ``_adapter_manifest_id`` (the dataset id in
    ``semantic_layer.external.registry``). The adapter is imported and
    instantiated on first ``verdict`` call. Import / construction failure
    yields a permanent sentinel that makes every verdict return False, so
    a missing optional dep degrades gracefully rather than breaking the
    whole audit harness.
    """

    _adapter_module: str = ""
    _adapter_class_name: str = ""
    # Dataset id to look up in semantic_layer.external.registry. If the
    # id is unknown to the registry, a minimal DatasetManifest with just
    # this id is synthesised so the bridge still works without pinning.
    _adapter_manifest_id: str = ""

    def __init__(self) -> None:
        self._adapter = None
        self._adapter_failed = False

    def _import_adapter_module(self) -> Any:
        """Import the adapter module, trying both top-level and cga_bench.* paths.

        ``semantic_layer/external/pipeline.py`` uses a ``from ...cpg_model``
        relative import that only resolves when the package is imported as
        ``cga_bench.semantic_layer.*``. But the rest of the audit harness
        expects top-level ``audit.*``. We try both so the bridge works in
        either PYTHONPATH layout.
        """
        candidates = [self._adapter_module]
        if not self._adapter_module.startswith("cga_bench."):
            candidates.append(f"cga_bench.{self._adapter_module}")
        last_exc: Exception | None = None
        for mod_name in candidates:
            try:
                return __import__(mod_name, fromlist=[self._adapter_class_name])
            except Exception as e:  # ImportError and relative-import errors
                last_exc = e
                continue
        if last_exc is not None:
            raise last_exc
        raise ImportError(f"no candidate succeeded for {self._adapter_module}")

    def _build_manifest(self) -> object:
        """Return a DatasetManifest suitable for the adapter constructor.

        Registered datasets get their pinned manifest; unregistered ones
        get a minimal fallback so the bridge is still usable for ad-hoc
        experimentation.
        """
        # Try both import paths for the same reason as _import_adapter_module.
        models_mod = None
        for mod_name in ("semantic_layer.external.models", "cga_bench.semantic_layer.external.models"):
            try:
                models_mod = __import__(mod_name, fromlist=["DatasetManifest"])
                break
            except Exception:
                continue
        if models_mod is None:
            raise ImportError("Could not import DatasetManifest from either path")
        DatasetManifest = models_mod.DatasetManifest

        if not self._adapter_manifest_id:
            return DatasetManifest(dataset_id="unknown", dataset_name="unknown")
        for reg_name in ("semantic_layer.external.registry", "cga_bench.semantic_layer.external.registry"):
            try:
                reg = __import__(reg_name, fromlist=["get_manifest"])
                return reg.get_manifest(self._adapter_manifest_id)
            except Exception:
                continue
        return DatasetManifest(
            dataset_id=self._adapter_manifest_id,
            dataset_name=self._adapter_manifest_id,
        )

    def _get_adapter(self) -> object | None:
        if self._adapter_failed:
            return None
        if self._adapter is not None:
            return self._adapter
        try:
            module = self._import_adapter_module()
            cls = getattr(module, self._adapter_class_name)
            self._adapter = cls(self._build_manifest())
            return self._adapter
        except Exception:
            self._adapter_failed = True
            return None


@register_external_benchmark("art_native")
class ARTNativeBridge(_LazyAdapterBridge):
    """Routes CGA-Bench trajectories through ART's checklist-satisfaction scorer."""

    benchmark_name = "ART-native"
    pass_threshold = 0.5
    pi_family_hypothesis = "aset"
    source_url = "https://arxiv.org/abs/2502.06589"

    _adapter_module = "semantic_layer.external.art"
    _adapter_class_name = "ARTAdapter"
    _adapter_manifest_id = "art"

    def _build_adapter_input(self, trajectory: dict[str, Any]) -> tuple[dict, list[str]]:
        taken = [a.get("action_id") for a in (trajectory.get("actions") or []) if a.get("action_id")]
        checklist = list(trajectory.get("expected_actions") or [])
        raw = {"checklist": checklist}
        return raw, taken

    def _score_from_adapter(self, adapter_input: tuple[dict, list[str]]) -> float:
        adapter = self._get_adapter()
        if adapter is None:
            return 0.0
        raw, output = adapter_input
        res = adapter.native_score(raw, output)
        return _extract_score_from_native_dict(res)


@register_external_benchmark("agentehr_native")
class AgentEHRNativeBridge(_LazyAdapterBridge):
    """Routes CGA-Bench trajectories through AgentEHR's label-recall scorer."""

    benchmark_name = "AgentEHR-native"
    pass_threshold = 0.5
    pi_family_hypothesis = "aset"
    source_url = "https://arxiv.org/abs/2501.14514"

    _adapter_module = "semantic_layer.external.agentehr"
    _adapter_class_name = "AgentEHRAdapter"
    _adapter_manifest_id = "agentehr"

    def _build_adapter_input(self, trajectory: dict[str, Any]) -> tuple[dict, list[str]]:
        taken = [a.get("action_id") for a in (trajectory.get("actions") or []) if a.get("action_id")]
        labels = [{"name": e} for e in (trajectory.get("expected_actions") or [])]
        raw = {"label": labels, "task": trajectory.get("scenario_id", "")}
        return raw, taken

    def _score_from_adapter(self, adapter_input: tuple[dict, list[str]]) -> float:
        adapter = self._get_adapter()
        if adapter is None:
            return 0.0
        raw, output = adapter_input
        res = adapter.native_score(raw, output)
        return _extract_score_from_native_dict(res)


@register_external_benchmark("healthbench_native")
class HealthBenchNativeBridge(NativeAdapterEvaluator):
    """Routes CGA-Bench trajectories through HealthBench's rubric-points scorer."""

    benchmark_name = "HealthBench-native"
    pass_threshold = 0.5
    pi_family_hypothesis = "aset"
    source_url = "https://openai.com/index/healthbench/"

    def _build_adapter_input(self, trajectory: dict[str, Any]) -> tuple[list[dict], list[bool]]:
        taken = {a.get("action_id") for a in (trajectory.get("actions") or []) if a.get("action_id")}
        expected = list(trajectory.get("expected_actions") or [])
        forbidden = list(trajectory.get("forbidden_actions") or [])
        # +1 per expected action (hit if taken), -1 per forbidden (hit if taken → penalty)
        rubrics: list[dict] = [{"criterion": f"expected:{e}", "points": 1} for e in expected] + [
            {"criterion": f"forbidden:{f}", "points": -1} for f in forbidden
        ]
        satisfied: list[bool] = [e in taken for e in expected] + [f in taken for f in forbidden]
        return rubrics, satisfied

    def _score_from_adapter(self, adapter_input: tuple[list[dict], list[bool]]) -> float:
        # Try both import paths — see _LazyAdapterBridge._import_adapter_module.
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
        if compute_native_score is None:
            return 0.0

        rubrics, satisfied = adapter_input
        if not rubrics:
            return 1.0
        res = compute_native_score(rubrics, satisfied)
        # compute_native_score returns "normalized_score"; fall back to the
        # shared key list (which also accepts numpy scalars) if it ever
        # renames. Note: we cannot short-circuit with ``or`` because 0.0 is
        # a valid score value.
        for key in ("normalized_score", "normalized"):
            coerced = _coerce_to_unit_float(res.get(key))
            if coerced is not None:
                return coerced
        return _extract_score_from_native_dict(res)
