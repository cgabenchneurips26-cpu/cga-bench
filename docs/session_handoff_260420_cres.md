# CRES Tier A — Session Handoff (2026-04-20 07:20 UTC)

## Status: In Progress (7/10 scripts built, 5/8 verified)

### Scripts Created (9 total)
| Script | Status | Key Result |
|--------|--------|------------|
| `_episode_cache.py` | PASS | 14,826 eps loaded, 7 models verified |
| `exp_cres_1c_catalogue_perturbation.py` | BUILT, not run | CPU-heavy (~30min), run last |
| `exp_cres_1d_feature_classifier.py` | BUILT, not run | Needs sklearn/shap |
| `exp_cres_1e_counterfactual.py` | PASS | 0% all-4 agreement (strong negative control) |
| `exp_cres_5_effect_size.py` | RUNNING | 10K permutation test in progress |
| `exp_cres_7_theorem_partition.py` | PASS | 33.0% Class-B invisible, 33.2% ASC FA invisible |
| `exp_cres_9_tost.py` | PASS | 7/36 pair-field combos equivalent at 3pp |
| `exp_cres_11_dashboard.py` | BUILT, depends on others | Run after all inputs ready |
| `exp_cres_12_rank_reversal.py` | PASS | Spearman rho=0.060, 18/21 reversals, depth=5 |
| `exp_cres_13_compute.py` | PASS | 505M tokens, 14.0 A100-hrs, 1.68 kgCO2 |

### Evidence Files Generated
```
evidence_pack/cres_12/cres_12_results.json  (6.3 KB)
evidence_pack/cres_13/cres_13_results.json  (5.5 KB)
evidence_pack/cres_1e/cres_1e_results.json  (1.9 KB)
evidence_pack/cres_7/cres_7_results.json    (1.9 KB)
evidence_pack/cres_9/cres_9_results.json    (56.8 KB)
```

### Bugs Found & Fixed
1. **CRES-12 `bootstrap_rank_ci_width`**: `all_model_rates[ev_name][evaluator]` — confused model names with evaluator names. Fixed: pass `target_model` + full `model_pass_rates` dict.

### Still Running
- CRES-5: 10K permutation test (~10min expected)
- CRES-1D: Not yet run (needs sklearn)
- CRES-1C: Not yet run (CPU-heavy, ~30min)

### Next Steps
1. Wait for CRES-5 completion
2. Run CRES-1D (may need `pip install sklearn shap`)
3. Run CRES-1C (CPU-heavy, background)
4. Run CRES-11 dashboard (depends on CRES-5 output)
5. Git commit + push all results
6. Create preregistration YAML
