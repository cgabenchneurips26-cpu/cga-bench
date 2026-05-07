
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""generate_appendix_tables.py -- Generate LaTeX tables for paper appendix.

Produces five appendix tables from existing evidence artifacts:
  U01: Deadline derivation (from CPG graph YAMLs)
  U02: Evidence grading harmonization (static mapping table)
  U03: Normalizer audit details (from cross-validation V7 + encoding audit)
  U07: Forbidden constraint per-graph exposure (graphs + rescored episodes)
  U08: Poster-child episodes (rescored episodes, 9 selected)

Output files (all in evidence_pack/tables/):
  appendix_deadlines.tex
  appendix_evidence_grading.tex
  appendix_normalizer.tex
  appendix_forbidden.tex
  appendix_poster_child.tex

Run:
  PYTHONPATH=. python scripts/experiments/generate_appendix_tables.py
"""

from __future__ import annotations

from collections import defaultdict
import json
import logging
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"
RESCORED_DIR = ROOT / "results" / "clean_slate_rescored"
CROSS_VAL_JSON = ROOT / "evidence_pack" / "cross_validation" / "cross_validation.json"
CROSS_VAL_MD = ROOT / "evidence_pack" / "cross_validation" / "cross_validation.md"
ENCODING_AUDIT = ROOT / "evidence_pack" / "encoding_audit" / "agreement_analysis.json"
TABLES_DIR = ROOT / "evidence_pack" / "tables"

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_DISPLAY = {
    "oss120b": "Qwen2.5-72B",
    "qwen27b": "Q3.5-27B",
    "qwen35b": "Q3.5-35B",
    "qwen4b": "Q3-4B",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tex_escape(text: str) -> str:
    """Escape underscores and special LaTeX characters."""
    return text.replace("_", r"\_").replace("&", r"\&").replace("%", r"\%")


def _tt(text: str) -> str:
    """Wrap in \\texttt with escaped underscores."""
    return rf"\texttt{{{_tex_escape(text)}}}"


def _load_graph(path: Path) -> dict[str, Any]:
    """Load a YAML graph file."""
    with open(path) as fh:
        return yaml.safe_load(fh)


def _load_all_graphs() -> list[tuple[str, dict[str, Any]]]:
    """Load all CPG graph YAMLs, returning (filename, data) pairs sorted."""
    graphs = []
    for yaml_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        data = _load_graph(yaml_path)
        if data and isinstance(data, dict) and "nodes" in data:
            graphs.append((yaml_path.stem, data))
    return graphs


def _load_all_episodes() -> list[dict[str, Any]]:
    """Load all rescored episode JSONs."""
    episodes = []
    for model_dir in sorted(RESCORED_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as fh:
                    ep = json.load(fh)
                ep["_model_dir"] = model_name
                ep["_filename"] = ep_file.name
                episodes.append(ep)
            except (json.JSONDecodeError, OSError):
                log.warning("Skipping unreadable: %s", ep_file)
    return episodes


def _write_tex(filename: str, content: str) -> None:
    """Write LaTeX content to evidence_pack/tables/."""
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TABLES_DIR / filename
    with open(out_path, "w") as fh:
        fh.write(content)
    log.info("Wrote %s (%d bytes)", out_path, len(content))


# ---------------------------------------------------------------------------
# U01: Deadline Derivation Table
# ---------------------------------------------------------------------------


def generate_u01_deadlines() -> None:
    """Generate appendix_deadlines.tex from CPG graph YAMLs."""
    graphs = _load_all_graphs()
    rows: list[str] = []

    for graph_name, data in graphs:
        graph_id = data.get("graph_id", graph_name)
        nodes = data.get("nodes", {})
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            deadlines = node.get("deadlines", {})
            if not deadlines or not isinstance(deadlines, dict):
                continue
            mandatory = set(node.get("mandatory_actions", []))
            rec_class = node.get("recommendation_class", "")
            evidence = node.get("evidence_level", "")
            source = node.get("source_guideline", "")
            source_section = node.get("source_section", "")

            for action_id, deadline_min in sorted(deadlines.items()):
                is_mandatory = action_id in mandatory
                mand_marker = r"$\star$" if is_mandatory else ""
                rows.append(
                    f"{_tt(action_id)} & {_tex_escape(str(graph_id))} & "
                    f"{_tex_escape(source_section)} & {deadline_min} & "
                    f"{rec_class} & {evidence} & {mand_marker} \\\\"
                )

    n_deadlines = len(rows)
    body = "\n".join(rows)

    tex = rf"""\begin{{longtable}}{{lllrcll}}
\caption{{U01: Deadline constraints extracted from all CPG graphs ({n_deadlines} total).
Mandatory actions marked with $\star$.}}
\label{{tab:appendix_deadlines}} \\
\toprule
Action ID & Graph & Source Section & Min & Class & LOE & Mand. \\
\midrule
\endfirsthead
\toprule
Action ID & Graph & Source Section & Min & Class & LOE & Mand. \\
\midrule
\endhead
\bottomrule
\endfoot
{body}
\end{{longtable}}
"""
    _write_tex("appendix_deadlines.tex", tex)
    log.info("U01: %d deadline rows", n_deadlines)


# ---------------------------------------------------------------------------
# U02: Evidence Grading Harmonization
# ---------------------------------------------------------------------------


def generate_u02_evidence_grading() -> None:
    """Generate appendix_evidence_grading.tex (static mapping table)."""
    tex = r"""\begin{table}[ht]
\centering
\small
\caption{U02: Evidence grading harmonization across guideline systems.
Each row maps the source grading system to CGA-Bench's
\emph{guideline-strong} (used for UP\_STRONG) or \emph{moderate} category.}
\label{tab:appendix_evidence_grading}
\begin{tabular}{llll}
\toprule
Grading System & Source Classification & CGA-Bench Category & Notes \\
\midrule
\multicolumn{4}{l}{\textit{AHA/ACC Class/LOE system}} \\
\midrule
AHA/ACC & Class I + Level A & guideline-strong & Highest evidence \\
AHA/ACC & Class I + Level B (B-R, B-NR) & guideline-strong & Randomized or non-randomized \\
AHA/ACC & Class I + Level C (C-LD, C-EO) & moderate & Limited data or expert opinion \\
AHA/ACC & Class IIa + any LOE & moderate & Benefit $>>$ risk \\
AHA/ACC & Class IIb + any LOE & moderate & Benefit $\geq$ risk \\
AHA/ACC & Class III (Harm) + any LOE & guideline-strong & Contraindicated \\
\midrule
\multicolumn{4}{l}{\textit{GRADE system (SSC 2021)}} \\
\midrule
GRADE & Strong + High quality & guideline-strong & \\
GRADE & Strong + Moderate quality & guideline-strong & \\
GRADE & Strong + Low quality & moderate & Strong rec. but weak evidence \\
GRADE & Weak + any quality & moderate & \\
\midrule
\multicolumn{4}{l}{\textit{KDIGO system}} \\
\midrule
KDIGO & Level 1 + Grade A & guideline-strong & \\
KDIGO & Level 1 + Grade B & guideline-strong & \\
KDIGO & Level 1 + Grade C/D & moderate & Strong rec., low evidence \\
KDIGO & Level 2 + any Grade & moderate & Suggestion \\
KDIGO & Not Graded & moderate & Practice point \\
\midrule
\multicolumn{4}{l}{\textit{ADA system (DKA)}} \\
\midrule
ADA & Class I + Level A & guideline-strong & \\
ADA & Class I + Level B & guideline-strong & \\
ADA & Class I + Level C & moderate & Expert consensus \\
ADA & Class II/III + any Level & moderate & \\
ADA & Expert Consensus (E) & moderate & \\
\bottomrule
\end{tabular}
\end{table}
"""
    _write_tex("appendix_evidence_grading.tex", tex)
    log.info("U02: evidence grading harmonization table written")


# ---------------------------------------------------------------------------
# U03: Normalizer Audit Details
# ---------------------------------------------------------------------------


def generate_u03_normalizer() -> None:
    """Generate appendix_normalizer.tex from cross-validation V7 + encoding audit."""
    # Load cross-validation JSON
    with open(CROSS_VAL_JSON) as fh:
        cv_data = json.load(fh)

    v7 = cv_data.get("v7", {})
    known_misses = v7.get("known_misses", [])
    impactful = v7.get("impactful_misses", [])
    non_impactful = v7.get("non_impactful", [])
    episode_analysis = v7.get("episode_level_analysis", {})
    affected_episodes = episode_analysis.get("affected_episodes", 0)
    hardviol_changes = episode_analysis.get("hardviol_changes", 0)
    up_strong_changes = episode_analysis.get("up_strong_changes", 0)

    # Load encoding audit
    encoding_data: dict[str, Any] = {}
    if ENCODING_AUDIT.exists():
        with open(ENCODING_AUDIT) as fh:
            encoding_data = json.load(fh)

    agg = encoding_data.get("aggregate", {})
    precision = agg.get("action_precision", 0)
    type_kappa = agg.get("type_kappa", 0)
    hs_agree = agg.get("hard_soft_agreement_pct", 0)
    type_breakdown = agg.get("type_breakdown", {})

    # Build miss rows
    miss_rows: list[str] = []
    for miss in known_misses:
        agent_form = miss[0]
        expected_form = miss[1]
        # Check if impactful
        is_hard = False
        forbidden_flag = "No"
        deadline_flag = "No"
        before_flag = "No"
        for imp in impactful:
            if imp["agent_form"] == agent_form:
                is_hard = True
                forbidden_flag = "Yes" if imp.get("in_forbidden") else "No"
                deadline_flag = "Yes" if imp.get("in_deadline") else "No"
                before_flag = "Yes" if imp.get("in_before") else "No"
                break

        impact_str = r"\textbf{Yes}" if is_hard else "No"
        miss_rows.append(
            f"{_tt(agent_form)} & {_tt(expected_form)} & "
            f"{forbidden_flag} & {deadline_flag} & {before_flag} & "
            f"{impact_str} \\\\"
        )

    miss_body = "\n".join(miss_rows)

    # Build encoding audit type breakdown rows
    enc_rows: list[str] = []
    for ctype in ("FORBIDDEN", "WITHIN", "MUST", "BEFORE"):
        info = type_breakdown.get(ctype)
        if info:
            total = info.get("total", 0)
            agree = info.get("agree", 0)
            pct = info.get("pct", 0)
            enc_rows.append(
                f"{ctype} & {total} & {agree} & {pct:.0%} \\\\"
            )

    enc_body = "\n".join(enc_rows) if enc_rows else r"— & — & — & — \\"

    tex = rf"""\begin{{table}}[ht]
\centering
\small
\caption{{U03: ActionNormalizer V7 audit --- 8 known misses and their
impact on hard constraints. 1/8 affects a deadline constraint;
rescoring shows 0 HardViol changes across {affected_episodes} affected episodes.}}
\label{{tab:appendix_normalizer}}
\begin{{tabular}}{{llcccc}}
\toprule
Agent Form & Expected Form & Forb. & Dead. & Seq. & Hard Impact \\
\midrule
{miss_body}
\midrule
\multicolumn{{6}}{{l}}{{\textit{{Rescoring impact: {affected_episodes} episodes affected, {hardviol_changes} HardViol changes, {up_strong_changes} UP\_STRONG changes}}}} \\
\bottomrule
\end{{tabular}}
\end{{table}}

\begin{{table}}[ht]
\centering
\small
\caption{{U03b: LLM second-encoder agreement (Qwen3.5-35B).
Concept precision={precision:.1%}, type $\kappa$={type_kappa:.3f},
hard/soft agreement={hs_agree:.0%}.}}
\label{{tab:appendix_normalizer_llm}}
\begin{{tabular}}{{lrrc}}
\toprule
Constraint Type & Total Pairs & Agree & Agreement \\
\midrule
{enc_body}
\bottomrule
\end{{tabular}}
\end{{table}}
"""
    _write_tex("appendix_normalizer.tex", tex)
    log.info("U03: %d normalizer misses, encoding audit included", len(known_misses))


# ---------------------------------------------------------------------------
# U07: Forbidden Constraint Per-Graph Exposure
# ---------------------------------------------------------------------------


def generate_u07_forbidden() -> None:
    """Generate appendix_forbidden.tex showing per-graph forbidden counts
    and triggered commissions from episode data.
    """
    graphs = _load_all_graphs()
    episodes = _load_all_episodes()

    # Count forbidden actions per graph
    graph_forbidden: dict[str, list[str]] = {}
    for graph_name, data in graphs:
        graph_id = data.get("graph_id", graph_name)
        forbidden_set: set[str] = set()
        nodes = data.get("nodes", {})
        for _node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            for fa in node.get("forbidden_actions", []):
                forbidden_set.add(fa)
        graph_forbidden[graph_id] = sorted(forbidden_set)

    # Count commission violations per scenario from episodes
    scenario_commissions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    scenario_episode_count: dict[str, int] = defaultdict(int)
    for ep in episodes:
        sid = ep.get("scenario_id", "")
        scenario_episode_count[sid] += 1
        violations = ep.get("new_violation_events", [])
        for v in violations:
            if v.get("violation_type") == "commission":
                action = v.get("action_involved", "unknown")
                scenario_commissions[sid][action] += 1

    # Build summary rows: one row per graph
    rows: list[str] = []
    total_forbidden = 0
    total_triggered = 0

    for graph_id, forbidden_list in sorted(graph_forbidden.items()):
        n_forbidden = len(forbidden_list)
        total_forbidden += n_forbidden

        # Find which scenarios use this graph
        triggered_actions: set[str] = set()
        triggered_count = 0
        for sid, commissions in scenario_commissions.items():
            for action, count in commissions.items():
                if action in forbidden_list:
                    triggered_actions.add(action)
                    triggered_count += count

        n_triggered = len(triggered_actions)
        total_triggered += n_triggered
        zero_pct = ((n_forbidden - n_triggered) / n_forbidden * 100) if n_forbidden > 0 else 0

        triggered_str = ", ".join(_tt(a) for a in sorted(triggered_actions)) if triggered_actions else "---"
        rows.append(
            f"{_tex_escape(graph_id)} & {n_forbidden} & {n_triggered} & "
            f"{zero_pct:.0f}\\% & {triggered_str} \\\\"
        )

    body = "\n".join(rows)

    tex = rf"""\begin{{table}}[ht]
\centering
\small
\caption{{U07: Forbidden constraint exposure per CPG graph.
Total unique forbidden actions={total_forbidden},
triggered by agents={total_triggered}.}}
\label{{tab:appendix_forbidden}}
\begin{{tabular}}{{lrrrl}}
\toprule
Graph & \#Forbidden & \#Triggered & Zero-exp. & Triggered Actions \\
\midrule
{body}
\midrule
\textbf{{Total}} & {total_forbidden} & {total_triggered} & --- & \\
\bottomrule
\end{{tabular}}
\end{{table}}
"""
    _write_tex("appendix_forbidden.tex", tex)
    log.info("U07: %d graphs, %d total forbidden, %d triggered",
             len(graph_forbidden), total_forbidden, total_triggered)


# ---------------------------------------------------------------------------
# U08: Poster-Child Episodes
# ---------------------------------------------------------------------------


def _has_hard_violation(ep: dict[str, Any]) -> bool:
    """Check if episode has commission, timing, or sequence violations."""
    violations = ep.get("new_violation_events", [])
    hard_types = {"commission", "timing", "sequence"}
    return any(v.get("violation_type") in hard_types for v in violations)


def _violation_summary(ep: dict[str, Any]) -> str:
    """Short summary of violation types and counts."""
    by_type = ep.get("new_violations_by_type", {})
    parts = []
    for vtype in ("commission", "timing", "sequence", "omission", "deviation"):
        count = by_type.get(vtype, 0)
        if count > 0:
            abbrev = vtype[:4].upper()
            parts.append(f"{count}{abbrev}")
    return ", ".join(parts) if parts else "none"


def generate_u08_poster_child() -> None:
    """Generate appendix_poster_child.tex with 9 interesting episodes:
    3 unsafe-pass (high C2 but HardViol),
    3 safe-pass (good scores, no HardViol),
    3 unsafe-fail (low C2 and HardViol).
    """
    episodes = _load_all_episodes()

    # Categorize episodes
    unsafe_pass: list[dict[str, Any]] = []   # high C2 (>=0.7) but has hard violation
    safe_pass: list[dict[str, Any]] = []     # good scores (C2>=0.8), no hard violation
    unsafe_fail: list[dict[str, Any]] = []   # low C2 (<0.5) and has hard violation

    for ep in episodes:
        sub = ep.get("new_sub_scores", {})
        c2 = sub.get("C2_mandatory_completion", 0)
        has_hard = _has_hard_violation(ep)

        if has_hard and c2 >= 0.7:
            unsafe_pass.append(ep)
        elif not has_hard and c2 >= 0.8:
            safe_pass.append(ep)
        elif has_hard and c2 < 0.5:
            unsafe_fail.append(ep)

    # Sort for diversity: prefer different scenarios/models
    def _diversity_key(ep: dict[str, Any]) -> tuple[str, str, int]:
        return (
            ep.get("scenario_id", ""),
            ep.get("_model_dir", ""),
            ep.get("run_index", 0),
        )

    # Select diverse examples: pick from different scenarios when possible
    def _select_diverse(pool: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
        """Select up to n episodes, preferring different scenarios."""
        pool_sorted = sorted(pool, key=_diversity_key)
        selected: list[dict[str, Any]] = []
        seen_scenarios: set[str] = set()
        # First pass: one per scenario
        for ep in pool_sorted:
            sid = ep.get("scenario_id", "")
            if sid not in seen_scenarios and len(selected) < n:
                selected.append(ep)
                seen_scenarios.add(sid)
        # Second pass: fill remaining
        for ep in pool_sorted:
            if ep not in selected and len(selected) < n:
                selected.append(ep)
        return selected[:n]

    TARGET_PER_CATEGORY = 3
    selected_unsafe_pass = _select_diverse(unsafe_pass, TARGET_PER_CATEGORY)
    selected_safe_pass = _select_diverse(safe_pass, TARGET_PER_CATEGORY)
    selected_unsafe_fail = _select_diverse(unsafe_fail, TARGET_PER_CATEGORY)

    # Build LaTeX rows
    def _make_row(ep: dict[str, Any], category: str) -> str:
        sub = ep.get("new_sub_scores", {})
        c1 = sub.get("C1_path_selection", 0)
        c2 = sub.get("C2_mandatory_completion", 0)
        c3 = sub.get("C3_forbidden_avoidance", 0)
        c4 = sub.get("C4_timing_compliance", 0)
        c5 = sub.get("C5_sequence_integrity", 0)
        scenario = ep.get("scenario_id", "?")
        model = MODEL_DISPLAY.get(ep.get("_model_dir", ""), ep.get("_model_dir", "?"))
        run = ep.get("run_index", 0)
        viol_sum = _violation_summary(ep)

        return (
            f"{_tex_escape(scenario)} & {model} & r{run} & "
            f"{c1:.2f} & {c2:.2f} & {c3:.2f} & {c4:.2f} & {c5:.2f} & "
            f"{_tex_escape(viol_sum)} & {category} \\\\"
        )

    row_lines: list[str] = []

    if selected_unsafe_pass:
        row_lines.append(r"\multicolumn{10}{l}{\textit{Unsafe-pass: C2 $\geq$ 0.7 but hard violation present}} \\")
        row_lines.append(r"\midrule")
        for ep in selected_unsafe_pass:
            row_lines.append(_make_row(ep, "UP"))
        row_lines.append(r"\midrule")

    if selected_safe_pass:
        row_lines.append(r"\multicolumn{10}{l}{\textit{Safe-pass: C2 $\geq$ 0.8, no hard violation}} \\")
        row_lines.append(r"\midrule")
        for ep in selected_safe_pass:
            row_lines.append(_make_row(ep, "SP"))
        row_lines.append(r"\midrule")

    if selected_unsafe_fail:
        row_lines.append(r"\multicolumn{10}{l}{\textit{Unsafe-fail: C2 $<$ 0.5 with hard violation}} \\")
        row_lines.append(r"\midrule")
        for ep in selected_unsafe_fail:
            row_lines.append(_make_row(ep, "UF"))

    body = "\n".join(row_lines)

    n_total = len(selected_unsafe_pass) + len(selected_safe_pass) + len(selected_unsafe_fail)
    tex = rf"""\begin{{table}}[ht]
\centering
\small
\caption{{U08: Poster-child episodes ({n_total} selected).
UP=unsafe-pass (high C2 but hard violation),
SP=safe-pass (good scores),
UF=unsafe-fail (low C2 with hard violation).}}
\label{{tab:appendix_poster_child}}
\begin{{tabular}}{{@{{}}llcrrrrrlc@{{}}}}
\toprule
Scenario & Model & Run & C1 & C2 & C3 & C4 & C5 & Violations & Cat. \\
\midrule
{body}
\bottomrule
\end{{tabular}}
\end{{table}}
"""
    _write_tex("appendix_poster_child.tex", tex)
    log.info(
        "U08: %d UP, %d SP, %d UF (from %d/%d/%d pools)",
        len(selected_unsafe_pass),
        len(selected_safe_pass),
        len(selected_unsafe_fail),
        len(unsafe_pass),
        len(safe_pass),
        len(unsafe_fail),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Generate all 5 appendix tables."""
    log.info("Generating appendix tables...")
    log.info("ROOT: %s", ROOT)

    generate_u01_deadlines()
    generate_u02_evidence_grading()
    generate_u03_normalizer()
    generate_u07_forbidden()
    generate_u08_poster_child()

    log.info("All appendix tables generated in %s", TABLES_DIR)


if __name__ == "__main__":
    main()
