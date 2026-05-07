"""Playwright-based PDF fetcher for Cloudflare-protected OA URLs.

When Unpaywall returns an OA URL but direct `curl`/`requests` returns a
Cloudflare "Just a moment..." challenge page, this script uses Playwright
with headed Chromium to render the JS challenge, acquire cf_clearance
cookie, then download the PDF.

Reads the acquisition manifest CSV, targets rows with status
MANUAL_UPLOAD_OA_PAYWALLED (previously failed OA downloads), attempts a
real-browser fetch, and saves to data/source_pdfs/<graph_id>.pdf on
success.

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/playwright_pdf_fetch.py \
        --manifest data/source_pdfs/acquisition_manifest.csv \
        --target-status MANUAL_UPLOAD_OA_PAYWALLED \
        --out-dir data/source_pdfs \
        --headless
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def download_via_playwright(
    url: str, out_path: Path, timeout_ms: int = 60_000, headless: bool = True
) -> tuple[bool, str]:
    """Attempt to download the URL as a PDF via real Chromium.

    Returns (ok, reason). On success out_path exists and contains a valid PDF.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return False, f"playwright import failed: {exc}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )
        page = context.new_page()
        pdf_url: str | None = None

        # Listen for the first PDF response; some publisher pages redirect
        # through a CF-protected HTML landing first, then serve the PDF.
        def _on_response(response):
            nonlocal pdf_url
            if pdf_url:
                return
            ctype = (response.headers.get("content-type") or "").lower()
            if "application/pdf" in ctype:
                pdf_url = response.url

        page.on("response", _on_response)

        # Server-initiated download path: when Content-Disposition: attachment,
        # Chromium fires a download event and goto raises. Capture the download
        # instead of treating it as a failure.
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
                    return True, f"download-event saved {out_path.stat().st_size // 1024} KiB"
                return False, f"download-event produced non-PDF {head!r}"
            return False, "download-event produced too-small file"
        except Exception:
            pass  # no download event — fall through to inline-PDF path

        try:
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
        except Exception as exc:
            browser.close()
            return False, f"navigation error: {exc}"

        # If the page itself is the PDF (content-type application/pdf),
        # Chromium auto-downloads or shows the embedded viewer. Some
        # publishers redirect to an HTML shell with <iframe> / <embed>
        # pointing at the actual PDF.
        if pdf_url is None:
            # Check DOM for <iframe>/<embed> with .pdf src
            try:
                pdf_url = page.evaluate(
                    "() => {"
                    '  const el = document.querySelector(\'iframe[src*=".pdf"], '
                    'embed[src*=".pdf"], object[data*=".pdf"]\');'
                    "  return el ? (el.src || el.data) : null;"
                    "}"
                )
            except Exception:
                pass

        if pdf_url is None:
            pdf_url = url  # last resort: fetch the original URL directly

        # Download via context (persists cf_clearance cookie)
        try:
            resp = context.request.get(pdf_url, timeout=timeout_ms)
        except Exception as exc:
            browser.close()
            return False, f"context.request.get error: {exc}"

        if resp.status != 200:
            body = resp.body()
            browser.close()
            return False, f"HTTP {resp.status}, body head {body[:40]!r}"

        body = resp.body()
        browser.close()

        if len(body) < 50_000:
            return False, f"too small ({len(body)} bytes)"
        if body[:4] != b"%PDF":
            return False, f"not a PDF ({body[:40]!r})"

        out_path.write_bytes(body)
        return True, f"downloaded {len(body) // 1024} KiB"


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target-status", default="MANUAL_UPLOAD_OA_PAYWALLED")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", action="store_false", dest="headless")
    parser.add_argument(
        "--graph-ids",
        default="",
        help="Optional comma-separated subset; otherwise all matching rows",
    )
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(args.manifest.open(encoding="utf-8")))
    subset = {g.strip() for g in args.graph_ids.split(",") if g.strip()}
    targets = [
        r
        for r in rows
        if r["status"] == args.target_status
        and r.get("open_access_url", "").strip()
        and (not subset or r["graph_id"] in subset)
    ]
    logger.info("Attempting Playwright fetch for %d rows", len(targets))

    ok_count = 0
    fail_count = 0
    results: list[tuple[str, bool, str]] = []
    for i, r in enumerate(targets, start=1):
        gid = r["graph_id"]
        url = r["open_access_url"]
        target = args.out_dir / f"{gid}.pdf"
        if target.exists() and target.stat().st_size > 50_000:
            logger.info("[%d/%d] %s already exists, skipping", i, len(targets), gid)
            ok_count += 1
            results.append((gid, True, "exists"))
            continue
        logger.info("[%d/%d] %s <- %s", i, len(targets), gid, url)
        ok, reason = download_via_playwright(url, target, timeout_ms=args.timeout_ms, headless=args.headless)
        if ok:
            ok_count += 1
            logger.info("  OK: %s", reason)
        else:
            fail_count += 1
            logger.warning("  FAIL: %s", reason)
            if target.exists():
                target.unlink()
        results.append((gid, ok, reason))

    print(f"\nPlaywright fetch summary: {ok_count} ok / {fail_count} failed")
    for gid, ok, reason in results:
        marker = "OK  " if ok else "FAIL"
        print(f"  {marker}  {gid}: {reason}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
