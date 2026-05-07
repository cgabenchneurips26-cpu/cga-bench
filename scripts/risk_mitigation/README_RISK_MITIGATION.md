# CGA-Bench Pre-Clinician Risk Mitigation Suite

## 왜 이것이 필요한가

NeurIPS 2026 제출(5/6)까지 3가지 **논문 reject 가능 위험**이 남아있다:

| 위험 | 심각도 | Clinician 필요? | 코드로 해결 가능? |
|------|--------|----------------|-----------------|
| OMISSION 29.3x surge + enginePrecision=0.217 | 🔴 Critical | 부분적 | **대부분 가능** |
| aba_burn/apa_agitation 98-100% hard violation | 🔴 Critical | 확인 필요 | **원인 특정 가능** |
| All-oblivious FA ~24% approximation (±5pp) | 🟡 High | 불필요 | **완전 해결 가능** |

이 suite는 clinician audit 전에 코드 레벨에서 **최대한 위험을 차단**한다.

---

## 실행 방법

```bash
# CGA-Bench repo root에서:
cp /path/to/scripts/*.py scripts/risk_mitigation/
cp /path/to/scripts/run_risk_mitigation.sh scripts/

# 실행 (에피소드 완료 후)
bash scripts/run_risk_mitigation.sh results/full_706_final

# 또는 개별 실행
python scripts/risk_mitigation/diagnose_omission_surge.py --episodes-dir results/full_706_final
python scripts/risk_mitigation/diagnose_heldout_extremes.py --episodes-dir results/full_706_final
python scripts/risk_mitigation/compute_exact_evaluator_verdicts.py --episodes-dir results/full_706_final
python scripts/risk_mitigation/pre_clinician_constraint_triage.py --episodes-dir results/full_706_final
```

**에피소드 실행 중(7,229개 중간 결과)에도 실행 가능.**
에피소드 완료 후 최종 실행하여 확정 수치를 얻는다.

---

## 각 스크립트가 하는 일

### 1. `diagnose_omission_surge.py` — OMISSION 29.3x 원인 특정

**핵심 질문**: Engine이 지정한 REQUIRED constraints 중 "어떤 모델도 수행하지 않는" 것은 몇 %?

**분석 항목**:
- Violation type 분포 (전체, manual vs auto, graph별, model별)
- **Structural Precision 추정**: 각 REQUIRED action을 모델 수행률로 분류
  - `NEVER_PERFORMED`: 모든 모델이 모든 episode에서 실패 → over-specification 후보
  - `SOMETIMES`: 일부 모델만 수행 → borderline
  - `ALWAYS`: 모든 모델이 수행 → valid constraint
- Graph별 OMISSION 기여도 (Top 3가 50% 이상이면 concentration)
- Clinician에게 보낼 `never_performed_required_actions.csv` 자동 생성

**결과가 말해주는 것**:
- `structural_precision > 0.217` → enginePrecision이 과소평가됨. 논문에서 corrected precision 보고
- `structural_precision < 0.217` → engine이 실제로 over-specify. constraint 수정 필요
- NEVER_PERFORMED가 auto-only에 집중 → engine 로직 버그 가능성

---

### 2. `diagnose_heldout_extremes.py` — aba_burn/apa_agitation 원인 특정

**핵심 질문**: 98-100% hard violation이 "constraint가 너무 엄격"인지 "모델이 진짜 못 하는 것"인지?

**분석 항목**:
- 전 도메인 constraint density 비교표
- aba_burn vs aabb_transfusion(2.8%) 직접 대비
- Violation type breakdown: OMISSION 지배적이면 over-strict, FORBIDDEN 지배적이면 conditional rule 문제
- Model별 action 수 비교: 모든 모델이 8개뿐이면 구조적 문제
- Constraint conflict 자동 탐지 (REQUIRED ∩ FORBIDDEN 충돌)

**결과에 따른 조치**:
- OMISSION 지배 + high density → expected_actions 중 일부를 soft로 전환
- FORBIDDEN 지배 → conditional rule의 condition 검증
- 모든 모델이 비슷한 패턴 → 시나리오/graph 구조 문제
- 논문에서 aggregate 대신 per-domain table 사용

---

### 3. `compute_exact_evaluator_verdicts.py` — FA 근사치 → 정확값

**핵심 질문**: All-oblivious FA가 정말 ~24%인가?

**방법**:
- 각 episode의 actions, expected_actions, violation_events에서
- 5개 evaluator(TOM, ASC, CwT, PAF, TCC) verdict를 독립 재계산
- Exact FA, verdict-flip, BSR, pairwise disagreement 산출
- `auto_numbers.tex` 갱신용 매크로 자동 생성

**한계**: CwT와 PAF의 정확한 penalty 공식을 추정했으므로 ±1-2pp 오차 가능.
`make post-episode`에서 실제 evaluator 코드로 재채점하면 완전 정확.

**결과**:
- `exact_auto_numbers_update.tex` — 바로 paper/auto_numbers.tex에 반영 가능
- `exact_verdict_results.json` — 전체 결과 JSON

---

### 4. `pre_clinician_constraint_triage.py` — Clinician 부담 최소화

**핵심 전략**: 전체 1,049 constraints를 clinician에게 보내는 대신, 코드로 분류하여 **의심 항목만** 검토 요청.

**Triage 분류**:
| Category | 의미 | 조치 |
|----------|------|------|
| `BUG_NOT_IN_EFFECTS` | action_effects.yaml에 없음 | 🔴 즉시 수정 |
| `STRUCTURAL_ZERO_PERFORM` | 모든 모델 실패 | 🟡 precondition 확인 후 clinician |
| `BORDERLINE_LOW` | <25% 모델만 수행 | 🟠 clinician 우선 |
| `BORDERLINE_MED` | 25-50% 모델 수행 | clinician 필요 시 |
| `VALID_MODERATE` | 50-75% 모델 수행 | ✅ likely valid |
| `VALID_HIGH` | 75%+ 모델 수행 | ✅ valid |
| `EASY_ALL_PERFORM` | 모든 모델 수행 | ✅ trivially valid |

**핵심 출력**:
- `clinician_minimal_review.md` — 의사에게 바로 보낼 수 있는 체크리스트
- `auto_fix_suggestions.md` — BUG 항목 수정 가이드
- Corrected Precision 추정 — 논문에 보고할 수 있는 수치

---

## 결과 활용 플로우

```
[스크립트 실행]
     │
     ├─→ BUG 발견됨?
     │     YES → auto_fix_suggestions.md 따라 수정 → 재실행
     │     NO  → 계속
     │
     ├─→ exact FA 계산됨
     │     → exact_auto_numbers_update.tex를 auto_numbers.tex에 반영
     │     → Abstract/Conclusion 매크로 자동 갱신
     │
     ├─→ OMISSION 원인 특정됨
     │     → NEVER_PERFORMED 리스트 확인
     │     → Graph-concentrated이면 해당 graph constraint 조정
     │     → 논문에 precision 한계를 E7 옆에 명시
     │
     ├─→ Held-out 극단 원인 특정됨
     │     → Per-domain table로 논문 수정
     │     → Constraint density 상관관계로 framing
     │
     └─→ clinician_minimal_review.md 생성됨
           → 의사 섭외 시 이 파일만 전달
           → 전체 1,049가 아닌 ~50-100개만 검토
           → Clinician-endorsed precision 계산 가능
```

---

## 논문 반영 전략

### E7 (Engine vs Manual) 문단에 추가할 문장:
```latex
The engine's structural precision---measured as the fraction of 
engine-derived {\sc required} constraints for which at least one 
model performs the action---is \correctedPrecision{}\%.
\numNeverPerformed{} engine-derived {\sc required} actions are 
never performed by any model; clinician review of this subset 
(Section~\ref{sec:clinician_validation}) will determine whether 
these represent genuinely challenging clinical requirements or 
over-specified constraints.
```

### Held-out 문단에 추가할 Table:
```latex
\begin{table}[t]
\caption{Per-domain held-out results. Violation rates vary with 
constraint density (Spearman $\rho$ = \holdoutDensityCorr{}).}
\begin{tabular}{lcccc}
Domain & Constraints & Density & Hard Viol. Rate & Dominant Type \\
\midrule
aba\_burn     & X & Y & 98.6\% & OMISSION \\
apa\_agitation & X & Y & 100\% & ... \\
aabb\_transfusion & X & Y & 2.8\% & ... \\
...
\end{tabular}
\end{table}
```

### Abstract FA 수치:
`\faAllOblivious{}`를 매크로로 쓰고 있으므로,
`exact_auto_numbers_update.tex`의 `\renewcommand`를 반영하면 자동 갱신.

---

## Dependencies

```
Python 3.8+
PyYAML (pip install pyyaml)
```

기본 Python 표준 라이브러리만 사용. 외부 의존성 최소화.
