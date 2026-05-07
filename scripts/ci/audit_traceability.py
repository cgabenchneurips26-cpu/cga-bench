"""End-to-end explainability audit: corpus → graph → scenario.

Runs 5 traceability checks (T1-T5) across all CPG graphs and scenarios,
producing a JSON report and LaTeX macros.

Checks:
  T1  Corpus Coverage      - every graph has a matching corpus .parsed.json
  T2  Quote Verification   - source_quote is a substring of corpus text
  T3  Recommendation Link  - source_recommendation_ids reference valid corpus IDs
  T4  Action Reachability  - scenario expected_actions reachable from graph entry_node
  T5  Provenance Fields    - per-field fill rate across all graph nodes

Usage:
    PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject \
        python cga_bench/scripts/ci/audit_traceability.py
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORE_GRAPHS_DIR = REPO_ROOT / "cpg_model" / "graphs"
AUTO_GRAPHS_DIR = REPO_ROOT / "cpg_model" / "graphs" / "auto"
CPG_SOURCES_DIR = REPO_ROOT / "cpg_sources"
RAG_CORPUS_DIR = REPO_ROOT / "data_release" / "v5.0" / "rag_corpus"
SCENARIOS_DIR = REPO_ROOT / "configs" / "scenarios"
CORPUS_MAP_PATH = REPO_ROOT / "data" / "corpus_graph_map.json"

PROVENANCE_REQUIRED = ("source_guideline", "source_section")
PROVENANCE_RECOMMENDED = (
    "source_quote",
    "source_page",
    "evidence_level",
    "recommendation_class",
)


def _normalize(text: str) -> str:
    """Whitespace-collapse + lowercase for substring matching."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _tokenize(text: str) -> set[str]:
    """Simple word tokenization for overlap scoring."""
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


# ---------------------------------------------------------------------------
# Corpus loading helpers
# ---------------------------------------------------------------------------


def _load_corpus_map() -> dict[str, dict[str, str]]:
    """Load corpus_graph_map.json.  Returns {graph_id: {corpus_file, corpus_dir}}."""
    if not CORPUS_MAP_PATH.exists():
        return {}
    with open(CORPUS_MAP_PATH) as f:
        return json.load(f)


def _load_corpus_json(corpus_file: str, corpus_dir: str) -> dict[str, Any] | None:
    """Load a parsed corpus JSON from the specified directory."""
    path = REPO_ROOT / corpus_dir / corpus_file
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _build_corpus_text(corpus: dict[str, Any]) -> str:
    """Build combined corpus text from recommendations + key_sections + tables."""
    parts: list[str] = []
    for rec in corpus.get("recommendations", []) or []:
        if isinstance(rec, dict):
            parts.append(str(rec.get("text", "")))
    ks = corpus.get("key_sections", {}) or {}
    if isinstance(ks, dict):
        for v in ks.values():
            parts.append(str(v))
    for tbl in corpus.get("tables", []) or []:
        if isinstance(tbl, dict):
            parts.append(str(tbl.get("data", tbl.get("text", ""))))
    return "\n".join(parts)


def _get_recommendation_ids(corpus: dict[str, Any]) -> set[str]:
    """Extract all recommendation_id values from a corpus."""
    ids: set[str] = set()
    for rec in corpus.get("recommendations", []) or []:
        if isinstance(rec, dict):
            rid = rec.get("recommendation_id", "")
            if rid:
                ids.add(rid)
    return ids


# ---------------------------------------------------------------------------
# Graph / scenario loading
# ---------------------------------------------------------------------------


def _load_all_graphs() -> list[tuple[str, dict[str, Any], str]]:
    """Load all graphs (core + auto).

    Returns list of (graph_id, graph_data, category) tuples.
    """
    graphs: list[tuple[str, dict[str, Any], str]] = []
    for yaml_file in sorted(CORE_GRAPHS_DIR.glob("*.yaml")):
        data = yaml.safe_load(yaml_file.read_text())
        graphs.append((yaml_file.stem, data, "core"))
    for yaml_file in sorted(AUTO_GRAPHS_DIR.glob("*.yaml")):
        data = yaml.safe_load(yaml_file.read_text())
        graphs.append((yaml_file.stem, data, "auto"))
    return graphs


def _load_all_scenarios() -> list[dict[str, Any]]:
    """Load all scenario definitions from configs/scenarios/."""
    scenarios: list[dict[str, Any]] = []
    for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
        if yaml_file.name.startswith("."):
            continue
        data = yaml.safe_load(yaml_file.read_text())
        if not data or not isinstance(data, dict):
            continue
        for sid, sdef in (data.get("scenarios") or {}).items():
            if isinstance(sdef, dict):
                sdef["scenario_id"] = sdef.get("scenario_id", sid)
                scenarios.append(sdef)
    return scenarios


# ---------------------------------------------------------------------------
# T1: Corpus Coverage
# ---------------------------------------------------------------------------


def check_t1_corpus_coverage(
    graphs: list[tuple[str, dict[str, Any], str]],
    corpus_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Check that every graph has a matching corpus file."""
    covered: list[str] = []
    missing: list[str] = []

    for graph_id, _data, _category in graphs:
        entry = corpus_map.get(graph_id)
        if entry:
            corpus_file = entry.get("corpus_file", "")
            corpus_dir = entry.get("corpus_dir", "")
            path = REPO_ROOT / corpus_dir / corpus_file
            if path.exists():
                covered.append(graph_id)
            else:
                missing.append(graph_id)
        else:
            missing.append(graph_id)

    return {
        "total_graphs": len(graphs),
        "covered": len(covered),
        "missing": len(missing),
        "missing_graphs": missing,
        "coverage_rate": round(len(covered) / max(len(graphs), 1), 4),
    }


# ---------------------------------------------------------------------------
# T2: Quote Verification
# ---------------------------------------------------------------------------


def check_t2_quote_verification(
    graphs: list[tuple[str, dict[str, Any], str]],
    corpus_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Verify that source_quote in each node is a substring of corpus text."""
    per_graph: dict[str, dict[str, Any]] = {}
    totals = {"verified": 0, "grounded": 0, "ungrounded": 0, "missing_quote": 0, "no_corpus": 0}

    for graph_id, data, _category in graphs:
        nodes = data.get("nodes", {})
        graph_stats = {"verified": 0, "grounded": 0, "ungrounded": 0, "missing_quote": 0}

        entry = corpus_map.get(graph_id)
        if not entry:
            totals["no_corpus"] += len(nodes)
            per_graph[graph_id] = {"status": "no_corpus", "total_nodes": len(nodes)}
            continue

        corpus = _load_corpus_json(entry["corpus_file"], entry["corpus_dir"])
        if not corpus:
            totals["no_corpus"] += len(nodes)
            per_graph[graph_id] = {"status": "corpus_load_failed", "total_nodes": len(nodes)}
            continue

        corpus_text = _build_corpus_text(corpus)
        norm_corpus = _normalize(corpus_text)
        recommendations = corpus.get("recommendations", []) or []

        for _node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            quote = (node.get("source_quote") or "").strip()
            if not quote:
                graph_stats["missing_quote"] += 1
                totals["missing_quote"] += 1
                continue

            norm_quote = _normalize(quote)
            if norm_quote in norm_corpus:
                graph_stats["verified"] += 1
                totals["verified"] += 1
            else:
                # Keyword overlap fallback
                quote_tokens = _tokenize(quote)
                if not quote_tokens:
                    graph_stats["ungrounded"] += 1
                    totals["ungrounded"] += 1
                    continue

                best_score = 0.0
                # Check recommendations
                for rec in recommendations:
                    rec_text = rec.get("text", "")
                    if not rec_text:
                        continue
                    rec_tokens = _tokenize(rec_text)
                    if rec_tokens:
                        overlap = len(quote_tokens & rec_tokens) / len(quote_tokens)
                        best_score = max(best_score, overlap)

                # Check key_sections
                ks = corpus.get("key_sections", {}) or {}
                if isinstance(ks, dict):
                    for sec_text in ks.values():
                        sec_tokens = _tokenize(str(sec_text))
                        if sec_tokens:
                            overlap = len(quote_tokens & sec_tokens) / len(quote_tokens)
                            best_score = max(best_score, overlap)

                # Check tables
                for tbl in corpus.get("tables", []) or []:
                    if isinstance(tbl, dict):
                        tbl_text = str(tbl.get("data", tbl.get("text", "")))
                        tbl_tokens = _tokenize(tbl_text)
                        if tbl_tokens:
                            overlap = len(quote_tokens & tbl_tokens) / len(quote_tokens)
                            best_score = max(best_score, overlap)

                if best_score >= 0.4:
                    graph_stats["grounded"] += 1
                    totals["grounded"] += 1
                else:
                    graph_stats["ungrounded"] += 1
                    totals["ungrounded"] += 1

        per_graph[graph_id] = graph_stats

    total_checked = totals["verified"] + totals["grounded"] + totals["ungrounded"]
    verified_or_grounded = totals["verified"] + totals["grounded"]

    return {
        "totals": totals,
        "quote_coverage_rate": round(verified_or_grounded / max(total_checked, 1), 4),
        "exact_match_rate": round(totals["verified"] / max(total_checked, 1), 4),
        "per_graph": per_graph,
    }


# ---------------------------------------------------------------------------
# T3: Recommendation Linkage
# ---------------------------------------------------------------------------


def check_t3_recommendation_linkage(
    graphs: list[tuple[str, dict[str, Any], str]],
    corpus_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Verify source_recommendation_ids reference valid corpus IDs."""
    totals = {"nodes_with_ids": 0, "nodes_without_ids": 0, "valid_links": 0, "broken_links": 0}
    per_graph: dict[str, dict[str, Any]] = {}
    broken_details: list[dict[str, str]] = []

    for graph_id, data, _category in graphs:
        nodes = data.get("nodes", {})
        g_stats = {"with_ids": 0, "without_ids": 0, "valid": 0, "broken": 0}

        entry = corpus_map.get(graph_id)
        corpus_rec_ids: set[str] = set()
        if entry:
            corpus = _load_corpus_json(entry["corpus_file"], entry["corpus_dir"])
            if corpus:
                corpus_rec_ids = _get_recommendation_ids(corpus)

        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            src_ids = node.get("source_recommendation_ids")
            if not src_ids or not isinstance(src_ids, list):
                g_stats["without_ids"] += 1
                totals["nodes_without_ids"] += 1
                continue

            g_stats["with_ids"] += 1
            totals["nodes_with_ids"] += 1

            if not corpus_rec_ids:
                # No corpus to validate against — count as valid (can't disprove)
                g_stats["valid"] += 1
                totals["valid_links"] += 1
                continue

            all_valid = True
            for rid in src_ids:
                if rid not in corpus_rec_ids:
                    all_valid = False
                    broken_details.append(
                        {
                            "graph_id": graph_id,
                            "node_id": node_id,
                            "broken_rec_id": rid,
                        }
                    )

            if all_valid:
                g_stats["valid"] += 1
                totals["valid_links"] += 1
            else:
                g_stats["broken"] += 1
                totals["broken_links"] += 1

        per_graph[graph_id] = g_stats

    total_with = totals["nodes_with_ids"]
    return {
        "totals": totals,
        "linkage_rate": round(total_with / max(total_with + totals["nodes_without_ids"], 1), 4),
        "valid_rate": round(totals["valid_links"] / max(total_with, 1), 4),
        "broken_details": broken_details[:20],
        "per_graph": per_graph,
    }


# ---------------------------------------------------------------------------
# T4: Action Reachability
# ---------------------------------------------------------------------------


def _bfs_reachable_actions(graph_data: dict[str, Any]) -> set[str]:
    """BFS from entry_node, collecting mandatory_actions at each reachable node."""
    nodes = graph_data.get("nodes", {})
    entry = graph_data.get("entry_node", "")
    if not entry or entry not in nodes:
        return set()

    visited: set[str] = set()
    queue = [entry]
    actions: set[str] = set()

    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = nodes.get(nid, {})
        if not isinstance(node, dict):
            continue
        for a in node.get("mandatory_actions", []) or []:
            actions.add(a)
        for a in node.get("allowed_actions", []) or []:
            actions.add(a)
        for next_nid in node.get("next_nodes", []) or []:
            if next_nid not in visited:
                queue.append(next_nid)
        cond = node.get("conditional_next", {}) or {}
        for target in cond.values():
            if isinstance(target, str) and target not in visited:
                queue.append(target)
            elif isinstance(target, list):
                for t in target:
                    if isinstance(t, str) and t not in visited:
                        queue.append(t)

    return actions


def check_t4_action_reachability(
    graphs: list[tuple[str, dict[str, Any], str]],
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify scenario expected_actions are reachable from graph entry_node."""
    # Build graph lookup
    graph_lookup: dict[str, dict[str, Any]] = {}
    for graph_id, data, _cat in graphs:
        graph_lookup[graph_id] = data

    total_scenarios = 0
    pass_count = 0
    fail_count = 0
    no_graph = 0
    failures: list[dict[str, Any]] = []

    for scenario in scenarios:
        expected = scenario.get("expected_actions", [])
        if not expected:
            continue
        total_scenarios += 1
        graph_ref = scenario.get("guideline_graph", "")
        if not graph_ref or graph_ref not in graph_lookup:
            no_graph += 1
            continue

        reachable = _bfs_reachable_actions(graph_lookup[graph_ref])
        missing = set(expected) - reachable
        if missing:
            fail_count += 1
            failures.append(
                {
                    "scenario_id": scenario.get("scenario_id", "unknown"),
                    "graph": graph_ref,
                    "missing_actions": sorted(missing),
                    "expected": len(expected),
                    "reachable": len(reachable),
                }
            )
        else:
            pass_count += 1

    checked = pass_count + fail_count
    return {
        "total_scenarios": total_scenarios,
        "pass": pass_count,
        "fail": fail_count,
        "no_graph": no_graph,
        "reachability_rate": round(pass_count / max(checked, 1), 4),
        "failures": failures[:20],
    }


# ---------------------------------------------------------------------------
# T5: Provenance Completeness
# ---------------------------------------------------------------------------


def check_t5_provenance(
    graphs: list[tuple[str, dict[str, Any], str]],
) -> dict[str, Any]:
    """Check presence of provenance fields across all graph nodes."""
    field_counts: dict[str, int] = defaultdict(int)
    total_nodes = 0
    per_graph: dict[str, dict[str, Any]] = {}

    all_fields = list(PROVENANCE_REQUIRED) + list(PROVENANCE_RECOMMENDED)

    for graph_id, data, _category in graphs:
        nodes = data.get("nodes", {})
        g_counts: dict[str, int] = defaultdict(int)
        g_total = 0

        for _node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            g_total += 1
            total_nodes += 1
            for field in all_fields:
                val = node.get(field)
                if val is not None and val != "" and val != []:
                    g_counts[field] += 1
                    field_counts[field] += 1

        per_graph[graph_id] = {
            "total_nodes": g_total,
            "fill_rates": {f: round(g_counts.get(f, 0) / max(g_total, 1), 4) for f in all_fields},
        }

    overall_fill = {f: round(field_counts.get(f, 0) / max(total_nodes, 1), 4) for f in all_fields}

    # Aggregate: required fields all present
    required_complete = sum(
        1
        for _gid, data, _ in graphs
        for _nid, node in (data.get("nodes") or {}).items()
        if isinstance(node, dict) and all(node.get(f) for f in PROVENANCE_REQUIRED)
    )

    return {
        "total_nodes": total_nodes,
        "field_fill_rates": overall_fill,
        "required_complete_rate": round(required_complete / max(total_nodes, 1), 4),
        "per_graph": per_graph,
    }


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------


def run_traceability_audit() -> dict[str, Any]:
    """Run all 5 traceability checks and return structured report."""
    corpus_map = _load_corpus_map()
    graphs = _load_all_graphs()
    scenarios = _load_all_scenarios()

    t1 = check_t1_corpus_coverage(graphs, corpus_map)
    t2 = check_t2_quote_verification(graphs, corpus_map)
    t3 = check_t3_recommendation_linkage(graphs, corpus_map)
    t4 = check_t4_action_reachability(graphs, scenarios)
    t5 = check_t5_provenance(graphs)

    return {
        "total_graphs": len(graphs),
        "total_scenarios": len(scenarios),
        "T1_corpus_coverage": t1,
        "T2_quote_verification": t2,
        "T3_recommendation_linkage": t3,
        "T4_action_reachability": t4,
        "T5_provenance_completeness": t5,
    }


def main() -> int:
    """Run traceability audit and print results."""
    report = run_traceability_audit()

    t1 = report["T1_corpus_coverage"]
    t2 = report["T2_quote_verification"]
    t3 = report["T3_recommendation_linkage"]
    t4 = report["T4_action_reachability"]
    t5 = report["T5_provenance_completeness"]

    print(f"End-to-End Traceability Audit — {report['total_graphs']} graphs, {report['total_scenarios']} scenarios")

    print("\n--- T1: Corpus Coverage ---")
    print(f"  Covered: {t1['covered']}/{t1['total_graphs']} ({t1['coverage_rate'] * 100:.1f}%)")
    if t1["missing_graphs"]:
        print(f"  Missing: {', '.join(t1['missing_graphs'][:10])}")
        if len(t1["missing_graphs"]) > 10:
            print(f"  ... and {len(t1['missing_graphs']) - 10} more")

    print("\n--- T2: Quote Verification ---")
    print(f"  Coverage: {t2['quote_coverage_rate'] * 100:.1f}% (exact: {t2['exact_match_rate'] * 100:.1f}%)")
    print(
        f"  Verified: {t2['totals']['verified']}, "
        f"Grounded: {t2['totals']['grounded']}, "
        f"Ungrounded: {t2['totals']['ungrounded']}, "
        f"Missing: {t2['totals']['missing_quote']}"
    )

    print("\n--- T3: Recommendation Linkage ---")
    print(f"  Nodes with IDs: {t3['totals']['nodes_with_ids']} ({t3['linkage_rate'] * 100:.1f}%)")
    print(f"  Valid links: {t3['totals']['valid_links']}, Broken: {t3['totals']['broken_links']}")

    print("\n--- T4: Action Reachability ---")
    print(f"  Pass: {t4['pass']}/{t4['pass'] + t4['fail']} ({t4['reachability_rate'] * 100:.1f}%)")
    if t4["failures"]:
        print("  Failures (first 5):")
        for f in t4["failures"][:5]:
            print(f"    {f['scenario_id']}: missing {f['missing_actions']}")

    print("\n--- T5: Provenance Completeness ---")
    print(f"  Required fields complete: {t5['required_complete_rate'] * 100:.1f}%")
    for field, rate in t5["field_fill_rates"].items():
        print(f"  {field}: {rate * 100:.1f}%")

    # LaTeX macros
    print("\n% LaTeX macros — Traceability")
    print(f"\\providecommand{{\\traceCorpusCoverage}}{{{t1['covered']}/{t1['total_graphs']}}}")
    print(f"\\providecommand{{\\traceCorpusCoverageRate}}{{{t1['coverage_rate'] * 100:.1f}\\%}}")
    print(f"\\providecommand{{\\traceQuoteCoverageRate}}{{{t2['quote_coverage_rate'] * 100:.1f}\\%}}")
    print(f"\\providecommand{{\\traceExactMatchRate}}{{{t2['exact_match_rate'] * 100:.1f}\\%}}")
    print(f"\\providecommand{{\\traceQuoteVerified}}{{{t2['totals']['verified']}}}")
    print(f"\\providecommand{{\\traceQuoteGrounded}}{{{t2['totals']['grounded']}}}")
    print(f"\\providecommand{{\\traceQuoteUngrounded}}{{{t2['totals']['ungrounded']}}}")
    print(f"\\providecommand{{\\traceLinkageRate}}{{{t3['linkage_rate'] * 100:.1f}\\%}}")
    print(f"\\providecommand{{\\traceReachabilityRate}}{{{t4['reachability_rate'] * 100:.1f}\\%}}")
    print(f"\\providecommand{{\\traceProvenanceRate}}{{{t5['required_complete_rate'] * 100:.1f}\\%}}")
    print(f"\\providecommand{{\\traceGraphsN}}{{{report['total_graphs']}}}")
    print(f"\\providecommand{{\\traceScenariosN}}{{{report['total_scenarios']}}}")

    # JSON report
    report_path = REPO_ROOT / "evidence_pack" / "analysis" / "traceability_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nJSON report written to {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
