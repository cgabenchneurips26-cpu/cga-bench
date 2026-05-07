TIER-1 (paper 정확성 직결 — 제출 전 권고)
T1. Tier-A footnote arithmetic — off-by-one 가능성
§C3 분석에서:
교집합: 10 (CDE 11 중 10이 normalizer에서도 발견)
CDE에만 존재: 1
Normalizer에만 존재: 8
그런데 footnote 본문:
latex\conflictPatternsN{} of these correspond to CDE-audited Tier-B/C patterns,
\conflictPatternsN = 11. 실제 intersection 은 10. 즉 "11 of 18 correspond to CDE patterns" 인데 실제는 "10 of 18".
bash# footnote 본문 정확한 wording 확인
grep -B 2 -A 8 "of these correspond to CDE\|correspond to CDE-audited" C:\Users\renkr\Downloads\cga_bench\paper\appendix_v18.tex 2>/dev/null

# 정확한 set diff 재확인
python -c "
import json
audit = json.load(open('C:\Users\renkr\Downloads\cga_bench\evidence_pack\cde_conflict_audit_v1.json'))
norm = json.load(open('C:\Users\renkr\Downloads\cga_bench\evidence_pack\analysis\normalizer_audit.json'))
audit_keys = {(c.get('graph'), c.get('canonical', c.get('action'))) for c in (audit.get('conflicts') or audit if isinstance(audit, list) else [])}
norm_keys = {(b.get('graph'), b.get('canonical', b.get('action'))) for b in norm.get('conflict_blindspots', [])}
inter = audit_keys & norm_keys
print(f'audit {len(audit_keys)}, norm {len(norm_keys)}, intersection {len(inter)}')
" 2>&1
권고: footnote 의 \conflictPatternsN{} 을 새로운 macro \cdeNormIntersectionN{10} 으로 바꾸거나, 본문 wording 을 "10 of these {18}" 로 hardcode. 전자가 더 정확.
T2. v1.1 ViolationExtractor 가 real episode data 에 한 번이라도 실행 됐는가
3,584 conflict-touch 는 action-set static membership 검사. ViolationExtractor with derived_constraints != None 은 11 synthesised episodes 위에서만 검증됐고 (results/scn012_repatch/pre_post_diff.json), 실제 16,944 Phase A episodes 위에서 한 번도 실행되지 않은 상태 일 가능성.
위험: production code path 가 real data 와 만났을 때 bug 잠재 (예: episode log 형식 vs CDE patient_dict 변환에서의 schema 차이, ActionRecord vs Action 파싱 mismatch). 5/6 제출 후 reviewer 가 코드 돌려보다 fail 발견 시 치명적.
bash# 실제 enable_cde_rescoring=True 로 16,944 episodes 일부라도 채점한 결과 record 가 있나
grep -rn "enable_cde_rescoring.*True\|cde_cga_score" /sessions/eager-awesome-lovelace/mnt/cga_bench/results/ 2>/dev/null | head

# ViolationExtractor + DerivedConstraintSet 호출 흔적 (synth 외)
grep -rn "extract_violations.*derived_constraints" /sessions/eager-awesome-lovelace/mnt/cga_bench/results/ /sessions/eager-awesome-lovelace/mnt/cga_bench/scripts/ 2>/dev/null | head

# 16,944 episode logs 가 실제 V1 ViolationExtractor 와 호환되는 형식인지 확인
ls /sessions/eager-awesome-lovelace/mnt/cga_bench/data_release/v5.0/episodes/oss120b/ 2>/dev/null | head -3
python -c "
import json
import glob
files = glob.glob('C:\Users\renkr\Downloads\cga_bench\data_release\v5.0\episodes\oss120b\*.json')
files = [f for f in files if 'summary' not in f and 'checkpoint' not in f][:1]
if files:
    d = json.load(open(files[0]))
    print('keys:', list(d.keys())[:15])
    print('actions count:', len(d.get('actions', [])) if 'actions' in d else 'N/A')
    print('states count:', len(d.get('states', [])) if 'states' in d else 'N/A')
    print('first action:', d.get('actions', [{}])[0] if d.get('actions') else 'no actions')
" 2>&1 | head -20
권고: T3 (아래) 를 실행하는 과정에서 최소 1 model × 706 scenarios (≈2,118 episodes) 만이라도 v1.1 ViolationExtractor 를 통과시켜 0 crash 확인. 1시간 작업.
T3. ★ 3,584 episodes 위 light v1.1 dry-run — quantitative content 확보 가능
P7 는 touch presence only. 그러나 stored episode logs 가 있다면 그 3,584 episode 위에서만 다음을 실행 가능:

CDE 로 derived_constraints 생성
Stored agent actions + states 로 ViolationExtractor (with derived) 호출
새 violation 수, CONFLICT/OMISSION/COMMISSION 분리 카운트

이는 Phase A 706 full re-score 보다 훨씬 가벼움 — 16,944 → 3,584 만 처리 (21%). 시간: 1-2h.
산출 가능한 macros:

\conflictDryRunN{X} — 3,584 중 v1.1 mode 에서 실제 새 violation surface 한 episode 수
\conflictDryRunPct{Y} — X / 3,584 비율
\conflictDryRunCorpusPct{Z} — X / 16,944 (전체 대비)

이 세 macro 가 paper App.~Z.4 의 "qualitative-only" caveat 를 부분적으로 quantitative 로 격상 가능. Reviewer 의 "what's the actual impact?" 공격에 "X (Y% of touch, Z% of corpus) episodes flipped, full 706 re-score deferred" 답변 가능.
bash# 가능성 빠른 sanity check — 1 episode 위에서 v1.1 path 작동 확인
python -c "
from cga_bench.cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
from cga_bench.assessor_core.violations import ViolationExtractor, ViolationExtractorConfig
# 실제 episode 1개로 dry-run pipeline test
# ... (구현 시 detail 필요)
print('Pipeline test placeholder')
" 2>&1
비용/효과 평가:

비용: 1-2h
효과: paper 의 핵심 weakness (\strictFAThreeFixed = 6.6 = 6.6 의 공허) 부분 보완. 더이상 "qualitative only" 가 아닌 "quantitative on a 21% subset" 가 됨.

권고: deadline 까지 시간 허락 시 반드시 실행. 가장 가성비 높음.
T4. Untracked files commit-risk — 9개
?? appendix_v18.tex 가 untracked. 모든 C1-C4 교정이 이 파일에 들어있음. submission bundle 만들 때 git add 누락 시 paper 가 v1.0 텍스트로 제출.
bash# 즉시 stage (안전한 항목들만)
cd C:\Users\renkr\Downloads\cga_bench && git add \
  paper/appendix_v18.tex \
  paper/auto_numbers.tex \
  scripts/ci/audit_action_normalizer.py \
  scripts/ci/audit_graph_validity.py \
  scripts/ci/audit_conflict_presence.py \
  tests/test_engine/test_graph_validator.py \
  tests/test_assessor/test_cde_gap_coverage.py \
  evidence_pack/analysis/normalizer_audit.json \
  evidence_pack/analysis/graph_validity_audit.json \
  evidence_pack/analysis/conflict_presence_audit.json

# 확인
git -C C:\Users\renkr\Downloads\cga_bench status --short 2>/dev/null
권고: 지금 stage 만 해두기 (commit 은 별도). 그러면 다음 commit cycle 에서 자동 포함.

TIER-2 (defense 강화)
T5. audit_conflict_presence.py substring matching 인플레이션 가능성
L85: aid_norm in conflict_normalized or any(ca in aid_norm for ca in conflict_normalized). 두 번째 조건 (any(ca in aid_norm)) 은 substring containment.
위험 예시: conflict-prone action give_anticoagulation 이 agent action consider_anticoagulation_after_imaging 의 substring → match 카운트 됨. 그러나 이는 논의 행위 일 뿐 수행 아닐 수 있음. Inflation 가능성.
bashgrep -A 3 "_normalize_for_matching\|conflict_normalized" C:\Users\renkr\Downloads\cga_bench\scripts\ci\audit_conflict_presence.py 2>/dev/null | head -30

# Substring match 가 strict prefix/exact match 와 얼마나 차이 나는지 빠른 비교
python -c "
import json, sys
sys.path.insert(0, '/sessions/eager-awesome-lovelace/mnt/cga_bench')
# Strict variant counter — 시간 허락하면 audit_conflict_presence.py 의 strict 버전 만들기
"
권고: substring 매칭이 진짜 필요한지 audit 하고 (정규화로 prefix 충분할 수도) → strict match 만으로 재계산 한 비교 수치 보고. "Substring matching contributes ≤X% inflation to the 21.2% upper bound" 식 footnote 추가.
T6. Per-model conflict-touch — 첫 보고서 vs 교정 보고서 수치 자체가 다름
원 보고서: deepseek_r1_7b ~16%
교정 보고서 §6.1: deepseek_r1_7b 23.2%
같은 분석에서 7pp 차이. 원인:

(a) 원 보고서는 예상치 / 외부 인용 이고 실제는 23.2 (정확)
(b) model_summary.json 필터 적용 전후 차이? — 그러나 16,952→16,944 만 -8 episodes 변화로는 23pp swing 설명 불가
(c) 다른 분석 결과를 잘못 인용?

bashpython -c "
import json
d = json.load(open('C:\Users\renkr\Downloads\cga_bench\evidence_pack\analysis\conflict_presence_audit.json'))
per_model = d.get('per_model', d.get('by_model', d))
# 출력 형식 확인
print(json.dumps(per_model, indent=2)[:2000])
" 2>&1 | head -40
권고: 원 보고서의 "~16%" 가 어디서 나왔는지 trace. 만약 원 보고서가 그냥 추정 이었으면 신뢰성 문제 — 다른 quantitative claim 들도 의심 필요.
T7. size → aggression 해석 invalidation (H4 보강)
H4 verify 결과 paper 미포함이라 안전. 그러나 내부 분석 narrative 에서 다음이 invalidated:

deepseek_r1_7b (7B param) — 23.2% touch
gemma31b (3B?) — 19.0%
qwen4b (4B) — 14.5%
nemotron30b (30B?) — 14.9%

7B 가 30B 보다 더 높음 — "larger models more aggressive" 단순 가설 fail.
권고: 다음 보고서 / 메모에서 "action-rate variation reflects training-data and prompt-sensitivity differences rather than monotonic capability scaling" 식 evenhanded framing.
T8. Abstract / §1 hero — \strictFAThree{6.6} caveat 정합성
C1 교정은 App.~Z.4 의 conflict-touch 텍스트 손봤지만, \strictFAThree{6.6%} 의 abstract / §1 hero 인용은 그대로일 가능성. 헤드라인 6.6% 가 v1.0 baseline 임이 abstract 에서 명확한가?
bash# Abstract 의 6.6% 인용 컨텍스트
grep -B 2 -A 3 "6\.6\\\\%\|strictFAThree\|6\.6.*FA\|FA.*6\.6" C:\Users\renkr\Downloads\cga_bench\paper\main_final_v18.tex 2>/dev/null | head -30
권고: 만약 abstract/§1 에 "v1.0; v1.1 patch is in progress, results pending v1.2" hedging 미존재 면 1 줄 추가.

TIER-3 (cosmetic / 후속)
T9. Macro re-grep after C4 corrections — 13/15 actually used 확인
C4 교정에서 \normalizerCanonicalN, \normalizerUnmappedPct, \conflictTouchActionsN 추가 사용 보고. Re-verify:
bashfor m in graphValidatorChecksN graphValidatorTotalN graphValidatorGraphsN \
         graphValidatorErrorsN graphValidatorWarningsN \
         normalizerRawActionsN normalizerCanonicalN normalizerUnmappedN \
         normalizerUnmappedPct normalizerMultiCanonicalN normalizerBlindspotN \
         conflictTouchEpisodes conflictTouchScenarios conflictTouchPct \
         conflictTouchActionsN; do
  count=$(grep -rn "\\\\${m}" C:\Users\renkr\Downloads\cga_bench\paper\main_final_v18.tex C:\Users\renkr\Downloads\cga_bench\paper\appendix_v18.tex 2>/dev/null | wc -l)
  echo "  ${m}: ${count}"
done
13 개 에 ≥1 occurrence, 2 개 (graphValidatorWarningsN, normalizerUnmappedN) 가 0 — 보고서 claim 일치 여부 확인.
T10. Phase B 76,464 episodes 의 conflict-touch 미분석 — 명시?
P7 는 Phase A (16,944) 만. Phase B (76,464 추정) 는 전혀 분석 안 됨. App.~Z 에 "Phase B 76,464 episodes were not subject to conflict-presence audit due to scope; v1.2 will extend" 명시 필요.
bashgrep -n "76464\|Phase B\|\\\\phaseBEpisodes" C:\Users\renkr\Downloads\cga_bench\paper\appendix_v18.tex 2>/dev/null | head
T11. Compile 시 font shape warning 의미 — submission 영향?
pdflatex 통과 (font shape warning만, undefined 없음)
font shape warning 은 LaTeX engine 의 사소한 디스플레이 경고. NeurIPS 양식 검사에서 이슈 안 됨. 그러나:
bashcd C:\Users\renkr\Downloads\cga_bench\paper && pdflatex -interaction=nonstopmode main_final_v18.tex 2>&1 | grep -i "warning\|font shape\|Underfull\|Overfull" | head -20
만약 Overfull hbox 가 다수 면 paper 일부 텍스트 margin 초과 — submission 형식 검사 reject 위험.
T12. auto_numbers.tex vs auto_numbers_v2.tex — input 정확성
Plan 18 은 auto_numbers_v2.tex 에 macros 추가 권고. 이번 교정은 auto_numbers.tex (canonical) 에 추가. 정합성은 OK이나 둘 다 paper 에 \input 되는지 확인:
bashgrep -n "input.*auto_numbers" C:\Users\renkr\Downloads\cga_bench\paper\main_final_v18.tex 2>/dev/null
grep -rn "auto_numbers_v2" /sessions/eager-awesome-lovelace/mnt/cga_bench/paper/ 2>/dev/null | head
만약 v18 paper 가 auto_numbers_v2.tex 만 \input 한다면 — 이번 교정 macros 가 paper 컴파일 시 미적용. 이건 CRITICAL 이지만 컴파일 통과했으니 적어도 errors=0; 그러나 어떤 macros 가 누구를 통해 들어가는지 한 번 확인.

우선 실행 sequence
1. T1 (footnote 11→10 정정)         — 5분; 가장 빠른 정확성 fix
2. T12 (auto_numbers input 경로)    — 3분; macro 적용 경로 확정
3. T4 (untracked stage)              — 2분; 잃지 않게
4. T2 (v1.1 path real-data sanity)   — 30분; 1 model 1 scenario 만 dry-run
5. T3 (★ light v1.1 dry-run on 3,584) — 1-2h; quantitative content 확보
6. T5 (substring inflation check)    — 30분; strict-match counter
7. T8 (abstract caveat 정합성)       — 5분; grep + 1 줄 hedging
8. T9 (macro re-grep)                — 2분; remediation claim 검증
9. T10 (Phase B 미분석 명시)         — 5분; appendix 1 줄