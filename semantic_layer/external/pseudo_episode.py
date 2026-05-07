"""Pseudo-episode wrapper for static QA/MCQ benchmarks.

Static benchmarks (AMEGA, MedGUIDE, LLMEval-Med) have no environment steps.
Wrap them as minimal 3-event episodes:
  t=0: observation input
  t=1: agent output (extracted actions)
  t=2: scorer comparison with gold

This allows existing evaluator.py to process them without special-casing.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .models import CanonicalCase, ExpectedAction


def wrap_as_pseudo_episode(
    case: CanonicalCase,
    expected_actions: List[ExpectedAction],
    agent_actions: List[str] | None = None,
) -> Dict[str, Any]:
    """Create pseudo-episode from static benchmark case.

    Returns dict compatible with evaluator pipeline:
    {
        "episode_id": ...,
        "events": [observation, agent_output, score_event],
        "expected_actions": [...],
        "eval_mode": ...,
        "sub_score_mask": ...,
    }
    """
    events = [
        {
            "timestamp_min": 0.0,
            "event_type": "observation",
            "data": {
                "input_text": case.input_text,
                "options": case.options,
                "domain": case.domain,
            },
        },
        {
            "timestamp_min": 1.0,
            "event_type": "agent_output",
            "data": {
                "actions": agent_actions or [],
                "raw_output": None,
            },
        },
        {
            "timestamp_min": 2.0,
            "event_type": "score_comparison",
            "data": {
                "gold_actions": [ea.action_id for ea in expected_actions],
                "gold_path": case.gold_path,
            },
        },
    ]

    return {
        "episode_id": f"{case.dataset_id}:{case.case_id}",
        "events": events,
        "expected_actions": [
            {
                "action_id": ea.action_id,
                "kind": ea.kind,
                "deadline_min": ea.deadline_min,
                "required_before": ea.required_before,
                "confidence": ea.confidence,
                "provenance": ea.provenance,
            }
            for ea in expected_actions
        ],
        "eval_mode": case.eval_mode.value,
        "sub_score_mask": {
            "c1": case.sub_score_mask.c1_path_selection,
            "c2": case.sub_score_mask.c2_mandatory_completion,
            "c3": case.sub_score_mask.c3_forbidden_avoidance,
            "c4": case.sub_score_mask.c4_timing_compliance,
            "c5": case.sub_score_mask.c5_sequence_integrity,
        },
        "metadata": {
            "dataset_id": case.dataset_id,
            "task_type": case.task_type.value,
            "domain": case.domain,
        },
    }
