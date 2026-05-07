# NeurIPS 2026 D&B Anonymization Remediation Plan

**Status**: 자동화 단계 완료, 수동 결정 + 외부 도구 사용 단계로 이행
**Generated**: 2026-05-06
**Anonymized stage location**: `/tmp/cga-bench-anon/` (commit `2eea94e`+)

---

## Executive Summary

NeurIPS 2026은 D&B 트랙도 **default = double-blind**로 변경됨. CGA-Bench는 코드 + 데이터 + paper 전체에 대한 anonymization이 필수.

7개 NeurIPS 요구사항 중:
- ✅ (2) Croissant + RAI: `paper_artifacts/croissant_v7_3_minimal_valid.json` (validator 통과)
- ✅ (3) Code submission: `github.com/anonymous/cga_bench` (단 익명화 안 됨, 별도 stage 필요)
- ✅ (4) Reviewer accessibility: public repo (단 anonymize 필요)
- 🟡 (1) Double-blind: anonymous.4open.science 미러 필요
- 🟡 (5) Long-term hosting: GitHub만으론 부족, Zenodo DOI 권장
- 🟡 (6) Dataset 4GB+ 처리: 398MB tracked 만 → reviewer-friendly
- 🚨 (7) Anonymization 범위: 부분 완료, 잔여 위반 다수 존재

---

## ✅ 최종 검증 통과 (commit `26e01e1`)

| 패턴 | 잔여 hits |
|------|----------|
| IP `127.0.0.1 | **0** |
| `anonymous-org` / `anonymous-org` (단어) | **0** |
| `anonymous-user` | **0** |
| `anonymous-user` | **0** |
| `anonymous-org.ai` email | **0** |
| `[email-redacted]` | **0** |
| `/home/anonymous-org` paths | **0** |
| `anonymous-project` paths | **0** |

**Stage 통계 (최종)**: 8,296 files / 698 MB working tree / 90 MB .git, single anonymous commit.

**Zenodo 상태**: `.zenodo.json` 스켈레톤 준비됨 (creator 익명, version 6.0). **실제 deposit (DOI 발급)은 PENDING — camera-ready 일정**. `docs/NEURIPS_DB_REPRO_CHECKLIST.md` A2 항목에 명시.

---

## 자동화 완료 (`/tmp/cga-bench-anon/`)

| 작업 | 처리 결과 |
|------|----------|
| `.claude/` directory 제거 (60 파일) | ✅ |
| `.hypothesis/` directory 제거 (147 파일) | ✅ |
| Internal IPs `127.0.0.1 마스킹 | ✅ 0 hits |
| ALLM.H 4 files 익명화 (config + 3 runners) | ✅ "anon-medical-31b", "anonymized.example.com" |
| `paper/SESSION_HANDOFF_v17.md` 제거 ([email-redacted] 포함) | ✅ |
| `anonymous-org` / `anonymous-org.ai` mentions | ✅ 0 hits |
| `[email-redacted]` email | ✅ → `[email-redacted]` |
| Path `/home/anonymous-org/anonymous-project/AnonProject/cga_bench` mass replace | ✅ 대부분 |
| `anonymous-user` user mentions | ✅ 0 hits |
| Commit author identity | ✅ `Anonymous <[email-redacted]>` |
| `.gitignore` updated to exclude `.claude/`, `.hypothesis/` | ✅ |

**Stage 통계**: 8,296 files / 698 MB working tree / 87 MB .git, single commit `2eea94e`

---

## 잔여 위반사항 (수동 결정 필요)

### A. 자동 redaction이 어려운 식별 정보 — 잔존 카운트

| 패턴 | 잔여 hits | 비고 |
|------|----------|------|
| `\bTommy\b` (standalone first-name) | **82** | 주로 `clinician_validation/scenario_data*.json` (시나리오 캐릭터 이름) + handoff 문서. 캐릭터 이름은 fictional이지만 Tommy가 lead author 닉네임이라면 식별 위험 |
| `anonymous-user` | 11 | 144 server SSH user — `scripts/infra/`에 SSH 명령 잔존 |
| `/home/anonymous-org` | 8 | 일부 path 잔존 (변수 형태로 sed 미스) |
| `anonymous-project` | 6 | 일부 PYTHONPATH 잔존 |

### B. anonymous-user = Lead author 라면 — 추가 작업

만약 "anonymous-user"가 1저자 Lee 등의 닉네임이면, 다음 파일들은 추가 익명화 필수:
```
clinician_validation/scenario_data_full.json     (78 hits — 시나리오 캐릭터 이름)
clinician_validation/scenario_data_full_v2.json  (26 hits)
docs/260430_CAV_Vocab.md                         (18 hits)
docs/cpg_expansion_v7/TODO_expansion_session.md  (15 hits)
docs/260430_cav_05.md                            (12 hits)
scripts/infra/phase_orchestrator.sh              (19 hits)
scripts/infra/worker_watchdog.sh                 (11 hits)
docs/CLAUDE_CODE_PROMPTS_v73_path_alpha.md       (anonymous-user decision references)
```
처리: `sed -i 's|\bTommy\b|the lead author|g'` 일괄 적용 또는 파일별 검수 후 결정.

### C. PDF / Image metadata (사용자 작업 필요)

본 repo에는 tracked image/PDF 0개 → 우려 없음.

**그러나** paper PDF 자체는 별도 처리 필수:
1. Adobe Acrobat / `pdftk` 등으로 author/title metadata 제거
2. LaTeX `\hypersetup{pdfauthor=}` 비워두기
3. `\maketitle`에 author 비워두기

### D. README / CITATION.cff / CHANGELOG.md (사용자 작업)

| 파일 | 검토 사항 |
|------|----------|
| `README.md` | "CGA-Bench Authors" 등 포괄적 표현 OK. 단 GitHub URL은 placeholder로 |
| `CITATION.cff` | `authors:` 필드 → `Anonymous` |
| `CHANGELOG.md` | 작성자 이름 / Slack 채널 / Notion 링크 등 다 익명화 |

### E. 파일별 검토 권고 — `docs/` + `paper/`

`docs/` 디렉토리 (~150 파일) 와 `paper/` 디렉토리에 internal session handoff, planning notes 등 다수 존재. 이들은 학회 제출에 부적절한 정보를 포함할 가능성:
- 회의록 / 결정 사항
- internal IP / 자격증명 (이미 mass-redact 했지만 변형 가능)
- 작성자 이름 / 닉네임
- 미공개 모델 / 벤더 명

권고: `docs/` + `paper/` 디렉토리를 anonymous repo에서 **전체 제외 or 선별 제외**. 핵심 README + paper supplementary만 남기기.

---

## 실행 옵션 비교

### Option α — anonymous.4open.science (추천)

**작업량**: 5분  
**자동 처리**: ✅ commit history 마스킹, ✅ 작성자 감춤, ✅ 익명 URL 발급  
**한계**: 익명화는 hosting 레벨만, **파일 내용의 식별 정보는 그대로** (anonymous-user 등). 따라서 **자동 anonymization 결과(`/tmp/cga-bench-anon/`)를 새 GitHub repo에 push한 후** 그 URL을 anonymous.4open에 넣는 것이 정공법.

절차:
1. `/tmp/cga-bench-anon/`을 새 GitHub repo (예: `someuser/anon-cga-bench-staging`)에 push
2. https://anonymous.4open.science 에 새 repo URL 입력
3. 발급된 익명 URL (예: `anonymous.4open.science/r/cga-bench-A1B2/`)을 paper, Croissant, NeurIPS 폼에 입력

### Option β — Single-blind 명시

NeurIPS 2026 D&B는 코드/데이터의 anonymization이 비실용적인 경우 single-blind 옵션 허용. 단:
- Submission form에서 명시적으로 single-blind 선택 필요
- Reviewer를 위해 PI/연락처 노출 가능 (리뷰의 익명성은 유지)

CGA-Bench가 ALLM.H 모델명, KorMedMCQA 인용 등으로 vendor가 식별 가능하다면, 차라리 single-blind를 정직하게 선택하는 게 desk-reject 방어에 안전.

### Option γ — Aggressive Anonymization

`/tmp/cga-bench-anon/`에 추가 작업:
1. anonymous-user 일괄 redact: `find . -type f \\( -name "*.md" -o -name "*.py" -o -name "*.sh" -o -name "*.json" -o -name "*.yaml" \\) -exec sed -i 's/\\bTommy\\b/the lead author/g' {} +`
2. anonymous-user 일괄 redact
3. `clinician_validation/scenario_data_full.json` 캐릭터 이름들 점검 (Korean 이름 fictional vs 실명)
4. `docs/` 디렉토리 통째로 제외 (internal artifacts)
5. `paper/` 디렉토리에서 SESSION_HANDOFF/TODO 등 internal-only 파일 제외

---

## Long-term Hosting (5번 항목)

NeurIPS 권장 플랫폼: Dataverse / Kaggle / HuggingFace Datasets / OpenML.

**추천**: Zenodo (DOI 자동 발급, 무료, NeurIPS 권장 충족)
1. https://zenodo.org 접속
2. New upload → cga_bench tarball 업로드
3. DOI 발급 (예: 10.5281/zenodo.XXXXX)
4. Croissant `url` 필드에 DOI URL 추가

**보조**: HuggingFace Datasets — `cga-bench/v7.3` 등으로 mirror

---

## 재현 절차 (anonymized stage 재생성)

```bash
ANON=/tmp/cga-bench-anon
mkdir -p $ANON
cd /home/anonymous-org/anonymous-project/AnonProject
git archive HEAD cga_bench | tar -x -C $ANON
shopt -s dotglob
mv $ANON/cga_bench/* $ANON/ && rmdir $ANON/cga_bench

# Remove .claude / .hypothesis  
mv $ANON/.claude /tmp/_excluded_claude
mv $ANON/.hypothesis /tmp/_excluded_hypothesis

# Redact IPs / anonymous-org / paths
grep -rl "211\\.54\\.28" $ANON | xargs sed -i 's|211\\.54\\.28\\.144|anon-host-A|g; ...'
grep -rl "/home/anonymous-org" $ANON | xargs sed -i 's|/home/anonymous-org/anonymous-project/AnonProject/cga_bench|/path/to/cga_bench|g; ...'

# Anonymize ALLM.H
cat > $ANON/configs/agents/clean_slate_allm_h.yaml << 'EOF'
agent:
  llm_model: "anon-medical-31b"
  base_url: "http://anonymized.example.com:8000/v1"
  ...
EOF

# Remove SESSION_HANDOFF_v17.md
rm $ANON/paper/SESSION_HANDOFF_v17.md

# Init + commit as Anonymous
cd $ANON
git init
git symbolic-ref HEAD refs/heads/main
echo -e ".claude/\n.hypothesis/" >> .gitignore
git add -A
GIT_AUTHOR_NAME="Anonymous" GIT_AUTHOR_EMAIL="[email-redacted]" \
  git commit -m "Initial anonymized release for NeurIPS 2026 D&B review"
```

---

## 체크리스트 (사용자 결정 후 실행)

- [ ] **(α / β / γ 중 선택)**: 익명화 정책 결정
- [ ] (γ 선택 시) anonymous-user/anonymous-user 추가 redact
- [ ] (γ 선택 시) `docs/`, `paper/` 디렉토리 정제
- [ ] PDF metadata 제거 (논문 PDF Adobe / pdftk)
- [ ] LaTeX `\hypersetup{pdfauthor=}`, `\maketitle` author 비우기
- [ ] CITATION.cff `authors: Anonymous`로
- [ ] (α 선택 시) anonymous.4open.science URL 발급
- [ ] Croissant URL 갱신 (`paper_artifacts/croissant_v7_3_minimal_valid.json` `url` 필드)
- [ ] HuggingFace Croissant Checker 추가 검증 (`huggingface.co/spaces/JoaquinVanschoren/croissant-checker`)
- [ ] Zenodo DOI 발급 (long-term preservation)
- [ ] Submission form에 single-blind/double-blind 옵션 선택
- [ ] `cga-bench-anonymous-user@anyplace` 등 잔여 닉네임 grep 재검증

---

## 참조

- Memory `project_neurips_croissant_submission.md` — Croissant 검증 기록
- Memory `project_cga_bench_repo_extraction.md` — public repo (anonymous/cga_bench) 생성 기록
- `paper_artifacts/CROISSANT_README.md` — Croissant submission 가이드
- `paper_artifacts/croissant_v7_3_minimal_valid.json` — submission용 validator-passing Croissant
- 본 문서: `docs/neurips_anonymization_remediation_20260506.md`
