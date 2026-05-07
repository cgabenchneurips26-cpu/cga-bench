# Expansion Session TODO — 2026-04-23 (Updated 07:39 UTC / resume)

## Current State

### YAML Graph Generation

| Batch | Score Range | Graphs Done | Script | Status |
|-------|------------|-------------|--------|--------|
| batch1 (orig) | 19-18 | 16 | `generate_expansion_graphs.py` | DONE |
| batch1 +5 | 17 partial | 5 | `generate_expansion_graphs.py` (registered) | DONE |
| batch2 | 17 remaining | 10 | `generate_expansion_graphs_batch2.py` | DONE |
| batch3 | 16 | 0/14 target | `generate_expansion_graphs_batch3.py` | **NOT CREATED** |
| batch4 | 15 | 0/14 target | `generate_expansion_graphs_batch4.py` | **NOT CREATED** |

**Current auto YAMLs: 31/59 target**
**Current auto scenarios: 124 (31 graphs x 4)**
**Missing: 28 graphs (14 score-16 + 14 score-15)**

### Batch3/4 Agent Status

Previous agents hit `max_output_tokens` (32K) writing full 6-8 node builders.
**Resume (07:39 UTC)**: Launched 2 parallel Opus executor agents with strict **3-node minimal** builder template (initial_assessment → primary_treatment → monitoring, ~100 lines each). In progress.

### Score-16 CPGs Needing YAML (batch3 — 14 graphs)

From `reports/cpg_scores_v2_full_124.json`, these score-16 CPGs need builder functions:

1. `aagbi_perioperative_hemorrhage_2016`
2. `acs_colorectal_cancer_2021`
3. `aha_acc_peripheral_artery_disease_2024`
4. `btf_severe_tbi_2020`
5. `eacts_aortic_valve_2021`
6. `eanm_esc_cardiac_amyloidosis_2023`
7. `esc_acute_coronary_syndrome_2023`
8. `esc_infective_endocarditis_2023`
9. `esge_acute_lower_gi_bleed_2021`
10. `eucast_antimicrobial_susceptibility_2024`
11. `ilcor_neonatal_resuscitation_2020`
12. `nsclc_molecular_testing_2023`
13. `sign_acute_coronary_syndrome_2023`
14. `wses_acute_appendicitis_2020`

### Score-15 CPGs Needing YAML (batch4 — 14 graphs)

1. `acc_aha_valvular_heart_disease_2020`
2. `acg_peptic_ulcer_bleed_2021`
3. `acs_pancreatic_cancer_2021`
4. `aha_acc_coronary_revascularization_2021`
5. `asco_breast_cancer_adjuvant_2024`
6. `asco_lung_cancer_screening_2023`
7. `bts_community_pneumonia_2009`
8. `eaaci_drug_allergy_2022`
9. `eacts_esc_myocardial_revascularization_2024`
10. `esc_hcm_2024`
11. `esmo_gastric_cancer_2022`
12. `nccn_melanoma_2024`
13. `who_hiv_2023`
14. `wses_perforated_peptic_ulcer_2020`

---

## GPU Episode Runners (ACTIVE — concurrent workers)

All 11 runners were restarted at 07:18 KST with `--workers N` (ThreadPoolExecutor).

| # | Endpoint | Model | PID | Workers | Done | Target | Log |
|---|----------|-------|-----|---------|------|--------|-----|
| 1 | 145:30005 | oss-120b | 140471 | 10 | ~12 | 372 | `/tmp/expansion_oss120b_w10.log` |
| 2 | 145:30015 | oss-120b | 140472 | 10 | ~12 | 372 | `/tmp/expansion_oss120b_exp2_w10.log` |
| 3 | 145:30025 | oss-120b | 140473 | 10 | ~12 | 372 | `/tmp/expansion_oss120b_exp3_w10.log` |
| 4 | 145:30039 | DeepSeek-R1-7B | 140474 | 20 | ~5 | 372 | `/tmp/expansion_deepseek_exp1_w20.log` |
| 5 | 145:30049 | DeepSeek-R1-7B | 140475 | 20 | ~4 | 372 | `/tmp/expansion_deepseek_exp2_w20.log` |
| 6 | 144:30001 | Qwen3.5-397B | 140476 | 6 | ~12 | 372 | `/tmp/expansion_qwen397b_w6.log` |
| 7 | 144:30002 | Qwen3.5-397B-S2 | 140477 | 6 | ~12 | 372 | `/tmp/expansion_qwen397b_s2_w6.log` |
| 8 | 146:28002 | Qwen3.5-9B | 140478 | 16 | ~8 | 372 | `/tmp/expansion_qwen9b_w16.log` |
| 9 | 146:28003 | Qwen3.5-35B-A3B | 140479 | 12 | ~10 | 372 | `/tmp/expansion_qwen35b_a3b_w12.log` |
| 10 | 146:30059 | DeepSeek-R1-7B | 140480 | 20 | ~0 | 372 | `/tmp/expansion_deepseek_local1_w20.log` |
| 11 | 146:30069 | DeepSeek-R1-7B | 140481 | 20 | ~0 | 372 | `/tmp/expansion_deepseek_local2_w20.log` |

**Total target: 11 runners x 372 episodes = 4,092 episodes**
**Output: `results/expansion_v7/`**
**Runner script: `scripts/experiments/expansion_runner.py`**
**Shared log: `/tmp/expansion_runner_20260423_071833.log`**

### Known Issues

1. ~~**`aha_asa_ich_2022` graph has schema errors**~~ **FIXED 07:37 UTC.** ICH failures went to OK at 07:38+. Bulk-audited all 31 auto/ graphs: 17 string-valued `required_prior_actions` (wrapped to lists) + 19 `conditional_rules` missing `evidence` (defaulted from node's recommendation_class/evidence_level). 23 files updated in-place. `_node()` helper in `generate_expansion_graphs.py` now auto-wraps strings → lists as defense-in-depth. Broader schema audit: 0 remaining issues across all 31 YAMLs.

2. **RAG corpus loading is slow with many workers** — ~3.5 min for 100+ threads to load 868 documents. First episodes take long to start.

3. **DeepSeek-R1-7B JSON repair failures** — Expected for 7B reasoning model. Runner continues with failures logged.

4. **Low scores on auto-graphs (score≈0.0)** — Many episodes return score=0.000, indicating agents aren't earning CPG credit on the new graphs. Separate quality issue from schema. Investigate after batch3/4 land.

### Infrastructure

- **145**: 8x A100 80GB, 5 vLLM processes (3x oss-120b TP=2, 2x DeepSeek-7B TP=1)
- **144**: 8x H200 143GB, 2 vLLM processes (2x Qwen3.5-397B TP=4) — READ-ONLY, don't restart
- **146 (local)**: 8x A100 80GB
  - GPU 0: Qwen3.5-2B (port 28001, docker)
  - GPU 1: Qwen3.5-9B (port 28002, docker) + embeddings
  - GPU 2: Qwen3.5-35B-A3B (port 28003, anonymous-user)
  - GPU 3: Qwen3.5-27B (port 28088, docker)
  - GPU 4: Llama-3.2-3B (port 28005, docker)
  - GPU 5: Nemotron-3-Nano-30B (port 28006, docker)
  - GPU 6: DeepSeek-R1-7B (port 30059, research user)
  - GPU 7: DeepSeek-R1-7B (port 30069, research user)
- **SSH**: `sudo -u anonymous-org ssh 127.0.0.1 `sudo -u anonymous-org ssh [email-redacted]`

---

## TODO (in priority order)

### 1. CRITICAL: Create batch3.py and batch4.py

Both agent attempts failed due to `max_output_tokens`. Create manually:

```bash
# Pattern: follow generate_expansion_graphs_batch2.py exactly
# Each batch file needs:
#   - Import _node, validate_graph, write_graph, OUTPUT_DIR from batch1
#   - 14 builder functions (one per CPG)
#   - GRAPH_BUILDERS dict mapping short_name -> builder function
#   - main() that calls each builder, validates, writes YAML

# Use this template for each builder:
# def build_<short_name>_graph() -> dict[str, Any]:
#     src = "<Society Full Name Year>"
#     doi = "<DOI>"
#     nodes: dict[str, Any] = {}
#     nodes["initial_assessment"] = _node(...)
#     ...
#     return { "graph_id": "<graph_id>", ... }
```

After creation:
```bash
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench

# Generate YAML graphs
PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch3.py
PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch4.py

# Validate
PYTHONPATH=. python scripts/ci/validate_cpg_schema.py --dir cpg_model/graphs/auto/

# Generate scenarios for ALL auto graphs
PYTHONPATH=. python scripts/generate_scenarios_from_cpg.py \
  --graphs-dir cpg_model/graphs/auto/ \
  --output-dir configs/scenarios/auto/
```

### 2. Fix aha_asa_ich_2022 graph schema errors

File: `cpg_model/graphs/auto/aha_asa_ich_2022.yaml`

Errors:
- `required_prior_actions.give_pcc_4factor`: Change from string `"order_lab_inr"` to list `["order_lab_inr"]`
- `conditional_rules[0..2]`: Add missing `evidence` field to each rule (e.g., `evidence: "Class I, Level B"`)

### 3. Restart runners after new graphs

When batch3/4 graphs + scenarios are generated:

```bash
# Kill all runners
kill $(ps aux | grep "expansion_runner.py" | grep -v grep | awk '{print $2}')

# Wait 5 seconds
sleep 5

# Restart all 11 runners (they skip completed episodes via checkpoint)
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench

PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py oss120b --host 127.0.0.1 --port 30005 --workers 10 > /tmp/expansion_oss120b_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py oss120b_exp2 --host 127.0.0.1 --port 30015 --workers 10 > /tmp/expansion_oss120b_exp2_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py oss120b_exp3 --host 127.0.0.1 --port 30025 --workers 10 > /tmp/expansion_oss120b_exp3_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py deepseek_r1_7b_exp1 --host 127.0.0.1 --port 30039 --workers 20 > /tmp/expansion_deepseek_exp1_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py deepseek_r1_7b_exp2 --host 127.0.0.1 --port 30049 --workers 20 > /tmp/expansion_deepseek_exp2_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py qwen397b --host 127.0.0.1 --port 30001 --workers 6 > /tmp/expansion_qwen397b_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py qwen397b_react_s2 --host 127.0.0.1 --port 30002 --workers 6 > /tmp/expansion_qwen397b_s2_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py qwen9b --host localhost --port 28002 --workers 16 > /tmp/expansion_qwen9b_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py qwen35b_a3b_local --host localhost --port 28003 --workers 12 > /tmp/expansion_qwen35b_a3b_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py deepseek_r1_7b_local1 --host localhost --port 30059 --workers 20 > /tmp/expansion_deepseek_local1_r3.log 2>&1 &
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject nohup python scripts/experiments/expansion_runner.py deepseek_r1_7b_local2 --host localhost --port 30069 --workers 20 > /tmp/expansion_deepseek_local2_r3.log 2>&1 &
```

### 4. Queue additional models

Models with idle vLLM on 146 (already serving):

| Model | Port | GPU | Config | Workers |
|-------|------|-----|--------|---------|
| Qwen3.5-27B | 28088 | 3 | Need new config | 12 |
| Nemotron-3-Nano-30B | 28006 | 5 | `clean_slate_nemotron30b.yaml` | 12 |
| Llama-3.2-3B | 28005 | 4 | Need new config | 32 |
| Qwen3.5-2B | 28001 | 0 | Need new config | 32 |

To add a new model:
1. Create `configs/agents/clean_slate_<model>_local.yaml` with correct `llm_model` matching served name
2. Add entry in `scripts/experiments/full_690_runner.py` MODELS dict
3. Launch: `PYTHONPATH=... nohup python scripts/experiments/expansion_runner.py <key> --workers N > /tmp/... 2>&1 &`

**Check served model names**: `curl -s -H "Authorization: Bearer sk-no-key-required" http://localhost:<PORT>/v1/models`

### 5. Git commit

```bash
git add scripts/experiments/expansion_runner.py \
       scripts/cpg_v2_phase3/generate_expansion_graphs_batch2.py \
       scripts/cpg_v2_phase3/generate_expansion_graphs.py \
       scripts/experiments/full_690_runner.py \
       eval_harness/scenario_loader.py \
       cpg_model/graphs/auto/ \
       configs/scenarios/auto/ \
       configs/agents/clean_slate_qwen9b.yaml \
       configs/agents/clean_slate_qwen35b_a3b_local.yaml \
       docs/cpg_expansion_v7/TODO_expansion_session.md

git commit -m "feat(expansion): 31 auto YAML graphs + concurrent runner + 11 GPU endpoints"
```

### 6. Analysis preparation

After all episodes complete:
```bash
PYTHONPATH=. python scripts/experiments/aggregate_expansion.py results/expansion_v7/
```

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/experiments/expansion_runner.py` | Auto-only episode runner with `--workers N` concurrency |
| `scripts/cpg_v2_phase3/generate_expansion_graphs.py` | Batch1: 21 builder functions (16 orig + 5 score-17) |
| `scripts/cpg_v2_phase3/generate_expansion_graphs_batch2.py` | Batch2: 10 score-17 builders |
| `scripts/generate_scenarios_from_cpg.py` | Scenario generator from YAML graphs |
| `scripts/ci/validate_cpg_schema.py` | YAML graph schema validator |
| `eval_harness/scenario_loader.py` | Modified to scan `auto/` subdirectories |
| `scripts/experiments/full_690_runner.py` | MODELS registry (all 14 model entries) |
| `results/expansion_v7/` | Episode results (separate from core 706) |
| `configs/scenarios/auto/` | Auto-generated scenarios (31 files, 124 scenarios) |
| `cpg_model/graphs/auto/` | Auto-generated CPG graphs (31 files) |
| `reports/cpg_scores_v2_full_124.json` | Full CPG census with C1-C12 scores |
