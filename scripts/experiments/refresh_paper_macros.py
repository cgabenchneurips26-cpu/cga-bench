"""Reusable paper-macro refresh tool.

Refreshes the LaTeX `\\providecommand` / `\\newcommand` block in
`paper/auto_numbers.tex` with values computed from a verdict-matrix JSON.

Why this exists
---------------
The CGA-Bench paper uses dozens of macros (\\strictFAThree,
\\consensusFACritical, \\bsrDSPct, \\hlAllMAB, ...) that must agree
exactly with the data in `evidence_pack/analysis/verdict_matrix_*.json`.
Hand-editing these macros after a corpus change is error-prone (Phase B
to Phase A migration that motivated this tool revealed five separate
inconsistencies; see docs/critical_review/v18_consistency_audit_20260429.md).

This script encapsulates every "macro <- formula(corpus)" rule in a
single registry so:
  1. Re-running the script after any corpus change refreshes everything.
  2. Adding a new macro means adding one entry to `MACRO_REGISTRY`.
  3. Verification piggybacks on the same registry: --verify-only prints
     differences without writing.

Usage
-----
    # Refresh paper/auto_numbers.tex (v6 / v18 mirrors are kept in sync):
    PYTHONPATH=. python scripts/experiments/refresh_paper_macros.py

    # Or override paths / dry-run / verify-only:
    PYTHONPATH=. python scripts/experiments/refresh_paper_macros.py \\
        --verdict-matrix evidence_pack/analysis/verdict_matrix_v6.json \\
        --auto-numbers paper/auto_numbers.tex \\
        --dry-run

    # Verify only — exits non-zero if any macro disagrees with the data:
    PYTHONPATH=. python scripts/experiments/refresh_paper_macros.py --verify-only

    # Force a different corpus subset (e.g., 8-model Phase B):
    PYTHONPATH=. python scripts/experiments/refresh_paper_macros.py \\
        --verdict-matrix evidence_pack/analysis/verdict_matrix_v6_full.json \\
        --label phase_b_full

Adding a new macro
------------------
1. Compute the value once interactively from `verdict_matrix.json`.
2. Append a new `MacroSpec` to `MACRO_REGISTRY` with a closure that
   reads the cleanly-aggregated `Corpus` object.
3. Re-run the script. The macro will appear in `auto_numbers.tex`
   either as an in-place replacement (if already declared) or
   as an appended `\\providecommand`.

Conventions
-----------
* Pass-rates / FA rates are reported as percentages with one decimal.
* Counts are formatted with thousands separators using `19{,}062`
  (the LaTeX-friendly form auto_numbers.tex already uses).
* The script never deletes macros it does not own; existing entries are
  only overwritten when their name appears in `MACRO_REGISTRY`.

DUPLICATE WRITER WARNING (added 2026-04-30 after N5 systemic audit)
-------------------------------------------------------------------
A second script — `scripts/experiments/compute_table26_bsr_per_model.py` —
also writes a SUBSET of macros to `paper/auto_numbers.tex` that overlaps
with this script's output. Specifically, both emit `\\nonTimingForbiddenOnly`
and several other `nonTiming*`/`strictFA*` macros. When ONLY one writer is
modified, the file lands in whichever state was written last, and CI
`--verify-only` catches end-state divergence from `verdict_matrix_v6.json`
but does NOT enforce that the two writers stay in sync with each other.
Both writers had the COMMISSION→FORBIDDEN bug (Step D fixed this script,
Step F fixed the other). v1.2 cleanup: consolidate into a single registry-
based generator and retire `compute_table26_bsr_per_model.py`.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import statistics
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_VERDICT = REPO_ROOT / "evidence_pack/analysis/verdict_matrix_v6.json"
DEFAULT_AUTO_MAIN = REPO_ROOT / "paper/auto_numbers.tex"
DEFAULT_MIRRORS = (
    REPO_ROOT / "paper/auto_numbers_v6.tex",
    REPO_ROOT / "paper/auto_numbers_v18.tex",
)
DEFAULT_EVIDENCE_OUT = REPO_ROOT / "evidence_pack/analysis/per_model_bsr_v6.json"

# Mapping from `model_dir` (key in verdict_matrix.json) to the macro stem
# used in paper/auto_numbers*.tex. New models: append here; new macros
# referencing them: append to MACRO_REGISTRY.
MODEL_TO_STEM: dict[str, str] = {
    "deepseek_r1_7b": "DS",
    "qwen4b": "Qfour",
    "qwen27b": "Qtwentyseven",
    "qwen35b": "Qthirtyfive",
    "nemotron30b": "Nemo",
    "gemma31b": "Gemma",
    "llama4scout": "LlamaFour",
    "oss120b": "OSS",
    "qwen397b": "Qthreenine",
}


# ---------------------------------------------------------------------------
# Corpus aggregation
# ---------------------------------------------------------------------------


@dataclass
class ModelStats:
    n: int = 0
    ac_pass: int = 0
    mab_pass: int = 0
    c2_pass: int = 0
    dxem_pass: int = 0
    tcc_pass: int = 0  # NOT v4_hard
    ac_pass_and_tcc_fail: int = 0


@dataclass
class Corpus:
    """Aggregated quantities used by every MacroSpec computation."""

    per_episode: list[dict[str, Any]]
    per_model: dict[str, ModelStats] = field(default_factory=dict)
    total: ModelStats = field(default_factory=ModelStats)

    n_dxem_pass: int = 0
    n_ac_pass: int = 0
    n_c2_pass: int = 0
    n_mab_pass: int = 0
    n_cga_pass: int = 0
    n_v4_hard: int = 0

    fa_dxem: int = 0
    fa_ac: int = 0
    fa_c2: int = 0
    fa_mab: int = 0

    nviols_when_ac_pass: list[int] = field(default_factory=list)
    nviols_when_c2_pass: list[int] = field(default_factory=list)
    nviols_when_mab_pass: list[int] = field(default_factory=list)
    nviols_when_dxem_pass: list[int] = field(default_factory=list)

    n_loose_fa: int = 0  # ASC and CwT and v4_hard
    n_loose_fa_critical: int = 0  # loose FA and v4_crit
    n_strict_fa: int = 0  # ASC and CwT and PAF and v4_hard
    n_strict_fa_critical: int = 0  # strict FA and v4_crit
    nviols_loose: list[int] = field(default_factory=list)

    n_within_only: int = 0
    n_non_timing_natural: int = 0
    n_non_timing_forbid_only: int = 0
    n_non_timing_before_only: int = 0
    n_disagree_any: int = 0


_VALID_VIOL_TYPES = frozenset({"WITHIN", "FORBIDDEN", "BEFORE"})


def aggregate(per_episode: list[dict[str, Any]]) -> Corpus:
    """Walk the verdict matrix once and accumulate everything we need."""
    c = Corpus(per_episode=per_episode)

    # Schema-drift guard (added 2026-04-30 after N5 audit).
    # The consumer logic in this loop compares viol_types against literal
    # uppercase tokens {WITHIN, FORBIDDEN, BEFORE}. If a future verdict_matrix
    # schema introduces new tokens (e.g., OMISSION, CONFLICT), they would be
    # silently dropped by every consumer condition — same failure mode as the
    # COMMISSION/FORBIDDEN bug fixed in commit d5ada272. Fail loud instead.
    seen_types: set[str] = {t for ep in per_episode for t in (ep.get("viol_types") or [])}
    unknown = seen_types - _VALID_VIOL_TYPES
    if unknown:
        raise RuntimeError(
            f"Schema drift in verdict_matrix viol_types: unknown tokens {sorted(unknown)}. "
            f"Expected vocabulary {sorted(_VALID_VIOL_TYPES)}. "
            f"Update consumer literals or extend _VALID_VIOL_TYPES before re-running."
        )

    for ep in per_episode:
        m = ep["model_dir"]
        s = c.per_model.setdefault(m, ModelStats())
        ac = bool(ep.get("ac_proxy"))
        mab = bool(ep.get("mab_proxy"))
        c2 = bool(ep.get("c2_pass"))
        dxem = bool(ep.get("dxem"))
        hard = bool(ep.get("v4_hard"))
        crit = bool(ep.get("v4_crit"))
        cga = not hard
        nv = int(ep.get("n_viols", 0))
        types = set(ep.get("viol_types") or [])

        # Per-model counters
        s.n += 1
        s.ac_pass += int(ac)
        s.mab_pass += int(mab)
        s.c2_pass += int(c2)
        s.dxem_pass += int(dxem)
        if cga:
            s.tcc_pass += 1
        if ac and hard:
            s.ac_pass_and_tcc_fail += 1

        # Corpus-wide counters
        c.n_dxem_pass += int(dxem)
        c.n_ac_pass += int(ac)
        c.n_c2_pass += int(c2)
        c.n_mab_pass += int(mab)
        c.n_cga_pass += int(cga)
        c.n_v4_hard += int(hard)
        if dxem and hard:
            c.fa_dxem += 1
            c.nviols_when_dxem_pass.append(nv)
        if ac and hard:
            c.fa_ac += 1
            c.nviols_when_ac_pass.append(nv)
        if c2 and hard:
            c.fa_c2 += 1
            c.nviols_when_c2_pass.append(nv)
        if mab and hard:
            c.fa_mab += 1
            c.nviols_when_mab_pass.append(nv)
        if ac and c2 and hard:
            c.n_loose_fa += 1
            c.nviols_loose.append(nv)
            if crit:
                c.n_loose_fa_critical += 1
            if mab:
                c.n_strict_fa += 1
                if crit:
                    c.n_strict_fa_critical += 1
        if hard and types:
            if types == {"WITHIN"}:
                c.n_within_only += 1
            if "WITHIN" not in types:
                c.n_non_timing_natural += 1
                if types == {"FORBIDDEN"}:
                    c.n_non_timing_forbid_only += 1
                if types == {"BEFORE"}:
                    c.n_non_timing_before_only += 1
        verdicts = (dxem, ac, c2, mab, cga)
        if not (all(verdicts) or not any(verdicts)):
            c.n_disagree_any += 1

    # Aggregate totals
    for s in c.per_model.values():
        for fld in (
            "n",
            "ac_pass",
            "mab_pass",
            "c2_pass",
            "dxem_pass",
            "tcc_pass",
            "ac_pass_and_tcc_fail",
        ):
            setattr(c.total, fld, getattr(c.total, fld) + getattr(s, fld))
    return c


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def fmt_pct(num: int, den: int, decimals: int = 1) -> str:
    if den == 0:
        return f"{0.0:.{decimals}f}"
    return f"{(num / den) * 100:.{decimals}f}"


def fmt_count_latex(n: int) -> str:
    """LaTeX-friendly thousand-separator: 19062 -> '19{,}062'."""
    s = f"{n:,}"
    return s.replace(",", "{,}")


def fmt_signed_pct(num: int, den: int, decimals: int = 1) -> str:
    pct = (num / den) * 100 if den else 0.0
    return f"{pct:+.{decimals}f}"


def median_or_zero(xs: list[int]) -> str:
    return f"{statistics.median(xs):.1f}" if xs else "0"


# ---------------------------------------------------------------------------
# Macro registry
# ---------------------------------------------------------------------------


@dataclass
class MacroSpec:
    """One macro and how to compute its value from a Corpus."""

    name: str
    compute: Callable[[Corpus], str]
    description: str
    category: str  # "corpus", "bsr", "headline", "evaluator", "consensus", "subtype"


def _build_per_model_specs() -> list[MacroSpec]:
    out: list[MacroSpec] = []
    for model_dir, stem in MODEL_TO_STEM.items():
        # Per-model BSR: ASC-pass count, TCC-fail-within-ASC-pass count, BSR%
        out.extend(
            [
                MacroSpec(
                    name=f"bsr{stem}N",
                    compute=lambda c, m=model_dir: fmt_count_latex(c.per_model[m].ac_pass),
                    description=f"BSR table: ASC-pass count for {model_dir}",
                    category="bsr",
                ),
                MacroSpec(
                    name=f"bsr{stem}Fail",
                    compute=lambda c, m=model_dir: fmt_count_latex(c.per_model[m].ac_pass_and_tcc_fail),
                    description=f"BSR table: TCC-fail within ASC-pass for {model_dir}",
                    category="bsr",
                ),
                MacroSpec(
                    name=f"bsr{stem}Pct",
                    compute=lambda c, m=model_dir: fmt_pct(c.per_model[m].ac_pass_and_tcc_fail, c.per_model[m].ac_pass),
                    description=f"BSR table: BSR% for {model_dir}",
                    category="bsr",
                ),
                # Per-model headline replay: MAB / AC / TCC pass-rate, Δ(MAB-TCC)
                MacroSpec(
                    name=f"hl{stem}MAB",
                    compute=lambda c, m=model_dir: fmt_pct(c.per_model[m].mab_pass, c.per_model[m].n),
                    description=f"Headline replay: MAB pass-rate for {model_dir}",
                    category="headline",
                ),
                MacroSpec(
                    name=f"hl{stem}AC",
                    compute=lambda c, m=model_dir: fmt_pct(c.per_model[m].ac_pass, c.per_model[m].n),
                    description=f"Headline replay: AC pass-rate for {model_dir}",
                    category="headline",
                ),
                MacroSpec(
                    name=f"hl{stem}TCC",
                    compute=lambda c, m=model_dir: fmt_pct(c.per_model[m].tcc_pass, c.per_model[m].n),
                    description=f"Headline replay: TCC pass-rate for {model_dir}",
                    category="headline",
                ),
                MacroSpec(
                    name=f"hl{stem}Delta",
                    compute=lambda c, m=model_dir: fmt_signed_pct(
                        c.per_model[m].mab_pass - c.per_model[m].tcc_pass,
                        c.per_model[m].n,
                    ),
                    description=f"Headline replay: Δ(MAB-TCC) pp for {model_dir}",
                    category="headline",
                ),
            ]
        )
    return out


def _build_overall_specs() -> list[MacroSpec]:
    return [
        MacroSpec(
            name="bsrAllN",
            compute=lambda c: fmt_count_latex(c.total.ac_pass),
            description="BSR table: Overall ASC-pass count",
            category="bsr",
        ),
        MacroSpec(
            name="bsrAllFail",
            compute=lambda c: fmt_count_latex(c.total.ac_pass_and_tcc_fail),
            description="BSR table: Overall TCC-fail within ASC-pass",
            category="bsr",
        ),
        MacroSpec(
            name="bsrAllPct",
            compute=lambda c: fmt_pct(c.total.ac_pass_and_tcc_fail, c.total.ac_pass),
            description="BSR table: Overall BSR%",
            category="bsr",
        ),
        MacroSpec(
            name="hlAllMAB",
            compute=lambda c: fmt_pct(c.total.mab_pass, c.total.n),
            description="Headline replay: Overall MAB pass-rate",
            category="headline",
        ),
        MacroSpec(
            name="hlAllAC",
            compute=lambda c: fmt_pct(c.total.ac_pass, c.total.n),
            description="Headline replay: Overall AC pass-rate",
            category="headline",
        ),
        MacroSpec(
            name="hlAllTCC",
            compute=lambda c: fmt_pct(c.total.tcc_pass, c.total.n),
            description="Headline replay: Overall TCC pass-rate",
            category="headline",
        ),
        MacroSpec(
            name="hlAllDelta",
            compute=lambda c: fmt_signed_pct(c.total.mab_pass - c.total.tcc_pass, c.total.n),
            description="Headline replay: Overall Δ(MAB-TCC) pp (aggregate)",
            category="headline",
        ),
        MacroSpec(
            name="hlMacroAvgDelta",
            compute=lambda c: (
                f"{sum(((s.mab_pass / s.n - s.tcc_pass / s.n) * 100) for s in c.per_model.values()) / len(c.per_model):+.1f}"
                if c.per_model
                else "+0.0"
            ),
            description="Headline replay: macro-averaged per-model Δ(MAB-TCC) pp",
            category="headline",
        ),
        MacroSpec(
            name="hlNumModelsMABgtTCC",
            compute=lambda c: str(sum(1 for s in c.per_model.values() if s.mab_pass > s.tcc_pass)),
            description="Headline replay: count of models where MAB pass-rate > TCC pass-rate",
            category="headline",
        ),
    ]


def _build_corpus_specs() -> list[MacroSpec]:
    return [
        MacroSpec(
            name="numEpisodes",
            compute=lambda c: fmt_count_latex(c.total.n),
            description="Headline corpus size: number of model-run trajectories",
            category="corpus",
        ),
    ]


def _build_evaluator_row_specs() -> list[MacroSpec]:
    """Table 1 (Evaluator performance) row macros."""
    rows = [
        ("DxEM", "passrateDxEM", "n_dxem_pass", "fa_dxem", "nviols_when_dxem_pass"),
        ("AC", "passtrateACProxy", "n_ac_pass", "fa_ac", "nviols_when_ac_pass"),
        ("CTwo", "passrateCTwo", "n_c2_pass", "fa_c2", "nviols_when_c2_pass"),
        ("MAB", "passtrateMABProxy", "n_mab_pass", "fa_mab", "nviols_when_mab_pass"),
    ]
    out: list[MacroSpec] = []
    for stem, pass_macro, pass_attr, fa_attr, nviols_attr in rows:
        out.append(
            MacroSpec(
                name=pass_macro,
                compute=lambda c, a=pass_attr: fmt_pct(getattr(c, a), c.total.n),
                description=f"Evaluator-row Pass% for {stem}",
                category="evaluator",
            )
        )
        out.append(
            MacroSpec(
                name=f"bsr{stem}",
                compute=lambda c, a=fa_attr: fmt_pct(getattr(c, a), c.total.n),
                description=f"Evaluator-row FA% for {stem}",
                category="evaluator",
            )
        )
        out.append(
            MacroSpec(
                name=f"bsrCond{stem}",
                compute=lambda c, fa=fa_attr, p=pass_attr: fmt_pct(getattr(c, fa), getattr(c, p)),
                description=f"Evaluator-row conditional FA% (FA | pass) for {stem}",
                category="evaluator",
            )
        )
        out.append(
            MacroSpec(
                name=f"bsrN{stem}",
                compute=lambda c, fa=fa_attr: fmt_count_latex(getattr(c, fa)),
                description=f"Evaluator-row FA count for {stem}",
                category="evaluator",
            )
        )
        out.append(
            MacroSpec(
                name=f"medDg{stem}",
                compute=lambda c, n=nviols_attr: median_or_zero(getattr(c, n)),
                description=f"Evaluator-row median d_G surrogate (n_viols) for {stem}",
                category="evaluator",
            )
        )
    out.append(
        MacroSpec(
            name="passrateCGABench",
            compute=lambda c: fmt_pct(c.n_cga_pass, c.total.n),
            description="Evaluator-row Pass% for TCC (CGA-Bench)",
            category="evaluator",
        )
    )
    return out


def _build_consensus_specs() -> list[MacroSpec]:
    return [
        MacroSpec(
            name="strictFAThree",
            compute=lambda c: fmt_pct(c.n_strict_fa, c.total.n, decimals=2),
            description="Strict 3-way consensus FA%: ASC and PAF and CwT and v4_hard",
            category="consensus",
        ),
        MacroSpec(
            name="strictFAThreeCount",
            compute=lambda c: fmt_count_latex(c.n_strict_fa),
            description="Strict 3-way consensus FA count",
            category="consensus",
        ),
        MacroSpec(
            name="faAllOblivious",
            compute=lambda c: fmt_pct(c.n_loose_fa, c.total.n),
            description="Loose consensus (ASC and CwT and v4_hard) FA%",
            category="consensus",
        ),
        MacroSpec(
            name="faAllObliviousCount",
            compute=lambda c: fmt_count_latex(c.n_loose_fa),
            description="Loose consensus FA count",
            category="consensus",
        ),
        # Historical "consensusFA*" macros refer to the LOOSE 2-way consensus
        # (ASC ∩ CwT) — this is what the v5 paper's 22.1% critical claim
        # was computed against (see docs/critical_review/v18_consistency_audit_*).
        # Strict 3-way critical decomposition is reported separately.
        MacroSpec(
            name="consensusFATotal",
            compute=lambda c: fmt_count_latex(c.n_loose_fa),
            description="Loose 2-way consensus FA count (ASC ∩ CwT ∧ v4_hard)",
            category="consensus",
        ),
        MacroSpec(
            name="consensusFARate",
            compute=lambda c: fmt_pct(c.n_loose_fa, c.total.n, decimals=2),
            description="Loose 2-way consensus FA rate (% of all trajectories)",
            category="consensus",
        ),
        MacroSpec(
            name="consensusFACritical",
            compute=lambda c: fmt_count_latex(c.n_loose_fa_critical),
            description="Loose consensus FA count whose v4_crit=True",
            category="consensus",
        ),
        MacroSpec(
            name="consensusFACriticalPct",
            compute=lambda c: fmt_pct(c.n_loose_fa_critical, c.n_loose_fa, decimals=2),
            description="% of loose consensus FA that are catalogue-critical",
            category="consensus",
        ),
        MacroSpec(
            name="consensusFACritFracTotal",
            compute=lambda c: fmt_pct(c.n_loose_fa_critical, c.total.n, decimals=2),
            description="Loose consensus critical FA as % of all trajectories",
            category="consensus",
        ),
        MacroSpec(
            name="strictFACritical",
            compute=lambda c: fmt_count_latex(c.n_strict_fa_critical),
            description="Strict 3-way consensus FA count whose v4_crit=True",
            category="consensus",
        ),
        MacroSpec(
            name="strictFACriticalPct",
            compute=lambda c: fmt_pct(c.n_strict_fa_critical, c.n_strict_fa, decimals=2),
            description="% of strict 3-way consensus FA that are catalogue-critical",
            category="consensus",
        ),
        MacroSpec(
            name="strictFACritFracTotal",
            compute=lambda c: fmt_pct(c.n_strict_fa_critical, c.total.n, decimals=2),
            description="Strict consensus critical FA as % of all trajectories",
            category="consensus",
        ),
        MacroSpec(
            name="verdictFlipRate",
            compute=lambda c: fmt_pct(c.n_disagree_any, c.total.n),
            description="% trajectories with at least one evaluator-pair pass/fail flip",
            category="consensus",
        ),
        MacroSpec(
            name="medianViolFalseAccept",
            compute=lambda c: f"{int(statistics.median(c.nviols_loose))}" if c.nviols_loose else "0",
            description="Median n_viols among loose-consensus FA",
            category="consensus",
        ),
    ]


def _build_subtype_specs() -> list[MacroSpec]:
    return [
        MacroSpec(
            name="faWithinOnlyN",
            compute=lambda c: fmt_count_latex(c.n_within_only),
            description="Hard-violating trajectories where viol_types == {WITHIN}",
            category="subtype",
        ),
        MacroSpec(
            name="withinOnlyRate",
            compute=lambda c: fmt_pct(c.n_within_only, c.total.n),
            description="Within-only fraction of all trajectories",
            category="subtype",
        ),
        MacroSpec(
            name="nonTimingNaturalCount",
            compute=lambda c: fmt_count_latex(c.n_non_timing_natural),
            description="Hard-violating trajectories without WITHIN type",
            category="subtype",
        ),
        MacroSpec(
            name="nonTimingForbiddenOnly",
            compute=lambda c: fmt_count_latex(c.n_non_timing_forbid_only),
            description="Trajectories with viol_types == {FORBIDDEN} only",
            category="subtype",
        ),
        MacroSpec(
            name="nonTimingBeforeOnly",
            compute=lambda c: fmt_count_latex(c.n_non_timing_before_only),
            description="Trajectories with viol_types == {BEFORE} only",
            category="subtype",
        ),
    ]


MACRO_REGISTRY: list[MacroSpec] = (
    _build_corpus_specs()
    + _build_per_model_specs()
    + _build_overall_specs()
    + _build_evaluator_row_specs()
    + _build_consensus_specs()
    + _build_subtype_specs()
)


# ---------------------------------------------------------------------------
# Patcher
# ---------------------------------------------------------------------------


def patch_auto_numbers(
    path: Path,
    macros: dict[str, str],
    *,
    comment_tag: str,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Replace existing \\(new|provide)command{\\<name>}{...} for any name in
    `macros`; append remaining names as \\providecommand at end of file.
    Uses a balanced-brace parser so values like '19{,}062' don't get
    truncated by a naive regex.
    """
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    written: set[str] = set()
    name_re = re.compile(r"^(\\(?:new|provide)command)\{\\([A-Za-z]+)\}")
    for i, line in enumerate(lines):
        m = name_re.match(line)
        if not m:
            continue
        name = m.group(2)
        if name not in macros or name in written:
            continue
        rest = line[m.end() :]
        if not rest.startswith("{"):
            continue
        depth = 0
        end_idx = -1
        for j, ch in enumerate(rest):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_idx = j
                    break
        if end_idx < 0:
            continue
        tail = rest[end_idx + 1 :]
        cmd = m.group(1)
        new_line = f"{cmd}{{\\{name}}}{{{macros[name]}}}{tail}"
        if not new_line.endswith("\n"):
            new_line += "\n"
        lines[i] = new_line
        written.add(name)
    missing = [n for n in macros if n not in written]
    if missing:
        if not lines or not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append(f"% --- {comment_tag} ---\n")
        for name in missing:
            lines.append(f"\\providecommand{{\\{name}}}{{{macros[name]}}}\n")

    if dry_run:
        return len(written), len(missing)
    path.write_text("".join(lines))
    return len(written), len(missing)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def parse_macros_from_tex(path: Path) -> dict[str, str]:
    text = path.read_text()
    out: dict[str, str] = {}
    name_re = re.compile(r"\\(?:new|provide)command\{\\([A-Za-z]+)\}")
    for line in text.splitlines():
        m = name_re.search(line)
        if not m:
            continue
        name = m.group(1)
        rest = line[m.end() :]
        if not rest.startswith("{"):
            continue
        depth = 0
        end_idx = -1
        for j, ch in enumerate(rest):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_idx = j
                    break
        if end_idx >= 0:
            out[name] = rest[1:end_idx]
    return out


def _normalize(value: str) -> str:
    """Treat '1{,}062' and '1,062' as equal (both render identically in LaTeX)."""
    return value.replace("{", "").replace("}", "").replace(",", "").strip()


def verify(corpus: Corpus, auto_numbers_path: Path) -> tuple[int, int]:
    declared = parse_macros_from_tex(auto_numbers_path)
    expected = {spec.name: spec.compute(corpus) for spec in MACRO_REGISTRY}
    n_ok = n_diff = 0
    print(f"\nVerifying {auto_numbers_path.relative_to(REPO_ROOT)} against verdict matrix:")
    for name, want in expected.items():
        got = declared.get(name)
        if got is None:
            print(f"  [MISS] {name:<30s}  expected={want}  (not declared)")
            n_diff += 1
        elif _normalize(got) == _normalize(want):
            n_ok += 1
        else:
            print(f"  [DIFF] {name:<30s}  expected={want}  found={got}")
            n_diff += 1
    print(f"  -> {n_ok} match, {n_diff} differ")
    return n_ok, n_diff


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--verdict-matrix",
        type=Path,
        default=DEFAULT_VERDICT,
        help=f"Path to verdict matrix JSON (default: {DEFAULT_VERDICT.relative_to(REPO_ROOT)})",
    )
    p.add_argument(
        "--auto-numbers",
        type=Path,
        default=DEFAULT_AUTO_MAIN,
        help=f"Path to paper auto_numbers.tex (default: {DEFAULT_AUTO_MAIN.relative_to(REPO_ROOT)})",
    )
    p.add_argument(
        "--mirror",
        type=Path,
        action="append",
        default=list(DEFAULT_MIRRORS),
        help="Additional auto_numbers files to update with the same values (repeatable; default: v6/v18 mirrors)",
    )
    p.add_argument(
        "--evidence-out",
        type=Path,
        default=DEFAULT_EVIDENCE_OUT,
        help="JSON file to write computed values + per-model stats",
    )
    p.add_argument("--label", type=str, default="phase_a_9m_19062", help="Tag included in the appended comment block")
    p.add_argument("--dry-run", action="store_true", help="Compute and print, but do not write files")
    p.add_argument(
        "--verify-only",
        action="store_true",
        help="Compare current auto_numbers.tex with verdict-matrix data; exit 1 if any disagreement",
    )
    p.add_argument(
        "--filter-category",
        choices=["corpus", "bsr", "headline", "evaluator", "consensus", "subtype"],
        help="Only refresh macros in the given category (others left alone)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    matrix = json.loads(args.verdict_matrix.read_text())
    pe = matrix["per_episode"]
    print(f"Loaded {len(pe)} per-episode entries from {args.verdict_matrix.relative_to(REPO_ROOT)}")
    print(f"Models: {sorted(matrix.get('metadata', {}).get('models', {}).keys())}")
    corpus = aggregate(pe)

    specs = MACRO_REGISTRY
    if args.filter_category:
        specs = [s for s in specs if s.category == args.filter_category]
        print(f"Filtering to category={args.filter_category}: {len(specs)} macros")
    macros = {s.name: s.compute(corpus) for s in specs}

    if args.verify_only:
        n_ok, n_diff = verify(corpus, args.auto_numbers)
        for mirror in args.mirror:
            if mirror.exists():
                verify(corpus, mirror)
        sys.exit(0 if n_diff == 0 else 1)

    print(f"\nComputed {len(macros)} macros from corpus.")
    print("Sample (first 8 across categories):")
    seen_cats: set[str] = set()
    for spec in specs:
        if spec.category in seen_cats:
            continue
        seen_cats.add(spec.category)
        print(f"  [{spec.category:<10s}] \\{spec.name:<28s} = {macros[spec.name]:<10s}  ({spec.description})")

    n_main, app_main = patch_auto_numbers(
        args.auto_numbers,
        macros,
        comment_tag=f"refreshed by refresh_paper_macros.py [{args.label}]",
        dry_run=args.dry_run,
    )
    print(
        f"\n{args.auto_numbers.relative_to(REPO_ROOT)}: "
        f"{n_main} replaced, {app_main} appended"
        f"{'  (dry-run; no write)' if args.dry_run else ''}"
    )
    for mirror in args.mirror:
        if not mirror.exists():
            continue
        n, app = patch_auto_numbers(
            mirror,
            macros,
            comment_tag=f"mirror of {args.auto_numbers.name} [{args.label}]",
            dry_run=args.dry_run,
        )
        print(f"{mirror.relative_to(REPO_ROOT)}: {n} replaced, {app} appended{'  (dry-run)' if args.dry_run else ''}")

    if not args.dry_run:
        args.evidence_out.write_text(
            json.dumps(
                {
                    "verdict_matrix": str(args.verdict_matrix.relative_to(REPO_ROOT)),
                    "label": args.label,
                    "metadata": matrix.get("metadata", {}),
                    "macros": macros,
                    "per_model_stats": {
                        k: {
                            f: getattr(v, f)
                            for f in (
                                "n",
                                "ac_pass",
                                "mab_pass",
                                "c2_pass",
                                "dxem_pass",
                                "tcc_pass",
                                "ac_pass_and_tcc_fail",
                            )
                        }
                        for k, v in corpus.per_model.items()
                    },
                    "total": {
                        f: getattr(corpus.total, f)
                        for f in (
                            "n",
                            "ac_pass",
                            "mab_pass",
                            "c2_pass",
                            "dxem_pass",
                            "tcc_pass",
                            "ac_pass_and_tcc_fail",
                        )
                    },
                    "categories": sorted({s.category for s in MACRO_REGISTRY}),
                },
                indent=2,
            )
        )
        print(f"Wrote evidence: {args.evidence_out.relative_to(REPO_ROOT)}")

    n_ok, n_diff = verify(corpus, args.auto_numbers)
    if n_diff:
        print(f"\nWARNING: {n_diff} macro(s) still differ from data.")
        sys.exit(1)
    print(f"\nAll {n_ok} macros match data. Done.")


if __name__ == "__main__":
    main()
