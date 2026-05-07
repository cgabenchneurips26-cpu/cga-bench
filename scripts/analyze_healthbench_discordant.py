#!/usr/bin/env python3
"""Deep analysis of HealthBench keyword-mandatory discordant cases."""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

RESULTS_PATH = Path("results/healthbench_sample_1000.json")
INDICES_PATH = Path("evidence_pack/sampling/healthbench_sample_indices.json")
HF_URL = (
    "https://huggingface.co/datasets/openai/healthbench/resolve/main/"
    "2025-05-07-06-14-12_oss_eval.jsonl"
)

ACTION_KW = [
    "order", "prescribe", "administer", "perform", "initiate",
    "start", "give", "refer", "obtain", "measure", "check", "draw", "send",
]
EXPLANATION_KW = [
    "explain", "counsel", "educate", "inform", "discuss", "rationale",
]
STOP_WORDS = {
    "should", "must", "need", "with", "that", "this", "from", "have",
    "been", "will", "they", "their", "about", "more", "some", "would",
    "could", "also", "does", "response", "mention", "include", "provide",
    "recommend", "suggest", "patient", "doctor", "medical", "health",
    "important", "appropriate", "necessary", "treatment", "condition",
    "information", "possible", "specific", "general", "based", "such",
    "following", "being", "other", "when", "make", "like", "well",
    "care", "note", "case", "help", "time", "risk", "cause",
}

AXIS_TO_KIND = {
    "accuracy": "ASSESSMENT",
    "completeness": "ACTION",
    "communication_quality": "EXPLANATION",
    "context_awareness": "ASSESSMENT",
    "safety": "ACTION",
}


def classify_criterion(text: str) -> str:
    lower = text.lower()
    if any(kw in lower for kw in ACTION_KW):
        return "ACTION"
    if any(kw in lower for kw in EXPLANATION_KW):
        return "EXPLANATION"
    return "ASSESSMENT"


def classify_enhanced(
    text: str,
    tags: List[str],
    points: int,
) -> str:
    if tags:
        for tag in tags:
            if tag.startswith("axis:"):
                axis = tag.split(":", 1)[1]
                if axis in AXIS_TO_KIND:
                    return AXIS_TO_KIND[axis]
    if points < 0:
        return "ACTION"
    return classify_criterion(text)


def content_words(text: str) -> set:
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    return words - set(ACTION_KW) - set(EXPLANATION_KW) - STOP_WORDS


def main() -> None:
    # Load results
    with open(RESULTS_PATH) as f:
        results: List[Dict[str, Any]] = json.load(f)
    print(f"Loaded {len(results)} result records")

    result_by_id: Dict[str, Dict[str, Any]] = {}
    for r in results:
        result_by_id[r.get("prompt_id", "")] = r

    # Load sample indices
    with open(INDICES_PATH) as f:
        idx_data = json.load(f)
    sample_indices = sorted(idx_data["indices"])
    print(f"Sample indices: {len(sample_indices)}")

    # Load raw HF data
    print("Downloading HealthBench eval data...")
    data = urllib.request.urlopen(HF_URL).read().decode()
    lines = data.strip().split("\n")
    print(f"Total HF lines: {len(lines)}")

    raw_rows: Dict[str, Dict[str, Any]] = {}
    for idx in sample_indices:
        if idx < len(lines):
            row = json.loads(lines[idx])
            raw_rows[row["prompt_id"]] = row
    print(f"Loaded {len(raw_rows)} raw rows for sample")

    # Find discordant episodes
    discordant: List[Tuple[Dict, Dict]] = []
    commission_all: List[Tuple[Dict, Dict]] = []

    for r in results:
        pid = r.get("prompt_id", "")
        nn = r.get("native_normalized", 0)
        mc = r.get("mandatory_coverage", 1.0)
        fa = r.get("forbidden_avoidance", 1.0)

        if nn >= 0.5 and (mc < 1.0 or fa < 1.0):
            if pid in raw_rows:
                discordant.append((r, raw_rows[pid]))

        if fa < 1.0 and pid in raw_rows:
            commission_all.append((r, raw_rows[pid]))

    print(f"Discordant episodes (with raw data): {len(discordant)}")
    print(f"Commission violation episodes: {len(commission_all)}")
    print()

    # ── Analyze first 50 discordant ──
    analysis_results: List[Dict[str, Any]] = []
    classification_counts: Counter = Counter()
    keyword_trigger_counts: Counter = Counter()

    for result, raw_row in discordant[:50]:
        pid = result["prompt_id"]
        rubrics = raw_row.get("rubrics", [])
        prompt = raw_row.get("prompt", [])
        prompt_text = " ".join(
            t.get("content", "") for t in prompt if t.get("role") == "user"
        )[:300]
        completion_preview = (result.get("completion_preview", "") or "")[:200]

        mc = result.get("mandatory_coverage", 1.0)
        fa = result.get("forbidden_avoidance", 1.0)

        # Split rubrics into mandatory (positive pts) and forbidden (negative pts)
        mandatory_rubrics: List[Dict[str, Any]] = []
        forbidden_rubrics: List[Dict[str, Any]] = []
        for i, r in enumerate(rubrics):
            pts = r.get("points", 0)
            text = r.get("criterion", "")
            tags = r.get("tags", [])
            kind = classify_enhanced(text, tags, pts)

            if pts > 0:
                has_action = any(kw in text.lower() for kw in ACTION_KW)
                triggered = [kw for kw in ACTION_KW if kw in text.lower()]
                mandatory_rubrics.append({
                    "idx": i,
                    "text": text,
                    "points": pts,
                    "tags": tags,
                    "kind": kind,
                    "has_action_kw": has_action,
                    "triggered_kws": triggered,
                })
                for kw in triggered:
                    keyword_trigger_counts[kw] += 1
            elif pts < 0:
                forbidden_rubrics.append({
                    "idx": i,
                    "text": text,
                    "points": pts,
                    "tags": tags,
                })

        n_mandatory = len(mandatory_rubrics)
        n_mandatory_satisfied = round(mc * n_mandatory) if n_mandatory > 0 else 0
        n_mandatory_missed = n_mandatory - n_mandatory_satisfied

        action_kw_rubrics = [m for m in mandatory_rubrics if m["has_action_kw"]]
        non_action_rubrics = [m for m in mandatory_rubrics if not m["has_action_kw"]]
        n_action_kw = len(action_kw_rubrics)
        n_non_action = len(non_action_rubrics)

        # Check how many rubric topics the completion addresses
        completion_lower = completion_preview.lower()
        addressed = 0
        not_addressed = 0
        for mr in mandatory_rubrics:
            cw = content_words(mr["text"])
            if cw:
                overlap = sum(1 for w in cw if w in completion_lower)
                if overlap >= max(1, len(cw) * 0.2):
                    addressed += 1
                else:
                    not_addressed += 1

        # Classify: A=true omission, B=matching failure, C=over-classification
        if n_action_kw == 0 and n_non_action > 0:
            classification = "C"
        elif n_non_action > n_action_kw:
            classification = "C" if addressed <= not_addressed else "B"
        elif addressed > n_mandatory_missed:
            classification = "B"
        elif not_addressed > addressed:
            classification = "A"
        else:
            classification = "B"

        classification_counts[classification] += 1

        analysis_results.append({
            "episode_num": len(analysis_results) + 1,
            "prompt_id": pid,
            "prompt_preview": prompt_text[:200],
            "completion_preview": completion_preview,
            "native_normalized": result.get("native_normalized"),
            "mandatory_coverage": mc,
            "forbidden_avoidance": fa,
            "n_mandatory": n_mandatory,
            "n_mandatory_missed": n_mandatory_missed,
            "n_action_keyword_rubrics": n_action_kw,
            "n_non_action_rubrics": n_non_action,
            "classification": classification,
            "sample_mandatory_rubrics": [
                mr["text"][:150] for mr in mandatory_rubrics[:5]
            ],
            "sample_non_action_rubrics": [
                mr["text"][:150] for mr in non_action_rubrics[:3]
            ],
            "sample_action_kw_rubrics": [
                {"text": mr["text"][:150], "kws": mr["triggered_kws"]}
                for mr in action_kw_rubrics[:3]
            ],
        })

    # ── Commission violation analysis (10 episodes) ──
    commission_analysis: List[Dict[str, Any]] = []
    for result, raw_row in commission_all[:10]:
        pid = result["prompt_id"]
        rubrics = raw_row.get("rubrics", [])
        prompt = raw_row.get("prompt", [])
        prompt_text = " ".join(
            t.get("content", "") for t in prompt if t.get("role") == "user"
        )[:200]

        forbidden_rubrics = []
        for r in rubrics:
            pts = r.get("points", 0)
            if pts < 0:
                forbidden_rubrics.append({
                    "text": r.get("criterion", ""),
                    "points": pts,
                    "tags": r.get("tags", []),
                })

        commission_analysis.append({
            "prompt_id": pid,
            "prompt_preview": prompt_text,
            "forbidden_avoidance": result.get("forbidden_avoidance"),
            "native_normalized": result.get("native_normalized"),
            "n_forbidden": len(forbidden_rubrics),
            "forbidden_rubrics": [
                {"text": fr["text"][:200], "points": fr["points"]}
                for fr in forbidden_rubrics
            ],
        })

    # ── Keyword frequency in mandatory rubrics (across 50 episodes) ──
    all_mandatory_kw_freq: Counter = Counter()
    total_mandatory_count = 0
    for _, raw_row in discordant[:50]:
        for r in raw_row.get("rubrics", []):
            if r.get("points", 0) > 0:
                total_mandatory_count += 1
                lower = r.get("criterion", "").lower()
                for kw in ACTION_KW:
                    if kw in lower:
                        all_mandatory_kw_freq[kw] += 1

    tag_axis_freq: Counter = Counter()
    for _, raw_row in discordant[:50]:
        for r in raw_row.get("rubrics", []):
            for tag in r.get("tags", []):
                if tag.startswith("axis:"):
                    tag_axis_freq[tag] += 1

    # ── Classification by tag axis ──
    axis_mandatory_counts: Counter = Counter()
    axis_non_action_mandatory: Counter = Counter()
    for _, raw_row in discordant[:50]:
        for r in raw_row.get("rubrics", []):
            pts = r.get("points", 0)
            if pts <= 0:
                continue
            tags = r.get("tags", [])
            text = r.get("criterion", "")
            has_action = any(kw in text.lower() for kw in ACTION_KW)
            for tag in tags:
                if tag.startswith("axis:"):
                    axis_mandatory_counts[tag] += 1
                    if not has_action:
                        axis_non_action_mandatory[tag] += 1

    output = {
        "summary": {
            "total_results": len(results),
            "total_discordant_with_raw": len(discordant),
            "analyzed_discordant": min(50, len(discordant)),
            "commission_episodes": len(commission_all),
        },
        "classification_counts": {
            "A_true_omission": classification_counts["A"],
            "B_matching_failure": classification_counts["B"],
            "C_over_classification": classification_counts["C"],
            "total": sum(classification_counts.values()),
        },
        "action_keyword_frequency": {
            "total_mandatory_rubrics_in_50_episodes": total_mandatory_count,
            "keyword_hits": dict(all_mandatory_kw_freq.most_common()),
        },
        "tag_axis_frequency": dict(tag_axis_freq.most_common()),
        "axis_mandatory_vs_non_action": {
            axis: {
                "total_mandatory": axis_mandatory_counts[axis],
                "non_action_mandatory": axis_non_action_mandatory[axis],
                "pct_non_action": round(
                    axis_non_action_mandatory[axis]
                    / max(axis_mandatory_counts[axis], 1)
                    * 100,
                    1,
                ),
            }
            for axis in sorted(axis_mandatory_counts.keys())
        },
        "discordant_examples_first_10": analysis_results[:10],
        "commission_examples": commission_analysis,
        "all_50_classifications": [
            {
                "num": a["episode_num"],
                "pid": a["prompt_id"][:16],
                "class": a["classification"],
                "mc": a["mandatory_coverage"],
                "nn": a["native_normalized"],
                "n_mand": a["n_mandatory"],
                "n_missed": a["n_mandatory_missed"],
                "n_action_kw": a["n_action_keyword_rubrics"],
                "n_non_action": a["n_non_action_rubrics"],
            }
            for a in analysis_results
        ],
    }

    out_path = Path("evidence_pack/analysis/healthbench_keyword_mandatory_deep.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults written to {out_path}")
    print(json.dumps(output["summary"], indent=2))
    print(json.dumps(output["classification_counts"], indent=2))
    print("\nKeyword frequency:")
    print(json.dumps(output["action_keyword_frequency"], indent=2))
    print("\nAxis tag frequency:")
    print(json.dumps(output["tag_axis_frequency"], indent=2))
    print("\nAxis mandatory vs non-action:")
    print(json.dumps(output["axis_mandatory_vs_non_action"], indent=2))


if __name__ == "__main__":
    main()
