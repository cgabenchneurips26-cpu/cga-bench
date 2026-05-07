#!/bin/bash
# After qwen397b W8 completes on 144, chain:
#   1. nemotron30b W8 (4 scaffolds) on 144:30001 (GPU 0-3) — needs H200 for FP8
#   2. qwen397b held-out (175 remaining) on 144:30002 (GPU 4-7) — parallel with nemotron30b
cd ${CGA_BENCH_ROOT}/cga_bench
export PYTHONPATH=${CGA_BENCH_ROOT}
LOG=/tmp/chain_post_qwen397b.log
echo "[$(date '+%H:%M:%S')] Post-qwen397b chain starting" | tee "$LOG"

# Wait for both qwen397b W8 chains (F and G) to finish
echo "[$(date '+%H:%M:%S')] Waiting for qwen397b W8 chains to complete..." | tee -a "$LOG"
while true; do
    F_DONE=0; G_DONE=0
    # Check if F chain (react+checklist) runner is still running
    if ! pgrep -f "full_690_runner.py qwen397b_react " > /dev/null 2>&1 && \
       ! pgrep -f "full_690_runner.py qwen397b_checklist " > /dev/null 2>&1; then
        F_DONE=1
    fi
    # Check if G chain (direct+tooluse) runner is still running
    if ! pgrep -f "full_690_runner.py qwen397b_direct_s2 " > /dev/null 2>&1 && \
       ! pgrep -f "full_690_runner.py qwen397b_tooluse_s2 " > /dev/null 2>&1; then
        G_DONE=1
    fi
    if [ $F_DONE -eq 1 ] && [ $G_DONE -eq 1 ]; then
        echo "[$(date '+%H:%M:%S')] Both qwen397b W8 chains done" | tee -a "$LOG"
        break
    fi
    sleep 60
done

# --- Chain 1: nemotron30b W8 on 144:30001 (GPU 0-3) ---
# First, need to restart the endpoint with nemotron30b model
echo "[$(date '+%H:%M:%S')] Restarting 144:30001 with nemotron30b..." | tee -a "$LOG"
ssh -i /tmp/anonymous-org_key [email-redacted] "docker stop qwen3.5-397b && docker rm qwen3.5-397b && docker run -d --name nemotron30b --gpus '\"device=0,1,2,3\"' -v /home/anonymous-user/.cache/huggingface:/root/.cache/huggingface -p 30001:8000 vllm/vllm-openai:latest --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8 --tensor-parallel-size 4 --max-model-len 16384 --trust-remote-code --api-key sk-no-key-required" >> "$LOG" 2>&1

# Wait for nemotron30b to be ready
echo "[$(date '+%H:%M:%S')] Waiting for nemotron30b endpoint..." | tee -a "$LOG"
while true; do
    resp=$(curl -s --max-time 3 -H "Authorization: Bearer sk-no-key-required" http://localhost:8013/v1/models 2>/dev/null)
    if echo "$resp" | grep -q '"object":"list"'; then
        echo "[$(date '+%H:%M:%S')] nemotron30b READY on 144:30001" | tee -a "$LOG"
        break
    fi
    sleep 15
done

# Create nemotron30b W8 configs pointing to 144:30001
for scaffold in react direct checklist tooluse; do
    cat > configs/agents/clean_slate_nemotron30b_${scaffold}_144.yaml <<YAMLEOF
# Nemotron30b on 144:30001 for W8
agent:
  type: "rag"
  agent_id: "rag_nemotron30b_${scaffold}_144"
  llm_backend: "vllm"
  llm_model: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8"
  temperature: 0.1
  use_llm: true
  base_url: "http://localhost:8013/v1"
  api_key: "sk-no-key-required"
  top_k: 5
  use_bm25: true
  cpg_sources_path: null
  scaffold: "${scaffold}"
  max_actions_per_step: $([ "$scaffold" = "direct" ] && echo 10 || ([ "$scaffold" = "tooluse" ] && echo 5 || echo 3))
  budget_limit_tokens: 100000
  budget_limit_tool_calls: 50
YAMLEOF
done

# Run nemotron30b W8 (uses symlinks to canonical dirs)
for scaffold in react direct checklist tooluse; do
    # Symlink so output goes to canonical dir
    ln -sfn nemotron30b_${scaffold} results/ex_w8_crossmodel/nemotron30b_${scaffold}_144 2>/dev/null
    mkdir -p results/ex_w8_crossmodel/nemotron30b_${scaffold}
done

echo "[$(date '+%H:%M:%S')] Starting nemotron30b W8 chain on 144:30001" | tee -a "$LOG"
for scaffold in react direct checklist tooluse; do
    echo "[$(date '+%H:%M:%S')] ==> nemotron30b_${scaffold}" | tee -a "$LOG"
    python scripts/experiments/full_690_runner.py "nemotron30b_${scaffold}" results/ex_w8_crossmodel >> "$LOG" 2>&1
    echo "[$(date '+%H:%M:%S')] nemotron30b_${scaffold} exit=$?" | tee -a "$LOG"
done

echo "[$(date '+%H:%M:%S')] nemotron30b W8 chain complete" | tee -a "$LOG"

# --- Chain 2: qwen397b held-out on 144:30002 (already running, just need runner) ---
echo "[$(date '+%H:%M:%S')] Starting qwen397b held-out (175 remaining)" | tee -a "$LOG"
python scripts/experiments/heldout_runner.py qwen397b results/heldout_v1 >> "$LOG" 2>&1
echo "[$(date '+%H:%M:%S')] qwen397b held-out exit=$?" | tee -a "$LOG"

echo "[$(date '+%H:%M:%S')] All post-qwen397b chains complete" | tee -a "$LOG"
