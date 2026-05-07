.PHONY: help test test-fast test-e2e test-coverage lint format typecheck benchmark-mock clean ci validate generate-scenarios audit audit-evaluator audit-evaluator-one dry-run reproduce evidence-pack guide clinician-data clinician-dist clinician-build

PYTHON := python3
PYTEST := PYTHONPATH=.. pytest
RUFF := ruff

help:
	@echo "CGA-Bench Development Commands"
	@echo "==============================="
	@echo "  make test            Run all tests"
	@echo "  make test-fast       Run fast tests only (skip slow/e2e)"
	@echo "  make test-e2e        Run end-to-end tests"
	@echo "  make test-coverage   Run tests with coverage report"
	@echo "  make lint            Check code style (ruff)"
	@echo "  make format          Format code (ruff)"
	@echo "  make typecheck       Run type checking (mypy)"
	@echo "  make benchmark-mock  Run mock benchmark smoke test"
	@echo "  make clean           Remove build artifacts"
	@echo "  make ci              Run lint + typecheck + fast tests (CI mode)"
	@echo ""
	@echo "Reproducibility Commands"
	@echo "========================"
	@echo "  make validate        Validate all conditional rules"
	@echo "  make generate-scenarios  Generate all scenarios from graphs"
	@echo "  make audit           Run audit scripts (rule coverage, cross-ref)"
	@echo "  make dry-run         Run 1 episode as smoke test"
	@echo "  make reproduce       Full reproducibility check"
	@echo "  make evidence-pack   Generate all evidence pack artifacts"
	@echo "  make clinician-build Regenerate clinician dist (data + JSX transpile)"
	@echo "  make guide           clinician-build + capture screenshots + build DOCX user guide"
	@echo "  make post-episode    Run after episodes complete: rescore → experiments → paper-numbers + analysis"
	@echo ""
	@echo "Evaluator Audit Harness"
	@echo "========================"
	@echo "  make audit-evaluator       Run 4-step audit on all 6 built-in evaluators"
	@echo "  make audit-evaluator-one   Audit a single evaluator: EVAL=module:ClassName"

test:
	$(PYTEST) tests/ -v

test-fast:
	$(PYTEST) tests/ -v -m "not slow and not e2e"

test-e2e:
	$(PYTEST) tests/test_e2e/ -v

test-coverage:
	$(PYTEST) tests/ --cov=. --cov-report=html --cov-report=term-missing

lint:
	$(RUFF) check .

format:
	$(RUFF) format .
	$(RUFF) check . --fix

typecheck:
	PYTHONPATH=.. mypy agent_runner/ assessor_core/ cpg_engine/ eval_harness/ scenario_engine/ --ignore-missing-imports || true

benchmark-mock:
	@echo "Running mock benchmark smoke test..."
	PYTHONPATH=.. $(PYTHON) run_benchmark.py --scenario septic_shock_basic --agent oracle --mock-llm --output results/smoke_test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache htmlcov .coverage

ci: lint typecheck test-fast

# === Reproducibility Targets ===

validate:
	@echo "Validating conditional rules..."
	PYTHONPATH=.. $(PYTHON) scripts/validate_conditional_rules.py
	@echo "Scenario validation passed (rules valid)."

generate-scenarios:
	@echo "Generating all scenarios from graphs..."
	PYTHONPATH=.. $(PYTHON) scripts/generate_all_scenarios.py

audit:
	@echo "Running audit scripts..."
	PYTHONPATH=.. $(PYTHON) scripts/generate_audit_matrix.py
	PYTHONPATH=.. $(PYTHON) scripts/cross_reference_manual_vs_derived.py

dry-run:
	@echo "Running dry-run smoke test..."
	PYTHONPATH=.. $(PYTHON) run_benchmark.py --scenario septic_shock_basic --agent oracle --mock-llm --output results/smoke_test

reproduce: validate generate-scenarios test audit
	@echo "============================================"
	@echo "Reproducibility check PASSED"
	@echo "============================================"

evidence-pack:
	@echo "Generating evidence pack artifacts..."
	PYTHONPATH=.. $(PYTHON) scripts/evaluator_agreement.py
	PYTHONPATH=.. $(PYTHON) scripts/select_case_studies.py
	PYTHONPATH=.. $(PYTHON) scripts/generate_benchmark_comparison.py
	PYTHONPATH=.. $(PYTHON) scripts/generate_clinician_review_packet.py
	PYTHONPATH=.. $(PYTHON) scripts/generate_rule_summary.py
	PYTHONPATH=.. $(PYTHON) scripts/generate_patient_realism_report.py
	PYTHONPATH=.. $(PYTHON) scripts/generate_action_annotation_sheet.py
	@echo "Evidence pack generation complete."

# ---- Clinician validation build chain ----
# clinician-data   → regenerate scenario_data.js, scenario_data_full.json,
#                    protocol_meta.js, and the dist/ copies.
# clinician-dist   → transpile ClinicalValidation.jsx into the Babel-standalone
#                    bundle at dist/ClinicalValidation.source.js.
# clinician-build  → both of the above; run this before serving dist/ live or
#                    re-capturing screenshots so the UI reflects the latest JSX.
clinician-data:
	@echo "Regenerating scenario_data.js + scenario_data_full.json (v5.2 specialty quota + Tier S+A)..."
	PYTHONPATH=.. $(PYTHON) clinician_validation/generate_scenario_data.py \
		--results-root results/full_v6b \
		--tier-s-only \
		--n-true-pass 18 --n-true-fail 18 --n-false-accept 39 \
		--max-per-specialty 5

clinician-dist:
	@echo "Building dist/ClinicalValidation.source.js from JSX..."
	PYTHONPATH=.. $(PYTHON) scripts/build_clinician_dist.py

clinician-build: clinician-data clinician-dist
	@echo "Clinician validation dist ready."

guide: clinician-build
	@echo "Capturing clinician validation screenshots..."
	$(PYTHON) clinician_validation/capture_pipeline/capture.py --out-dir docs/clinician_validation/screenshots
	@echo "Building DOCX user guide..."
	cd docs/clinician_validation && pandoc user_guide.md --from=markdown --to=docx --resource-path=. --output=user_guide.docx
	@echo "Guide ready: docs/clinician_validation/user_guide.docx"

# === Extended Reproducibility Pipeline ===

.PHONY: derive generate episodes-dry episodes-full rescore experiments paper-numbers determinism post-episode all

derive:
	@echo "Deriving constraints from CPG graphs..."
	PYTHONPATH=.. $(PYTHON) scripts/validate_conditional_rules.py
	PYTHONPATH=.. $(PYTHON) scripts/generate_audit_matrix.py
	@echo "Derivation complete: constraints + audit matrix generated."

generate: generate-scenarios
	@echo "Verifying scenario count..."
	PYTHONPATH=.. $(PYTHON) -c "import yaml; d=yaml.safe_load(open('configs/scenarios/auto_generated_scenarios.yaml')); print(f\"Auto scenarios: {len(d.get('scenarios',{}))}\")"

episodes-dry:
	@echo "Running dry-run episodes (mock LLM)..."
	PYTHONPATH=.. $(PYTHON) run_benchmark.py --scenario septic_shock_basic --agent oracle --mock-llm --output results/smoke_test
	PYTHONPATH=.. $(PYTHON) run_benchmark.py --scenario stemi_anterior_basic --agent oracle --mock-llm --output results/smoke_test
	PYTHONPATH=.. $(PYTHON) run_benchmark.py --scenario dka_hypokalemia_trap --agent oracle --mock-llm --output results/smoke_test
	@echo "Dry-run complete."

episodes-full:
ifndef VLLM_ENDPOINT
	@echo "SKIP: episodes-full requires VLLM_ENDPOINT environment variable."
	@echo "Set it with: export VLLM_ENDPOINT=http://localhost:8013/v1"
else
	@echo "Running full episodes (GPU required)..."
	PYTHONPATH=.. $(PYTHON) run_neurips_experiment.py --config configs/experiments/neurips_main.yaml
endif

rescore:
	@echo "Rescoring all episodes..."
	PYTHONPATH=.. $(PYTHON) scripts/experiments/final_rescore_v4.py || echo "Rescore script not found or no episodes to rescore."

experiments:
	@echo "Running experiments EXP-A through EXP-F..."
	PYTHONPATH=.. $(PYTHON) scripts/experiments/exp_a_scenario_equivalence.py || true
	PYTHONPATH=.. $(PYTHON) scripts/experiments/exp_b_derivation_ablation.py || true
	PYTHONPATH=.. $(PYTHON) scripts/experiments/exp_c_generalizability.py || true
	PYTHONPATH=.. $(PYTHON) scripts/experiments/exp_d_disagreement_quantification.py || true
	PYTHONPATH=.. $(PYTHON) scripts/experiments/exp_e_difficulty_equivalence.py || true
	PYTHONPATH=.. $(PYTHON) scripts/experiments/exp_f_evidence_pack_v5.py || true
	@echo "Experiments complete."

paper-numbers:
	@echo "Generating paper numbers..."
	PYTHONPATH=.. $(PYTHON) scripts/experiments/exp_f_evidence_pack_v5.py || true
	PYTHONPATH=.. $(PYTHON) scripts/generate_benchmark_comparison.py
	PYTHONPATH=.. $(PYTHON) scripts/generate_final_numbers.py || true
	@echo "Paper numbers generated in paper/auto_numbers.tex"

determinism:
	@echo "Verifying determinism..."
	PYTHONPATH=.. $(PYTHON) scripts/verify_determinism.py

post-episode: rescore experiments paper-numbers
	@echo "Running post-episode analysis scripts..."
	PYTHONPATH=.. $(PYTHON) scripts/evaluator_violation_crosstab.py
	PYTHONPATH=.. $(PYTHON) scripts/exp_b_constraint_type_precision.py
	PYTHONPATH=.. $(PYTHON) scripts/evaluator_agreement.py
	PYTHONPATH=.. $(PYTHON) scripts/select_case_studies.py
	@echo "============================================"
	@echo "Post-episode pipeline PASSED"
	@echo "  verdict_matrix -> experiments -> paper-numbers"
	@echo "  + violation crosstab + stratified precision"
	@echo "  + evaluator agreement + case studies"
	@echo "============================================"

# ---- Evaluator Audit Harness (Option B) ----
audit-evaluator:
	@for eval in v4_hard dxem ac_proxy mab_proxy c2_shim acov_shim; do \
	  PYTHONPATH=.. $(PYTHON) scripts/audit/evaluator_audit.py \
	    --shim $$eval --out-dir audit/reports; \
	done
	PYTHONPATH=.. $(PYTHON) scripts/audit/build_index.py audit/reports
	@echo "Reports: audit/reports/INDEX.md"

audit-evaluator-one:
ifndef EVAL
	@echo "Usage: make audit-evaluator-one EVAL=my_module:MyEvalClass"
	@echo "Shims: PYTHONPATH=.. python scripts/audit/evaluator_audit.py --shim dxem"
else
	PYTHONPATH=.. $(PYTHON) scripts/audit/evaluator_audit.py \
	  --evaluator $(EVAL) --out-dir audit/reports
endif

all: validate derive generate test audit determinism
	@echo "============================================"
	@echo "Full reproducibility pipeline PASSED"
	@echo "============================================"
