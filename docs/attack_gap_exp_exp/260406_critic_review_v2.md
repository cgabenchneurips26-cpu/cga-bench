# CGA-Bench 전면 공격-방어 매트릭스 v6 (2026-04-06)

---

## 1. E8 Adapter 해결 방안

Action coverage 9.1%, Avg actions 1.5는 환경 비호환성. 3가지 해결책:

**방안 A: "Safety-by-inaction" 증거로 전환 (30분, 텍스트만)**

E8 section에 추가: "An agent generating 1.5 actions/scenario receives Safety=99% — because committing no actions commits no violations. This illustrates the complementary failure: safety-focused evaluators cannot distinguish safe-by-inaction from safe-by-compliance. Only MUST constraints detect clinically dangerous omissions."

**방안 B: Domain-matched 재실행 (8h, GPU 1개)**

AgentClinic 논문 Table 2에서 CGA-Bench와 겹치는 도메인(pneumonia, chest pain, sepsis) 추출 → CGA-Bench 환경 + CGA-Bench 프롬프트로 정상 실행 → TCC + AC-style 모두 채점. 이것은 "외부 benchmark case에서도 같은 blind spot."

**방안 C: AgentClinic 공개 trace 직접 scoring (4h)**

AgentClinic GitHub repo에서 example traces 확보 → TCC로 scoring → 외부 데이터에서도 violation 발견.

**권장: A(즉시) + B(시간 여유 시)**

---

## 2. 전체 실험 목록

### 완료 (12개)

| ID | 실험 | 결과 | 상태 |
|----|------|------|------|
| EX-1 | LLM Judge (2 judges × 4 prompts × 4 levels) | T2→T3: 23.9%→4.8%, P4 no bias, gemma31b cross-validation | ✅ |
| EX-2 | Observability Ladder | 78.4%→0%, 1,812 timing-only episodes | ✅ |
| EX-3 | Scorer Fidelity | 7/7 fidelity, CwT penalty insufficient | ✅ |
| EX-4C | Jitter Sensitivity | 1.25% flip at ±30min | ✅ |
| EX-4D | Margin Distribution | 34.1% genuine, 59% urgent, 18% parallelizable | ✅ |
| EX-5 | Engine Precision Taxonomy | 21.7%→62.3%→+3.6pp | ✅ |
| EX-6 | Provenance Sanity | max Δ=2.3pp | ✅ |
| EX-7 | Held-out Breakdown | 5 domains, 1,259 ep | ✅ |
| EX-12 | Regression Harness | 8/8 pass | ✅ |
| EX-13 | Ranking as Consequence | χ²=20.0, W=0.473, 71.4% reversal | ✅ |
| EX-15 | Constraint-Type Ablation | 11.7pp from TIMING/SEQUENCE | ✅ |
| EX-16 | Source Traceability | 100% (1,306 constraints) | ✅ |

### 미완료 — Tier 0 (마감 전 필수, 4개)

| ID | 실험 | 공격 | 비용 | 의존 |
|----|------|------|------|------|
| — | Re-scoring (전체 14,826 ep) | OMISSION accuracy | 4h | 에피소드 완료 |
| — | auto_numbers 최종 (62/62) | ?? placeholder | 1h | re-scoring |
| — | E3-E5 재실행 (14,826 ep) | sample size 180 | 4h | re-scoring |
| EX-14 | Reproducibility Pack | desk rejection | 8h | 코드 정리 |

### 미완료 — Tier 1 (accept 크게 향상, 9개)

| ID | 실험 | 공격 | 비용 | GPU |
|----|------|------|------|-----|
| EX-17 | Solver Agreement (tiered vs ILP) | solver conflation | 2h | ❌ |
| EX-18 | Artifact Mimic (AC/MAB-like mode) | 왜 새 artifact | 3h | ❌ |
| EX-20 | No-Context Matched Pair | conditional-safety (Thm Case 4) | 2h | ❌ |
| EX-4A | Clock Sweep (2/5/10/15/20 min) | timing = clock | 4h | ❌ |
| EX-4E | Action-Class Duration | uniform step 비현실 | 2h | ❌ |
| EX-4F | Parallelizable Batching | serialization artifact | 2h | ❌ |
| EX-4G | Zero-Cost Reasoning | reasoning도 시간 먹음 | 1h | ❌ |
| — | Medical Model (OpenBioLLM-70B) | medical model이면 해결? | 24h | ✅ |
| — | Reasoning Model (DeepSeek-R1-32B) | reasoning이면 해결? | 24h | ✅ |

### 미완료 — Tier 2 (논문 강화, 8개)

| ID | 실험 | 공격 | 비용 | GPU |
|----|------|------|------|-----|
| EX-19 | Native Scorer Fidelity (30-50 examples) | proxy unofficial | 4h | ❌ |
| EX-9 | Scaffold Ablation (3 scaffolds × 2 models) | single scaffold | 24h | ✅ |
| EX-10 | Witness-Based Patch Loop (50 ep) | grading only, no improvement | 12h | ✅ |
| EX-8B | E8 Domain-Matched Adapter | cross-benchmark replay뿐 | 8h | ✅ |
| — | GPT-4o 50 Episodes | open model artifact | API | ❌ |
| — | Bug-Fix Invariance Matrix | pipeline unstable | 1h | ❌ |
| — | E7 Paired Delta (ΔFA, McNemar, CI) | engine inflation | 2h | ❌ |
| — | Held-out All-Oblivious FA | held-out = parsing only | 1h | ❌ |

---

## 3. 공격 21개 — 방어 상태 + 해결 방안

### 🔴🔴 Desk-Reject급

| # | 공격 | 상태 | 해결 | 비용 |
|---|------|------|------|------|
| 1 | 이론-실험 불일치 (abstract/intro) | ✅ | 수정완료 | — |
| 2 | numBefore=0 accounting | ✅ | 65 교정완료, merge 확인 | 5분 |
| 3 | Clinician validation 부재 | 🔄 | 응답 시 Section 6 채우기 / 미도착 시 wording 하향 | 1h |

### 🔴 Major Revision급

| # | 공격 | 상태 | 해결 | 비용 |
|---|------|------|------|------|
| 4 | Solver exact/tiered conflation | ✅ 문장 | EX-17 scatter + stats | 2h |
| 5 | ?? placeholder (57/62) | 🟡 | re-scoring → auto_numbers 최종 | 1h |
| 6 | Code/data availability E&D 규정 | ⬜ | EX-14 Reproducibility | 8h |
| 7 | First-page synthetic 치우침 | ✅ | Abstract prevalence first | 30분 |
| 8 | Engine precision 0.217 | ✅ | 3-level framing, main에서 raw 안 노출 | 20분 |
| 9 | Artifact necessity 미닫힘 | 🟡 | EX-18 Artifact Mimic | 3h |
| 10 | External scorer overclaim | ✅ | 용어교체 완료, EX-19로 강화 | 4h |
| 11 | Timing dominance / clock artifact | 🟡 | EX-4A + 4E + 4F + 4G 전체 bundle | 9h |
| 12 | Engine = inflation machine | ✅ | EX-16 100% traceability | — |
| 13 | OMISSION/DEVIATION accuracy | 🟡 | re-scoring + invariance matrix | 5h |
| 14 | E3-E5 sample size (180ep) | ⬜ | 14,826ep 재실행 | 4h |

### 🟡 Minor Revision급

| # | 공격 | 상태 | 해결 | 비용 |
|---|------|------|------|------|
| 15 | Construct validity 과잉 언어 | ✅ | "patient-safety" → "hard guideline violation" | 15분 |
| 16 | FORBIDDEN/SEQUENCE under-activated | 🟡 | EX-20 No-Context Pair | 2h |
| 17 | DxEM trivial | ✅ | EX-1 (2 judges) | — |
| 18 | Held-out = parsing only | 🟡 | all-oblivious FA 추가 | 1h |
| 19 | Model diversity | 🟡 | Medical + Reasoning + GPT-4o | 48h+API |
| 20 | Single scaffold | Limitations | EX-9 (시간 여유 시) | 24h |
| 21 | Appendix 미완성 (P2/P3) | 🟡 | 2-judge table 완성 | 30분 |

---

## 4. 즉시 수정 (코드/실험 불필요, 논문 텍스트만)

| # | 항목 | 비용 | 상태 |
|---|------|------|------|
| 1 | auto_numbers 마침표 매크로 30개 삭제 | 10분 | 🔄 진행중 |
| 2 | auto_numbers 중복 블록 20개 삭제 | 5분 | 🔄 진행중 |
| 3 | auto_numbers EX-1 pop-weighted 통일 | 5분 | ⬜ |
| 4 | auto_numbers solver 매크로 3개 추가 | 2분 | ⬜ |
| 5 | 1,677 vs 1,812 확인 | 10분 | ⬜ |
| 6 | "patient-safety" → "hard guideline violation" grep/교체 | 15분 | ⬜ |
| 7 | Code availability 문구 E&D 규정 적합화 | 10분 | ⬜ |
| 8 | Abstract 순서 재검토 (prevalence → perturbation → theorem) | 30분 | ⬜ |
| 9 | E6 cluster discussion 압축 (2문장) | 20분 | ⬜ |
| 10 | Mixed-effects exposition 1문장으로 | 10분 | ⬜ |
| 11 | Ranking flip Conclusion에서 한 줄 | 10분 | ⬜ |
| 12 | Engine precision main story에서 빼기 | 15분 | ⬜ |
| 13 | bsrCGA 코멘트 "ground truth" → "structural" | 1분 | ⬜ |
| 14 | Appendix P2/P3/P4 LLM Judge table 완성 | 30분 | ⬜ |
| 15 | E8 "safety-by-inaction" 문단 추가 | 30분 | ⬜ |
| 16 | gemma31b judge variance → "LLM judge unreliable" 추가 | 20분 | ⬜ |

---

## 5. 방어 완성도

```
현재:  ✅ 11/21 (52%) | 🟡 7/21 (33%) | ⬜ 2/21 (10%) | 🔄 1/21 (5%)
목표:  ✅ 19/21 (90%) | 🟡 1/21 (5%)  | 🔄 1/21 (5%)

닫아야 할 🟡 → ✅ 전환 7개:
  re-scoring → auto_numbers → E3-E5 (3개 일괄)
  EX-17, EX-18, EX-20, EX-4A bundle (4개)
  Medical + Reasoning model (시간 투자 대비 최대 impact)

유일한 열린 공격: Clinician validation (외부 의존)
```