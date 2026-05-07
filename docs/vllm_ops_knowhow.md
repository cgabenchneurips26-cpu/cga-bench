# vLLM Operations Knowhow

CGA-Bench / SGSC 프로젝트에서 축적된 vLLM 엔드포인트 운영 노하우.
서버 인프라, 기동/정지, 모델별 설정, 워커 관리, 트러블슈팅을 포함한다.

---

## 1. 서버 인프라 개요

| 호스트 | IP | GPU | VRAM | 역할 | vLLM 바이너리 | vLLM 버전 | Python |
|---|---|---|---:|---|---|---|---|
| **144** | `127.0.0.1 | H200 × 8 | 143 GB × 8 = 1,144 GB | 대형 모델 (397B MoE 등) | `~/.local/bin/vllm` | 0.19.0 | 3.10 |
| **145** | `127.0.0.1 | A100 × 8 | 80 GB × 8 = 640 GB | 중소형 모델 fleet | `/home/anonymous-org/anaconda3/bin/vllm` | — | 3.11 |
| **146** | 로컬 (localhost) | A100 × 8 | 80 GB × 8 = 640 GB | 오케스트레이터 + 소형 모델 | `/home/anonymous-org/anaconda3/bin/vllm` | — | 3.13 |

**참고**: Claude Code는 146 (hostname `localhost`, IP `127.0.0.1 실행됨. 144/145 작업은 반드시 SSH로.

SSH 접속:
```bash
# 144 접속 (사용자 anonymous-user)
ssh [email-redacted]

# 145 접속 (사용자 anonymous-org)
ssh 127.0.0.1

# 146에서 원격 실행 (sudo 필요)
sudo -u anonymous-org ssh [email-redacted] 'bash -s' < script.sh
sudo -u anonymous-org ssh 127.0.0.1 'bash -s' < script.sh
```

### 1.1 현재 가동 중 (2026-05-02 확인)

| 호스트 | 포트 | 모델 | TP | max_model_len |
|---|---|---|---:|---:|
| 144 | **30001** | `Qwen/Qwen3.5-397B-A17B-FP8` | 4 | 16,384 |
| 144 | **30002** | `Qwen/Qwen3.5-397B-A17B-FP8` | 4 | 16,384 |
| 146 | 30003 | `google/gemma-4-31b-it` | 1 | 8,192 |
| 146 | 30004 | `nvidia/Nemotron-3-Nano-30B-A3B-FP8` | 1 | 8,192 |
| 146 | 30009 | `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` | 1 | 8,192 |
| 146 | 28010 | `Qwen/Qwen3.5-27B-FP8` | 1 | 8,192 |
| 146 | 8101 | `Qwen/Qwen3-4B-Instruct-2507` | 1 | 8,192 |
| 145 | 30210-30217 | `google/gemma-4-31b-it` | 1 | 8,192 |

인증키: `sk-no-key-required` (모든 엔드포인트 공통)

### 1.2 호스트별 코드/결과 경로

| 호스트 | 코드 경로 | 결과 경로 |
|---|---|---|
| 146 | `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/` | `results/v73_full/` |
| 145 | `/home/anonymous-org/bench_ws/cga_bench/` | `results/v73_full/` |

### 1.3 모델 캐시 경로

| 호스트 | HuggingFace 캐시 | 비고 |
|---|---|---|
| 144 | `~/.cache/huggingface/hub/` | 기본 HF 경로 |
| 145 | `~/.cache/huggingface/hub/` | 기본 HF 경로 |
| **146** | **`/home/hub/`** | 비표준 경로 — `v6_endpoint.sh` 에서 `-v /home/hub:/root/.cache/huggingface` 마운트 |

> **주의**: 146의 캐시가 `/home/hub/`에 있으므로 Docker 마운트 시 반드시 이 경로를 지정해야 함.
> `v6_endpoint.sh` line 26에서 `HF_CACHE` 변수가 이 경로를 참조하도록 수정됨.

---

## 2. 기동 방법 (Launch)

### 2.1 방법 A: Docker 컨테이너 (v6 표준)

**v6_endpoint.sh** — 모든 모델에 대해 검증된 Docker 설정이 내장됨.

```bash
# 기본 사용법
bash scripts/infra/v6_endpoint.sh launch <호스트> <GPU> <포트> <모델키>

# 예시: 144에서 qwen397b, GPU 0-3, 포트 30001
bash scripts/infra/v6_endpoint.sh launch 144 0,1,2,3 30001 qwen397b

# 예시: 145에서 gemma31b, GPU 3, 포트 30010
bash scripts/infra/v6_endpoint.sh launch 145 3 30010 gemma31b

# 예시: 144에서 nemotron30b, GPU 4-5, 포트 30013
bash scripts/infra/v6_endpoint.sh launch 144 4,5 30013 nemotron30b
```

내부적으로 실행되는 Docker 명령 구조:
```bash
docker run -d --rm --runtime=nvidia --init \
  -e "NVIDIA_VISIBLE_DEVICES=${GPU}" \
  --ipc host \
  -v "${HF_CACHE}:/root/.cache/huggingface" \
  -p "${PORT}:8000" \
  --name "vllm-${MODEL}-${HOST}-g${GPU}-p${PORT}" \
  ${IMAGE} \
  --model ${MODEL_ID} \
  --port 8000 \
  ${MODEL_SPECIFIC_FLAGS} \
  --api-key sk-no-key-required
```

### 2.2 방법 B: Bare-metal `vllm serve` (v8 이후)

Docker 없이 직접 vLLM 바이너리를 실행. `nohup` + `disown` 패턴 사용.

```bash
# 기본 구조 (launch 함수)
launch() {
  local name="$1" cuda="$2" port="$3" tp="$4" model="$5"
  shift 5; local extra=("$@")
  local log="${HOME}/vllm_logs/${name}.log"

  CUDA_VISIBLE_DEVICES="${cuda}" nohup "${VLLM_BIN}" serve "${model}" \
    --port "${port}" \
    --tensor-parallel-size "${tp}" \
    "${COMMON_FLAGS[@]}" \
    "${extra[@]}" \
    >"${log}" 2>&1 &
  disown
}
```

표준 공통 플래그 (`COMMON_FLAGS`):
```bash
COMMON_FLAGS=(
  --gpu-memory-utilization 0.92      # H200은 0.90 권장
  --max-model-len 8192               # 벤치마크용, 필요시 16384
  --max-num-seqs 256                 # 동시 시퀀스 (throughput ↑)
  --enable-prefix-caching            # 반복 프롬프트 캐시 (3x throughput)
  --enable-chunked-prefill           # 메모리 효율 ↑
  --api-key sk-no-key-required
)
```

#### Qwen3.5-397B (현재 운영 설정)

```bash
# 144에서 GPU 0-3, 포트 30001 (TP=4)
CUDA_VISIBLE_DEVICES=0,1,2,3 nohup vllm serve Qwen/Qwen3.5-397B-A17B-FP8 \
  --port 30001 \
  --tensor-parallel-size 4 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --max-num-seqs 256 \
  --api-key sk-no-key-required \
  > ~/vllm_logs/qwen397b_1.log 2>&1 &
disown

# 2번째 인스턴스: GPU 4-7, 포트 30002
CUDA_VISIBLE_DEVICES=4,5,6,7 nohup vllm serve Qwen/Qwen3.5-397B-A17B-FP8 \
  --port 30002 \
  --tensor-parallel-size 4 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --max-num-seqs 256 \
  --api-key sk-no-key-required \
  > ~/vllm_logs/qwen397b_2.log 2>&1 &
disown
```

---

## 3. 정지 방법 (Stop)

### Docker 컨테이너
```bash
# 특정 컨테이너 정지
bash scripts/infra/v6_endpoint.sh stop 144 vllm-qwen397b-144-g0-1-2-3-p30001

# 전체 목록 확인 후 수동 정지
bash scripts/infra/v6_endpoint.sh listall
docker rm -f <container_name>
```

### Bare-metal 프로세스
```bash
# PID로 정지
kill <PID>

# 모든 vLLM 프로세스 정지
pkill -f "vllm serve"

# 특정 모델만 정지
pkill -f "vllm serve Qwen/Qwen3.5-397B"
```

---

## 4. 모델별 검증 설정 (v6-validated)

### 4.1 Qwen3.5-397B-A17B-FP8 (MoE, 397B total / 17B active)

| 항목 | 값 |
|---|---|
| Docker Image | `vllm-qwen35:latest` (커스텀) |
| TP (Tensor Parallel) | **4** |
| max-model-len | 16384 |
| gpu-memory-utilization | 0.90 |
| 최소 VRAM | 4 × 143GB = 572GB (H200 전용) |
| 추가 플래그 | `--tool-call-parser hermes --enable-auto-tool-choice` |
| 주의사항 | **thinking model** — `chat_template_kwargs: {"enable_thinking": false}` 필수 |

**Thinking model 이슈**: Qwen3.5-397B는 reasoning model이라 응답이 `<think>...</think>` 로 시작함.
atom_proposer에서 `"chat_template_kwargs": {"enable_thinking": false}` 를 payload에 포함하여 해결.
`_extract_json()`에서도 `<think>` 블록을 strip하는 방어 코드 적용됨.

### 4.2 Nemotron-3-Nano-30B-A3B-FP8

| 항목 | 값 |
|---|---|
| Docker Image | `vllm/vllm-openai:v0.12.0` (고정) |
| TP | **2** (Docker) / **1** (Bare-metal) |
| max-num-seqs | **8** (낮춤 — Xid 43 방지) |
| max-model-len | 32768 (Docker) / 8192 (Bare-metal) |
| kv-cache-dtype | fp8 |
| 추가 플래그 | `--trust-remote-code` |
| 주의사항 | compute capability 8.9+ 필요 → **H200(9.0) OK, A100(8.0) 실패** |

**Xid 43 이슈**: NVIDIA GPU Xid error 43 (GPU fell off the bus) 발생 빈도 높음.
`max-num-seqs 8`로 제한하고 watchdog 스크립트로 자동 재시작 필요.
```bash
nohup bash scripts/infra/nemotron_watchdog.sh > /tmp/nemo_wd.log 2>&1 &
```

### 4.3 Google Gemma-4-31B-IT

| 항목 | 값 |
|---|---|
| Docker Image | `vllm/vllm-openai:nightly` |
| TP | 1 |
| VRAM | ~62GB BF16 → A100 80GB OK |
| 추가 플래그 | `--limit-mm-per-prompt '{"image":0}' --trust-remote-code` |
| 주의사항 | multi-modal 모델이므로 이미지 입력 비활성화 필수 |

### 4.4 기타 소형 모델 (공통 설정)

Qwen3.5-27B-FP8, Qwen3.5-35B-A3B-FP8, Qwen3-4B-Instruct-2507, DeepSeek-R1-Distill-Qwen-7B:

```bash
# 모두 동일한 표준 설정
--tensor-parallel-size 1
--max-model-len 8192
--max-num-seqs 256
--gpu-memory-utilization 0.92
--enable-prefix-caching
--enable-chunked-prefill
```

### 4.5 OpenAI GPT-OSS-120B

| 항목 | 값 |
|---|---|
| TP | 2 (최소) / 4 (여유있게) |
| max-model-len | 8192 (벤치마크) / 131072 (full) |
| VRAM | TP=2: 2 × 80GB / TP=4: 4 × 80GB |

### 4.6 Llama-4-Scout-17B-16E-Instruct (MoE 109B)

| 항목 | 값 |
|---|---|
| TP | **4** (TP=2 OOM on A100: 218GB BF16 > 160GB) |
| VRAM | TP=4: 4 × 80GB = 320GB (fits with margin) |
| 추가 플래그 | `--trust-remote-code` |
| A100 주의 | TP=2 (160GB) OOM → 반드시 TP=4 필요 |
| H200 | TP=2 (286GB) OK |

---

## 5. 최대 Worker 수 / Co-location 전략

### 5.1 Worker 관리

```bash
# 146에서 워커 기동 (원격 엔드포인트 호출)
bash scripts/infra/v6_workers.sh start <model> <output_dir> <host_ip> <port> <worker_count>

# 예시: 144:30001의 qwen397b에 8 워커
bash scripts/infra/v6_workers.sh start qwen397b results/full_v6b 127.0.0.1 30001 8

# 145에서 co-located 워커 (네트워크 hop 없음, throughput 최대)
bash scripts/infra/v6_workers.sh start145 gemma31b 30100 16

# 워커 정지
bash scripts/infra/v6_workers.sh stop qwen397b
bash scripts/infra/v6_workers.sh stop145 gemma31b
bash scripts/infra/v6_workers.sh stopall  # 긴급 전체 정지
```

### 5.2 Co-location (같은 호스트에서 vLLM + Worker 실행)

네트워크 레이턴시를 제거하여 처리량을 극대화하는 전략.

```
┌─────── 145 (A100 × 8) ──────────────┐
│  GPU 0: vLLM qwen4b (port 30006)    │
│  GPU 1: vLLM qwen4b (port 30008)    │
│  ...                                 │
│  CPU: 16× Python worker processes    │ ← co-located
│       → http://localhost:30006/v1    │    네트워크 hop 없음
└──────────────────────────────────────┘

┌─────── 146 (orchestrator) ──────────────┐
│  CPU: 8× Python worker processes         │ ← 원격
│       → http://localhost:8013/v1    │   네트워크 경유
└──────────────────────────────────────────┘
```

### 5.3 최대 동시 인스턴스 수 (GPU-to-Model 매핑)

**144 (H200 × 8, 1,144 GB)**:

| 배치 | GPU 매핑 | 포트 | 모델 |
|---|---|---|---|
| qwen397b × 2 | 0-3 / 4-7 | 30001 / 30002 | TP=4 × 2 = 8 GPU 전부 |
| oss120b × 2 | 0-1 / 2-3 | 30001 / 30002 | TP=2 × 2, GPU 4-7 idle |
| gemma31b × 4 + nemotron30b × 4 | 0-3 / 4-7 | 30310-30323 | TP=1 × 8 |
| llama4scout + nemotron30b × 6 | 0-1 / 2-7 | 30401 / 30420-30425 | TP=2 + TP=1×6 |

**144 실행 방법 2가지**:
- **Bare-metal** (권장, 빠른 기동): `~/.local/bin/vllm` (v0.19.0, Python 3.10)
  ```bash
  ssh [email-redacted] "CUDA_VISIBLE_DEVICES=0,1 nohup ~/.local/bin/vllm serve MODEL_ID \
    --port 30001 --tensor-parallel-size 2 --max-model-len 8192 \
    --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill \
    --max-num-seqs 256 --api-key sk-no-key-required > ~/vllm_logs/model.log 2>&1 & disown"
  ```
- **Docker**: `vllm/vllm-openai:nightly` — GPU `--gpus '"device=0,1"'` 필수, `-e NVIDIA_VISIBLE_DEVICES` 단독 사용 불가
  - oss120b 등 일부 모델은 `--enforce-eager` 필수 (CUDA graph capture 무한 대기 방지)
  - HF 캐시 마운트: `-v /home/anonymous-user/.cache/huggingface:/root/.cache/huggingface`

**145 (A100 × 8, 640 GB)**:

| 배치 | GPU 매핑 | 포트 | 모델 |
|---|---|---|---|
| v6 standard fleet | 0-7 | 30005-30012 | 7종 모델, oss120b만 TP=2 |
| llama4scout + 소형 × 4 | 0-1,6-7 / 2-5 | 30201-30221 | TP=4 + TP=1×4 |

---

## 6. 헬스 체크 및 API 호출

### 6.1 헬스 체크

```bash
# 모델 목록 (인증 필요)
curl -s -H "Authorization: Bearer sk-no-key-required" \
  http://localhost:8013/v1/models | python3 -m json.tool

# 버전 확인
curl -s -H "Authorization: Bearer sk-no-key-required" \
  http://localhost:8013/version

# health 엔드포인트 (인증 불필요)
curl -s http://localhost:8013/health
```

### 6.2 추론 호출 (Chat Completion)

```bash
curl -s -H "Authorization: Bearer sk-no-key-required" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8013/v1/chat/completions \
  -d '{
    "model": "Qwen/Qwen3.5-397B-A17B-FP8",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello"}
    ],
    "max_tokens": 100,
    "temperature": 0.2,
    "chat_template_kwargs": {"enable_thinking": false}
  }' | python3 -m json.tool
```

### 6.3 Python에서 호출 (httpx)

```python
import httpx

url = "http://localhost:8013/v1/chat/completions"
payload = {
    "model": "Qwen/Qwen3.5-397B-A17B-FP8",
    "messages": [
        {"role": "system", "content": "System prompt here"},
        {"role": "user", "content": "User message here"},
    ],
    "temperature": 0.2,
    "max_tokens": 8192,
    "chat_template_kwargs": {"enable_thinking": False},
}

resp = httpx.post(
    url,
    json=payload,
    headers={"Authorization": "Bearer sk-no-key-required"},
    timeout=600.0,
)
resp.raise_for_status()
result = resp.json()["choices"][0]["message"]["content"]
```

### 6.4 전체 상태 대시보드

```bash
bash scripts/infra/v6_status.sh           # 전체
bash scripts/infra/v6_status.sh endpoints  # 엔드포인트만
bash scripts/infra/v6_status.sh gpu        # GPU 사용률
bash scripts/infra/v6_status.sh workers    # 워커 상태
bash scripts/infra/v6_status.sh eps        # 처리 속도
```

---

## 7. Throughput 최적화 체크리스트

1. **`--enable-prefix-caching`**: 반복 시스템 프롬프트 캐시 → ~3x throughput
2. **`--enable-chunked-prefill`**: long-prompt 메모리 효율 개선
3. **`--max-num-seqs 256`**: 동시 배치 크기 (소형 모델 기준, nemotron은 8로 제한)
4. **`--gpu-memory-utilization 0.92`**: VRAM 최대 활용 (H200은 0.90)
5. **`--max-model-len 8192`**: 벤치마크 용도에서는 낮추어 KV cache 여유 확보
6. **Co-location**: vLLM과 worker를 같은 호스트에서 실행 → 네트워크 레이턴시 제거
7. **다중 인스턴스**: 소형 모델(TP=1)은 GPU당 1개씩 병렬 인스턴스로 throughput 극대화

---

## 8. 트러블슈팅

### 8.1 Thinking Model 응답 오염

**증상**: Qwen3.5-397B 응답이 `"Thinking Process:\n1. ..."` 로 시작하여 JSON 파싱 실패.

**원인**: vLLM이 `<think>` 태그를 strip하지만 thinking content는 남김.

**해결**:
```python
# 요청 시 thinking 비활성화
"chat_template_kwargs": {"enable_thinking": False}

# 방어 코드 (atom_proposer._extract_json)
text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
```

### 8.2 Nemotron Xid 43 (GPU fell off the bus)

**증상**: nemotron30b 컨테이너 갑작스러운 사망, dmesg에 `Xid 43`.

**해결**:
- `--max-num-seqs 8` 로 제한 (256에서 대폭 축소)
- watchdog 스크립트로 자동 재시작:
  ```bash
  nohup bash scripts/infra/nemotron_watchdog.sh > /tmp/nemo_wd.log 2>&1 &
  ```

### 8.3 Docker GPU 할당 오류

**증상**: `cannot set both Count and DeviceIDs on device request`

**원인**: `--gpus "device=X,Y"` 형식이 SSH 파이프를 통과하면서 인용부호 손실.

**해결**: `--runtime=nvidia` + `-e "NVIDIA_VISIBLE_DEVICES=${GPU}"` 환경변수 방식 사용.

### 8.4 Llama-4-Scout OOM

**증상**: A100 TP=2에서 OOM (109B BF16 = 218GB > 160GB).

**해결**: TP=4 (320GB) 사용. H200에서는 TP=2 (286GB) 가능.

### 8.5 torchao 버전 충돌

**증상**: `torch._inductor` import 실패.

**해결**:
```bash
pip uninstall torchao  # 0.12.0 제거
pip install ninja      # FX graph compile용
```

### 8.6 qwen35b 146 불안정 (torch.compile death loop)

**증상**: 146에서 qwen35b(Qwen3.5-35B-A3B-FP8) vLLM 프로세스가 `torch.compile` 단계에서 반복적으로 사망.
v73 세션 동안 5회 이상 death 관찰.

**원인**: A100의 VRAM 여유가 부족하거나 torch inductor 컴파일 중 메모리 피크 발생.

**해결**: 146에서 qwen35b 대신 다른 모델 사용 권장. qwen35b는 144 또는 145에서 실행.

### 8.7 `docker system prune -a` 위험

**증상**: 디스크 부족 시 `docker system prune -a` 실행하면 **모든 Docker 이미지** 삭제.
이미지 재다운로드 시 `/var/lib/docker` 에 수십 GB가 쌓여 오히려 디스크가 더 꽉 참.

**해결**:
- `docker system prune -a` 대신 **특정 컨테이너/이미지만** 삭제:
  ```bash
  docker image rm <image_id>     # 특정 이미지만
  docker container prune          # 정지된 컨테이너만
  ```
- 디스크 정리 시 확인 순서:
  ```bash
  df -h /                         # 전체 여유
  du -sh /var/lib/docker/         # Docker 사용량
  du -sh /home/hub/               # 모델 캐시 사용량
  docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | sort -k3 -h
  ```

### 8.8 Claim 파일 교착 (Stale claims)

**증상**: worker가 claim 파일을 남긴 채 죽으면 해당 시나리오 영구 skip.

**해결**:
```bash
# 30분 이상 된 stale claim 찾기
find results/full_v6*/<model>/.claim_* -mmin +30

# 삭제 후 워커 재시작
find results/full_v6*/<model>/.claim_* -mmin +30 -delete
bash scripts/infra/v6_workers.sh stop <model>
bash scripts/infra/v6_workers.sh start <model> ...
```

---

## 9. 코드 동기화

### 9.1 145로 전체 동기화 (rsync)

```bash
sudo -n -u anonymous-org rsync -az --ignore-errors \
  --exclude='.git' --exclude='results' --exclude='__pycache__' --exclude='.omc' \
  /home/anonymous-org/anonymous-project/AnonProject/cga_bench/ \
  127.0.0.1
```

### 9.2 145로 개별 파일 동기화 (scp)

워커 실행 중 단일 파일만 패치할 때:
```bash
sudo -u anonymous-org scp assessor_core/action_normalizer.py \
  127.0.0.1

sudo -u anonymous-org scp scripts/experiments/full_v73_runner.py \
  127.0.0.1
```

> **주의**: 145의 코드 경로는 `/home/anonymous-org/bench_ws/cga_bench/` (146과 다름)

---

## 10. v73 Runner 운영

### 10.1 `original_key` shard 패턴

동일 모델을 복수 엔드포인트에서 실행할 때 (예: qwen397b를 144:30001과 144:30002에서),
runner에 `qwen397b_s2` 같은 별도 키를 등록하되 `original_key` 로 정규 디렉토리를 지정한다.

```python
# full_v73_runner.py MODELS dict
"qwen397b_s2": {
    "config": "configs/agents/clean_slate_qwen397b.yaml",
    "port": 30002,
    "host": "127.0.0.1
    "label": "Qwen3.5-397B-S2",
    "original_key": "qwen397b",   # ← 결과는 qwen397b/ 디렉토리에 저장
},
```

`run_single_episode()`, `run_model()`, `--validate`, `--dedup` 모두 `canonical_key = model_info.get("original_key", model_key)` 를 사용하여 파일명과 출력 경로를 결정.
이를 통해 두 엔드포인트의 워커가 동일한 디렉토리에서 dedup 체크를 하며 중복 작업을 방지.

### 10.2 크로스 서버 워커 패턴

145에서 워커를 실행하고 146의 vLLM 엔드포인트를 호출하는 패턴:

```bash
# 145에서 실행 — 146의 엔드포인트를 원격으로 호출
ssh 127.0.0.1 'cd /home/anonymous-org/bench_ws/cga_bench && \
  PYTHONPATH=. nohup python scripts/experiments/full_v73_runner.py \
    qwen397b --host 127.0.0.1 --port 30001 \
    --output results/v73_full --workers 24 \
    > /tmp/w_qwen397b.log 2>&1 & disown'
```

145 워커가 146 vLLM 엔드포인트를 호출할 수 있으나, 네트워크 hop 추가로 co-located 대비 레이턴시 증가.

### 10.3 v73 실제 워커 동시성 (2026-05-01 기준)

| 모델 | 146 워커 | 145 워커 | 합계 |
|---|---:|---:|---:|
| deepseek_r1_7b | 64 | 36 | 100 |
| qwen4b | 48 | 25 | 73 |
| qwen397b (×2 endpoints) | 24 | 24 | 48 |
| qwen27b | 16 | 16 | 32 |
| gemma31b | 16 | 32 | 48 |
| nemotron30b | 8 | 8 | 16 |
| **합계** | **176** | **141** | **317** |

---

## 11. 빠른 참조 카드

```
# 현재 활성 엔드포인트 확인
curl -s -H "Authorization: Bearer sk-no-key-required" http://localhost:8013/v1/models
curl -s -H "Authorization: Bearer sk-no-key-required" http://localhost:8013/v1/models

# qwen397b 기동 (144, bare-metal, 2 인스턴스)
CUDA_VISIBLE_DEVICES=0,1,2,3 nohup ~/.local/bin/vllm serve Qwen/Qwen3.5-397B-A17B-FP8 \
  --port 30001 --tensor-parallel-size 4 --max-model-len 16384 \
  --gpu-memory-utilization 0.90 --enable-prefix-caching --enable-chunked-prefill \
  --max-num-seqs 256 --api-key sk-no-key-required > ~/vllm_logs/qwen397b_1.log 2>&1 & disown

CUDA_VISIBLE_DEVICES=4,5,6,7 nohup ~/.local/bin/vllm serve Qwen/Qwen3.5-397B-A17B-FP8 \
  --port 30002 --tensor-parallel-size 4 --max-model-len 16384 \
  --gpu-memory-utilization 0.90 --enable-prefix-caching --enable-chunked-prefill \
  --max-num-seqs 256 --api-key sk-no-key-required > ~/vllm_logs/qwen397b_2.log 2>&1 & disown

# 전체 상태 확인
bash scripts/infra/v6_status.sh

# 전체 정지
pkill -f "vllm serve"
```

---

## 12. 스크립트 인벤토리

| 스크립트 | 위치 | 용도 |
|---|---|---|
| `v6_endpoint.sh` | `scripts/infra/` | Docker 컨테이너 launch/stop/listall |
| `v6_workers.sh` | `scripts/infra/` | 벤치마크 워커 spawn/stop |
| `v6_status.sh` | `scripts/infra/` | 전체 상태 대시보드 |
| `nemotron_watchdog.sh` | `scripts/infra/` | nemotron 자동 재시작 |
| `launch_vllm_145.sh` | `scripts/infra/` | 145 7-instance fleet (bare-metal) |
| `launch_vllm_145_v6.sh` | `scripts/infra/` | 145 v6 fleet (bare-metal) |
| `launch_vllm_v8_track1_144.sh` | `scripts/infra/` | 144 v8 fleet (gemma+nemotron) |
| `launch_vllm_v8_track1_144_v2.sh` | `scripts/infra/` | 144 v8 fleet (llama+nemotron) |
| `launch_vllm_v8_track1_145.sh` | `scripts/infra/` | 145 v8 fleet |
| `launch_vllm_v8_track1_llama4scout_tp4.sh` | `scripts/infra/` | llama4scout TP=4 전용 |
| `launch_vllm_v8_track1_nemotron_144_v6.sh` | `scripts/infra/` | nemotron ×8 on 144 |
| `phase_b_boost.sh` | `scripts/infra/` | Phase B 동적 GPU 재할당 |
| `phase_b_resume.sh` | `scripts/infra/` | Phase B 중단 재개 |
| `v73_workers_145.sh` | `scripts/infra/` | 145 v73 워커 spawn |
| `v73_schedule_146.sh` | `scripts/infra/` | 146 v73 워커 spawn |
| `v73_monitor.sh` | `scripts/infra/` | v73 진행 모니터링 |
| `full_v73_runner.py` | `scripts/experiments/` | v73 벤치마크 에피소드 러너 |
| `shard_runner.py` | `scripts/experiments/` | 듀얼 엔드포인트 shard 러너 |

---

*Last updated: 2026-05-02*
