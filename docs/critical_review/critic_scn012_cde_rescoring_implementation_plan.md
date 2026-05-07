# 18. SCN-012 CDE-Rescoring Implementation Plan (B-cde-rescoring)

> **Document scope.** 17번 보고서에서 surface된 SCN-012 finding 의 *코드 검증* 결과 발견된 architectural mismatch 와, D1=B + D5=A + D2=B + D4=B 결정에 따라 채택된 *B-cde-rescoring path* 의 implementation plan. **구현 코드는 포함하지 않음** — remote 작업용 spec.
>
> **Trigger.** 사용자 D1=B 채택 후 진행 중 코드 직접 확인 → `cpg_engine/engine.py` runtime 가 `conditional_rules` 를 *전혀 읽지 않음* 발견. 17번 보고서의 1.5일 추정은 conditional_rules 가 wired-in 되어 있다는 가정 위에 만들어진 것이라, 스코프 재평가 후 사용자가 *B-cde-rescoring* 채택 (cpg_engine 런타임 그대로 두고 scoring path 에만 CDE 도입). 이어서 사용자 지시 *"plan만 작성. remote에서 작업"*.
>
> **Author.** Tooling team analysis, 2026-04-30.
> **Status.** Plan only — no code applied. 5/6 deadline 6일 잔여.
> **Predecessor.** [17_scn012_pe_scoring_gap_analysis.md](./17_scn012_pe_scoring_gap_analysis.md) (clinician finding + initial 4-option matrix).

---

## Part I. Critical Architectural Finding (스코프 재평가 근거)

### I.1 두 개의 분리된 engine

| 모듈 | 역할 | `conditional_rules` 평가 | runtime path 사용 |
|---|---|---|---|
| `cpg_engine/engine.py` (`CPGEngine`) | episode loop 의 step-by-step 제약 평가 — `engine.evaluate(state)` | **NO** (정적 `mandatory_actions`/`forbidden_actions` 리스트만) | YES (`eval_harness/runner.py` line 27, 277, 333) |
| `cpg_model/constraint_derivation.py` (`ConstraintDerivationEngine`, CDE) | offline patient generation, audit, CSV export | **YES** (line 256-284 `_process_conditional_rules`) | **NO** (eval_harness/assessor_core 어디서도 import 안 함) |

**확인 방법** (재현 가능):
```bash
grep -rn "ConstraintDerivationEngine\|from.*constraint_derivation" \
  cga_bench/eval_harness/ cga_bench/assessor_core/ cga_bench/cpg_engine/
# → 0 hits. 오직 cpg_model/patient_generator.py + audit/* + tests/*에만.
```

### I.2 결과: 모든 conditional_rules 의 runtime silent-bypass

25개 graph YAML 의 모든 `conditional_rules` 블록 (PE-MASSIVE-THROMBOLYSIS, PE-RECENT-SURGERY-NO-THROMBOLYSIS, PE-HIT-NO-HEPARIN, AHA-STROKE-LATE-WINDOW, SSC-VASOPRESSOR-IF-MAP-LOW, ... 등 *수백 개* 임상 critical rule) 이 **runtime 채점 시 평가되지 않음**.

각 graph 의 conditional_rules 위치 확인:
```bash
grep -ln "conditional_rules:" cga_bench/cpg_model/graphs/*.yaml | wc -l
# → 22 graphs (out of 25; 3개 graph는 정적 lists로만 운영)
```

### I.3 SCN-012 의 진정한 의미

원 보고서 claim: *"REQUIRED-FORBIDDEN conflict resolution 결함이 mandate 를 silent suppress"*.
**실제**: 두 conditional rule 모두 evaluator 에 도달조차 못 함. SCN-012 의 score 1.0 은 *conflict bug* 가 아니라 *conditional_rules unhooked at runtime* 의 직접 결과.

이는 single bug 가 아니라 *systemic gap*: TCC 의 "FA $=$ 0 by construction" 청구는 사실상 *static-list scope* 한정 — conditional rule 이 catch 해야 할 모든 violation 은 현재 runtime 에서 missed.

### I.4 CDE 자체의 추가 silent-filter

CDE 도 완벽하지 않음 — `_process_expected_actions` line 333:
```python
# Collect mandatory_actions as expected
for action in node.get("mandatory_actions", []):
    if action not in seen_actions and action not in all_forbidden:  # ← silent drop
        seen_actions.add(action)
        result.add(...EXPECTED...)
```

같은 action 이 mandatory + forbidden 둘 다 있으면 EXPECTED 에서 silently 제외, conflict 으로 surface 안 함. Runtime 에 CDE 도입 시 이 filter 도 보정 필요.

### I.5 17번 보고서와의 차이

| 항목 | 17번 추정 | 실제 (코드 확인 후) |
|---|---|---|
| 결함 위치 | engine 의 conflict-resolution logic | CDE 가 runtime 에 wired-in 안 됨 + CDE 자체에도 silent filter |
| 영향 범위 | 일부 PE scenarios | 22개 graph × 모든 conditional_rules — 잠재적으로 수백 개 rule |
| 수정 작업 | engine 에 CONFLICT type 추가 + PE.yaml 보강 | scoring path 에 CDE 도입 + conflict surfacing + CDE filter 보정 |
| 1.5일 추정 | 적절 (좁은 가정) | 부족 — 2일+ |
| Re-scoring 영향 | SCN-012 1건 | 잠재적으로 수십~수백 episode 점수 변화 |

---

## Part II. Chosen Approach: B-cde-rescoring

### II.1 핵심 원칙

1. **Episode loop 불변**: `cpg_engine/engine.py` runtime 동작 그대로 유지. Agent 가 보는 mandatory/forbidden list 변경 없음 → episode trajectory 동일 → existing 19,062 + 76,464 episodes 재실행 불필요.
2. **Scoring path additive 보강**: `assessor_core/violations.py::ViolationExtractor` 가 episode 종료 후 *추가* violation source 로 CDE-derived constraints 를 consume.
3. **Conflict 명시화**: 새 `ViolationType.CONFLICT` 추가 — 같은 action 이 REQUIRED 와 FORBIDDEN 둘 다 hit 인 경우 surface (suppress 아님).
4. **Backward-compat**: `derived_constraints=None` 이면 기존 동작과 byte-identical (regression guard).

### II.2 왜 cpg_engine 보강 (B-runtime-wire) 이 아니라 CDE-rescoring 인가

| 차원 | B-runtime-wire | B-cde-rescoring (선택) |
|---|---|---|
| Code surface | `cpg_engine/engine.py` + `node_types.py` 핵심 로직 변경 | `assessor_core/violations.py` + `eval_harness/runner.py` 후처리만 |
| Episode dynamics 영향 | mandatory list 가 동적으로 늘어남 → agent prompt 도 변경됨 → 모든 episode rerun 필요 (수만 episode) | Episode trajectory 불변, scoring 만 재계산 |
| Regression risk | HIGH — agent behavior, state transitions, deadline timing 모두 영향 | LOW — runtime 불변, scoring 만 추가적 |
| Re-scoring 비용 | 수만 episode rerun (수일 GPU + API 비용) | 706 manual scenarios 만 re-score (분 단위) |
| Paper claim 변경 | "Runtime engine evaluates conditional rules" — 큰 architectural claim | "Scoring engine couples CDE — runtime stays static" — 더 narrow, 정직한 framing |
| 5/6 deadline 적합성 | 빡빡, 위험 | 적합 (2일 작업) |

### II.3 Scope & non-goals

**In scope (5/6 deadline 까지)**:
- `ViolationType.CONFLICT` 추가
- `ViolationExtractor` 가 `derived_constraints` 받기
- CDE 가 `result.conflicts` channel 출력 + `_process_expected_actions` filter 보정
- `eval_harness/runner.py` 가 ConstraintDerivationEngine instantiate 후 ViolationExtractor 에 주입
- 22 graph 의 conditional_rules 중 *명백한 logic error* (e.g., 같은 condition 으로 REQUIRED + FORBIDDEN — 실제로는 OR_REQUIRED 의도) 만 narrow patch
- 706 manual scenarios re-score (legacy vs cde-coupled)
- Paper §6 + App.~Z

**Out of scope (v2.0 deferred — App.~Z 에 명시)**:
- `OR_REQUIRED` operator (formalism extension)
- Auto-transition rules (`state.working_diagnosis` 의존성 제거)
- Episode 전체 re-run 으로 trajectory-level 재평가
- 76,464 Phase B episodes re-score (computational scope 초과)
- `cpg_engine/engine.py` runtime 에 conditional_rules 통합

---

## Part III. Implementation Spec by File

### III.1 `cpg_model/schemas/base.py` (ViolationType 확장)

**현 상태** (KEY-DATA-TYPES.md 기준):
```python
class ViolationType(Enum):
    OMISSION = "omission"
    COMMISSION = "commission"
    TIMING = "timing"
    SEQUENCE = "sequence"
    DEVIATION = "deviation"
```

**수정 후**:
```python
class ViolationType(Enum):
    OMISSION = "omission"
    COMMISSION = "commission"
    TIMING = "timing"
    SEQUENCE = "sequence"
    DEVIATION = "deviation"
    CONFLICT = "conflict"  # NEW: action mandated AND forbidden under simultaneously satisfiable conditions
```

`ViolationEvent` dataclass 의 `violation_type: ViolationType` 필드는 그대로. 추가 fields 도입 (optional):
```python
@dataclass
class ViolationEvent:
    # ... 기존 fields ...
    conflict_provenance: list[str] | None = None  # NEW: e.g. ["graph:pulmonary_embolism:node:initial_assessment:rule:PE-MASSIVE-THROMBOLYSIS",
                                                  #         "graph:pulmonary_embolism:node:initial_assessment:rule:PE-RECENT-SURGERY-NO-THROMBOLYSIS"]
```

### III.2 `cpg_model/constraint_derivation.py` (CDE filter 보정 + conflicts channel)

**변경 1**: `DerivedConstraintSet` 에 `conflicts` channel 추가:
```python
@dataclass
class DerivedConstraintSet:
    # ... 기존 fields ...
    conflicts: list[DerivedConstraint] = field(default_factory=list)  # NEW
```

**변경 2**: `_process_expected_actions` line 333 의 silent filter 보정:
```python
for action in node.get("mandatory_actions", []):
    if action in all_forbidden:  # NEW: surface as conflict
        # Find which forbidden constraint(s) match
        matching_forbidden = [c for c in result.forbidden if action in c.actions]
        for fc in matching_forbidden:
            result.conflicts.append(DerivedConstraint(
                constraint_type="CONFLICT",
                actions=[action],
                provenance=f"graph:{graph_id}:node:{node_id}:mandatory|{fc.provenance}",
                evidence=f"Mandatory action conflicts with forbidden constraint",
                severity="CRITICAL",
                description=f"{action} mandated by node but forbidden by {fc.provenance}",
                condition_met=fc.condition_met,
                is_conditional=fc.is_conditional,
            ))
        continue  # do NOT add to expected — but DO surface
    if action not in seen_actions:
        seen_actions.add(action)
        result.add(...EXPECTED...)  # 기존 로직
```

**변경 3**: REQUIRED + FORBIDDEN 동시 hit 검출 (conditional rules 간):
```python
def _detect_required_forbidden_conflicts(self, result: DerivedConstraintSet) -> None:
    """Surface CONFLICT when same action is both REQUIRED and FORBIDDEN."""
    forbidden_actions_by_provenance = {
        a: c.provenance for c in result.forbidden for a in c.actions
    }
    for req in result.required:
        for action in req.actions:
            if action in forbidden_actions_by_provenance:
                result.conflicts.append(DerivedConstraint(
                    constraint_type="CONFLICT",
                    actions=[action],
                    provenance=f"{req.provenance}|{forbidden_actions_by_provenance[action]}",
                    evidence=f"Required by {req.provenance} and forbidden by {forbidden_actions_by_provenance[action]}",
                    severity="CRITICAL",
                    description=f"{action} is both required and forbidden simultaneously",
                    condition_met=req.condition_met,
                    is_conditional=True,
                ))
```

**변경 4**: `derive()` 마지막에 conflict detection 호출:
```python
def derive(self, graph, patient, scenario_id="") -> DerivedConstraintSet:
    # ... 기존 로직 ...
    self._detect_required_forbidden_conflicts(result)  # NEW
    return result
```

### III.3 `assessor_core/violations.py` (ViolationExtractor 확장)

**변경 1**: `extract_violations` signature 확장:
```python
def extract_violations(
    self,
    episode: EpisodeLog,
    scenario_expected_actions: list[str] | None = None,
    derived_constraints: DerivedConstraintSet | None = None,  # NEW (optional, backward-compat)
) -> list[ViolationEvent]:
```

**변경 2**: 메서드 끝부분 (omission check 후) 에 CDE-based 추가 violation 추출:
```python
# 6. CDE-based supplementary violations (B-cde-rescoring)
if derived_constraints is not None:
    cde_violations = self._extract_cde_violations(
        derived_constraints, performed_actions, episode.states
    )
    violations.extend(cde_violations)
return violations
```

**변경 3**: 신규 helper:
```python
def _extract_cde_violations(
    self,
    dc: DerivedConstraintSet,
    performed_actions: dict[str, ActionRecord],
    states: list[PatientState],
) -> list[ViolationEvent]:
    """Extract violations from CDE-derived constraints not captured by runtime engine.
    
    Strictly additive: emits OMISSION for unmet REQUIRED, COMMISSION for performed FORBIDDEN,
    CONFLICT for required-AND-forbidden actions. Deduplicates against actions already covered
    by runtime-engine-derived violations (caller dedupes via violation_id).
    """
    cde_violations = []
    performed_set = {self._normalize_for_comparison(k) for k in performed_actions.keys()}
    
    # OMISSION: REQUIRED actions not performed
    for req_constraint in dc.required:
        for action_id in req_constraint.actions:
            normalized = self._normalize_for_comparison(action_id)
            if normalized not in performed_set:
                cde_violations.append(ViolationEvent(
                    violation_id=str(uuid.uuid4()),
                    violation_type=ViolationType.OMISSION,
                    action_id=action_id,
                    severity=self._severity_from_cde(req_constraint.severity),
                    timestamp_minutes=states[-1].time_since_arrival_minutes if states else 0.0,
                    source="cde",  # NEW field, optional
                    provenance=req_constraint.provenance,
                    description=f"CDE-derived REQUIRED action not performed: {action_id} ({req_constraint.description})",
                ))
    
    # COMMISSION: FORBIDDEN actions performed
    for forb_constraint in dc.forbidden:
        for action_id in forb_constraint.actions:
            normalized = self._normalize_for_comparison(action_id)
            if normalized in performed_set:
                cde_violations.append(ViolationEvent(
                    violation_id=str(uuid.uuid4()),
                    violation_type=ViolationType.COMMISSION,
                    action_id=action_id,
                    severity=self._severity_from_cde(forb_constraint.severity),
                    timestamp_minutes=performed_actions.get(normalized).timestamp if normalized in performed_actions else 0.0,
                    source="cde",
                    provenance=forb_constraint.provenance,
                    description=f"CDE-derived FORBIDDEN action performed: {action_id} ({forb_constraint.description})",
                ))
    
    # CONFLICT: from result.conflicts channel
    for conf_constraint in dc.conflicts:
        for action_id in conf_constraint.actions:
            cde_violations.append(ViolationEvent(
                violation_id=str(uuid.uuid4()),
                violation_type=ViolationType.CONFLICT,
                action_id=action_id,
                severity=HarmSeverity.MAJOR,  # default; configurable
                timestamp_minutes=0.0,
                source="cde",
                provenance=conf_constraint.provenance,
                conflict_provenance=conf_constraint.provenance.split("|"),
                description=f"Conflicting CPG constraints: {conf_constraint.description}",
            ))
    
    return cde_violations
```

**변경 4**: dedup logic — runtime engine 이 이미 catch 한 violation 과 CDE-derived 가 중복될 수 있음:
```python
# Before extending violations with cde_violations:
existing_keys = {(v.action_id, v.violation_type) for v in violations}
deduped_cde = [v for v in cde_violations 
               if (v.action_id, v.violation_type) not in existing_keys]
violations.extend(deduped_cde)
```

### III.4 `eval_harness/runner.py` (CDE instantiation + injection)

현 상태 (line 27, 277):
```python
from cga_bench.cpg_engine.engine import CPGEngineFactory
# ...
engine = CPGEngineFactory.load_from_file(guideline_graph_path)
```

추가:
```python
from cga_bench.cpg_model.constraint_derivation import (
    ConstraintDerivationEngine, load_graph
)

# Per-scenario:
cde_engine = ConstraintDerivationEngine()
graph_dict = load_graph(guideline_graph_path)
patient_dict = scenario.patient_context  # serialize to dict if dataclass

derived_set = cde_engine.derive(graph_dict, patient_dict, scenario_id=scenario.scenario_id)

# When calling ViolationExtractor:
violations = violation_extractor.extract_violations(
    episode_log,
    scenario_expected_actions=scenario.expected_actions,
    derived_constraints=derived_set,  # NEW
)
```

**중요**: feature flag 도입 — `ExperimentConfig.enable_cde_rescoring: bool = True`. False 면 기존 path (regression baseline 용도).

### III.5 `cpg_model/schemas/base.py` (DerivedConstraint forward import)

`DerivedConstraint` 와 `DerivedConstraintSet` 은 현재 `cpg_model/constraint_derivation.py` 에 정의되어 있고 `cpg_model/schemas/base.py` 에는 없음. ViolationExtractor 가 import 하려면 circular import 주의.

**해결**: `assessor_core/violations.py` 에서 lazy import — TYPE_CHECKING 블록 안에 import 추가, runtime 에는 string forward ref 사용.

### III.6 `assessor_core/harm_scorer.py` (CONFLICT severity weight)

`HarmScorerConfig.violation_type_weights` 에 `"CONFLICT": 1.5` 등 가중치 추가. 외부 주입 원칙 유지.

`ViolationType.CONFLICT` 가 sub-construct C1-C5 어디에 매핑되는지 명시:
- C1 path selection? — 기각 (path 외 conflict 자체)
- 새 sub-construct C6 으로 도입? — paper §3 변경 큼
- 기존 C3 (forbidden_avoidance) + C2 (mandatory_completion) 에 동시 영향? — 가장 honest

권고: CONFLICT 는 *별도 violation row* 로 보고 (sum 에 포함), C2/C3 영향 중복 카운트 안 함. App.~Z 에 명시.

---

## Part IV. Test Strategy (T2)

### IV.1 Regression Guards (CRITICAL)

```python
# tests/test_assessor/test_cde_rescoring_regression.py

def test_violation_extractor_backward_compat_with_none(...):
    """derived_constraints=None 일 때 기존 동작과 byte-identical."""
    # 기존 fixture 모두 돌려서 violations 결과 동일성 확인
    
def test_existing_3185_tests_pass_unchanged(...):
    """기존 전체 test suite 통과."""
    # CI 에서 PYTHONPATH=. pytest tests/ -v 통과
```

### IV.2 SCN-012 fixture (구체 reproduce)

```python
def test_scn012_pre_patch_score_one(...):
    """legacy mode (derived_constraints=None) 에서 SCN-012 가 1.0 점."""
    
def test_scn012_post_patch_score_drops(...):
    """cde-coupled mode 에서 SCN-012 가 < 1.0, 최소 2 violations.
    Expected:
      - OMISSION on give_thrombolytic (REQUIRED by PE-MASSIVE-THROMBOLYSIS)
      - CONFLICT on give_alteplase_pe (REQUIRED + FORBIDDEN)
    """
```

### IV.3 CDE-only unit tests

```python
def test_cde_required_forbidden_conflict_surfacing(...):
    """REQUIRED + FORBIDDEN on same action → result.conflicts populated."""

def test_cde_mandatory_static_vs_forbidden_conditional(...):
    """static mandatory_actions list 의 action 이 conditional FORBIDDEN 으로 가려질 때 surface."""

def test_cde_no_conflict_when_unrelated(...):
    """REQUIRED 와 FORBIDDEN 이 서로 다른 action 이면 conflict 없음 (regression guard)."""

def test_cde_idempotent(...):
    """같은 patient + graph 로 두 번 derive() → 동일 결과."""
```

### IV.4 Integration

```python
def test_eval_harness_with_cde_enabled_full_loop(...):
    """SCN-012 scenario eval_harness → score < 1.0."""

def test_eval_harness_disable_cde_baseline(...):
    """enable_cde_rescoring=False → 기존 점수 동일."""
```

### IV.5 Property tests (선택)

- `additivity`: CDE-coupled 모드의 violation 수 ≥ legacy 모드 (모든 episode 에서, no exception). 위반 시 regression bug.
- `conflict_symmetry`: REQUIRED-only 와 FORBIDDEN-only 단독은 CONFLICT 안 나옴.

---

## Part V. Audit Script Spec (T3)

### V.1 목적

25 graph YAML 의 모든 conditional_rules 를 정적 분석 → REQUIRED-FORBIDDEN conflict pattern 카운트. Tier 분류:
- **Tier-A**: Engine fix (T1) 만으로 자동 해결 (CDE conflict surfacing → ConflictViolation 으로 보고)
- **Tier-B**: YAML 자체에 logic error 가 의심됨 — 실제 임상 의도가 OR_REQUIRED 인데 두 rule 로 풀어 쓴 케이스. Graph 수정 권고.
- **Tier-C**: Genuine OR_REQUIRED 의미 — formalism extension 필요. v2.0 deferred.

### V.2 구현 스케치

```python
# scripts/ci/audit_cde_rule_conflicts.py
import yaml
from pathlib import Path
from collections import defaultdict

GRAPH_DIR = Path("cpg_model/graphs")

def load_graphs():
    return {p.stem: yaml.safe_load(p.read_text()) 
            for p in GRAPH_DIR.glob("*.yaml") if "_archive" not in str(p)}

def detect_conflicts_in_node(graph_id, node_id, node):
    """For one node, find action_ids that appear under both REQUIRED and FORBIDDEN
    via conditional_rules (or static + conditional combination)."""
    required_by_action = defaultdict(list)
    forbidden_by_action = defaultdict(list)
    
    # Static lists
    for action in node.get("mandatory_actions", []):
        required_by_action[action].append(("static_mandatory", node_id))
    for action in node.get("forbidden_actions", []):
        forbidden_by_action[action].append(("static_forbidden", node_id))
    
    # Conditional rules
    for rule in node.get("conditional_rules", []):
        rule_id = rule.get("rule_id", "unknown")
        condition = rule.get("condition", "")
        effect = rule.get("effect", {})
        effect_type = effect.get("type", "")
        for action in effect.get("actions", []):
            if effect_type == "REQUIRED":
                required_by_action[action].append((rule_id, condition))
            elif effect_type == "FORBIDDEN":
                forbidden_by_action[action].append((rule_id, condition))
    
    conflicts = []
    for action in set(required_by_action) & set(forbidden_by_action):
        conflicts.append({
            "graph": graph_id,
            "node": node_id,
            "action": action,
            "required_sources": required_by_action[action],
            "forbidden_sources": forbidden_by_action[action],
            "tier": classify_tier(required_by_action[action], forbidden_by_action[action]),
        })
    return conflicts

def classify_tier(req_sources, forb_sources):
    """A=mechanical (engine fix solves), B=YAML logic error, C=needs OR_REQUIRED."""
    # Heuristic:
    # - If REQUIRED is unconditional but FORBIDDEN is conditional → Tier-B (graph patch)
    # - If both are conditional with disjoint conditions → Tier-A (CDE rarely fires both)
    # - If both conditional with co-satisfiable conditions → Tier-B or Tier-C
    # Concrete classification rules: see Appendix in this doc.
    pass

def main():
    graphs = load_graphs()
    all_conflicts = []
    for gid, g in graphs.items():
        for nid, node in g.get("nodes", {}).items():
            all_conflicts.extend(detect_conflicts_in_node(gid, nid, node))
    
    # Tier counts
    tier_counts = defaultdict(int)
    for c in all_conflicts:
        tier_counts[c["tier"]] += 1
    
    # Output
    Path("evidence_pack/cde_conflict_audit_v1.json").write_text(json.dumps({
        "conflicts": all_conflicts,
        "tier_counts": dict(tier_counts),
        "total": len(all_conflicts),
    }, indent=2))
    
    # Macros for paper
    macros = {
        "conflictPatternsN": len(all_conflicts),
        "tierAN": tier_counts["A"],
        "tierBN": tier_counts["B"],
        "tierCN": tier_counts["C"],
        "conflictGraphsN": len({c["graph"] for c in all_conflicts}),
    }
    # Append to paper/auto_numbers_v2.tex via macro updater script.
```

### V.3 Tier classification heuristics (구체)

| Pattern | Example (PE) | Tier | 처리 |
|---|---|---|---|
| 두 conditional rule 의 condition 이 *disjoint* | REQUIRED if SBP<90; FORBIDDEN if active_bleeding | A | engine fix 로 충분 |
| Conditional REQUIRED + 다른 conditional FORBIDDEN, conditions 공동 만족 가능 (SCN-012) | REQUIRED if SBP<90; FORBIDDEN if recent_surgery | B (또는 C) | OR_REQUIRED 의도 면 C; YAML 단순 오류 면 B |
| Static mandatory + conditional FORBIDDEN of same action | `mandatory: [give_alteplase_pe]` + FORBIDDEN if recent_surgery | B | YAML 수정 필요 |
| 같은 condition 으로 REQUIRED + FORBIDDEN | (PE 에 없음, audit 가 catch) | B | YAML logic bug |

권고: Tier-B 는 audit 후 *각 case 마다 임상 검토* 필요 — 자동 patch 불가. Tier-A 는 자동, Tier-C 는 v2.0 deferred.

### V.4 예상 결과 (가설, 검증 필요)

PE graph 수동 검토 기준:
- PE-MASSIVE-THROMBOLYSIS (REQ) + PE-RECENT-SURGERY-NO-THROMBOLYSIS (FORB) → SCN-012 (Tier-C: OR_REQUIRED 가 진짜 의도)
- PE-MASSIVE-THROMBOLYSIS (REQ) + PE-ACTIVE-BLEED-NO-THROMBOLYSIS (FORB) → 같은 패턴 (Tier-C)
- PE-MASSIVE-THROMBOLYSIS (REQ) + PE-PREGNANCY-NO-WARFARIN (FORB) → action 다름, conflict 아님

22 graph × 평균 3-5 conditional rule blocks 이면 audit 결과 *50-100 patterns* 예상. 그 중 Tier-B+C 는 *5-15* 추정.

---

## Part VI. Re-scoring Methodology (T5)

### VI.1 Scope

- **In**: 706 manual scenarios (Phase A subset 사용 — 완전한 ground truth + 임상 검토 완료된 set)
- **Out**: 19,062 Phase A 전체 / 76,464 Phase B (compute scope 초과)

### VI.2 Two-mode comparison

```
Mode 1 (legacy): enable_cde_rescoring=False → ViolationExtractor with derived_constraints=None
Mode 2 (cde-coupled): enable_cde_rescoring=True → ViolationExtractor with derived_constraints from CDE
```

**중요**: episode logs 자체는 *재실행 안 함* — 기존 episode_log artifacts 를 두 mode 로 재채점만. 빠르고 비용 낮음.

### VI.3 Diff metrics

```python
# results/scn012_repatch/pre_post_diff.json
{
    "scenario_id": "...",
    "model": "...",
    "run_idx": 1,
    "legacy_cga_score": 1.0,
    "cde_cga_score": 0.42,
    "delta_cga": -0.58,
    "legacy_violations": [...],
    "cde_violations": [...],
    "newly_surfaced": [
        {"type": "OMISSION", "action": "give_thrombolytic", "source": "cde", "rule": "PE-MASSIVE-THROMBOLYSIS"},
        {"type": "CONFLICT", "action": "give_alteplase_pe", "rules": ["PE-MASSIVE-THROMBOLYSIS", "PE-RECENT-SURGERY-NO-THROMBOLYSIS"]},
    ],
}
```

### VI.4 Headline 수치

- `\strictFAThree{}` → `\strictFAThreePre{}` (rename, legacy mode 결과)
- 신규 `\strictFAThreeFixed{}` (post-CDE 결과)
- `\scnTwelveImpactN{}` (개수: post 가 pre 와 다른 episode 수)
- `\conflictViolationN{}` (CONFLICT type violation 총 수, post 모드)

### VI.5 Additivity assertion

```python
for episode in re_scored:
    assert episode.cde_cga_score <= episode.legacy_cga_score, \
        f"REGRESSION: {episode.scenario_id} cde-coupled score {episode.cde_cga_score} > legacy {episode.legacy_cga_score}"
```

만약 이 assertion 이 깨지면 ViolationExtractor 의 dedup logic 에 bug — 같은 violation 을 2번 카운트하거나 violation 을 제거하는 행위.

### VI.6 예상 결과 가설

| 가설 | post 변화 | 의미 |
|---|---|---|
| Optimistic | \strictFAThree 6.6% → \strictFAThreeFixed 7-8% | 1-2 percentage point 변화. abstract/§1 hero 그대로. |
| Realistic | 6.6% → 9-12% | 3-5 percentage point. abstract reword 필요. |
| Pessimistic | 6.6% → 15-20% | Major rewrite. § Limitations 에 disclosure. |

**중요**: 어느 결과든 transparently 보고 — hide 옵션 없음. App.~Z 에 pre vs post 표 명시.

---

## Part VII. Paper Integration Spec

### VII.1 §6 Limitations addition (D2=B reframe)

새 paragraph (≤8줄, after existing limitations):

```latex
\paragraph{Iterative refinement under expert review.}
Clinician validation surfaced one scenario where the runtime engine, by
construction, only evaluated static mandatory/forbidden lists and not
the conditional rules attached to each node. We address this by coupling
the Constraint Derivation Engine (\S\ref{sec:cde}) into the scoring path
(App.~\ref{app:conflict_patch}): episode trajectories are unchanged, but
violation extraction now consumes both engine-derived and CDE-derived
constraints, and surfaces \emph{conflict} violations when an action is
simultaneously required and forbidden under co-satisfiable conditions.
This patch (v1.1) demonstrates the operational value of audit-not-validation
framing — the framework surfaces its own catalogue gaps under expert review.
Pre/post-patch headline numbers (\strictFAThreePre{} vs \strictFAThreeFixed{})
are reported transparently in App.~\ref{app:conflict_patch}.
```

### VII.2 App.~Z spec ("Conflict-Resolution Logic Patch v1.1")

위치: `paper/appendix.tex`, label `app:conflict_patch`. Length ~1.5-2 pages.

**Z.1 Anonymized case** (~0.3 page):
```
A massive PE scenario with relative-contraindication overlap (recent surgery
within 3 weeks; SBP < 90; SpO2 < 80%) revealed that conditional rules
declaring thrombolysis as REQUIRED (ESC 2019 Class I, hemodynamic instability)
and as FORBIDDEN (relative contraindication) were both active at the same
runtime step, yet the runtime engine — which evaluates only static
mandatory/forbidden lists — saw neither. The agent took 12 actions including
no thrombolysis, no embolectomy, and no anticoagulation, and the legacy
scorer assigned a CGA score of 1.0. (Anonymous; full case description withheld
to focus on the systemic finding.)
```

**Z.2 Resolver pseudocode (old vs new)** (~0.3 page):

```python
# Old (cpg_engine/engine.py runtime)
def evaluate(state):
    return GuidelineEngineOutput(
        mandatory=set(node.mandatory_actions),  # static
        forbidden=set(node.forbidden_actions),  # static
        # conditional_rules: NOT EVALUATED
    )

# New (assessor_core/violations.py + CDE coupling)
def extract_violations(episode, derived_constraints=None):
    violations = legacy_extract(episode)  # unchanged
    if derived_constraints is not None:
        for req in derived_constraints.required:  # NEW: conditional REQUIRED
            if not_performed(req): emit OMISSION
        for forb in derived_constraints.forbidden:  # NEW: conditional FORBIDDEN
            if performed(forb): emit COMMISSION
        for conf in derived_constraints.conflicts:  # NEW: REQUIRED ∩ FORBIDDEN
            emit CONFLICT
    return violations
```

**Z.3 Audit table** (~0.5 page):

```
Table Z.1: Conditional-rule conflict patterns across 25 CPGs (v1.1)

Tier  Description                             Patterns  Graphs  Status
A     Engine-fix auto-resolved                {tierAN}  {a_g}   patched (v1.1)
B     YAML logic error / ambiguous intent     {tierBN}  {b_g}   patched (v1.1, manual)
C     Genuine OR_REQUIRED semantics            {tierCN}  {c_g}   deferred (v2.0)
─────────────────────────────────────────────────────────────────────────
Total                                          {N}       {tg}
```

**Z.4 Pre vs post-patch numbers** (~0.4 page):

```
Table Z.2: Headline metric changes after v1.1 patch

Metric                         Pre (v1.0)        Post (v1.1)        Δ
Strict-consensus FA            \strictFAThreePre  \strictFAThreeFixed  +X%
CONFLICT violations (count)    0 (not surfaced)  \conflictViolationN
Mean CGA (706 manual)          \meanCgaPre       \meanCgaPost         -Y
Episodes affected              0                 \scnTwelveImpactN

All deltas are non-negative on per-episode CGA (additivity guarantee:
re-scoring with CDE coupling can only surface more violations, never fewer).
```

**Z.5 v2.0 roadmap** (~0.3 page):

```
Limitations and v2.0 work:
1. OR_REQUIRED operator: Tier-C conflicts (e.g., massive-PE thrombolysis
   contraindicated → embolectomy required) reflect genuine clinical OR-semantics
   that current formalism (typed FORBID/MUST/BEFORE/WITHIN) cannot express
   directly. v2.0 will extend §3 typed-constraints with OR_REQUIRED.
2. Auto-transition: time-critical nodes (massive_pe, septic_shock, cardiac_arrest,
   acute_stroke) currently require agent-set state.working_diagnosis to activate.
   v2.0 will add objective-trigger auto-transitions.
3. Runtime conditional_rules: this patch couples CDE into scoring only; the
   runtime engine still evaluates static lists. Wiring conditional_rules into
   runtime would change agent-visible mandatory/forbidden lists per step,
   requiring full episode re-runs (76,464+ episodes); deferred to v2.0.
```

### VII.3 Macros to add (T6)

`paper/auto_numbers_v2.tex`:
```latex
% SCN-012 patch v1.1 numerics
\providecommand{\strictFAThreePre}{6.6}
\providecommand{\strictFAThreeFixed}{TBD}  % populate from results/scn012_repatch
\providecommand{\conflictPatternsN}{TBD}
\providecommand{\tierAN}{TBD}
\providecommand{\tierBN}{TBD}
\providecommand{\tierCN}{TBD}
\providecommand{\conflictGraphsN}{TBD}
\providecommand{\conflictViolationN}{TBD}
\providecommand{\scnTwelveImpactN}{TBD}
\providecommand{\meanCgaPre}{TBD}
\providecommand{\meanCgaPost}{TBD}
```

기존 `\strictFAThree{}` 가 다른 곳에서 사용된다면 search-replace 로 일관되게 `\strictFAThreePre` 또는 본문 맥락에 맞게 분기.

### VII.4 §3 (Constraint Derivation Engine) 약간의 보강

§3.x 의 CDE 설명 paragraph 에 *"runtime scoring couples CDE for conflict-aware violation extraction (v1.1)"* 한 줄 추가. 큰 narrative 변경 아님.

### VII.5 Figure 3 (CDE worked example) 영향

`paper/figures/figure3.tex` 의 caption 변경 불필요 — Theorem 3.4 Case 4 에서 same-action conflict 가 surface 된다는 새 사실이 강조점이지만 figure 내용 자체는 유지.

---

## Part VIII. Risk Mitigation

### VIII.1 Regression risk

**Mitigation**: 
1. Feature flag `enable_cde_rescoring=False` default 로 일단 출시 → CI 통과 확인 → flag flip
2. Mode 1 (legacy) 전체 test suite 통과 확인 후 Mode 2 enable
3. Per-episode additivity assertion (post ≥ pre violation count, post ≤ pre CGA)

### VIII.2 Numbers swing risk

post-patch \strictFAThreeFixed 가 12%+ 면 abstract/§1 reword 필요.

**Mitigation**:
1. 706 re-score 가 가장 빠른 단계 (분 단위) — 일찌감치 실행해서 magnitude 파악
2. 결과에 따라 abstract 의 *"6.6% strict consensus FA"* 를 *"approximately X% under full CDE coupling (v1.1)"* 로 변경
3. 변경이 크면 §1 hero claim 도 *"projection-induced under-detection"* 의 quantitative magnitude 를 Tier-A/B/C breakdown 으로 보고

### VIII.3 Time risk (5/6 deadline)

| Day | Work | Deliverable |
|---|---|---|
| Day 1 AM | Audit script (T3) + macros | `cde_conflict_audit_v1.json`, tier counts |
| Day 1 PM | T4.5 triage decision (Tier-B count 보고 user 협의) | Tier-B patch list |
| Day 1 evening | Engine patch (T1) + tests (T2) start | `ViolationExtractor` 확장, 단위 테스트 |
| Day 2 AM | Tests 마무리 + 706 re-score (T5) | `pre_post_diff.json`, 신규 macros |
| Day 2 PM | Tier-B graph patches (T4) + 재 re-score | 최종 \strictFAThreeFixed |
| Day 2 evening | Macros (T6) + §6 (T7) + App.~Z (T8) | paper draft 통합 |
| Day 3 AM | Compile + cross-ref (T9) | clean PDF, leakage scan pass |

총 ~2.5일. 5/6 deadline 6일 잔여라 buffer 충분. 단 Tier-B 가 audit 결과 10개+ 면 user 협의 후 우선순위 선정 (T4.5 gate).

### VIII.4 Reviewer attack vectors & defenses

| Attack | Defense |
|---|---|
| "Why didn't you wire conditional_rules into runtime?" | App.~Z.5: episode re-runs (76,464+) computational scope; v2.0 deferred with explicit roadmap. |
| "How many other graphs have the same bug?" | App.~Z.3 audit table — \conflictPatternsN identified, all triaged. |
| "Show one concrete fix" | App.~Z.1 anonymized case + Z.2 pseudocode diff. |
| "Did the patch change your headline?" | App.~Z.4 pre vs post table — full transparency. |
| "Validation pending in §5.4 contradicts §6 reframe" | §5.4 update: clinician validation 0/60 → 1 finding integrated, framework surfaced gap, framework-self-corrects. |

---

## Part IX. Decision Points (남은 협의 사항)

### IX.1 Tier-B audit count 가 큰 경우 (D5 fallback)

**Question**: T3 audit 결과 Tier-B 가 6개 graph 초과면?

**Default**: T4.5 gate 발동 — 사용자에 알림 → 우선순위 선택 (massive_pe, septic_shock, cardiac_arrest, anaphylaxis, status_epilepticus 우선).

**Alternative**: 모두 Tier-C 로 deferred 처리 → App.~Z.3 에 *"5 graphs patched, N graphs deferred to v2.0 with stated rationale"* 보고.

### IX.2 Post-patch \strictFAThreeFixed 가 큰 경우

**3 percentage point 미만 차이**: abstract 그대로 두고 본문에 *"after v1.1 patch, X%"* 추가만.

**3-7 percentage point**: abstract 수치 update (`6.6\%` → `\strictFAThreeFixed{}`), 본문에 pre/post 둘 다 명시.

**7%+**: §1 hero claim 도 reword. 사용자 협의 필요.

### IX.3 CONFLICT 를 sub-construct 어디에?

권고: 별도 row, C2/C3 영향 중복 카운트 안 함. 사용자 의견 필요 시 협의.

### IX.4 Feature flag default (enable_cde_rescoring)

권고: paper 제출 직전에는 `True` 로 flip → 모든 published numbers 가 v1.1 결과. 코드 base 의 default 도 `True`.

대안: `False` default 유지 → opt-in. paper 에는 *"with --enable-cde-rescoring flag"* 명시. 더 conservative 지만 이상한 선택 — 우리 자신이 v1.1 을 채택하지 않은 것처럼 보임.

---

## Part X. Concrete File Touch List

### X.1 Code changes (실제 수정 필요한 파일)

```
cga_bench/cpg_model/schemas/base.py               # ViolationType.CONFLICT, conflict_provenance field
cga_bench/cpg_model/constraint_derivation.py       # conflicts channel + filter 보정 + _detect_required_forbidden_conflicts
cga_bench/assessor_core/violations.py              # extract_violations signature + _extract_cde_violations
cga_bench/assessor_core/harm_scorer.py             # CONFLICT weight (config-injected)
cga_bench/eval_harness/runner.py                   # CDE instantiation + injection
cga_bench/eval_harness/experiment_config.py        # enable_cde_rescoring flag
```

### X.2 New files

```
scripts/ci/audit_cde_rule_conflicts.py             # T3 audit script
scripts/scn012_repatch/run_re_scoring.py           # T5 re-scoring driver
tests/test_assessor/test_cde_rescoring.py          # T2 main tests
tests/test_assessor/test_cde_rescoring_regression.py  # T2 regression guards
tests/test_engine/test_cde_conflict_surfacing.py   # T2 CDE-only tests
evidence_pack/cde_conflict_audit_v1.json           # T3 output
results/scn012_repatch/pre_post_diff.json          # T5 output
```

### X.3 Paper changes

```
paper/main_final_v18.tex                           # §6 paragraph (Part VII.1)
paper/appendix.tex                                 # App.~Z (Part VII.2)
paper/auto_numbers_v2.tex                          # 신규 macros (Part VII.3)
paper/figures/figure3.tex                          # caption 보강 (선택)
```

### X.4 Graph YAML changes (Tier-B 만)

T3 audit 결과로 결정. 후보 (예측, 확정 아님):
- `pulmonary_embolism.yaml` (SCN-012 case + 유사 patterns)
- `aha_stroke_2019.yaml` (tPA contraindication overlaps)
- `aha_chest_pain_evaluation.yaml` (RV infarct trap)
- `ssc_sepsis_hour1_bundle.yaml` (vasopressor timing)
- `anaphylaxis_management.yaml` (epinephrine routes)

각 패치마다 임상 검토 + audit_sources.py + audit_citations.py 통과 필수.

---

## Part XI. Validation Checklist (작업 완료 시점)

- [ ] **Code**: 모든 file change 가 X.1/X.2 list 와 일치. Diff 가 strictly additive (default behavior unchanged when CDE off).
- [ ] **Tests**: 기존 3185+ tests pass. 신규 50+ tests (regression + CDE + integration) pass.
- [ ] **Audit**: `audit_cde_rule_conflicts.py` 결과 evidence_pack/ 에 저장. Tier-B 모두 patch 됐거나 deferred 명시.
- [ ] **Re-scoring**: 706 manual scenarios 재채점. Per-episode `cde_cga ≤ legacy_cga` 만족 (additivity).
- [ ] **Macros**: auto_numbers_v2.tex 에 \strictFAThreePre/Fixed, \conflictPatternsN, tier counts, \conflictViolationN, \scnTwelveImpactN 모두 채워짐.
- [ ] **Paper compile**: pdflatex twice + bibtex clean. Zero undefined refs. App.~Z 와 §6 cross-ref 작동.
- [ ] **CI**: `audit_sources.py`, `audit_citations.py`, `leakage_scan.py` 통과. Croissant.json 무영향 (데이터 변경 없음).
- [ ] **Disclosure**: §6 reframe paragraph + App.~Z 모든 sub-section 작성. SCN-012 anonymized.
- [ ] **Feature flag**: `enable_cde_rescoring=True` default. opt-out flag 보존 (regression debugging 용).
- [ ] **Bundle**: `cgabench_overleaf_v18.zip` 재생성 — 신규 paper/auto_numbers + appendix 포함.

---

## Part XII. Open Questions for Remote Work Session

1. **Tier-B 우선순위**: audit 후 Tier-B 가 5+ 면 어느 graph 부터?
2. **Macro flip 시점**: feature flag default `True` → 언제? 모든 pipeline 통과 직후 vs paper 제출 직전?
3. **Anonymized case wording**: App.~Z.1 의 정확한 문구. 임상 검토자 (clinician validator) 와 합의 필요할 수도.
4. **Sub-construct mapping**: CONFLICT 를 별도 row 로 (권고) vs C2/C3 동시 카운트?
5. **Phase B 76,464 episode 재채점 하지 않는 것에 대한 정당성**: §6 에 명시 vs App.~Z.5 에만?
6. **\strictFAThree{} 의 모든 본문 occurrences 정리**: search-replace 시 context-aware 분기 필요한 곳들 사전 list-up.

---

## Part XIII. 결론 요약

17번 보고서가 진단한 *engine-level conflict resolution 결함* 보다 *더 깊은 architectural mismatch* — `conditional_rules` 가 runtime 에 wired-in 되지 않음 — 가 root cause. 5/6 deadline 6일 잔여에서 안전한 path 는 **B-cde-rescoring**: episode loop 불변, scoring path 만 CDE 와 coupling. 

이 plan 이 권고하는 작업은 ~2.5일 (audit → triage → patch → re-score → paper). Strictly additive 이므로 regression risk 매우 낮음. Numbers swing 은 magnitude 따라 abstract reword 가능성 있으나 *transparency 가 최선의 reviewer 답변*.

권고 sequence: T3 audit → T4.5 triage gate (사용자 협의) → T1+T2 (engine + tests) → T5 re-score → T4 (Tier-B graph patches) → T6/T7/T8 (paper) → T9 (compile + bundle).

본 plan 은 implementation spec 수준이며, *코드는 포함되지 않음*. Remote session 에서 이 spec 을 따라 실제 변경을 적용하면 됨. 진행 중 Tier-B count 가 예상보다 크거나 \strictFAThreeFixed magnitude 가 ≥7% 이면 user 협의 후 abstract reword 결정.

---

**End of plan.**
