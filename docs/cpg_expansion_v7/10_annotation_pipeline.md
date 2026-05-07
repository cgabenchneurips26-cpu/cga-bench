# Annotation Pipeline (Method A + Method B) — beta Tier Promotion

**Scope**: Promote 29 bulk_A/bulk_B Tier S candidates listed in
[`09_tier_s_preregistration.md §3.1 (beta core)`](./09_tier_s_preregistration.md#31-core-43-cpgs--16-alpha--27-beta) and
[§3.2 (held-out beta)](./09_tier_s_preregistration.md#32-held-out-5-cpgs--3-alpha--2-beta)
from metadata-based estimates to beta-authoritative per-criterion scores with
verbatim `source_text` quotes and dual-LLM inter-rater records.

**Output**: For each of the 29 CPGs, a new entry in
`data/cpg_source_properties.json` that is schema-identical to the existing 25
core alpha entries, with two additional provenance fields:
- `annotation_tier: "beta"`
- `dual_llm_agreement: { kappa: <float>, disagreements: [<list of resolved cases>] }`
- `human_verified_by: <annotator_id>` (e.g., commit author on eval_science)
- `verification_date: <ISO-8601>`

**Success gate** (per CPG): C1-C12 Total Tier S (>= 15) confirmed after human
adjudication. If a CPG drops below 15 post-annotation, it stays in §3 of the
pre-registration (list is frozen) but receives a `tier_post_annotation: "A"`
flag for paper transparency. This is the "do not move the goalposts" commitment.

---

## 1. Prerequisites (per-CPG source acquisition)

For each of the 29 beta CPGs, a parsed source document is required at:
`data_release/v5.0/rag_corpus/<guideline_name_slug>.parsed.json` (same schema as
existing 25 alpha entries: `{guideline_name, graph_id, source, doi,
recommendations, tables, key_sections}`).

Acquisition workflow (expected 2-3 min/CPG for open-access; variable for paywall):

1. **DOI resolution**: from `data/cpg_source_properties_candidates_bulk_{A,B}.json`,
   each candidate has `c5_doi` or an equivalent identifier. Resolve to publisher URL.
2. **PDF download**: use `scripts/cpg_v2_phase_annotation/acquire_source_pdf.py`
   (see §4). The manifest classifies each DOI as `OPEN_ACCESS` (downloadable via
   Unpaywall) or `MANUAL_UPLOAD_REQUIRED` (paywalled). For paywalled sources, the
   user supplies PDFs via secure institutional access and drops them in
   `data/source_pdfs/<graph_id>.pdf`.
3. **Parse to JSON**: `semantic_layer/cpg_parser.py` already handles
   PDF → structured `ExtractedRecommendation` objects. Wrap it to emit the
   rag_corpus-schema parsed.json. Missing sections (e.g., `tables`) remain
   empty — acceptable.

**Gate**: all 29 parsed.json files *that will be included* must exist before
Method A runs. Some beta candidates may be dropped per the accessibility
policy (§1.1) rather than blocking the batch.

### 1.1 Accessibility-first inclusion policy (2026-04-23 amendment)

**Rationale**: a strict interpretation of "all 29 β must be annotated" would
block benchmark submission on paywall access. To maintain the authoritative-
only spirit of the pre-registration without depending on paywall bypasses,
the policy is:

- **If a β candidate's source document is accessible** (Unpaywall open-access
  URL OR the user has institutional access) — proceed through Methods A + B
  + human verification as normal.
- **If a β candidate's source document is inaccessible** — the CPG is
  **excluded from the β pool** and moved to §5.1 "Deferred" in
  `09_tier_s_preregistration.md`. Its slot is *not* refilled from a lower-
  scoring candidate (no goalpost-move).

This may shrink the β pool from 29 to ~22-27, reducing the total from 48
(43 core + 5 held-out) to ~40-46. Paper discloses the exact exclusion list
and the following claim:

> *"We include all CPGs with accessible source documents. Paywall-only
> guidelines are excluded from the β-tier authoritative pool. This is a
> conservative choice: every included CPG has a reviewer-verifiable source
> quote; no CPG is included based on metadata inference alone."*

**Operational gate**:
1. Run `acquire_source_pdf.py --email <real> --output manifest.md`.
2. Count rows with `status = OPEN_ACCESS` or `MANUAL_UPLOAD_REQUIRED` with
   user-confirmed institutional access. Call this N_accessible.
3. The other 29 − N_accessible β candidates are flagged for §5.1 deferral.
4. `09_tier_s_preregistration.md` is updated with a new commit that moves
   inaccessible CPGs from §3 to §5.1 *before* Methods A + B run. This
   update is a clarification of the accessibility policy, not a list
   change — the pre-registration SHA 8e60cd3e remains the primary citable
   commit.

**Held-out implications**: if either held-out β (aha_acc_aortic_dissection_2022
or aha_asa_ich_2022) is inaccessible, one replacement is pulled from the
top of the accessible β pool to maintain held-out n=5. This single-slot
swap is disclosed with full rationale. All other slots (core β) are not
refilled.

## 2. Method A — LLM-Assisted Source-Quote Extraction

**Purpose**: for every (CPG, criterion C1..C12) pair, produce a verbatim
`source_text` quote that supports the criterion score. Exactly the same shape
as the `source_text` fields in core-25 alpha entries.

**Model**: Qwen3.5-397B at endpoint `http://localhost:8013/v1`
(per `.claude/rules/vllm-launch.md`; read-only host, do not restart).

**Temperature**: 0 (determinism matters for reproducibility).

**Prompt template** (per-criterion, skipping C1/C4 which are metadata-trivial):

```
SYSTEM: You are a clinical-guideline annotator. For criterion {C_NAME} of the
C1-C12 rubric, extract a verbatim quote from the source document below that
supports or refutes the scoring rule. Your reply MUST be a JSON object with
fields {criterion, score, source_text, page_or_section, confidence}. Do not
paraphrase; `source_text` must be an exact substring of the source.

Criterion definition: {C_DEFINITION_FROM_06_DOC}

USER: Guideline: {GUIDELINE_NAME}
DOI: {DOI}

Source document (recommendations, key_sections, tables):
{RAG_CORPUS_PARSED_JSON}

Respond now.
```

**Runtime**: 12 criteria × ~30s/criterion = ~6 min/CPG.
× 29 CPGs = ~2.9 hours of GPU wall-clock (single Qwen 397B endpoint).

**Output path**: `data/cpg_source_properties_candidates_beta_method_a.json` —
a machine-readable file keyed by graph_id. Each criterion's quote is
committed to the repo so a reviewer can diff against `rag_corpus/<id>.parsed.json`
to verify the quote is an exact substring (non-paraphrase guarantee).

## 3. Method B — Dual-LLM Score Agreement

**Purpose**: defend against "LLM A and its maker might be biased the same way"
by scoring each CPG with a second, architecturally different LLM and
measuring inter-rater agreement.

**Models**:
- LLM A: Qwen3.5-397B at 30001 (same as Method A)
- LLM B: GPT-oss-120B at 8013 (local) — confirmed available per
  `.claude/rules/vllm-launch.md` and `configs/agents/clean_slate_*_tooluse.yaml`.

**Prompt template** (same for both, no chain-of-thought — score + evidence
only):

```
SYSTEM: Score criterion {C_NAME} on the scale {C_SCALE} using the definition
below. Return JSON {score, source_text, brief_justification}.

Criterion: {C_DEFINITION_FROM_06_DOC}

USER: Guideline: {GUIDELINE_NAME}
Source: {RAG_CORPUS_PARSED_JSON}
```

Temperature: 0 for both. Max tokens: 256 (force brevity).

**Agreement metric**: Cohen's weighted kappa for ordinal criteria (C2, C4,
C6-C10; scale 0/1/2), Cohen's kappa for binary (C1, C3, C5, C11, C12).
Computed over the 12-criterion vector, then averaged per CPG; aggregate
kappa across 29 CPGs is the headline number for the paper.

**Disagreement handling**:
- |score_A − score_B| == 0: no action.
- |score_A − score_B| == 1: human reviews both quotes, picks one.
- |score_A − score_B| >= 2 or tier flip: flagged `disagreement: high`,
  human reviews the source document directly and writes a tie-break note.

**Runtime**: 12 criteria × 2 models × ~15s = ~6 min/CPG.
× 29 CPGs = ~2.9 hours (models run in parallel so effective = 1.5 hours).

**Output path**: `data/cpg_source_properties_candidates_beta_method_b.json`,
plus `reports/dual_llm_agreement_report.md` (kappa table + disagreement log).

## 4. Scripts (to build in Phase 1)

| Path | Purpose |
|------|---------|
| `scripts/cpg_v2_phase_annotation/acquire_source_pdf.py` | DOI → publisher URL → PDF. Handles Crossref, PubMed; flags paywalled with `MANUAL_UPLOAD_REQUIRED`. |
| `scripts/cpg_v2_phase_annotation/parse_pdf_to_rag_corpus.py` | Wrapper over `semantic_layer/cpg_parser.py`: PDF → rag_corpus-schema parsed.json. |
| `scripts/cpg_v2_phase_annotation/method_a_extract_quotes.py` | Method A runner. Inputs: rag_corpus/*.parsed.json + target graph_id list. Output: `cpg_source_properties_candidates_beta_method_a.json`. Determinism seed: temperature=0. |
| `scripts/cpg_v2_phase_annotation/method_b_dual_llm.py` | Method B runner. Same inputs; outputs per-criterion score from each model + kappa report. |
| `scripts/cpg_v2_phase_annotation/merge_beta_annotations.py` | Combines Method A + B + human adjudication log into final per-CPG entry for `data/cpg_source_properties.json`. |
| `scripts/cpg_v2_phase_annotation/verify_beta_substring.py` | CI check: every `source_text` in beta entries is an exact substring of the corresponding parsed.json content. Runs in the leakage scan suite. |

All scripts follow the repo conventions: `PYTHONPATH=.`, type hints, Google-style
docstrings, ruff-clean.

## 5. Human Verification Protocol

For each of the 29 CPGs:

1. Review Method A output: for every C7-C12 score, confirm the quote is an
   exact substring of the parsed.json source and that the quote supports the
   score. (C1-C6 largely metadata, skimmed.)
2. Review Method B disagreements: any `|score_A - score_B| >= 1` is surfaced
   in `reports/dual_llm_agreement_report.md` for human decision.
3. Sign off by editing `data/cpg_source_properties.json` entry:
   - Set `human_verified_by: <annotator_id>`.
   - Set `verification_date: <ISO-8601>`.
   - If the annotator overrode either LLM score, record the override in
     `verification_notes: "..."`.

Estimated: 3-5 min/CPG × 29 = 1.5-2.5 hours human time total.

## 6. CI Integration

After all 29 CPGs annotated:

```
PYTHONPATH=. python scripts/score_cpg_v2.py \
  --source-props-path data/cpg_source_properties.json \
  --output-prefix cpg_scores_v2_tier_s_2026

PYTHONPATH=. python scripts/cpg_v2_phase_annotation/verify_beta_substring.py
PYTHONPATH=. python scripts/ci/audit_sources.py
PYTHONPATH=. python scripts/ci/leakage_scan.py --dir . --canaries 10
```

All must pass. Commit the result with a descriptive message and a new
pre-registration SHA.

## 7. Failure Modes to Watch

1. **Quote paraphrase drift**: LLM returns a near-verbatim quote that isn't
   an exact substring. Detection: `verify_beta_substring.py` diffs against
   parsed.json. Fix: reject the quote, rerun with a more specific prompt
   hint (e.g., "the quote must appear in the recommendations section").
2. **Dual-LLM collusion by prompt leakage**: LLM B sees a hint of LLM A's
   answer. Mitigation: Methods A and B run on separate parsed.json reads
   with independent LLM sessions; no shared state.
3. **Silent hallucinated tables / scores**: LLM invents a `source_text` that
   looks plausible but is fabricated. Primary defense: exact-substring check.
   Secondary defense: mandatory human spot-check of at least 3 random
   criteria per CPG.
4. **Tier-flip cascade**: after annotation, several bulk CPGs drop below
   Tier S. The pre-registration keeps them in §3 with a `tier_post_annotation`
   flag — no list change. Paper discloses the count.
5. **GPU throughput starvation**: Qwen 397B is a shared resource on 144
   (read-only). If competing load spikes, Method A rate drops. Accepted —
   wall-clock is a soft target, correctness is hard.
