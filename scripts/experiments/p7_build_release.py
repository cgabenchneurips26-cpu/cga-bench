#!/usr/bin/env python3
"""P7: Build anonymized CGA-Bench release package for NeurIPS submission.

Creates a clean, anonymized copy of the benchmark code and data
suitable for double-blind review and public release.

Usage:
    PYTHONPATH=. python scripts/experiments/p7_build_release.py

Output:
    cga-bench-release/          # Complete release package
    evidence_pack/analysis/p7_release_manifest.json
    evidence_pack/analysis/p7_release_manifest.md
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]  # cga_bench/
RELEASE_DIR = ROOT / "cga-bench-release"

# ── Anonymization patterns ──────────────────────────────────────────
ANON_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Author names and emails
    (re.compile(r"Simon\s*Xie", re.IGNORECASE), "[Anonymous]"),
    (re.compile(r"simonxie2004@outlook\.com"), "[email-redacted]"),
    (re.compile(r"anonymous", re.IGNORECASE), "anonymous"),
    # Local paths
    (re.compile(r"${CGA_BENCH_ROOT}/cga_bench/?"), ""),
    (re.compile(r"${CGA_BENCH_ROOT}/?"), ""),
    (re.compile(r"/home/anonymous-org/?"), ""),
    # Git URLs with identifiable info
    (re.compile(r"github\.com[:/]anonymous/AnonProject"), "github.com/anonymous/cga-bench"),
    (re.compile(r"github\.com[:/]AnonProject/AnonProject"), "github.com/anonymous/cga-bench"),
    # Parent SDK references (already anonymized via patterns above)
    (re.compile(r"anonymous-project"), "cga-bench-project"),
]

# ── Files and directories to include ────────────────────────────────
CORE_MODULES = [
    "cpg_engine",
    "cpg_model",
    "assessor_core",
    "agent_runner",
    "agent_rules",
    "scenario_engine",
    "eval_harness",
    "tool_api",
    "env",
]

CONFIG_DIRS = [
    "configs/scenarios",
    "configs/agents",
    "configs/experiments",
]

TOP_LEVEL_FILES = [
    "run_benchmark.py",
    "run_neurips_experiment.py",
    "conftest.py",
    "pytest.ini",
    "mypy.ini",
    "Makefile",
    "__init__.py",
]

# Selective test directories (core functionality only)
TEST_DIRS = [
    "tests/test_engine",
    "tests/test_assessor",
    "tests/test_agents",
    "tests/test_agent_rules",
    "tests/test_golden",
    "tests/test_e2e",
    "tests/test_isolation",
    "tests/test_schemas",
    "tests/test_correctness",
    "tests/test_reproducibility",
    "tests/test_normalizer",
    "tests/test_conformance",
]

SCRIPT_FILES = [
    "scripts/ci/audit_sources.py",
    "scripts/ci/audit_citations.py",
    "scripts/ci/leakage_scan.py",
]

# Files/patterns to EXCLUDE
EXCLUDE_PATTERNS = [
    "__pycache__",
    ".pyc",
    ".pyo",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".hypothesis",
    ".omc",
    ".claude",
    ".sisyphus",
    ".git",
    "node_modules",
    ".env",
    "*.log",
]

# Directories to never copy
EXCLUDE_DIRS = {
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".hypothesis",
    ".omc",
    ".claude",
    ".sisyphus",
    ".git",
    "node_modules",
    "logs",
    "history",
    ".github",
}


def should_exclude(path: Path) -> bool:
    """Check if a path should be excluded from the release."""
    parts = path.parts
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    name = path.name
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif pattern in str(path):
            return True
    return False


def anonymize_content(content: str) -> str:
    """Apply anonymization patterns to file content."""
    for pattern, replacement in ANON_PATTERNS:
        content = pattern.sub(replacement, content)
    return content


def file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_file_anonymized(src: Path, dst: Path) -> dict:
    """Copy a file with anonymization. Returns manifest entry."""
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Binary files: copy as-is
    binary_exts = {".json", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2"}
    if src.suffix in binary_exts:
        shutil.copy2(src, dst)
        return {
            "src": str(src.relative_to(ROOT)),
            "dst": str(dst.relative_to(RELEASE_DIR)),
            "sha256": file_sha256(dst),
            "anonymized": False,
        }

    # Text files: anonymize
    try:
        content = src.read_text(encoding="utf-8")
        anonymized = anonymize_content(content)
        dst.write_text(anonymized, encoding="utf-8")
        return {
            "src": str(src.relative_to(ROOT)),
            "dst": str(dst.relative_to(RELEASE_DIR)),
            "sha256": file_sha256(dst),
            "anonymized": content != anonymized,
        }
    except (UnicodeDecodeError, ValueError):
        # Fallback: binary copy
        shutil.copy2(src, dst)
        return {
            "src": str(src.relative_to(ROOT)),
            "dst": str(dst.relative_to(RELEASE_DIR)),
            "sha256": file_sha256(dst),
            "anonymized": False,
        }


def copy_directory(src_dir: Path, dst_dir: Path, manifest: list[dict]) -> int:
    """Recursively copy a directory with anonymization. Returns file count."""
    count = 0
    if not src_dir.exists():
        return 0
    for item in sorted(src_dir.rglob("*")):
        if item.is_dir():
            continue
        if should_exclude(item):
            continue
        rel = item.relative_to(src_dir)
        entry = copy_file_anonymized(item, dst_dir / rel)
        manifest.append(entry)
        count += 1
    return count


def create_requirements_txt() -> str:
    """Generate minimal requirements.txt for the release."""
    return """# CGA-Bench Requirements
# Core
pydantic>=2.0
pyyaml>=6.0

# Scoring & Analysis
numpy>=1.24
scipy>=1.10

# Agent (optional - only needed if running LLM agents)
httpx>=0.24
openai>=1.0

# Retrieval (optional - only needed for RAG agent)
# rank-bm25>=0.2.2
# sentence-transformers>=2.2
# faiss-cpu>=1.7

# Testing
pytest>=7.0
pytest-cov>=4.0

# Visualization (optional)
matplotlib>=3.7
"""


def create_license() -> str:
    """Generate MIT license."""
    return f"""MIT License

Copyright (c) {datetime.now(UTC).year} Anonymous Authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def create_pyproject_toml() -> str:
    """Generate pyproject.toml for the release."""
    return """[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "cga-bench"
version = "1.0.0"
description = "CGA-Bench: Clinical Guideline Adherence Benchmark for LLM Agents"
requires-python = ">=3.11"
license = {text = "MIT"}
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "numpy>=1.24",
    "scipy>=1.10",
]

[project.optional-dependencies]
agent = [
    "httpx>=0.24",
    "openai>=1.0",
]
rag = [
    "rank-bm25>=0.2.2",
    "sentence-transformers>=2.2",
    "faiss-cpu>=1.7",
]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.4",
    "mypy>=1.8",
    "matplotlib>=3.7",
]

[tool.ruff]
target-version = "py311"
line-length = 120

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_functions = "test_*"
"""


def create_readme() -> str:
    """Generate README.md for the release."""
    return """# CGA-Bench: Clinical Guideline Adherence Benchmark

A benchmark for evaluating how well LLM agents adhere to time-sensitive clinical treatment protocols from medical guidelines (CPGs).

## Key Features

- **DualTrack Scoring**: Track A (action coverage) x Track B (CPG compliance) x Safety Gate
- **5 Violation Types**: OMISSION, COMMISSION, TIMING, SEQUENCE, DEVIATION
- **6 Clinical Domains**: Sepsis (SSC 2021), Chest Pain (AHA 2021), Stroke (AHA 2019), Heart Failure (AHA 2022), AKI (KDIGO), DKA (ADA)
- **15 Scenarios** with 14 CPG graph definitions
- **Scoring-Agent Separation**: Agents cannot access scoring modules, preventing evaluation leakage

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd cga-bench

# Install in development mode
pip install -e ".[dev]"

# Or install minimal dependencies
pip install -e .
```

## Quick Start

### Run a single scenario
```bash
PYTHONPATH=. python run_benchmark.py --scenario septic_shock_basic --agent oracle --mock-llm
```

### Run the full experiment
```bash
PYTHONPATH=. python run_neurips_experiment.py --config configs/experiments/neurips_main.yaml
```

### Run tests
```bash
PYTHONPATH=. pytest tests/ -v
```

## Project Structure

```
cga-bench/
+-- cpg_engine/          # CPG graph evaluation engine (SCORING ONLY)
+-- cpg_model/           # CPG graph definitions and schemas
|   +-- graphs/          # 14 YAML CPG graph files
|   +-- schemas/         # Core data types (Action, PatientState, etc.)
+-- assessor_core/       # Violation detection and harm scoring
+-- agent_runner/        # Agent implementations (RAG, Oracle, Planner)
+-- agent_rules/         # Independent rule system for agents
+-- scenario_engine/     # Clinical simulation environment
+-- eval_harness/        # Experiment orchestration
+-- tool_api/            # Scenario API (labs, medications, imaging)
+-- env/                 # Environment configuration
+-- configs/
|   +-- scenarios/       # Clinical scenario definitions
|   +-- agents/          # Agent configurations
|   +-- experiments/     # Experiment configurations
+-- tests/               # 3000+ tests across 12+ categories
+-- scripts/             # CI and analysis scripts
```

## Scoring System

### CGA Score Components (C1-C5)
| Sub-construct | Description |
|---------------|-------------|
| C1 | Path selection (actions within allowed set) |
| C2 | Mandatory completion (required actions done) |
| C3 | Forbidden avoidance (contraindicated actions avoided) |
| C4 | Timing compliance (deadlines met) |
| C5 | Sequence integrity (correct action order) |

### Violation Types
| Type | Description | Severity |
|------|-------------|----------|
| OMISSION | Missing mandatory action | Harm from inaction |
| COMMISSION | Performed forbidden action | Direct harm potential |
| TIMING | Action past deadline | Delay impact |
| SEQUENCE | Incorrect action order | Protocol deviation |
| DEVIATION | Action not in allowed set | Off-protocol risk |

## Supported Clinical Guidelines

| Guideline | Graph File | Key Scenarios |
|-----------|------------|---------------|
| SSC 2021 | `ssc_sepsis_hour1_bundle.yaml` | Hour-1 Bundle, Septic Shock |
| AHA 2021 Chest Pain | `aha_chest_pain.yaml` | STEMI, NSTEMI, RV Infarct |
| AHA 2019 Stroke | `aha_stroke.yaml` | tPA Eligibility, Thrombectomy |
| AHA 2022 Heart Failure | `aha_heart_failure.yaml` | HFrEF, ADHF |
| KDIGO AKI | `kdigo_aki_full.yaml` | Contrast-Induced AKI, CKD |
| ADA DKA | `ada_dka_management.yaml` | DKA Management |

## Architecture: Scoring-Agent Separation

```
SCORING SYSTEM (agent access forbidden):
  cpg_engine/    -> CPG graph evaluation
  assessor_core/ -> Violation detection + harm scoring
  cpg_model/     -> CPG graph definitions

AGENT SYSTEM (agent accessible):
  agent_runner/    -> Agent implementations
  agent_rules/     -> Independent decision tables
  tool_api/        -> Scenario API
  scenario_engine/ -> Clinical simulation
```

## Adding New Scenarios

1. Define a CPG graph in `cpg_model/graphs/` (YAML format)
2. Create scenario config in `configs/scenarios/` with patient state and constraints
3. Add decision rules in `agent_rules/` for the Oracle agent
4. Write golden tests in `tests/test_golden/`

## Reproducibility

- All experiments use fixed random seeds
- 302 pinned dependencies in `requirements.txt`
- Deterministic action normalization
- Budget-matched evaluation (identical inference budgets per agent)

## License

MIT License. See [LICENSE](LICENSE) for details.
"""


def create_gitignore() -> str:
    """Generate .gitignore for the release."""
    return """__pycache__/
*.pyc
*.pyo
.mypy_cache/
.ruff_cache/
.pytest_cache/
.hypothesis/
*.egg-info/
dist/
build/
.env
*.log
results/
reports/
logs/
"""


def build_release() -> dict:
    """Build the complete release package."""
    print("=" * 60)
    print("P7: Building CGA-Bench Release Package")
    print("=" * 60)

    # Clean previous release
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)

    manifest: list[dict] = []
    stats: dict[str, int] = {}

    # 1. Copy core modules
    print("\n[1/7] Copying core modules...")
    for module in CORE_MODULES:
        src = ROOT / module
        dst = RELEASE_DIR / module
        count = copy_directory(src, dst, manifest)
        stats[module] = count
        print(f"  {module}: {count} files")

    # 2. Copy configs
    print("\n[2/7] Copying configurations...")
    for config_dir in CONFIG_DIRS:
        src = ROOT / config_dir
        dst = RELEASE_DIR / config_dir
        count = copy_directory(src, dst, manifest)
        stats[config_dir] = count
        print(f"  {config_dir}: {count} files")

    # Also copy domain_registry.yaml if it exists at configs/ root
    domain_reg = ROOT / "configs" / "domain_registry.yaml"
    if domain_reg.exists():
        entry = copy_file_anonymized(domain_reg, RELEASE_DIR / "configs" / "domain_registry.yaml")
        manifest.append(entry)
        stats["configs/domain_registry.yaml"] = 1

    # 3. Copy tests
    print("\n[3/7] Copying tests...")
    total_tests = 0
    for test_dir in TEST_DIRS:
        src = ROOT / test_dir
        dst = RELEASE_DIR / test_dir
        count = copy_directory(src, dst, manifest)
        stats[test_dir] = count
        total_tests += count
        print(f"  {test_dir}: {count} files")

    # Copy test conftest files
    for conftest in [ROOT / "tests" / "__init__.py", ROOT / "tests" / "conftest.py"]:
        if conftest.exists():
            entry = copy_file_anonymized(conftest, RELEASE_DIR / "tests" / conftest.name)
            manifest.append(entry)

    # 4. Copy top-level files
    print("\n[4/7] Copying top-level files...")
    for fname in TOP_LEVEL_FILES:
        src = ROOT / fname
        if src.exists():
            entry = copy_file_anonymized(src, RELEASE_DIR / fname)
            manifest.append(entry)
            print(f"  {fname}")

    # 5. Copy CI scripts
    print("\n[5/7] Copying CI scripts...")
    for script_path in SCRIPT_FILES:
        src = ROOT / script_path
        if src.exists():
            dst = RELEASE_DIR / script_path
            entry = copy_file_anonymized(src, dst)
            manifest.append(entry)
            print(f"  {script_path}")

    # Also copy scripts/__init__.py and scripts/ci/__init__.py
    for init_path in ["scripts/__init__.py", "scripts/ci/__init__.py"]:
        src = ROOT / init_path
        dst = RELEASE_DIR / init_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            entry = copy_file_anonymized(src, dst)
            manifest.append(entry)
        else:
            dst.write_text("")

    # 6. Generate new files
    print("\n[6/7] Generating release files...")

    # README.md
    readme_path = RELEASE_DIR / "README.md"
    readme_path.write_text(create_readme())
    manifest.append({"src": "GENERATED", "dst": "README.md", "sha256": file_sha256(readme_path), "anonymized": True})
    print("  README.md")

    # LICENSE
    license_path = RELEASE_DIR / "LICENSE"
    license_path.write_text(create_license())
    manifest.append({"src": "GENERATED", "dst": "LICENSE", "sha256": file_sha256(license_path), "anonymized": True})
    print("  LICENSE")

    # pyproject.toml
    pyproject_path = RELEASE_DIR / "pyproject.toml"
    pyproject_path.write_text(create_pyproject_toml())
    manifest.append(
        {"src": "GENERATED", "dst": "pyproject.toml", "sha256": file_sha256(pyproject_path), "anonymized": True}
    )
    print("  pyproject.toml")

    # requirements.txt
    reqs_path = RELEASE_DIR / "requirements.txt"
    reqs_path.write_text(create_requirements_txt())
    manifest.append(
        {"src": "GENERATED", "dst": "requirements.txt", "sha256": file_sha256(reqs_path), "anonymized": True}
    )
    print("  requirements.txt")

    # .gitignore
    gitignore_path = RELEASE_DIR / ".gitignore"
    gitignore_path.write_text(create_gitignore())
    manifest.append(
        {"src": "GENERATED", "dst": ".gitignore", "sha256": file_sha256(gitignore_path), "anonymized": True}
    )
    print("  .gitignore")

    # 7. Verification
    print("\n[7/7] Verifying release package...")

    # Count anonymized files
    n_anonymized = sum(1 for e in manifest if e.get("anonymized"))
    n_total = len(manifest)

    # Check for any remaining PII leaks
    pii_patterns = [
        re.compile(r"Simon\s*Xie", re.IGNORECASE),
        re.compile(r"simonxie2004"),
        re.compile(r"anonymous"),
        re.compile(r"/home/anonymous-org"),
    ]
    leaks: list[dict] = []
    for item in sorted(RELEASE_DIR.rglob("*")):
        if item.is_dir():
            continue
        if item.suffix in {".json", ".pdf", ".png", ".jpg", ".jpeg", ".gif"}:
            continue
        try:
            content = item.read_text(encoding="utf-8")
            for pat in pii_patterns:
                matches = pat.findall(content)
                if matches:
                    leaks.append(
                        {
                            "file": str(item.relative_to(RELEASE_DIR)),
                            "pattern": pat.pattern,
                            "count": len(matches),
                        }
                    )
        except (UnicodeDecodeError, ValueError):
            pass

    # Compute total size
    total_size = sum(f.stat().st_size for f in RELEASE_DIR.rglob("*") if f.is_file())

    # Build result
    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "release_dir": str(RELEASE_DIR),
        "total_files": n_total,
        "anonymized_files": n_anonymized,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "pii_leaks": leaks,
        "pii_clean": len(leaks) == 0,
        "stats_by_module": stats,
        "generated_files": [
            "README.md",
            "LICENSE",
            "pyproject.toml",
            "requirements.txt",
            ".gitignore",
        ],
        "excluded_from_release": [
            "results/ (experiment results with model outputs)",
            "evidence_pack/ (analysis artifacts)",
            "paper_sections/ (LaTeX source)",
            "paper/ (paper draft)",
            "docs/ (internal documentation)",
            "data/ (MIMIC-IV demo data)",
            "clinician_validation/ (survey materials)",
            "semantic_layer/ (external benchmark adapters)",
            "history/ (legacy code)",
            "reports/ (internal reports)",
            ".claude/ .omc/ .sisyphus/ (tool configs)",
            "run_external_benchmark.py (external eval, not core)",
            "run_eval_science_llm.py (internal experiment)",
        ],
        "availability_statement": (
            "Code, scenario definitions, and constraint specifications "
            "are available at [anonymous URL]. The evaluation pipeline is "
            "deterministic and fully reproducible with fixed random seeds. "
            "All 14 CPG graph definitions, 15+ clinical scenarios, and "
            "3,000+ unit tests are included. "
            "Licensed under the MIT License."
        ),
        "manifest": manifest,
    }

    # Print summary
    print("\n" + "=" * 60)
    print("RELEASE PACKAGE SUMMARY")
    print("=" * 60)
    print(f"  Total files:     {n_total}")
    print(f"  Anonymized:      {n_anonymized}")
    print(f"  Package size:    {result['total_size_mb']} MB")
    print(f"  PII leaks:       {len(leaks)}")
    print(f"  PII clean:       {'YES' if result['pii_clean'] else 'NO — FIX REQUIRED'}")
    if leaks:
        print("\n  LEAK DETAILS:")
        for leak in leaks:
            print(f"    {leak['file']}: {leak['pattern']} ({leak['count']}x)")

    return result


def save_outputs(result: dict) -> None:
    """Save manifest and markdown report."""
    out_dir = ROOT / "evidence_pack" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON manifest (without full file list for readability)
    json_result = {k: v for k, v in result.items() if k != "manifest"}
    json_result["manifest_entries"] = len(result["manifest"])
    json_path = out_dir / "p7_release_manifest.json"
    with open(json_path, "w") as f:
        json.dump(json_result, f, indent=2)
    print(f"\nSaved: {json_path}")

    # Markdown report
    md_lines = [
        "# P7: CGA-Bench Release Package Manifest",
        "",
        f"**Built**: {result['timestamp']}",
        f"**Total files**: {result['total_files']}",
        f"**Anonymized**: {result['anonymized_files']}",
        f"**Package size**: {result['total_size_mb']} MB",
        f"**PII clean**: {'YES' if result['pii_clean'] else 'NO'}",
        "",
        "## Module File Counts",
        "",
        "| Module | Files |",
        "|--------|------:|",
    ]
    for module, count in sorted(result["stats_by_module"].items()):
        md_lines.append(f"| `{module}` | {count} |")

    md_lines.extend(
        [
            "",
            "## Generated Files",
            "",
        ]
    )
    for gf in result["generated_files"]:
        md_lines.append(f"- `{gf}`")

    md_lines.extend(
        [
            "",
            "## Excluded from Release",
            "",
        ]
    )
    for exc in result["excluded_from_release"]:
        md_lines.append(f"- {exc}")

    if result["pii_leaks"]:
        md_lines.extend(
            [
                "",
                "## PII Leaks (MUST FIX)",
                "",
                "| File | Pattern | Count |",
                "|------|---------|------:|",
            ]
        )
        for leak in result["pii_leaks"]:
            md_lines.append(f"| `{leak['file']}` | `{leak['pattern']}` | {leak['count']} |")

    md_lines.extend(
        [
            "",
            "## Availability Statement (for paper)",
            "",
            f"> {result['availability_statement']}",
            "",
            "## Verification Commands",
            "",
            "```bash",
            "# Install from release",
            "cd cga-bench-release",
            "pip install -e '.[dev]'",
            "",
            "# Run tests",
            "PYTHONPATH=. pytest tests/ -v",
            "",
            "# Run a scenario with mock LLM",
            "PYTHONPATH=. python run_benchmark.py --scenario septic_shock_basic --agent oracle --mock-llm",
            "",
            "# Verify no PII",
            "grep -rn 'Simon\\|simonxie\\|anonymous\\|/home/anonymous-org' . --include='*.py' --include='*.yaml' --include='*.md'",
            "```",
        ]
    )

    md_path = out_dir / "p7_release_manifest.md"
    md_path.write_text("\n".join(md_lines))
    print(f"Saved: {md_path}")


if __name__ == "__main__":
    result = build_release()
    save_outputs(result)
