"""CI graph-load gate: loads all CPG graphs through CPGEngine and reports validation results.

Wraps P1's ``_validate_graph_structure()`` into a CI-runnable script.
Exit code 0 = no errors across all graphs; exit 1 = at least one error.

Usage:
    PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject \
        python cga_bench/scripts/ci/audit_graph_validity.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

from cga_bench.cpg_engine.engine import CPGEngineFactory  # noqa: E402


def audit_graphs(
    graphs_dir: str | Path | None = None,
) -> dict:
    """Load every CPG YAML through CPGEngine and collect validation results.

    Returns a dict with per-graph results and aggregate counts.
    """
    graphs_dir = REPO_ROOT / "cpg_model" / "graphs" if graphs_dir is None else Path(graphs_dir)

    results: dict[str, dict] = {}
    total_errors = 0
    total_warnings = 0
    total_checks = 0
    graphs_ok = 0

    for yaml_file in sorted(graphs_dir.glob("*.yaml")):
        graph_id = yaml_file.stem
        try:
            CPGEngineFactory.clear_cache()
            engine = CPGEngineFactory.load_from_file(str(yaml_file))
            vr = engine._validation_result
            results[graph_id] = {
                "ok": vr.ok,
                "errors": vr.errors,
                "warnings": vr.warnings,
            }
            total_errors += len(vr.errors)
            total_warnings += len(vr.warnings)
            total_checks += 1
            if vr.ok:
                graphs_ok += 1
        except Exception as e:
            results[graph_id] = {
                "ok": False,
                "errors": [f"Failed to load: {e}"],
                "warnings": [],
            }
            total_errors += 1
            total_checks += 1

    n_graphs = len(results)
    n_checks_per_graph = 6  # P1 validator performs 6 structural checks

    return {
        "total_graphs": n_graphs,
        "graphs_ok": graphs_ok,
        "graphs_with_errors": n_graphs - graphs_ok,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "total_validations": n_graphs * n_checks_per_graph,
        "checks_per_graph": n_checks_per_graph,
        "per_graph": results,
    }


def main() -> int:
    """Run graph validity audit and print results."""
    report = audit_graphs()

    print(
        f"Graph Validity Audit — {report['total_graphs']} graphs, "
        f"{report['checks_per_graph']} checks each = "
        f"{report['total_validations']} total validations"
    )
    print(f"  OK: {report['graphs_ok']}/{report['total_graphs']}")
    print(f"  Errors: {report['total_errors']}")
    print(f"  Warnings: {report['total_warnings']}")

    if report["total_errors"] > 0:
        print("\n--- Graphs with errors ---")
        for gid, r in report["per_graph"].items():
            if not r["ok"]:
                for e in r["errors"]:
                    print(f"  [{gid}] ERROR: {e}")

    if report["total_warnings"] > 0:
        print("\n--- Warnings ---")
        for gid, r in report["per_graph"].items():
            for w in r["warnings"]:
                print(f"  [{gid}] WARN: {w}")

    # LaTeX macro output
    print("\n% LaTeX macros")
    print(f"\\providecommand{{\\graphValidatorChecksN}}{{{report['checks_per_graph']}}}")
    print(f"\\providecommand{{\\graphValidatorTotalN}}{{{report['total_validations']}}}")
    print(f"\\providecommand{{\\graphValidatorGraphsN}}{{{report['total_graphs']}}}")
    print(f"\\providecommand{{\\graphValidatorErrorsN}}{{{report['total_errors']}}}")
    print(f"\\providecommand{{\\graphValidatorWarningsN}}{{{report['total_warnings']}}}")

    # JSON report
    report_path = REPO_ROOT / "evidence_pack" / "analysis" / "graph_validity_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nJSON report written to {report_path}")

    return 0 if report["total_errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
