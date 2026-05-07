"""Numerical sanity check for NeurIPS v18 paper claims.

Verifies that every load-bearing macro in paper/auto_numbers_v6.tex (and v18)
that we recently injected or that depends on the v6 9-model headline corpus
matches the source data.

Run after editing auto_numbers_*.tex or after data changes:

    PYTHONPATH=. python scripts/experiments/verify_paper_numbers.py
"""

from __future__ import annotations

import json
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
VERDICT = REPO / "evidence_pack/analysis/verdict_matrix_v6.json"
EVIDENCE_BSR = REPO / "evidence_pack/analysis/per_model_bsr_v6.json"
AUTO_V6 = REPO / "paper/auto_numbers_v6.tex"
AUTO_V18 = REPO / "paper/auto_numbers_v18.tex"

EXPECTED_MODELS = [
    "deepseek_r1_7b",
    "qwen4b",
    "qwen27b",
    "qwen35b",
    "nemotron30b",
    "gemma31b",
    "llama4scout",
    "oss120b",
    "qwen397b",
]
N_RUNS = 3
N_SCENARIOS_MANUAL = 706
N_MODELS = 9
TOL_PCT = 0.05


def parse_macros(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    pattern = re.compile(r"\\(?:newcommand|providecommand)\{\\([A-Za-z]+)\}\{([^}]*)\}")
    for line in path.read_text().splitlines():
        m = pattern.search(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def num_from_str(s: str) -> float:
    return float(s.replace(",", "").replace("{", "").replace("}", ""))


def check(label: str, expected: float, actual: float, tol: float = TOL_PCT) -> bool:
    ok = abs(expected - actual) <= tol
    mark = "OK " if ok else "FAIL"
    if isinstance(expected, float) or isinstance(actual, float):
        print(f"  [{mark}] {label}: expected={expected:.3f}  actual={actual:.3f}  diff={abs(expected - actual):.3f}")
    else:
        print(f"  [{mark}] {label}: expected={expected}  actual={actual}")
    return ok


def verify_corpus_arithmetic(macros_v6: dict[str, str]) -> bool:
    print("\n=== Corpus arithmetic ===")
    n_models = int(num_from_str(macros_v6["numModels"]))
    n_episodes = int(num_from_str(macros_v6["numEpisodes"]))
    expected_episodes = N_SCENARIOS_MANUAL * n_models * N_RUNS
    ok1 = check(
        f"\\numEpisodes == {N_SCENARIOS_MANUAL} x {n_models} x {N_RUNS}",
        expected_episodes,
        n_episodes,
    )
    ok2 = check("\\numModels == 9", N_MODELS, n_models)
    return ok1 and ok2


def verify_bsr_aggregates(matrix: dict, macros: dict[str, str]) -> bool:
    print("\n=== BSR aggregates (per model) ===")
    by_model: dict[str, dict[str, int]] = {}
    for ep in matrix["per_episode"]:
        m = ep["model_dir"]
        s = by_model.setdefault(m, {"n": 0, "ac_pass": 0, "ac_pass_and_tcc_fail": 0})
        s["n"] += 1
        if ep.get("ac_proxy"):
            s["ac_pass"] += 1
            if ep.get("v4_hard"):
                s["ac_pass_and_tcc_fail"] += 1

    stems = {
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
    all_ok = True
    total = {"ac_pass": 0, "ac_pass_and_tcc_fail": 0}
    for model_dir, stem in stems.items():
        if model_dir not in by_model:
            print(f"  [FAIL] {model_dir} missing from verdict matrix")
            all_ok = False
            continue
        s = by_model[model_dir]
        total["ac_pass"] += s["ac_pass"]
        total["ac_pass_and_tcc_fail"] += s["ac_pass_and_tcc_fail"]
        ok_n = check(
            f"\\bsr{stem}N",
            s["ac_pass"],
            int(num_from_str(macros[f"bsr{stem}N"])),
            tol=0,
        )
        ok_f = check(
            f"\\bsr{stem}Fail",
            s["ac_pass_and_tcc_fail"],
            int(num_from_str(macros[f"bsr{stem}Fail"])),
            tol=0,
        )
        expected_pct = (s["ac_pass_and_tcc_fail"] / s["ac_pass"]) * 100 if s["ac_pass"] else 0.0
        ok_p = check(
            f"\\bsr{stem}Pct",
            round(expected_pct, 1),
            float(macros[f"bsr{stem}Pct"]),
            tol=0.05,
        )
        all_ok = all_ok and ok_n and ok_f and ok_p

    expected_all_pct = total["ac_pass_and_tcc_fail"] / total["ac_pass"] * 100
    ok_all_n = check("\\bsrAllN", total["ac_pass"], int(num_from_str(macros["bsrAllN"])), tol=0)
    ok_all_f = check(
        "\\bsrAllFail",
        total["ac_pass_and_tcc_fail"],
        int(num_from_str(macros["bsrAllFail"])),
        tol=0,
    )
    ok_all_p = check("\\bsrAllPct", round(expected_all_pct, 1), float(macros["bsrAllPct"]), tol=0.05)
    return all_ok and ok_all_n and ok_all_f and ok_all_p


def verify_headline_replay(matrix: dict, macros: dict[str, str]) -> bool:
    print("\n=== Headline Replay (per-model MAB/AC/TCC pass-rates) ===")
    by_model: dict[str, dict[str, int]] = {}
    for ep in matrix["per_episode"]:
        m = ep["model_dir"]
        s = by_model.setdefault(m, {"n": 0, "mab_pass": 0, "ac_pass": 0, "tcc_pass": 0})
        s["n"] += 1
        if ep.get("mab_proxy"):
            s["mab_pass"] += 1
        if ep.get("ac_proxy"):
            s["ac_pass"] += 1
        if not ep.get("v4_hard"):
            s["tcc_pass"] += 1

    stems = {
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
    all_ok = True
    for model_dir, stem in stems.items():
        if model_dir not in by_model:
            continue
        s = by_model[model_dir]
        n = s["n"]
        for col, key in [("MAB", "mab_pass"), ("AC", "ac_pass"), ("TCC", "tcc_pass")]:
            expected = round((s[key] / n) * 100, 1)
            actual = float(macros[f"hl{stem}{col}"])
            all_ok = check(f"\\hl{stem}{col}", expected, actual, tol=0.05) and all_ok
        expected_delta = round((s["mab_pass"] / n - s["tcc_pass"] / n) * 100, 1)
        actual_delta = float(macros[f"hl{stem}Delta"])
        all_ok = check(f"\\hl{stem}Delta", expected_delta, actual_delta, tol=0.05) and all_ok
    return all_ok


def verify_strict_consensus(matrix: dict, macros: dict[str, str]) -> bool:
    r"""Verify \strictFAThree, \strictFAThreeCount, \consensusFACritical[Pct]."""
    print("\n=== Strict consensus and Critical decomposition ===")
    n_total = 0
    n_strict_fa = 0
    n_strict_fa_critical = 0
    for ep in matrix["per_episode"]:
        n_total += 1
        ac_pass = bool(ep.get("ac_proxy"))
        mab_pass = bool(ep.get("mab_proxy"))
        c2_pass = bool(ep.get("c2_pass"))
        v4_hard = bool(ep.get("v4_hard"))
        v4_crit = bool(ep.get("v4_crit"))
        if ac_pass and mab_pass and c2_pass and v4_hard:
            n_strict_fa += 1
            if v4_crit:
                n_strict_fa_critical += 1

    expected_strict_pct = round((n_strict_fa / n_total) * 100, 1)
    actual_strict_pct = float(macros["strictFAThree"])
    ok_a = check("\\strictFAThree", expected_strict_pct, actual_strict_pct, tol=0.5)
    ok_b = check(
        "\\strictFAThreeCount",
        n_strict_fa,
        int(num_from_str(macros["strictFAThreeCount"])),
        tol=10,
    )
    expected_crit = n_strict_fa_critical
    expected_crit_pct = round((n_strict_fa_critical / n_strict_fa) * 100, 1) if n_strict_fa else 0.0
    actual_crit = int(num_from_str(macros["consensusFACritical"]))
    actual_crit_pct = float(macros["consensusFACriticalPct"])
    ok_c = check("\\consensusFACritical (count)", expected_crit, actual_crit, tol=10)
    ok_d = check(
        "\\consensusFACriticalPct (% of strict FA)",
        expected_crit_pct,
        actual_crit_pct,
        tol=0.5,
    )
    print(f"  Computed total: n_total={n_total}, strict_FA={n_strict_fa}, critical={n_strict_fa_critical}")
    print(f"  Critical fraction of all trajectories: {n_strict_fa_critical / n_total * 100:.2f}%")
    return ok_a and ok_b and ok_c and ok_d


def verify_macro_parity(v6: dict[str, str], v18: dict[str, str]) -> bool:
    """Macros injected by compute_table26_bsr_per_model.py must agree v6 <-> v18."""
    print("\n=== v6 <-> v18 macro parity (BSR + Headline) ===")
    targets = []
    for stem in [
        "DS",
        "Qfour",
        "Qtwentyseven",
        "Qthirtyfive",
        "Nemo",
        "Gemma",
        "LlamaFour",
        "OSS",
        "Qthreenine",
        "All",
    ]:
        targets += [f"bsr{stem}N", f"bsr{stem}Fail", f"bsr{stem}Pct"]
        targets += [f"hl{stem}MAB", f"hl{stem}AC", f"hl{stem}TCC", f"hl{stem}Delta"]
    bad = [t for t in targets if v6.get(t) != v18.get(t)]
    if bad:
        for t in bad:
            print(f"  [FAIL] {t}: v6={v6.get(t)}  v18={v18.get(t)}")
        return False
    print(f"  [OK ] all {len(targets)} macros agree")
    return True


def main() -> None:
    matrix = json.loads(VERDICT.read_text())
    print(
        f"verdict_matrix_v6.json: {len(matrix['per_episode'])} per-episode entries, "
        f"models={list(matrix['metadata']['models'].keys())}"
    )
    macros_v6 = parse_macros(AUTO_V6)
    macros_v18 = parse_macros(AUTO_V18)
    print(f"auto_numbers_v6: {len(macros_v6)} macros parsed")
    print(f"auto_numbers_v18: {len(macros_v18)} macros parsed")

    results = [
        verify_corpus_arithmetic(macros_v6),
        verify_bsr_aggregates(matrix, macros_v6),
        verify_headline_replay(matrix, macros_v6),
        verify_strict_consensus(matrix, macros_v6),
        verify_macro_parity(macros_v6, macros_v18),
    ]
    print("\n=== SUMMARY ===")
    print(f"  passed: {sum(results)} / {len(results)}")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
