# E5 Debug Notes: MAB-Proxy Clustering and 3-Family Structure

## Finding: 2-cluster is correct but the split is CGA-Bench vs. everything else

### k=2 Clustering (silhouette=0.630, optimal)
- **Cluster 1** (safety/conformance): CGA-Bench(hard), CGA-Bench-soft
- **Cluster 2** (coverage/completeness): AC-Proxy x4, C2 x4, MAB-Proxy x2

### k=3 Clustering (silhouette=0.530)
- **Cluster 1**: CGA-Bench(hard), CGA-Bench-soft
- **Cluster 2**: [email-redacted], [email-redacted]
- **Cluster 3**: AC-Proxy x4, C2 x4

### k=4 Clustering (silhouette=0.406)
- CGA-Bench, MAB-Proxy, lenient AC/C2, strict AC/C2

## Why MAB-Proxy Clusters with Coverage (Not CGA-Bench)

### Distance matrix evidence

| Pair | Distance (1-kappa) |
|------|-------------------|
| [email-redacted] vs [email-redacted] | 0.471 (closest non-MAB) |
| [email-redacted] vs [email-redacted] | 0.647 |
| [email-redacted] vs CGA(hard) | **1.357** (very far!) |
| [email-redacted] vs [email-redacted] | 0.921 |
| [email-redacted] vs CGA(hard) | 0.921 |

[email-redacted] is **much closer** to AC-Proxy (0.47) than to CGA-Bench (1.36).
[email-redacted] is equidistant to everything (~0.92) due to extreme sparsity (only 16/180 pass).

### Root cause: MAB-Proxy measures action F1, not safety

MAB-Proxy computes F1 between agent actions and expected actions — it's fundamentally a **coverage metric** (how well did the agent cover expected actions?), not a safety metric (did the agent avoid harm?). Its kappa with CGA-Bench is **negative** (-0.115 from kappa_precision_debug.json), meaning it actively disagrees with CGA-Bench: episodes MAB passes are often ones CGA fails, and vice versa.

The negative kappa translates to distance = 1 - (-0.115) = 1.115, pushing MAB far from CGA-Bench. Meanwhile, [email-redacted]'s modest positive agreement with AC-Proxy (kappa ~0.53) means distance ~0.47.

### Reconciliation with prior kappa_precision_debug analysis

Prior analysis had 4 evaluators and found 2 clusters: {AC-Proxy, C2} vs {MAB-Proxy, CGA-Bench}. But that was with only 4 points — with 12 points, the structure refines:

- The prior "cluster" of {MAB, CGA} was an artifact of both having low kappa with {AC, C2}
- With threshold variants, MAB's behavior is revealed as coverage-like (F1 is a coverage metric)
- CGA-Bench is the true outlier — it measures something fundamentally different (constraint violations)

## clusterPreservedE4 = false

This field comes from E4's operating-point matching experiment. It checks whether the original 4-evaluator {AC,C2} vs {MAB,CGA} cluster assignment is preserved after threshold adjustment. Since MAB's behavior is actually coverage-like, threshold-matching doesn't preserve the original (incorrect) 2-cluster labeling. This is consistent with E5's finding.

## Recommended Paper Framing

### Option A: Embrace the 3-family structure (recommended)
The 12-variant expansion reveals a more nuanced picture than the initial 4-evaluator analysis:
- **Family 1 (Action Coverage)**: AC-Proxy, C2 — "did the agent do the right things?"
- **Family 2 (Action Precision)**: MAB-Proxy — "did the agent do only the right things?" (F1 penalizes extra actions)  
- **Family 3 (Safety Conformance)**: CGA-Bench — "did the agent avoid harmful constraint violations?"

At k=2 (optimal silhouette), Families 1+2 merge because both measure action sets, while Family 3 measures constraint violations — a fundamentally different evaluation axis.

### Option B: Reframe as "coverage-family vs. conformance-family"
The 2-cluster split is really "action-set metrics" vs. "constraint-violation metrics":
- **Action-set family** (10 variants): AC-Proxy, C2, MAB-Proxy — all compute |agent actions intersect expected actions| in various ways
- **Conformance family** (2 variants): CGA-Bench — computes FORBIDDEN/WITHIN/BEFORE constraint violations

This is actually a **stronger** paper argument: it shows that ALL coverage-style metrics (regardless of threshold) cluster together and AWAY from safety-conformance metrics. The gap is not about calibration — it's about what dimension is being measured.

### Key numbers for paper
- Cophenetic correlation: 0.941 (excellent hierarchical fit)
- Bootstrap ARI: 0.828 [0.641, 1.000] (robust)
- 100% of 1000 bootstraps preserve the 2-cluster split
- k=3 silhouette: 0.530 (MAB-Proxy separates as intermediate family)
