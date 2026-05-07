# EX-2: What Mode B Misses (12.6% severity breakdown)

1,677 episodes have TIMING as the ONLY hard violation.
Mode B (action multiset) cannot detect these — it sees the right actions
but not that they were performed too late.

## Severity of missed TIMING violations
- Minor: 2,030 (64.5%)
- Moderate: 666 (21.2%)
- Major: 350 (11.1%)
- Severe: 98 (3.1%)
- **Non-minor: 1,114 (35.5%)**

## Domains (timing-critical conditions)
- AHA Stroke: 390 episodes (tPA window, thrombectomy timing)
- Meningitis: 351 episodes (antibiotic delay → mortality)
- DKA: 138+31 episodes (insulin timing, bicarbonate)
- Toxicology: 111 episodes (antidote timing)

## Paper narrative
"The 1,677 episodes (12.0%) that action-set evaluation misses are
concentrated in stroke, meningitis, and DKA — conditions where
timing-to-treatment determines survival."
