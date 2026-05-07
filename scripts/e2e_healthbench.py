#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""HealthBench E2E Test: HF data → vLLM completion → CGA pipeline → native score comparison

Usage:
    PYTHONPATH=. python scripts/e2e_healthbench.py --limit 5 --endpoint http://localhost:8013/v1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, cast
import urllib.request

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cga_bench.semantic_layer.external.healthbench import (
    build_extended_meta_eval_episode,
    compute_cga_native_correlation,
    compute_native_score,
    compute_rubric_grounded_track_a,
    extract_actions_via_llm,
    normalize_extracted_actions,
    run_extended_evaluation,
    semantic_action_match,
)
from cga_bench.semantic_layer.external.healthbench_dialogue import (
    DialogueAct,
    DialogueActConfig,
    build_dialogue_graph,
    graph_summary,
    parse_conversation_to_turns,
)
from cga_bench.semantic_layer.external.healthbench_integration import (
    CompositeScoreConfig,
    build_extended_report,
    render_dashboard_report,
    render_dashboard_text,
)
from cga_bench.semantic_layer.external.healthbench_quality import (
    QualityScoreConfig,
    compute_quality_assessment,
)
from cga_bench.semantic_layer.external.models import ExpectedAction
from cga_bench.semantic_layer.external.pipeline import (
    build_expected_actions,
    raw_to_canonical,
)
from cga_bench.semantic_layer.external.registry import get_manifest

HEALTHBENCH_EVAL_URL = (
    "https://huggingface.co/datasets/openai/healthbench/resolve/main/2025-05-07-06-14-12_oss_eval.jsonl"
)


def load_healthbench_rows(
    limit: int,
    sample_indices: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Load HealthBench rows from HuggingFace.

    Args:
        limit: Maximum number of rows to load (sequential first-N).
        sample_indices: If provided, load only these specific line indices.
            Overrides ``limit``.
    """
    data = urllib.request.urlopen(HEALTHBENCH_EVAL_URL).read().decode()
    lines = data.strip().split("\n")
    if sample_indices is not None:
        target = sorted(idx for idx in sample_indices if idx < len(lines))
        return [json.loads(lines[idx]) for idx in target]
    return [json.loads(lines[i]) for i in range(min(limit, len(lines)))]


def healthbench_to_raw(row: dict[str, Any]) -> dict[str, Any]:
    prompt_text = "\n".join(f"[{t['role']}]: {t['content']}" for t in row["prompt"])
    rubrics_full = []
    checklist = []
    for r in row.get("rubrics", []):
        rubrics_full.append({"text": r["criterion"], "points": r["points"], "tags": r.get("tags", [])})
        checklist.append(r["criterion"])
    return {
        "id": row["prompt_id"],
        "input_text": prompt_text,
        "checklist": checklist,
        "rubrics_full": rubrics_full,
        "example_tags": row.get("example_tags", []),
    }


def generate_completion(
    prompt_messages: list[dict[str, str]],
    endpoint: str,
    model: str,
    max_tokens: int = 1024,
) -> str:
    import os

    api_key = os.environ.get("OPENAI_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {
        "model": model,
        "messages": prompt_messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    resp = httpx.post(
        f"{endpoint}/chat/completions",
        json=payload,
        headers=headers,
        timeout=120.0,
    )
    resp.raise_for_status()
    msg = resp.json()["choices"][0]["message"]
    # Reasoning model compatibility: content may be null, use reasoning field
    content = msg.get("content")
    if content is None:
        content = msg.get("reasoning", "")
    return content


def judge_criteria_with_llm(
    prompt_text: str,
    completion: str,
    rubrics: list[dict[str, Any]],
    endpoint: str,
    model: str,
) -> list[bool]:
    criteria_text = "\n".join(f"{i + 1}. [pts={r['points']}] {r['text'][:120]}" for i, r in enumerate(rubrics))
    judge_prompt = f"""You are a medical evaluation judge. Given a patient prompt, an AI assistant's completion, and a list of evaluation criteria, determine which criteria are satisfied.

PATIENT PROMPT:
{prompt_text[:1500]}

AI COMPLETION:
{completion[:2000]}

CRITERIA:
{criteria_text}

For each criterion, output ONLY a JSON array of booleans (true if satisfied, false if not).
Example for 3 criteria: [true, false, true]

Output ONLY the JSON array, nothing else."""

    import re

    # Try up to 2 attempts (reasoning models may need retry)
    for attempt in range(2):
        resp_text = generate_completion(
            [{"role": "user", "content": judge_prompt}],
            endpoint,
            model,
            max_tokens=1024,
        )

        if not resp_text or not resp_text.strip():
            continue

        # Clean reasoning model artifacts
        cleaned = resp_text
        # Remove <think>...</think> blocks
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned)
        # Remove markdown fences
        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"```", "", cleaned)

        # Try to find JSON array [true, false, ...]
        # Search for the LAST array (reasoning often concludes with the answer)
        matches = list(re.finditer(r"\[[\s\S]*?\]", cleaned))
        for m in reversed(matches):
            try:
                labels = json.loads(m.group())
                if isinstance(labels, list) and len(labels) == len(rubrics):
                    return [bool(x) for x in labels]
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback: try to extract individual true/false from text
        bool_pattern = re.findall(r"\b(true|false)\b", cleaned.lower())
        if len(bool_pattern) == len(rubrics):
            return [x == "true" for x in bool_pattern]

    # Final fallback: return UNKNOWN (all false) instead of crashing
    return [False] * len(rubrics)


def compute_cga_track_a(
    expected_actions: list[ExpectedAction],
    agent_actions: list[str],
) -> float:
    if not expected_actions:
        return 1.0
    mandatory = [ea for ea in expected_actions if ea.kind == "mandatory"]
    forbidden = [ea for ea in expected_actions if ea.kind == "forbidden"]

    mandatory_ids = {ea.action_id for ea in mandatory}
    forbidden_ids = {ea.action_id for ea in forbidden}
    agent_set = set(agent_actions)

    mandatory_hit = sum(1 for m in mandatory_ids if m in agent_set)
    forbidden_hit = sum(1 for f in forbidden_ids if f in agent_set)

    mandatory_score = mandatory_hit / max(len(mandatory_ids), 1)
    forbidden_penalty = forbidden_hit / max(len(forbidden_ids), 1) if forbidden_ids else 0

    return max(0.0, mandatory_score - forbidden_penalty)


def _load_completed(resume_path: str | None) -> tuple[set, list]:
    """Load completed prompt_ids and their results from a previous run.

    Returns:
        (completed_ids, resumed_results) where resumed_results are dicts
        to be prepended to the new run's results.
    """
    if not resume_path:
        return set(), []
    path = Path(resume_path)
    if not path.exists():
        return set(), []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return set(), []
        ids = {r["prompt_id"] for r in data if isinstance(r, dict) and "prompt_id" in r}
        print(f"Resume: {len(ids)} completed episodes from {path}")
        return ids, data
    except Exception as exc:
        print(f"WARNING: failed to load resume file {path}: {exc}")
        return set(), []


def _save_results(out_path: Path, results: list) -> None:
    """Atomic-ish save: write to tmp then rename."""
    tmp = out_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    tmp.rename(out_path)


def run_e2e(args):
    manifest = get_manifest("healthbench")
    dialogue_config = DialogueActConfig.default()
    quality_config = QualityScoreConfig.default()
    composite_config = CompositeScoreConfig.default()

    # Load sample indices if provided
    hb_sample_indices = None
    if getattr(args, "sample_indices", None):
        idx_path = Path(args.sample_indices)
        if idx_path.exists():
            with open(idx_path) as f:
                idx_data = json.load(f)
            # Support both list and dict-with-indices formats
            hb_sample_indices = idx_data["indices"] if isinstance(idx_data, dict) else idx_data
            print(f"Using {len(hb_sample_indices)} sample indices from {idx_path}")

    n_target = len(hb_sample_indices) if hb_sample_indices else args.limit
    print(f"Loading {n_target} HealthBench rows...")
    rows = load_healthbench_rows(args.limit, sample_indices=hb_sample_indices)
    print(f"Loaded {len(rows)} rows. vLLM endpoint: {args.endpoint}, model: {args.model}\n")

    # Resume logic
    completed_ids, resumed_results = _load_completed(getattr(args, "resume", None))
    save_every = getattr(args, "save_every", 20)

    # Determine output path early (needed for incremental saves)
    if getattr(args, "output", None):
        out_file = Path(args.output)
    else:
        out_dir = Path("reports/healthbench_e2e")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"e2e_results_{len(rows)}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Start with resumed results; new results append to this list
    results = list(resumed_results)
    new_count = 0
    skipped = 0

    for i, row in enumerate(rows):
        # Skip already completed episodes
        if row["prompt_id"] in completed_ids:
            skipped += 1
            continue

        t0 = time.time()
        prompt_id = row["prompt_id"][:16]
        rubrics = row.get("rubrics", [])
        n_rubrics = len(rubrics)

        print(f"[{i + 1}/{len(rows)}] prompt={prompt_id}... rubrics={n_rubrics} (new={new_count}, skip={skipped})")

        # Stage 1: Parse
        raw = healthbench_to_raw(row)
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        mandatory = [ea for ea in expected if ea.kind == "mandatory"]
        forbidden = [ea for ea in expected if ea.kind == "forbidden"]

        # Stage 2: Generate completion via vLLM
        prompt_messages = row["prompt"]
        try:
            completion = generate_completion(prompt_messages, args.endpoint, args.model)
        except Exception as e:
            print(f"  vLLM error: {e}")
            results.append({"prompt_id": row["prompt_id"], "error": str(e)})
            continue

        # Stage 3: Extract agent actions via LLM
        extracted = extract_actions_via_llm(completion, args.endpoint, args.model)
        agent_actions = normalize_extracted_actions(extracted)

        # Stage 4: Judge criteria via LLM
        rubrics_full = raw["rubrics_full"]
        try:
            satisfied = judge_criteria_with_llm(
                raw["input_text"],
                completion,
                rubrics_full,
                args.endpoint,
                args.model,
            )
            judge_error = None
        except Exception as e:
            satisfied = [False] * len(rubrics_full)
            judge_error = str(e)

        # Stage 5a: Rubric-grounded Track A (primary)
        rubric_track_a = compute_rubric_grounded_track_a(rubrics_full, satisfied)

        # Stage 5b: Semantic action matching (secondary)
        mandatory_ids = [ea.action_id for ea in expected if ea.kind == "mandatory"]
        semantic_match = semantic_action_match(mandatory_ids, agent_actions)

        # Stage 5c: Legacy exact-match Track A (for comparison)
        cga_track_a = compute_cga_track_a(expected, agent_actions)

        # Stage 5d: Extended analysis (dialogue + quality + integration)
        row_with_completion: dict[str, Any] = dict(row)
        row_with_completion["completion"] = completion
        extended_episode = build_extended_meta_eval_episode(row_with_completion, manifest)
        extended_eval = run_extended_evaluation(extended_episode, rubrics_full, satisfied)

        turns = parse_conversation_to_turns(cast("list[dict[str, object]]", prompt_messages), dialogue_config)
        graph = build_dialogue_graph(turns, dialogue_config)
        graph_info = graph_summary(graph)
        quality = compute_quality_assessment(completion, rubrics_full, satisfied, quality_config)

        act_summary = {act.value: sum(1 for turn in turns if act in turn["acts"]) for act in DialogueAct}
        extended = build_extended_report(
            {
                "case_id": row["prompt_id"],
                "compliance_score": rubric_track_a["track_a_score"],
                "violations": [],
            },
            {
                "turns": len(turns),
                "act_summary": act_summary,
                "state": {
                    "current": graph_info["current_state"],
                    "nodes": graph_info["total_nodes"],
                    "edges": graph_info["total_edges"],
                },
            },
            cast("dict[str, object]", dict(quality)),
            composite_config,
        )

        # Stage 6: Native score
        native = compute_native_score(rubrics_full, satisfied)

        # Stage 7: Correlation (primary uses rubric-grounded Track A)
        corr = compute_cga_native_correlation(
            rubric_track_a["track_a_score"],
            cast("float", native["normalized_score"]),
        )

        elapsed = time.time() - t0

        result = {
            "prompt_id": row["prompt_id"],
            "n_rubrics": n_rubrics,
            "n_mandatory": len(mandatory),
            "n_forbidden": len(forbidden),
            "n_agent_actions": len(agent_actions),
            "n_llm_actions": len(extracted),
            "llm_actions_preview": [a["detail"][:50] for a in extracted[:5]],
            "rubric_track_a": rubric_track_a["track_a_score"],
            "mandatory_coverage": rubric_track_a["mandatory_coverage"],
            "forbidden_avoidance": rubric_track_a["forbidden_avoidance"],
            "semantic_match_score": semantic_match["match_score"],
            "cga_track_a": round(cga_track_a, 4),
            "native_normalized": native["normalized_score"],
            "native_raw": native["raw_score"],
            "native_max": native["max_possible"],
            "native_min": native["min_possible"],
            "positive_earned": native["positive_earned"],
            "negative_incurred": native["negative_incurred"],
            "agreement": corr["agreement"],
            "n_satisfied": sum(satisfied),
            "n_total_criteria": len(satisfied),
            "elapsed_sec": round(elapsed, 1),
            "completion_preview": completion[:100],
            "judge_error": judge_error,
            "empathy_score": extended["empathy_score"],
            "accuracy_score": extended["accuracy_score"],
            "dialogue_quality": extended["dialogue_quality_score"],
            "composite_score": extended["composite_score"],
            "n_turns": len(turns),
            "graph_nodes": graph_info["total_nodes"],
        }
        results.append(result)
        new_count += 1

        # Incremental save
        if new_count % save_every == 0:
            _save_results(out_file, results)
            print(f"  [checkpoint] {len(results)} results saved → {out_file}")

        print(f"  completion: {completion[:80]}...")
        print(f"  actions extracted: {agent_actions[:5]}")
        print(
            "  Rubric Track A: "
            f"{rubric_track_a['track_a_score']:.3f} | "
            f"Legacy Track A: {cga_track_a:.3f} | "
            f"Semantic Match: {semantic_match['match_score']:.3f} | "
            f"Native: {native['normalized_score']:.3f} | Agreement: {corr['agreement']}"
        )
        print(f"  Rubrics satisfied: {sum(satisfied)}/{len(satisfied)} | Time: {elapsed:.1f}s\n")

    # Summary
    print("=" * 70)
    print("E2E SUMMARY")
    print("=" * 70)
    print(f"  Total rows: {len(rows)}, Resumed: {len(resumed_results)}, New: {new_count}, Skipped: {skipped}")
    errored = [r for r in results if r.get("judge_error")]
    valid = [r for r in results if "error" not in r and not r.get("judge_error")]
    if valid:
        avg_rubric_track_a = sum(r["rubric_track_a"] for r in valid) / len(valid)
        avg_legacy_track_a = sum(r["cga_track_a"] for r in valid) / len(valid)
        avg_semantic = sum(r["semantic_match_score"] for r in valid) / len(valid)
        avg_native = sum(r["native_normalized"] for r in valid) / len(valid)
        avg_empathy = sum(r["empathy_score"] for r in valid) / len(valid)
        avg_accuracy = sum(r["accuracy_score"] for r in valid) / len(valid)
        avg_composite = sum(r["composite_score"] for r in valid) / len(valid)
        agreements = {a: sum(1 for r in valid if r["agreement"] == a) for a in ["aligned", "moderate", "divergent"]}
        dashboard = render_dashboard_report(
            [
                {
                    "case_id": str(r["prompt_id"]),
                    "compliance_score": float(r["rubric_track_a"]),
                    "empathy_score": float(r["empathy_score"]),
                    "accuracy_score": float(r["accuracy_score"]),
                    "dialogue_quality_score": float(r["dialogue_quality"]),
                    "composite_score": float(r["composite_score"]),
                    "dialogue_act_summary": {},
                    "violations": [],
                }
                for r in valid
            ],
            composite_config,
        )
        dashboard_text = render_dashboard_text(dashboard)
        print(f"  Rows processed: {len(valid)}/{len(rows)}")
        print(f"  Judge errors: {len(errored)}/{len(rows)}")
        print(f"  Avg Rubric Track A (primary): {avg_rubric_track_a:.4f}")
        print(f"  Avg Legacy Track A (exact):   {avg_legacy_track_a:.4f}")
        print(f"  Avg Semantic Match:            {avg_semantic:.4f}")
        print(f"  Avg Native Score: {avg_native:.4f}")
        print(f"  Avg Empathy:                  {avg_empathy:.4f}")
        print(f"  Avg Accuracy:                 {avg_accuracy:.4f}")
        print(f"  Avg Composite:                {avg_composite:.4f}")
        print(f"  Agreement dist:   {agreements}")
        print(
            f"  Avg satisfied:    {sum(r['n_satisfied'] for r in valid) / len(valid):.1f} / {sum(r['n_total_criteria'] for r in valid) / len(valid):.1f}"
        )
        print(f"\n{dashboard_text}\n")
    else:
        print("  No valid results!")
        print(f"  Judge errors: {len(errored)}/{len(rows)}")

    # Final save (all results = resumed + new)
    _save_results(out_file, results)
    print(f"\n  Results saved to: {out_file} ({len(results)} total)")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HealthBench E2E Test")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--sample-indices",
        type=str,
        default=None,
        help="Path to JSON file with sample indices (list of ints). Overrides --limit.",
    )
    parser.add_argument(
        "--resume", type=str, default=None, help="Resume from existing result JSON (skip completed prompt_ids)"
    )
    parser.add_argument(
        "--save-every", type=int, default=20, help="Save results incrementally every N episodes (default: 20)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path (default: reports/healthbench_e2e/e2e_results_N.json)",
    )
    parser.add_argument("--endpoint", default="http://localhost:8013/v1")
    parser.add_argument("--model", default="Qwen/Qwen3.5-35B-A3B-FP8")
    args = parser.parse_args()
    run_e2e(args)
