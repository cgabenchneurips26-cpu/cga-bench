"""Trace how critical-FA numbers evolved across every available verdict matrix.

Reproduces the per-corpus statistics that go into the "1.46% critical" claim
(Phase B 8-model 16944 origin) so we can decide which corpus the App. T
severity breakdown should reference.

Definitions (the paper has used both at different times — this script reports
both side by side):

  loose-FA    = ac_proxy AND c2_pass AND v4_hard
  loose-crit  = loose-FA AND v4_crit
  strict-FA   = ac_proxy AND c2_pass AND mab_proxy AND v4_hard
  strict-crit = strict-FA AND v4_crit

Reported per corpus:
  total trajectories  N
  loose-FA            (count, % of N)
  loose-crit          (count, % of loose-FA, % of N)
  strict-FA           (count, % of N)
  strict-crit         (count, % of strict-FA, % of N)

Usage:
  PYTHONPATH=. python scripts/experiments/trace_critical_fa_evolution.py
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = REPO / "evidence_pack/analysis"

CORPORA = [
    ("v6 (Phase A 9m, 19062)", "verdict_matrix_v6.json"),
    ("v6_typed (Phase A 9m, 19062, typed CwT)", "verdict_matrix_v6_typed.json"),
    ("v6_full (Phase B 8m, 76464)", "verdict_matrix_v6_full.json"),
    ("v6_full_typed (Phase B 8m, 76464, typed)", "verdict_matrix_v6_full_typed.json"),
    ("v8_typed (auto-expanded, 29502)", "verdict_matrix_v8_typed.json"),
]

# Historical paper-time anchors copied from auto_numbers.tex git history.
# These are not recomputed; they show what the paper has *claimed* at each
# stage so we can spot drift.
PAPER_HISTORY = [
    (
        "v3-era (initial)",
        {
            "corpus": "(unknown 2038-loose-FA)",
            "loose_FA_count": 2038,
            "loose_crit_count": 554,
            "loose_crit_pct_of_FA": 27.2,
            "loose_FA_pct_of_total": 13.7,
        },
    ),
    (
        "v5 8-model 16944 (paper before 9m expansion)",
        {
            "corpus": "Phase A 8-model 16944",
            "loose_FA_count": 1959,
            "loose_crit_count": 432,
            "loose_crit_pct_of_FA": 22.1,
            "loose_FA_pct_of_total": 11.6,
        },
    ),
    (
        "v6 self-review correction",
        {
            "corpus": "Phase A 8-model 16944 (re-anchored)",
            "loose_FA_count": 2038,
            "loose_crit_count": 554,
            "loose_crit_pct_of_FA": 27.2,
            "loose_FA_pct_of_total": 13.7,
        },
    ),
    ("v6 9m 19062 (current after refresh)", {"corpus": "Phase A 9-model 19062 (computed below)"}),
]


@dataclass
class CorpusStats:
    name: str
    n_total: int
    loose_FA: int
    loose_crit: int
    strict_FA: int
    strict_crit: int

    @property
    def loose_FA_pct(self) -> float:
        return 100.0 * self.loose_FA / self.n_total if self.n_total else 0.0

    @property
    def loose_crit_pct_of_FA(self) -> float:
        return 100.0 * self.loose_crit / self.loose_FA if self.loose_FA else 0.0

    @property
    def loose_crit_pct_of_total(self) -> float:
        return 100.0 * self.loose_crit / self.n_total if self.n_total else 0.0

    @property
    def strict_FA_pct(self) -> float:
        return 100.0 * self.strict_FA / self.n_total if self.n_total else 0.0

    @property
    def strict_crit_pct_of_FA(self) -> float:
        return 100.0 * self.strict_crit / self.strict_FA if self.strict_FA else 0.0

    @property
    def strict_crit_pct_of_total(self) -> float:
        return 100.0 * self.strict_crit / self.n_total if self.n_total else 0.0


def aggregate(per_episode: list[dict], name: str) -> CorpusStats:
    n = loose = lcrit = strict = scrit = 0
    for ep in per_episode:
        n += 1
        ac = bool(ep.get("ac_proxy"))
        c2 = bool(ep.get("c2_pass"))
        mab = bool(ep.get("mab_proxy"))
        hard = bool(ep.get("v4_hard"))
        crit = bool(ep.get("v4_crit"))
        if ac and c2 and hard:
            loose += 1
            if crit:
                lcrit += 1
            if mab:
                strict += 1
                if crit:
                    scrit += 1
    return CorpusStats(name=name, n_total=n, loose_FA=loose, loose_crit=lcrit, strict_FA=strict, strict_crit=scrit)


def main() -> None:
    rows: list[CorpusStats] = []
    for name, fname in CORPORA:
        path = ANALYSIS_DIR / fname
        if not path.exists():
            print(f"  (skip, missing) {fname}")
            continue
        m = json.loads(path.read_text())
        pe = m.get("per_episode", [])
        if not pe:
            print(f"  (skip, no per_episode) {fname}")
            continue
        rows.append(aggregate(pe, name))

    print()
    print("=" * 116)
    print("Critical-FA evolution across all available verdict matrices")
    print("=" * 116)
    hdr = (
        f"{'Corpus':<48s} | {'N':>8s} | {'loose-FA':>10s} | {'loose-crit':>13s} | "
        f"{'strict-FA':>10s} | {'strict-crit':>14s}"
    )
    print(hdr)
    print("-" * 116)
    for r in rows:
        print(
            f"{r.name:<48s} | {r.n_total:>8,} | "
            f"{r.loose_FA:>5,} ({r.loose_FA_pct:>4.1f}%) | "
            f"{r.loose_crit:>3,} ({r.loose_crit_pct_of_FA:>4.1f}%/{r.loose_crit_pct_of_total:>4.2f}%) | "
            f"{r.strict_FA:>5,} ({r.strict_FA_pct:>4.1f}%) | "
            f"{r.strict_crit:>3,} ({r.strict_crit_pct_of_FA:>4.1f}%/{r.strict_crit_pct_of_total:>4.2f}%)"
        )
    print("-" * 116)
    print("Legend: 'loose-crit X (Y%/Z%)' = X trajectories; Y% of loose-FA; Z% of total trajectories.")
    print()
    print("=== Paper-time history (copied from auto_numbers.tex git history) ===")
    print("-" * 116)
    for tag, claim in PAPER_HISTORY:
        loose_FA = claim.get("loose_FA_count", "—")
        loose_crit = claim.get("loose_crit_count", "—")
        crit_pct_FA = claim.get("loose_crit_pct_of_FA", "—")
        FA_pct_tot = claim.get("loose_FA_pct_of_total", "—")
        print(f"  [{tag}]")
        print(f"     loose-FA={loose_FA}  loose-crit={loose_crit}  (crit/FA={crit_pct_FA}%, FA/total={FA_pct_tot}%)")
    print()


if __name__ == "__main__":
    main()
