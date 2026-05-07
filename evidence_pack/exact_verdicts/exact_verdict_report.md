================================================================================
EXACT EVALUATOR VERDICT 재계산 보고서
총 9982 episodes
================================================================================

## 1. Evaluator Pass Rates
  Evaluator   Pass Rate    FA Rate   FA Count   BSR_cond
  -------------------------------------------------------
  TOM            100.0%      74.7%       7458      74.7%
  ASC             79.7%      59.3%       5918      74.4%
  CwT             37.0%      25.1%       2506      67.8%
  PAF             58.3%      44.2%       4415      75.8%
  TCC             25.3%       0.0%          0       0.0%

## 2. All-Oblivious FA (Hero Metric)
  ★ TOM+ASC+CwT 모두 pass AND hard violation:
    25.1% (2506/9982)
  ★ TOM+ASC+PAF 모두 pass AND hard violation:
    41.2% (4117/9982)

  ⚠️ 이전 근사치: ~24.1% (±5pp)
  ⚠️ 정확한 값:   25.1%
  ✅ 차이 1.0pp — 근사치가 유효 범위 내

## 3. Verdict-Flip
  Flip rate: 91.6% (9144/9982)
  이전 근사치: ~56.2%

## 4. Pairwise Disagreement
  ASC_vs_CwT          :  4260 (42.7%)
  ASC_vs_PAF          :  2859 (28.6%)
  ASC_vs_TCC          :  6405 (64.2%)
  CwT_vs_PAF          :  4185 (41.9%)
  CwT_vs_TCC          :  3841 (38.5%)
  PAF_vs_TCC          :  5532 (55.4%)
  TOM_vs_ASC          :  2027 (20.3%)
  TOM_vs_CwT          :  6287 (63.0%)
  TOM_vs_PAF          :  4160 (41.7%)
  TOM_vs_TCC          :  7458 (74.7%)

## 5. Model별 Pass/FA Rates

  [gemma31b]
    ASC_fa_rate              : 63.5%
    ASC_pass_rate            : 85.7%
    CwT_pass_rate            : 31.8%
    PAF_pass_rate            : 71.8%
    TCC_pass_rate            : 22.7%
    TOM_pass_rate            : 100.0%

  [nemotron30b]
    ASC_fa_rate              : 34.7%
    ASC_pass_rate            : 49.5%
    CwT_pass_rate            : 17.3%
    PAF_pass_rate            : 46.2%
    TCC_pass_rate            : 27.7%
    TOM_pass_rate            : 100.0%

  [oss120b]
    ASC_fa_rate              : 66.8%
    ASC_pass_rate            : 94.5%
    CwT_pass_rate            : 40.0%
    PAF_pass_rate            : 52.0%
    TCC_pass_rate            : 29.2%
    TOM_pass_rate            : 100.0%

  [qwen27b]
    ASC_fa_rate              : 60.1%
    ASC_pass_rate            : 88.5%
    CwT_pass_rate            : 51.8%
    PAF_pass_rate            : 60.3%
    TCC_pass_rate            : 32.3%
    TOM_pass_rate            : 100.0%

  [qwen35b]
    ASC_fa_rate              : 68.9%
    ASC_pass_rate            : 91.5%
    CwT_pass_rate            : 45.1%
    PAF_pass_rate            : 59.9%
    TCC_pass_rate            : 24.8%
    TOM_pass_rate            : 100.0%

  [qwen397b]
    ASC_fa_rate              : 86.4%
    ASC_pass_rate            : 90.6%
    CwT_pass_rate            : 49.5%
    PAF_pass_rate            : 75.5%
    TCC_pass_rate            : 4.2%
    TOM_pass_rate            : 100.0%

  [qwen4b]
    ASC_fa_rate              : 52.8%
    ASC_pass_rate            : 64.6%
    CwT_pass_rate            : 24.7%
    PAF_pass_rate            : 49.7%
    TCC_pass_rate            : 21.9%
    TOM_pass_rate            : 100.0%

## 6. FA Episode 내 Median Violations
  TOM       : median 9.0 violations per FA episode
  ASC       : median 8.0 violations per FA episode
  CwT       : median 6.0 violations per FA episode
  PAF       : median 9.0 violations per FA episode

## 7. 권장 조치
============================================================

  1. auto_numbers.tex에 아래 매크로를 반영:
     → exact_auto_numbers_update.tex 파일 생성됨
     → paper/auto_numbers.tex에 copy-paste 또는 \input

  2. Abstract에서 faAllOblivious를 매크로로 참조하고 있으므로
     매크로만 갱신하면 자동 반영됨

  3. 이 스크립트의 evaluator 구현이 실제 코드와 정확히 일치하는지 확인:
     → 특히 CwT의 timing penalty 계산 방식
     → PAF의 forbidden penalty 계수
     → ASC의 threshold (0.5)
     
  4. 실제 evaluator 코드(cpg_model/ 내)를 import해서 재채점하는 것이 더 정확:
     → make post-episode 실행 시 이 로직이 포함되어야 함


## 8. ⚠️ 이 스크립트의 한계

  이 스크립트는 episode JSON에서 action set을 추출하여 evaluator verdict를
  **독립적으로 재계산**합니다. 하지만 아래 한계가 있습니다:

  1. CwT의 정확한 timing penalty 공식을 모름
     → 현재 violation당 0.05 감점으로 추정
     → 실제 구현과 다를 수 있음

  2. PAF의 정확한 forbidden penalty 공식을 모름
     → 현재 forbidden action당 0.1 감점으로 추정

  3. Action normalization이 episode JSON에서 이미 적용되었는지 불확실
     → 대소문자, 공백 등의 차이로 false mismatch 가능

  4. Expected actions가 episode JSON에 포함되지 않은 경우 coverage 계산 불가
     → 이 경우 compliance_score를 fallback으로 사용

  ➡️ 최선의 방법: `make post-episode`에서 실제 evaluator 코드를 사용하여 재채점.
     이 스크립트는 그 전까지의 best-effort 추정입니다.
