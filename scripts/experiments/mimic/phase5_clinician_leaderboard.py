#!/usr/bin/env python3
"""Phase 5 — Add MIMIC-IV clinicians as a 9th row to the leaderboard rank-bump chart.

Treats the MIMIC-IV cohort as a single pseudo-model named
``Human-Clinicians (MIMIC-IV)`` and inserts a new row into
``evidence_pack/analysis/rank_bootstrap.json`` (consumed by
``paper/figures/make_figure4_ranking.py``).

Framing locked (per source contract §Phase 5 / KNOWN_ISSUES.md §6):
  * "fixed-distribution reference point", NOT a head-to-head benchmark.
  * Never report "LLMs are X% worse than humans". Only rank-reversal.

Sanity gate (HALT):
  * Human ASC pass rate < ANY LLM's ASC pass rate (cohort/mapping issue).
  * CwT pass rate >= ASC pass rate (CwT must be stricter).

Outputs:
  * Updated ``evidence_pack/analysis/rank_bootstrap.json`` (in place;
    backup written to ``rank_bootstrap.pre_phase5.json``).
  * evidence_pack/mimic_iv/phase5/clinician_leaderboard.json
  * Macros: \\HumanRankAsc{}, \\HumanRankTcc{}, \\HumanAscPassRate{},
            \\HumanTccPassRate{}.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.experiments.mimic._common import (  # noqa: E402
    EVIDENCE_ROOT,
    GateFailure,
    PhaseSummary,
    git_sha,
    halt_and_log,
    mimic_version,
    resolve_mimic_root,
)

VERDICT_PARQUET = (
    REPO_ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_mimic_iv.parquet"
)
RANK_BOOTSTRAP = REPO_ROOT / "evidence_pack" / "analysis" / "rank_bootstrap.json"
RANK_BOOTSTRAP_BACKUP = (
    REPO_ROOT / "evidence_pack" / "analysis" / "rank_bootstrap.pre_phase5.json"
)
PHASE5_DIR = EVIDENCE_ROOT / "phase5"
OUTPUT_JSON = PHASE5_DIR / "clinician_leaderboard.json"
OUTPUT_MACROS = REPO_ROOT / "tex" / "auto_numbers_mimic_iv.tex"

EVAL_CODE_MAP = {
    "ASC": "AC",  # AC-Proxy in rank_bootstrap.json
    "CwT": "C2",
    "PAF": "MAB",
    "TCC": "CGA",
}


def _compute_pass_rates(df: pd.DataFrame) -> dict[str, float]:
    return {
        ev: float(df[f"verdict_{ev.lower()}"].mean())
        for ev in ("ASC", "CwT", "PAF", "TCC", "TOM", "ACov")
    }


def _rank_within_evaluator(
    rank_data: dict, evaluator_code: str, model_key: str, pass_rate: float
) -> int:
    """Insert (model_key, pass_rate) into the ranking and return the rank
    of model_key (1 = best). Higher pass rate = better rank.
    """
    per_cell = rank_data.get("per_cell", {})
    rates: list[tuple[str, float]] = []
    for m, evals in per_cell.items():
        if evaluator_code not in evals:
            continue
        rates.append((m, float(evals[evaluator_code].get("pass_rate", 0.0))))
    rates.append((model_key, pass_rate))
    rates.sort(key=lambda x: x[1], reverse=True)
    for rank, (m, _) in enumerate(rates, start=1):
        if m == model_key:
            return rank
    return -1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--skip-gates", action="store_true")
    ap.add_argument(
        "--no-bootstrap-update",
        action="store_true",
        help="Compute pass rates + ranks but do not write back into "
        "rank_bootstrap.json. Useful for dry-run inspection.",
    )
    args = ap.parse_args()

    t0 = time.time()
    if not VERDICT_PARQUET.is_file():
        print(f"[error] missing {VERDICT_PARQUET}", file=sys.stderr)
        return 2

    df = pd.read_parquet(VERDICT_PARQUET)
    rates = _compute_pass_rates(df)
    print(f"[phase5] human pass rates: {rates}")

    rank_data = {}
    if RANK_BOOTSTRAP.is_file():
        rank_data = json.loads(RANK_BOOTSTRAP.read_text())
    else:
        print(
            f"[warn] {RANK_BOOTSTRAP.relative_to(REPO_ROOT)} missing; "
            "human-row JSON will be standalone (no chart re-render).",
            file=sys.stderr,
        )

    model_key = "mimic_iv_clinicians"
    label = "Human-Clinicians (MIMIC-IV)"

    ranks = {}
    for ev_short, ev_code in EVAL_CODE_MAP.items():
        ranks[ev_short] = _rank_within_evaluator(rank_data, ev_code, model_key, rates[ev_short])

    if rank_data and not args.no_bootstrap_update:
        if not RANK_BOOTSTRAP_BACKUP.is_file():
            shutil.copy(RANK_BOOTSTRAP, RANK_BOOTSTRAP_BACKUP)
        per_cell = rank_data.setdefault("per_cell", {})
        # rank_ci_lo/hi are needed by the bump-chart highlight bands. We
        # don't have a bootstrap-driven CI for the human row here; emit
        # the point rank for both bounds (zero-width band) so the
        # downstream plotter doesn't error. Owner can recompute proper
        # CIs if a re-bootstrap pass is run.
        per_cell[model_key] = {
            ev_code: {
                "pass_rate": rates[ev_short],
                "point_rank": ranks[ev_short],
                "rank_ci_lo": ranks[ev_short],
                "rank_ci_hi": ranks[ev_short],
            }
            for ev_short, ev_code in EVAL_CODE_MAP.items()
        }
        labels = rank_data.setdefault("model_labels", {})
        labels[model_key] = label
        RANK_BOOTSTRAP.write_text(json.dumps(rank_data, indent=2) + "\n")
        print(f"[phase5] updated {RANK_BOOTSTRAP} (9th row added)")
        # The bump-chart Python file (make_figure4_ranking.py) hardcodes
        # MODEL_LABELS — owner must add ONE line manually:
        print(
            "[phase5] OWNER: add to paper/figures/make_figure4_ranking.py "
            "MODEL_LABELS dict:\n"
            f'      "{model_key}": "{label}",'
        )

    payload = {
        "metadata": {
            "git_sha": git_sha(),
            "mimic_version": mimic_version(resolve_mimic_root(prefer_full=True)),
            "n": len(df),
            "label": label,
        },
        "pass_rates": rates,
        "ranks": ranks,
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"[phase5] wrote {OUTPUT_JSON}")

    _append_macros(rates, ranks)

    summary = PhaseSummary(
        script_name="phase5_clinician_leaderboard",
        phase="phase5",
        n_episodes=len(df),
        seed=args.seed,
        git_sha=git_sha(),
        mimic_version=mimic_version(resolve_mimic_root(prefer_full=True)),
        wall_time_s=time.time() - t0,
        extra={"pass_rates": rates, "ranks": ranks},
    )
    summary.write(PHASE5_DIR)

    failures: list[str] = []
    if rank_data:
        # Compare human ASC to all other LLMs' ASC
        per_cell = rank_data.get("per_cell", {})
        llm_asc_rates = [
            float(per_cell[m]["AC"].get("pass_rate", 0.0))
            for m in per_cell
            if m != model_key and "AC" in per_cell[m]
        ]
        if llm_asc_rates and rates["ASC"] < min(llm_asc_rates):
            failures.append(
                f"human_asc {rates['ASC']:.3f} < min LLM ASC {min(llm_asc_rates):.3f} "
                f"(suspect cohort or mapping)"
            )
    if rates["CwT"] >= rates["ASC"]:
        failures.append(
            f"human_cwt {rates['CwT']:.3f} >= human_asc {rates['ASC']:.3f} "
            f"(CwT must be stricter)"
        )

    if failures and not args.skip_gates:
        try:
            halt_and_log(
                gate_name="phase5_clinician_gates",
                detail="; ".join(failures),
                known_issues_section="6",
            )
        except GateFailure as exc:
            print(f"[HALT] {exc}", file=sys.stderr)
            return 1

    print(f"[phase5] done in {time.time() - t0:.1f}s")
    return 0


def _append_macros(rates: dict[str, float], ranks: dict[str, int]) -> None:
    block = (
        "% Phase 5 (clinician leaderboard row)\n"
        f"\\newcommand{{\\HumanAscPassRate}}{{{rates['ASC'] * 100:.1f}}}\n"
        f"\\newcommand{{\\HumanCwtPassRate}}{{{rates['CwT'] * 100:.1f}}}\n"
        f"\\newcommand{{\\HumanPafPassRate}}{{{rates['PAF'] * 100:.1f}}}\n"
        f"\\newcommand{{\\HumanTccPassRate}}{{{rates['TCC'] * 100:.1f}}}\n"
        f"\\newcommand{{\\HumanRankAsc}}{{{ranks['ASC']}}}\n"
        f"\\newcommand{{\\HumanRankCwt}}{{{ranks['CwT']}}}\n"
        f"\\newcommand{{\\HumanRankPaf}}{{{ranks['PAF']}}}\n"
        f"\\newcommand{{\\HumanRankTcc}}{{{ranks['TCC']}}}\n"
    )
    if OUTPUT_MACROS.is_file():
        existing = OUTPUT_MACROS.read_text()
        marker = "% Phase 5 (clinician leaderboard row)"
        if marker in existing:
            head, _ = existing.split(marker, 1)
            tail_after = existing.split(marker, 1)[1]
            tail_lines = tail_after.splitlines(keepends=True)
            i = 0
            while i < len(tail_lines) and tail_lines[i].startswith(("\\newcommand", "\n")):
                i += 1
            new = head + block + "".join(tail_lines[i:])
            OUTPUT_MACROS.write_text(new)
        else:
            OUTPUT_MACROS.write_text(existing + "\n" + block)
    else:
        OUTPUT_MACROS.write_text("% Auto-generated MIMIC-IV macros.\n" + block)
    print(f"[phase5] updated {OUTPUT_MACROS}")


if __name__ == "__main__":
    raise SystemExit(main())
