#!/usr/bin/env python3
"""One-shot status monitor for expansion_runner episodes.

Usage:
    python scripts/monitoring/expansion_status.py
    python scripts/monitoring/expansion_status.py --gpus            # also poll GPU util
    python scripts/monitoring/expansion_status.py --sample 5        # raw 5 eps / endpoint
    python scripts/monitoring/expansion_status.py --eta-baseline 07:50  # override rate baseline

Derives:
    - per-endpoint episode count & delta vs restart baseline
    - compliance score stats (mean, p50, zero-rate, non-zero %)
    - aggregate throughput (ep/min) and per-endpoint rate
    - ETA by endpoint + worst-case (slowest bottleneck)
    - GPU utilization snapshot across 146/145/144 (if --gpus)
    - random sample of raw episode JSONs (if --sample N)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = REPO_ROOT / "results" / "expansion_v7"
TARGET_PER_ENDPOINT = 708  # 236 scenarios × 3 runs
GPU_HOSTS = {
    "146-local": None,
    "145": "127.0.0.1
    "144": "[email-redacted]",
}


@dataclass
class EndpointStats:
    name: str
    n: int
    zero_count: int
    scores: list[float]
    avg_actions: float

    @property
    def nonzero_pct(self) -> float:
        return 100 * (1 - self.zero_count / self.n) if self.n else 0.0

    @property
    def mean_score(self) -> float:
        return statistics.mean(self.scores) if self.scores else 0.0

    @property
    def median_score(self) -> float:
        return statistics.median(self.scores) if self.scores else 0.0


def collect_endpoint_stats(endpoint_dir: Path) -> EndpointStats | None:
    files = [f for f in endpoint_dir.glob("*.json") if f.name != "checkpoint.json"]
    scores: list[float] = []
    zero = 0
    actions_per: list[int] = []
    for f in files:
        try:
            e = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        s = e.get("compliance_score")
        if s is None:
            continue
        scores.append(s)
        if s == 0.0:
            zero += 1
        actions_per.append(len(e.get("actions", [])))
    if not scores:
        return None
    return EndpointStats(
        name=endpoint_dir.name,
        n=len(scores),
        zero_count=zero,
        scores=scores,
        avg_actions=statistics.mean(actions_per),
    )


def fmt_table(rows: list[EndpointStats]) -> str:
    hdr = f"{'endpoint':<25} {'n':>4} {'target':>6} {'%done':>6} {'zero':>5} {'nz%':>6} {'mean':>6} {'p50':>6} {'avgAct':>7}"
    out = [hdr, "-" * len(hdr)]
    for r in rows:
        pct_done = 100 * r.n / TARGET_PER_ENDPOINT
        out.append(
            f"{r.name:<25} {r.n:>4} {TARGET_PER_ENDPOINT:>6} {pct_done:>5.1f}% "
            f"{r.zero_count:>5} {r.nonzero_pct:>5.1f}% {r.mean_score:>6.3f} "
            f"{r.median_score:>6.3f} {r.avg_actions:>7.1f}"
        )
    return "\n".join(out)


def estimate_eta(rows: list[EndpointStats], baseline_epoch: float) -> dict[str, float]:
    now = time.time()
    elapsed_min = (now - baseline_epoch) / 60 if baseline_epoch else 0
    etas: dict[str, float] = {}
    for r in rows:
        remaining = TARGET_PER_ENDPOINT - r.n
        if remaining <= 0:
            etas[r.name] = 0
            continue
        rate_per_min = r.n / elapsed_min if elapsed_min > 0 else 0
        etas[r.name] = remaining / rate_per_min if rate_per_min > 0 else float("inf")
    return etas


def gpu_snapshot(host: str | None) -> str:
    cmd = ["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used", "--format=csv,noheader"]
    if host:
        cmd = ["sudo", "-n", "-u", "anonymous-org", "ssh", "-o", "StrictHostKeyChecking=no", host] + [" ".join(cmd)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception as e:
        return f"ERR: {e}"


def random_samples(endpoint_dir: Path, n: int) -> list[dict]:
    files = sorted(f for f in endpoint_dir.glob("*.json") if f.name != "checkpoint.json")
    random.seed(42)
    sample = random.sample(files, min(n, len(files)))
    out = []
    for f in sample:
        try:
            e = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        out.append(
            {
                "scenario": e.get("scenario_id", "?"),
                "score": e.get("compliance_score", "?"),
                "actions": len(e.get("actions", [])),
                "viols": len(e.get("violations", [])),
                "first3": [a.get("action_id", "?") for a in e.get("actions", [])[:3]],
            }
        )
    return out


def latest_runner_log() -> Path | None:
    logs = sorted(Path("/tmp").glob("expansion_runner_*.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def parse_restart_time(log: Path | None) -> float:
    """Extract the most recent 'Starting ThreadPoolExecutor' timestamp as baseline."""
    if not log or not log.exists():
        return 0.0
    for line in log.read_text().splitlines():
        if "Loaded" in line and "scenario IDs" in line:
            try:
                ts = line.split("[")[0].strip()  # "2026-04-23 07:50:58,xxx "
                t = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                return t.timestamp()
            except (ValueError, IndexError):
                continue
    return 0.0


def empty_action_count(log: Path | None) -> int:
    if not log or not log.exists():
        return 0
    return sum(1 for line in log.read_text().splitlines() if "empty actions" in line)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--gpus", action="store_true", help="poll GPU utilization on all 3 hosts")
    p.add_argument("--sample", type=int, default=0, metavar="N", help="show N random raw episode samples per endpoint")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = p.parse_args()

    log = latest_runner_log()
    baseline = parse_restart_time(log)

    stats = [
        s for s in (collect_endpoint_stats(d) for d in sorted(RESULTS_DIR.iterdir()) if d.is_dir()) if s is not None
    ]
    if not stats:
        print("No episode data yet.", file=sys.stderr)
        return 1

    total_n = sum(s.n for s in stats)
    total_target = TARGET_PER_ENDPOINT * len(stats)
    elapsed_min = (time.time() - baseline) / 60 if baseline else 0
    throughput = total_n / elapsed_min if elapsed_min > 0 else 0

    etas = estimate_eta(stats, baseline)
    worst_eta_min = max((e for e in etas.values() if e != float("inf")), default=0)
    worst_endpoint = next((n for n, e in etas.items() if e == worst_eta_min), "?")
    worst_done_at = datetime.now() + timedelta(minutes=worst_eta_min)

    empties = empty_action_count(log)

    if args.json:
        out = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "total_done": total_n,
            "total_target": total_target,
            "pct_done": 100 * total_n / total_target,
            "throughput_ep_per_min": throughput,
            "elapsed_min": elapsed_min,
            "empty_actions": empties,
            "worst_eta_min": worst_eta_min,
            "worst_eta_endpoint": worst_endpoint,
            "completion_etc": worst_done_at.isoformat(timespec="minutes"),
            "per_endpoint": [
                {
                    "name": s.name,
                    "n": s.n,
                    "target": TARGET_PER_ENDPOINT,
                    "pct_done": 100 * s.n / TARGET_PER_ENDPOINT,
                    "zero_count": s.zero_count,
                    "nonzero_pct": s.nonzero_pct,
                    "mean_score": s.mean_score,
                    "median_score": s.median_score,
                    "eta_min": etas.get(s.name, float("inf")),
                }
                for s in stats
            ],
        }
        print(json.dumps(out, indent=2, default=str))
        return 0

    print(f"=== expansion_v7 status @ {datetime.now().strftime('%H:%M:%S')} ===")
    print(f"Restart baseline: {datetime.fromtimestamp(baseline).strftime('%H:%M:%S') if baseline else 'unknown'}")
    print(f"Elapsed: {elapsed_min:.1f} min")
    print(f"Progress: {total_n} / {total_target} ({100 * total_n / total_target:.1f}%)")
    print(f"Throughput: {throughput:.2f} ep/min aggregate")
    print(f"Empty-action warnings in log: {empties}")
    print()
    print(fmt_table(stats))
    print()
    print("=== ETA (per-endpoint) ===")
    for name, eta_min in sorted(etas.items(), key=lambda x: -x[1] if x[1] != float("inf") else 0):
        hours = eta_min / 60
        done = datetime.now() + timedelta(minutes=eta_min)
        print(f"  {name:<25} {hours:>5.1f} h  (done by {done.strftime('%H:%M')})")
    print()
    print(f"BOTTLENECK: {worst_endpoint} ({worst_eta_min / 60:.1f}h -> {worst_done_at.strftime('%Y-%m-%d %H:%M')})")

    if args.gpus:
        print("\n=== GPU utilization ===")
        for label, host in GPU_HOSTS.items():
            snap = gpu_snapshot(host)
            print(f"-- {label} --")
            print(snap)

    if args.sample > 0:
        print(f"\n=== {args.sample} raw sample per endpoint ===")
        for s in stats:
            endpoint_dir = RESULTS_DIR / s.name
            samples = random_samples(endpoint_dir, args.sample)
            print(f"\n-- {s.name} --")
            for r in samples:
                print(
                    f"  {r['scenario'][:55]:<55} score={r['score']} acts={r['actions']:2d} viol={r['viols']:2d} first3={r['first3']}"
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
