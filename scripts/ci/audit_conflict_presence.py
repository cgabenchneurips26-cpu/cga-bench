r"""Light conflict-presence audit across episode logs.

For each episode in data_release/v5.0/episodes/, checks whether the agent
performed any conflict-prone action (from CDE conflict audit v1.1).

Produces ``\conflictTouchN`` family of macros for the paper.

Usage:
    PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject \
        python cga_bench/scripts/ci/audit_conflict_presence.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))


def _load_conflict_actions(
    audit_path: str | Path | None = None,
) -> set[str]:
    """Extract conflict-prone action IDs from CDE audit JSON."""
    audit_path = REPO_ROOT / "evidence_pack" / "cde_conflict_audit_v1.json" if audit_path is None else Path(audit_path)

    with open(audit_path) as f:
        data = json.load(f)

    actions: set[str] = set()
    for conflict in data.get("conflicts", []):
        if "action" in conflict:
            actions.add(conflict["action"])
        for a in conflict.get("actions", []):
            actions.add(a)
    return actions


def _normalize_for_matching(action_id: str) -> str:
    """Lightweight normalization for substring matching."""
    return action_id.lower().strip().replace("-", "_").replace(" ", "_")


def audit_conflict_presence(
    episodes_dir: str | Path | None = None,
    audit_path: str | Path | None = None,
) -> dict:
    """Scan episode logs for conflict-prone actions.

    Returns structured report with per-model and aggregate statistics.
    """
    episodes_dir = REPO_ROOT / "data_release" / "v5.0" / "episodes" if episodes_dir is None else Path(episodes_dir)

    conflict_actions = _load_conflict_actions(audit_path)
    conflict_normalized = {_normalize_for_matching(a) for a in conflict_actions}

    per_model: dict[str, dict] = {}
    all_touched_episodes: list[dict] = []
    all_touched_scenarios: set[str] = set()
    all_strict_touched = 0
    total_episodes = 0

    for model_dir in sorted(episodes_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        model_touched = 0
        model_strict_touched = 0
        model_total = 0
        model_scenarios: set[str] = set()

        _NON_EPISODE = {"checkpoint.json", "model_summary.json"}
        for ep_file in sorted(model_dir.glob("*.json")):
            if ep_file.name in _NON_EPISODE:
                continue
            model_total += 1
            total_episodes += 1
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            scenario_id = ep.get("scenario_id", "unknown")
            agent_actions = ep.get("actions", [])
            matched_actions: list[str] = []
            strict_matched_actions: list[str] = []

            for action in agent_actions:
                aid = action.get("action_id", "")
                aid_norm = _normalize_for_matching(aid)
                # Strict: exact match only
                if aid_norm in conflict_normalized:
                    strict_matched_actions.append(aid)
                    matched_actions.append(aid)
                # Loose: substring containment (upper bound)
                elif any(ca in aid_norm for ca in conflict_normalized):
                    matched_actions.append(aid)

            if strict_matched_actions:
                model_strict_touched += 1
            if matched_actions:
                model_touched += 1
                model_scenarios.add(scenario_id)
                all_touched_scenarios.add(scenario_id)
                all_touched_episodes.append(
                    {
                        "model": model_name,
                        "file": ep_file.name,
                        "scenario_id": scenario_id,
                        "matched_actions": matched_actions,
                        "strict_matched_actions": strict_matched_actions,
                    }
                )

        all_strict_touched += model_strict_touched
        per_model[model_name] = {
            "total_episodes": model_total,
            "touched_episodes": model_touched,
            "strict_touched_episodes": model_strict_touched,
            "touched_scenarios": len(model_scenarios),
            "touch_rate": round(model_touched / max(model_total, 1), 4),
            "strict_touch_rate": round(model_strict_touched / max(model_total, 1), 4),
        }

    total_touched = len(all_touched_episodes)
    touch_pct = round(100 * total_touched / max(total_episodes, 1), 1)
    strict_touch_pct = round(100 * all_strict_touched / max(total_episodes, 1), 1)

    return {
        "conflict_actions": sorted(conflict_actions),
        "conflict_action_count": len(conflict_actions),
        "total_episodes_scanned": total_episodes,
        "conflict_touch_episodes": total_touched,
        "conflict_touch_strict_episodes": all_strict_touched,
        "conflict_touch_scenarios": len(all_touched_scenarios),
        "conflict_touch_pct": touch_pct,
        "conflict_touch_strict_pct": strict_touch_pct,
        "per_model": per_model,
        "touched_scenarios": sorted(all_touched_scenarios),
        "sample_touched": all_touched_episodes[:20],
    }


def main() -> int:
    """Run conflict-presence audit and print results."""
    report = audit_conflict_presence()

    print(f"Conflict-Presence Audit — {report['total_episodes_scanned']} episodes scanned")
    print(f"  Conflict actions tracked: {report['conflict_action_count']}")
    print(f"  Episodes touched (substring): {report['conflict_touch_episodes']} ({report['conflict_touch_pct']}%)")
    print(
        f"  Episodes touched (strict):    {report['conflict_touch_strict_episodes']} ({report['conflict_touch_strict_pct']}%)"
    )
    print(f"  Unique scenarios touched: {report['conflict_touch_scenarios']}")

    print("\n--- Per-model ---")
    for model, stats in sorted(report["per_model"].items()):
        print(
            f"  {model}: {stats['touched_episodes']}/{stats['total_episodes']} "
            f"({stats['touch_rate'] * 100:.1f}%) substr, "
            f"{stats['strict_touched_episodes']} ({stats['strict_touch_rate'] * 100:.1f}%) strict, "
            f"{stats['touched_scenarios']} scenarios"
        )

    if report["sample_touched"]:
        print("\n--- Sample touched episodes (first 10) ---")
        for t in report["sample_touched"][:10]:
            print(f"  [{t['model']}] {t['scenario_id']}: {t['matched_actions']}")

    # LaTeX macros
    print("\n% LaTeX macros")
    print(f"\\providecommand{{\\conflictTouchEpisodes}}{{{report['conflict_touch_episodes']}}}")
    print(f"\\providecommand{{\\conflictTouchScenarios}}{{{report['conflict_touch_scenarios']}}}")
    print(f"\\providecommand{{\\conflictTouchPct}}{{{report['conflict_touch_pct']}}}")
    print(f"\\providecommand{{\\conflictTouchStrictPct}}{{{report['conflict_touch_strict_pct']}}}")
    print(f"\\providecommand{{\\conflictTouchActionsN}}{{{report['conflict_action_count']}}}")

    # JSON report
    report_path = REPO_ROOT / "evidence_pack" / "analysis" / "conflict_presence_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nJSON report written to {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
