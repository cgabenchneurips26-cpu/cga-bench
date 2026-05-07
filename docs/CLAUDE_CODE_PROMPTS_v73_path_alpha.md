# v7.3 Path α-Full Expansion — Claude Code Prompts (Sequential)

**Target**: Run full B-4 patient profile expansion on v7.3 atoms, compile expanded corpus, launch 9-model × 3-run rerun within 12h compute window.

**Resource**: H200 8 + A100 8 = 16 GPUs, ~1,500 episodes/hour aggregate
**Expected scope**: ~600 expansion scenarios × 9 models × 3 runs = ~16,200 episodes
**Timeline**: 5/2 16:00 prep start → 17:00 launch → 5/3 04:00 complete → 06:00 paper writing

**Critical rule**: Do not proceed to next step until current step's gate check PASSES. If FAIL, report and wait for anonymous-user decision.

---

## STEP 1: Pre-prep verification (5 min)

**Paste to Claude Code:**

```
v7.3 Path α-Full expansion 시작 전 사전 검증입니다.

다음 4개 모두 PASS여야 진행 가능:

1. v7.3 atoms 무결성 확인:
   - sgsc_output/v7_e3_combined_v3/{25 graphs}/atoms_smoke.json 모두 존재
   - sgsc_output/v7_2_atoms_v3/{20 graphs}/atoms_smoke.json 모두 존재 (asco_tls 포함, east_damage_control 제외)
   - 각 파일 JSON parseable
   - 총 atoms = 1,494 (883 core + 611 expansion)
   
2. B-4 PROFILE_BANK 코드 무결성:
   - scripts/sgsc/patient_profile_expansion.py 존재
   - PROFILE_BANK 30 specs 정의됨 (T1×12 + T2×6 + T3×5 + T4×4 + T5×3)
   - tests/test_sgsc/test_patient_profile_expansion.py 20 tests pass
   
3. Recompile script 준비:
   - scripts/sgsc/recompile_corpus.py 존재
   - --enable-patient-profiles 플래그 작동
   - --profile-catalog 인자 받음

4. Disk space:
   - results/v73_full 보존 확인 (기존 11,286 episodes)
   - 추가 16,200 episodes × 50KB = ~810MB 여유

각 항목 결과를 표로 보고. 하나라도 FAIL이면 STOP.

GATE: 4/4 PASS 시 STEP 2 진행
```

---

## STEP 2: Profile expansion smoke test on 1 graph (15 min)

**Paste after STEP 1 PASS:**

```
1 graph로 patient profile expansion smoke test.

Graph: kdigo_contrast_aki (이전 B-4 검증된 graph, 7→35 expansion 결과 있음)

실행:
PYTHONPATH=. python scripts/sgsc/recompile_corpus.py \
  --atoms-dir sgsc_output/v7_e3_combined_v3/ \
  --output-dir sgsc_output/v7_3_smoke_expansion/ \
  --enable-patient-profiles \
  --profile-catalog data/v6_patient_profile_catalog.json \
  --max-profiles-per-cluster 5 \
  --graph-filter kdigo_contrast_aki

산출물 확인:
  sgsc_output/v7_3_smoke_expansion/kdigo_contrast_aki/kdigo_contrast_aki_scenarios.json
  
검증 항목:
  1. Scenario count: v7.3 base에서 N개 → expansion 후 M개 (5× 정도 expected)
  2. 각 scenario의 patient block 채워짐 (population_criteria 포함)
  3. _sgsc_profile_tier 필드 존재 (T1/T2/T3/T4/T5 중 하나)
  4. _sgsc_profile_name 필드 존재
  5. expected_actions 변경 없음 (atom-derived 그대로)
  6. forbidden_actions 변경 없음 (graph-level 그대로)
  
표로 보고:
  v7.3 base scenarios | expansion 후 scenarios | ratio | tier 분포 (T1/T2/T3/T4/T5 count)

GATE: 
  - Ratio >= 3× (expansion 작동)
  - 5 tier 모두 존재
  - patient block 채워짐
  - PASS시 STEP 3, FAIL시 STOP
```

---

## STEP 3: 49-graph full profile expansion (30 min)

**Paste after STEP 2 PASS:**

```
49 graph 전체 profile expansion compile.

실행:
PYTHONPATH=. python scripts/sgsc/recompile_corpus.py \
  --atoms-dir sgsc_output/v7_3_atoms_union/ \
  --output-dir sgsc_output/v7_3_expanded_final/ \
  --enable-patient-profiles \
  --profile-catalog data/v6_patient_profile_catalog.json \
  --max-profiles-per-cluster 5

(만약 v7_3_atoms_union/ 디렉토리 없으면, v7_e3_combined_v3 + v7_2_atoms_v3를 union하는 step 먼저)

per-graph override 적용 (B-4와 동일):
  ssc_sepsis_hour1_bundle: 30
  universal_clinical_safety: 30
  aha_chest_pain_evaluation: 15
  kdigo_aki_full: 10
  acls_cardiac_arrest: 8
  pals_pediatric_emergency: 6
  rest: 5 (default)

산출물:
  sgsc_output/v7_3_expanded_final/{49 graphs}/{graph_id}_scenarios.json
  
Quality gate 7개 (B-5와 동일) 재실행:
  1. Total scenarios in [400, 800] range (expansion graphs sparse 고려, 범위 relaxed)
  2. Hallucination rate 0%
  3. Truncated stem rate 0%
  4. Action type diversity 5-9 per graph
  5. Population coherence (no pregnancy+male, no pediatric+cad)
  6. Forbidden action consistency (profile-specific never intersects graph mandatory)
  7. T1-T5 coverage gates: T1≥30%, T2≥15%, T3≥10%, T4≥8%, T5≥20%

산출 보고:
  - Total expansion scenarios: N
  - Per-graph scenario count distribution (top 10, bottom 10)
  - 7 quality gates 결과 표
  - T1/T2/T3/T4/T5 분포 (count + %)

GATE:
  - 7/7 gates PASS
  - Total scenarios in [400, 800]
  - 5 tiers 모두 minimum 충족
  - PASS시 STEP 4, FAIL시 STOP + anonymous-user 결정 대기
```

---

## STEP 4: SHA256 freeze + manifest (10 min)

**Paste after STEP 3 PASS:**

```
v7.3-expanded corpus freeze.

1. SHA256 manifest 생성:
   find sgsc_output/v7_3_expanded_final -type f -name "*.json" | sort | \
     xargs sha256sum > reports/path_d_day3/v7_3_expanded_sha256.txt

2. Frozen tar:
   tar czf reports/path_d_day3/v7_3_expanded.tar.gz sgsc_output/v7_3_expanded_final/
   sha256sum reports/path_d_day3/v7_3_expanded.tar.gz > reports/path_d_day3/v7_3_expanded.tar.sha256

3. Manifest JSON:
   sgsc_output/sgsc_manifest_v7_3_expanded.json with:
     - total_atoms: 1494
     - total_scenarios: <STEP 3 result>
     - graph_count: 49
     - profile_expansion: enabled
     - profile_catalog: v6_patient_profile_catalog.json
     - tier_distribution: T1/T2/T3/T4/T5 counts
     - per_graph_counts: {graph_id: scenario_count}
     - sha256_manifest: <hash of sha256.txt>
     - freeze_date: 2026-05-02

4. Macro pre-stage (paper/auto_numbers_v73_expanded.tex):
   \providecommand{\sgscExpandedScenarios}{<count>}
   \providecommand{\sgscExpandedEpisodes}{<count × 9 × 3>}
   \providecommand{\sgscExpandedTierOne}{...}
   ... 5 tiers
   \providecommand{\sgscExpandedTotalCorpus}{<v7.3 base + expanded>}

산출 보고:
  - Frozen artifacts 경로
  - SHA256 hashes
  - Manifest JSON 산출 확인
  - Macro file 작성 확인

GATE: 4/4 산출 시 STEP 5 진행
```

---

## STEP 5: Endpoint inventory + health check (15 min)

**Paste after STEP 4 PASS:**

```
16 endpoints (H200 8 + A100 8) inventory + health check.

각 endpoint별 확인:
  1. Endpoint URL + port
  2. Loaded model name
  3. /v1/models 200 response
  4. /v1/chat/completions 1-call test (1 token output)

9 model × endpoint 매핑 확인:
  qwen397b: H200 endpoint × ?
  oss120b: H200 endpoint × ?
  llama-4-scout: H200 endpoint × ?
  gemma-4-31b: H200 endpoint × ?
  nemotron-30b: H200 endpoint × ?
  qwen35b: A100 endpoint × ? (smaller, A100에 fit)
  qwen27b: A100 endpoint × ?
  qwen4b: A100 endpoint × ?
  deepseek-r1-7b: A100 endpoint × ?

H200 8장 / A100 8장 활용 전략:
  - 큰 model (>30B): H200, 1 endpoint per GPU 또는 TP
  - 중간 model (7-30B): H200 또는 A100, 2 endpoints
  - 작은 model (<10B): A100, 다중 endpoint

목표 throughput: 1,500 ep/hour aggregate
산출 보고:
  - 16/16 endpoint health 표
  - Model assignment matrix
  - Estimated per-model throughput
  - Bottleneck model 식별 (가장 느린 model이 critical path)

GATE:
  - 16/16 endpoints respond
  - 9 models 모두 endpoint 할당됨
  - Bottleneck throughput >= 100 ep/hour (12h × 100 × 9 = 10,800 minimum)
  - PASS시 STEP 6, FAIL시 STOP
```

---

## STEP 6: Single-episode smoke on each model (30 min)

**Paste after STEP 5 PASS:**

```
9 models 각각 1 episode smoke test.

목적: Patient profile이 실제로 trace에 반영되는지 검증.

Smoke scenario 선정:
  - T3 또는 T4 profile이 들어간 scenario 1개
  - Graph: aha_heart_failure_2022 (rich graph, 다양한 profile)
  - Profile tier: T4_rare_population (pregnancy 가능성 높음)

각 model별 실행:
PYTHONPATH=. python scripts/experiments/full_v73_runner.py <MODEL> \
  --scenarios-dir <expanded scenario YAML 위치> \
  --max-scenarios 1 \
  --runs-per-scenario 1 \
  --output /tmp/v73_expanded_smoke/<MODEL>/ \
  --scenario-filter <T4 profile scenario>

각 결과 검증:
  1. Episode 완성 (timeout 아님)
  2. Trace에 patient context (population_criteria) 포함
  3. Action 출력 정상 (empty 아님)
  4. CGA score 계산됨 (NaN 아님)
  5. T4 profile (pregnancy 등)에 대해 agent reasoning이 *다르게* 나오는가
     (T5 default scenario와 비교 시 다른 actions 출력)

산출 보고:
  - 9 models × 1 episode 결과 표 (CGA, action count, profile detected)
  - Patient profile이 trace에 미치는 영향 정성적 분석
  - 실패한 model 있으면 root cause 진단

GATE:
  - 9/9 smoke 성공
  - patient context trace 반영 확인
  - PASS시 STEP 7, FAIL시 model별 fix 또는 제외 결정
```

---

## STEP 7: Watchdog + launch script preparation (15 min)

**Paste after STEP 6 PASS:**

```
Launch 전 watchdog script 준비.

1. Watchdog script 생성:
cat > /tmp/v73_expanded_watchdog.sh << 'EOF'
#!/bin/bash
LAUNCH_TIME=$(date +%s)
LOG_FILE="/tmp/full_v73_expanded.log"
OUTPUT_DIR="results/v73_expanded"
TARGET=16200  # 9 × <expansion count> × 3

while true; do
  sleep 600  # 10분
  ELAPSED=$(($(date +%s) - LAUNCH_TIME))
  EPISODES=$(find $OUTPUT_DIR -name "*.json" 2>/dev/null | wc -l)
  RATE=$(echo "scale=2; $EPISODES / ($ELAPSED / 3600)" | bc)
  
  echo "[$(date)] $EPISODES / $TARGET (rate: $RATE/h, elapsed: ${ELAPSED}s)" >> /tmp/v73_expanded_watchdog.log
  
  # 30분 시점 첫 점검
  if [ $ELAPSED -gt 1800 ] && [ $EPISODES -lt 200 ]; then
    echo "ABORT: Only $EPISODES after 30min" | tee -a /tmp/v73_expanded_watchdog.log
    pkill -f full_v73_runner
    exit 1
  fi
  
  # 1시간 후 ETA estimate
  if [ $ELAPSED -gt 3600 ]; then
    ETA_HOURS=$(echo "scale=1; ($TARGET - $EPISODES) / $RATE" | bc)
    echo "ETA: ${ETA_HOURS}h remaining" >> /tmp/v73_expanded_watchdog.log
    
    # 12h 안에 완료 못 할 것 같으면 alert
    REMAINING=$((43200 - ELAPSED))  # 12h = 43200s
    if [ $(echo "$ETA_HOURS * 3600 > $REMAINING" | bc) -eq 1 ]; then
      echo "WARNING: ETA exceeds 12h budget" >> /tmp/v73_expanded_watchdog.log
    fi
  fi
done
EOF
chmod +x /tmp/v73_expanded_watchdog.sh

2. Launch command 준비 (paste 가능한 형태):
nohup PYTHONPATH=. python scripts/experiments/full_v73_runner.py all \
  --scenarios-dir <expanded scenario directory> \
  --runs-per-scenario 3 \
  --output results/v73_expanded/ \
  --resume \
  > /tmp/full_v73_expanded.log 2>&1 &
echo $! > /tmp/v73_expanded.pid

3. Pre-launch backup:
cp -r results/v73_full results/v73_full_backup_pre_expansion_$(date +%Y%m%d_%H%M)

4. Disk space check:
df -h /
필요: 5GB+ 여유

산출 보고:
  - Watchdog script 작성 확인
  - Launch command 준비 확인
  - Pre-launch backup 산출 확인 (size)
  - Disk space 충분 여부

GATE: 4/4 PASS 시 STEP 8 진행
```

---

## STEP 8: Launch + 30min monitoring (35 min)

**Paste after STEP 7 PASS:**

```
v7.3-expanded 9-model rerun launch.

1. Watchdog 백그라운드 실행:
nohup /tmp/v73_expanded_watchdog.sh > /tmp/v73_expanded_watchdog.log 2>&1 &
echo $! > /tmp/v73_expanded_watchdog.pid

2. Main launch:
nohup PYTHONPATH=. python scripts/experiments/full_v73_runner.py all \
  --scenarios-dir <expanded scenario directory> \
  --runs-per-scenario 3 \
  --output results/v73_expanded/ \
  --resume \
  > /tmp/full_v73_expanded.log 2>&1 &
echo $! > /tmp/v73_expanded.pid

3. 첫 5분 monitoring:
   - tail -f /tmp/full_v73_expanded.log
   - First episode 완성 확인
   - Cat /tmp/full_v73_expanded.log first episode 결과
   - Endpoint 5xx error 없는지

4. 15분 시점 check:
   - Episode count: find results/v73_expanded -name "*.json" | wc -l
   - 10+ episodes 완성 expected
   - GPU util via nvidia-smi (모든 endpoint 50%+)

5. 30분 시점 final check:
   - 50-100 episodes 완성 expected
   - Rate calculation: episodes / 30min × 60 = ep/hour
   - 목표 1,500 ep/hour 도달 여부
   - Endpoint health 재확인

6. ETA 산출:
   - If rate < 1,000 ep/hour at 30min: WARN
   - If rate < 800 ep/hour: ABORT 결정 (Path γ fallback)

산출 보고:
  - Launch PID 기록
  - 30min 시점 episode count + rate + ETA
  - Endpoint health summary
  - 첫 episode raw trace 1개 (sanity)

GATE:
  - 30min 시점 50+ episodes
  - Rate >= 1,000 ep/hour
  - 9/9 model에서 episodes 산출 중
  - PASS시 LONG WAIT (12h compute)
  - FAIL시 즉시 abort 결정 → Path γ fallback
```

---

## STEP 9: Sleep prep (after STEP 8 PASS, ~5/2 18:00)

**anonymous-user 직접 (Claude Code 작업 아님)**:

```
Sleep 준비:
1. Watchdog log monitoring 위치 확인:
   - /tmp/v73_expanded_watchdog.log
   - /tmp/full_v73_expanded.log
   
2. anonymous-user 5/2 23:00 무렵 final check (30초):
   - tail -1 /tmp/v73_expanded_watchdog.log
   - Episode count 5,000+ expected (5h × 1,500 ep/h × 0.7 actual rate)
   - Stable이면 sleep
   
3. Alarm 5/3 04:00 설정 (compute 끝나는 시점)
```

---

## STEP 10: Wake-up post-compute (5/3 04:00, ~2h)

**Paste after wake:**

```
v7.3-expanded compute 결과 검증.

1. Episode count 확인:
   find results/v73_expanded -name "*.json" | wc -l
   목표: 16,200 (9 × 600 × 3)
   허용: 14,000+ (87% completion)
   
2. Per-model completion check:
   for model in deepseek_r1_7b gemma31b llama4scout nemotron30b oss120b qwen27b qwen35b qwen397b qwen4b; do
     n=$(find results/v73_expanded/$model -name "*.json" 2>/dev/null | wc -l)
     echo "$model: $n / 1800"  # 1800 = 600 × 3
   done
   
3. Cat A/B/M classification on 16,200:
   PYTHONPATH=. python scripts/experiments/categorize_episodes.py \
     --episode-dir results/v73_expanded/ \
     --output evidence_pack/analysis/v73_expanded_episode_analysis.json

4. T1-T5 stratification:
   - 각 episode의 _sgsc_profile_tier 추출
   - Per-tier C2, CGA, CGA breakdown
   - 표 산출:
     | Tier | N | CGA | C2 | Match% |
     | T1 common comorbidity | ... |
     | T2 severity | ... |
     | T3 rare special | ... |
     | T4 rare population | ... |
     | T5 default | ... |
   
5. Tier-stratified Cat A subset (가장 critical):
   - Cat A AND T_x 별로 C2 산출
   - T3/T4 Cat A에서 C2가 catastrophically low인지 확인
   - 만약 T3/T4 C2 < 0.1 (vs T5 ~0.5) → Theorem 1 Case (iv) headline evidence
   
6. Macro file v4 export:
   paper/auto_numbers_v73_expanded.tex
   - Total expansion scenarios + episodes
   - Per-tier C2/CGA
   - Per-tier × Cat A subset
   - Per-model × Cat A × tier (3-way breakdown)

산출 보고:
  - 16,200 / 16,200 episode count check
  - Cat A/B/M re-classification on full 27,486 corpus (기존 11,286 + 16,200)
  - Tier × Cat A C2 표
  - Theorem 1 Case (iv) evidence 정량화
  - Macro file v4 ready 확인

GATE: 모두 PASS 시 STEP 11 (paper writing)
```

---

## STEP 11: Paper §V7 writing (5/3 06:00 ~ 5/4 EOD)

**Paste after STEP 10 PASS:**

```
Paper §V7 3-tier draft 시작.

Reference 문서:
  - /mnt/user-data/outputs/PATH_D_DAY2_PAPER_INTEGRATION_PLAN.md (§3 LaTeX text)
  - /mnt/user-data/outputs/META_GAP_ANALYSIS_iterative_closing.md (P0 작업들)
  - paper/auto_numbers_v73_expanded.tex (방금 산출)

작업 순서:
  1. Phase A vs Cat A/B/M consistency audit (meta-gap §7 P0)
  2. §V7.1 Graph-anchored + T1-T5 stratification (headline)
  3. §V7.2 Atom granularity (Cat B+M)
  4. §V7.3 Domain coverage
  5. §1 contribution C4 empirical demonstration paragraph
  6. §AY.4 Entailment threshold sensitivity
  7. §App reproducibility (multi-shot, families)
  8. §App CAV v0.5→v0.6
  9. Abstract update with stratification headline

이 단계는 anonymous-user 직접 작업. Claude Code는 reference 산출 정도.
```

---

## Fallback path (각 GATE FAIL 시)

```
STEP 1 FAIL: 환경 issue, 진행 불가
STEP 2 FAIL: profile expansion 작동 안 함 → B-4 코드 fix 또는 Path β
STEP 3 FAIL: quality gate 실패 → expansion 강도 조정 (max_profiles 줄이기) 또는 Path β
STEP 4 FAIL: freeze 실패 → 수동 freeze
STEP 5 FAIL: endpoint 부족 → 8-model launch 또는 throughput 줄이기
STEP 6 FAIL: model별 issue → 해당 model 제외, 8 또는 7 model launch
STEP 7 FAIL: watchdog 또는 backup 실패 → 수동 운영
STEP 8 FAIL: launch 실패 또는 rate 낮음 → Path γ (T3/T4 only) fallback
STEP 9 (sleep): sleep 가능 여부만 결정
STEP 10 FAIL: 부분 결과 → 가용 episodes로 진행
```

---

## Critical timing reminders

```
5/2 16:00: STEP 1 시작
5/2 17:00: STEP 8 launch (compute 시작)
5/2 18:00 - 23:00: anonymous-user 병행 paper-prep work (meta-gap §7 P0 작업)
5/2 23:00: Sleep 시작
5/3 04:00: STEP 10 (wake)
5/3 06:00: STEP 11 (paper writing)
5/3 EOD: §V7 draft 완료
5/4: Polish + cross-references
5/5: Final review
5/6: 마감
```

---

## Single most important reminder

**Each GATE check is mandatory.** Do not optimistically proceed to next step. The cascade rework risk in this session has been the #1 cost. A 5-min FAIL detection + report is far cheaper than a 12h compute on bad input.

If any step's result is *unexpected* (not just FAIL but "weird"), STOP and report to anonymous-user. Examples:
- STEP 2: smoke ratio is 5× as expected but tier distribution is weird
- STEP 3: 7 gates pass but T3 coverage is exactly at minimum (10.0%)
- STEP 6: 9 models all succeed but CGA is uniformly 1.0 (likely bug)

These "looks-OK-but-suspicious" patterns are the most dangerous. Report and wait.
