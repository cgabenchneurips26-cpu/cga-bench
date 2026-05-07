# Hardware Requirements — CGA-Bench

*Part of the NeurIPS D&B reproducibility checklist (Item D5).*

This document records the hardware profile used to produce the v6.0 results and the
minimum configuration needed to re-run the benchmark. The benchmark itself is
**inference-only** (no gradient training), so requirements are dominated by the
selected agent LLM.

---

## 1. Tiers of Reproduction

| Tier | What you reproduce | Hardware needed |
|---|---|---|
| T1 — metrics only | Recompute paper numbers from committed `results/full_706_v5/*.json` episode traces | 1 CPU core, 8 GB RAM, ~5 GB disk |
| T2 — scorer / ablations | Re-score existing episodes with new scorers or ablations (`scripts/ablations/*.py`, `scripts/experiments/exp_x*.py`) | 4 CPU cores, 16 GB RAM, ~50 GB disk |
| T3 — single model re-benchmark | Re-run the 706-scenario × 3-run sweep for one model via its vLLM endpoint | Depends on model (see §3) |
| T4 — full 8-model benchmark | Reproduce the full 8-model × 706-scenario × 3-run matrix | Aggregate of §3 rows |

Most readers will only need T1 or T2. T1/T2 run comfortably on a laptop; T3/T4
require GPU-backed inference servers.

---

## 2. Software Prerequisites

| Component | Version | Notes |
|---|---|---|
| Python | 3.11+ | Tested on 3.11 and 3.13 |
| CUDA | 12.1+ | Required only for vLLM backends |
| vLLM | 0.5.0+ | For T3/T4 |
| System packages | `ruff`, `mypy`, `pytest` for dev | `pip install -e ".[dev]"` |

Exact pinned Python dependencies: `requirements.lock`.

---

## 3. Per-Model Inference Cost (v6.0 production run)

| Model | Parameters | Quantization | Minimum VRAM | Recommended GPU | vLLM flags (canonical) |
|---|---|---|---|---|---|
| `deepseek_r1_7b` | 7 B | BF16 | 20 GB | 1× A100 40 GB / A10 24 GB | `--tensor-parallel-size 1 --max-model-len 16384` |
| `qwen4b` | 4 B | BF16 | 12 GB | 1× A10 24 GB | `--tensor-parallel-size 1` |
| `qwen27b` | 27 B | BF16 | 64 GB | 2× A100 40 GB | `--tensor-parallel-size 2` |
| `qwen35b` | 35 B | BF16 | 80 GB | 2× A100 40 GB | `--tensor-parallel-size 2` |
| `gemma31b` | 31 B | FP8 | 48 GB | 1× A100 80 GB | `--tensor-parallel-size 1 --max-model-len 16384` |
| `nemotron30b` | 30 B | FP8 | 48 GB | 4× A100 40 GB (as deployed) | `--tensor-parallel-size 4 --max-model-len 16384` |
| `oss120b` | 120 B | FP8 | 160 GB | 4× H100 80 GB | `--tensor-parallel-size 4 --max-model-len 16384` |
| `qwen397b` | 397 B | FP8 | ≥ 512 GB | 8× H100 80 GB | `--tensor-parallel-size 8 --max-model-len 16384` |

Numbers reflect the production deployment used for v6.0 release data. Alternative
configurations (higher quantization, MoE offload, etc.) can reduce VRAM at the cost
of inference throughput.

---

## 4. Inference-Time Resource Use

Per scenario, the agent issues 15–30 tool calls on average. Token budgets per
scenario (used by the `BudgetMatchedExperimentConfig`):

| Metric | Typical range |
|---|---|
| Prompt tokens per step | 1,500–3,000 |
| Generation tokens per step | 200–600 |
| Total tokens per scenario (single run) | 40k–120k |
| Wall-clock per scenario (single run, 1× A100) | 60–240 s |

Full 706-scenario × 3-run sweep for one model:
- **Small models (≤ 7 B)**: ~8–20 GPU-hours.
- **Medium models (30 B class)**: ~40–80 GPU-hours.
- **Large models (120 B+)**: ~200–400 GPU-hours.

---

## 5. Storage

| Artefact | Size |
|---|---|
| Source repository (`.git` excluded) | ~ 500 MB |
| `results/full_706_v5/` (episodes, 8 models × 3 runs) | ~ 12 GB |
| `evidence_pack/` (aggregated analyses + figures) | ~ 1 GB |
| `_archive/` (historical logs, optional) | ~ 142 MB |
| Zenodo deposit (tar-gz, camera-ready) | ~ 3 GB (compressed) |

Total workstation footprint for T2 reproduction: ~15 GB.

---

## 6. Minimum Laptop Profile

For readers who only need to reproduce paper numbers (T1) or run scorer ablations
(T2):

- **CPU**: any x86_64, 4 cores.
- **RAM**: 16 GB.
- **Disk**: 20 GB free.
- **GPU**: not required.
- **OS**: Linux (tested), macOS (should work), Windows WSL2 (untested).

The CI runs (`pytest tests/`) complete in roughly 10 minutes on this profile.

---

## 7. HPC / Cloud Notes

The production run used a mixed cluster of institutional A100 and H100 nodes
reached over internal SSH. For public reproduction, the canonical path is:

1. Provision a single-node GPU VM (e.g., AWS `p4d.24xlarge`, GCP `a3-highgpu-8g`).
2. Launch the target model via `vllm.entrypoints.openai.api_server` with the flags
   from §3.
3. Point `VLLM_ENDPOINT` at the server's `/v1` endpoint.
4. Run `python scripts/experiments/full_690_runner.py <model> results/<dir>`.

---

## 8. Energy Considerations

We encourage reproducers to declare GPU-hours spent and report approximate
energy footprint. A useful rule-of-thumb:

- 1 H100-hour ≈ 0.7 kWh (including host overhead) at ~ 70% utilisation.
- 1 A100-hour ≈ 0.3–0.4 kWh under similar assumptions.

For the full 8-model v6.0 production run we estimate ~ 3,500 GPU-hours equivalent
(dominated by the 397B model), i.e., ~ 1.8 MWh at the rule-of-thumb rate.
Publishing this figure is encouraged as part of the Responsible AI culture around
LLM benchmarking.

---

*End of hardware requirements.*
