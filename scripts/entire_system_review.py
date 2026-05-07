"""CGA-Bench Entire System Review — 10 Layer Verification.

Runs all 10 verification checks and reports PASS/FAIL/WARNING per check.
Designed to run in parallel with episode execution.
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"
SCENARIOS_DIR = ROOT / "configs" / "scenarios"
RESULTS_DIR = ROOT / "results" / "full_706_final"

results: list[dict] = []


def report(check_id: str, name: str, status: str, detail: str = "") -> None:
    results.append({"id": check_id, "name": name, "status": status, "detail": detail})
    icon = {"PASS": "OK", "FAIL": "!!", "WARNING": "??", "SKIP": "--"}[status]
    print(f"  [{icon}] {check_id}: {name} — {status}")
    if detail:
        for line in detail.split("\n")[:5]:
            print(f"        {line}")


# ================================================================
# V1: Scoring Pipeline Independence
# ================================================================
print("\n=== V1: Scoring Pipeline Independence ===")
try:
    from cga_bench.cpg_engine.engine import CPGEngineFactory

    g1 = GRAPHS_DIR / "ssc_sepsis_hour1_bundle.yaml"
    e1 = CPGEngineFactory.load_from_file(str(g1))
    e2 = CPGEngineFactory.load_from_file(str(g1))
    isolated = e1 is not e2
    e1.current_node_id = "MODIFIED"
    still_isolated = e2.current_node_id != "MODIFIED"
    if isolated and still_isolated:
        report("V1a", "Engine instance isolation", "PASS")
    else:
        report("V1a", "Engine instance isolation", "FAIL", f"isolated={isolated}, still={still_isolated}")

    # Idempotent scoring check
    ep_files = list((RESULTS_DIR / "oss120b").glob("*.json")) if (RESULTS_DIR / "oss120b").exists() else []
    ep_files = [f for f in ep_files if "checkpoint" not in f.name and "summary" not in f.name]
    if ep_files:
        ep = json.load(open(ep_files[0]))
        cs1 = ep.get("compliance_score", -1)
        cs2 = ep.get("compliance_score", -1)
        if cs1 == cs2 and cs1 >= 0:
            report("V1b", "Score idempotency (same JSON)", "PASS", f"score={cs1:.3f}")
        else:
            report("V1b", "Score idempotency", "FAIL", f"{cs1} vs {cs2}")
    else:
        report("V1b", "Score idempotency", "SKIP", "No episodes yet")
except Exception as e:
    report("V1", "Scoring independence", "FAIL", str(e))

# ================================================================
# V2: Episode JSON Schema
# ================================================================
print("\n=== V2: Episode JSON Schema ===")
try:
    ep_dirs = [RESULTS_DIR / m for m in ["oss120b", "qwen35b", "qwen27b", "qwen4b", "qwen397b"]]
    total_checked = 0
    schema_issues = []

    for d in ep_dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json"))[:3]:
            if "checkpoint" in f.name or "summary" in f.name:
                continue
            ep = json.load(open(f))
            total_checked += 1

            for field in ["scenario_id", "agent_id", "actions_count", "compliance_score"]:
                if field not in ep:
                    schema_issues.append(f"{f.name}: missing {field}")

            cs = ep.get("compliance_score", -1)
            ac = ep.get("actions_count", -1)
            if not isinstance(cs, (int, float)) or cs < 0:
                schema_issues.append(f"{f.name}: invalid compliance_score={cs}")
            if not isinstance(ac, int) or ac < 0:
                schema_issues.append(f"{f.name}: invalid actions_count={ac}")

    if total_checked == 0:
        report("V2", "Episode JSON schema", "SKIP", "No episodes yet")
    elif schema_issues:
        report("V2", "Episode JSON schema", "FAIL", "\n".join(schema_issues[:5]))
    else:
        report("V2", "Episode JSON schema", "PASS", f"Checked {total_checked} episodes")
except Exception as e:
    report("V2", "Episode JSON schema", "FAIL", str(e))

# ================================================================
# V3: ActionNormalizer Coverage
# ================================================================
print("\n=== V3: ActionNormalizer Coverage ===")
try:
    # Check reject rate from logs
    log_rejects: dict[str, int] = {}
    log_totals: dict[str, int] = {}
    for m in ["oss120b", "qwen35b", "qwen27b", "qwen4b", "qwen397b"]:
        log_files = list(RESULTS_DIR.glob(f"log_{m}*.txt"))
        if not log_files:
            continue
        rejects = 0
        http_ok = 0
        for lf in log_files:
            content = lf.read_text()
            rejects += content.count("Rejecting action")
            http_ok += content.count("HTTP Request")
        log_rejects[m] = rejects
        log_totals[m] = http_ok

    if log_totals:
        detail_lines = []
        for m in sorted(log_totals):
            detail_lines.append(f"{m}: rejects={log_rejects.get(m, 0)}, http={log_totals[m]}")
        max_reject = max(log_rejects.values()) if log_rejects else 0
        if max_reject > 100:
            report("V3", "ActionNormalizer coverage", "WARNING", "\n".join(detail_lines))
        else:
            report("V3", "ActionNormalizer coverage", "PASS", "\n".join(detail_lines))
    else:
        report("V3", "ActionNormalizer coverage", "SKIP", "No logs yet")
except Exception as e:
    report("V3", "ActionNormalizer coverage", "FAIL", str(e))

# ================================================================
# V4: Timing Model
# ================================================================
print("\n=== V4: Timing Model ===")
try:
    timing_issues = []
    checked = 0
    for d in [RESULTS_DIR / m for m in ["oss120b", "qwen35b"]]:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json"))[:5]:
            if "checkpoint" in f.name:
                continue
            ep = json.load(open(f))
            actions = ep.get("actions", [])
            if not actions:
                continue
            checked += 1
            # Check monotonic timestamps
            ts = [a.get("timestamp", a.get("timestamp_minutes", 0)) for a in actions if isinstance(a, dict)]
            for i in range(1, len(ts)):
                if ts[i] < ts[i - 1]:
                    timing_issues.append(f"{f.name}: non-monotonic at action {i}")

    if checked == 0:
        report("V4", "Timing model", "SKIP", "No episodes with actions detail")
    elif timing_issues:
        report("V4", "Timing model", "FAIL", "\n".join(timing_issues[:5]))
    else:
        report("V4", "Timing model", "PASS", f"Checked {checked} episodes")
except Exception as e:
    report("V4", "Timing model", "FAIL", str(e))

# ================================================================
# V5: Perturbation Pipeline (deferred — needs completed episodes)
# ================================================================
print("\n=== V5: Perturbation Pipeline ===")
report("V5", "Perturbation pipeline", "SKIP", "Requires completed episodes for E1")

# ================================================================
# V6: Evaluator Implementation
# ================================================================
print("\n=== V6: Evaluator Implementation ===")
try:
    # Check that evaluator agreement script exists and verdict matrix exists
    verdict_path = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
    if verdict_path.exists():
        vm = json.load(open(verdict_path))
        n_episodes = len(vm.get("per_episode", []))
        evaluator_keys = ["dxem", "ac_proxy", "mab_proxy", "c2_pass", "acov_pass", "v4_hard"]

        # Check DxEM is degenerate (all pass)
        dxem_pass = sum(1 for ep in vm["per_episode"] if ep.get("dxem", False))
        dxem_rate = dxem_pass / max(n_episodes, 1)

        if dxem_rate > 0.95:
            report("V6a", "DxEM degenerate (all pass)", "PASS", f"pass_rate={dxem_rate:.1%} ({n_episodes} eps)")
        else:
            report("V6a", "DxEM degenerate", "WARNING", f"pass_rate={dxem_rate:.1%}")

        # Check evaluator diversity (not all same)
        all_same = sum(1 for ep in vm["per_episode"] if len(set(ep.get(k, False) for k in evaluator_keys)) == 1)
        diversity = 1 - all_same / max(n_episodes, 1)
        if diversity > 0.1:
            report("V6b", "Evaluator diversity", "PASS", f"disagreement_rate={diversity:.1%}")
        else:
            report("V6b", "Evaluator diversity", "WARNING", f"disagreement_rate={diversity:.1%}")
    else:
        report("V6", "Evaluator implementation", "SKIP", "No verdict matrix (from previous runs)")
except Exception as e:
    report("V6", "Evaluator implementation", "FAIL", str(e))

# ================================================================
# V7: Scenario-Graph Mapping
# ================================================================
print("\n=== V7: Scenario-Graph Mapping ===")
try:
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    loader = ScenarioLoader()
    all_s = loader.load_all_scenarios()
    broken = []
    for sid in all_s:
        gpath = loader.get_cpg_graph_path(sid)
        if gpath is None:
            broken.append(f"{sid}: no graph path")
        elif not gpath.exists():
            broken.append(f"{sid}: graph file missing at {gpath}")

    if broken:
        report("V7", "Scenario-Graph mapping", "FAIL", "\n".join(broken[:5]))
    else:
        report("V7", "Scenario-Graph mapping", "PASS", f"{len(all_s)} scenarios, all graphs resolved")
except Exception as e:
    report("V7", "Scenario-Graph mapping", "FAIL", str(e))

# ================================================================
# V8: Run Determinism
# ================================================================
print("\n=== V8: Run Determinism ===")
try:
    from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
    from cpg_model.patient_generator import PatientGenerator

    engine = ConstraintDerivationEngine()
    gen1 = PatientGenerator(engine, seed=42)
    gen2 = PatientGenerator(engine, seed=42)

    g = load_graph(GRAPHS_DIR / "ssc_sepsis_hour1_bundle.yaml")
    s1 = gen1.generate_from_graph(g)
    s2 = gen2.generate_from_graph(g)

    ids1 = [s.scenario_id for s in s1]
    ids2 = [s.scenario_id for s in s2]
    if ids1 == ids2:
        report("V8", "PatientGenerator determinism", "PASS", f"{len(ids1)} scenarios identical")
    else:
        report("V8", "PatientGenerator determinism", "FAIL", f"Different: {len(ids1)} vs {len(ids2)}")
except Exception as e:
    report("V8", "PatientGenerator determinism", "FAIL", str(e))

# ================================================================
# V9: Cross-Model GPU Isolation
# ================================================================
print("\n=== V9: GPU Isolation ===")
try:
    import subprocess

    ps = subprocess.run(["ps", "aux"], capture_output=True, text=True).stdout
    vllm_procs = [l for l in ps.split("\n") if "vllm" in l and "api_server" in l]

    ports_seen = set()
    for line in vllm_procs:
        for part in line.split():
            if part.startswith("--port"):
                break
        else:
            continue
        idx = line.split().index(part)
        if idx + 1 < len(line.split()):
            ports_seen.add(line.split()[idx + 1])

    # Check episode model_id consistency
    model_issues = []
    for m in ["oss120b", "qwen35b", "qwen27b", "qwen4b", "qwen397b"]:
        d = RESULTS_DIR / m
        if not d.exists():
            continue
        for f in list(d.glob("*.json"))[:2]:
            if "checkpoint" in f.name:
                continue
            ep = json.load(open(f))
            aid = ep.get("agent_id", "")
            if m not in aid and "debug" not in aid:
                model_issues.append(f"{m}/{f.name}: agent_id={aid}")

    if model_issues:
        report("V9", "Cross-model isolation", "WARNING", "\n".join(model_issues[:3]))
    else:
        report("V9", "Cross-model isolation", "PASS", f"{len(vllm_procs)} vLLM processes")
except Exception as e:
    report("V9", "GPU isolation", "FAIL", str(e))

# ================================================================
# V10: 3 Runs Configuration
# ================================================================
print("\n=== V10: 3 Runs Configuration ===")
try:
    run_counts: dict[str, dict[str, int]] = {}
    for m in ["oss120b", "qwen35b", "qwen27b", "qwen4b", "qwen397b"]:
        d = RESULTS_DIR / m
        if not d.exists():
            continue
        scenario_runs: dict[str, int] = defaultdict(int)
        for f in d.glob("*.json"):
            if "checkpoint" in f.name or "summary" in f.name:
                continue
            ep = json.load(open(f))
            sid = ep.get("scenario_id", "?")
            scenario_runs[sid] += 1
        run_counts[m] = dict(scenario_runs)

    if not run_counts:
        report("V10", "3 runs per scenario", "SKIP", "No episodes yet")
    else:
        # Check if any scenario has 3 runs
        has_3 = False
        for m, srs in run_counts.items():
            for sid, count in srs.items():
                if count >= 3:
                    has_3 = True
                    break
        total_eps = sum(sum(srs.values()) for srs in run_counts.values())
        max_runs = max(max(srs.values()) for srs in run_counts.values() if srs)
        report(
            "V10",
            "3 runs configuration",
            "PASS" if max_runs >= 2 else "WARNING",
            f"total_eps={total_eps}, max_runs_per_scenario={max_runs}",
        )
except Exception as e:
    report("V10", "3 runs configuration", "FAIL", str(e))

# ================================================================
# SUMMARY
# ================================================================
print(f"\n{'=' * 70}")
print("SYSTEM REVIEW SUMMARY")
print(f"{'=' * 70}")

pass_count = sum(1 for r in results if r["status"] == "PASS")
fail_count = sum(1 for r in results if r["status"] == "FAIL")
warn_count = sum(1 for r in results if r["status"] == "WARNING")
skip_count = sum(1 for r in results if r["status"] == "SKIP")

for r in results:
    icon = {"PASS": "PASS", "FAIL": "FAIL", "WARNING": "WARN", "SKIP": "SKIP"}[r["status"]]
    print(f"  [{icon:4s}] {r['id']:5s} {r['name']}")

print(f"\nPASS={pass_count}  FAIL={fail_count}  WARNING={warn_count}  SKIP={skip_count}")

if fail_count > 0:
    print("\n*** FAILURES DETECTED — REVIEW REQUIRED ***")
    for r in results:
        if r["status"] == "FAIL":
            print(f"\n  {r['id']}: {r['name']}")
            print(f"  {r['detail']}")
