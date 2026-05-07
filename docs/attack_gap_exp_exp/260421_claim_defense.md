Claim (TCC construct validity) 방어 — Scope 유지 가능
Experiment X1: Context-swap probe (1-2일, 기존 데이터만 필요)
동일 trajectory T를 서로 다른 patient state P1, P2에 대해 TCC로 채점. P1에서는 해당 action이 mandatory고 P2에서는 forbidden인 경우를 의도적으로 구성 (예: anticoagulant는 acute ischemic stroke에서 mandatory, active hemorrhage에서 forbidden). CRES-1D morphology classifier는 P와 독립이므로 같은 예측을 낸다. TCC는 반전된 verdict를 내야 한다. 만약 TCC가 verdict를 반전시키는 비율이 ≥80%면 A1 공격은 구조적으로 소멸한다. "morphology로 predict 가능"과 "morphology로 환원됨"이 분리되는 증거다. 이게 A1의 진짜 killing-level defense다. 전 답에서 내가 "2-3시간 분석"이라고 얼버무린 residual regression은 약한 대용이었다. Context-swap이 정답이다.
Experiment X2: Causal intervention (1일, 기존 데이터)
각 violation-containing trajectory에서 해당 violation action 하나만 제거하거나 치환. TCC가 그 개별 event에 반응해서 verdict를 flip하는지 측정. Morphology classifier는 single-action perturbation에 둔감할 것으로 예상 (aggregate feature). 이것도 "TCC는 specific clinical events를 읽는다"의 직접 증거.
Experiment X3: Cross-annotator TCC (3-5일)
TCC의 rule encoding을 다른 저자가 같은 guideline에서 독립적으로 다시 작성. TCC-A vs TCC-B의 κ agreement. κ ≥ 0.8이면 TCC는 specific author's encoding의 artefact가 아니다. 지금까지 한 normalizer ablation은 같은 encoding 위의 surface normalizer만 건드렸다. 이건 더 깊은 층이다.
Claim (Oracle = upper bound) — Scope 유지 가능 (조건부)
Experiment X4: Clinician trace upper bound (2주, 의뢰됨이 있으니 활용)
2-3 attending이 실제 50-100 scenario를 trace-by-trace로 진행 (Likert rating이 아니라 action sequence 생성). ClinicianAgent.cga_score 측정. Oracle ≤ Clinician이면 "Oracle은 rule-based upper bound, Clinician은 expert upper bound, 두 개가 서로를 상한/하한 관계로 정의"로 재구성 가능. 이 경우 "Oracle은 upper bound"가 아닌 **"Oracle은 rule-space의 상한, Clinician은 expert-space의 상한"**으로 두 축 제시 — scope가 줄지 않고 정확해진다.
Experiment X5: Independent rule-author (1-2주)
비-저자에게 같은 guideline text 주고 rule 작성 의뢰. Oracle-A vs Oracle-B 비교. 수렴하면 spec-level leakage 공격 무력화. 저자의 rule-coding이 guideline의 객관적 content에 수렴한다는 증거.
Claim (Theorem 3.4 mathematical content) — Scope 유지 가능
Experiment X6: Information-theoretic separation result (4-5일 수학 작업)
현재 Theorem은 projection 정의에서 바로 따라나오는 내용만 담았다. 다음 중 하나가 non-trivial mathematical content가 된다:

Lower bound: H(TCC verdict∣πnctx(trajectory))≥δH(\text{TCC verdict} \mid \pi_{\text{nctx}}(\text{trajectory})) \geq \delta
H(TCC verdict∣πnctx​(trajectory))≥δ for some measurable δ>0\delta > 0
δ>0 on population DD
D. 이게 정리화되면 "process-oblivious evaluator는 정보이론적으로 TCC를 근사할 수 없다"는 정량 bound가 된다.

Existence of separating instance: 공식적으로 ∃\exists
∃ trajectory pair (T1,T2)(T_1, T_2)
(T1​,T2​) such that π(T1)=π(T2)\pi(T_1) = \pi(T_2)
π(T1​)=π(T2​) and TCC(T1)≠TCC(T2)\text{TCC}(T_1) \neq \text{TCC}(T_2)
TCC(T1​)=TCC(T2​) for each projection π\pi
π, with explicit construction. 이걸 Lemma + constructive proof로 달면 tautology 공격 붕괴.

Sample complexity separation: TCC를 ε\varepsilon
ε-approximate하려면 projection π\pi
π의 sample complexity가 Ω(f(ε))\Omega(f(\varepsilon))
Ω(f(ε)) 필요, direct trace access는 O(g(ε))O(g(\varepsilon))
O(g(ε)), f/g=ω(1)f/g = \omega(1)
f/g=ω(1). 이건 진짜 theorem이다.


수학 가능한 멤버 있으면 4-5일. Paper에 정리로 들어가고 기존 Observation-Coarsening은 그 정리의 corollary로 격하. 이러면 Theorem은 오히려 강화된다.
Claim (Scenario realism) — Scope 유지 가능
Experiment X7: MIMIC propensity matching (3-5일, full run 없이)
Full MIMIC replay 말고, 각 engine-marginal scenario에 대해 MIMIC-IV에서 K-nearest-neighbor를 propensity score로 찾기. "각 scenario는 MIMIC에 k≥10 neighbor를 가진다" 보이면 in-distribution 주장이 selectively 성립. 전면 MIMIC run이 아니라 분포 매핑만. 1 week 이하.
Experiment X8: Clinician face-validity (1주, X4와 병렬 가능)
동일 clinician들에게 scenario 100개에 대해 "이런 환자를 ED에서 본 적 있는가?" 4-point. 80%+ yes면 face validity 방어 성립.
Claim (Evaluator divergence — one-cell dependent 아님) — Scope 유지 가능
Experiment X9: Full 4×3 grid re-analysis (0.5-1일, 순수 재분석)
12 cell 전부에서 TCC pass rate vs AC-Proxy pass rate의 gap 분포 시각화. 기존 data만 써서 "non-degenerate 10/12 cell에서도 동일 direction의 gap이 0이 아니다" 보이면 A6 소멸. 현재는 이걸 hero cell 하나로 대표하고 있어서 얻어 맞는다.
Experiment X10: Adversarial pair construction (2-3일)
TCC / AC-Proxy / MAB-Proxy가 반드시 다른 verdict를 내도록 설계된 trajectory pair set을 50개 생성. 이건 benchmark contribution이기도 하다 — "divergence-inducing test set" 자체가 발표 가치.
Claim (Canary leakage) — 이미 잘 방어됨. 축소 불필요.
그럼 2주 안에 뭘 해야 big claim이 산다?
PriorityExperiment시간Defense 대상구조적 / CosmeticP0X1 context-swap1-2일A1 (TCC construct)구조적P0X2 causal intervention1일A1 (TCC vs morphology)구조적P0X9 full grid re-analysis0.5일A6 (one-cell)구조적P01188 typo + Spearman 재계산0.5일A2, A5cosmeticP1X3 cross-annotator TCC3-5일A14 (self-gold)구조적P1X6 proper theorem4-5일A13 (tautology)구조적P1X5 independent rule-author1-2주A7 (Oracle leakage)구조적P2X7 MIMIC propensity3-5일A3/A4 (realism)구조적P2X4 clinician trace2주 (의뢰 중)A7, A14, realism구조적P3X10 adversarial pairs2-3일A6, A13강화
P0 4개 다 끝내면 3일. 이것만으로도 A1/A2/A5/A6 네 개가 지워지고, 이건 reject 공격의 심장부다. P1 3개는 1-2주이며 이게 끝나면 A7/A13/A14까지 지워진다 — 이러면 정말 big claim이 하나도 안 줄어든다.
그래서 답
Scope 축소는 logically necessary가 아니다. 내가 전 답에서 그걸로 가자고 한 건 "안전한 퇴각로"를 우선시한 것이고, 논리적 분석이 아니라 전략적 compromise였다. 구체적으로:

Theorem 3.4를 tautology 공격에서 살리는 건 X6 (proper math) 하나면 된다. Scope 축소 없이.
Oracle upper-bound를 살리는 건 X4 clinician trace 또는 X5 independent rule-author 하나면 된다. 둘 다 돌리면 두 축 bounds로 오히려 더 강력해진다.
TCC construct validity를 살리는 건 X1 context-swap 하나면 충분하다. CRES-1D가 A1의 attack base를 만들었지만 X1이 그 base를 부순다.
Scenario realism을 살리는 건 X7 propensity matching이면 된다. Full MIMIC 없이도.
Evaluator divergence one-cell 공격은 X9 재분석 0.5일로 끝난다.

실험이 아예 불가능한 건 0개다. 다만 각각의 실험이 요구하는 compute / 인력 / 시간은 존재하고, 그걸 동시에 다 돌릴 수 있는 cap이 있다면 P0 네 개 먼저, P1 세 개 그 다음 — 이게 우선순위다.
논리적으로 가능한가? 전부 가능하다. 단, "전부"는 3일 안에 4개 + 2주 안에 3개 + 의뢰된 clinician 결과 + (가능하면) MIMIC propensity 도달, 이런 roadmap이다. 이건 현실적으로 혼자 감당 가능한 분량이면 해야 하고, 감당 불가면 P0 4개만 해도 reject 공격 심장부는 없어진다 — 그 상태에서 남은 A7/A13만 scope 축소하는 partial 전략도 있다 (A13은 "Observation-Coarsening Lemma"로 제목만 내리고, A7만 Oracle rename). 이 중간 전략은 scope 축소가 2개로 국한된다.
가장 정직한 답: 지난 2일은 잘못된 내부 실험에 썼다. Multi-model normalizer와 CRES-1D는 internal consistency를 증명했지만 그건 공격되는 부분이 아니었다. X1 context-swap이 먼저 갔어야 했다. 지금이라도 P0를 3일 안에 끝내면 논문은 big claim으로 복귀 가능하다.