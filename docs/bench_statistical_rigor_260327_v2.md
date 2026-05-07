# CGA-Bench 엄밀성 2차 수정 — Critical Review 반영

**원칙: 각 Fix의 "실행은 했지만 엄밀하지 않은" 부분을 모두 수정**

---

## Fix 1-R: Wilcoxon 보완 — Power caveat + 도메인별 비교

```
cga_bench의 Multi-LLM 통계 검정을 보완해라.

문제 1: Wilcoxon signed-rank test의 N=8에서 power가 낮다.
"p>0.05 = 차이 없음"이 아니라 "검증력 부족으로 판단 불가"일 수 있다.

문제 2: 시나리오별 mean으로 축약하면 run 간 variability가 소실된다.

문제 3: 평균만 비교하면 stroke에서 72B가 36%인 것 같은 도메인별 차이가 숨겨진다.

수정:

1. 통계 보고에 power caveat를 추가:
   - evidence_pack/analysis/multi_llm_statistical_test.json에
     "note": "N=8 paired samples; Wilcoxon power is limited.
     Non-significant p-values should not be interpreted as evidence
     of equivalence. A well-powered equivalence test (TOST) would
     require N≥20 scenarios."
   - LaTeX 테이블 각주에도 동일 caveat

2. 도메인별 비교 테이블 추가:
   각 시나리오에서 3모델의 mean±SD를 나란히 보여주는 테이블.
   평균이 아닌 시나리오별로 어디서 차이가 나는지 한눈에 보이게.
   특히 stroke_tpa에서의 큰 차이를 명시적으로 보고.

3. Run-level 분석 추가 (mean 축약 대신):
   - 72 에피소드 (3모델 × 8시나리오 × 3회) 전체를
     mixed-effects 관점에서 분석:
   - model을 fixed effect, scenario를 random effect로 하는
     linear mixed model을 돌려라
   - python에서: statsmodels의 mixedlm 또는
     scipy로 2-way ANOVA (model × scenario)
   - run 간 variability를 포함한 결과 보고
   - 이게 어려우면 bootstrap permutation test:
     모델 라벨을 랜덤 셔플 → compliance 차이 분포 생성 → 관찰값의 위치

4. effect size 보고:
   - Cohen's d (pooled SD 사용)
   - d < 0.2이면 "작은 차이", 0.2-0.8 "중간", > 0.8 "큰 차이"
   - 이걸 "차이 있다/없다"보다 더 informative한 결론으로 사용

5. 결과 업데이트:
   - evidence_pack/analysis/multi_llm_statistical_test.json
   - evidence_pack/tables/table_multi_llm.tex
```

---

## Fix 2-R: Failure Taxonomy — 상세 정보 추출 + chi-squared

```
cga_bench의 failure taxonomy를 완성해라.

문제 1: violation type만 추출하고 action_involved 등 상세 정보 미수집.
문제 2: oss-120b는 summary.json에서, 나머지는 stdout 파싱 — 데이터 소스 불일치.
문제 3: 모델별 패턴 차이에 chi-squared test 없음.

수정:

1. 72 에피소드 로그에서 통일된 방법으로 violation 추출:
   - 먼저 에피소드 로그의 실제 저장 형식을 확인해라
   - violation_events가 JSON으로 저장되어 있으면 거기서 직접 파싱
   - 없으면 CGAScore 객체를 재생성해서 추출
   - 3모델 모두 동일한 방법으로 추출 (소스 일관성)

2. 각 violation에서 다음 필드를 수집:
   - violation_type (DEVIATION, TIMING, OMISSION, SEQUENCE, COMMISSION)
   - action_involved (어떤 action이 위반인지)
   - severity (Step A의 ViolationExplainer 사용)
   - scenario, model, run_id

3. violation별 action 상위 20개 리스트:
   "가장 빈번하게 deviation으로 판정된 action"이 뭔지
   모델 간에 다른지

4. chi-squared test:
   - 3모델의 violation type 분포가 유의하게 다른지
   - contingency table: model × violation_type
   - scipy.stats.chi2_contingency() 사용
   - p-value + Cramér's V (effect size) 보고

5. 저장:
   - evidence_pack/analysis/failure_taxonomy.json 업데이트
     (action_involved, severity 포함)
   - evidence_pack/analysis/failure_taxonomy_by_model.json 업데이트
     (chi-squared 결과 포함)
   - scripts/extract_failure_taxonomy.py가 위 모든 걸 자동으로 하게 수정
```

---

## Fix 3-R: Process Timeline — 실제 JSON 파싱 또는 정직한 명시

```
cga_bench의 process timeline figure에서 하드코딩을 완전히 제거해라.

현재 문제:
model_data dict를 스크립트에 직접 입력했다.
이건 run output에서 숫자를 눈으로 읽어서 입력한 것이지,
JSON 로그에서 자동 파싱한 게 아니다.

수정 방법 A (best): 에피소드 로그에서 자동 추출

1. 에피소드 로그에 action별 timestamp가 저장되어 있는지 확인:
   - episode_log.json 또는 유사 파일의 구조를 보여줘
   - 각 action의 step number, timestamp_minutes 필드가 있는지
   - violation_events의 timestamp_minutes가 있는지

2. 있다면:
   - EpisodeNarrativeGenerator를 호출해서 timeline JSON 생성
   - timeline JSON에서 figure 자동 생성
   - scripts/generate_process_timeline.py가 에피소드 로그를 입력받아
     figure를 출력하는 완전 자동화 파이프라인으로 수정

3. figure 형태:
   - X축: time (step number 또는 minutes)
   - Y축: 모델 3개 (행으로 구분)
   - 각 action을 점으로 표시, 색상으로 compliant/violation 구분
   - violation에는 type 라벨 (TIMING, DEVIATION 등)

수정 방법 B (fallback): 자동 추출 불가 시

4. 에피소드 로그에 timestamp가 없으면:
   - step number만으로 순서 기반 timeline 생성
   - figure 캡션에 명시적으로:
     "Timeline shows action sequence order (step number),
     not wall-clock time. Detailed timestamps are not available
     in the current episode log format."
   - model_data를 에피소드 로그에서 자동 추출 가능한 범위로만 구성:
     step count, action count, violation count는 자동 추출 가능
   - 하드코딩 숫자를 모두 삭제하고 자동 추출 코드로 교체

5. 어떤 방법이든 scripts/generate_process_timeline.py는
   입력: 에피소드 로그 디렉토리
   출력: figure
   중간에 하드코딩된 숫자 0개
   로 만들어라.
```

---

## Fix 5-R: Structural Complexity — 가중치 sensitivity + pseudo-replication

```
cga_bench의 difficulty calibration에서 두 가지 문제를 수정해라.

문제 1: complexity 가중치 (mandatory*1.0 + forbidden*2.0 + timed*1.5 + nodes*0.5)의
근거가 없다.

문제 2: sepsis_basic과 sepsis_allergy가 동일 CPG → 같은 complexity →
독립 데이터포인트로 취급하면 pseudo-replication.

수정:

1. 가중치 sensitivity analysis:
   다음 4가지 가중치 조합으로 상관을 재계산:
   - Equal weight: 모든 요소 1.0
   - Forbidden-heavy: forbidden*3.0, 나머지 1.0
   - Timing-heavy: timed*3.0, 나머지 1.0
   - Node-heavy: nodes*2.0, 나머지 1.0
   + 현재 가중치

   5가지 조합 각각에 대해 Spearman ρ + p-value를 보고.
   결과가 가중치에 따라 크게 달라지면
   "가중치 선택에 민감하다"고 정직하게 보고.

2. 가중치 없이 raw metrics 각각의 상관도 보고:
   - mandatory_count vs compliance: ρ = ?
   - forbidden_count vs compliance: ρ = ?
   - timed_actions_ratio vs compliance: ρ = ?
   - node_count vs compliance: ρ = ?
   어떤 개별 지표가 compliance와 가장 상관이 높은지

3. Pseudo-replication 수정:
   - 동일 CPG를 사용하는 시나리오 쌍 확인 (sepsis_basic & sepsis_allergy 등)
   - 옵션 A: 동일 CPG 시나리오를 하나로 합산 (평균)해서 N을 줄이고 재분석
   - 옵션 B: 두 분석 모두 보고 (with/without pseudo-replication correction)
   - 어느 쪽이든 차이가 있으면 보고

4. Oracle score 기반 난이도도 동일 처리:
   - pseudo-replication 보정 후 Oracle ρ 재계산
   - sensitivity analysis 결과와 함께 보고

5. 저장:
   - evidence_pack/analysis/difficulty_calibration.json 업데이트
     (sensitivity 결과, pseudo-replication 보정 포함)
   - evidence_pack/figures/difficulty_calibration.png 재생성
     (error bar + sensitivity 범위 표시)
```

---

## Fix 7-R: 외부 벤치마크 인플레이션 수정 반영

```
cga_bench의 외부 벤치마크 테이블에 인플레이션 진단 결과를 실제로 반영해라.

현재 문제:
Fix 7에서 MedAgentBench 96.7%가 100% universal fallback이라는 걸 진단했지만,
테이블에는 여전히 96.7%로 보고하고 있다.

수정:

1. 각 외부 벤치마크 결과에 "CPG Coverage" 정보를 추가:
   - Specific CPG로 매핑된 케이스 비율
   - Universal fallback으로 평가된 케이스 비율

2. 외부 벤치마크 테이블에 열 추가:
   ┌───────────────┬──────┬────────────┬──────────────┬───────────────────┐
   │   Benchmark   │  N   │ Compliance │ CPG Coverage │      Note         │
   ├───────────────┼──────┼────────────┼──────────────┼───────────────────┤
   │ MedAgentBench │ 20   │ 96.7%      │ 0% specific  │ ⚠️  All universal  │
   │ AgentClinic   │ 20   │ 62.0%      │ ?% specific  │                   │
   │ MedChain      │ 49   │ 10.0%      │ ?% specific  │                   │
   │ HealthBench   │ 50   │ 45.0%      │ N/A (rubric) │                   │
   └───────────────┴──────┴────────────┴──────────────┴───────────────────┘

3. MedAgentBench에 대해:
   - "CPG Coverage 0%이므로 compliance 96.7%는 universal safety 기준이며,
     domain-specific CPG 준수율이 아님"을 각주에 명시
   - 논문 본문에서도 이 구분을 명확히

4. 가능하면 "Specific CPG only" 점수를 별도 계산:
   - universal fallback 케이스를 제외하고
   - specific CPG로 매핑된 케이스만의 compliance 계산
   - 해당 케이스가 0건이면 "N/A (no specific CPG match)"

5. 모든 외부 벤치마크 LaTeX 테이블 업데이트:
   - table_external_final_v2.tex
   - table_external_multi.tex
   - table_external_all.tex (있으면)
```

---

## 실행 체크리스트

```
□ Fix 1-R: Power caveat + 도메인별 테이블 + mixed-effects 또는 bootstrap + effect size
□ Fix 2-R: 통일된 violation 파싱 + action 상세 + chi-squared test
□ Fix 3-R: 하드코딩 완전 제거, 자동 추출 또는 정직한 명시
□ Fix 5-R: 5가지 가중치 sensitivity + raw metric별 상관 + pseudo-replication 보정
□ Fix 7-R: CPG Coverage 열 추가 + inflation 주석 반영 + LaTeX 업데이트

완료 후: 모든 evidence_pack 산출물이 자동 생성 가능한 스크립트에 의해 만들어지는지 확인.
하드코딩된 숫자가 남아있으면 보고.
```