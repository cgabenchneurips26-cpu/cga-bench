> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# auto_numbers.tex ↔ main_final_v10.tex 전수 감사 결과

## 🔴🔴 LaTeX 컴파일 에러 (pdflatex 크래시)

### 1. 매크로 이름에 마침표 (30개) — INVALID LaTeX

LaTeX 매크로 이름에 `.`을 넣을 수 없습니다. 다음 30개 매크로가 컴파일을 깨뜨립니다:

```
L188-199, L425-434: \clusterACProxyAt0.3, \clusterACProxyAt0.4, ...
L236-247, L437-446: \passRateACProxyAt0.3, \passRateACProxyAt0.4, ...
```

**수정**: 이름 변경 필요 (e.g., `\clusterACProxyAtThree`, `\passRateACProxyAtZeroThree`)
다만 이 매크로들은 main.tex에서 참조되지 않으므로, **사용하지 않으면 삭제**하는 것이 가장 안전.

### 2. 중복 매크로 정의 (20개) — LaTeX 에러

L188-199과 L425-434에서 동일한 cluster 매크로가 두 번 정의됩니다.
L236-247과 L437-446에서 동일한 passRate 매크로가 두 번 정의됩니다.

```
\newcommand{\clusterACProxyAt0.3}{action-set}  % L188
\newcommand{\clusterACProxyAt0.3}{action-set}  % L425 ← 중복!
```

**수정**: L425-446 블록 전체 삭제 (L188-247의 첫 정의만 유지)

### 수정 스크립트 (Claude Code에서 실행):

```bash
# 1. 중복 블록 삭제 (L421-446)
sed -i '421,446d' paper/auto_numbers.tex

# 2. 마침표 매크로를 사용하지 않으면 삭제, 사용하면 이름 변경
# 현재 main.tex에서 참조되지 않으므로 삭제 권장
sed -i '/clusterACProxyAt0\./d' paper/auto_numbers.tex
sed -i '/clusterC2At0\./d' paper/auto_numbers.tex
sed -i '/clusterMABProxyAt0\./d' paper/auto_numbers.tex
sed -i '/passRateACProxyAt0\./d' paper/auto_numbers.tex
sed -i '/passRateC2At0\./d' paper/auto_numbers.tex
sed -i '/passRateMABProxyAt0\./d' paper/auto_numbers.tex
```

---

## 🔴 Missing 매크로 (PDF에 "??" 표시)

### 3. solver 관련 3개 매크로 미정의

| 매크로 | 참조 위치 | 필요한 값 |
|--------|----------|----------|
| `\solverILPRho` | main L362, appendix L436 | tiered↔ILP rank correlation (현재 데이터에서 계산 필요) |
| `\solverILPPct` | appendix L436 | ILP가 lower cost인 비율 (%) |
| `\solverSubsetN` | appendix L436 | 두 solver 모두 실행한 에피소드 수 |

**수정**: auto_numbers.tex에 추가:
```latex
% Solver agreement (tiered vs ILP)
\newcommand{\solverILPRho}{0.94}        % PLACEHOLDER — EX-17에서 확정
\newcommand{\solverILPPct}{22.2}        % PLACEHOLDER — EX-17에서 확정
\newcommand{\solverSubsetN}{108}        % PLACEHOLDER — EX-17에서 확정
```
(이전 handoff에서 \solverSubsetN=108, \solverILPPct=22.2, \solverILPRho=0.983이었으나 old 180ep 기준)

---

## 🔴 수치 불일치

### 4. EX-1 LLM Judge: raw vs pop-weighted 혼재 🔴🔴

auto_numbers.tex (L451-457):
```latex
\newcommand{\termJudgeT2FA}{21.8}      % ← RAW
\newcommand{\termJudgeT3FA}{4.4}       % ← RAW
\newcommand{\termJudgeT2T3Gap}{19.1}   % ← POP-WEIGHTED (23.9-4.8=19.1)
```

**문제**: T2FA=21.8, T3FA=4.4이면 gap=17.4pp인데, gap은 19.1pp로 되어 있음. 
이건 gap만 pop-weighted이고 개별 FA는 raw인 **혼재 상태**.

main_final_v10.tex (L85, L688)에서는 pop-weighted 값을 **하드코딩**:
```
false-accepts 23.9\% ... 4.8\% ($\Delta = 19.1$ pp)
```

**수정 (2가지 중 택 1)**:

**옵션 A (권장)**: pop-weighted를 primary로 통일
```latex
% EX-1: LLM Judge (population-weighted, P1 strict)
\newcommand{\termJudgeT0FA}{0.4}
\newcommand{\termJudgeT1FA}{18.5}
\newcommand{\termJudgeT2FA}{23.9}       % pop-weighted
\newcommand{\termJudgeT3FA}{4.8}        % pop-weighted
\newcommand{\termJudgeT2T3Gap}{19.1}    % pop-weighted
\newcommand{\termJudgeT2BSRcond}{32.1}
\newcommand{\termJudgeT3BSRcond}{6.5}
% Raw (sample-weighted) values for appendix:
\newcommand{\termJudgeT2FARaw}{21.8}
\newcommand{\termJudgeT3FARaw}{4.4}
\newcommand{\termJudgeT2T3GapRaw}{17.4}
```

**옵션 B**: raw를 primary로 (main.tex 수정 필요)

→ **옵션 A 권장**: 논문에서 이미 pop-weighted를 쓰고 있으므로.

### 5. main.tex 하드코딩 수치 (매크로 전환 필요)

| 위치 | 하드코딩 | 사용해야 할 매크로 |
|------|---------|-------------------|
| L85 | 23.9\% | `\termJudgeT2FA{}` (옵션A 적용 후) |
| L85 | 4.8\% | `\termJudgeT3FA{}` |
| L85 | 19.1 pp | `\termJudgeT2T3Gap{}` |
| L688 | 23.9\% | `\termJudgeT2FA{}` |
| L688 | 4.8\% | `\termJudgeT3FA{}` |
| L688 | 19.1~pp | `\termJudgeT2T3Gap{}` |
| L688 | 32.1\% | `\termJudgeT2BSRcond{}` |
| L688 | 6.5\% | `\termJudgeT3BSRcond{}` |
| L499 | 1,677 | `\instrWithinOnlyN{}` (auto_numbers에 1812로 정의 — **불일치!**) |
| L704 | 11.7~pp | `\ablationGapActionFull{}` |
| L704 | 33.1\% (implied) | `\ablationPassActionOnly{}` |
| L738 | 11.7~pp | `\ablationGapActionFull{}` |

### 6. 1,677 vs 1,812 불일치 🔴

main.tex L499: "1,677 contain {\sc within} as the only hard violation type"
auto_numbers L486: `\instrWithinOnlyN{1812}`

**이건 다른 집계입니다**: 1,677은 EX-2 severity analysis에서 나온 수(timing-only episodes), 1,812는 instrWithinOnlyN에서 나온 수. 집계 기준이 다를 수 있지만, 둘 다 "WITHIN-only violation episodes"를 의미한다면 **불일치**.

**수정**: 어느 쪽이 정확한지 확인 후 통일. 또는 별도 매크로 `\timingOnlyEpisodes{1677}` 추가.

---

## 🟡 의미론적 이슈

### 7. E3 Instrumentation 수치가 old 180 episodes 기준

```latex
\instrFullHard{36}      % 36/180 = 20%
\instrHardNoTime{24}    % 24/36 = 66.7%
```

이 수치들은 re-scoring 전의 old 180 episodes 기준. 14,826 에피소드로 갱신되면 크게 바뀔 것.
현재 논문 테이블에서 이 매크로를 사용 중이므로, **re-scoring 후 즉시 갱신 필요**.

### 8. `\bsrCGA{0.0}` 코멘트 framing

```latex
\newcommand{\bsrCGA}{0.0}  % CGA-Bench BSR (%) — ground truth by construction
```

v10에서 "ground truth" framing을 제거했으므로 코멘트도 변경:
```latex
\newcommand{\bsrCGA}{0.0}  % CGA-Bench BSR (%) — structural: checks all constraint types
```

### 9. `\numEpisodes{9982}`는 부분 데이터

현재 88%+ 완료. 에피소드 전체 완료 후 갱신 필요.

### 10. `\numExtraBefore{0}` — engine-only BEFORE가 0개

이건 실제로 0일 수 있지만, numBefore=65와 함께 보면 혼란스러울 수 있음. 
"Engine이 BEFORE를 추가 생성하지 않는다"는 뜻이라면 맞지만, Table caption에서 설명 필요.

---

## 전수 감사 체크리스트

| # | 이슈 | 심각도 | 수정 위치 | 비용 |
|---|------|--------|----------|------|
| 1 | 매크로명 마침표 (30개) | 🔴🔴 크래시 | auto_numbers | 10분 |
| 2 | 중복 매크로 (20개) | 🔴🔴 크래시 | auto_numbers | 5분 |
| 3 | solver 매크로 3개 미정의 | 🔴 ?? 표시 | auto_numbers | 5분 |
| 4 | EX-1 raw/pop-weighted 혼재 | 🔴🔴 불일치 | auto_numbers + main | 15분 |
| 5 | 하드코딩 수치 12개소 | 🔴 불일치 위험 | main.tex | 20분 |
| 6 | 1,677 vs 1,812 | 🔴 불일치 | 확인 필요 | 10분 |
| 7 | E3 old 180ep 기준 | 🟡 갱신 필요 | re-scoring 후 | — |
| 8 | bsrCGA 코멘트 framing | 🟡 cosmetic | auto_numbers | 1분 |
| 9 | numEpisodes 부분 | 🟡 갱신 필요 | 에피소드 후 | — |
| 10 | numExtraBefore=0 혼란 | 🟡 설명 필요 | table caption | 5분 |