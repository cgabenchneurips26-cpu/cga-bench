# AgentClinic forward-direction TCC re-score — blocked

Status: 2026-04-23 — not executed in this session.

## Blocker

`data/episodes/agentclinic_converted.jsonl` has 122 cases but **0 of
them populate the `interactions` field**. Without agent↔patient
dialogue turns, we cannot extract an ordered action trace, and
TCC-style mandatory-completion scoring has no trajectory to evaluate
against.

Every non-empty field (`chief_complaint`, `vitals`, `test_results`,
`ground_truth`, `raw_osce`) is scenario metadata, not a trajectory.

## Options for a future session

1. **Re-run AgentClinic via `run_external_benchmark.py --benchmark agentclinic`**
   with an LLM agent (e.g. Qwen3-30B @ 145) to populate dialogue, then
   feed through `normalize_agentclinic_case` +
   `env/adapters/agentclinic_adapter.py::ACTION_PATTERNS`.
2. **Pull upstream**: fetch the original AgentClinic OSCE trajectory
   dumps from `github.com/jennymckinsey/agentclinic` (license check
   first) and re-parse.
3. **Declare AC out of scope**: the forward-direction claim stays MAB-only; add a caveat in §6.

Plan file reference: `/home/anonymous-user/.claude/plans/contribution-4-evaluator-melodic-cupcake.md`
(Experiment X, X.1 inventory).
