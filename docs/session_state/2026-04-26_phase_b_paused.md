# Phase B Run — Session State (PAUSED)

**Snapshot timestamp**: 2026-04-26T07:56:50Z
**Reason for pause**: User requested switch to a different experiment
**Branch**: `eval_science` @ `3c44161a`
**Host**: localhost (146)

---

## What was running

Phase B sweep across 8 models on the 56-CPG Tier S+ scenario corpus
(target = `~3186 scenarios × 8 models × 3 runs ≈ 76,464 episodes`).
Per-model target: **9558 episodes**.

Output dir: `results/full_v6b/`
Phase A reference: `results/full_v6a_706/`

### Endpoint topology when paused

| Host | Port | Model | Container | Status |
|---|---|---|---|---|
| 145 | 30005 | openai/gpt-oss-120b | `vllm-oss120b` | Up 10h |
| 145 | 30006 | Qwen/Qwen3-4B-Instruct-2507 | `vllm-qwen4b` | Up 10h |
| 145 | 30007 | Qwen/Qwen3.5-27B-FP8 | `vllm-qwen27b` | Up 10h |
| 145 | 30008 | Qwen/Qwen3.5-35B-A3B-FP8 | `vllm-qwen35b` | Up 10h |
| 145 | 30012 | deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | `vllm-deepseek` | Up 10h |
| 145 | 30106 | google/gemma-4-31b-it | `vllm-gemma4-g6` | Up 19h |
| 145 | 30107 | google/gemma-4-31b-it | `vllm-gemma4-g7` | Up 19h |
| 144 | 30001 | Qwen/Qwen3.5-397B-A17B-FP8 | `qwen3.5-397b-a` | Up 16h |
| 144 | 30002 | Qwen/Qwen3.5-397B-A17B-FP8 | `qwen3.5-397b-b` | Up 16h |
| 144 | 30003 | (was nemotron) | — | **DEAD** |
| 144 | 30004 | (was nemotron) | — | **DEAD** |

All 8 GPUs on 144 at 0% utilization at pause time (idle, model loaded).

### Daemons running on 146 when paused

| PID | Process | Logs |
|---|---|---|
| 1737893 | `bash scripts/infra/phase_orchestrator.sh` | `/tmp/phase_orch.log` |
| 2404947 | `bash scripts/infra/worker_watchdog.sh` | `/tmp/worker_wd.log` |

**No `full_690_runner` workers were running** on 146/145/144 at pause time.

---

## Phase B episode counts (at pause)

After 145→146 rsync of `gemma31b` (1800 unmirrored episodes recovered):

| Model | 146 (mirror) | 145 (source-of-truth) | Target | % |
|---|---:|---:|---:|---:|
| gemma31b | **9594** | 9594 | 9558 | **100%** ✓ |
| qwen397b | 4174 | n/a (writes from 146) | 9558 | 43% |
| oss120b | 2118 | 2118 | 9558 | 22% |
| qwen35b | 2118 | 2118 | 9558 | 22% |
| qwen27b | 2118 | 2118 | 9558 | 22% |
| qwen4b | 2118 | 2118 | 9558 | 22% |
| nemotron30b | 2118 | (n/a, 144-side dead) | 9558 | 22% |
| deepseek_r1_7b | 2118 | 2118 | 9558 | 22% |
| **Total** | **26,476** | — | **76,464** | **34.6%** |

### Last-episode timestamps (sanity)
- gemma31b: 2026-04-25 21:42:48 UTC (workers exited cleanly after gemma "COMPLETE")
- qwen397b: 2026-04-25 20:20:32 UTC (last write before stall)
- 6 small models: 2026-04-25 16:10:42 UTC ± a few seconds (synchronized halt)

---

## Phase A reference (`results/full_v6a_706/`) — already complete

| Model | Episodes |
|---|---:|
| gemma31b | 9914 |
| qwen397b | 6365 |
| oss120b / qwen35b / qwen27b / qwen4b / nemotron30b / deepseek_r1_7b | 4238 each |
| nemotron30b_PARTIAL_g4_died | 1433 (archived) |
| nemotron30b_contaminated_pre_v012 | 209 (archived) |

Phase A is the source for `evidence_pack/analysis/verdict_matrix_v6.json`
(16,944 episodes after dedup) and the corrected typed-CwT recompute
(`verdict_matrix_v6_typed.json`).

---

## Why Phase B stalled (root cause hypothesis)

The `worker_watchdog.sh` daemon stopped logging at
`[21:45:15] gemma31b: COMPLETE (eps=9574/9558); workers will exit naturally`
and never advanced to refilling the 6 small models or qwen397b workers.
The `phase_orchestrator.sh` daemon kept reporting `qwen397b eps=4174/9558 (43%)`
every 3 minutes for ~10h with zero progress — orchestrator only reports
counts; refill is the watchdog's job.

Suspected cause: watchdog hit an unhandled SSH/curl error while transitioning
from Stage 0 (gemma+qwen397b) to Stage 1 (5 small models on 145) and silently
died without emitting any final log line.

The Stage 1 entries in `worker_watchdog.conf` were correctly populated, so
restarting the watchdog with the same conf should resume cleanly.

---

## Resume instructions

When ready to continue this Phase B run (NOT now):

```bash
# 1. Verify endpoints still alive
sudo -n -u anonymous-org ssh 127.0.0.1 'docker ps | grep vllm'
sudo -n -u anonymous-org ssh [email-redacted] 'docker ps | grep qwen3.5-397b'

# 2. (If killed) restart endpoints — see scripts/infra/launch_vllm_*.sh
# 3. (For nemotron) rebuild 4× vllm:v0.12.0 containers on 144:30003/30004 etc.

# 4. Restart watchdog with existing conf
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
nohup bash scripts/infra/worker_watchdog.sh \
  scripts/infra/worker_watchdog.conf \
  > /tmp/worker_wd.log 2>&1 &

# 5. (Optional) restart phase_orchestrator for Stage 2 transition
nohup bash scripts/infra/phase_orchestrator.sh > /tmp/phase_orch.log 2>&1 &

# 6. Monitor
tail -f /tmp/worker_wd.log
```

Remaining work to reach Phase B completion:
- gemma31b: **DONE** (9594/9558)
- qwen397b: 5384 episodes remaining (~17h on 144 at v6 throughput)
- 6 small models: 7440 each = 44,640 total (~3.5h on 145 with full 145-fleet)
- nemotron30b: needs container rebuild first; then 7440 episodes (~6h)

---

## Pause actions (this session)

1. `rsync 145:gemma31b → 146` — recovered 1800 unmirrored episodes
2. `pkill -f phase_orchestrator.sh; pkill -f worker_watchdog.sh` (146 daemons)
3. **vLLM endpoints LEFT RUNNING** on 145/144 — they consume GPU memory but
   no compute; cheap to leave for fast resume. Kill them only if user wants
   to free GPUs entirely.
4. Workers: already 0; nothing to kill on 145/144.

---

## Cross-references
- Daemon stall analysis: memory file `project_phase_b_daemon_stall.md`
- Tier S+ pre-registration: `docs/cpg_expansion_v7/09_tier_s_plus_preregistration.md`
- Architecture-matters finding: memory `project_tier_s_plus_cpg_reconstruction.md`
- Typed CwT recompute: `docs/critical_review/typed_cwt_v2_corrected.md`
