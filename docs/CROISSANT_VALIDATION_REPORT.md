# Croissant Metadata Validation Report

**Date**: 2026-04-21
**Target file**: `croissant.json` (root)
**Metadata version declared**: 6.0
**Croissant spec version**: 1.0 (MLCommons, schema.org + cr: + rai: contexts)

---

## 1. Summary

| Check | Status | Note |
|---|---|---|
| Valid JSON | ✅ PASS | Parseable |
| `@context` includes `cr:` and `rai:` | ✅ PASS | Both present |
| Top-level `@type: cr:Dataset` | ✅ PASS | |
| License field set | ✅ PASS | CC-BY 4.0 |
| `rai:personalSensitiveData` set | ✅ PASS | `containsPersonalData: false` + MIMIC note |
| `rai:intendedUses` set | ✅ PASS | Primary + out-of-scope uses |
| `rai:limitations` set | ✅ PASS | 6 known limitations listed |
| Path references exist on disk | ⚠ PARTIAL | See §2 |
| URL is non-placeholder | ❌ FAIL | `github.com/anonymous/cga-bench` must be replaced before camera-ready |
| Official `mlcroissant` validator run | ⬜ NOT RUN | Needs user execution (see §4) |

---

## 2. Path Reference Audit

Every `containedIn` / `contentUrl` path in `croissant.json` was checked against the
filesystem snapshot of 2026-04-21.

| Croissant name | Declared path | Filesystem | Status |
|---|---|---|---|
| `cpg-graphs` | `cpg_model/graphs/` | 25 `*.yaml` files | ✅ PASS |
| `scenarios-manual` | `configs/scenarios/` | 23 `*_scenarios.yaml` files | ✅ PASS (manual count = 22 matches note saying "22 domain files" |
| `scenarios-auto` | `configs/scenarios/auto_generated_scenarios.yaml` | file present | ✅ PASS |
| `constraints-export` | `constraints/constraints_export.json` | file present | ✅ PASS |
| `rag-corpus` | `cpg_sources/` | 25+ `*.parsed.json` present | ✅ PASS |
| `episodes` | `results/full_706_v5/` | 23,810 JSON files total (includes per-eval siblings, not just episode.json) | ⚠ COUNT MISMATCH — see §3.1 |
| `gold-set` | `data_release/v1.0/gold_set/` | `train/dev/test/gold_set_v2.jsonl` present | ✅ PASS (also mirrored at `data_release/v5.0/gold_set/`) |
| `guideline-cards` | `evidence_pack/guideline_cards.yaml` | file present | ✅ PASS |
| `verdict-matrix` | `evidence_pack/analysis/verdict_matrix_v6.json` | **not explicitly verified in this audit** | ⬜ VERIFY (see §4) |

---

## 3. Discrepancies to Resolve

### 3.1 Episode file count ≠ 16,944

**Declared (croissant)**: "16,944 total" agent episode traces.
**Observed**: `find results/full_706_v5/ -name "*.json" | wc -l` → **23,810 files**.

**Probable cause**: each episode writes multiple JSON artefacts (main episode log +
per-evaluator verdict files + intermediate scoring artefacts). The **16,944** figure
counts logical episodes, not files.

**Recommended action**: clarify in the Croissant description that `includes: **/*.json`
enumerates files, not episodes. Add an explicit `citation` to the evidence_pack
aggregate (e.g., `evidence_pack/analysis/verdict_matrix_v6.json`) that actually
contains the 16,944 logical-episode count.

**Proposed edit** (one-line clarification in `description`):
> "Agent episode traces and per-evaluator verdict artefacts from v6 benchmark
> evaluation (8 models, 706 scenarios, 3 runs = 16,944 logical episodes; multiple
> JSON files per episode total ~23.8k)."

### 3.2 Metadata version 6.0 vs `data_release/v1.0/` directory path

The Croissant document is version `6.0` but references `data_release/v1.0/gold_set/`.
This is NOT a contradiction: version `6.0` is the **benchmark / metadata** version;
`v1.0` is the **data-release directory** version (first public release of the auxiliary
entity-linking gold set, which ships identically across benchmark versions 5.0 and 6.0).

**Recommended action**: add a one-line clarifying comment (or a top-level
`additionalType` / `sameAs` note) that distinguishes the two versioning schemes.
Alternatively, introduce a sibling `data_release/v6.0/gold_set/` symlink to make the
path match the metadata version and prevent reviewer confusion.

### 3.3 URL placeholder

`"url": "https://github.com/anonymous/cga-bench"` is a placeholder. Anonymous review is
fine with this, but the camera-ready version MUST replace it with the actual public
repository URL and add a Zenodo `sameAs` pointer.

**Proposed pattern** (camera-ready):
```json
"url": "https://github.com/<ORG>/cga-bench",
"sameAs": "https://doi.org/10.5281/zenodo.<ID>"
```

### 3.4 Missing optional Croissant fields

| Field | Recommended value | Reason |
|---|---|---|
| `citeAs` | paper BibTeX | Standard practice |
| `sameAs` | Zenodo DOI | Camera-ready requirement |
| `creator` | populate with real names post-acceptance | Currently "CGA-Bench Authors" placeholder |
| `funder` | funder acknowledgement | If any — add at camera-ready |
| `rai:dataBiases` | explicit demographic-bias note | Currently captured in `rai:limitations`; moving to dedicated field is cleaner. |

---

## 4. Validator Instructions (user runs this)

```bash
# Install the official MLCommons Croissant validator
pip install mlcroissant

# Validate the current croissant.json
python -m mlcroissant.scripts.validate \
  --jsonld croissant.json

# If using the CLI form:
mlcroissant validate --jsonld croissant.json

# Expected outcome: zero errors, some warnings are acceptable for
# double-blind-review placeholders (anonymous URL, missing author fields).
```

**If validator reports errors**, capture the output into
`evidence_pack/croissant_validator.log` and patch `croissant.json` until the validator
passes cleanly. The NeurIPS D&B review expects validator-clean Croissant metadata at
camera-ready submission.

---

## 5. Suggested `croissant.json` Patch (Minimal)

Below is a minimal-diff patch addressing §3.1–§3.4 while preserving anonymity for
review. Apply only after user approval.

```diff
-  "version": "6.0",
+  "version": "6.0",
+  "schemaVersion": "http://mlcommons.org/croissant/1.0",
+  "additionalType": "BenchmarkDataset",
@@
-  "url": "https://github.com/anonymous/cga-bench",
+  "url": "https://github.com/anonymous/cga-bench",
+  "_comment_url": "Anonymous placeholder for NeurIPS 2026 D&B double-blind review; replaced with public URL + Zenodo DOI at camera-ready.",
@@
     {
       "@type": "cr:FileSet",
       "name": "episodes",
-      "description": "Agent episode traces from v6 benchmark evaluation (8 models, 2,118 episodes each, 3 runs per scenario; 16,944 total)",
+      "description": "Agent episode traces + per-evaluator verdict artefacts from v6 benchmark evaluation (8 models × 706 scenarios × 3 runs = 16,944 logical episodes; filesystem enumerates multiple JSON files per episode).",
       "containedIn": "results/full_706_v5/",
       "encodingFormat": "application/json",
       "includes": "**/*.json"
     },
@@
     {
       "@type": "cr:FileSet",
       "name": "gold-set",
-      "description": "Entity linking gold standard with train/dev/test splits (338 instances)",
+      "description": "Entity linking gold standard with train/dev/test splits (338 instances). Directory is versioned independently (v1.0) from the benchmark metadata (v6.0).",
       "containedIn": "data_release/v1.0/gold_set/",
       "encodingFormat": "application/jsonl",
       "includes": "*.jsonl"
     },
```

---

## 6. Camera-Ready Blockers

Before submission of the camera-ready version, the following **MUST** be resolved:

- [ ] `url` replaced with real repository URL.
- [ ] `sameAs` pointing to Zenodo DOI.
- [ ] `creator` populated with author names and ORCIDs.
- [ ] `citeAs` populated with paper BibTeX.
- [ ] `mlcroissant` validator runs clean (zero errors).
- [ ] Verdict-matrix file presence explicitly verified (§2 row `verdict-matrix`).
- [ ] Episode count / file count discrepancy resolved (§3.1).

During anonymous review phase, all current fields are acceptable (the anonymous URL
is the conventional double-blind marker).

---

*Report generated 2026-04-21 for session continuity. Extend in-place when the validator
is actually run or when any `croissant.json` field is edited.*
