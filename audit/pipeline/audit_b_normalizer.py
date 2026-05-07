"""Section B: ActionNormalizer가 새 Action을 처리하는가?"""

from __future__ import annotations

from pathlib import Path
import traceback

import yaml

from cga_bench.assessor_core.action_normalizer import ActionNormalizer

ROOT = Path(__file__).resolve().parents[2]
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"


def collect_graph_actions() -> set[str]:
    """Collect all unique actions from all graph YAMLs.

    Gathers from: mandatory_actions, allowed_actions, forbidden_actions,
    and conditional_rules[].effect.actions.

    Returns:
        Set of unique action IDs.
    """
    actions: set[str] = set()
    graph_files = sorted(GRAPHS_DIR.glob("*.yaml"))

    for graph_path in graph_files:
        try:
            with open(graph_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            nodes: dict = data.get("nodes", {})
            for _node_id, node_data in nodes.items():
                for field in ("mandatory_actions", "allowed_actions", "forbidden_actions"):
                    field_val = node_data.get(field)
                    if isinstance(field_val, list):
                        actions.update(field_val)

                # conditional_rules[].effect.actions
                cond_rules = node_data.get("conditional_rules")
                if isinstance(cond_rules, list):
                    for rule in cond_rules:
                        effect = rule.get("effect", {})
                        if isinstance(effect, dict):
                            effect_actions = effect.get("actions")
                            if isinstance(effect_actions, list):
                                actions.update(effect_actions)
        except Exception:
            print(f"  ERROR reading {graph_path.stem}")
            traceback.print_exc()

    return actions


def run_b1_normalizer_coverage() -> tuple[int, int, int]:
    """B.1: Pass all graph actions through normalizer.

    Returns:
        (identity_count, mapped_count, unmapped_count)
    """
    print("=" * 60)
    print("B.1: All graph actions through ActionNormalizer")
    print("=" * 60)

    normalizer = ActionNormalizer()
    all_actions = collect_graph_actions()
    print(f"Collected {len(all_actions)} unique actions from {len(list(GRAPHS_DIR.glob('*.yaml')))} graphs\n")

    identity_count = 0
    mapped_count = 0

    for action in sorted(all_actions):
        result = normalizer.normalize(action)
        if result == action:
            identity_count += 1
        else:
            mapped_count += 1
            print(f"  MAPPED  {action:50s} -> {result}")

    unmapped = sorted(normalizer._unmapped_actions)
    unmapped_count = len(unmapped)

    print(f"\nIdentity (no mapping needed): {identity_count}")
    print(f"Mapped (transformed):         {mapped_count}")
    print(f"Unmapped (no rule found):     {unmapped_count}")

    if unmapped:
        print("\nUnmapped actions:")
        for action in unmapped:
            print(f"  - {action}")

    print(f"\nB.1 summary: identity={identity_count} mapped={mapped_count} unmapped={unmapped_count}")
    return identity_count, mapped_count, unmapped_count


def run_b2_agent_pattern_test() -> tuple[int, int]:
    """B.2: Test 15 agent output patterns against expected mappings.

    Returns:
        (ok_count, mismatch_count)
    """
    print("\n" + "=" * 60)
    print("B.2: Agent output patterns -> expected mapping (15 test cases)")
    print("=" * 60)

    test_cases: list[tuple[str, str]] = [
        ("obtain 12-lead ECG", "obtain_12_lead_ecg"),
        ("order troponin", "order_lab_troponin"),
        ("give aspirin", "give_aspirin"),
        ("start IV normal saline", "start_iv_fluid_ns"),
        ("activate cath lab", "activate_cath_lab"),
        ("check potassium", "order_lab_bmp"),
        ("start insulin drip", "start_insulin_infusion"),
        ("intubate", "perform_early_intubation"),
        ("give epinephrine IM", "give_epinephrine_im"),
        ("order CT head", "order_stat_ct_head"),
        ("consult neurosurgery", "neurosurgery_consult"),
        ("give tPA", "give_alteplase_0.9mg_kg"),
        ("start norepinephrine", "start_vasopressor_if_hypotensive"),
        ("give lorazepam", "give_benzodiazepine_weight_based"),
        ("perform needle decompression", "perform_needle_decompression"),
    ]

    normalizer = ActionNormalizer()
    ok_count = 0
    mismatch_count = 0

    for agent_output, expected in test_cases:
        actual = normalizer.normalize(agent_output)
        if actual == expected:
            print(f"  OK       {agent_output:40s} -> {actual}")
            ok_count += 1
        else:
            print(f"  MISMATCH {agent_output:40s} -> {actual}  (expected: {expected})")
            mismatch_count += 1

    print(f"\nB.2 summary: {ok_count} OK, {mismatch_count} MISMATCH")
    return ok_count, mismatch_count


def main() -> None:
    """Run all Section B audits."""
    id_count, map_count, unmap_count = run_b1_normalizer_coverage()
    ok2, mis2 = run_b2_agent_pattern_test()

    print("\n" + "=" * 60)
    print("Section B complete.")
    print(f"  B.1: identity={id_count} mapped={map_count} unmapped={unmap_count}")
    print(f"  B.2: {ok2} OK, {mis2} MISMATCH")
    print("=" * 60)


if __name__ == "__main__":
    main()
