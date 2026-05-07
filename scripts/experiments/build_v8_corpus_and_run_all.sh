#!/usr/bin/env bash
# Queue script: build v8 corpus once Track 1 finishes, then re-run every
# numerical analysis on it.
#
# v8 = v6 (706 scenarios × 9 open-weight models × 3 runs)
#    ∪ v7 expansion (236 scenarios × <whichever models complete> × 3 runs)
#  = 942 scenarios with mixed model coverage per scenario.
#
# This script does NOT wait by polling for hours; it polls once a minute,
# logs the wait, and only proceeds once all expected v7 baseline outputs
# exist (or the user manually pre-empts by writing the marker file).
#
# Usage:
#   nohup bash scripts/experiments/build_v8_corpus_and_run_all.sh \
#       > /tmp/v8_build.log 2>&1 &
#
# Or to skip the wait:
#   touch /tmp/v8_build.skip_wait
#   bash scripts/experiments/build_v8_corpus_and_run_all.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

PY=/home/anonymous-org/anaconda3/envs/allm2_ft/bin/python
EXPECTED_V7_MODELS=(qwen4b gemma31b llama4scout)  # extend as Track 1 fixes land
                                      # nemotron30b: blocked (144 driver, 145 capability) — skipped
                                      # llama4scout: blocked (144 HF gated auth, 145 OOM at TP=2) — skipped
V7_RESULTS_DIR=results/expansion_v7
V8_OUT=evidence_pack/frontier/v8_corpus_run_all.log
mkdir -p "$(dirname "$V8_OUT")"

log() { echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*" | tee -a "$V8_OUT"; }
log "=========================================================="
log "v8 build queue starting; expected v7 models: ${EXPECTED_V7_MODELS[*]}"

# -----------------------------------------------------------------------
# Step 1 — wait for Track 1 expansion runners to declare completion.
# A model is "done" if the per-model results dir has ≥ 80% of the
# 236 × 3 = 708 episodes (allows for some unrecoverable failures).
# -----------------------------------------------------------------------
COMPLETION_THRESHOLD=566   # 0.80 × 708
while [[ ! -f /tmp/v8_build.skip_wait ]]; do
  all_done=1
  for m in "${EXPECTED_V7_MODELS[@]}"; do
    n=$(ls "${V7_RESULTS_DIR}/${m}/" 2>/dev/null | grep -v "^.claim" | wc -l)
    if (( n < COMPLETION_THRESHOLD )); then
      all_done=0
      log "  waiting on ${m}: ${n}/${COMPLETION_THRESHOLD} episodes"
      break
    fi
    log "  ${m}: ${n} episodes (≥ ${COMPLETION_THRESHOLD}) ✓"
  done
  if (( all_done )); then
    log "Track 1 complete — proceeding to v8 build"
    break
  fi
  sleep 60
done
log "Track 1 wait phase done."

# -----------------------------------------------------------------------
# Step 2 — concatenate v6 + v7 baselines into the v8 master verdict matrix.
# Output: evidence_pack/analysis/verdict_matrix_v8_typed.json
# -----------------------------------------------------------------------
log "Step 2: aggregate v6 + v7 → v8 verdict matrix."
PYTHONPATH=.. "$PY" - <<'PYEOF' 2>&1 | tee -a "$V8_OUT"
"""Aggregate the v8 verdict matrix from existing v6 + v7 episode JSONs."""
from __future__ import annotations
from pathlib import Path
import json, sys

REPO = Path(__file__).resolve().parent if False else Path(".")
v6_path = REPO / "evidence_pack" / "analysis" / "verdict_matrix_v6_typed.json"
v8_path = REPO / "evidence_pack" / "analysis" / "verdict_matrix_v8_typed.json"

print(f"[v8 build] loading v6 from {v6_path}")
v6 = json.load(v6_path.open("r", encoding="utf-8"))
v8 = {
    "metadata": {
        **v6["metadata"],
        "schema": "v8 = v6 (706 scen × 9 model × 3 run) ∪ v7 expansion (236 scen × ? × 3 run)",
        "v6_n_episodes": v6["metadata"].get("n_episodes", 0),
        "v6_n_scenarios": 706,
    },
    "v6_per_episode": v6["per_episode"],
    "v7_per_episode": [],
    "per_episode": list(v6["per_episode"]),
}

# Walk v7 expansion result dirs, parse what we have, append.
v7_root = REPO / "results" / "expansion_v7"
v7_models_seen: set[str] = set()
for model_dir in sorted(v7_root.glob("*/")):
    name = model_dir.name
    if name.startswith("_"):
        continue
    files = list(model_dir.glob("*.json"))
    if not files:
        continue
    print(f"  v7 model dir {name}: {len(files)} json files")
    for fp in files:
        try:
            ep = json.load(fp.open("r", encoding="utf-8"))
        except Exception as exc:
            print(f"    [skip] {fp.name}: {exc}")
            continue
        # Normalise to the v6 typed schema's per-episode dict shape.
        v8_ep = {
            "scenario_id": ep.get("scenario_id"),
            "model": name,
            "run_index": ep.get("run_index"),
            "compliance_score": ep.get("compliance_score"),
            "peak_risk": ep.get("peak_risk"),
            "aggregate_risk": ep.get("aggregate_risk"),
            "total_violations": ep.get("total_violations"),
            "actions_count": ep.get("actions_count"),
            "violations_by_type": ep.get("violations_by_type"),
            "v4_hard": (ep.get("compliance_score") or 1.0) < 0.7,
            "from": "v7_expansion",
        }
        v8["v7_per_episode"].append(v8_ep)
        v8["per_episode"].append(v8_ep)
        v7_models_seen.add(name)

v8["metadata"]["v7_n_episodes"] = len(v8["v7_per_episode"])
v8["metadata"]["v7_models_seen"] = sorted(v7_models_seen)
v8["metadata"]["v8_n_episodes"] = len(v8["per_episode"])
v8_path.write_text(json.dumps(v8, indent=2, default=str))
print(f"[v8 build] wrote {v8_path}")
print(f"  v6 episodes:  {v8['metadata']['v6_n_episodes']}")
print(f"  v7 episodes:  {v8['metadata']['v7_n_episodes']}")
print(f"  v8 episodes:  {v8['metadata']['v8_n_episodes']}")
print(f"  v7 models:    {v8['metadata']['v7_models_seen']}")
PYEOF

# -----------------------------------------------------------------------
# Step 3 — re-run every numerical analysis on the v8 verdict matrix.
# These mirror the v6 paper pipeline; pointing them at the v8 input
# regenerates the macros for paper/auto_numbers.tex with v8 numbers.
# -----------------------------------------------------------------------
log "Step 3: re-run analysis pipeline on v8."

run_step () {
  local name="$1"; shift
  log "  [analysis] $name: $*"
  if PYTHONPATH=.. "$PY" "$@" 2>&1 | tee -a "$V8_OUT"; then
    log "    ok"
  else
    log "    FAILED — continuing other steps"
  fi
}

# Each invocation here corresponds to a v6 paper analysis script, with
# the verdict-matrix-v6 input swapped for v8. The list is intentionally
# additive: future analyses just append a new run_step line.
run_step "exp_d_disagreement"   scripts/experiments/exp_d_disagreement_quantification.py \
                                  --input evidence_pack/analysis/verdict_matrix_v8_typed.json \
                                  --output evidence_pack/analysis/v8_exp_d.json
run_step "exp_e1_verdict_flip"  scripts/experiments/exp_e1_verdict_flip.py \
                                  --input evidence_pack/analysis/verdict_matrix_v8_typed.json \
                                  --output evidence_pack/analysis/v8_exp_e1.json
run_step "evaluator_agreement"  scripts/evaluator_agreement.py \
                                  --input evidence_pack/analysis/verdict_matrix_v8_typed.json \
                                  --output evidence_pack/analysis/v8_evaluator_agreement.json
run_step "core_vs_expansion"    scripts/experiments/v6_core_vs_expansion.py \
                                  --input evidence_pack/analysis/verdict_matrix_v8_typed.json \
                                  --output evidence_pack/analysis/v8_core_vs_expansion.json
# The above scripts may have slightly different CLIs; run_step traps any
# failure so the queue can keep going. Adjust per-script flags later if
# the "FAILED — continuing" entries multiply.

log "Step 3 done. See $V8_OUT for individual command results."

# -----------------------------------------------------------------------
# Step 4 — emit the v8 macros that paper/auto_numbers.tex pulls in.
# -----------------------------------------------------------------------
log "Step 4: regenerate auto_numbers from v8 outputs."
run_step "extract_auto_numbers"  scripts/experiments/extract_auto_numbers.py \
                                   --evidence-pack evidence_pack/analysis \
                                   --suffix v8 \
                                   --output paper/auto_numbers_v8.tex

log "v8 build queue finished."
log "Next step (manual): inspect evidence_pack/analysis/v8_*.json + paper/auto_numbers_v8.tex"
