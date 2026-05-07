#!/usr/bin/env python3
"""T0-1 rerun + T0-2: extended-pool permutation + bootstrap for pi-class separation.

Background
----------
The original c6_audit_guided_selection.json was built on 6 evaluators
(C(6,2)=15 pairs, C(6,3)=20 splits), which made the permutation-test
p-value bounded below by ~0.1 regardless of effect size. This script
rebuilds the pi-class evidence on the *full* current SHIM_REGISTRY
(minus llm_judge, which requires a precomputed cache, and optionally
minus v4_hard for reference-contamination robustness), then re-runs:

  - T0-1 permutation test on pi-class labels (pre-existing structure)
  - T0-2 bootstrap 95% CI on same-class / cross-class mean τ

Outputs
-------
  evidence_pack/audit/piclass_pool_expand_selection_results.json
  evidence_pack/audit/piclass_pool_expand_permutation_results.json
  evidence_pack/audit/piclass_pool_expand_bootstrap_results.json
  evidence_pack/audit/piclass_pool_expand_macros.tex

Usage
-----
    PYTHONPATH=. python scripts/experiments/exp_piclass_pool_expand.py
    PYTHONPATH=. python scripts/experiments/exp_piclass_pool_expand.py --skip v4_hard --B 5000
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import itertools
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audit.metrics.selection import binary_tau  # noqa: E402
from audit.shims import SHIM_REGISTRY  # noqa: E402
from audit.shims._verdict_cache import load_w8_episodes  # noqa: E402
from scripts.audit.evaluator_audit import step1_pi_class  # noqa: E402

OUT_DIR = ROOT / "evidence_pack" / "audit"

DEFAULT_SKIP = {"llm_judge"}  # requires cache precompute
NONDEGEN_EPS = 1e-3


def _compute_verdicts(names: list[str]) -> tuple[list[str], dict[str, list[bool]], dict[str, str]]:
    """Instantiate each shim, classify pi, compute verdict vector.

    Returns (episode_ids, verdict_map, pi_class_map).
    """
    episodes = load_w8_episodes()
    ep_ids = sorted(episodes.keys())

    verdicts: dict[str, list[bool]] = {}
    pi_classes: dict[str, str] = {}
    for name in names:
        cls = SHIM_REGISTRY[name]
        ev = cls()
        print(f"  classify + verdict: {name} ...", end="", flush=True)
        s1 = step1_pi_class(ev)
        pi_classes[name] = s1["pi_class"]
        verdicts[name] = [ev.verdict({"episode_id": eid}) for eid in ep_ids]
        print(f" pi={s1['pi_class']}")
    return ep_ids, verdicts, pi_classes


def _pair_taus(
    verdicts: dict[str, list[bool]], idx: list[int] | None = None
) -> list[tuple[str, str, float]]:
    """Compute all C(n,2) pair-wise binary_tau. idx optionally subsets rows."""
    names = sorted(verdicts.keys())
    out: list[tuple[str, str, float]] = []
    if idx is not None:
        view = {n: [verdicts[n][i] for i in idx] for n in names}
    else:
        view = verdicts
    for a, b in itertools.combinations(names, 2):
        tau = binary_tau(view[a], view[b])
        out.append((a, b, tau))
    return out


def _same_cross_nondegen_means(
    pairs: list[tuple[str, str, float]], pi_classes: dict[str, str]
) -> tuple[float, float, int, int]:
    same, cross = [], []
    for a, b, t in pairs:
        if abs(t) <= NONDEGEN_EPS:
            continue
        if pi_classes[a] == pi_classes[b]:
            same.append(t)
        else:
            cross.append(t)
    return (
        statistics.fmean(same) if same else 0.0,
        statistics.fmean(cross) if cross else 0.0,
        len(same),
        len(cross),
    )


def run_permutation(
    pairs: list[tuple[str, str, float]], pi_classes: dict[str, str], B: int, seed: int
) -> dict:
    names = list(pi_classes.keys())
    labels = list(pi_classes.values())
    rng = random.Random(seed)

    s_obs, c_obs, ns, nc = _same_cross_nondegen_means(pairs, pi_classes)
    obs_gap = s_obs - c_obs

    null_gaps: list[float] = []
    for _ in range(B):
        shuffled = labels[:]
        rng.shuffle(shuffled)
        perm_map = dict(zip(names, shuffled))
        s, c, _, _ = _same_cross_nondegen_means(pairs, perm_map)
        null_gaps.append(s - c)

    n_extreme = sum(1 for g in null_gaps if abs(g) >= abs(obs_gap))
    return {
        "B": B,
        "seed": seed,
        "n_evaluators": len(names),
        "n_pairs": len(pairs),
        "n_same_nondegen": ns,
        "n_cross_nondegen": nc,
        "obs_same": round(s_obs, 4),
        "obs_cross": round(c_obs, 4),
        "obs_gap": round(obs_gap, 6),
        "null_mean": round(statistics.fmean(null_gaps), 6),
        "null_sd": round(statistics.pstdev(null_gaps), 6) if B > 1 else 0.0,
        "n_extreme": n_extreme,
        "p_value": n_extreme / B,
    }


def run_bootstrap(
    verdicts: dict[str, list[bool]], pi_classes: dict[str, str], B: int, seed: int
) -> dict:
    n_eps = len(next(iter(verdicts.values())))
    rng = random.Random(seed)

    # Observed full-corpus point estimate
    pairs_full = _pair_taus(verdicts)
    s_obs, c_obs, _, _ = _same_cross_nondegen_means(pairs_full, pi_classes)
    obs_gap = s_obs - c_obs

    same_draws, cross_draws, gap_draws = [], [], []
    for _ in range(B):
        idx = [rng.randrange(n_eps) for _ in range(n_eps)]
        pairs_b = _pair_taus(verdicts, idx=idx)
        s, c, _, _ = _same_cross_nondegen_means(pairs_b, pi_classes)
        same_draws.append(s)
        cross_draws.append(c)
        gap_draws.append(s - c)

    def _pctile(vals: list[float], q: float) -> float:
        s = sorted(vals)
        k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
        return s[k]

    s_lo, s_hi = _pctile(same_draws, 0.025), _pctile(same_draws, 0.975)
    c_lo, c_hi = _pctile(cross_draws, 0.025), _pctile(cross_draws, 0.975)
    g_lo, g_hi = _pctile(gap_draws, 0.025), _pctile(gap_draws, 0.975)
    return {
        "B": B,
        "seed": seed,
        "n_eps": n_eps,
        "obs_same": round(s_obs, 4),
        "obs_cross": round(c_obs, 4),
        "obs_gap": round(obs_gap, 4),
        "same_ci_lo": round(s_lo, 4),
        "same_ci_hi": round(s_hi, 4),
        "cross_ci_lo": round(c_lo, 4),
        "cross_ci_hi": round(c_hi, 4),
        "gap_ci_lo": round(g_lo, 4),
        "gap_ci_hi": round(g_hi, 4),
        "ci_overlap": bool(s_lo <= c_hi and c_lo <= s_hi),
    }


def _fmt_p(p: float, B: int) -> str:
    return f"< {1 / B:.0e}" if p == 0.0 else f"{p:.4f}"


def _emit_macros(perm: dict, boot: dict, path: Path) -> None:
    lines = [
        "% Auto-generated by scripts/experiments/exp_piclass_pool_expand.py",
        f"\\providecommand{{\\piPoolNEval}}{{{perm['n_evaluators']}}}",
        f"\\providecommand{{\\piPoolNPairs}}{{{perm['n_pairs']}}}",
        f"\\providecommand{{\\piPoolObsSame}}{{{perm['obs_same']:.4f}}}",
        f"\\providecommand{{\\piPoolObsCross}}{{{perm['obs_cross']:.4f}}}",
        f"\\providecommand{{\\piPoolObsGap}}{{{perm['obs_gap']:.4f}}}",
        f"\\providecommand{{\\piPoolPermB}}{{{perm['B']:,}}}",
        f"\\providecommand{{\\piPoolPermNullMean}}{{{perm['null_mean']:.4f}}}",
        f"\\providecommand{{\\piPoolPermNullSd}}{{{perm['null_sd']:.4f}}}",
        f"\\providecommand{{\\piPoolPermNExtreme}}{{{perm['n_extreme']}}}",
        f"\\providecommand{{\\piPoolPermP}}{{{_fmt_p(perm['p_value'], perm['B'])}}}",
        f"\\providecommand{{\\piPoolBootB}}{{{boot['B']:,}}}",
        f"\\providecommand{{\\piPoolBootSameLo}}{{{boot['same_ci_lo']:.4f}}}",
        f"\\providecommand{{\\piPoolBootSameHi}}{{{boot['same_ci_hi']:.4f}}}",
        f"\\providecommand{{\\piPoolBootCrossLo}}{{{boot['cross_ci_lo']:.4f}}}",
        f"\\providecommand{{\\piPoolBootCrossHi}}{{{boot['cross_ci_hi']:.4f}}}",
        f"\\providecommand{{\\piPoolBootGapLo}}{{{boot['gap_ci_lo']:.4f}}}",
        f"\\providecommand{{\\piPoolBootGapHi}}{{{boot['gap_ci_hi']:.4f}}}",
        f"\\providecommand{{\\piPoolBootOverlap}}{{{str(boot['ci_overlap']).lower()}}}",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="T0-1 + T0-2 on extended SHIM_REGISTRY pool")
    parser.add_argument(
        "--skip",
        nargs="+",
        default=sorted(DEFAULT_SKIP),
        help="Shim names to exclude (default: llm_judge)",
    )
    parser.add_argument("--exclude-v4-hard", action="store_true")
    parser.add_argument("--perm-B", type=int, default=10_000)
    parser.add_argument("--boot-B", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=str, default=str(OUT_DIR))
    args = parser.parse_args()

    skip = set(args.skip)
    if args.exclude_v4_hard:
        skip.add("v4_hard")

    names = sorted(n for n in SHIM_REGISTRY.keys() if n not in skip)
    print(f"Pool: {len(names)} evaluators (skipped: {sorted(skip)})")
    for n in names:
        print(f"  - {n}")

    ep_ids, verdicts, pi_classes = _compute_verdicts(names)
    print(f"\nPi-class distribution: {sorted(set(pi_classes.values()))}")
    for pc in sorted(set(pi_classes.values())):
        members = [n for n, c in pi_classes.items() if c == pc]
        print(f"  {pc} ({len(members)}): {members}")

    pairs = _pair_taus(verdicts)
    print(f"\nComputed {len(pairs)} pair-wise τ values.")

    perm = run_permutation(pairs, pi_classes, args.perm_B, args.seed)
    print(
        f"\n[T0-1 Permutation] obs_gap={perm['obs_gap']:.4f}  "
        f"null_mean={perm['null_mean']:.4f} (sd={perm['null_sd']:.4f})  "
        f"p={_fmt_p(perm['p_value'], perm['B'])}  "
        f"n_extreme={perm['n_extreme']}/{perm['B']}"
    )

    print(f"\n[T0-2 Bootstrap] running B={args.boot_B} episode-resample on {len(ep_ids)} eps ...")
    boot = run_bootstrap(verdicts, pi_classes, args.boot_B, args.seed)
    print(
        f"  same τ̄ ∈ [{boot['same_ci_lo']:.4f}, {boot['same_ci_hi']:.4f}]  "
        f"cross τ̄ ∈ [{boot['cross_ci_lo']:.4f}, {boot['cross_ci_hi']:.4f}]  "
        f"CI_overlap={boot['ci_overlap']}"
    )

    # Persist
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sel = {
        "timestamp": datetime.now(UTC).isoformat(),
        "n_evaluators": len(names),
        "evaluators": names,
        "pi_classes": pi_classes,
        "skip": sorted(skip),
        "excluded_v4_hard": args.exclude_v4_hard,
        "pairs": [{"evaluator_a": a, "evaluator_b": b, "tau": round(t, 4),
                   "pi_class_a": pi_classes[a], "pi_class_b": pi_classes[b]}
                  for (a, b, t) in pairs],
    }
    (out / "piclass_pool_expand_selection_results.json").write_text(
        json.dumps(sel, indent=2) + "\n"
    )
    perm["timestamp"] = datetime.now(UTC).isoformat()
    (out / "piclass_pool_expand_permutation_results.json").write_text(
        json.dumps(perm, indent=2) + "\n"
    )
    boot["timestamp"] = datetime.now(UTC).isoformat()
    (out / "piclass_pool_expand_bootstrap_results.json").write_text(
        json.dumps(boot, indent=2) + "\n"
    )
    _emit_macros(perm, boot, out / "piclass_pool_expand_macros.tex")
    print(f"\nSaved: {out / 'piclass_pool_expand_*.{json,tex}'}")


if __name__ == "__main__":
    main()
