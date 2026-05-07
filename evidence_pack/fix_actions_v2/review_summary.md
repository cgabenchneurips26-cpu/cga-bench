# Action Effects 수정 가이드

## 요약
- Mandatory (즉시): 0개
- Forbidden: 121개
- Allowed: 0개
- Unknown: 0개

## Mandatory Actions by Domain

## Merge 순서

```bash
# 1. Mandatory (OMISSION 수정)
cat evidence_pack/fix_actions_v2/mandatory_action_effects.yaml >> cpg_model/action_effects.yaml

# 2. 검증
python -m pytest tests/ -x -q

# 3. Dry-run (시나리오 1개)
python scripts/full_690_runner.py --dry-run --scenarios 1

# 4. 전체 재실행
python scripts/full_690_runner.py --output results/full_706_v6

# 5. (재실행 후) Forbidden + Allowed 추가 평가
```
