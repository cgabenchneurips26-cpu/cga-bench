#!/usr/bin/env python3
"""Upload CGA-Bench v5 dataset to HuggingFace Hub.

Requires: pip install huggingface_hub

Usage:
    # Login first
    huggingface-cli login

    # Upload (dry run)
    python scripts/hf_upload.py --dry-run

    # Upload for real
    python scripts/hf_upload.py --repo-id <org>/cga-bench

    # Upload specific version
    python scripts/hf_upload.py --repo-id <org>/cga-bench --version 5.0
"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VERSION = "5.0"


def upload_dataset(
    repo_id: str,
    version: str,
    data_dir: Path,
    dry_run: bool = False,
) -> str | None:
    """Upload packaged dataset to HuggingFace Hub.

    Returns:
        The repo URL if upload succeeds, None if dry run.
    """
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("ERROR: huggingface_hub not installed. Run: pip install huggingface_hub")
        return None

    if not data_dir.exists():
        print(f"ERROR: Data directory not found: {data_dir}")
        print(f"Run: PYTHONPATH=. python scripts/package_hf_dataset.py")
        return None

    api = HfApi()

    # Count files
    files = list(data_dir.rglob("*"))
    data_files = [f for f in files if f.is_file()]
    total_size = sum(f.stat().st_size for f in data_files)
    print(f"Dataset: {data_dir}")
    print(f"Files: {len(data_files)}")
    print(f"Size: {total_size / (1024 * 1024):.1f} MB")
    print(f"Repo: {repo_id}")
    print(f"Version tag: v{version}")

    if dry_run:
        print("\n[DRY RUN] Would upload to HuggingFace. Skipping.")
        print(f"  Largest files:")
        largest = sorted(data_files, key=lambda f: f.stat().st_size, reverse=True)[:10]
        for f in largest:
            rel = f.relative_to(data_dir)
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"    {rel}: {size_mb:.1f} MB")
        return None

    print(f"\nCreating/updating repo: {repo_id}")
    api.create_repo(
        repo_id=repo_id,
        repo_type="dataset",
        exist_ok=True,
    )

    print("Uploading files...")
    api.upload_folder(
        repo_id=repo_id,
        folder_path=str(data_dir),
        repo_type="dataset",
        commit_message=f"CGA-Bench v{version} data release",
    )

    # Create version tag
    print(f"Creating tag: v{version}")
    try:
        api.create_tag(
            repo_id=repo_id,
            tag=f"v{version}",
            repo_type="dataset",
        )
    except Exception as e:
        print(f"  Tag creation skipped (may already exist): {e}")

    url = f"https://huggingface.co/datasets/{repo_id}"
    print(f"\nUpload complete: {url}")
    return url


def main() -> None:
    """CLI entry point."""
    parser = ArgumentParser(description="Upload CGA-Bench to HuggingFace Hub")
    parser.add_argument(
        "--repo-id",
        default="anonymous/cga-bench",
        help="HuggingFace repo ID (org/name)",
    )
    parser.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"Version tag (default: {DEFAULT_VERSION})",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Data directory (default: data_release/v{version})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without uploading",
    )
    args = parser.parse_args()

    data_dir = args.data_dir or ROOT / "data_release" / f"v{args.version}"
    upload_dataset(
        repo_id=args.repo_id,
        version=args.version,
        data_dir=data_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
