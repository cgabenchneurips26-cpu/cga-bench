# Adding a New External Benchmark to the Audit Harness

This guide walks through adding a new open-source external medical
benchmark (e.g. AMEGA, MedGUIDE, MedAgentBench, CancerGUIDE, any new
public release) to the CGA-Bench audit harness so its scoring style
can be classified by π-class, compared against the Bayes-error floor,
and surfaced in the blind-spot grid — **all via a single subclass and
one decorator**.

The path exercised end-to-end: `audit/wrappers/external.py` (bridge),
`audit/wrappers/external_examples.py` (two worked examples), then the
audit CLI runs it as `--shim ext_<name>`.

---

## When to use this path

Use `ExternalBenchmarkEvaluator` when you have:

- A published external benchmark with its own scoring rubric (rubric
  points, exact-match, F1 on expected actions, etc.), and
- A way to apply that rubric to a CGA-Bench trajectory JSON (the ones
  under `results/full_706_v6_aliasfix_*/<model_dir>/*.json`).

The wrapper does **not** require the external benchmark to natively
consume CGA-Bench traces. You replicate the benchmark's *scoring
style* on CGA-Bench inputs; the audit harness then tells you where
that style is blind.

If you want to run the external benchmark on its own dataset, use
`run_external_benchmark.py` instead — that's the runner side, not
the audit side.

---

## The 3-step recipe

### Step 1 — Subclass `ExternalBenchmarkEvaluator`

Add a file under `audit/wrappers/` (or your own module) containing:

```python
from audit.wrappers.external import (
    ExternalBenchmarkEvaluator,
    register_external_benchmark,
)


@register_external_benchmark("mybench")
class MyBenchEvaluator(ExternalBenchmarkEvaluator):
    benchmark_name = "MyBench"             # appears in EvaluatorMeta
    pass_threshold = 0.7                    # score >= threshold -> verdict True
    pi_family_hypothesis = "aset"           # documents expected pi-class (verified by step 1)
    source_url = "https://my-benchmark.org/paper"

    def score_trajectory(self, trajectory: dict) -> float:
        """Return a float score in [0, 1] for this CGA-Bench trajectory.

        The trajectory dict has fields:
          - actions: list[{action_id, timestamp_minutes, type, args, justification}]
          - expected_actions: list[str]         (scenario-derived)
          - forbidden_actions: list[str]        (scenario-derived)
          - scenario_id, model_name, ...        (metadata)
        """
        taken = {a["action_id"] for a in trajectory.get("actions", []) if a.get("action_id")}
        expected = set(trajectory.get("expected_actions") or [])
        return len(taken & expected) / max(1, len(expected))
```

That's it for the code. The `@register_external_benchmark("mybench")`
decorator inserts the class into `EXTERNAL_BENCHMARK_REGISTRY`; the
`audit/wrappers/__init__.py` side-effect imports your module (if it
lives under `audit/wrappers/`) or you import it explicitly at startup.

### Step 2 — Verify it's wired up

```bash
PYTHONPATH=. python -c "
from audit.shims import SHIM_REGISTRY
from audit.wrappers import EXTERNAL_BENCHMARK_REGISTRY
assert 'mybench' in EXTERNAL_BENCHMARK_REGISTRY
assert 'ext_mybench' in SHIM_REGISTRY
print('OK: MyBench registered as shim ext_mybench')"
```

### Step 3 — Run the audit

```bash
PYTHONPATH=. python scripts/audit/evaluator_audit.py \
    --shim ext_mybench \
    --out-dir audit/reports \
    --top-k 5
```

This produces `audit/reports/mybench/report.{md,json}` with:

- **π-class classification** (Step 1 of the runbook) — which projection
  equivalence your style factors through (term / aset / nord / nctx).
- **Blind-Spot Rate** against the TCC reference, with false-accept /
  false-reject breakdown.
- **Bayes-error floor** for your classified π-class (theoretical lower
  bound given the observation).
- **ρ(d_G) and monotonicity violations** (Option C2 — minimal-repair
  distance correlation).
- **Blind-spot grid** (Option C3) — domain × constraint-type heatmap
  with exemplar episodes for each red cell.
- **Top-K false-accept witnesses** — concrete episodes where your
  evaluator said "pass" but TCC says "harmful".

---

## Design constraints (must respect)

- **No TCC-derived fields.** `score_trajectory` must not read
  `n_viols`, `viol_types`, `compliance_score`, `sub_scores`, or
  `violation_events` — all of these are TCC assessor outputs and
  consulting them lets your evaluator trivially tie TCC, defeating the
  BSR measurement. The default `observed_features()` already excludes
  them; `test_external_wrapper.py::test_observed_features_exclude_tcc_fields`
  enforces this.
- **Deterministic and side-effect free.** No network calls, no RNG,
  no file writes from inside `score_trajectory`.
- **Range [0, 1] or adjust `pass_threshold` accordingly.** The wrapper
  does a simple ≥ comparison; keep semantics consistent.

---

## Current worked examples

Two concrete `ExternalBenchmarkEvaluator` subclasses ship in
`audit/wrappers/external_examples.py`:

| Shim key | Scoring style | `pi_family_hypothesis` | `pass_threshold` |
|---|---|---|---|
| `ext_medagent_style` | action-list F1 vs expected, no ordering | `aset` | 0.8 |
| `ext_healthbench_style` | rubric-point hits − forbidden penalties, normalized | `aset` | 0.6 |

Both are smoke-tested by `test_external_wrapper.py` and appear in the
harness audit run — see `audit/reports/INDEX.md` (after running
`python scripts/audit/verify_audit_harness.py`).

---

## Verification commands

End-to-end sanity after adding `mybench`:

```bash
# 1. Registration
PYTHONPATH=. python -c "
from audit.shims import SHIM_REGISTRY
print('ext_mybench' in SHIM_REGISTRY)"

# 2. Instantiate + one verdict on a real episode
PYTHONPATH=. python -c "
from audit.shims import SHIM_REGISTRY
from audit.shims._verdict_cache import load_w8_episodes
ev = SHIM_REGISTRY['ext_mybench']()
eid = next(iter(load_w8_episodes()))
print(eid, '->', ev.verdict({'episode_id': eid}))"

# 3. Full audit report
PYTHONPATH=. python scripts/audit/evaluator_audit.py --shim ext_mybench --out-dir /tmp/my_audit --top-k 3

# 4. Full harness regression (all shims incl. your new one)
PYTHONPATH=. python scripts/audit/verify_audit_harness.py --fast
```

If step 4 prints `Summary: N/N OK, 0 FAIL`, the addition is fully
wired into the audit pipeline.

---

## Related

- Option B plan: `docs/attack_gap_exp_exp/260422_evaluator_expansion_option_b_plan.md`
- Option C plan: `docs/attack_gap_exp_exp/260422_evaluator_expansion_option_c_plan.md`
- Self-review of B-tier: `docs/260423_btier_self_review.md`
- B3 retry (constructive π_nord witness): `docs/260423_b3_retry_report.md`
