SHELL := /bin/bash
PYTHONPATH := $(shell cd .. && pwd)
export PYTHONPATH

.PHONY: all data score experiments guideline-cards paper clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

all: data score experiments paper ## Run full reproduction pipeline

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

data: guideline-cards ## Prepare data artifacts
	@echo "=== Data preparation complete ==="

guideline-cards: ## Generate guideline cards from CPG graphs
	python ../scripts/generate_guideline_cards.py
	@echo "Guideline cards: ../evidence_pack/guideline_cards.yaml"

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

score: ## Re-generate verdict matrix from episode results
	@echo "=== Scoring ==="
	@echo "Verdict matrix regeneration requires episode results in results/full_706_v5/"
	@echo "Pre-computed verdict matrix: ../evidence_pack/analysis/verdict_matrix_v4.json"
	@if [ -d "../results/full_706_v5" ]; then \
		python ../scripts/experiments/verdict_matrix_v5.py; \
	else \
		echo "Episode results not found. Using pre-computed verdict matrix."; \
	fi

# ---------------------------------------------------------------------------
# Experiments (defense experiments E1-E5 + EX-4A/17/18/20)
# ---------------------------------------------------------------------------

experiments: exp-e1 exp-e2 exp-e3 exp-e4 exp-e5 exp-ex18 exp-heldout-ao exp-ex17 exp-ex20 exp-ex4a ## Run all defense experiments
	@echo "=== All experiments complete ==="

exp-e1: ## E1: Verdict flip sensitivity
	python ../scripts/experiments/exp_e1_verdict_flip.py

exp-e2: ## E2: Boundary stress ratio
	python ../scripts/experiments/exp_e2_bsr.py

exp-e3: ## E3: Instrumentation ablation
	python ../scripts/experiments/exp_e3_instrumentation_ablation.py

exp-e4: ## E4: Operating point analysis
	python ../scripts/experiments/exp_e4_operating_point.py

exp-e5: ## E5: Evaluator expansion
	python ../scripts/experiments/exp_e5_evaluator_expansion.py

exp-ex18: ## EX-18: Artifact mimic (TCC value-add)
	python ../scripts/experiments/exp_before_only_perturbation.py

exp-heldout-ao: ## Exp 6: Held-out all-oblivious FA
	python ../scripts/experiments/exp_heldout_ao_fa.py

exp-ex17: ## EX-17: Solver agreement (tiered vs ILP)
	python ../scripts/experiments/exp_e17_solver_agreement.py

exp-ex20: ## EX-20: No-context matched pair
	python ../scripts/experiments/exp_e20_no_context_pair.py

exp-ex4a: ## EX-4A: Clock sweep timing robustness
	python ../scripts/experiments/exp_e4a_clock_sweep.py

# ---------------------------------------------------------------------------
# Paper
# ---------------------------------------------------------------------------

paper: ## Extract auto_numbers and compile paper
	python ../scripts/experiments/extract_auto_numbers.py
	@echo "=== auto_numbers.tex updated ==="
	@if command -v pdflatex >/dev/null 2>&1; then \
		cd ../paper && pdflatex -interaction=nonstopmode main_final_v10.tex; \
		echo "Paper compiled: paper/main_final_v10.pdf"; \
	else \
		echo "pdflatex not found; skipping compilation."; \
	fi

# ---------------------------------------------------------------------------
# Episodes (GPU required)
# ---------------------------------------------------------------------------

episodes: ## Run episode generation (requires GPU + vLLM)
	@echo "=== Episode generation ==="
	@echo "This step requires GPU infrastructure with vLLM endpoints."
	@echo "Pre-computed episodes: results/full_706_v5/ (download from release)"
	@echo ""
	@echo "To run fresh:"
	@echo "  PYTHONPATH=$(PYTHONPATH) python ../scripts/experiments/full_690_runner.py <model> results/full_706_v5"
	@echo ""
	@echo "Models: oss120b, qwen35b, qwen27b, qwen4b, qwen397b, gemma31b, nemotron30b"

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

clean: ## Remove generated artifacts
	rm -rf ../evidence_pack/ex17_solver_agreement/
	rm -rf ../evidence_pack/ex20_no_context/
	rm -rf ../evidence_pack/ex4a_clock_sweep/
	rm -rf ../evidence_pack/heldout_ao_fa/
	@echo "Cleaned experiment outputs."
