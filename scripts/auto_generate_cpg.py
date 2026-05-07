"""Auto-generate a CPG graph YAML from a guideline document.

End-to-end pipeline for v7 expansion:
  guideline text/JSON/PDF
     → CPGParser (LLM structured extraction, temperature=0)
     → ParsedGuideline (source-traced ExtractedRecommendations)
     → CPGYAMLGenerator
     → cpg_model/graphs/auto/{guideline_id}.yaml
     → [optional] validate_cpg_schema.py

Usage examples:

  # Real vLLM server (default if VLLM_URL or VLLM_ENDPOINT is set)
  PYTHONPATH=. VLLM_URL=http://localhost:8013/v1 \\
    python scripts/auto_generate_cpg.py \\
      --input data_release/v5.0/rag_corpus/ATA-2016-Thyroid-Storm.parsed.json \\
      --domain thyroid_storm \\
      --source "ATA 2016" \\
      --guideline-id ata_thyroid_storm_2016 \\
      --validate

  # Dry run (prints YAML to stdout, does not write)
  PYTHONPATH=. python scripts/auto_generate_cpg.py \\
      --input <file> --domain <d> --source <s> --dry-run

  # Mock backend for CI smoke test (no LLM required)
  PYTHONPATH=. python scripts/auto_generate_cpg.py \\
      --input tests/fixtures/fake_guideline.txt \\
      --domain fake --source "MOCK" --backend mock --dry-run
"""

from __future__ import annotations

import argparse
from datetime import UTC
import logging
import os
from pathlib import Path
import subprocess
import sys

import yaml

from cga_bench.agent_runner.llm_provider import (
    LLMBackend,
    LLMConfig,
    LLMProviderFactory,
)
from cga_bench.semantic_layer.cpg_parser import CPGParser
from cga_bench.semantic_layer.cpg_yaml_generator import CPGYAMLGenerator
from cga_bench.semantic_layer.parsed_json_loader import (
    ParsedJSONError,
    load_and_normalize,
)
from cga_bench.semantic_layer.parsed_json_loader import (
    write_yaml as write_yaml_from_loader,
)

logger = logging.getLogger("auto_generate_cpg")

# Default output directory for auto-generated graphs. Kept separate from the
# canonical cpg_model/graphs/ so clinician review can promote approved files.
DEFAULT_OUTPUT_DIR = Path("cpg_model/graphs/auto")


# ---------------------------------------------------------------------------
# Provider setup
# ---------------------------------------------------------------------------


def _build_llm_config(args: argparse.Namespace) -> LLMConfig:
    """Build an LLMConfig from CLI flags. Env vars fill in missing pieces."""
    backend_map = {
        "openai": LLMBackend.OPENAI,
        "anthropic": LLMBackend.ANTHROPIC,
        "vllm": LLMBackend.VLLM,
        "mock": LLMBackend.MOCK,
    }
    if args.backend == "env":
        # Auto-select based on env vars (same logic as create_from_env).
        if os.environ.get("VLLM_URL") or os.environ.get("VLLM_ENDPOINT"):
            backend = LLMBackend.VLLM
        elif os.environ.get("ANTHROPIC_API_KEY"):
            backend = LLMBackend.ANTHROPIC
        elif os.environ.get("OPENAI_API_KEY"):
            backend = LLMBackend.OPENAI
        else:
            backend = LLMBackend.MOCK
            logger.warning("No provider env var found — falling back to MOCK backend.")
    else:
        backend = backend_map[args.backend]

    base_url = args.endpoint or os.environ.get("VLLM_URL") or os.environ.get("VLLM_ENDPOINT")

    return LLMConfig(
        backend=backend,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        base_url=base_url,
        seed=args.seed,
    )


def _load_input_text(input_path: Path) -> str:
    """Read guideline text. For .parsed.json we concatenate recognized text fields."""
    if input_path.suffix == ".pdf":
        raise SystemExit(
            f"PDF input ({input_path}) requires a separate PDF-to-text step "
            "(not implemented in Phase 1). Use .txt or pre-parsed .json."
        )
    raw = input_path.read_text(encoding="utf-8")
    if input_path.name.endswith(".parsed.json"):
        import json as _json

        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError as exc:
            raise SystemExit(f"Failed to parse {input_path}: {exc}") from exc
        # Supported parsed-RAG shapes:
        #   {"text": "..."}
        #   {"chunks": [{"text": "..."}]}
        #   {"recommendations": [{"text": "...", "page": "..."}], "tables": [...], "key_sections": {...}}
        #     (rag_corpus/*.parsed.json canonical schema)
        if isinstance(data, dict):
            if isinstance(data.get("text"), str):
                return data["text"]
            recs = data.get("recommendations")
            if isinstance(recs, list) and recs:
                # Concatenate rec text + key_sections (if any) for LLM parsing.
                parts: list[str] = []
                for r in recs:
                    if isinstance(r, dict) and isinstance(r.get("text"), str):
                        rid = r.get("recommendation_id", "")
                        page = r.get("page", "")
                        header = f"[{rid} p.{page}]".strip() if rid or page else ""
                        parts.append(f"{header} {r['text']}".strip())
                # Include key_sections as auxiliary context
                ks = data.get("key_sections")
                if isinstance(ks, dict):
                    for section_name, section_text in ks.items():
                        if isinstance(section_text, str):
                            parts.append(f"\n## {section_name}\n{section_text}")
                if parts:
                    return "\n\n".join(parts)
            chunks = data.get("chunks")
            if isinstance(chunks, list):
                return "\n\n".join(c["text"] for c in chunks if isinstance(c, dict) and isinstance(c.get("text"), str))
        raise SystemExit(f"Unsupported parsed.json shape in {input_path}")
    return raw


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _resolve_output_path(args: argparse.Namespace, guideline_id: str) -> Path:
    if args.output:
        return Path(args.output)
    return DEFAULT_OUTPUT_DIR / f"{guideline_id}.yaml"


def _run_validator(yaml_path: Path) -> int:
    """Run scripts/ci/validate_cpg_schema.py on the parent dir of yaml_path.

    Resolves the validator script path relative to THIS file so the subprocess
    works from any cwd (fixes cwd bug where the parent repo directory lacks
    scripts/ci/).
    """
    validator_path = Path(__file__).resolve().parent / "ci" / "validate_cpg_schema.py"
    cmd = [
        sys.executable,
        str(validator_path),
        "--graphs-dir",
        str(yaml_path.parent),
        "--skip-scenarios",
    ]
    logger.info("Running validator: %s", " ".join(cmd))
    # Inherit PYTHONPATH so the validator can import cga_bench modules if it ever needs to.
    env = {**os.environ}
    env.setdefault("PYTHONPATH", str(Path(__file__).resolve().parents[2]))
    return subprocess.run(cmd, env=env, check=False).returncode


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Auto-generate a CPG graph YAML from a guideline document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--input",
        type=Path,
        help="Guideline text file (.txt or legacy .parsed.json). Mutually exclusive with --from-parsed-json.",
    )
    p.add_argument(
        "--from-parsed-json",
        type=Path,
        help=(
            "Path to an extended parsed.json that is structurally homomorphic to "
            "the CPG YAML schema. Uses the deterministic rule-based loader "
            "(no LLM call). Mutually exclusive with --input."
        ),
    )
    p.add_argument(
        "--domain", help="Clinical domain, e.g., 'sepsis'. Required with --input; ignored with --from-parsed-json."
    )
    p.add_argument(
        "--source", help="Source label, e.g., 'SSC 2021'. Required with --input; ignored with --from-parsed-json."
    )
    p.add_argument("--guideline-id", default=None, help="graph_id (defaults to input stem lowercased)")
    p.add_argument("--output", default=None, type=Path, help="Output YAML path (defaults to cpg_model/graphs/auto/)")
    p.add_argument(
        "--backend",
        default="env",
        choices=["env", "vllm", "openai", "anthropic", "mock"],
        help="LLM backend (default: auto-detect from env)",
    )
    p.add_argument("--model", default="Qwen/Qwen3-30B-A3B-Instruct-2507", help="Model name for the LLM call")
    p.add_argument("--endpoint", default=None, help="Override vLLM base URL (takes precedence over VLLM_URL env)")
    p.add_argument("--temperature", type=float, default=0.0, help="LLM temperature (0.0 for reproducibility)")
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--seed", type=int, default=42, help="LLM sampling seed (reproducibility)")
    p.add_argument("--dry-run", action="store_true", help="Print YAML to stdout, do not write")
    p.add_argument("--validate", action="store_true", help="Run validate_cpg_schema.py after write")
    p.add_argument("--verbose", "-v", action="store_true")
    # Batch mode
    p.add_argument(
        "--batch-dir",
        type=Path,
        help="Directory of .parsed.json files to process in batch (rule-based loader).",
    )
    p.add_argument(
        "--max-parallel",
        type=int,
        default=4,
        help="Max parallel workers for batch mode (default: 4).",
    )
    p.add_argument(
        "--batch-report",
        type=Path,
        default=None,
        help="Path for JSON batch report (default: <output-dir>/batch_report.json).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Dispatch: batch mode, rule-based path, or LLM extraction path.
    if args.batch_dir is not None:
        return _run_batch(args)
    if args.from_parsed_json is not None:
        if args.input is not None:
            logger.error("--input and --from-parsed-json are mutually exclusive.")
            return 2
        return _run_rule_based(args)

    if args.input is None:
        logger.error("Either --input (LLM path) or --from-parsed-json (rule-based path) is required.")
        return 2
    if not args.input.exists():
        logger.error("Input file does not exist: %s", args.input)
        return 2
    if not args.domain or not args.source:
        logger.error("--domain and --source are required when using --input (LLM path).")
        return 2

    guideline_id = args.guideline_id or args.input.stem.replace(" ", "_").lower()

    # --- Build LLM provider
    config = _build_llm_config(args)
    logger.info("LLM backend: %s  model: %s  endpoint: %s", config.backend.value, config.model, config.base_url)
    llm = LLMProviderFactory.create(config)

    # --- Parse guideline
    text = _load_input_text(args.input)
    logger.info("Loaded %d chars from %s", len(text), args.input)
    parser = CPGParser(llm)
    parsed = parser.parse_text(text=text, guideline_id=guideline_id, domain=args.domain, source=args.source)
    logger.info(
        "Extracted %d recommendations  parse_confidence=%.2f",
        len(parsed.recommendations),
        parsed.parse_confidence,
    )

    if not parsed.recommendations:
        logger.error("Extractor returned 0 recommendations — refusing to generate an empty CPG YAML.")
        return 3

    # --- Generate YAML
    generator = CPGYAMLGenerator()

    if args.dry_run:
        data = generator.generate(parsed)
        sys.stdout.write(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
        return 0

    output_path = _resolve_output_path(args, guideline_id)
    written = generator.write(parsed, output_path)
    logger.info("Wrote %s (%d bytes)", written, written.stat().st_size)

    if args.validate:
        rc = _run_validator(written)
        if rc != 0:
            logger.error("validate_cpg_schema.py failed with rc=%d", rc)
            return rc

    return 0


def _run_batch(args: argparse.Namespace) -> int:
    """Batch mode: process all .parsed.json files in a directory.

    Uses the rule-based loader (no LLM) by default. Each file produces one
    CPG YAML in the output directory. A JSON report summarises the run.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import datetime
    import json as _json
    import time as _time

    batch_dir = args.batch_dir
    if not batch_dir.is_dir():
        logger.error("Batch directory does not exist: %s", batch_dir)
        return 2

    input_files = sorted(batch_dir.glob("*.parsed.json"))
    if not input_files:
        input_files = sorted(batch_dir.glob("*.json"))
    if not input_files:
        logger.error("No .parsed.json or .json files found in %s", batch_dir)
        return 2

    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Batch: %d files -> %s (workers=%d)", len(input_files), output_dir, args.max_parallel)

    results: list[dict] = []
    t0 = _time.monotonic()

    def _process_one(input_path: Path) -> dict:
        """Process a single parsed JSON file. Returns a status dict."""
        file_t0 = _time.monotonic()
        graph_id = input_path.stem.replace(".parsed", "").replace(" ", "_").lower()
        out_path = output_dir / f"{graph_id}.yaml"
        status = {"input": str(input_path), "graph_id": graph_id, "output": str(out_path)}
        try:
            result = load_and_normalize(input_path)
            status["nodes"] = len(result.data.get("nodes", {}))
            write_yaml_from_loader(result, out_path)
            status["status"] = "success"
            status["bytes"] = out_path.stat().st_size
        except (ParsedJSONError, Exception) as exc:
            status["status"] = "failed"
            status["error"] = str(exc)
            logger.warning("FAILED %s: %s", input_path.name, exc)

        # Validate if requested
        if status["status"] == "success" and args.validate:
            rc = _run_validator(out_path)
            status["validator_rc"] = rc
            if rc != 0:
                status["status"] = "validation_failed"

        status["elapsed_s"] = round(_time.monotonic() - file_t0, 2)
        return status

    with ThreadPoolExecutor(max_workers=args.max_parallel) as executor:
        futures = {executor.submit(_process_one, f): f for f in input_files}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            tag = "OK" if result["status"] == "success" else result["status"].upper()
            logger.info("[%s] %s (%.1fs)", tag, result["graph_id"], result.get("elapsed_s", 0))

    elapsed = round(_time.monotonic() - t0, 1)

    # Build report
    n_success = sum(1 for r in results if r["status"] == "success")
    n_failed = sum(1 for r in results if r["status"] == "failed")
    n_val_fail = sum(1 for r in results if r["status"] == "validation_failed")
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "batch_dir": str(batch_dir),
        "output_dir": str(output_dir),
        "total": len(results),
        "success": n_success,
        "failed": n_failed,
        "validation_failed": n_val_fail,
        "success_rate": round(n_success / max(len(results), 1), 3),
        "elapsed_s": elapsed,
        "files": sorted(results, key=lambda r: r["graph_id"]),
    }

    report_path = args.batch_report or (output_dir / "batch_report.json")
    report_path.write_text(_json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Batch complete: %d/%d success, %d failed, %d validation_failed (%.1fs)",
        n_success,
        len(results),
        n_failed,
        n_val_fail,
        elapsed,
    )
    logger.info("Report: %s", report_path)

    return 0 if n_failed == 0 and n_val_fail == 0 else 1


def _run_rule_based(args: argparse.Namespace) -> int:
    """Deterministic path: extended parsed.json → CPG YAML via rule-based loader.

    No LLM call is made. Re-running on the same input produces byte-identical
    output — this is the reviewer-facing reproducibility guarantee.
    """
    if not args.from_parsed_json.exists():
        logger.error("Parsed JSON file does not exist: %s", args.from_parsed_json)
        return 2

    try:
        result = load_and_normalize(args.from_parsed_json)
    except ParsedJSONError as exc:
        logger.error("Rule-based loader rejected input: %s", exc)
        return 4

    graph_id = result.data.get("graph_id", "unknown")
    logger.info(
        "Rule-based load OK: graph_id=%s  nodes=%d  entry=%s",
        graph_id,
        len(result.data.get("nodes", {})),
        result.data.get("entry_node"),
    )

    if args.dry_run:
        sys.stdout.write(yaml.safe_dump(result.data, sort_keys=False, allow_unicode=True, width=120))
        return 0

    guideline_id = args.guideline_id or graph_id
    output_path = _resolve_output_path(args, guideline_id)
    written = write_yaml_from_loader(result, output_path)
    logger.info("Wrote %s (%d bytes)", written, written.stat().st_size)

    if args.validate:
        rc = _run_validator(written)
        if rc != 0:
            logger.error("validate_cpg_schema.py failed with rc=%d", rc)
            return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
