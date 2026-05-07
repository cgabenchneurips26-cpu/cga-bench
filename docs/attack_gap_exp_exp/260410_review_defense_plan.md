# CGA-Bench 리뷰 통합 공격 분석 & 방어 설계

> 리뷰 2건 통합, 중복 제거, 우선순위 정렬
> 기준: 리젝 영향도(H/M/L) × 방어 난이도(코드/텍스트/외부)

---

## 공격 지점 통합 테이블 (19건)

| ID | 공격 요약 | R1 | R2 | 리젝 영향 | 방어 유형 | 현재 상태 |
|----|----------|----|----|----------|----------|----------|
| **A1** | Hero FA가 degenerate TOM 포함 intersection — "all three"가 사실상 약한 정의 | ✓ | ✓ | 🔴 H | 코드+텍스트 | ❌ 미방어 |
| **A2** | Clinician validation pending — criterion validity 부재 | ✓ | ✓ | 🔴 H | 외부 | 🟡 protocol만 |
| **A3** | E8 AC-Diag 내부 불일치 — pass rate 74.4%인데 "too few" 표기 | ✓ | ✓ | 🔴 H | 텍스트 | ❌ 버그 |
| **A4** | Artifact mimic ablation이 supporting에 숨어 있음 — artifact necessity 미닫힘 | ✓ | - | 🔴 H | 텍스트 | 🟡 appendix |
| **A5** | External replay = "paradigm-faithful"이지 native scorer 아님 — fidelity 공격 | ✓ | ✓ | 🟠 M-H | 코드+텍스트 | 🟡 부분방어 |
| **A6** | Opening claim 과장 — "most scoring protocols collapse" | ✓ | ✓ | 🟠 M | 텍스트 | 🟡 수정불완전 |
| **A7** | Code/data availability가 E&D 규정 미준수 — desk reject 위험 | ✓ | ✓ | 🔴 H | 텍스트+인프라 | 🟡 부분 |
| **A8** | Solver 7.19% tiered-better — ILP formulation 불완전 의심 | - | ✓ | 🟠 M-H | 텍스트 | 🟡 appendix만 |
| **A9** | First page가 perturbation(E1)에 과의존 — synthetic evidence 우선 인상 | ✓ | - | 🟠 M | 텍스트 | 🟡 부분 |
| **A10** | LLM judge를 hero로 더 승격해야 — DxEM보다 강한 necessity evidence | ✓ | - | 🟡 L-M | 텍스트 | 🟡 intro에 있으나 순서 후방 |
| **A11** | Engine을 first-page hero로 두면 위험 — clinician 전 over-generation 의심 | ✓ | - | 🟠 M | 텍스트 | 🟡 부분 |
| **A12** | Construct-validity 언어가 clinician보다 앞서감 | ✓ | ✓ | 🟠 M | 텍스트 | 🟡 부분 |
| **A13** | Timing-heavy benchmark로 축소 위험 — "fixed-step acute-care" 딱지 | ✓ | ✓ | 🟠 M | 코드+텍스트 | ✅ EX-27 |
| **A14** | E7 서사 과장 — "manual under-specification" claim이 clinician 없이 과함 | - | ✓ | 🟡 L-M | 텍스트 | 🟡 |
| **A15** | Ranking flip over-sell — W=0.408, p=0.99는 null result | - | ✓ | 🟡 L-M | 텍스트 | 🟡 |
| **A16** | Benchmark survey strawman 위험 — 기존 benchmark의 interactive 특성 무시 | ✓ | ✓ | 🟡 L-M | 텍스트 | 🟡 |
| **A17** | 제목 "Actually"가 clinician 전에 과함 | - | ✓ | 🟡 L | 텍스트 | ❌ |
| **A18** | Non-timing trap 추가 필요 — timing 외 blind spot 보강 | ✓ | - | 🟡 L | 코드 | ✅ 354건+4 synthetic |
| **A19** | Cluster/ranking을 first page에서 내려야 | ✓ | ✓ | 🟡 L | 텍스트 | ✅ abstract에서 제거됨 |

---

## 우선순위 그룹별 방어 설계

### 🔴 P0: 리젝 직결 — 반드시 제출 전 해결 (4건)

---

#### A1: Hero FA를 strict non-degenerate intersection으로 강화

**공격**: "all three"에 TOM(degenerate, 100% pass) 포함 → 사실상 ASC ∩ CwT만 의미
**현재**: `\faAllOblivious{11.6}` = TOM + ASC + CwT 동시 통과

**방어 설계**:

```
실험: strict_consensus_fa.py
─────────────────────────────
Input:  evidence_pack/verdict_matrix_v6.json (16,944 episodes)
Output: strict_fa_results.json + macros.tex

계산할 것:
1. ASC ∩ PAF ∩ CwT pass & TCC fail → strictFA3
2. ASC ∩ PAF ∩ CwT ∩ TOM pass & TCC fail → strictFA4 (= 현재 + PAF)
3. 각 intersection의:
   - count, rate
   - critical severity %
   - domain breakdown (top-5)
   - median violations per episode
   - representative 3 trace IDs

보고 형태 (abstract/intro):
"X.X% of episodes (N) pass ALL FOUR non-degenerate process-oblivious
evaluators (ASC, PAF, CwT, and terminal match) while containing hard
guideline violations; restricting to the three action-set evaluators
(ASC ∩ PAF ∩ CwT) yields Y.Y% (M episodes)."

예상 결과:
- strictFA4 ≤ 11.6% (PAF가 추가 필터이므로 같거나 낮음)
- strictFA3 (TOM 제외) ≤ strictFA4
- 핵심: 숫자가 줄어도 0이 아닌 한 claim 성립
```

**텍스트 변경**:
- Abstract: "all three process-oblivious evaluators" → "all four evaluators (including the strictest action-set F1)"
- Intro L66: 두 줄 구조로 분리 (TOM 포함 / TOM 제외)
- 새 매크로: `\strictFAThree{}`, `\strictFAFour{}`, `\strictFAThreeCount{}` 등

**소요**: 1-2h (코드) + 30min (텍스트)

---

#### A3: E8 AC-Diag 내부 불일치 즉시 수정

**공격**: `\crossReplayACPass{74.4}` (pass rate 74.4%)인데 footnote "very low", 본문 "too few"
**원인**: AC-Diag pass rate 매크로가 AC-Proxy(coverage) 값을 잘못 참조하고 있을 가능성

**방어 설계**:

```
진단:
1. crossReplayACPass = 74.4 = passtrateACProxy = 74.4 → 동일값
   → AC-Diag replay가 실제로 diagnosis match를 체크하는지 확인
   → diagnosis match라면 pass rate가 100%(현재 DxEM)에 가까워야
   → coverage check라면 74.4%가 맞지만 "AC-Diag"라는 이름과 불일치

수정 방향 (2가지 중 택1):
Case 1: 74.4%가 맞으면
  - footnote "very low" 삭제
  - "too few for reliable conditional rate" → BSR_cond 계산해서 보고
  - BSR_cond = 42.5/74.4 = 57.1%로 보고 가능

Case 2: 실제 AC-Diag(diagnosis match) pass rate가 다르면
  - 파이프라인에서 실제 값 재계산
  - 매크로 수정
```

**텍스트 변경**:
- Table 6 footnote 수정
- L510 "too few" 문장 수정 또는 삭제
- BSR_cond 값 추가 또는 footnote 정정

**소요**: 30min (확인) + 15min (수정)
**위험도**: 🔴 최우선 — 이 한 줄이 E8 전체 신뢰도를 깨뜨림

---

#### A4: Artifact mimic ablation을 main text table로 승격

**공격**: "왜 기존 benchmark에 좋은 scorer를 붙이면 안 되는가?" 질문에 대한 답이 appendix에 숨어 있음

**방어 설계**:

```
변경: appendix app:artifact_mimic의 Table을 main text로 이동

삽입 위치: E4 (Instrumentation Ablation) 뒤, 또는 E8 앞
  → "E4.5: Artifact-Level Ablation" 또는 Supporting Analyses 첫 번째로

Main text에 올릴 표:
┌──────────────┬──────────┬──────────┬──────────┬──────┐
│ Violation    │ AC-Art.  │ MAB-Art. │ HB-Art.  │ TCC  │
├──────────────┼──────────┼──────────┼──────────┼──────┤
│ FORBIDDEN    │ 20.5%    │ 56.1%    │ 20.5%    │ 100% │
│ WITHIN       │ 18.2%    │ 36.0%    │ 18.3%    │ 100% │
│ BEFORE       │ 0.0%     │ 8.3%     │ 1.9%     │ 100% │
│ MUST         │ 35.8%    │ 48.4%    │ 35.8%    │ 50.3%│
├──────────────┼──────────┼──────────┼──────────┼──────┤
│ Detection    │ 84.2%    │ 63.2%    │ 81%      │ 0%   │
│ loss         │          │          │          │      │
└──────────────┴──────────┴──────────┴──────────┴──────┘

핵심 문장 (main text):
"Even with an ideal scorer, evaluation under the observation level
of existing benchmark artifacts loses 63–84% of hard violations
relative to full trace checking. The bottleneck is the artifact,
not the scoring rule."
```

**텍스트 변경**:
- appendix에서 table 이동 (appendix에는 cross-ref 남기기)
- Intro L70의 detection loss 수치 뒤에 "(Table X)" 참조 추가
- Supporting Analyses에 1 paragraph + 1 table 삽입

**소요**: 1h (텍스트 재배치)

---

#### A7: Code/data availability를 E&D 규정에 정확히 맞추기

**공격**: E&D는 submission 시점에 reviewer-accessible, documented, executable 요구 — desk reject 위험

**방어 설계**:

```
현재 L625:
"released under CC-BY-4.0 at the anonymous repository and dataset
hub included in supplementary materials"

수정:
"All code, CPG graphs, and evaluation pipelines are released under
CC-BY-4.0 and are accessible to reviewers at submission time via
the anonymous repository URL provided in the supplementary materials.
The repository includes a documented Makefile and Dockerfile for
one-command reproduction (make reproduce), pinned dependencies
(requirements.txt with == versions), and pre-registered experiment
configurations. The dataset is hosted on HuggingFace with
MLCommons Croissant metadata (croissant.json)."

핵심 추가 키워드:
- "accessible to reviewers at submission time" (E&D 필수 문구)
- "documented" (E&D 필수 문구)
- "executable" → make reproduce (E&D 필수 문구)
- "final form" 뉘앙스
```

**소요**: 15min (텍스트만)

---

### 🟠 P1: 강한 공격 방어 — 제출 전 권장 (7건)

---

#### A2: Clinician validation — claim downscope 또는 partial result

**공격**: "unsafe according to whom?"

**방어 설계 (2 트랙)**:

```
트랙 A (결과 도착 시):
- partial이라도 30/60 episodes 결과 보고
- P(clinician No | TCC fail), Gwet AC1, severity agreement
- abstract/intro에 "preliminary clinician review confirms X%"

트랙 B (결과 미도착 시):
- claim downscope:
  × "actually follow guidelines" → ✓ "certified as guideline-following"
  × "construct validity" → ✓ "evaluation-design failure / mis-certification risk"
  × "clinically unsafe" → ✓ "nonconformant under published guideline criteria"
- 제목 변경 검토:
  현재: "When Do Clinical AI Agents Actually Follow Guidelines?"
  대안: "When Are Clinical AI Agent Trajectories Certified as Guideline-Following?"
- Section 5 첫 문단에 명시:
  "TCC validity depends on whether its constraints correspond to
  clinically meaningful requirements. We validate along three axes:
  source traceability (100% CPG backing), instrumentation ablation
  (40.9pp gap), and independent physician review (in progress)."
```

**소요**: 30min (텍스트 downscope) 또는 2h (partial result 반영)

---

#### A5: External replay fidelity 강화

**공격**: "paradigm-faithful ≠ native scorer"

**방어 설계**:

```
실험: replay_fidelity_audit.py
─────────────────────────────
10-15 toy traces 설계:
- 3 timing-only (WITHIN 위반, action set 동일)
- 3 ordering-only (BEFORE 위반, action set 동일)
- 3 forbidden-only (FORBID 위반, action set 변경)
- 3 omission-only (MUST 누락)
- 3 mixed

각 trace에 대해:
- expected verdict (ground truth)
- MAB-replay verdict
- AC-replay verdict
- TCC verdict
- 일치/불일치 표시

표 형태:
┌────────┬──────────┬──────────┬──────────┬──────────┐
│ Trace  │ Expected │ MAB-repl │ AC-repl  │ TCC      │
├────────┼──────────┼──────────┼──────────┼──────────┤
│ T1-tim │ Fail     │ Pass     │ Pass     │ Fail     │
│ ...    │          │          │          │          │
│ All    │          │ 12/15    │ 13/15    │ 15/15    │
└────────┴──────────┴──────────┴──────────┴──────────┘

추가: E8 첫 문단에 disclaimer 삽입
"These are replayed scoring paradigms applied to CGA-Bench traces,
not full reproductions of the original benchmark environments."
```

**소요**: 2-3h (코드+텍스트)

---

#### A6: Opening claim 정밀화

**공격**: "most scoring protocols collapse"는 HealthBench/AgentClinic에 대한 strawman

**방어 설계**:

```
현재 (L62):
"yet most scoring protocols still collapse each episode to a
terminal answer or an unordered action set"

수정:
"yet most released scoring protocols do not explicitly preserve the
typed process observables—timing deadlines, execution ordering, and
conditional safety constraints—needed to detect several classes of
clinically meaningful failures"

현재 Abstract 첫 문장:
"Many clinical-agent scoring protocols reduce each episode to a
terminal output or an unordered action set"

수정:
"Many clinical-agent scoring protocols do not preserve timing,
ordering, and patient-state observables, reducing each episode to
a terminal output or an unordered action set"

핵심: "collapse"/"reduce" 주어를 "all benchmarks"에서
"released scoring protocols"로 한정
```

**소요**: 15min

---

#### A8: Solver audit를 main text에서 강화

**공격**: "tiered가 7.19%에서 ILP보다 낫다면 ILP formulation이 불완전"

**방어 설계**:

```
현재 방어: appendix에 solver taxonomy + 0 verdict reversals

추가 필요 (main text L284 또는 Supporting):
"The tiered solver produces a lower-cost repair in 7.2% of episodes,
concentrated in formulation edge cases (65.7%) and phase-ordering
effects (21.8%). Critically, solver choice produces zero verdict
reversals across all 16,944 episodes (ρ = 0.919): the pass/fail
boundary is identical under both solvers, and only the within-episode
cost allocation differs."

핵심 문장:
"Solver choice changes repair costs but not pass/fail verdicts."

이 한 문장이 solver 공격의 대부분을 막음.
이미 데이터 있음 — 텍스트 승격만 필요.
```

**소요**: 30min

---

#### A9: First-page 순서 재배치 — natural prevalence 먼저

**공격**: "E1은 synthetic — natural prevalence가 더 중요한 증거"

**방어 설계**:

```
현재 Intro 순서:
1. sepsis example (L62-64)
2. natural prevalence 11.6% (L66)
3. E1 perturbation (L68)
4. artifact necessity (L70)
5. LLM judge (L70 후반)

권장 순서:
1. sepsis example
2. natural prevalence 11.6% + strict FA + critical severity ← 확대
3. LLM judge T2→T3 gap ← 승격 (A10과 연동)
4. artifact necessity 63-84% ← 승격 (A4와 연동)
5. E1 perturbation ← "The cause is structural" 도입으로 유지하되 순서 하향

핵심: "얼마나 심각한가" → "왜 blind한가" → "고칠 수 있나" 순서
```

**소요**: 1h (intro 재구성)

---

#### A10: LLM judge를 first-page hero로 승격

**공격**: "DxEM은 trivial — 더 강한 baseline은?"

**방어 설계**:

```
현재: Intro L70에서 LLM judge 언급하지만 후반부
수정: Intro L66-67 prevalence 직후에 배치

삽입 문장:
"Even a capable LLM judge (Qwen3.5-35B) falsely accepts 30.7% of
hard-violating episodes when given the full action list; adding
timestamps reduces this to 18.5% (Δ = 12.2 pp), confirming that
the information loss is not recoverable by a stronger scorer."

이것이 DxEM보다 강한 이유:
- DxEM = trivial (100% pass)
- LLM judge = "best possible scorer" proxy
- LLM judge도 action list에서 30.7% FA → scorer 문제가 아님
- T2→T3 gap = observation level 문제의 직접 증거
```

**소요**: 30min (텍스트 이동)

---

#### A12: Construct-validity 언어 downscope

**공격**: "construct validity 주장하면서 clinician 없음"

**방어 설계**:

```
검색 & 치환:
- "construct validity" → 사용 빈도 확인 후 최소화
- 허용: "evaluation-design failure", "mis-certification risk",
        "blind spot", "structural incompleteness"
- Related Work의 construct-validity 인용은 유지 (남의 주장)
- 자기 claim에서는 "construct validity"를 피하고
  "observability failure"로 대체

clinician 결과 도착 시만 "construct validity" 복원
```

**소요**: 15min

---

### 🟡 P2: 추가 강화 — 시간 허용 시 (8건)

| ID | 방어 | 소요 | 방법 |
|----|------|------|------|
| A11 | Engine을 infrastructure로 positioning 유지 | 15min | 텍스트: "supporting infrastructure" 톤 유지 |
| A13 | Timing-heavy 축소 방어 | ✅ 완료 | EX-27 3종 stress test 반영됨 |
| A14 | E7 서사 → "under-specification" 삭제, 결과 중심 기술 | 15min | 텍스트 |
| A15 | Ranking flip → supporting으로 하향, deployment 함의 축소 | 15min | 텍스트 |
| A16 | Survey → "released evaluation protocols"로 범위 한정 | 15min | 텍스트 |
| A17 | 제목 "Actually" → clinician 전에는 대안 검토 | 5min | 텍스트 |
| A18 | Non-timing trap 추가 | ✅ 완료 | 354건+4 synthetic 이미 반영 |
| A19 | Cluster/ranking first page 하향 | ✅ 완료 | abstract에서 이미 제거 |

---

## 방어 실행 체크리스트 (우선순위순)

### Phase 1: 즉시 수정 (텍스트만, 2h)
- [ ] **A3**: E8 AC-Diag 불일치 수정 (매크로 확인 → footnote/본문 정정)
- [ ] **A7**: Code/data availability E&D 규정 문구 수정
- [ ] **A6**: Opening claim "most" → "many released scoring protocols"
- [ ] **A12**: Construct-validity 언어 downscope
- [ ] **A8**: Solver "0 verdict reversals" main text 승격
- [ ] **A14**: E7 "under-specification" → 결과 중심으로
- [ ] **A15**: Ranking flip deployment 함의 축소
- [ ] **A17**: 제목 "Actually" 검토

### Phase 2: 실험+승격 (코드+텍스트, 3-4h)
- [ ] **A1**: Strict non-degenerate FA intersection 계산+보고
- [ ] **A4**: Artifact mimic table main text 승격
- [ ] **A9+A10**: Intro 순서 재배치 (natural prevalence → LLM judge → artifact → E1)
- [ ] **A5**: Replay fidelity audit (toy traces 10-15개)

### Phase 3: 외부 의존 (clinician)
- [ ] **A2**: Partial result 반영 또는 claim downscope 확정

---

## 방어 후 예상 Abstract 골격

```
Many clinical-agent scoring protocols do not preserve timing,
ordering, and patient-state observables. Across 16,944 episodes
(8 models, 25 domains):

[STRICT PREVALENCE]
X.X% of trajectories pass all four process-oblivious evaluators
(including action-set F1) while containing hard guideline violations;
Y.Y% are critical severity.

[OBSERVABILITY]
Even a capable LLM judge falsely accepts 30.7% of hard-violating
episodes from action lists alone; adding timestamps reduces this
to 18.5%.

[ARTIFACT NECESSITY]
The gap cannot be closed by replacing the scorer: under the
observation levels of existing benchmark artifacts, detection
loss reaches 63–84%.

[STRUCTURAL CAUSE]
We prove an Observation-Coarsening Theorem: action-set projections
are provably blind to timing and ordering violations.

[SOLUTION]
CGA-Bench: trace-level conformance auditing with 1,049 typed
constraints from 20 CPG graphs, 706 scenarios, 25 domains.
```

---

## 타임라인

| 날짜 | 작업 |
|------|------|
| 4/11 | Phase 1 텍스트 수정 (A3,A6,A7,A8,A12,A14,A15,A17) |
| 4/12 | A1 strict FA 실험 실행 + abstract/intro 재구성 |
| 4/13 | A4 artifact table 승격 + A9/A10 intro 순서 재배치 |
| 4/14 | A5 replay fidelity audit |
| 4/15 | OpenReview 오픈 — 제출 인프라 시작 |
| 4/16-20 | 인프라 (repo + HF + Croissant) |
| 4/21-30 | A2 clinician 결과 반영 (도착 시) |
| 5/4 | Abstract 제출 |
| 5/6 | Full paper 제출 |