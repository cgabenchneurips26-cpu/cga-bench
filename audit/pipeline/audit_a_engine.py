"""Section A: CPG Engine이 새 Graph를 정상 처리하는가?"""

from __future__ import annotations

from collections import deque
from pathlib import Path
import traceback

import yaml

from cga_bench.cpg_engine.engine import CPGEngineFactory

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


def run_a1_load_all_graphs() -> tuple[int, int]:
    """A.1: Load all graphs via CPGEngineFactory.

    Returns:
        (ok_count, fail_count)
    """
    print("=" * 60)
    print("A.1: Load all graphs via CPGEngineFactory")
    print("=" * 60)

    graph_files = sorted(GRAPHS_DIR.glob("*.yaml"))
    print(f"Found {len(graph_files)} graph files in {GRAPHS_DIR}\n")

    ok_count = 0
    fail_count = 0

    for graph_path in graph_files:
        try:
            CPGEngineFactory.clear_cache()
            engine = CPGEngineFactory.load_from_file(str(graph_path))
            node_count = len(engine.graph.nodes)
            entry = engine.graph.entry_node
            print(f"  OK  {graph_path.stem:40s}  nodes={node_count:3d}  entry={entry}")
            ok_count += 1
        except Exception:
            fail_count += 1
            print(f"  FAIL {graph_path.stem}")
            traceback.print_exc()

    print(f"\nA.1 summary: {ok_count} OK, {fail_count} FAIL (total {ok_count + fail_count})")
    return ok_count, fail_count


def run_a2_node_traversal() -> tuple[int, int]:
    """A.2: BFS traversal for 11 new/held-out graphs.

    Returns:
        (ok_count, warn_count)
    """
    print("\n" + "=" * 60)
    print("A.2: Node traversal for 11 new/held-out graphs")
    print("=" * 60)

    ok_count = 0
    warn_count = 0

    for graph_name in NEW_GRAPHS:
        graph_path = GRAPHS_DIR / f"{graph_name}.yaml"
        if not graph_path.exists():
            print(f"  SKIP {graph_name:40s}  file not found")
            warn_count += 1
            continue

        try:
            with open(graph_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            entry_node: str = data.get("entry_node", "")
            nodes: dict = data.get("nodes", {})

            # Validate entry_node exists
            if entry_node not in nodes:
                print(f"  FAIL {graph_name:40s}  entry_node '{entry_node}' not in nodes")
                warn_count += 1
                continue

            # Build adjacency and check dangling references
            all_node_ids = set(nodes.keys())
            edge_count = 0
            dangling: list[str] = []

            for node_id, node_data in nodes.items():
                next_nodes: list[str] = node_data.get("next_nodes") or []
                conditional_next: dict = node_data.get("conditional_next") or {}

                for target in next_nodes:
                    edge_count += 1
                    if target not in all_node_ids:
                        dangling.append(f"{node_id} -> {target} (next_nodes)")

                for _cond, target in conditional_next.items():
                    edge_count += 1
                    if target not in all_node_ids:
                        dangling.append(f"{node_id} -> {target} (conditional_next)")

            if dangling:
                print(f"  FAIL {graph_name:40s}  dangling edges:")
                for d in dangling:
                    print(f"         {d}")
                warn_count += 1
                continue

            # BFS from entry_node
            visited: set[str] = set()
            queue: deque[str] = deque([entry_node])

            while queue:
                current = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)
                node_data = nodes.get(current, {})
                for target in node_data.get("next_nodes") or []:
                    if target not in visited:
                        queue.append(target)
                for target in (node_data.get("conditional_next") or {}).values():
                    if target not in visited:
                        queue.append(target)

            unreachable = all_node_ids - visited
            if unreachable:
                print(
                    f"  WARN {graph_name:40s}  "
                    f"nodes={len(all_node_ids)}  edges={edge_count}  "
                    f"unreachable={sorted(unreachable)}"
                )
                warn_count += 1
            else:
                print(
                    f"  OK   {graph_name:40s}  "
                    f"entry={entry_node}  nodes={len(all_node_ids)}  edges={edge_count}  "
                    f"all reachable"
                )
                ok_count += 1

        except Exception:
            warn_count += 1
            print(f"  FAIL {graph_name}")
            traceback.print_exc()

    print(f"\nA.2 summary: {ok_count} OK, {warn_count} WARN/FAIL (total {ok_count + warn_count})")
    return ok_count, warn_count


def main() -> None:
    """Run all Section A audits."""
    ok1, fail1 = run_a1_load_all_graphs()
    ok2, warn2 = run_a2_node_traversal()

    print("\n" + "=" * 60)
    print("Section A complete.")
    print(f"  A.1: {ok1} OK, {fail1} FAIL")
    print(f"  A.2: {ok2} OK, {warn2} WARN/FAIL")
    print("=" * 60)


if __name__ == "__main__":
    main()
