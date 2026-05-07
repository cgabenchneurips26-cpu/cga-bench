"""Audit 2: "100% Differentiation" 직접 검증

모든 trap 시나리오를 직접 열어서 같은 graph의 normal과 forbidden을 비교.
verify_trap_differentiation.py의 결과를 믿지 말고 직접 계산.
"""

from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit._helpers import load_raw_scenarios

scenarios = load_raw_scenarios()

# Build normal forbidden union per graph
normal_fb: dict[str, set[str]] = defaultdict(set)
for s in scenarios:
    if not s.get("trap_scenario"):
        normal_fb[s["guideline_graph"]].update(s.get("forbidden_actions") or [])

# Check each trap
undiff: list[dict] = []
total_traps = 0
for s in scenarios:
    if not s.get("trap_scenario"):
        continue
    total_traps += 1
    trap_fb = set(s.get("forbidden_actions") or [])
    normal = normal_fb.get(s["guideline_graph"], set())
    unique = trap_fb - normal

    if not unique:
        undiff.append(
            {
                "id": s["scenario_id"],
                "graph": s["guideline_graph"],
                "trap_fb_count": len(trap_fb),
                "normal_fb_count": len(normal),
                "overlap": len(trap_fb & normal),
            }
        )

print(f"Total scenarios: {len(scenarios)}")
print(f"Total traps: {total_traps}")
print(f"Total normals: {len(scenarios) - total_traps}")
print(f"Undifferentiated traps: {len(undiff)}")

if undiff:
    for u in undiff[:20]:
        print(
            f"  {u['id']} ({u['graph']}): trap={u['trap_fb_count']}, normal={u['normal_fb_count']}, overlap={u['overlap']}"
        )
else:
    print("CONFIRMED: 0 undifferentiated traps")

# Per-graph breakdown
print("\nPer-graph trap counts:")
graph_traps: dict[str, int] = defaultdict(int)
graph_normals: dict[str, int] = defaultdict(int)
for s in scenarios:
    if s.get("trap_scenario"):
        graph_traps[s["guideline_graph"]] += 1
    else:
        graph_normals[s["guideline_graph"]] += 1

for g in sorted(set(list(graph_traps.keys()) + list(graph_normals.keys()))):
    t = graph_traps.get(g, 0)
    n = graph_normals.get(g, 0)
    nfb = len(normal_fb.get(g, set()))
    print(f"  {g}: {t} traps, {n} normals, normal_fb_union={nfb}")

print(f"\n{'=' * 50}")
print(
    f"Differentiation rate: {total_traps - len(undiff)}/{total_traps} = {(total_traps - len(undiff)) / total_traps * 100:.1f}%"
    if total_traps
    else "N/A"
)
