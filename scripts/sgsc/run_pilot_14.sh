#!/bin/bash
# run_pilot_14.sh — Batch runner for SGSC v7 pilot (14 CPG guidelines)
#
# Usage:
#   bash scripts/sgsc/run_pilot_14.sh --endpoint http://localhost:8013/v1
#   bash scripts/sgsc/run_pilot_14.sh --dry-run          # validate paths only
#   bash scripts/sgsc/run_pilot_14.sh --atoms-dir precomputed_atoms/  # skip LLM
#
# Reads configs/sgsc/pilot_14_registry.json for guideline definitions.
# Output lands in sgsc_output/{guideline_id}/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REGISTRY="$REPO_ROOT/configs/sgsc/pilot_14_registry.json"
OUTPUT_BASE="$REPO_ROOT/sgsc_output"

# Defaults
ENDPOINT=""
MODEL="default"
ATOMS_DIR=""
MAX_SCENARIOS=55
THRESHOLD=0.4
DRY_RUN=false
PARALLEL=4
VERBOSE=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --endpoint URL     vLLM endpoint (required unless --atoms-dir or --dry-run)
  --model NAME       Model name for endpoint (default: "default")
  --atoms-dir DIR    Directory with precomputed atoms (skip LLM step)
  --max-scenarios N  Max scenarios per guideline (default: 55)
  --threshold F      Grounding threshold (default: 0.4)
  --parallel N       Max parallel jobs (default: 4)
  --dry-run          Validate paths only, don't run pipeline
  -v, --verbose      Verbose logging
  -h, --help         Show this help
EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --endpoint)   ENDPOINT="$2"; shift 2 ;;
        --model)      MODEL="$2"; shift 2 ;;
        --atoms-dir)  ATOMS_DIR="$2"; shift 2 ;;
        --max-scenarios) MAX_SCENARIOS="$2"; shift 2 ;;
        --threshold)  THRESHOLD="$2"; shift 2 ;;
        --parallel)   PARALLEL="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=true; shift ;;
        -v|--verbose) VERBOSE="-v"; shift ;;
        -h|--help)    usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

# Validate registry exists
if [[ ! -f "$REGISTRY" ]]; then
    echo "ERROR: Registry not found: $REGISTRY"
    exit 1
fi

# Validate endpoint if not dry-run and no precomputed atoms
if [[ "$DRY_RUN" == false && -z "$ATOMS_DIR" && -z "$ENDPOINT" ]]; then
    echo "ERROR: --endpoint required (or use --atoms-dir or --dry-run)"
    exit 1
fi

echo "=== SGSC v7 Pilot Runner ==="
echo "Registry: $REGISTRY"
echo "Output:   $OUTPUT_BASE"
echo "Endpoint: ${ENDPOINT:-'(precomputed atoms)'}"
echo "Max scenarios/guideline: $MAX_SCENARIOS"
echo "Parallel jobs: $PARALLEL"
echo ""

# Extract guidelines from registry using Python
GUIDELINES=$(python3 -c "
import json
r = json.load(open('$REGISTRY'))
for g in r['guidelines']:
    print(f\"{g['guideline_id']}|{g['guideline_name']}|{g['corpus_file']}\")
")

# Validate all paths
echo "--- Validating paths ---"
ERRORS=0
while IFS='|' read -r gid gname corpus; do
    outdir="$OUTPUT_BASE/$gid"
    if [[ ! -f "$REPO_ROOT/$corpus" ]]; then
        echo "  MISSING corpus: $corpus"
        ERRORS=$((ERRORS + 1))
    fi
    if [[ ! -d "$outdir" ]]; then
        echo "  Creating output dir: $outdir"
        mkdir -p "$outdir"
    fi
    if [[ -n "$ATOMS_DIR" && ! -f "$ATOMS_DIR/${gid}_atoms.json" ]]; then
        echo "  WARNING: No precomputed atoms for $gid at $ATOMS_DIR/${gid}_atoms.json"
    fi
done <<< "$GUIDELINES"

if [[ $ERRORS -gt 0 ]]; then
    echo "ERROR: $ERRORS missing corpus files. Aborting."
    exit 1
fi

TOTAL=$(echo "$GUIDELINES" | wc -l)
echo "All $TOTAL guidelines validated."

if [[ "$DRY_RUN" == true ]]; then
    echo ""
    echo "DRY RUN complete. All paths valid. Would run $TOTAL guidelines."
    exit 0
fi

# Run pipeline for each guideline
echo ""
echo "--- Running SGSC pipeline ---"
RUNNING=0
PIDS=()
GIDS=()
FAILED=0

while IFS='|' read -r gid gname corpus; do
    outdir="$OUTPUT_BASE/$gid"
    logfile="$outdir/run.log"

    # Build command
    CMD="cd $REPO_ROOT && PYTHONPATH=. python -m sgsc.cli"
    CMD+=" --corpus $corpus"
    CMD+=" --guideline-id $gid"
    CMD+=" --guideline-name \"$gname\""
    CMD+=" --output-dir $outdir"
    CMD+=" --max-scenarios $MAX_SCENARIOS"
    CMD+=" --threshold $THRESHOLD"
    CMD+=" $VERBOSE"

    if [[ -n "$ENDPOINT" ]]; then
        CMD+=" --endpoint $ENDPOINT --model $MODEL"
    fi

    if [[ -n "$ATOMS_DIR" && -f "$ATOMS_DIR/${gid}_atoms.json" ]]; then
        CMD+=" --atoms-json $ATOMS_DIR/${gid}_atoms.json"
    fi

    echo "  Starting: $gid -> $logfile"
    eval "$CMD" > "$logfile" 2>&1 &
    PIDS+=($!)
    GIDS+=("$gid")
    RUNNING=$((RUNNING + 1))

    # Throttle parallel jobs
    if [[ $RUNNING -ge $PARALLEL ]]; then
        # Wait for any job to finish
        for i in "${!PIDS[@]}"; do
            if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
                wait "${PIDS[$i]}" || {
                    echo "  FAILED: ${GIDS[$i]} (exit $?)"
                    FAILED=$((FAILED + 1))
                }
                unset "PIDS[$i]"
                unset "GIDS[$i]"
                RUNNING=$((RUNNING - 1))
                break
            fi
        done
        # Re-index arrays
        PIDS=("${PIDS[@]}")
        GIDS=("${GIDS[@]}")

        # If still at limit, sleep and retry
        while [[ $RUNNING -ge $PARALLEL ]]; do
            sleep 2
            for i in "${!PIDS[@]}"; do
                if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
                    wait "${PIDS[$i]}" || {
                        echo "  FAILED: ${GIDS[$i]} (exit $?)"
                        FAILED=$((FAILED + 1))
                    }
                    unset "PIDS[$i]"
                    unset "GIDS[$i]"
                    RUNNING=$((RUNNING - 1))
                fi
            done
            PIDS=("${PIDS[@]}")
            GIDS=("${GIDS[@]}")
        done
    fi
done <<< "$GUIDELINES"

# Wait for remaining jobs
echo ""
echo "--- Waiting for remaining jobs ---"
for i in "${!PIDS[@]}"; do
    wait "${PIDS[$i]}" || {
        echo "  FAILED: ${GIDS[$i]} (exit $?)"
        FAILED=$((FAILED + 1))
    }
    echo "  Done: ${GIDS[$i]}"
done

echo ""
echo "=== Summary ==="
echo "Total: $TOTAL guidelines"
echo "Failed: $FAILED"

if [[ $FAILED -gt 0 ]]; then
    echo "Some guidelines failed. Check logs in sgsc_output/*/run.log"
    exit 1
fi

# Aggregate scenario counts
echo ""
echo "--- Scenario counts ---"
TOTAL_SCENARIOS=0
while IFS='|' read -r gid gname corpus; do
    outdir="$OUTPUT_BASE/$gid"
    count=$(python3 -c "
import json
from pathlib import Path
p = Path('$outdir')
for f in p.glob('*_scenarios.json'):
    if 'public' not in f.name and 'private' not in f.name:
        d = json.loads(f.read_text())
        if isinstance(d, dict):
            print(len(d))
        elif isinstance(d, list):
            print(len(d))
        break
else:
    print(0)
" 2>/dev/null || echo "0")
    TOTAL_SCENARIOS=$((TOTAL_SCENARIOS + count))
    printf "  %-35s %4s scenarios\n" "$gid" "$count"
done <<< "$GUIDELINES"

echo ""
echo "Total scenarios: $TOTAL_SCENARIOS (target: ~700)"
echo "Expected episodes: $((TOTAL_SCENARIOS * 8 * 3)) (8 models x 3 runs)"
echo "Done."
