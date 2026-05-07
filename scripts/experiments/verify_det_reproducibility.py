"""Task 5: Verify deterministic reproducibility of SGSC extraction.

Runs a fresh DET extraction on a single guideline and compares SHA256
against the rollout output. Produces a verification report for paper
§App Reproducibility (Phase B Patch B3).

Usage:
    PYTHONPATH=.:.. python scripts/experiments/verify_det_reproducibility.py \
        --rollout-dir sgsc_output/v7_e3_combined_overnight \
        --guideline kdigo_contrast_aki \
        --endpoint http://localhost:8013/v1 \
        --model "Qwen/Qwen3.5-397B-A17B-FP8"

    # Dry-test (compare NONDET archive against itself — trivially identical):
    PYTHONPATH=.:.. python scripts/experiments/verify_det_reproducibility.py \
        --rollout-dir sgsc_output/v7_e3_combined_overnight_NONDET \
        --verify-dir sgsc_output/v7_e3_combined_overnight_NONDET \
        --guideline kdigo_contrast_aki \
        --skip-extraction
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("det_repro")

# Files to compare for byte-identity
COMPARE_FILES = [
    "atoms_smoke.json",
    "{gid}_constraints.json",
    "{gid}_graph.json",
    "{gid}_scenarios.json",
]


def sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def run_fresh_extraction(
    guideline: str,
    output_dir: Path,
    endpoint: str,
    model: str,
) -> bool:
    """Run a fresh DET extraction for one guideline via subprocess. Returns True on success."""
    import subprocess

    logger.info("Running fresh DET extraction: %s -> %s", guideline, output_dir)
    cmd = [
        sys.executable, str(ROOT / "scripts" / "sgsc" / "run_full_25.py"),
        "--endpoint", endpoint,
        "--model", model,
        "--output-dir", str(output_dir),
        "--multi-pass",
        "--corpus-chars", "6000",
        "--deterministic",
        "--guidelines", guideline,
    ]
    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = f"{ROOT}:{ROOT.parent}"

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
    # run_full_25.py returns rc=1 for NO-GO checks (entailment report missing)
    # which is expected — check for actual output files instead
    atoms_path = output_dir / guideline / "atoms_smoke.json"
    if atoms_path.exists():
        logger.info("Fresh extraction completed for %s (rc=%d, atoms present)", guideline, result.returncode)
        return True
    logger.error("Extraction failed (rc=%d): %s", result.returncode, result.stderr[-500:])
    return False


def compare_outputs(
    rollout_dir: Path,
    verify_dir: Path,
    guideline: str,
) -> list[dict[str, str | bool]]:
    """Compare SHA256 of key output files. Returns list of comparison results."""
    results: list[dict[str, str | bool]] = []
    for template in COMPARE_FILES:
        fname = template.format(gid=guideline)
        rollout_path = rollout_dir / guideline / fname
        verify_path = verify_dir / guideline / fname

        entry: dict[str, str | bool] = {"file": fname}
        if not rollout_path.exists():
            entry["status"] = "MISSING_ROLLOUT"
            entry["match"] = False
            results.append(entry)
            continue
        if not verify_path.exists():
            entry["status"] = "MISSING_VERIFY"
            entry["match"] = False
            results.append(entry)
            continue

        h_rollout = sha256_file(rollout_path)
        h_verify = sha256_file(verify_path)
        entry["sha256_rollout"] = h_rollout[:16]
        entry["sha256_verify"] = h_verify[:16]
        entry["match"] = h_rollout == h_verify
        entry["status"] = "IDENTICAL" if entry["match"] else "DIFFER"
        results.append(entry)

    return results


def write_report(
    results: list[dict[str, str | bool]],
    guideline: str,
    output_path: Path,
    rollout_dir: str,
    verify_dir: str,
) -> None:
    """Write markdown verification report."""
    all_match = all(r.get("match", False) for r in results)
    verdict = "PASS" if all_match else "FAIL"

    lines = [
        "# SGSC Deterministic Reproducibility Verification",
        "",
        f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Guideline**: `{guideline}`",
        f"**Rollout dir**: `{rollout_dir}`",
        f"**Verify dir**: `{verify_dir}`",
        f"**Verdict**: **{verdict}**",
        "",
        "## File Comparison",
        "",
        "| File | Rollout SHA256 | Verify SHA256 | Status |",
        "|------|---------------|--------------|--------|",
    ]
    for r in results:
        sha_r = r.get("sha256_rollout", "—")
        sha_v = r.get("sha256_verify", "—")
        status = r.get("status", "UNKNOWN")
        lines.append(f"| `{r['file']}` | `{sha_r}` | `{sha_v}` | **{status}** |")

    lines.extend([
        "",
        "## Interpretation",
        "",
    ])
    if all_match:
        lines.append(
            "All key output files are byte-identical between the rollout and "
            "the fresh verification run. The deterministic mode (`seed` per pass "
            "+ explicit `top_p=1.0`) produces fully reproducible SGSC extraction."
        )
    else:
        differ = [r["file"] for r in results if not r.get("match", False)]
        lines.append(f"**{len(differ)} file(s) differ**: {', '.join(differ)}")
        lines.append("Investigation required — check LLM sampling or pipeline changes.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")
    logger.info("Report written to %s", output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify SGSC deterministic reproducibility")
    parser.add_argument("--rollout-dir", required=True, help="Path to rollout output dir")
    parser.add_argument("--verify-dir", default=None, help="Path to verification output (default: temp dir)")
    parser.add_argument("--guideline", default="kdigo_contrast_aki", help="Guideline ID to verify")
    parser.add_argument("--endpoint", default="http://localhost:8013/v1")
    parser.add_argument("--model", default="Qwen/Qwen3.5-397B-A17B-FP8")
    parser.add_argument("--report", default="reports/path_d_day2/v7_det_repro_verification.md")
    parser.add_argument("--skip-extraction", action="store_true", help="Skip LLM extraction (use existing verify-dir)")
    args = parser.parse_args()

    rollout_dir = Path(args.rollout_dir)
    if not rollout_dir.exists():
        logger.error("Rollout dir does not exist: %s", rollout_dir)
        sys.exit(1)

    if args.skip_extraction:
        if not args.verify_dir:
            logger.error("--verify-dir required when --skip-extraction is set")
            sys.exit(1)
        verify_dir = Path(args.verify_dir)
    else:
        verify_dir = Path(args.verify_dir) if args.verify_dir else Path("sgsc_output/_det_repro_verify")
        verify_dir.mkdir(parents=True, exist_ok=True)
        ok = run_fresh_extraction(args.guideline, verify_dir, args.endpoint, args.model)
        if not ok:
            logger.error("Fresh extraction failed — aborting")
            sys.exit(1)

    results = compare_outputs(rollout_dir, verify_dir, args.guideline)
    for r in results:
        logger.info("  %s: %s", r["file"], r.get("status", "UNKNOWN"))

    write_report(
        results,
        args.guideline,
        Path(args.report),
        str(rollout_dir),
        str(verify_dir),
    )

    all_match = all(r.get("match", False) for r in results)
    sys.exit(0 if all_match else 1)


if __name__ == "__main__":
    main()
