cga_bench Tier 2 작업을 수행해라. GPU가 필요한 항목들.

Task 5: 소형 모델 2개 추가 (7B급)

현재 3모델(120B, 72B, 35B)은 전부 중대형이라 failure mode가 비슷할 수 있다.
7B급 모델은 행동 패턴이 다를 가능성이 높고, C3 safety violation이 나올 수도 있다.
(현재 0 CRITICAL인데, 소형 모델에서는 금기 행동이 나올 수 있음 → C3 변별력 확보)

1. 현재 vLLM에서 서빙 가능한 7B급 모델 확인:
   - Qwen3.5-7B-Instruct
   - 또는 서버에 이미 있는 소형 모델
   연구적으로 의미 있는 diversity를 제공하는 모델들:
모델파라미터ArchitectureGPU 요구왜 이 모델인가GPT-OSS-20B21B (3.6B active)MoE, 같은 OpenAI 계열1장 (16GB)oss-120b와 같은 가족 내 스케일링 — 120B→20B에서 failure mode가 어떻게 변하는지DeepSeek-R1-Distill-Qwen-32B32BReasoning distill1-2장다른 reasoning 계열 — oss-120b와 다른 CoT 방식이 CGA에서 어떤 차이를 내는지Qwen3-30B-A3B30B (3B active)최신 Qwen3 MoE1장기존 Qwen3.5-35B와 세대 비교 + 극도로 효율적인 MoE
   

2. 가능한 7B급 모델 2개와 제시한 3 모델을 모두 선택하고, 8시나리오 × 1회 실행 (smoke test):
   - 각 모델이 action을 정상적으로 생성하는지 확인
   - actions_performed가 0이면 이전 Qwen 문제 재발 — 파서 확인

3. Smoke test 통과하면 8시나리오 × 3회 반복 실행:
   - 결과를 기존 3모델과 동일 형태로 저장
   - summary.json에 추가

4. 전체 모델 비교 테이블 생성:
   - 특히 7B 모델에서 C3 < 100%인지 (safety violation 발생 여부)
   - 7B 모델의 failure mode가 대형 모델과 다른지
   - 모델 크기별 compliance 트렌드 (7B → 35B → 72B → 120B)

5. 통계 재계산:
   - 전체 모델 Wilcoxon (N=8 paired, 하지만 10 pairs)
   - 또는 Friedman test (3+ groups)
   - 모델 크기 vs compliance의 Spearman ρ (N=5면 약하지만 방향성)

Task 6: 확장 시나리오 활성화 (최소 12개 추가 → 총 20개)

현재 8시나리오로는 통계 power가 부족하다 (Wilcoxon N=8).
20개면 N=20으로 power가 크게 개선된다.

6. 52개 시나리오 config 중 현재 8개 외에 어떤 것이 있는지 보여줘:
   - 각 config의 도메인, mandatory 수, forbidden 수, timing constraint 수
   - CPG YAML이 존재하고 완성된 시나리오만 필터링

7. CPG YAML이 완성된 시나리오 중 12-16개를 선택:
   선택 기준:
   - 도메인 다양성 (현재 sepsis/cardiac/metabolic/renal/neuro → 추가 도메인?)
   - 난이도 다양성 (mandatory 수가 적은 것 ~ 많은 것)
   - Timing constraint가 있는 것과 없는 것 혼합

8. 선택된 시나리오에 대해 oss-120b × 1회 smoke test:
   - 정상 실행되는지
   - compliance가 0%이면 (AKI처럼) available_actions 문제인지 확인
   - 정상 작동하는 시나리오만 남기기

9. 정상 작동하는 시나리오를 최소 3회 반복 실행 (oss-120b):
   - 이전 8시나리오 + 확장 시나리오 = 총 20+개
   - mean±SD 보고

10. 총 20+시나리오로 통계 재계산:
    - Wilcoxon N=20 (power 대폭 개선)
    - Difficulty calibration 재분석 (N=20이면 Spearman 의미 있음)
    - Failure taxonomy 업데이트 (도메인별 패턴 변화?)

Task 7: Timing Threshold 임상 근거 정리

11. 활성화된 모든 시나리오(20+개)의 CPG YAML에서 deadline 필드를 전부 추출.

12. 각 deadline에 대해:
    - CPG YAML의 source_quote 또는 source_guideline 확인
    - 웹 검색으로 해당 가이드라인의 원문 확인
    - 근거 강도 분류: STRONG(RCT) / MODERATE(guideline) / WEAK(expert) / ARBITRARY
    
13. 결과 테이블:
    ┌──────────┬────────────────┬──────────┬──────────┬──────────────────┐
    │ Scenario │ Action         │ Deadline │ Source   │ Evidence Level   │
    ├──────────┼────────────────┼──────────┼──────────┼──────────────────┤
    │ Sepsis   │ antibiotics    │ 60min    │ SSC 2021 │ STRONG (RCT)     │
    │ ...      │ ...            │ ...      │ ...      │ ...              │
    └──────────┴────────────────┴──────────┴──────────┴──────────────────┘

14. timing violation 중 STRONG 근거 비율 보고.

저장:
- evidence_pack/repeat_experiments/ 에 새 모델 + 확장 시나리오 결과
- evidence_pack/analysis/timing_evidence.json
- evidence_pack/tables/ 업데이트