#!/usr/bin/env python3
"""Generate auto_numbers_audit.csv — Category A/B/C label per macro.

Phase 0.F deliverable: parse all TeX macro files, extract every
\\newcommand and \\providecommand, classify each as:

  Category A — Independent of verdicts (corpus size, graph count, etc.)
  Category B — Verdict-dependent, must recompute in Phase 2/3
  Category C — Borderline (thresholds, projection defs, bootstrap config)

Output: auto_numbers_audit.csv with columns:
  macro_name, file, category, recompute_phase, notes
"""

from __future__ import annotations

import csv
from pathlib import Path
import re

# ---------------------------------------------------------------------------
# Keyword sets for classification heuristics
# ---------------------------------------------------------------------------

# Category B keywords: verdict-dependent numbers
B_KEYWORDS: set[str] = {
    # Verdict / evaluator names
    "bsr",
    "fa",
    "flip",
    "verdict",
    "pass",
    "blind",
    "detect",
    "kappa",
    "fleiss",
    "kendall",
    "friedman",
    "reversal",
    "eta",
    "anova",
    "wilcoxon",
    "cochran",
    # Evaluator-specific
    "dxem",
    "acproxy",
    "mabproxy",
    "ctwo",
    "cga",
    "acov",
    "tcc",
    "paf",
    "asc",
    "cwt",
    "tom",
    # Metrics
    "spearman",
    "rho",
    "cohen",
    "jaccard",
    "silhouette",
    "cophenetic",
    "ari",
    "entropy",
    # Experiment result types
    "consensus",
    "strict",
    "severity",
    "critical",
    "ablation",
    "instr",
    "clock",
    "timing",
    # Score / rate / count suffixes
    "rate",
    "pct",
    "count",
    "delta",
    "gap",
    "loss",
    "gain",
    "median",
    "mean",
    "ci",
    "lo",
    "hi",
    # Cross-benchmark / replay
    "cross",
    "replay",
    "native",
    "fidelity",
    # Audit harness
    "audit",
    "shim",
    "ensemble",
    "piclass",
    "witness",
    "bayes",
    "floor",
    "projection",
    # CRES experiments
    "cres",
    "auc",
    "feature",
    "cliff",
    "vpc",
    # Solver
    "solver",
    "ilp",
    "tiered",
    # LLM judge
    "judge",
    "gemma",
    "term",
    # Held-out
    "heldout",
    # W8 scaffold
    "scaffold",
    "weight",
    "prompt",
    # GEE
    "gee",
    "or",
    # AMEGA
    "amega",
    # Per-model
    "model",
    # Normalizer
    "normalizer",
    # Option Z
    "repl",
    "dual",
    "catalogue",
    # Tier S
    "tier",
}

# Category A keywords: independent of verdicts
A_KEYWORDS: set[str] = {
    "numgraphs",
    "numdomains",
    "numnodes",
    "numscenarios",
    "numtotalscenarios",
    "nummanualscenarios",
    "numautoscenarios",
    "numconditionalrules",
    "numcombocandidates",
    "numforbidden",
    "nummust",
    "numshould",
    "numbefore",
    "numwithin",
    "numshouldwithin",
    "numhardconstraints",
    "numsoftconstraints",
    "numtotalconstraints",
    "numextra",
    "leakagescan",
    "timestep",
    "oraclecode",
    "overgen",
    "expansion",
    "avg",
    "mimicprotocol",
    "distcheck",
    # Engine structure
    "auditngraphs",
    "audittotalrules",
    "auditunique",
    "auditconstraints",
    "auditdead",
    "auditduplicate",
    "auditunreachable",
    "auditgraphs",
    "auditprovenance",
    "auditcontradictory",
    # Constraint comparison structure
    "pertype",
    "cde",
    "methodclass",
}

# Category C keywords: borderline (thresholds, config, framework params)
C_KEYWORDS: set[str] = {
    "threshold",
    "nbootstrap",
    "seed",
    "config",
    "nummodels",
    "numruns",
    "numevaluators",
    "numscaffolds",
    "numepisodes",
    "numaudit",  # audit infra counts
    "kit",
    "cpgselection",
    "candidatepool",
    "spotcheck",
}

# Exact macro overrides (take precedence over keyword matching)
CATEGORY_OVERRIDES: dict[str, str] = {
    # System-level constants → A
    r"\numMainGraphs": "A",
    r"\numHoldoutGraphs": "A",
    r"\numGraphsMain": "A",
    r"\numGraphsHeldout": "A",
    r"\numGraphsTotal": "A",
    r"\numTotalScenarios": "A",
    r"\numDomains": "A",
    r"\numNodes": "A",
    r"\timeStepMinutes": "A",
    r"\numConditionalRules": "A",
    r"\numComboCandidates": "A",
    r"\surveyNBenchmarks": "A",
    r"\surveyNOthers": "A",
    r"\constraintDensityP": "A",
    r"\enginePrecision": "A",
    r"\engineRecall": "A",
    # Corpus params → C (depends on corpus version decision)
    r"\numModels": "C",
    r"\numRuns": "C",
    r"\numEvaluators": "C",
    r"\numEvaluatorsAll": "C",
    r"\numEpisodes": "C",
    r"\numScaffolds": "C",
    # Constraint structure → A
    r"\numForbidden": "A",
    r"\numMust": "A",
    r"\numBefore": "A",
    r"\numWithin": "A",
    r"\numHardConstraints": "A",
    r"\numSoftConstraints": "A",
    r"\numTotalConstraints": "A",
    # Audit kit infra → C
    r"\numAuditShims": "C",
    r"\numAuditTests": "C",
    r"\numAuditTestFiles": "C",
    r"\kitSixSteps": "C",
    # Engine audit structure → A
    r"\auditNGraphs": "A",
    r"\auditTotalRules": "A",
    r"\auditUniqueActions": "A",
    r"\auditDeadNodes": "A",
    r"\auditDuplicates": "A",
    r"\auditUnreachableNodes": "A",
    r"\auditUnreachableRate": "A",
    r"\auditContradictoryRate": "A",
    r"\auditProvenanceComplete": "A",
    r"\auditConstraintsPerNode": "A",
    r"\auditGraphsWithUnreachable": "A",
    r"\auditDeadRate": "A",
    r"\auditDuplicateRate": "A",
    # Selection criteria → A (graph-structure metadata)
    r"\numCandidatePool": "A",
    r"\cpgSelectionCriteriaCount": "A",
    # Artifact-mimic detection loss → B (verdict-dependent, from exp_e23)
    # Without override, "mimic" substring matches A_KEYWORDS "mimicprotocol"
    r"\mimicACDetectionLoss": "B",
    r"\mimicMABDetectionLoss": "B",
    r"\mimicHBDetectionLoss": "B",
}

# Phase mapping for category B
PHASE_MAP: dict[str, str] = {
    "bsr": "Phase 2",
    "fa": "Phase 3",
    "flip": "Phase 3",
    "verdict": "Phase 2",
    "pass": "Phase 2",
    "kappa": "Phase 3",
    "eta": "Phase 3",
    "anova": "Phase 3",
    "consensus": "Phase 3",
    "solver": "Phase 3",
    "judge": "Phase 4",
    "replay": "Phase 3",
    "cres": "Phase 3",
    "heldout": "Phase 4",
    "scaffold": "Phase 3",
    "amega": "Phase 4",
    "audit": "Phase 3",
    "bayes": "Phase 3",
    "tier": "Phase 3",
}

# ---------------------------------------------------------------------------
# TeX macro extraction
# ---------------------------------------------------------------------------

MACRO_RE = re.compile(r"\\(?:new|provide)command\{(\\[A-Za-z]+)\}\{([^}]*)\}")
COMMENTED_RE = re.compile(r"^%\s*COMMENTED-OUT.*\\(?:new|provide)command\{(\\[A-Za-z]+)\}")


def extract_macros(tex_path: Path) -> list[dict[str, str]]:
    """Extract all macro definitions from a .tex file."""
    macros: list[dict[str, str]] = []
    with open(tex_path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            # Skip pure comments (but check for COMMENTED-OUT macros)
            cm = COMMENTED_RE.match(stripped)
            if cm:
                macros.append(
                    {
                        "macro_name": cm.group(1),
                        "value": "(commented-out)",
                        "file": str(tex_path),
                        "commented": "yes",
                    }
                )
                continue
            if stripped.startswith("%"):
                continue
            m = MACRO_RE.search(stripped)
            if m:
                macros.append(
                    {
                        "macro_name": m.group(1),
                        "value": m.group(2),
                        "file": str(tex_path),
                        "commented": "no",
                    }
                )
    return macros


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_macro(name: str, value: str, filepath: str) -> tuple[str, str, str]:
    """Classify a macro as A/B/C and assign recompute phase + notes.

    Returns:
        (category, recompute_phase, notes)
    """
    # Check exact overrides first
    if name in CATEGORY_OVERRIDES:
        cat = CATEGORY_OVERRIDES[name]
        phase = "" if cat != "B" else "Phase 2"
        note = "override" if cat != "C" else "corpus/config parameter"
        return cat, phase, note

    lower = name.lstrip("\\").lower()

    # Check A keywords (structural/system constants)
    for kw in A_KEYWORDS:
        if kw in lower:
            return "A", "", "system/structural constant"

    # Check C keywords (borderline)
    for kw in C_KEYWORDS:
        if kw in lower:
            return "C", "", "config/threshold parameter"

    # Check B keywords (verdict-dependent)
    for kw in B_KEYWORDS:
        if kw in lower:
            # Find recompute phase
            phase = "Phase 3"
            for pk, pv in PHASE_MAP.items():
                if pk in lower:
                    phase = pv
                    break
            return "B", phase, f"verdict-dependent ({kw})"

    # Placeholder macros (value is "--")
    if value.strip() == "--":
        return "B", "Phase 3", "placeholder (pending computation)"

    # Default: B (conservative — assume verdict-dependent unless proven otherwise)
    return "B", "Phase 3", "default (unclassified)"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Generate auto_numbers_audit.csv."""
    root = Path(__file__).resolve().parents[2]  # cga_bench/

    # Collect all macro files
    tex_files: list[Path] = []

    auto_numbers = root / "paper" / "auto_numbers.tex"
    if auto_numbers.exists():
        tex_files.append(auto_numbers)

    # evidence_pack/**/*_macros.tex
    ep_dir = root / "evidence_pack"
    if ep_dir.exists():
        tex_files.extend(sorted(ep_dir.rglob("*_macros.tex")))

    # Extract all macros
    all_macros: list[dict[str, str]] = []
    for tf in tex_files:
        rel = tf.relative_to(root)
        for macro in extract_macros(tf):
            macro["file"] = str(rel)
            all_macros.append(macro)

    # Classify
    rows: list[dict[str, str]] = []
    for macro in all_macros:
        cat, phase, notes = classify_macro(
            macro["macro_name"],
            macro["value"],
            macro["file"],
        )
        if macro.get("commented") == "yes":
            notes = f"commented-out; {notes}"
        rows.append(
            {
                "macro_name": macro["macro_name"],
                "file": macro["file"],
                "value": macro["value"][:60],  # truncate long values
                "category": cat,
                "recompute_phase": phase,
                "notes": notes,
            }
        )

    # Write CSV
    out_path = root / "auto_numbers_audit.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "macro_name",
                "file",
                "value",
                "category",
                "recompute_phase",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    counts = {"A": 0, "B": 0, "C": 0}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    total = len(rows)

    print(f"Wrote {out_path} ({total} macros)")
    print(f"  Category A (independent):       {counts.get('A', 0)}")
    print(f"  Category B (verdict-dependent):  {counts.get('B', 0)}")
    print(f"  Category C (borderline):         {counts.get('C', 0)}")

    # Also print file distribution
    from collections import Counter

    file_counts = Counter(r["file"] for r in rows)
    print(f"\nFiles scanned: {len(file_counts)}")
    for fp, cnt in file_counts.most_common(5):
        print(f"  {fp}: {cnt} macros")


if __name__ == "__main__":
    main()
