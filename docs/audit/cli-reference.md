# CLI reference

## `scripts/audit/evaluator_audit.py`

```
usage: evaluator_audit.py [-h] (--shim SHIM | --evaluator EVALUATOR)
                          [--out-dir OUT_DIR] [--top-k TOP_K]
```

| Flag | Description |
|---|---|
| `--shim <name>` | Pick a registered shim from `SHIM_REGISTRY` |
| `--evaluator <module:Class>` | Load a custom evaluator by dotted path |
| `--out-dir <path>` | Where to write `<evaluator_slug>/report.{md,json}` |
| `--top-k <N>` | Top-K false-accept witnesses to write (default 5) |

Produces 6-step report: π-class, BSR, Bayes floor, witnesses, repair
distance (ρ + monotonicity), blindspot grid.

## `scripts/audit/verify_audit_harness.py`

```
usage: verify_audit_harness.py [-h] [--out-dir OUT_DIR] [--top-k TOP_K] [--fast]
```

Runs `evaluator_audit.py` against every `SHIM_REGISTRY` entry and
asserts the report has the expected structure. Exits 0 iff every shim
passes. Use `--fast` (sets `top_k=0`) for CI.

## `scripts/audit/compute_bayes_error.py`

Regenerates `evidence_pack/theorem_v2/bayes_error_macros.tex`. Uses
`_projections.py` for the four canonical π functions.

## `scripts/audit/build_index.py`

Walks `audit/reports/*/report.json` and emits
`audit/reports/INDEX.md` summarizing every audited evaluator.

## `scripts/experiments/exp_ensemble_bsr.py`

B1 ensemble BSR experiment. Default evaluator pool excludes `v4_hard`
(the TCC reference) to avoid self-pairing.

## `scripts/experiments/exp_bayes_matrix.py`

B2 per-violation-type 4×5 Bayes error matrix. Emits derived row/col
means and sharpest-separation macros to
`evidence_pack/audit/bayes_matrix_derived_macros.tex`.

## `scripts/experiments/exp_pi_nord_witness.py`

B3-retry constructive π_nord witness. Evaluates 4 variant rules
against the TCC reference and writes
`evidence_pack/audit/pi_nord_witness_{macros.tex,results.json}`.

## Gradio demo

```
pip install -r demo/requirements.txt
PYTHONPATH=. python demo/app.py  # http://localhost:7860
```

## MkDocs

```
pip install mkdocs mkdocs-material
mkdocs build        # output: site/
mkdocs serve        # http://localhost:8000
```
