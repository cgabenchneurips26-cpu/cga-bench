"""CAV v0.5 Phase 1 — Vocabulary Harvesting.

Walks every CPG graph YAML and every scenario YAML, collects action IDs from
mandatory/allowed/forbidden fields, normalises each via ActionNormalizer, and
writes a single deduplicated raw-harvest JSON.

Path-aware: --graphs / --scenarios / --output flags so the same code can be
re-pointed at the v7 corpus on 2026-05-03 to build CAV v0.6.

Scope (CAV v0.5 = v6 paper §4 headline scope):
- Graphs: `<graphs>/*.yaml` top-level only (25 manual graphs).
- Scenarios: `<scenarios>/*.yaml` top-level only (~709 manual scenarios, of
  which paper benchmarks 706 after e2e-test filtering).

Excluded by default: `<graphs>/auto/`, `<scenarios>/auto/`, `<scenarios>/auto_v2/`.
This matches the corpus that produced the paper's 19,062-episode headline
(706 × 9 models × 3 runs). Use `--include-auto` to additionally harvest the
auto/ subdirectories for ablation / V7 prep work.

Conditional rules: `nodes[*].conditional_rules[*].effect.actions` ARE harvested
and folded into the corresponding field_type (FORBIDDEN→graph_forbidden,
MANDATORY→graph_mandatory, ALLOWED→graph_allowed). Otherwise actions that only
appear in conditional rules would also fall to extension tier.

Output: cav_v0_5/01_raw_harvest.json
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

from cga_bench.assessor_core.action_normalizer import ActionNormalizer  # noqa: E402

# Conditional rule effect types -> graph field type
_COND_EFFECT_TO_FIELD = {
    "MANDATORY": "graph_mandatory",
    "REQUIRED": "graph_mandatory",
    "FORBIDDEN": "graph_forbidden",
    "ALLOWED": "graph_allowed",
}


def _collect_graph_actions(
    graph_data: dict[str, Any],
    graph_id: str,
) -> list[tuple[str, str, str]]:
    """Extract (raw_action_id, field_type, node_id) triples from one graph YAML.

    field_type ∈ {graph_mandatory, graph_allowed, graph_forbidden}.
    """
    triples: list[tuple[str, str, str]] = []
    nodes = graph_data.get("nodes", {}) or {}
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_id in node.get("mandatory_actions", []) or []:
            triples.append((action_id, "graph_mandatory", node_id))
        for action_id in node.get("allowed_actions", []) or []:
            triples.append((action_id, "graph_allowed", node_id))
        for action_id in node.get("forbidden_actions", []) or []:
            triples.append((action_id, "graph_forbidden", node_id))
        for rule in node.get("conditional_rules", []) or []:
            effect = rule.get("effect", {}) or {}
            etype = effect.get("type", "")
            field = _COND_EFFECT_TO_FIELD.get(etype.upper())
            if not field:
                continue
            for action_id in effect.get("actions", []) or []:
                triples.append((action_id, field, node_id))
    return triples


def _iter_scenario_files(scenarios_dir: Path, include_auto: bool) -> list[Path]:
    """Yield scenario YAML paths.

    Default scope = paper §4 headline corpus = top-level *.yaml only
    (excludes auto/, auto_v2/, _archive*/, etc.).

    If include_auto=True, also walks scenarios_dir/auto/*.yaml. auto_v2/ is
    NEVER walked (V7 expansion, out of v6 paper scope).
    """
    files: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        files.extend(scenarios_dir.glob(ext))
        if include_auto:
            files.extend((scenarios_dir / "auto").glob(ext))
    return sorted(files)


def _collect_scenario_actions(
    scenario_data: dict[str, Any],
) -> list[tuple[str, str, str, str]]:
    """Extract (raw_action_id, field_type, scenario_id, graph_ref) tuples.

    field_type ∈ {scenario_expected, scenario_forbidden}. Each YAML file may
    contain a top-level `scenarios` dict (dict-of-dict) or a single scenario
    dict; support both.
    """
    out: list[tuple[str, str, str, str]] = []

    def _emit(scenario_obj: dict[str, Any], fallback_id: str) -> None:
        if not isinstance(scenario_obj, dict):
            return
        scenario_id = str(scenario_obj.get("scenario_id") or fallback_id)
        graph_ref = str(scenario_obj.get("guideline_graph") or "")
        for a in scenario_obj.get("expected_actions", []) or []:
            out.append((a, "scenario_expected", scenario_id, graph_ref))
        for a in scenario_obj.get("forbidden_actions", []) or []:
            out.append((a, "scenario_forbidden", scenario_id, graph_ref))

    if "scenarios" in scenario_data and isinstance(scenario_data["scenarios"], dict):
        for sid, sobj in scenario_data["scenarios"].items():
            _emit(sobj, sid)
    else:
        _emit(scenario_data, "<inline>")
    return out


def _normalizer_version() -> str:
    """Return short git SHA + mtime of the normalizer file for reproducibility."""
    norm_path = REPO_ROOT / "assessor_core" / "action_normalizer.py"
    try:
        sha = (
            subprocess.check_output(
                ["git", "log", "-1", "--format=%h", "--", str(norm_path)],
                cwd=REPO_ROOT,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        sha = "unknown"
    mtime = datetime.fromtimestamp(norm_path.stat().st_mtime, tz=UTC).isoformat()
    return f"{sha}@{mtime}"


def harvest(graphs_dir: Path, scenarios_dir: Path, include_auto: bool = False) -> dict[str, Any]:
    normalizer = ActionNormalizer()

    # canonical_id -> {"raw_forms": set[str], "occurrences": list[dict]}
    entries: dict[str, dict[str, Any]] = defaultdict(lambda: {"raw_forms": set(), "occurrences": []})

    # ---- Walk graphs ----
    graph_files = sorted(graphs_dir.glob("*.yaml"))
    if include_auto:
        graph_files += sorted((graphs_dir / "auto").glob("*.yaml"))
    n_graphs = 0
    for yaml_file in graph_files:
        if "_archive" in yaml_file.parts:
            continue
        n_graphs += 1
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] Failed to parse {yaml_file.name}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, dict):
            continue
        graph_id = str(data.get("graph_id") or yaml_file.stem)
        for raw_id, field_type, node_id in _collect_graph_actions(data, graph_id):
            canonical = normalizer.normalize(raw_id, cpg_id=graph_id)
            entries[canonical]["raw_forms"].add(raw_id)
            entries[canonical]["occurrences"].append(
                {
                    "source": field_type,
                    "graph_id": graph_id,
                    "node_id": node_id,
                }
            )

    # ---- Walk scenarios ----
    scenario_files = _iter_scenario_files(scenarios_dir, include_auto=include_auto)
    n_scenarios = 0
    for yaml_file in scenario_files:
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] Failed to parse {yaml_file.name}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, dict):
            continue
        for raw_id, field_type, scenario_id, graph_ref in _collect_scenario_actions(data):
            n_scenarios_in_file = 1  # increment per scenario emission below
            canonical = normalizer.normalize(raw_id, cpg_id=graph_ref or None)
            entries[canonical]["raw_forms"].add(raw_id)
            entries[canonical]["occurrences"].append(
                {
                    "source": field_type,
                    "scenario_id": scenario_id,
                    "graph_ref": graph_ref,
                }
            )
        # Count distinct scenario_ids in this file
        if "scenarios" in data and isinstance(data["scenarios"], dict):
            n_scenarios += len(data["scenarios"])
        else:
            n_scenarios += 1

    # ---- Serialise ----
    serialised_entries: dict[str, dict[str, Any]] = {}
    for canonical, entry in sorted(entries.items()):
        serialised_entries[canonical] = {
            "raw_forms": sorted(entry["raw_forms"]),
            "occurrences": entry["occurrences"],
        }

    return {
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "n_graphs": n_graphs,
            "n_scenarios": n_scenarios,
            "n_scenario_files": len(scenario_files),
            "normalizer_version": _normalizer_version(),
            "graphs_dir": str(graphs_dir),
            "scenarios_dir": str(scenarios_dir),
        },
        "entries": serialised_entries,
    }


def _print_summary(result: dict[str, Any]) -> tuple[int, int]:
    """Print summary; returns (total_entries, scenario_only_count) for sanity-stop."""
    entries = result["entries"]
    total = len(entries)

    graph_only = 0
    scenario_only = 0
    both = 0
    occ_count: dict[str, int] = {}
    raw_form_count: dict[str, int] = {}

    for canonical, entry in entries.items():
        sources = {occ["source"] for occ in entry["occurrences"]}
        in_graph = any(s.startswith("graph_") for s in sources)
        in_scenario = any(s.startswith("scenario_") for s in sources)
        if in_graph and in_scenario:
            both += 1
        elif in_graph:
            graph_only += 1
        else:
            scenario_only += 1
        occ_count[canonical] = len(entry["occurrences"])
        raw_form_count[canonical] = len(entry["raw_forms"])

    print("=== CAV Phase 1: Vocabulary Harvest ===")
    print(f"  Graphs walked:    {result['metadata']['n_graphs']}")
    print(f"  Scenarios walked: {result['metadata']['n_scenarios']} ({result['metadata']['n_scenario_files']} files)")
    print(f"  Normalizer:       {result['metadata']['normalizer_version']}")
    print("")
    print(f"  Total unique canonical IDs: {total}")
    print(f"    graph-only:    {graph_only}")
    print(f"    scenario-only: {scenario_only}  ← extension-tier candidates")
    print(f"    both:          {both}")
    print("")
    print("  Top 10 by total occurrence count:")
    for canonical, n in sorted(occ_count.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {n:5d}  {canonical}")
    print("")
    print("  Top 10 with most raw_form variants:")
    for canonical, n in sorted(raw_form_count.items(), key=lambda kv: -kv[1])[:10]:
        if n < 2:
            break
        forms = entries[canonical]["raw_forms"]
        print(f"    {n:5d}  {canonical}  <- {forms[:5]}{'...' if len(forms) > 5 else ''}")
    return total, scenario_only


def main() -> int:
    parser = argparse.ArgumentParser(description="CAV v0.5 Phase 1: harvest vocabulary")
    parser.add_argument(
        "--graphs",
        type=Path,
        default=REPO_ROOT / "cpg_model" / "graphs",
        help="Directory containing CPG graph YAMLs (walks *.yaml + auto/*.yaml).",
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=REPO_ROOT / "configs" / "scenarios",
        help="Directory of scenario YAMLs (rglob, skips auto_v2/).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "01_raw_harvest.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--include-auto",
        action="store_true",
        help="Also walk graphs/auto/ and scenarios/auto/ (NOT auto_v2/). "
        "Off by default = paper §4 headline scope (manual only).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if total entries < 400 or > 1000, or scenario-only count < 50 or > 200.",
    )
    args = parser.parse_args()

    if not args.graphs.is_dir():
        print(f"[ERROR] --graphs not found: {args.graphs}", file=sys.stderr)
        return 2
    if not args.scenarios.is_dir():
        print(f"[ERROR] --scenarios not found: {args.scenarios}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = harvest(args.graphs, args.scenarios, include_auto=args.include_auto)
    result["metadata"]["include_auto"] = args.include_auto
    args.output.write_text(json.dumps(result, indent=2, sort_keys=False), encoding="utf-8")
    print(f"[INFO] Wrote {args.output} ({len(result['entries'])} entries)")
    print()

    total, scenario_only = _print_summary(result)

    if args.strict:
        if not (400 <= total <= 1000):
            print(f"[STOP] total entries {total} outside expected band [400,1000]", file=sys.stderr)
            return 1
        if not (50 <= scenario_only <= 200):
            print(f"[STOP] scenario-only {scenario_only} outside expected band [50,200]", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
