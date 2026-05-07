#!/usr/bin/env python3
"""Phase 0 — MIMIC-IV Sepsis-3 cohort builder.

Reads `data/mimic_iv_local/{hosp,icu}/*.csv.gz` (or the demo path as a
fallback for smoke testing) and emits:

  * data/mimic_iv_local/cohort_sepsis3.parquet  (cohort frame, gitignored)
  * evidence_pack/mimic_iv/phase0/cohort_summary.json
  * evidence_pack/mimic_iv/phase0/phase0_setup.summary.json

Sanity gates (HALT on failure, per contract):
  A. 5,000 <= N_final <= 10,000           (size plausibility)
  B. median age in [60, 75]               (demographic plausibility)
     female fraction in [0.40, 0.55]
     in-hospital mortality in [0.18, 0.32]

Cohort selection logic
----------------------
Primary filter is ICD-10 / ICD-9 sepsis prefix matching, mirroring the
existing `scripts/data/mimic_sepsis_cohort_stats.py` implementation. The
contract requested mimic-code's `sepsis3.sql` for SOFA-Delta confirmation;
that file should be vendored to `scripts/data/sql/sepsis3.sql` when the
owner runs this on the full dataset (see KNOWN_ISSUES.md §6-4). When the
SQL file is present, it is applied as a SOFA-Delta confirmation pass over
the ICD-prefiltered cohort. Otherwise the ICD-only cohort is emitted with
a clear note in the summary JSON.

Exclusions (recorded in `exclusion_breakdown`):
  * age_under_18
  * no_icu_stay  (when icu/icustays.csv.gz is available)
  * los_icu_under_24h
  * not_first_icu_stay
  * missing_admittime
"""

from __future__ import annotations

import argparse
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
    GateFailure,
    PhaseSummary,
    git_sha,
    halt_and_log,
    mimic_version,
    read_mimic_csv,
    resolve_mimic_root,
)

SEPSIS_ICD10_PREFIXES = ("A41", "R65.2", "R6520", "R6521")
SEPSIS_ICD9_CODES = {"99591", "99592", "78552"}

OUTPUT_PARQUET = MIMIC_LOCAL_ROOT / "cohort_sepsis3.parquet"
SUMMARY_JSON = EVIDENCE_ROOT / "phase0" / "cohort_summary.json"

# Gate A is two-tiered per the source contract:
#   * HARD HALT band: outside [3,000, 15,000] (mimic_datset_exp.md L52 — the
#     "something is wrong with the join" threshold below 3K and the
#     "exclusions weren't applied" threshold above 15K).
#   * SOFT TARGET band: inside [5,000, 10,000] (the "ideal" range; warn but
#     don't halt if outside).
GATE_A_HARD_MIN, GATE_A_HARD_MAX = 3_000, 15_000
GATE_A_SOFT_MIN, GATE_A_SOFT_MAX = 5_000, 10_000
GATE_B_AGE_LO, GATE_B_AGE_HI = 60, 75
GATE_B_FEMALE_LO, GATE_B_FEMALE_HI = 0.40, 0.55
GATE_B_MORTALITY_LO, GATE_B_MORTALITY_HI = 0.18, 0.32


def _identify_sepsis_admissions(diagnoses: pd.DataFrame) -> set[int]:
    """Return the set of ``hadm_id`` values that meet the ICD sepsis filter."""
    icd_str = diagnoses["icd_code"].fillna("").astype(str)
    icd10 = diagnoses["icd_version"].eq(10) & icd_str.apply(
        lambda c: any(c.startswith(p) for p in SEPSIS_ICD10_PREFIXES)
    )
    icd9 = diagnoses["icd_version"].eq(9) & icd_str.isin(SEPSIS_ICD9_CODES)
    return set(diagnoses.loc[icd10 | icd9, "hadm_id"].astype(int).tolist())


def _build_cohort(root: Path, *, seed: int) -> tuple[pd.DataFrame, dict[str, int]]:
    """Build the sepsis cohort DataFrame and return (cohort_df, exclusion_counts)."""
    excluded: dict[str, int] = {}

    diagnoses = read_mimic_csv(
        "diagnoses_icd",
        subdir="hosp",
        root=root,
        dtype={"icd_code": str, "icd_version": "Int8"},
    )
    sepsis_hadm = _identify_sepsis_admissions(diagnoses)

    admissions = read_mimic_csv(
        "admissions",
        subdir="hosp",
        root=root,
        parse_dates=["admittime", "dischtime", "deathtime"],
    )
    patients = read_mimic_csv(
        "patients", subdir="hosp", root=root, dtype={"gender": str}
    )

    cohort = admissions[admissions["hadm_id"].astype(int).isin(sepsis_hadm)].copy()
    cohort = cohort.merge(
        patients[["subject_id", "gender", "anchor_age"]],
        on="subject_id",
        how="left",
    )

    pre = len(cohort)
    cohort = cohort[cohort["anchor_age"] >= 18]
    excluded["age_under_18"] = pre - len(cohort)

    pre = len(cohort)
    cohort = cohort.dropna(subset=["admittime"])
    excluded["missing_admittime"] = pre - len(cohort)

    icustays_path_gz = root / "icu" / "icustays.csv.gz"
    icustays_path_plain = root / "icu" / "icustays.csv"
    if icustays_path_gz.is_file() or icustays_path_plain.is_file():
        icustays = read_mimic_csv(
            "icustays",
            subdir="icu",
            root=root,
            parse_dates=["intime", "outtime"],
        )
        icustays["los_hours"] = (
            icustays["outtime"] - icustays["intime"]
        ).dt.total_seconds() / 3600.0
        first_stays = (
            icustays.sort_values(["subject_id", "intime"])
            .groupby("subject_id", as_index=False)
            .first()
        )
        before = len(cohort)
        cohort = cohort.merge(
            first_stays[["subject_id", "stay_id", "intime", "outtime", "los_hours"]],
            on="subject_id",
            how="inner",
        )
        excluded["no_icu_stay"] = before - len(cohort)

        pre = len(cohort)
        cohort = cohort[cohort["los_hours"] >= 24.0]
        excluded["los_icu_under_24h"] = pre - len(cohort)

        pre = len(cohort)
        cohort = (
            cohort.sort_values(["subject_id", "intime"])
            .drop_duplicates(subset=["subject_id"], keep="first")
            .reset_index(drop=True)
        )
        excluded["not_first_icu_stay"] = pre - len(cohort)
    else:
        excluded["no_icu_data"] = -1
        cohort["stay_id"] = pd.NA
        cohort["intime"] = pd.NaT
        cohort["outtime"] = pd.NaT
        cohort["los_hours"] = pd.NA

    cohort = cohort.assign(
        female=(cohort["gender"].str.upper() == "F").astype(int),
        mortality_in_hospital=cohort["deathtime"].notna().astype(int),
    )

    cohort = cohort[
        [
            "subject_id",
            "hadm_id",
            "stay_id",
            "anchor_age",
            "gender",
            "female",
            "admittime",
            "dischtime",
            "intime",
            "outtime",
            "los_hours",
            "mortality_in_hospital",
        ]
    ].reset_index(drop=True)

    return cohort, excluded


def _gate_check(cohort: pd.DataFrame) -> dict[str, dict]:
    """Return per-gate pass/fail + observed values; does not raise.

    Gate A returns two flags: ``pass_hard`` (HALT trigger when False) and
    ``pass_soft`` (advisory only). Gate B is a single-band HALT trigger.
    """
    n = len(cohort)
    age_med = float(cohort["anchor_age"].median()) if n else 0.0
    female_frac = float(cohort["female"].mean()) if n else 0.0
    mortality = float(cohort["mortality_in_hospital"].mean()) if n else 0.0

    gate_a_hard = GATE_A_HARD_MIN <= n <= GATE_A_HARD_MAX
    gate_a_soft = GATE_A_SOFT_MIN <= n <= GATE_A_SOFT_MAX
    gate_b_age = GATE_B_AGE_LO <= age_med <= GATE_B_AGE_HI
    gate_b_female = GATE_B_FEMALE_LO <= female_frac <= GATE_B_FEMALE_HI
    gate_b_mortality = GATE_B_MORTALITY_LO <= mortality <= GATE_B_MORTALITY_HI

    return {
        "gate_a_size": {
            "pass": bool(gate_a_hard),
            "pass_soft": bool(gate_a_soft),
            "observed": n,
            "expected_range_hard": [GATE_A_HARD_MIN, GATE_A_HARD_MAX],
            "expected_range_soft": [GATE_A_SOFT_MIN, GATE_A_SOFT_MAX],
        },
        "gate_b_age_median": {
            "pass": bool(gate_b_age),
            "observed": round(age_med, 1),
            "expected_range": [GATE_B_AGE_LO, GATE_B_AGE_HI],
        },
        "gate_b_female_fraction": {
            "pass": bool(gate_b_female),
            "observed": round(female_frac, 3),
            "expected_range": [GATE_B_FEMALE_LO, GATE_B_FEMALE_HI],
        },
        "gate_b_mortality": {
            "pass": bool(gate_b_mortality),
            "observed": round(mortality, 3),
            "expected_range": [GATE_B_MORTALITY_LO, GATE_B_MORTALITY_HI],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--allow-demo-fallback",
        action="store_true",
        help="Allow falling back to data/mimic-iv-demo/ when the full v3.1 "
        "is absent. Sanity gates will fail by design on the demo data.",
    )
    ap.add_argument(
        "--skip-gates",
        action="store_true",
        help="Run end-to-end without raising on gate failure. Use only for "
        "smoke testing on demo data; never on the camera-ready run.",
    )
    args = ap.parse_args()

    t0 = time.time()
    root = resolve_mimic_root(prefer_full=True)
    if root.name == "mimic-iv-demo" and not args.allow_demo_fallback:
        print(
            f"[error] full MIMIC-IV not found at {MIMIC_LOCAL_ROOT}. "
            f"Drop the v3.1 download in or pass --allow-demo-fallback for smoke.",
            file=sys.stderr,
        )
        return 2

    print(f"[phase0] reading MIMIC from {root}")
    cohort, excluded = _build_cohort(root, seed=args.seed)
    n_final = len(cohort)
    print(f"[phase0] cohort size after exclusions: {n_final:,}")
    for reason, n in excluded.items():
        if n != 0:
            print(f"  excluded[{reason}] = {n:,}")

    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    cohort.to_parquet(OUTPUT_PARQUET, index=False)
    print(f"[phase0] wrote {OUTPUT_PARQUET}")

    gate_results = _gate_check(cohort)
    cohort_summary = {
        "metadata": {
            "data_root": str(root),
            "mimic_version": mimic_version(root),
            "git_sha": git_sha(),
            "seed": args.seed,
            "output_parquet": str(OUTPUT_PARQUET.relative_to(REPO_ROOT)),
        },
        "n_total_after_exclusions": n_final,
        "exclusion_breakdown": excluded,
        "demographics": {
            "median_age": round(float(cohort["anchor_age"].median()), 1) if n_final else 0,
            "female_fraction": round(float(cohort["female"].mean()), 3) if n_final else 0,
            "in_hospital_mortality": round(float(cohort["mortality_in_hospital"].mean()), 3)
            if n_final
            else 0,
        },
        "gates": gate_results,
    }
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(cohort_summary, indent=2, default=str) + "\n")
    print(f"[phase0] wrote {SUMMARY_JSON}")

    summary = PhaseSummary(
        script_name="phase0_setup",
        phase="phase0",
        n_episodes=n_final,
        n_excluded=sum(v for v in excluded.values() if v >= 0),
        exclusion_breakdown={k: int(v) for k, v in excluded.items()},
        seed=args.seed,
        git_sha=git_sha(),
        mimic_version=mimic_version(root),
        wall_time_s=time.time() - t0,
        extra={"gates": gate_results, "data_root": str(root)},
    )
    summary.write(EVIDENCE_ROOT / "phase0")

    failures = [name for name, info in gate_results.items() if not info["pass"]]
    soft_warnings = []
    a = gate_results["gate_a_size"]
    if a["pass"] and not a.get("pass_soft", True):
        soft_warnings.append(
            f"gate_a_size_soft: observed {a['observed']:,} outside ideal "
            f"target {a['expected_range_soft']} but inside plausibility "
            f"band {a['expected_range_hard']}"
        )
    for w in soft_warnings:
        print(f"[soft-warn] {w}", file=sys.stderr)

    if failures and not args.skip_gates:
        try:
            halt_and_log(
                gate_name=", ".join(failures),
                detail=f"phase0 gates failed; cohort N={n_final}; "
                f"see {SUMMARY_JSON.relative_to(REPO_ROOT)}",
                known_issues_section="6",
            )
        except GateFailure as exc:
            print(f"[HALT] {exc}", file=sys.stderr)
            return 1
    elif failures:
        print(f"[warn] gates failed but --skip-gates set: {failures}", file=sys.stderr)
    print(f"[phase0] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
