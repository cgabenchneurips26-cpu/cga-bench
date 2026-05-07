#!/usr/bin/env python3
"""Dedup v73_full results: merge qwen397b_s2 → qwen397b, then keep latest per (scenario, run)."""

from collections import defaultdict
from pathlib import Path
import re
import shutil

RESULTS_DIR = Path("results/v73_full")
ARCHIVE_DIR = RESULTS_DIR / "_dedup_archive"
TARGET_PER_MODEL = 1254  # 418 scenarios × 3 runs

# Pattern: {scenario_id}_{model}_r{run}_{timestamp}.json
# e.g. aabb_transfusion_adverse_events_c004_deepseek_r1_7b_r0_20260501_220656.json
# The model name can contain underscores, so we match from the right:
# _r{digit}_{8digit}_{6digit}.json
FILE_RE = re.compile(r"^(.+)_r(\d+)_(\d{8}_\d{6})\.json$")


def parse_filename(fname: str) -> tuple[str, str, str] | None:
    """Return (scenario_key, run_index, timestamp) or None."""
    m = FILE_RE.match(fname)
    if not m:
        return None
    # scenario_key includes everything before _r{N}_{timestamp}
    # This is: {scenario_id}_{model}
    return m.group(1), m.group(2), m.group(3)


def merge_s2() -> int:
    """Move qwen397b_s2 files into qwen397b, renaming model in filename."""
    s2_dir = RESULTS_DIR / "qwen397b_s2"
    target_dir = RESULTS_DIR / "qwen397b"
    if not s2_dir.exists():
        print("qwen397b_s2 not found, skip merge")
        return 0

    moved = 0
    for f in sorted(s2_dir.glob("*.json")):
        if f.name in ("checkpoint.json", "model_summary.json"):
            continue
        # Replace model name in filename: qwen397b_s2 → qwen397b
        new_name = f.name.replace("qwen397b_s2", "qwen397b")
        dest = target_dir / new_name
        if dest.exists():
            # Already exists in qwen397b, archive the s2 version
            archive_dest = ARCHIVE_DIR / "qwen397b_s2" / f.name
            archive_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(archive_dest))
        else:
            shutil.move(str(f), str(dest))
            moved += 1

    # Clean up s2 dir
    remaining = list(s2_dir.glob("*.json"))
    if not remaining:
        shutil.rmtree(s2_dir)
        print("  Removed empty qwen397b_s2 dir")

    return moved


def dedup_model(model_dir: Path) -> tuple[int, int]:
    """Dedup one model dir. Returns (kept, archived)."""
    model_name = model_dir.name

    files = sorted(f for f in model_dir.glob("*.json") if f.name not in ("checkpoint.json", "model_summary.json"))

    # Group by (scenario_key, run_index)
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    unparsed = []

    for f in files:
        parsed = parse_filename(f.name)
        if parsed is None:
            unparsed.append(f)
            continue
        scenario_key, run_idx, timestamp = parsed
        groups[(scenario_key, run_idx)].append(f)

    kept = 0
    archived = 0

    for key, file_list in groups.items():
        if len(file_list) == 1:
            kept += 1
            continue

        # Sort by timestamp (embedded in filename), keep latest
        file_list.sort(key=lambda p: p.name, reverse=True)
        latest = file_list[0]
        kept += 1

        for dup in file_list[1:]:
            archive_dest = ARCHIVE_DIR / model_name / dup.name
            archive_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dup), str(archive_dest))
            archived += 1

    kept += len(unparsed)
    return kept, archived


def main() -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Merge qwen397b_s2 → qwen397b
    print("=== Step 1: Merge qwen397b_s2 → qwen397b ===")
    moved = merge_s2()
    print(f"  Moved {moved} files from s2 → qwen397b")

    # Step 2: Dedup each model
    print("\n=== Step 2: Dedup per model ===")
    total_kept = 0
    total_archived = 0

    models = sorted(
        d for d in RESULTS_DIR.iterdir() if d.is_dir() and d.name not in ("_logs", "_dedup_archive", "qwen397b_s2")
    )

    for model_dir in models:
        before = len(
            list(f for f in model_dir.glob("*.json") if f.name not in ("checkpoint.json", "model_summary.json"))
        )
        kept, archived = dedup_model(model_dir)
        after = before - archived
        status = "OK" if after == TARGET_PER_MODEL else f"WARN({after})"
        print(f"  {model_dir.name}: {before} → {after} (archived {archived}) [{status}]")
        total_kept += kept
        total_archived += archived

    print("\n=== Summary ===")
    print(f"Total kept: {total_kept}")
    print(f"Total archived: {total_archived}")
    print(f"Target: {TARGET_PER_MODEL * len(models)} ({TARGET_PER_MODEL} × {len(models)} models)")
    print(f"Archive dir: {ARCHIVE_DIR}")


if __name__ == "__main__":
    main()
