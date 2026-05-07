#!/usr/bin/env python3
"""Package CGA-Bench v5 data for HuggingFace Datasets upload.

Creates a self-contained dataset directory with:
  - CPG graphs (25 YAML)
  - Scenarios (manual + auto)
  - Typed constraints export (JSON)
  - Episode results (9 models × ~2,118 episodes)
  - Gold set splits (train/dev/test)
  - RAG corpus (25 parsed guideline docs)
  - Dataset card (README.md)
  - Checksums (SHA256)

Usage:
    PYTHONPATH=. python scripts/package_hf_dataset.py [--output-dir /path/to/output]
"""

from __future__ import annotations

from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path
import shutil

import yaml

ROOT = Path(__file__).resolve().parent.parent
VERSION = "5.0"
RELEASE_DATE = "2026-04-10"

# Models included in the paper
# Models included in the paper (biomed8b excluded: only 1 episode, incomplete run)
PAPER_MODELS = [
    "oss120b",
    "qwen27b",
    "qwen35b",
    "qwen4b",
    "qwen397b",
    "gemma31b",
    "nemotron30b",
    "deepseek_r1_7b",
    "llama4scout",
]

# Minimum episodes required to include a model
MIN_EPISODES = 100


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_graphs(dst: Path) -> int:
    """Copy CPG graph YAML files."""
    src = ROOT / "cpg_model" / "graphs"
    out = dst / "cpg_graphs"
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in sorted(src.glob("*.yaml")):
        shutil.copy2(f, out / f.name)
        count += 1
    return count


def copy_scenarios(dst: Path) -> tuple[int, int]:
    """Copy scenario YAML files. Returns (manual, auto) counts."""
    src = ROOT / "configs" / "scenarios"
    out = dst / "scenarios"
    out.mkdir(parents=True, exist_ok=True)
    manual = auto = 0
    for f in sorted(src.glob("*.yaml")):
        shutil.copy2(f, out / f.name)
        if "auto_generated" in f.name:
            auto += 1
        else:
            manual += 1
    return manual, auto


def copy_constraints(dst: Path) -> int:
    """Copy constraints export."""
    src = ROOT / "constraints" / "constraints_export.json"
    out = dst / "constraints"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out / "constraints_export.json")
    data = json.loads(src.read_text())
    return data["metadata"]["total_constraints"]


def copy_gold_set(dst: Path) -> dict[str, int]:
    """Copy gold set splits."""
    src = ROOT / "data_release" / "v1.0" / "gold_set"
    out = dst / "gold_set"
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for f in sorted(src.glob("*.jsonl")):
        shutil.copy2(f, out / f.name)
        with open(f) as fh:
            counts[f.stem] = sum(1 for _ in fh)
    return counts


def copy_rag_corpus(dst: Path) -> int:
    """Copy RAG corpus parsed documents from cpg_sources/."""
    src = ROOT / "cpg_sources"
    out = dst / "rag_corpus"
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in sorted(src.glob("*.parsed.json")):
        shutil.copy2(f, out / f.name)
        count += 1
    return count


def copy_episodes(dst: Path) -> dict[str, int]:
    """Copy episode result JSON files for paper models.

    Skips checkpoint*.json runner artifacts and models with fewer
    than MIN_EPISODES episodes.
    """
    src = ROOT / "results" / "full_706_v5"
    out = dst / "episodes"
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for model in PAPER_MODELS:
        model_src = src / model
        if not model_src.is_dir():
            print(f"  WARNING: {model} not found, skipping")
            continue
        # Collect only episode files (exclude checkpoint artifacts)
        episode_files = [f for f in sorted(model_src.glob("*.json")) if not f.name.startswith("checkpoint")]
        if len(episode_files) < MIN_EPISODES:
            print(f"  WARNING: {model} has only {len(episode_files)} episodes (< {MIN_EPISODES}), skipping")
            continue
        model_dst = out / model
        model_dst.mkdir(exist_ok=True)
        for f in episode_files:
            shutil.copy2(f, model_dst / f.name)
        counts[model] = len(episode_files)
    return counts


def copy_guideline_cards(dst: Path) -> bool:
    """Copy guideline cards metadata."""
    src = ROOT / "evidence_pack" / "guideline_cards.yaml"
    if src.exists():
        shutil.copy2(src, dst / "guideline_cards.yaml")
        return True
    return False


def copy_license(dst: Path) -> bool:
    """Copy LICENSE file."""
    src = ROOT / "LICENSE"
    if src.exists():
        shutil.copy2(src, dst / "LICENSE")
        return True
    return False


def compute_checksums(dst: Path) -> dict[str, str]:
    """Compute SHA-256 checksums for all data files."""
    checksums: dict[str, str] = {}
    for f in sorted(dst.rglob("*")):
        if f.is_file() and f.name not in ("sha256sums.txt", "README.md"):
            rel = f.relative_to(dst)
            checksums[str(rel)] = sha256_file(f)
    # Write checksums file
    sums_file = dst / "sha256sums.txt"
    with open(sums_file, "w") as fh:
        for path, digest in sorted(checksums.items()):
            fh.write(f"{digest}  {path}\n")
    return checksums


def count_scenarios_in_yamls(dst: Path) -> int:
    """Count total scenarios across YAML files."""
    total = 0
    for f in (dst / "scenarios").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        if isinstance(data, dict):
            # auto scenarios: dict with scenario keys
            scenarios = data.get("scenarios", data)
            if isinstance(scenarios, (dict, list)):
                total += len(scenarios) if isinstance(scenarios, list) else len(scenarios)
    return total


def generate_dataset_card(
    dst: Path,
    *,
    n_graphs: int,
    n_manual: int,
    n_auto: int,
    n_constraints: int,
    gold_counts: dict[str, int],
    n_rag: int,
    episode_counts: dict[str, int],
) -> None:
    """Generate HuggingFace dataset card (README.md)."""
    total_episodes = sum(episode_counts.values())
    total_gold = gold_counts.get("gold_set_v2", 0)

    card = f"""---
language:
  - en
license: cc-by-4.0
size_categories:
  - 10K<n<100K
task_categories:
  - text-generation
  - question-answering
tags:
  - medical
  - clinical-guidelines
  - benchmark
  - agent-evaluation
  - conformance-testing
  - neurips-2026
pretty_name: CGA-Bench
dataset_info:
  config_name: default
  features:
    - name: scenario_id
      dtype: string
    - name: model_id
      dtype: string
    - name: run_id
      dtype: int32
    - name: compliance_score
      dtype: float64
    - name: total_violations
      dtype: int32
    - name: verdict
      dtype: string
---

# CGA-Bench: Clinical Guideline Adherence Benchmark

**Version {VERSION}** | Released {RELEASE_DATE} | CC-BY-4.0

CGA-Bench evaluates how well LLM agents adhere to time-sensitive clinical
treatment protocols from medical guidelines (CPGs). It uses typed constraints
(FORBIDDEN, REQUIRED, BEFORE, WITHIN) derived from 25 clinical practice
guideline graphs to audit agent trace-level conformance.

## Dataset Summary

| Component | Count |
|-----------|-------|
| CPG Graphs | {n_graphs} (20 core + 5 held-out) |
| Scenarios (manual) | {n_manual} files |
| Scenarios (auto-generated) | {n_auto} files |
| Typed Constraints | {n_constraints} |
| Episode Results | {total_episodes:,} ({len(episode_counts)} models) |
| Gold Set Instances | {total_gold} |
| RAG Corpus Documents | {n_rag} |

## Models Evaluated

| Model | Episodes |
|-------|----------|
"""
    for model, count in sorted(episode_counts.items()):
        card += f"| {model} | {count:,} |\n"

    card += f"""
## Directory Structure

```
cga-bench-v{VERSION}/
├── cpg_graphs/              # 25 CPG graph YAML files
├── scenarios/               # Evaluation scenario configurations
├── constraints/             # Typed constraint export (JSON)
├── episodes/                # Agent episode traces per model
│   ├── oss120b/
│   ├── qwen27b/
│   └── ...
├── gold_set/                # Entity linking gold standard
│   ├── train.jsonl
│   ├── dev.jsonl
│   └── test.jsonl
├── rag_corpus/              # Parsed guideline documents
├── guideline_cards.yaml     # Per-graph provenance summaries
├── LICENSE                  # CC-BY-4.0
└── sha256sums.txt           # File integrity checksums
```

## Constraint Types

- **REQUIRED**: Mandatory clinical actions (n={n_constraints} total across types)
- **FORBIDDEN**: Contraindicated actions
- **BEFORE**: Temporal ordering constraints (A must precede B)
- **WITHIN**: Deadline constraints (action must occur within N minutes)

## Violation Types

- **OMISSION**: Missing mandatory action
- **COMMISSION**: Performed forbidden action
- **TIMING**: Action performed past deadline
- **SEQUENCE**: Incorrect action order
- **DEVIATION**: Action not in allowed set

## Clinical Domains

SSC Sepsis (2021), AHA Chest Pain (2021), AHA Stroke (2019),
AHA Heart Failure (2022), KDIGO AKI, ADA DKA, ESC AF (2020),
ATS/IDSA CAP (2019), GOLD COPD (2024), ACG GI Bleeding (2023),
AHA Hypertensive Crisis (2017), KDIGO Contrast AKI,
ESC PE (2019), ACLS (2020), Anaphylaxis (2020),
AABB Transfusion (2024), ATS Asthma (2020),
Meningitis (2021), Status Epilepticus (2016),
+ 5 held-out guidelines

## Citation

```bibtex
@inproceedings{{cgabench2026,
  title={{CGA-Bench: Clinical Guideline Adherence Benchmark}},
  author={{Anonymous}},
  booktitle={{NeurIPS 2026 Datasets and Benchmarks Track}},
  year={{2026}}
}}
```

## License

CC-BY-4.0. Clinical guideline content is attributed to original
organizations and used under fair use for research. MIMIC-IV Demo
data is subject to the PhysioNet Credentialed Health Data License 1.5.0.
"""
    (dst / "README.md").write_text(card)


def main() -> None:
    """Package the dataset."""
    parser = ArgumentParser(description="Package CGA-Bench for HuggingFace")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data_release" / f"v{VERSION}",
        help="Output directory",
    )
    args = parser.parse_args()
    dst: Path = args.output_dir

    print(f"{'=' * 60}")
    print(f"CGA-Bench Dataset Packaging v{VERSION}")
    print(f"Output: {dst}")
    print(f"{'=' * 60}")

    # Clean output dir
    if dst.exists():
        print(f"\nWARNING: {dst} exists, will overwrite")
    dst.mkdir(parents=True, exist_ok=True)

    # 1. CPG Graphs
    print("\n[1/8] Copying CPG graphs...")
    n_graphs = copy_graphs(dst)
    print(f"  {n_graphs} graphs copied")

    # 2. Scenarios
    print("\n[2/8] Copying scenarios...")
    n_manual, n_auto = copy_scenarios(dst)
    print(f"  {n_manual} manual + {n_auto} auto scenario files copied")

    # 3. Constraints
    print("\n[3/8] Copying constraints export...")
    n_constraints = copy_constraints(dst)
    print(f"  {n_constraints} typed constraints")

    # 4. Gold set
    print("\n[4/8] Copying gold set...")
    gold_counts = copy_gold_set(dst)
    for name, count in sorted(gold_counts.items()):
        print(f"  {name}: {count} instances")

    # 5. RAG corpus
    print("\n[5/8] Copying RAG corpus...")
    n_rag = copy_rag_corpus(dst)
    print(f"  {n_rag} parsed guideline documents")

    # 6. Episodes
    print("\n[6/8] Copying episode results...")
    episode_counts = copy_episodes(dst)
    for model, count in sorted(episode_counts.items()):
        print(f"  {model}: {count:,} episodes")
    print(f"  Total: {sum(episode_counts.values()):,} episodes")

    # 7. Metadata files
    print("\n[7/8] Copying metadata...")
    copy_guideline_cards(dst)
    copy_license(dst)
    print("  guideline_cards.yaml + LICENSE copied")

    # 8. Checksums
    print("\n[8/8] Computing SHA-256 checksums...")
    checksums = compute_checksums(dst)
    print(f"  {len(checksums)} files checksummed")

    # Generate dataset card
    print("\nGenerating README.md dataset card...")
    generate_dataset_card(
        dst,
        n_graphs=n_graphs,
        n_manual=n_manual,
        n_auto=n_auto,
        n_constraints=n_constraints,
        gold_counts=gold_counts,
        n_rag=n_rag,
        episode_counts=episode_counts,
    )

    # Summary
    total_size = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file())
    print(f"\n{'=' * 60}")
    print("PACKAGING COMPLETE")
    print(f"{'=' * 60}")
    print(f"Output: {dst}")
    print(f"Total size: {total_size / (1024 * 1024):.1f} MB")
    print(f"Total files: {sum(1 for _ in dst.rglob('*') if _.is_file())}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
