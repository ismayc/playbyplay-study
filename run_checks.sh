#!/bin/bash
# Every check in this repo: unit tests, then the study's reconciliation /
# validation gate. Non-zero exit on any failure. PY overrides the
# interpreter (the family orchestrator sets it to a shared venv).
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}

echo "=== unit tests: Python (pytest) ==="
$PY -m pytest tests/python -q

echo
echo "=== unit tests: R (testthat) ==="
Rscript tests/R/run_tests.R

echo
echo "=== reconciliation / validation ==="
$PY python/04_reconcile.py | tail -1

echo
echo "=== team/quarter extension: offline gate replay ==="
$PY python/06_team_quarter.py --check | tail -1
