#!/usr/bin/env python3
"""Patch the live URLs in croissant.json after the dataset is hosted.

Run this AFTER you have uploaded the dataset to one of the preferred
hosts (HuggingFace / Dataverse / Kaggle / OpenML) so the published
Croissant metadata points at retrievable URLs rather than placeholders.

Updates the following fields:
  - top-level `url`              -> dataset landing page
  - `distribution[*].contentUrl` -> per-FileObject download URL,
                                    only when its existing value still
                                    matches a known placeholder host
                                    (anonymous/cga-bench, github.com/anon...)

Validation: re-runs `mlcroissant.Dataset(jsonld=...)` against the
patched file and prints metadata + warnings; the script aborts with
a non-zero exit if mlcroissant raises.

Usage
-----
    # HuggingFace (most common)
    python3 scripts/release/update_croissant_urls.py \
        --croissant croissant.json \
        --hf-repo <user>/cga-bench

    # Generic — provide both landing URL and a base for contentUrl
    python3 scripts/release/update_croissant_urls.py \
        --croissant croissant.json \
        --landing-url https://example.org/cga-bench \
        --content-base https://example.org/cga-bench/raw/main
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Hosts whose URLs are placeholders and should be patched. Anything
# else is left alone so manual edits survive.
PLACEHOLDER_HOST_FRAGMENTS: tuple[str, ...] = (
    "github.com/anonymous/",
    "github.com/anon/",
    "anonymous.4open.science/r/",
    "huggingface.co/datasets/anonymous/",
    "anonymous",
)


def _is_placeholder(url: str) -> bool:
    return any(frag in url for frag in PLACEHOLDER_HOST_FRAGMENTS)


def patch_croissant(
    path: Path,
    landing_url: str,
    content_base: str | None,
) -> int:
    """Return number of fields updated."""
    data = json.loads(path.read_text(encoding="utf-8"))
    updated = 0

    if data.get("url") != landing_url:
        data["url"] = landing_url
        updated += 1

    if content_base:
        for dist in data.get("distribution", []) or []:
            old = dist.get("contentUrl", "")
            if not old:
                continue
            if _is_placeholder(old):
                # Replace the host segment with the new base; keep the
                # path tail (relative file path inside the repo) intact.
                # We approximate by using the existing path-after-host.
                from urllib.parse import urlparse

                parsed = urlparse(old)
                tail = parsed.path.lstrip("/")
                new = content_base.rstrip("/") + "/" + tail
                dist["contentUrl"] = new
                updated += 1

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return updated


def validate(path: Path) -> None:
    try:
        import mlcroissant  # noqa: F401
    except ImportError:
        print(
            "WARN: mlcroissant not installed; skipping validation. "
            "Run: pip install mlcroissant",
            file=sys.stderr,
        )
        return
    import mlcroissant as mlc

    ds = mlc.Dataset(jsonld=str(path))
    print(
        f"  validated: name={ds.metadata.name} "
        f"version={ds.metadata.version} "
        f"n_distribution={len(ds.metadata.distribution)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--croissant",
        type=Path,
        default=Path("croissant.json"),
        help="Path to croissant.json (default: ./croissant.json)",
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--hf-repo",
        help="HuggingFace dataset repo id (e.g. user/cga-bench).",
    )
    grp.add_argument(
        "--landing-url",
        help="Custom dataset landing URL (used with --content-base).",
    )
    parser.add_argument(
        "--content-base",
        help="Base URL for resolved file downloads "
        "(default for HF: https://huggingface.co/datasets/<repo>/resolve/main)",
    )
    args = parser.parse_args()

    if args.hf_repo:
        landing = f"https://huggingface.co/datasets/{args.hf_repo}"
        content_base = (
            args.content_base
            or f"https://huggingface.co/datasets/{args.hf_repo}/resolve/main"
        )
    else:
        landing = args.landing_url
        content_base = args.content_base

    if not args.croissant.exists():
        print(f"ERR: not found: {args.croissant}", file=sys.stderr)
        raise SystemExit(2)

    print(f"Patching {args.croissant}")
    print(f"  landing -> {landing}")
    if content_base:
        print(f"  content -> {content_base}/<path>")
    n = patch_croissant(args.croissant, landing, content_base)
    print(f"  fields updated: {n}")
    validate(args.croissant)


if __name__ == "__main__":
    main()
