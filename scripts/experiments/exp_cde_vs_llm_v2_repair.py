#!/usr/bin/env python3
"""v2 repair: retry 10 gpt-oss CPG extractions that returned 0 constraints.

Tactics:
  - Bump max_tokens to 8000 (model max=8192)
  - Force reasoning_effort=low via extra_body
  - Swap SYSTEM_PROMPT to one explicitly forbidding any narrative /
    reasoning output
  - More aggressive JSON extraction: first try message.content, then
    reasoning, then tool_calls[0].function.arguments; for each candidate
    scan all `{...}` substrings and take the largest-parseable one

Usage:
    PYTHONPATH=. python scripts/experiments/exp_cde_vs_llm_v2_repair.py
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

from scripts.experiments.exp_cde_vs_llm import (  # noqa: E402
    _build_user_prompt,
    _parse_parsed_json,
)

RAG_CORPUS = ROOT / "data_release" / "v5.0" / "rag_corpus"
OUT_DIR = ROOT / "evidence_pack" / "constraint_comparison"
RAW_DIR = OUT_DIR / "llm_raw_v2"

ENDPOINTS = [
    "http://localhost:8013/v1/chat/completions",
    "http://localhost:8013/v1/chat/completions",
    "http://localhost:8013/v1/chat/completions",
]
MODEL = "openai/gpt-oss-120b"
API_KEY = "sk-no-key-required"

# Stricter prompt: no thinking, output only raw JSON
SYSTEM_PROMPT_STRICT = (
    "Return ONLY JSON. No thinking. "
    'Schema: {"constraints":[{"type":"MUST|FORBIDDEN|WITHIN|BEFORE",'
    '"action":"...","deadline_minutes":null,"before_action":null,'
    '"source_section":null}]}. '
    "Hard constraints only."
)


def _http_post(url: str, headers: dict, body: dict, timeout: float = 300.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _call_oss_strict(cpg_text: str, cpg_name: str, endpoint: str) -> dict:
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_STRICT},
            {"role": "user", "content": _build_user_prompt(cpg_text, cpg_name)},
        ],
        "temperature": 0.1,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
        # gpt-oss OpenAI-Reasoning API — ask for minimal reasoning
        "reasoning_effort": "low",
    }
    return _http_post(endpoint, headers, body)


def _candidate_texts(msg: dict) -> list[str]:
    out: list[str] = []
    for k in ("content", "reasoning"):
        v = msg.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v)
    # Tool-call path
    for tc in msg.get("tool_calls") or []:
        fn = (tc or {}).get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str) and args.strip():
            out.append(args)
    return out


def _largest_parseable(s: str) -> dict | None:
    """Find every {...} substring, return the one with the most keys."""
    best: dict | None = None
    best_size = -1
    # Greedy: all '{' … '}' substrings (outer to inner via stack scan)
    opens: list[int] = []
    for i, ch in enumerate(s):
        if ch == "{":
            opens.append(i)
        elif ch == "}" and opens:
            start = opens.pop()
            sub = s[start : i + 1]
            try:
                obj = json.loads(sub)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                size = len(obj.get("constraints") or [])
                if size > best_size:
                    best_size = size
                    best = obj
    return best


def _extract_constraint_list(llm_response: dict) -> list[dict]:
    msg = llm_response["choices"][0]["message"]
    for text in _candidate_texts(msg):
        obj = _largest_parseable(text)
        if obj and "constraints" in obj:
            return obj["constraints"] or []
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 repair — retry empty gpt-oss CPGs")
    parser.add_argument("--targets", nargs="+", default=None)
    args = parser.parse_args()

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

    print(f"Repair targets ({len(targets)}):")
    for t in targets:
        print(f"  - {t}")

    endpoint_cursor = 0
    succeeded, failed = 0, 0
    for cpg in targets:
        src = RAG_CORPUS / f"{cpg}.parsed.json"
        if not src.exists():
            print(f"  [miss]  {cpg}: parsed source not found")
            failed += 1
            continue
        text, _ = _parse_parsed_json(src)
        endpoint = ENDPOINTS[endpoint_cursor % len(ENDPOINTS)]
        endpoint_cursor += 1
        t0 = time.time()
        try:
            resp = _call_oss_strict(text, cpg, endpoint)
            cs = _extract_constraint_list(resp)
        except Exception as e:
            print(f"  [error] {cpg}: {type(e).__name__}: {str(e)[:100]}")
            failed += 1
            continue
        elapsed = time.time() - t0
        out_file = RAW_DIR / f"{cpg}.json"
        out_file.write_text(
            json.dumps(
                {
                    "cpg": cpg,
                    "model": MODEL,
                    "endpoint": endpoint,
                    "constraints": cs,
                    "elapsed_s": round(elapsed, 2),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "repair_round": 2,
                },
                indent=2,
            )
            + "\n"
        )
        marker = "fresh" if cs else "still-empty"
        print(
            f"  [{marker}]  {cpg}: {len(cs)} in {elapsed:.1f}s "
            f"(ep={endpoint.split(':')[-1].split('/')[0]})"
        )
        if cs:
            succeeded += 1
        else:
            failed += 1

    print(f"\nRepair complete: {succeeded} recovered, {failed} still empty")


if __name__ == "__main__":
    main()
