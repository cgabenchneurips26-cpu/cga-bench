"""CAV v0.5 Phase 5 — Spot-Check Form Generator.

Stratified sample of 30 dropped extension-tier IDs, with parsed-CPG source
text snippets where available. Output as markdown (for anonymous-user review) + CSV
(spreadsheet-friendly).

Stratification (fixed seed = 20260501 for reproducibility):
- Top 10 by total occurrence count (highest paper impact)
- Random 10 from medication kind (RxNorm decision validation)
- Random 10 from non-medication kinds (procedure/assessment/consult/lab/imaging/disposition/other)

Source-context lookup (best-effort, deterministic, no LLM):
1. Try cpg_sources/<graph_ref>.parsed.json directly.
2. Iterate cpg_sources/*.parsed.json; match if data.get("graph_id") == graph_ref.
3. Case-insensitive substring match on filename.
4. Naive substring match on canonical_id (with underscores -> spaces) in
   recommendations[*].text. Extract ±250 char window around first hit.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED = 20260501
SNIPPET_RADIUS = 250


def stratified_sample(
    dropped_entries: dict[str, dict[str, Any]],
    n_top: int = 10,
    n_med: int = 10,
    n_other: int = 10,
) -> list[tuple[str, dict[str, Any], str]]:
    """Return list of (canonical_id, entry, stratum_label) tuples in display order."""
    rng = random.Random(SEED)
    items = list(dropped_entries.items())

    by_occ = sorted(items, key=lambda kv: -len(kv[1]["occurrences"]))
    top_set = {cid for cid, _ in by_occ[:n_top]}
    top_rows = [(cid, entry, "top_occurrence") for cid, entry in by_occ[:n_top]]

    medication_pool = [
        (cid, entry) for cid, entry in items if entry["action_kind"] == "medication" and cid not in top_set
    ]
    non_med_pool = [(cid, entry) for cid, entry in items if entry["action_kind"] != "medication" and cid not in top_set]

    med_sample = rng.sample(medication_pool, k=min(n_med, len(medication_pool)))
    other_sample = rng.sample(non_med_pool, k=min(n_other, len(non_med_pool)))

    med_rows = [(cid, entry, "random_medication") for cid, entry in med_sample]
    other_rows = [(cid, entry, "random_non_medication") for cid, entry in other_sample]

    return top_rows + med_rows + other_rows


def _load_parsed_index(corpus_dir: Path) -> dict[str, Path]:
    """Build index of graph_id -> parsed_json_path."""
    out: dict[str, Path] = {}
    if not corpus_dir.is_dir():
        return out
    for p in sorted(corpus_dir.glob("*.parsed.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("graph_id"):
            out[str(data["graph_id"])] = p
    return out


def _filename_substring_match(corpus_dir: Path, graph_ref: str) -> Path | None:
    """Case-insensitive substring match: graph_ref vs file stem."""
    if not corpus_dir.is_dir() or not graph_ref:
        return None
    needle = graph_ref.lower().replace("_", "").replace("-", "")
    for p in corpus_dir.glob("*.parsed.json"):
        stem = p.name.lower().replace("_", "").replace("-", "").replace(".parsed.json", "")
        if needle in stem or stem in needle:
            return p
    return None


def resolve_corpus_file(
    corpus_dir: Path,
    graph_ref: str,
    parsed_index: dict[str, Path],
) -> tuple[Path | None, str]:
    """Return (path or None, lookup-method-tag)."""
    if not graph_ref:
        return None, "no_graph_ref"
    direct = corpus_dir / f"{graph_ref}.parsed.json"
    if direct.is_file():
        return direct, "direct_filename"
    if graph_ref in parsed_index:
        return parsed_index[graph_ref], "graph_id_field"
    fn = _filename_substring_match(corpus_dir, graph_ref)
    if fn:
        return fn, "filename_substring"
    return None, "not_found"


def extract_snippet(parsed_json_path: Path, canonical_id: str) -> str:
    """Naive substring search in concatenated recommendations[*].text."""
    try:
        data = json.loads(parsed_json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"[parse error: {exc}]"
    recs = data.get("recommendations") or []
    needle = canonical_id.replace("_", " ").strip().lower()
    if not needle:
        return "[empty needle]"
    blob_parts: list[str] = []
    for r in recs:
        if isinstance(r, dict):
            t = r.get("text") or ""
            if t:
                blob_parts.append(str(t))
    blob = "\n".join(blob_parts)
    blob_lower = blob.lower()
    idx = blob_lower.find(needle)
    if idx == -1:
        # Try the last token (often a drug name or specific noun)
        tokens = needle.split()
        if len(tokens) >= 2:
            last = tokens[-1]
            idx = blob_lower.find(last)
    if idx == -1:
        return "[no source match]"
    start = max(0, idx - SNIPPET_RADIUS)
    end = min(len(blob), idx + SNIPPET_RADIUS)
    snippet = blob[start:end].replace("\n", " ").replace("|", "\\|").strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(blob):
        snippet = snippet + "..."
    return snippet


def _first_graph_ref(entry: dict[str, Any]) -> str:
    for occ in entry["occurrences"]:
        gref = occ.get("graph_ref")
        if gref:
            return str(gref)
    return ""


def build_rows(
    sampled: list[tuple[str, dict[str, Any], str]],
    corpus_dir: Path,
) -> list[dict[str, str]]:
    parsed_index = _load_parsed_index(corpus_dir)
    rows: list[dict[str, str]] = []
    for i, (cid, entry, stratum) in enumerate(sampled, 1):
        graph_ref = _first_graph_ref(entry)
        n_occ = len(entry["occurrences"])
        kind = entry["action_kind"]
        if not graph_ref:
            snippet = "[no graph_ref in occurrences]"
        else:
            cpg_path, _method = resolve_corpus_file(corpus_dir, graph_ref, parsed_index)
            if cpg_path is None:
                snippet = f"[CPG file not found for graph_ref={graph_ref}]"
            else:
                snippet = extract_snippet(cpg_path, cid)
        rows.append(
            {
                "#": str(i),
                "stratum": stratum,
                "canonical_id": cid,
                "kind": kind,
                "n_occ": str(n_occ),
                "graph_ref": graph_ref or "(none)",
                "source_snippet": snippet,
                "verdict": "",
            }
        )
    return rows


def write_markdown(rows: list[dict[str, str]], path: Path) -> None:
    lines: list[str] = []
    lines.append("# CAV v0.5 — Spot-Check Form")
    lines.append("")
    lines.append("**For each entry mark exactly one verdict:**")
    lines.append("")
    lines.append(
        "- `author_inject` — the action is genuinely a scenario-author-introduced concept not in the source CPG"
    )
    lines.append("- `extraction_miss` — the source CPG mentions this concept but our graph YAML failed to capture it")
    lines.append("- `unclear` — cannot tell from the snippet")
    lines.append("")
    lines.append("**Decision rule** (apply to extraction_miss count out of 30):")
    lines.append("")
    lines.append("- `< 5` → Strict policy holds, proceed to α-6")
    lines.append("- `5-10` → Strict + paper graph-extraction-limitation disclosure, proceed to α-6")
    lines.append("- `> 10` → STOP, decide whether to patch graph YAMLs")
    lines.append("")
    lines.append("| # | stratum | canonical_id | kind | n_occ | graph_ref | source_snippet | verdict |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        verdict_box = "☐ author_inject ☐ extraction_miss ☐ unclear"
        snippet = r["source_snippet"][:300] + ("..." if len(r["source_snippet"]) > 300 else "")
        snippet = snippet.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {r['#']} | {r['stratum']} | `{r['canonical_id']}` | {r['kind']} | "
            f"{r['n_occ']} | {r['graph_ref']} | {snippet} | {verdict_box} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    fieldnames = ["#", "stratum", "canonical_id", "kind", "n_occ", "graph_ref", "source_snippet", "verdict"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def print_inline(rows: list[dict[str, str]]) -> None:
    print("=" * 78)
    print("CAV v0.5 SPOT-CHECK — 30 entries (review verdict for each):")
    print("=" * 78)
    print()
    print("Decision rule:")
    print("  extraction_miss < 5  → Strict policy holds, proceed to α-6")
    print("  extraction_miss 5-10 → Strict + paper disclosure, proceed to α-6")
    print("  extraction_miss > 10 → STOP, patch graph YAMLs")
    print()
    cur_stratum = ""
    for r in rows:
        if r["stratum"] != cur_stratum:
            cur_stratum = r["stratum"]
            print()
            print(f"--- stratum: {cur_stratum} ---")
        print(f"[{r['#']:>2}] kind={r['kind']:12s}  n_occ={r['n_occ']:>3}  graph={r['graph_ref']}")
        print(f"      canonical: {r['canonical_id']}")
        snippet_short = r["source_snippet"][:600]
        snippet_short = snippet_short.replace("\n", " ")
        print(f"      snippet:   {snippet_short}")
        print("      verdict:   ☐ author_inject  ☐ extraction_miss  ☐ unclear")
        print()
    print("=" * 78)
    print("anonymous-user MANUAL REVIEW (target ~1h):")
    print("  1. cav_v0_5/05_spotcheck_form.md  (markdown)")
    print("  2. cav_v0_5/05_spotcheck_form.csv (spreadsheet)")
    print("  3. Mark each verdict, count extraction_miss, reply with the count.")
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(description="CAV v0.5 Phase 5: spot-check form")
    parser.add_argument(
        "--dropped",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "cav_v0_5_dropped.json",
        help="Phase 4 dropped-entries JSON.",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=REPO_ROOT / "cpg_sources",
        help="Directory of parsed CPG source JSONs (*.parsed.json).",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "05_spotcheck_form.md",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "05_spotcheck_form.csv",
    )
    args = parser.parse_args()

    if not args.dropped.is_file():
        print(f"[ERROR] --dropped not found: {args.dropped}", file=sys.stderr)
        return 2

    data = json.loads(args.dropped.read_text(encoding="utf-8"))
    dropped_entries = data.get("dropped_entries", {})
    if not dropped_entries:
        print("[ERROR] no dropped_entries to sample", file=sys.stderr)
        return 1

    sampled = stratified_sample(dropped_entries)
    rows = build_rows(sampled, args.corpus_dir)

    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(rows, args.output_md)
    write_csv(rows, args.output_csv)
    print(f"[INFO] Wrote {args.output_md}")
    print(f"[INFO] Wrote {args.output_csv}")
    print()
    print_inline(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
