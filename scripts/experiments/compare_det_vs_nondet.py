"""Task 6: Compare DET vs NONDET SGSC extraction outputs.

Produces per-graph and aggregate comparison metrics for paper
Phase B Patch B4.

Metrics per graph:
  - Atom count (DET vs NONDET, delta)
  - Hallucination rate (both expected 0)
  - Truncated stem rate (both expected 0, E3-c effect)
  - Action type diversity (count of distinct action_type in 14-type taxonomy)
  - Vocabulary Jaccard (canonical_id set overlap)

Usage:
    PYTHONPATH=.:.. python scripts/experiments/compare_det_vs_nondet.py \
        --det-dir sgsc_output/v7_e3_combined_overnight \
        --nondet-dir sgsc_output/v7_e3_combined_overnight_NONDET

    # Dry-test (NONDET vs itself — trivially identical):
    PYTHONPATH=.:.. python scripts/experiments/compare_det_vs_nondet.py \
        --det-dir sgsc_output/v7_e3_combined_overnight_NONDET \
        --nondet-dir sgsc_output/v7_e3_combined_overnight_NONDET
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("det_vs_nondet")

# Truncated stem heuristic: canonical_id ending with underscore or
# single char after underscore (e.g. "give_" or "order_l")
_TRUNCATED_STEM_MIN_LEN = 4


def _load_atoms(atoms_path: Path) -> list[dict]:
    """Load atoms from atoms_smoke.json."""
    if not atoms_path.exists():
        return []
    with open(atoms_path) as f:
        return json.load(f)


def _canonical_ids(atoms: list[dict]) -> set[str]:
    """Extract set of canonical_id values from atoms."""
    ids: set[str] = set()
    for a in atoms:
        action = a.get("action", {})
        cid = action.get("canonical_id", "")
        if cid:
            ids.add(cid)
    return ids


def _action_types(atoms: list[dict]) -> set[str]:
    """Extract set of action_type values from atoms."""
    types: set[str] = set()
    for a in atoms:
        action = a.get("action", {})
        at = action.get("action_type", "")
        if at:
            types.add(at)
    return types


def _hallucination_rate(atoms: list[dict]) -> float:
    """Fraction of atoms with empty or missing source quote."""
    if not atoms:
        return 0.0
    n_halluc = sum(
        1 for a in atoms
        if not a.get("source", {}).get("quote", "").strip()
    )
    return n_halluc / len(atoms)


def _truncated_stem_rate(atoms: list[dict]) -> float:
    """Fraction of atoms with truncated canonical_id stems."""
    if not atoms:
        return 0.0
    n_trunc = 0
    for a in atoms:
        cid = a.get("action", {}).get("canonical_id", "")
        if not cid:
            continue
        # Truncated: ends with underscore, or final segment is 1 char
        if cid.endswith("_"):
            n_trunc += 1
        elif len(cid) < _TRUNCATED_STEM_MIN_LEN:
            n_trunc += 1
        else:
            parts = cid.split("_")
            if parts and len(parts[-1]) <= 1:
                n_trunc += 1
    return n_trunc / len(atoms)


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity coefficient."""
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def _scenario_count(guideline_dir: Path, gid: str) -> int:
    """Count scenarios from scenarios.json."""
    spath = guideline_dir / f"{gid}_scenarios.json"
    if not spath.exists():
        return 0
    with open(spath) as f:
        data = json.load(f)
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        # Top-level dict with scenario_id keys (production format)
        # vs nested {"scenarios": [...]} wrapper
        nested = data.get("scenarios", data.get("items", None))
        if nested is not None:
            return len(nested)
        # Keys are scenario IDs directly
        return len(data)
    return 0


def compare_guideline(
    det_dir: Path,
    nondet_dir: Path,
    gid: str,
) -> dict:
    """Compare a single guideline's outputs. Returns metrics dict."""
    det_atoms = _load_atoms(det_dir / gid / "atoms_smoke.json")
    nondet_atoms = _load_atoms(nondet_dir / gid / "atoms_smoke.json")

    det_cids = _canonical_ids(det_atoms)
    nondet_cids = _canonical_ids(nondet_atoms)

    det_types = _action_types(det_atoms)
    nondet_types = _action_types(nondet_atoms)

    return {
        "guideline": gid,
        "det_atoms": len(det_atoms),
        "nondet_atoms": len(nondet_atoms),
        "atom_delta": len(det_atoms) - len(nondet_atoms),
        "det_halluc_rate": round(_hallucination_rate(det_atoms), 3),
        "nondet_halluc_rate": round(_hallucination_rate(nondet_atoms), 3),
        "det_trunc_rate": round(_truncated_stem_rate(det_atoms), 3),
        "nondet_trunc_rate": round(_truncated_stem_rate(nondet_atoms), 3),
        "det_type_diversity": len(det_types),
        "nondet_type_diversity": len(nondet_types),
        "vocab_jaccard": round(_jaccard(det_cids, nondet_cids), 3),
        "det_scenarios": _scenario_count(det_dir / gid, gid),
        "nondet_scenarios": _scenario_count(nondet_dir / gid, gid),
        "det_only_cids": sorted(det_cids - nondet_cids),
        "nondet_only_cids": sorted(nondet_cids - det_cids),
    }


def write_report(
    results: list[dict],
    det_dir: str,
    nondet_dir: str,
    report_path: Path,
    json_path: Path | None = None,
) -> None:
    """Write markdown comparison report + optional JSON."""
    total_det = sum(r["det_atoms"] for r in results)
    total_nondet = sum(r["nondet_atoms"] for r in results)
    total_det_scn = sum(r["det_scenarios"] for r in results)
    total_nondet_scn = sum(r["nondet_scenarios"] for r in results)
    avg_jaccard = sum(r["vocab_jaccard"] for r in results) / len(results) if results else 0.0
    avg_halluc_det = sum(r["det_halluc_rate"] for r in results) / len(results) if results else 0.0
    avg_halluc_nondet = sum(r["nondet_halluc_rate"] for r in results) / len(results) if results else 0.0

    lines = [
        "# DET vs NONDET SGSC Comparison",
        "",
        f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**DET dir**: `{det_dir}`",
        f"**NONDET dir**: `{nondet_dir}`",
        f"**Guidelines compared**: {len(results)}",
        "",
        "## Aggregate Summary",
        "",
        "| Metric | DET | NONDET | Delta |",
        "|--------|-----|--------|-------|",
        f"| Total atoms | {total_det} | {total_nondet} | {total_det - total_nondet:+d} |",
        f"| Total scenarios | {total_det_scn} | {total_nondet_scn} | {total_det_scn - total_nondet_scn:+d} |",
        f"| Avg hallucination rate | {avg_halluc_det:.3f} | {avg_halluc_nondet:.3f} | — |",
        f"| Avg vocab Jaccard | — | — | {avg_jaccard:.3f} |",
        "",
        "## Per-Graph Comparison",
        "",
        "| Guideline | DET atoms | NONDET atoms | Delta | Halluc D/N | Trunc D/N | Types D/N | Jaccard |",
        "|-----------|-----------|-------------|-------|------------|-----------|-----------|---------|",
    ]
    for r in results:
        lines.append(
            f"| `{r['guideline']}` "
            f"| {r['det_atoms']} | {r['nondet_atoms']} | {r['atom_delta']:+d} "
            f"| {r['det_halluc_rate']:.3f}/{r['nondet_halluc_rate']:.3f} "
            f"| {r['det_trunc_rate']:.3f}/{r['nondet_trunc_rate']:.3f} "
            f"| {r['det_type_diversity']}/{r['nondet_type_diversity']} "
            f"| {r['vocab_jaccard']:.3f} |"
        )

    # Vocabulary diff section (only if there are differences)
    has_diff = any(r["det_only_cids"] or r["nondet_only_cids"] for r in results)
    if has_diff:
        lines.extend([
            "",
            "## Vocabulary Differences",
            "",
        ])
        for r in results:
            if r["det_only_cids"] or r["nondet_only_cids"]:
                lines.append(f"### `{r['guideline']}`")
                if r["det_only_cids"]:
                    lines.append(f"- DET-only ({len(r['det_only_cids'])}): {', '.join(r['det_only_cids'][:10])}")
                if r["nondet_only_cids"]:
                    lines.append(f"- NONDET-only ({len(r['nondet_only_cids'])}): {', '.join(r['nondet_only_cids'][:10])}")
                lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")
    logger.info("Report written to %s", report_path)

    if json_path:
        # Strip non-serializable items for JSON
        json_results = []
        for r in results:
            jr = dict(r)
            json_results.append(jr)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps({
            "date": datetime.now(timezone.utc).isoformat(),
            "det_dir": det_dir,
            "nondet_dir": nondet_dir,
            "aggregate": {
                "total_det_atoms": total_det,
                "total_nondet_atoms": total_nondet,
                "total_det_scenarios": total_det_scn,
                "total_nondet_scenarios": total_nondet_scn,
                "avg_vocab_jaccard": round(avg_jaccard, 3),
                "avg_halluc_det": round(avg_halluc_det, 3),
                "avg_halluc_nondet": round(avg_halluc_nondet, 3),
            },
            "per_graph": json_results,
        }, indent=2) + "\n")
        logger.info("JSON written to %s", json_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare DET vs NONDET SGSC outputs")
    parser.add_argument("--det-dir", required=True, help="Path to DET output dir")
    parser.add_argument("--nondet-dir", required=True, help="Path to NONDET output dir")
    parser.add_argument("--report", default="reports/path_d_day2/v7_det_vs_nondet_comparison.md")
    parser.add_argument("--json", default="reports/path_d_day2/v7_det_vs_nondet_comparison.json")
    args = parser.parse_args()

    det_dir = Path(args.det_dir)
    nondet_dir = Path(args.nondet_dir)

    if not det_dir.exists():
        logger.error("DET dir does not exist: %s", det_dir)
        sys.exit(1)
    if not nondet_dir.exists():
        logger.error("NONDET dir does not exist: %s", nondet_dir)
        sys.exit(1)

    # Discover guidelines (union of both dirs)
    det_gids = {d.name for d in det_dir.iterdir() if d.is_dir()}
    nondet_gids = {d.name for d in nondet_dir.iterdir() if d.is_dir()}
    all_gids = sorted(det_gids | nondet_gids)

    logger.info("Comparing %d guidelines (DET=%d, NONDET=%d)", len(all_gids), len(det_gids), len(nondet_gids))

    results = []
    for gid in all_gids:
        r = compare_guideline(det_dir, nondet_dir, gid)
        logger.info(
            "  %s: DET=%d NONDET=%d delta=%+d jaccard=%.3f",
            gid, r["det_atoms"], r["nondet_atoms"], r["atom_delta"], r["vocab_jaccard"],
        )
        results.append(r)

    write_report(
        results,
        str(det_dir),
        str(nondet_dir),
        Path(args.report),
        Path(args.json) if args.json else None,
    )

    logger.info("Done. %d guidelines compared.", len(results))


if __name__ == "__main__":
    main()
