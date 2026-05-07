"""Check 1: ActionNormalizer idempotency verification.

Verifies normalize(normalize(x)) == normalize(x) for ALL entries
across direct mappings, domain-specific mappings, abbreviation map,
synonym groups, pattern rule outputs, and CPG allowed action sets.

Usage:
    PYTHONPATH=. python scripts/experiments/check1_normalizer_idempotency.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from cga_bench.assessor_core.action_normalizer import (
    ActionNormalizer,
    _DEFAULT_DIRECT_MAPPINGS,
    _DEFAULT_DOMAIN_SPECIFIC_MAPPINGS,
    _DEFAULT_SYNONYM_GROUPS,
    _DEFAULT_CPG_ALLOWED_ACTIONS,
)


def main() -> None:
    norm = ActionNormalizer()  # default config
    violations: list[dict[str, str]] = []
    tested: int = 0

    # --- 1. Direct mapping KEYS (input side) ---
    for raw_input, target in _DEFAULT_DIRECT_MAPPINGS.items():
        tested += 1
        n1 = norm.normalize(raw_input)
        n2 = norm.normalize(n1)
        if n1 != n2:
            violations.append({
                "source": "direct_mapping_key",
                "input": raw_input,
                "n1": n1,
                "n2": n2,
            })

    # --- 2. Direct mapping VALUES (output side — these should be fixed points) ---
    seen_values: set[str] = set()
    for target in _DEFAULT_DIRECT_MAPPINGS.values():
        if target in seen_values:
            continue
        seen_values.add(target)
        tested += 1
        n1 = norm.normalize(target)
        n2 = norm.normalize(n1)
        if n1 != n2:
            violations.append({
                "source": "direct_mapping_value",
                "input": target,
                "n1": n1,
                "n2": n2,
            })

    # --- 3. Domain-specific mapping keys and values ---
    for cpg_id, domain_map in _DEFAULT_DOMAIN_SPECIFIC_MAPPINGS.items():
        for raw_input, target in domain_map.items():
            tested += 1
            n1 = norm.normalize(raw_input, cpg_id=cpg_id)
            n2 = norm.normalize(n1, cpg_id=cpg_id)
            if n1 != n2:
                violations.append({
                    "source": f"domain_specific[{cpg_id}]_key",
                    "input": raw_input,
                    "n1": n1,
                    "n2": n2,
                })
            # Check target is also a fixed point under its own domain
            tested += 1
            t1 = norm.normalize(target, cpg_id=cpg_id)
            t2 = norm.normalize(t1, cpg_id=cpg_id)
            if t1 != t2:
                violations.append({
                    "source": f"domain_specific[{cpg_id}]_value",
                    "input": target,
                    "n1": t1,
                    "n2": t2,
                })

    # --- 4. Abbreviation map keys (as standalone input) ---
    for abbrev, expansion in ActionNormalizer.ABBREVIATION_MAP.items():
        tested += 1
        n1 = norm.normalize(abbrev)
        n2 = norm.normalize(n1)
        if n1 != n2:
            violations.append({
                "source": "abbreviation_key",
                "input": abbrev,
                "n1": n1,
                "n2": n2,
            })
        # Also test with order_ prefix
        prefixed = f"order_{abbrev}"
        tested += 1
        n1 = norm.normalize(prefixed)
        n2 = norm.normalize(n1)
        if n1 != n2:
            violations.append({
                "source": "abbreviation_prefixed",
                "input": prefixed,
                "n1": n1,
                "n2": n2,
            })

    # --- 5. Synonym group entries ---
    for canonical, synonyms in _DEFAULT_SYNONYM_GROUPS.items():
        # Check canonical is a fixed point
        tested += 1
        n1 = norm.normalize(canonical)
        n2 = norm.normalize(n1)
        if n1 != n2:
            violations.append({
                "source": "synonym_canonical",
                "input": canonical,
                "n1": n1,
                "n2": n2,
            })
        # Check each synonym
        for syn in synonyms:
            tested += 1
            n1 = norm.normalize(syn)
            n2 = norm.normalize(n1)
            if n1 != n2:
                violations.append({
                    "source": "synonym_entry",
                    "input": syn,
                    "n1": n1,
                    "n2": n2,
                })

    # --- 6. CPG allowed action sets ---
    for cpg_id, allowed in _DEFAULT_CPG_ALLOWED_ACTIONS.items():
        for action_id in allowed:
            tested += 1
            n1 = norm.normalize(action_id, cpg_id=cpg_id)
            n2 = norm.normalize(n1, cpg_id=cpg_id)
            if n1 != n2:
                violations.append({
                    "source": f"cpg_allowed[{cpg_id}]",
                    "input": action_id,
                    "n1": n1,
                    "n2": n2,
                })

    # --- Report ---
    print(f"Tested: {tested} entries")
    print(f"Violations: {len(violations)}")
    if violations:
        print("\n=== IDEMPOTENCY VIOLATIONS ===")
        for v in violations:
            print(f"  [{v['source']}] '{v['input']}' → n1='{v['n1']}' → n2='{v['n2']}'")
        sys.exit(1)
    else:
        print("PASS — normalize(normalize(x)) == normalize(x) for all entries")
        sys.exit(0)


if __name__ == "__main__":
    main()
