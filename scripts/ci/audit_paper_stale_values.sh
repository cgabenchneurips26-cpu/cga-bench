#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PAPER="$ROOT/paper"
ACTIVE_TEX=(
    "$PAPER/main_final_v18.tex"
    "$PAPER/appendix_v18.tex"
    "$PAPER/auto_numbers.tex"
)

fail_count=0

check_pattern() {
    local label="$1"
    local pattern="$2"
    for f in "${ACTIVE_TEX[@]}"; do
        [ -f "$f" ] || continue
        # Strip comment-only lines (first non-whitespace char is '%'), then grep
        matches=$(awk '!/^[[:space:]]*%/' "$f" | grep -nE "$pattern" || true)
        if [ -n "$matches" ]; then
            # Apply whitelist: skip lines that are self-disclaimed
            filtered=$(echo "$matches" | grep -vE "Phase A 8m|demo|legacy" || true)
            if [ -n "$filtered" ]; then
                echo "FAIL [$label] in $(basename "$f"):"
                echo "$filtered"
                fail_count=$((fail_count + 1))
            fi
        fi
    done
}

# Pattern 1: 1258 as standalone number or formatted as 1{,}258
check_pattern "1258" '(^|[^0-9])1258([^0-9]|$)|1\{,\}258'

# Pattern 2: Old v5 EX-30 prose using wrong episode count + context
check_pattern "354_strict_consensus" '354 episodes that pass strict consensus'

# Pattern 3: 904 as standalone number (old MUST-only count from v5 8m)
check_pattern "904" '(^|[^0-9])904([^0-9]|$)'

# Pattern 4: 72.0 — old AC-blind% on EX-30 v5 (now 69.1)
check_pattern "72.0" '(^|[^0-9])72\.0([^0-9]|$)'

# Pattern 5: 52.0 — old MAB-blind% on EX-30 v5 (now 45.4)
check_pattern "52.0" '(^|[^0-9])52\.0([^0-9]|$)'

# Pattern 6: Old prose corrected to "ordering or contraindication"
check_pattern "old_prose" 'violating timing, ordering, or contraindication'

if [ "$fail_count" -gt 0 ]; then
    echo
    echo "audit_paper_stale_values.sh: $fail_count pattern(s) failed"
    exit 1
fi

echo "audit_paper_stale_values.sh: all patterns clean"
exit 0
