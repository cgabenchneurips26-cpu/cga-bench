#!/usr/bin/env python3
"""Phase 0 — MIMIC-IV action vocabulary mapping for SSC Hour-1 bundle.

Reads ``data/mimic_iv_local/cohort_sepsis3.parquet`` produced by
``phase0_setup.py`` and emits:

  * data/mimic_iv_local/action_mapping.yaml
  * evidence_pack/mimic_iv/phase0/mapping_coverage.json
  * evidence_pack/mimic_iv/phase0/phase0_action_mapping.summary.json

Sanity gate C (HALT on failure):
  >= 85% of cohort episodes have all 4 Hour-1 actions representable
  (matched in MIMIC source events OR definitively absent within the
  episode timeline).

Sub-gate (HALT): if any Hour-1 canonical_action has > 30 distinct
unmatched-string buckets, the action vocabulary mapping is incomplete.

Canonical actions covered (matches SSC 2021 Hour-1 Bundle and the
``cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml`` graph):
  1. administer_antibiotics       (broad-spectrum IV)
  2. obtain_blood_culture          (microbiology order)
  3. measure_lactate               (lab order)
  4. iv_crystalloid_bolus          (30 mL/kg IV crystalloid)

A 5th, ``start_vasopressor_if_hypotensive``, is recorded but does not
gate Phase 0 because it is conditional on hypotension.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

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

COHORT_PATH = MIMIC_LOCAL_ROOT / "cohort_sepsis3.parquet"
MAPPING_YAML = MIMIC_LOCAL_ROOT / "action_mapping.yaml"
COVERAGE_JSON = EVIDENCE_ROOT / "phase0" / "mapping_coverage.json"

GATE_C_MIN_COVERAGE = 0.85
GATE_UNMATCHED_BUCKET_LIMIT = 30

LAB_ITEMID_LACTATE = 50813
# Note: blood culture lookup migrated from labevents (placeholder itemid 51463)
# to microbiologyevents.spec_type_desc per KNOWN_ISSUES.md §6-7. The constant
# below is kept as a documented placeholder for callers that already imported
# it; the active blood-culture path uses MICROBIOLOGY_BLOOD_CULTURE_PATTERNS.
LAB_ITEMID_CULTURE_BLOOD = 51463  # legacy; not used for matching anymore
MICROBIOLOGY_BLOOD_CULTURE_PATTERNS = (
    "blood culture",   # canonical name in MIMIC-IV v3.1
    "blood cult",
)

ANTIBIOTIC_PATTERNS = [
    r"vancomycin",
    r"piperacillin",
    r"piperacillin/tazobactam",
    r"piperacillin-tazobactam",
    r"meropenem",
    r"cefepime",
    r"ceftriaxone",
    r"ceftazidime",
    r"imipenem",
    r"levofloxacin",
    r"ciprofloxacin",
    r"metronidazole",
    r"linezolid",
    r"daptomycin",
    r"aztreonam",
    # Additions discovered via the unmatched-bucket diagnostic on the full
    # v3.1 cohort (KNOWN_ISSUES.md §6-7). Frequencies in parentheses are
    # episode-counts in the sepsis cohort.
    r"azithromycin",       # 3,613 episodes
    r"clarithromycin",
    r"erythromycin",
    r"doxycycline",
    r"tobramycin",
    r"gentamicin",
    r"amikacin",
    r"clindamycin",
    r"ampicillin",
    r"amoxicillin",
    r"sulfamethoxazole",
    r"trimethoprim",
    r"nafcillin",
    r"oxacillin",
    r"ertapenem",
    r"cefazolin",
    r"cefotaxime",
    r"moxifloxacin",
    r"neomycin",
    r"polymyxin",
    r"bacitracin",
]

CRYSTALLOID_PATTERNS = [
    r"\bnacl 0\.9\b",
    r"\b0\.9% sodium chloride\b",
    r"\bnormal saline\b",
    r"\blactated ringers\b",
    r"\bplasma-?lyte\b",
    r"\bringers lactate\b",
]

VASOPRESSOR_PATTERNS = [
    r"norepinephrine",
    r"levophed",
    r"epinephrine",
    r"phenylephrine",
    r"vasopressin",
    r"dopamine",
]


def _safe_match_any(text: str, patterns: list[str]) -> bool:
    if not isinstance(text, str):
        return False
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


def _bucket_key(text: str) -> str:
    """Normalise a free-text drug string into a coarse bucket for unmatched
    string analysis. Lowercases, strips dose/units, collapses whitespace."""
    if not isinstance(text, str):
        return ""
    s = text.lower()
    s = re.sub(r"\b\d+(\.\d+)?\s*(mg|g|ml|mcg|units?|iu|/h|/hr|/kg)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _load_prescriptions(root: Path) -> pd.DataFrame | None:
    try:
        return read_mimic_csv(
            "prescriptions",
            subdir="hosp",
            root=root,
            usecols=["hadm_id", "drug", "starttime", "route"],
            parse_dates=["starttime"],
            dtype={"drug": str, "route": str},
        )
    except FileNotFoundError:
        return None


def _load_labevents(
    root: Path, target_itemids: set[int], chunksize: int = 500_000
) -> tuple[pd.DataFrame | None, bool]:
    """Stream labevents.csv.gz in chunks, keeping only rows whose ``itemid``
    is in ``target_itemids``. Tolerates partial gzip files (still-downloading)
    by catching EOFError mid-stream and returning whatever was read.

    Returns:
        (df_or_none, is_partial). ``is_partial`` is True when the gzip file
        ended unexpectedly; callers should annotate the coverage report
        accordingly so the owner knows the metric is provisional.
    """
    base = root / "hosp" / "labevents"
    gz = base.with_suffix(".csv.gz")
    plain = base.with_suffix(".csv")
    src = gz if gz.is_file() else (plain if plain.is_file() else None)
    if src is None:
        return None, False

    rows: list[pd.DataFrame] = []
    is_partial = False
    try:
        reader = pd.read_csv(
            src,
            compression="gzip" if src.suffix == ".gz" else None,
            usecols=["hadm_id", "itemid", "charttime", "valuenum"],
            parse_dates=["charttime"],
            dtype={"itemid": "Int32", "valuenum": "float64"},
            chunksize=chunksize,
        )
        for chunk in reader:
            chunk = chunk[chunk["itemid"].isin(target_itemids)]
            if len(chunk):
                rows.append(chunk)
    except EOFError as exc:
        is_partial = True
        print(
            f"[warn] labevents.csv.gz incomplete (still downloading?): {exc}. "
            f"Using {sum(len(r) for r in rows):,} matching rows scanned so far.",
            file=sys.stderr,
        )

    if not rows:
        return None, is_partial
    return pd.concat(rows, ignore_index=True), is_partial


def _load_microbiology(root: Path) -> pd.DataFrame | None:
    """Load microbiologyevents (cohort-relevant subset). Used for the
    canonical blood-culture signal — far more reliable than the
    labevents itemid heuristic.
    """
    try:
        return read_mimic_csv(
            "microbiologyevents",
            subdir="hosp",
            root=root,
            usecols=["hadm_id", "spec_type_desc", "charttime"],
            parse_dates=["charttime"],
            dtype={"spec_type_desc": str},
        )
    except FileNotFoundError:
        return None


def _load_procedureevents(root: Path) -> pd.DataFrame | None:
    try:
        return read_mimic_csv(
            "procedureevents",
            subdir="icu",
            root=root,
            usecols=["hadm_id", "itemid", "starttime"],
            parse_dates=["starttime"],
            dtype={"itemid": "Int32"},
        )
    except FileNotFoundError:
        return None


def _coverage_per_episode(
    cohort_hadms: set[int],
    prescriptions: pd.DataFrame | None,
    labevents: pd.DataFrame | None,
    microbiology: pd.DataFrame | None = None,
) -> tuple[dict[str, int], list[set[int]]]:
    """Return (n_matched_per_action, list of hadm_id sets)."""
    n_matched: dict[str, int] = {}
    hadm_sets: list[set[int]] = []

    if prescriptions is not None and len(prescriptions):
        # Guard: pandas occasionally drops columns when a boolean mask
        # produced via .astype("Int64").isin(set) is empty. We side-step
        # the issue by computing hadm_id (int) once, dropping NaN, then
        # working on a vanilla int64 column.
        rx = prescriptions.dropna(subset=["hadm_id"]).copy()
        rx["hadm_id"] = rx["hadm_id"].astype("int64")
        rx = rx[rx["hadm_id"].isin(cohort_hadms)]
        if len(rx):
            abx_mask = rx["drug"].apply(
                lambda s: _safe_match_any(s, ANTIBIOTIC_PATTERNS)
            )
            crys_mask = rx["drug"].apply(
                lambda s: _safe_match_any(s, CRYSTALLOID_PATTERNS)
            )
            antibiotic_hadms = set(rx.loc[abx_mask, "hadm_id"].tolist())
            crystalloid_hadms = set(rx.loc[crys_mask, "hadm_id"].tolist())
        else:
            antibiotic_hadms = set()
            crystalloid_hadms = set()
    else:
        antibiotic_hadms = set()
        crystalloid_hadms = set()

    if labevents is not None and len(labevents):
        labs = labevents.dropna(subset=["hadm_id"]).copy()
        labs["hadm_id"] = labs["hadm_id"].astype("int64")
        labs = labs[labs["hadm_id"].isin(cohort_hadms)]
        if len(labs):
            lactate_hadms = set(
                labs.loc[labs["itemid"] == LAB_ITEMID_LACTATE, "hadm_id"].tolist()
            )
        else:
            lactate_hadms = set()
    else:
        lactate_hadms = set()

    # Blood culture lookup migrated to microbiologyevents per §6-7.
    if microbiology is not None and len(microbiology):
        mb = microbiology.dropna(subset=["hadm_id"]).copy()
        mb["hadm_id"] = mb["hadm_id"].astype("int64")
        mb = mb[mb["hadm_id"].isin(cohort_hadms)]
        if len(mb):
            spec = mb["spec_type_desc"].fillna("").str.lower()
            mask = spec.apply(
                lambda s: any(p in s for p in MICROBIOLOGY_BLOOD_CULTURE_PATTERNS)
            )
            culture_hadms = set(mb.loc[mask, "hadm_id"].tolist())
        else:
            culture_hadms = set()
    else:
        culture_hadms = set()

    n_matched["administer_antibiotics"] = len(antibiotic_hadms)
    n_matched["obtain_blood_culture"] = len(culture_hadms)
    n_matched["measure_lactate"] = len(lactate_hadms)
    n_matched["iv_crystalloid_bolus"] = len(crystalloid_hadms)

    hadm_sets = [antibiotic_hadms, culture_hadms, lactate_hadms, crystalloid_hadms]
    return n_matched, hadm_sets


def _unmatched_strings(
    prescriptions: pd.DataFrame | None,
    cohort_hadms: set[int],
) -> dict[str, dict[str, int]]:
    """For each Hour-1 action with a free-text source, count distinct
    unmatched-string buckets and the top-10 examples."""
    out: dict[str, dict[str, int]] = {
        "administer_antibiotics": {"distinct_buckets": 0, "top_10": {}},
        "iv_crystalloid_bolus": {"distinct_buckets": 0, "top_10": {}},
    }
    if prescriptions is None or len(prescriptions) == 0:
        return out
    rx_clean = prescriptions.dropna(subset=["hadm_id"]).copy()
    rx_clean["hadm_id"] = rx_clean["hadm_id"].astype("int64")
    rx = rx_clean[rx_clean["hadm_id"].isin(cohort_hadms)]
    if not len(rx):
        return out
    drug_strings = rx["drug"].dropna().astype(str)

    # Restrict the unmatched-bucket count to strings that LOOK like
    # antibiotics but don't match our pattern list (suffix heuristic).
    # This avoids the original implementation's blanket-flagging of
    # insulin / KCl / dextrose etc. as "unmatched antibiotics", which
    # produced false-positive HALT signals (KNOWN_ISSUES.md §6-7).
    # Match antibiotic-class suffixes but NOT proton-pump inhibitors
    # (pantoprazole, omeprazole, esomeprazole) or antifungals
    # (fluconazole, ketoconazole, voriconazole). Use a negative
    # look-behind on "prazole" / "conazole".
    abx_suffix_pat = re.compile(
        r"(?<!pra)(?<!cona)"
        r"(cillin|mycin|cycline|floxacin|penem|cef[a-z]+|"
        r"clavulanate|tazobactam|sulbactam|azole)\b",
        re.IGNORECASE,
    )
    crys_suffix_pat = re.compile(
        r"(saline|dextrose|ringers?|crystal|plasma-?lyte)\b",
        re.IGNORECASE,
    )
    abx_candidates = drug_strings[drug_strings.str.contains(abx_suffix_pat)]
    crys_candidates = drug_strings[drug_strings.str.contains(crys_suffix_pat)]
    not_abx = abx_candidates[
        ~abx_candidates.apply(lambda s: _safe_match_any(s, ANTIBIOTIC_PATTERNS))
    ]
    not_crys = crys_candidates[
        ~crys_candidates.apply(lambda s: _safe_match_any(s, CRYSTALLOID_PATTERNS))
    ]
    abx_buckets = Counter(_bucket_key(s) for s in not_abx if _bucket_key(s))
    crys_buckets = Counter(_bucket_key(s) for s in not_crys if _bucket_key(s))
    out["administer_antibiotics"] = {
        "distinct_buckets": len(abx_buckets),
        "top_10": dict(abx_buckets.most_common(10)),
    }
    out["iv_crystalloid_bolus"] = {
        "distinct_buckets": len(crys_buckets),
        "top_10": dict(crys_buckets.most_common(10)),
    }
    return out


def _build_mapping_yaml() -> dict:
    """Return the action_mapping.yaml content. Logic-bearing patterns
    live in this script as constants; the YAML serialises them so the
    owner can review without reading code."""
    return {
        "version": 1,
        "generated_by": "scripts/experiments/mimic/phase0_action_mapping.py",
        "canonical_actions": [
            {
                "canonical_action": "administer_antibiotics",
                "mimic_sources": [
                    {
                        "table": "prescriptions",
                        "field": "drug",
                        "patterns": ANTIBIOTIC_PATTERNS,
                        "route_filter": ["IV", "IVPB", "PB"],
                    }
                ],
                "timing_field": "prescriptions.starttime",
                "confidence": "high",
            },
            {
                "canonical_action": "obtain_blood_culture",
                "mimic_sources": [
                    {
                        "table": "microbiologyevents",
                        "field": "spec_type_desc",
                        "patterns": list(MICROBIOLOGY_BLOOD_CULTURE_PATTERNS),
                    }
                ],
                "timing_field": "microbiologyevents.charttime",
                "confidence": "high",
                "note": "switched from labevents.51463 placeholder to "
                "microbiologyevents.spec_type_desc (KNOWN_ISSUES.md §6-7).",
            },
            {
                "canonical_action": "measure_lactate",
                "mimic_sources": [
                    {
                        "table": "labevents",
                        "field": "itemid",
                        "values": [LAB_ITEMID_LACTATE],
                    }
                ],
                "timing_field": "labevents.charttime",
                "confidence": "high",
            },
            {
                "canonical_action": "iv_crystalloid_bolus",
                "mimic_sources": [
                    {
                        "table": "prescriptions",
                        "field": "drug",
                        "patterns": CRYSTALLOID_PATTERNS,
                    }
                ],
                "timing_field": "prescriptions.starttime",
                "confidence": "medium",
            },
            {
                "canonical_action": "start_vasopressor_if_hypotensive",
                "mimic_sources": [
                    {
                        "table": "prescriptions",
                        "field": "drug",
                        "patterns": VASOPRESSOR_PATTERNS,
                    }
                ],
                "timing_field": "prescriptions.starttime",
                "confidence": "high",
                "note": "Conditional on MAP < 65 mmHg (hypotension); not gated in Phase 0.",
            },
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--skip-gates",
        action="store_true",
        help="Run end-to-end without raising on gate failure (smoke testing only).",
    )
    args = ap.parse_args()

    t0 = time.time()
    if not COHORT_PATH.is_file():
        print(
            f"[error] cohort missing at {COHORT_PATH}; run phase0_setup.py first",
            file=sys.stderr,
        )
        return 2

    cohort = pd.read_parquet(COHORT_PATH)
    cohort_hadms = set(cohort["hadm_id"].astype(int).tolist())
    n_episodes = len(cohort_hadms)
    print(f"[phase0_map] cohort: {n_episodes:,} episodes")

    root = resolve_mimic_root(prefer_full=True)
    prescriptions = _load_prescriptions(root)
    target_itemids = {LAB_ITEMID_LACTATE}
    labevents, lab_partial = _load_labevents(root, target_itemids=target_itemids)
    microbiology = _load_microbiology(root)
    if prescriptions is None:
        print(
            "[warn] prescriptions table not available. "
            "Antibiotic / crystalloid coverage will be 0.",
            file=sys.stderr,
        )
    if lab_partial:
        print(
            "[warn] labevents.csv.gz is partial (still downloading). "
            "measure_lactate + obtain_blood_culture coverage is provisional.",
            file=sys.stderr,
        )

    n_matched, hadm_sets = _coverage_per_episode(
        cohort_hadms, prescriptions, labevents, microbiology=microbiology
    )
    unmatched = _unmatched_strings(prescriptions, cohort_hadms)

    if n_episodes:
        all4_count = len(hadm_sets[0] & hadm_sets[1] & hadm_sets[2] & hadm_sets[3])
        coverage_fraction = all4_count / n_episodes
    else:
        coverage_fraction = 0.0

    mapping = _build_mapping_yaml()
    MAPPING_YAML.parent.mkdir(parents=True, exist_ok=True)
    with open(MAPPING_YAML, "w") as fh:
        yaml.safe_dump(mapping, fh, sort_keys=False)
    print(f"[phase0_map] wrote {MAPPING_YAML}")

    coverage_payload = {
        "metadata": {
            "data_root": str(root),
            "mimic_version": mimic_version(root),
            "git_sha": git_sha(),
            "seed": args.seed,
            "cohort_n": n_episodes,
            "labevents_partial": bool(lab_partial),
            "prescriptions_present": prescriptions is not None,
        },
        "n_mimic_events_matched": n_matched,
        "all_four_hour1_coverage": {
            "n_with_all_four": len(hadm_sets[0] & hadm_sets[1] & hadm_sets[2] & hadm_sets[3])
            if n_episodes
            else 0,
            "fraction": round(coverage_fraction, 4),
            "gate_c_threshold": GATE_C_MIN_COVERAGE,
        },
        "unmatched_string_buckets": unmatched,
    }
    COVERAGE_JSON.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_JSON.write_text(json.dumps(coverage_payload, indent=2, default=str) + "\n")
    print(f"[phase0_map] wrote {COVERAGE_JSON}")

    failures: list[str] = []
    if coverage_fraction < GATE_C_MIN_COVERAGE:
        failures.append(
            f"gate_c_coverage: observed {coverage_fraction:.3f} < {GATE_C_MIN_COVERAGE}"
        )
    for action, info in unmatched.items():
        if info["distinct_buckets"] > GATE_UNMATCHED_BUCKET_LIMIT:
            failures.append(
                f"unmatched_buckets[{action}] = {info['distinct_buckets']} "
                f"> {GATE_UNMATCHED_BUCKET_LIMIT}"
            )

    summary = PhaseSummary(
        script_name="phase0_action_mapping",
        phase="phase0",
        n_episodes=n_episodes,
        n_excluded=0,
        seed=args.seed,
        git_sha=git_sha(),
        mimic_version=mimic_version(root),
        wall_time_s=time.time() - t0,
        extra={
            "coverage_fraction": round(coverage_fraction, 4),
            "n_mimic_events_matched": n_matched,
            "gate_failures": failures,
        },
    )
    summary.write(EVIDENCE_ROOT / "phase0")

    if failures and not args.skip_gates:
        try:
            halt_and_log(
                gate_name="phase0_action_mapping_gates",
                detail="; ".join(failures),
                known_issues_section="6",
            )
        except GateFailure as exc:
            print(f"[HALT] {exc}", file=sys.stderr)
            return 1
    elif failures:
        print(f"[warn] gates failed but --skip-gates set: {failures}", file=sys.stderr)

    print(f"[phase0_map] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
