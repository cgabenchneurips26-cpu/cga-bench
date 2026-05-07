#!/usr/bin/env python3
"""Y.3 replication pillar: second LLM catalogue via gpt-oss-120b on 145.

Mirrors exp_cde_vs_llm.py but switches endpoint + model to gpt-oss-120b
at http://localhost:8013 (or 30015 / 30025 for sharded load).
Adapts to gpt-oss's reasoning-mode response shape: the "content" field
is often null and the extractable JSON lives in "reasoning" (or in
rare cases "tool_calls"). We parse both paths and repair via regex.

Purpose: check whether the Qwen3.5-397B nested-subset finding
(ASC∩CwT∩PAF collapsing to CwT alone under LLM catalogue; strict-FA
5.5× CDE) replicates on a different LLM family.

Outputs
-------
  evidence_pack/constraint_comparison/llm_raw_v2/<CPG>.json    (25 files)
  evidence_pack/constraint_comparison/llm_summary_v2.json

Usage
-----
    PYTHONPATH=. python scripts/experiments/exp_cde_vs_llm_v2.py
    PYTHONPATH=. python scripts/experiments/exp_cde_vs_llm_v2.py --limit 1  # smoke
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Reuse prompt + text-flatten utilities from v1
from scripts.experiments.exp_cde_vs_llm import (  # noqa: E402
    SYSTEM_PROMPT,
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


def _http_post(url: str, headers: dict, body: dict, timeout: float = 300.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _call_oss(cpg_text: str, cpg_name: str, endpoint: str, temperature: float = 0.1) -> dict:
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(cpg_text, cpg_name)},
        ],
        "temperature": temperature,
        "max_tokens": 6144,
        "response_format": {"type": "json_object"},
    }
    return _http_post(endpoint, headers, body)


def _extract_constraint_list(llm_response: dict) -> list[dict]:
    """gpt-oss may return JSON in content, reasoning, or not at all."""
    msg = llm_response["choices"][0]["message"]
    for field in ("content", "reasoning"):
        v = msg.get(field)
        if not v:
            continue
        try:
            parsed = json.loads(v)
            if isinstance(parsed, dict) and "constraints" in parsed:
                return parsed["constraints"] or []
        except json.JSONDecodeError:
            # Look for an embedded JSON object
            m = re.search(r"\{[\s\S]*\}", v)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, dict) and "constraints" in parsed:
                        return parsed["constraints"] or []
                except json.JSONDecodeError:
                    pass
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Y.3 replication: gpt-oss-120b catalogue")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    inputs = sorted(RAG_CORPUS.glob("*.parsed.json"))
    if args.limit:
        inputs = inputs[: args.limit]

    endpoint_cursor = 0
    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "endpoints": ENDPOINTS,
        "model": MODEL,
        "n_cpgs": len(inputs),
        "per_cpg": {},
    }
    for p in inputs:
        cpg = p.stem.replace(".parsed", "")
        out = RAW_DIR / f"{cpg}.json"
        if out.exists() and not args.force:
            try:
                prior = json.loads(out.read_text())
                cs = prior.get("constraints") or []
                summary["per_cpg"][cpg] = {"n_constraints": len(cs), "source": "cached"}
                print(f"  [cache]  {cpg}: {len(cs)}")
                continue
            except json.JSONDecodeError:
                pass
        text, _ = _parse_parsed_json(p)
        endpoint = ENDPOINTS[endpoint_cursor % len(ENDPOINTS)]
        endpoint_cursor += 1
        t0 = time.time()
        try:
            resp = _call_oss(text, cpg, endpoint)
            cs = _extract_constraint_list(resp)
        except Exception as e:
            print(f"  [error]  {cpg}: {type(e).__name__}: {str(e)[:80]}")
            summary["per_cpg"][cpg] = {"error": str(e)[:200]}
            continue
        elapsed = time.time() - t0
        out.write_text(
            json.dumps(
                {
                    "cpg": cpg,
                    "model": MODEL,
                    "endpoint": endpoint,
                    "constraints": cs,
                    "elapsed_s": round(elapsed, 2),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
            + "\n"
        )
        summary["per_cpg"][cpg] = {"n_constraints": len(cs), "elapsed_s": round(elapsed, 2), "source": "fresh"}
        print(f"  [fresh]  {cpg}: {len(cs)} in {elapsed:.1f}s (ep={endpoint.split(':')[-1].split('/')[0]})")

    summary["total_constraints"] = sum(
        v.get("n_constraints", 0) for v in summary["per_cpg"].values()
    )
    (OUT_DIR / "llm_summary_v2.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nTotal v2 constraints: {summary['total_constraints']}")
    print(f"Saved: {OUT_DIR / 'llm_summary_v2.json'}")


if __name__ == "__main__":
    main()
