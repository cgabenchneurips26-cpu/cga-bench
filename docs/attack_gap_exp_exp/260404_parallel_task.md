# 병렬 작업: Episode 실행 대기 중 수행

## 작업 1: References.bib 완성 (우선순위 1)

현재 main.tex의 \begin{thebibliography}에 15개 약식 엔트리가 있다.
이것을 full bibliographic detail로 교체한다.

### 작업 내용

각 reference에 대해:
1. 정확한 저자 전원 (et al. 대신 실제 이름)
2. 정확한 제목
3. 저널/학회명, 볼륨, 페이지, DOI
4. 출판 연도

### 현재 엔트리 목록 (main.tex에서 추출)

```
medagentbench2025 — MedAgentBench, Stanford 2025
agentclinic2024 — AgentClinic 2024
amega2025 — AMEGA, NEJM AI 2025
healthbench2025 — HealthBench, OpenAI 2025
arewlearningyet2021 — Are We Learning Yet?, NeurIPS D&B 2021
betterbench2024 — BetterBench, NeurIPS 2024
measuringwhatmatters2025 — Measuring What Matters, NeurIPS 2025
alaa2025 — Alaa et al., ICML 2025
peleg2003 — Peleg et al., JAMIA 2003
munoz2022 — Munoz-Gama et al., J Biomed Informatics 2022
dkg2023 — Decision Knowledge Graphs 2023
cpgprompt2025 — CPGPrompt 2025
ontologytest2019 — Ontology Based Test Case Generation 2019
kgtest2020 — Nayak et al., ACM CoDS-COMAD 2020
landis1977 — Landis & Koch, Biometrics 1977
```

### 방법

각 reference를 웹에서 검색하여 full citation을 작성하라.
- arXiv preprint이면 arXiv ID 포함
- 학회 논문이면 proceedings 정보 포함
- 저널 논문이면 volume, pages, DOI 포함

BibTeX 형식으로 작성한 후, \begin{thebibliography} 형식으로도 변환하라.
(NeurIPS 2026은 BibTeX 또는 thebibliography 모두 허용)

### 주의
- 존재하지 않는 reference를 만들지 말 것. 검색해서 찾을 수 없으면 그대로 두고 표시.
- DOI가 있으면 반드시 포함
- 2025년 논문은 arXiv preprint일 가능성 높음

---

## 작업 2: BSR=0 순환성 해소 (우선순위 2)

### 배경 (self-critical-review #12)
리뷰어 B 지적: "CGA-Bench achieves BSR=0 by construction은 순환적 — 자기 evaluator가 정의한 violation set으로 자기를 0이라 부르는 것"

### 수정 내용

main.tex에서 CGA-Bench BSR = 0.0%가 나오는 모든 곳에 다음 중 하나를 적용:

Option A (footnote):
```latex
CGA-Bench achieves BSR = \bsrCGA{}\% by construction\footnote{This is a structural property, not an empirical finding: any trace that violates a hard constraint receives a \emph{fail} verdict under CGA-Bench scoring, so no false-accepts are possible by definition. The clinically meaningful question---whether the constraints themselves are valid---is addressed through provenance chains (Section~\ref{sec:engine}) and clinician review (Appendix~\ref{app:clinician}).}
```

Option B (본문 수정):
```latex
CGA-Bench achieves BSR = 0\% \emph{by construction}: it checks all four constraint types, so any hard violation produces a fail. This is not an empirical claim but a structural guarantee. The validity of this guarantee depends on whether the underlying constraints are clinically correct---a question we address through provenance tracing and clinician review.
```

### 파일 수정
main.tex에서 `bsrCGA` 또는 `BSR = 0`을 검색하여 모든 출현 위치에 적용.
현재 확인된 위치:
- Section 5.3 (E2 결과)
- Conclusion

---

## 작업 3: BSR joint vs conditional 구분 (우선순위 3)

### 배경 (self-critical-review #11)
리뷰어 B 지적: "joint probability로 쓰고 conditional rate로 읽는다"

### 수정 내용

Section 3.3에 이미 BSR과 BSR_cond가 정의되어 있다.
Section 5.3 (E2 결과)의 table과 본문에서 이 구분을 일관되게 사용:

```latex
% E2 table에 두 행 추가
BSR (joint)     & ... & ... & ... \\
BSR$_{\text{cond}}$ (false-accept rate) & ... & ... & ... \\
```

이 수치는 episode 재실행 후 나오므로, 지금은 **매크로만 정의**하고 자리만 잡아두면 됨:
```latex
\newcommand{\bsrJointAC}{\textbf{TBD}}
\newcommand{\bsrCondAC}{\textbf{TBD}}
```

---

## 작업 4: Croissant Metadata (우선순위 4)

### 배경
NeurIPS Datasets & Benchmarks Track 필수 요구사항.
Croissant은 dataset을 기계가 읽을 수 있는 형식으로 기술하는 JSON-LD 표준.

### 작업 내용

`croissant.json` 파일을 생성한다:

```json
{
  "@context": {"@vocab": "http://mlcommons.org/croissant/"},
  "@type": "sc:Dataset",
  "name": "CGA-Bench",
  "description": "Clinical Guideline Adherence Benchmark for medical AI agents",
  "license": "CC-BY-4.0",
  "url": "https://github.com/anonymous/cga-bench",
  "distribution": [
    {
      "@type": "cr:FileObject",
      "name": "cpg-graphs",
      "description": "Clinical Practice Guideline graphs in YAML format",
      "contentUrl": "cpg_model/graphs/",
      "encodingFormat": "application/yaml",
      "fileCount": 25
    },
    {
      "@type": "cr:FileObject", 
      "name": "scenarios",
      "description": "Evaluation scenarios (manual + auto-generated)",
      "contentUrl": "configs/scenarios/",
      "encodingFormat": "application/yaml"
    },
    {
      "@type": "cr:FileObject",
      "name": "episodes",
      "description": "Agent episode traces",
      "contentUrl": "results/",
      "encodingFormat": "application/json"
    }
  ],
  "recordSet": [
    {
      "@type": "cr:RecordSet",
      "name": "episodes",
      "description": "Individual agent-environment interaction episodes",
      "field": [
        {"name": "scenario_id", "dataType": "sc:Text"},
        {"name": "model_id", "dataType": "sc:Text"},
        {"name": "run_id", "dataType": "sc:Integer"},
        {"name": "compliance_score", "dataType": "sc:Float"},
        {"name": "violations", "dataType": "sc:Text"},
        {"name": "verdict", "dataType": "sc:Text"}
      ]
    }
  ]
}
```

실제 필드명은 episode JSON 구조에 맞게 조정. Croissant 공식 스키마(https://mlcommons.org/croissant/)를 참조.

---

## 작업 5: Guideline Cards Content (우선순위 5)

### 배경
논문 Section 4.5와 Appendix에 Guideline Cards skeleton이 있지만 실제 content가 비어 있음.

### 작업 내용

25개 CPG graph 각각에 대해 Guideline Card를 작성:

```yaml
# 각 graph당 1개 카드
graph_id: ssc_sepsis_hour1_bundle
guideline_name: Surviving Sepsis Campaign Hour-1 Bundle
source: Rhodes et al., Intensive Care Medicine, 2017
version: "2021 update"
scope: "Emergency management of adult sepsis and septic shock"
target_population: "Adults ≥ 18 with suspected or confirmed sepsis"
constraint_summary:
  forbidden: ["delay_antibiotics_beyond_1h", "..."]
  required: ["obtain_blood_cultures", "measure_lactate", "..."]
  before: ["blood_cultures BEFORE antibiotics"]
  within: ["antibiotics WITHIN 60min of recognition"]
total_constraints: N  # graph에서 자동 계산
evidence_level: "Class I / Level A (SSC 2021)"
known_limitations: 
  - "Hour-1 target is debated; some guidelines use 3-hour window"
  - "Lactate clearance target varies by institution"
```

모든 25개 graph의 YAML을 읽고 위 형식으로 Guideline Card를 자동 생성하는 스크립트를 작성하라.
Evidence level과 known_limitations는 graph YAML의 metadata + 임상 지식에서 도출.

---

## 실행 순서

이 5개 작업은 모두 episode 실행과 독립이므로 동시 진행 가능.
1번(References)부터 시작하고, 완료되는 대로 다음으로 넘어가라.