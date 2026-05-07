"""Auto Graph Pipeline: orchestrates Option B (generate) → Option A (ground).

Single entry point for the explainable auto graph pipeline:
  --mode generate : Option B only (LLM-based graph generation from corpus)
  --mode ground   : Option A only (verify/replace quotes in existing graph)
  --mode auto     : Try B first; if graph exists or LLM unavailable, fall back to A

Usage:
    # Auto mode (recommended)
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/auto_graph_pipeline.py \\
        --mode auto \\
        --corpus data_release/v5.0/rag_corpus/ATS-ESICM-SCCM-2023-ARDS.parsed.json \\
        --graph cpg_model/graphs/auto/ats_esicm_sccm_ards_2023.yaml \\
        --endpoint http://localhost:8013/v1

    # Batch mode
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/auto_graph_pipeline.py \\
        --mode auto \\
        --graphs-dir cpg_model/graphs/auto/ \\
        --corpus-dir data_release/v5.0/rag_corpus/ \\
        --endpoint http://localhost:8013/v1 \\
        --report reports/pipeline_report.json
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any

from scripts.cpg_v2_phase_annotation.generate_graph_from_corpus import (
    LLMUnavailable,
    generate_graph,
    write_graph,
)
from scripts.cpg_v2_phase_annotation.ground_graph_quotes import (
    apply_grounding,
    find_corpus_for_graph,
    ground_all_nodes,
    load_corpus,
    write_grounded_graph,
)
import yaml

logger = logging.getLogger(__name__)

RAG_CORPUS_DIR = Path("data_release/v5.0/rag_corpus")
DEFAULT_ENDPOINT = "http://localhost:8013/v1"
DEFAULT_MODEL = "Qwen/Qwen3.5-397B-A17B-FP8"


@dataclass
class PipelineResult:
    """Result of a single pipeline run."""

    graph_id: str = ""
    mode_used: str = ""  # "A" | "B" | "SKIPPED"
    success: bool = False
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def run_single(
    mode: str,
    corpus_path: Path,
    graph_path: Path | None,
    graph_id: str,
    guideline_name: str,
    endpoint: str,
    model: str,
    output_path: Path | None,
    dry_run: bool,
    api_key: str = "sk-no-key-required",
) -> PipelineResult:
    """Run the pipeline for a single graph."""
    corpus = load_corpus(corpus_path)
    graph_exists = graph_path is not None and graph_path.exists()

    # --- Option B: Generate ---
    if mode == "generate" or (mode == "auto" and not graph_exists):
        try:
            logger.info("[%s] Option B: generating graph from corpus...", graph_id)
            graph = generate_graph(
                corpus=corpus,
                graph_id=graph_id,
                guideline_name=guideline_name or corpus.get("guideline_name", graph_id),
                endpoint=endpoint,
                model=model,
                api_key=api_key,
            )
            out = output_path or Path(f"cpg_model/graphs/auto/{graph_id}.yaml")
            write_graph(graph, out, dry_run=dry_run)

            errors = graph.get("_generation_pipeline", {}).get("validation_errors", 0)
            return PipelineResult(
                graph_id=graph_id,
                mode_used="B",
                success=errors == 0,
                message=f"Generated with {errors} validation warnings" if errors else "Generated successfully",
                details={"output": str(out), "validation_errors": errors},
            )
        except LLMUnavailable as exc:
            if mode == "generate":
                return PipelineResult(
                    graph_id=graph_id,
                    mode_used="B",
                    success=False,
                    message=f"LLM unavailable: {exc}",
                )
            logger.warning("[%s] Option B failed (%s), falling back to Option A", graph_id, exc)
        except (ValueError, KeyError) as exc:
            if mode == "generate":
                return PipelineResult(
                    graph_id=graph_id,
                    mode_used="B",
                    success=False,
                    message=f"Generation error: {exc}",
                )
            logger.warning("[%s] Option B error (%s), falling back to Option A", graph_id, exc)

    # --- Option A: Ground ---
    if graph_exists:
        logger.info("[%s] Option A: grounding existing graph quotes...", graph_id)
        graph = yaml.safe_load(graph_path.read_text(encoding="utf-8"))
        report = ground_all_nodes(graph, corpus)

        if not dry_run:
            updated = apply_grounding(graph, report)
            out = output_path or graph_path
            write_grounded_graph(updated, out)

        total = report.verified + report.grounded + report.ungrounded
        return PipelineResult(
            graph_id=graph_id,
            mode_used="A",
            success=report.ungrounded == 0,
            message=f"Grounded {report.verified + report.grounded}/{total} nodes ({report.ungrounded} ungrounded)",
            details={
                "verified": report.verified,
                "grounded": report.grounded,
                "ungrounded": report.ungrounded,
                "pages_filled": report.pages_filled,
            },
        )

    # Neither B nor A applicable
    if mode == "ground":
        return PipelineResult(
            graph_id=graph_id,
            mode_used="SKIPPED",
            success=False,
            message="No graph file exists for grounding",
        )

    return PipelineResult(
        graph_id=graph_id,
        mode_used="SKIPPED",
        success=False,
        message="No graph exists and Option B failed or was not attempted",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", choices=["auto", "generate", "ground"], default="auto")

    # Single mode
    parser.add_argument("--corpus", type=Path, help="rag_corpus parsed.json (single mode)")
    parser.add_argument("--graph", type=Path, help="Existing graph YAML (single/ground mode)")
    parser.add_argument("--graph-id", help="Graph ID (required for generate mode)")
    parser.add_argument("--guideline-name", default="", help="Human-readable guideline name")
    parser.add_argument("--output", type=Path, help="Output path")

    # Batch mode
    parser.add_argument("--graphs-dir", type=Path, help="Directory of graph YAMLs (batch)")
    parser.add_argument("--corpus-dir", type=Path, default=RAG_CORPUS_DIR, help="Directory of corpus files")
    parser.add_argument("--report", type=Path, help="JSON report output (batch)")

    # LLM config
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default="sk-no-key-required", help="API key for vLLM endpoint")

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results: list[PipelineResult] = []

    if args.graphs_dir or (not args.corpus and not args.graph):
        # Batch mode
        graphs_dir = args.graphs_dir or Path("cpg_model/graphs/auto")
        corpus_dir = args.corpus_dir

        if not graphs_dir.exists():
            logger.error("Graphs directory not found: %s", graphs_dir)
            return 1

        graph_files = sorted(graphs_dir.glob("*.yaml"))
        for gf in graph_files:
            graph_data = yaml.safe_load(gf.read_text(encoding="utf-8"))
            gid = graph_data.get("graph_id", gf.stem)
            cp = find_corpus_for_graph(gid, corpus_dir)
            if cp is None:
                logger.warning("[%s] No corpus found — skipping", gid)
                results.append(PipelineResult(graph_id=gid, mode_used="SKIPPED", message="No corpus"))
                continue

            result = run_single(
                mode=args.mode,
                corpus_path=cp,
                graph_path=gf,
                graph_id=gid,
                guideline_name="",
                endpoint=args.endpoint,
                model=args.model,
                output_path=None,
                dry_run=args.dry_run,
                api_key=args.api_key,
            )
            results.append(result)

    else:
        # Single mode
        corpus_path = args.corpus
        graph_path = args.graph

        if corpus_path is None and graph_path is not None:
            graph_data = yaml.safe_load(graph_path.read_text(encoding="utf-8"))
            gid = graph_data.get("graph_id", graph_path.stem)
            corpus_path = find_corpus_for_graph(gid, args.corpus_dir)
            if corpus_path is None:
                logger.error("No corpus found for %s", gid)
                return 1

        graph_id = args.graph_id
        if not graph_id:
            if graph_path:
                graph_data = yaml.safe_load(graph_path.read_text(encoding="utf-8"))
                graph_id = graph_data.get("graph_id", graph_path.stem)
            elif corpus_path:
                corpus_data = json.loads(corpus_path.read_text(encoding="utf-8"))
                graph_id = corpus_data.get("graph_id", corpus_path.stem.replace(".parsed", ""))

        if not graph_id:
            logger.error("Cannot determine graph_id — provide --graph-id")
            return 1

        result = run_single(
            mode=args.mode,
            corpus_path=corpus_path,
            graph_path=graph_path,
            graph_id=graph_id,
            guideline_name=args.guideline_name,
            endpoint=args.endpoint,
            model=args.model,
            output_path=args.output,
            dry_run=args.dry_run,
            api_key=args.api_key,
        )
        results.append(result)

    # Summary
    success = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success and r.mode_used != "SKIPPED")
    skipped = sum(1 for r in results if r.mode_used == "SKIPPED")

    print(f"\n=== Pipeline Summary ({len(results)} graphs) ===")
    for r in results:
        status = "OK" if r.success else ("SKIP" if r.mode_used == "SKIPPED" else "FAIL")
        print(f"  [{status}] {r.graph_id} (mode={r.mode_used}): {r.message}")
    print(f"\n  Success: {success}, Failed: {failed}, Skipped: {skipped}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        report_data = [
            {
                "graph_id": r.graph_id,
                "mode_used": r.mode_used,
                "success": r.success,
                "message": r.message,
                "details": r.details,
            }
            for r in results
        ]
        args.report.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Report: {args.report}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
