실험 설계: Held-out sweep + Frontier API + Strict Normalizer Ablation"2개"를 Frontier + Strict normalizer로 해석하되, Held-out은 이미 협상 불가로 결정된 상태니 맨 위에 "H" 실험으로 간단히 얹어 드리겠습니다. 세 실험 모두 pre-registered hypothesis, compute budget, landing section을 명시했습니다.실험 H — Held-out 5 CPG Full Sweep (non-negotiable)Research Question
"CGA-Bench가 model-selection에 쓰이지 않은 5개 guideline에도 동일하게 작동하는가?"Design Matrix
FactorLevelsNGuidelineaabb_transfusion, aba_burn_resuscitation, acog_obstetric_hemorrhage, apa_agitation_management, pals_pediatric_emergency5Episodes/guideline288, 480, 216, 360, 2401,584Modelsoss120b, qwen35b, qwen27b, qwen4b, qwen397b, gemma31b, nemotron30b, deepseek_r1_7b8Runsseed ∈ {42, 137, 2026}3Total trajectories38,016Execution
bash# Per model (loop or parallel shards)
PYTHONPATH=${CGA_BENCH_ROOT} \
  python scripts/experiments/heldout_runner.py <model> results/heldout_v1 \
  --guidelines aabb,aba,acog,apa,pals --runs 3
신규 러너 파일 필요 (full_690_runner.py를 템플릿으로 복제, graph list만 교체).Compute Estimate
CRES-13 기준 per-episode 0.000829 A100-hr → 38,016 × 0.000829 = ~31.5 A100-hr, CO₂eq ~3.8 kg. 2×A100 병렬이면 wall clock ~16시간.Pre-registered Hypotheses

H1 (primary): per-model ΔCGA = mean(held-out) − mean(core) 의 |ΔCGA| 중앙값 < 0.05 → "benchmark generalizes"
H2 (secondary): core 20 vs held-out 5에서 모델 랭킹 Spearman ρ ≥ 0.85 → "relative ordering preserved"
H3 (tertiary): held-out에서만 나타나는 violation type 분포가 core와 χ² p > 0.05 → "failure modes transfer"
Statistical Plan
Wilcoxon signed-rank per model (core-pair vs held-out-pair on matched sub-scores C1–C5), bootstrap 95% CI (10k resamples) on ΔCGA, Holm–Bonferroni correction across 8 models.Failure-mode Framing (미리 준비)

|ΔCGA| > 0.10 → "external-validity threat identified, flagged as open problem" (솔직하게 보고, reject 리스크 낮춤)
랭킹 flip 발생 → 별도 paragraph로 "model-specific domain sensitivity" 분석
Landing
§5.4 (신규) "Held-out Evaluation" + Appendix app:heldout_results full table.

실험 N — Strict Normalizer Ablation (GPU-free)
Research Question
"action_normalizer.py의 fuzzy matching이 CGA Score를 얼마나 높이고 있는가?"
Design Key Insight
GPU 불필요 — 이미 저장된 full_706 trajectory를 재점수화만 하면 됨. LLM inference 재실행 X.
FactorLevelsModeloss120b (top open-source, conservative choice)Scenarioscore 706Runs기존 3 runs 모두 재활용Normalization mode(A) current (DIRECT_MAPPINGS 500+ + PATTERN_RULES + Jaccard≥0.7), (B) strict-exact-match-only, (C) strict + PATTERN_RULES (no fuzzy), (D) DIRECT_MAPPINGS only
Execution
bash# 재점수화 스크립트 (신규)
PYTHONPATH=. python scripts/ablations/normalizer_ablation.py \
  --trajectories results/full_706_v5/oss120b/ \
  --modes current,strict,pattern_only,direct_only \
  --output results/normalizer_ablation_v1/
신규 파일:

scripts/ablations/normalizer_ablation.py — trajectory JSONL 로드 → 4가지 normalizer 모드로 재매핑 → ViolationExtractor 재실행 → 재 HarmScorer
assessor_core/action_normalizer.py에 NormalizationMode enum 추가 (CURRENT, STRICT, PATTERN_ONLY, DIRECT_ONLY)

Compute Estimate
순수 CPU 재점수화 — 706 × 3 runs × 4 modes = 8,472 re-evaluations. 예상 15–20분 wall clock (GPU 0).
Pre-registered Hypotheses

H1: mean(current) − mean(strict) < 0.05 → "normalizer is cosmetic, not outcome-determining"
H2: mean(current) − mean(strict) ∈ [0.05, 0.15] → 정직 공개하고 both reported
H3: mean(current) − mean(strict) > 0.15 → red flag, normalizer over-rewrites, 본문에 명시 필요

Secondary Analysis

Violation type 별 absorption rate: fuzzy matching이 주로 어떤 violation을 "보이지 않게" 만드는가
가장 자주 매핑되는 top-20 (raw → normalized) 쌍 공개 → reviewer가 직접 검증 가능
Model ranking preservation: strict 모드에서도 top-3 모델이 동일한가? (cross-check but only oss120b run needs only 1 row)

Landing
Appendix app:normalizer_ablation (0.5 page) + 본문 §5 ablation paragraph 한 줄 요약 (mean drop = X%p, ranking preserved Y/N).
