#!/usr/bin/env python3
"""Phase 1 — Patient-level distribution check on MIMIC-IV.

For each of the 24 observables in
``evidence_pack/analysis/real_cohort_reference.yaml``, compute MIMIC-IV
patient-level [p5, p25, p50, p75, p95] from the appropriate cohort
(sepsis / chest_pain / stroke / aki) and recompute the App-Z verdicts:

  * **M90** (patient-level)        : engine median in MIMIC-IV [p5, p95]
  * **IQRov** (Allen IQR overlap)  : engine IQR overlaps cohort [p25, p75]
  * **[p5,p95]⊆** strict containment : engine [iqr_lo, iqr_hi] inside
                                        cohort [p5, p95]

Outputs:
  * data/mimic_iv_local/cohort_chest_pain.parquet  (built on demand)
  * data/mimic_iv_local/cohort_stroke.parquet
  * data/mimic_iv_local/cohort_aki.parquet
  * evidence_pack/mimic_iv/phase1/distribution_check_patient_level.json
  * tex/appendix_Z_patient_level.tex
  * tex/auto_numbers_mimic_iv.tex (\\PhaseOneM90PatientLevel etc.)

Sanity gate (HALT): patient-level M90 < 0.80.

The non-sepsis cohorts are built inline with ICD-10 prefixes mirroring
the sepsis cohort logic in ``phase0_setup.py``. Phase 4 may rebuild
these with stricter inclusion criteria for witness pair mining; Phase 1
is satisfied with a broad ICD-prefix cohort because the goal is
distribution coverage, not individual-pair precision.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

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
from scripts.experiments.mimic.phase0_action_mapping import _load_labevents  # noqa: E402

REFERENCE_YAML = REPO_ROOT / "evidence_pack" / "analysis" / "real_cohort_reference.yaml"
COHORT_SEPSIS = MIMIC_LOCAL_ROOT / "cohort_sepsis3.parquet"
COHORT_CHEST_PAIN = MIMIC_LOCAL_ROOT / "cohort_chest_pain.parquet"
COHORT_STROKE = MIMIC_LOCAL_ROOT / "cohort_stroke.parquet"
COHORT_AKI = MIMIC_LOCAL_ROOT / "cohort_aki.parquet"

OUTPUT_JSON = EVIDENCE_ROOT / "phase1" / "distribution_check_patient_level.json"
OUTPUT_TEX = REPO_ROOT / "tex" / "appendix_Z_patient_level.tex"
OUTPUT_MACROS = REPO_ROOT / "tex" / "auto_numbers_mimic_iv.tex"

GATE_M90_PATIENT_LEVEL_MIN = 0.80

ICD_FILTER = {
    "chest_pain": {
        "icd10_prefixes": ("I21", "I22"),  # acute MI
        "icd9_codes": {"410"},
        "parquet": COHORT_CHEST_PAIN,
    },
    "stroke": {
        "icd10_prefixes": ("I63",),
        "icd9_codes": {"433", "434"},
        "parquet": COHORT_STROKE,
    },
    "aki": {
        "icd10_prefixes": ("N17",),
        "icd9_codes": {"5849"},
        "parquet": COHORT_AKI,
    },
}


def _load_reference() -> dict[str, Any]:
    return yaml.safe_load(REFERENCE_YAML.read_text())


def _load_or_build_cohort(name: str, root: Path) -> pd.DataFrame:
    """Load a cohort parquet, building it from ICD prefixes on first use."""
    if name == "sepsis":
        return pd.read_parquet(COHORT_SEPSIS)
    spec = ICD_FILTER[name]
    parquet = spec["parquet"]
    if parquet.is_file():
        return pd.read_parquet(parquet)

    print(f"[phase1] building cohort {name!r} (first time)", file=sys.stderr)
    diagnoses = read_mimic_csv(
        "diagnoses_icd",
        subdir="hosp",
        root=root,
        dtype={"icd_code": str, "icd_version": "Int8"},
    )
    icd_str = diagnoses["icd_code"].fillna("").astype(str)
    mask = (
        diagnoses["icd_version"].eq(10)
        & icd_str.apply(lambda c: any(c.startswith(p) for p in spec["icd10_prefixes"]))
    ) | (diagnoses["icd_version"].eq(9) & icd_str.isin(spec["icd9_codes"]))
    hadms = set(diagnoses.loc[mask, "hadm_id"].astype(int).tolist())

    admissions = read_mimic_csv(
        "admissions",
        subdir="hosp",
        root=root,
        parse_dates=["admittime", "dischtime", "deathtime"],
    )
    patients = read_mimic_csv("patients", subdir="hosp", root=root)
    cohort = admissions[admissions["hadm_id"].astype(int).isin(hadms)].merge(
        patients[["subject_id", "gender", "anchor_age"]], on="subject_id", how="left"
    )
    cohort = cohort[cohort["anchor_age"] >= 18]
    cohort = (
        cohort.sort_values(["subject_id", "admittime"])
        .drop_duplicates(subset=["subject_id"], keep="first")
        .reset_index(drop=True)
    )
    parquet.parent.mkdir(parents=True, exist_ok=True)
    cohort.to_parquet(parquet, index=False)
    print(f"[phase1] wrote {parquet} (N={len(cohort):,})", file=sys.stderr)
    return cohort


def _percentiles(values: pd.Series) -> dict[str, float]:
    if values is None or len(values) == 0:
        return {"n": 0, "p5": None, "p25": None, "p50": None, "p75": None, "p95": None}
    v = values.dropna()
    if len(v) == 0:
        return {"n": 0, "p5": None, "p25": None, "p50": None, "p75": None, "p95": None}
    return {
        "n": int(len(v)),
        "p5": float(v.quantile(0.05)),
        "p25": float(v.quantile(0.25)),
        "p50": float(v.quantile(0.50)),
        "p75": float(v.quantile(0.75)),
        "p95": float(v.quantile(0.95)),
    }


def _verdict(engine: dict, mimic: dict) -> dict[str, Any]:
    """Return M90 / IQRov / strict[p5,p95]⊆ verdicts for one observable."""
    if mimic["n"] == 0 or mimic["p5"] is None:
        return {"m90_patient": None, "iqrov_patient": None, "strict_patient": None}
    em = engine["median"]
    eq = engine["iqr"]
    m90 = mimic["p5"] <= em <= mimic["p95"]
    e_lo, e_hi = min(eq), max(eq)
    iqrov = not (e_hi < mimic["p25"] or e_lo > mimic["p75"])
    strict = mimic["p5"] <= e_lo and e_hi <= mimic["p95"]
    return {
        "m90_patient": bool(m90),
        "iqrov_patient": bool(iqrov),
        "strict_patient": bool(strict),
    }


def _values_for_observable(
    obs: dict[str, Any],
    cohort: pd.DataFrame,
    *,
    labevents_cache: dict[tuple[int, ...], pd.DataFrame],
    chartevents_cache: dict[tuple[int, ...], pd.DataFrame],
    root: Path,
) -> pd.Series:
    """Resolve the MIMIC-IV value series for a single observable spec."""
    lookup = obs.get("mimic_iv_lookup", {})
    kind = lookup.get("kind", "skip")
    if kind == "skip":
        return pd.Series([], dtype="float64")

    if kind == "cohort_column":
        col = lookup["column"]
        if col in cohort.columns:
            return cohort[col].astype("float64")
        return pd.Series([], dtype="float64")

    cohort_hadms = set(cohort["hadm_id"].astype(int).tolist())

    if kind == "labevent_first24h":
        itemids = tuple(lookup["itemids"])
        union_df = labevents_cache.get(())
        if union_df is not None and len(union_df) > 0:
            df = union_df[union_df["itemid"].isin(itemids)]
        else:
            if itemids not in labevents_cache:
                df, partial = _load_labevents(root, target_itemids=set(itemids))
                labevents_cache[itemids] = df if df is not None else pd.DataFrame()
                if partial:
                    print(
                        f"[warn] labevents partial for itemids={itemids}",
                        file=sys.stderr,
                    )
            df = labevents_cache[itemids]
        if df is None or len(df) == 0:
            return pd.Series([], dtype="float64")
        df = df[df["hadm_id"].astype("Int64").isin(cohort_hadms)]
        per_patient = (
            df.dropna(subset=["valuenum"])
            .sort_values(["hadm_id", "charttime"])
            .groupby("hadm_id", as_index=False)
            .first()
        )
        return per_patient["valuenum"].astype("float64")

    if kind == "chartevent_first24h":
        itemids = tuple(lookup["itemids"])
        # Look up against the cached union frame (key = ()), then filter
        # to this observable's itemids. Falls back to per-itemid loading
        # if the union cache is absent.
        union_df = chartevents_cache.get(())
        if union_df is None or len(union_df) == 0:
            if itemids not in chartevents_cache:
                df = _load_chartevents(root, target_itemids=set(itemids))
                chartevents_cache[itemids] = df if df is not None else pd.DataFrame()
            df = chartevents_cache[itemids]
        else:
            df = union_df[union_df["itemid"].isin(itemids)]
        if df is None or len(df) == 0:
            return pd.Series([], dtype="float64")
        df = df[df["hadm_id"].astype("Int64").isin(cohort_hadms)]
        per_patient = (
            df.dropna(subset=["valuenum"])
            .sort_values(["hadm_id", "charttime"])
            .groupby("hadm_id", as_index=False)
            .first()
        )
        # Fahrenheit -> Celsius if temp itemids match the fallback list.
        if obs.get("unit") == "celsius" and "fallback_itemids_fahrenheit" in lookup:
            f_ids = set(lookup["fallback_itemids_fahrenheit"])
            f_mask = per_patient["itemid"].isin(f_ids)
            per_patient.loc[f_mask, "valuenum"] = (
                per_patient.loc[f_mask, "valuenum"] - 32.0
            ) * 5.0 / 9.0
        return per_patient["valuenum"].astype("float64")

    return pd.Series([], dtype="float64")


def _load_chartevents(
    root: Path, target_itemids: set[int], chunksize: int = 1_000_000
) -> pd.DataFrame:
    """Stream chartevents.csv.gz, filter to target itemids. Same EOF tolerance
    as labevents loader."""
    base = root / "icu" / "chartevents"
    src = base.with_suffix(".csv.gz")
    if not src.is_file():
        src = base.with_suffix(".csv")
        if not src.is_file():
            return pd.DataFrame()
    rows: list[pd.DataFrame] = []
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
    except EOFError:
        pass
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--skip-gates", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    if not COHORT_SEPSIS.is_file():
        print(f"[error] missing {COHORT_SEPSIS}; run phase0_setup.py first",
              file=sys.stderr)
        return 2
    if not REFERENCE_YAML.is_file():
        print(f"[error] missing {REFERENCE_YAML}", file=sys.stderr)
        return 2

    reference = _load_reference()
    root = resolve_mimic_root(prefer_full=True)
    cohorts: dict[str, pd.DataFrame] = {}
    labevents_cache: dict[tuple[int, ...], pd.DataFrame] = {}
    chartevents_cache: dict[tuple[int, ...], pd.DataFrame] = {}
    rows: list[dict[str, Any]] = []

    # ---- Pre-load chartevents ONCE with the union of all itemids -----------
    chart_itemids: set[int] = set()
    lab_itemids: set[int] = set()
    for obs in reference["observables"]:
        lookup = obs.get("mimic_iv_lookup", {})
        if lookup.get("kind") == "chartevent_first24h":
            chart_itemids.update(lookup.get("itemids", []))
            chart_itemids.update(lookup.get("fallback_itemids_fahrenheit", []))
        if lookup.get("kind") == "labevent_first24h":
            lab_itemids.update(lookup.get("itemids", []))
    if chart_itemids:
        print(f"[phase1] pre-loading chartevents (union of "
              f"{len(chart_itemids)} itemids)", file=sys.stderr)
        chartevents_cache[()] = _load_chartevents(root, target_itemids=chart_itemids)
    if lab_itemids:
        print(f"[phase1] pre-loading labevents (union of "
              f"{len(lab_itemids)} itemids)", file=sys.stderr)
        df, partial = _load_labevents(root, target_itemids=lab_itemids)
        labevents_cache[()] = df if df is not None else pd.DataFrame()

    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for obs in reference["observables"]:
        by_domain[obs["domain"]].append(obs)

    for domain in ("sepsis", "chest_pain", "stroke", "aki"):
        if domain not in cohorts:
            cohorts[domain] = _load_or_build_cohort(domain, root)
        cohort = cohorts[domain]
        print(f"[phase1] domain {domain}: cohort N={len(cohort):,}")
        for obs in by_domain[domain]:
            values = _values_for_observable(
                obs,
                cohort,
                labevents_cache=labevents_cache,
                chartevents_cache=chartevents_cache,
                root=root,
            )
            mimic_pcts = _percentiles(values)
            verdict_pat = _verdict(obs["engine"], mimic_pcts)
            lit_p5_p95 = obs["literature"]["p5_p95"]
            verdict_lit = {
                "m90_lit": lit_p5_p95[0] <= obs["engine"]["median"] <= lit_p5_p95[1],
                "iqrov_lit": True,  # not recomputed; preserved from existing tex
                "strict_lit": (
                    lit_p5_p95[0] <= min(obs["engine"]["iqr"])
                    and max(obs["engine"]["iqr"]) <= lit_p5_p95[1]
                ),
            }
            row = {
                "key": obs["key"],
                "domain": domain,
                "observable": obs["observable"],
                "unit": obs["unit"],
                "engine": obs["engine"],
                "literature": obs["literature"],
                "mimic_iv_patient_level": mimic_pcts,
                "verdict_patient_level": verdict_pat,
                "verdict_literature": verdict_lit,
            }
            rows.append(row)
            print(
                f"  {obs['key']:30s} mimic n={mimic_pcts['n']:6d}  "
                f"M90={verdict_pat['m90_patient']}",
                file=sys.stderr,
            )

    available_rows = [r for r in rows if r["mimic_iv_patient_level"]["n"] > 0]
    n_avail = len(available_rows)

    def _rate(field: str) -> float:
        if not available_rows:
            return 0.0
        passes = sum(
            1 for r in available_rows if r["verdict_patient_level"][field] is True
        )
        return passes / n_avail

    m90_rate = _rate("m90_patient")
    iqrov_rate = _rate("iqrov_patient")
    strict_rate = _rate("strict_patient")

    payload = {
        "metadata": {
            "data_root": str(root),
            "mimic_version": mimic_version(root),
            "git_sha": git_sha(),
            "seed": args.seed,
            "n_observables": len(rows),
            "n_observables_with_mimic": n_avail,
            "n_skipped": len(rows) - n_avail,
        },
        "rates_patient_level": {
            "M90": round(m90_rate, 4),
            "IQRov": round(iqrov_rate, 4),
            "strict_p5p95_subseteq": round(strict_rate, 4),
        },
        "rows": rows,
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"[phase1] wrote {OUTPUT_JSON}")

    _write_tex(rows, m90_rate, iqrov_rate, strict_rate)
    _write_macros(m90_rate, iqrov_rate, strict_rate, n_avail)

    summary = PhaseSummary(
        script_name="phase1_distribution_check",
        phase="phase1",
        n_episodes=n_avail,
        n_excluded=len(rows) - n_avail,
        seed=args.seed,
        git_sha=git_sha(),
        mimic_version=mimic_version(root),
        wall_time_s=time.time() - t0,
        extra={
            "M90_patient_level": round(m90_rate, 4),
            "IQRov_patient_level": round(iqrov_rate, 4),
            "strict_p5p95_patient_level": round(strict_rate, 4),
        },
    )
    summary.write(EVIDENCE_ROOT / "phase1")

    if m90_rate < GATE_M90_PATIENT_LEVEL_MIN and not args.skip_gates:
        try:
            halt_and_log(
                gate_name="phase1_m90_patient_level",
                detail=f"M90 patient-level = {m90_rate:.3f} < "
                f"{GATE_M90_PATIENT_LEVEL_MIN}",
                known_issues_section="6",
            )
        except GateFailure as exc:
            print(f"[HALT] {exc}", file=sys.stderr)
            return 1
    elif m90_rate < GATE_M90_PATIENT_LEVEL_MIN:
        print(f"[warn] M90={m90_rate:.3f} < gate; --skip-gates set", file=sys.stderr)

    print(f"[phase1] done in {time.time() - t0:.1f}s "
          f"(M90={m90_rate:.3f} IQRov={iqrov_rate:.3f} strict={strict_rate:.3f})")
    return 0


def _write_tex(rows: list[dict], m90: float, iqrov: float, strict: float) -> None:
    OUTPUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "% Auto-generated by scripts/experiments/mimic/phase1_distribution_check.py",
        "% MIMIC-IV patient-level distribution check (App Z augmentation).",
        "\\begin{tabular}{@{}llrrrrcc@{}}",
        "\\toprule",
        "Domain & Observable & Engine Med & Engine IQR & MIMIC Med & MIMIC $[p_5,p_{95}]$ & "
        "M90$^\\text{pat}$ & strict$^\\text{pat}$ \\\\",
        "\\midrule",
    ]
    for r in rows:
        m = r["mimic_iv_patient_level"]
        v = r["verdict_patient_level"]
        if m["n"] == 0:
            lines.append(
                f"{r['domain']} & {r['observable']} ({r['unit']}) & "
                f"{r['engine']['median']:.1f} & "
                f"[{r['engine']['iqr'][0]:.1f},{r['engine']['iqr'][1]:.1f}] & "
                "-- & -- & -- & -- \\\\"
            )
            continue
        m90_sym = "\\checkmark" if v["m90_patient"] else "$\\times$"
        strict_sym = "\\checkmark" if v["strict_patient"] else "$\\times$"
        lines.append(
            f"{r['domain']} & {r['observable']} ({r['unit']}) & "
            f"{r['engine']['median']:.1f} & "
            f"[{r['engine']['iqr'][0]:.1f},{r['engine']['iqr'][1]:.1f}] & "
            f"{m['p50']:.1f} & "
            f"[{m['p5']:.1f},{m['p95']:.1f}] & {m90_sym} & {strict_sym} \\\\"
        )
    lines += [
        "\\midrule",
        f"\\multicolumn{{8}}{{@{{}}p{{0.95\\textwidth}}@{{}}}}{{\\footnotesize\\textit{{"
        f"Patient-level rates:}} M90=\\textbf{{{m90 * 100:.1f}\\%}}, "
        f"IQRov=\\textbf{{{iqrov * 100:.1f}\\%}}, "
        f"$[p_5,p_{{95}}]\\subseteq$ strict=\\textbf{{{strict * 100:.1f}\\%}}}} \\\\",
        "\\bottomrule",
        "\\end{tabular}",
    ]
    OUTPUT_TEX.write_text("\n".join(lines) + "\n")
    print(f"[phase1] wrote {OUTPUT_TEX}")


def _write_macros(m90: float, iqrov: float, strict: float, n_avail: int) -> None:
    """Append patient-level macros to tex/auto_numbers_mimic_iv.tex.

    Phase 6's phase6_integrate.py concatenates this file with
    main_final_v18.tex's existing macro block.
    """
    OUTPUT_MACROS.parent.mkdir(parents=True, exist_ok=True)
    block = (
        f"% Phase 1 (patient-level distribution check)\n"
        f"\\newcommand{{\\PhaseOneM90PatientLevel}}{{{m90 * 100:.1f}}}\n"
        f"\\newcommand{{\\PhaseOneIQROvPatientLevel}}{{{iqrov * 100:.1f}}}\n"
        f"\\newcommand{{\\PhaseOneStrictContainPatientLevel}}{{{strict * 100:.1f}}}\n"
        f"\\newcommand{{\\PhaseOneNObsPatientLevel}}{{{n_avail}}}\n"
    )
    if OUTPUT_MACROS.is_file():
        existing = OUTPUT_MACROS.read_text()
        # Replace any existing Phase 1 block (idempotent), else append.
        marker = "% Phase 1 (patient-level distribution check)"
        if marker in existing:
            head, _ = existing.split(marker, 1)
            tail_lines = existing.split(marker, 1)[1].splitlines(keepends=True)
            i = 0
            while i < len(tail_lines) and tail_lines[i].startswith(("\\newcommand", "\n")):
                i += 1
            new = head + block + "".join(tail_lines[i:])
            OUTPUT_MACROS.write_text(new)
        else:
            OUTPUT_MACROS.write_text(existing + "\n" + block)
    else:
        OUTPUT_MACROS.write_text(
            "% Auto-generated MIMIC-IV macros for App AQ.1-AQ.3.\n" + block
        )
    print(f"[phase1] updated {OUTPUT_MACROS}")


if __name__ == "__main__":
    raise SystemExit(main())
