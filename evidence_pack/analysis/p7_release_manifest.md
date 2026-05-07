# P7: CGA-Bench Release Package Manifest

**Built**: 2026-04-02T03:43:28.395848+00:00
**Total files**: 339
**Anonymized**: 6
**Package size**: 2.72 MB
**PII clean**: YES

## Module File Counts

| Module | Files |
|--------|------:|
| `agent_rules` | 13 |
| `agent_runner` | 7 |
| `assessor_core` | 16 |
| `configs/agents` | 24 |
| `configs/domain_registry.yaml` | 1 |
| `configs/experiments` | 14 |
| `configs/scenarios` | 16 |
| `cpg_engine` | 7 |
| `cpg_model` | 23 |
| `env` | 17 |
| `eval_harness` | 22 |
| `scenario_engine` | 3 |
| `tests/test_agent_rules` | 7 |
| `tests/test_agents` | 3 |
| `tests/test_assessor` | 19 |
| `tests/test_conformance` | 10 |
| `tests/test_correctness` | 6 |
| `tests/test_e2e` | 9 |
| `tests/test_engine` | 7 |
| `tests/test_golden` | 87 |
| `tests/test_isolation` | 2 |
| `tests/test_normalizer` | 2 |
| `tests/test_reproducibility` | 3 |
| `tests/test_schemas` | 2 |
| `tool_api` | 2 |

## Generated Files

- `README.md`
- `LICENSE`
- `pyproject.toml`
- `requirements.txt`
- `.gitignore`

## Excluded from Release

- results/ (experiment results with model outputs)
- evidence_pack/ (analysis artifacts)
- paper_sections/ (LaTeX source)
- paper/ (paper draft)
- docs/ (internal documentation)
- data/ (MIMIC-IV demo data)
- clinician_validation/ (survey materials)
- semantic_layer/ (external benchmark adapters)
- history/ (legacy code)
- reports/ (internal reports)
- .claude/ .omc/ .sisyphus/ (tool configs)
- run_external_benchmark.py (external eval, not core)
- run_eval_science_llm.py (internal experiment)

## Availability Statement (for paper)

> Code, scenario definitions, and constraint specifications are available at [anonymous URL]. The evaluation pipeline is deterministic and fully reproducible with fixed random seeds. All 14 CPG graph definitions, 15+ clinical scenarios, and 3,000+ unit tests are included. Licensed under the MIT License.

## Verification Commands

```bash
# Install from release
cd cga-bench-release
pip install -e '.[dev]'

# Run tests
PYTHONPATH=. pytest tests/ -v

# Run a scenario with mock LLM
PYTHONPATH=. python run_benchmark.py --scenario septic_shock_basic --agent oracle --mock-llm

# Verify no PII
grep -rn '<author-given-names>\|<author-handles>\|<author-paths>\|/home/\\w+' . --include='*.py' --include='*.yaml' --include='*.md'
```