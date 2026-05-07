#!/usr/bin/env python3
"""Theorem 3.4 v2 — Empirical Bayes-error estimator.

Implements the plug-in estimator of eq. (empirical-bayes) in
appendix_theorem_proofs.tex over the 19,062-episode CGA-Bench corpus
(9 models × 706 scenarios × 3 runs), under four trace projections:

    pi_term : termination reason only (coarsest; scenario-agnostic end)
    pi_aset : sorted multiset of performed action IDs
    pi_nord : ordered action ID sequence (timestamps stripped)
    pi_nctx : (action_id, timestamp_5min_bin) sequence (context stripped)

Label: hard_violation ∈ {0,1} = any violation_event with type ∈
{commission, timing, sequence}. Matches _episode_cache.score_episode
field `v4_hard`.

Bootstrap: B=1000 index-resamples for a 95% CI on each Bayes error.

Outputs:
    evidence_pack/theorem_v2/bayes_error_results.json
    evidence_pack/theorem_v2/bayes_error_macros.tex   (regenerated)

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/compute_bayes_error.py
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
import hashlib
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.experiments._episode_cache import (  # noqa: E402
    HARD_VIOL_TYPES,
    _classify_violation_type,
    load_cached_episodes,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = ROOT / "evidence_pack" / "theorem_v2"
BOOTSTRAP_N = 1000
RNG_SEED = 42
TIMESTAMP_BIN_MIN = 5.0
HARD_TYPES = tuple(sorted(HARD_VIOL_TYPES))


# ---------------------------------------------------------------------------
# Label: hard violation (commission/timing/sequence)
# ---------------------------------------------------------------------------


def hard_violation_label(ep: dict[str, Any]) -> int:
    """Return 1 if the episode contains any hard (commission/timing/sequence) violation."""
    for v in ep.get("violation_events", []) or []:
        if not isinstance(v, dict):
            continue
        raw = str(v.get("violation_type", v.get("type", "")))
        if _classify_violation_type(raw) in HARD_VIOL_TYPES:
            return 1
    return 0


def per_type_labels(ep: dict[str, Any]) -> dict[str, int]:
    """Return {violation_type: 0|1} indicator per canonical type."""
    canon = ("omission", "commission", "timing", "sequence", "deviation")
    flags = dict.fromkeys(canon, 0)
    for v in ep.get("violation_events", []) or []:
        if not isinstance(v, dict):
            continue
        raw = str(v.get("violation_type", v.get("type", "")))
        ct = _classify_violation_type(raw)
        if ct in flags:
            flags[ct] = 1
    return flags


# ---------------------------------------------------------------------------
# Projections (return a hashable key per episode)
# ---------------------------------------------------------------------------


def _norm(aid: str) -> str:
    return aid.strip().lower().replace("-", "_").replace(" ", "_")


def tau_term(ep: dict[str, Any]) -> str:
    """Terminal projection: coarsest. Episode ends in one of a few termination_reason buckets."""
    return str(ep.get("termination_reason") or "unknown")


def tau_aset(ep: dict[str, Any]) -> tuple[str, ...]:
    """Action multiset projection."""
    return tuple(sorted({_norm(a.get("action_id", "")) for a in ep.get("actions", []) if a.get("action_id")}))


def tau_nord(ep: dict[str, Any]) -> tuple[str, ...]:
    """Ordered action projection: timestamps stripped."""
    return tuple(_norm(a.get("action_id", "")) for a in ep.get("actions", []) if a.get("action_id"))


def tau_nctx(ep: dict[str, Any]) -> tuple[tuple[str, int], ...]:
    """Context-stripped projection: (action_id, ts_bin) sequence; patient state absent anyway."""
    out = []
    for a in ep.get("actions", []):
        aid = _norm(a.get("action_id", ""))
        if not aid:
            continue
        ts_raw = a.get("timestamp_minutes", 0.0)
        try:
            ts = float(ts_raw)
        except (TypeError, ValueError):
            ts = 0.0
        bin_idx = int(ts // TIMESTAMP_BIN_MIN) * int(TIMESTAMP_BIN_MIN)
        out.append((aid, bin_idx))
    return tuple(out)


PROJECTIONS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "term": tau_term,
    "aset": tau_aset,
    "nord": tau_nord,
    "nctx": tau_nctx,
}


def _hash_key(key: Any) -> str:
    """Stable string hash for dict keys."""
    return hashlib.md5(repr(key).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Plug-in estimator
# ---------------------------------------------------------------------------


def _fibre_bayes_stats(keys: np.ndarray, labels: np.ndarray) -> tuple[float, float, int, int]:
    """Compute Bayes error stats for given (key, label) arrays.

    Returns: (bayes_error, mixed_fibre_mass, n_fibres, n_mixed_fibres)
    """
    n = len(keys)
    if n == 0:
        return (0.0, 0.0, 0, 0)
    fibres: dict[str, list[int]] = defaultdict(list)
    for i, k in enumerate(keys):
        fibres[k].append(int(labels[i]))
    total_minority = 0
    mixed_mass = 0
    n_mixed = 0
    for _, verdicts in fibres.items():
        counts = Counter(verdicts)
        if len(counts) >= 2:
            size = sum(counts.values())
            mixed_mass += size
            total_minority += size - counts.most_common(1)[0][1]
            n_mixed += 1
    return (total_minority / n, mixed_mass / n, len(fibres), n_mixed)


def compute_one_projection(
    proj_name: str,
    proj_keys: np.ndarray,
    labels: np.ndarray,
    n_bootstrap: int,
    seed: int,
) -> dict[str, Any]:
    """Bayes error + bootstrap CI for one projection."""
    t0 = time.time()
    eps, mu_mix, n_fib, n_mixed = _fibre_bayes_stats(proj_keys, labels)

    rng = np.random.default_rng(seed)
    n = len(proj_keys)
    boot_eps: list[float] = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        e, _, _, _ = _fibre_bayes_stats(proj_keys[idx], labels[idx])
        boot_eps.append(e)
    arr = np.array(boot_eps)
    dt = time.time() - t0
    print(f"  [{proj_name}] eps={eps:.4f}  mu_mix={mu_mix:.4f}  n_fibres={n_fib}  ({dt:.1f}s)")
    return {
        "bayes_error": float(round(eps, 6)),
        "mixed_fibre_mass": float(round(mu_mix, 6)),
        "n_fibres": int(n_fib),
        "n_mixed_fibres": int(n_mixed),
        "ci95_lo": float(round(float(np.percentile(arr, 2.5)), 6)),
        "ci95_hi": float(round(float(np.percentile(arr, 97.5)), 6)),
        "bootstrap_n": n_bootstrap,
        "runtime_sec": round(dt, 2),
    }


def compute_all_projections(
    episodes: list[dict[str, Any]],
    n_bootstrap: int = BOOTSTRAP_N,
    seed: int = RNG_SEED,
) -> dict[str, Any]:
    """Run all 4 projections on the hard_violation label, precomputing keys once."""
    labels = np.array([hard_violation_label(ep) for ep in episodes], dtype=np.int8)
    print(f"  Label distribution: {int(labels.sum())} hard / {len(labels)} total (positive rate {labels.mean():.4f})")
    results: dict[str, Any] = {}
    for name, fn in PROJECTIONS.items():
        print(f"  Projecting pi_{name} ...")
        keys = np.array([_hash_key(fn(ep)) for ep in episodes])
        results[name] = compute_one_projection(name, keys, labels, n_bootstrap, seed)
    return results


def compute_per_type(
    episodes: list[dict[str, Any]],
    n_bootstrap: int = 200,
    seed: int = RNG_SEED,
) -> dict[str, Any]:
    """Per-coordinate Bayes error — used in the appendix per-type table."""
    coords = ("omission", "commission", "timing", "sequence", "deviation")
    label_mat = np.array([[per_type_labels(ep)[k] for k in coords] for ep in episodes], dtype=np.int8)
    out: dict[str, Any] = {}
    for name, fn in PROJECTIONS.items():
        keys = np.array([_hash_key(fn(ep)) for ep in episodes])
        per_coord: dict[str, Any] = {}
        for ci, c in enumerate(coords):
            per_coord[c] = compute_one_projection(f"{name}:{c}", keys, label_mat[:, ci], n_bootstrap, seed)
        out[name] = per_coord
    return out


# ---------------------------------------------------------------------------
# Macro rendering
# ---------------------------------------------------------------------------


_COORD_MACRO_NAME = {
    "omission": "Omit",
    "commission": "Commit",
    "timing": "Time",
    "sequence": "Seq",
    "deviation": "Dev",
}
_PROJ_MACRO_NAME = {"term": "Term", "aset": "Aset", "nord": "Nord", "nctx": "Nctx"}


def render_macros(
    results: dict[str, Any],
    n_episodes: int,
    output_path: Path,
    per_type: dict[str, Any] | None = None,
) -> None:
    """Rewrite bayes_error_macros.tex with real numbers."""

    def fmt3(x: float) -> str:
        return f"{x:.3f}"

    def fmtpct(x: float) -> str:
        return f"{x * 100:.1f}\\%"

    r = results
    lines = [
        "% Auto-generated by scripts/compute_bayes_error.py — DO NOT EDIT",
        "% Empirical Bayes error of Theorem 3.4 under four trace projections.",
        "%",
        "% Install via (already present in main_final_v17.tex):",
        "%   \\IfFileExists{../evidence_pack/theorem_v2/bayes_error_macros.tex}",
        "%     {\\input{../evidence_pack/theorem_v2/bayes_error_macros.tex}}{}",
        "",
        "% --- Empirical Bayes error per projection ---",
        f"\\providecommand{{\\bayesErrTerm}}{{{fmt3(r['term']['bayes_error'])}}}",
        f"\\providecommand{{\\bayesErrAset}}{{{fmt3(r['aset']['bayes_error'])}}}",
        f"\\providecommand{{\\bayesErrNord}}{{{fmt3(r['nord']['bayes_error'])}}}",
        f"\\providecommand{{\\bayesErrNctx}}{{{fmt3(r['nctx']['bayes_error'])}}}",
        "",
        "% --- Mixed-fibre mass (fraction of verdict-heterogeneous fibres) ---",
        f"\\providecommand{{\\bayesErrMixedFracTerm}}{{{fmtpct(r['term']['mixed_fibre_mass'])}}}",
        f"\\providecommand{{\\bayesErrMixedFracAset}}{{{fmtpct(r['aset']['mixed_fibre_mass'])}}}",
        f"\\providecommand{{\\bayesErrMixedFracNord}}{{{fmtpct(r['nord']['mixed_fibre_mass'])}}}",
        f"\\providecommand{{\\bayesErrMixedFracNctx}}{{{fmtpct(r['nctx']['mixed_fibre_mass'])}}}",
        "",
        "% --- Sample size ---",
        f"\\providecommand{{\\bayesErrNEpisodes}}{{{n_episodes:,}}}".replace(",", "{,}"),
        "",
        "% --- 95% bootstrap CI (B=1000) ---",
        f"\\providecommand{{\\bayesErrTermCI}}{{[{fmt3(r['term']['ci95_lo'])},\\,{fmt3(r['term']['ci95_hi'])}]}}",
        f"\\providecommand{{\\bayesErrAsetCI}}{{[{fmt3(r['aset']['ci95_lo'])},\\,{fmt3(r['aset']['ci95_hi'])}]}}",
        f"\\providecommand{{\\bayesErrNordCI}}{{[{fmt3(r['nord']['ci95_lo'])},\\,{fmt3(r['nord']['ci95_hi'])}]}}",
        f"\\providecommand{{\\bayesErrNctxCI}}{{[{fmt3(r['nctx']['ci95_lo'])},\\,{fmt3(r['nctx']['ci95_hi'])}]}}",
        "",
    ]
    if per_type:
        lines.append("% --- Per-coordinate Bayes error (projection x violation type) ---")
        lines.append("% Macro name: \\bayesErrCoord<Proj><Coord>  e.g. \\bayesErrCoordAsetOmit = 0.109")
        for proj in ("term", "aset", "nord", "nctx"):
            if proj not in per_type:
                continue
            for coord in ("omission", "commission", "timing", "sequence", "deviation"):
                entry = per_type[proj].get(coord)
                if not entry:
                    continue
                mname = f"bayesErrCoord{_PROJ_MACRO_NAME[proj]}{_COORD_MACRO_NAME[coord]}"
                lines.append(f"\\providecommand{{\\{mname}}}{{{fmt3(entry['bayes_error'])}}}")
                lines.append(
                    f"\\providecommand{{\\{mname}CI}}{{[{fmt3(entry['ci95_lo'])},\\,{fmt3(entry['ci95_hi'])}]}}"
                )
        lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    print(f"  Saved: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run Bayes-error computation on CGA-Bench corpus and emit macros + JSON."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", type=int, default=BOOTSTRAP_N)
    parser.add_argument("--per-type", action="store_true", help="Also compute per-coordinate Bayes errors (slower)")
    parser.add_argument("--per-type-bootstrap", type=int, default=200)
    args = parser.parse_args()

    print("Loading cached episodes...")
    episodes = load_cached_episodes()
    n = len(episodes)
    print(f"  Loaded {n} episodes from results/full_706_v5")
    if n == 0:
        logger.error("No episodes found — aborting")
        return 1

    print(f"\nComputing Bayes error with B={args.bootstrap} bootstrap samples...")
    results = compute_all_projections(episodes, n_bootstrap=args.bootstrap)

    per_type: dict[str, Any] = {}
    if args.per_type:
        print(f"\nComputing per-coordinate Bayes error (B={args.per_type_bootstrap})...")
        per_type = compute_per_type(episodes, n_bootstrap=args.per_type_bootstrap)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUTPUT_DIR / "bayes_error_results.json"
    payload = {
        "experiment": "Theorem 3.4 v2: empirical Bayes-error estimator",
        "n_episodes": n,
        "bootstrap_n": args.bootstrap,
        "rng_seed": RNG_SEED,
        "timestamp_bin_min": TIMESTAMP_BIN_MIN,
        "label": "hard_violation (commission|timing|sequence)",
        "projections": list(PROJECTIONS.keys()),
        "results": results,
        "per_type": per_type,
    }
    with open(out_json, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n  Saved: {out_json}")

    render_macros(results, n, OUTPUT_DIR / "bayes_error_macros.tex", per_type=per_type)

    print("\n" + "=" * 70)
    print("BAYES ERROR SUMMARY")
    print("=" * 70)
    print(f"  {'proj':<10} {'eps*':>7} {'mu_mix':>9} {'n_fibres':>10} {'CI95':>22}")
    for name, r in results.items():
        ci = f"[{r['ci95_lo']:.3f}, {r['ci95_hi']:.3f}]"
        print(f"  pi_{name:<7} {r['bayes_error']:>7.4f} {r['mixed_fibre_mass']:>9.4f} {r['n_fibres']:>10} {ci:>22}")
    print()
    ordering = sorted(results.items(), key=lambda kv: -kv[1]["bayes_error"])
    rank_str = " > ".join(f"{n}={r['bayes_error']:.3f}" for n, r in ordering)
    print(f"  Ordering (descending): {rank_str}")
    expected = "term > nctx > aset ~ nord"
    print(f"  Expected (per README): {expected}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
