"""Extract off-graph medical actions from ``empty_raw_samples``.

When the RAG scaffold's LLM path returns actions that the 3-tier normaliser
cannot match against the scenario's ``available_actions``, the raw model
output is captured into ``empty_raw_samples[*].raw_preview`` (only when
``CGA_DEBUG_RAW_RESPONSE=1``).

This tool scans those raw previews, recovers action proposals via a
lenient regex-based JSON parser (tolerates truncation / partial output),
and tabulates the action IDs that repeatedly appear but never land in the
scenario graph. The resulting table is the seed for expanding
``cpg_model/action_alias_map.yaml`` and/or ``universal_clinical_safety.yaml``
so the scorer can tag these proposals as GENERAL_WORKUP instead of
collapsing them to empty.

Usage:
    python scripts/analysis/extract_off_graph_actions.py \\
        results/dryrun_task2_postfix_20260421_155930 \\
        --out paper/off_graph_catalog.tsv
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator


ACTION_ID_RE = re.compile(r'"action_id"\s*:\s*"([^"]+)"')
ACTION_TYPE_RE = re.compile(r'"action_type"\s*:\s*"([^"]+)"')
JUSTIFICATION_RE = re.compile(r'"justification"\s*:\s*"((?:[^"\\]|\\.){0,400})"')


def iter_episode_files(results_root: Path) -> Iterator[Path]:
    for p in results_root.rglob("*.json"):
        name = p.name
        if name.startswith("checkpoint") or name.startswith("model_summary"):
            continue
        if name.startswith("."):
            continue
        yield p


def extract_actions_from_raw(raw: str) -> list[tuple[str, str, str]]:
    """Pull (action_id, action_type, justification_head) tuples out of a
    raw LLM JSON payload. Tolerates truncated / unclosed JSON by regexing
    each field independently — order within a single action object is not
    guaranteed, so we pair positionally. For each action_id match, try to
    find the nearest-following action_type and justification."""
    results: list[tuple[str, str, str]] = []
    ids = list(ACTION_ID_RE.finditer(raw))
    for i, m in enumerate(ids):
        aid = m.group(1)
        start = m.end()
        end = ids[i + 1].start() if i + 1 < len(ids) else len(raw)
        window = raw[start:end]
        t = ACTION_TYPE_RE.search(window)
        j = JUSTIFICATION_RE.search(window)
        action_type = t.group(1) if t else ""
        justification = (j.group(1)[:200] if j else "").replace("\n", " ")
        results.append((aid, action_type, justification))
    return results


def collect(results_root: Path) -> dict:
    """Walk episode JSONs, collect off-graph proposals."""
    proposal_counts: Counter[str] = Counter()
    proposal_types: dict[str, Counter[str]] = defaultdict(Counter)
    proposal_scenarios: dict[str, set[str]] = defaultdict(set)
    sample_justifications: dict[str, str] = {}
    truncation_episodes = 0
    total_samples = 0
    total_episodes = 0

    for ep_path in iter_episode_files(results_root):
        try:
            doc = json.loads(ep_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        raw_samples = doc.get("empty_raw_samples") or []
        if not raw_samples:
            continue
        total_episodes += 1
        scenario_id = doc.get("scenario_id", "?")
        episode_truncated = False
        for sample in raw_samples:
            total_samples += 1
            raw = sample.get("raw_preview") or ""
            raw_len = sample.get("raw_len", 0)
            if raw_len > len(raw) + 16:
                # ``raw_preview`` is capped at 2000 bytes; anything longer
                # than that in the actual response is truncated in-sample
                # but the LLM also returns truncated content when hitting
                # ``max_tokens`` mid-JSON.
                episode_truncated = True
            if raw.count("{") != raw.count("}"):
                episode_truncated = True
            for aid, atype, just in extract_actions_from_raw(raw):
                proposal_counts[aid] += 1
                if atype:
                    proposal_types[aid][atype] += 1
                proposal_scenarios[aid].add(scenario_id)
                if aid not in sample_justifications and just:
                    sample_justifications[aid] = just
        if episode_truncated:
            truncation_episodes += 1

    return {
        "proposal_counts": proposal_counts,
        "proposal_types": proposal_types,
        "proposal_scenarios": proposal_scenarios,
        "sample_justifications": sample_justifications,
        "truncation_episodes": truncation_episodes,
        "total_samples": total_samples,
        "total_episodes": total_episodes,
    }


def render_tsv(summary: dict, out_path: Path) -> None:
    rows = []
    rows.append(
        [
            "action_id",
            "frequency",
            "scenarios_observed",
            "dominant_action_type",
            "sample_justification",
        ]
    )
    counts: Counter[str] = summary["proposal_counts"]
    types = summary["proposal_types"]
    scenarios = summary["proposal_scenarios"]
    justifications = summary["sample_justifications"]
    for aid, freq in counts.most_common():
        type_counter = types.get(aid, Counter())
        dominant_type = type_counter.most_common(1)[0][0] if type_counter else ""
        scn_list = ",".join(sorted(scenarios[aid]))
        just = justifications.get(aid, "").replace("\t", " ")
        rows.append([aid, str(freq), scn_list, dominant_type, just])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join("\t".join(r) for r in rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", type=Path, help="Run output directory containing episode JSONs")
    parser.add_argument("--out", type=Path, default=None, help="TSV output path (default: stdout table)")
    parser.add_argument("--top", type=int, default=30, help="Top-N rows to print to stdout")
    args = parser.parse_args()

    summary = collect(args.results_dir)
    counts: Counter[str] = summary["proposal_counts"]
    print(f"Episodes with empty_raw_samples: {summary['total_episodes']}")
    print(f"Total empty_raw samples scanned: {summary['total_samples']}")
    print(f"Episodes showing JSON truncation signs: {summary['truncation_episodes']}")
    print(f"Unique off-graph action_ids recovered: {len(counts)}")
    print(f"Total off-graph action proposals: {sum(counts.values())}")
    print()
    print(f"Top {args.top} off-graph actions (freq, scenarios):")
    scenarios = summary["proposal_scenarios"]
    for aid, freq in counts.most_common(args.top):
        scn_count = len(scenarios[aid])
        print(f"  {freq:3d}  [{scn_count} scen]  {aid}")

    if args.out:
        render_tsv(summary, args.out)
        print(f"\nWrote full catalog to {args.out}")


if __name__ == "__main__":
    main()
