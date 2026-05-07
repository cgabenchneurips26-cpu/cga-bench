#!/usr/bin/env python3
"""Y.1: LLM-extracted constraint catalogue for comparison against CDE.

Calls Qwen3.5-397B-A17B-FP8 (endpoint http://localhost:8013) on
each of the 25 parsed CPG documents in data_release/v5.0/rag_corpus/,
asks it to enumerate hard constraints (MUST / FORBIDDEN / WITHIN /
BEFORE), and persists raw JSON output per CPG. A follow-up analysis
step (run_compare) then diffs the LLM output against CDE's
engine_audit.json (1,049 constraints: MUST=557, FORBIDDEN=212,
WITHIN=215, BEFORE=65).

Usage
-----
    # single-CPG smoke:
    PYTHONPATH=. python scripts/experiments/exp_cde_vs_llm.py --limit 1

    # full 25-CPG extraction:
    PYTHONPATH=. python scripts/experiments/exp_cde_vs_llm.py

    # comparison analysis (after extraction):
    PYTHONPATH=. python scripts/experiments/exp_cde_vs_llm.py --compare

Endpoint is read-only (per .claude/rules/vllm-launch.md) and shared;
calls are serial.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time

import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RAG_CORPUS = ROOT / "data_release" / "v5.0" / "rag_corpus"
OUT_DIR = ROOT / "evidence_pack" / "constraint_comparison"
RAW_DIR = OUT_DIR / "llm_raw"
ENGINE_AUDIT_PATH = ROOT / "evidence_pack" / "ex25_engine_audit" / "engine_audit.json"

ENDPOINT = "http://localhost:8013/v1/chat/completions"
MODEL = "Qwen/Qwen3.5-397B-A17B-FP8"
API_KEY = "sk-no-key-required"

SYSTEM_PROMPT = (
    "You are a clinical-guideline parser. Given a medical guideline's "
    "parsed text, extract every hard constraint the guideline imposes "
    "on actions. Hard constraints are of four types:\n"
    "  MUST       — an action that must be performed\n"
    "  FORBIDDEN  — an action that must not be performed\n"
    "  WITHIN     — an action that must be completed within a time window (minutes)\n"
    "  BEFORE     — an action that must be completed before another action\n"
    "Return ONLY a JSON object with key 'constraints' whose value is a "
    "list of {type, action, deadline_minutes, before_action, source_section} entries. "
    "Deadline_minutes is null for non-WITHIN types; before_action is null for non-BEFORE; "
    "source_section is the heading or section label the constraint comes from, or null. "
    "Do not include soft/recommended guidance. No prose, only JSON."
)


def _http_post(url: str, headers: dict, body: dict, timeout: float = 300.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _build_user_prompt(cpg_text: str, cpg_name: str) -> str:
    head = (
        f"Guideline name: {cpg_name}\n"
        "Below is the parsed guideline text. Extract every hard constraint.\n\n"
        "--- GUIDELINE TEXT START ---\n"
    )
    tail = "\n--- GUIDELINE TEXT END ---"
    # Endpoint max_model_len is 16384; be conservative with trimming.
    max_chars = 28_000
    if len(cpg_text) > max_chars:
        cpg_text = cpg_text[:max_chars] + "\n...[truncated]"
    return head + cpg_text + tail


def _call_qwen(cpg_text: str, cpg_name: str, temperature: float = 0.1) -> dict:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(cpg_text, cpg_name)},
        ],
        "temperature": temperature,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    return _http_post(ENDPOINT, headers, body)


def _parse_parsed_json(path: Path) -> tuple[str, dict]:
    """Return (concatenated_text, raw_dict)."""
    raw = json.loads(path.read_text())
    # parsed.json has a nested structure; flatten any textual fields.
    parts: list[str] = []

    def _walk(node) -> None:
        if isinstance(node, str):
            if node.strip():
                parts.append(node.strip())
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(raw)
    return "\n".join(parts), raw


def _extract_constraint_list(llm_response: dict) -> list[dict]:
    content = llm_response["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # repair attempt: strip stray text around first / last braces
        a, b = content.find("{"), content.rfind("}")
        if a >= 0 and b > a:
            parsed = json.loads(content[a : b + 1])
        else:
            raise
    return parsed.get("constraints") or []


def run_extraction(limit: int | None, force: bool) -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    inputs = sorted(RAG_CORPUS.glob("*.parsed.json"))
    if limit is not None:
        inputs = inputs[:limit]
    print(f"Processing {len(inputs)} CPGs (force={force})")

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "endpoint": ENDPOINT,
        "model": MODEL,
        "n_cpgs": len(inputs),
        "per_cpg": {},
    }
    for p in inputs:
        cpg = p.stem.replace(".parsed", "")
        out_path = RAW_DIR / f"{cpg}.json"
        if out_path.exists() and not force:
            prior = json.loads(out_path.read_text())
            summary["per_cpg"][cpg] = {
                "n_constraints": len(prior.get("constraints") or []),
                "source": "cached",
            }
            print(f"  [cache]  {cpg}: {len(prior.get('constraints') or [])} constraints")
            continue
        text, _ = _parse_parsed_json(p)
        t0 = time.time()
        try:
            resp = _call_qwen(text, cpg)
            constraints = _extract_constraint_list(resp)
        except Exception as e:
            print(f"  [error]  {cpg}: {type(e).__name__}: {e}")
            summary["per_cpg"][cpg] = {"error": str(e)}
            continue
        elapsed = time.time() - t0
        out = {
            "cpg": cpg,
            "model": MODEL,
            "constraints": constraints,
            "elapsed_s": round(elapsed, 2),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        out_path.write_text(json.dumps(out, indent=2) + "\n")
        summary["per_cpg"][cpg] = {
            "n_constraints": len(constraints),
            "elapsed_s": round(elapsed, 2),
            "source": "fresh",
        }
        print(f"  [fresh]  {cpg}: {len(constraints)} constraints in {elapsed:.1f}s")

    summary["total_constraints"] = sum(
        v.get("n_constraints", 0) for v in summary["per_cpg"].values()
    )
    (OUT_DIR / "llm_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_compare() -> dict:
    """Diff LLM extraction against CDE engine_audit."""
    cde = json.loads(ENGINE_AUDIT_PATH.read_text())
    cde_by_type = cde["constraint_type_distribution"]
    cde_total = cde["n_total_constraints"]

    llm_by_type: dict[str, int] = defaultdict(int)
    llm_total = 0
    per_cpg: dict[str, dict] = {}
    for p in sorted(RAW_DIR.glob("*.json")):
        cpg = p.stem
        out = json.loads(p.read_text())
        cs = out.get("constraints") or []
        llm_total += len(cs)
        type_counts = defaultdict(int)
        for c in cs:
            t = str(c.get("type", "")).upper()
            if t in ("MUST", "FORBIDDEN", "WITHIN", "BEFORE"):
                llm_by_type[t] += 1
                type_counts[t] += 1
        per_cpg[cpg] = {"n": len(cs), "by_type": dict(type_counts)}

    ratio = cde_total / llm_total if llm_total else float("inf")
    res = {
        "cde_total": cde_total,
        "cde_by_type": cde_by_type,
        "llm_total": llm_total,
        "llm_by_type": dict(llm_by_type),
        "per_type_ratio": {
            t: round(cde_by_type[t] / llm_by_type[t], 2) if llm_by_type.get(t) else None
            for t in ("MUST", "FORBIDDEN", "WITHIN", "BEFORE")
        },
        "ratio_cde_over_llm": round(ratio, 2),
        "per_cpg": per_cpg,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (OUT_DIR / "compare_summary.json").write_text(json.dumps(res, indent=2) + "\n")

    # Macros
    macros = [
        "% Auto-generated by scripts/experiments/exp_cde_vs_llm.py",
        f"\\providecommand{{\\cdeVsLlmCdeTotal}}{{{cde_total}}}",
        f"\\providecommand{{\\cdeVsLlmLlmTotal}}{{{llm_total}}}",
        f"\\providecommand{{\\cdeVsLlmRatio}}{{{res['ratio_cde_over_llm']:.2f}}}",
    ]
    for t in ("MUST", "FORBIDDEN", "WITHIN", "BEFORE"):
        macros.append(f"\\providecommand{{\\cdeVsLlmCde{t.capitalize()}}}{{{cde_by_type.get(t, 0)}}}")
        macros.append(f"\\providecommand{{\\cdeVsLlmLlm{t.capitalize()}}}{{{llm_by_type.get(t, 0)}}}")
        r = res["per_type_ratio"].get(t)
        if r is not None:
            macros.append(f"\\providecommand{{\\cdeVsLlmRatio{t.capitalize()}}}{{{r:.2f}}}")
    (OUT_DIR / "macros.tex").write_text("\n".join(macros) + "\n")

    print(f"\nCDE total   : {cde_total:>5d}  {cde_by_type}")
    print(f"LLM total   : {llm_total:>5d}  {dict(llm_by_type)}")
    print(f"Ratio       : {res['ratio_cde_over_llm']:.2f}× (CDE / LLM)")
    print(f"Per-type ratio: {res['per_type_ratio']}")
    return res


def main() -> None:
    parser = argparse.ArgumentParser(description="Y.1 CDE vs LLM constraint extraction")
    parser.add_argument("--limit", type=int, default=None, help="Only process N CPGs")
    parser.add_argument("--force", action="store_true", help="Re-extract even if cached")
    parser.add_argument("--compare", action="store_true", help="Skip extraction, just diff")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.compare:
        run_compare()
        return
    run_extraction(args.limit, args.force)
    # Run compare if we now have any cached output
    if any(RAW_DIR.glob("*.json")):
        run_compare()


if __name__ == "__main__":
    main()
