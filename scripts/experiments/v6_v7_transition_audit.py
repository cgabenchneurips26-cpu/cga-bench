"""TG-V4 — v6 -> v7 transition attribution table.

The paper Appendix Z transition-disclosure subsection must attribute the
v6 -> v7 score delta across four orthogonal dimensions:

    1. Corpus change       25 -> 14 CPGs              (scenario count, headline FA)
    2. CDS=False default   agent loses mandatory hint (compliance score)
    3. ALTERNATIVE active  OR-path violations counted (violation count)
    4. v1.1 CDE coupling   CONFLICT surfacing added   (CONFLICT count)

This script consumes per-arm aggregate JSONs and emits both a JSON
attribution record and a Markdown table suitable for paper inclusion.

Each input JSON is an aggregate produced by the existing v6/v7 runners
(``aggregate_heldout_v6.py``, ``recompute_v6_full_macros.py`` etc.).  We
do not re-run experiments here — the script is a *delta calculator* that
reads canonical aggregates and writes the transition table.

Required inputs (paths configurable via CLI):

    --v6-baseline aggregate.json
        v6 corpus (25 CPGs), CDS=True implicit, ALTERNATIVE reserved,
        no CDE coupling.

    --v7-corpus-only aggregate.json
        v7 corpus (14 CPGs), but with v6's CDS=True / no ALTERNATIVE /
        no CDE — isolates the corpus-change contribution.

    --v7-cds-flip aggregate.json
        v7 corpus, CDS=False, but v6's coverage rules — isolates the
        CDS-default contribution on top of the corpus change.

    --v7-alternative aggregate.json
        v7 corpus, CDS=False, ALTERNATIVE active, no CDE — isolates the
        coverage contribution.

    --v7-final aggregate.json
        v7 corpus, CDS=False, ALTERNATIVE active, CDE coupling — full
        v7 result.

Each aggregate JSON is expected to contain at minimum:

    {
        "n_scenarios": int,
        "headline_fa": float,
        "mean_compliance": float,
        "mean_violations_per_episode": float,
        "n_conflict_events": int,
    }

Output:

    transition_audit.json   — structured attribution record
    transition_audit.md     — Appendix-Z-ready table
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ArmSnapshot:
    """One arm's headline metrics."""

    label: str
    n_scenarios: int
    headline_fa: float
    mean_compliance: float
    mean_violations_per_episode: float
    n_conflict_events: int


@dataclass(frozen=True)
class AttributionRow:
    """One row of the attribution table — a single dimension's contribution."""

    dimension: str
    description: str
    delta_headline_fa: float
    delta_mean_compliance: float
    delta_violations_per_episode: float
    delta_conflict_events: int


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def load_arm(path: Path, label: str) -> ArmSnapshot:
    """Load an aggregate JSON into an ArmSnapshot.

    Raises ``ValueError`` if any required key is missing — callers should
    surface that as a CLI error rather than silently filling defaults.
    """
    data = json.loads(path.read_text())
    required = (
        "n_scenarios",
        "headline_fa",
        "mean_compliance",
        "mean_violations_per_episode",
        "n_conflict_events",
    )
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"{path}: missing keys {missing}")
    return ArmSnapshot(
        label=label,
        n_scenarios=int(data["n_scenarios"]),
        headline_fa=float(data["headline_fa"]),
        mean_compliance=float(data["mean_compliance"]),
        mean_violations_per_episode=float(data["mean_violations_per_episode"]),
        n_conflict_events=int(data["n_conflict_events"]),
    )


def attribute(
    v6: ArmSnapshot,
    v7_corpus_only: ArmSnapshot,
    v7_cds_flip: ArmSnapshot,
    v7_alternative: ArmSnapshot,
    v7_final: ArmSnapshot,
) -> list[AttributionRow]:
    """Compute four ordered attribution rows from the five arm snapshots.

    Each row is the *marginal* contribution of switching ONE additional
    dimension on, holding earlier dimensions at their already-flipped state.
    The four marginals sum to the total v6 -> v7_final delta.
    """
    rows: list[AttributionRow] = []

    rows.append(
        AttributionRow(
            dimension="corpus_change_25_to_14_cpgs",
            description="v6 corpus (25 CPGs) -> v7 corpus (14 CPGs); CDS+coverage held at v6.",
            delta_headline_fa=v7_corpus_only.headline_fa - v6.headline_fa,
            delta_mean_compliance=v7_corpus_only.mean_compliance - v6.mean_compliance,
            delta_violations_per_episode=(
                v7_corpus_only.mean_violations_per_episode - v6.mean_violations_per_episode
            ),
            delta_conflict_events=v7_corpus_only.n_conflict_events - v6.n_conflict_events,
        )
    )
    rows.append(
        AttributionRow(
            dimension="cds_default_true_to_false",
            description="CDS=True (v6 implicit) -> CDS=False (Phase F default); on top of corpus change.",
            delta_headline_fa=v7_cds_flip.headline_fa - v7_corpus_only.headline_fa,
            delta_mean_compliance=v7_cds_flip.mean_compliance - v7_corpus_only.mean_compliance,
            delta_violations_per_episode=(
                v7_cds_flip.mean_violations_per_episode
                - v7_corpus_only.mean_violations_per_episode
            ),
            delta_conflict_events=v7_cds_flip.n_conflict_events - v7_corpus_only.n_conflict_events,
        )
    )
    rows.append(
        AttributionRow(
            dimension="alternative_coverage_reserved_to_active",
            description="ALTERNATIVE reserved -> active (Phase D); OR-path violations now counted.",
            delta_headline_fa=v7_alternative.headline_fa - v7_cds_flip.headline_fa,
            delta_mean_compliance=v7_alternative.mean_compliance - v7_cds_flip.mean_compliance,
            delta_violations_per_episode=(
                v7_alternative.mean_violations_per_episode - v7_cds_flip.mean_violations_per_episode
            ),
            delta_conflict_events=v7_alternative.n_conflict_events - v7_cds_flip.n_conflict_events,
        )
    )
    rows.append(
        AttributionRow(
            dimension="cde_coupling_added",
            description="v1.1 CDE coupling (CONFLICT surfacing); on top of alternative coverage.",
            delta_headline_fa=v7_final.headline_fa - v7_alternative.headline_fa,
            delta_mean_compliance=v7_final.mean_compliance - v7_alternative.mean_compliance,
            delta_violations_per_episode=(
                v7_final.mean_violations_per_episode - v7_alternative.mean_violations_per_episode
            ),
            delta_conflict_events=v7_final.n_conflict_events - v7_alternative.n_conflict_events,
        )
    )
    return rows


def render_audit_md(
    v6: ArmSnapshot,
    v7_final: ArmSnapshot,
    rows: list[AttributionRow],
) -> str:
    """Render the attribution table as Markdown."""
    total_fa = v7_final.headline_fa - v6.headline_fa
    total_compliance = v7_final.mean_compliance - v6.mean_compliance
    total_violations = (
        v7_final.mean_violations_per_episode - v6.mean_violations_per_episode
    )
    total_conflict = v7_final.n_conflict_events - v6.n_conflict_events

    summed_fa = sum(r.delta_headline_fa for r in rows)
    summed_compliance = sum(r.delta_mean_compliance for r in rows)
    summed_violations = sum(r.delta_violations_per_episode for r in rows)
    summed_conflict = sum(r.delta_conflict_events for r in rows)

    lines = [
        "# v6 -> v7 Transition Attribution Table (TG-V4 evidence)",
        "",
        f"v6 baseline: {v6.label} (n_scenarios={v6.n_scenarios})",
        f"v7 final:    {v7_final.label} (n_scenarios={v7_final.n_scenarios})",
        "",
        "| Dimension | Δ headline_FA | Δ mean_compliance | Δ violations/ep | Δ conflict_events |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r.dimension} | {r.delta_headline_fa:+.4f} | {r.delta_mean_compliance:+.4f} | "
            f"{r.delta_violations_per_episode:+.4f} | {r.delta_conflict_events:+d} |"
        )
    lines.append(
        f"| **Sum (marginals)** | {summed_fa:+.4f} | {summed_compliance:+.4f} | "
        f"{summed_violations:+.4f} | {summed_conflict:+d} |"
    )
    lines.append(
        f"| **Direct delta (v7 - v6)** | {total_fa:+.4f} | {total_compliance:+.4f} | "
        f"{total_violations:+.4f} | {total_conflict:+d} |"
    )
    lines.append("")
    lines.append("Marginals sum to the direct delta when the four arms are properly nested.")
    lines.append("Discrepancy > 1e-6 indicates the intermediate aggregates were not run on the")
    lines.append("expected ablation sequence.")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TG-V4 v6->v7 transition attribution table generator.",
    )
    parser.add_argument("--v6-baseline", type=Path, required=True)
    parser.add_argument("--v7-corpus-only", type=Path, required=True)
    parser.add_argument("--v7-cds-flip", type=Path, required=True)
    parser.add_argument("--v7-alternative", type=Path, required=True)
    parser.add_argument("--v7-final", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    v6 = load_arm(args.v6_baseline, "v6_baseline")
    v7_corpus_only = load_arm(args.v7_corpus_only, "v7_corpus_only")
    v7_cds_flip = load_arm(args.v7_cds_flip, "v7_cds_flip")
    v7_alternative = load_arm(args.v7_alternative, "v7_alternative")
    v7_final = load_arm(args.v7_final, "v7_final")

    rows = attribute(v6, v7_corpus_only, v7_cds_flip, v7_alternative, v7_final)

    json_out = args.output_dir / "transition_audit.json"
    md_out = args.output_dir / "transition_audit.md"
    json_out.write_text(
        json.dumps(
            {
                "arms": {
                    "v6": asdict(v6),
                    "v7_corpus_only": asdict(v7_corpus_only),
                    "v7_cds_flip": asdict(v7_cds_flip),
                    "v7_alternative": asdict(v7_alternative),
                    "v7_final": asdict(v7_final),
                },
                "attribution": [asdict(r) for r in rows],
            },
            indent=2,
        )
    )
    md_out.write_text(render_audit_md(v6, v7_final, rows))
    print(f"Wrote {json_out} and {md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
