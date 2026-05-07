"""Prepare an anonymous copy of the repository for NeurIPS submission.

Strips PII, GitHub handles, email addresses, organization names, and
server URLs. Copies the tree to anonymous_repo/ with redactions applied.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "anonymous_repo"

# Patterns to redact
PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[email-redacted]"),
    # GitHub handles — specific known handles only (generic @handle pattern
    # removed: it mangles Python decorators (@dataclass, @property, etc.)
    # and provides zero additional coverage beyond the name patterns below).
    # Known organization / author names (add more as needed)
    (re.compile(r"anonymous", re.IGNORECASE), "anonymous"),
    (re.compile(r"anonymous-user", re.IGNORECASE), "anonymous-user"),
    (re.compile(r"anonymous-org", re.IGNORECASE), "anonymous-org"),
    (re.compile(r"anonymous-project", re.IGNORECASE), "anonymous-project"),
    (re.compile(r"\bAgentBeats\b", re.IGNORECASE), "AnonProject"),
    (re.compile(r"\bresearch_ai\b", re.IGNORECASE), "anonymous-user"),
    (re.compile(r"\bsystem_ai\b", re.IGNORECASE), "anonymous-user"),
    (re.compile(r"anonymous-user", re.IGNORECASE), "anonymous-user"),
    (re.compile(r"\btommy\b", re.IGNORECASE), "anonymous-user"),
    # Korean institution names that could de-anonymize raters/authors
    (re.compile(r"(서울대|강원대|연세대|고려대|삼성서울)병원"), "anonymous-hospital"),
    # Server URLs with IP addresses
    (re.compile(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}[:\d]*"), "http://localhost:8013"),
    # Bare IP addresses (SSH targets, config files, etc.) - catch full and partial
    (re.compile(r"211\.54\.28\.\S+"), "127.0.0.1"),
    # Hostnames
    (re.compile(r"\bidc93\b"), "localhost"),
    # SSH git URLs
    (re.compile(r"git@github\.com:[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+\.git"), "[email-redacted]:anonymous/anonymous.git"),
]

# Directories to exclude from the anonymous copy
EXCLUDE_DIRS: set[str] = {
    ".git",
    ".omc",
    "_archive",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".hypothesis",
    ".ruff_cache",
    ".venv311",
    "reports",
    "anonymous_repo",
    ".claude",
    "node_modules",
    "sgsc_output",
    "paper_artifacts",
    "physionet.org",
    "supplementary",
    "cav_v0_6",
    "tex",
    "artifacts",
    "results",
    "data_release",
    "results_old_rag_backup",
    ".sisyphus",
    "secrets",
    "logs",
    "clinician_validation",  # rater PII risk; not needed for review
    "paper",                  # paper-bound per (C) policy
}

# File extensions to exclude
EXCLUDE_EXTENSIONS: set[str] = {
    ".pyc",
    ".pyo",
    ".egg-info",
    ".so",
    ".dylib",
}

# Files to skip entirely
EXCLUDE_FILES: set[str] = {
    ".env",
    ".env.local",
    "credentials.json",
    "requirements.lock",
}

# Text file extensions (apply redaction)
TEXT_EXTENSIONS: set[str] = {
    ".py",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".tex",
    ".bib",
    ".json",
    ".jinja2",
    ".j2",
    ".sh",
    ".bash",
    ".html",
    ".css",
    ".js",
    # Run logs from experiments / vLLM frequently embed lab IPs and host
    # paths; redact rather than copy verbatim.
    ".log",
    ".out",
    ".err",
    ".csv",
    ".conf",
}


def should_exclude(path: Path) -> bool:
    """Check if a path should be excluded."""
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    if path.name in EXCLUDE_FILES:
        return True
    if path.suffix in EXCLUDE_EXTENSIONS:
        return True
    return False


def redact_text(content: str) -> str:
    """Apply all PII patterns to redact content."""
    for pattern, replacement in PII_PATTERNS:
        content = pattern.sub(replacement, content)
    return content


def copy_with_redaction(src: Path, dst: Path) -> tuple[int, int]:
    """Copy directory tree with redactions. Returns (files_copied, files_redacted)."""
    files_copied = 0
    files_redacted = 0

    for src_path in sorted(src.rglob("*")):
        rel = src_path.relative_to(src)
        if should_exclude(rel):
            continue

        dst_path = dst / rel

        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
            continue

        if not src_path.is_file():
            continue

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if src_path.suffix in TEXT_EXTENSIONS:
            try:
                content = src_path.read_text(encoding="utf-8")
                redacted = redact_text(content)
                dst_path.write_text(redacted, encoding="utf-8")
                if content != redacted:
                    files_redacted += 1
            except (UnicodeDecodeError, PermissionError):
                shutil.copy2(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)

        files_copied += 1

    return files_copied, files_redacted


def verify_no_pii(directory: Path) -> list[str]:
    """Scan for any remaining PII in the output directory."""
    findings: list[str] = []
    check_patterns = [
        (re.compile(r"anonymous", re.IGNORECASE), "GitHub handle"),
        (re.compile(r"[a-zA-Z0-9_.+-]+@(?!example\.com)[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "Email address"),
    ]

    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_EXTENSIONS:
            continue
        try:
            content = path.read_text(encoding="utf-8")
            for pattern, label in check_patterns:
                matches = pattern.findall(content)
                for match in matches:
                    findings.append(f"{path.relative_to(directory)}: {label} '{match}'")
        except (UnicodeDecodeError, PermissionError):
            pass

    return findings


def main() -> None:
    print("Preparing anonymous repository...")
    print(f"  Source: {ROOT}")
    print(f"  Output: {OUTPUT_DIR}")

    if OUTPUT_DIR.exists():
        print("  Removing existing anonymous_repo/...")
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True)

    files_copied, files_redacted = copy_with_redaction(ROOT, OUTPUT_DIR)
    print(f"  Files copied: {files_copied}")
    print(f"  Files redacted: {files_redacted}")

    # Verification pass
    print("\nVerifying no PII remains...")
    findings = verify_no_pii(OUTPUT_DIR)
    if findings:
        print(f"  WARNING: {len(findings)} potential PII items found:")
        for f in findings[:20]:
            print(f"    {f}")
        if len(findings) > 20:
            print(f"    ... and {len(findings) - 20} more")
    else:
        print("  PASS: No PII detected.")

    print("\nDone. Review anonymous_repo/ before submission.")


if __name__ == "__main__":
    main()
