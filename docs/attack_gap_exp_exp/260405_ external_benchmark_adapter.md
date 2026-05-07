# CGA-Bench Adapter 현황 감사 + Cross-Benchmark 실험 준비

## 목적
논문 리뷰어 방어를 위해 기존 벤치마크(MedAgentBench, AgentClinic) adapter와 에피소드 로그 현황을 파악하고,
"E8: Cross-Benchmark Blind-Spot Audit" 실험 실행 가능성을 평가한다.

---

## Task 1: Adapter 코드 현황 파악

아래를 순서대로 실행하고 결과를 보고하라.

```bash
# 1-1. Adapter 관련 파일 찾기
find . -type f -name "*.py" | xargs grep -l -i "adapter\|medagentbench\|agentclinic\|fhir" 2>/dev/null

# 1-2. Adapter 디렉토리 구조
find . -type f -path "*/adapter*" -o -path "*/adapters/*" | head -30

# 1-3. base_adapter 인터페이스 확인
find . -name "base_adapter.py" -exec cat {} \;

# 1-4. MedAgentBench adapter 확인
find . -name "*medagent*" -exec echo "=== {} ===" \; -exec head -80 {} \;

# 1-5. AgentClinic adapter 확인
find . -name "*agentclinic*" -o -name "*agent_clinic*" | xargs head -80 2>/dev/null

# 1-6. 테스트 파일 확인
find . -name "test_adapter*" -exec echo "=== {} ===" \; -exec cat {} \;
```

각 adapter에 대해 다음을 보고하라:
- [ ] 파일이 존재하는가?
- [ ] import가 동작하는가? (`python -c "from src.adapters.medagentbench import MedAgentBenchAdapter"` 등)
- [ ] 핵심 메서드가 구현되어 있는가? (stub/TODO vs 실제 로직)
- [ ] 테스트가 있고 통과하는가?

---

## Task 2: 에피소드 로그 현황 파악

```bash
# 2-1. MedAgentBench 관련 데이터 찾기
find . -type f \( -name "*.json" -o -name "*.jsonl" \) -path "*medagent*" | head -20
find . -type d -name "*medagent*"

# 2-2. AgentClinic 관련 데이터 찾기
find . -type f \( -name "*.json" -o -name "*.jsonl" \) -path "*agentclinic*" | head -20
find . -type d -name "*agentclinic*"

# 2-3. 매핑된 에피소드 데이터 찾기
find . -type d -name "*mapped*" -o -name "*converted*" -o -name "*adapted*"
find . -type f -name "*.json" -path "*mapped*" | head -10

# 2-4. 에피소드 로그 샘플 확인 (MedAgentBench)
MAB_EPISODE=$(find . -type f -name "*.json" -path "*medagent*" | head -1)
if [ -n "$MAB_EPISODE" ]; then
  echo "=== MedAgentBench episode sample: $MAB_EPISODE ==="
  python3 -c "
import json
with open('$MAB_EPISODE') as f:
    ep = json.load(f)
print('Top-level keys:', list(ep.keys()) if isinstance(ep, dict) else f'list of {len(ep)} items')
if isinstance(ep, dict):
    for k, v in ep.items():
        print(f'  {k}: {type(v).__name__}', end='')
        if isinstance(v, list): print(f' (len={len(v)})', end='')
        if isinstance(v, str) and len(v) > 100: print(f' (len={len(v)})', end='')
        print()
"
fi

# 2-5. AgentClinic 에피소드 샘플
AC_EPISODE=$(find . -type f \( -name "*.json" -o -name "*.jsonl" \) -path "*agentclinic*" | head -1)
if [ -n "$AC_EPISODE" ]; then
  echo "=== AgentClinic episode sample: $AC_EPISODE ==="
  head -5 "$AC_EPISODE" | python3 -c "import sys,json; [print(json.dumps(json.loads(l),indent=2)[:500]) for l in sys.stdin]"
fi

# 2-6. 에피소드 수 집계
echo "=== Episode counts ==="
for dir in $(find . -type d -name "*medagent*" -o -name "*agentclinic*" -o -name "*mapped*"); do
  count=$(find "$dir" -name "*.json" -o -name "*.jsonl" | wc -l)
  echo "  $dir: $count files"
done
```

각 벤치마크에 대해 다음을 보고하라:
- [ ] 에피소드 로그가 존재하는가?
- [ ] 몇 개인가?
- [ ] 어떤 clinical domain을 커버하는가? (sepsis, chest_pain 등)
- [ ] native scorer 결과(task_success, score 등)가 포함되어 있는가?
- [ ] 이미 CGA-Bench format으로 변환된 것이 있는가?

---

## Task 3: Domain Overlap 확인

```bash
# 3-1. CGA-Bench의 CPG graph 도메인 목록
echo "=== CGA-Bench domains ==="
ls cpg_model/graphs/*.yaml 2>/dev/null | sed 's|.*/||;s|\.yaml||' | sort

# 3-2. MedAgentBench 태스크에서 domain 추출
echo "=== MedAgentBench domains (from task descriptions) ==="
find . -path "*medagent*" -name "*.json" | head -50 | while read f; do
  python3 -c "
import json
try:
    with open('$f') as fp:
        d = json.load(fp)
    # Try common field names for task/scenario description
    for key in ['task', 'scenario', 'clinical_domain', 'domain', 'category', 'description']:
        if key in d:
            val = d[key]
            if isinstance(val, str):
                print(val[:80])
            break
except: pass
" 2>/dev/null
done | sort -u | head -20

# 3-3. Sepsis 관련 에피소드 특정
echo "=== Sepsis episodes in MedAgentBench ==="
find . -path "*medagent*" -name "*.json" | xargs grep -l -i "sepsis\|ssc\|surviving.sepsis" 2>/dev/null | head -10
echo "Count: $(find . -path "*medagent*" -name "*.json" | xargs grep -l -i "sepsis" 2>/dev/null | wc -l)"
```

---

## Task 4: Adapter 동작 테스트 (코드가 있는 경우)

adapter 코드가 존재하면 아래를 실행:

```bash
# 4-1. MedAgentBench adapter dry-run
python3 -c "
import sys
sys.path.insert(0, '.')

# Adapter import 시도
try:
    # 경로는 실제 구조에 맞게 조정
    from src.adapters.medagentbench import MedAgentBenchAdapter
    print('✅ MedAgentBenchAdapter imported')
    
    # 인스턴스 생성 시도
    adapter = MedAgentBenchAdapter()
    print('✅ Adapter instantiated')
    print(f'   Methods: {[m for m in dir(adapter) if not m.startswith(\"_\")]}')
    
except ImportError as e:
    print(f'❌ Import failed: {e}')
    # 다른 가능한 경로 시도
    import glob
    candidates = glob.glob('**/medagent*.py', recursive=True)
    print(f'   Found files: {candidates}')
except Exception as e:
    print(f'⚠️ Import OK but init failed: {e}')
"

# 4-2. 단일 에피소드 변환 테스트
python3 -c "
import json, glob, sys
sys.path.insert(0, '.')

# 에피소드 파일 찾기
episodes = glob.glob('**/medagent*/**/*.json', recursive=True)
if not episodes:
    episodes = glob.glob('**/medagent*/*.json', recursive=True)
if not episodes:
    print('No MedAgentBench episodes found')
    sys.exit(0)

print(f'Found {len(episodes)} episode files')
ep_path = episodes[0]

with open(ep_path) as f:
    raw = json.load(f)

try:
    from src.adapters.medagentbench import MedAgentBenchAdapter
    adapter = MedAgentBenchAdapter()
    
    # 변환 시도 (메서드 이름은 실제 구현에 맞게)
    for method_name in ['convert', 'adapt', 'process', 'transform', 'to_trace', 'convert_episode']:
        if hasattr(adapter, method_name):
            result = getattr(adapter, method_name)(raw)
            print(f'✅ {method_name}() succeeded')
            print(f'   Result type: {type(result)}')
            if hasattr(result, '__dict__'):
                print(f'   Fields: {list(result.__dict__.keys())[:10]}')
            break
    else:
        print(f'Available methods: {[m for m in dir(adapter) if not m.startswith(\"_\")]}')
        
except Exception as e:
    print(f'❌ Conversion failed: {e}')
"
```

---

## Task 5: 현황 요약 보고

위 결과를 바탕으로 아래 표를 채워서 보고하라:

```markdown
## Adapter 현황 요약

| 항목 | MedAgentBench | AgentClinic |
|------|--------------|-------------|
| Adapter 파일 존재 | ✅/❌ (경로) | ✅/❌ (경로) |
| Import 성공 | ✅/❌ | ✅/❌ |
| 핵심 변환 메서드 | 구현됨/stub | 구현됨/stub |
| 테스트 존재 | ✅/❌ (N개) | ✅/❌ (N개) |
| 에피소드 로그 수 | N개 | N개 |
| Native scorer 결과 포함 | ✅/❌ | ✅/❌ |
| Domain overlap (CGA-Bench) | [domains] | [domains] |
| Sepsis 에피소드 수 | N개 | N개 |
| CGA-Bench format 변환 테스트 | PASS/FAIL | PASS/FAIL |

## Cross-Benchmark 실험 실행 가능성

- 즉시 가능: [yes/no, 이유]
- 필요한 작업: [목록]
- 예상 소요: [시간]
```

---

## 참고: 이 감사의 목적

NeurIPS 2026 제출 논문에서 리뷰어 공격 #16 "native scorer baseline"과 #17 "counterfactual replay with official scorers"를 방어하기 위해,
**MedAgentBench의 task-success scorer가 pass한 에피소드 중 CGA-Bench TCC가 violation을 발견하는 사례**를 보여야 한다.

이를 위해 최소한 필요한 것:
1. MedAgentBench Sepsis 에피소드 로그 (~20개)
2. 각 에피소드의 MedAgentBench native score (task_success)
3. adapter로 CGA-Bench trace format으로 변환
4. TCC evaluator 실행 → violation 탐지
5. "native pass + TCC fail" 에피소드 수 보고

이 실험이 성공하면 논문에 **E8: Cross-Benchmark Portability** 실험으로 추가되며,
#16/#17이 직접 해소되고, contribution이 "기존 벤치마크 에피소드에도 적용 가능한 범용 도구"로 격상된다.