# External Benchmark Scale Analysis & Execution Plan

## 1. 벤치마크별 전체 데이터 규모 vs 현재 실행 규모

### 1.1 Action-Level Evaluation (CPG scoring 가능)

| Benchmark | 전체 케이스 | 돌린 수 | 비율 | 평가 방식 | 데이터 위치 |
|-----------|------------|---------|------|----------|------------|
| **AgentClinic** | 456 | 20 | 4.4% | Live LLM agent | `data/external_benchmarks/AgentClinic/` |
| **MedAgentBench** | 300 (v2) | 20 | 6.7% | Live LLM agent | `data/external_benchmarks/MedAgentBench/` |
| **MedChain** | 12,163 | 20 | 0.16% | Live LLM agent | `data/external_benchmarks/MedChain/` |
| **HealthBench** | 5,000 (eval) | 50 | 1.0% | Live LLM (oss-120b) | HuggingFace (OpenAI) |

### 1.2 Assessment-Level Evaluation (pipeline only, no CPG scoring)

| Benchmark | 전체 케이스 | 돌린 수 | 비율 | 평가 방식 | 데이터 위치 |
|-----------|------------|---------|------|----------|------------|
| **AMEGA** | 24 | 24 | 100% | Static pipeline | `data/external_benchmarks/amega/` |
| **LLMEval-Med** | 667 | 50 | 7.5% | Static pipeline | `data/external_benchmarks/llmeval_med/` |

### 1.3 Sample Only / Not Available

| Benchmark | 전체 케이스 | 돌린 수 | 상태 | 비고 |
|-----------|------------|---------|------|------|
| **ART** | 5 (synthetic) | 0 | Full data unreleased | arxiv 2601.08988 |
| **AgentEHR** | 5 (sample) | 0 | PhysioNet 필요 | HF: BlueZeros/AgentEHR-Bench |
| **FHIR-AgentBench** | 49,439 | 0 | 로컬 데이터 있음 | SQL/FHIR query, CPG 평가와 무관 |
| **CliBench** | ? | 0 | PhysioNet 필요 | MIMIC-IV derived |
| **MedGUIDE** | 7,747 | 0 | NCCN 허가 필요 | 55 decision trees |

### 1.4 AgentClinic 데이터 세부 구성

| File | Cases |
|------|-------|
| `agentclinic_medqa.jsonl` | 107 |
| `agentclinic_medqa_extended.jsonl` | 214 |
| `agentclinic_nejm.jsonl` | 15 |
| `agentclinic_nejm_extended.jsonl` | 120 |
| **Total** | **456** |

---

## 2. 현재 Cross-Comparison 현황

현재 feasibility report에서 사용된 데이터:

| Benchmark | N (cross-comparison) | Discordant | Discordant % |
|-----------|---------------------|------------|--------------|
| AgentClinic | 20 | 6 | 30% |
| MedAgentBench | 20 | 10 | 50% |
| MedChain | 20 | 2 | 10% |
| HealthBench | 50 | 7 | 14% |
| **Total** | **110** | **25** | **23%** |

---

## 3. 통계적 유의성을 위한 최소 샘플 크기

### 3.1 목표
- Discordant rate의 95% CI width < ±10%p
- 현재 관찰된 discordant rate: 23% (25/110)

### 3.2 Sample Size 계산

이항 비율의 신뢰구간: `n ≥ (z²·p·(1-p)) / E²`

```
z = 1.96 (95% CI)
p = 0.23 (관찰된 discordant rate)
E = 0.10 (margin of error ±10%p)

n ≥ (1.96² × 0.23 × 0.77) / 0.10²
n ≥ (3.8416 × 0.1771) / 0.01
n ≥ 68.04
```

**최소 N ≥ 68 per benchmark** (±10%p margin)

더 정밀한 ±5%p를 원하면:
```
n ≥ (1.96² × 0.23 × 0.77) / 0.05²
n ≥ 272
```

### 3.3 벤치마크별 적정 N

| Benchmark | 전체 | 목표 N | 근거 |
|-----------|------|--------|------|
| AgentClinic | 456 | **100** | ±10%p CI, 전체의 22% |
| MedAgentBench | 300 | **100** | ±10%p CI, 전체의 33% |
| MedChain | 12,163 | **100** | ±10%p CI, random sample |
| HealthBench | 5,000 | **100** | ±10%p CI, random sample |
| AMEGA | 24 | **24 (전체)** | 전체가 68 미만, 전수 조사 |
| LLMEval-Med | 667 | **100** | ±10%p CI (pipeline only) |

---

## 4. 에피소드당 소요 시간 (실측치)

Live LLM agent 평가 (Qwen3.5-35B-A3B-FP8, vLLM):

| Benchmark | Avg/episode | 20 ep 실측 | 소요 시간 |
|-----------|-------------|------------|----------|
| **AgentClinic** | 16.4s | 327s | 5.5 min |
| **MedAgentBench** | 27.2s | 545s | 9.1 min |
| **MedChain** | 14.1s | 281s | 4.7 min |
| **HealthBench** | 20.3s | 1,014s (50ep) | 16.9 min |

Static pipeline 평가 (no LLM):

| Benchmark | Avg/episode | 비고 |
|-----------|-------------|------|
| **AMEGA** | <1s | 24건 즉시 완료 |
| **LLMEval-Med** | <1s | 50건 즉시 완료 |

---

## 5. 목표 N=100 기준 GPU 시간 추정

| Benchmark | 추가 필요 | Avg/ep | 추가 시간 | 총 시간 (100ep) | GPU 필요 |
|-----------|----------|--------|----------|----------------|---------|
| **AgentClinic** | 80건 | 16.4s | 21.9 min | 27.3 min | vLLM 1대 |
| **MedAgentBench** | 80건 | 27.2s | 36.3 min | 45.3 min | vLLM 1대 |
| **MedChain** | 80건 | 14.1s | 18.8 min | 23.5 min | vLLM 1대 |
| **HealthBench** | 50건 | 20.3s | 16.9 min | 33.8 min | vLLM 1대 |
| **AMEGA** | 0건 | — | — | — | 완료 |
| **LLMEval-Med** | 50건 | <1s | <1 min | <2 min | CPU only |
| **Total** | **340건** | — | **~94 min** | **~132 min** | — |

**총 추가 GPU 시간: ~94분 (1.6시간)**
**4벤치마크 병렬 실행 시: ~37분** (가장 긴 MedAgentBench 기준)

---

## 6. 실행 계획

### Phase 1: 즉시 실행 가능 (GPU 불필요)

| 작업 | 대상 | 시간 |
|------|------|------|
| AMEGA 전체 | 이미 완료 (24/24) | 0 min |
| LLMEval-Med 100건 | 추가 50건 pipeline | <1 min |

### Phase 2: Live LLM 실행 (vLLM 서버 필요)

**실행 명령 템플릿:**
```bash
# AgentClinic 100건
python run_external_benchmark.py --benchmark agentclinic \
  --agent llm_assist --limit 100 \
  --llm-model "Qwen/Qwen3.5-35B-A3B-FP8" \
  --llm-backend vllm --llm-endpoint "http://localhost:8013/v1"

# MedAgentBench 100건
python run_external_benchmark.py --benchmark medagentbench \
  --agent llm_assist --limit 100 \
  --llm-model "Qwen/Qwen3.5-35B-A3B-FP8" \
  --llm-backend vllm --llm-endpoint "http://localhost:8013/v1"

# MedChain 100건
python run_external_benchmark.py --benchmark medchain \
  --agent llm_assist --limit 100 \
  --llm-model "Qwen/Qwen3.5-35B-A3B-FP8" \
  --llm-backend vllm --llm-endpoint "http://localhost:8013/v1"

# HealthBench 100건
python run_external_benchmark.py --benchmark healthbench \
  --agent llm_assist --limit 100 \
  --llm-model "Qwen/Qwen3.5-35B-A3B-FP8" \
  --llm-backend vllm --llm-endpoint "http://localhost:8013/v1"
```

### Phase 3: 결과 분석

100건 기준 예상 discordant 수 (현재 rate 유지 가정):

| Benchmark | N=100 | 예상 discordant | 95% CI |
|-----------|-------|----------------|--------|
| AgentClinic | 100 | ~30 | 21-39 |
| MedAgentBench | 100 | ~50 | 40-60 |
| MedChain | 100 | ~10 | 4-16 |
| HealthBench | 100 | ~14 | 7-21 |
| **Total** | **400** | **~104** | 87-121 |

**총 400건, discordant ~104건 → 95% CI: 21.8%-30.3% (width ±4.2%p)**

이 수준이면 NeurIPS paper에 "~25% of episodes show discordance across 4 benchmarks (N=400, 95% CI: 22-30%)" 라고 쓸 수 있음.

---

## 7. 전체 실행 vs 샘플링 판단

| Benchmark | 전체 | 전체 시간 | 판단 |
|-----------|------|----------|------|
| **AgentClinic** | 456 | ~125 min | **전체 가능** (2시간) |
| **MedAgentBench** | 300 | ~136 min | **전체 가능** (2.3시간) |
| **MedChain** | 12,163 | ~2,858 min | **Random sample 100** (48시간 불가) |
| **HealthBench** | 5,000 | ~1,692 min | **Random sample 100-200** (28시간 불가) |
| **AMEGA** | 24 | 완료 | **전체 완료** |
| **LLMEval-Med** | 667 | <11 min | **전체 가능** (pipeline) |

### 추천 실행 계획

| Priority | Benchmark | 목표 N | 예상 시간 | 비고 |
|----------|-----------|--------|----------|------|
| P0 | AMEGA | 24 (완료) | 0 | 이미 완료 |
| P0 | LLMEval-Med | 667 (전체) | <11 min | Pipeline, CPU only |
| P1 | AgentClinic | 456 (전체) | ~125 min | 가장 다양한 clinical cases |
| P1 | MedAgentBench | 300 (전체) | ~136 min | 50% discordant, 핵심 evidence |
| P2 | MedChain | 100 (sample) | ~24 min | Random seed 42 |
| P2 | HealthBench | 200 (sample) | ~68 min | eval split에서 random |

**총 실행 시간: ~364 min (6.1시간)**
**P1까지만 하면: ~261 min (4.4시간)**

### Random Sampling 근거 (MedChain, HealthBench)

- MedChain (12,163건): 전체 실행 시 48시간. N=100 random sample로 ±10%p CI 확보.
  - `random.seed(42)` + `random.sample(range(12163), 100)`
- HealthBench (5,000건): 전체 실행 시 28시간. N=200 random sample로 ±7%p CI 확보.
  - `random.seed(42)` + `random.sample(range(5000), 200)`
  - N=200 선택 근거: HealthBench가 유일한 physician-graded rubric으로 가장 설득력 있는 cross-comparison이므로 larger sample.

---

## 8. 결과 테이블 (실행 후 예상)

```
┌───────────────┬──────────┬─────────┬─────────┬────────────┬───────────────┐
│   Benchmark   │ 전체     │ 돌린 수 │ 비율    │ Discordant │ 95% CI width  │
├───────────────┼──────────┼─────────┼─────────┼────────────┼───────────────┤
│ AgentClinic   │ 456      │ 456     │ 100%    │ ~137       │ exact (전수)  │
│ MedAgentBench │ 300      │ 300     │ 100%    │ ~150       │ exact (전수)  │
│ MedChain      │ 12,163   │ 100     │ 0.8%   │ ~10        │ ±10%p         │
│ HealthBench   │ 5,000    │ 200     │ 4.0%   │ ~28        │ ±7%p          │
│ AMEGA         │ 24       │ 24      │ 100%    │ N/A (QA)   │ exact (전수)  │
│ LLMEval-Med   │ 667      │ 667     │ 100%    │ N/A (QA)   │ exact (전수)  │
├───────────────┼──────────┼─────────┼─────────┼────────────┼───────────────┤
│ Total (scored)│ 17,919   │ 1,056   │ 5.9%   │ ~325       │ ±2.6%p        │
│ Total (all)   │ 18,610   │ 1,747   │ 9.4%   │ —          │ —             │
└───────────────┴──────────┴─────────┴─────────┴────────────┴───────────────┘
```

---

## 9. Paper Claim 강화 예시

### 현재 (N=110)
> "25/110 episodes (23%) show discordance across 4 benchmarks."

### 실행 후 (N≈1,056 scored)
> "Cross-comparison across 4 external benchmarks (AgentClinic N=456, MedAgentBench N=300, MedChain N=100, HealthBench N=200; total N=1,056) reveals X% discordance (95% CI: Y%-Z%), confirming that existing outcome-only metrics have systematic blind spots that CGA detects."
