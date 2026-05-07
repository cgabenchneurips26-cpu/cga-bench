#!/usr/bin/env python3
"""Audit normalizer accuracy for hard-constraint-linked actions.

Loads all CPG graph YAML files, extracts action IDs that appear in hard
constraints (forbidden, timing/deadline, sequence/required_prior_actions),
then checks how many of those canonical actions have at least one normalizer
mapping pointing to them.

Outputs:
  - results/normalizer_hard_linked.json
  - evidence_pack/tables/normalizer_audit.tex
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys
import textwrap

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRAPHS_DIR = PROJECT_ROOT / "cpg_model" / "graphs"
NORMALIZER_FILE = PROJECT_ROOT / "assessor_core" / "action_normalizer.py"
RESULTS_FILE = PROJECT_ROOT / "results" / "normalizer_hard_linked.json"
TEX_FILE = PROJECT_ROOT / "evidence_pack" / "tables" / "normalizer_audit.tex"

GRAPH_FILES = [
    "ssc_sepsis_hour1_bundle.yaml",
    "aha_chest_pain_evaluation.yaml",
    "ada_dka_management.yaml",
    "kdigo_aki_full.yaml",
    "aha_stroke_2019.yaml",
    "aha_heart_failure_2022.yaml",
    "atrial_fibrillation.yaml",
    "cap_pneumonia.yaml",
    "copd_exacerbation.yaml",
    "gi_bleeding.yaml",
    "hypertensive_emergency.yaml",
    "kdigo_contrast_aki.yaml",
    "pulmonary_embolism.yaml",
    "universal_clinical_safety.yaml",
]


# ---------------------------------------------------------------------------
# 1. Extract hard-constraint-linked actions from CPG graphs
# ---------------------------------------------------------------------------
def extract_hard_linked_actions(
    graphs_dir: Path,
    graph_files: list[str],
) -> dict[str, set[str]]:
    """Return actions by constraint type: forbidden, timing, sequence."""
    forbidden: set[str] = set()
    timing: set[str] = set()
    sequence: set[str] = set()

    for filename in graph_files:
        filepath = graphs_dir / filename
        if not filepath.exists():
            print(f"  [WARN] graph not found: {filepath}", file=sys.stderr)
            continue

        with open(filepath, encoding="utf-8") as fh:
            graph = yaml.safe_load(fh)

        nodes = graph.get("nodes", {})
        if not isinstance(nodes, dict):
            continue

        for _node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue

            # --- FORBIDDEN ---
            for action_id in node.get("forbidden_actions", []) or []:
                if isinstance(action_id, str) and action_id:
                    forbidden.add(action_id)

            # --- TIMING (actions with deadlines) ---
            deadlines = node.get("deadlines", {}) or {}
            if isinstance(deadlines, dict):
                for action_id in deadlines:
                    if isinstance(action_id, str) and action_id:
                        timing.add(action_id)

            # --- SEQUENCE (required_prior_actions: key and values) ---
            rpa = node.get("required_prior_actions", {}) or {}
            if isinstance(rpa, dict):
                for after_action, before_list in rpa.items():
                    if isinstance(after_action, str) and after_action:
                        sequence.add(after_action)
                    if isinstance(before_list, list):
                        for before_action in before_list:
                            if isinstance(before_action, str) and before_action:
                                sequence.add(before_action)

    return {
        "forbidden": forbidden,
        "timing": timing,
        "sequence": sequence,
    }


# ---------------------------------------------------------------------------
# 2. Parse normalizer mappings from source
# ---------------------------------------------------------------------------
def _extract_dict_literal(source: str, var_name: str) -> dict[str, str] | None:
    """Extract a top-level dict literal assignment from Python source."""
    pattern = rf"^{re.escape(var_name)}\s*(?::\s*[^=]+)?\s*=\s*\{{"
    match = re.search(pattern, source, re.MULTILINE)
    if not match:
        return None

    start = match.start()
    # Find the matching closing brace
    brace_start = source.index("{", start)
    depth = 0
    idx = brace_start
    while idx < len(source):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        idx += 1

    dict_source = source[brace_start : idx + 1]
    # Remove inline comments (# ...) to make it parseable
    dict_source = re.sub(r"#[^\n]*", "", dict_source)
    try:
        return ast.literal_eval(dict_source)
    except (SyntaxError, ValueError) as exc:
        print(f"  [WARN] Could not parse {var_name}: {exc}", file=sys.stderr)
        return None


def _extract_domain_specific_mappings(source: str) -> dict[str, dict[str, str]]:
    """Extract the nested domain-specific mappings dict."""
    result = _extract_dict_literal(source, "_DEFAULT_DOMAIN_SPECIFIC_MAPPINGS")
    if result is None:
        return {}
    # The value is dict[str, dict[str, str]]
    return result  # type: ignore[return-value]


def load_normalizer_targets(normalizer_path: Path) -> set[str]:
    """Load all canonical target action IDs from the normalizer.

    Returns the set of all values (targets) that the normalizer can produce
    via direct mappings, domain-specific mappings, and synonym groups.
    """
    source = normalizer_path.read_text(encoding="utf-8")

    targets: set[str] = set()

    # Direct mappings
    direct = _extract_dict_literal(source, "_DEFAULT_DIRECT_MAPPINGS")
    if direct:
        targets.update(direct.values())

    # Domain-specific mappings
    domain_specific = _extract_domain_specific_mappings(source)
    for _domain, mapping in domain_specific.items():
        if isinstance(mapping, dict):
            targets.update(mapping.values())

    # Synonym groups (keys are canonical targets)
    synonyms = _extract_dict_literal(source, "_DEFAULT_SYNONYM_GROUPS")
    if synonyms:
        targets.update(synonyms.keys())

    return targets


def load_normalizer_reverse_map(normalizer_path: Path) -> dict[str, list[str]]:
    """Build a reverse map: canonical_target -> [input_keys].

    Counts how many distinct input forms map to each canonical target.
    """
    source = normalizer_path.read_text(encoding="utf-8")
    reverse: dict[str, list[str]] = {}

    # Direct mappings
    direct = _extract_dict_literal(source, "_DEFAULT_DIRECT_MAPPINGS")
    if direct:
        for inp, target in direct.items():
            reverse.setdefault(target, []).append(inp)

    # Domain-specific mappings
    domain_specific = _extract_domain_specific_mappings(source)
    for _domain, mapping in domain_specific.items():
        if isinstance(mapping, dict):
            for inp, target in mapping.items():
                reverse.setdefault(target, []).append(f"{_domain}:{inp}")

    # Synonym groups
    synonyms = _extract_dict_literal(source, "_DEFAULT_SYNONYM_GROUPS")
    if synonyms:
        for target, syns in synonyms.items():
            if isinstance(syns, list):
                for syn in syns:
                    reverse.setdefault(target, []).append(f"synonym:{syn}")

    return reverse


# ---------------------------------------------------------------------------
# 3. Coverage analysis
# ---------------------------------------------------------------------------
def compute_coverage(
    actions_by_type: dict[str, set[str]],
    reverse_map: dict[str, list[str]],
) -> dict[str, dict]:
    """Compute normalizer coverage for each constraint type."""
    results: dict[str, dict] = {}

    for constraint_type, actions in actions_by_type.items():
        covered: list[str] = []
        uncovered: list[str] = []
        mapping_counts: dict[str, int] = {}

        for action_id in sorted(actions):
            inputs = reverse_map.get(action_id, [])
            # An action is "covered" if it has at least one mapping OR
            # it is an identity mapping (input == output, always normalizes
            # to itself).
            count = len(inputs)
            mapping_counts[action_id] = count
            if count > 0:
                covered.append(action_id)
            else:
                uncovered.append(action_id)

        total = len(actions)
        coverage_count = len(covered)
        coverage_pct = (coverage_count / total * 100) if total > 0 else 0.0

        results[constraint_type] = {
            "total": total,
            "covered": coverage_count,
            "coverage_pct": round(coverage_pct, 1),
            "uncovered_actions": uncovered,
            "mapping_counts": mapping_counts,
        }

    return results


# ---------------------------------------------------------------------------
# 4. V7 normalizer impact cross-reference
# ---------------------------------------------------------------------------
V7_MISSES = 8
V7_HARD_LINKED = 1
V7_NOTE = (
    "V7 normalizer audit found 8 total misses, of which 1 was hard-constraint-linked. "
    "This script provides granular per-constraint-type breakdown for the full CPG graph set."
)


# ---------------------------------------------------------------------------
# 5. Output generation
# ---------------------------------------------------------------------------
def write_json_report(
    results: dict[str, dict],
    all_hard_linked: set[str],
    reverse_map: dict[str, list[str]],
    output_path: Path,
) -> None:
    """Write full audit results to JSON."""
    # Overall stats
    total_unique = len(all_hard_linked)
    total_covered = sum(
        1 for a in all_hard_linked if len(reverse_map.get(a, [])) > 0
    )
    total_pct = (total_covered / total_unique * 100) if total_unique > 0 else 0.0

    report = {
        "audit_name": "normalizer_hard_linked_audit",
        "description": "Coverage of normalizer mappings for hard-constraint-linked CPG actions",
        "total_hard_linked_unique_actions": total_unique,
        "total_covered": total_covered,
        "total_coverage_pct": round(total_pct, 1),
        "by_constraint_type": results,
        "v7_cross_reference": {
            "v7_total_misses": V7_MISSES,
            "v7_hard_linked_misses": V7_HARD_LINKED,
            "note": V7_NOTE,
        },
        "graph_files_audited": GRAPH_FILES,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"  JSON report written to {output_path}")


def write_latex_table(
    results: dict[str, dict],
    all_hard_linked: set[str],
    reverse_map: dict[str, list[str]],
    output_path: Path,
) -> None:
    """Write LaTeX table for evidence pack."""
    total_unique = len(all_hard_linked)
    total_covered = sum(
        1 for a in all_hard_linked if len(reverse_map.get(a, [])) > 0
    )
    total_pct = (total_covered / total_unique * 100) if total_unique > 0 else 0.0

    label_map = {
        "forbidden": "FORBIDDEN",
        "timing": "WITHIN (timing)",
        "sequence": "BEFORE (sequence)",
    }

    rows: list[str] = []
    for constraint_type in ["forbidden", "timing", "sequence"]:
        data = results[constraint_type]
        label = label_map[constraint_type]
        total = data["total"]
        covered = data["covered"]
        pct = data["coverage_pct"]
        rows.append(f"{label} & {total} & {covered}/{total} ({pct:.0f}\\%) \\\\")

    table = textwrap.dedent(f"""\
        \\begin{{table}}[t]
        \\centering
        \\caption{{Normalizer coverage for hard-constraint-linked actions.}}
        \\label{{tab:normalizer-audit}}
        \\begin{{tabular}}{{lrr}}
        \\toprule
        Constraint Type & Unique Actions & Normalizer Coverage \\\\
        \\midrule
        {rows[0]}
        {rows[1]}
        {rows[2]}
        \\midrule
        Total & {total_unique} & {total_covered}/{total_unique} ({total_pct:.0f}\\%) \\\\
        \\bottomrule
        \\end{{tabular}}
        \\end{{table}}
    """)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(table)

    print(f"  LaTeX table written to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the normalizer hard-linked audit."""
    print("=== Normalizer Hard-Linked Audit ===\n")

    # Step 1: Extract hard-linked actions from CPG graphs
    print("1. Loading CPG graph files...")
    actions_by_type = extract_hard_linked_actions(GRAPHS_DIR, GRAPH_FILES)
    for ctype, actions in actions_by_type.items():
        print(f"   {ctype}: {len(actions)} unique actions")

    all_hard_linked = set()
    for actions in actions_by_type.values():
        all_hard_linked.update(actions)
    print(f"   Total unique hard-linked: {len(all_hard_linked)}")

    # Step 2: Load normalizer mappings
    print("\n2. Loading normalizer mappings...")
    reverse_map = load_normalizer_reverse_map(NORMALIZER_FILE)
    total_targets = len(reverse_map)
    total_inputs = sum(len(v) for v in reverse_map.values())
    print(f"   {total_targets} canonical targets, {total_inputs} input mappings")

    # Step 3: Compute coverage
    print("\n3. Computing coverage...")
    results = compute_coverage(actions_by_type, reverse_map)
    for ctype in ["forbidden", "timing", "sequence"]:
        data = results[ctype]
        print(
            f"   {ctype}: {data['covered']}/{data['total']} "
            f"({data['coverage_pct']}%)"
        )
        if data["uncovered_actions"]:
            for action_id in data["uncovered_actions"]:
                print(f"     [MISS] {action_id}")

    # Overall
    total_covered = sum(
        1 for a in all_hard_linked if len(reverse_map.get(a, [])) > 0
    )
    total_pct = (
        (total_covered / len(all_hard_linked) * 100)
        if all_hard_linked
        else 0.0
    )
    print(f"\n   Overall: {total_covered}/{len(all_hard_linked)} ({total_pct:.1f}%)")

    # Step 4: V7 cross-reference
    print(f"\n4. V7 cross-reference: {V7_MISSES} misses, {V7_HARD_LINKED} hard-linked")

    # Step 5: Write outputs
    print("\n5. Writing outputs...")
    write_json_report(results, all_hard_linked, reverse_map, RESULTS_FILE)
    write_latex_table(results, all_hard_linked, reverse_map, TEX_FILE)

    print("\nDone.")


if __name__ == "__main__":
    main()
