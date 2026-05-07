# CRES-4: Oracle-Fair Comparison — Design

Status: **Design + skeleton only.** V2 (Oracle-RAG) and V3 (RAG-Table)
agent variants are NOT implemented. This doc locks the specification so
the follow-up PR implements exactly what the pre-registration
(`rebuttal_preregister_v1.yaml::cres_4_oracle_fair`) commits to.

## Defense target

**Attack (FATAL-4 / reviewer)**: Oracle reads the decision table
directly while RAG must retrieve. The Oracle-vs-RAG gap therefore
measures retrieval quality, not reasoning capability, so the "Oracle as
upper bound" framing is misleading.

**Test (CRES-4)**: factor out the two confounds — information access and
reasoning modality — by running four variants on identical scenarios.
If `Delta(V2 - V3) >= 3 pp`, rule-based reasoning (not information
access) drives the Oracle gap, and the upper-bound framing survives.

## Four variants

| Variant | Reasoning | Information access | Implemented? |
|---------|-----------|--------------------|--------------|
| V1 — Oracle (current) | Rule-based | Direct decision-table read | YES (`agent_runner/oracle_agent.py`) |
| V2 — Oracle-RAG | Rule-based | Decision table via BM25 | **NO — needs new class** |
| V3 — RAG-Table | LLM | Full decision table in context | **NO — needs new class** |
| V4 — RAG (current) | LLM | BM25 retrieval from RAG corpus | YES (`agent_runner/rag_agent.py`) |

## Pre-registered endpoint

From `rebuttal_preregister_v1.yaml`:
- `delta_v2_v3_pp_gte: 3.0`
- `holds_on_n_domains_gte: 5` of 6

For WIN: V2 - V3 >= 3 pp on >=5 of 6 core CPG domains. If <3 pp, the
Oracle gap is attributable to information access and the paper must
retract the "rule-based upper bound" framing but keep main findings.

## Sample size

- 706 scenarios × 3 runs × 4 variants = **8,472 episodes** (not 16,944).
  The 16,944 number in the defense doc refers to an 8-variant extension.
  Pre-reg commits to the 4-variant version first; 8-variant is a
  potential camera-ready extension.

## Compute plan (once V2 and V3 exist)

- V1 Oracle: rule-based, CPU-only, ~0.2 s/episode → 425 s total.
- V2 Oracle-RAG: rule-based + BM25 query, CPU-only, ~0.5 s/episode → 1,060 s total.
- V3 RAG-Table: LLM inference with ~30k token context (full decision table),
  ~15 s/episode → 31,770 s total (~9 wallclock hours on 8× parallel vLLM).
- V4 RAG (current): ~5 s/episode → 10,590 s total (~3 wallclock hours).

With 144's 8 idle Qwen3.5-35B-A3B-FP8 endpoints (:8025–:8032), V3 and V4
can run in parallel. V1/V2 are CPU-bound and run on 145 concurrently.

Total wallclock once V2/V3 exist: ~10 hours.

## V2 — Oracle-RAG design

New class `agent_runner/oracle_rag_agent.py`. Contract:

```python
class OracleRAGAgent(OracleAgent):
    """Oracle that accesses its decision table via BM25 retrieval.

    Inherits all rule application logic from OracleAgent but overrides
    the rule lookup so each decision issues a BM25 query against an index
    built over the same `agent_rules/*.py` commentary strings that RAG
    uses. Only the top-k retrieved rules are applied.
    """

    def __init__(self, config: OracleRAGConfig):
        super().__init__(config)
        self.index = BM25Index()
        self.index.add_documents(self._build_rule_docs())
        self.top_k = config.top_k  # default 10

    def _select_applicable_rules(self, state, query):
        # Override: retrieve via BM25 instead of scanning full table.
        hits = self.index.search(query, top_k=self.top_k)
        return [self._all_rules[idx] for idx, _ in hits]
```

Matched RAG retrieval-budget: same `top_k` and same BM25 parameters as
V4. Corpus: concatenated commentary strings from `agent_rules/*.py`.

## V3 — RAG-Table design

New class `agent_runner/rag_table_agent.py`. Contract:

```python
class RAGTableAgent(RAGAgent):
    """RAG variant that skips retrieval and stuffs the full decision
    table into the LLM context as a 'reference table' section.

    Purpose: isolate the LLM-reasoning factor from the retrieval factor.
    """

    def __init__(self, config: RAGTableConfig):
        super().__init__(config)
        self._full_table_text = self._serialize_full_decision_table()

    def _build_context(self, state) -> str:
        # Override: skip BM25 retrieval entirely.
        return self._format_with_full_table(state, self._full_table_text)
```

Token budget: truncate the full table to the largest slice that fits in
the 32k context window of Qwen3.5-35B-A3B-FP8 (≈28k after prompt
overhead). If a domain's full table exceeds that, emit a documented
"truncation rule" rather than silently cropping.

## Risks

- **Context overflow**: RAG-Table may not fit in 32k context for domains
  with the largest rule tables (GI bleeding, sepsis). Test before launch.
- **Oracle-RAG degeneracy**: If `top_k` is too low, Oracle-RAG will miss
  critical rules and underperform V1 for reasons unrelated to retrieval
  quality. Use `top_k=10` (matches V4's default) and verify by spot check.
- **Compute contention**: V3 and V4 cannot share the same vLLM
  endpoint simultaneously; schedule them in sequence (V4 first —
  cheaper — then V3 once V4 completes).

## Launch command (once V2 and V3 exist)

```bash
# From 145 (repo has CRES-4 launcher)
PYTHONPATH=${CGA_BENCH_ROOT} \
  python scripts/experiments/exp_cres_4_oracle_fair.py \
    --variants V1,V2,V3,V4 \
    --scenarios 706 \
    --runs 3 \
    --vllm-endpoints http://localhost:8013,http://localhost:8013,...,http://localhost:8013 \
    --output-dir results/cres_4/
```

A skeleton of this runner lives at
`scripts/experiments/exp_cres_4_oracle_fair.py` (not launched).
