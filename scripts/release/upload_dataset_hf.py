#!/usr/bin/env python3
"""Upload CGA-Bench dataset to a HuggingFace Datasets repo.

Tested on huggingface_hub >= 0.25 with `pip install -U huggingface_hub`.
Uses an anonymous HuggingFace account; obtain a write token from
https://huggingface.co/settings/tokens and export HF_TOKEN before running.

Usage
-----
    HF_TOKEN=hf_xxxxxxxx python3 scripts/release/upload_dataset_hf.py \
        --repo-id <user>/cga-bench \
        --source . \
        [--private] [--commit-message "..."]

What gets uploaded
------------------
Only reproducibility-essential paths are uploaded; large redundant
artifacts (results/, _archive/, anonymous_repo/, etc.) are excluded
via `IGNORE_PATTERNS`.

After upload, run `update_croissant_urls.py --repo-id <user>/cga-bench`
to patch `croissant.json` so the published `url` / `contentUrl`
fields point at the live repo.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Patterns excluded from the HF upload (rsync-style globs honoured by
# huggingface_hub's `allow_patterns` / `ignore_patterns`).
IGNORE_PATTERNS: list[str] = [
    # Caches / build artifacts
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.mypy_cache/**",
    "**/.ruff_cache/**",
    "**/.hypothesis/**",
    # Internal / out-of-scope content
    "anonymous_repo/**",
    "anonymous_repo.zip",
    "_archive/**",
    "logs/**",
    "data_release/**",
    "results_old_rag_backup/**",
    "site/**",
    "staging/**",
    "secrets/**",
    "physionet.org/**",
    # Paper sources excluded by submission policy (C)
    "paper/**",
    "paper_artifacts/**",
    "tex/**",
    "supplementary/**",
    # Heavy regenerable caches
    "evidence_pack/expansion_v7_track1_logs/**",
    "evidence_pack/cres_cache/**",
    "evidence_pack/analysis/_probe_corpus_cache.pkl",
    # Dev-only metadata
    "MEMORY.md",
    "CLAUDE.md",
    "auto_numbers_audit.csv",
    "mkdocs.yml",
    "rebuttal_preregister_v1.yaml",
    ".git/**",
    ".omc/**",
    ".claude/**",
    ".venv311/**",
]


def upload(repo_id: str, source: Path, private: bool, message: str) -> None:
    try:
        from huggingface_hub import HfApi, create_repo
    except ImportError as e:
        print(
            "ERROR: huggingface_hub not installed. Run: pip install -U huggingface_hub",
            file=sys.stderr,
        )
        raise SystemExit(2) from e

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN env var not set.", file=sys.stderr)
        raise SystemExit(2)

    print(f"Source:  {source.resolve()}")
    print(f"Repo:    {repo_id}  (private={private})")
    print(f"Message: {message}")
    print(f"Excludes: {len(IGNORE_PATTERNS)} patterns")

    create_repo(
        repo_id=repo_id,
        repo_type="dataset",
        private=private,
        exist_ok=True,
        token=token,
    )

    api = HfApi(token=token)
    api.upload_folder(
        folder_path=str(source),
        repo_id=repo_id,
        repo_type="dataset",
        ignore_patterns=IGNORE_PATTERNS,
        commit_message=message,
    )
    print(f"\nDone. View: https://huggingface.co/datasets/{repo_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--repo-id",
        required=True,
        help="HF repo id, e.g. <user-or-org>/cga-bench",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("."),
        help="Local dataset root (default: cwd)",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Create as private repo (default: public)",
    )
    parser.add_argument(
        "--commit-message",
        default="Initial CGA-Bench v7.3 upload",
    )
    args = parser.parse_args()
    upload(args.repo_id, args.source.resolve(), args.private, args.commit_message)


if __name__ == "__main__":
    main()
