#!/bin/bash
# Every check in this repo: unit tests, then the study's reconciliation /
# validation gates. Non-zero exit on any failure. PY overrides the
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
echo "=== reconciliation: R vs Python, every league-season and pooled ==="
$PY python/04_reconcile.py --all --pooled | tail -1

echo
echo "=== team/quarter extension: offline gate replay, every league-season ==="
for pair in nba:2023-24 nba:2024-25 nba:2025-26 wnba:2024 wnba:2025 wnba:2026; do
  $PY python/06_team_quarter.py --league "${pair%%:*}" --season "${pair#*:}" --check | tail -1
done

echo
echo "=== possessions: pbpstats builds vs the bulk archive ==="
$PY python/08_reconcile_possessions.py | tail -1

echo
echo "=== sources: window points vs the NBA liveData feed ==="
$PY python/10_check_sources.py --check | tail -1

echo
echo "=== seasons: cross-season table and pooled estimates reproduce ==="
$PY python/09_seasons.py --check | tail -1

echo
echo "=== correction: published vs corrected table reproduces ==="
$PY python/11_correction.py --check | tail -1

echo
echo "=== diagrams: every explainer SVG rebuilds identically ==="
$PY -I python/12_diagrams.py --check | tail -1

echo
echo "=== findings: README numbers regenerate from outputs ==="
$PY python/03_findings.py --check | tail -1
