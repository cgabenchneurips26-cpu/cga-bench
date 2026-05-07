구체 실험 설계: “High-Authority Core” 하나면 충분합니다

복잡하게 하지 말고, 추가 실험은 하나로 제한하는 게 좋습니다.

실험 이름

E9: Authority-Stratified Conformance Audit

또는 더 간결하게:

High-Authority Core Robustness

실험 질문

Does the evaluator blind spot persist when CGA-Bench is restricted to high-authority CPG constraints?

subset 정의

가능하면 2-level로 갑니다.

High-authority core:
GRADE 1A/1B, AHA Class I 또는 Class IIa with LOE A/B, IDSA Strong 또는 equivalent, KDIGO strong recommendation, AABB strong recommendation.

All-source catalogue:
현재 전체 1049 hard constraints.

여기서 중요한 건 “evidence quality”와 “recommendation strength”를 과도하게 통합하지 않는 것입니다. GRADE 자체도 quality와 strength를 분리하므로, paper에서는 다음처럼 조심스럽게 말하는 게 안전합니다.

We define high-authority constraints by recommendation strength first, using evidence level only as a tie-breaker when the source guideline separates the two.

GRADE Working Group은 evidence certainty와 recommendation strength를 구분하는 접근을 제공한다고 설명합니다. 이 구분을 존중해야 reviewer가 덜 칩니다.

재계산할 metric

많이 하지 않아도 됩니다. 아래 4개면 충분합니다.

FA_strict = ASC∩CwT∩PAF pass, TCC_high_authority fail
detection loss for MAB/AC replay under high-authority-only TCC
ranking reversal under high-authority-only TCC
per-violation-type breakdown: WITHIN / BEFORE / FORBID / MUST

결과가 좋으면 main body §5.5에 4–5문장으로 넣고, 상세 table은 appendix에 넣습니다.

성공 기준

pre-register 식으로 쓰면 더 좋습니다.

We treat the high-authority audit as successful if strict-consensus false acceptance remains non-zero, replay detection loss remains above 50%, and at least one ranking reversal persists.

현재 전체 corpus에서 strict false accept 6.6%, replay detection loss 63.2–84.2%, ranking reversal 75%라서, high-authority subset에서도 완전히 사라지지는 않을 가능성이 큽니다.

결과가 애매할 때의 해석

결과가 작아져도 망한 게 아닙니다. 오히려 이렇게 해석할 수 있습니다.

High-authority filtering reduces blind-spot prevalence but preserves the qualitative projection ordering.

즉 “모든 수치가 유지되어야 한다”가 아니라, projection-blindness pattern이 유지되는가를 보면 됩니다.

5. 이 실험을 넣으면 contribution 문장이 이렇게 바뀝니다

현재 contribution 3은 “multi-axis sensitivity audit”로 잘 되어 있습니다. 여기에 한 문장만 추가하면 됩니다.

We further stratify the audit by clinical authority: restricting the catalogue to high-authority recommendations (strong/Grade-1 or guideline-equivalent constraints) preserves the qualitative false-accept and rank-reversal pattern, showing that the blind spot is not driven by weak or author-dependent guideline edges.

Abstract에는 길게 넣지 말고, source-grounded sentence 뒤에 짧게 붙이면 됩니다.

The signal persists under a high-authority CPG subset, ruling out weak-recommendation artefacts.

결과가 나오기 전에는 abstract에 넣지 말고, main/appendix 준비만 하는 게 안전합니다.

6. 왜 “patient-state context-swap”보다 이걸 1순위로 보나?

사실 context-swap도 매우 좋습니다. 현재 원고에는 이미 Figure 2가 “same action trace, different typed constraints”를 보여주고, Appendix AU에는 238 conditional FORBID matched patient pairs가 있습니다. 이건 CondMedQA와 차별화하기 좋은 강한 medical-specific witness입니다.

하지만 이것은 이미 paper에 상당히 들어가 있습니다. 새 contribution으로 추가하기보다는 §5.5 또는 §6에서 더 prominent하게 승격하면 됩니다.

반면 evidence-authority stratification은 현재 원고에서 “provenance가 있다” 수준이지, 그 provenance를 이용한 실험은 아직 없습니다. 즉 r이라는 formal object를 실제 empirical axis로 쓰는 추가 contribution입니다. reviewer가 “evidence grade를 넣었다고 했는데 평가에는 쓰지 않네?”라고 물을 수 있는 지점을 선제적으로 막습니다.

따라서 우선순위는 다음이 좋습니다.

Primary 추가 실험: High-Authority Core Robustness
Secondary 승격: existing context-swap / no-context matched-pair pool을 main text에서 더 선명하게 언급
하지 말 것: Five Rights, multimorbidity conflict resolution, pharmacokinetic state-dependent Δ를 main contribution으로 새로 주장

이 판단은 첨부된 mechanism 분석과 후속 비판 메모와도 일치합니다. 8-axis를 모두 paper에 넣으면 overclaim 위험이 크고, formalism이 실제 encoding하는 axis만 살리는 게 더 안전합니다. 특히 Five Rights의 dose/route, multimorbidity cross-CPG conflict resolution, state-dependent therapeutic window는 현재 CGA-Bench가 충분히 encoding하지 않으므로 main contribution으로 쓰면 reviewer가 공격하기 쉽습니다.

7. 실험 난이도와 예상 작업량

이 실험은 새 모델 inference가 필요 없을 가능성이 큽니다. CPG graph에 evidence grade provenance가 이미 있으므로, scorer 쪽에서 constraint filter만 추가하면 됩니다.

필요한 작업은 대략 다음입니다.

evidence grade parser / mapper 작성
GRADE 1A/1B, AHA Class I, IDSA Strong, KDIGO strong, AABB strong 등을 high-authority로 mapping.
CDE -> active constraints 이후 filter 적용
전체 Chard 대신 Chard_high_authority로 TCC 재계산.
기존 verdict matrix 재집계
ASC/CwT/PAF/MAB/AC replay는 그대로 두고, TCC verdict만 high-authority reference로 바꿔서 FA/detection loss/ranking reversal 재계산.
appendix table 작성
constraint count, type count, evidence-grade count, per-metric delta.