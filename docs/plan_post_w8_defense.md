# Post-W8 Defense Experiment Plan

**Status**: W8 완료 대기 중 (direct 632/706, checklist 540/706)
**작성**: 2026-04-19

---

## 1순위 — W8 완료 후 즉시 (컴파일만 필요)

### 1-1. Macro flip (auto_numbers.tex)
- `auto_numbers.tex` 676행의 6개 macro 교체:
  - `{two}` → `{four}`, `{2}` → `{4}`
  - `\scaffoldAOFAMin`, `\scaffoldAOFAMax`, `\scaffoldAOFARange` → 4-scaffold 실측치
- 본문 텍스트 수정 0줄

### 1-2. Scaffold-independence 통계검정 추가
- **입력**: 4 scaffold × 3 model AO-FA 매트릭스
- **검정 1**: Friedman χ² (scaffold across models)
- **검정 2**: pairwise Wilcoxon signed-rank
- **목표**: "range ≤ 3.3 pp" → "Friedman p=..., 모든 pairwise p>..." 로 강화
- **방어 목적**: 리뷰어 C2 (외적 타당도) 공격 선제 차단

---

## 2순위 — 추가 run 필요 (반나절~하루)

### 2-1. Seed variance CI
- **대상 모델**: Qwen3.5-35B + oss120b (2개만)
- **변경**: 3 runs → 6 runs per scenario
- **목표**: AO-FA의 seed-변동 CI 확보, E3 BSR 주장 동시 강화
- **참고**: 전체 8 모델 확장은 비용 대비 효용 낮음

### 2-2. Qwen-specific prompt sensitivity 크로스체크
- **배경**: KNOWN_ISSUES §1-5 prompt 취약성 기록, 본문 footnote 1줄로만 reconcile
- **설계**: Qwen3-4B + Qwen3.5-35B
  - 조건 A: "mandatory-first optional-after" prompt
  - 조건 B: "continue-with-optional" prompt
  - Scope: 2 scaffold × 1 domain (sepsis)
- **목표**: AO-FA 변동 ≤ 2 pp 확인
- **산출물**: Appendix K 한 표
- **방어 목적**: "Qwen이 prompt fragile → AO-FA도 prompt artifact" 공격 봉쇄

---

## 실행 조건
- 1순위: W8 4-scaffold 완료 즉시 (verdict_matrix 생성 후)
- 2순위: 1순위 결과 검토 후 GPU 가용 시
