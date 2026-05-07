"""YAML graph source traceability audit.

Checks all graph nodes for required source fields and quote verification
status (when ``_quote_verification`` metadata is present from the grounding
pipeline).

Exit code 0 = all fields present, 1 = issues found.
"""

from pathlib import Path
import sys

import yaml

REQUIRED_FIELDS = ["source_guideline"]
# source_section, source_page, source_quote are recommended but some nodes
# (especially decision/enquiry) may not have them. Only require source_guideline.

RECOMMENDED_FIELDS = ["source_section", "source_page", "source_quote"]


def audit(graphs_dir: str = "cpg_model/graphs") -> tuple[list[str], list[str]]:
    """Audit YAML graphs for source traceability.

    Returns:
        (errors, warnings) — errors are missing required fields, warnings are missing recommended.
    """
    errors: list[str] = []
    warnings: list[str] = []

    graphs_path = Path(graphs_dir)
    if not graphs_path.exists():
        graphs_path = Path(__file__).parent.parent.parent / graphs_dir

    for f in sorted(graphs_path.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        nodes = data.get("nodes", {})
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            for field in REQUIRED_FIELDS:
                if not node.get(field):
                    errors.append(f"{f.name}:{node_id} — missing {field}")
            for field in RECOMMENDED_FIELDS:
                if not node.get(field):
                    warnings.append(f"{f.name}:{node_id} — missing recommended {field}")

    return errors, warnings


def audit_quote_verification(graphs_dir: str = "cpg_model/graphs/auto") -> tuple[list[str], list[str]]:
    """Audit quote verification status of auto-generated graphs.

    Checks ``_quote_verification`` metadata injected by
    ``ground_graph_quotes.py``.  Nodes that have been grounded should have
    ``source_page`` populated; nodes flagged UNGROUNDED are errors.

    Returns:
        (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    graphs_path = Path(graphs_dir)
    if not graphs_path.exists():
        graphs_path = Path(__file__).parent.parent.parent / graphs_dir

    if not graphs_path.exists():
        return errors, warnings

    for f in sorted(graphs_path.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        nodes = data.get("nodes", {})
        has_any_verification = False

        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue

            meta = node.get("_quote_verification")
            if meta is not None:
                has_any_verification = True
                status = meta.get("status", "")
                if status == "UNGROUNDED":
                    errors.append(f"{f.name}:{node_id} — quote UNGROUNDED against corpus")

            # source_page NULL check (only warn if graph has verification metadata)
            if has_any_verification and node.get("source_page") is None:
                warnings.append(f"{f.name}:{node_id} — source_page is NULL (not grounded)")

    return errors, warnings


if __name__ == "__main__":
    errors, warnings = audit()

    if warnings:
        print(f"\n=== Warnings ({len(warnings)}) ===")
        for w in warnings[:20]:  # Show first 20
            print(f"  WARN: {w}")
        if len(warnings) > 20:
            print(f"  ... and {len(warnings) - 20} more warnings")

    if errors:
        print(f"\n=== Errors ({len(errors)}) ===")
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    else:
        print(f"\n=== Source audit PASSED (0 errors, {len(warnings)} warnings) ===")

    # Also run quote verification audit on auto graphs
    qv_errors, qv_warnings = audit_quote_verification()
    if qv_errors or qv_warnings:
        print(f"\n=== Quote Verification ({len(qv_errors)} errors, {len(qv_warnings)} warnings) ===")
        for e in qv_errors:
            print(f"  ERROR: {e}")
        for w in qv_warnings[:10]:
            print(f"  WARN: {w}")
        if len(qv_warnings) > 10:
            print(f"  ... and {len(qv_warnings) - 10} more warnings")

    total_errors = len(errors) + len(qv_errors)
    if total_errors:
        sys.exit(1)
    else:
        sys.exit(0)
