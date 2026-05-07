# Auto-Scenario Generator v4 자체 품질 평가 보고서

> 작성일: 2026-04-29 | 브랜치: eval_science
> 목적: Generator 개선 (Gap 1-3) 후 과잉 설계 여부 정직한 자체 평가

## 1. 3-Way 비교 결과 (Manual-only vs Old-Auto vs Regen v4)

이전 비교에서 "Manual" 컬럼은 수동(107) + 구 자동(601) = 708의 혼합이었음.
수동 시나리오만 분리하면 실제 품질 기준이 달라짐.

| 지표 | Manual (107) | Old Auto (601) | Regen v4 (1067) | 평가 |
|------|-------------|----------------|-----------------|------|
| Chief complaints (고유) | 106 | 15 | 102 | OK - Manual 수준 도달 |
| Vitals diversity | 0.981 | 0.168 | 0.994 | OK - Manual과 동등 |
| Forbidden actions % | **80.4%** | 100.0% | **100.0%** | **WARN - 과잉 주입** |
| Avg FA/시나리오 | **2.2** | 12.7 | **4.9** | **WARN - Manual의 2.2배** |
| Unique diagnoses | 54 | 0 | 77 | OK - 싱글톤 0개 |
| Empty/general dx % | 0.0% | 100.0% | 0.0% | OK - 해결됨 |
| Trap scenarios % | **59.8%** | 84.0% | **39.6%** | INFO - Manual보다 낮음 |
| Ground truth % | 100.0% | 0.0% | 100.0% | OK - Manual과 동일 |
| Avg GT keys | **5.7** | 0 | **5.3** | OK - Manual의 93% |
| Comorbidity % | **83.2%** | 58.6% | **61.0%** | **GAP - Manual 대비 22pp 부족** |
| Unique comorbidities | 82 | 94 | 173 | OK - 풀 자체는 풍부 |
| Allergies % | **5.6%** | 3.0% | **1.0%** | GAP - Manual 대비 부족 |

## 2. 과잉 설계 (Over-Engineering) 진단

### 2.1 Forbidden Actions 100% — 과잉 (WARN)

**현상**: 모든 1067개 시나리오에 forbidden_actions가 강제 주입됨.
Manual은 80.4%만 FA를 가짐 (19.6%는 FA 없음이 자연스러운 시나리오).

**원인**: `_extract_node_forbidden_actions()`가 그래프 전체 노드에서 FA를 수집하여
모든 시나리오에 일괄 적용. 그래프에 FA가 1개라도 있으면 모든 시나리오가 FA를 가짐.

**영향도**: 낮음. FA 있는 것 자체는 해로운 것이 아니며, 평가 시 FA를 수행하지
않으면 violation이 발생하지 않음. 단, 시나리오 리얼리즘 측면에서 약간 인위적.

**수정 필요 여부**: P2 (선택). Phase 3 baseline에서 FA를 제거하거나,
branch scenario에서 확률적으로 FA 포함 여부를 결정하면 80% 수준으로 조정 가능.

### 2.2 시나리오당 평균 FA 4.9 vs Manual 2.2 — 주의 (INFO)

**현상**: 시나리오당 평균 4.9개의 forbidden actions (Manual은 2.2개).
Old Auto의 12.7에 비하면 크게 개선되었으나 여전히 Manual의 2배.

**원인**: 그래프 노드 FA + universal trap FA가 중복 합산됨.
auto 그래프 일부가 노드별로 세분화된 FA 목록을 가짐.

**영향도**: 낮음. FA가 많을수록 평가가 엄격해지지만, 임상적으로
실제 금기 행위가 많은 프로토콜도 있으므로 반드시 과잉은 아님.

### 2.3 Ground Truth 100% — 적절 (OK)

**이전 비교의 착시**: "Manual" 708개의 GT 15.1%는 Old Auto 601개가
GT 0%이기 때문에 희석된 수치. **Manual-only 107개는 GT 100%**.

**결론**: Regen v4의 GT 100%는 Manual 기준과 일치. 과잉이 아님.

### 2.4 진단 다양성 77개 — 적절 (OK)

Manual 54개보다 많지만, 싱글톤(1회만 등장) 0개.
모든 진단이 최소 2개 이상의 시나리오에 사용되어 의미있는 다양성.
`_DOMAIN_DIAGNOSES` 풀에서 파생되므로 임상적으로 유효한 진단명.

## 3. 미달 영역 (Under-Engineering)

### 3.1 Comorbidity 61% vs Manual 83.2% — GAP

**원인**: `rng.randint(0, 2)`로 0-2개 랜덤 부여 → P(0)=33.3%.
Manual 시나리오는 의도적으로 83.2%에 동반질환을 포함.

**해결 방안**: `rng.randint(0, 2)` → 가중 랜덤 (예: 70% 확률로 1-2개)
또는 severity가 moderate/severe일 때 comorbidity 확률을 높이기.

### 3.2 Trap 시나리오 39.6% vs Manual 59.8% — 구조적 차이

**원인**: 자동 그래프는 branch-based 시나리오가 Phase 1에서 많이 생성되고,
conditional_rules가 적어 Phase 2 trap이 적음. Universal traps (Phase 2b)가
보완하지만 `applicable_domains` 필터링으로 일부 제외됨.

**평가**: 구조적 한계이며 과잉/부족의 문제라기보다 수동 vs 자동의 설계 차이.
수동 시나리오는 trap 중심으로 설계된 반면, 자동은 가이드라인 전체 경로를 커버.

### 3.3 Allergies 1.0% vs Manual 5.6% — 미미한 GAP

**원인**: 알러지는 Phase 2b universal traps에서만 부여 (penicillin, contrast).
Phase 1 branch 시나리오에는 알러지 부여 로직 없음.

**영향도**: 낮음. 5.6% 자체가 소수이며, 알러지 기반 trap은 Phase 2b에서 커버.

## 4. 개선 이력 요약 (Old Auto → Regen v4)

| 항목 | Old Auto | Regen v4 | 개선폭 |
|------|----------|----------|--------|
| Chief complaints | 15 unique | 102 unique | +580% |
| Vitals diversity | 0.168 | 0.994 | +492% |
| Working diagnosis | 모두 빈값 | 77 unique, 0% 빈값 | 치명적 결함 해소 |
| Ground truth | 0% | 100% (avg 5.3 keys) | 치명적 결함 해소 |
| Avg FA/시나리오 | 12.7 | 4.9 | -61% (아직 Manual 2.2 대비 높음) |
| Comorbidity % | 58.6% (trap에서만) | 61.0% (branch+trap) | +2.4pp |

## 5. 결론

### 진짜 문제 (P0-P1)

없음. 과잉 설계로 인한 평가 왜곡이나 결과 무효화 우려는 없음.

### 개선 여지 (P2)

1. FA 100% → 80-85%로 조정 (Phase 3 baseline에서 FA 제거)
2. Comorbidity 61% → 75-80%로 조정 (가중 랜덤)
3. Avg FA/시나리오 4.9 → 3.0 수준으로 줄이기 (graph FA에서 랜덤 샘플링)

### 과잉 설계 아닌 것 (OK)

- GT 100%: Manual-only 기준 100%와 일치
- 진단 다양성 77개: 싱글톤 0, 전부 유효한 임상 진단명
- Vitals diversity 0.994: 가우시안 노이즈 기반으로 자연스러운 분포
- Chief complaint 102개: 도메인별 3-5개 풀에서 랜덤 선택
