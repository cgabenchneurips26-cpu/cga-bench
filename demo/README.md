# CGA-Bench Audit Demo (Gradio)

Minimal Gradio app that exposes the audit harness as a clickable UI.

## Run locally

```bash
pip install -r demo/requirements.txt
PYTHONPATH=. python demo/app.py
# opens http://localhost:7860
```

Any shim registered in `audit/shims/__init__.py`'s `SHIM_REGISTRY`
appears in the dropdown, including externally-registered benchmarks
(`ext_*` prefix — see `docs/add_external_benchmark_to_audit.md`).

## What the demo shows

For a selected shim the audit returns:

- π-equivalence class (`term` / `aset` / `nord` / `nctx`)
- Blind-Spot Rate vs the TCC reference (`v4_hard`)
- False-accept count
- Bayes-error floor ε* for the classified π-class
- Top-K false-accept witness episode IDs
- Blindspot-grid red-cell count (domain × violation-type)

The underlying computation is `scripts/audit/evaluator_audit.py::run_audit`,
the same entry point the CLI uses.

## HuggingFace Spaces deployment

This app is deployment-ready. To host on HF Spaces:

1. Create a new Space with SDK = Gradio.
2. Copy `demo/` plus the top-level `cga_bench/` package + `results/full_706_v6_aliasfix_*/`
   + `evidence_pack/` into the Space repo.
3. Set the entry point to `demo/app.py`.

The trajectory cache (`audit/shims/_trajectory_cache.py`) and
verdict-matrix cache (`audit/shims/_verdict_cache.py`) both lazy-load
on first audit, so cold start is one-episode's worth of IO per audit.

## Not included in the demo

- Custom-evaluator upload: out of scope for the MVP (the shim dropdown
  already covers all 15 registered evaluators). The dotted-path
  `--evaluator module:Class` route on the CLI remains the path for
  truly custom code.
- Full blindspot-grid heatmap visualization: rendered as red-cell count
  here; the full grid markdown lives in the on-disk report.
