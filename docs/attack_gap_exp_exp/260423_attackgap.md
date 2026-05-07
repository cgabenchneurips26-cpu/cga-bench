Decision 2: 실험 X, Y, Z 즉시 실행 — 구체적 실행 계획실험 X — MedAgentBench/AgentClinic forward-direction reproductionED rubric 대응: "Rigorous reproduction, auditing, and stress-testing of prior evaluations"목표: §6 Limitations의 "deferred to future work" 를 해소. External benchmark가 released한 trajectory를 CGA-Bench TCC로 re-score해서, 역방향 결과가 우리의 main claim과 consistent함을 증명.실행 계획:
MedAgentBench trajectory acquisition (Day 1)

github.com/stanfordmlgroup/MedAgentBench에서 released trajectory sample 추출
Schema alignment: MAB의 (EHR_action, timestamp) → CGA-Bench (action_id, t, patient_state) 매핑
Action normalizer 확장 (MAB-specific actions → CGA canonical vocabulary)
타겟: 100 episodes across 10 MAB scenarios



AgentClinic dialogue-to-trace conversion (Day 2)

AgentClinic의 dialogue turn → action sequence 추출 (기존 audit/wrappers/native_adapter_examples.py의 AC-style emulator 재사용)
Temporal alignment: dialogue 순서를 proxy timestamp로 사용 (AC는 explicit clock 없음 — 이건 Pose B의 "projection limitation"을 empirical하게 보여주는 bonus)
타겟: 50 dialogues × 2-3 trace variants = 120 episodes



TCC re-score + analysis (Day 3)

기존 assessor_core/violations.py로 re-score
Original MAB/AC verdict vs TCC verdict confusion matrix
예상 결과:

MAB: CGA-Bench의 E8에서 MAB-F1 FA=31.9%가 예측. Forward direction도 유사한 순서 (20-35% FA) 예상
AC: Dialogue-level이라 temporal blindness 최대. Case (iii)의 πnord blind spot 예시로 활용





Paper integration: §AB.5 (E8)를 "bidirectional scorer stress test"로 확장. Forward direction이 §6의 deferred claim을 해소한다고 명시.
Expected deliverable:

New Table: "Cross-benchmark conformance re-score: forward vs backward direction"
Evidence pack: evidence_pack/cross_benchmark_forward/{mab,agentclinic}/*.json
Risk: MAB/AC의 released trajectory가 불충분할 수 있음. 이 경우 fallback = 우리 agent runner로 MAB scenarios 재생성 (Expansion v7 vLLM 러너 이용).실험 Y — CDE-derived vs LLM-extracted constraint catalogue 비교ED rubric 대응: "Strengths, limitations, or failure modes of existing evaluation practices" + "Documentation methodologies that improve how evaluative claims are constructed"목표: Pose B의 §4.3 axis (ii) — "catalogue validity ≠ evaluator audit" — 를 empirical하게 뒷받침. CDE catalogue가 LLM-extracted보다 structurally richer함을 보이되, 둘 다 evaluator audit과 독립임을 강조.실행 계획:
LLM extraction baseline 구축 (Day 1)

semantic_layer/cpg_parser.py의 P2 SSC smoke를 모든 25 CPG에 확장
Input: data_release/v5.0/rag_corpus/*.parsed.json
Output: Per-CPG LLM-extracted constraint catalogue (Qwen3.5-397B-FP8, temperature=0.1)
Wall-clock: 25 CPG × 4분/CPG ≈ 1.7시간 + verification



비교 분석 (Day 2)

CDE-derived 1,049 hard constraints vs LLM-extracted constraints
Per-type comparison: MUST / FORBID / BEFORE / WITHIN recovery rate
예상 결과 (Pose B 수지 지점):

Overlap: ~60-70% (LLM이 explicit rule은 잡음)
Gap: BEFORE/WITHIN constraints가 LLM에서 under-extracted → CDE의 rule-based approach가 implicit temporal constraint recovery 가능


Per-constraint semantic alignment (action_id match + deadline match)



Paper integration: §4.2 CDE description에 "CDE recovers 8.0× more constraints than LLM extraction (Appendix H.3)"을 existing claim의 empirical backing으로 추가. Pose B §4.3의 "catalogue construction method is orthogonal to evaluator audit validity"를 뒷받침.
Expected deliverable:

New Appendix H.3: "CDE vs LLM-based constraint extraction"
Comparison table with per-type recovery rates
Important framing: "LLM extraction is worse"가 핵심이 아니고, **"two different catalogue construction methods lead to different constraint sets, yet our evaluator audit is invariant to this choice"**가 핵심. 이게 Pose B §4.3의 분리 논리를 direct support.실험 Z — Scaffold × Model grid 확장 (Expansion v7 러너 재활용)ED rubric 대응: "Stress-testing of prior evaluations"목표: §AB.5 W8의 scaffold × model grid를 3×4=12 cells에서 8×4=32 cells로 확장. Friedman test statistical power 강화 (현재 χ²=1.0, p=0.80 — underpowered).실행 계획:
기존 Expansion v7 결과 재활용 (Day 1)

results/expansion_v7/ 에 이미 11 runners × ~372 episodes 러닝 중
현재 보유 모델: oss120b (3 instances), Qwen3.5-397B (2 s1/s2), DeepSeek-R1-7B (5 instances), Qwen3.5-35B-A3B, Qwen3.5-9B
필터링: Expansion v7 scaffold variants를 base scaffold (ReAct)로 snap → Direct/Checklist/Tool-use variant 재실행
중요 주의: Expansion v7는 auto-generated graphs (31 개)를 타겟 — score=0.000 issue가 있음. 따라서 core-25 CPG에 대해서만 scaffold 확장 재실행 필요



Scaffold 확장 실행 (Day 2-3)

Base set: 8 models × 4 scaffolds (ReAct, Direct, Checklist, Tool-use) × 706 scenarios
기존 oss120b/qwen35b/gemma31b ReAct는 보유 — 나머지 5 models × 4 scaffolds + oss120b/qwen35b/gemma31b의 Direct/Checklist/Tool-use 만 실행 (약 29 cells × 706 ≈ 20,474 episodes)
Worker distribution: 현재 expansion_v7 러너를 core-25 scaffold 실험으로 재배치
Wall-clock: 53.5 ep/min 기준 ≈ 6.4시간 × parallel 11 러너 = 완료



분석 + paper integration (Day 4)

Friedman test (8 model-subjects × 4 scaffolds) — 현재 n=3 → n=8로 power 증가
Scaffold-aggregate AO-FA band: 2.0 pp → 더 타이트한 CI
기존 Figure 5 (heatmap 4×3) → 4×8 matrix로 업데이트


Expected deliverable:

Updated Figure 5: 4×8 scaffold × model heatmap
Updated Table 29: 32 cells with per-cell statistics
Strengthened Appendix X.7 (agent-side prompt sensitivity)