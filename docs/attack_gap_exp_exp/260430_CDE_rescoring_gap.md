CRITICAL (제출 전 반드시 확인)
C1. \strictFAThreeFixed = 6.6 (legacy 동일) — paper 핵심 청구의 공허화 위험
latex\providecommand{\strictFAThreePre}{6.6}
\providecommand{\strictFAThreeFixed}{6.6}
§6 reframe paragraph 가 "the framework surfaces its own catalogue gaps" 청구하고, App.~Z.4 가 pre vs post 표를 보여주는데 숫자가 동일 하면 reviewer 는 "what did the patch actually achieve?" 묻습니다. "qualitative-only v1.1 demo" 라는 caveat 가 충분히 surface 안 되면 "misleading" 공격 받음.
확인 사항:

§6 paragraph 본문에 "v1.1 demonstrates conflict-surfacing capability; full numerical re-evaluation on the 706-scenario corpus is deferred to v1.2 due to episode-log artefact availability" 가 명시적으로 들어갔는지
App.~Z.4 표가 "this v1.1 patch has no numerical effect on \strictFAThree because re-scoring depends on stored episode logs which are not reproducible at this revision" 캐비엇을 반드시 포함하는지
abstract 의 6.6% 옆에 (v1.0 baseline; v1.1 patch deferred) 같은 문구 추가 검토

bash# Verify §6 + App.~Z 의 caveat 문구
grep -n "qualitative\|deferred\|episode.log\|v1\.2" C:\Users\renkr\Downloads\cga_bench\paper\main_final_v18.tex C:\Users\renkr\Downloads\cga_bench\paper\appendix_v18.tex 2>/dev/null

# Abstract 와 App.~Z 의 \strictFAThree 인용 일관성
grep -n "strictFAThree\|6\.6" C:\Users\renkr\Downloads\cga_bench\paper\main_final_v18.tex
C2. Tier-A = 0 — heuristic over-classification 가능성
22 graph × 평균 5+ conditional_rules 인데 single negation-pair 도 안 발견됐다는 건 통계적으로 의심스럽습니다. 가능성 두 가지:

(a) 진짜 0 — graph 작성자들이 negation-style 안 씀
(b) audit script 의 condition co-satisfiability 분석이 너무 엄격 해서 negation pair 를 Tier-B 로 잘못 흘림

확인 사항 (audit script 내부 검사):
bash# Audit script 가 condition 비교를 어떻게 하는지
grep -n "co.satisfiable\|negation\|disjoint\|Tier" C:\Users\renkr\Downloads\cga_bench\scripts\ci\audit_cde_rule_conflicts.py

# 알려진 negation pair 가 detect 되는지 검증 — 예시:
# PE-PREGNANCY-NO-WARFARIN (FORBID warfarin if pregnant) vs 가상 PE-NON-PREGNANCY-WARFARIN (REQ warfarin if not pregnant)
# 또는 acls_cardiac_arrest 의 hypothermia (T<30) vs 정상체온 정맥주사 분기

# 실제 11 patterns 의 condition 들을 표시
python -c "import json; d=json.load(open('C:\Users\renkr\Downloads\cga_bench\evidence_pack\cde_conflict_audit_v1.json')); [print(c.get('graph'), c.get('node'), c.get('action'), '|REQ:', c.get('required_sources'), '|FORB:', c.get('forbidden_sources')) for c in d.get('conflicts', d if isinstance(d, list) else [])]"
특히 SCN-012 의 원본 결함 — PE-MASSIVE-THROMBOLYSIS (REQ) ∩ PE-RECENT-SURGERY-NO-THROMBOLYSIS (FORB) — 이 Tier-C 로 잘 분류되었지만, 동일 graph 의 다른 thrombolysis 금기 들 (PE-ACTIVE-BLEED-NO-THROMBOLYSIS, PE-PREGNANCY-IMAGING) 도 같은 패턴인지 확인 필요. 한 audit pattern 이 여러 (REQ, FORB) 쌍을 consolidate 한 거면 카운트 11이 underestimate.
bash# pulmonary_embolism.yaml 의 모든 thrombolysis-action 관련 rules 손으로 매칭
grep -n "give_thrombolysis\|give_alteplase_pe\|give_thrombolytic" C:\Users\renkr\Downloads\cga_bench\cpg_model\graphs\pulmonary_embolism.yaml
C3. dataset drift — 64 pre-existing failures 중 "n_total 16944 vs 19062"
1× test_dxem_degenerate (n_total 16944 vs 19062, dataset version drift)
이건 paper 의 \phaseAEpisodesN{19062} 청구 자체가 흔들리는 신호 입니다. 만약 actual dataset 이 16944 episodes 면 abstract/§4/§5 의 모든 19062 인용이 잘못된 것.
bash# 실제 episode count 검증
find C:\Users\renkr\Downloads\cga_bench -name "*.parquet" -path "*phase_a*" 2>/dev/null | head
find C:\Users\renkr\Downloads\cga_bench\data -name "manifest*" 2>/dev/null

# auto_numbers 의 19062 원천
grep -rn "19062\|16944\|phaseAEpisodesN\|totalEpisodesN" /sessions/eager-awesome-lovelace/mnt/cga_bench/paper/ /sessions/eager-awesome-lovelace/mnt/cga_bench/evidence_pack/ 2>/dev/null | head -20

# 실제 test_dxem_degenerate 가 검증하는 것
grep -A 5 "n_total\|16944\|19062" C:\Users\renkr\Downloads\cga_bench\tests\test_*\test_dxem* 2>/dev/null
이 drift 가 짙을 때, paper 본문 16944 로 정정 또는 데이터 재생성 둘 중 결정해야 함. v1.1 patch 와 무관하지만, 같은 commit 으로 paper 제출한다면 reviewer 가 cross-check 할 때 발견함.

HIGH (제출 전 강하게 권장)
H1. CDE patient context 형식 일치성 — silent skip 빈도
runner.py 의 derived_constraints = None fail-safe 가 얼마나 자주 발동 되는지 모르면 v1.1 patch 가 사실상 비활성 일 수 있음:
pythonif self.config.enable_cde_rescoring and patient_context_for_cde is not None:
    try:
        ...
    except Exception as exc:
        derived_constraints = None  # fail-safe to legacy
확인 사항:

patient_context_for_cde 가 어떻게 생성되는가? (scenario_loader 인가, 별도 추출인가)
CDE 가 기대하는 dict shape (patient.labs.potassium, patient.vitals.sbp, patient.comorbidities, patient.history, patient.weight_kg) 가 706 manual scenarios 의 YAML 과 정확히 일치하는가
706 중 몇 개에서 derived_constraints = None 이 되는가

bash# scenario YAML 의 patient field 형식
ls /sessions/eager-awesome-lovelace/mnt/cga_bench/configs/scenarios/ 2>/dev/null | head -5
head -50 C:\Users\renkr\Downloads\cga_bench\configs\scenarios\*.yaml 2>/dev/null | head -100

# patient_context_for_cde 생성 위치
grep -rn "patient_context_for_cde\|scenario\.patient_context" /sessions/eager-awesome-lovelace/mnt/cga_bench/eval_harness/ /sessions/eager-awesome-lovelace/mnt/cga_bench/scenario_engine/ 2>/dev/null

# CDE 가 condition string 평가 시 KeyError 빈도 — test 한 번
python -c "
from cga_bench.cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
e = ConstraintDerivationEngine()
g = load_graph('C:\Users\renkr\Downloads\cga_bench\cpg_model\graphs\pulmonary_embolism.yaml')
# 최소한의 patient
patient = {'vitals': {'sbp': 76}, 'comorbidities': [], 'history': ['recent_surgery_3_weeks'], 'allergies': [], 'weight_kg': 80, 'labs': {}, 'contraindications': [], 'presentation': []}
r = e.derive(g, patient, scenario_id='test_scn012')
print('REQUIRED:', [c.actions for c in r.required])
print('FORBIDDEN:', [c.actions for c in r.forbidden])
print('CONFLICTS:', [c.actions for c in r.conflicts])
print('rules_evaluated:', r.total_rules_evaluated, 'triggered:', r.total_rules_triggered)
" 2>&1 | head -30
이 마지막 명령이 SCN-012 reproduction 의 가장 빠른 sanity check — CONFLICTS: 가 비어있으면 _detect_required_forbidden_conflicts 가 작동 안 하는 것.
H2. C6 sub-construct — compliance_score 통합 공식
보고서 §3.4 "C1-C5 sub-construct 영향 없음 — CONFLICT는 별도 row로 보고" + "신규 sub-construct C6_conflict_avoidance". 모순적입니다. 두 가지 가능성:

(a) C6 는 sub_scores dict 에만 들어가고 compliance_score 공식에는 안 들어감 → CONFLICT violation 의 수치적 영향 이 conflict weight × n_conflicts 의 aggregate_risk 만으로 제한됨
(b) C6 가 compliance_score 평균에 들어감 → 같은 conflict 가 (1) violation count, (2) C6 binary, (3) C2/C3 영향 cancellation 등 multi-counting

확인 사항:
bash# C6 가 compliance_score 공식에 들어가는지
grep -n "C6\|c6_conflict\|compliance_score\|sub_construct" C:\Users\renkr\Downloads\cga_bench\assessor_core\harm_scorer.py | head -30

# CGAScore data class 의 sub_scores 키
grep -n "C1\|C2\|C3\|C4\|C5\|C6\|sub_scores\|sub_score" C:\Users\renkr\Downloads\cga_bench\cpg_model\schemas\base.py
grep -rn "C6\|c6_" /sessions/eager-awesome-lovelace/mnt/cga_bench/paper/ 2>/dev/null | head
Paper §3.4 (Bayes interpretation) + Table 2 (sub-construct decomposition) 가 C1-C5 만 표기하는데 코드에 C6 가 추가됐다면 paper-code drift. Paper 에 C6 행 추가하든가 코드의 C6 sub_scores 에 안 넣든가 결정 필요.
H3. synthesised episode 가 strict-consensus FA 에 못 들어감 — paper claim 정확성
- 11 synthesised episodes는 strict-consensus FA pipeline 통과 안 함 → \strictFAThreeFixed = 6.6 (legacy 동일, qualitative)
Paper 의 "the v1.1 patch surfaces 11 conflict patterns" 청구는 OK. 그러나 "these 11 patterns translate to N additional false-acceptances" 류 청구는 못 함. App.~Z.3 의 표가 patterns 11 만 보여주고 "FA impact: TBD in v1.2" 라고 써야 함.
확인 사항:
bash# App.~Z.3, Z.4 의 표 본문
grep -A 20 "tab:cde_conflict_audit\|tab:cde_pre_post" C:\Users\renkr\Downloads\cga_bench\paper\appendix_v18.tex 2>/dev/null

# §6 paragraph 의 정확한 청구 문구
grep -B 1 -A 15 "Iterative refinement\|v1\.1 patch\|catalogue gap" C:\Users\renkr\Downloads\cga_bench\paper\main_final_v18.tex 2>/dev/null
H4. Untracked paper edits — commit 누락 위험
Untracked (NOT in commit — pre-existing v18 paper drafts edited but contain massive non-CDE content):
  cga_bench/paper/main_final_v18.tex   (709 lines, my edit: §6 paragraph 1)
  cga_bench/paper/appendix_v18.tex     (2241 lines, my edit: App.~Z 5 subsections)
paper 본체 변경이 git status 상 untracked 또는 unstaged 상태로 남아있다는 의미. Submission bundle 만들 때 누락되면 submitted PDF 가 v1.1 reframe 없이 그대로 가는 사고.
bashcd C:\Users\renkr\Downloads\cga_bench && git status --short paper/ 2>/dev/null

# 변경분 확인 — §6 paragraph 와 App.~Z 가 실제로 들어갔는지
git diff --stat paper/main_final_v18.tex paper/appendix_v18.tex 2>/dev/null

# overleaf zip bundle 갱신 됐는지
ls -la C:\Users\renkr\Downloads\cga_bench\paper\cgabench_overleaf_v18*.zip 2>/dev/null

MEDIUM (시간 허락 시)
M1. CDE _detect_required_forbidden_conflicts — ESC PE 의 다른 contraindication 누락 가능성
PE graph 에는 thrombolysis 관련 4개 금기 rule 이 있습니다:

PE-RECENT-SURGERY-NO-THROMBOLYSIS (FORB give_thrombolysis, give_alteplase_pe)
PE-ACTIVE-BLEED-NO-THROMBOLYSIS (FORB give_thrombolysis, give_alteplase_pe, give_full_dose_anticoagulation)
(그 외 정맥주사 관련)

PE-MASSIVE-THROMBOLYSIS (REQ give_thrombolytic, give_alteplase_pe) 와 4개 금기 가 모두 같은 action 으로 conflict. Audit 의 11 patterns 중 PE 에 몇 개 들어갔는지 확인:
bashpython -c "
import json
d = json.load(open('C:\Users\renkr\Downloads\cga_bench\evidence_pack\cde_conflict_audit_v1.json'))
items = d.get('conflicts', d.get('items', d if isinstance(d, list) else []))
pe = [c for c in items if 'pulmonary' in str(c).lower() or 'pe' in str(c.get('graph', ''))]
print(f'PE patterns: {len(pe)}')
for c in pe: print(' ', c.get('node'), c.get('action'), '|REQ:', len(c.get('required_sources', []) or []), '|FORB:', len(c.get('forbidden_sources', []) or []))
"
만약 PE 에서 1개만 잡혔으면 audit 가 (REQ-action) 별 unique 카운트 — pair 별 카운트 면 더 많을 것.
M2. ConflictViolation severity weight 1.5 적정성
pythoncde_conflict_default_weight: float = 1.5
CDE-derived COMMISSION (1.5) 와 같은 가중치. 임상적으로 CONFLICT 가 더 심각 — mandate 와 contraindication 둘 다 정보 손실. 권고 weight: 2.0 (catastrophic information conflict). 결정 필요.
bash# 현재 weight injection 위치
grep -n "violation_type_weights\|conflict_default" C:\Users\renkr\Downloads\cga_bench\assessor_core\harm_scorer.py C:\Users\renkr\Downloads\cga_bench\configs\**\*.yaml 2>/dev/null | head
M3. test 12 개의 간접 coverage gap
Plan 18 Part IV 의 권고는 ~50+ 였으나 실제 12개. 누락된 critical scenario:

M3-a. End-to-end eval_harness 통합 테스트 (enable_cde_rescoring=True 로 SCN-012 풀 채점)
M3-b. CDE patient context 결손 시 graceful degradation
M3-c. Multi-graph (한 scenario 가 여러 CPG 매칭) 시나리오
M3-d. C6 sub-construct 가 compliance_score 에 미치는 영향

bashls C:\Users\renkr\Downloads\cga_bench\tests\test_assessor\test_cde_*.py C:\Users\renkr\Downloads\cga_bench\tests\test_engine\test_cde_*.py 2>/dev/null
wc -l C:\Users\renkr\Downloads\cga_bench\tests\test_assessor\test_cde_*.py C:\Users\renkr\Downloads\cga_bench\tests\test_engine\test_cde_*.py 2>/dev/null
M4. \conflictGraphsN = 9 — Tier-B 9 + Tier-C 2 가 unique 9 graphs 인가?
Tier-B graphs: aabb, acls (×2 patterns), ada, aha_chest_pain, aha_hf (×2), pals, ssc_sepsis = 7 unique.
Tier-C graphs: idsa_meningitis, pulmonary_embolism = 2 unique.
Total unique = 9 graphs. Math checks out. 단, paper 에 "11 patterns spanning 9 graphs" 표기인지 "11 patterns spanning 11 nodes" 표기인지 명확화.

LOW (cosmetic / 후속)
L1. Skill consolidate-memory 호출 검토
이번 세션 작업물이 많아 17, 18 doc + 신규 보고서 + 코드 변경. Cowork memory file 들 정리 가치 있음 — 단 deadline 후.
L2. setup-cowork / 다른 설치 skills — 현 작업과 무관, 무시.
L3. v1.2 episode_log artefact loader
v1.2 (post-deadline, 임상 검토 필요):
- Phase A 706 manual scenarios full re-scoring (episode_log artefact loader 필요)
가능하면 v1.1 deadline 전에 706 중 일부 (high-stake scenarios) 만이라도 episode_log 가 보존되어 있는지 확인 → 일부라도 numerical impact 보고:
bashfind C:\Users\renkr\Downloads\cga_bench\results -name "episode*.json*" -o -name "*.parquet" 2>/dev/null | grep -i "phase_a\|706\|manual" | head
ls /sessions/eager-awesome-lovelace/mnt/cga_bench/results/ 2>/dev/null | head
만약 episode log 보존되어 있으면 v1.2 작업의 일부 를 deadline 전 v1.1 patch v1.1.1 로 끌어올 수 있음 → \strictFAThreeFixed 의 진짜 숫자 확보.

우선 실행 권장 sequence
deadline 시간 대비 영향-비용 비율로:
1. C3 (dataset drift)        — 5분; 19062 vs 16944 사실 확인 → paper-wide impact
2. H4 (untracked paper edits) — 2분; git status + diff 만
3. C1 (qualitative caveat)    — 5분; §6/App.Z/abstract 의 "deferred" 문구 grep
4. H1-마지막 (CDE smoke test) — 3분; 위 python -c 한 줄 SCN-012 reproduction
5. C2 (Tier-A=0 sanity)       — 10분; audit JSON dump + PE 에 몇 개 잡혔는지
6. H2 (C6 in compliance?)     — 5분; harm_scorer.py grep
7. L3 (episode logs 잔존?)    — 5분; results/ 디렉토리 listing
8. H3 (App.Z claims 정확?)    — 5분; appendix grep
9. M1, M2, M3, M4             — 10분 합산; 시간 허락 시
C3, C1, H4, H1-마지막 4개가 제출 무결성에 직결 입니다. 나머지는 defensibility 강화.