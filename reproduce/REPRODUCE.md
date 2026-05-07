# CGA-Bench Reproduction Guide

## Prerequisites

- Python 3.11+
- ~2 GB disk space for code and pre-computed results
- (Optional) GPU infrastructure for episode generation

## Quick Start (Docker)

```bash
# Build reproduction container
docker build -f reproduce/Dockerfile -t cga-bench-reproduce .

# Run full pipeline (score + experiments + paper)
docker run --rm -v $(pwd)/results:/app/results cga-bench-reproduce

# Run specific step
docker run --rm cga-bench-reproduce make -f reproduce/Makefile experiments
```

## Quick Start (Local)

```bash
# Install dependencies
pip install -r reproduce/requirements-reproduce.txt

# Set PYTHONPATH
export PYTHONPATH=$(pwd)

# Run all experiments
make -f reproduce/Makefile experiments

# Or individual experiments
make -f reproduce/Makefile exp-ex17    # Solver agreement
make -f reproduce/Makefile exp-ex20    # No-context matched pair
make -f reproduce/Makefile exp-ex4a    # Clock sweep
make -f reproduce/Makefile exp-heldout-ao  # Held-out AO FA
```

## Reproduction Steps

### Step 1: Data Artifacts

Pre-computed data is included in the repository:

| Artifact | Path | Description |
|----------|------|-------------|
| CPG Graphs | `cpg_model/graphs/*.yaml` | 25 clinical guideline graphs (20 core + 5 held-out) |
| Scenarios | `configs/scenarios/*.yaml` | 690 clinical scenarios |
| Guideline Cards | `evidence_pack/guideline_cards.yaml` | Constraint summaries |
| Croissant Metadata | `croissant.json` | MLCommons dataset metadata |

To regenerate guideline cards:
```bash
make -f reproduce/Makefile guideline-cards
```

### Step 2: Episode Generation (GPU Required)

Episode generation requires GPU infrastructure with vLLM endpoints serving the target models. Pre-computed episodes are available in `results/full_706_v5/`.

```bash
# Example: run a single model
PYTHONPATH=$(pwd) python scripts/experiments/full_690_runner.py oss120b results/full_706_v5

# Available models: oss120b, qwen35b, qwen27b, qwen4b, qwen397b, gemma31b, nemotron30b
# Each model: 706 scenarios x 3 runs = 2,118 episodes
# Total: 7 models x 2,118 = 14,826 raw episodes (14,055 after 3-run completeness filter)
```

### Step 3: Scoring

Generate the verdict matrix from episode results:
```bash
make -f reproduce/Makefile score
```

This produces `evidence_pack/analysis/verdict_matrix_v4.json` containing per-episode verdicts from all evaluators.

### Step 4: Defense Experiments

All experiments read from `verdict_matrix_v4.json` and produce JSON + Markdown outputs in `evidence_pack/`.

| Experiment | Script | Output | Attack Closed |
|-----------|--------|--------|---------------|
| E1 Verdict Flip | `exp_e1_verdict_flip.py` | `evidence_pack/exp_e1_verdict_flip/` | #2 |
| E2 BSR | `exp_e2_bsr.py` | `evidence_pack/exp_e2_bsr/` | #3 |
| E3 Ablation | `exp_e3_instrumentation_ablation.py` | `evidence_pack/exp_e3_ablation/` | #7 |
| E4 Operating Point | `exp_e4_operating_point.py` | `evidence_pack/exp_e4_operating_point/` | #8 |
| E5 Evaluator Expansion | `exp_e5_evaluator_expansion.py` | `evidence_pack/exp_e5_evaluator_expansion/` | #9 |
| EX-18 Artifact Mimic | `exp_before_only_perturbation.py` | `evidence_pack/exp_ex18_mimic/` | #12 |
| Exp 6 Held-out AO FA | `exp_heldout_ao_fa.py` | `evidence_pack/heldout_ao_fa/` | #18 |
| EX-17 Solver Agreement | `exp_e17_solver_agreement.py` | `evidence_pack/ex17_solver_agreement/` | #4 |
| EX-20 No-Context Pair | `exp_e20_no_context_pair.py` | `evidence_pack/ex20_no_context/` | #16 |
| EX-4A Clock Sweep | `exp_e4a_clock_sweep.py` | `evidence_pack/ex4a_clock_sweep/` | #11 |

Run all:
```bash
make -f reproduce/Makefile experiments
```

### Step 5: Paper Compilation

```bash
make -f reproduce/Makefile paper
```

This extracts `auto_numbers.tex` macros from experiment outputs and compiles the LaTeX paper.

## Verification

```bash
# Verify zero undefined macros
grep -c '{?' paper/auto_numbers.tex  # expect: 0

# Verify all evidence files exist
ls evidence_pack/ex17_solver_agreement/ex17_solver_agreement.json
ls evidence_pack/ex20_no_context/ex20_no_context.json
ls evidence_pack/ex4a_clock_sweep/ex4a_clock_sweep.json
ls evidence_pack/heldout_ao_fa/heldout_ao_fa.json

# Verify paper compiles
cd paper && pdflatex -interaction=nonstopmode main_final_v10.tex 2>&1 | grep -c "Undefined"
# expect: 0
```

## Dataset Metadata

MLCommons Croissant metadata is provided at `croissant.json` for standardized dataset discovery and loading.

## License

See repository LICENSE file.
