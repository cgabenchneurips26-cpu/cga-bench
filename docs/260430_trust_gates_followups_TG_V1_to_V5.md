# Trust-Gate Follow-Up Pass — TG-V1 through TG-V5

Branch: `eval_science`
Predecessor: `23fd0e6b` (comprehensive implementation report)
Date: 2026-04-30

This pass actions the five operational concerns raised on top of the
trust-gate close-out. Three are **landed as code** (TG-V2, TG-V3, TG-V5);
two are **scaffolded as runnable harnesses** (TG-V1, TG-V4) so the actual
compute can be triggered as soon as budget is available, with deterministic
driver logic already test-covered.

---

## 1. Status Matrix

| ID | Concern | This pass | Status |
|----|---------|-----------|--------|
| TG-V1 | CDS=True/False subset comparison evidence (Phase F leakage delta) | Driver + aggregator scaffold (`scripts/experiments/cds_subset_comparison.py`) + 12 tests | Scaffold landed, compute deferred |
| TG-V2 | D5 — measure 0.5 vs 0.7 entailment threshold impact during SGSC-3 | `compare_entailment_thresholds()` helper + 3 tests | Landed |
| TG-V3 | Add Krippendorff alpha (50 LOC) to validation packet | `_krippendorff_alpha_binary()` + 4 tests | Landed |
| TG-V4 | v6→v7 attribution table over 4 dimensions | Generator scaffold (`scripts/experiments/v6_v7_transition_audit.py`) + 5 tests | Scaffold landed, real-data run deferred |
| TG-V5 | Manifest CI safe-failure during data-sweep window | `--allow-missing` flag + 5 tests | Landed |

Total test delta: **499 → 528 (+29)**. All pass in 2.43 s.

---

## 2. Code Landings

### 2.1 TG-V3 — Krippendorff alpha (`sgsc/validation_packet.py`)

Added `_krippendorff_alpha_binary(r1, r2)` for binary nominal data with
two raters per unit. Formula:

```
D_o = (number of disagreeing units) / n_units
p_1 = pooled prevalence of category 1 across all 2n ratings
D_e = 2 * p_1 * (1 - p_1)              # uncorrected expected disagreement
D_e_c = D_e * total_ratings / (total_ratings - 1)   # small-sample correction
alpha = 1 - D_o / D_e_c
```

This differs from Cohen's kappa in that the chance baseline is computed
from the **pooled** marginal across all raters (Scott's-pi family) rather
than the product of per-rater marginals. Krippendorff alpha is therefore
more conservative when raters have asymmetric biases.

The `_compute_agreement` function now returns three metrics:

```python
{"cohen_kappa": ..., "gwet_ac1": ..., "krippendorff_alpha": ...,
 "n_paired_items": n}
```

`_ADJUDICATION_PROTOCOL["metric"]` was updated to advertise all three:
`"Cohen's kappa + Gwet AC1 + Krippendorff alpha (binary, pairwise)"`.

**Why three metrics, not one?** Reviewers can attack any single agreement
metric (Cohen has the kappa-paradox; AC1 can be argued under-corrected;
Krippendorff has the prevalence-correction debate). Reporting all three
chance-corrected coefficients pre-empts that line of attack.

**Reproducibility cost.** Pure Python, no numpy / scipy. ~30 LOC added.

### 2.2 TG-V2 — Dual-threshold entailment (`sgsc/verification/entailment_checker.py`)

Threaded a `threshold` parameter through `_check_action_entailment` and
`_check_guard_entailment` (defaults preserved at 0.5 for backwards
compatibility), and added a new public helper:

```python
def compare_entailment_thresholds(
    atoms: list[RecommendationAtom],
    thresholds: list[float] | None = None,
) -> dict[float, dict[str, int]]:
    """Run rule-based entailment at multiple thresholds."""
```

Default sweep is `[0.5, 0.7]`. Each threshold yields:

```python
{
    "n_total":            int,
    "n_strict_passing":   int,  # every applicable field ENTAILED
    "n_lenient_passing":  int,  # no field NOT_ENTAILED (PARTIAL allowed)
    "n_rejected":         int,  # at least one NOT_ENTAILED field
    "n_partial_only":     int,  # lenient - strict
}
```

**Use during SGSC-3 atom proposal:** call this immediately after the LLM
batch returns. If the 0.7 threshold drops `n_strict_passing` by >30%
relative to 0.5, the atom proposer prompt is too lenient and needs a
re-run before downstream phases consume the atoms.

```python
from sgsc.verification.entailment_checker import compare_entailment_thresholds

stats = compare_entailment_thresholds(proposed_atoms)
print(stats[0.5]["n_strict_passing"], "->", stats[0.7]["n_strict_passing"])
```

### 2.3 TG-V5 — Manifest CI safe-failure (`scripts/ci/audit_manifest.py`)

Added `--allow-missing` flag that turns the missing-manifest case into
exit-0 with a stderr warning. Behaviour matrix:

| Manifest state | `--allow-missing` | Exit code |
|----------------|-------------------|-----------|
| present, all hashes match | (any) | 0 |
| present, drift detected | (any) | 1 |
| missing | absent | 1 |
| missing | present | 0 (warns to stderr) |

Critically, `--allow-missing` does **not** suppress drift detection; it
only relaxes the missing-file failure mode. Tests cover all four cells.

**CI usage during the data-sweep window:**

```yaml
- name: Audit SGSC manifest
  run: python scripts/ci/audit_manifest.py --allow-missing
```

Drop the flag once `sgsc/v1/manifest.json` lands; this restores strict
drift detection without any other CI change.

---

## 3. Scaffolds Landed

### 3.1 TG-V1 — CDS True/False subset comparison
**File:** `scripts/experiments/cds_subset_comparison.py`

A two-stage CLI driver:

1. **`plan` subcommand** — emits per-job descriptors as JSONL on STDOUT.
   Cartesian product of `(cpg, scenario, model, run_idx, arm)`, with the
   subset selected deterministically by seed. Defaults: 50 scenarios per
   CPG × 14 CPGs × 9 models × 3 runs × 2 arms = ~37,800 episodes.

   ```bash
   python scripts/experiments/cds_subset_comparison.py plan \
       --scenarios-manifest cpg_model/scenarios_index.json \
       --models qwen35b qwen27b qwen4b oss120b nemotron30b gemma31b \
                deepseek_r1_7b qwen397b qwen3-30b \
       --per-cpg 50 --runs 3 \
       --output-dir results/cds_subset \
       > job_descriptors.jsonl
   ```

   The 9 models above match the canonical SGSC sweep. Job descriptors
   are consumed by the existing runner pool — the driver does NOT spawn
   compute, it only enumerates the work.

2. **`aggregate` subcommand** — walks `cds_true/` and `cds_false/`
   episode JSONs, joins on `(cpg, model)`, and writes both
   `comparison.json` and a paper-ready `comparison.md` with per-CPG /
   per-model deltas plus the overall mean.

   ```bash
   python scripts/experiments/cds_subset_comparison.py aggregate \
       --arms-dir results/cds_subset
   ```

**Determinism:** Selection uses `random.Random(seed)`. Same seed +
manifest -> same sample. The 12 tests cover selection, cartesian-product
size, both-arms-emitted, output-path partitioning, aggregation grouping,
delta sign convention, inner-join semantics on missing models, and the
markdown rendering.

**What this script will tell the reviewer.** If the overall mean delta
is positive (CDS=True boosts compliance), the magnitude is the
quantitative evidence that Phase F's `cds_assistance=False` default is
not arbitrary — it removes a measurable score-inflating leak. If the
delta is near zero, Phase F's design is conservative but still defensible
(no harm from removing the hint).

### 3.2 TG-V4 — v6→v7 transition attribution table
**File:** `scripts/experiments/v6_v7_transition_audit.py`

A pure delta-calculator that consumes five aggregate JSONs and emits the
four-dimension attribution table for paper Appendix Z:

| Marginal | Description |
|----------|-------------|
| `corpus_change_25_to_14_cpgs` | v6 corpus → v7 corpus, CDS+coverage held |
| `cds_default_true_to_false` | CDS=True → CDS=False, on top of corpus |
| `alternative_coverage_reserved_to_active` | ALTERNATIVE family activation |
| `cde_coupling_added` | v1.1 CDE conflict-surfacing |

The four marginals are reported alongside the **direct delta**
(v7_final − v6); the script also surfaces the discrepancy between the
two so a reviewer can immediately see whether the ablation chain was
actually nested. Tests pin the dimension order and the marginal-sum
identity.

```bash
python scripts/experiments/v6_v7_transition_audit.py \
    --v6-baseline       results/v6_full/aggregate.json \
    --v7-corpus-only    results/v7_corpus_only/aggregate.json \
    --v7-cds-flip       results/v7_cds_flip/aggregate.json \
    --v7-alternative    results/v7_alternative/aggregate.json \
    --v7-final          results/v7_full/aggregate.json \
    --output-dir        results/transition_audit
```

The four intermediate aggregate JSONs require running the existing
`full_v6_runner.py`-style scripts with each ablation flag flipped one
at a time. That is a Day 5-6 compute task.

---

## 4. Test Inventory Delta

| Bucket | Pre-pass | Post-pass | New tests |
|--------|----------|-----------|-----------|
| `tests/test_sgsc/test_validation_packet.py` | 22 | 26 | +4 (Krippendorff: keys, perfect, anti-corr, three-metrics consistency, label) |
| `tests/test_sgsc/test_entailment_checker.py` | 19 | 23 | +3 (compare_thresholds: tightening rejects borderline, defaults are 0.5 & 0.7, partial_only identity) |
| `tests/test_sgsc/test_manifest.py` | 13 | 18 | +5 (CLI: missing-default-fail, missing-allow-pass, present-still-audited, drift-still-fails, argv-position-flexible) |
| `tests/test_experiments/test_cds_subset_comparison.py` | 0 | 12 | +12 (TG-V1 driver coverage) |
| `tests/test_experiments/test_v6_v7_transition_audit.py` | 0 | 5 | +5 (TG-V4 generator coverage) |
| **Total** | 499 | 528 | **+29** |

All 528 pass in 2.43 s.

---

## 5. What Remains Deferred (and Why)

| Item | Why deferred |
|------|--------------|
| Real CDS=True/False sweep (~37,800 episodes) | Compute budget. Driver and aggregator now ready; trigger when GPU/API budget is available. |
| Real v6→v7 ablation runs (5 aggregate JSONs) | Same compute constraint. Each ablation needs a full sweep with one flag flipped. |
| `manifest.json` populated with canonical 706 counts | Requires the canonical sweep to finalise. CI now safe under `--allow-missing` until then. |
| Tightening 0.5 → 0.7 threshold as the new default | Decided per-corpus after `compare_entailment_thresholds` runs on real SGSC-3 atoms. Both thresholds remain selectable via parameter. |
| Krippendorff alpha for >2 raters | Current implementation is binary 2-rater. The clinician-validation packet is 3-rater, so the natural extension is the general nominal-data formula. ~80 more LOC; deferred until the clinician pilot returns data. |

---

## 6. Reproducibility

```bash
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
PYTHONPATH=. /home/anonymous-org/anaconda3/bin/python -m pytest \
  tests/test_sgsc/ tests/test_engine/ \
  tests/test_experiments/test_cds_subset_comparison.py \
  tests/test_experiments/test_v6_v7_transition_audit.py \
  --tb=short -q
# Expected: 528 passed in ~2.4s
```

CLI smoke tests:

```bash
# TG-V5 — manifest audit safe-failure
python scripts/ci/audit_manifest.py --allow-missing
# Expected: SKIPPED message to stderr, exit 0

# TG-V1 — emit a tiny job-descriptor stream for sanity check
echo '{"ssc_test": ["s1", "s2", "s3"]}' > /tmp/test_manifest.json
python scripts/experiments/cds_subset_comparison.py plan \
  --scenarios-manifest /tmp/test_manifest.json \
  --models m1 \
  --per-cpg 2 --runs 1 \
  --output-dir /tmp/cds_subset_smoke
# Expected: 4 JSON lines emitted (2 scenarios × 1 model × 1 run × 2 arms)
```

---

## 7. Files Modified or Created

### Modified (5)

* `sgsc/validation_packet.py` — Krippendorff alpha + label update
* `sgsc/verification/entailment_checker.py` — threshold params + comparison helper
* `scripts/ci/audit_manifest.py` — `--allow-missing` flag + parser refactor
* `tests/test_sgsc/test_validation_packet.py` — 4 new tests
* `tests/test_sgsc/test_entailment_checker.py` — 3 new tests + fixture extension
* `tests/test_sgsc/test_manifest.py` — 5 new CLI tests

### New (4)

* `scripts/experiments/cds_subset_comparison.py` (TG-V1)
* `scripts/experiments/v6_v7_transition_audit.py` (TG-V4)
* `tests/test_experiments/test_cds_subset_comparison.py` (TG-V1 coverage)
* `tests/test_experiments/test_v6_v7_transition_audit.py` (TG-V4 coverage)
* `docs/260430_trust_gates_followups_TG_V1_to_V5.md` (this report)
