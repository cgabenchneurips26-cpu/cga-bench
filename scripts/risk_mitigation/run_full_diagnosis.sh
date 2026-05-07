#!/usr/bin/env bash
# =============================================================================
# CGA-Bench Full Risk Mitigation + Deep Diagnosis
# =============================================================================
# 실행 순서:
#   Phase 1: 기존 4개 진단 (omission, heldout, exact verdict, triage)
#   Phase 2: 심층 진단 (B1-B10 버그 전수조사)
#   Phase 3: 수정 생성 (missing action_effects + rename patches)
# =============================================================================

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
EPISODES="${1:-results/full_706_final}"
GRAPHS="${2:-cpg_model/graphs}"
AE="${3:-cpg_model/action_effects.yaml}"

echo "══════════════════════════════════════════════════════════"
echo " CGA-Bench Full Risk Mitigation Suite"
echo "══════════════════════════════════════════════════════════"
echo " Episodes: $EPISODES"
echo " Graphs:   $GRAPHS"
echo " Effects:  $AE"
echo ""

mkdir -p evidence_pack/{omission_audit,heldout_audit,exact_verdicts,constraint_triage,deep_diagnosis,fix_actions}

# ═══ Phase 1: 기존 진단 ═══
echo "━━━ Phase 1: Core Diagnostics ━━━"

echo "[1/6] OMISSION Surge..."
python3 "$DIR/diagnose_omission_surge.py" \
    --episodes-dir "$EPISODES" --graphs-dir "$GRAPHS" \
    --output-dir evidence_pack/omission_audit 2>&1 | tail -5

echo "[2/6] Held-out Extremes..."
python3 "$DIR/diagnose_heldout_extremes.py" \
    --episodes-dir "$EPISODES" --graphs-dir "$GRAPHS" \
    --output-dir evidence_pack/heldout_audit 2>&1 | tail -5

echo "[3/6] Exact Evaluator Verdicts..."
python3 "$DIR/compute_exact_evaluator_verdicts.py" \
    --episodes-dir "$EPISODES" \
    --output-dir evidence_pack/exact_verdicts 2>&1 | tail -5

echo "[4/6] Constraint Triage..."
python3 "$DIR/pre_clinician_constraint_triage.py" \
    --episodes-dir "$EPISODES" --graphs-dir "$GRAPHS" --action-effects "$AE" \
    --output-dir evidence_pack/constraint_triage 2>&1 | tail -5

# ═══ Phase 2: 심층 진단 ═══
echo ""
echo "━━━ Phase 2: Deep Diagnosis (B1-B10) ━━━"

echo "[5/6] Deep Pipeline Diagnosis..."
python3 "$DIR/deep_pipeline_diagnosis.py" \
    --episodes-dir "$EPISODES" --graphs-dir "$GRAPHS" --action-effects "$AE" \
    --output-dir evidence_pack/deep_diagnosis 2>&1 | tail -10

# ═══ Phase 3: 수정 생성 ═══
echo ""
echo "━━━ Phase 3: Fix Generation ━━━"

echo "[6/6] Generate Missing Action Effects..."
python3 "$DIR/generate_missing_action_effects.py" \
    --graphs-dir "$GRAPHS" --action-effects "$AE" \
    --triage-json evidence_pack/constraint_triage/constraint_triage_full.json \
    --b1-renames evidence_pack/deep_diagnosis/b1_rename_suggestions.json \
    --output evidence_pack/fix_actions 2>&1 | tail -10

# ═══ Summary ═══
echo ""
echo "══════════════════════════════════════════════════════════"
echo " 완료. 수정 실행 순서:"
echo "══════════════════════════════════════════════════════════"
echo ""
echo " 1. B1 Renames 확인 + 적용:"
echo "    cat evidence_pack/deep_diagnosis/b1_rename_suggestions.json"
echo "    python evidence_pack/fix_actions/apply_renames.py cpg_model/graphs"
echo ""
echo " 2. Deep diagnosis CRITICAL/HIGH 확인:"
echo "    cat evidence_pack/deep_diagnosis/fix_list_priority.json | python -m json.tool | head -50"
echo ""
echo " 3. Missing action_effects 검토 + merge:"
echo "    cat evidence_pack/fix_actions/new_action_effects.yaml"
echo "    # 검토 후 cpg_model/action_effects.yaml에 append"
echo ""
echo " 4. 테스트 + 재실행:"
echo "    python -m pytest tests/ -x"
echo "    # 에피소드 재실행"
echo ""
echo " 5. 논문 매크로 갱신:"
echo "    cat evidence_pack/exact_verdicts/exact_auto_numbers_update.tex"
echo ""
echo " 6. Clinician 검토 요청:"
echo "    cat evidence_pack/constraint_triage/clinician_minimal_review.md"
echo "══════════════════════════════════════════════════════════"
