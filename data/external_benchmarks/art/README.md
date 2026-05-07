# ART: Action-based Reasoning clinical Task

## Status
**Data NOT yet publicly released** (as of 2026-03-26)

Paper: https://arxiv.org/abs/2601.08988
"ART: Action-based Reasoning Task Benchmarking for Medical AI Agents"

## What is ART
ART mines real-world EHR data to create tasks targeting known LLM reasoning weaknesses:
- **Threshold evaluation**: Decisions based on lab/vital value thresholds
- **Temporal aggregation**: Reasoning over time-series clinical data
- **Conditional logic**: Multi-condition branching clinical decisions

## Expected Data Format (from paper)
Each case contains:
- `case_id`: Unique identifier
- `task_type`: One of threshold_evaluation | temporal_aggregation | conditional_logic
- `input_text`: Clinical narrative / EHR summary
- `structured_fields`: Labs, vitals, medications, timeline
- `checklist`: List of required/forbidden actions
- `gold_answer`: Target diagnosis or decision label
- `reasoning_type`: Maps to task_type

## Synthetic Sample
`synthetic_sample.json` contains 5 synthetic cases created from paper description
for pipeline compatibility testing only. Replace with real data when released.

## Access
When released, expected at: https://github.com/[TBD]/ART-benchmark
License: Unknown (check paper authors)
