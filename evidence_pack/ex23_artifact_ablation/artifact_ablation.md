# EX-23: Artifact Mimic Ablation

**Total episodes:** 16944
**TCC fail (hard violation):** 8553 (50.5%)

## Mode Overview

| Mode | Pass Rate | FA Count | FA Rate | Detection Loss |
|------|-----------|----------|---------|----------------|
| AC-Artifact | 74.4% | 7202 | 42.5% | 84.2% |
| MAB-Artifact | 53.0% | 5406 | 31.9% | 63.2% |
| HB-Artifact | 74.4% | 7200 | 42.5% | 84.2% |
| TCC | 49.5% | 0 | 0.0% | 0.0% |

## Detection by Violation Type (constraint label)

| Mode | FORBIDDEN | WITHIN | BEFORE | MUST |
|------|-----------|--------|--------|------|
| AC-Artifact | 21.1% | 15.3% | 0.0% | 30.8% |
| MAB-Artifact | 60.0% | 36.3% | 10.6% | 47.5% |
| HB-Artifact | 21.1% | 15.3% | 0.7% | 30.8% |
| TCC | 100.0% | 100.0% | 100.0% | 51.1% |

## Violation Type Episode Totals

- BEFORE: 283 episodes
- FORBIDDEN: 1632 episodes
- MUST: 11660 episodes
- WITHIN: 8199 episodes

## Key Finding

AC-Artifact and MAB-Artifact cannot detect WITHIN (timing) or BEFORE (sequence) violations by design — their detection of such episodes is purely incidental (co-occurring OMISSION lowers coverage).