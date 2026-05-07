> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# CGA-Bench 저장소 정리: 현행 코드/데이터 식별 및 아카이빙

## 목표

수많은 실험을 거치면서 파일이 누적되었다.
논문 최종본(main_final_v5.tex)에 실제로 필요한 코드, 데이터, 결과만
식별하고, 나머지는 `_archive/`로 이동시켜 repo를 깨끗하게 만든다.

## Step 1: 의존성 추적 — 논문에서 역으로 추적

### 1a. main.tex의 모든 수치가 어떤 파일에서 오는지 매핑

tracking/tracking_sheet.md를 읽어서, 각 claim의 "Source" 컬럼에 
적힌 파일/실험을 전부 추출해줘.

예를 들어:
- "V0/v3_constraint_audit" → scripts/experiments/v3_p0_constraint_audit.py + 출력파일
- "EXP11" → 어떤 스크립트가 exp11을 실행하는지
- "V3/verdict" → v3_p1c_verdict_integration.py + 출력파일
- "P2/timestamp" → v3_p2_timestamp_sensitivity.py + 출력파일

이렇게 해서 **논문에 직접 기여하는 파일 목록**을 만들어줘.

### 1b. 실행 의존성 추적

위에서 찾은 스크립트들이 import하거나 읽는 파일도 추적:
- 공통 모듈 (assessor_core/, utils/ 등)
- 데이터 파일 (YAML, episode JSON, config 등)
- 중간 결과물 (다른 스크립트의 출력을 입력으로 쓰는 경우)

## Step 2: 파일 분류

전체 저장소의 모든 파일을 스캔해서 4개 카테고리로 분류:

### Category A: ACTIVE — 논문 최종본에 필수
논문 수치의 source chain에 있는 파일.
- 평가 파이프라인 코드 (assessor_core/ 등)
- CPG YAML 그래프
- Scenario 정의
- Episode 데이터 (clean_slate_rescored)
- 확정된 실험 스크립트 (V0-V7, P0-P8 중 결과가 논문에 쓰인 것)
- 확정된 결과 파일
- tracking_sheet.md, reconciliation_report.md
- main_final_v5.tex, references.bib

### Category B: IN_PROGRESS — 아직 빈칸을 채울 실험
tracking_sheet에서 상태가 NOT_STARTED 또는 IN_PROGRESS인 실험의 스크립트:
- EXP-SPREAD 관련
- EXP-Z1 관련
- EXP-NORM 관련
- EXP-CLINICIAN 자료
- 기타 아직 실행해야 할 것

### Category C: ARCHIVE — 과거 버전, 대체된 실험
- main.tex 이전 버전들 (v1, v2, v3, v4)
- 대체된 실험 스크립트 (예: P2 방식이 Exp11으로 대체된 경우)
- reconciliation 전의 중간 결과물
- 더 이상 참조되지 않는 출력 파일
- 과거 review document들
- 이전 버전의 tracking sheet

### Category D: INFRASTRUCTURE — 유지해야 하는 기반
- .git, .gitignore
- requirements.txt, pyproject.toml
- README.md
- 테스트 코드
- CI/CD 설정

## Step 3: 정리 실행 계획 생성

분류 결과를 바탕으로 실행 계획을 만들어줘.
**아직 실행하지 마** — 계획만 만들어서 내가 확인할 수 있게.

```
# 출력 형식

## ACTIVE 파일 목록 (이동 안 함)
path/to/file — 용도 — 참조하는 논문 claim ID

## IN_PROGRESS 파일 목록 (이동 안 함)
path/to/file — 용도 — 채울 빈칸 ID

## ARCHIVE 후보 목록 (확인 후 _archive/로 이동)
path/to/file → _archive/path/to/file — 대체된 이유

## 판단 불가 (수동 확인 필요)
path/to/file — 불확실한 이유
```

## Step 4: 디렉토리 구조 제안

정리 후 repo가 어떤 구조가 되면 좋을지 제안해줘:

```
cga-bench/
├── paper/
│   ├── main_final_v5.tex
│   ├── references.bib
│   └── figures/
├── src/                    # 평가 파이프라인 (assessor_core 등)
├── data/
│   ├── cpg_graphs/         # YAML
│   ├── scenarios/          # scenario config
│   └── episodes/           # clean_slate_rescored
├── experiments/
│   ├── scripts/            # 확정된 실험 스크립트
│   └── results/            # 확정된 결과
├── tracking/               # tracking_sheet, reconciliation
├── _archive/               # 과거 버전 전부
└── release/                # 제출용 패키지 (나중에)
```

## 주의사항

1. **삭제하지 마.** 모든 것은 _archive/로 이동만.
2. git history는 건드리지 마.
3. 이동 전에 반드시 계획을 출력해서 내가 확인.
4. ACTIVE인지 ARCHIVE인지 판단이 안 되면 "판단 불가"로 분류.
5. episode 데이터는 용량이 클 수 있으므로 경로만 기록하고 
   실제 이동은 내가 결정.

## 입력

저장소 루트: [현재 프로젝트 루트 경로]
tracking sheet: tracking/tracking_sheet.md
main tex: paper/main_final_v5.tex (또는 현재 위치)