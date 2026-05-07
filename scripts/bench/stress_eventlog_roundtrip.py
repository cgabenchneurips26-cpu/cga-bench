import argparse
import json
import resource
import sys
import time
from pathlib import Path
from typing import cast

_script_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_script_dir))
sys.path.insert(0, str(_script_dir.parent))

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.ocel_exporter import OCELExporter
from cga_bench.semantic_layer.export.reimport import import_from_ocel, import_from_xes
from cga_bench.semantic_layer.export.xes_exporter import XESExporter


PROFILES = {
    "small": 1_000,
    "medium": 50_000,
    "large": 500_000,
}


def make_events(n: int) -> list[ActivityEvent]:
    return [
        ActivityEvent(
            name=f"action_{i % 100:03d}",
            timestamp_min=float(i),
            raw_event={"step": i},
        )
        for i in range(n)
    ]


def run_stress(profile: str, fmt: str) -> dict[str, object]:
    n = PROFILES[profile]
    events = make_events(n)

    t0 = time.perf_counter()
    if fmt == "xes":
        exporter = XESExporter()
        output = exporter.export_episode("stress_test", events)
    else:
        exporter = OCELExporter()
        output = exporter.export_episode("stress_test", events)
    export_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    if fmt == "xes":
        reimported = import_from_xes(output)
    else:
        reimported = import_from_ocel(output)
    import_time = time.perf_counter() - t1

    peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    return {
        "profile": profile,
        "format": fmt,
        "n_events": n,
        "export_time_seconds": round(export_time, 3),
        "events_per_second": round(n / max(export_time, 0.001)),
        "peak_rss_mb": round(peak_rss_kb / 1024, 1),
        "output_size_bytes": len(output) if isinstance(output, (str, bytes)) else 0,
        "import_time_seconds": round(import_time, 3),
        "reimport_count": len(reimported),
    }


FALLBACK_THRESHOLDS = {
    "small": {
        "max_export_seconds": 10.0,
        "max_rss_mb": 2000,
        "min_events_per_second": 50,
    },
    "medium": {
        "max_export_seconds": 60.0,
        "max_rss_mb": 4000,
        "min_events_per_second": 200,
    },
    "large": {
        "max_export_seconds": 300.0,
        "max_rss_mb": 12000,
        "min_events_per_second": 500,
    },
}


def load_baseline(profile: str) -> dict | None:
    """Load stored baseline from baselines/ directory if available."""
    baseline_dir = Path(__file__).resolve().parent / "baselines"
    baseline_file = baseline_dir / f"{profile}_baseline.json"
    if baseline_file.exists():
        with open(baseline_file, encoding="utf-8") as f:
            return json.load(f)
    return None


def check_against_baseline(
    result: dict, profile: str, fmt: str,
) -> tuple[bool, list[str], dict]:
    """Check result against stored baseline with relative thresholds.

    ENG-08 requires:
    - throughput_drop > 10% vs baseline → FAIL
    - rss_increase > 15% vs baseline → FAIL
    """
    baseline = load_baseline(profile)
    fallback = FALLBACK_THRESHOLDS.get(profile, FALLBACK_THRESHOLDS["small"])

    passed = True
    failures: list[str] = []

    export_time_seconds = cast(float, result["export_time_seconds"])
    peak_rss_mb = cast(float, result["peak_rss_mb"])
    events_per_second = cast(float, result["events_per_second"])

    # Always check absolute thresholds
    if export_time_seconds > fallback["max_export_seconds"]:
        failures.append(
            f"Export time {export_time_seconds}s > {fallback['max_export_seconds']}s (absolute)",
        )
        passed = False
    if peak_rss_mb > fallback["max_rss_mb"]:
        failures.append(
            f"Peak RSS {peak_rss_mb}MB > {fallback['max_rss_mb']}MB (absolute)",
        )
        passed = False
    if events_per_second < fallback["min_events_per_second"]:
        failures.append(
            f"Throughput {events_per_second} evt/s < {fallback['min_events_per_second']} evt/s (absolute)",
        )
        passed = False

    # Relative comparison against stored baseline (ENG-08)
    if baseline:
        baseline_key = f"{profile}_{fmt}"
        bp = baseline.get("profiles", {}).get(baseline_key, {})
        rel = baseline.get("thresholds", {})
        throughput_drop_pct = rel.get("throughput_drop_pct", 10)
        rss_increase_pct = rel.get("rss_increase_pct", 15)

        baseline_min_eps = bp.get("min_events_per_second")
        baseline_max_rss = bp.get("max_rss_mb")

        if baseline_min_eps and events_per_second < baseline_min_eps * (1 - throughput_drop_pct / 100):
            failures.append(
                f"Throughput {events_per_second} evt/s dropped >{throughput_drop_pct}% vs baseline {baseline_min_eps} evt/s",
            )
            passed = False
        if baseline_max_rss and peak_rss_mb > baseline_max_rss * (1 + rss_increase_pct / 100):
            failures.append(
                f"Peak RSS {peak_rss_mb}MB increased >{rss_increase_pct}% vs baseline {baseline_max_rss}MB",
            )
            passed = False

    return passed, failures, {"baseline_loaded": baseline is not None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=PROFILES.keys(), default="small")
    parser.add_argument("--format", choices=["xes", "ocel"], default="xes")
    args = parser.parse_args()

    result = run_stress(args.profile, args.format)

    passed, failures, meta = check_against_baseline(result, args.profile, args.format)

    result["passed"] = passed
    result["failures"] = failures
    result["baseline_loaded"] = meta["baseline_loaded"]
    result["thresholds"] = FALLBACK_THRESHOLDS.get(args.profile, FALLBACK_THRESHOLDS["small"])

    out_dir = Path("reports/stress")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"stress_{args.profile}_{args.format}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    if passed:
        print(f"\nSTRESS TEST PASSED ({args.profile}/{args.format})")
    else:
        print(f"\nSTRESS TEST FAILED ({args.profile}/{args.format})")
        for failure in failures:
            print(f"  FAIL: {failure}")

    sys.exit(0 if passed else 1)
