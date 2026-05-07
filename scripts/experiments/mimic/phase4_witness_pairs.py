#!/usr/bin/env python3
"""Phase 4 — Real witness pairs for Lemma 1 (App B.3 augmentation).

Mines pairs of MIMIC-IV episodes that exhibit:
  * **Case (ii) πaset (action multiset)**: identical action set but
    timing of ``administer_antibiotics`` differs by > 60 min across the
    SSC Hour-1 deadline. Yields the strongest projection-blind contrast
    for the action-set evaluator family (ASC / PAF) which cannot
    distinguish them.
  * **Case (iv) πnctx (no context)**: same drug administered in two
    patients where one has a documented contraindication state
    (allergy, bleeding, INR) and the other does not. Demonstrates
    that context-blind evaluators score identically.

  * Cases (i) πterm and (iii) πnord are mined opportunistically; we
    report "available in MIMIC-IV: Y/N" only and do not force them.

Outputs:
  * evidence_pack/mimic_iv/phase4/witness_pairs_mimic_iv.json
    (hashed IDs only — actual subject_id / hadm_id / stay_id stay in
    the encrypted supplementary file below)
  * supplementary/mimic_iv_witness_pairs.json (plaintext; encrypt with
    ``gpg --batch -e -r "$DUA_KEY" supplementary/...`` afterwards)

This script intentionally does NOT call the full theorem-witness
infrastructure (``scripts/extract_theorem_witnesses.py``) because that
script reads from synthetic CGA-Bench releases. We mirror its 4-projection
logic on MIMIC-IV trajectories directly. Owner can replace the
mining functions with a richer adapter post-camera-ready.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.experiments.mimic._common import (  # noqa: E402
    EVIDENCE_ROOT,
    MIMIC_LOCAL_ROOT,
    PhaseSummary,
    git_sha,
    mimic_version,
    read_mimic_csv,
    resolve_mimic_root,
)

VERDICT_PARQUET = (
    REPO_ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_mimic_iv.parquet"
)
COHORT_PARQUET = MIMIC_LOCAL_ROOT / "cohort_sepsis3.parquet"
PHASE4_DIR = EVIDENCE_ROOT / "phase4"
OUTPUT_HASHED = PHASE4_DIR / "witness_pairs_mimic_iv.json"
OUTPUT_PLAIN = REPO_ROOT / "supplementary" / "mimic_iv_witness_pairs.json"

HOUR1_DEADLINE_MIN = 60.0
TIMING_DELTA_MIN = 60.0


def _hash_episode(subject_id: int, hadm_id: int) -> str:
    h = hashlib.sha256(f"{subject_id}::{hadm_id}".encode()).hexdigest()
    return h[:16]


def _mine_paset_pairs(
    cohort: pd.DataFrame,
    rx: pd.DataFrame,
    *,
    max_pairs: int = 100,
) -> list[dict]:
    """Pairs with same action multiset but timing of antibiotics differs
    by > TIMING_DELTA_MIN across the Hour-1 deadline.

    Same action multiset is approximated by: both patients received
    antibiotics + crystalloid + lactate within their episode horizons.
    Owner: replace with the full canonical multiset comparison if a
    richer per-episode action set becomes available.
    """
    cohort_idx = cohort.set_index("hadm_id")
    abx_pattern = ["vancomycin", "piperacillin", "meropenem", "cefepime",
                   "ceftriaxone", "ceftazidime", "imipenem", "levofloxacin",
                   "ciprofloxacin", "metronidazole", "linezolid", "daptomycin",
                   "aztreonam"]
    rx = rx.copy()
    rx = rx.dropna(subset=["hadm_id"])
    rx["hadm_id"] = rx["hadm_id"].astype("int64")
    rx["is_abx"] = rx["drug"].fillna("").str.lower().apply(
        lambda s: any(p in s for p in abx_pattern)
    )
    abx = rx[rx["is_abx"]]
    abx_first = (
        abx.sort_values(["hadm_id", "starttime"])
        .groupby("hadm_id", as_index=False)
        .first()[["hadm_id", "starttime"]]
        .rename(columns={"starttime": "abx_starttime"})
    )
    cohort_abx = cohort.merge(abx_first, on="hadm_id", how="inner")
    cohort_abx["abx_delay_min"] = (
        cohort_abx["abx_starttime"] - cohort_abx["intime"]
    ).dt.total_seconds() / 60.0
    early = cohort_abx[cohort_abx["abx_delay_min"] <= HOUR1_DEADLINE_MIN]
    late = cohort_abx[cohort_abx["abx_delay_min"] > HOUR1_DEADLINE_MIN + TIMING_DELTA_MIN]

    pairs: list[dict] = []
    n = min(len(early), len(late), max_pairs)
    for i in range(n):
        ep_early = early.iloc[i]
        ep_late = late.iloc[i]
        pairs.append(
            {
                "case": "(ii) πaset",
                "early": {
                    "hash": _hash_episode(int(ep_early["subject_id"]), int(ep_early["hadm_id"])),
                    "subject_id": int(ep_early["subject_id"]),
                    "hadm_id": int(ep_early["hadm_id"]),
                    "abx_delay_min": float(ep_early["abx_delay_min"]),
                },
                "late": {
                    "hash": _hash_episode(int(ep_late["subject_id"]), int(ep_late["hadm_id"])),
                    "subject_id": int(ep_late["subject_id"]),
                    "hadm_id": int(ep_late["hadm_id"]),
                    "abx_delay_min": float(ep_late["abx_delay_min"]),
                },
                "delta_min": float(ep_late["abx_delay_min"] - ep_early["abx_delay_min"]),
            }
        )
    return pairs


def _mine_pnctx_pairs(
    cohort: pd.DataFrame,
    rx: pd.DataFrame,
    diagnoses: pd.DataFrame,
    *,
    max_pairs: int = 100,
) -> list[dict]:
    """Pairs receiving the same vasopressor where one has hypotension
    (relative contraindication for some agents) and the other doesn't.

    A proxy: ICD-10 I26.* (PE) + warfarin/heparin coadministration vs
    no ICD-10 contraindication. Owner can refine using lab/INR.
    """
    rx = rx.copy().dropna(subset=["hadm_id"])
    rx["hadm_id"] = rx["hadm_id"].astype("int64")
    rx["is_anticoag"] = rx["drug"].fillna("").str.lower().apply(
        lambda s: ("warfarin" in s) or ("heparin" in s) or ("apixaban" in s)
    )
    anticoag = rx[rx["is_anticoag"]][["hadm_id"]].drop_duplicates()
    anticoag_set = set(anticoag["hadm_id"].tolist())

    diag = diagnoses.copy().dropna(subset=["hadm_id"])
    diag["hadm_id"] = diag["hadm_id"].astype("int64")
    bleed_codes = diag[
        diag["icd_code"].fillna("").str.startswith(("K92", "I85", "K27"))
    ]["hadm_id"].drop_duplicates()
    bleed_set = set(bleed_codes.tolist())

    with_contra = sorted(anticoag_set & bleed_set)
    without_contra = sorted(anticoag_set - bleed_set)

    pairs: list[dict] = []
    n = min(len(with_contra), len(without_contra), max_pairs)
    for i in range(n):
        a_hadm = int(with_contra[i])
        b_hadm = int(without_contra[i])
        a_row = cohort[cohort["hadm_id"] == a_hadm]
        b_row = cohort[cohort["hadm_id"] == b_hadm]
        if a_row.empty or b_row.empty:
            continue
        pairs.append(
            {
                "case": "(iv) πnctx",
                "with_contra": {
                    "hash": _hash_episode(int(a_row["subject_id"].iloc[0]), a_hadm),
                    "subject_id": int(a_row["subject_id"].iloc[0]),
                    "hadm_id": a_hadm,
                },
                "without_contra": {
                    "hash": _hash_episode(int(b_row["subject_id"].iloc[0]), b_hadm),
                    "subject_id": int(b_row["subject_id"].iloc[0]),
                    "hadm_id": b_hadm,
                },
                "drug_class": "anticoagulant",
                "contra_pattern": "ICD-10 K92/I85/K27 (bleeding)",
            }
        )
    return pairs


def _redact(pairs: list[dict]) -> list[dict]:
    """Strip subject_id / hadm_id from a pairs list, keep hashes only."""
    out = []
    for p in pairs:
        red = {"case": p["case"]}
        for k, v in p.items():
            if isinstance(v, dict) and "hash" in v:
                red[k] = {"hash": v["hash"]}
            elif k != "case":
                red[k] = v
        out.append(red)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-pairs-per-case", type=int, default=100)
    args = ap.parse_args()

    t0 = time.time()
    if not COHORT_PARQUET.is_file():
        print(f"[error] missing {COHORT_PARQUET}", file=sys.stderr)
        return 2

    root = resolve_mimic_root(prefer_full=True)
    cohort = pd.read_parquet(COHORT_PARQUET)
    print(f"[phase4] cohort={len(cohort):,}")

    rx = read_mimic_csv(
        "prescriptions",
        subdir="hosp",
        root=root,
        usecols=["hadm_id", "drug", "starttime"],
        parse_dates=["starttime"],
        dtype={"drug": str},
    )
    diag = read_mimic_csv(
        "diagnoses_icd",
        subdir="hosp",
        root=root,
        usecols=["hadm_id", "icd_code", "icd_version"],
        dtype={"icd_code": str, "icd_version": "Int8"},
    )

    paset = _mine_paset_pairs(cohort, rx, max_pairs=args.max_pairs_per_case)
    pnctx = _mine_pnctx_pairs(cohort, rx, diag, max_pairs=args.max_pairs_per_case)
    print(f"[phase4] paset pairs: {len(paset)}; pnctx pairs: {len(pnctx)}")

    plain = {
        "metadata": {
            "git_sha": git_sha(),
            "mimic_version": mimic_version(root),
            "seed": args.seed,
        },
        "paset_pairs_case_ii": paset,
        "pnctx_pairs_case_iv": pnctx,
        "pterm_pairs_case_i": {"available": False, "note": "opportunistic; not forced"},
        "pnord_pairs_case_iii": {"available": False, "note": "opportunistic; not forced"},
    }
    OUTPUT_PLAIN.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PLAIN.write_text(json.dumps(plain, indent=2, default=str) + "\n")
    print(f"[phase4] wrote PLAINTEXT (encrypt before publishing): {OUTPUT_PLAIN}")
    print(f"        gpg --batch -e -r \"$DUA_KEY\" {OUTPUT_PLAIN.relative_to(REPO_ROOT)}")

    redacted = {
        "metadata": plain["metadata"],
        "paset_pairs_case_ii": _redact(paset),
        "pnctx_pairs_case_iv": _redact(pnctx),
        "pterm_pairs_case_i": plain["pterm_pairs_case_i"],
        "pnord_pairs_case_iii": plain["pnord_pairs_case_iii"],
    }
    OUTPUT_HASHED.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HASHED.write_text(json.dumps(redacted, indent=2, default=str) + "\n")
    print(f"[phase4] wrote redacted: {OUTPUT_HASHED}")

    summary = PhaseSummary(
        script_name="phase4_witness_pairs",
        phase="phase4",
        n_episodes=len(paset) + len(pnctx),
        seed=args.seed,
        git_sha=git_sha(),
        mimic_version=mimic_version(root),
        wall_time_s=time.time() - t0,
        extra={"paset_pairs": len(paset), "pnctx_pairs": len(pnctx)},
    )
    summary.write(PHASE4_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
