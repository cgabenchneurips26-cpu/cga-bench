#!/bin/bash
# nemotron30b W8 on 144:30003 (GPU 4-7, H200)
# After completion: restart qwen397b on same GPU 4-7 port 30003 → resume F chain → held-out
cd ${CGA_BENCH_ROOT}/cga_bench
export PYTHONPATH=${CGA_BENCH_ROOT}
LOG=/tmp/chain_w8_nemotron30b_144.log
echo "[$(date '+%H:%M:%S')] Starting nemotron30b W8 chain (144:30003 GPU 4-7)" | tee "$LOG"

for scaffold in react direct checklist tooluse; do
    echo "[$(date '+%H:%M:%S')] ==> nemotron30b_${scaffold}" | tee -a "$LOG"
    python scripts/experiments/full_690_runner.py "nemotron30b_${scaffold}" results/ex_w8_crossmodel >> "$LOG" 2>&1
    echo "[$(date '+%H:%M:%S')] nemotron30b_${scaffold} exit=$?" | tee -a "$LOG"
done
echo "[$(date '+%H:%M:%S')] nemotron30b W8 complete!" | tee -a "$LOG"

# --- Auto-chain: restart qwen397b on 144 GPU 4-7 port 30003 ---
echo "[$(date '+%H:%M:%S')] Replacing nemotron30b with qwen397b on 144:30003 (GPU 4-7)..." | tee -a "$LOG"
ssh -i /tmp/anonymous-org_key [email-redacted] \
  "docker stop nemotron30b 2>/dev/null; docker rm nemotron30b 2>/dev/null; \
   docker run -d --name qwen3.5-397b-f --gpus '\"device=4,5,6,7\"' \
   -v /home/anonymous-user/.cache/huggingface:/root/.cache/huggingface \
   -p 30003:8000 vllm/vllm-openai:latest \
   --model Qwen/Qwen3.5-397B-A27B-FP8 --tensor-parallel-size 4 \
   --max-model-len 16384 --api-key sk-no-key-required" >> "$LOG" 2>&1

echo "[$(date '+%H:%M:%S')] Waiting for qwen397b endpoint on 30003..." | tee -a "$LOG"
while true; do
    resp=$(curl -s --max-time 3 -H "Authorization: Bearer sk-no-key-required" http://localhost:8013/v1/models 2>/dev/null)
    if echo "$resp" | grep -q '"object":"list"'; then
        echo "[$(date '+%H:%M:%S')] qwen397b READY on 144:30003" | tee -a "$LOG"
        break
    fi
    sleep 15
done

# Resume F chain: react (from checkpoint ~145), then checklist
echo "[$(date '+%H:%M:%S')] Resuming qwen397b F chain (react+checklist)" | tee -a "$LOG"
for scaffold in react checklist; do
    echo "[$(date '+%H:%M:%S')] ==> qwen397b_${scaffold}" | tee -a "$LOG"
    python scripts/experiments/full_690_runner.py "qwen397b_${scaffold}" results/ex_w8_crossmodel >> "$LOG" 2>&1
    echo "[$(date '+%H:%M:%S')] qwen397b_${scaffold} exit=$?" | tee -a "$LOG"
done

# Chain qwen397b held-out (175 remaining episodes)
echo "[$(date '+%H:%M:%S')] Starting qwen397b held-out (175 remaining)" | tee -a "$LOG"
python scripts/experiments/heldout_runner.py qwen397b results/heldout_v1 >> "$LOG" 2>&1
echo "[$(date '+%H:%M:%S')] All done on 144 GPU 4-7" | tee -a "$LOG"
