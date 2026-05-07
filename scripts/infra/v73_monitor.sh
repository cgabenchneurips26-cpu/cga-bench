#!/usr/bin/env bash
# v7.3 SGSC live monitor — episodes per model, worker count, GPU utilisation.
# Adapted from phase_b_monitor.sh for local 146 + remote 144 (qwen397b).
#
# Usage:
#   bash scripts/infra/v73_monitor.sh           # one-shot
#   watch -n 30 'bash scripts/infra/v73_monitor.sh'   # continuous

set -uo pipefail

ROOT=/home/anonymous-org/anonymous-project/AnonProject/cga_bench
OUTPUT="$ROOT/results/v73_full"
TARGET=1254  # 418 scenarios x 3 runs

printf "=== v7.3 SGSC Status @ %s ===\n\n" "$(date '+%F %T %Z')"

# ── Per-model episode counts & workers ──────────────────────────────

printf "%-18s %6s %6s %5s %8s  %s\n" "MODEL" "EPS" "TGT" "PCT" "WORKERS" "LOCATION"
printf "%-18s %6s %6s %5s %8s  %s\n" "─────" "───" "───" "───" "───────" "────────"
total_eps=0; total_workers=0; models_done=0

# 146 local models
for m in qwen4b deepseek_r1_7b qwen27b qwen35b gemma31b nemotron30b oss120b llama4scout; do
  d="$OUTPUT/$m"
  if [ -d "$d" ]; then
    eps=$(find "$d" -maxdepth 1 -name '*.json' \
      ! -name 'checkpoint*' ! -name 'model_summary*' ! -name '.claim_*' \
      2>/dev/null | wc -l)
  else
    eps=0
  fi
  workers=$(ps aux 2>/dev/null | grep "full_v73_runner.py $m " | grep -v grep | wc -l)
  pct=$(( eps * 100 / TARGET ))
  status="running"
  [ "$eps" -ge "$TARGET" ] && { status="DONE"; models_done=$((models_done + 1)); }
  [ "$eps" -eq 0 ] && [ "$workers" -eq 0 ] && status="pending"
  printf "%-18s %6d %6d %4d%% %8d  146 local [%s]\n" "$m" "$eps" "$TARGET" "$pct" "$workers" "$status"
  total_eps=$(( total_eps + eps ))
  total_workers=$(( total_workers + workers ))
done

# 144 remote: qwen397b (2 instances on 30001/30002)
qwen397b_eps=0
d_397="$OUTPUT/qwen397b"
if [ -d "$d_397" ]; then
  qwen397b_eps=$(find "$d_397" -maxdepth 1 -name '*.json' \
    ! -name 'checkpoint*' ! -name 'model_summary*' ! -name '.claim_*' \
    2>/dev/null | wc -l)
fi
# Also check qwen397b_s2 (shard 2 results land in same dir or separate)
d_s2="$OUTPUT/qwen397b_s2"
if [ -d "$d_s2" ]; then
  s2_eps=$(find "$d_s2" -maxdepth 1 -name '*.json' \
    ! -name 'checkpoint*' ! -name 'model_summary*' ! -name '.claim_*' \
    2>/dev/null | wc -l)
  qwen397b_eps=$((qwen397b_eps + s2_eps))
fi
q_workers=$(ps aux 2>/dev/null | grep "full_v73_runner.py qwen397b" | grep -v grep | wc -l)
q_pct=$(( qwen397b_eps * 100 / TARGET ))
q_status="running"
[ "$qwen397b_eps" -ge "$TARGET" ] && { q_status="DONE"; models_done=$((models_done + 1)); }
[ "$qwen397b_eps" -eq 0 ] && [ "$q_workers" -eq 0 ] && q_status="pending"
printf "%-18s %6d %6d %4d%% %8d  144 remote [%s]\n" "qwen397b" "$qwen397b_eps" "$TARGET" "$q_pct" "$q_workers" "$q_status"
total_eps=$(( total_eps + qwen397b_eps ))
total_workers=$(( total_workers + q_workers ))

# ── Totals ──────────────────────────────────────────────────────────

total_models=9
target_total=$(( total_models * TARGET ))
total_pct=$(( total_eps * 100 / (target_total > 0 ? target_total : 1) ))
printf "%-18s %6s %6s %5s %8s\n" "" "" "" "" ""
printf "%-18s %6d %6d %4d%% %8d  models done: %d/%d\n" \
  "==TOTAL==" "$total_eps" "$target_total" "$total_pct" "$total_workers" "$models_done" "$total_models"

# ── Docker containers ───────────────────────────────────────────────

printf "\n--- 146 Docker (vLLM) ---\n"
docker ps --format "  {{.Names}}\t{{.Status}}" 2>/dev/null | grep -i vllm || echo "  (none)"

# ── GPU utilisation ─────────────────────────────────────────────────

printf "\n--- 146 GPU ---\n"
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu \
  --format=csv,noheader 2>/dev/null || echo "  nvidia-smi unavailable"

printf "\n--- 144 GPU (remote) ---\n"
sudo -n -u anonymous-org ssh -o ConnectTimeout=3 [email-redacted] \
  "nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits" 2>/dev/null \
  || echo "  (unreachable)"

# ── Endpoint health ─────────────────────────────────────────────────

printf "\n--- Endpoint Health ---\n"
for pair in "localhost:8101:qwen4b" "localhost:30009:deepseek" "localhost:28010:qwen27b" \
            "localhost:8013:qwen35b" "localhost:30003:gemma31b" "localhost:30004:nemotron" \
            "localhost:28000:oss120b" "localhost:8201:llama4scout" \
            "127.0.0.1 "127.0.0.1 do
  host="${pair%%:*}"
  rest="${pair#*:}"
  port="${rest%%:*}"
  label="${rest#*:}"
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
    -H 'Authorization: Bearer sk-no-key-required' \
    "http://${host}:${port}/v1/models" 2>/dev/null)
  if [ "$code" = "200" ]; then
    printf "  %-14s %s:%s  OK\n" "$label" "$host" "$port"
  else
    printf "  %-14s %s:%s  DOWN (%s)\n" "$label" "$host" "$port" "$code"
  fi
done
