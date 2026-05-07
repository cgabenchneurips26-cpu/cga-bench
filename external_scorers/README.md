# External Scorers (CRES-3 Native Replay)

Adapters that bridge CGA-Bench traces to the **original** scorers from
MedAgentBench, AgentClinic, and AMEGA. The defense purpose is documented
in `docs/attack_gap_exp_exp/260420_defense_exp.md` §E-R3 and
`docs/attack_gap_exp_exp/260420_defense_exp_add.md` §CRES-3.

## Anonymity protocol (READ BEFORE CLONING)

The external repos live on public GitHub under their authors' accounts.
Cloning them into this workspace and pushing a branch that references
them would leak anonymity during NeurIPS review.

Rules:
1. Clone **shallow and local only**:
   ```bash
   mkdir -p native
   git clone --depth 1 <repo-url> native/<short-name>
   ```
2. `external_scorers/.gitignore` excludes `native/`; do not override it.
3. Do **not** add the clones as git submodules.
4. Do **not** push a branch that references the clones.
5. Do **not** open PRs / issues against the upstream repos while the
   paper is under review.
6. Record the clone's commit SHA in
   `evidence_pack/cres_3/clone_provenance.json` so reviewers can
   verify reproducibility without re-cloning.

## Files

- `medagentbench_adapter.py` — converts cached verdict records to the
  MedAgentBench scorer's input schema. Priority 1 per defense doc.
- `agentclinic_adapter.py` — (TODO) trace→dialogue conversion for the
  AgentClinic LLM judge.
- `amega_adapter.py` — (TODO) prompt-template replay for AMEGA.

## Runner

`scripts/experiments/exp_cres_3_native_replay.py` is the CLI entry point.

```bash
# Dry-run using the stub adapter on synthetic traces (no clone needed).
# PYTHONPATH must point at the parent dir of cga_bench/.
PYTHONPATH="$(pwd)/.." \
  python scripts/experiments/exp_cres_3_native_replay.py \
    --benchmark medagentbench --pilot-n 10

# After cloning + wiring the real scorer (per-benchmark instructions in each adapter):
PYTHONPATH="$(pwd)/.." \
  python scripts/experiments/exp_cres_3_native_replay.py \
    --benchmark medagentbench --pilot-n 100 --no-dry-run \
    --clone-dir external_scorers/native/medagentbench
```
