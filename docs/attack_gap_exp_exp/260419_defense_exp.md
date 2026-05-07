실험 (iii) — Tool-Use Scaffold Expansion (권장 착수)
목표
"Single-scaffold" 공격을 완전 차단. Current 2-scaffold (ReAct + direct I/O) → 3-scaffold. Theorem 3.4의 scaffold-invariance 예측을 empirically 확증.
왜 tool-use인가

ReAct: 계획-관찰-행동 루프 (현재 main)
Direct I/O: single-shot JSON output (현재 ablation)
Tool-use: function-calling API 기반 — 실제 OpenAI/Anthropic 상용배포와 가장 가까움
Reflection은 이미 ReflectionAgent로 variant만 다를 뿐 새 scaffold 아님 → 제외

실행 단계
Day 1–2: Scaffold 구현 (agent_runner/tool_use_agent.py)

각 ActionType을 function schema로 정의 (JSON Schema Draft-7)

order_lab(test_name, priority, timestamp)
give_medication(drug, dose, route, indication)
order_imaging(modality, region, urgency)
procedure, consult, reassess, disposition


vLLM function-calling API 사용 (Qwen3, Llama3는 native 지원; oss120b는 JSON mode fallback)
Function dispatch → 기존 tool_api/ 재사용 (기존 코드 90% 재활용)
Budget matching: current ReAct 100K token budget → tool-use에서는 function schema overhead 제외한 effective token으로 통일

Day 3: Smoke test

10 scenarios × 8 models × 1 run 돌려서 format 에러 없는지 확인
Qwen 4B가 tool-use 지원하는지 체크 (못하면 결과 그대로 보고)
Budget tracking이 기존 P2 fix와 호환되는지

Day 4–6: Full run

706 scenarios × 8 models × 3 runs = 16,944 episodes
기존 full_690_runner.py / shard_runner.py 재활용
GPU 시간: 4× A100 기준 40–50h wall
결과 저장: results/full_706_v5_toolsuse/

Day 7: 분석 + paper 통합

Scaffold-invariance 통계 (3-way McNemar / Cochran Q)

H0H_0
H0​: FA rate는 세 scaffold에서 동일

Expected: fail to reject → Theorem 3.4 invariance confirmed


Limitations 첫 문단 수정:

  "a two-scaffold comparison" → "a three-scaffold comparison (ReAct, direct I/O, tool-use)"
  \promptScaffoldReactAOFA vs \promptScaffoldDirectAOFA  →  3-way values

Appendix D에 tool-use scaffold 상세 + per-model breakdown

신규 auto-numbers 매크로
\scaffoldToolUseAOFA   (예상 ~28% 주변)
\scaffoldThreeWayChi   (Cochran Q χ²)
\scaffoldThreeWayP
\scaffoldThreeWayKappa (3-way agreement)
Risk & Mitigation
리스크발생확률Mitigation작은 모델이 function-calling 못 함높음결과 그대로 보고 — FA 측정엔 영향 없음 (FA는 pass인데 violation인 케이스를 보는 것이므로 모델 성능 무관)3-scaffold에서 invariance 깨짐낮음오히려 더 흥미로운 story ("structural projection은 불변이지만 coverage는 scaffold-dependent")로 전환 가능Budget 불공정 논란중간effective-action-budget(50 actions) 통일. Appendix에 protocol 명시
총 공수: 40–50 person-hours + 50h GPU

실험 (ii) — MedAgentBench Native End-to-End Reproduction
타겟 선정
세 외부벤치마크 중 MAB만:

MAB: action-F1을 scorer로 쓰고 FHIR 환경 — 우리 trace 포맷과 trivial 매핑 가능
AgentClinic: multimodal + patient simulator LLM 필요 → infra 2배
AMEGA: rubric 기반, trace 없음 → projection 실험 대상 아님

실행 단계
Week 1: Infra 구축

MAB repo clone (MedAgentBench 2025 NEJM AI)
FHIR mock server docker-compose 설정 (공식 제공)
MAB test set (N=300 tasks 추정) 다운로드
우리 run_external_benchmark.py 의 기존 MAB adapter 확인/갱신

Week 1–2: Action taxonomy 매핑

MAB의 FHIR action (patch, post, get on FHIR resources) → CGA-Bench ActionType
MedicationRequest POST → give_medication
ServiceRequest POST (lab) → order_lab
ServiceRequest POST (imaging) → order_imaging
매핑 테이블 mab_to_cgabench_mapping.yaml 공개
변환 후 trace가 PatientState 에 정상 attach되는지 E2E 검증

Week 2: Trace 생성 Run

8 models × 300 MAB tasks × 3 runs = 7,200 episodes
ReAct scaffold로 돌리되 MAB 네이티브 interface (FHIR tool API)
저장: results/mab_native_run/
동시에 MAB-native F1 scorer 계산 + CGA-Bench TCC 계산

Week 2–3: Cross-paradigm 분석

핵심 비교: 동일 trace에 대해 MAB F1 pass 비율 vs TCC fail 비율
예상: MAB F1 pass 에피소드의 X%X\%
X% 가 TCC에서 fail → 이것이 "projection-predicted FA rate"

현재 paper의 E8 숫자 (\crossReplayMABFA{}%)가 native 재현에서도 유사하게 나오면 → E8을 "projection-transfer probe"에서 "cross-benchmark validation"으로 업그레이드 가능

Week 3: Paper 통합

§5.8 "E8: cross-paradigm stress test" 섹션을 native-run 숫자로 갱신
Limitations 둘째 문단의 "native reproduction ongoing" 제거
새 Appendix app:mab_native_reproduction (매핑 표, per-task breakdown, FHIR-side action 의미)

Risk & Mitigation
리스크발생확률MitigationFHIR mock server 세팅 실패중간공식 docker-compose 이미지가 깨져있으면 AgentClinic으로 pivotMAB action과 our action 매핑 mismatch중간Soft matching (Jaccard ≥0.7) 사용; unmapped → "out-of-taxonomy" bin으로 분리 보고MAB에서 우리 숫자(\crossReplayMABFA)가 재현 안 됨낮음-중간프레이밍 후퇴: "native run confirms direction but absolute rates differ (protocol A vs B)" — 여전히 story는 살아있음MAB test set 저작권 제약낮음NEJM AI CC-BY 확인; 불가 시 우리 trace만 저장, MAB input은 재배포 안 함
총 공수: 80–100 person-hours + 20h compute