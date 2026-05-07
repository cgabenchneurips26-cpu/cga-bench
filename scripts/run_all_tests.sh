#!/bin/bash
set -e
echo "=== Lint ===" && ruff check . || true
echo "=== Type Check ===" && mypy . --ignore-missing-imports || true
echo "=== Schema Tests ===" && PYTHONPATH=. pytest tests/test_schemas/ -q
echo "=== Engine Tests ===" && PYTHONPATH=. pytest tests/test_engine/ -q
echo "=== Assessor Tests ===" && PYTHONPATH=. pytest tests/test_assessor/ -q
echo "=== Golden Tests ===" && PYTHONPATH=. pytest tests/test_golden/ -q
echo "=== Isolation Tests ===" && PYTHONPATH=. pytest tests/test_isolation/ -q
echo "=== ALL PASSED ==="
