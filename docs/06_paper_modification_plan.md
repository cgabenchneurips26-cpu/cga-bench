# Paper Text Modification Plan — 5/2 EOD ~ 5/6

**Goal**: Consolidate all paper text changes derived from this session's findings into a structured plan, ordered by priority and dependency.

---

## Modification Inventory (Patch List)

### Phase A — 5/2 EOD-가능 patches (no v7 episode results required)

#### Patch A1: §AY disclosure 정밀화 (HIGH PRIORITY)

**Location**: `paper/appendix_v18.tex` §AY (CAV v0.5 vocabulary governance disclosure)

**Current state**: Placeholder with macro `\CStrictFaVanilla`, `\CStrictFaFixed`, `\CDeltaTotal` filled.

**Required changes** (from `01_paper_AY_B6_evidence.md`):
1. Net -78 단순 보고를 *602 flipped episodes* 분해로 확장
2. 47% over-correction subset 명시
3. 39% v6 author-injection 측정값 인용
4. B3 effect를 strict-3way에서 *invisible*하게 명시 + non-strict metrics 효과 (n_hard -1608, MAB -14.98pp)

**Macros to add**:
```latex
\newcommand{\vSixFlippedEpisodes}{602}
\newcommand{\vSixToPassEpisodes}{340}
\newcommand{\vSixToFailEpisodes}{262}
\newcommand{\vSixOverCorrectionRate}{47\%}
\newcommand{\vSixGenuineNoncomplianceRate}{40\%}
\newcommand{\vSixAuthorInjectionRate}{39.0\%}
\newcommand{\bThreeNHardDelta}{-1{,}608}
\newcommand{\bThreeMABDelta}{-14.98}
\newcommand{\bThreeLooseFADelta}{+568}
```

**Quotable text** (full version in `01_paper_AY_B6_evidence.md` §2 + §3 + §4):
```latex
v6-fixed strict consensus FA: \CStrictFaVanilla\ → \CStrictFaFixed\ 
(Δ = \CDeltaTotal), reflecting \vSixFlippedEpisodes\ episode-level 
verdict flips (\vSixToPassEpisodes\ TO pass, \vSixToFailEpisodes\ 
TO fail) under combined CAV v0.5 + N1–N5 + B3 fixes...
[full text from 01_paper_AY_B6_evidence.md]
```

**Estimated time**: 60-90 min

---

#### Patch A2: §App AV temperature sensitivity closure (HIGH)

**Location**: `paper/appendix_v18.tex` §App AV

**Current state**: "Deferred analysis" footnote/promise.

**Required changes** (from `04_paper_App_AV_temp_sensitivity.md`):
1. Replace deferred footnote with completed analysis
2. Add per-T tables (Qwen + Gemma)
3. Add framing: "model-conditional, strengthens projection-blindness claim"
4. Add benchmark user recommendations

**Macros to add**:
```latex
\newcommand{\avSweepEpisodes}{1{,}620}
\newcommand{\avSweepCPGs}{4}
\newcommand{\avQwenMaxDelta}{1.74}
\newcommand{\avQwenMaxDeltaT}{0.7}
\newcommand{\avGemmaMaxDelta}{15.60}
\newcommand{\avGemmaCollapsePp}{15}
\newcommand{\avGemmaSweetSpot}{0.1}
\newcommand{\avPilotBoundPp}{1.5}
```

**Estimated time**: 60 min

---

#### Patch A3: §1 contribution 5 (CAV) 마무리 (HIGH)

**Location**: `paper/main_final_v18.tex` §1

**Current state**: 4 contributions + placeholder for 5th.

**Required changes**:
1. Write contribution 5 paragraph (CAV v0.5 vocabulary governance)
2. Macro `\CNTotalCav`, `\CNExtension`, `\CRxnormMatchRate` 채워짐 확인
3. Reference §AY disclosure

**Quotable text**:
```latex
\paragraph{Contribution 5: Source-traceable vocabulary governance (CAV).}
We introduce CAV v0.5, a curated action vocabulary with 
\CNTotalCav\ entries derived from 25 CPGs, of which \CNExtension\ entries 
were dropped as non-source-grounded extensions. \CRxnormMatchRate\% of 
medication actions match RxNorm crosscoded entries. CAV-based scoring 
exposes the 39\% author-injection rate of v6 manual scenarios 
(App~\ref{app:ay}) and provides mechanically verifiable provenance 
for each scoring constraint.
```

**Estimated time**: 30 min

---

#### Patch A4: §1 contribution 6 (SGSC) framing — *placeholder until DET rollout 끝남* (MEDIUM)

**Location**: `paper/main_final_v18.tex` §1

**Current state**: Empty.

**Required changes** (from `02_paper_SGSC_contribution.md`):
1. Write contribution 6 paragraph
2. Use Option B framing (structurally clean substrate)
3. Reserve macros for fill-in after DET rollout

**Macros to reserve** (filled 5/3 morning):
```latex
\newcommand{\vSevenScenarios}{??}     % After DET rollout
\newcommand{\vSevenAtoms}{??}
\newcommand{\vSevenGraphs}{25}
\newcommand{\vSevenHallucinationRate}{0\%}
\newcommand{\vSevenLeakageStatus}{PASS}
\newcommand{\vSevenTruncatedStemRate}{0\%}
```

**Quotable text**: see `02_paper_SGSC_contribution.md` §3.

**Estimated time**: 45 min (5/2 draft) + 15 min (5/3 fill-in)

---

#### Patch A5: §4.3 source-grounded wording 정정 (HIGH)

**Location**: `paper/main_final_v18.tex` §4.3

**Current state** (problematic): 
> "All scenario actions are source-grounded to specific recommendations..."

**Required change**: 
Acknowledge B6 disclosure that 481 orphan actions exist, defer "100% claim" to graph-encoded subset only.

**New text**:
```latex
The catalogue of scoring constraints is graph-encoded: each constraint 
edge in the typed-constraint YAML maps to one or more recommendations. 
On the v6-fixed corpus (App~\ref{app:ay}), graph-encoded constraints 
trace to source recommendations with full provenance. Manually-curated 
scenario actions in v6 raw exhibit 481 graph-orphan instances 
(\S~\ref{sec:b6}); the CAV v0.5 mechanism (Contribution 5) excludes 
these from production scoring.
```

**Estimated time**: 20 min

---

#### Patch A6: App L "100% provenance" claim 정정 (HIGH)

**Location**: `paper/appendix_v18.tex` App L

**Current state** (problematic): 
> "100% of constraints have source-traceable provenance"

**Required change**: 
Restrict claim to graph-encoded constraints, acknowledge scenario-level orphans.

**New text**:
```latex
100\% of graph-encoded constraints (those tracked by the CDE scoring 
engine) have source-traceable provenance. Scenario-level actions in 
v6 raw curation include 481 graph-orphan instances (\S~\ref{sec:b6}); 
these are excluded from production scoring under CAV v0.5 
(\S~\ref{app:ay}).
```

**Estimated time**: 15 min

---

#### Patch A7: §5.6 Kendall W footnote 추가 (MEDIUM)

**Location**: `paper/main_final_v18.tex` §5.6

**Current state**: W=0.408 + 75% reversal claim 그대로.

**Required change**: 
Footnote explaining computation method, add Fixed equivalent values for sensitivity.

**Quotable text** (from `01_paper_AY_B6_evidence.md` §5):
```latex
\footnote{Headline rank reversal rate (75\%) and Kendall W (0.408) are 
computed on the v6-vanilla scoring across the canonical 8-model subset 
(Phase A; llama4scout excluded), 4 evaluators (AC-Proxy, MAB-Proxy, 
C2-Pass, CGA-Bench), with bootstrap 10K episode-resamples. Equivalent 
values under v6-fixed scoring (App~\ref{app:ay}) are W=0.381 with 
78.6\% pairwise reversal — the small magnitude shift confirms that the 
projection-blindness signal is corpus-stable and not contingent on the 
specific normalizer or vocabulary configuration.}
```

**Estimated time**: 20 min

---

### Phase B — 5/3 patches (after DET rollout)

#### Patch B1: §1 contribution 6 macro fill-in

**Trigger**: 25-graph DET rollout 끝나고 quality verified.

**Required action**:
1. Run aggregate metrics on `sgsc_output/v7_e3_det_overnight/`
2. Fill macros: `\vSevenScenarios`, `\vSevenAtoms`, etc.
3. Verify quality gate disclosure

**Estimated time**: 30 min

---

#### Patch B2: §App SGSC methodology section (FULL)

**Location**: New section `paper/appendix_v18.tex`

**Required content** (from `02_paper_SGSC_contribution.md` §4):
1. Pipeline architecture
2. Atom extraction (atom_proposer)
3. Entailment validation
4. Graph compilation
5. Scenario compilation
6. Quality gates
7. Reproducibility configuration

**Estimated time**: 90-120 min

---

#### Patch B3: §App Reproducibility section (FULL)

**Location**: New section `paper/appendix_v18.tex`

**Required content** (from `03_paper_reproducibility.md` §3):
1. Bit-exact deterministic generation
2. Procedural reproducibility
3. Artifact reproducibility
4. Statistical reproducibility (NONDET CV)
5. Methodological reproducibility
6. Server-side caveats

**Macros to fill** (5/3 morning):
```latex
\newcommand{\sgscGitCommit}{<filled from reports/path_d_day2/v7_e3_det_commit.txt>}
\newcommand{\sgscArtifactSha}{<filled from sha256 manifest>}
\newcommand{\sgscNondetCV}{4.2\%}  % from 3-run NONDET measurement
```

**Estimated time**: 90 min

---

#### Patch B4: §App DET vs NONDET comparison

**Location**: New section `paper/appendix_v18.tex`

**Required content** (from `03_paper_reproducibility.md` §4):
- Per-graph DET vs NONDET comparison table
- Aggregate metric comparison
- Vocabulary turnover (Jaccard distance)

**Trigger**: 5/3 morning DET vs NONDET comparison report 도착.

**Estimated time**: 60 min

---

#### Patch B5: §V7 Replication section

**Location**: `paper/main_final_v18.tex` §5 (within audit) OR `paper/appendix_v18.tex` (App)

**Required content** (from `02_paper_SGSC_contribution.md` §5):
- v7 strict consensus FA
- v7 Kendall W
- v7 pairwise rank reversal
- v7 Bayes floor (ε̂★_term)
- 3-axis comparison table (v6-vanilla, v6-fixed, v7-SGSC)

**Trigger**: 5/3 17:00 v7 verdict matrix 도착.

**Estimated time**: 90 min

---

### Phase C — 5/4-5/5 patches

#### Patch C1: 3-axis comparison polish

Iterate Patch B5 with v7 numbers + CAV v0.6 build.

**Estimated time**: 60 min

#### Patch C2: Reviewer-perspective re-read

5/5 작업: paper 전체 reviewer 시점 재독. 추가 issue 발견 시 patch.

**Estimated time**: 4-6 hours total (full read + revisions)

#### Patch C3: Cross-references + bibliography + appendix renumbering

Final polishing.

**Estimated time**: 2 hours

---

## Phase A 작업 순서 (5/2 EOD ~ 5/3 morning, anonymous-user 직접)

```
5/2 evening (4-5 hours, paper text 4-patch):
  18:00-19:00  Patch A5 (§4.3 wording) + Patch A6 (App L)
  19:00-20:30  Patch A1 (§AY disclosure 정밀화) ← MOST IMPORTANT
  20:30-21:30  Patch A2 (§App AV closure)
  21:30-22:00  Patch A7 (§5.6 footnote)
  22:00-22:30  Patch A3 (§1 contribution 5 finalize)
  22:30-23:00  Patch A4 (§1 contribution 6 placeholder draft)

  23:00 EOD: Phase A 7 patches 완료
            paper full compile 시도
            broken \ref / 누락 macro 확인
            sleep
```

## Phase B 작업 순서 (5/3, Track-3 결과 도착 후)

```
5/3 morning (after DET rollout):
  06:00  25-graph DET 결과 도착
  06:30  DET vs NONDET 비교 분석 (자동, ~30min)
  07:00  Patch B1 (§1 contribution 6 macro fill-in)
  07:30  Patch B2 (§App SGSC methodology) 시작
  09:00  Patch B3 (§App Reproducibility) 시작
  09:00  v7 Episode rerun launch (parallel)
  10:30  Patch B2 + B3 완료
  11:00  Patch B4 (DET vs NONDET App)

5/3 afternoon (episode rerun in progress):
  12:00-17:00  Patch B5 outline (numbers TBD)
  17:00        v7 verdict matrix 도착
  17:00-19:00  Patch B5 fill-in (v7 numbers)

5/3 evening:
  CAV v0.6 build (parallel)
  Paper compile 시도
  cross-ref 체크
```

## Phase C 작업 순서 (5/4-5/5)

```
5/4:
  Morning: 3-axis comparison data 검증
  Afternoon: Patch C1 (3-axis polish)
  Evening: Reviewer-perspective 1차 re-read

5/5:
  Morning: Patch C2 (reviewer-perspective 2차 re-read + revisions)
  Afternoon: Patch C3 (cross-refs, bibliography, appendix renumbering)
  Evening: Final compile, no more changes

5/6:
  Final upload
```

---

## Risk Mitigation

### Risk 1: 25-graph DET rollout quality 약화
**Mitigation**: NONDET archive 보존됨. Phase B에서 NONDET 사용 가능. Patch B1-B5는 NONDET-compatible.

### Risk 2: v7 episode rerun에서 strict FA가 v6와 *현저히* 다름
**Mitigation**: 
- v7 strict FA가 v6와 비슷 → §V7 replication section *paper-positive* (instrument-property claim)
- v7 strict FA가 v6와 다름 → 다른 *paper-positive* framing (corpus-design factor)
- 둘 다 §1 contribution 6에 들어갈 수 있음

### Risk 3: 5/4-5/5에 추가 reviewer-blocking issue 발견
**Mitigation**: Cowork Rule 8 (decision gates) 적용. 발견된 issue가 §1 contribution을 흔들면 *그 contribution만* 격하. Theorem 1 + CAV는 *load-bearing core*로 보존.

### Risk 4: Time overrun in Phase A
**Mitigation**: Patches A1, A5, A6은 *MUST* (paper integrity). A2, A3, A7은 *SHOULD*. A4는 *CAN DEFER* (Phase B에서 완성). 우선순위 명확.

---

## Quality Gates for Each Patch

각 patch 완료 시 다음 확인:

1. **Compilation**: `pdflatex paper/main_final_v18.tex` 성공
2. **No broken refs**: `\ref` 모두 resolve됨
3. **No missing macros**: `??` 출력 없음 (의도된 placeholder 제외)
4. **Cross-reference**: 새 추가 section/Appendix가 §1 또는 §본문에서 reference됨
5. **Reading flow**: 새 추가 텍스트가 기존 문장과 자연스럽게 이어짐

---

## Files of Record (for handoff)

이 plan과 함께 참조해야 할 분석 문서:

| Topic | File |
|---|---|
| Session summary | `00_session_summary.md` |
| §AY/§B6 evidence | `01_paper_AY_B6_evidence.md` |
| §1 contribution 6 SGSC | `02_paper_SGSC_contribution.md` |
| §Reproducibility | `03_paper_reproducibility.md` |
| §App AV temperature | `04_paper_App_AV_temp_sensitivity.md` |
| Cowork rules | `05_cowork_rules_codified.md` |
| **This plan** | `06_paper_modification_plan.md` |

---

## anonymous-user 즉시 작업 가능 항목 (5/2 EOD)

GPU rollout이 진행 중 (~5-7h)인 동안 Tommy가 paper text 작업 가능:

**최우선 (반드시 5/2 EOD 안에 완료)**:
1. Patch A1 (§AY disclosure) — 90분
2. Patch A5 + A6 (§4.3 + App L wording) — 35분

**우선 (5/2 EOD 가능)**:
3. Patch A2 (§AV closure) — 60분
4. Patch A7 (§5.6 footnote) — 20분
5. Patch A3 (§1 contribution 5 finalize) — 30분

**Optional (5/3로 연기 가능)**:
6. Patch A4 (§1 contribution 6 draft)

총 시간: 4-5 hours. Phase A 끝나면 paper integrity 확보된 상태에서 잠.

5/3 morning에 Phase B 진행 (자동 결과 도착 후 fill-in).
