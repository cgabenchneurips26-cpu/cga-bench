#!/usr/bin/env python3
"""T1-4: Held-out 5-CPG generalisation of the canonical-6 π-class separation.

Tests whether the within-cross τ̄ gap observed on the 6 canonical
evaluators (0.281 on the full corpus) generalises to the 5 held-out
CPG guidelines: ABA Burn, ACOG Obstetric Hemorrhage, APA Agitation,
PALS Pediatric, Toxicology. Scope-limited per
`docs/260423_piclass_pool_dilution_finding.md`: canonical-6 only.

The 5 held-out guidelines are not in the 20-CPG core set used to build
the audit separating pairs, so a preserved gap on them is a real
generalisation signal (CPG axis), even if pool-composition
generalisation has been retired.

Outputs
-------
  evidence_pack/audit/piclass_heldout_canonical6_results.json
  evidence_pack/audit/piclass_heldout_canonical6_macros.tex
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import itertools
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audit.metrics.selection import binary_tau  # noqa: E402
from audit.shims._verdict_cache import COLUMN_MAP, load_all_episodes, load_w8_episodes  # noqa: E402

OUT_DIR = ROOT / "evidence_pack" / "audit"
C6_PATH = ROOT / "evidence_pack" / "audit" / "c6_audit_guided_selection.json"

HELDOUT_PREFIXES: tuple[str, ...] = (
    "aba_burn",
    "acog_o",
    "apa_a",
    "pals_p",
    "toxicology_m",
)
CANONICAL_SIX: tuple[str, ...] = (
    "dxem",
    "ac_proxy",
    "mab_proxy",
    "c2_shim",
    "acov_shim",
    "v4_hard",
)
NONDEGEN_EPS = 1e-3


def _verdict_col(ep: dict, shim: str) -> bool:
    """Resolve a canonical-6 shim name to the verdict_matrix column value."""
    mapping = {
        "dxem": "dxem",
        "ac_proxy": "ac_proxy",
        "mab_proxy": "mab_proxy",
        "c2_shim": "c2_pass",
        "acov_shim": "acov_pass",
        "v4_hard": "v4_hard",
    }
    return bool(ep[mapping[shim]])


def _same_cross_nondegen(
    pairs: list[dict], pi_classes: dict[str, str]
) -> tuple[float, float, int, int]:
    same, cross = [], []
    for p in pairs:
        t = float(p["tau"])
        if abs(t) <= NONDEGEN_EPS:
            continue
        if pi_classes[p["evaluator_a"]] == pi_classes[p["evaluator_b"]]:
            same.append(t)
        else:
            cross.append(t)
    return (
        statistics.fmean(same) if same else 0.0,
        statistics.fmean(cross) if cross else 0.0,
        len(same),
        len(cross),
    )


def _pair_results(
    verdicts: dict[str, list[bool]], pi_classes: dict[str, str]
) -> list[dict]:
    names = sorted(verdicts.keys())
    out: list[dict] = []
    for a, b in itertools.combinations(names, 2):
        out.append(
            {
                "evaluator_a": a,
                "evaluator_b": b,
                "pi_class_a": pi_classes[a],
                "pi_class_b": pi_classes[b],
                "tau": round(binary_tau(verdicts[a], verdicts[b]), 4),
            }
        )
    return out


def _filter_episodes(
    episodes: dict[str, dict], prefixes: tuple[str, ...]
) -> dict[str, dict]:
    return {
        eid: ep
        for eid, ep in episodes.items()
        if any(ep["scenario_id"].startswith(p) for p in prefixes)
    }


def _heldout_vs_core(
    episodes: dict[str, dict],
    pi_classes: dict[str, str],
) -> dict:
    """Compute canonical-6 within/cross τ̄ on held-out vs core episodes."""
    held = _filter_episodes(episodes, HELDOUT_PREFIXES)
    core = {eid: ep for eid, ep in episodes.items() if eid not in held}

    def _compute(subset: dict[str, dict]) -> tuple[list[dict], float, float, int, int, int]:
        if not subset:
            return [], 0.0, 0.0, 0, 0, 0
        ep_ids = sorted(subset.keys())
        verdicts = {
            n: [_verdict_col(subset[e], n) for e in ep_ids] for n in CANONICAL_SIX
        }
        pr = _pair_results(verdicts, pi_classes)
        s, c, ns, nc = _same_cross_nondegen(pr, pi_classes)
        return pr, s, c, ns, nc, len(ep_ids)

    h_pairs, h_same, h_cross, h_ns, h_nc, h_n = _compute(held)
    c_pairs, c_same, c_cross, c_ns, c_nc, c_n = _compute(core)
    return {
        "held_out": {
            "n_episodes": h_n,
            "same_nondegen_mean": round(h_same, 4),
            "cross_nondegen_mean": round(h_cross, 4),
            "gap": round(h_same - h_cross, 4),
            "n_same_nondegen": h_ns,
            "n_cross_nondegen": h_nc,
            "pairs": h_pairs,
        },
        "core": {
            "n_episodes": c_n,
            "same_nondegen_mean": round(c_same, 4),
            "cross_nondegen_mean": round(c_cross, 4),
            "gap": round(c_same - c_cross, 4),
            "n_same_nondegen": c_ns,
            "n_cross_nondegen": c_nc,
        },
        "gap_delta_held_minus_core": round((h_same - h_cross) - (c_same - c_cross), 4),
    }


def _emit_macros(res: dict, path: Path) -> None:
    h = res["held_out"]
    c = res["core"]
    lines = [
        "% Auto-generated by scripts/experiments/exp_piclass_heldout.py",
        f"\\providecommand{{\\piHeldoutNEp}}{{{h['n_episodes']:,}}}",
        f"\\providecommand{{\\piHeldoutSame}}{{{h['same_nondegen_mean']:.4f}}}",
        f"\\providecommand{{\\piHeldoutCross}}{{{h['cross_nondegen_mean']:.4f}}}",
        f"\\providecommand{{\\piHeldoutGap}}{{{h['gap']:.4f}}}",
        f"\\providecommand{{\\piHeldoutCoreNEp}}{{{c['n_episodes']:,}}}",
        f"\\providecommand{{\\piHeldoutCoreSame}}{{{c['same_nondegen_mean']:.4f}}}",
        f"\\providecommand{{\\piHeldoutCoreCross}}{{{c['cross_nondegen_mean']:.4f}}}",
        f"\\providecommand{{\\piHeldoutCoreGap}}{{{c['gap']:.4f}}}",
        f"\\providecommand{{\\piHeldoutDelta}}{{{res['gap_delta_held_minus_core']:+.4f}}}",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="T1-4 held-out 5-CPG generalisation (canonical-6)")
    parser.add_argument("--include-deepseek", action="store_true")
    parser.add_argument("--out-dir", type=str, default=str(OUT_DIR))
    args = parser.parse_args()

    with open(C6_PATH) as f:
        pi_classes = json.load(f)["pi_classes"]
    print(f"Loaded canonical-6 pi-classes: {pi_classes}")

    episodes = load_all_episodes() if args.include_deepseek else load_w8_episodes()
    print(f"Working on {len(episodes)} episodes (include_deepseek={args.include_deepseek})")

    res = _heldout_vs_core(episodes, pi_classes)
    print(
        f"\n[Held-out] n={res['held_out']['n_episodes']}  "
        f"same={res['held_out']['same_nondegen_mean']:.4f}  "
        f"cross={res['held_out']['cross_nondegen_mean']:.4f}  "
        f"gap={res['held_out']['gap']:.4f}"
    )
    print(
        f"[Core]     n={res['core']['n_episodes']}  "
        f"same={res['core']['same_nondegen_mean']:.4f}  "
        f"cross={res['core']['cross_nondegen_mean']:.4f}  "
        f"gap={res['core']['gap']:.4f}"
    )
    print(f"[Δ gap]    held-out − core = {res['gap_delta_held_minus_core']:+.4f}")

    res["timestamp"] = datetime.now(UTC).isoformat()
    res["pi_classes"] = pi_classes
    res["canonical_six"] = list(CANONICAL_SIX)
    res["heldout_prefixes"] = list(HELDOUT_PREFIXES)
    res["include_deepseek"] = args.include_deepseek

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "piclass_heldout_canonical6_results.json").write_text(json.dumps(res, indent=2) + "\n")
    _emit_macros(res, out / "piclass_heldout_canonical6_macros.tex")
    print(f"\nSaved: piclass_heldout_canonical6_{{results.json, macros.tex}}")


if __name__ == "__main__":
    main()
