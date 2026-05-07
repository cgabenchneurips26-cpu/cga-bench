P0 — 가장 비싼 공격을 선제 차단
MedAgentBench / AgentClinic native replay (C3 방어). 현재 E8 는 "AC-style / MAB-style adapter" 라는 시뮬레이션이고, reviewer 가 "그건 MAB 가 아니라 너네 재구현이잖아" 로 때릴 수 있는 가장 큰 약점입니다. AMEGA 와 같은 경로로 run_external_benchmark.py --benchmark medagentbench --agent llm_assist / --benchmark agentclinic 을 3개 모델에서 돌려두면, E8 이 "replay-style → real native benchmark" 으로 승격됩니다.

bash   PYTHONPATH=. python run_external_benchmark.py --benchmark medagentbench --llm-model "OpenGVLab/oss120b" --llm-backend vllm --llm-endpoint <EP> --limit 200
   PYTHONPATH=. python run_external_benchmark.py --benchmark agentclinic --llm-model "Qwen/Qwen3-30B-A3B-Instruct-2507" --llm-backend vllm --llm-endpoint <EP> --limit 200
Strong LLM judge variant (GPT-4o 혹은 Claude) (M6 방어). 현재 LLM-judge 는 Qwen3.5-35B 뿐 — "네가 쓴 judge 가 약해서 그런거 아니냐" 공격이 옵니다. 같은 E1 matched-pair 에 대해 GPT-4o / Claude 4.5 / Gemini 2.5 를 judge 로 한 번씩만 돌려도 "frontier LLM judge 도 action-list 위에서는 T₂ projection blind-spot 을 못 고침" 증거가 확보됩니다.
P1 — 추가 강화
Temperature sweep (T ∈ {0.0, 0.3, 0.7}) 1 모델 × 100 scenarios. "T=0.1 이라서 deterministic 이라 그런거" 공격 차단. AMEGA 돌리는 endpoint 그대로 사용, 옵션만 바꾸면 됨.

Held-out graph 3개 모델 크로스-cover 확인 (ards / dic / hyperkalemia / thyroid_storm / agitation_delirium). 기존 scripts/experiments/full_690_runner.py 에서 held-out 가 누락된 조합이 있다면 채워두면 appendix tab:fa_per_model 의 held-out 칼럼을 완성할 수 있음.

Prompt sensitivity — 동일 모델에 3개 system prompt variant. Qwen 에서 경험적으로 민감도가 있으므로 (CLAUDE.md §Qwen prompt sensitivity) 한 번 quantify 해두면 reviewer 선제차단.
P2 — 여유 있을 때
Clock-step sensitivity extension — appendix 에 이미 1/2/5/10분 sweep 일부만 있음. 전체 범위 채우기.

Run-level variance bootstrap (η² CI) — 현재 η²_evaluator / η²_run ratio 는 점추정. 95% CI 를 붙이면 "variance decomposition 이 통계적으로 robust" 논증이 완성.