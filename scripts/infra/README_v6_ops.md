# v6 Ops Scripts

Codified versions of the manual commands used during v6 Phase A/B
development. Each script handles one concern; combine via shell pipelines.

## Scripts

| Script | Purpose |
|---|---|
| `v6_status.sh` | Read-only dashboard — endpoints / workers / GPU / eps / fb% |
| `v6_workers.sh` | Spawn / stop benchmark workers (146 or 145 co-located) |
| `v6_endpoint.sh` | Launch / stop vLLM containers with v6-validated configs |
| `nemotron_watchdog.sh` | Background daemon: auto-restart dead nemotron containers |
| `launch_vllm_145_v6.sh` | Bulk-launch 7-instance fleet on 145 (legacy, replaced by v6_endpoint.sh) |
| `launch_workers_145_v6a_phase1.sh` | Phase A worker bulk-launch on 145 |
| `launch_workers_146_v6a_qwen397b.sh` | Phase A qwen397b workers from 146 |

## Quick reference

### Status check
```bash
# Full dashboard
bash scripts/infra/v6_status.sh

# Just one section
bash scripts/infra/v6_status.sh endpoints
bash scripts/infra/v6_status.sh workers
bash scripts/infra/v6_status.sh gpu
bash scripts/infra/v6_status.sh eps
bash scripts/infra/v6_status.sh fb     # fb% sanity per model
```

### Endpoint management
```bash
# Launch with v6-validated per-model config
bash scripts/infra/v6_endpoint.sh launch 144 0,1,2,3 30001 qwen397b
bash scripts/infra/v6_endpoint.sh launch 145 3 30010 gemma31b
bash scripts/infra/v6_endpoint.sh launch 144 4,5 30013 nemotron30b

# Stop one
bash scripts/infra/v6_endpoint.sh stop 144 vllm-qwen397b-144-g0-1-2-3-p30001

# List all vllm containers across 3 hosts
bash scripts/infra/v6_endpoint.sh listall
```

### Worker management
```bash
# Spawn 8 workers from 146 hitting 144:30001
bash scripts/infra/v6_workers.sh start qwen397b results/full_v6b 127.0.0.1 30001 8

# Spawn 16 workers ON 145 (co-located, no network hop)
bash scripts/infra/v6_workers.sh start145 gemma31b 30100 16

# Stop one model's workers
bash scripts/infra/v6_workers.sh stop qwen397b
bash scripts/infra/v6_workers.sh stop145 gemma31b

# Emergency stop everything
bash scripts/infra/v6_workers.sh stopall
```

### Watchdog (nemotron-specific, mitigates Xid 43 + container death)
```bash
nohup bash scripts/infra/nemotron_watchdog.sh > /tmp/nemo_wd.log 2>&1 &
```

## v6-validated per-model configs

These are baked into `v6_endpoint.sh launch`:

| Model | Image | TP | Notes |
|---|---|---:|---|
| qwen397b | vllm-qwen35:latest | 4 | --max-model-len 16384 --tool-call-parser hermes |
| nemotron30b | vllm/vllm-openai:**v0.12.0** | 2 | **fp8 kv-cache + qwen3_coder parser + max-num-seqs 8** (avoids Xid 43) |
| gemma-4-31b-it | vllm/vllm-openai:**nightly** | 1 | **--limit-mm-per-prompt {"image":0}** (multi-modal disabled) |
| qwen35b/27b/4b | vllm/vllm-openai:latest | 1 | standard prefix-caching + chunked-prefill |
| oss120b | vllm/vllm-openai:latest | 2 | TP=2 needed for 120B |
| deepseek_r1_7b | vllm/vllm-openai:latest | 1 | standard |

All endpoints use `--ipc host` and `--init` (avoids zombie containers and
shm exhaustion).

## Phase B environment variables

```bash
# Phase A: 706 manual scenarios only
export CGA_BENCH_EXCLUDE_AUTO=1

# Phase B: 706 manual + 4720 auto_v2 (after 28-CPG archive: 706 + 2480 = 3186)
export CGA_BENCH_EXCLUDE_AUTO=1
export CGA_BENCH_INCLUDE_AUTO_V2=1
```

## Common operational patterns

### "Did an endpoint die?"
```bash
bash scripts/infra/v6_status.sh endpoints
```

### "Some scenarios stuck in claim files (skipped_claimed > 0)"
```bash
# Find stale claims
find results/full_v6*/<model>/.claim_* -mmin +30
# Delete them
find results/full_v6*/<model>/.claim_* -mmin +30 -delete
# Restart workers
bash scripts/infra/v6_workers.sh stop <model>
bash scripts/infra/v6_workers.sh start <model> ...
```

### "checkpoint.json says complete but file count says no"
```bash
# Delete corrupt checkpoint, workers will rebuild from existing files
rm -f results/full_v6*/<model>/checkpoint*.json
bash scripts/infra/v6_workers.sh stop <model>
bash scripts/infra/v6_workers.sh start <model> ...
```

### "Need to dedup / verify"
```bash
PYTHONPATH=. python scripts/experiments/full_690_runner.py <model> <output_dir> --dedup
PYTHONPATH=. python scripts/experiments/full_690_runner.py <model> <output_dir> --validate
```

## Sync code to 145

```bash
sudo -n -u anonymous-org rsync -az --ignore-errors \
  --exclude='.git' --exclude='results' --exclude='__pycache__' --exclude='.omc' \
  /home/anonymous-org/anonymous-project/AnonProject/cga_bench/ \
  127.0.0.1
```

The symlink `/home/anonymous-org/cga_bench → cga_bench_v6` on 145 must exist for
imports to work.
