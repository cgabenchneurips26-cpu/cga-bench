#!/usr/bin/env python3
"""γ-1 SGSC v7 E3-a sanity pilot on kdigo_contrast_aki.

Monkeypatches atom_proposer.SYSTEM_PROMPT with the E3-a expanded
14-type taxonomy (7 baseline + 7 added) and runs the full SGSC
pipeline against ONE guideline. Writes output to a pilot-only
directory so frozen v7 baselines under sgsc_output/{guideline_id}/
are never touched.

Usage:
    PYTHONPATH=cga_bench:. python scripts/sgsc/run_e3a_pilot.py \
        --endpoint http://localhost:8013/v1 \
        --model "Qwen/Qwen3.5-397B-A17B-FP8"
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent))

GUIDELINE_ID = "kdigo_contrast_aki"
GUIDELINE_NAME = "KDIGO 2012 Contrast AKI"
CORPUS_FILE = REPO_ROOT / "data_release/v5.0/rag_corpus/KDIGO-2012-Contrast-AKI.parsed.json"
PILOT_OUTPUT = REPO_ROOT / "sgsc_output" / "v7_e3a_pilot" / GUIDELINE_ID

E3A_SYSTEM_PROMPT = """\
You are a clinical guideline analyst. Extract structured RecommendationAtom \
objects from guideline recommendations.

For EACH actionable recommendation, output a JSON object with:
- atom_id: unique identifier (guideline_id + action, snake_case)
- source: {guideline_id, section, page (if known), quote (verbatim substring)}
- population: {inclusion: [...], exclusion: [...]}
- action: {canonical_id (snake_case verb_noun), action_type}
- constraint: {type (FORBIDDEN|REQUIRED|BEFORE|WITHIN|EXPECTED), activation_event (if any), deadline_minutes (if WITHIN)}
- sequence: {before: [...action_ids...], required_prior: [...action_ids...]}
- evidence: {system (AHA|GRADE|etc), recommendation_class, level}
- scenario_hooks: {boundary_variables: [...], counterfactual_pairs: [...]}

action_type MUST be one of these 14 categories. Choose the most specific:
  Baseline 7:
    medication           (e.g., give_aspirin, start_norepinephrine)
    lab                  (e.g., order_lactate, order_troponin)
    imaging              (e.g., order_ct_chest, order_echo)
    procedure            (e.g., intubation, central_line)
    consult              (e.g., consult_nephrology, cardiology_consult)
    reassess             (e.g., reassess_vitals, reassess_response)
    disposition          (e.g., admit_icu, discharge_home)
  Added 7 (E3-a expansion):
    medication_hold      (e.g., hold_ace_inhibitor, hold_metformin)
    medication_avoid     (e.g., avoid_nsaid, avoid_aminoglycoside)
    monitoring           (e.g., monitor_urine_output, monitor_scr_48h)
    dose_adjustment      (e.g., dose_adjust_renal, reduce_contrast_volume)
    followup             (e.g., schedule_nephrology_followup, recheck_egfr_72h)
    prevention           (e.g., pre_hydration, n_acetylcysteine_prophylaxis)
    discharge            (e.g., discharge_with_renal_plan, discharge_education)

Use medication_hold/_avoid for "do not give" or "withhold" recommendations
instead of forcing them into procedure. Use monitoring for surveillance
(serial labs, vital trending). Use prevention for pre-event mitigations
(pre-hydration, prophylactic agents). Use dose_adjustment for contrast
volume caps or weight-based dose limits.

Output a JSON array of atoms. Be exhaustive — extract every actionable recommendation.\
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", default="default")
    parser.add_argument("--threshold", type=float, default=0.6)
    parser.add_argument("--max-scenarios", type=int, default=55)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("e3a_pilot")

    # Monkeypatch BEFORE importing pipeline so propose_atoms picks up new prompt
    from sgsc.extraction import atom_proposer

    atom_proposer.SYSTEM_PROMPT = E3A_SYSTEM_PROMPT
    logger.info("Patched atom_proposer.SYSTEM_PROMPT with E3-a 14-type taxonomy")

    from sgsc.extraction.atom_proposer import AtomProposerConfig
    from sgsc.pipeline import PipelineConfig, run_pipeline

    if not CORPUS_FILE.exists():
        logger.error("Corpus not found: %s", CORPUS_FILE)
        return 2

    data = json.loads(CORPUS_FILE.read_text())
    if isinstance(data, dict):
        recommendations = data.get("recommendations", [])
        full_text = data.get("full_text", "")
        if not full_text and recommendations:
            full_text = " ".join(str(r.get("text", "")) for r in recommendations)
    elif isinstance(data, list):
        recommendations = data
        full_text = " ".join(str(r.get("text", "")) for r in data)
    else:
        recommendations = []
        full_text = str(data)
    logger.info("Loaded %d recommendations from corpus", len(recommendations))

    PILOT_OUTPUT.mkdir(parents=True, exist_ok=True)
    config = PipelineConfig(
        guideline_id=GUIDELINE_ID,
        guideline_name=GUIDELINE_NAME,
        output_dir=str(PILOT_OUTPUT),
        llm_config=AtomProposerConfig(
            endpoint=args.endpoint,
            model=args.model,
            timeout_seconds=600.0,
        ),
        grounding_threshold=args.threshold,
        max_scenarios=args.max_scenarios,
    )

    logger.info("Running pipeline -> %s", PILOT_OUTPUT)
    result = run_pipeline(config, full_text, recommendations)

    summary = {
        "guideline_id": GUIDELINE_ID,
        "atoms_accepted": len(result.atoms),
        "atoms_rejected": len(result.rejected_atoms),
        "atoms_review_required": len(result.review_required_atoms),
        "scenarios": len(result.scenarios),
        "hallucination_rate": result.hallucination_rate,
        "leakage_passed": result.leakage_passed,
        "model": args.model,
        "threshold": args.threshold,
    }
    summary_path = PILOT_OUTPUT / "_pilot_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info("Summary written -> %s", summary_path)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
