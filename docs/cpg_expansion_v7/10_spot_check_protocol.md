# CPG Annotation Spot-Check Validation Protocol

**Version**: 1.0
**Date**: 2026-04-23
**Status**: Pre-registration (commit sample list before review)

## Overview

This protocol defines stratified sampling and validation procedures for C1-C12 auto-annotator scores across 123 CPG candidates. The spot-check validates auto-annotation reliability while maintaining efficient throughput for the v7 expansion.

## Population

| Tier | Score Range | Count | Definition |
|------|-------------|-------|------------|
| S | 15-19 | 76 | High-priority (≥15) |
| A | 11-14 | 35 | Secondary tier |
| B | 7-10 | 9 | Marginal |
| Excluded | <7 | 3 | Below threshold |
| **Total** | | **123** | |

**Held-out validation set**: 8 candidates already authoritatively reviewed (not part of spot-check).

## Stratified Sampling Strategy

### Tier-Based Sampling

| Tier | Auto Score | Sample Rate | Rationale | Expected N |
|------|------------|-------------|-----------|------------|
| **Borderline** | 14-15 | 100% | Tier flip sensitivity maximal | ~15 |
| **Tier S** | 16-19 | 30% | False-positive S most dangerous | ~18 |
| **Tier A** | 11-13 | 20% | Moderate risk | ~5 |
| **Tier B/Excluded** | <11 | 10% | Low priority | ~2 |

### Confidence-Based Forced Inclusion

**Bottom 20% by confidence score**: Forced into spot-check regardless of tier.

Confidence indicators:
- Missing structured tables/figures in source PDF
- High variability in per-criterion inter-rater agreement (if pilot data available)
- Auto-annotator flagged ambiguity in C7/C9/C11/C12

**Total spot-check count (estimate)**: ~35 candidates

## Pre-Registration Procedure

1. Generate stratified random sample using fixed seed (`random_seed=42`)
2. Commit sample list to `evidence_pack/cpg_expansion_v7/spot_check_sample.json`
3. Include: candidate_id, tier, auto_score, confidence_score, sample_reason
4. Timestamp and hash the file
5. **No modification allowed after commit** — prevents cherry-picking

## Review Focus Areas

Spot-check targets the **4 high-judgment criteria**:

| Criterion | Name | Why Spot-Check Required |
|-----------|------|-------------------------|
| C7 | Time-to-harm specificity | Requires clinical judgment on urgency |
| C9 | Algorithm figure quality | Visual assessment, not automatable |
| C11 | Sequence dependencies | Subtle clinical logic parsing |
| C12 | Conditional branching | Rare patterns, low auto-scorer confidence |

**Other criteria (C1-C6, C8, C10)**: Auto-annotation via mechanical heuristics (e.g., page count, table presence). Spot-check for sanity only.

## Review Protocol

### Per-Candidate Time Budget
- **4 criteria × 3 min/criterion** = 12 min per candidate
- **Total time estimate**: 35 candidates × 12 min = **7 hours**

### Authoritative Review Steps
1. Open source guideline PDF
2. For each of C7, C9, C11, C12:
   - Read auto-annotator justification
   - Re-score criterion independently (0-2 scale)
   - Record: `agree | disagree_+1 | disagree_-1 | disagree_+2 | disagree_-2`
3. Compute per-candidate delta: `authoritative_score - auto_score`
4. Flag candidates with |delta| > 3 for full re-annotation

### Disagreement Categories
- **Minor** (|delta| ≤ 2): Auto-score accepted, note discrepancy
- **Moderate** (3 ≤ |delta| ≤ 5): Trigger full 12-criterion re-review
- **Major** (|delta| > 5): Escalate to senior reviewer, re-examine auto-annotator heuristics

## Quality Metrics

### Spot-Check Outputs
1. **Disagreement rate**: % of spot-checked candidates with |delta| > 0
2. **Mean delta**: Average `authoritative - auto` across sample
3. **95% CI on delta**: Quantify systematic bias
4. **Spearman correlation**: Rank-order agreement between auto and authoritative scores
5. **Tier flip rate**: % of candidates crossing tier boundary after authoritative review

### Acceptance Criteria
- **Spearman rho ≥ 0.75**: Rank-order reliability acceptable
- **|Mean delta| ≤ 2.0**: No catastrophic systematic bias
- **Tier S false-positive rate ≤ 10%**: High-priority tier integrity maintained

## Decision Rules

### Tier Flip Protocol
If authoritative review moves candidate across tier boundary:
1. **S ↔ A**: Accept authoritative score, update tier assignment
2. **A ↔ B**: Accept authoritative score, update tier assignment
3. **Into/out of Excluded**: Escalate to 3-reviewer panel

### Auto-Annotator Recalibration Triggers
Full auto-annotator audit required if:
- **Tier S false-positive rate > 15%** in spot-check sample
- **Mean delta > +3.0** (systematic under-scoring exceeds held-out validation bounds)
- **Disagreement rate > 50%** for any single criterion (C7/C9/C11/C12)

## Reporting

### Spot-Check Report Sections
1. **Sample composition**: Tier distribution, confidence distribution
2. **Disagreement analysis**: Per-criterion disagreement rates, delta histogram
3. **Tier stability**: Before/after tier assignments
4. **Auto-annotator reliability metrics**: Spearman rho, mean delta, 95% CI
5. **Flagged candidates**: List of |delta| > 3 cases requiring full re-review

**Output file**: `evidence_pack/cpg_expansion_v7/spot_check_report.md`

## Integration with Two-Pass Protocol

This spot-check validates the **heuristic pre-filter → authoritative review** pipeline:

| Pass | Scope | Method | Output |
|------|-------|--------|--------|
| Pass 1 | All 123 candidates | Auto-annotator (C1-C12) | Initial tier assignments |
| Pass 2 | ~35 stratified sample | Authoritative spot-check | Validated tier assignments |

**Held-out validation** (8 candidates): Provides independent benchmark for Pass 2 reliability (Spearman rho=0.82, mean delta=+1.75).

## Pre-Registration Commitment

**Sample list commit deadline**: Before first spot-check review begins.

**Commit hash verification**: `git log --oneline evidence_pack/cpg_expansion_v7/spot_check_sample.json` must show single commit with timestamp before review start.

**No post-hoc sample adjustment**: Maintains integrity of stratified sampling for paper reporting.
