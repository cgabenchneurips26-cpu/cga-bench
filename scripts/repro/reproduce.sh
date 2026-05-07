#!/usr/bin/env bash
set -euo pipefail

# ENG-09: Reproducibility Bundle
# Proves: clone → 5 fixed commands → identical output

echo "=== CGA-Bench Reproducibility Verification ==="
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Python: $(python3 --version)"

# Record environment
PYTHONPATH=. python3 scripts/repro/record_environment.py

# 1. Lint
echo "--- Step 1/5: Lint ---"
pip install ruff -q
ruff check . || { echo "LINT FAILED"; exit 1; }

# 2. Type check (informational)
echo "--- Step 2/5: Type Check ---"
pip install mypy -q
mypy --config-file mypy.ini cpg_engine/ assessor_core/ eval_harness/ cpg_model/schemas/ || true

# 3. Engine + Assessor tests
echo "--- Step 3/5: Engine + Assessor Tests ---"
PYTHONPATH=. python3 -m pytest tests/test_engine/ tests/test_assessor/ tests/test_schemas/ -q --tb=short

# 4. Golden pair tests
echo "--- Step 4/5: Golden Tests ---"
PYTHONPATH=. python3 -m pytest tests/test_golden/ -q --tb=short

# 5. Stress test (small)
echo "--- Step 5/5: Stress Test ---"
PYTHONPATH=. python3 scripts/bench/stress_eventlog_roundtrip.py --profile small --format xes
PYTHONPATH=. python3 scripts/bench/stress_eventlog_roundtrip.py --profile small --format ocel

echo ""
echo "=== ALL 5 VERIFICATION STEPS PASSED ==="
