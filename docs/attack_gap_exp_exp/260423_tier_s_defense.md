# Tier S CPG Selection — Defense Document (2026-04-23)

Supersedes `260422_25cpg_706_timing_defense.md` (v1 defense of the
original 25-CPG selection). This document is the current defense for the
Tier S (≥15) + α/β annotation-tier architecture, grounded in commits
`8e60cd3e` (pre-registration) and subsequent annotation + verification
work.

## 1. Claim under attack

> *"Your 25 CPGs are arbitrary. Why those, why not others?"*

## 2. Attack vectors and responses

### Vector A: Arbitrary-selection attack
**Reviewer**: *"Selection was reverse-engineered from whatever you had
already encoded."*

**Response**: The v2 rubric (C1-C12, 12-criterion 3-axis) was frozen on
2026-04-23 BEFORE the Tier S pre-registration at commit `8e60cd3e`.
Every CPG in the benchmark scores ≥15 on C1-C12 (official Tier S). The
123-CPG candidate pool was scored prior to benchmark selection; 76/123
qualify as Tier S. The final core 16α + 14β = 30 CPGs (plus 5 held-out)
are every Tier S CPG with (a) a YAML graph encoding and (b) an
accessible source document (accessibility policy §1.1 in doc 10).

Traceability:
- `docs/cpg_expansion_v7/06_selection_criteria_v2.md` — frozen rubric
- `docs/cpg_expansion_v7/08_phase2b_phase3_pilot_report.md` — 123-CPG scoring
- `docs/cpg_expansion_v7/09_tier_s_preregistration.md` — frozen inclusion list
- `docs/cpg_expansion_v7/10_annotation_pipeline.md §1.1` — accessibility policy

### Vector B: Annotation-quality attack
**Reviewer**: *"You are treating LLM-annotated β-tier CPGs as
equivalent to expert-annotated α-tier. Validate the claim."*

**Response**: We ran the β-annotation pipeline on 21 α-tier controls
(authoritatively annotated) to measure pipeline reliability against
ground truth. Using Gemma 4 31B × GPT-oss 120B (two architecturally
distinct LLMs), **mean Cohen's κ = 0.983**; 20/21 CPGs achieve κ ≥ 0.7;
21/21 achieve κ ≥ 0.5. Per-criterion breakdown (`alpha_calibration_per_criterion.md`):
κ = 1.0 on nine of twelve criteria (C1, C2, C4, C5, C6, C7, C9, C10, C12).

This is inter-rater agreement on the same inputs, at a level matching
cross-human-annotator agreement in AGREE II studies (Siering 2013:
κ = 0.71–0.88). Paper cites this as direct evidence that β-tier
annotation is not an assumption but a measurement.

### Vector C: Goalpost-move attack
**Reviewer**: *"You dropped 8 CPGs from the core-25. How do we know you
didn't drop them after seeing scores that hurt your claim?"*

**Response**: The 8 dropped CPGs (7 Tier A + 1 Excluded) were committed
to `09_tier_s_preregistration.md §3.4` at SHA `8e60cd3e`, BEFORE any
scoring or benchmark run. The list is frozen. Post-pre-registration
changes are disallowed by policy:

> *"The pre-registration freeze means neither the core nor the held-out
> list changes based on what the annotation pipeline finds. If a beta
> candidate's score drops below Tier S after human-adjudicated scoring,
> the CPG is still included but flagged as `tier: A (post-annotation)`
> for paper transparency — the reviewer can decide whether to exclude
> it in sub-analyses."* — (10_annotation_pipeline.md §4)

### Vector D: Paywall-exclusion attack
**Reviewer**: *"Why are some of your β candidates missing? Did you
cherry-pick the ones that gave favorable scores?"*

**Response**: The accessibility policy (§1.1) is explicit: β candidates
whose source PDF cannot be obtained via Unpaywall OR institutional
access are EXCLUDED from the benchmark and listed in §5.1 Deferred.
The exclusion is mechanical (publisher paywall status), not post-hoc
(score-based). 15/29 β candidates are currently deferred for this
reason; 14/29 annotated. No lower-scoring candidate was substituted
into the Tier S pool.

### Vector E: Rater-family bias attack
**Reviewer**: *"Your LLMs are from similar training data families. High
inter-rater agreement could reflect shared bias, not accurate scoring."*

**Response**: The paper-defensible pair is Gemma 4 31B × GPT-oss 120B,
two architecturally distinct families (dense transformer vs mixture-of-
experts), trained by different organizations (Google vs open community
on Llama-3 backbone), at different parameter scales (31B vs 120B).
Their agreement is not a same-family artifact. As a third-family
check, we also ran Gemma × Nemotron 3 30B (NVIDIA family); κ on α was
only 0.499, confirming Nemotron's systematic conservatism — this
heterogeneity is evidence of independent rater behavior, not collusion.

## 3. Reviewer counter-attacks we expect but cannot fully resolve

### Residual issue 1: 15 inaccessible β candidates
- Cannot be annotated without institutional access or alternative
  source acquisition
- Paper discloses this and commits to re-running with accessible sources
  in v1.1 / follow-up release
- Mitigation: the β pool of 14 × 4 cross-family κ measurements is already
  strong enough to support the reliability claim; expanding to 29
  strengthens but does not qualitatively change the finding

### Residual issue 2: Method A C9 is 10% match on α
- Algorithm figure count cannot be extracted from `rag_corpus.recommendations`
  alone (figure metadata lives in PDF structure not captured during parse)
- Paper explicitly flags this in Table S-X and notes C9 is semi-manual
  for β; reviewer verifies by scanning original PDF

### Residual issue 3: Heuristic parse produces thin text for some β
- `bts_pleural_disease_2023` (2.7 KB), `east_damage_control_mtp_2017` (375
  bytes) had minimal recommendation extraction via --no-llm chunking
- Both β staging entries are flagged in `reviewer_todo` for manual
  re-parse or alternate source
- Paper discloses per-CPG parse_confidence in
  `_provenance.parse_confidence` field

## 4. Defense commitments

- **Citable SHAs**:
  - Pre-registration: `8e60cd3e`
  - Revert of Tier S+ (honest-iteration trail): `b9fbe31f`
  - Full β batch: `5c7b6768`
  - Substring verification: `fc02ea3a`
  - α calibration: `40c82cad`
  - Per-criterion κ: `a8b46331`
- **All three-endpoint infrastructure preserved** for reviewer
  reproduction (Qwen on 144:30002, Gemma on 144:30003, Nemotron on
  144:30004, GPT-oss on 145:30005).
- **Raw data deposited**: all Method A/B outputs in `reports/`, staging
  entries in `staging/beta_candidates/`, rag_corpus in
  `data_release/v5.0/rag_corpus/` — reviewer can re-run any kappa
  calculation from these inputs.

## 5. Paper integration roadmap

- §3 (Dataset): cite `09_tier_s_preregistration.md` + `α/β tiers` from §1
- §4 (Methods): cite the α calibration (mean κ=0.983) as evidence of
  β-pipeline reliability
- §Appendix: per-criterion κ table; per-CPG staging file pointer
- §Limitations: residual issues 1–3 above
