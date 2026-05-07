"""Source-PDF acquisition manifest for beta-candidate CPGs.

For each beta candidate listed in 09_tier_s_preregistration.md §3 (or any
--graph-ids list), looks up the DOI in data/cpg_source_properties_candidates_*.json
and queries Unpaywall (https://unpaywall.org/products/api) for a free
open-access PDF URL. Emits a manifest CSV/markdown the user can act on
manually for paywalled sources.

The script NEVER downloads from sci-hub or other unauthorized sources. For
paywalled guidelines the manifest flags `status=MANUAL_UPLOAD_REQUIRED`
and the user supplies the PDF via institutional access, saving to
`data/source_pdfs/<graph_id>.pdf`.

Usage:
    # Generate manifest for all 29 beta candidates
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/acquire_source_pdf.py \
        --preregistration-doc docs/cpg_expansion_v7/09_tier_s_preregistration.md \
        --email [email-redacted] \
        --output data/source_pdfs/acquisition_manifest.md

    # Manifest for a single CPG
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/acquire_source_pdf.py \
        --graph-ids aha_cardiogenic_shock_2017 \
        --email [email-redacted] \
        --output /tmp/one.md

Outputs:
    - acquisition_manifest.md: human-readable table (graph_id, doi, title,
      open_access_url, license, status)
    - acquisition_manifest.csv: machine-readable version (same columns)

NOTE on Unpaywall etiquette: the API requires an email parameter for rate-
limiting and abuse response. Provide a real email.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
import re
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

UNPAYWALL_ENDPOINT = "https://api.unpaywall.org/v2/{doi}?email={email}"
RATE_LIMIT_DELAY_SECONDS = 0.2  # be polite

# Default pool from 09_tier_s_preregistration.md §3 (27 core beta + 2 heldout beta = 29)
DEFAULT_BETA_GRAPH_IDS: list[str] = [
    # Core beta (score 19)
    "ats_esicm_sccm_ards_2023",
    "esvs_aaa_2024",
    "ncs_aha_sah_2023",
    "nrp_neonatal_resuscitation_2020",
    "pals_pediatric_traumatic_arrest_2020",
    "sccm_pediatric_septic_shock_2020",
    # Core beta (score 18)
    "aha_cardiogenic_shock_2017",
    "aha_ttm_post_arrest_2023",
    "bts_pleural_disease_2023",
    "esvs_acute_limb_ischemia_2020",
    "ispad_pediatric_dka_2022",
    "who_severe_malaria_2023",
    # Core beta (score 17)
    "asam_alcohol_withdrawal_2020",
    "asco_tls_2023",
    "ash_sickle_cell_acs_2020",
    "baveno_vii_varices_2022",
    "east_damage_control_mtp_2017",
    "eau_obstructive_pyelonephritis_2024",
    "erc_drowning_2021",
    "ers_ats_niv_2017",
    "gina_pediatric_status_asthma_2024",
    "hrs_vt_sd_2017",
    "idsa_cdi_2021",
    "isth_ash_ttp_2020",
    "sccm_rsi_2019",
    "smfm_maternal_sepsis_2019",
    "wses_pelvic_trauma_reboa_2017",
    # Held-out beta (score 19)
    "aha_acc_aortic_dissection_2022",
    "aha_asa_ich_2022",
]


def load_all_candidate_props() -> dict[str, dict[str, Any]]:
    """Merge draft + bulk_A + bulk_B source_properties into one dict."""
    merged: dict[str, dict[str, Any]] = {}
    for path in [
        "data/cpg_source_properties_candidates_draft.json",
        "data/cpg_source_properties_candidates_bulk_A.json",
        "data/cpg_source_properties_candidates_bulk_B.json",
    ]:
        p = Path(path)
        if not p.exists():
            logger.warning("Missing %s", p)
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        graphs = d.get("graphs", d)
        merged.update(graphs)
    return merged


def extract_doi(props: dict[str, Any]) -> str | None:
    """Best-effort DOI extraction from a source_properties entry."""
    # Tried fields, in priority order.
    for field in ("c5_doi", "doi", "primary_doi"):
        v = props.get(field)
        if v:
            return str(v).strip()
    # Try parsing from any text field.
    for field in ("c5_source_text", "c7_source_text", "source_text"):
        v = props.get(field)
        if v and isinstance(v, str):
            m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", v)
            if m:
                return m.group(0)
    return None


def query_unpaywall(doi: str, email: str, timeout: float = 10.0) -> dict[str, Any] | None:
    """Single Unpaywall query with sane error handling."""
    url = UNPAYWALL_ENDPOINT.format(doi=urllib.parse.quote(doi, safe="/"), email=urllib.parse.quote(email))
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        logger.info("unpaywall HTTP %s for %s", exc.code, doi)
        return None
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("unpaywall network error for %s: %s", doi, exc)
        return None
    except json.JSONDecodeError as exc:
        logger.warning("unpaywall json error for %s: %s", doi, exc)
        return None


def best_oa_pdf(unpaywall_response: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract (pdf_url, license) for the best open-access location."""
    best = unpaywall_response.get("best_oa_location")
    if best:
        return best.get("url_for_pdf") or best.get("url"), best.get("license")
    for loc in unpaywall_response.get("oa_locations", []) or []:
        if loc.get("url_for_pdf"):
            return loc["url_for_pdf"], loc.get("license")
    return None, None


def process_graph_ids(
    graph_ids: list[str], email: str, sleep_between: float = RATE_LIMIT_DELAY_SECONDS
) -> list[dict[str, Any]]:
    """Look up DOI + open-access status for each graph_id."""
    candidate_props = load_all_candidate_props()
    rows: list[dict[str, Any]] = []
    for i, gid in enumerate(graph_ids, start=1):
        props = candidate_props.get(gid, {})
        doi = extract_doi(props)
        title = props.get("guideline_name") or props.get("title") or ""
        publisher = props.get("publisher") or props.get("c1_publisher") or ""
        year = props.get("c4_recency_year") or props.get("publication_year") or ""

        pdf_url: str | None = None
        license_str: str | None = None
        status = "NO_DOI"

        if doi:
            status = "UNPAYWALL_QUERYING"
            logger.info("[%d/%d] %s → DOI %s", i, len(graph_ids), gid, doi)
            resp = query_unpaywall(doi, email)
            if resp is None:
                status = "UNPAYWALL_ERROR"
            else:
                pdf_url, license_str = best_oa_pdf(resp)
                status = "OPEN_ACCESS" if pdf_url else "MANUAL_UPLOAD_REQUIRED"
            time.sleep(sleep_between)
        else:
            logger.warning("[%d/%d] %s → no DOI in candidate props", i, len(graph_ids), gid)

        rows.append(
            {
                "graph_id": gid,
                "title": title,
                "publisher": publisher,
                "year": year,
                "doi": doi or "",
                "open_access_url": pdf_url or "",
                "license": license_str or "",
                "status": status,
            }
        )
    return rows


def write_markdown(rows: list[dict[str, Any]], out_path: Path) -> None:
    """Emit a human-readable table."""
    lines = ["# Source-PDF Acquisition Manifest", "", f"Total CPGs: {len(rows)}", ""]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for k, v in sorted(counts.items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "| graph_id | title | doi | status | open_access_url |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            "| "
            + " | ".join(
                str(r.get(col, "") or "").replace("|", "\\|")[:120]
                for col in ["graph_id", "title", "doi", "status", "open_access_url"]
            )
            + " |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    """Emit a machine-readable version."""
    fieldnames = ["graph_id", "title", "publisher", "year", "doi", "open_access_url", "license", "status"]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--graph-ids",
        default="",
        help="Comma-separated list of graph_ids. Empty => use the frozen 29 beta pool.",
    )
    parser.add_argument(
        "--preregistration-doc",
        type=Path,
        default=None,
        help="Optional: parse graph_ids out of 09_tier_s_preregistration.md instead of the default list.",
    )
    parser.add_argument("--email", required=True, help="Email for Unpaywall API etiquette")
    parser.add_argument("--output", required=True, type=Path, help="Output .md path")
    parser.add_argument("--csv-output", default=None, type=Path, help="Optional companion CSV path")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.graph_ids:
        gids = [g.strip() for g in args.graph_ids.split(",") if g.strip()]
    elif args.preregistration_doc and args.preregistration_doc.exists():
        # Extract graph_ids from markdown tables (simple heuristic).
        text = args.preregistration_doc.read_text(encoding="utf-8")
        gids = sorted(
            set(re.findall(r"\|\s*([a-z][a-z0-9_]+_\d{4})\s*\|", text))
            | set(re.findall(r"\|\s*([a-z][a-z0-9_]+)\s*\|\s*\d+\s*\|", text))
        )
        # Filter to known beta pool only.
        gids = [g for g in gids if g in DEFAULT_BETA_GRAPH_IDS]
    else:
        gids = DEFAULT_BETA_GRAPH_IDS

    logger.info("Processing %d graph_ids", len(gids))
    rows = process_graph_ids(gids, email=args.email)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(rows, args.output)
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        write_csv(rows, args.csv_output)

    print("\nManifest written to", args.output)
    statuses: dict[str, int] = {}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    for k, v in sorted(statuses.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
