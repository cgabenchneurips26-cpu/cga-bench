#!/usr/bin/env python3
"""MIMIC-IV Sepsis-3 cohort statistics from partially-downloaded hosp/.

Computes paper §3 cohort statistics from the files currently available
under physionet.org/files/mimiciv/3.1/hosp/ — does NOT require icu/.

What we can compute (with hosp/ alone):
  * Sepsis-3 cohort size (ICD-10 A41.*/R65.2*; ICD-9 995.91/92, 785.52)
  * ICD code prevalence within the cohort
  * DRG distribution (drgcodes.csv) — sepsis-related DRG 870/871/872
  * Length-of-stay distribution from admissions
  * Admission type / source / discharge disposition
  * Comorbidity distribution (top-N ICD-10 prefixes co-occurring with sepsis)
  * Lactate / WBC / Creatinine distributions in sepsis admissions
    (if labevents.csv.gz is available)

Outputs:
  * docs/260429_mimic_sepsis_cohort_stats_partial.md (human-readable report)
  * evidence_pack/frontier/mimic_sepsis_cohort_stats.json (machine-readable)
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]


SEPSIS_ICD10_PREFIXES = ("A41", "R65.2", "R6520", "R6521")
SEPSIS_ICD9_CODES = {"99591", "99592", "78552"}

# Sepsis-related DRG codes (MS-DRG)
SEPSIS_DRG_CODES = {
    870: "Septicemia or severe sepsis with MV >96 hours",
    871: "Septicemia or severe sepsis without MV >96 hours with MCC",
    872: "Septicemia or severe sepsis without MV >96 hours without MCC",
}

# Comorbidity ICD-10 prefixes (3-char rollup) that gate SSC forbidden actions
COMORBIDITY_PREFIXES_ICD10 = {
    "I50": "heart_failure",
    "K70": "alcoholic_liver_disease",
    "K74": "fibrosis_cirrhosis",
    "N18": "ckd",
    "Z99": "dialysis_dependence",
    "E10": "type_1_diabetes",
    "E11": "type_2_diabetes",
    "I10": "essential_hypertension",
    "J44": "copd",
    "J45": "asthma",
    "C": "neoplasm_any",   # all C-codes
    "F1": "substance_use",
    "F3": "mood_disorder",
    "I63": "ischemic_stroke",
    "I21": "acute_mi",
}

# Critical lab itemids
LAB_LACTATE = 50813
LAB_WBC = 51301
LAB_CREATININE = 50912
LAB_PROCALCITONIN = 50889
LAB_GLUCOSE = 50931


def _read_csv_gz(path: Path, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, compression="gzip", **kwargs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default="physionet.org/files/mimiciv/3.1")
    ap.add_argument("--lab-sample", type=int, default=2_000_000,
                    help="If labevents is huge, sample this many rows")
    ap.add_argument("--report",
                    default="docs/260429_mimic_sepsis_cohort_stats_partial.md")
    ap.add_argument("--json-out",
                    default="evidence_pack/frontier/mimic_sepsis_cohort_stats.json")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    data_dir = Path(args.data_dir)
    hosp = data_dir / "hosp"
    if not hosp.is_dir():
        print(f"[error] hosp/ not found at {hosp}", file=sys.stderr)
        return 1

    available = sorted(p.name for p in hosp.glob("*.csv.gz"))
    print(f"[info] hosp/ has {len(available)} csv.gz files")

    # ------------------------------------------------------------------
    # 1. Diagnoses → Sepsis-3 cohort identification
    # ------------------------------------------------------------------
    dx_path = hosp / "diagnoses_icd.csv.gz"
    if not dx_path.exists():
        print("[error] diagnoses_icd.csv.gz missing — cannot identify cohort",
              file=sys.stderr)
        return 1

    print("[step 1/4] loading diagnoses_icd.csv.gz ...")
    dx = _read_csv_gz(dx_path, dtype={"icd_code": str, "icd_version": "Int8"})
    print(f"  total rows: {len(dx):,}")

    # Sepsis filter
    icd10_mask = dx["icd_version"].eq(10) & dx["icd_code"].fillna("").apply(
        lambda c: any(c.startswith(p) for p in SEPSIS_ICD10_PREFIXES))
    icd9_mask = dx["icd_version"].eq(9) & dx["icd_code"].fillna("").isin(SEPSIS_ICD9_CODES)
    sepsis_dx = dx[icd10_mask | icd9_mask]
    sepsis_admits = sepsis_dx["hadm_id"].drop_duplicates()
    print(f"  sepsis admissions: {len(sepsis_admits):,}")
    print(f"  sepsis dx rows:    {len(sepsis_dx):,}")

    sepsis_subjects = sepsis_dx["subject_id"].drop_duplicates()
    print(f"  unique sepsis patients: {len(sepsis_subjects):,}")

    icd_counts = sepsis_dx["icd_code"].value_counts().head(20).to_dict()

    # ------------------------------------------------------------------
    # 2. Comorbidity distribution within cohort
    # ------------------------------------------------------------------
    print("[step 2/4] computing comorbidity distribution ...")
    cohort_admits_set = set(sepsis_admits.tolist())
    cohort_dx = dx[dx["hadm_id"].isin(cohort_admits_set)]
    print(f"  cohort total dx rows (incl. comorbidities): {len(cohort_dx):,}")

    # Roll up to 3-char ICD prefix and count comorbidity flags
    comorb_counter: Counter[str] = Counter()
    cohort_dx_icd10 = cohort_dx[cohort_dx["icd_version"].eq(10)]
    code_str = cohort_dx_icd10["icd_code"].fillna("").astype(str)
    by_admit_comorb: defaultdict[int, set[str]] = defaultdict(set)
    for hadm_id, code in zip(cohort_dx_icd10["hadm_id"], code_str):
        for prefix, tag in COMORBIDITY_PREFIXES_ICD10.items():
            if code.startswith(prefix):
                by_admit_comorb[hadm_id].add(tag)
                break
    for tags in by_admit_comorb.values():
        for t in tags:
            comorb_counter[t] += 1
    n_admits_with_dx = max(len(by_admit_comorb), 1)
    comorb_pct = {
        tag: round(100 * c / n_admits_with_dx, 1)
        for tag, c in comorb_counter.most_common()
    }

    # ------------------------------------------------------------------
    # 3. Admissions metadata (LOS, type, disposition)
    # ------------------------------------------------------------------
    adm_path = hosp / "admissions.csv.gz"
    los_stats = {}
    adm_type = {}
    adm_disp = {}
    if adm_path.exists():
        print("[step 3/4] loading admissions.csv.gz ...")
        adm = _read_csv_gz(adm_path, parse_dates=["admittime", "dischtime"])
        cohort_adm = adm[adm["hadm_id"].isin(cohort_admits_set)].copy()
        cohort_adm["los_days"] = (
            cohort_adm["dischtime"] - cohort_adm["admittime"]
        ).dt.total_seconds() / 86400.0
        los_clean = cohort_adm["los_days"].dropna()
        los_stats = {
            "n": int(len(los_clean)),
            "mean": round(float(los_clean.mean()), 2) if len(los_clean) else 0,
            "median": round(float(los_clean.median()), 2) if len(los_clean) else 0,
            "p25": round(float(los_clean.quantile(0.25)), 2) if len(los_clean) else 0,
            "p75": round(float(los_clean.quantile(0.75)), 2) if len(los_clean) else 0,
            "max": round(float(los_clean.max()), 2) if len(los_clean) else 0,
        }
        adm_type = cohort_adm["admission_type"].value_counts().head(10).to_dict()
        adm_disp = cohort_adm["discharge_location"].value_counts(dropna=False).head(10).to_dict()
        print(f"  cohort admissions matched: {len(cohort_adm):,}")
    else:
        print("  admissions.csv.gz missing — skipping LOS / type / disposition")

    # ------------------------------------------------------------------
    # 4. DRG distribution
    # ------------------------------------------------------------------
    drg_path = hosp / "drgcodes.csv.gz"
    drg_top = {}
    sepsis_drg_count = 0
    if drg_path.exists():
        print("[step 4/4] loading drgcodes.csv.gz ...")
        drg = _read_csv_gz(drg_path, dtype={"drg_code": str})
        cohort_drg = drg[drg["hadm_id"].isin(cohort_admits_set)]
        drg_top = cohort_drg["drg_code"].value_counts().head(15).to_dict()
        sepsis_drg_codes_str = {str(c) for c in SEPSIS_DRG_CODES}
        sepsis_drg_count = int(
            cohort_drg["drg_code"].astype(str).isin(sepsis_drg_codes_str).sum()
        )
        print(f"  cohort drg rows: {len(cohort_drg):,}")

    # ------------------------------------------------------------------
    # 5. Lab distributions (lactate / WBC / creatinine)
    # ------------------------------------------------------------------
    lab_path = hosp / "labevents.csv.gz"
    lab_stats: dict[str, dict] = {}
    if lab_path.exists():
        print(f"[step 5/4] loading labevents.csv.gz "
              f"(sample {args.lab_sample:,} rows) ...")
        lab_iter = pd.read_csv(
            lab_path, compression="gzip",
            dtype={"itemid": "Int32", "valuenum": "float64"},
            usecols=["hadm_id", "itemid", "valuenum"],
            chunksize=500_000,
        )
        critical_items = {LAB_LACTATE, LAB_WBC, LAB_CREATININE,
                          LAB_PROCALCITONIN, LAB_GLUCOSE}
        rows: list[pd.DataFrame] = []
        seen = 0
        try:
            for chunk in lab_iter:
                chunk = chunk[chunk["hadm_id"].isin(cohort_admits_set)
                              & chunk["itemid"].isin(critical_items)]
                rows.append(chunk)
                seen += len(chunk)
                if seen >= args.lab_sample:
                    break
        except EOFError as exc:
            # labevents.csv.gz is still being downloaded — incomplete gzip.
            # Take whatever we read so far.
            print(f"  [partial] labevents.csv.gz still downloading: {exc}; "
                  f"using {seen:,} rows scanned so far")
        if rows:
            cohort_lab = pd.concat(rows, ignore_index=True)
            for itemid, name in [
                (LAB_LACTATE, "lactate"), (LAB_WBC, "wbc"),
                (LAB_CREATININE, "creatinine"),
                (LAB_PROCALCITONIN, "procalcitonin"),
                (LAB_GLUCOSE, "glucose"),
            ]:
                vals = cohort_lab[cohort_lab["itemid"].eq(itemid)]["valuenum"].dropna()
                if len(vals) == 0:
                    continue
                lab_stats[name] = {
                    "n": int(len(vals)),
                    "mean": round(float(vals.mean()), 3),
                    "median": round(float(vals.median()), 3),
                    "p25": round(float(vals.quantile(0.25)), 3),
                    "p75": round(float(vals.quantile(0.75)), 3),
                    "max": round(float(vals.max()), 3),
                }
        print(f"  cohort lab rows scanned: {seen:,}")
    else:
        print("  labevents.csv.gz missing — skipping lab distributions")

    # ------------------------------------------------------------------
    # Compose output
    # ------------------------------------------------------------------
    summary = {
        "metadata": {
            "data_dir": str(data_dir),
            "computed_at_utc": datetime.now(timezone.utc).isoformat(),
            "hosp_files_available": available,
        },
        "cohort": {
            "n_sepsis_admissions": int(len(sepsis_admits)),
            "n_unique_sepsis_patients": int(len(sepsis_subjects)),
            "n_sepsis_diagnoses_rows": int(len(sepsis_dx)),
            "top20_sepsis_icd_codes": icd_counts,
        },
        "comorbidities": {
            "n_admits_with_dx": n_admits_with_dx,
            "rate_pct_by_tag": comorb_pct,
        },
        "admissions": {
            "los_days": los_stats,
            "admission_type": adm_type,
            "discharge_location": adm_disp,
        },
        "drg": {
            "top15": drg_top,
            "n_sepsis_drg_870_871_872": sepsis_drg_count,
        },
        "labs": lab_stats,
    }

    json_path = REPO_ROOT / args.json_out
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[ok] wrote {json_path}")

    # Markdown report
    lines = [
        f"# MIMIC-IV Sepsis-3 Cohort Statistics (from partial download)",
        "",
        f"**Computed**: {summary['metadata']['computed_at_utc']}",
        f"**Source**: `{data_dir}` (hosp/ only; icu/ not yet available)",
        "",
        "## 1. Cohort identification (Sepsis-3)",
        "",
        f"- **{len(sepsis_admits):,}** sepsis admissions",
        f"- **{len(sepsis_subjects):,}** unique sepsis patients",
        f"- **{len(sepsis_dx):,}** sepsis diagnosis rows",
        "",
        "**Top-20 sepsis ICD codes:**",
        "",
        "| ICD code | Count |",
        "|---|---|",
    ]
    for code, count in icd_counts.items():
        lines.append(f"| {code} | {count:,} |")
    lines += [
        "",
        "## 2. Comorbidity distribution",
        "",
        f"Among {n_admits_with_dx:,} sepsis admissions with at least one ICD-10 code:",
        "",
        "| Tag | % of admissions |",
        "|---|---|",
    ]
    for tag, pct in list(comorb_pct.items())[:15]:
        lines.append(f"| {tag} | {pct} % |")
    if los_stats:
        lines += [
            "",
            "## 3. Length of stay (cohort admissions)",
            "",
            f"- n: {los_stats['n']:,}",
            f"- mean: {los_stats['mean']} days",
            f"- median: {los_stats['median']} days",
            f"- IQR: {los_stats['p25']}–{los_stats['p75']} days",
            f"- max: {los_stats['max']} days",
            "",
            "## 4. Admission type",
            "",
            "| Type | Count |",
            "|---|---|",
        ]
        for k, v in adm_type.items():
            lines.append(f"| {k} | {v:,} |")
        lines += ["", "## 5. Discharge location", "", "| Location | Count |", "|---|---|"]
        for k, v in adm_disp.items():
            lines.append(f"| {k} | {v:,} |")
    if drg_top:
        lines += [
            "",
            "## 6. DRG distribution",
            "",
            f"- Sepsis-specific DRGs (870/871/872): **{sepsis_drg_count:,}**",
            "",
            "**Top-15 DRGs in cohort:**",
            "",
            "| DRG | Count |",
            "|---|---|",
        ]
        for k, v in drg_top.items():
            lines.append(f"| {k} | {v:,} |")
    if lab_stats:
        lines += ["", "## 7. Lab distributions in cohort", "",
                  "| Lab | n | mean | median | IQR | max |", "|---|---|---|---|---|---|"]
        for name, s in lab_stats.items():
            lines.append(
                f"| {name} | {s['n']:,} | {s['mean']} | {s['median']} | "
                f"{s['p25']}–{s['p75']} | {s['max']} |"
            )
    lines += [
        "",
        "## 8. Files used",
        "",
    ]
    for f in available:
        lines.append(f"- `hosp/{f}`")
    lines += [
        "",
        "## Caveats",
        "",
        "- ICU module not yet downloaded — vitals, ICU LOS, vasopressor /",
        "  fluid administration timeline missing from this report.",
        "- ICD-10/ICD-9 mapping is conservative (prefix-only match).",
        "- Comorbidity tags use 3-char rollup; finer granularity available",
        "  on full v3.1.",
        "- patients.csv.gz not yet downloaded → no age/sex demographics in",
        "  this report. Add when patients.csv.gz arrives.",
    ]
    rep_path = REPO_ROOT / args.report
    rep_path.parent.mkdir(parents=True, exist_ok=True)
    rep_path.write_text("\n".join(lines))
    print(f"[ok] wrote {rep_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
