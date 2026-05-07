# vLLM Known-Good Configurations on 145 — to Avoid Trial-and-Error

> **목적**: 145에서 model deploy 시 시행착오 방지. 어떤 docker image / flag 조합이 working configuration인지 명시.
> **선행**: `.claude/rules/vllm-launch.md` (5 standard options) — 본 문서는 그 위에 model-specific overrides 정리.
> **소스**: `scripts/infra/v6_endpoint.sh` (Phase A 검증된 known-good config)

---

## 핵심 교훈 — Bare-metal 금지, Docker Only

145의 `/home/anonymous-org/anaconda3/bin/vllm` (bare-metal vllm 0.x)은 **Gemma-4 / Nemotron-3 등 최신 아키텍처를 인식하지 못함**:

```
Gemma-4-31B 에러: "model type `gemma4` but Transformers does not recognize this architecture"
Nemotron-3-30B 에러: "trust_remote_code=True required"
```

**정답**: docker 컨테이너로 model-specific image + flag 조합 사용.

`scripts/infra/launch_vllm_145_v6.sh` 의 bare-metal `nohup vllm serve ...` 경로는 Qwen / OSS / DeepSeek-distill 까지만 동작. **Gemma-4, Nemotron-3에는 사용 금지**.

---

## Per-Model Known-Good Config (`scripts/infra/v6_endpoint.sh`)

| Model key | Docker image | TP | extra flags | Reason |
|---|---|---|---|---|
| **gemma31b** (`google/gemma-4-31b-it`) | `vllm/vllm-openai:nightly` | 1 | `--max-num-batched-tokens 8192 --limit-mm-per-prompt {"image":0} --enable-prefix-caching --enable-chunked-prefill --trust-remote-code` | gemma4 architecture는 nightly에만; multimodal support 차단 |
| **nemotron30b** (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8`) | `vllm/vllm-openai:v0.12.0` | 2 | `--max-num-seqs 8 --max-model-len 32768 --kv-cache-dtype fp8 --tool-call-parser qwen3_coder --enable-auto-tool-choice --trust-remote-code` | custom code (Mamba); FP8 KV cache; max-num-seqs 8 (낮음, Mamba state 비용) |
| **qwen397b** (`Qwen/Qwen3.5-397B-A17B-FP8`) | `vllm-qwen35:latest` (custom) | 4 | `--max-model-len 16384 --gpu-memory-utilization 0.90 --tool-call-parser hermes --enable-auto-tool-choice` | 144에서만 deploy (read-only); 4 GPUs 필요 |
| **oss120b** (`openai/gpt-oss-120b`) | `vllm/vllm-openai:latest` | 2 | 표준 5 옵션 | reasoning-mode JSON 응답 별도 파싱 필요 (`exp_cde_vs_llm_v2.py:_extract_constraint_list`) |
| qwen35b (`Qwen/Qwen3.5-35B-A3B-FP8`) | `vllm/vllm-openai:latest` | 1 | 표준 5 옵션 | 표준 동작 |
| qwen27b (`Qwen/Qwen3.5-27B-FP8`) | `vllm/vllm-openai:latest` | 1 | 표준 5 옵션 | 표준 동작 |
| qwen4b (`Qwen/Qwen3-4B-Instruct-2507`) | `vllm/vllm-openai:latest` | 1 | 표준 5 옵션 | 표준 동작 |
| deepseek_r1_7b (`deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`) | `vllm/vllm-openai:latest` | 1 | 표준 5 옵션 | 표준 동작 |

**5 표준 옵션** (per `.claude/rules/vllm-launch.md`): `--max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill --api-key sk-no-key-required`

---

## 사용법 (전혀 시행착오 없는 launch)

```bash
# v6_endpoint.sh가 위 known-good config을 자동 적용
bash scripts/infra/v6_endpoint.sh launch <host> <gpu_spec> <port> <model_key>

# 예시:
bash scripts/infra/v6_endpoint.sh launch 145 3 30010 gemma31b
bash scripts/infra/v6_endpoint.sh launch 145 4,5 30011 nemotron30b
bash scripts/infra/v6_endpoint.sh launch 145 6,7 30005 oss120b
bash scripts/infra/v6_endpoint.sh launch 144 0,1,2,3 30001 qwen397b

# 종료
bash scripts/infra/v6_endpoint.sh stop 145 vllm-gemma31b-145-g3-p30010

# 전체 list
bash scripts/infra/v6_endpoint.sh listall
```

---

## 주의 — 절대 하지 말 것

1. **Gemma-4-31B 또는 Nemotron-3-30B를 bare-metal `vllm serve`로 launch 금지**
   - bare-metal vllm은 최신 transformers 미포함, `gemma4` 미인식
   - nemotron-3은 `trust_remote_code` 필요한데 bare-metal 환경에 없음

2. **Docker `--rm` 플래그를 시작 단계에서 사용 시 실패 시 자동 삭제**
   - 디버깅 시 `--rm` 빼고 `docker logs <name>` 으로 확인 가능
   - v6_endpoint.sh는 `--rm` 사용하지만 known-good config라 실패 빈도 낮음

3. **Nemotron `max-num-seqs`를 256으로 올리면 OOM**
   - Mamba state space 비용 큼 → 8이 known-good
   - 표준 5 옵션 그대로 적용 시 실패

4. **Gemma-4 multimodal flag 무시 시 image embedding 시도**
   - `--limit-mm-per-prompt {"image":0}` 명시 필요

---

## 145 GPU 할당 정책 (v6 fleet)

| GPU | Model | Port | TP | Memory |
|---|---|---|---|---|
| 0 | qwen4b | 30006 | 1 | ~75 GB |
| 1 | qwen27b | 30007 | 1 | ~75 GB |
| 2 | qwen35b | 30008 | 1 | ~75 GB |
| 3 | gemma31b | 30010 | 1 | ~75 GB |
| 4-5 | nemotron30b | 30011 | 2 | ~150 GB |
| 6-7 | oss120b | 30005 | 2 | ~150 GB |

DeepSeek-R1-7B (port 30012) 은 GPU 3-5 중 빈 자리에 위치 가능 (작음).

---

## 144 GPU 할당 (read-only — 변경 금지)

| GPU | Model | Port | TP |
|---|---|---|---|
| 0-3 | qwen397b | 30001 | 4 |

**144는 절대 변경하지 말 것** — read-only host.

---

## 146 (이 host)

GPU serving용 아님. **HTTP client / runner 전용**.
- expansion_runner, cataloguer, mainfinding 등 모두 146에서 실행 → 145/144 endpoints에 호출

---

## Worker 동시성 (per-endpoint)

`.claude/rules/vllm-launch.md` 표:

| Model size | Workers per endpoint |
|---|---|
| ≤ 7B | 16-32 |
| 27-35B | 12-16 (sweet spot 16) |
| ≥ 70B | 8-12 |
| ≥ 200B | 4-8 |

**default 권장**: `--workers 16` (`exp_cde_vs_llm_v3.py`).

---

## Track A 재시도 시 정확한 sequence

```bash
# 1) 145 endpoints all stop
sudo -u anonymous-org ssh 127.0.0.1 'docker ps --format "{{.Names}}" | grep "^vllm-" | xargs -r docker rm -f'

# 2) Bare-metal vllm 잔존 process 제거 (있을 경우)
sudo -u anonymous-org ssh 127.0.0.1 'pgrep -f "vllm.*serve" | xargs -r kill -9'

# 3) Track A endpoints launch (docker, known-good config)
bash scripts/infra/v6_endpoint.sh launch 145 3 30010 gemma31b
bash scripts/infra/v6_endpoint.sh launch 145 4,5 30011 nemotron30b

# 4) endpoints up 대기 (Monitor or until-loop)
until curl -s -m 3 -H 'Authorization: Bearer sk-no-key-required' http://localhost:8013/v1/models | grep -q '"id"'; do sleep 30; done
echo gemma-up

# 5) Track A v3 cataloguer (Gemma)
PY=/home/anonymous-org/anaconda3/bin/python3.13
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject:/home/anonymous-org/anonymous-project/AnonProject/cga_bench
$PY scripts/experiments/exp_cde_vs_llm_v3.py \
    --endpoint http://localhost:8013/v1/chat/completions \
    --model google/gemma-4-31b-it \
    --output-suffix v3_gemma \
    --workers 16

# 6) v4 cataloguer (Nemotron)
$PY scripts/experiments/exp_cde_vs_llm_v3.py \
    --endpoint http://localhost:8013/v1/chat/completions \
    --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8 \
    --output-suffix v4_nemotron \
    --workers 12   # nemotron max-num-seqs 8이라 12 worker 적정

# 7) main-finding replications
$PY scripts/experiments/exp_mainfinding_llm_replication_v3.py --output-suffix v3_gemma --catalogue-name "Gemma-4-31B"
$PY scripts/experiments/exp_mainfinding_llm_replication_v3.py --output-suffix v4_nemotron --catalogue-name "Nemotron-3-30B"
```

---

## 145 실패 case 디버깅 명령어

```bash
# 컨테이너 logs
sudo -u anonymous-org ssh 127.0.0.1 "docker logs <container_name> 2>&1 | tail -30"

# Bare-metal vllm logs
sudo -u anonymous-org ssh 127.0.0.1 "tail -n 30 /home/anonymous-org/vllm_logs/<model>.log"

# GPU 메모리
sudo -u anonymous-org ssh 127.0.0.1 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader"

# 모든 endpoint 리스트
bash scripts/infra/v6_endpoint.sh listall
```

---

*Last updated: 2026-04-26 — 145 Gemma-4 / Nemotron-3 launch 시행착오 후 정리.*
