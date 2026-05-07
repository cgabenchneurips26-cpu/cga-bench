"""Comprehensive recomputation + injection of paper-headline macros against
the Phase A 9-model 19,062-episode corpus (paper/auto_numbers.tex).

Source of truth: evidence_pack/analysis/verdict_matrix_v6.json
Paper version targeted: v18 (canonical); v6 mirror kept in sync.

Macros recomputed from scratch:

  Corpus:
    \\numEpisodes, \\numModels

  Per-model BSR table (App.):
    \\bsr<Stem>N, \\bsr<Stem>Fail, \\bsr<Stem>Pct  (DS, Qfour, Qtwentyseven,
      Qthirtyfive, Nemo, Gemma, LlamaFour, OSS, Qthreenine)
    \\bsrAllN, \\bsrAllFail, \\bsrAllPct

  Headline replay table (Main \\S5):
    \\hl<Stem>{MAB,AC,TCC,Delta}    (same nine stems + All)

  Main-body false-accept claims:
    \\strictFAThree, \\strictFAThreeCount  (ASC ∩ MAB ∩ CwT ∧ v4_hard)
    \\faAllOblivious, \\faAllObliviousCount (ASC ∩ CwT ∧ v4_hard)
    \\consensusFACritical, \\consensusFACriticalPct
    \\verdictFlipRate                       (any-pair pass/fail flip)
    \\medianViolFalseAccept                 (median n_viols among consensus FA)

  Evaluator performance row (Table 1):
    \\passrateDxEM,    \\bsrDxEM,    \\bsrCondDxEM,    \\bsrNDxEM,    \\medDgDxEM
    \\passtrateACProxy,\\bsrAC,      \\bsrCondAC,      \\bsrNAC,      \\medDgAC
    \\passrateCTwo,    \\bsrCTwo,    \\bsrCondCTwo,    \\bsrNCTwo,    \\medDgCTwo
    \\passtrateMABProxy,\\bsrMAB,    \\bsrCondMAB,     \\bsrNMAB,     \\medDgMAB
    \\passrateCGABench

The script writes verbose pass/fail to stdout, replaces matching
\\newcommand / \\providecommand lines in paper/auto_numbers.tex, appends new
macros that don't yet have a definition, and mirrors all values into
paper/auto_numbers_v6.tex and paper/auto_numbers_v18.tex for backup.

DUPLICATE WRITER WARNING (added 2026-04-30 after N5 systemic audit)
-------------------------------------------------------------------
A second script — `scripts/experiments/refresh_paper_macros.py` — also
writes a SUBSET of macros to `paper/auto_numbers.tex` that overlaps with
this script's output. Specifically, both emit `\\nonTimingForbiddenOnly`
and several other `nonTiming*`/`strictFA*` macros. When ONLY one writer
is modified, the file lands in whichever state was written last, and CI
`--verify-only` catches end-state divergence from `verdict_matrix_v6.json`
but does NOT enforce that the two writers stay in sync with each other.
Both writers had the COMMISSION→FORBIDDEN bug (refresh_paper_macros.py
fixed in commit d5ada272; this script fixed in Step F, line 209).
v1.2 cleanup: consolidate into a single registry-based generator and
retire this script.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import statistics
from typing import Any

REPO = Path(__file__).resolve().parents[2]
VERDICT = REPO / "evidence_pack/analysis/verdict_matrix_v6.json"
AUTO_MAIN = REPO / "paper/auto_numbers.tex"
AUTO_V6 = REPO / "paper/auto_numbers_v6.tex"
AUTO_V18 = REPO / "paper/auto_numbers_v18.tex"
EVIDENCE_OUT = REPO / "evidence_pack/analysis/per_model_bsr_v6.json"

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


@dataclass
class ModelStats:
    n: int = 0
    ac_pass: int = 0
    mab_pass: int = 0
    c2_pass: int = 0
    dxem_pass: int = 0
    tcc_pass: int = 0  # NOT v4_hard
    ac_pass_and_tcc_fail: int = 0


def aggregate_model_stats(per_episode: list[dict[str, Any]]) -> dict[str, ModelStats]:
    out: dict[str, ModelStats] = {}
    for ep in per_episode:
        s = out.setdefault(ep["model_dir"], ModelStats())
        s.n += 1
        s.ac_pass += int(bool(ep.get("ac_proxy")))
        s.mab_pass += int(bool(ep.get("mab_proxy")))
        s.c2_pass += int(bool(ep.get("c2_pass")))
        s.dxem_pass += int(bool(ep.get("dxem")))
        if not bool(ep.get("v4_hard")):
            s.tcc_pass += 1
        if bool(ep.get("ac_proxy")) and bool(ep.get("v4_hard")):
            s.ac_pass_and_tcc_fail += 1
    return out


def fmt_pct(numer: int, denom: int, decimals: int = 1) -> str:
    if denom == 0:
        return f"{0.0:.{decimals}f}"
    return f"{(numer / denom) * 100:.{decimals}f}"


def fmt_int(n: int) -> str:
    return f"{n:,}"


def emit_per_model_macros(stats: dict[str, ModelStats]) -> dict[str, str]:
    macros: dict[str, str] = {}
    total = ModelStats()
    for model_dir, stem in MODEL_TO_STEM.items():
        s = stats[model_dir]
        macros[f"bsr{stem}N"] = fmt_int(s.ac_pass)
        macros[f"bsr{stem}Fail"] = fmt_int(s.ac_pass_and_tcc_fail)
        macros[f"bsr{stem}Pct"] = fmt_pct(s.ac_pass_and_tcc_fail, s.ac_pass)
        macros[f"hl{stem}MAB"] = fmt_pct(s.mab_pass, s.n)
        macros[f"hl{stem}AC"] = fmt_pct(s.ac_pass, s.n)
        macros[f"hl{stem}TCC"] = fmt_pct(s.tcc_pass, s.n)
        delta = (s.mab_pass / s.n - s.tcc_pass / s.n) * 100 if s.n else 0.0
        macros[f"hl{stem}Delta"] = f"{delta:+.1f}"
        for fld in ("n", "ac_pass", "mab_pass", "c2_pass", "dxem_pass", "tcc_pass", "ac_pass_and_tcc_fail"):
            setattr(total, fld, getattr(total, fld) + getattr(s, fld))
    macros["bsrAllN"] = fmt_int(total.ac_pass)
    macros["bsrAllFail"] = fmt_int(total.ac_pass_and_tcc_fail)
    macros["bsrAllPct"] = fmt_pct(total.ac_pass_and_tcc_fail, total.ac_pass)
    macros["hlAllMAB"] = fmt_pct(total.mab_pass, total.n)
    macros["hlAllAC"] = fmt_pct(total.ac_pass, total.n)
    macros["hlAllTCC"] = fmt_pct(total.tcc_pass, total.n)
    delta_all = (total.mab_pass / total.n - total.tcc_pass / total.n) * 100 if total.n else 0.0
    macros["hlAllDelta"] = f"{delta_all:+.1f}"
    return macros, total


def emit_main_body_macros(per_episode: list[dict[str, Any]], total: ModelStats) -> dict[str, str]:
    macros: dict[str, str] = {}
    n = total.n
    macros["numEpisodes"] = f"{n:,}".replace(",", "{,}")
    macros["numModels"] = "9"

    # --- Per-evaluator pass / FA / cond-FA / median d_G ---
    n_dxem_pass = 0
    n_ac_pass = 0
    n_c2_pass = 0
    n_mab_pass = 0
    n_cga_pass = 0  # TCC pass = NOT v4_hard
    n_v4_hard = 0

    fa_dxem = fa_ac = fa_c2 = fa_mab = 0
    nviols_when_dxem_pass: list[int] = []
    nviols_when_ac_pass: list[int] = []
    nviols_when_c2_pass: list[int] = []
    nviols_when_mab_pass: list[int] = []

    n_loose_fa = 0  # ASC AND CwT AND v4_hard
    n_strict_fa = 0  # ASC AND PAF AND CwT AND v4_hard
    n_strict_fa_critical = 0
    nviols_loose: list[int] = []

    n_within_only = 0
    n_non_timing_natural = 0
    n_non_timing_forbid_only = 0
    n_non_timing_before_only = 0

    n_disagree_any = 0  # any-pair pass/fail flip among the 5 evaluators

    # Schema-drift guard (added 2026-04-30 after N5 audit).
    # Consumer logic below filters viol_types using literal uppercase tokens
    # {WITHIN, FORBIDDEN, BEFORE}. Any new schema token (e.g. OMISSION, CONFLICT)
    # would be silently dropped — same failure mode as the original COMMISSION
    # bug fixed at line 209. Fail loud instead.
    _valid_viol_types = frozenset({"WITHIN", "FORBIDDEN", "BEFORE"})
    seen_types = {t for ep in per_episode for t in (ep.get("viol_types") or [])}
    unknown = seen_types - _valid_viol_types
    if unknown:
        raise RuntimeError(
            f"Schema drift in verdict_matrix viol_types: unknown tokens {sorted(unknown)}. "
            f"Expected vocabulary {sorted(_valid_viol_types)}. "
            f"Update consumer literals before re-running."
        )

    for ep in per_episode:
        ac = bool(ep.get("ac_proxy"))
        mab = bool(ep.get("mab_proxy"))
        c2 = bool(ep.get("c2_pass"))
        dxem = bool(ep.get("dxem"))
        hard = bool(ep.get("v4_hard"))
        crit = bool(ep.get("v4_crit"))
        nv = int(ep.get("n_viols", 0))
        types = set(ep.get("viol_types") or [])
        cga = not hard

        n_dxem_pass += dxem
        n_ac_pass += ac
        n_c2_pass += c2
        n_mab_pass += mab
        n_cga_pass += cga
        n_v4_hard += hard

        if dxem and hard:
            fa_dxem += 1
            nviols_when_dxem_pass.append(nv)
        if ac and hard:
            fa_ac += 1
            nviols_when_ac_pass.append(nv)
        if c2 and hard:
            fa_c2 += 1
            nviols_when_c2_pass.append(nv)
        if mab and hard:
            fa_mab += 1
            nviols_when_mab_pass.append(nv)

        if ac and c2 and hard:
            n_loose_fa += 1
            nviols_loose.append(nv)
            if mab:
                n_strict_fa += 1
                if crit:
                    n_strict_fa_critical += 1

        # Single-type breakdowns (only when violations are present)
        if hard and types:
            if types == {"WITHIN"}:
                n_within_only += 1
            if "WITHIN" not in types:
                n_non_timing_natural += 1
                if types == {"FORBIDDEN"}:
                    n_non_timing_forbid_only += 1
                if types == {"BEFORE"}:
                    n_non_timing_before_only += 1

        verdicts = (dxem, ac, c2, mab, cga)
        if not (all(verdicts) or not any(verdicts)):
            n_disagree_any += 1

    # Strict-consensus blind-spot expressed as % of all trajectories
    macros["strictFAThree"] = fmt_pct(n_strict_fa, n)
    macros["strictFAThreeCount"] = fmt_int(n_strict_fa)
    macros["faAllOblivious"] = fmt_pct(n_loose_fa, n)
    macros["faAllObliviousCount"] = fmt_int(n_loose_fa)

    macros["consensusFACritical"] = fmt_int(n_strict_fa_critical)
    macros["consensusFACriticalPct"] = fmt_pct(n_strict_fa_critical, n_strict_fa)

    macros["verdictFlipRate"] = fmt_pct(n_disagree_any, n)
    macros["medianViolFalseAccept"] = f"{int(statistics.median(nviols_loose))}" if nviols_loose else "0"

    # Evaluator-row table (Table 1)
    macros["passrateDxEM"] = fmt_pct(n_dxem_pass, n)
    macros["passtrateACProxy"] = fmt_pct(n_ac_pass, n)
    macros["passrateCTwo"] = fmt_pct(n_c2_pass, n)
    macros["passtrateMABProxy"] = fmt_pct(n_mab_pass, n)
    macros["passrateCGABench"] = fmt_pct(n_cga_pass, n)

    macros["bsrDxEM"] = fmt_pct(fa_dxem, n)
    macros["bsrAC"] = fmt_pct(fa_ac, n)
    macros["bsrCTwo"] = fmt_pct(fa_c2, n)
    macros["bsrMAB"] = fmt_pct(fa_mab, n)

    macros["bsrCondDxEM"] = fmt_pct(fa_dxem, n_dxem_pass)
    macros["bsrCondAC"] = fmt_pct(fa_ac, n_ac_pass)
    macros["bsrCondCTwo"] = fmt_pct(fa_c2, n_c2_pass)
    macros["bsrCondMAB"] = fmt_pct(fa_mab, n_mab_pass)

    macros["bsrNDxEM"] = fmt_int(fa_dxem)
    macros["bsrNAC"] = fmt_int(fa_ac)
    macros["bsrNCTwo"] = fmt_int(fa_c2)
    macros["bsrNMAB"] = fmt_int(fa_mab)

    macros["medDgDxEM"] = f"{statistics.median(nviols_when_dxem_pass):.1f}" if nviols_when_dxem_pass else "0"
    macros["medDgAC"] = f"{statistics.median(nviols_when_ac_pass):.1f}" if nviols_when_ac_pass else "0"
    macros["medDgCTwo"] = f"{statistics.median(nviols_when_c2_pass):.1f}" if nviols_when_c2_pass else "0"
    macros["medDgMAB"] = f"{statistics.median(nviols_when_mab_pass):.1f}" if nviols_when_mab_pass else "0"

    # Subset claims
    macros["faWithinOnlyN"] = fmt_int(n_within_only)
    macros["withinOnlyRate"] = fmt_pct(n_within_only, n)
    macros["nonTimingNaturalCount"] = fmt_int(n_non_timing_natural)
    macros["nonTimingForbiddenOnly"] = fmt_int(n_non_timing_forbid_only)
    macros["nonTimingBeforeOnly"] = fmt_int(n_non_timing_before_only)

    return macros


def patch_auto_numbers(path: Path, macros: dict[str, str], comment: str) -> tuple[int, int]:
    """Replace existing \\(new|provide)command{\\<name>}{...} for any name in
    `macros`; append remaining names as \\providecommand at end of file.
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
        # Walk past the macro name and parse the value's balanced-brace block.
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
        lines[i] = f"{cmd}{{\\{name}}}{{{macros[name]}}}{tail}"
        if not lines[i].endswith("\n"):
            lines[i] += "\n"
        written.add(name)
    missing = [n for n in macros if n not in written]
    if missing:
        if not lines or not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append(f"% --- {comment} ---\n")
        for name in missing:
            lines.append(f"\\providecommand{{\\{name}}}{{{macros[name]}}}\n")
    path.write_text("".join(lines))
    return len(written), len(missing)


def main() -> None:
    matrix = json.loads(VERDICT.read_text())
    pe = matrix["per_episode"]
    print(
        f"verdict_matrix_v6.json: {len(pe)} per-episode entries; models = {sorted(matrix['metadata']['models'].keys())}"
    )

    stats = aggregate_model_stats(pe)
    per_model_macros, total = emit_per_model_macros(stats)
    main_body_macros = emit_main_body_macros(pe, total)
    all_macros = {**per_model_macros, **main_body_macros}

    print("\n=== Per-model BSR ===")
    for mdir, stem in MODEL_TO_STEM.items():
        s = stats[mdir]
        print(
            f"  {mdir:<20s} ASC-pass={s.ac_pass:>6,}  "
            f"TCC-fail-in-ASC-pass={s.ac_pass_and_tcc_fail:>6,}  "
            f"BSR={fmt_pct(s.ac_pass_and_tcc_fail, s.ac_pass)}%"
        )
    print(
        f"  {'Overall':<20s} ASC-pass={total.ac_pass:>6,}  "
        f"TCC-fail-in-ASC-pass={total.ac_pass_and_tcc_fail:>6,}  "
        f"BSR={fmt_pct(total.ac_pass_and_tcc_fail, total.ac_pass)}%"
    )

    print("\n=== Main-body false-accept ===")
    for k in (
        "strictFAThree",
        "strictFAThreeCount",
        "faAllOblivious",
        "faAllObliviousCount",
        "consensusFACritical",
        "consensusFACriticalPct",
        "verdictFlipRate",
        "medianViolFalseAccept",
        "withinOnlyRate",
        "faWithinOnlyN",
        "nonTimingNaturalCount",
        "nonTimingForbiddenOnly",
        "nonTimingBeforeOnly",
    ):
        print(f"  \\{k:<28s} = {main_body_macros[k]}")

    print("\n=== Evaluator-row (Table 1) ===")
    for ev in ("DxEM", "AC", "CTwo", "MAB"):
        passname = "passtrateACProxy" if ev == "AC" else "passtrateMABProxy" if ev == "MAB" else f"passrate{ev}"
        print(
            f"  {ev:<5s}  pass={main_body_macros[passname]}%"
            f"  FA={main_body_macros[f'bsr{ev}']}%"
            f"  cond={main_body_macros[f'bsrCond{ev}']}%"
            f"  n={main_body_macros[f'bsrN{ev}']}"
            f"  med dG~{main_body_macros[f'medDg{ev}']}"
        )
    print(f"  TCC    pass={main_body_macros['passrateCGABench']}%  FA=0  cond=0  n=0")

    n_main, app_main = patch_auto_numbers(
        AUTO_MAIN,
        all_macros,
        comment="appended by compute_table26_bsr_per_model.py (Phase A 9-model 19,062 corpus)",
    )
    n_v6, app_v6 = patch_auto_numbers(AUTO_V6, all_macros, comment="mirror of auto_numbers.tex")
    n_v18, app_v18 = patch_auto_numbers(AUTO_V18, all_macros, comment="mirror of auto_numbers.tex")
    print(
        f"\nUpdated {n_main} (+{app_main} appended) macros in {AUTO_MAIN.relative_to(REPO)}\n"
        f"Mirrored {n_v6} (+{app_v6}) in {AUTO_V6.relative_to(REPO)}\n"
        f"Mirrored {n_v18} (+{app_v18}) in {AUTO_V18.relative_to(REPO)}\n"
    )

    EVIDENCE_OUT.write_text(
        json.dumps(
            {
                "metadata": matrix.get("metadata", {}),
                "macros": all_macros,
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
                    for k, v in stats.items()
                },
                "total": {
                    f: getattr(total, f)
                    for f in ("n", "ac_pass", "mab_pass", "c2_pass", "dxem_pass", "tcc_pass", "ac_pass_and_tcc_fail")
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
