#!/usr/bin/env python3
"""C-6: Entailment rejection audit across 24 core productive graphs.

Re-runs atom proposer (DET mode) + entailment checker to capture
rejected atoms and tally rejection reasons by field.

Usage:
    PYTHONPATH=. python scripts/experiments/c6_entailment_audit.py \
        --endpoint http://localhost:8013/v1 \
        --parallel 8
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

REGISTRY_PATH = REPO_ROOT / "configs" / "sgsc" / "full_25_registry.json"

logger = logging.getLogger("c6_audit")


@dataclass
class FieldTally:
    """Per-field entailment tally for one graph."""

    entailed: int = 0
    not_entailed: int = 0
    partial: int = 0
    not_applicable: int = 0


@dataclass
class GraphAuditResult:
    """Audit result for a single graph."""

    graph_id: str
    proposed_atoms: int = 0
    passed_atoms: int = 0
    rejected_atoms: int = 0
    review_atoms: int = 0
    grounding_failures: int = 0
    field_tallies: dict[str, FieldTally] = field(default_factory=dict)
    # Near-threshold atoms: entailment score 0.5-0.6
    near_threshold_count: int = 0
    near_threshold_atoms: list[dict] = field(default_factory=list)
    # Per-atom rejection details (for rejected atoms only)
    rejection_details: list[dict] = field(default_factory=list)
    error: str = ""
    duration_seconds: float = 0.0


def load_registry() -> list[dict]:
    """Load registry entries."""
    data = json.loads(REGISTRY_PATH.read_text())
    return data["guidelines"]


def audit_single_graph(
    entry: dict,
    endpoint: str,
    model: str,
    threshold: float,
) -> GraphAuditResult:
    """Run atom proposer + entailment on one graph, capture all rejections."""
    start = time.monotonic()
    gid = entry["guideline_id"]
    result = GraphAuditResult(graph_id=gid)

    try:
        from sgsc.extraction.atom_proposer import AtomProposerConfig, propose_atoms
        from sgsc.extraction.schema_validator import validate_atoms
        from sgsc.verification.quote_verifier import verify_atom_quotes
        from sgsc.verification.entailment_checker import (
            check_atoms_entailment,
            ENTAILMENT_FIELDS,
        )
        from sgsc.pipeline import _normalize_atom_actions

        # Load corpus
        corpus_path = REPO_ROOT / entry["corpus_file"]
        data = json.loads(corpus_path.read_text())
        if isinstance(data, dict):
            recommendations = data.get("recommendations", [])
            full_text = data.get("full_text", "")
            if not full_text and recommendations:
                full_text = " ".join(str(r.get("text", "")) for r in recommendations)
        elif isinstance(data, list):
            recommendations = data
            full_text = " ".join(str(r.get("text", "")) for r in data)
        else:
            recommendations = []
            full_text = str(data)

        if not recommendations:
            result.error = "empty_corpus"
            result.duration_seconds = time.monotonic() - start
            return result

        # Step 2: Propose atoms (DET mode)
        llm_config = AtomProposerConfig(
            endpoint=endpoint,
            model=model,
            timeout_seconds=600.0,
            top_p=1.0,
            deterministic=True,
            base_seed=42,
        )
        atoms = propose_atoms(llm_config, gid, recommendations, full_text)
        result.proposed_atoms = len(atoms)

        if not atoms:
            result.error = "zero_proposed"
            result.duration_seconds = time.monotonic() - start
            return result

        # Step 2b: Normalize
        atoms = _normalize_atom_actions(atoms)

        # Step 3: Schema validation
        validation = validate_atoms(atoms)
        atoms = validation.valid_atoms

        # Step 5: Quote grounding
        verification_results = verify_atom_quotes(
            atoms, full_text, recommendations, threshold
        )
        verified_ids = {
            r.atom_id
            for r in verification_results
            if r.status in ("VERIFIED", "GROUNDED")
        }
        result.grounding_failures = len(atoms) - len(verified_ids)
        grounded_atoms = [a for a in atoms if a.atom_id in verified_ids]

        # Step 6: Entailment check (THE MAIN AUDIT TARGET)
        reports = check_atoms_entailment(
            grounded_atoms,
            mode="rule_based",
            action_threshold=threshold,
            guard_threshold=threshold,
        )

        # Initialize field tallies
        for f in ENTAILMENT_FIELDS:
            result.field_tallies[f] = FieldTally()

        # Tally results
        n_pass = 0
        n_reject = 0
        n_review = 0
        for report in reports:
            is_passing = report.all_passed  # lenient mode (default)

            for fr in report.field_results:
                tally = result.field_tallies.get(fr.field)
                if not tally:
                    tally = FieldTally()
                    result.field_tallies[fr.field] = tally

                if fr.verdict == "ENTAILED":
                    tally.entailed += 1
                elif fr.verdict == "NOT_ENTAILED":
                    tally.not_entailed += 1
                elif fr.verdict == "PARTIAL":
                    tally.partial += 1
                elif fr.verdict == "NOT_APPLICABLE":
                    tally.not_applicable += 1

                # Track near-threshold (confidence 0.5-0.6)
                if fr.verdict == "NOT_ENTAILED" and 0.5 <= fr.confidence < 0.6:
                    result.near_threshold_count += 1
                    result.near_threshold_atoms.append(
                        {
                            "atom_id": report.atom_id,
                            "field": fr.field,
                            "confidence": fr.confidence,
                            "reason": fr.reason,
                        }
                    )

            if is_passing:
                n_pass += 1
            elif report.failed_fields:
                n_reject += 1
                result.rejection_details.append(
                    {
                        "atom_id": report.atom_id,
                        "failed_fields": report.failed_fields,
                        "pass_rate": report.pass_rate,
                        "details": [
                            {
                                "field": fr.field,
                                "verdict": fr.verdict,
                                "confidence": fr.confidence,
                                "reason": fr.reason,
                            }
                            for fr in report.field_results
                            if fr.verdict == "NOT_ENTAILED"
                        ],
                    }
                )
            else:
                n_review += 1

        result.passed_atoms = n_pass
        result.rejected_atoms = n_reject
        result.review_atoms = n_review

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"

    result.duration_seconds = time.monotonic() - start
    return result


def format_table(results: list[GraphAuditResult]) -> str:
    """Format results as markdown table."""
    lines = []
    lines.append(
        "| # | graph_id | proposed | passed | rejected | grnd_fail "
        "| seq_rej | act_rej | guard_rej | evid_rej | near_thr | rej_pct |"
    )
    lines.append(
        "|---|----------|------:|------:|------:|------:"
        "|------:|------:|------:|------:|------:|------:|"
    )

    total_proposed = 0
    total_passed = 0
    total_rejected = 0
    total_seq = 0
    total_act = 0
    over_rejection_graphs = []

    for i, r in enumerate(results, 1):
        seq_rej = r.field_tallies.get("sequence", FieldTally()).not_entailed
        act_rej = r.field_tallies.get("action", FieldTally()).not_entailed
        grd_rej = r.field_tallies.get("guard", FieldTally()).not_entailed
        evd_rej = r.field_tallies.get("evidence", FieldTally()).not_entailed

        rej_pct = (
            f"{r.rejected_atoms / r.proposed_atoms * 100:.1f}%"
            if r.proposed_atoms > 0
            else "N/A"
        )

        # Check sequence over-rejection (>30% of NOT_ENTAILED are sequence)
        total_not_entailed = seq_rej + act_rej + grd_rej + evd_rej
        seq_pct = (
            seq_rej / total_not_entailed * 100
            if total_not_entailed > 0
            else 0
        )
        if seq_pct > 30 and r.rejected_atoms > 0:
            over_rejection_graphs.append((r, seq_pct))

        total_proposed += r.proposed_atoms
        total_passed += r.passed_atoms
        total_rejected += r.rejected_atoms
        total_seq += seq_rej
        total_act += act_rej

        lines.append(
            f"| {i} | {r.graph_id[:35]:35s} | {r.proposed_atoms:5d} | "
            f"{r.passed_atoms:5d} | {r.rejected_atoms:5d} | {r.grounding_failures:5d} | "
            f"{seq_rej:5d} | {act_rej:5d} | {grd_rej:5d} | {evd_rej:5d} | "
            f"{r.near_threshold_count:5d} | {rej_pct:>6s} |"
        )

    lines.append(
        f"| | **TOTAL** | **{total_proposed}** | **{total_passed}** | "
        f"**{total_rejected}** | | **{total_seq}** | **{total_act}** | | | | |"
    )

    return "\n".join(lines), over_rejection_graphs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="C-6 entailment rejection audit")
    p.add_argument("--endpoint", required=True)
    p.add_argument("--model", default="Qwen/Qwen3.5-397B-A17B-FP8")
    p.add_argument("--threshold", type=float, default=0.6)
    p.add_argument("--parallel", type=int, default=4)
    p.add_argument("--output-dir", type=Path, default=REPO_ROOT / "reports" / "path_d_day2")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    entries = load_registry()
    logger.info("Loaded %d graphs from registry", len(entries))

    results: list[GraphAuditResult] = []

    if args.parallel > 1:
        with ProcessPoolExecutor(max_workers=args.parallel) as pool:
            futures = {
                pool.submit(
                    audit_single_graph, e, args.endpoint, args.model, args.threshold
                ): e
                for e in entries
            }
            for fut in as_completed(futures):
                r = fut.result()
                logger.info(
                    "[%s] proposed=%d passed=%d rejected=%d (%.1fs)%s",
                    r.graph_id,
                    r.proposed_atoms,
                    r.passed_atoms,
                    r.rejected_atoms,
                    r.duration_seconds,
                    f" ERROR={r.error}" if r.error else "",
                )
                results.append(r)
    else:
        for e in entries:
            r = audit_single_graph(e, args.endpoint, args.model, args.threshold)
            logger.info(
                "[%s] proposed=%d passed=%d rejected=%d (%.1fs)%s",
                r.graph_id,
                r.proposed_atoms,
                r.passed_atoms,
                r.rejected_atoms,
                r.duration_seconds,
                f" ERROR={r.error}" if r.error else "",
            )
            results.append(r)

    # Sort by graph_id
    results.sort(key=lambda r: r.graph_id)

    # Format and print table
    table_text, over_rejection = format_table(results)
    print("\n" + table_text + "\n")

    # Decision output
    n_over = len(over_rejection)
    if n_over <= 3:
        verdict = "isolated"
        recommendation = f"Fix only affected graphs ({n_over} with >30% sequence rejection)"
    elif n_over > 5:
        verdict = "systematic"
        recommendation = "Fix entailment checker globally, re-extract all atoms"
    else:
        verdict = "border"
        recommendation = f"{n_over} graphs affected — document and decide with anonymous-user"

    print(f"\n{'='*70}")
    print(f"Over-rejection candidates (sequence >30% of NOT_ENTAILED):")
    for r, seq_pct in over_rejection:
        print(f"  {r.graph_id}: seq_pct={seq_pct:.1f}%, rejected={r.rejected_atoms}")
    print(f"\nVERDICT: {verdict}")
    print(f"RECOMMENDATION: {recommendation}")
    print(f"{'='*70}\n")

    # Save detailed JSON
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "c6_entailment_audit.json"
    json_data = {
        "audit_date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "endpoint": args.endpoint,
        "threshold": args.threshold,
        "verdict": verdict,
        "recommendation": recommendation,
        "n_over_rejection_graphs": n_over,
        "results": [
            {
                "graph_id": r.graph_id,
                "proposed_atoms": r.proposed_atoms,
                "passed_atoms": r.passed_atoms,
                "rejected_atoms": r.rejected_atoms,
                "review_atoms": r.review_atoms,
                "grounding_failures": r.grounding_failures,
                "near_threshold_count": r.near_threshold_count,
                "field_tallies": {
                    f: {
                        "entailed": t.entailed,
                        "not_entailed": t.not_entailed,
                        "partial": t.partial,
                        "not_applicable": t.not_applicable,
                    }
                    for f, t in r.field_tallies.items()
                },
                "rejection_details": r.rejection_details[:10],  # cap at 10
                "near_threshold_atoms": r.near_threshold_atoms[:5],  # cap at 5
                "error": r.error,
                "duration_seconds": round(r.duration_seconds, 1),
            }
            for r in results
        ],
    }
    json_path.write_text(json.dumps(json_data, indent=2))
    logger.info("Saved JSON: %s", json_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
