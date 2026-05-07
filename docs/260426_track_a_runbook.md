# Track A v3 Cataloguer Runbook

> **Purpose**: Step-by-step guide for running a 3rd (or 4th) LLM-family cataloguer extraction to verify the paper's pillar 3 ratio (5.50× Qwen v1 / 5.60× gpt-oss v2).
> **Owner**: Track A — extending Pose-B catalogue replication to a 3rd LLM family.
> **Prerequisites**: GPU window (currently saturated by `anonymous-user`'s full_v6b run, ETA TBD).

---

## When to Run

Use this runbook when:
1. GPU 145 has free memory for a new vLLM endpoint (≥ 60 GB on at least 2 GPUs at FP8, or 1 GPU for ≤30B FP8 models)
2. `anonymous-user` confirms full_v6b run can spare an endpoint, or full_v6b has completed
3. A new LLM family (not Qwen, not OpenAI gpt-oss) is approved for cataloguing

## Recommended LLM Family Candidates

| Model | Family | Local cache (145) | TP | VRAM (FP8) | Comment |
|---|---|---|---|---|---|
| **Gemma-4-31B-IT** | Google | ✅ already downloaded | 1 | ~32 GB | Distinct family, smallest setup |
| **Llama-4-Scout-17B-16E** | Meta | ✅ already downloaded | 1 | ~36 GB (MoE) | Distinct family, MoE architecture |
| **Nemotron-3-Nano-30B** | NVIDIA | ✅ already downloaded | 1 | ~32 GB | Distinct family |

Choose based on family-diversity argument strength. Gemma-4-31B is the fastest deploy (1 GPU, single-shard).

---

## Phase 1 — Endpoint Deployment (operator: human or anonymous-user)

### Pre-flight

```bash
# Confirm GPU memory available
sudo -u anonymous-org ssh 127.0.0.1 "nvidia-smi --query-gpu=index,memory.free --format=csv,noheader"
# Need at least 1 GPU with > 35 GB free (or 2 GPUs with > 35 GB each for TP=2)
```

### Launch (example: Gemma-4-31B-IT on port 30030)

```bash
sudo -u anonymous-org ssh 127.0.0.1
docker run -d --rm \
    --gpus '"device=N"' \
    --name vllm-gemma4-track-a \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -p 30030:8000 \
    vllm/vllm-openai:latest \
    --model google/gemma-4-31b-it \
    --port 8000 \
    --tensor-parallel-size 1 \
    --max-model-len 8192 \
    --max-num-seqs 256 \
    --gpu-memory-utilization 0.92 \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --api-key sk-no-key-required
```

(Substitute `device=N` with the free GPU index. Per `.claude/rules/vllm-launch.md` — five standard options preserved.)

### Verify endpoint live

```bash
curl -s -H "Authorization: Bearer sk-no-key-required" \
    http://localhost:8013/v1/models | jq '.data[].id'
# Expected: "google/gemma-4-31b-it"
```

---

## Phase 2 — Catalogue Extraction (operator: anyone with PYTHONPATH)

### Smoke test (1 CPG, ~30s)

```bash
PY=/home/anonymous-org/anaconda3/bin/python3.13
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject:/home/anonymous-org/anonymous-project/AnonProject/cga_bench

$PY scripts/experiments/exp_cde_vs_llm_v3.py \
    --endpoint http://localhost:8013/v1/chat/completions \
    --model google/gemma-4-31b-it \
    --output-suffix v3_gemma \
    --limit 1
```

Expected: 1 file `evidence_pack/constraint_comparison/llm_raw_v3_gemma/<CPG>.json` with ≥ 5 constraints.

### Full extraction (25 CPGs, 1-2 hours)

```bash
$PY scripts/experiments/exp_cde_vs_llm_v3.py \
    --endpoint http://localhost:8013/v1/chat/completions \
    --model google/gemma-4-31b-it \
    --output-suffix v3_gemma
```

Expected outputs:
- `evidence_pack/constraint_comparison/llm_raw_v3_gemma/*.json` (25 files)
- `evidence_pack/constraint_comparison/llm_summary_v3_gemma.json`
- `evidence_pack/constraint_comparison/compare_summary_v3_gemma.json`
- `evidence_pack/constraint_comparison/macros_v3_gemma.tex`

### Recovery (if some CPGs failed JSON parsing)

If errors logged in `llm_summary_v3_gemma.json`, look at v2 patterns for guidance:
- `exp_cde_vs_llm_v2_repair.py` — strict prompt + reasoning_effort=low for reasoning-mode models
- `exp_cde_vs_llm_v2_chunked.py` — 6000-char chunked recovery for very long CPGs

Mirror the same approach by editing `exp_cde_vs_llm_v3.py` if needed.

---

## Phase 3 — Main-Finding Replication (operator: anyone)

After catalogue is extracted (Phase 2 complete):

```bash
$PY scripts/experiments/exp_mainfinding_llm_replication_v3.py \
    --output-suffix v3_gemma \
    --catalogue-name "Gemma-4-31B"
```

Expected outputs:
- `evidence_pack/constraint_comparison/main_finding_full_replication_v3_gemma_results.json`
- `evidence_pack/constraint_comparison/main_finding_full_replication_v3_gemma_macros.tex`

Expected ratio band: **5.0–6.0×** if pillar 3 is genuinely cross-family robust. A ratio outside this band requires investigation.

---

## Phase 4 — Paper Integration (after Phase 3 succeeds)

1. Add the new macros file to `paper/auto_numbers.tex` or a similar load point:
   ```latex
   \input{../evidence_pack/constraint_comparison/main_finding_full_replication_v3_gemma_macros.tex}
   ```

2. Update `paper/appendix.tex` Phase 1.J subsection to add a row to the cross-LLM-family ratio table:
   - Add column or row showing Qwen v1 (5.50×), gpt-oss v2 (5.60×), Gemma-4 v3 (NEW), …

3. Recompile:
   ```bash
   cd paper && pdflatex -interaction=nonstopmode main_final_v17.tex && pdflatex -interaction=nonstopmode main_final_v17.tex
   ```

4. Verify all macros resolve and 55–58 page count maintained.

---

## Cleanup (after Phase 4)

```bash
# Stop the temporary endpoint
sudo -u anonymous-org ssh 127.0.0.1 "docker stop vllm-gemma4-track-a"
```

The cataloguer JSON outputs are persistent (committed to git). Only the live endpoint is ephemeral.

---

## Troubleshooting

### Endpoint returns Unauthorized

Set `--api-key` correctly on the cataloguer call. Default is `sk-no-key-required` (matches existing 144/145 endpoints).

### LLM returns prose instead of JSON

Models in reasoning mode (e.g., gpt-oss) sometimes put JSON in `reasoning` field instead of `content`. The v3 script's `_extract_constraint_list` handles the basic content path; extend with v2 patterns if needed (see `exp_cde_vs_llm_v2.py:_extract_constraint_list` for the full content/reasoning/tool_calls fallback).

### Catalogue too sparse (< 20 CPGs)

`exp_mainfinding_llm_replication_v3.py` warns when `n_cpgs < 20`. Re-run extraction with `--force` to retry failed CPGs, or consult v2 chunked recovery script.

### Ratio outside 5.0–6.0× band

- Below 4×: catalogue may be too STRICT (high MUST-coverage threshold). Compare per-family pass rates against v1/v2 anchors (LlmCwt should pass ~70%, LlmPaf ~91%).
- Above 7×: catalogue may be too LENIENT (low MUST count, false-accept dominant). Inspect a sample CPG output to confirm constraint quality.

---

## File map

| File | Purpose |
|---|---|
| `scripts/experiments/exp_cde_vs_llm_v3.py` | Generic v3 cataloguer (any endpoint+model) |
| `scripts/experiments/exp_mainfinding_llm_replication_v3.py` | Generic v3 main-finding replication |
| `scripts/experiments/exp_cde_vs_llm.py` (v1) | Source of `SYSTEM_PROMPT`, `_build_user_prompt`, `_parse_parsed_json` |
| `scripts/experiments/exp_cde_vs_llm_v2.py` (v2) | Reference for reasoning-mode parsing |
| `scripts/experiments/exp_cde_vs_llm_v2_chunked.py` | Reference for chunked recovery on long CPGs |
| `audit/shims/llm_catalogue_shim.py` | Catalogue loader (monkey-patched at runtime) |
| `audit/shims/llm_family_shims.py` | LlmAsc / LlmCwt / LlmPaf shims used by main-finding script |

---

*Last updated: 2026-04-26 — Track A infrastructure ready, pending GPU window for execution.*
