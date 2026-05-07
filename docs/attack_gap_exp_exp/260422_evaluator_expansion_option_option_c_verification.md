Option B에서 했던 "69 pytest + 6-angle 매트릭스" 를 Option C 스케일로 재확장한다고 보면 됩니다. 각 step별로 blocker급 테스트 만 남기고, 끝에 8-angle 최종 검증 매트릭스 하나.
각 Step의 critical test (blocker만)
C1 — External wrappers
TestWhatWhyAdapter parity8개 × 100개 랜덤 episode에서 wrapper.verdict(ep) == (adapter.native_score(ep) >= threshold) 일치wrapper가 native scorer를 왜곡하지 않는다는 유일한 보증. 1-bit 차이 허용 안 됨Calibration 완전성EXTERNAL_EVALUATOR_REGISTRY의 모든 키가 calibration.yaml에 pass_threshold + pi_family_hypothesis 둘 다 가짐누락되면 paper Appendix E 테이블이 null 박힘π-class 가설 검증8개 중 ≥6개가 behavioral classifier와 hypothesis 일치 (C1 AC#2)맞으면 "any evaluator" 주장 성립, 안 맞는 2개는 DISCREPANCIES.md 에 사유 명시Read-only 보장git diff semantic_layer/external/ 빈 결과외부 adapter 수정하면 Option B 회귀 가능
C2 — Repair distance d_G
TestWhatWhyCompliance invariantd_G(ep) == 0 ⟺ v4_hard(ep) == False — 14,826 전체 episoded_G 의 가장 강한 구조적 property. 깨지면 ILP 공식 잘못Handcrafted micro-cases5개 toy episode: 단일 WITHIN → d_G=5, 단일 FORBID → d_G=10 등숫자 하나라도 틀리면 severity cost weight 적용 버그Separating-pair 순서20쌍에서 d_G(harmful) > d_G(safe) 가 ≥18/20 (AC#2)2개 miss는 허용하되 그 이상이면 d_G 정의 재검토Solver soft-failpulp 제거된 venv에서 {"status": "SOLVER_UNAVAILABLE"} 반환, 크래시 Xcontainer 배포시 의존성 축소 허용
C3 — Blindspot clusters
TestWhatWhyMarginal consistencygrid cell BSR 가중합 == Option B의 scalar BSR (10⁻⁴ tol)이게 제일 쉽게 깨지는데 눈에 안 보임. Option B 숫자와 분리되면 논문 전체 신뢰도 흔들림Known-pattern 단정DxEM TIMING 5개 셀 전부 red (>20%), ACov COMMISSION 컬럼 전부 green (<5%)페이퍼 서사(§5.7)와 grid 결과 sanity matchExemplar 링크모든 red cell의 exemplar episode_id가 verdict_matrix_v6.json에서 resolveAppendix E heatmap이 dead link면 credibility 추락
C4a — Gradio demo
TestWhatWhy업로드 샌드박스 (SECURITY)os.system("id"), import subprocess 포함 .py 업로드 시 SecurityError — AST 화이트리스트 또는 RestrictedPython리뷰어가 거의 확실히 시도함. 터지면 submission 취하 수준 리스크Latency SLAdxem 500-sample audit < 10초 on HF Space free tier넘으면 reviewer가 demo 포기 → Contribution 4 설득 실패Dropdown wiring14개 선택지 전부 click-through로 report 생성 (gradio_client 사용)"6 shim + 8 external" 주장의 정량 증명
C4b — MkDocs
TestWhatWhyDead-link 스캔lychee docs/ 0 broken내부 링크 하나라도 깨지면 docs 품질 질문받음Code block 실행\``python블록 전부pytest-examples` 통과"5-line shim template" 주장의 집행 가능성
C5 — Paper
TestWhatWhySingle-source-of-truthAppendix E의 숫자 전부 audit_macros.tex에서 옴 (hardcoded digit grep 0 hit)다른 곳 숫자와 drift 방지9페이지 본문 유지pdfinfo main_final_v17.pdf | grep Pages ≤ 9NeurIPS 제출 요건
C6 — Audit-guided selection 실험
TestWhatWhyNull control랜덤 2-of-6 pair 10회 뽑아 bootstrap CI 계산. audit-guided τ가 null 95%ile 초과없으면 "그냥 우리가 잘 뽑아서" 공격에 무방비Adversarial 대칭같은 π-class 2개 고르면 τ가 최저인지 확인mechanism ("서로 다른 π-class가 안정성 원천") 을 대조로 증명Seed 재현성동일 seed 재실행 시 bit-identical 결과모든 실험 제출 필수 요건
Cross-step (반드시 필요한 통합 테스트 3개)

Regression 고정 (Option B 회귀 방지) — C 반영 후 Option B 6개 shim의 report.json BSR / π-class / witness id가 완전히 동일. 하나라도 drift하면 C 어딘가에서 Option B 경로 오염시킨 것.
Negative control: trivial evaluator — class AlwaysTrue(Evaluator): def verdict(ep): return True 를 감사 돌림. 기대 결과: π-class = "trivial / unstructured", BSR ≈ 0.5, ρ(d_G) ≈ 0, 모든 blindspot cell red. 해석: harness가 "쓰레기 evaluator도 감지한다" 증명.
E2E 새 evaluator 추가 (5-line template) — docs의 quickstart를 literally 따라해서 verdict = lambda ep: len(ep.actions) > 5 같은 장난감 evaluator 하나 더 wrap → make audit-evaluator-one EVAL=... 실행 → report 생성까지 전부 자동. 중간에 어떤 수동 개입도 필요 없어야 함. Docs의 5-line 주장을 실제로 집행.

최종 8-angle 검증 매트릭스 (Option B의 6-angle 확장판)
#AngleCheckTarget1Adapter parity8 wrapper × 100ep = 800 개 verdict = native score threshold0 mismatch2d_G complianced_G == 0 ⟺ ¬v4_hard on 14,8260 violation3Blindspot margingrid sum == Option B scalar BSR6개 shim 전부 일치4RegressionOption B report.json 재생산 bit-identical모든 숫자 동일5Negative controlAlwaysTrue → BSR ≈ 0.5, π-class = trivial성립6Demo security악성 업로드 차단 + 정상 업로드 < 10초둘 다 통과7C6 null controlaudit-guided τ > random pair 95%ile통과8Paper SSoT + 9phardcoded digit grep 0, pages ≤ 9둘 다 통과
자주 놓치는 gotcha 3개

C3 marginal consistency는 grid 구현 자체 버그가 아니라 데이터 로딩 필터 불일치(W8 filter 적용/미적용)에서 제일 많이 틀어집니다. 로딩 path 하나로 통일하는 fixture 먼저.
C4a 업로드 샌드박스는 나중에 붙이면 아키텍처 수술이 필요합니다. demo/app.py 착수 직후 RestrictedPython 또는 importlib.util.spec_from_file_location + AST 화이트리스트 먼저 박고 기능 개발하세요.
C6 null control을 안 만들면 reviewer가 "cherry-picked pair 아니냐" 로 공격했을 때 막을 방법 없습니다. Step C6 AC에 "random baseline 포함" 을 명시하세요.