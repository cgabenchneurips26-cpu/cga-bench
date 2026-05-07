# CGA-Bench Reproducibility Guide

This document provides step-by-step instructions to reproduce all results reported in the paper.

## Prerequisites

- **Python 3.10+** (tested on 3.11 / 3.12 / 3.13). The codebase uses
  PEP-604 union syntax (`int | None`) and PEP-585 generics (`list[str]`)
  in module-level type annotations. Python 3.8 / 3.9 will fail at import
  with `TypeError: 'type' object is not subscriptable` or
  `unsupported operand type(s) for |: 'type' and 'NoneType'`.
- conda (recommended) or virtualenv
- 16GB RAM minimum
- GPU with 80GB+ VRAM for full episode execution (optional for analysis-only reproduction)

### Verifying your environment

If you cloned the **submission tree** (`cga_bench_submission/`), rename it
first — all imports use `from cga_bench.*`:

```bash
mv cga_bench_submission cga_bench   # or: ln -s cga_bench_submission cga_bench
cd cga_bench
```

Install dependencies (see README.md for full notes — there is no
`requirements.txt` or `pyproject.toml`; use the lock or split files):

```bash
pip install -r requirements.lock
# OR a smaller install:
pip install -r requirements-scorer.txt   # for analysis-only reproduction
pip install -r requirements-agent.txt    # additionally for agent runs
```

Pick a Python that has both 3.10+ AND the project deps installed:

```bash
# Verify Python version >= 3.10
python -c "import sys; assert sys.version_info >= (3, 10), sys.version"

# Verify deps importable
python -c "import pydantic, yaml; print('deps OK')"

# Verify cga_bench imports — PYTHONPATH must point to the PARENT of
# cga_bench/, NOT cga_bench/ itself, because all imports are absolute
# (from cga_bench.*). From inside cga_bench/, use PYTHONPATH=..:
PYTHONPATH=.. python -c "
from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.assessor_core.violations import ViolationExtractor
from cga_bench.agent_runner.rag_agent import RAGAgent
print('imports OK')
"

# Mock-LLM benchmark smoke run (no API, no GPU):
PYTHONPATH=.. python run_benchmark.py --scenario septic_shock_basic \
    --agent rag_gpt4 --mock-llm

# Or run the bundled verifier (covers 19 modules + 11 critical files):
python scripts/submission/prepare_submission.py \
    --source . --dest . --verify-only
```

The Makefile targets (`make test`, `make test-fast`, `make benchmark-mock`,
`make reproduce`) wrap pytest, which auto-discovers the package via
the top-level `conftest.py`; they continue to work with `PYTHONPATH=.`
as written.

## Quick Start (Analysis Only, No GPU)

```bash
# 1. Environment setup
conda env create -f environment.yml
conda activate cga-bench

# 2. Validate CPG graphs and conditional rules
make validate

# 3. Run all tests (194 tests)
make test

# 4. Derive constraints from CPG graphs
make derive

# 5. Generate scenarios from graphs
make generate

# 6. Verify determinism (same seed -> same output)
make determinism

# 7. Run smoke test (mock LLM, no GPU needed)
make episodes-dry

# 8. Generate evidence pack artifacts
make evidence-pack
```

## Full Reproduction (GPU Required)

```bash
# Prerequisites: vLLM server running with target model
export VLLM_ENDPOINT=http://localhost:8013/v1

# Run full episode execution (requires GPU)
make episodes-full

# Rescore all episodes with strict evaluators
make rescore

# Run all experiments (EXP-A through EXP-F)
make experiments

# Generate paper numbers
make paper-numbers

# Or run everything in sequence:
make all
```

## Makefile Targets

| Target | GPU | Description | Time |
|--------|-----|-------------|------|
| `make validate` | No | Validate 25 CPG graphs + 239 conditional rules | <1 min |
| `make test` | No | Run 194 unit/integration tests | ~10 sec |
| `make derive` | No | Derive 453+ constraints from graphs | <1 min |
| `make generate` | No | Generate 250+ auto scenarios | <30 sec |
| `make determinism` | No | Verify pipeline determinism (3 runs) | ~2 min |
| `make episodes-dry` | No | Smoke test with mock LLM | ~1 min |
| `make audit` | No | Rule coverage + cross-reference audit | <1 min |
| `make evidence-pack` | No | Generate all evidence pack artifacts | ~5 min |
| `make episodes-full` | Yes | Full episode execution (all models) | ~5 days |
| `make rescore` | No | Rescore episodes with strict evaluators | ~30 min |
| `make experiments` | No | Run EXP-A through EXP-F | ~1 hour |
| `make paper-numbers` | No | Generate auto_numbers.tex | ~5 min |
| `make all` | No | Full analysis pipeline (no episodes) | ~15 min |

## Expected Outputs

After `make all`:
- `evidence_pack/rule_coverage_audit.yaml` — 25 graphs, 239 conditional rules
- `configs/scenarios/auto_generated_scenarios.yaml` — 250+ auto-generated scenarios
- `evidence_pack/tables/*.tex` — 50+ LaTeX tables for paper appendix
- `paper/auto_numbers.tex` — All paper numbers auto-generated

## Docker Alternative

```bash
# CPU-only (analysis + tests)
docker compose up scorer

# Inside container:
make all
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'cga_bench'"
Set `PYTHONPATH=.` before running scripts, or use `make` targets which set it automatically.

### "SKIP: episodes-full requires VLLM_ENDPOINT"
Full episode execution needs a running vLLM server. For analysis-only reproduction, use `make all` instead.

### Test failures in test_e2e
E2E tests may fail without episode data. Use `make test-fast` to skip slow/e2e tests.

## Hardware Used in Paper

- GPU: 4x NVIDIA H200 80GB (for Qwen3.5-397B) + 2x A100 80GB (for smaller models)
- CPU: AMD EPYC 7763 64-Core
- RAM: 512GB
- Storage: 2TB NVMe SSD
- Total episode execution time: ~5.4 days (4 GPU parallel)
