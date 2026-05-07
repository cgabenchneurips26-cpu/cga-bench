# Session Handoff: vLLM qwen397b + Auto Graph Pipeline
<!-- 2026-04-29 16:35 UTC -->

## Goal
Option B (LLM-based auto graph generation from rag_corpus) 파이프라인을 실행하기 위해 Qwen3.5-397B-A17B-FP8 endpoint를 올리는 것.

## Current State (144 Server)

### GPU 상태
- **GPU 0-3**: vLLM Worker_TP0-3 (PID 838588-838591) — 99GB each — OOM으로 crash된 zombie
- **GPU 4-7**: vLLM Worker_TP0-3 (PID 839386-839389) — 103GB each — 누군가 새로 올린 인스턴스

### 필요한 조치
1. **GPU 0-3 zombie 프로세스 kill**: `kill -9 838588 838589 838590 838591`
2. **GPU 4-7 인스턴스 확인**: 정상 동작하면 그대로 쓰기. 포트/API key 확인 필요.
3. 안되면 전부 kill 후 TP=8로 재시작 (아래 명령어)

## Root Cause Analysis

### 왜 Docker가 안 됐는가
1. **vllm-qwen35:latest (v0.16.0rc2-dev)**: shm_broadcast hang — V1 engine IPC 버그. 2번째 인스턴스에서 발생. 1번째도 초기화 후 외부 kill (signal 9) 당함.
2. **vllm/vllm-openai:v0.19.0 Docker**: Container crash 반복 (원인 불명, auto-removed by --rm)

### 왜 Native vLLM v0.19.0이 안 됐는가 (3번의 시도)
1. **1차**: Worker-3 died — `ninja` 미설치로 FlashInfer GDN kernel JIT 컴파일 실패
2. **2차 (ninja 설치 후)**: `CUDA_VISIBLE_DEVICES=0,1,2,3` 설정했으나 **8개 GPU 전부에 메모리 할당** → TP=4인데 GPU당 95GB 사용 → OOM
3. **핵심**: Qwen3.5는 Attention+Mamba 하이브리드 → GDN 레이어가 추가 메모리 소비 → TP=4로는 GPU당 메모리 부족

### 해결된 것
- `ninja` v1.13.0 설치 완료: `/home/anonymous-user/.local/bin/ninja`
- FlashInfer GDN JIT 컴파일 문제 해결
- Native vLLM v0.19.0 경로 확인: `/home/anonymous-user/.local/bin/vllm`

## Recommended Launch Command (TP=8)

```bash
# 144 서버에서 직접 실행 (SSH로)
ssh -i /tmp/anonymous-org_key [email-redacted]

# 1. 기존 프로세스 전부 kill
kill -9 838588 838589 838590 838591 839386 839387 839388 839389

# 2. GPU 메모리 해제 대기 (10-30초)
sleep 15 && nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
# 전부 0 MiB 확인

# 3. TP=8로 재시작 (8개 GPU 전부 사용)
export PATH=/home/anonymous-user/.local/bin:$PATH
nohup vllm serve Qwen/Qwen3.5-397B-A17B-FP8 \
  --port 30001 \
  --tensor-parallel-size 8 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.90 \
  --enforce-eager \
  --api-key sk-no-key-required \
  > /home/anonymous-user/vllm_qwen397b.log 2>&1 &

# 4. 5-7분 대기 후 확인
curl -H 'Authorization: Bearer sk-no-key-required' http://localhost:30001/v1/models
```

### TP=8 선택 이유
- TP=4로 GPU당 ~95GB → OOM (Qwen3.5 하이브리드 모델이 v0.16보다 메모리 더 씀)
- TP=8로 GPU당 ~25GB weights + 충분한 KV cache 여유
- 8개 GPU 전부 비어있으므로 리소스 낭비 없음

### 대안: TP=4 + 낮은 memory utilization
```bash
# gpu-memory-utilization을 0.80으로 낮추면 될 수도 있음
nohup env CUDA_VISIBLE_DEVICES=0,1,2,3 vllm serve Qwen/Qwen3.5-397B-A17B-FP8 \
  --port 30001 --tensor-parallel-size 4 --max-model-len 8192 \
  --gpu-memory-utilization 0.80 --enforce-eager \
  --api-key sk-no-key-required \
  > /home/anonymous-user/vllm_qwen397b.log 2>&1 &
```

## Option B Pipeline (endpoint 올라간 후 실행)

```bash
# 146 서버에서 (cga_bench 디렉토리)
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench

# 1. 단일 그래프 테스트
PYTHONPATH=. python scripts/cpg_v2_phase_annotation/auto_graph_pipeline.py \
  --mode generate \
  --corpus data_release/v5.0/rag_corpus/WSES-2020-Acute-Appendicitis.parsed.json \
  --graph-id wses_acute_appendicitis_2020 \
  --guideline-name "WSES Acute Appendicitis 2020" \
  --endpoint http://localhost:8013/v1 \
  --output /tmp/test_generated_graph.yaml \
  --dry-run

# 2. 배치 실행 (16개 매칭된 auto 그래프)
PYTHONPATH=. python scripts/cpg_v2_phase_annotation/auto_graph_pipeline.py \
  --mode auto \
  --graphs-dir cpg_model/graphs/auto/ \
  --corpus-dir data_release/v5.0/rag_corpus/ \
  --endpoint http://localhost:8013/v1 \
  --report reports/pipeline_report.json
```

## Code Status (완료된 것)

### Explainable Auto Graph Pipeline (Tasks 1-5 DONE)
- **Task 1**: `scripts/cpg_v2_phase_annotation/ground_graph_quotes.py` — Option A (quote grounding)
- **Task 2**: `scripts/cpg_v2_phase_annotation/generate_graph_from_corpus.py` — Option B (LLM generation)
- **Task 3**: `scripts/cpg_v2_phase_annotation/auto_graph_pipeline.py` — Orchestrator
- **Task 4**: `scripts/ci/audit_sources.py` — CI validation extension
- **Task 5**: `tests/test_ci/test_ground_graph_quotes.py` — 29/29 tests pass
- **Commit**: `fb518eb1` on `eval_science` branch

### 미완료
- **Task 6**: Pilot run — endpoint 필요 (이 문서의 목적)
- **Option A (grounding) 단독 실행**: endpoint 없이도 가능 — rag_corpus에서 기존 graph quotes 검증

## Server Reference

| Server | IP | GPUs | Account | Key |
|--------|-----|------|---------|-----|
| 144 | 127.0.0.1 | H200 x 8 (cap 89) | anonymous-user | /tmp/anonymous-org_key |
| 145 | 127.0.0.1 | A100 x 8 (cap 80) | anonymous-org | /tmp/anonymous-org_key |
| 146 | localhost | Local GPUs | - | - |

## Memory Files Updated
- `/home/anonymous-user/.claude/projects/.../memory/vllm_144_deployment.md` — Docker/native deployment reference
- `MEMORY.md` — Updated with deployment gotchas

## Key Gotchas
1. **ninja 필수**: FlashInfer GDN kernel JIT에 필요. 설치됨: `/home/anonymous-user/.local/bin/ninja`
2. **PATH 설정**: `/home/anonymous-user/.local/bin`을 PATH에 포함 (vllm, ninja 모두 여기)
3. **CUDA_VISIBLE_DEVICES 주의**: nohup + env 조합에서 child process에 전파 안될 수 있음
4. **TP=4 OOM**: Qwen3.5 하이브리드 모델은 v0.19.0에서 TP=4로 H200 140GB에서도 OOM 발생
5. **144 외부 kill**: 다른 사용자/자동화 스크립트가 컨테이너를 kill할 수 있음
6. **FP8 on A100**: nemotron30b FP8이 A100에서 crash — Qwen3.5 FP8도 위험
