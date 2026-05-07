# Option C Implementation Plan — Public Audit Artifact (Bold Build)

**Target**: NeurIPS 2026 D&B / Evaluations track paper `paper/main_final_v17.tex` + community-facing release.
**Status**: Planning complete. Coding to be executed on external server.
**Precondition**: **Option B complete and merged** (`option_b_plan.md`). Option C composes on top of Option B's ABC + Bayes script + separating-pair catalogue.
**Total estimated effort**: 4 engineer-days (range 3.5–5). Steps are more parallel than Option B.

> Option B ships the *harness as code*. Option C ships the *harness as a public artifact* — live demo, docs, every external benchmark wrapped, and two novel analyses (repair distance, blind-spot clusters) surfaced as first-class columns.

---

## Motivation (why go beyond Option B)

Option B already establishes the π-class classifier + Bayes floor + separating-pair witnesses + worked examples on 6 evaluators. That alone is a defensible Contribution 4 for the Evaluations track.

Option C answers the **next four skeptic questions** a NeurIPS reviewer will ask:

1. *"Does this 'any evaluator' claim extend to real external benchmarks, not just your own shims?"* → Step C1: all 8 `ExternalBenchmarkAdapter` concrete classes wrapped as `Evaluator`, audited end-to-end.
2. *"BSR is just a scalar. Can you tell me **where** an evaluator is blind?"* → Step C3: blind-spot cluster discovery (domain × constraint-type grid per evaluator).
3. *"Theorem 3.4 talks about 'minimal repair distance d_G' with tiered severity costs — where is that actually computed?"* → Step C2: surface d_G as a live audit column via ILP solver.
4. *"Can I, as a reviewer, just run this on my own evaluator in 30 seconds without cloning the repo?"* → Step C4: Gradio/Streamlit web demo + MkDocs docs, deployable to HF Spaces.

Delivering these turns Contribution 4 from "a CLI + 6 worked examples" into "a public audit service with 14+ evaluators covered, a clickable witness browser, and a living leaderboard" — a qualitatively stronger artifact-track contribution.

---

## What exists at the start of Option C (assuming Option B is merged)

| From Option B | Path | Usable for Option C as |
|---|---|---|
| `Evaluator` ABC + 6 shims | `cga_bench/audit/base.py`, `cga_bench/audit/shims/` | Template for external wrappers (C1). |
| `compute_bayes_error.py` + `_projections.py` | `scripts/audit/` | Used by all subsequent analyses. |
| `separating_pairs.yaml` (20 pairs) | `evidence_pack/separating_pairs.yaml` | Input for C3 blind-spot clustering. |
| `evaluator_audit.py` runbook CLI | `scripts/audit/` | Extension point for C2, C3 columns. |
| `make audit-evaluator` Makefile target | `Makefile` | Composes with new targets. |
| `audit/reports/INDEX.md` | `audit/reports/` | Source for web demo + docs. |

External benchmark adapter ABC (pre-existing, 8 concrete): `semantic_layer/external/base.py`
- Registered adapters: AMEGA, CliBench, MedGUIDE, CancerGUIDE, MTBBench, EHRStruct, LLMEval-Med, NICE.
- Contract: 7 abstract methods returning `NormalizedEpisode`.

---

## Step C1 — Wrap all 8 external benchmarks as `Evaluator` instances

**Goal**: prove the "any evaluator" claim end-to-end by routing each of the 8 existing external benchmark scorers through the Option-B audit harness, unmodified.

**Deliverables**

- `cga_bench/audit/wrappers/__init__.py`
- `cga_bench/audit/wrappers/external.py` (~150 LOC) — one bridge class:

```python
# cga_bench/audit/wrappers/external.py
from cga_bench.audit.base import Evaluator, EvaluatorMeta
from cga_bench.semantic_layer.external.base import ExternalBenchmarkAdapter
from cga_bench.cpg_model.schemas.base import EpisodeLog

class ExternalEvaluatorWrapper(Evaluator):
    """Adapts an ExternalBenchmarkAdapter's native scoring fn into the Evaluator
    contract. The native scorer is treated as a black-box deterministic function."""

    def __init__(self, adapter: ExternalBenchmarkAdapter, score_fn_name: str = "score"):
        self._adapter = adapter
        self._score_fn = getattr(adapter, score_fn_name)
        self.meta = EvaluatorMeta(
            name=adapter.__class__.__name__,
            family=self._infer_family(adapter),
            source=getattr(adapter, "SOURCE_URL", None),
        )

    def verdict(self, ep: EpisodeLog) -> bool:
        # 1. Convert EpisodeLog -> NormalizedEpisode via adapter.parse_to_normalized
        # 2. Pass to the native scorer
        # 3. Threshold at 0.5 (or adapter.PASS_THRESHOLD if defined)
        normalized = self._episode_log_to_normalized(ep)
        raw_score = self._score_fn(normalized)
        threshold = getattr(self._adapter, "PASS_THRESHOLD", 0.5)
        return raw_score >= threshold

    @staticmethod
    def _infer_family(adapter) -> str:
        """Heuristic: AMEGA/HealthBench -> 'TOM', CliBench/MedGUIDE -> 'ASC',
        MedAgentBench -> 'PAF', etc. Allow override via class attribute PI_FAMILY."""
        return getattr(adapter, "PI_FAMILY", "unknown")
```

- `cga_bench/audit/wrappers/registry.py` (~60 LOC) — enumerates all 8 adapters and exposes them as factory callables:

```python
EXTERNAL_EVALUATOR_REGISTRY: dict[str, Callable[[], Evaluator]] = {
    "amega":          lambda: ExternalEvaluatorWrapper(AMEGAAdapter()),
    "clibench":       lambda: ExternalEvaluatorWrapper(CliBenchAdapter()),
    "medguide":       lambda: ExternalEvaluatorWrapper(MedGUIDEAdapter()),
    "cancerguide":    lambda: ExternalEvaluatorWrapper(CancerGUIDEAdapter()),
    "mtbbench":       lambda: ExternalEvaluatorWrapper(MTBBenchAdapter()),
    "ehrstruct":      lambda: ExternalEvaluatorWrapper(EHRStructAdapter()),
    "llmeval_med":    lambda: ExternalEvaluatorWrapper(LLMEvalMedAdapter()),
    "nice":           lambda: ExternalEvaluatorWrapper(NICEAdapter()),
}
```

**Open question / calibration step**: each external scorer returns a different scalar type
(0-1 score, pass/fail, rubric tuple). For each of the 8 adapters, commit a short YAML note
to `cga_bench/audit/wrappers/calibration.yaml`:

```yaml
amega:
  native_output: "rubric_score[0..1]"
  pass_threshold: 0.7
  pi_family_hypothesis: "TOM"   # to be verified by Step 4 of Option B runbook
clibench:
  native_output: "classification_pass[bool]"
  pass_threshold: null
  pi_family_hypothesis: "ASC"
...
```

**Acceptance criteria**
1. `make audit-evaluator AUDIT_EVALS='$(EXTERNAL_EVALS)'` runs end-to-end on all 8
   external wrappers and emits 8 report directories in `audit/reports/external/`.
2. At least 6 of the 8 external wrappers produce a π-class classification consistent
   with their hypothesis in `calibration.yaml`. Discrepancies documented in
   `audit/reports/external/DISCREPANCIES.md`.
3. No modifications to `semantic_layer/external/` — wrappers are pure read-only.
4. Runtime < 2 minutes per wrapper (the verdict cache makes this trivial; heavy adapters
   optionally memoize their score fn).

**Dependencies**: Option B Steps 1–5.

**Estimated time**: 1 day.

**Verification commands**
```bash
PYTHONPATH=. python -c "
from cga_bench.audit.wrappers.registry import EXTERNAL_EVALUATOR_REGISTRY
for name, factory in EXTERNAL_EVALUATOR_REGISTRY.items():
    ev = factory(); print(f'{name:15s} -> {ev.meta}')"
make audit-evaluator AUDIT_EVALS="$(python -c 'from cga_bench.audit.wrappers.registry import *; print(\" \".join(f\"cga_bench.audit.wrappers.registry:{k}\" for k in EXTERNAL_EVALUATOR_REGISTRY))')"
ls audit/reports/external/
```

---

## Step C2 — Minimal-repair distance d_G as a live audit column

**Goal**: Operationalize the paper's ILP-based minimal-repair distance (tiered costs:
FORBID=10, WITHIN=5, BEFORE=3, MUST=1) as a per-episode metric the audit harness exposes.

Currently d_G is described in §3 of the paper but has no standalone script or column in
audit reports. Exposing it closes another reproducibility gap and gives reviewers a
second quantitative angle on evaluator quality ("does the evaluator respect d_G ordering?").

**Deliverables**

- `scripts/audit/repair_distance.py` (~180 LOC) — ILP minimal-repair solver:

```python
def minimal_repair_distance(
    ep: EpisodeLog,
    constraints: list[Constraint],       # FORBID / MUST / BEFORE / WITHIN
    severity_costs: dict[str, int] = {   # paper-committed defaults
        "FORBID": 10, "WITHIN": 5, "BEFORE": 3, "MUST": 1,
    },
    solver: str = "pulp",                # or "ortools"
) -> dict:
    """Formulate as ILP: minimize total severity_cost of constraint flips
    needed to make the trajectory fully compliant. Returns:
      {"d_G": int, "flips": [{"constraint_id": ..., "cost": ...}, ...],
       "solve_time_ms": float, "status": "OPTIMAL"|"INFEASIBLE"}"""
```

- `cga_bench/audit/metrics/repair.py` (~60 LOC) — wraps the solver and caches results per
  `episode_id` to avoid re-solving across evaluators.
- Extension to `scripts/audit/evaluator_audit.py`: add two new columns to `report.json` /
  `report.md`:
  - **Repair-sensitivity correlation**: Pearson ρ between the evaluator's scalar score
    (where available) and d_G. Poor evaluators have ρ → 0; good evaluators have ρ
    strongly negative (lower d_G = better trajectory = higher score).
  - **Monotonicity violations**: count of (ep_a, ep_b) where `d_G(a) < d_G(b)` but the
    evaluator ranks `verdict(a) = harmful, verdict(b) = safe`. Directly reveals
    non-monotonic evaluators.

**Acceptance criteria**
1. `minimal_repair_distance()` returns d_G = 0 for fully-compliant episodes and d_G > 0 for
   all episodes with `v4_hard = True`.
2. On the separating-pair catalogue, d_G correctly orders `expected_verdict_a < expected_verdict_b`
   in ≥ 18/20 pairs.
3. Cached solve time: full corpus (14,826 episodes) solves in ≤ 15 minutes on a laptop.
4. New audit report columns appear in all Option-B and Option-C-C1 worked examples.

**Dependencies**: Option B Step 3 (separating pairs); Option C-C1 not required.

**Estimated time**: 0.5 day.

**Verification commands**
```bash
PYTHONPATH=. python scripts/audit/repair_distance.py \
  --episodes results/full_706_v5/all_episodes.jsonl \
  --graphs cpg_model/graphs/ \
  --out audit/cache/repair_distances.jsonl
PYTHONPATH=. python -c "
import json
with open('audit/cache/repair_distances.jsonl') as f:
    rows = [json.loads(l) for l in f]
print(f'N={len(rows)}, compliant={sum(1 for r in rows if r[\"d_G\"]==0)}, mean_d_G={sum(r[\"d_G\"] for r in rows)/len(rows):.2f}')"
```

---

## Step C3 — Blind-spot cluster discovery (where is each evaluator blind?)

**Goal**: Replace the scalar BSR with a **domain × constraint-type grid** per evaluator,
so reviewers can see *which* clinical settings and *which* constraint types an evaluator
systematically misses.

**Deliverables**

- `scripts/audit/blindspot_clusters.py` (~200 LOC):

```python
def compute_blindspot_grid(
    evaluator: Evaluator,
    corpus: list[EpisodeLog],
    labels: list[bool],
    group_by: list[str] = ["domain", "constraint_type"],
) -> pd.DataFrame:
    """Returns a DataFrame indexed by (domain, constraint_type) with columns:
       N_episodes, N_fn (false-negative count), N_fp (false-positive count),
       BSR_cell, exemplar_episode_id.

    'domain' comes from scenario_id prefix (sepsis / chest_pain / aki / ...).
    'constraint_type' comes from the violation-type the evaluator missed
    (OMISSION / COMMISSION / TIMING / SEQUENCE / DEVIATION).
    """
```

- Markdown heatmap output embedded in each `report.md`:
  - Rows: 25 CPG domains (20 core + 5 held-out).
  - Columns: 5 violation types.
  - Cells: BSR_cell with color-coding (green <5%, yellow 5–20%, red >20%).
- Exemplar links: each red cell links to 1 concrete `episode_id` the reviewer can read.

**Acceptance criteria**
1. For `V4HardShim`, grid is almost uniformly green (< 5% BSR per cell), except a small
   number of known-hard AKI cells.
2. For `DxEMShim` (terminal-only), grid shows systematic red in all TIMING + SEQUENCE cells
   across every domain — matching the paper's `ε̂★_term,timing = 0.429` number.
3. For `ACovShim` (ACov), grid shows red in OMISSION columns but green in COMMISSION columns,
   matching the paper's narrative about coverage metrics.
4. Each red cell has a clickable exemplar `episode_id` in the markdown output.

**Dependencies**: Option B Steps 1–4. Can run in parallel with C1, C2.

**Estimated time**: 1 day.

**Verification commands**
```bash
PYTHONPATH=. python scripts/audit/blindspot_clusters.py \
  --evaluator cga_bench.audit.shims.dxem:DxEMShim \
  --out audit/reports/dxem/blindspot_grid.md
head -30 audit/reports/dxem/blindspot_grid.md
```

---

## Step C4 — Web demo + documentation site

**Goal**: a zero-install reviewer experience. A Gradio Space where a reviewer drops in an
evaluator file (or selects from 14+ shims) and gets a live audit report. Plus a MkDocs
Material site with quickstart, API reference, and contributor guide.

### C4a — Gradio demo (~250 LOC)

**Deliverables**
- `demo/app.py` — single-file Gradio app with three tabs:
  1. **Select evaluator**: dropdown (6 built-in shims + 8 external wrappers + "upload your own .py file").
  2. **Run audit**: button → calls `scripts/audit/evaluator_audit.py` in-process on a
     pre-loaded episode sample (500 episodes, not the full 14,826 for latency).
  3. **Witness browser**: side-by-side view of the top-K false-accept pairs with
     constraint violations highlighted in color.
- `demo/Dockerfile` — reproducible container for HF Spaces.
- `demo/requirements.txt` — pinned: gradio==4.x, all `cga_bench` deps.
- `.github/workflows/deploy-demo.yml` — pushes to HF Space on tag.

**Acceptance criteria**
1. `docker build -t cga-audit-demo . && docker run -p 7860:7860 cga-audit-demo`
   serves a working app at `http://localhost:7860`.
2. Selecting `dxem` and clicking "Run audit" returns a full report within 10 seconds
   (using the 500-episode sample cache).
3. "Upload your own .py file" accepts a file with a class inheriting from `Evaluator`
   and runs it without sandbox violations.
4. Deployed to HF Space at `huggingface.co/spaces/cga-bench/audit-demo`, link committed
   to `README.md`.

**Dependencies**: Option B + C1 + C2 + C3 (needs full feature set in the audit report).

**Estimated time**: 1 day (0.5 day app code + 0.5 day HF Spaces deployment + container tuning).

**Verification commands**
```bash
cd demo && docker build -t cga-audit-demo . && docker run --rm -p 7860:7860 cga-audit-demo
# open http://localhost:7860 and run the dxem audit manually
```

### C4b — MkDocs Material documentation site (~150 LOC config + ~15 markdown pages)

**Deliverables**
- `docs/audit/index.md` — landing page.
- `docs/audit/quickstart.md` — 5-minute install + first audit.
- `docs/audit/api/` — auto-generated from docstrings via `mkdocs-material` + `mkdocstrings`.
- `docs/audit/add-your-evaluator.md` — 5-line shim template + full worked example.
- `docs/audit/worked-examples/` — one page per shimmed/wrapped evaluator (14 pages total).
- `docs/audit/theory.md` — π-class / Bayes floor / separating-pair definitions (linked to paper).
- `mkdocs.yml` at repo root.
- `.github/workflows/deploy-docs.yml` — pushes to GitHub Pages on merge to `main`.

**Acceptance criteria**
1. `mkdocs serve` runs locally without warnings.
2. GitHub Pages site live at `https://cga-bench.github.io/audit/`.
3. Auto-generated API pages cover `Evaluator`, `ExternalEvaluatorWrapper`,
   `minimal_repair_distance`, `compute_blindspot_grid`, all public functions.
4. Quickstart results in a working audit report within 5 minutes of clone + `pip install`.

**Dependencies**: C4a for the "Try the live demo" landing-page link.

**Estimated time**: 0.5 day (mostly wiring; content reuses Option B's worked examples).

**Verification commands**
```bash
pip install mkdocs-material mkdocstrings[python]
mkdocs serve
# open http://localhost:8000
```

---

## Step C5 — Paper integration (Appendix E + links in §4.4 and Contribution 4)

**Goal**: surface Option C's artifacts in the paper without exceeding the 9-page main-body
limit.

### C5a — Appendix E "Extended Evaluator Coverage" (~3 pages)

- **E.1** — Table of 14+ audited evaluators (6 Option-B shims + 8 external wrappers) with
  columns: name, family, π-class, BSR, Bayes floor, Pearson ρ(d_G), red-cell count.
- **E.2** — Three representative blind-spot grids (compact heatmaps).
- **E.3** — Two end-to-end external-adapter worked examples (AMEGA + CliBench).
- **E.4** — Pointer to live demo + docs URLs (archived snapshots committed to
  `anonymous_repo/` for double-blind review; public URLs disclosed at camera-ready).

### C5b — §4.4 extension (~30 additional words, stays within page budget)

Add a final sentence to the existing §4.4 paragraph:

> *"A zero-install Gradio demo (App. E.4) and MkDocs documentation site let reviewers and
> subsequent authors audit their own evaluators without cloning the repo."*

### C5c — Contribution 4 strengthening (replace version from Option B)

> "**An evaluator audit harness and public artifact.** We release `cga_bench.audit` — an
> `Evaluator` ABC, a minimal-repair ILP solver, a blind-spot cluster diagnostic, and a
> plug-in Bayes-error script — alongside a Gradio demo covering 14 audited evaluators
> (6 canonical families + 8 external benchmarks) and a documentation site with a 5-line
> template for adding new evaluators (§4.4, App. D–E)."

### C5d — Reproducibility statement update

Add paths to the reproducibility statement:
- `scripts/audit/repair_distance.py`
- `scripts/audit/blindspot_clusters.py`
- `demo/` (live demo sources)
- `mkdocs.yml` + `docs/audit/` (docs sources)

**Acceptance criteria**
1. Main body stays ≤ 9 pages. Appendix E does not push the submission over NeurIPS's
   total supplementary budget (50 pages).
2. `scripts/ci/audit_citations.py` passes.
3. All URLs in Appendix E are reachable (or have archived snapshots in `anonymous_repo/`).

**Dependencies**: Steps C1–C4 complete.

**Estimated time**: 0.5 day.

**Verification commands**
```bash
cd paper && make clean && make
PYTHONPATH=. python ../scripts/ci/audit_citations.py
```

---

## Execution order and parallelism

```
Option B merged (precondition)
         │
         ├── Step C1 (external wrappers) ─┐
         │                                 │
         ├── Step C2 (repair distance) ────┼── Step C4a (Gradio) ── Step C4b (MkDocs) ── Step C5 (paper)
         │                                 │
         └── Step C3 (blind-spot clusters)─┘
```

Steps C1, C2, C3 are fully independent and run in parallel on day 1.
Step C4a gates on C1+C2+C3 (day 2 afternoon).
Step C4b gates on C4a (day 3 morning).
Step C5 is text-only (day 3 afternoon).

Total wall-clock: **4 engineer-days** (single engineer). **3 days** with two engineers
splitting C1/C2/C3 on day 1 and C4a/C4b on day 2.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| External adapter native scorers have incompatible output types | High | Step C1 calibration YAML explicitly documents each adapter's `PASS_THRESHOLD` and `PI_FAMILY` hypothesis. At least 6/8 must calibrate cleanly; 2 edge cases can be documented in `DISCREPANCIES.md`. |
| ILP solver dependency bloats container size | Medium | Soft-fail: if `pulp` + `ortools` not available, `minimal_repair_distance()` returns `{"status": "SOLVER_UNAVAILABLE"}` and audit report notes the column is disabled. |
| Gradio HF Spaces build fails for double-blind submission | Medium | Stage on a private HF Space during review; public URL in camera-ready. Archive snapshots in `anonymous_repo/` as fallback. |
| Blind-spot grid exposes PHI-like trace content | Low | Audit corpus is already synthetic / de-identified. Re-run `scripts/ci/leakage_scan.py --canaries 200` on all exemplar episodes before release. |
| Docs site fragments reviewer attention from paper | Low | Docs link in Appendix E.4 only; paper body has a single 30-word mention. |
| Reviewer asks "why don't you cover MedAgentBench or more recent 2025 benchmarks" | High | Step C5d's reproducibility statement commits to a post-submission rolling release: new benchmarks added via the 5-line shim template, public issue tracker accepts evaluator submissions. |
| Total file count growth breaks CI | Low | Option C adds ~15 new files, all under `cga_bench/audit/`, `scripts/audit/`, `demo/`, `docs/`. Existing CI patterns already cover these prefixes. |

---

## Files to create / modify (one-stop checklist)

**New files** (Option C adds roughly 1,100 LOC + 15 markdown docs pages + 1 Dockerfile)

- `cga_bench/audit/wrappers/__init__.py`
- `cga_bench/audit/wrappers/external.py` — 150 LOC
- `cga_bench/audit/wrappers/registry.py` — 60 LOC
- `cga_bench/audit/wrappers/calibration.yaml` — 8 entries
- `cga_bench/audit/metrics/__init__.py`
- `cga_bench/audit/metrics/repair.py` — 60 LOC
- `scripts/audit/repair_distance.py` — 180 LOC
- `scripts/audit/blindspot_clusters.py` — 200 LOC
- `demo/app.py` — 250 LOC
- `demo/Dockerfile`
- `demo/requirements.txt`
- `mkdocs.yml`
- `docs/audit/index.md`
- `docs/audit/quickstart.md`
- `docs/audit/add-your-evaluator.md`
- `docs/audit/theory.md`
- `docs/audit/worked-examples/*.md` — 14 pages
- `docs/audit/api/*.md` — auto-generated
- `.github/workflows/deploy-demo.yml`
- `.github/workflows/deploy-docs.yml`
- `tests/test_audit/test_external_wrappers.py`
- `tests/test_audit/test_repair_distance.py`
- `tests/test_audit/test_blindspot_clusters.py`

**Modified files**

- `scripts/audit/evaluator_audit.py` — add Pearson ρ(d_G) + monotonicity-violation columns
- `Makefile` — add `audit-evaluator-external`, `audit-evaluator-all`, `docs-serve`,
  `demo-serve` targets
- `paper/main_final_v17.tex` — §4.4 extension (30 words), Contribution 4 replacement,
  reproducibility-statement paths
- `paper/appendix.tex` — add Appendix E "Extended Evaluator Coverage"
- `README.md` — add "Try the live demo" badge + link to docs site
- `anonymous_repo/README.md` — commit archived snapshots of demo + docs for double-blind

**Do not modify**

- `semantic_layer/external/` — wrappers are pure read-only (acceptance criterion for C1)
- `assessor_core/`, `cpg_engine/`, `agent_runner/` — scorer/agent isolation preserved
- `paper/main_final_v17.tex` §3.4 / §2 P4 / Abstract — Option B's rewording proposals A–D
  remain authoritative; Option C does not re-edit them

---

## Explicitly out of scope (Option D and beyond)

1. **Adversarial-evaluator bounty program** — community-submitted evaluators scored on a
   leaderboard. Needs moderation infrastructure; post-submission.
2. **New scenarios or CPG graphs** — 14,826-episode corpus and 25 guidelines are frozen
   for this submission cycle.
3. **Retraining any model** — audit harness reads verdicts, never trains.
4. **Cross-LLM-judge meta-evaluation** — tempting but doubles the scope; Option D.
5. **FHIR / HL7 live-EHR integration** — reviewer might ask; answer: Task W9 Prong C
   (MIMIC-IV pre-registration) is the path, not Option C.
6. **Mobile or CLI-installer packaging** — defer to `pip install cga-bench-audit` in a
   future release.

---

## Decision gate before starting Option C

Before kicking off Option C, confirm that:

- [ ] Option B is fully merged and `make audit-evaluator` passes CI.
- [ ] `bayes_error_macros.tex` numbers reproduce from `scripts/audit/compute_bayes_error.py`.
- [ ] Paper has been re-read by a reviewer-proxy (e.g. another co-author or Claude in a
      fresh session) to confirm Option B's §4.4 + App. D + Contribution 4 stand on their
      own without Option C. Option C should *amplify*, not *rescue*, the paper.

If any of the three gates fails, pause Option C and close the Option B gap first. Option C
only pays off when the underlying harness is already trustworthy.

---

## Carry-over tasks (unchanged from Option B plan)

- **Task #131** — E3-E5 14,826-ep re-run on updated verdict matrix.
- **Task #150** — P1+ defense integration (X2 placebo, X1 broader, per-type Lemma).
- **Task #173** — Figure 2 v14b Panel C + BEFORE row overflow fix.

These proceed on their own tracks and do not block Option C.
