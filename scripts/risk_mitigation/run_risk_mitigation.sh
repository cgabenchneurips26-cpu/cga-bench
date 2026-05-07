#!/usr/bin/env bash
# =============================================================================
# CGA-Bench Pre-Clinician Risk Mitigation Suite
# =============================================================================
# 
# 3개 핵심 위험을 코드 레벨에서 사전 차단:
#   1. OMISSION 29.3x surge → 원인 특정 + invalid constraint 식별
#   2. aba_burn/apa_agitation 98-100% → constraint density/feasibility 분석
#   3. FA ~24% approximation → exact evaluator verdict 재계산
#
# 실행 방법:
#   cd /path/to/cga-bench-repo
#   bash run_risk_mitigation.sh [--episodes-dir results/full_706_final]
#
# 결과:
#   evidence_pack/omission_audit/       — OMISSION 진단
#   evidence_pack/heldout_audit/        — Held-out 극단 도메인 진단
#   evidence_pack/exact_verdicts/       — Exact evaluator verdicts
#   evidence_pack/constraint_triage/    — Pre-clinician constraint triage
#
# =============================================================================

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
EPISODES_DIR="${1:-results/full_706_final}"
GRAPHS_DIR="${2:-cpg_model/graphs}"
ACTION_EFFECTS="${3:-cpg_model/action_effects.yaml}"

echo "=================================================================="
echo "CGA-Bench Pre-Clinician Risk Mitigation Suite"
echo "=================================================================="
echo "Episodes:       $EPISODES_DIR"
echo "Graphs:         $GRAPHS_DIR"
echo "Action Effects: $ACTION_EFFECTS"
echo ""

# Check if episodes exist
if [ ! -d "$EPISODES_DIR" ]; then
    echo "[ERROR] Episodes directory not found: $EPISODES_DIR"
    echo "  Available directories:"
    ls -d results/full_* 2>/dev/null || echo "  (none)"
    echo ""
    echo "Usage: bash run_risk_mitigation.sh [episodes_dir] [graphs_dir] [action_effects_path]"
    exit 1
fi

# Count episodes
N_EPISODES=$(find "$EPISODES_DIR" -name "*.json" -type f | wc -l)
echo "Found $N_EPISODES episode files"
echo ""

if [ "$N_EPISODES" -lt 100 ]; then
    echo "[WARN] < 100 episodes found. Results may not be representative."
    echo "       Continuing anyway..."
    echo ""
fi

# ─── Script 1: OMISSION Surge Diagnosis ─────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [1/4] OMISSION Surge Diagnosis"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 "$SCRIPTS_DIR/diagnose_omission_surge.py" \
    --episodes-dir "$EPISODES_DIR" \
    --graphs-dir "$GRAPHS_DIR" \
    --output-dir evidence_pack/omission_audit \
    2>&1 | tee evidence_pack/omission_audit/run.log || true

# ─── Script 2: Held-out Extreme Domain Diagnosis ────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [2/4] Held-out Extreme Domain Diagnosis"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 "$SCRIPTS_DIR/diagnose_heldout_extremes.py" \
    --episodes-dir "$EPISODES_DIR" \
    --graphs-dir "$GRAPHS_DIR" \
    --output-dir evidence_pack/heldout_audit \
    2>&1 | tee evidence_pack/heldout_audit/run.log || true

# ─── Script 3: Exact Evaluator Verdicts ─────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [3/4] Exact Evaluator Verdict Recomputation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 "$SCRIPTS_DIR/compute_exact_evaluator_verdicts.py" \
    --episodes-dir "$EPISODES_DIR" \
    --output-dir evidence_pack/exact_verdicts \
    2>&1 | tee evidence_pack/exact_verdicts/run.log || true

# ─── Script 4: Pre-Clinician Constraint Triage ──────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [4/4] Pre-Clinician Constraint Triage"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 "$SCRIPTS_DIR/pre_clinician_constraint_triage.py" \
    --episodes-dir "$EPISODES_DIR" \
    --graphs-dir "$GRAPHS_DIR" \
    --action-effects "$ACTION_EFFECTS" \
    --output-dir evidence_pack/constraint_triage \
    2>&1 | tee evidence_pack/constraint_triage/run.log || true

# ─── Summary ────────────────────────────────────────────────────────
echo ""
echo "=================================================================="
echo "  전체 완료. 생성된 파일:"
echo "=================================================================="
echo ""
echo "  📊 OMISSION Surge:"
echo "     evidence_pack/omission_audit/omission_surge_diagnosis.md"
echo "     evidence_pack/omission_audit/never_performed_required_actions.csv"
echo "     evidence_pack/omission_audit/per_graph_violation_summary.json"
echo ""
echo "  📊 Held-out Extremes:"
echo "     evidence_pack/heldout_audit/heldout_extreme_diagnosis.md"
echo "     evidence_pack/heldout_audit/domain_comparison.json"
echo ""
echo "  📊 Exact Verdicts:"
echo "     evidence_pack/exact_verdicts/exact_verdict_report.md"
echo "     evidence_pack/exact_verdicts/exact_auto_numbers_update.tex"
echo "     evidence_pack/exact_verdicts/exact_verdict_results.json"
echo ""
echo "  📊 Constraint Triage:"
echo "     evidence_pack/constraint_triage/constraint_triage_report.md"
echo "     evidence_pack/constraint_triage/clinician_minimal_review.md  ← 의사에게 전달"
echo "     evidence_pack/constraint_triage/auto_fix_suggestions.md     ← 즉시 수정"
echo "     evidence_pack/constraint_triage/constraint_triage_full.json"
echo ""
echo "  🔴 즉시 확인할 것:"
echo "     1. auto_fix_suggestions.md — BUG 항목 수정"
echo "     2. exact_auto_numbers_update.tex — 매크로 갱신"
echo "     3. clinician_minimal_review.md — 의사 섭외 시 함께 전달"
echo ""
echo "=================================================================="
