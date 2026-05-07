#!/usr/bin/env python3
"""P0-1: Runtime observation leakage audit for SGSC artifacts.

Scans public scenario files and config YAMLs to verify that no private
evaluation fields (expected_actions, forbidden_actions, mandatory_actions,
ground_truth, etc.) leak into agent-visible artifacts.

Usage:
    PYTHONPATH=. python scripts/sgsc/audit_runtime_observation_leakage.py
    PYTHONPATH=. python scripts/sgsc/audit_runtime_observation_leakage.py --sgsc-dir sgsc_output
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from sgsc.audit.leakage_scanner import _PRIVATE_TOKENS, scan_public_scenarios  # noqa: E402

logger = logging.getLogger("audit_runtime_leakage")

# Fields that MUST NOT appear in public scenarios
PRIVATE_KEYS = set(_PRIVATE_TOKENS)

# Config keys that indicate CDS assistance leakage
CDS_ASSISTANCE_KEY = "cds_assistance"


def _safe_relative(path: Path) -> str:
    """Return path relative to REPO_ROOT, or absolute if outside."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def scan_sgsc_public_scenarios(sgsc_dir: Path) -> tuple[int, list[dict[str, str]]]:
    """Scan all *_scenarios_public.json in sgsc_output for private field leaks."""
    total_scanned = 0
    all_leaks: list[dict[str, str]] = []

    for guideline_dir in sorted(sgsc_dir.iterdir()):
        if not guideline_dir.is_dir():
            continue
        for pub_file in guideline_dir.glob("*_scenarios_public.json"):
            try:
                data = json.loads(pub_file.read_text())
            except (json.JSONDecodeError, OSError) as e:
                all_leaks.append(
                    {
                        "file": _safe_relative(pub_file),
                        "pattern": "PARSE_ERROR",
                        "detail": str(e),
                    }
                )
                continue

            if not isinstance(data, dict):
                continue

            result = scan_public_scenarios(data)
            total_scanned += result.scenarios_scanned
            for leak in result.leaks:
                leak["file"] = _safe_relative(pub_file)
                all_leaks.append(leak)

    return total_scanned, all_leaks


def scan_config_yamls_for_cds(config_dir: Path) -> tuple[int, list[dict[str, str]]]:
    """Scan configs/scenarios/*.yaml for cds_assistance: true."""
    import yaml

    scanned = 0
    leaks: list[dict[str, str]] = []

    for yaml_file in sorted(config_dir.glob("**/*.yaml")):
        try:
            content = yaml_file.read_text()
        except OSError:
            continue
        scanned += 1

        # Quick text scan first
        if CDS_ASSISTANCE_KEY not in content:
            continue

        try:
            docs = list(yaml.safe_load_all(content))
        except yaml.YAMLError:
            continue

        for doc in docs:
            if not isinstance(doc, dict):
                continue
            _scan_dict_for_cds(doc, yaml_file, "", leaks)

    return scanned, leaks


def _scan_dict_for_cds(
    d: dict,
    source_file: Path,
    path: str,
    leaks: list[dict[str, str]],
) -> None:
    for key, val in d.items():
        current = f"{path}.{key}" if path else key
        if key == CDS_ASSISTANCE_KEY and val is True:
            leaks.append(
                {
                    "file": _safe_relative(source_file),
                    "path": current,
                    "pattern": "cds_assistance_true",
                    "detail": f"cds_assistance=True at {current}",
                }
            )
        elif isinstance(val, dict):
            _scan_dict_for_cds(val, source_file, current, leaks)
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    _scan_dict_for_cds(item, source_file, f"{current}[{i}]", leaks)


def scan_for_canary_tokens(sgsc_dir: Path, canary_tokens: list[str] | None = None) -> list[dict[str, str]]:
    """Scan public artifacts for planted canary tokens."""
    if not canary_tokens:
        return []

    leaks: list[dict[str, str]] = []
    for pub_file in sgsc_dir.rglob("*_scenarios_public.json"):
        content = pub_file.read_text()
        for token in canary_tokens:
            if token in content:
                leaks.append(
                    {
                        "file": _safe_relative(pub_file),
                        "pattern": "canary_token",
                        "detail": f"Canary '{token[:20]}...' found in public artifact",
                    }
                )
    return leaks


def run_audit(
    sgsc_dir: Path,
    config_dir: Path,
    canary_tokens: list[str] | None = None,
) -> dict:
    """Run the full runtime leakage audit."""
    input_files: list[Path] = []
    input_files.extend(sgsc_dir.rglob("*_scenarios_public.json"))
    input_files.extend(config_dir.glob("**/*.yaml"))

    # 1. Public scenario scan
    pub_scanned, pub_leaks = scan_sgsc_public_scenarios(sgsc_dir)

    # 2. Config YAML scan for cds_assistance
    cfg_scanned, cds_leaks = scan_config_yamls_for_cds(config_dir)

    # 3. Canary token scan
    canary_leaks = scan_for_canary_tokens(sgsc_dir, canary_tokens)

    all_failures = pub_leaks + cds_leaks + canary_leaks

    # Determine status
    if all_failures:
        status = "fail"
    else:
        status = "pass"

    report = {
        "check_name": "runtime_observation_leakage",
        "status": status,
        "commit": _git_commit(),
        "input_hash": _hash_files(input_files),
        "metrics": {
            "public_scenarios_scanned": pub_scanned,
            "config_yamls_scanned": cfg_scanned,
            "private_field_leaks": len(pub_leaks),
            "cds_assistance_true_count": len(cds_leaks),
            "canary_hits": len(canary_leaks),
            "total_failures": len(all_failures),
        },
        "failures": all_failures,
    }

    # Add output_hash after building report
    report_bytes = json.dumps(report, sort_keys=True).encode()
    report["output_hash"] = hashlib.sha256(report_bytes).hexdigest()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P0-1: Runtime observation leakage audit")
    parser.add_argument("--sgsc-dir", default=str(REPO_ROOT / "sgsc_output"))
    parser.add_argument("--config-dir", default=str(REPO_ROOT / "configs"))
    parser.add_argument(
        "--output", default=str(REPO_ROOT / "evidence_pack" / "analysis" / "runtime_leakage_audit.json")
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sgsc_dir = Path(args.sgsc_dir)
    config_dir = Path(args.config_dir)

    if not sgsc_dir.is_dir():
        logger.error("SGSC output dir not found: %s", sgsc_dir)
        return 1

    report = run_audit(sgsc_dir, config_dir)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Report written to %s", output_path)

    print("\n=== Runtime Leakage Audit ===")
    print(f"Status: {report['status'].upper()}")
    print(f"Public scenarios scanned: {report['metrics']['public_scenarios_scanned']}")
    print(f"Config YAMLs scanned: {report['metrics']['config_yamls_scanned']}")
    print(f"Private field leaks: {report['metrics']['private_field_leaks']}")
    print(f"CDS assistance true: {report['metrics']['cds_assistance_true_count']}")
    print(f"Canary hits: {report['metrics']['canary_hits']}")

    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
