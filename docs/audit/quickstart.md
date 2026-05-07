# Quickstart

Five-minute smoke test from a fresh clone.

## Prerequisites

- Python 3.11+
- CGA-Bench repo checked out at `$CGA_BENCH_ROOT`
- `results/full_706_v6_aliasfix_*/` trajectory files present
- `evidence_pack/analysis/verdict_matrix_v6.json` present

## 1. Run a single audit

```bash
cd $CGA_BENCH_ROOT
PYTHONPATH=. python scripts/audit/evaluator_audit.py \
    --shim v4_hard \
    --out-dir audit/reports \
    --top-k 5
```

Expected output (~0.4 seconds on the v4_hard TCC reference):

```
Auditing evaluator: CGA-Bench (TCC)
  pi-class:      nctx
  BSR:           0.0000 (0/14826)
  Bayes floor:   0.003
  False accepts: 0
  rho(d_G):      0.7383 (mono=0/2481)
  Red cells:     0/43
  Report:        audit/reports/cga_bench/report.json
```

## 2. Run the full regression sweep

```bash
PYTHONPATH=. python scripts/audit/verify_audit_harness.py --fast
```

Expected:

```
Summary: 15/15 OK, 0 FAIL
```

Any failure with `llm_judge` is expected unless the cache at
`evidence_pack/audit/llm_judge_cache.json` is precomputed.

## 3. Launch the Gradio demo

```bash
pip install -r demo/requirements.txt
PYTHONPATH=. python demo/app.py
# open http://localhost:7860
```

## 4. Add your own benchmark

See [Add your evaluator](add-your-evaluator.md) for the 3-step recipe.
TL;DR:

```python
from audit.wrappers.external import (
    ExternalBenchmarkEvaluator, register_external_benchmark,
)

@register_external_benchmark("mybench")
class MyBench(ExternalBenchmarkEvaluator):
    benchmark_name = "MyBench"
    pass_threshold = 0.7
    pi_family_hypothesis = "aset"

    def score_trajectory(self, trajectory: dict) -> float:
        ...
```

The audit CLI immediately sees it as `--shim ext_mybench`.
