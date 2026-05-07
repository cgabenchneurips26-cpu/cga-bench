# Phase 2: P0 Guard + P1 (ENG-06 → 07 → 08 → 09 → 11)

Phase 1(ENG-00~05)이 완료된 상태에서 진행한다. 먼저 `git log --oneline -10`으로 Phase 1 커밋을 확인해라.

## 공통 규칙

- 각 태스크 시작 시 **수정 대상 파일을 먼저 읽어라**
- 게이트 실패 시 수정 → 최대 3회 재시도
- 게이트 통과 후: `git add -A && git commit -m "[ENG-XX] 구현 완료" && git push origin HEAD`
- 게이트 3회 실패: WIP 커밋 후 다음 태스크로 진행 (P1은 개별 독립성이 높다)

---

## ENG-06. scorer-agent 격리와 누출 탐지

**먼저 읽을 것**:
- `pyproject.toml` (또는 setup.py/setup.cfg) — 현재 extras 구조
- `docs/specs/engineering_spec.md`의 ENG-06

**작업**:

1) pyproject.toml에 extras 분리 추가:
```toml
[project.optional-dependencies]
scorer = ["pydantic>=2.0"]  # cpg_engine, assessor_core 관련 의존성
agent = ["pydantic>=2.0"]   # agent_runner, agent_rules 관련 의존성
dev = ["pytest", "hypothesis", "ruff", "mypy"]  # 전체 + 개발 도구
```
(실제 의존성은 기존 requirements.txt/pyproject.toml에서 가져와라)

2) `scripts/ci/leakage_scan.py` 신설:
```python
"""Canary-based leakage detection between scorer and agent."""
import uuid, json
from pathlib import Path

def generate_canaries(n: int = 5) -> list[str]:
    return [f"CGA_CANARY__{uuid.uuid4().hex[:12]}" for _ in range(n)]

def scan_transcripts(transcript_dir: str | Path, canaries: list[str]) -> dict:
    hits = {c: 0 for c in canaries}
    for f in Path(transcript_dir).rglob("*"):
        if f.is_file() and f.suffix in (".json", ".txt", ".log", ".yaml"):
            try:
                text = f.read_text(errors="ignore")
                for c in canaries:
                    if c in text:
                        hits[c] += 1
            except Exception:
                pass
    total = sum(hits.values())
    return {"total_hits": total, "hits": hits, "passed": total == 0}
```

3) `tests/test_isolation/` 작성:
- test_extras_separation: scorer 모듈과 agent 모듈의 import 경로가 분리 가능한지 검증
- test_canary_scan: 테스트용 transcript에 canary를 일부러 넣지 않았을 때 pass, 넣었을 때 fail

**게이트**: `PYTHONPATH=. pytest tests/test_isolation/ -v`

---

## ENG-07. 외부 벤치마크 어댑터 계약 테스트

**먼저 읽을 것**:
- `cga_bench/semantic_layer/external/agentclinic.py` — 전체
- `cga_bench/semantic_layer/external/medagentbench.py` — 전체
- `cga_bench/semantic_layer/external/medchain.py` — 전체
- `cga_bench/semantic_layer/external/normalize.py`
- `cga_bench/env/adapters/` 아래 파일들
- ENG-00에서 만든 EpisodeLog, ExternalParseResult 스키마

**작업**:

1) 공통 추상 인터페이스 확인/신설:
```python
# semantic_layer/external/base.py
from abc import ABC, abstractmethod

class ExternalBenchmarkAdapter(ABC):
    @abstractmethod
    def load_raw_case(self, path: str) -> dict: ...
    @abstractmethod
    def parse_to_scenario(self, raw: dict) -> dict: ...
    @abstractmethod
    def parse_to_episode_log(self, raw: dict) -> EpisodeLog: ...
    @abstractmethod
    def detect_domain(self, raw: dict) -> str: ...
    @abstractmethod
    def normalize_actions(self, actions: list) -> list: ...
```

2) 각 어댑터가 이 인터페이스를 구현하는지 확인/수정.

3) `tests/test_external/` 계약 테스트:
- 각 어댑터에 대해 mock raw input fixture 작성 (실제 데이터가 없으면 어댑터 코드에서 기대하는 포맷을 보고 만들어라)
- parse_to_episode_log 결과가 EpisodeLog pydantic 검증 통과
- detect_domain이 합리적 도메인 반환 (또는 "unknown")
- domain mismatch 시 fallback 동작
- malformed input에 대한 graceful failure (크래시 없이 에러 반환)

**게이트**: `PYTHONPATH=. pytest tests/test_external/ -v`

---

## ENG-08. XES/OCEL export-import와 스트레스 러너

**먼저 읽을 것**:
- `cga_bench/semantic_layer/export/xes_exporter.py` — export 함수 시그니처
- `cga_bench/semantic_layer/export/ocel_exporter.py` — export 함수 시그니처
- 위 파일에서 사용하는 import 라이브러리 확인 (pm4py 등)

**작업**:

1) `tests/test_export/test_roundtrip.py`:
```python
def test_xes_roundtrip():
    """internal → XES → reimport → 동치성"""
    original_log = make_sample_episode_log(n_events=100)
    xes_path = tmp_path / "test.xes"
    export_to_xes(original_log, xes_path)
    reloaded = import_from_xes(xes_path)
    assert len(reloaded.events) == len(original_log.events)
    # timestamp 정렬 순서 동일
    # action_id 매칭

def test_ocel_roundtrip():
    """internal → OCEL JSON → reimport → 동치성"""
    ...
```
- import 함수가 없으면 만들어라.
- make_sample_episode_log 헬퍼: N개의 ActionEvent를 시간 순서대로 생성

2) `scripts/bench/stress_eventlog_roundtrip.py`:
```bash
python scripts/bench/stress_eventlog_roundtrip.py --profile small --format xes
```
- small: 1,000 events / medium: 50,000 / large: 500,000
- 측정: events/sec, export time, import time, peak RSS (resource 모듈 사용)
- 결과를 JSON으로 `reports/stress/` 에 저장

**게이트**: `PYTHONPATH=. pytest tests/test_export/ -v`

---

## ENG-09. 재현성 번들 및 CI 명령 표준화

**작업**:

1) `scripts/repro/record_environment.py`:
```python
"""현재 환경 정보를 JSON으로 기록"""
import sys, platform, subprocess, json
info = {
    "python": sys.version,
    "os": platform.platform(),
    "git_sha": subprocess.getoutput("git rev-parse HEAD"),
    "git_dirty": bool(subprocess.getoutput("git status --porcelain")),
    "pip_freeze": subprocess.getoutput("pip freeze"),
}
# reports/<date>/<gitsha>/environment.json 에 저장
```

2) `scripts/repro/seed_manager.py`:
```python
import random, os
def fix_all_seeds(seed: int = 42):
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy; numpy.random.seed(seed)
    except ImportError: pass
    try:
        import torch; torch.manual_seed(seed)
    except ImportError: pass
```

3) `scripts/run_all_tests.sh`:
```bash
#!/bin/bash
set -e
echo "=== Lint ===" && ruff check . || true
echo "=== Type Check ===" && mypy . --ignore-missing-imports || true
echo "=== Schema Tests ===" && PYTHONPATH=. pytest tests/test_schemas/ -q
echo "=== Engine Tests ===" && PYTHONPATH=. pytest tests/test_engine/ -q
echo "=== Assessor Tests ===" && PYTHONPATH=. pytest tests/test_assessor/ -q
echo "=== Golden Tests ===" && PYTHONPATH=. pytest tests/test_golden/ -q
echo "=== ALL PASSED ==="
```

**게이트**: `bash scripts/run_all_tests.sh`

---

## ENG-11. 문서와 출처 정합성

**먼저 읽을 것**:
- `cga_bench/cpg_model/graphs/` — 모든 YAML

**작업**:

1) 각 YAML의 모든 node에 source_guideline/source_section/source_page/source_quote 누락 확인. 빠진 필드를 합리적으로 채워라 (README.md의 References 참조).

2) DKA 그래프: "ADA dc24-S015" → DKA 관리는 ADA Standards of Care의 Section 4 또는 별도 consensus statement에 해당. 확인 후 수정.

3) `scripts/ci/audit_sources.py` 작성:
```python
"""YAML 그래프의 source traceability 감사"""
import yaml, sys
from pathlib import Path

REQUIRED_FIELDS = ["source_guideline", "source_section", "source_page", "source_quote"]

def audit(graphs_dir: str = "cga_bench/cpg_model/graphs") -> list[str]:
    issues = []
    for f in Path(graphs_dir).glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        for node_id, node in data.get("nodes", {}).items():
            for field in REQUIRED_FIELDS:
                if not node.get(field):
                    issues.append(f"{f.name}:{node_id} — missing {field}")
    return issues

if __name__ == "__main__":
    issues = audit()
    for i in issues: print(i)
    sys.exit(1 if issues else 0)
```

**게이트**: `python scripts/ci/audit_sources.py`

---

## Phase 2 완료 체크

```bash
bash scripts/run_all_tests.sh
PYTHONPATH=. pytest tests/test_isolation/ tests/test_external/ tests/test_export/ -v --tb=short
```

통과하면:
```bash
git add -A && git commit -m "[Phase2] P1 전체 게이트 통과" && git push origin HEAD
```
