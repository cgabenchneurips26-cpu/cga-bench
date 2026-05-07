"""Section F: Temporal Constraints 검증."""

from __future__ import annotations

from pathlib import Path
import traceback

import yaml

ROOT = Path(__file__).resolve().parents[2]
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"

NEW_GRAPHS = [
    "anaphylaxis_management",
    "acls_cardiac_arrest",
    "status_epilepticus",
    "gina_asthma_exacerbation",
    "idsa_meningitis",
    "toxicology_management",
    "aba_burn_resuscitation",
    "aabb_transfusion",
    "acog_obstetric_hemorrhage",
    "pals_pediatric_emergency",
    "apa_agitation_management",
]


def run_f1_deadline_entries() -> None:
    """F.1: Parse all graph YAMLs and report deadline entries."""
    print("=" * 60)
    print("F.1: Deadline entries across all graphs")
    print("=" * 60)

    graph_files = sorted(GRAPHS_DIR.glob("*.yaml"))
    print(f"Scanning {len(graph_files)} graph files\n")

    total_deadline_entries = 0
    graphs_with_deadlines: list[str] = []
    graphs_without_deadlines: list[str] = []
    new_graph_ids: set[str] = set(NEW_GRAPHS)

    for graph_path in graph_files:
        try:
            with open(graph_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            graph_id: str = data.get("graph_id", graph_path.stem)
            nodes: dict = data.get("nodes", {})
            graph_deadlines: dict[str, float] = {}

            for node_id, node_data in nodes.items():
                deadlines = node_data.get("deadlines")
                if isinstance(deadlines, dict) and deadlines:
                    for action_id, minutes in deadlines.items():
                        graph_deadlines[f"{node_id}/{action_id}"] = minutes

            deadline_count = len(graph_deadlines)
            total_deadline_entries += deadline_count

            if deadline_count > 0:
                graphs_with_deadlines.append(graph_id)
                # Print sample deadlines (first 2)
                samples = list(graph_deadlines.items())[:2]
                sample_str = ", ".join(
                    f"{k}={v}min" for k, v in samples
                )
                remaining = deadline_count - len(samples)
                suffix = f" (+{remaining} more)" if remaining > 0 else ""
                print(f"  {graph_id:40s}  deadlines={deadline_count:3d}  sample: {sample_str}{suffix}")
            else:
                graphs_without_deadlines.append(graph_id)
                print(f"  {graph_id:40s}  deadlines=  0")

        except Exception:
            print(f"  ERROR  {graph_path.stem}")
            traceback.print_exc()

    print(f"\nTotal deadline entries across all graphs: {total_deadline_entries}")
    print(f"Graphs with deadlines:    {len(graphs_with_deadlines)}")
    print(f"Graphs without deadlines: {len(graphs_without_deadlines)}")

    # Report on new graphs specifically
    print("\n--- New/held-out graph deadline status ---")
    for gid in NEW_GRAPHS:
        if gid in graphs_with_deadlines:
            print(f"  {gid:40s}  HAS deadlines")
        elif gid in graphs_without_deadlines:
            print(f"  {gid:40s}  NO deadlines")
        else:
            print(f"  {gid:40s}  NOT FOUND in scan")

    # Report which graphs have deadlines vs not (for reference)
    print("\n--- All graphs with deadlines ---")
    for gid in sorted(graphs_with_deadlines):
        marker = " [NEW]" if gid in new_graph_ids else ""
        print(f"  {gid}{marker}")

    print("\n--- All graphs without deadlines ---")
    for gid in sorted(graphs_without_deadlines):
        marker = " [NEW]" if gid in new_graph_ids else ""
        print(f"  {gid}{marker}")

    print(f"\nF.1 summary: {total_deadline_entries} deadline entries, "
          f"{len(graphs_with_deadlines)} graphs with, "
          f"{len(graphs_without_deadlines)} graphs without")


def main() -> None:
    """Run all Section F audits."""
    run_f1_deadline_entries()
    print("\n" + "=" * 60)
    print("Section F complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
