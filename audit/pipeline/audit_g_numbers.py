"""Section G: 논문 수치 일관성 검증.

Handoff v2 문서의 수치와 현재 코드/데이터가 일치하는지 확인.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"
SCENARIOS_DIR = ROOT / "configs" / "scenarios"


def count_graphs() -> int:
    """Count YAML graph files."""
    return len(list(GRAPHS_DIR.glob("*.yaml")))


def count_scenarios() -> tuple[int, int, int]:
    """Count manual, auto, and total scenarios.

    Returns:
        (manual, auto, total)
    """
    manual = 0
    auto = 0
    for path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or "scenarios" not in data:
            continue
        items = data.get("scenarios", {})
        if not isinstance(items, dict):
            continue

        is_auto = path.name == "auto_generated_scenarios.yaml"
        count = len(items)
        if is_auto:
            auto += count
        else:
            manual += count
    return manual, auto, manual + auto


def count_conditional_rules() -> int:
    """Count conditional rules across all graphs."""
    total = 0
    for p in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(p) as f:
            g = yaml.safe_load(f)
        if not g:
            continue
        for node in g.get("nodes", {}).values():
            total += len(node.get("conditional_rules", []))
    return total


def count_sequence_rules() -> int:
    """Count sequence rules across all graphs."""
    total = 0
    for p in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(p) as f:
            g = yaml.safe_load(f)
        if not g:
            continue
        for node in g.get("nodes", {}).values():
            sr = node.get("sequence_rules", [])
            if isinstance(sr, list):
                total += len(sr)
    return total


def count_nodes() -> int:
    """Count total nodes across all graphs."""
    total = 0
    for p in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(p) as f:
            g = yaml.safe_load(f)
        if not g:
            continue
        total += len(g.get("nodes", {}))
    return total


def count_unique_actions() -> int:
    """Count unique action IDs across all graphs."""
    actions: set[str] = set()
    for p in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(p) as f:
            g = yaml.safe_load(f)
        if not g:
            continue
        for node in g.get("nodes", {}).values():
            actions.update(node.get("mandatory_actions", []))
            actions.update(node.get("allowed_actions", []))
            actions.update(node.get("forbidden_actions", []))
            for rule in node.get("conditional_rules", []):
                effect = rule.get("effect", {})
                actions.update(effect.get("actions", []))
    return len(actions)


def main() -> None:
    """Run Section G audit."""
    print("=" * 70)
    print("Section G: 논문 수치 일관성")
    print("=" * 70)

    actual_graphs = count_graphs()
    manual, auto, total_scenarios = count_scenarios()
    cond_rules = count_conditional_rules()
    seq_rules = count_sequence_rules()
    total_nodes = count_nodes()
    unique_actions = count_unique_actions()

    print("\n--- G.1: Number Verification ---")
    print(f"  CPG Graphs:          {actual_graphs}")
    print(f"  Total Scenarios:     {total_scenarios} (manual={manual}, auto={auto})")
    print(f"  Total Nodes:         {total_nodes}")
    print(f"  Conditional Rules:   {cond_rules}")
    print(f"  Sequence Rules:      {seq_rules}")
    print(f"  Unique Actions:      {unique_actions}")

    # Per-graph breakdown
    print("\n--- Per-graph breakdown ---")
    for p in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(p) as f:
            g = yaml.safe_load(f)
        if not g:
            continue
        gid = g.get("graph_id", p.stem)
        nodes = g.get("nodes", {})
        n_nodes = len(nodes)
        n_cond = sum(len(n.get("conditional_rules", [])) for n in nodes.values())
        n_seq = sum(
            len(n.get("sequence_rules", []))
            for n in nodes.values()
            if isinstance(n.get("sequence_rules", []), list)
        )
        n_actions: set[str] = set()
        for node in nodes.values():
            n_actions.update(node.get("mandatory_actions", []))
            n_actions.update(node.get("allowed_actions", []))
        print(f"  {gid:45s}  nodes={n_nodes:3d}  cond_rules={n_cond:3d}  "
              f"seq_rules={n_seq:3d}  actions={len(n_actions):3d}")

    # Scenario count per domain
    print("\n--- Scenarios per guideline_graph ---")
    domain_counts: dict[str, dict[str, int]] = {}
    for path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or "scenarios" not in data:
            continue
        is_auto = path.name == "auto_generated_scenarios.yaml"
        tag = "auto" if is_auto else "manual"
        items = data.get("scenarios", {})
        if not isinstance(items, dict):
            continue
        for cfg in items.values():
            gg = cfg.get("guideline_graph", "unknown")
            domain_counts.setdefault(gg, {"manual": 0, "auto": 0})
            domain_counts[gg][tag] += 1

    for gg in sorted(domain_counts):
        m = domain_counts[gg]["manual"]
        a = domain_counts[gg]["auto"]
        print(f"  {gg:45s}  manual={m:3d}  auto={a:3d}  total={m + a:3d}")


if __name__ == "__main__":
    main()
