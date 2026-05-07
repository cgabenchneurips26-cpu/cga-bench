# v6 Full — Outstanding Macros Rerun Plan

**Date**: 2026-04-28
**Scope**: ~21 paper macros NOT yet recomputed on Phase B because they belong
to separate experiments. Many already have data; only aggregation needed.

---

## TL;DR

| Group | # Macros | Data exists? | Effort | Compute | GPU? |
|---|---:|---|---|---|---|
| W8 cross-scaffold | ~13 | ✅ all 24 cells exist (full_706_v6_scaffolds_20260422_1022) | aggregate-only | 5 min CPU | no |
| Held-out (8 models) | ~5 | 🟡 7/8 complete, qwen397b 23/199 | aggregate + 1 partial rerun | 30 min CPU + 2 GPU-h | yes (1 model) |
| Constraint precision (`\prec*`) | 5 | 🔴 needs engine-vs-manual audit | new script + run | 10 min CPU | no |

**Total compute**: ~45 min CPU + ~2 GPU-hour (only for qwen397b heldout completion).
**Total wallclock**: ~3–4 hours including writing aggregation scripts.

---

## Group A — W8 Cross-Scaffold Macros (~13 macros)

### Current paper macros at risk
```
\wEightTotalEpisodes{8,472}      ← from 706×3runs×4(model,scaffold) cells
\wEightNPerCell{706}
\wEightAggReactAOFA{19.5}
\wEightAggDirectAOFA{17.5}
\wEightAggChecklistAOFA{19.0}
\wEightAggToolUseAOFA{19.1}
\wEightAggAOFAMin/Max/Range
\wEightFriedmanChi{1.0} \wEightFriedmanP{0.80} \wEightKendallW{0.11}
\wEightComplianceMin/Max/Spread
\wEightQwenTUActions/PassAC/PassMAB/PassCGA/FA
```

### Existing data
`results/full_706_v6_scaffolds_20260422_1022/` has **24 cells** (8 models × 3
scaffolds: react/direct/checklist/tooluse — wait, 3 scaffolds but 4 macros
imply 4 scaffolds. Let me check).

Actual scaffolds in dir: `direct`, `checklist`, `tooluse`. The
`\wEightAggReactAOFA` macro likely refers to the default `react` scaffold from
Phase B v6b (which IS effectively "react" since `full_v6b/{model}/` files have
no scaffold suffix → react default). So 4 scaffolds across 2 dirs:
- `full_v6b/{model}/` = react (default)
- `full_706_v6_scaffolds_20260422_1022/{model}_{checklist,direct,tooluse}/` = the other 3

### Recommended approach
**Don't change W8 macros** — they're already aggregated on full Phase A scope
and the W8 experiment is *by design* scoped to 706 manual scenarios. Adding
auto_v2 scenarios would be a different experiment ("W8-Phase-B"), not an
update of W8.

If user wants Phase B-scope W8 (76,464 ep × 4 scaffolds = ~305,856 ep), that's
a major GPU experiment requiring 8 models × 3 NEW scaffolds × 2480 auto_v2
scenarios × 3 runs = **178,560 additional episodes**. At Phase B's 53.5 ep/min
× 11 parallel runners ≈ **5 days** of GPU compute on the existing fleet. Not
recommended for v1 paper.

### Decision
**Action: NONE.** W8 macros remain valid for the W8 experiment's documented
scope. Add `% W8 retained at Phase A scope (706 scenarios) — see appendix
methods` annotation. Mark in paper §Methods that "W8 cross-scaffold replication
uses the original 706 manual scenarios per cell".

### Cost: 0 GPU, 5 min editing.

---

## Group B — Held-out Subset (~5 macros)

### Current paper macros at risk
```
\heldoutFARate{87.3}
\heldoutFlipRate{87.4}
\heldoutCompliance{0.586}
\indomainFARate{45.4}
\indomainCompliance{0.546}
\heldoutFisherP{0.0}
```

### Existing data
`results/heldout_v1/` has 8 model dirs:

| Model | n_episodes | Status |
|---|---:|---|
| oss120b | 200 | ✓ |
| deepseek_r1_7b | 199 | ✓ |
| gemma31b | 199 | ✓ |
| nemotron30b | 199 | ✓ |
| qwen27b | 199 | ✓ |
| qwen35b | 199 | ✓ |
| qwen4b | 199 | ✓ |
| **qwen397b** | **23** | **🔴 incomplete (was supposed to be ~199)** |

### Recommended approach
Two options:

#### Option B1 — Recompute on existing 7 complete models (no GPU)
- Drop qwen397b or impute from its Phase B episodes
- Re-aggregate via `scripts/experiments/heldout_aggregator.py` (find or write)
- Compare to current macros; flag if shifted
- **Cost: 30 min CPU, 0 GPU**

#### Option B2 — Complete qwen397b heldout run (with GPU)
- 199 - 23 = **176 missing episodes**
- qwen397b is on 144:30001/30002 endpoint (currently up)
- Heldout runner already supports incremental (atomic claims)
- Single command: `python scripts/experiments/heldout_runner.py qwen397b results/heldout_v1`
- At Phase B's 53.5 ep/min × 4 workers ≈ **45 minutes**
- Then re-aggregate
- **Cost: 30 min CPU + ~45 min × 4 workers GPU = 3 GPU-hours on 144**

#### Decision
Recommend Option B2 (complete qwen397b) — gives canonical 8-model heldout
with paper-consistent macros. The 144 endpoint is already running.

### Output macros (new)
Same names retained (`\heldoutFARate` etc.) — comments updated.

---

## Group C — Constraint-Type Precision (`\prec*`, 5 macros)

### Current paper macros at risk
```
\precForbidden{??}
\precRequired{??}
\precBefore{??}
\precWithin{??}
\precAll{??}      (used in main_final_v17:337 as "manual-overlap fraction")
```

### Semantics
Per `paper/appendix.tex:402–407`, these reflect **engine-derived constraint vs
manual constraint match rate** by constraint type. Counts already exist:
- `\numExtraForbidden{927}`, `\numExtraRequired{3066}`, `\numExtraBefore{0}`,
  `\numExtraWithin{888}`, `\numExtraAll{4881}`

The `prec*` values would be the *fraction* of engine-derived constraints that
manually-authored scenarios also encode (or vice versa). The audit needs:
1. List of all engine-derived constraints from Phase B's 31 Tier S+ CPGs
2. List of all manually-authored constraints from the 706 manual scenarios
3. Match each engine constraint against manual set → precision per type

### Existing data + script
- Engine constraints: extractable from `cpg_model/graphs/auto_v2/*.yaml`
- Manual constraints: extractable from `configs/scenarios/*_scenarios.yaml`
- No existing `audit_constraint_precision.py` script — need to write

### Recommended approach
**Option C1 — Write new audit script** (`scripts/ci/audit_constraint_precision.py`)
- Extract engine constraints from CPG YAMLs by type (FORBIDDEN/REQUIRED/BEFORE/WITHIN)
- Extract manual constraints from scenario YAMLs
- Compute Jaccard or coverage per type
- Emit `\prec*` macros
- **Cost: 2 hours engineering + 5 min compute, 0 GPU**

**Option C2 — Skip + remove from paper**
If the paper's appendix table can drop the precision column without losing the
argument, just remove `\prec*` references and keep `\numExtra*`.
- **Cost: 30 min editing**

#### Decision
Recommend Option C1 — paper's appendix references this metric explicitly. Cost
is reasonable; output is reusable for future audits.

---

## Execution order (3-phase plan)

### Phase 1 — Pure aggregation, no GPU (Day 1, ~30 min)

```bash
# 1.1 — Re-aggregate W8 with documentation update only (no recompute needed)
# Just add \cite{w8_methods} note to paper:
#   "W8 cross-scaffold replication uses the original 706 manual scenarios per cell"

# 1.2 — Aggregate held-out 7-of-8 (drop qwen397b temporarily)
# Find or write: scripts/experiments/aggregate_heldout.py
# Compute \heldoutFARate*, \heldoutFlipRate*, \indomainFARate, \heldoutCompliance
# Output: evidence_pack/analysis/v6_full_heldout.json

# 1.3 — Update paper macros to reflect 7-model heldout temporarily
# Mark with comment: "% v6 heldout (7/8 models — qwen397b run pending)"
```

### Phase 2 — Constraint precision audit (Day 1, ~2 hours)

```bash
# 2.1 — Write audit script
cat > scripts/ci/audit_constraint_precision.py <<'EOF'
"""Engine-vs-manual constraint match audit per type.
For each of {FORBIDDEN, REQUIRED, BEFORE, WITHIN}:
  - Engine set: union over CPG YAMLs (graphs/, graphs/auto/, graphs/auto_v2/)
  - Manual set: union over configs/scenarios/*.yaml constraint blocks
  - Precision = |engine ∩ manual| / |engine|
  - Recall = |engine ∩ manual| / |manual|
Emit:
  evidence_pack/analysis/constraint_precision.json
  evidence_pack/tables/constraint_precision.tex (\prec* macros)
EOF

# 2.2 — Run + update paper macros
PYTHONPATH=. python3 scripts/ci/audit_constraint_precision.py
# Replace \prec*{??} → computed values in paper/auto_numbers.tex
```

### Phase 3 — qwen397b heldout completion (Day 2, ~3 GPU-hours on 144)

```bash
# 3.1 — Verify 144 qwen397b endpoint healthy
sudo -n -u anonymous-org ssh [email-redacted] \
  'curl -sf -m 3 -H "Authorization: Bearer sk-no-key-required" http://localhost:30001/v1/models'

# 3.2 — Resume qwen397b heldout run (atomic claim respects existing 23 episodes)
PYTHONPATH=. nohup python scripts/experiments/heldout_runner.py qwen397b \
  results/heldout_v1 \
  --launcher_host 127.0.0.1 --launcher_port 30001 \
  > /tmp/heldout_qwen397b_resume.log 2>&1 &

# 3.3 — Wait for completion (target n=199); then re-aggregate
# At 53.5 ep/min × 4 workers (144:30001+30002) → 176/214 ≈ 0.8 hour
# Re-run: scripts/experiments/aggregate_heldout.py
# Update paper macros: \heldoutFARate, \heldoutFlipRate, etc. (8-model canonical)

# 3.4 — Update auto_numbers.tex comments to "% v6 heldout (canonical, 8 models)"
```

---

## Risk + mitigations

| Risk | Mitigation |
|---|---|
| W8 reviewer attack ("why 706 not 76,464?") | Explicit §Methods note: "W8 scope by design = 706 manual scenarios; cross-scaffold replication argument doesn't depend on auto_v2 scenarios" |
| Heldout qwen397b rerun fails (144 endpoint dies) | Phase 1 with 7-model holdover macros; Phase 3 optional. Or impute qwen397b heldout FA from its Phase B held-out CPGs (toxicology, aha_acc_aortic_dissection, etc.) |
| `\prec*` audit reveals very low precision (e.g. <30%) | This would be a paper-level finding worth its own §Discussion paragraph; not a blocker. Frame as "engine derives more constraints than manual scenarios encode" — already implied by `\numExtra*` counts. |
| qwen397b heldout episodes have different scenarios than other 7 models | Heldout scenarios are CPG-specific, not model-specific. All models run same scenario set. |

---

## Decision matrix — what to ship in v1 paper

| Macro group | "Ship as-is" risk | Effort to fix | Recommended path |
|---|---|---|---|
| W8 (~13) | Low — scope clearly documented | 5 min note | **Ship as-is + §Methods note** |
| Heldout (~5) | Medium — 7/8 incomplete | 3 GPU-h | **Phase 1 (7-model interim) → Phase 3 (canonical) before camera-ready** |
| `\prec*` (~5) | High — `??` placeholder is reviewer red flag | 2 hours | **Phase 2 mandatory before submission** |

### Total minimum effort to clean v1 submission
- **Mandatory**: Phase 2 (constraint precision audit) — 2 hours, 0 GPU
- **Recommended**: Phase 1 (heldout 7-model interim) — 30 min, 0 GPU
- **Optional**: Phase 3 (heldout canonical) — 3 GPU-hours

If user authorizes the GPU work on 144 (qwen397b is already up), all 21 macros
are addressable within **a single afternoon**. Total ~5–6 hours wallclock.

---

## Outputs after rerun

```
evidence_pack/analysis/
  ├── v6_full_heldout.json              ← Phase 1
  └── constraint_precision.json         ← Phase 2

evidence_pack/tables/
  ├── v6_full_heldout.tex               ← Phase 1: \heldout* macros
  └── constraint_precision.tex          ← Phase 2: \prec* macros

scripts/
  ├── experiments/aggregate_heldout.py  ← Phase 1 (new, ~80 LOC)
  └── ci/audit_constraint_precision.py  ← Phase 2 (new, ~150 LOC)

paper/
  └── auto_numbers.tex                  ← updated with computed values
```

---

## Reproducibility once complete

```bash
# Full Phase B + outstanding pipeline
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject

# Step 1: Phase B core (already done)
$PYTHONPATH python3 scripts/experiments/verdict_matrix_v5.py
$PYTHONPATH python3 scripts/experiments/recompute_typed_verdicts.py ...
$PYTHONPATH python3 scripts/experiments/recompute_v6_full_macros.py
$PYTHONPATH python3 scripts/experiments/recompute_v6_full_extras.py
$PYTHONPATH python3 scripts/experiments/recompute_v6_full_severity.py

# Step 2: Outstanding (this plan)
$PYTHONPATH python3 scripts/experiments/aggregate_heldout.py
$PYTHONPATH python3 scripts/ci/audit_constraint_precision.py

# Step 3: Compile paper
cd paper && pdflatex main_final_v17.tex
```

---

## User decision needed

Choose one of:

1. **Minimal cleanup (Phase 2 only, 2h CPU)** — write constraint precision
   audit; ship W8 + heldout as-is with §Methods notes. Paper has zero `??`
   placeholders.

2. **Recommended (Phase 1 + 2, 3h CPU)** — also re-aggregate heldout from
   existing 7/8 models; macros updated but qwen397b held-out has only 23
   episodes (acknowledge in caption).

3. **Canonical (Phases 1 + 2 + 3, 3 GPU-hours + 3h CPU)** — complete
   qwen397b held-out run; full 8-model canonical macros; paper hero claim
   "76,464 + 199×8 held-out episodes". Cleanest defensive posture.

Recommend Option 3 for NeurIPS rebuttal-strength; Option 2 if GPU-time is
tight; Option 1 only if camera-ready deadline imminent.
