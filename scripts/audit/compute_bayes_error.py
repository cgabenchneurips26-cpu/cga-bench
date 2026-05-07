#!/usr/bin/env python3
"""Wrapper for Bayes-error computation — entry point for audit harness.

Delegates to scripts/compute_bayes_error.py (the canonical implementation).
Adds --emit-tex and --verify convenience flags.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute plug-in Bayes error (Theorem 3.4)")
    parser.add_argument("--emit-tex", action="store_true", help="Print macros to stdout")
    parser.add_argument("--verify", action="store_true", help="Verify against committed macros")
    args, remaining = parser.parse_known_args()

    # Isolate sys.argv so the delegated main() only sees its own flags
    original_argv = sys.argv
    sys.argv = [sys.argv[0]] + remaining

    from scripts.compute_bayes_error import main as compute_main

    compute_main()
    sys.argv = original_argv

    macros_path = ROOT / "evidence_pack" / "theorem_v2" / "bayes_error_macros.tex"
    if args.emit_tex and macros_path.exists():
        print(macros_path.read_text())

    if args.verify and macros_path.exists():
        content = macros_path.read_text()
        checks = [
            ("bayesErrTerm", "0.436"),
            ("bayesErrAset", "0.024"),
            ("bayesErrNord", "0.003"),
            ("bayesErrNctx", "0.003"),
        ]
        for macro, expected in checks:
            if f"\\{macro}{{{expected}}}" not in content:
                print(f"MISMATCH: {macro} expected {expected}")
                sys.exit(1)
        print("VERIFY OK: all Bayes error values match committed macros")


if __name__ == "__main__":
    main()
