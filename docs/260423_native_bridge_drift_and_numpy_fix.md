# Native-Adapter Bridge: Schema Drift Detection + Numpy Scalar Support

**Date:** 2026-04-23
**Scope:** `audit/wrappers/native_adapter_examples.py`,
`tests/test_audit/test_native_adapter_drift.py` (new)
**Session:** Camera-ready follow-up to `260423_session_final_summary.md`
bridging the two remaining TODOs ("Adapter schema drift 감지 테스트",
"numpy scalar 지원").

---

## 1. Why this change

The three native bridges landed in commit `a619a6b1` (`ext_art_native`,
`ext_agentehr_native`, `ext_healthbench_native`) all reported identical
`BSR=0.4839, 26/43 red` on the audit harness. Identical metrics across
three independent scorers is a red flag — **it usually means every
verdict is `False` and the apparent agreement comes from the reference
distribution alone**, not from any real adapter scoring.

Walking the code found **three silent-failure modes** that together
guaranteed every ART/AgentEHR trajectory scored `0.0`:

| # | Location | Bug |
|---|----------|-----|
| A | `_LazyAdapterBridge._get_adapter()` | Called `cls()` with zero args, but `ARTAdapter`/`AgentEHRAdapter` inherit `UniversalExternalAdapter.__init__(self, manifest)` — the constructor **requires a `DatasetManifest`**. Every instantiation raised, caught by the broad `except Exception`, setting `_adapter_failed=True`. Bridge returned 0.0 forever. |
| B | `_extract_score_from_native_dict` | Looked for keys `{"score", "normalized_score", "satisfied_fraction", "accuracy", "f1", "recall", "coverage"}`. But `ARTAdapter.native_score` returns `{"native_score": ...}` and `AgentEHRAdapter.native_score` returns `{"native_score": f1, "f1": f1, ...}`. ART always fell through to `return 0.0`; AgentEHR got F1 by happy accident. |
| C | `_score_from_adapter` | `isinstance(v, (int, float))` silently drops numpy scalars: `np.float32`, `np.int64`, `np.bool_` do **not** inherit from Python `float`. Only `np.float64` does. Any adapter backed by numpy returning non-float64 scalars would score 0.0. |

The combination was invisible from the outside because the audit
harness' `score < pass_threshold` gate naturally maps 0.0 → `verdict=False`.
Looked healthy. Wasn't.

## 2. Fix

### 2a. Coercion helper (Python bool → numpy scalar → None)

```python
def _coerce_to_unit_float(v: object) -> float | None:
    """[0,1] float or None. Accepts numpy scalars via __float__."""
```

- Handles `bool`, plain `int`/`float`, `np.float32/64`, `np.int32/64`,
  `np.bool_`, and anything else with a working `__float__`.
- **Explicitly rejects strings** even when they parse (drift intent: an
  adapter returning `"0.5"` is contract violation, not success).
- Rejects NaN and ±Inf.
- Clamps to `[0, 1]`.

Returning `None` rather than `0.0` lets callers distinguish "key missing"
from "key present but unusable" — important for the fallback chain.

### 2b. `_NATIVE_SCORE_KEYS` tuple + `native_score` priority

```python
_NATIVE_SCORE_KEYS: tuple[str, ...] = (
    "native_score",  # ART, AgentEHR primary
    "score", "normalized_score", "satisfied_fraction",
    "accuracy", "f1", "recall", "coverage",
)
```

`native_score` now comes first. Drift test asserts `_NATIVE_SCORE_KEYS[0]
== "native_score"` as an invariant so nobody accidentally reorders away
from the ART/AgentEHR primary.

### 2c. `_LazyAdapterBridge` now passes a manifest

Added `_adapter_manifest_id` class var (e.g., `"art"`, `"agentehr"`) and
`_build_manifest()` that resolves via
`semantic_layer.external.registry.get_manifest()` with a minimal
`DatasetManifest` fallback. Also added dual-path import helper
(`_import_adapter_module`) because the underlying
`semantic_layer/external/pipeline.py` uses `from ...cpg_model` which only
resolves when the package is imported as `cga_bench.semantic_layer.*`
(parent-dir PYTHONPATH), not top-level.

### 2d. HealthBench bridge: dual-path import + proper fallback order

The original `val = res.get("normalized") or res.get("normalized_score")`
short-circuits on 0.0 (a valid score). Replaced with an explicit
key-chain loop + `_coerce_to_unit_float`.

## 3. Drift test suite

`tests/test_audit/test_native_adapter_drift.py` — 37 tests, 4 classes:

| Class | Tests | Gate |
|-------|-------|------|
| `TestCoerceToUnitFloat` | 16 | Always runs — covers Python/numpy/edge-case coercion |
| `TestExtractScoreFromNativeDict` | 11 | Always runs — key-drift + primary-key invariant |
| `TestARTBridgeDrift` | 3 | Requires real adapter imports |
| `TestAgentEHRBridgeDrift` | 3 | Requires real adapter imports |
| `TestHealthBenchBridgeDrift` | 3 | Requires real adapter imports |
| `TestNumpyScalarRoundTripThroughBridge` | 1 | Requires real adapter imports |

The "requires real adapter imports" suites are gated by
`@_adapter_skip` — a `pytest.mark.skipif` that probes both top-level and
`cga_bench.*` import paths. In `PYTHONPATH=.` (cga_bench dir) mode they
skip with a clear reason; in `PYTHONPATH=cga_bench:.` (parent dir) mode
they execute.

### Failure-mode coverage

Each drift test is written to fail loudly when the specific regression
reappears:

- `test_adapter_instantiates_with_manifest` — catches constructor
  signature change or `_adapter_manifest_id` misconfiguration.
- `test_native_score_returns_dict_with_known_key` — catches adapter
  renaming its primary score key.
- `test_full_match_produces_nonzero_score` /
  `test_partial_match_produces_nonzero_f1` — catches the whole chain
  from adapter load → score extraction → coercion. If any link breaks,
  these score 0.0 and fail with a specific diagnostic message.
- `test_compute_native_score_returns_normalized_score_key` — pins the
  HealthBench-specific key name.
- `test_bridge_with_numpy_returning_adapter` — injects a monkeypatched
  adapter returning numpy scalars; fails if the bridge drops them.

## 4. Verification

**PYTHONPATH=. (dev default):**
```
tests/test_audit/test_native_adapter_drift.py  27 passed, 10 skipped
tests/test_audit/                              296 passed (full audit suite)
```

**PYTHONPATH=cga_bench:. (full coverage):**
```
cga_bench/tests/test_audit/test_native_adapter_drift.py  37 passed
```

10 skipped → 0 failures in the dev-mode run is the right behavior: the
drift suite degrades gracefully when the semantic_layer module can't be
imported, but runs in full in CI or parent-dir mode.

## 5. Downstream impact — regenerated BSR numbers

The pre-fix values (0.4839, 26/43 red, identical across all three
bridges) were re-run with the fixed bridges on 2026-04-23 against the
v6 canonical corpus (14,826 episodes). Post-fix report JSONs under
`audit/reports/260423_postfix/`.

| Bridge | Pre-fix (silent 0.0) | Post-fix | Red cells Δ | False accepts | ρ(d_G) |
|---|---|---|---|---|---|
| `ext_art_native`         | 0.4839 / 26 red | **0.4430** | −5 (21/43) | 5,653 | 0.1513 |
| `ext_agentehr_native`    | 0.4839 / 26 red | **0.4243** | +3 (29/43) | 3,618 | 0.0950 |
| `ext_healthbench_native` | 0.4839 / 26 red | **0.5210** | −6 (20/43) | 7,354 | 0.0019 |

The spread (0.4243 – 0.5210) is now consistent with theory: ART sits
at the Bayes floor (0.436) as its thin checklist-matching scorer should;
AgentEHR's F1 weighting edges slightly below the floor because F1
rewards precision even on irrelevant labels; HealthBench's rubric
scoring carries more signal and lands above the floor with the highest
false-accept count. MedAgentBench (0.4839) was never buggy so it
remains as-is.

These new numbers are the ones that should appear in the paper. Updated
in `docs/audit/worked-examples.md` and in report JSONs under the
`260423_postfix` subdirectory. The pre-fix values in prior docs should
be read as "silent all-False baseline", not as a real measurement.

## 6. What the drift tests do NOT catch

- Semantic drift (the adapter returns a plausible-looking number that is
  calculated incorrectly). These bridges are thin by design; deep
  semantic validation belongs in the adapter's own test suite, not in
  the drift harness.
- CI running PYTHONPATH=. (cga_bench dir mode). The end-to-end classes
  are gated to skip there — if your CI runs only in that mode you will
  miss real-adapter regressions. Run at least one job with
  `PYTHONPATH=cga_bench:.`.

## 7. Files touched

- `audit/wrappers/native_adapter_examples.py` — +161/-58 lines
- `tests/test_audit/test_native_adapter_drift.py` — +373 lines (new)
- `docs/260423_native_bridge_drift_and_numpy_fix.md` — this document
