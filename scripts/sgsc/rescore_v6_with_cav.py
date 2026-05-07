"""α-6 — Layer-2 v6 verdict matrix recompute with CAV (combined-only mode).

baseline run:
  Read each existing v6 episode JSON and call score_episode() from
  aggregate_heldout_v6 against the *stored* violation_events / compliance_score.
  This is the v6-vanilla evaluator state.

full run:
  Re-extract violations with HEAD ViolationExtractor (which has α-1~α-3 fixes
  applied) AFTER filtering expected_actions / forbidden_actions through the
  CAV (Strict policy). Then call score_episode() on the rescored results.
  This is the v6-fixed evaluator state.

The 5-ablation source attribution (CAV-only / +norm / +eng / +assessor) is
deferred to v1 per anonymous-user's instruction; the present script only emits the
two endpoints (baseline and full) and the combined-effect delta.

Usage:
    PYTHONPATH=. python scripts/sgsc/rescore_v6_with_cav.py \\
        --episodes results/full_v6a_706 \\
        --cav cav_v0_5/cav_v0_5.json \\
        --output reports/path_d_day1/v6_fixed_verdict_matrix.json \\
        --extraction-miss N

PRECONDITION: α-7 spot-check verdict from anonymous-user.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from cga_bench.assessor_core.harm_scorer import HarmScorer  # noqa: E402
from cga_bench.assessor_core.violations import ViolationExtractor  # noqa: E402
from cga_bench.cpg_engine.engine import CPGEngineFactory  # noqa: E402
from cga_bench.cpg_model.schemas.base import (  # noqa: E402
    Action,
    ActionType,
    EpisodeLog,
)
from cga_bench.eval_harness.scenario_loader import ScenarioLoader  # noqa: E402
from cga_bench.scripts.cav.cav_validator import filter_action_list, load_cav  # noqa: E402
from cga_bench.scripts.experiments.aggregate_heldout_v6 import score_episode  # noqa: E402
from cga_bench.scripts.experiments.rescore_v6 import build_hs_config, build_ve_config  # noqa: E402

os.environ.setdefault("CGA_BENCH_EXCLUDE_AUTO", "1")
os.environ.setdefault("CGA_BENCH_INCLUDE_AUTO_V2", "0")


def _action_type_from_str(s: str) -> ActionType:
    try:
        return ActionType(s)
    except (ValueError, KeyError):
        return ActionType.PROCEDURE


def load_canonical_episode_keys(verdict_matrix_path: Path) -> set[tuple[str, str, int]]:
    """Load the canonical 19,062 (scenario_id, model_dir, run_index) keys from the
    paper's verdict_matrix_v6.json (Phase A headline, not Phase B _full).
    """
    d = json.loads(verdict_matrix_path.read_text(encoding="utf-8"))
    pe = d.get("per_episode", [])
    return {(e["scenario_id"], e.get("model_dir", ""), int(e.get("run_index", 0))) for e in pe}


def _episode_key_from_payload(ep: dict, model_dir: str) -> tuple[str, str, int]:
    return (ep.get("scenario_id", ""), model_dir, int(ep.get("run_index", 0)))


def _iter_episode_files(episodes_dir: Path, canonical_keys: set[tuple[str, str, int]] | None = None):
    """Yield (model_dir_name, json_path) tuples filtered to canonical_keys (if provided).

    The full_v6a_706 directory holds 20,704 .json files but the paper §5.1 corpus
    is exactly 19,062. The 1,642 extras are race-duplicates / re-runs that pre-date
    the canonical verdict matrix. Filtering to the verdict_matrix_v6.json keys
    guarantees vanilla vs fixed are scored on the same paper-anchor episode set.
    """
    for model_dir in sorted(episodes_dir.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("_"):
            continue
        for f in sorted(model_dir.glob("*.json")):
            if f.name.startswith(("checkpoint", "model_summary", ".claim", "log_")):
                continue
            if canonical_keys is not None:
                # Cheap pre-filter: peek at scenario_id + run_index without full load.
                # We need to load anyway since the key includes run_index from JSON.
                try:
                    ep = json.load(open(f))
                except Exception:
                    continue
                key = _episode_key_from_payload(ep, model_dir.name)
                if key not in canonical_keys:
                    continue
                yield model_dir.name, f, ep
            else:
                yield model_dir.name, f, None


def run_baseline(
    episodes_dir: Path,
    canonical_keys: set[tuple[str, str, int]] | None = None,
    limit: int = 0,
) -> list[dict]:
    """v6-vanilla: aggregate existing episode files via score_episode (no re-extraction)."""
    out = []
    n = 0
    for model_name, fpath, ep_pre in _iter_episode_files(episodes_dir, canonical_keys):
        if limit and n >= limit:
            break
        if ep_pre is not None:
            ep = ep_pre
        else:
            try:
                ep = json.load(open(fpath))
            except Exception:
                continue
        if not isinstance(ep, dict) or not ep.get("scenario_id"):
            continue
        rec = score_episode(ep, model_name)
        out.append(rec)
        n += 1
        if n % 2000 == 0:
            print(f"[baseline] {n} episodes processed", flush=True)
    return out


def run_full(
    episodes_dir: Path,
    cav: dict,
    loader: ScenarioLoader,
    canonical_keys: set[tuple[str, str, int]] | None = None,
    limit: int = 0,
) -> tuple[list[dict], dict[str, int]]:
    """v6-fixed: re-extract with HEAD code + CAV filter.

    Per-scenario caching: 706 unique scenarios × ~27 episodes each. Without
    caching, every episode re-loads CPGEngine + scenario contract (~600ms);
    with caching, only the first episode per scenario pays that cost.
    """
    ve_config = build_ve_config()
    hs_config = build_hs_config()
    out: list[dict] = []
    cav_drops = {"expected": 0, "forbidden": 0}
    n = 0
    err = 0

    # Caches: keyed by scenario_id
    scenario_cache: dict[str, Any] = {}
    graph_path_cache: dict[str, str] = {}
    cav_filtered_expected: dict[str, list[str]] = {}
    cav_filtered_forbidden: dict[str, list[str]] = {}

    for model_name, fpath, ep_pre in _iter_episode_files(episodes_dir, canonical_keys):
        if limit and n >= limit:
            break
        if ep_pre is not None:
            ep = ep_pre
        else:
            try:
                ep = json.load(open(fpath))
            except Exception:
                err += 1
                continue
        if not isinstance(ep, dict) or not ep.get("scenario_id"):
            continue

        scenario_id = ep["scenario_id"]
        if scenario_id not in scenario_cache:
            scenario = loader.get_scenario(scenario_id)
            if scenario is None:
                err += 1
                continue
            graph_path = str(loader.get_cpg_graph_path(scenario_id))
            if not graph_path:
                err += 1
                continue
            scenario_cache[scenario_id] = scenario
            graph_path_cache[scenario_id] = graph_path
            ke, de = filter_action_list(list(scenario.expected_actions or []), context="expected", cav=cav)
            kf, df = filter_action_list(list(scenario.forbidden_actions or []), context="forbidden", cav=cav)
            cav_filtered_expected[scenario_id] = ke
            cav_filtered_forbidden[scenario_id] = kf
            cav_drops["expected"] += len(de)
            cav_drops["forbidden"] += len(df)

        scenario = scenario_cache[scenario_id]
        graph_path = graph_path_cache[scenario_id]
        kept_expected = cav_filtered_expected[scenario_id]
        kept_forbidden = cav_filtered_forbidden[scenario_id]

        # Re-extract violations
        try:
            engine = CPGEngineFactory.load_from_file(graph_path)
            ve = ViolationExtractor(engine, ve_config)
            n_expected = len(kept_expected) if kept_expected else 5
            hs = HarmScorer(n_expected, hs_config)

            actions = []
            for a in ep.get("actions") or []:
                actions.append(
                    Action(
                        type=_action_type_from_str(a.get("type", "procedure")),
                        action_id=a["action_id"],
                        args=a.get("args") or {},
                        timestamp_minutes=a.get("timestamp_minutes", a.get("timestamp", 0.0)),
                    )
                )

            env = loader.create_environment(scenario_id)
            env._cpg_engine = engine
            env.reset()
            for a in actions:
                try:
                    env.step(a)
                except Exception:
                    break
                if getattr(env, "terminated", False):
                    break

            states = list(env.state_history) if env.state_history else [env.current_state]
            while len(states) < max(len(actions), 1):
                states.append(states[-1])

            episode = EpisodeLog(
                episode_id=f"rescore_{scenario_id}_{ep.get('run_index', 0)}",
                scenario_id=scenario_id,
                agent_id=ep.get("agent_id", "unknown"),
                actions=actions,
                states=states,
                observations=[],
                total_duration_minutes=ep.get("total_duration_minutes", 60.0),
                total_llm_calls=ep.get("total_llm_calls", 0),
                total_tokens=ep.get("total_tokens", 0),
                total_tool_calls=0,
                termination_reason=ep.get("termination_reason", "max_time"),
            )
            violations = ve.extract_violations(
                episode,
                scenario_expected_actions=kept_expected if kept_expected else None,
            )
            score = hs.compute_score(violations, episode)
        except Exception:
            err += 1
            continue

        # Build a synthetic dict shaped like score_episode expects
        rescored_ep = {
            "scenario_id": scenario_id,
            "run_index": ep.get("run_index", 0),
            "actions": ep.get("actions") or [],
            "expected_actions": kept_expected,
            "forbidden_actions": kept_forbidden,
            "compliance_score": score.compliance_score,
            "violation_events": [
                {
                    "violation_type": v.violation_type.value
                    if hasattr(v.violation_type, "value")
                    else str(v.violation_type)
                }
                for v in violations
            ],
        }
        rec = score_episode(rescored_ep, model_name)
        out.append(rec)
        n += 1
        if n % 1000 == 0:
            print(
                f"[full] {n} episodes  cav_drops={cav_drops}  err={err}",
                flush=True,
            )

    print(f"[full] DONE n={n} err={err} cav_drops={cav_drops}")
    return out, cav_drops


def fa_summary(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {"n": 0}
    fa_strict_3 = sum(1 for r in records if r["ac_proxy"] and r["mab_proxy"] and r["c2_pass"] and r["v4_hard"])
    fa_consensus_loose = sum(1 for r in records if r["ac_proxy"] and r["c2_pass"] and r["v4_hard"])
    n_v4 = sum(1 for r in records if r["v4_hard"])
    pass_ac = sum(1 for r in records if r["ac_proxy"])
    pass_mab = sum(1 for r in records if r["mab_proxy"])
    pass_c2 = sum(1 for r in records if r["c2_pass"])
    return {
        "n": n,
        "v4_hard": n_v4,
        "v4_hard_pct": round(100 * n_v4 / n, 2),
        "fa_strict_3way": fa_strict_3,
        "fa_strict_3way_pct": round(100 * fa_strict_3 / n, 2),
        "fa_loose_consensus": fa_consensus_loose,
        "fa_loose_consensus_pct": round(100 * fa_consensus_loose / n, 2),
        "pass_ac_proxy": pass_ac,
        "pass_mab_proxy": pass_mab,
        "pass_c2": pass_c2,
    }


def write_delta_report(
    baseline: dict,
    full: dict,
    cav_drops: dict,
    output: Path,
    extraction_miss: int,
) -> None:
    delta_strict = full["fa_strict_3way"] - baseline["fa_strict_3way"]
    delta_loose = full["fa_loose_consensus"] - baseline["fa_loose_consensus"]
    delta_v4 = full["v4_hard"] - baseline["v4_hard"]
    lines = [
        "# v6 Vanilla vs Fixed — Delta Report (α-6 combined-only)",
        "",
        f"_α-7 verdict: extraction_miss = {extraction_miss}/30._",
        "",
        "## Strict-3way Consensus FA (ASC ∩ CwT ∩ PAF, with v4_hard)",
        "",
        "| | n | strict-3way FA | pct |",
        "|---|---|---|---|",
        f"| baseline (v6 vanilla) | {baseline['n']} | {baseline['fa_strict_3way']} | {baseline['fa_strict_3way_pct']}% |",
        f"| full (v6 fixed) | {full['n']} | {full['fa_strict_3way']} | {full['fa_strict_3way_pct']}% |",
        f"| **Δ (full − baseline)** | — | **{delta_strict:+d}** | — |",
        "",
        "## Loose Consensus FA (AC ∩ C2, with v4_hard)",
        "",
        "| | loose FA | pct |",
        "|---|---|---|",
        f"| baseline | {baseline['fa_loose_consensus']} | {baseline['fa_loose_consensus_pct']}% |",
        f"| full | {full['fa_loose_consensus']} | {full['fa_loose_consensus_pct']}% |",
        f"| **Δ** | **{delta_loose:+d}** | — |",
        "",
        "## v4_hard (TCC violation present)",
        "",
        "| | v4_hard | pct |",
        "|---|---|---|",
        f"| baseline | {baseline['v4_hard']} | {baseline['v4_hard_pct']}% |",
        f"| full | {full['v4_hard']} | {full['v4_hard_pct']}% |",
        f"| **Δ** | **{delta_v4:+d}** | — |",
        "",
        "## CAV filter activity",
        "",
        f"- expected_actions dropped: {cav_drops['expected']}",
        f"- forbidden_actions dropped: {cav_drops['forbidden']}",
        "",
        "## Per-evaluator pass counts",
        "",
        "| | baseline | full | Δ |",
        "|---|---|---|---|",
        f"| ac_proxy | {baseline['pass_ac_proxy']} | {full['pass_ac_proxy']} | {full['pass_ac_proxy'] - baseline['pass_ac_proxy']:+d} |",
        f"| mab_proxy | {baseline['pass_mab_proxy']} | {full['pass_mab_proxy']} | {full['pass_mab_proxy'] - baseline['pass_mab_proxy']:+d} |",
        f"| c2_pass | {baseline['pass_c2']} | {full['pass_c2']} | {full['pass_c2'] - baseline['pass_c2']:+d} |",
        "",
        "## Source attribution",
        "",
        "Combined-only mode: per-source decomposition (CAV vs N1-N5 vs B3-engine vs B3-defensive)",
        "deferred to v1. Present run shows the **combined effect** of all four mechanisms.",
        "",
        "## Headline survival check",
        "",
        f"- Vanilla strict-3way FA: {baseline['fa_strict_3way']} ({baseline['fa_strict_3way_pct']}%)",
        f"- Fixed strict-3way FA: {full['fa_strict_3way']} ({full['fa_strict_3way_pct']}%)",
        f"- Headline (>1% with non-trivial absolute count): "
        f"{'SURVIVES' if full['fa_strict_3way_pct'] > 1.0 and full['fa_strict_3way'] > 50 else 'FRAGILE'}",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--episodes", type=Path, default=REPO_ROOT / "results" / "full_v6a_706")
    p.add_argument("--cav", type=Path, default=REPO_ROOT / "cav_v0_5" / "cav_v0_5.json")
    p.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "reports" / "path_d_day1" / "v6_fixed_verdict_matrix.json",
    )
    p.add_argument(
        "--delta-report",
        type=Path,
        default=REPO_ROOT / "reports" / "path_d_day1" / "v6_vanilla_vs_fixed_delta.md",
    )
    p.add_argument("--extraction-miss", type=int, default=0)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument(
        "--canonical-matrix",
        type=Path,
        default=REPO_ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json",
        help="Use this verdict matrix as the canonical 19,062-episode keyset filter. "
        "Set to NONE to score all .json files in --episodes (legacy 20,704 behavior).",
    )
    args = p.parse_args()

    if not args.episodes.is_dir():
        print(f"[ERROR] --episodes not found: {args.episodes}", file=sys.stderr)
        return 2
    if not args.cav.is_file():
        print(f"[ERROR] --cav not found: {args.cav}", file=sys.stderr)
        return 2

    cav = load_cav(args.cav)
    loader = ScenarioLoader()

    canonical_keys: set[tuple[str, str, int]] | None = None
    if args.canonical_matrix and str(args.canonical_matrix).upper() != "NONE":
        if not args.canonical_matrix.is_file():
            print(f"[ERROR] --canonical-matrix not found: {args.canonical_matrix}", file=sys.stderr)
            return 2
        canonical_keys = load_canonical_episode_keys(args.canonical_matrix)
        print(f"[INFO] canonical keyset: {len(canonical_keys)} episodes (from {args.canonical_matrix.name})")

    print("[INFO] === Run 1/2: baseline (v6 vanilla, no CAV, no re-extract) ===")
    t0 = time.time()
    baseline_records = run_baseline(args.episodes, canonical_keys=canonical_keys, limit=args.limit)
    t_baseline = time.time() - t0
    baseline_summary = fa_summary(baseline_records)
    print(f"[INFO] baseline: n={baseline_summary['n']} wall={t_baseline:.1f}s")
    print(f"       strict-3way FA = {baseline_summary['fa_strict_3way']} ({baseline_summary['fa_strict_3way_pct']}%)")
    print()

    print("[INFO] === Run 2/2: full (v6 fixed, CAV-filtered + α-1~α-3 re-extract) ===")
    t1 = time.time()
    full_records, cav_drops = run_full(args.episodes, cav, loader, canonical_keys=canonical_keys, limit=args.limit)
    t_full = time.time() - t1
    full_summary = fa_summary(full_records)
    print(f"[INFO] full: n={full_summary['n']} wall={t_full:.1f}s")
    print(f"       strict-3way FA = {full_summary['fa_strict_3way']} ({full_summary['fa_strict_3way_pct']}%)")
    print()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "metadata": {
            "n_episodes": baseline_summary["n"],
            "extraction_miss_count": args.extraction_miss,
            "cav_path": str(args.cav),
            "episodes_dir": str(args.episodes),
            "wall_seconds": {"baseline": round(t_baseline, 1), "full": round(t_full, 1)},
            "cav_drops": cav_drops,
        },
        "baseline_summary": baseline_summary,
        "full_summary": full_summary,
        "baseline_per_episode": baseline_records,
        "full_per_episode": full_records,
    }
    args.output.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    write_delta_report(baseline_summary, full_summary, cav_drops, args.delta_report, args.extraction_miss)
    print(f"[INFO] Wrote {args.output}")
    print(f"[INFO] Wrote {args.delta_report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
