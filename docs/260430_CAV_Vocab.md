좋습니다. Claude Code에 바로 붙여 넣을 수 있는 형태로 Day 1 전체 프롬프트 시리즈를 드리겠습니다.
작업 단위를 5개 phase로 나눴습니다. 각 phase는 독립 실행 가능하고, 각 phase 끝에 Tommy가 검증할 artifact가 나옵니다. phase 사이마다 결과 보고 다음 phase를 시작하시는 걸 권장합니다 — 중간에 가정이 깨지면 빠르게 조정 가능합니다.

사전 준비 (Tommy가 직접 1분)
Claude Code 시작 전에 repo root에서 한 번 확인:
bash# 1. 작업 브랜치 생성
git checkout -b cav_v0_5_build

# 2. 현재 상태 스냅샷 (rollback 안전망)
git tag pre_cav_$(date +%Y%m%d_%H%M)

# 3. RxNav API 동작 확인 (네트워크 sanity)
curl -s "https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term=acetaminophen&maxEntries=1" | head -c 200
마지막 명령이 JSON을 반환하면 RxNav 사용 가능. 만약 아무것도 안 나오면 회사 방화벽이 막는 것일 수 있으니 알려주세요.

Phase 1 — Vocabulary Harvesting (예상 1h)
Claude Code 프롬프트:
We are building CAV (Canonical Action Vocabulary) v0.5 for CGA-Bench. This is Phase 1 of 5: vocabulary harvesting.

GOAL: Extract every action ID referenced anywhere in the benchmark, deduplicate, and produce a single canonical list with raw provenance.

INPUTS:
- 25 CPG graph YAML files at cpg_model/graphs/*.yaml
  - Each graph has nodes[*].mandatory_actions, nodes[*].allowed_actions, nodes[*].forbidden_actions
- 706 scenario YAML files (locate via: find configs/scenarios -name "*.yaml" -o -name "*.yml")
  - Each scenario has expected_actions, forbidden_actions
- Existing normalizer at scoring/action_normalizer.py (or wherever ActionNormalizer lives — locate it first)

DELIVERABLE: scripts/cav/harvest_vocabulary.py that:
1. Walks all 25 graph YAMLs, collects every action ID with its source field type:
   - graph_mandatory, graph_allowed, graph_forbidden
   - Records: action_id, graph_id, node_id, field_type
2. Walks all scenario YAMLs, collects expected_actions and forbidden_actions:
   - Records: action_id, scenario_id, graph_ref, field_type (scenario_expected, scenario_forbidden)
3. Applies the existing ActionNormalizer to canonicalize each ID (use the normalize() method)
4. Deduplicates by (canonical_id) — keep all source occurrences as a list
5. Outputs cav_v0_5/01_raw_harvest.json with structure:
   {
     "metadata": {"timestamp": "...", "n_graphs": 25, "n_scenarios": ..., "normalizer_version": "..."},
     "entries": {
       "<canonical_id>": {
         "raw_forms": ["form1", "form2", ...],   // pre-normalization variants
         "occurrences": [
           {"source": "graph_mandatory", "graph_id": "...", "node_id": "..."},
           {"source": "scenario_expected", "scenario_id": "...", "graph_ref": "..."},
           ...
         ]
       },
       ...
     }
   }
6. Prints summary at end:
   - Total unique canonical IDs
   - Breakdown: how many appear ONLY in graphs / ONLY in scenarios / BOTH
   - Top 10 most frequently occurring IDs
   - Top 10 raw_forms variation count (IDs that have most pre-normalization variants)

CONSTRAINTS:
- Pure Python, no external deps beyond what's already in the repo
- DO NOT modify any source YAMLs
- Output goes to cav_v0_5/ (create dir if needed)
- Add cav_v0_5/ to .gitignore for now (will commit selectively after Phase 5)

After running, REPORT:
- Total entry count (we expect ~600-750)
- Scenario-only count (this is the candidate "extension" tier — we expect ~100-130)
- Any anomalies you notice in the data

Do not proceed to Phase 2. Stop after producing the JSON and the summary.
anonymous-user 검증 포인트 (Phase 1 끝):

Total entries가 600~750 범위 안인지 — 너무 적으면 (300 미만) harvesting이 뭔가 놓치고 있음, 너무 많으면 (900 초과) normalizer가 동작 안 하는 것
Scenario-only count가 100~130 범위인지 — 이게 author_extension tier 후보. 481 (paper §B6 숫자)과 다르면 normalizer 효과로 줄어든 것 (정상)


Phase 2 — 3-Tier Provenance Labeling (예상 2h)
Phase 1 결과 확인 후 시작.
Claude Code 프롬프트:
Phase 2 of CAV v0.5 build: 3-tier provenance labeling.

INPUT: cav_v0_5/01_raw_harvest.json from Phase 1

GOAL: Label every CAV entry with its provenance tier based on where it appears.

TIER DEFINITIONS:
- "explicit": appears in ANY graph's mandatory_actions OR forbidden_actions
  (these are the strongest source-grounded references — graph author marked them required/forbidden)
- "implicit": appears in graph allowed_actions but NEVER in mandatory_actions or forbidden_actions across ALL graphs
  (graph author listed as permissible but not required)
- "extension": appears ONLY in scenario expected_actions/forbidden_actions, NEVER in any graph field
  (this is the orphan tier — author injection at scenario level)

PRIORITY ORDER: if an ID qualifies for multiple tiers, take the strongest:
explicit > implicit > extension

DELIVERABLE: scripts/cav/label_provenance.py that:
1. Reads 01_raw_harvest.json
2. For each canonical_id, applies tier logic above
3. Adds an "action_kind" classification by prefix-matching the canonical_id:
   - "medication" if starts with: give_, administer_, start_, prescribe_, infuse_, bolus_
   - "lab" if starts with: order_lab_, draw_, check_lab_, measure_
   - "imaging" if starts with: order_imaging_, perform_ct, perform_mri, obtain_xray, order_ecg
   - "procedure" if starts with: perform_, intubate_, place_, insert_, cannulate_
   - "assessment" if starts with: assess_, monitor_, evaluate_, examine_
   - "consult" if starts with: consult_
   - "disposition" if starts with: admit_, discharge_, transfer_
   - "other" otherwise
4. Outputs cav_v0_5/02_labeled.json with structure:
   {
     "metadata": {...},
     "tier_summary": {"explicit": N1, "implicit": N2, "extension": N3},
     "kind_summary": {"medication": M1, "lab": M2, ...},
     "entries": {
       "<canonical_id>": {
         "tier": "explicit"|"implicit"|"extension",
         "action_kind": "medication"|...,
         "raw_forms": [...],
         "occurrences": [...]   // unchanged from Phase 1
       }
     }
   }
5. Also outputs cav_v0_5/02_extension_dropped.json — JUST the extension-tier entries:
   sorted by occurrence count descending. This is the file anonymous-user will use for spot-check.
6. Prints:
   - Tier counts (explicit/implicit/extension)
   - Kind counts within each tier (especially medication count within explicit+implicit — this feeds Phase 3 RxNorm mapping)
   - Top 30 extension-tier entries by occurrence count, with their action_kind

CONSTRAINTS:
- Read-only on Phase 1 output
- Output to cav_v0_5/

After running, REPORT:
- The three tier counts
- Total medication count (explicit + implicit) — this determines Phase 3 workload
- Top 30 extension entries — paste them so anonymous-user can eyeball spot-check candidates

Stop after Phase 2. Do not proceed.
anonymous-user 검증 포인트 (Phase 2 끝):

Tier 분포가 explicit ~440, implicit ~150, extension ~110 근처인지 — 크게 다르면 라벨링 룰이 graph 데이터와 안 맞을 수 있음
Top 30 extension list를 눈으로 훑어보세요. 명백히 source CPG에 있어야 할 것들 (예: discontinue_nsaid for AKI, calculate_glasgow_blatchford_score for GI bleeding)이 보이면 Phase 5 spot-check에서 graph extraction bug 가능성 확인


Phase 3 — RxNorm Crosscoding (예상 1.5h)
Phase 2 끝나고 medication 수 확인 후 시작.
Claude Code 프롬프트:
Phase 3 of CAV v0.5 build: RxNorm crosscoding for medication actions.

INPUT: cav_v0_5/02_labeled.json from Phase 2

GOAL: Map every medication-kind CAV entry (explicit + implicit tiers only — skip extension since it'll be dropped) to RxNorm RxCUI via deterministic RxNav API calls. NO LLM involvement.

API ENDPOINT: https://rxnav.nlm.nih.gov/REST/approximateTerm.json
- No auth required
- Rate limit: be polite, 0.1s sleep between calls
- Param: term=<drug_name>, maxEntries=5

DELIVERABLE: scripts/cav/map_rxnorm.py that:
1. Reads 02_labeled.json, filters to entries where action_kind="medication" AND tier in ("explicit","implicit")
2. For each entry, extracts drug name by stripping action verb prefix:
   - "give_acetaminophen" -> "acetaminophen"
   - "start_norepinephrine" -> "norepinephrine"
   - "administer_broad_spectrum_antibiotics" -> "broad spectrum antibiotics" (replace _ with space)
   - Handle "_if_*" suffix by dropping it: "start_vasopressor_if_hypotensive" -> "vasopressor"
3. Calls RxNav approximateTerm API
4. Acceptance criteria (deterministic):
   - Top hit must have score >= 50
   - Verify RxCUI exists by GET /rxcui/{rxcui}/properties.json
   - tty must be in {"IN", "BN", "SBD", "SCD", "SCDC", "SBDC"} (ingredient/branded/generic forms)
   - If criteria fail: mark as "rxnorm_unmatched"
5. Cache responses to cav_v0_5/03_rxnav_cache.json so re-runs are free
6. Outputs cav_v0_5/03_rxnorm_mapping.json:
   {
     "metadata": {"api": "rxnav.nlm.nih.gov", "n_attempted": N, "n_matched": M, "n_unmatched": U},
     "mappings": {
       "<canonical_id>": {
         "rxcui": "161",
         "rxnorm_name": "Acetaminophen",
         "tty": "IN",
         "score": 100,
         "extracted_term": "acetaminophen"
       }
     },
     "unmatched": [
       {"canonical_id": "...", "extracted_term": "...", "reason": "score_below_threshold|tty_invalid|api_error"}
     ]
   }
7. Prints:
   - n_matched / n_attempted ratio
   - List of unmatched IDs with reasons (these need anonymous-user's eyes)
   - Sample of 10 successful mappings to verify they look right

CONSTRAINTS:
- Use stdlib urllib or requests, no other deps
- Network calls must have try/except — if RxNav is down, write a clear error and exit 1
- Cache file must be valid even if script crashes mid-run (write incrementally or atomic)

After running, REPORT:
- Match rate (we expect 85-95% for canonical drug names)
- Unmatched list — anonymous-user will scan these
- Any unexpected mappings (e.g., "broad spectrum antibiotics" might not match — that's expected)

Stop after Phase 3.
anonymous-user 검증 포인트 (Phase 3 끝):

Match rate가 85% 이상이면 정상. 70% 이하면 prefix stripping 룰이 약함 — Tommy가 unmatched list 보고 패턴 추가 결정
Unmatched list에 "broad_spectrum_antibiotics", "vasopressor", "antibiotics" 같은 일반명사 약물군은 매핑 실패가 정상 (RxNorm은 specific drug 단위) — 이건 paper에서 "152개 중 14개는 RxNorm 매핑 실패; 일반 약물군 명칭으로 reported as CAV-only" 같은 disclosure로 처리


Phase 4 — Strict Policy Application + Re-score Prep (예상 1h)
Claude Code 프롬프트:
Phase 4 of CAV v0.5 build: apply Strict policy and prepare for re-scoring.

INPUTS:
- cav_v0_5/02_labeled.json
- cav_v0_5/03_rxnorm_mapping.json

GOAL: Produce the final CAV v0.5 artifact and a scenario validator that drops extension-tier IDs from expected_actions during scoring.

DELIVERABLE 1: scripts/cav/build_final_cav.py that:
1. Merges 02_labeled.json + 03_rxnorm_mapping.json
2. Drops all extension-tier entries (Strict policy)
3. Outputs cav_v0_5/cav_v0_5.json — THE canonical artifact:
   {
     "version": "0.5",
     "build_date": "...",
     "policy": "strict",
     "summary": {
       "total_entries": N,
       "by_tier": {"explicit": ..., "implicit": ...},
       "by_kind": {...},
       "rxnorm_mapped": M
     },
     "entries": {
       "<canonical_id>": {
         "tier": "explicit"|"implicit",
         "action_kind": "...",
         "raw_forms": [...],
         "rxnorm": {"rxcui": "...", "name": "...", "tty": "..."} | null,
         "occurrences": [...]
       }
     }
   }
4. Outputs cav_v0_5/cav_v0_5_dropped.json — the dropped extension entries (for paper disclosure):
   {
     "policy": "strict",
     "n_dropped": N,
     "dropped_entries": {<canonical_id>: {action_kind, occurrences}, ...}
   }

DELIVERABLE 2: scripts/cav/cav_validator.py — a callable module:
   from scripts.cav.cav_validator import filter_action_list, is_in_cav

   - load_cav() -> dict (loads cav_v0_5.json once, caches)
   - is_in_cav(action_id: str) -> bool
   - filter_action_list(actions: list[str], context: str = "") -> tuple[list[str], list[str]]
     Returns (kept, dropped_with_reasons). "context" is logged for traceability.

   This module will be imported by the re-scoring pipeline in Day 2.

DELIVERABLE 3: tests/test_cav/test_cav_validator.py with:
   - test_known_explicit_id_passes (use a few real IDs from cav_v0_5.json)
   - test_known_extension_id_dropped (use a few from cav_v0_5_dropped.json)
   - test_unknown_id_dropped
   - test_filter_preserves_order
   - test_filter_returns_dropped_with_reason

CONSTRAINTS:
- pytest tests/test_cav/ must pass
- cav_v0_5.json is the ONLY artifact downstream code should depend on. cav_v0_5_dropped.json is paper-only.

After running, REPORT:
- Final CAV size (explicit + implicit count)
- Dropped extension count
- Test results
- Confirm cav_v0_5.json schema looks clean

Stop after Phase 4.
anonymous-user 검증 포인트 (Phase 4 끝):

최종 CAV size = explicit + implicit. ~590개 예상
Dropped count = extension count from Phase 2 (~110개)
Test 5개 pass


Phase 5 — Day 1 EOD Spot-check (예상 1h, anonymous-user 직접)
Claude Code 프롬프트 (sampling helper만):
Phase 5: Generate spot-check sample for anonymous-user's manual review.

INPUT: cav_v0_5/cav_v0_5_dropped.json

GOAL: Sample 30 dropped extension-tier IDs, generate a review form, and provide source-CPG context for anonymous-user to manually verify whether each one is a TRUE author-injection or a graph-extraction MISS.

DELIVERABLE: scripts/cav/generate_spotcheck.py that:
1. Reads cav_v0_5_dropped.json
2. Stratified sample of 30 entries:
   - Top 10 by occurrence count (most impactful drops)
   - Random 10 from medication kind
   - Random 10 from non-medication kinds (procedure/assessment/consult/...)
3. For each sampled entry, looks up the referenced CPG graph_ref from its scenario occurrences, finds the corresponding parsed CPG document at corpus/<cpg_name>.parsed.json (or wherever parsed CPGs live — locate first), and extracts a 500-char window around any text mention of the action concept (best-effort substring match on the action_id stripped of underscores)
4. Outputs cav_v0_5/05_spotcheck_form.md — markdown table:

   | # | canonical_id | kind | n_occ | graph_ref | source_text_snippet | anonymous-user's verdict |
   |---|---|---|---|---|---|---|
   | 1 | discontinue_nsaid | medication | 76 | kdigo_aki | "...avoidance of NSAIDs is recommended..." | ☐ author_inject ☐ extraction_miss ☐ unclear |
   ...

5. Also outputs a CSV version (05_spotcheck_form.csv) for spreadsheet review.

CONSTRAINTS:
- If parsed CPG not found, just mark "source_text_snippet" as "[CPG not found at expected path]"
- Snippet extraction can be naive (substring match); not aiming for high recall, just providing context

After running, PRINT the 30 entries inline so anonymous-user can start reviewing immediately.

Stop after Phase 5.
anonymous-user 직접 작업 (1h):

30개 각각에 verdict 표시: author_inject / extraction_miss / unclear
extraction_miss 비율 계산:

5개 미만 (<17%): Strict policy 그대로 진행. Day 2 re-score 시작.
5~10개: paper에 graph extraction limitation을 disclose하면서 Strict 진행. v1에서 patch.
10개 초과: 일정 압박. anonymous-user 결정 — graph YAML patch까지 Day 2에 끼울지 vs Strict 유지하고 paper에서 솔직하게 disclose할지