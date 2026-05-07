#!/usr/bin/env python3
"""Prepare a submission-ready copy of CGA-Bench.

Copies the development repository and strips it down to only the code
required to reproduce paper results.  Idempotent: safe to re-run on
an existing destination (it will be wiped and rebuilt).

Usage:
    python scripts/submission/prepare_submission.py \\
        --source .  \\
        --dest ../cga_bench_submission \\
        --keep-model-sample qwen4b

    # Dry-run (prints what would be removed, no changes):
    python scripts/submission/prepare_submission.py \\
        --source . --dest ../cga_bench_submission --dry-run
"""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

# ---------------------------------------------------------------------------
# Configuration: what to remove
# ---------------------------------------------------------------------------

# Step 2: Large generated / cache directories (always remove)
LARGE_DIRS_REMOVE: list[str] = [
    "anonymous_repo",
    "results_old_rag_backup",
    "data_release",
    "logs",
    "_archive",
    ".mypy_cache",
    ".pytest_cache",
    ".hypothesis",
    ".ruff_cache",
    ".sisyphus",
    ".omc",
    ".git",
    "cpg_sources",
    # v7.3+ additions
    "sgsc_output",
    "paper_artifacts",
    "cav_v0_6",
    "supplementary",
    "physionet.org",
    "tex",
    "artifacts",
    ".venv311",
    ".claude",
    # 2026-05-06 refresh: paper exclusion + secrets/_archive/site/staging
    "paper",                # excluded from submission (croissant.json kept at root)
    "secrets",              # API key templates (out-of-tree backup)
    "site",                 # MkDocs build artifact
    "staging",              # transient staging dir
    "fixtures",             # dev test fixtures (not consumed by submitted tests)
    "demo",                 # Gradio demo (audit harness extension; dev-only)
    "cav_v0_5",             # superseded by cav_v0_6/
    "testing",              # legacy E2E test runner (no imports; tests/ is canonical)
    "anonymous_repo",       # double-blind copy now lives outside submission tree
]

# Step 3: Ancillary non-code directories
ANCILLARY_DIRS_REMOVE: list[str] = [
    "clinician_validation",
    "clinician_study",
    "clinician_survey",
    "constraints",
    "reports",
    "index",
    "guidelines",
    "code_verification",
    "analysis",
    "tracking",
    "encoding_audit",
    "scenario_review",
    "system_review",
    "paper_sections",
    # v7.3+ additions
    # "audit" removed: imported by tests/test_audit/test_active_agent_shim.py
    # and test_authority_filter.py. Submission keeps it for test runnability.
    "scripts/monitoring",
    "scripts/cav",
]

# Step 4: evidence_pack subdirectories to remove
EVIDENCE_PACK_REMOVE: list[str] = [
    "cres_cache",
    "ex1_llm_judge_3judge",
    "ex1_llm_judge_gemma31b",
    "ex1_llm_judge_nemotron30b",
    "ex1_llm_judge_oss120b",
    # 2026-05-06: 388 MB of intermediate run logs from V7 track-1 expansion;
    # outputs they back are already in evidence_pack/analysis and tables/.
    "expansion_v7_track1_logs",
]

# Step 5: Paper files to remove (old versions, planning docs, build artifacts)
PAPER_FILES_REMOVE: list[str] = [
    # Old paper versions (keep v18 + v19 as active)
    "main_final_v12.tex",
    "main_final_v13.tex",
    "main_final_v14.tex",
    "main_final_v16.tex",
    "main_final_v17.tex.bak_preprint",
    "main_final_v17.txt",
    "main_test_compile.tex",
    "main_tier1-1.tex",
    "main_v18_v6_baseline_BACKUP.tex",
    # Old appendix versions (keep appendix.tex, appendix_v18.tex, appendix_frontier_v73.tex)
    "appendix_reconstructed.tex",
    "appendix_test.tex",
    "appendix_tier1-1.tex",
    "appendix_v3.tex",
    "testsize.tex",
    # Unreferenced auto_numbers supplementary files
    "auto_numbers_v2.tex",
    "auto_numbers_defense.tex",
    "auto_numbers_resample.tex",
    "auto_numbers_constraints.json",
    "auto_numbers.log",
    "observation_coarsening.tex",
    "appendix_figures.tex",
    # Superseded bridge/backup files
    "auto_numbers.tex.v6_phaseA_backup_20260428",
    "auto_numbers_v6_cat_a_bridge.tex.SUPERSEDED_20260504",
    "auto_numbers_v73_bridge.tex.SUPERSEDED_20260504",
    # Old compiled PDFs
    "main.pdf",
    "main_final_v7.pdf",
    "main_final_v17_2026-04-21_3exp_integrated.pdf",
    "main_final_v17_9pages.pdf",
    # Internal planning / session docs
    "SESSION_HANDOFF_v17.md",
    "STRATEGIC_PLAN_v17.md",
    "STRATEGIC_PLAN_v17_CRITIQUE.md",
    "APPENDIX_DEPENDENCY_AUDIT.md",
    "CI_AUDIT_REPORT_20260420.md",
    "CROSS_REF_AUDIT_v17.md",
    "claim_ledger.md",
]

PAPER_DIRS_REMOVE: list[str] = [
    "compiled",
    ".claude",
    "reports",
    "figures/_preview",
    "templates",
]

PAPER_GLOB_REMOVE: list[str] = [
    "*.aux",
    "*.log",
    "*.out",
    "*.blg",
    "figures/*.bak_*",
]

# Step 6: Development-only root files
ROOT_FILES_REMOVE: list[str] = [
    "gemma_nemotron_setup.md",
    "main_final_v10.log",
    "texput.log",
    "AUDIT_CHECKLIST.md",
    "run_eval_science_llm.py",
    "run_evaluation_science.py",
    # 2026-05-06 audit additions:
    "MEMORY.md",                   # Claude Code session scratchpad
    "CLAUDE.md",                   # Claude Code project instructions
    "auto_numbers_audit.csv",      # paper macro provenance log (paper-bound)
    "mkdocs.yml",                  # site/ build config (site/ is excluded)
    "rebuttal_preregister_v1.yaml",# NeurIPS rebuttal pre-reg (paper-bound)
]

# Step 7: docs/ — keep only these, remove everything else
DOCS_KEEP: set[str] = {
    "HARDWARE.md",
    "EXTENDING_CGA_BENCH.md",
    "MAINTENANCE.md",
    "RAI.md",
    "NEURIPS_DB_REPRO_CHECKLIST.md",
    "ANNOTATION_GUIDE_ACTION_NORMALIZATION.md",
    "PAPER_TRACEABILITY.md",
    "vllm_ops_knowhow.md",
    "RELEASE.md",  # release runbook for HF + anon4openreview
}

DOCS_DIRS_REMOVE: list[str] = [
    "attack_gap_exp_exp",
    "review",
    "impl",
    "specs",
    "cres_reports",
    "clinician_validation",
    "scenario_expansion",
    "cpg_expansion_v7",
    "critical_review",
    "reports",
    "sgsc",
    "session_state",
]

# Step 9: Stale nested directory
NESTED_DIRS_REMOVE: list[str] = [
    "cga_bench",
]

# Step 8: Path fixes  {file_relative_to_dest: [(old, new), ...]}
PATH_FIXES: dict[str, list[tuple[str, str]]] = {
    "paper/figures/make_figure6_w8_aofa_heatmap.py": [
        (
            "Input : evidence_pack/w8_full/w8_results.json",
            "Input : evidence_pack/ex_w8_crossmodel/w8_results.json",
        ),
        (
            '"w8_full"',
            '"ex_w8_crossmodel"',
        ),
    ],
}

# Step 10: Verification modules
VERIFY_MODULES: list[str] = [
    "cga_bench.cpg_model.schemas.base",
    "cga_bench.cpg_engine.engine",
    "cga_bench.assessor_core.violations",
    "cga_bench.assessor_core.harm_scorer",
    "cga_bench.assessor_core.action_normalizer",
    "cga_bench.agent_runner.rag_agent",
    "cga_bench.agent_runner.oracle_agent",
    "cga_bench.agent_runner.planner_agent",
    "cga_bench.agent_runner.reflection_agent",
    "cga_bench.agent_runner.llm_provider",
    "cga_bench.agent_rules.decision_table",
    "cga_bench.scenario_engine.environment",
    "cga_bench.eval_harness.runner",
    "cga_bench.eval_harness.scenario_loader",
    "cga_bench.semantic_layer",
    "cga_bench.env",
    "cga_bench.tool_api",
    # SGSC pipeline (v7.3 contribution)
    "cga_bench.sgsc.pipeline",
    "cga_bench.sgsc.schemas",
]

VERIFY_ENTRY_POINTS: list[str] = [
    "run_benchmark.py",
    "run_external_benchmark.py",
    "run_neurips_experiment.py",
]

VERIFY_CRITICAL_FILES: list[str] = [
    "evidence_pack/all_numbers_v5.json",
    "evidence_pack/canonical_numbers.json",
    "evidence_pack/exp_e1_verdict_flip.json",
    "evidence_pack/exp_e2_bsr.json",
    "evidence_pack/PAPER_NUMBER_SOURCE.md",
    # paper/* entries removed — paper/ is excluded from the submission tree
    # per the (C) policy. Reviewers receive the typeset paper separately.
    "croissant.json",
    ".zenodo.json",
    "CITATION.cff",
    "DATASHEET.md",
    "README.md",
    "CHANGELOG.md",
]

MIN_CPG_GRAPHS = 25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _size_fmt(nbytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024  # type: ignore[assignment]
    return f"{nbytes:.1f} TB"


def _dir_size(path: Path) -> int:
    """Total size of a directory in bytes."""
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = Path(dirpath) / f
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def _rmtree(path: Path, *, dry_run: bool) -> int:
    """Remove a directory tree.  Returns bytes freed."""
    if not path.exists():
        return 0
    size = _dir_size(path)
    label = f"  rm -rf {path.name}/ ({_size_fmt(size)})"
    if dry_run:
        print(f"  [dry-run] {label}")
    else:
        shutil.rmtree(path, ignore_errors=True)
        print(label)
    return size


def _rmfile(path: Path, *, dry_run: bool) -> int:
    """Remove a single file.  Returns bytes freed."""
    if not path.exists():
        return 0
    size = path.stat().st_size
    if dry_run:
        print(f"  [dry-run] rm {path.name} ({_size_fmt(size)})")
    else:
        path.unlink()
        print(f"  rm {path.name} ({_size_fmt(size)})")
    return size


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


def step_1_copy(source: Path, dest: Path, *, dry_run: bool) -> None:
    """Copy the source directory to the destination.

    Excludes large/strip-bound dirs upfront so the copy fits on a constrained
    disk. Steps 2-9 still pass over what's left to remove residue.
    """
    print("\n=== Step 1: Copy working directory ===")
    if dest.exists():
        print(f"  Destination exists, removing: {dest}")
        if not dry_run:
            shutil.rmtree(dest)
    # Pre-copy excludes: dirs we will remove anyway in step 2/3 (so we never
    # spend disk on copying them), plus tracked-but-huge hot paths.
    # results/ is excluded here and re-copied separately below as a single
    # model sample (--keep-model-sample).
    # Match-anywhere patterns (cache/junk dirs that nest at any depth).
    pre_excludes_anywhere: list[str] = [
        ".omc",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".hypothesis",
        ".ruff_cache",
        ".venv311",
        "__pycache__",
    ]
    # Anchored patterns: only match at the source root. CRITICAL — bare names
    # like "fixtures" or "audit" silently match nested dirs (e.g.
    # tests/fixtures/) and break the submission. Always use a leading "/".
    pre_excludes_root: list[str] = [
        "/_archive",
        "/anonymous_repo",
        "/anonymous_repo.zip",
        "/results_old_rag_backup",
        "/data_release",
        "/logs",
        "/physionet.org",
        "/secrets",
        "/site",
        "/staging",
        "/cav_v0_5",
        "/cav_v0_6",
        "/cpg_sources",
        "/sgsc_output",
        "/paper_artifacts",
        "/supplementary",
        "/tex",
        "/artifacts",
        "/fixtures",          # top-level only; tests/fixtures/ stays.
        "/demo",
        "/results",
        "/paper",
        # ANCILLARY_DIRS_REMOVE entries — root-anchored:
        "/clinician_validation",
        "/clinician_study",
        "/clinician_survey",
        "/constraints",
        "/reports",
        "/index",
        "/guidelines",
        "/code_verification",
        "/analysis",
        "/tracking",
        "/encoding_audit",
        "/scenario_review",
        "/system_review",
        "/paper_sections",
        # /audit retained: imported by tests/test_audit/* (authority filter
        # + taxonomies). Removing it would break the submission test suite.
    ]
    pre_excludes_root += [
        "/testing",          # legacy E2E runner; no imports
        "/anonymous_repo",   # double-blind copy lives outside submission tree
    ]
    # Path-prefix excludes (already anchored by virtue of containing a slash).
    pre_excludes_paths: list[str] = [
        "evidence_pack/expansion_v7_track1_logs",
        "evidence_pack/cres_cache",
        "evidence_pack/ex1_llm_judge_3judge",
        "evidence_pack/ex1_llm_judge_gemma31b",
        "evidence_pack/ex1_llm_judge_nemotron30b",
        "evidence_pack/ex1_llm_judge_oss120b",
        # Pickled probe-corpus cache (~485 MB, regenerated by
        # scripts/experiments/probe_cga_s_sensitivity.py on first run).
        "evidence_pack/analysis/_probe_corpus_cache.pkl",
    ]
    pre_excludes: list[str] = (
        pre_excludes_anywhere + pre_excludes_root + pre_excludes_paths
    )
    print(f"  Copying {source} -> {dest} (with {len(pre_excludes)} pre-excludes)")
    if not dry_run:
        rsync_args = ["rsync", "-a"]
        for pat in pre_excludes:
            rsync_args.append(f"--exclude={pat}")
        rsync_args += [f"{source}/", f"{dest}/"]
        subprocess.run(rsync_args, check=True)
    print(f"  Done (excluded {len(pre_excludes)} pre-strip paths).")


def step_1b_copy_model_sample(
    source: Path, dest: Path, model: str | None, *, dry_run: bool
) -> None:
    """Copy a single model sample under results/full_706_v5/<model>/.

    results/ was excluded from the pre-copy in step 1; this restores one
    model's outputs as a smoke-test sample for reviewers.
    """
    if not model:
        print("\n=== Step 1b: Skip model sample (none requested) ===")
        return
    src_dir = source / "results" / "full_706_v5" / model
    dst_dir = dest / "results" / "full_706_v5" / model
    print(f"\n=== Step 1b: Copy model sample ({model}) ===")
    if not src_dir.exists():
        print(f"  SKIP: source not found: {src_dir}")
        return
    print(f"  {src_dir} -> {dst_dir}")
    if not dry_run:
        dst_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["rsync", "-a", f"{src_dir}/", f"{dst_dir}/"],
            check=True,
        )
    print("  Done.")


def step_2_remove_large(
    dest: Path,
    keep_model_sample: str | None,
    *,
    dry_run: bool,
) -> int:
    """Remove large generated/cache directories.  Optionally keep one
    model's results as a smoke-test sample.
    """
    print("\n=== Step 2: Remove large generated/cache directories ===")
    freed = 0

    # Handle results/ specially: keep one model sample
    results_dir = dest / "results"
    if results_dir.exists():
        sample_src = results_dir / "full_706_v5" / (keep_model_sample or "")
        saved = None

        if keep_model_sample and sample_src.exists():
            import tempfile

            tmp = Path(tempfile.mkdtemp(prefix="cga_sample_"))
            if not dry_run:
                shutil.copytree(sample_src, tmp / keep_model_sample)
            saved = tmp
            print(f"  Saved {keep_model_sample} sample to {tmp}")

        freed += _rmtree(results_dir, dry_run=dry_run)

        if saved and keep_model_sample:
            target = dest / "results" / "full_706_v5" / keep_model_sample
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(saved / keep_model_sample, target)
                shutil.rmtree(saved)
            print(f"  Restored {keep_model_sample} sample")

    for dirname in LARGE_DIRS_REMOVE:
        freed += _rmtree(dest / dirname, dry_run=dry_run)

    # Remove all __pycache__
    for pycache in dest.rglob("__pycache__"):
        freed += _rmtree(pycache, dry_run=dry_run)

    print(f"  Total freed: {_size_fmt(freed)}")
    return freed


def step_3_remove_ancillary(dest: Path, *, dry_run: bool) -> int:
    """Remove ancillary non-code directories."""
    print("\n=== Step 3: Remove ancillary non-code directories ===")
    freed = 0
    for dirname in ANCILLARY_DIRS_REMOVE:
        freed += _rmtree(dest / dirname, dry_run=dry_run)
    print(f"  Total freed: {_size_fmt(freed)}")
    return freed


def step_4_trim_evidence_pack(dest: Path, *, dry_run: bool) -> int:
    """Remove regeneratable/unreferenced evidence_pack subdirectories."""
    print("\n=== Step 4: Trim evidence_pack ===")
    freed = 0
    ep = dest / "evidence_pack"
    for dirname in EVIDENCE_PACK_REMOVE:
        freed += _rmtree(ep / dirname, dry_run=dry_run)
    print(f"  Total freed: {_size_fmt(freed)}")
    return freed


def step_5_clean_paper(dest: Path, *, dry_run: bool) -> int:
    """Remove old paper versions, planning docs, build artifacts."""
    print("\n=== Step 5: Clean paper/ directory ===")
    freed = 0
    paper = dest / "paper"

    for fname in PAPER_FILES_REMOVE:
        freed += _rmfile(paper / fname, dry_run=dry_run)

    for dirname in PAPER_DIRS_REMOVE:
        freed += _rmtree(paper / dirname, dry_run=dry_run)

    for pattern in PAPER_GLOB_REMOVE:
        for match in paper.glob(pattern):
            if match.is_file():
                freed += _rmfile(match, dry_run=dry_run)

    print(f"  Total freed: {_size_fmt(freed)}")
    return freed


def step_6_remove_root_files(dest: Path, *, dry_run: bool) -> int:
    """Remove development-only root files."""
    print("\n=== Step 6: Remove development-only root files ===")
    freed = 0
    for fname in ROOT_FILES_REMOVE:
        freed += _rmfile(dest / fname, dry_run=dry_run)
    print(f"  Total freed: {_size_fmt(freed)}")
    return freed


def step_7_trim_docs(dest: Path, *, dry_run: bool) -> int:
    """Trim docs/ to submission-relevant files only."""
    print("\n=== Step 7: Trim docs/ ===")
    freed = 0
    docs = dest / "docs"
    if not docs.exists():
        print("  docs/ not found, skipping")
        return 0

    for dirname in DOCS_DIRS_REMOVE:
        freed += _rmtree(docs / dirname, dry_run=dry_run)

    for f in docs.iterdir():
        if f.is_file() and f.suffix == ".md" and f.name not in DOCS_KEEP:
            freed += _rmfile(f, dry_run=dry_run)

    print(f"  Total freed: {_size_fmt(freed)}")
    return freed


def step_8_fix_paths(dest: Path, *, dry_run: bool) -> None:
    """Apply path corrections to scripts."""
    print("\n=== Step 8: Fix path references ===")
    for relpath, replacements in PATH_FIXES.items():
        fpath = dest / relpath
        if not fpath.exists():
            print(f"  SKIP (not found): {relpath}")
            continue
        content = fpath.read_text()
        changed = False
        for old, new in replacements:
            if old in content:
                content = content.replace(old, new)
                changed = True
                print(f"  {relpath}: '{old}' -> '{new}'")
        if changed and not dry_run:
            fpath.write_text(content)


def step_9_remove_nested(dest: Path, *, dry_run: bool) -> int:
    """Remove stale nested directories."""
    print("\n=== Step 9: Remove stale nested directories ===")
    freed = 0
    for dirname in NESTED_DIRS_REMOVE:
        freed += _rmtree(dest / dirname, dry_run=dry_run)
    print(f"  Total freed: {_size_fmt(freed)}")
    return freed


def step_10_verify(dest: Path) -> bool:
    """Run verification checks on the submission copy."""
    print("\n=== Step 10: Verification ===")
    errors: list[str] = []

    # 10a: Check critical files exist
    print("  Checking critical files...")
    for relpath in VERIFY_CRITICAL_FILES:
        fpath = dest / relpath
        if fpath.exists():
            print(f"    OK: {relpath}")
        else:
            errors.append(f"MISSING: {relpath}")
            print(f"    MISSING: {relpath}")

    # 10b: Check CPG graphs
    graphs = list((dest / "cpg_model" / "graphs").glob("*.yaml"))
    print(f"  CPG graphs: {len(graphs)} (need >= {MIN_CPG_GRAPHS})")
    if len(graphs) < MIN_CPG_GRAPHS:
        errors.append(f"Only {len(graphs)} CPG graphs, expected >= {MIN_CPG_GRAPHS}")

    # 10c: Check entry point syntax
    print("  Checking entry point syntax...")
    for script in VERIFY_ENTRY_POINTS:
        fpath = dest / script
        if not fpath.exists():
            errors.append(f"Entry point missing: {script}")
            print(f"    MISSING: {script}")
            continue
        try:
            ast.parse(fpath.read_text())
            print(f"    OK (syntax): {script}")
        except SyntaxError as e:
            errors.append(f"SyntaxError in {script}: {e}")
            print(f"    FAIL (syntax): {script}: {e}")

    # 10d: Import verification (requires symlink trick)
    print("  Checking imports (via symlink)...")
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cga_verify_") as tmpdir:
        symlink = Path(tmpdir) / "cga_bench"
        symlink.symlink_to(dest)
        env = os.environ.copy()
        env["PYTHONPATH"] = tmpdir

        for mod in VERIFY_MODULES:
            result = subprocess.run(
                [sys.executable, "-c", f"import {mod}"],
                env=env,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"    OK: {mod}")
            else:
                err_line = result.stderr.strip().split("\n")[-1]
                errors.append(f"Import FAIL: {mod} -> {err_line}")
                print(f"    FAIL: {mod} -> {err_line}")

    # 10e: Size report
    total_size = _dir_size(dest)
    py_count = len(list(dest.rglob("*.py")))
    file_count = sum(1 for _ in dest.rglob("*") if _.is_file())
    print(f"\n  Final size: {_size_fmt(total_size)}")
    print(f"  Python files: {py_count}")
    print(f"  Total files: {file_count}")

    if errors:
        print(f"\n  VERIFICATION FAILED: {len(errors)} error(s)")
        for e in errors:
            print(f"    {e}")
        return False

    print("\n  ALL CHECKS PASSED")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a submission-ready copy of CGA-Bench.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              # Full run
              python scripts/submission/prepare_submission.py \\
                  --source . --dest ../cga_bench_submission

              # Dry run (no changes)
              python scripts/submission/prepare_submission.py \\
                  --source . --dest ../cga_bench_submission --dry-run

              # Keep a different model sample
              python scripts/submission/prepare_submission.py \\
                  --source . --dest ../cga_bench_submission \\
                  --keep-model-sample oss120b

              # Skip copy (dest already exists, just re-strip)
              python scripts/submission/prepare_submission.py \\
                  --source . --dest ../cga_bench_submission --skip-copy

              # Verify only (no removal)
              python scripts/submission/prepare_submission.py \\
                  --source . --dest ../cga_bench_submission --verify-only
        """),
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to the development cga_bench directory",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        required=True,
        help="Path for the submission copy",
    )
    parser.add_argument(
        "--keep-model-sample",
        type=str,
        default="qwen4b",
        help="Model name to keep in results/ as smoke-test sample (default: qwen4b)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be removed without making changes",
    )
    parser.add_argument(
        "--skip-copy",
        action="store_true",
        help="Skip the copy step (assume dest already exists)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only run verification on existing dest, no removal",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip the verification step",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    dest = args.dest.resolve()

    print(f"Source: {source}")
    print(f"Dest:   {dest}")
    print(f"Model sample: {args.keep_model_sample or '(none)'}")
    if args.dry_run:
        print("MODE: DRY RUN (no changes will be made)")

    if args.verify_only:
        ok = step_10_verify(dest)
        sys.exit(0 if ok else 1)

    # Step 1: Copy
    if not args.skip_copy:
        step_1_copy(source, dest, dry_run=args.dry_run)
        step_1b_copy_model_sample(
            source, dest, args.keep_model_sample, dry_run=args.dry_run
        )
    else:
        print("\n=== Step 1: Copy SKIPPED (--skip-copy) ===")

    initial_size = _dir_size(dest)
    total_freed = 0

    # Steps 2-9: Removal and fixes
    total_freed += step_2_remove_large(dest, args.keep_model_sample, dry_run=args.dry_run)
    total_freed += step_3_remove_ancillary(dest, dry_run=args.dry_run)
    total_freed += step_4_trim_evidence_pack(dest, dry_run=args.dry_run)
    total_freed += step_5_clean_paper(dest, dry_run=args.dry_run)
    total_freed += step_6_remove_root_files(dest, dry_run=args.dry_run)
    total_freed += step_7_trim_docs(dest, dry_run=args.dry_run)
    step_8_fix_paths(dest, dry_run=args.dry_run)
    total_freed += step_9_remove_nested(dest, dry_run=args.dry_run)

    print("\n=== Summary ===")
    print(f"  Initial size:  {_size_fmt(initial_size)}")
    print(f"  Total freed:   {_size_fmt(total_freed)}")
    final_size = _dir_size(dest)
    print(f"  Final size:    {_size_fmt(final_size)}")
    reduction = (1 - final_size / initial_size) * 100 if initial_size > 0 else 0
    print(f"  Reduction:     {reduction:.1f}%")

    # Step 10: Verify
    if not args.skip_verify and not args.dry_run:
        ok = step_10_verify(dest)
        sys.exit(0 if ok else 1)
    elif args.dry_run:
        print("\n  [dry-run] Verification skipped in dry-run mode")


if __name__ == "__main__":
    main()
