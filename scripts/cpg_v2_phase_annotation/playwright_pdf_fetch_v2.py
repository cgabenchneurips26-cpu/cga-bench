"""Playwright PDF fetcher v2 — more aggressive recovery strategies.

Extends playwright_pdf_fetch.py with:
1. SSL error bypass (`ignore_https_errors=True`) — fixes watermark.silverchair.com
2. Landing-page PDF link extraction — handles small-HTML responses
3. PubMed Central (PMC) alternate-source lookup for NIH-funded guidelines
4. Europe PMC fallback
5. Alternative User-Agent + Referer headers for 403 responses
6. Multi-timeout retry (15s → 60s → 120s)

Usage: same as v1 but tries harder before giving up.
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]


def lookup_pmc_alternate(doi: str, email: str = "[email-redacted]") -> str | None:
    """Search PMC for a free full-text link by DOI.

    Uses NCBI E-utilities idconv. Returns PMC ID URL if found.
    """
    if not doi:
        return None
    url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?tool=cga-bench&email={email}&ids={urllib.parse.quote(doi)}&format=json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            import json

            data = json.loads(r.read())
            records = data.get("records", [])
            if records and "pmcid" in records[0]:
                pmcid = records[0]["pmcid"]
                return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
    except Exception as exc:
        logger.debug("PMC lookup failed for %s: %s", doi, exc)
    return None


def lookup_europe_pmc(doi: str) -> str | None:
    """Europe PMC free full-text search by DOI."""
    if not doi:
        return None
    url = (
        f"https://europepmc.org/webservices/rest/search?query=DOI:{urllib.parse.quote(doi)}&format=json&resultType=core"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            import json

            data = json.loads(r.read())
            results = data.get("resultList", {}).get("result", [])
            for rec in results:
                if rec.get("isOpenAccess") == "Y":
                    full_text_urls = rec.get("fullTextUrlList", {}).get("fullTextUrl", [])
                    for ft in full_text_urls:
                        if ft.get("documentStyle") == "pdf":
                            return ft.get("url")
    except Exception as exc:
        logger.debug("Europe PMC lookup failed for %s: %s", doi, exc)
    return None


def extract_pdf_link_from_landing(html_bytes: bytes) -> str | None:
    """Parse HTML landing page for a direct .pdf link."""
    try:
        html = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        return None
    patterns = [
        r'<meta\s+name="citation_pdf_url"\s+content="([^"]+)"',
        r'href="([^"]+\.pdf[^"]*)"',
        r'data-pdf-url="([^"]+)"',
        r'<link[^>]+type="application/pdf"[^>]+href="([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def download_with_playwright(
    url: str,
    out_path: Path,
    timeout_ms: int = 90_000,
    user_agent: str | None = None,
    referer: str | None = None,
) -> tuple[bool, str]:
    """Attempt download with SSL bypass + download-event + inline fallback."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return False, f"playwright import: {exc}"

    ua = user_agent or USER_AGENTS[0]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=ua,
            accept_downloads=True,
            ignore_https_errors=True,
            extra_http_headers={"Referer": referer} if referer else None,
        )
        page = context.new_page()

        pdf_url: str | None = None
        landing_bytes: bytes | None = None

        def _on_response(response):
            nonlocal pdf_url, landing_bytes
            try:
                ctype = (response.headers.get("content-type") or "").lower()
                if "application/pdf" in ctype and pdf_url is None:
                    pdf_url = response.url
                elif "text/html" in ctype and landing_bytes is None and response.url == url:
                    try:
                        landing_bytes = response.body()
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", _on_response)

        # Strategy 1: download event
        try:
            with page.expect_download(timeout=timeout_ms) as dl_info:
                try:
                    page.goto(url, timeout=timeout_ms, wait_until="commit")
                except Exception:
                    pass
            download = dl_info.value
            download.save_as(str(out_path))
            browser.close()
            if out_path.exists() and out_path.stat().st_size > 50_000:
                head = out_path.read_bytes()[:4]
                if head == b"%PDF":
                    return True, f"download-event {out_path.stat().st_size // 1024} KiB"
                return False, f"download-event non-PDF: {head!r}"
        except Exception:
            pass

        # Strategy 2: navigate + inline PDF response
        try:
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
        except Exception as exc:
            browser.close()
            return False, f"navigation error: {exc}"

        # Strategy 3: parse landing HTML for embedded PDF link
        if pdf_url is None and landing_bytes:
            candidate = extract_pdf_link_from_landing(landing_bytes)
            if candidate:
                if candidate.startswith("/"):
                    from urllib.parse import urljoin

                    candidate = urljoin(url, candidate)
                pdf_url = candidate
                logger.info("  parsed landing → %s", pdf_url[:80])

        if pdf_url is None:
            pdf_url = url

        try:
            resp = context.request.get(pdf_url, timeout=timeout_ms)
        except Exception as exc:
            browser.close()
            return False, f"context.request.get: {exc}"

        body = resp.body()
        browser.close()

        if resp.status != 200:
            return False, f"HTTP {resp.status}"
        if len(body) < 50_000:
            return False, f"small body {len(body)}B"
        if body[:4] != b"%PDF":
            return False, f"non-PDF {body[:40]!r}"

        out_path.write_bytes(body)
        return True, f"inline-pdf {len(body) // 1024} KiB"


def try_all_strategies(gid: str, doi: str, orig_url: str, out_path: Path) -> tuple[bool, str]:
    """Try: original URL → PMC → EuropePMC → multi-UA Playwright."""
    # Already have file?
    if out_path.exists() and out_path.stat().st_size > 50_000:
        return True, "exists"

    attempts: list[tuple[str, str, str | None]] = [
        (orig_url, USER_AGENTS[0], None),
    ]
    if doi:
        pmc = lookup_pmc_alternate(doi)
        if pmc:
            attempts.append((pmc, USER_AGENTS[0], None))
        epmc = lookup_europe_pmc(doi)
        if epmc:
            attempts.append((epmc, USER_AGENTS[0], None))
    # Retry original with Firefox UA + Referer
    if orig_url:
        from urllib.parse import urlparse

        host = urlparse(orig_url).netloc
        attempts.append((orig_url, USER_AGENTS[1], f"https://{host}/"))
        attempts.append((orig_url, USER_AGENTS[2], None))

    for i, (url, ua, ref) in enumerate(attempts, 1):
        logger.info("[%s] attempt %d: %s (UA %s)", gid, i, url[:80], ua[:30])
        ok, reason = download_with_playwright(url, out_path, 60_000, user_agent=ua, referer=ref)
        if ok:
            return True, f"attempt {i}: {reason}"
        logger.info("  → %s", reason)
        time.sleep(0.5)
    return False, "all strategies exhausted"


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--graph-ids",
        default="",
        help="Comma-separated; empty => all MANUAL_UPLOAD_OA_PAYWALLED and MANUAL_UPLOAD_REQUIRED rows",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s: %(message)s")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(args.manifest.open(encoding="utf-8")))
    subset = {g.strip() for g in args.graph_ids.split(",") if g.strip()}
    candidates = [
        r
        for r in rows
        if r["status"] in ("MANUAL_UPLOAD_OA_PAYWALLED", "MANUAL_UPLOAD_REQUIRED", "UNPAYWALL_ERROR")
        and (not subset or r["graph_id"] in subset)
    ]
    logger.info("trying %d candidates with aggressive fetch", len(candidates))

    results = []
    for r in candidates:
        gid = r["graph_id"]
        doi = r["doi"]
        url = r.get("open_access_url") or f"https://doi.org/{doi}" if doi else ""
        if not url:
            logger.warning("no URL for %s", gid)
            results.append((gid, False, "no URL"))
            continue
        target = args.out_dir / f"{gid}.pdf"
        ok, reason = try_all_strategies(gid, doi, url, target)
        results.append((gid, ok, reason))
        if ok:
            logger.info("✓ %s: %s", gid, reason)
        else:
            logger.warning("✗ %s: %s", gid, reason)

    print(f"\nv2 summary: {sum(1 for _, ok, _ in results if ok)} ok / {sum(1 for _, ok, _ in results if not ok)} fail")
    for gid, ok, reason in results:
        marker = "OK  " if ok else "FAIL"
        print(f"  {marker}  {gid}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
