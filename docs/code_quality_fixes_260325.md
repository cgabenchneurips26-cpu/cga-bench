# CGA-Bench 코드 품질 수정 — Claude Code 프롬프트

**실행 순서**: Critical(1→2→3) 순차, Medium(4→5→6→7)은 Critical 완료 후, Minor(8→9)는 마지막.

---

## 🔴 Critical 1: Deviation Severity — Jaccard 유사도 오분류 수정

```
cga_bench의 eval_harness/explainability/deviation_severity.py에서 Jaccard 유사도 계산이
범용 prefix 토큰 때문에 severity를 오분류하는 문제를 수정해라.

문제:
action_id를 _ 토큰으로 쪼개서 Jaccard 유사도를 계산하는데,
"give", "order", "medication", "lab", "assess", "start", "check", "monitor" 같은
범용 prefix가 거의 모든 action에 포함되어 있어서 유사도가 과도하게 높게 나온다.

예시:
- "give_medication_heparin" vs "give_medication_insulin"
  → 토큰 {give, medication, heparin} vs {give, medication, insulin}
  → Jaccard = 2/4 = 0.5 → MODERATE로 판정
  → 하지만 AKI 환자에게 heparin은 HIGH 이상이어야 함

- "order_lab_troponin" vs "order_lab_creatinine"
  → 토큰 {order, lab, troponin} vs {order, lab, creatinine}
  → Jaccard = 2/4 = 0.5 → MODERATE
  → 실제로는 완전히 다른 검사

수정 방법:

1. _jaccard_similarity()에 stopword 제거를 추가해라:

   STOPWORDS = {
       "give", "order", "start", "stop", "check", "assess", "monitor",
       "evaluate", "perform", "obtain", "measure", "review", "calculate",
       "medication", "med", "drug", "lab", "test", "imaging",
       "patient", "result", "results", "basic", "standard",
   }

   토큰화 후 stopwords를 제거하고, 남은 토큰으로 Jaccard를 계산.
   만약 stopword 제거 후 양쪽 다 빈 집합이면 유사도 0.0 반환.

2. ActionNormalizer를 이미 import하고 있으니, normalizer의 fuzzy match 결과도 활용해라:
   - self.normalizer가 normalize() 메서드를 갖고 있으면, best_match와 score를 가져와서
   - Jaccard score와 normalizer score 중 max를 사용
   - normalizer에 해당 메서드가 없으면 Jaccard만 사용 (에러 나지 않게)

3. 수정 후 검증 — 다음 케이스들을 테스트해라:
   - "give_medication_heparin" vs allowed={"give_medication_nacl", "order_lab_creatinine"}
     → heparin은 AKI에서 stopword 제거 후 {heparin} vs {nacl}, {creatinine} → 0.0 → HIGH
   - "order_lab_troponin" vs allowed={"order_lab_creatinine", "order_lab_bun"}
     → stopword 제거 후 {troponin} vs {creatinine}, {bun} → 0.0 → HIGH
   - "order_lab_urine_electrolytes" vs allowed={"order_lab_urinalysis"}
     → stopword 제거 후 {urine, electrolytes} vs {urinalysis} → 부분 매칭 → MODERATE~LOW
   - "admit_patient" vs allowed={"admit_patient_icu"} → {admit} vs {admit, icu} → 0.5 → MODERATE

4. 수정 전/후 비교:
   - 8개 시나리오의 기존 3회 반복 에피소드 로그에 대해 severity 분류 결과를 비교
   - 변경된 케이스 수와 방향(어떤 severity에서 어떤 severity로)을 보고해라
   - 특히 AKI 시나리오에서 "관련 없는 PE 행동"이 HIGH/CRITICAL로 올라갔는지 확인
```

---

## 🔴 Critical 2: Deviation Severity — 에피소드 간 상태 오염 방지

```
cga_bench의 eval_harness/explainability/deviation_severity.py에서
_seen_actions 상태가 에피소드 간에 오염되는 문제를 수정해라.

문제:
- classify()가 호출될 때마다 _seen_actions에 action_id를 추가
- compute_weighted_deviation_score()는 내부에서 reset()을 호출하지만,
  외부에서 classify()를 직접 호출하는 코드가 있으면 상태가 오염됨
- 3회 반복 실험에서 같은 인스턴스를 재사용하면 2번째 run부터 결과가 달라질 수 있음

수정:

1. classify()의 인터페이스를 변경해라:
   - _seen_actions를 인스턴스 변수가 아닌 메서드 파라미터로 받는 방식으로 변경
   - 또는 context manager / episode scope 패턴 적용

   추천 방법 — episode_scope context manager:

   class DeviationSeverityClassifier:
       ...
       @contextmanager
       def episode_scope(self):
           """에피소드별 상태 격리. with 블록이 끝나면 자동 reset."""
           self._seen_actions = set()
           try:
               yield self
           finally:
               self._seen_actions = set()

   사용:
   with classifier.episode_scope():
       for action in deviations:
           label, weight = classifier.classify(action, allowed, forbidden)

2. compute_weighted_deviation_score()도 episode_scope를 사용하게 수정.

3. classify()가 episode_scope 밖에서 호출되면 경고 로그를 남겨라:
   if not hasattr(self, '_in_scope') or not self._in_scope:
       logger.warning("classify() called outside episode_scope — state may leak between episodes")

4. 기존에 classify()나 compute_weighted_deviation_score()를 호출하는 코드를 모두 찾아서
   episode_scope를 적용해라. grep으로 호출부를 찾아서 수정.

5. 테스트 추가:
   - 같은 classifier 인스턴스로 2개 에피소드를 순차 처리했을 때
     각 에피소드의 결과가 독립적인지 검증하는 유닛 테스트 작성
   - tests/test_explainability/ 디렉토리에 test_deviation_severity.py로 저장
```

---

## 🔴 Critical 3: Radar Chart — 하드코딩 점수 제거

```
cga_bench의 eval_harness/explainability/radar_chart.py에서
점수가 모듈 상단에 하드코딩된 문제를 수정해라.

문제:
SCORES 딕셔너리가 특정 시점의 스냅샷으로 하드코딩되어 있어서,
실험을 다시 돌리면 Figure와 실제 결과가 불일치한다.

수정:

1. SCORES 딕셔너리를 모듈 상단에서 제거해라.
   대신 summary.json에서 로드하는 함수를 추가:

   def load_scores_from_summary(summary_path: str) -> dict:
       """evidence_pack/repeat_experiments/summary.json에서 점수 로드."""
       with open(summary_path) as f:
           data = json.load(f)
       scores = {}
       for scenario_id, vals in data.items():
           # summary.json의 구조를 확인하고 적절히 파싱
           # C1~C5 mean 값을 추출
           scores[scenario_id] = {
               "C1": vals.get("c1_mean", 0),
               "C2": vals.get("c2_mean", 0),
               "C3": vals.get("c3_mean", 0),
               "C4": vals.get("c4_mean", 0),
               "C5": vals.get("c5_mean", 0),
           }
       return scores

   정확한 키 이름은 summary.json 구조를 먼저 확인하고 맞춰라.

2. plot_all()의 기본값을 변경:

   def plot_all(self, all_scores=None, output_dir="evidence_pack/figures",
                summary_path="evidence_pack/repeat_experiments/summary.json"):
       if all_scores is None:
           all_scores = load_scores_from_summary(summary_path)

3. DOMAIN_GROUPS와 _SAFE_NAMES도 하드코딩 대신
   scenario_id를 기반으로 자동 분류하는 로직 추가:
   - scenario_id에 "sepsis"가 포함되면 Sepsis 그룹
   - "dka"가 포함되면 Metabolic 그룹
   - 등등
   - 매핑이 안 되면 "Other" 그룹에 넣어라

4. 기존 SCORES를 FALLBACK_SCORES로 이름 변경하고,
   summary.json이 없을 때만 사용하도록 (경고 로그와 함께):

   if not os.path.exists(summary_path):
       logger.warning(f"summary.json not found at {summary_path}, using fallback scores")
       all_scores = FALLBACK_SCORES

5. 수정 후 plot_all()을 실행해서 기존과 동일한 10장의 차트가 생성되는지 확인.
```

---

## 🟡 Medium 4: Narrative Generator — c2_pct 변수명/의미 혼동 수정

```
cga_bench의 eval_harness/explainability/narrative_generator.py에서
_build_clinical_assessment의 변수명과 의미 혼동을 수정해라.

문제:
c2_pct = round(score.compliance_score * 100, 1)
→ compliance_score는 overall compliance인데 변수명이 c2_pct
→ 서사에서 "필수 행동 {c2_pct}% 완료"라고 쓰지만 이건 C2가 아님

수정:

1. 변수명을 compliance_pct로 변경하고, 서사 텍스트도 수정:
   compliance_pct = round(score.compliance_score * 100, 1)
   → "전체 준수율 {compliance_pct}%"

2. 실제 C2(mandatory completion)를 서사에 포함하고 싶다면:
   c2_val = score.sub_scores.get("C2", score.sub_scores.get("c2_mandatory_completion", None))
   → 값이 있으면 "필수 행동 {c2_val*100:.1f}% 완료"도 추가

3. 서사 포맷 최종:
   "전체 준수율 {compliance_pct}%, 필수 행동 완료율 {c2_pct}%, 금기 행동 {c3_status}. {primary_issue}."

4. 이 변경이 기존 narrative JSON/MD 파일에 영향을 주므로,
   8개 시나리오의 narrative를 재생성하고 evidence_pack/narratives/에 덮어써라.
```

---

## 🟡 Medium 5: Dead code 제거 + HealthBench 동적 import 분리

```
cga_bench 코드에서 두 가지 정리 작업을 수행해라.

작업 A: narrative_generator.py의 dead code 제거

1. _get_status_for_actions() 함수가 정의만 되고 사용되지 않는다.
   - _build_timeline()에서 같은 로직을 인라인으로 다시 작성했다.
   - _get_status_for_actions()를 삭제하거나,
     _build_timeline()의 인라인 로직을 이 함수 호출로 교체해라.
   - 교체하는 경우 두 로직이 동일한 결과를 내는지 테스트로 확인해라.

작업 B: pipeline.py의 HealthBench 동적 import 분리

1. _actions_from_checklist() 안에 있는 HealthBench 전용 분기를 분리해라:

   현재 (범용 함수 안에 특정 데이터셋 로직이 박혀 있음):
   if tags or points != 0:
       import importlib
       healthbench_module = importlib.import_module(...)
       kind_class = healthbench_module.classify_criterion_enhanced(...)

   수정 방향:
   - classify_criterion()을 확장하여 tags/points를 선택적으로 받게 하거나
   - _actions_from_checklist()에서 데이터셋별 분기 대신,
     criterion classifier를 manifest나 adapter에서 주입받는 구조로 변경

   구체적으로:

   (a) DatasetManifest에 criterion_classifier 필드 추가 (Optional[str]):
       criterion_classifier: Optional[str] = None  # e.g. "healthbench"

   (b) _actions_from_checklist()에서:
       if manifest has criterion_classifier:
           load and use that classifier
       else:
           use default classify_criterion()

   (c) 또는 더 간단하게: classify_criterion()이 tags/points를 optional로 받게 확장:
       def classify_criterion(text, tags=None, points=0) -> CriterionKind:
           if tags or points != 0:
               # enhanced logic (현재 healthbench 모듈에 있는)
               ...
           # 기존 키워드 기반 로직
           ...

   가장 간단한 방법으로 구현하되, importlib 동적 import는 제거해라.

2. 수정 후 기존 테스트가 통과하는지 확인.
```

---

## 🟡 Medium 6: ViolationExplainer — 도메인 힌트 CPG YAML 연동

```
cga_bench의 eval_harness/explainability/violation_explainer.py에서
_DOMAIN_HINTS 하드코딩을 CPG YAML 메타데이터 기반으로 개선해라.

현재 문제:
- _DOMAIN_HINTS가 8개 도메인의 임상적 의미를 하드코딩한 리스트
- 새 CPG 도메인(AF, COPD, CAP 등 7개 확장 예정)을 추가할 때마다 수동 편집 필요

수정:

1. CPG YAML 파일에 domain_significance 또는 clinical_context 필드가 있는지 확인해라.
   cpg_model/graphs/ 디렉토리의 YAML 파일 2-3개를 열어서 메타데이터 구조 확인.

2. 있다면:
   - _CPGIndex가 로드할 때 도메인별 significance 텍스트도 인덱싱
   - _clinical_significance()가 CPG에서 가져온 텍스트를 우선 사용하고,
     없을 때만 현재 _DOMAIN_HINTS를 fallback으로 사용

3. 없다면:
   - _DOMAIN_HINTS를 별도 YAML 파일로 분리 (explainability/domain_hints.yaml)
   - 새 도메인 추가 시 코드 수정 없이 YAML만 편집하면 되게
   - ViolationExplainer.__init__()에서 이 YAML을 로드

4. 어떤 방법이든, _DOMAIN_HINTS가 코드에 하드코딩되지 않게 해라.

5. 기존 8개 시나리오의 explanation 결과가 변하지 않는지 확인.
```

---

## 🟡 Medium 7: CPGIndex 경로 + 확장성 개선

```
cga_bench에서 파일 경로 관련 안정성을 개선해라.

1. violation_explainer.py의 _CPGIndex 기본 경로:
   현재: cpg_graphs_dir: str = "cpg_model/graphs"  ← 상대 경로

   수정:
   - 프로젝트 루트를 기준으로 절대 경로를 계산하는 유틸리티 사용
   - 또는 환경변수/config에서 경로를 읽는 방식
   - 최소한: Path(__file__).parent.parent.parent / "cpg_model" / "graphs" 같은
     모듈 위치 기반 상대 경로로 변경

   narrative_generator.py도 동일한 기본 경로를 사용하므로 함께 수정.

2. 경로를 못 찾았을 때의 에러 메시지를 개선:
   현재: _load()에서 os.path.isdir() 실패 시 조용히 빈 인덱스 반환
   수정: logger.warning()으로 "CPG graphs directory not found: {path}" 출력

3. 수정 후 프로젝트 루트와 다른 디렉토리에서 실행해도 CPG가 로드되는지 확인:
   cd /tmp && python -c "from cga_bench.eval_harness.explainability.violation_explainer import ViolationExplainer; v = ViolationExplainer(); print(len(v._cpg._index))"
```

---

## 🟢 Minor 8: 도메인 키워드 중복 통합

```
cga_bench에서 도메인 감지 키워드가 두 군데에 중복 정의된 문제를 통합해라.

1. 중복 위치 확인:
   - semantic_layer/external/pipeline.py의 _detect_domain() 안 domain_keywords
   - semantic_layer/external/compatibility_checker.py의 도메인 감지 로직 (있다면)
   - eval_harness/explainability/violation_explainer.py의 _DOMAIN_HINTS 키워드

2. 공통 도메인 키워드를 하나의 모듈로 통합:
   - semantic_layer/external/domain_keywords.py 또는 cpg_model/domain_registry.py
   - 구조:
     DOMAIN_KEYWORDS = {
         "sepsis": {"keywords": ["sepsis", "septic", "bacteremia"], "aliases": ["ssc"]},
         "aki": {"keywords": ["aki", "renal", "kidney", "creatinine"], "aliases": ["kdigo"]},
         ...
     }

3. pipeline.py, compatibility_checker.py, violation_explainer.py 모두 이 공통 모듈을 import하게 수정.

4. 기존 테스트가 통과하는지 확인.
```

---

## 🟢 Minor 9: BaseAdapter 인터페이스 정리

```
cga_bench의 semantic_layer/external/base.py에서
parse_to_episode_log과 parse_to_normalized가 사실상 동일한 역할인 문제를 정리해라.

1. UniversalExternalAdapter에서 두 메서드가 모두 process_case()를 호출하는지 확인.

2. 확인되면:
   - parse_to_episode_log()에 deprecation 경고 추가:
     import warnings
     warnings.warn("parse_to_episode_log is deprecated, use parse_to_normalized", DeprecationWarning)
     return self.parse_to_normalized(raw)
   - BaseAdapter의 docstring에 deprecated 표시

3. 외부에서 parse_to_episode_log()를 호출하는 코드를 찾아서
   parse_to_normalized()로 교체해라. (grep으로 전체 검색)

4. 기존 테스트가 통과하는지 확인.
```

---

## 실행 체크리스트

```
□ Critical 1: Jaccard stopword 적용, AKI 시나리오에서 PE 행동이 HIGH로 분류 확인
□ Critical 2: episode_scope context manager, 상태 격리 테스트 통과
□ Critical 3: summary.json 로드, 하드코딩 제거, 차트 10장 재생성
□ Medium 4: c2_pct → compliance_pct 수정, narrative 재생성
□ Medium 5: dead code 제거 + HealthBench import 분리
□ Medium 6: domain_hints YAML 분리 또는 CPG 연동
□ Medium 7: CPGIndex 절대 경로, 에러 메시지 개선
□ Minor 8: 도메인 키워드 공통 모듈 통합
□ Minor 9: parse_to_episode_log deprecated 처리

완료 후: 8개 시나리오 전체 1회 실행으로 regression 확인.
점수 변동이 있으면 (특히 severity 변경으로 인한) 변동 내역을 테이블로 보고.
```