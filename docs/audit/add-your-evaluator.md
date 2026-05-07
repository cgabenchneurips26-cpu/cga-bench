# Add your evaluator

Two paths to bring a new evaluator into the harness.

## Path A — Pure function on CGA-Bench trajectories

Use when you want to write a scoring rule (MedAgentBench-style,
HealthBench-style, or your own) that runs on the 14,826 CGA-Bench
trajectories.

```python
# cga_bench/audit/wrappers/my_bench.py
from audit.wrappers.external import (
    ExternalBenchmarkEvaluator,
    register_external_benchmark,
)

@register_external_benchmark("mybench")
class MyBenchEvaluator(ExternalBenchmarkEvaluator):
    benchmark_name = "MyBench"
    pass_threshold = 0.7
    pi_family_hypothesis = "aset"
    source_url = "https://my-benchmark.org/paper"

    def score_trajectory(self, trajectory: dict) -> float:
        taken = {a["action_id"] for a in trajectory["actions"] if a.get("action_id")}
        expected = set(trajectory.get("expected_actions") or [])
        return len(taken & expected) / max(1, len(expected))
```

Import the module once at startup (side-effect registers the class),
then run:

```bash
PYTHONPATH=. python scripts/audit/evaluator_audit.py \
    --shim ext_mybench --out-dir audit/reports
```

## Path B — Bridge an existing `ExternalBenchmarkAdapter`

Use when you have an `ExternalBenchmarkAdapter` subclass (from
`semantic_layer/external/`) and want to route its `native_score`
through the audit harness.

```python
# cga_bench/audit/wrappers/my_native_bridge.py
from audit.wrappers.native_adapter import NativeAdapterEvaluator
from audit.wrappers.external import register_external_benchmark
from semantic_layer.external.my_adapter import MyAdapter

@register_external_benchmark("mybench_native")
class MyNativeBridge(NativeAdapterEvaluator):
    benchmark_name = "MyBench-native"
    pi_family_hypothesis = "aset"
    adapter_cls = MyAdapter     # anything with `native_score(raw, output)`

    # override how a CGA-Bench trajectory maps to the adapter's raw/output
    def _raw_from_trajectory(self, trajectory: dict) -> dict:
        return {"expected": trajectory.get("expected_actions") or []}

    def _output_from_trajectory(self, trajectory: dict) -> object:
        return [a["action_id"] for a in trajectory["actions"] if a.get("action_id")]
```

See `audit/wrappers/native_adapter.py` for the base class and the two
worked bridges `ext_medagent_native` and `ext_closedloop_native`.

## Design constraints

- **No TCC-derived fields in `score_trajectory`.** Do not read
  `n_viols`, `viol_types`, `compliance_score`, `sub_scores`, or
  `violation_events`. These are TCC outputs; using them short-circuits
  the BSR measurement. The test suite enforces this via
  `test_observed_features_exclude_tcc_fields`.
- **Deterministic + side-effect free.** No RNG, no network calls.
- **Score range [0, 1]** or set `pass_threshold` accordingly.

## Verification

After adding the subclass:

```bash
# Confirm it registered
PYTHONPATH=. python -c "
from audit.shims import SHIM_REGISTRY
assert 'ext_mybench' in SHIM_REGISTRY
print('OK')"

# One verdict on a real episode
PYTHONPATH=. python -c "
from audit.shims import SHIM_REGISTRY
from audit.shims._verdict_cache import load_w8_episodes
ev = SHIM_REGISTRY['ext_mybench']()
eid = next(iter(load_w8_episodes()))
print(eid, '->', ev.verdict({'episode_id': eid}))"

# Full audit
PYTHONPATH=. python scripts/audit/evaluator_audit.py --shim ext_mybench --out-dir /tmp/my_audit

# Regression sweep
PYTHONPATH=. python scripts/audit/verify_audit_harness.py --fast
```

Expected result of the last command: `Summary: N/N OK, 0 FAIL` (where
N grows by one for each new registered external benchmark).
