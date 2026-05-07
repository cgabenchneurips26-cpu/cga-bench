# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CGA-Bench (Clinical Guideline Adherence Benchmark) evaluates how well LLM agents adhere to time-sensitive clinical treatment protocols from medical guidelines (CPGs). The benchmark prevents "evaluation leakage" through strict separation between scoring and agent-accessible components.

## Important: Known Issues

Before adding new scenarios, models, or external benchmarks, read [KNOWN_ISSUES.md](./KNOWN_ISSUES.md) for recurring problem patterns and checklists.

## Important: Paper Number Traceability

Before modifying any experiment script, macro, or evidence_pack file, read [docs/PAPER_TRACEABILITY.md](./docs/PAPER_TRACEABILITY.md). It maps every TeX macro in `auto_numbers.tex` back to its generator script and JSON source, documents the full `\input` chain, and lists 4 missing generator scripts whose values are hardcoded.

## Common Development Commands

### Running Benchmarks
```bash
# Single scenario with specific agent
python run_benchmark.py --scenario septic_shock_basic --agent rag_gpt4

# Run full experiment
python run_benchmark.py --experiment sepsis_benchmark

# Test run with mock LLM (no API calls)
python run_benchmark.py --scenario stemi_inferior_rv_trap --agent rag_gpt4 --mock-llm

# List available scenarios, agents, experiments
python run_benchmark.py --list-scenarios
python run_benchmark.py --list-agents
python run_benchmark.py --list-experiments

# Run external benchmark evaluation
python run_external_benchmark.py --benchmark agentclinic --agent llm_assist --limit 10
python run_external_benchmark.py --benchmark agentclinic --llm-model "Qwen/Qwen3-30B" --llm-backend vllm --llm-endpoint "http://localhost:8013/v1"
```

### Running Full Benchmark (706 scenarios × 8 models × 3 runs)
```bash
# Single model (available: oss120b, qwen35b, qwen27b, qwen4b, qwen397b, gemma31b, nemotron30b, deepseek_r1_7b)
PYTHONPATH=${CGA_BENCH_ROOT} \
  python scripts/experiments/full_690_runner.py oss120b results/full_706_v5

# Shard runner (second-half scenarios on alternate GPU/port)
PYTHONPATH=${CGA_BENCH_ROOT} \
  python scripts/experiments/shard_runner.py qwen4b_s2 8102 results/full_706_v5

# Dry run (1 scenario × 1 run)
PYTHONPATH=${CGA_BENCH_ROOT} \
  python scripts/experiments/full_690_runner.py oss120b --dry-run

# Diagnose LLM response issues (captures raw responses)
PYTHONPATH=${CGA_BENCH_ROOT} \
  python scripts/diagnose_llm_response.py qwen35b
```

### Running Tests (3185+ tests, 24 categories)
```bash
# Run all tests (from cga_bench directory)
PYTHONPATH=. pytest tests/ -v

# Run specific test categories
PYTHONPATH=. pytest tests/test_e2e/
PYTHONPATH=. pytest tests/test_agents/
PYTHONPATH=. pytest tests/test_assessor/
PYTHONPATH=. pytest tests/test_engine/
PYTHONPATH=. pytest tests/test_golden/
PYTHONPATH=. pytest tests/test_isolation/
PYTHONPATH=. pytest tests/test_schemas/
PYTHONPATH=. pytest tests/test_integration/
PYTHONPATH=. pytest tests/test_exit_criteria/
PYTHONPATH=. pytest tests/test_experiments/

# Run single test file or function
PYTHONPATH=. pytest tests/test_e2e/test_septic_shock_e2e.py -v
PYTHONPATH=. pytest tests/test_engine/test_ssc_sepsis.py::test_function_name -v
```

---

## Architecture: Scoring-Agent Separation

The system enforces strict separation between scoring (server-side only) and agent (agent-accessible) components to prevent cheating. This is a core design principle addressing NeurIPS reviewer concerns about evaluation leakage.

### SCORING SYSTEM (Agent Access Forbidden)
- `assessor_core/` - Violation detection (`ViolationExtractor`) and harm scoring (`HarmScorer`)
- `cpg_engine/` - CPG graph evaluation engine with core interface: `G(s_t) -> (A_G, M_G, F_G, D_G)`
- `cpg_model/graphs/` - CPG graph definitions in YAML format

### AGENT SYSTEM (Agent Accessible)
- `agent_runner/` - Agent implementations (RAG, Planner, Reflection, Oracle)
- `agent_rules/` - Independent rule system for Oracle agent (uses `decision_table.py`, **never** cpg_engine)
- `tool_api/` - Scenario API (labs, medications, imaging)
- `scenario_engine/` - Clinical simulation environment

### Shared (Limited Access)
- `cpg_model/schemas/base.py` - Core data types: `Action`, `PatientState`, `VitalSigns`, `LabResult`, `EpisodeLog`
- `eval_harness/` - Experiment runner, scenario/agent loaders, budget enforcement, fairness verification

---

## Violation Types

OMISSION, COMMISSION, TIMING, SEQUENCE, DEVIATION (details in `cpg_model/schemas/base.py`)

---

## Verification Commands

```bash
# Verify agents don't access forbidden modules
grep -r "from cga_bench.cpg_engine" agent_runner/oracle_agent.py  # Should be empty
grep -r "from cga_bench.assessor_core" agent_runner/rag_agent.py  # Should be empty
grep -r "from cga_bench.cpg_engine" agent_rules/                  # Should be empty

# Verify independence at runtime
python -c "from cga_bench.agent_runner.oracle_agent import OracleAgent; print(OracleAgent(OracleConfig()).get_independence_verification())"
```

---

## Environment Variables

```bash
PYTHONPATH=.                    # Required for module imports
OPENAI_API_KEY=<key>           # For OpenAI-based agents
ANTHROPIC_API_KEY=<key>        # For Anthropic-based agents

# vLLM Configuration (local)
VLLM_ENDPOINT=http://localhost:8013/v1
VLLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507

# Active external endpoints (2026-05-01)
# Qwen3.5-397B instance 1: http://localhost:8013/v1
# Qwen3.5-397B instance 2: http://localhost:8013/v1
# API key for all: sk-no-key-required
# Full vLLM ops reference: docs/vllm_ops_knowhow.md
# Claude rules reference:  .claude/rules/vllm-launch.md
```

---

## Design Principles

1. **No Hardcoded Defaults** - All config values must be explicitly injected via `*Config` dataclasses
2. **Source Traceability** - Every rule references original guideline (`source_guideline`, `source_section`, `evidence_level`)
3. **Action-Centric** - Agents output structured `Action` objects, not free-text responses
4. **Scoring-Agent Separation** - Agents cannot access scoring modules (cpg_engine, assessor_core)
5. **Budget-Matched Evaluation** - All agents evaluated with identical inference budgets
6. **Independent Oracle** - Oracle uses separately implemented rules, never cpg_engine

## vLLM Infrastructure & Operations

Full operational knowhow (server infra, launch/stop, model configs, troubleshooting):
- **Detailed guide**: [`docs/vllm_ops_knowhow.md`](./docs/vllm_ops_knowhow.md)
- **Claude rules**: [`.claude/rules/vllm-launch.md`](./.claude/rules/vllm-launch.md)

Servers: 144 (H200x8, `[email-redacted]`), 145 (A100x8, `127.0.0.1 146 (orchestrator).
Current active: `Qwen/Qwen3.5-397B-A17B-FP8` on 144 ports 30001/30002 (TP=4 each, API key `sk-no-key-required`).

---

## Critical: Qwen Prompt Sensitivity

Qwen models interpret instructions more literally than oss120b. Key rules:
- **Never say "mandatory FIRST, then optional"** without also saying "Do NOT return empty actions"
- After mandatory actions, the prompt MUST explicitly instruct the model to continue with optional actions
- The instruction "A stable patient still needs: serial vitals, trending labs, secondary workup" is **load-bearing** for Qwen models
- See `KNOWN_ISSUES.md` §1-5 for full diagnosis and before/after metrics
- See `KNOWN_ISSUES.md` §1-6 for Bug 6: rule-based fallback masking LLM empty loop (extreme value scenarios)
- Verify any prompt change with `scripts/diagnose_llm_response.py` on aabb_t scenario
