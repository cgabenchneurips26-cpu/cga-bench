# CGA-Bench Reproducibility Audit Checklist

This document records provenance for all experiments reported in the paper,
enabling independent verification of every reported number.

---

## 1. Main Experiment: full_706_v6 (paper baseline)

| Field | Value |
|-------|-------|
| Episodes | 16,944 (8 complete models x 706 scenarios x 3 runs) |
| Results dir | `results/full_706_v6_*/{model}/` |
| Runner script | `scripts/experiments/full_690_runner.py` |
| Dedup key | `{model}_{scenario_id}_{run_index}` |
| Random seed | Per-episode: `run_index` (0, 1, 2) |
| LLM temperature | 0.1 (greedy-ish) for all models |
| Scaffold | ReAct (default) |
| PYTHONPATH | `${CGA_BENCH_ROOT}` |

### Complete models (8)

| Model key | Label | vLLM port | TP | Approx params |
|-----------|-------|-----------|----|---------------|
| oss120b | OSS-120B | 28000 | 2 | 120B |
| qwen27b | Qwen3.5-27B | 28010 | 2 | 27B |
| qwen35b | Qwen3.5-35B-A3B | 8013 | 2 | 35B (MoE) |
| qwen4b | Qwen3-4B | 8101 | 1 | 4B |
| qwen397b | Qwen3-397B | 8111 | 2 | 397B (MoE) |
| gemma31b | Gemma-31B-IT | 8201 | 2 | 31B |
| nemotron30b | Nemotron-30B | 8301 | 2 | 30B |
| deepseek_r1_7b | DeepSeek-R1-Distill-7B | 8401 | 1 | 7B |

### Historical predecessor (v5, archived)

v5 was 14,826 episodes / 7 models (excluded `deepseek_r1_7b`). v6 added the
8th model and rebaselines the paper. See `docs/RESULT_LINEAGE_AUDIT.md`.

---

## 2. W8 Scaffold-Independence Experiment

| Field | Value |
|-------|-------|
| Episodes | 8,472 (3 models x 4 scaffolds x 706 scenarios) |
| Results dir | `results/ex_w8_crossmodel/{model}_{scaffold}/` |
| Script | `scripts/experiments/exp_w8_scaffold_independence.py` |
| Evidence | `evidence_pack/ex_w8_crossmodel/w8_scaffold_independence.json` |
| Commit | `3ceeb1d6` |

| Model | Scaffolds |
|-------|-----------|
| oss120b | react, direct, checklist, tooluse |
| qwen35b | react, direct, checklist, tooluse |
| gemma31b | react, direct, checklist, tooluse |

---

## 3. CRES Experiment Log

| CRES ID | Script | Evidence output | Status | Git SHA |
|---------|--------|-----------------|--------|---------|
| CRES-1A | `exp_cres_1a_tcc_free.py` | `cres_1a/` | Infrastructure ready | `b25ea921` |
| CRES-1C | `exp_cres_1c_catalogue_perturbation.py` | `cres_1c/cres_1c_results.json` | Complete | `5517b80b` |
| CRES-1D | `exp_cres_1d_feature_classifier.py` | `cres_1d/cres_1d_results.json` | Complete (v2 leakage-clean) | `428a5420` |
| CRES-1E | `exp_cres_1e_counterfactual.py` | `cres_1e/cres_1e_results.json` | Complete | `5517b80b` |
| CRES-3 | `exp_cres_3_native_replay.py` | `cres_3/` | Dry-run infra ready | `ecba389d` |
| CRES-4 | `exp_cres_4_oracle_fair.py` | `cres_4/` | Skeleton (V2/V3 pending) | `84520e9f` |
| CRES-5 | `exp_cres_5_permutation_test.py` | `cres_5/cres_5_results.json` | Complete | `5517b80b` |
| CRES-5x | `exp_cres_5_expansion.py` | `cres_5_expansion/cres_5_expansion_results.json` | Complete | `bf29fddc` |
| CRES-6 | `exp_cres_6_before_analysis.py` | `cres_6/cres_6_analysis.json` | Complete (n=17) | `03bffb98` |
| CRES-7 | `exp_cres_7_partition.py` | `cres_7/cres_7_results.json` | Complete | `5517b80b` |
| CRES-9 | `exp_cres_9_tost.py` | `cres_9/cres_9_results.json` | Complete | `5517b80b` |
| CRES-11 | `exp_cres_11_dashboard.py` | `cres_11/cres_11_results.json` | Complete | `3f05bdd2` |
| CRES-12 | `exp_cres_12_rank_reversal.py` | `cres_12/cres_12_results.json` | Complete | `5517b80b` |
| CRES-13 | `exp_cres_13_compute.py` | `cres_13/cres_13_results.json` | Complete | `5517b80b` |

All scripts live under `scripts/experiments/`. All evidence under `evidence_pack/cres_{id}/`.

---

## 4. Pre-registration

| Field | Value |
|-------|-------|
| File | `rebuttal_preregister_v1.yaml` |
| Original commit | `fe8ff525` |
| SHA-256 hash | `b2d397f9ba6de8587ea442bfbf1a110983fe56b746844a6af87206c62ed9a215` |
| Protocol | Hash computed over file bytes with `hash:` value replaced by `<TBD>` |
| Experiments | 14 CRES experiments across 3 layers |

---

## 5. Infrastructure

### GPU hosts

| Host | IP | SSH user | GPUs | vLLM ports |
|------|-----|----------|------|------------|
| 144 | 127.0.0.1 | anonymous-user | 8x A100 | 30008, 30010, 30011, 30012 |
| 145 | 127.0.0.1 | anonymous-org | 8x A100 | 30003, 30005, 30006, 30007 |

### vLLM configuration

- Tensor parallelism: TP=2 per endpoint (2 GPUs each)
- API key: `sk-cga-bench` (for remote access)
- Max model length: 32768 tokens
- Decoding: greedy (temperature=0.1)

### Software versions

| Component | Version / Commit |
|-----------|-----------------|
| Python | 3.13 |
| vLLM | Check `pip show vllm` on 144/145 |
| PyTorch | Check `pip show torch` on 144/145 |
| scipy | >= 1.11.0 |
| scikit-learn | >= 1.3.0 (for CRES-1D) |
| numpy | >= 1.26.0 |

---

## 6. Raw Data Paths

| Data | Location | Size |
|------|----------|------|
| Episode JSONs (v6) | `results/full_706_v6_*/` | ~16,944 files |
| Episode JSONs (v5, archived) | `results/full_706_v5/` | ~14,826 files |
| Episode JSONs (W8) | `results/ex_w8_crossmodel/` | ~8,472 files |
| Verdict cache | `evidence_pack/cres_cache/verdicts_v5.json` | 14,826 records |
| W8 verdict cache | `evidence_pack/cres_cache/verdicts_w8.json` | 8,472 records |
| CPG graphs | `cpg_model/graphs/*.yaml` | 25 files |
| Scenarios | `configs/scenarios/*_scenarios.yaml` | 690 scenarios |
| RAG corpus | `agent_runner/rag_corpus/` | 25 parsed.json files |

---

## 7. Reproduction Commands

```bash
# Reproduce CRES experiments (from cga_bench/ directory)
PYTHONPATH=${CGA_BENCH_ROOT}

# CRES-1C: Catalogue perturbation
python scripts/experiments/exp_cres_1c_catalogue_perturbation.py

# CRES-1D: Feature classifier (leakage-clean v2)
python scripts/experiments/exp_cres_1d_feature_classifier.py

# CRES-1E: Counterfactual inversion
python scripts/experiments/exp_cres_1e_counterfactual.py

# CRES-5: Permutation test
python scripts/experiments/exp_cres_5_permutation_test.py

# CRES-5 expansion: Effect size battery
python scripts/experiments/exp_cres_5_expansion.py

# CRES-6: Wilson CI (BEFORE-only)
python scripts/experiments/exp_cres_6_before_analysis.py

# CRES-7: Theorem partition
python scripts/experiments/exp_cres_7_partition.py

# CRES-9: TOST equivalence
python scripts/experiments/exp_cres_9_tost.py

# CRES-11: Falsification dashboard
python scripts/experiments/exp_cres_11_dashboard.py

# CRES-12: Rank reversal
python scripts/experiments/exp_cres_12_rank_reversal.py

# CRES-13: Compute disclosure
python scripts/experiments/exp_cres_13_compute.py
```

---

## 8. Evaluator Thresholds

| Evaluator | Metric | Threshold | Source |
|-----------|--------|-----------|--------|
| AC-Proxy | Action coverage | >= 0.5 | Action-set projection |
| MAB-Proxy | F1 score | >= 0.5 | MedAgentBench-style |
| C2 | Compliance score | >= 0.7 | Composite score |
| CGA-Bench | Hard violations | == 0 | Trace conformance |

Hard violation types: commission, timing, sequence.

---

*Last updated: 2026-04-26. Generated for NeurIPS 2026 D&B Track rebuttal.*
*v5 → v6 migration: added `deepseek_r1_7b` (706 × 3 = 2,118 episodes), bringing total to 16,944.*
