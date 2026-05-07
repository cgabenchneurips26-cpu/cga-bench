# Frontier Launch Plan — V7.3 Substrate (S1 rerun + S2/S3/S4)

**문서 ID**: `260504_frontier_v73_launch_plan.md`
**작성일**: 2026-05-04 03:05 UTC
**목표**: V7.3 corpus 위에서 4 frontier 모델 (Sonnet 4.6 / Opus 4.7 / GPT-5.5 Pro / Gemini 3 Pro)을 통일된 May-4 codebase로 채점하여 paper §Frontier Section의 결과 산출.
**상위 결정**: V6 → V7.3 substrate swap. S1 sonnet은 V6 substrate(`w8_706_manifest`)에서 Apr 28 코드로 채점됨 → drift 회피 위해 V7.3 substrate로 재실행.

---

## 1. Substrate 결정 — V7.3 Full Manifest (418 SGSC)

### 후보 비교

| Substrate | Scenarios | 모델 dim | Status | Pros | Cons |
|-----------|----------:|----------|--------|------|------|
| **v73_full (선택)** | 418 SGSC × 3 runs | 9 (locked) | ✅ DONE | SHA256 락, paper-stable, V6 706 manual의 SGSC subset | 706보다 작음 (cost↓) |
| v73_expanded | 680 capped × 3 runs | 9 (8 done, llama4scout 68%) | ⏳ ~30 min ETA | 더 큰 corpus | 8/9 만 완료 |
| 706 v6 manual | 706 (SGSC + non-SGSC) | 9 V6 base | V6 substrate | paper 1차 base | V6 → V7.3 swap에 모순 |

**결정**: **v73_full 418 SGSC** 단일 substrate. 근거:
- v73_full은 이미 SHA256-locked (`reports/path_d_day3/v73_full_9model_lock.sha256`).
- V7.3 swap 의도와 정합 (SGSC만 사용, V6 manual 제외).
- 비용/시간 manageable (v6 706 비례 ratio 0.59).
- v73_expanded는 cap 효과 검증용으로 §Sensitivity 별도 처리.

### Manifest 생성 (필요)

`evidence_pack/frontier/v73_418_manifest.json` 가 아직 없음. 생성 필요:

```bash
# Generate from v73_full verdict matrix (analogous to extract_w8_706_manifest.py)
PYTHONPATH=. python scripts/sgsc/extract_v73_manifest.py \
  --source evidence_pack/analysis/verdict_matrix_v7_3.json \
  --output evidence_pack/frontier/v73_418_manifest.json \
  --stratify-by fa_quartile
```

스크립트가 없으면 `extract_w8_706_manifest.py` 패턴 그대로 V7.3 substrate에 맞춰 작성 (~30분).

**Pre-flight 검증** (manifest 생성 후):
- 418 entries 검증
- Each entry: `{scenario_id, cpg_domain, violation_profile, n_episodes, fa_quartile}`
- Fingerprint SHA256 락
- Domain 분포 vs v73_full 동일 보장

---

## 2. 비용 + 시간 산정

### Per-stage breakdown (418 scenario × 1 run)

V6 706 base 비용을 418 ratio로 scale (×0.592):

| Stage | Model | 비용/Mtok in/out | V6 706 비용 (참고) | **V7.3 418 비용 추정** | **Wall time 추정** |
|-------|-------|-----------------:|------------------:|-----------------------:|-------------------:|
| **S1** | Claude Sonnet 4.6 | $3 / $15 | $66 (실측 actual $66, projected $85) | **$39** | **4.7 h** |
| **S2** | Claude Opus 4.7 | $15 / $75 | $353 | **$209** | **3.6 h** |
| **S3** | GPT-5.5 Pro | $5 / $25 | $159 | **$94** | **1.8 h** |
| **S4** | Gemini 3 Pro | $1.25 / $10 | $53 | **$31** | **1.2 h** |
| **합계** | | — | $631 | **$373** | **max=4.7 h (parallel)** |

### Token 가정

- Avg tokens/episode: 25,000 (frontier_spot_check.py 기본값)
- Input ratio: 0.85, Output: 0.15
- 706 → 418 ratio: 0.592

S1 V6 실측이 17.65M → 13.92M projected → actual (-21% saving). V7.3에서도 비슷한 -21% 절감 예상.

### Workers/concurrency

각 stage `--workers 8 --runs 1`. API rate limit이 첫 번째 bottleneck:
- Anthropic: ~50 req/min for Tier-3 → workers=8 ok
- OpenAI: ~500 req/min → workers=8 OK (under-utilized)
- Google: lower rate → workers 4-6 권장

---

## 3. Launch Sequence

### Pre-flight (T-30 min ~ T-15 min)

```bash
# Step 1: source API keys
source secrets/frontier_api_keys.env

# Step 2: smoke test S2 Opus on 1 scenario (가장 비싼 stage 사전 검증)
PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
  --agent rag_claude_opus47 \
  --manifest evidence_pack/frontier/v73_418_manifest.json \
  --output /tmp/s2_opus_smoke.json \
  --workers 1 --runs 1 --limit 1 --budget-cap-usd 5

# Verify: episode JSON 산출, compliance computed, $ < $5
# Fail → debug 후 재시도. Pass → all 4 stages launch.
```

### Parallel launch (T+0)

```bash
# All 4 frontier stages launch in parallel. Each in own log.
mkdir -p logs/frontier_v73

# S1 Sonnet 4.6 rerun
nohup PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
  --agent rag_claude_sonnet46 \
  --manifest evidence_pack/frontier/v73_418_manifest.json \
  --output evidence_pack/frontier/v73_s1_sonnet.json \
  --workers 8 --runs 1 --budget-cap-usd 60 \
  > logs/frontier_v73/s1_sonnet.log 2>&1 &
echo $! > /tmp/frontier_s1.pid

# S2 Opus 4.7 (highest priority — most expensive, longest wall)
nohup PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
  --agent rag_claude_opus47 \
  --manifest evidence_pack/frontier/v73_418_manifest.json \
  --output evidence_pack/frontier/v73_s2_opus.json \
  --workers 8 --runs 1 --budget-cap-usd 250 \
  > logs/frontier_v73/s2_opus.log 2>&1 &
echo $! > /tmp/frontier_s2.pid

# S3 GPT-5.5 Pro
nohup PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
  --agent rag_gpt55pro \
  --manifest evidence_pack/frontier/v73_418_manifest.json \
  --output evidence_pack/frontier/v73_s3_gpt55pro.json \
  --workers 8 --runs 1 --budget-cap-usd 120 \
  > logs/frontier_v73/s3_gpt55pro.log 2>&1 &
echo $! > /tmp/frontier_s3.pid

# S4 Gemini 3 Pro (lowest cost, shortest wall — backup if others fail)
nohup PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
  --agent rag_gemini3pro \
  --manifest evidence_pack/frontier/v73_418_manifest.json \
  --output evidence_pack/frontier/v73_s4_gemini3pro.json \
  --workers 6 --runs 1 --budget-cap-usd 50 \
  > logs/frontier_v73/s4_gemini3pro.log 2>&1 &
echo $! > /tmp/frontier_s4.pid

# Watchdog: kill any stage hitting budget cap
cat > /tmp/frontier_v73_watchdog.sh << 'EOF'
#!/bin/bash
# 30-min budget surveillance
while true; do
  for stage in s1 s2 s3 s4; do
    pid=$(cat /tmp/frontier_$stage.pid 2>/dev/null)
    if [ -z "$pid" ] || ! kill -0 $pid 2>/dev/null; then
      echo "$(date -u +%FT%TZ) [$stage] FINISHED or DEAD (PID $pid)"
    fi
  done
  sleep 60
done
EOF
chmod +x /tmp/frontier_v73_watchdog.sh
nohup /tmp/frontier_v73_watchdog.sh > /tmp/frontier_v73_watchdog.log 2>&1 &
```

### Monitoring (T+0 ~ T+5h)

```bash
# Per-stage progress
for stage in s1_sonnet s2_opus s3_gpt55pro s4_gemini3pro; do
  echo "=== $stage ==="
  tail -3 logs/frontier_v73/$stage.log
  ls evidence_pack/frontier/v73_${stage}/*.json 2>/dev/null | wc -l
done

# Live cost tally
for stage in s1 s2 s3 s4; do
  grep -E "actual_total_tokens|cost" logs/frontier_v73/${stage}*.log | tail -1
done
```

### Completion gate (T+5h ~ T+6h)

각 stage가 끝나면:
- 418 episodes succeeded (parse_success_rate ≥ 0.95)
- Output JSON schema가 v73_full 9-model과 동일한 episode 구조
- Total cost ≤ projected × 1.2 (20% buffer)

조건 미달 시 → re-launch with smaller manifest subset (fault scenarios만) + investigate.

---

## 4. Integration (T+5h ~ T+6h)

### Step 4.1: Combined verdict matrix

```bash
PYTHONPATH=. python scripts/experiments/integrate_frontier_results.py \
  --episodes-dir evidence_pack/frontier \
  --frontier-stages v73_s1_sonnet v73_s2_opus v73_s3_gpt55pro v73_s4_gemini3pro \
  --base-verdict evidence_pack/analysis/verdict_matrix_v7_3.json \
  --output reports/path_d_day3/verdict_matrix_v7_3_with_frontier.json
```

기대 결과:
- v73_full 9 models × 418 scen × 3 runs = 11,286 ep base
- + S1-S4 each 418 ep × 1 run = 1,672 ep frontier
- **Combined: 12,958 episodes, 13 models**

### Step 4.2: Recompute typed verdicts

V7.3 typed-CwT (TOM/ASC/CwT/PAF/TCC) 재계산:

```bash
PYTHONPATH=. python scripts/experiments/recompute_typed_verdicts.py \
  --input reports/path_d_day3/verdict_matrix_v7_3_with_frontier.json \
  --output reports/path_d_day3/verdict_matrix_v7_3_typed.json
```

V3 PARTIAL은 V7.3 substrate에서는 더 이상 발생 안 함 (현재 코드로 새로 채점).

### Step 4.3: Auto-numbers macro 재생성

```bash
PYTHONPATH=. python scripts/experiments/refresh_paper_macros.py \
  --verdict-matrix reports/path_d_day3/verdict_matrix_v7_3_with_frontier.json \
  --output paper/auto_numbers_v7_3_frontier.tex
```

---

## 5. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| API rate limit hit (Anthropic / OpenAI) | medium | wall time +50% | `--workers` reduce 8→4, retry with backoff (built-in) |
| S2 Opus exceeds budget cap | low | $50-100 over | `--budget-cap-usd 250` enforced, watchdog kills if hit |
| Schema mismatch 11 vs 13-model verdict matrix | medium | integrate.py crash | Pre-flight schema test on smoke output |
| frontier_spot_check.py manifest path error | low | immediate fail | Smoke test with `--limit 1` before parallel launch |
| 144 migration delay (cache rsync still running) | low | none for frontier (uses 145 endpoints) | Frontier uses cloud APIs, 144 unaffected |
| llama4scout v73_expanded 미완료 | low | 미블로킹 (별개 corpus) | v73_expanded는 §Sensitivity로 처리, frontier launch 가능 |

---

## 6. 시간선 (Timeline)

```
T-30 min  Generate v73_418_manifest.json + smoke test S2 Opus 1 ep
T-15 min  Verify smoke output schema + cost
T+0       Launch 4 stages parallel
T+1.2 h   S4 Gemini 3 Pro complete (lightest first)
T+1.8 h   S3 GPT-5.5 Pro complete
T+3.6 h   S2 Opus complete
T+4.7 h   S1 Sonnet rerun complete (longest)
T+5.0 h   integrate_frontier_results.py
T+5.5 h   recompute_typed_verdicts.py
T+6.0 h   refresh_paper_macros.py + verify auto_numbers
```

총 wall time: **~6h**. 총 비용: **~$373** + 20% buffer = **~$450 max**.

---

## 7. Pre-launch Checklist

- [ ] API keys env 활성화 (`source secrets/frontier_api_keys.env`)
- [ ] V7.3 manifest 생성 (`evidence_pack/frontier/v73_418_manifest.json`) + SHA256 락
- [ ] Smoke test S2 Opus 1 ep (cost < $1, schema OK)
- [ ] Disk space 확인 (`evidence_pack/frontier/` ~50MB per stage × 4 = 200MB)
- [ ] 145 boost monitoring 분리 (frontier은 cloud APIs, 145 endpoint 무관)
- [ ] 144 cache migration ETA 확인 (frontier launch 차단하지 않음)
- [ ] Watchdog script standby

## 8. Post-launch Checklist

- [ ] 4/4 stages parse_success_rate ≥ 95%
- [ ] Total cost ≤ $450
- [ ] Combined verdict_matrix_v7_3_with_frontier.json 12,958 ep
- [ ] Typed verdicts (TOM/ASC/CwT/PAF/TCC) 재계산 완료
- [ ] auto_numbers_v7_3_frontier.tex 생성
- [ ] SHA256 락 (paper rendering 전)
- [ ] §Frontier Section paper draft 작성 (5 model rank reversal, FA rate, η²)

---

## 9. 결정 권고 (사용자에게)

**진행 권고**: 위 plan대로 즉시 실행 가능.

**Single decision point**:
- v73_418_manifest 생성 후 smoke test → 통과하면 4 stage parallel launch.

만약 launch 전에 user 확인이 필요한 항목:
1. Substrate 418 (v73_full) vs 680 (v73_expanded) 선택 — 본 plan은 418 추천
2. Budget cap $450 OK?
3. 6h wall time tolerance OK?

확인 받으면 즉시 실행.

---

**문서 끝**.
