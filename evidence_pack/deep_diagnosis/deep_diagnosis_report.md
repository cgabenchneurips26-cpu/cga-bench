================================================================================
CGA-Bench 파이프라인 심층 진단 보고서
총 7 issues 발견
================================================================================

## 요약
  Severity    Count
  --------------------
  CRITICAL        0 🔴
  HIGH            0 🟡
  MEDIUM          7
  WARNING         0
  INFO            0

  Bug Category                         Count   Severity
  -------------------------------------------------------
  B8_MODERATE_DEVIATION_RATE               7     MEDIUM

──────────────────────────────────────────────────────────────────────
## B8_MODERATE_DEVIATION_RATE (7 issues)
──────────────────────────────────────────────────────────────────────

  [MEDIUM] #1
    model: gemma31b
    deviation_rate: 0.198
    deviation_count: 4296
    total_actions: 21730
    examples: ['unknown', 'unknown', 'unknown', 'unknown', 'unknown']
    fix: Review normalizer coverage

  [MEDIUM] #2
    model: nemotron30b
    deviation_rate: 0.226
    deviation_count: 3788
    total_actions: 16741
    examples: ['unknown', 'unknown', 'unknown', 'unknown', 'unknown']
    fix: Review normalizer coverage

  [MEDIUM] #3
    model: oss120b
    deviation_rate: 0.223
    deviation_count: 3959
    total_actions: 17740
    examples: ['unknown', 'unknown', 'unknown', 'unknown', 'unknown']
    fix: Review normalizer coverage

  [MEDIUM] #4
    model: qwen27b
    deviation_rate: 0.158
    deviation_count: 6336
    total_actions: 40045
    examples: ['unknown', 'unknown', 'unknown', 'unknown', 'unknown']
    fix: Review normalizer coverage

  [MEDIUM] #5
    model: qwen35b
    deviation_rate: 0.171
    deviation_count: 7345
    total_actions: 42976
    examples: ['unknown', 'unknown', 'unknown', 'unknown', 'unknown']
    fix: Review normalizer coverage

  [MEDIUM] #6
    model: qwen397b
    deviation_rate: 0.213
    deviation_count: 2412
    total_actions: 11342
    examples: ['unknown', 'unknown', 'unknown', 'unknown', 'unknown']
    fix: Review normalizer coverage

  [MEDIUM] #7
    model: qwen4b
    deviation_rate: 0.188
    deviation_count: 3149
    total_actions: 16787
    examples: ['unknown', 'unknown', 'unknown', 'unknown', 'unknown']
    fix: Review normalizer coverage

======================================================================
## 즉시 조치 필요 사항
======================================================================