#!/usr/bin/env python3
"""
Generate clinician evaluation materials for pairwise preference study.

Produces HTML files with action timelines for each trace pair,
hiding CGA scores to ensure blind evaluation.

Usage:
    python scripts/generate_clinician_materials.py
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCENARIO_DESCRIPTIONS = {
    "septic_shock_basic": "65세 남성, 발열(38.9°C)과 혈압저하(85/55mmHg)로 응급실 내원. qSOFA 2점, 패혈성 쇼크 의심.",
    "septic_shock_penicillin_allergy": "70세 여성, 페니실린 알레르기력, 발열과 의식저하. 패혈성 쇼크 의심, 항생제 선택 주의.",
    "stemi_inferior_rv_trap": "55세 남성, 갑자기 발생한 흉통과 발한. 하벽 ST 상승 의심, 우심실 경색 가능성.",
    "dka_moderate_basic": "28세 여성, 제1형 당뇨 환자, 구역/구토/복통. 혈당 450mg/dL, pH 7.15.",
    "dka_hypokalemia_trap": "35세 남성, DKA로 내원. 혈당 500mg/dL, pH 7.10, K+ 2.8mEq/L (저칼륨혈증).",
    "stroke_tpa_eligible": "68세 남성, 2시간 전 갑자기 좌측 편마비. NIHSS 14, tPA 투여 적응증.",
    "contrast_aki_prevention_basic": "72세 남성, 관상동맥 조영술 예정, 기저 Cr 1.8mg/dL. 조영제 유발 급성신손상 예방 필요.",
    "aki_stage1_basic": "60세 여성, 수술 후 Cr 0.3mg/dL 상승. KDIGO Stage 1 급성신손상.",
    "af_new_onset_basic": "62세 남성, 두근거림과 어지러움. 심전도에서 빠른 심방세동 확인.",
    "gi_bleeding_upper_basic": "58세 남성, 대량 토혈과 흑색변. 혈압 90/60, 맥박 120.",
    "htn_emergency_basic": "55세 여성, 두통과 시야 흐림. 혈압 220/130, 표적장기 손상 의심.",
    "pe_submassive_basic": "45세 여성, 갑작스런 호흡곤란과 흉통. D-dimer 양성, Wells 점수 높음.",
    "copd_moderate_exacerbation": "70세 남성, COPD 환자. 호흡곤란 악화, 화농성 객담 증가.",
    "adhf_warm_wet": "65세 남성, 심부전 환자. 호흡곤란, 양측 하지부종, 폐 수포음.",
    "hemorrhagic_stroke": "60세 남성, 갑자기 두통과 의식저하. CT에서 뇌출혈 확인.",
}


def generate_pair_html(
    pair: Dict,
    trace_a_actions: List[Dict],
    trace_b_actions: List[Dict],
    pair_index: int,
) -> str:
    """Generate HTML for a single trace pair evaluation."""
    sid = pair.get("scenario_id", "")
    description = SCENARIO_DESCRIPTIONS.get(sid, f"Clinical scenario: {sid}")

    def format_timeline(actions: List[Dict]) -> str:
        if not actions:
            return "<p><em>Action data not available for this trace.</em></p>"
        rows = []
        for a in sorted(actions, key=lambda x: x.get("timestamp", 0)):
            ts = a.get("timestamp", 0)
            aid = a.get("action_id", "unknown")
            atype = a.get("type", "")
            rows.append(
                f"<tr><td>{ts:.0f}분</td><td>{aid}</td><td>{atype}</td></tr>"
            )
        return (
            "<table border='1' cellpadding='5' cellspacing='0'>"
            "<tr><th>시간</th><th>Action</th><th>Type</th></tr>"
            + "".join(rows)
            + "</table>"
        )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Pair {pair_index}: {sid}</title>
<style>
body {{ font-family: 'Noto Sans KR', sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }}
h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
h2 {{ color: #2980b9; }}
.scenario {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; }}
.traces {{ display: flex; gap: 20px; }}
.trace {{ flex: 1; background: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 8px; }}
.trace h3 {{ text-align: center; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th {{ background: #3498db; color: white; }}
td {{ padding: 5px 8px; }}
tr:nth-child(even) {{ background: #f2f2f2; }}
.questions {{ background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; }}
.blind-note {{ color: #e74c3c; font-weight: bold; }}
</style>
</head>
<body>
<h1>Pair {pair_index}: {sid}</h1>

<div class="scenario">
<h2>환자 정보</h2>
<p>{description}</p>
</div>

<p class="blind-note">* CGA 점수 및 위반 정보는 의도적으로 숨겨져 있습니다 (blind evaluation).</p>

<div class="traces">
<div class="trace">
<h3>Trace A ({pair.get('trace_a_agent', 'Agent A')})</h3>
{format_timeline(trace_a_actions)}
</div>
<div class="trace">
<h3>Trace B ({pair.get('trace_b_agent', 'Agent B')})</h3>
{format_timeline(trace_b_actions)}
</div>
</div>

<div class="questions">
<h2>평가 질문</h2>
<p><strong>Q1 (가이드라인 충실도)</strong>: 어느 trace가 해당 임상 가이드라인에 더 충실합니까?</p>
<p>☐ Trace A &nbsp;&nbsp; ☐ Trace B &nbsp;&nbsp; ☐ 동등</p>
<br>
<p><strong>Q2 (환자 안전)</strong>: 어느 trace가 환자에게 더 안전합니까?</p>
<p>☐ Trace A &nbsp;&nbsp; ☐ Trace B &nbsp;&nbsp; ☐ 동등</p>
<br>
<p><strong>Q3 (지도의 판단)</strong>: 레지던트 지도의로서, 어느 trace를 허용하시겠습니까?</p>
<p>☐ Trace A &nbsp;&nbsp; ☐ Trace B &nbsp;&nbsp; ☐ 둘 다 허용 &nbsp;&nbsp; ☐ 둘 다 불허</p>
<br>
<p><strong>코멘트</strong> (선택사항):</p>
<p>_____________________________________________</p>
</div>

</body>
</html>"""


def main() -> None:
    base = Path(__file__).parent.parent
    pairs_file = base / "evidence_pack" / "experiments" / "clinician_pairs.json"
    output_dir = base / "evidence_pack" / "experiments" / "clinician_materials"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not pairs_file.exists():
        logger.error(f"Pairs file not found: {pairs_file}")
        logger.info("Run 'python run_evaluation_science.py --experiment B' first")
        return

    with open(pairs_file) as f:
        data = json.load(f)

    pairs = data.get("pairs", [])
    logger.info(f"Generating materials for {len(pairs)} pairs")

    for i, pair in enumerate(pairs, 1):
        # For now, generate with empty action timelines
        # (full action data would come from episode logs)
        html = generate_pair_html(pair, [], [], i)
        html_path = output_dir / f"pair_{i:03d}_{pair['scenario_id']}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

    # Generate survey CSV template
    csv_path = output_dir / "survey_template.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("rater_id,specialty,years_experience,pair_id,scenario_id,"
                "Q1_guideline_adherence,Q2_patient_safety,Q3_supervisory_acceptance,comments\n")
        for pair in pairs:
            f.write(f",,,{pair['pair_id']},{pair['scenario_id']},,,,\n")

    logger.info(f"Generated {len(pairs)} HTML files + survey template")
    logger.info(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
