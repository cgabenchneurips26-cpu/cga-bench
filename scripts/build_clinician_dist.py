#!/usr/bin/env python3
"""Bundle ``clinician_validation/ClinicalValidation.jsx`` into the Babel
Standalone-ready ``dist/ClinicalValidation.source.js`` used by the static
demo site.

Babel Standalone (loaded from a ``<script type="text/babel">`` tag in
``dist/index.html``) cannot resolve ES module imports, so we:

1. Replace ``import { ... } from "react";`` with ``const { ... } = React;``
2. Replace the ``import { SCENARIOS as GENERATED_SCENARIOS } from
   "./scenario_data.js"`` line with a ``window.SCENARIOS`` lookup, since the
   scenario data is loaded separately via a ``<script>`` tag.
3. Drop the ``export default`` prefix — the component becomes a top-level
   function declaration that Babel can then reference by name.
4. Propagate protocol/git/build-date constants into ``window.*`` so the
   page can override them at load time.

Run via ``make guide`` or directly::

    PYTHONPATH=. python scripts/build_clinician_dist.py
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


REACT_IMPORT_RE = re.compile(r'^import\s+\{([^}]+)\}\s+from\s+"react";', re.MULTILINE)
SCENARIO_IMPORT_RE = re.compile(
    r"^import\s+\{\s*SCENARIOS\s+as\s+GENERATED_SCENARIOS\s*\}"
    r'\s+from\s+"\./scenario_data\.js";',
    re.MULTILINE,
)
EXPORT_DEFAULT_RE = re.compile(r"^export\s+default\s+", re.MULTILINE)


def transform_jsx(source: str) -> str:
    """Apply the dist-specific import/export rewrites."""
    react_match = REACT_IMPORT_RE.search(source)
    if not react_match:
        raise RuntimeError('Expected `import { ... } from "react";` at the top of the JSX file')
    bindings = react_match.group(1).strip()
    react_destructure = f"const {{{bindings}}} = React;"
    out = REACT_IMPORT_RE.sub(react_destructure, source, count=1)

    scenario_match = SCENARIO_IMPORT_RE.search(out)
    if not scenario_match:
        raise RuntimeError(
            'Expected `import { SCENARIOS as GENERATED_SCENARIOS } from "./scenario_data.js";` — '
            "keep the named-import form so the dist bundler can rewrite it."
        )
    out = SCENARIO_IMPORT_RE.sub(
        'const GENERATED_SCENARIOS = (typeof window !== "undefined" && window.SCENARIOS) || [];',
        out,
        count=1,
    )

    out = EXPORT_DEFAULT_RE.sub("", out, count=1)
    return out


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    src_path = root / "clinician_validation" / "ClinicalValidation.jsx"
    dst_path = root / "clinician_validation" / "dist" / "ClinicalValidation.source.js"

    if not src_path.exists():
        logger.error("Missing source: %s", src_path)
        return 2
    if not dst_path.parent.is_dir():
        logger.error("Missing dist dir: %s", dst_path.parent)
        return 2

    src = src_path.read_text(encoding="utf-8")
    try:
        transformed = transform_jsx(src)
    except RuntimeError as exc:
        logger.error(str(exc))
        return 3

    header = (
        "// GENERATED FILE — DO NOT EDIT BY HAND.\n"
        "// Source: clinician_validation/ClinicalValidation.jsx\n"
        "// Run `python scripts/build_clinician_dist.py` (or `make guide`) to regenerate.\n\n"
    )
    dst_path.write_text(header + transformed, encoding="utf-8")
    logger.info("Wrote %s (%d lines)", dst_path, transformed.count("\n") + 1)

    # v5.0.2: Mirror plain-asset data files (no transform needed) and the
    # subset of source PDFs the modal links to. Files with the same content
    # are skipped to avoid spurious mtime churn.
    import shutil

    plain_data_files = [
        "action_descriptions_ko.js",
        "action_rationales_by_guideline.js",
        "guideline_full_recommendations.js",
    ]
    cv_root = root / "clinician_validation"
    for name in plain_data_files:
        src_file = cv_root / name
        dst_file = cv_root / "dist" / name
        if not src_file.exists():
            logger.warning("Plain data file missing — skipped: %s", src_file)
            continue
        if dst_file.exists() and dst_file.read_bytes() == src_file.read_bytes():
            continue
        shutil.copy2(src_file, dst_file)
        logger.info("Mirrored %s -> dist/", name)

    pdf_map = {
        "SSC-2021-Sepsis-Guidelines.pdf": root / "cpg_sources" / "pdfs" / "SSC-2021-Sepsis-Guidelines.pdf",
        "KDIGO-2012-AKI-Contrast-Section.pdf": root / "cpg_sources" / "pdfs" / "KDIGO-2012-AKI-Contrast-Section.pdf",
        "GINA-2024-Main-Report.pdf": root / "cpg_sources" / "pdfs" / "GINA-2024-Main-Report.pdf",
    }
    pdf_dir = cv_root / "dist" / "guidelines"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    for filename, src_pdf in pdf_map.items():
        dst_pdf = pdf_dir / filename
        if not src_pdf.exists():
            logger.warning("Source PDF missing — skipped: %s", src_pdf)
            continue
        if dst_pdf.exists() and dst_pdf.stat().st_size == src_pdf.stat().st_size:
            continue
        shutil.copy2(src_pdf, dst_pdf)
        logger.info("Mirrored %s -> dist/guidelines/", filename)

    return 0


if __name__ == "__main__":
    sys.exit(main())
