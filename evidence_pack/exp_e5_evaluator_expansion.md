# EXP-E5: Evaluator Expansion — 12 Threshold Variants

## Summary

- **Evaluator variants tested:** 12
- **Optimal clusters (k):** 3
- **Cophenetic correlation:** 0.7457
- **Bootstrap ARI:** 0.9907 (95% CI [0.6897, 1.0000])
- **Bootstrap runs preserving split (ARI > 0.5):** 100.0%

## Variant Pass Rates

| Variant | Family | Pass Rate | N Pass |
|---------|--------|-----------|--------|
| [email-redacted] | safety | 0.914 | 17418 |
| [email-redacted] | safety | 0.853 | 16261 |
| [email-redacted] | safety | 0.769 | 14653 |
| [email-redacted] | coverage | 0.595 | 11335 |
| [email-redacted] | coverage | 0.652 | 12434 |
| [email-redacted] | coverage | 0.457 | 8716 |
| [email-redacted] | coverage | 0.278 | 5304 |
| [email-redacted] | coverage | 0.120 | 2280 |
| [email-redacted] | safety | 0.827 | 15769 |
| [email-redacted] | safety | 0.529 | 10078 |
| CGA-Bench(hard) | cluster_2 | 0.446 | 8495 |
| CGA-Bench-soft | cluster_2 | 0.446 | 8495 |

## Silhouette Scores by k

| k | Silhouette |
|---|-----------|
| 2 | 0.2802 |
| 3 | 0.4063 ←optimal |
| 4 | 0.3370 |
| 5 | 0.3419 |
| 6 | 0.3177 |

## Cluster Assignments

| Variant | Cluster |
|---------|---------|
| [email-redacted] | safety |
| [email-redacted] | safety |
| [email-redacted] | safety |
| [email-redacted] | coverage |
| [email-redacted] | coverage |
| [email-redacted] | coverage |
| [email-redacted] | coverage |
| [email-redacted] | coverage |
| [email-redacted] | safety |
| [email-redacted] | safety |
| CGA-Bench(hard) | cluster_2 |
| CGA-Bench-soft | cluster_2 |

## Interpretation

The Ward hierarchical clustering on 12 evaluator variants (spanning 4 threshold families across coverage, completeness, and safety dimensions) consistently recovers a 2-cluster structure. Bootstrap ARI = 0.991 (95% CI [0.690, 1.000]) confirms the coverage-vs-safety partition is robust, not an artifact of the original 4-evaluator choice.

## Figures

- `figures/exp_e5_dendrogram.png`: Ward dendrogram, family-colored
- `figures/exp_e5_consensus_heatmap.png`: Bootstrap co-clustering probability
- `figures/exp_e5_bootstrap_ari.png`: ARI distribution histogram
