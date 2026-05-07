# Phase 3: P2 NeurIPS 실험 패키지 (ENG-10)

Phase 1, 2가 완료된 상태에서 진행. `git log --oneline -15`로 이전 커밋 확인.

---

## ENG-10. NeurIPS 실험 패키지

**먼저 읽을 것**:
- `docs/specs/engineering_spec.md`의 ENG-10
- `docs/specs/expansion_report.md` — 데이터셋/확장 전략
- `run_neurips_experiment.py` (있으면)
- `configs/experiments/` 아래 YAML (있으면)

**작업**:

1) `run_neurips_experiment.py` 구현 (없으면 신설):

```bash
# 사용법
python run_neurips_experiment.py --block baseline --track public --output reports/neurips/
python run_neurips_experiment.py --block ablation --track public --output reports/neurips/
python run_neurips_experiment.py --block scalability --track public --output reports/neurips/
python run_neurips_experiment.py --block alignment --track public --output reports/neurips/
```

2) 4개 블록:

- **baseline**: Oracle, RAG, Planner, Reflection 에이전트 + 외부 벤치마크 대표 설정
- **ablation**: 시간 제약 제거, 순서 제약 제거, 금기 규칙 제거, 위험 점수 완화, DualTrack 제거, fairness guard 제거
- **scalability**: data scale (이벤트 수 증가), format scale (XES/OCEL), environment scale (FHIR tools/budget)
- **alignment**: 3-way safety (SAFE/MARGINAL/UNSAFE), Cohen's κ, Fleiss' κ, Spearman ρ, accuracy

3) 각 블록의 설정은 `configs/experiments/` 아래 YAML로 관리:
```yaml
# configs/experiments/neurips_baseline.yaml
block: baseline
agents: [oracle, rag_gpt4, planner, reflection]
scenarios: [septic_shock_hour1, stemi_inferior, dka_severe]
budget:
  enforce_budget_matching: true
  budget_limit_tokens: 100000
num_runs: 3
seed: 42
```

4) `--track public` (Synthea/공개 데이터)와 `--track credentialed` (MIMIC 계열)을 분리.

5) `tests/test_experiments/` smoke test:
```python
def test_baseline_smoke():
    """Mock LLM으로 baseline 블록 축소 실행"""
    result = run_experiment(block="baseline", track="public", mock=True, limit=1)
    assert result["completed"]
    assert "scores" in result
```

**게이트**: `PYTHONPATH=. pytest tests/test_experiments/ -v`

통과하면:
```bash
git add -A && git commit -m "[ENG-10] NeurIPS 실험 패키지 구현" && git push origin HEAD
git add -A && git commit -m "[Phase3] 전체 구현 완료" && git push origin HEAD
```
