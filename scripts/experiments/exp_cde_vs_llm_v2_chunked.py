#!/usr/bin/env python3
"""Recovery pass 3: chunked prompt for gpt-oss persistent failures.

Seven guidelines consistently returned 0 constraints under both the
original v2 run and the shorter-prompt repair pass, because their
parsed text exceeds gpt-oss's 8192-token context window. This pass
splits each guideline into ≤ 6000-char chunks (snapping to paragraph
boundaries where possible with a 400-char overlap for constraints
that straddle a chunk boundary), calls gpt-oss-120b once per chunk,
merges the returned constraint lists, and de-duplicates by normalised
action text.

Output overwrites the existing (empty) entry in llm_raw_v2/.

Usage:
    PYTHONPATH=. python scripts/experiments/exp_cde_vs_llm_v2_chunked.py
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments.exp_cde_vs_llm import _parse_parsed_json  # noqa: E402
from scripts.experiments.exp_cde_vs_llm_v2_repair import (  # noqa: E402
    SYSTEM_PROMPT_STRICT,
    _candidate_texts,
    _largest_parseable,
)

RAG_CORPUS = ROOT / "data_release" / "v5.0" / "rag_corpus"
RAW_DIR = ROOT / "evidence_pack" / "constraint_comparison" / "llm_raw_v2"

ENDPOINTS = [
    "http://localhost:8013/v1/chat/completions",
    "http://localhost:8013/v1/chat/completions",
    "http://localhost:8013/v1/chat/completions",
]
MODEL = "openai/gpt-oss-120b"
API_KEY = "sk-no-key-required"


def _chunk_text(text: str, chunk_size: int = 6000, overlap: int = 400) -> list[str]:
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_size, n)
        if end < n:
            break_pos = text.rfind("\n\n", max(i, end - 800), end)
            if break_pos > i + chunk_size // 2:
                end = break_pos
        chunks.append(text[i:end])
        if end >= n:
            break
        nxt = end - overlap
        if nxt <= i:
            nxt = end
        i = nxt
    return chunks


def _http_post(url: str, headers: dict, body: dict, timeout: float = 180.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _call_chunk(chunk_text: str, cpg_name: str, chunk_idx: int, n_chunks: int, endpoint: str) -> list[dict]:
    user_prompt = (
        f"Guideline name: {cpg_name}\n"
        f"Chunk {chunk_idx + 1} of {n_chunks}. Extract every hard "
        f"constraint in this chunk. Do not invent constraints not "
        f"present in the text.\n\n--- CHUNK START ---\n"
        + chunk_text
        + "\n--- CHUNK END ---"
    )
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_STRICT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
        "reasoning_effort": "low",
    }
    try:
        resp = _http_post(endpoint, headers, body)
    except Exception as e:
        print(f"    chunk {chunk_idx + 1}/{n_chunks} HTTP error: {type(e).__name__}")
        return []
    msg = resp["choices"][0]["message"]
    for text in _candidate_texts(msg):
        obj = _largest_parseable(text)
        if obj and "constraints" in obj:
            return obj["constraints"] or []
    return []


def _dedupe(merged: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for c in merged:
        t = str(c.get("type", "")).upper()
        a = re.sub(r"\s+", " ", str(c.get("action", "")).strip().lower())
        key = (t, a)
        if not a or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunked-prompt recovery of long gpt-oss CPGs")
    parser.add_argument("--chunk-size", type=int, default=6000)
    parser.add_argument("--overlap", type=int, default=400)
    parser.add_argument("--targets", nargs="+", default=None)
    args = parser.parse_args()

    # Identify remaining empty CPGs unless overridden
    if args.targets:
        targets = args.targets
    else:
        targets = []
        for f in sorted(RAW_DIR.glob("*.json")):
            try:
                r = json.loads(f.read_text())
            except json.JSONDecodeError:
                continue
            if not (r.get("constraints") or []):
                targets.append(f.stem)
    print(f"Chunked recovery targets ({len(targets)}):")
    for t in targets:
        print(f"  - {t}")

    endpoint_cursor = 0
    recovered, still_empty = 0, 0
    for cpg in targets:
        src = RAG_CORPUS / f"{cpg}.parsed.json"
        if not src.exists():
            print(f"  [miss]  {cpg}: parsed source not found")
            still_empty += 1
            continue
        text, _ = _parse_parsed_json(src)
        chunks = _chunk_text(text, args.chunk_size, args.overlap)
        print(f"  [chunks] {cpg}: {len(text)} chars → {len(chunks)} chunks")
        merged: list[dict] = []
        t0 = time.time()
        for i, ch in enumerate(chunks):
            endpoint = ENDPOINTS[endpoint_cursor % len(ENDPOINTS)]
            endpoint_cursor += 1
            cs = _call_chunk(ch, cpg, i, len(chunks), endpoint)
            merged.extend(cs)
        elapsed = time.time() - t0
        deduped = _dedupe(merged)
        out_file = RAW_DIR / f"{cpg}.json"
        out_file.write_text(
            json.dumps(
                {
                    "cpg": cpg,
                    "model": MODEL,
                    "endpoint": "chunked",
                    "chunks": len(chunks),
                    "constraints": deduped,
                    "elapsed_s": round(elapsed, 2),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "repair_round": 3,
                },
                indent=2,
            )
            + "\n"
        )
        marker = "recovered" if deduped else "still-empty"
        print(f"  [{marker}]  {cpg}: {len(deduped)} deduped constraints in {elapsed:.1f}s")
        if deduped:
            recovered += 1
        else:
            still_empty += 1

    print(f"\nChunked-recovery complete: {recovered} recovered, {still_empty} still empty")


if __name__ == "__main__":
    main()
