# D2: Parallel Order Analysis

## Question

Can timing violations in the clean-slate experiment be resolved by
parallelising independent actions (ordering labs and imaging
simultaneously rather than sequentially)?

## Methodology

For each timing violation in the 180 rescored episodes we:

1. Identified all actions performed **before** the violated action.
2. Classified each prior action as:
   - **Sequential dependency** — clinically required before the violated
     action (e.g., blood culture before antibiotics).
   - **Agent-inserted** — off-protocol action not in the expected set.
   - **Parallelisable** — expected/protocol action with no hard dependency.
3. Computed the *adjusted timestamp*: minimum time assuming only sequential
   dependencies precede the violated action (5 min each).
4. Categorised the violation:
   - **Unavoidable** — adjusted time still exceeds the deadline.
   - **Agent-caused** — agent-inserted actions pushed the action late.
   - **Parallelisable** — would resolve with zero-latency parallel ordering.

## Results

| Category | Count | % |
|---|---:|---:|
| Sequential dependency (unavoidable) | 0 | 0.0% |
| Agent-inserted delay | 115 | 100.0% |
| Parallelisable (resolvable) | 0 | 0.0% |
| **Total timing violations** | **115** | **100%** |

## Per-Model Breakdown

| Model | Total | Unavoidable | Agent-caused | Parallelisable |
|---|---:|---:|---:|---:|
| DeepSeek-V3 (120B) | 46 | 0 (0%) | 46 (100%) | 0 (0%) |
| R1-Distill (27B) | 23 | 0 (0%) | 23 (100%) | 0 (0%) |
| Qwen3.5 (35B) | 23 | 0 (0%) | 23 (100%) | 0 (0%) |
| Qwen3 (4B) | 23 | 0 (0%) | 23 (100%) | 0 (0%) |

## Interpretation

Most timing violations (0.0% unavoidable + 100.0% agent-caused = 100.0%) cannot be resolved by parallelisation alone. Only 0.0% would benefit from concurrent ordering.

## Insertion Strength Analysis

Not all agent-caused violations have equal attribution confidence.
We stratify by insertion count (number of off-protocol prior actions):

| Insertion strength | Count | % | Description |
|---|---:|---:|---|
| Strong (>2 insertions) | 72 | 62.6% | Multiple unnecessary actions clearly caused the delay |
| Marginal (<=2 insertions) | 43 | 37.4% | Few insertions; delay may partly reflect sequential ordering |
| **Total** | **115** | **100%** | |

Of the 115 agent-caused violations, **72 (62.6%)** have strong attribution (>2 off-protocol insertions before the deadline miss), while **43 (37.4%)** are marginal cases where only 1-2 insertions preceded the target action. In marginal cases, the delay could partly reflect sequential dependencies rather than pure agent error.

