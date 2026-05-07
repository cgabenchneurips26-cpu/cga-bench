#!/usr/bin/env bash
# Poll the in-flight `wget -r ... physionet.org/files/mimiciv/3.1/`
# download until the icu/ subdirectory has the four critical CSV.gz files
# (chartevents, icustays, inputevents, outputevents) so the
# MIMIC-Sepsis cohort extractor can run.
#
# Usage:
#   bash scripts/infra/wait_for_mimic_full.sh                 # block until ready
#   bash scripts/infra/wait_for_mimic_full.sh --check-only   # one-shot status

set -euo pipefail

ROOT="${1:-physionet.org/files/mimiciv/3.1}"
ICU="$ROOT/icu"
HOSP="$ROOT/hosp"
INTERVAL=${INTERVAL:-600}   # 10 minutes
CRITICAL=(chartevents.csv.gz icustays.csv.gz inputevents.csv.gz outputevents.csv.gz)

print_status() {
  local hosp_count icu_count missing
  hosp_count=$(ls "$HOSP"/*.csv.gz 2>/dev/null | wc -l)
  icu_count=$(ls "$ICU"/*.csv.gz 2>/dev/null | wc -l)
  missing=()
  for f in "${CRITICAL[@]}"; do
    [[ -f "$ICU/$f" ]] || missing+=("$f")
  done
  if (( ${#missing[@]} == 0 )); then
    echo "[ready] hosp=$hosp_count icu=$icu_count, all critical icu files present"
    return 0
  fi
  echo "[waiting] hosp=$hosp_count icu=$icu_count, missing icu/: ${missing[*]}"
  return 1
}

if [[ "${1:-}" == "--check-only" ]]; then
  print_status
  exit $?
fi

echo "Polling $ROOT every ${INTERVAL}s (CRITICAL=${CRITICAL[*]})"
until print_status; do
  sleep "$INTERVAL"
done
echo "[done] MIMIC-IV v3.1 critical icu/ files ready at $(date -u +%FT%TZ)"
