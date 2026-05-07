#!/usr/bin/env python3
"""Reproduce HealthBench 50-sample overclassification audit.

Stratified random sampling (25 discordant + 25 concordant) from the 5,000
HealthBench evaluation episodes.  For each sample the script replays both
the old substring classifier and the new word-boundary classifier, records
which keywords triggered, and auto-categorises false-positive patterns.

Outputs
-------
- evidence_pack/sampling/healthbench_50sample_audit.json
- evidence_pack/sampling/healthbench_50sample_audit.csv
- evidence_pack/tables/healthbench_overclassification_breakdown.tex

Usage
-----
    PYTHONPATH=. python scripts/experiments/reproduce_healthbench_audit.py
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
import re
import sys
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent))

HEALTHBENCH_EVAL_URL = (
    "https://huggingface.co/datasets/openai/healthbench/resolve/main/"
    "2025-05-07-06-14-12_oss_eval.jsonl"
)

RANDOM_SEED = 20260331
DISCORDANCE_THRESHOLD = 0.10

ACTION_KEYWORDS: list[str] = [
    "order",
    "prescribe",
    "administer",
    "perform",
    "initiate",
    "start",
    "give",
    "refer",
    "obtain",
    "measure",
    "check",
    "draw",
    "send",
]

EXPLANATION_KEYWORDS: list[str] = [
    "explain",
    "counsel",
    "educate",
    "inform",
    "discuss",
    "rationale",
]

NEGATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:should\s+not|must\s+not|do\s+not|don'?t|cannot|never)\b.*\b(" + kw + r")\b", re.IGNORECASE)
    for kw in ACTION_KEYWORDS
]

CONDITIONAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:depends?\s+on|if\s+|whether|contingent|based\s+on)\b.*\b(" + kw + r")\b",
        re.IGNORECASE,
    )
    for kw in ACTION_KEYWORDS
]


# ---------------------------------------------------------------------------
# Classifier variants
# ---------------------------------------------------------------------------

def classify_substring(text: str) -> tuple[str, list[str]]:
    """Old classifier: plain substring match (pre-fix)."""
    lower = text.lower()
    matched: list[str] = []
    for kw in ACTION_KEYWORDS:
        if kw in lower:
            matched.append(kw)
    if matched:
        return "ACTION", matched

    for kw in EXPLANATION_KEYWORDS:
        if kw in lower:
            return "EXPLANATION", [kw]

    return "ASSESSMENT", []


def classify_word_boundary(text: str) -> tuple[str, list[str]]:
    """New classifier: word-boundary regex (current production)."""
    lower = text.lower()
    matched: list[str] = []
    for kw in ACTION_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", lower):
            matched.append(kw)
    if matched:
        return "ACTION", matched

    for kw in EXPLANATION_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", lower):
            return "EXPLANATION", [kw]

    return "ASSESSMENT", []


# ---------------------------------------------------------------------------
# FP auto-categorisation
# ---------------------------------------------------------------------------

def _detect_negation_context(text: str, triggered_kws: list[str]) -> bool:
    """Check if triggered keywords appear in negation context."""
    lower = text.lower()
    for pat in NEGATION_PATTERNS:
        m = pat.search(lower)
        if m and m.group(1) in triggered_kws:
            return True
    return False


def _detect_conditional_context(text: str, triggered_kws: list[str]) -> bool:
    """Check if triggered keywords appear in conditional context."""
    lower = text.lower()
    for pat in CONDITIONAL_PATTERNS:
        m = pat.search(lower)
        if m and m.group(1) in triggered_kws:
            return True
    return False


def _detect_substring_fp(
    text: str,
    old_kws: list[str],
    new_kws: list[str],
) -> bool:
    """Keyword matched by substring but not by word-boundary."""
    return len(old_kws) > len(new_kws)


def _detect_domain_misattribution(text: str) -> bool:
    """Rubric is about factual accuracy / communication, not clinical action."""
    lower = text.lower()
    non_action_signals = [
        "judge whether",
        "factual accuracy",
        "communication quality",
        "accurately describes",
        "correctly identifies",
        "appropriate tone",
        "empathetic",
        "clearly explains",
    ]
    return any(sig in lower for sig in non_action_signals)


def _detect_granularity_mismatch(text: str) -> bool:
    """Rubric describes high-level guidance, not a concrete clinical order."""
    lower = text.lower()
    mismatch_signals = [
        "mentions that",
        "emphasizes",
        "acknowledges",
        "recognizes",
        "discusses the importance",
        "notes that",
        "addresses",
    ]
    return any(sig in lower for sig in mismatch_signals)


def auto_categorise_rubric(
    text: str,
    old_result: str,
    new_result: str,
    old_kws: list[str],
    new_kws: list[str],
) -> str:
    """Auto-categorise a rubric into one of the FP taxonomy categories.

    Returns one of:
        true_action, true_discordant, keyword_false_positive,
        negation_context, conditional_context, domain_misattribution,
        granularity_mismatch, substring_artifact
    """
    if old_result != "ACTION" and new_result != "ACTION":
        return "true_assessment"

    if old_result == "ACTION" and new_result != "ACTION":
        if _detect_substring_fp(text, old_kws, new_kws):
            return "substring_artifact"
        return "keyword_false_positive"

    if new_result == "ACTION":
        if _detect_negation_context(text, new_kws):
            return "negation_context"
        if _detect_conditional_context(text, new_kws):
            return "conditional_context"
        if _detect_domain_misattribution(text):
            return "domain_misattribution"
        if _detect_granularity_mismatch(text):
            return "granularity_mismatch"
        # Check if it looks like a genuine clinical action imperative
        imperative_patterns = [
            r"^(?:order|prescribe|administer|perform|give|refer|obtain|start|check|measure|draw|send)\b",
            r"\bshould\s+(?:order|prescribe|administer|perform|give|refer|obtain|start|check|measure)\b",
            r"\brecommend(?:s|ed)?\s+(?:ordering|prescribing|performing|giving|referring|starting|checking)\b",
            r"\badvise(?:s|d)?\s+(?:the\s+(?:user|patient)\s+)?to\s+(?:order|prescribe|give|take|start|get|see)\b",
            r"\bsuggest(?:s|ed)?\s+(?:the\s+(?:user|patient)\s+)?(?:order|prescribe|give|take|start|get|see)\b",
            r"\bsuggest(?:s|ed)?\s+(?:that\s+)?(?:the\s+(?:user|patient)\s+)?(?:order|prescribe|give|take|start|get|see)\b",
        ]
        lower = text.lower().strip()
        for pat in imperative_patterns:
            if re.search(pat, lower):
                return "true_action"
        return "keyword_false_positive"

    return "true_assessment"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_healthbench_rows(limit: int | None = None) -> list[dict]:
    """Load HealthBench eval rows from HuggingFace."""
    logger.info("Downloading HealthBench eval data from HuggingFace ...")
    data = urllib.request.urlopen(HEALTHBENCH_EVAL_URL).read().decode()
    lines = data.strip().split("\n")
    logger.info("Downloaded %d rows", len(lines))
    if limit is not None:
        lines = lines[:limit]
    return [json.loads(line) for line in lines]


def load_result_shards() -> list[dict]:
    """Load pre-computed evaluation result shards."""
    shards: list[dict] = []
    shard_paths = [
        PROJECT_ROOT / "results" / "healthbench_sample_1000.json",
        PROJECT_ROOT / "results" / "healthbench_shard2_2000.json",
        PROJECT_ROOT / "results" / "healthbench_shard3_2000.json",
    ]
    for path in shard_paths:
        if path.exists():
            with open(path) as fh:
                shards.extend(json.load(fh))
    return shards


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def select_stratified_sample(
    results: list[dict],
    n_discordant: int = 25,
    n_concordant: int = 25,
    seed: int = RANDOM_SEED,
) -> tuple[list[int], list[int]]:
    """Select stratified indices: discordant vs concordant episodes.

    Discordance is defined as abs(rubric_track_a - native_normalized) > threshold.
    """
    import random

    rng = random.Random(seed)

    discordant_indices: list[int] = []
    concordant_indices: list[int] = []

    for i, r in enumerate(results):
        cga = r.get("rubric_track_a", 0.0)
        native = r.get("native_normalized", 0.0)
        diff = abs(cga - native)
        if diff > DISCORDANCE_THRESHOLD:
            discordant_indices.append(i)
        else:
            concordant_indices.append(i)

    logger.info(
        "Population: %d discordant, %d concordant (threshold=%.2f)",
        len(discordant_indices),
        len(concordant_indices),
        DISCORDANCE_THRESHOLD,
    )

    sampled_disc = rng.sample(
        discordant_indices, min(n_discordant, len(discordant_indices))
    )
    sampled_conc = rng.sample(
        concordant_indices, min(n_concordant, len(concordant_indices))
    )
    return sorted(sampled_disc), sorted(sampled_conc)


# ---------------------------------------------------------------------------
# Audit per rubric
# ---------------------------------------------------------------------------

def audit_single_rubric(
    rubric: dict,
    episode_idx: int,
    rubric_idx: int,
    prompt_id: str,
) -> dict:
    """Classify a single rubric with both old and new classifiers."""
    text = rubric.get("criterion", rubric.get("text", ""))
    points = rubric.get("points", 0)
    tags = rubric.get("tags", [])

    old_result, old_kws = classify_substring(text)
    new_result, new_kws = classify_word_boundary(text)
    category = auto_categorise_rubric(text, old_result, new_result, old_kws, new_kws)

    return {
        "episode_idx": episode_idx,
        "prompt_id": prompt_id,
        "rubric_idx": rubric_idx,
        "rubric_text": text,
        "points": points,
        "tags": tags,
        "old_classifier_result": old_result,
        "old_triggered_keywords": old_kws,
        "new_classifier_result": new_result,
        "new_triggered_keywords": new_kws,
        "classifier_changed": old_result != new_result,
        "auto_category": category,
        "manual_review_label": "",
        "manual_review_reasoning": "",
    }


def audit_episode(
    hb_row: dict,
    result_row: dict,
    episode_idx: int,
    stratum: str,
) -> dict:
    """Full audit of one episode: classify all rubrics."""
    prompt_id = hb_row.get("prompt_id", result_row.get("prompt_id", "unknown"))
    rubrics = hb_row.get("rubrics", [])

    rubric_audits: list[dict] = []
    for ri, rubric in enumerate(rubrics):
        rubric_audits.append(
            audit_single_rubric(rubric, episode_idx, ri, prompt_id)
        )

    n_old_action = sum(1 for ra in rubric_audits if ra["old_classifier_result"] == "ACTION")
    n_new_action = sum(1 for ra in rubric_audits if ra["new_classifier_result"] == "ACTION")
    n_changed = sum(1 for ra in rubric_audits if ra["classifier_changed"])

    category_counts: dict[str, int] = {}
    for ra in rubric_audits:
        cat = ra["auto_category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    prompt_turns = hb_row.get("prompt", [])
    prompt_preview = ""
    for turn in prompt_turns:
        if isinstance(turn, dict) and turn.get("role") == "user":
            prompt_preview = str(turn.get("content", ""))[:200]
            break

    return {
        "episode_idx": episode_idx,
        "prompt_id": prompt_id,
        "stratum": stratum,
        "prompt_preview": prompt_preview,
        "n_rubrics": len(rubrics),
        "n_old_action": n_old_action,
        "n_new_action": n_new_action,
        "n_classifier_changed": n_changed,
        "rubric_track_a": result_row.get("rubric_track_a", 0.0),
        "native_normalized": result_row.get("native_normalized", 0.0),
        "discordance": round(
            abs(
                result_row.get("rubric_track_a", 0.0)
                - result_row.get("native_normalized", 0.0)
            ),
            4,
        ),
        "category_counts": category_counts,
        "rubric_details": rubric_audits,
    }


# ---------------------------------------------------------------------------
# Aggregation and outputs
# ---------------------------------------------------------------------------

def aggregate_overclassification(
    episodes: list[dict],
) -> dict[str, dict]:
    """Aggregate FP categories across all rubric audits."""
    counts: dict[str, int] = {}
    examples: dict[str, str] = {}
    total_rubrics = 0

    for ep in episodes:
        for ra in ep.get("rubric_details", []):
            total_rubrics += 1
            cat = ra["auto_category"]
            counts[cat] = counts.get(cat, 0) + 1
            if cat not in examples:
                text = ra["rubric_text"]
                snippet = text[:80].replace('"', "'")
                examples[cat] = snippet

    table: dict[str, dict] = {}
    for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
        table[cat] = {
            "count": count,
            "pct": round(count / max(total_rubrics, 1) * 100, 1),
            "example": examples.get(cat, ""),
        }
    table["_total_rubrics"] = {"count": total_rubrics, "pct": 100.0, "example": ""}
    return table


def write_json_output(
    episodes: list[dict],
    overclassification: dict[str, dict],
    out_path: Path,
) -> None:
    """Write the full JSON audit report."""
    meta = {
        "audit_id": "healthbench_50sample_audit",
        "seed": RANDOM_SEED,
        "discordance_threshold": DISCORDANCE_THRESHOLD,
        "n_discordant_sampled": sum(1 for e in episodes if e["stratum"] == "discordant"),
        "n_concordant_sampled": sum(1 for e in episodes if e["stratum"] == "concordant"),
        "total_episodes": len(episodes),
        "action_keywords": ACTION_KEYWORDS,
        "explanation_keywords": EXPLANATION_KEYWORDS,
        "limitation": (
            "Single-reviewer automated categorisation only. "
            "manual_review_label and manual_review_reasoning fields are empty, "
            "awaiting human annotation. Inter-rater reliability (Krippendorff alpha) "
            "requires at least two independent reviewers and is planned as future work."
        ),
    }

    payload = {
        "metadata": meta,
        "overclassification_breakdown": overclassification,
        "episodes": episodes,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    logger.info("Wrote JSON: %s (%d episodes)", out_path, len(episodes))


def write_csv_output(episodes: list[dict], out_path: Path) -> None:
    """Write flat CSV for human reviewer."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "episode_idx",
        "prompt_id",
        "stratum",
        "rubric_idx",
        "rubric_text",
        "points",
        "tags",
        "old_classifier_result",
        "old_triggered_keywords",
        "new_classifier_result",
        "new_triggered_keywords",
        "classifier_changed",
        "auto_category",
        "manual_review_label",
        "manual_review_reasoning",
    ]
    total_rows = 0
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for ep in episodes:
            for ra in ep.get("rubric_details", []):
                row = {
                    **ra,
                    "stratum": ep["stratum"],
                    "tags": "; ".join(ra.get("tags", [])),
                    "old_triggered_keywords": ", ".join(ra.get("old_triggered_keywords", [])),
                    "new_triggered_keywords": ", ".join(ra.get("new_triggered_keywords", [])),
                }
                writer.writerow(row)
                total_rows += 1
    logger.info("Wrote CSV: %s (%d rubric rows)", out_path, total_rows)


def write_latex_table(overclassification: dict[str, dict], out_path: Path) -> None:
    """Generate LaTeX overclassification breakdown table."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fp_categories = [
        "keyword_false_positive",
        "negation_context",
        "conditional_context",
        "substring_artifact",
        "domain_misattribution",
        "granularity_mismatch",
    ]
    non_fp_categories = [
        "true_action",
        "true_assessment",
    ]

    total_info = overclassification.get("_total_rubrics", {})
    total_n = total_info.get("count", 0)

    lines: list[str] = [
        r"\begin{table}[ht]",
        r"\centering",
        rf"\caption{{HealthBench rubric overclassification breakdown (50-episode audit, $N={total_n}$ rubrics).}}",
        r"\label{tab:healthbench_overclassification}",
        r"\begin{tabular}{l r r p{5.5cm}}",
        r"\toprule",
        r"\textbf{Category} & \textbf{Count} & \textbf{\%} & \textbf{Example} \\",
        r"\midrule",
    ]

    for cat in fp_categories:
        info = overclassification.get(cat, {"count": 0, "pct": 0.0, "example": ""})
        count = info["count"]
        pct = info["pct"]
        example = _latex_escape(info["example"][:60])
        label = cat.replace("_", r"\_")
        lines.append(f"  {label} & {count} & {pct}\\% & \\textit{{{example}}} \\\\")

    lines.append(r"\midrule")

    for cat in non_fp_categories:
        info = overclassification.get(cat, {"count": 0, "pct": 0.0, "example": ""})
        count = info["count"]
        pct = info["pct"]
        label = cat.replace("_", r"\_")
        lines.append(f"  {label} & {count} & {pct}\\% & --- \\\\")

    lines.append(r"\midrule")
    lines.append(f"  \\textbf{{Total}} & \\textbf{{{total_n}}} & \\textbf{{100.0\\%}} & \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")

    with open(out_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    logger.info("Wrote LaTeX: %s", out_path)


def _latex_escape(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the 50-sample reproducible audit."""
    logger.info("=== HealthBench 50-Sample Reproducible Audit ===")
    logger.info("Seed: %d, Discordance threshold: %.2f", RANDOM_SEED, DISCORDANCE_THRESHOLD)

    # Step 1: Load pre-computed results for stratification
    results = load_result_shards()
    if not results:
        logger.error("No result shards found. Run e2e_healthbench.py first.")
        sys.exit(1)
    logger.info("Loaded %d result rows from shards", len(results))

    # Step 2: Stratified sampling
    disc_indices, conc_indices = select_stratified_sample(results)
    all_indices = sorted(set(disc_indices + conc_indices))
    logger.info(
        "Selected %d discordant + %d concordant = %d episodes",
        len(disc_indices),
        len(conc_indices),
        len(all_indices),
    )

    # Step 3: Load raw HuggingFace data for rubric texts
    hb_rows = load_healthbench_rows()

    if len(hb_rows) < max(all_indices):
        logger.error(
            "HuggingFace data has %d rows but need index %d",
            len(hb_rows),
            max(all_indices),
        )
        sys.exit(1)

    # Step 4: Audit each sampled episode
    disc_set = set(disc_indices)
    conc_set = set(conc_indices)
    audited_episodes: list[dict] = []

    for idx in all_indices:
        stratum = "discordant" if idx in disc_set else "concordant"
        ep = audit_episode(hb_rows[idx], results[idx], idx, stratum)
        audited_episodes.append(ep)

    # Step 5: Aggregate
    overclassification = aggregate_overclassification(audited_episodes)

    # Step 6: Summary stats
    total_rubrics = sum(ep["n_rubrics"] for ep in audited_episodes)
    total_old_action = sum(ep["n_old_action"] for ep in audited_episodes)
    total_new_action = sum(ep["n_new_action"] for ep in audited_episodes)
    total_changed = sum(ep["n_classifier_changed"] for ep in audited_episodes)

    logger.info("--- Audit Summary ---")
    logger.info("Episodes audited: %d", len(audited_episodes))
    logger.info("Total rubrics: %d", total_rubrics)
    logger.info(
        "Old classifier ACTION: %d (%.1f%%)",
        total_old_action,
        total_old_action / max(total_rubrics, 1) * 100,
    )
    logger.info(
        "New classifier ACTION: %d (%.1f%%)",
        total_new_action,
        total_new_action / max(total_rubrics, 1) * 100,
    )
    logger.info(
        "Classifier changed: %d (%.1f%%)",
        total_changed,
        total_changed / max(total_rubrics, 1) * 100,
    )

    for cat, info in overclassification.items():
        if cat.startswith("_"):
            continue
        logger.info("  %-30s %4d (%5.1f%%)", cat, info["count"], info["pct"])

    # Step 7: Write outputs
    json_out = PROJECT_ROOT / "evidence_pack" / "sampling" / "healthbench_50sample_audit.json"
    csv_out = PROJECT_ROOT / "evidence_pack" / "sampling" / "healthbench_50sample_audit.csv"
    tex_out = PROJECT_ROOT / "evidence_pack" / "tables" / "healthbench_overclassification_breakdown.tex"

    write_json_output(audited_episodes, overclassification, json_out)
    write_csv_output(audited_episodes, csv_out)
    write_latex_table(overclassification, tex_out)

    logger.info("=== Audit complete ===")


if __name__ == "__main__":
    main()
