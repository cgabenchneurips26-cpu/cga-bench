# Defense Round 2: Additional Evidence

## EX-2 Defense: TIMING-only is NOT domain-specific
- 39 graphs (out of 100+) have ≥1 TIMING-only episode
- Top: AHA Stroke (72.8%), AF anticoagulation (96.3%), meningitis (53.6%)
- These are genuinely time-critical conditions
- Paper: "TIMING-only violations appear across 39 clinical domains"

## EX-4D Defense: Boundary violations are clinically urgent
Boundary violations (≤5min margin): 3,546 total
- 59% clinically urgent (code team activation, anaphylaxis, glucose, IV access, CT)
- 18% parallelizable (lab panels — potential artifact)
- 23% other
- Paper: "Even boundary TIMING violations are dominated by
  time-critical actions (code activation 667, anaphylaxis 408)"

## EX-1 Defense: No conservative bias
P4 prompt ("assume appropriate unless clear violation"):
- P1 (neutral): FA=14.0%
- P4 (default-PASS): FA=4.0%
- P4 is LOWER, not higher → LLM does NOT have conservative bias
- The low T0 FA (0.4%) reflects genuine terminal blindness
- Paper: "A default-PASS prompt yields even lower FA (4.0%),
  ruling out conservative response bias as an explanation"
