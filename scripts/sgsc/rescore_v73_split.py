#!/usr/bin/env python3
"""rescore_v73_split.py — Split-reporting rescorer for v7.3 SGSC episodes.

Classifies episodes into Category A/B/M based on vocabulary alignment,
computes filtered C2 for Category M, and generates paper-ready outputs.

Categories:
  A (graph-anchored): ALL expected_actions exist in graph vocabulary → C2 valid
  B (vocab-disconnect): ALL expected_actions are SGSC-invented → C2=0 by design
  M (mixed): some graph-native, some SGSC-invented → filtered C2

Usage:
  PYTHONPATH=. python scripts/sgsc/rescore_v73_split.py
  PYTHONPATH=. python scripts/sgsc/rescore_v73_split.py --results-dir results/v73_full
  PYTHONPATH=. python scripts/sgsc/rescore_v73_split.py --output-dir evidence_pack/analysis
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import glob
import json
import logging
import os
import statistics
import sys

import yaml

logger = logging.getLogger(__name__)

# ── Core graphs (v6 baseline) ──────────────────────────────────────────────
CORE_GRAPHS: set[str] = {
    "acls_cardiac_arrest",
    "kdigo_contrast_aki",
    "aha_stroke_2019",
    "ada_dka_management",
    "ssc_sepsis_hour1_bundle",
    "aha_heart_failure_2022",
    "gina_asthma_exacerbation",
    "pulmonary_embolism",
    "cap_pneumonia",
    "idsa_meningitis",
    "kdigo_aki_full",
    "gi_bleeding",
    "apa_agitation_management",
    "aha_chest_pain_evaluation",
    "anaphylaxis_management",
    "hypertensive_emergency",
    "pals_pediatric_emergency",
    "status_epilepticus",
    "toxicology_management",
    "atrial_fibrillation",
    "copd_exacerbation",
    "aabb_transfusion",
    "aba_burn_resuscitation",
    "acog_obstetric_hemorrhage",
    "universal_clinical_safety",
}


@dataclass
class GraphVocab:
    """All action IDs known to a CPG graph."""

    name: str
    mandatory: set[str] = field(default_factory=set)
    allowed: set[str] = field(default_factory=set)
    forbidden: set[str] = field(default_factory=set)

    @property
    def all_actions(self) -> set[str]:
        return self.mandatory | self.allowed | self.forbidden

    @property
    def is_core(self) -> bool:
        return self.name in CORE_GRAPHS


@dataclass
class EpisodeRecord:
    """Parsed episode with category classification."""

    path: str
    scenario_id: str
    graph: str
    model: str
    is_core: bool
    category: str  # "A", "B", "M"
    expected: list[str]
    performed: list[str]
    matched: list[str]
    match_rate: float
    # Original scores
    cga: float
    c1: float
    c2: float
    c3: float
    c4: float
    c5: float
    c6: float
    n_violations: int
    violations_by_type: dict[str, int]
    # Filtered C2 (for Category M)
    c2_filtered: float | None = None
    n_expected_graph_native: int = 0
    n_expected_sgsc_invented: int = 0


def load_graph_vocabs(graph_dirs: list[str]) -> dict[str, GraphVocab]:
    """Load all graph YAMLs and extract action vocabularies."""
    vocabs: dict[str, GraphVocab] = {}
    for gdir in graph_dirs:
        for gf in glob.glob(os.path.join(gdir, "*.yaml")):
            try:
                with open(gf) as fh:
                    g = yaml.safe_load(fh)
            except Exception:
                continue
            gname = os.path.basename(gf).replace(".yaml", "")
            vocab = GraphVocab(name=gname)
            nodes = g.get("nodes", {})
            if isinstance(nodes, dict):
                for _nid, ndata in nodes.items():
                    if isinstance(ndata, dict):
                        vocab.mandatory.update(ndata.get("mandatory_actions", []))
                        vocab.allowed.update(ndata.get("allowed_actions", []))
                        vocab.forbidden.update(ndata.get("forbidden_actions", []))
            vocabs[gname] = vocab
    return vocabs


def load_sgsc_graph_map(sgsc_dir: str) -> dict[str, str]:
    """Map scenario_id → guideline_graph from SGSC scenario YAMLs."""
    mapping: dict[str, str] = {}
    for f in glob.glob(os.path.join(sgsc_dir, "*.yaml")):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh)
        except Exception:
            continue
        for sid, s in data.get("scenarios", {}).items():
            mapping[sid] = s.get("guideline_graph", "")
    return mapping


def classify_episode(
    expected: set[str],
    graph_vocab: set[str],
) -> tuple[str, int, int]:
    """Classify episode into A/B/M and count graph-native vs SGSC-invented."""
    in_graph = expected & graph_vocab
    not_in_graph = expected - graph_vocab
    n_native = len(in_graph)
    n_invented = len(not_in_graph)

    if n_invented == len(expected):
        return "B", n_native, n_invented
    if n_native == len(expected):
        return "A", n_native, n_invented
    return "M", n_native, n_invented


def compute_filtered_c2(
    expected: list[str],
    performed: set[str],
    graph_vocab: set[str],
) -> float | None:
    """Compute C2 using only graph-native expected_actions."""
    native_expected = [a for a in expected if a in graph_vocab]
    if not native_expected:
        return None
    matched = sum(1 for a in native_expected if a in performed)
    return matched / len(native_expected)


def shorten_model(model: str) -> str:
    """Shorten model name for display."""
    replacements = {
        "Qwen3.5-397B-A17B-FP8": "qwen397b",
        "Qwen3-4B-Instruct-2507": "qwen4b",
        "Qwen3.5-27B": "qwen27b",
        "NVIDIA-Nemotron-3-Nano-30B-A3B-BF16": "nemotron30b",
        "DeepSeek-R1-Distill-Qwen-7B": "deepseek_r1_7b",
        "DeepSeek-R1-0528-Qwen3-8B": "deepseek_r1_7b",
        "gemma-4-31b-it": "gemma31b",
        "gemma-3-27b-it": "gemma27b",
    }
    if "/" in model:
        model = model.split("/")[-1]
    for old, new in replacements.items():
        if old in model:
            return new
    for tag in ["rag_", "_local_baseline", "_baseline"]:
        model = model.replace(tag, "")
    return model


def load_episodes(
    results_dir: str,
    graph_vocabs: dict[str, GraphVocab],
    sgsc_map: dict[str, str],
) -> list[EpisodeRecord]:
    """Load and classify all episode files."""
    records: list[EpisodeRecord] = []
    skipped = 0

    for root, _dirs, files in os.walk(results_dir):
        for f in files:
            if not f.endswith(".json") or f in ("checkpoint.json", "model_summary.json"):
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp) as fh:
                    d = json.load(fh)
            except Exception:
                skipped += 1
                continue

            expected = d.get("expected_actions", [])
            if not expected:
                skipped += 1
                continue

            performed_set = set()
            for a in d.get("actions", []):
                aid = a.get("action_id", "")
                if aid:
                    performed_set.add(aid)

            sid = d.get("scenario_id", "")
            graph_name = sgsc_map.get(sid, "")
            gv = graph_vocabs.get(graph_name)
            g_all = gv.all_actions if gv else set()

            cat, n_native, n_invented = classify_episode(set(expected), g_all)
            matched = sorted(set(expected) & performed_set)
            match_rate = len(matched) / len(expected) if expected else 0.0

            sub = d.get("sub_scores", {})
            model_raw = d.get("model_name", d.get("agent_id", "unknown"))

            c2_filt = None
            if cat == "M":
                c2_filt = compute_filtered_c2(expected, performed_set, g_all)

            rec = EpisodeRecord(
                path=fp,
                scenario_id=sid,
                graph=graph_name,
                model=shorten_model(model_raw),
                is_core=graph_name in CORE_GRAPHS,
                category=cat,
                expected=expected,
                performed=sorted(performed_set),
                matched=matched,
                match_rate=match_rate,
                cga=d.get("compliance_score", -1),
                c1=sub.get("C1_path_selection", -1),
                c2=sub.get("C2_mandatory_completion", -1),
                c3=sub.get("C3_forbidden_avoidance", -1),
                c4=sub.get("C4_timing_compliance", -1),
                c5=sub.get("C5_sequence_integrity", -1),
                c6=sub.get("C6_conflict_avoidance", -1),
                n_violations=d.get("total_violations", 0),
                violations_by_type=d.get("violations_by_type", {}),
                c2_filtered=c2_filt,
                n_expected_graph_native=n_native,
                n_expected_sgsc_invented=n_invented,
            )
            records.append(rec)

    if skipped:
        logger.info("Skipped %d files (no expected_actions or parse error)", skipped)
    return records


# ── Aggregation helpers ────────────────────────────────────────────────────


def _mean(vals: list[float]) -> float | None:
    v = [x for x in vals if x >= 0]
    return round(statistics.mean(v), 4) if v else None


def _median(vals: list[float]) -> float | None:
    v = [x for x in vals if x >= 0]
    return round(statistics.median(v), 4) if v else None


def summarize_group(recs: list[EpisodeRecord]) -> dict:
    """Aggregate stats for a group of episodes."""
    if not recs:
        return {"n": 0}
    return {
        "n": len(recs),
        "cga_mean": _mean([r.cga for r in recs]),
        "cga_median": _median([r.cga for r in recs]),
        "C1_mean": _mean([r.c1 for r in recs]),
        "C2_mean": _mean([r.c2 for r in recs]),
        "C2_filtered_mean": _mean([r.c2_filtered for r in recs if r.c2_filtered is not None]),
        "C3_mean": _mean([r.c3 for r in recs]),
        "C4_mean": _mean([r.c4 for r in recs]),
        "C5_mean": _mean([r.c5 for r in recs]),
        "C6_mean": _mean([r.c6 for r in recs]),
        "match_rate_mean": _mean([r.match_rate for r in recs]),
        "match_rate_median": _median([r.match_rate for r in recs]),
        "pct_zero_match": round(sum(1 for r in recs if r.match_rate < 0.05) / len(recs), 4),
    }


# ── Output generators ─────────────────────────────────────────────────────


def generate_json_artifact(records: list[EpisodeRecord], output_path: str) -> None:
    """Write comprehensive JSON artifact."""
    cat_a = [r for r in records if r.category == "A"]
    cat_b = [r for r in records if r.category == "B"]
    cat_m = [r for r in records if r.category == "M"]

    # Per-model
    model_groups: dict[str, list[EpisodeRecord]] = defaultdict(list)
    for r in records:
        model_groups[r.model].append(r)

    by_model = {}
    for m in sorted(model_groups):
        eps = model_groups[m]
        eps_a = [e for e in eps if e.category == "A"]
        by_model[m] = {
            "all": summarize_group(eps),
            "cat_a": summarize_group(eps_a),
            "cat_b": summarize_group([e for e in eps if e.category == "B"]),
            "cat_m": summarize_group([e for e in eps if e.category == "M"]),
        }

    # Per-graph
    graph_groups: dict[str, list[EpisodeRecord]] = defaultdict(list)
    for r in records:
        graph_groups[r.graph].append(r)

    by_graph = {}
    for g in sorted(graph_groups):
        eps = graph_groups[g]
        by_graph[g] = {
            "is_core": g in CORE_GRAPHS,
            "all": summarize_group(eps),
            "cat_a": summarize_group([e for e in eps if e.category == "A"]),
            "cat_b_pct": round(sum(1 for e in eps if e.category == "B") / len(eps), 4),
        }

    artifact = {
        "audit_date": "2026-05-02",
        "audit_version": "v73_split_rescore_v1",
        "total_episodes": len(records),
        "categories": {
            "A": len(cat_a),
            "B": len(cat_b),
            "M": len(cat_m),
        },
        "overall": summarize_group(records),
        "by_category": {
            "A_graph_anchored": summarize_group(cat_a),
            "B_vocab_disconnect": summarize_group(cat_b),
            "M_mixed": summarize_group(cat_m),
        },
        "by_model": by_model,
        "by_graph": by_graph,
    }

    with open(output_path, "w") as fh:
        json.dump(artifact, fh, indent=2)
    logger.info("JSON artifact: %s (%d bytes)", output_path, os.path.getsize(output_path))


def generate_tex_macros(records: list[EpisodeRecord], output_path: str) -> None:
    """Write LaTeX macros for paper integration."""
    cat_a = [r for r in records if r.category == "A"]
    cat_b = [r for r in records if r.category == "B"]
    cat_m = [r for r in records if r.category == "M"]

    s_all = summarize_group(records)
    s_a = summarize_group(cat_a)
    s_b = summarize_group(cat_b)
    s_m = summarize_group(cat_m)

    lines = [
        "% Auto-generated by rescore_v73_split.py — DO NOT EDIT",
        f"% Date: 2026-05-02 | Episodes: {len(records)}",
        "",
        "% ── v7.3 Episode counts ──",
        f"\\providecommand{{\\vsevenThreeTotal}}{{{len(records)}}}",
        f"\\providecommand{{\\vsevenThreeCatA}}{{{len(cat_a)}}}",
        f"\\providecommand{{\\vsevenThreeCatB}}{{{len(cat_b)}}}",
        f"\\providecommand{{\\vsevenThreeCatM}}{{{len(cat_m)}}}",
        f"\\providecommand{{\\vsevenThreeCatAPct}}{{{len(cat_a) / len(records) * 100:.1f}\\%}}",
        f"\\providecommand{{\\vsevenThreeCatBPct}}{{{len(cat_b) / len(records) * 100:.1f}\\%}}",
        f"\\providecommand{{\\vsevenThreeCatMPct}}{{{len(cat_m) / len(records) * 100:.1f}\\%}}",
        "",
        "% ── Overall scores ──",
        f"\\providecommand{{\\vsevenThreeCGA}}{{{s_all['cga_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeCOne}}{{{s_all['C1_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeCTwo}}{{{s_all['C2_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeCThree}}{{{s_all['C3_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeCFour}}{{{s_all['C4_mean']:.3f}}}",
        "",
        "% ── Category A (graph-anchored, C2 valid) ──",
        f"\\providecommand{{\\vsevenThreeACGA}}{{{s_a['cga_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeACOne}}{{{s_a['C1_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeACTwo}}{{{s_a['C2_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeACThree}}{{{s_a['C3_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeACFour}}{{{s_a['C4_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeAMatch}}{{{s_a['match_rate_mean'] * 100:.1f}\\%}}",
        "",
        "% ── Category B (vocab-disconnect, C2 invalid) ──",
        f"\\providecommand{{\\vsevenThreeBCGA}}{{{s_b['cga_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeBCOne}}{{{s_b['C1_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeBCTwo}}{{{s_b['C2_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeBCThree}}{{{s_b['C3_mean']:.3f}}}",
        "",
        "% ── Category M (mixed, filtered C2) ──",
        f"\\providecommand{{\\vsevenThreeMCGA}}{{{s_m['cga_mean']:.3f}}}",
        f"\\providecommand{{\\vsevenThreeMCTwo}}{{{s_m['C2_mean']:.3f}}}",
    ]

    if s_m.get("C2_filtered_mean") is not None:
        lines.append(f"\\providecommand{{\\vsevenThreeMCTwoFiltered}}{{{s_m['C2_filtered_mean']:.3f}}}")

    # Per-model Cat A macros
    lines.append("")
    lines.append("% ── Per-model Category A scores ──")
    model_groups: dict[str, list[EpisodeRecord]] = defaultdict(list)
    for r in cat_a:
        model_groups[r.model].append(r)
    for m in sorted(model_groups):
        s = summarize_group(model_groups[m])
        tag = m.replace("-", "").replace("_", "").replace(".", "")
        lines.append(f"\\providecommand{{\\vsevenThreeA{tag}CGA}}{{{s['cga_mean']:.3f}}}")
        lines.append(f"\\providecommand{{\\vsevenThreeA{tag}CTwo}}{{{s['C2_mean']:.3f}}}")

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    logger.info("TeX macros: %s (%d macros)", output_path, sum(1 for l in lines if "providecommand" in l))


def print_summary(records: list[EpisodeRecord]) -> None:
    """Print human-readable summary to stdout."""
    cat_a = [r for r in records if r.category == "A"]
    cat_b = [r for r in records if r.category == "B"]
    cat_m = [r for r in records if r.category == "M"]

    print("=" * 72)
    print(f"v7.3 SPLIT RESCORE — {len(records)} episodes, {len(set(r.model for r in records))} models")
    print("=" * 72)

    print(
        f"\nCategories: A={len(cat_a)} ({len(cat_a) / len(records):.1%})  "
        f"B={len(cat_b)} ({len(cat_b) / len(records):.1%})  "
        f"M={len(cat_m)} ({len(cat_m) / len(records):.1%})"
    )

    for label, group in [
        ("A (graph-anchored)", cat_a),
        ("B (vocab-disconnect)", cat_b),
        ("M (mixed)", cat_m),
        ("ALL", records),
    ]:
        s = summarize_group(group)
        if not s["n"]:
            continue
        c2_str = f"{s['C2_mean']:.3f}" if s["C2_mean"] is not None else "N/A"
        c2f_str = ""
        if s.get("C2_filtered_mean") is not None:
            c2f_str = f" C2_filt={s['C2_filtered_mean']:.3f}"
        print(f"\n  {label} (n={s['n']}):")
        print(
            f"    CGA={s['cga_mean']:.3f}  C1={s['C1_mean']:.3f}  C2={c2_str}{c2f_str}"
            f"  C3={s['C3_mean']:.3f}  C4={s['C4_mean']:.3f}  Match={s['match_rate_mean'] * 100:.1f}%"
        )

    # Per-model Category A
    print(f"\n{'─' * 72}")
    print("Per-model — Category A only (C2 valid):")
    model_groups: dict[str, list[EpisodeRecord]] = defaultdict(list)
    for r in cat_a:
        model_groups[r.model].append(r)
    print(f"  {'Model':<20} {'N':>4} {'CGA':>6} {'C2':>6} {'Match%':>7}")
    for m in sorted(model_groups, key=lambda m: -summarize_group(model_groups[m])["cga_mean"]):
        s = summarize_group(model_groups[m])
        print(f"  {m:<20} {s['n']:>4} {s['cga_mean']:>6.3f} {s['C2_mean']:>6.3f} {s['match_rate_mean'] * 100:>6.1f}%")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="v7.3 split-reporting rescorer")
    parser.add_argument("--results-dir", default="results/v73_full", help="Directory containing v7.3 episode JSONs")
    parser.add_argument("--output-dir", default="evidence_pack/analysis", help="Output directory for artifacts")
    parser.add_argument(
        "--graph-dirs",
        nargs="+",
        default=["cpg_model/graphs", "cpg_model/graphs/auto"],
        help="Directories containing graph YAMLs",
    )
    parser.add_argument("--sgsc-dir", default="configs/scenarios/sgsc", help="Directory containing SGSC scenario YAMLs")
    args = parser.parse_args()

    # Load vocabularies
    logger.info("Loading graph vocabularies from %s", args.graph_dirs)
    graph_vocabs = load_graph_vocabs(args.graph_dirs)
    logger.info("Loaded %d graphs", len(graph_vocabs))

    logger.info("Loading SGSC scenario map from %s", args.sgsc_dir)
    sgsc_map = load_sgsc_graph_map(args.sgsc_dir)
    logger.info("Loaded %d scenario→graph mappings", len(sgsc_map))

    # Load and classify episodes
    logger.info("Loading episodes from %s", args.results_dir)
    records = load_episodes(args.results_dir, graph_vocabs, sgsc_map)
    logger.info("Loaded %d episodes", len(records))

    if not records:
        logger.error("No episodes found!")
        sys.exit(1)

    # Print summary
    print_summary(records)

    # Generate artifacts
    os.makedirs(args.output_dir, exist_ok=True)

    json_path = os.path.join(args.output_dir, "v73_split_rescore.json")
    generate_json_artifact(records, json_path)

    tex_path = os.path.join(args.output_dir, "v73_split_macros.tex")
    generate_tex_macros(records, tex_path)

    print("\nArtifacts written:")
    print(f"  {json_path}")
    print(f"  {tex_path}")


if __name__ == "__main__":
    main()
