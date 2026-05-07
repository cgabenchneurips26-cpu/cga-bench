#!/usr/bin/env python3
"""Track A v3 cataloguer — generic LLM-family-parameterized constraint extraction.

Mirrors exp_cde_vs_llm_v2.py but accepts arbitrary endpoint+model via CLI.
Targets a third (or more) LLM-family extraction to verify the paper's
5.50x/5.60x main-finding pillar 3 ratio is not Qwen+OpenAI coincidence.

Usage (when endpoint is live)
-----------------------------
    PYTHONPATH=..:. python scripts/experiments/exp_cde_vs_llm_v3.py \
        --endpoint http://localhost:8013/v1/chat/completions \
        --model meta-llama/Llama-4-Scout-17B-16E-Instruct \
        --output-suffix v3 \
        --limit 1                          # smoke test 1 CPG

    PYTHONPATH=..:. python scripts/experiments/exp_cde_vs_llm_v3.py \
        --endpoint http://localhost:8013/v1/chat/completions \
        --model meta-llama/Llama-4-Scout-17B-16E-Instruct \
        --output-suffix v3                 # full 25 CPGs

    PYTHONPATH=..:. python scripts/experiments/exp_cde_vs_llm_v3.py \
        --output-suffix v3 --compare       # post-extraction diff vs CDE

Dry-run (no endpoint)
---------------------
    python scripts/experiments/exp_cde_vs_llm_v3.py
    # Prints planned config and exits without HTTP calls.

Outputs
-------
    evidence_pack/constraint_comparison/llm_raw_<suffix>/<CPG>.json (25 files)
    evidence_pack/constraint_comparison/llm_summary_<suffix>.json
    evidence_pack/constraint_comparison/macros_<suffix>.tex (compare mode)

Reuse from v1
-------------
    SYSTEM_PROMPT, _build_user_prompt, _parse_parsed_json, _extract_constraint_list
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Reuse v1 utilities (prompt, text flatten). Local _extract_constraint_list
# overrides v1's content-only parser so reasoning-mode models (gpt-oss,
# DeepSeek-R1) can fall back to `reasoning` field, and so single-dict
# `constraints` outputs (R1 schema-deviation) get coerced to empty list
# instead of crashing the aggregator.
from scripts.experiments.exp_cde_vs_llm import (  # noqa: E402
    SYSTEM_PROMPT,
    _build_user_prompt,
    _parse_parsed_json,
)


def _extract_constraint_list(llm_response: dict) -> list[dict]:
    """Robust constraint extractor across content/reasoning fields and schemas.

    Handles three observed deviations beyond v1's content-only path:
      1. Reasoning-mode models put JSON in `reasoning` field (gpt-oss).
      2. R1-style models occasionally return `constraints` as a single dict
         instead of a list of dicts -> coerce to empty (no typed counts).
      3. R1-style models occasionally inject string elements alongside dicts
         -> filter to dicts only.
    """
    msg = llm_response["choices"][0]["message"]
    parsed: dict | None = None
    for field in ("content", "reasoning"):
        v = msg.get(field)
        if not v:
            continue
        try:
            candidate = json.loads(v)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", v)
            if not m:
                continue
            try:
                candidate = json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
        if isinstance(candidate, dict) and "constraints" in candidate:
            parsed = candidate
            break
    if parsed is None:
        return []
    cs = parsed.get("constraints") or []
    if isinstance(cs, dict):
        return []
    if not isinstance(cs, list):
        return []
    return [c for c in cs if isinstance(c, dict)]


RAG_CORPUS = ROOT / "data_release" / "v5.0" / "rag_corpus"
OUT_DIR = ROOT / "evidence_pack" / "constraint_comparison"
ENGINE_AUDIT_PATH = ROOT / "evidence_pack" / "ex25_engine_audit" / "engine_audit.json"

DEFAULT_API_KEY = "sk-no-key-required"
DEFAULT_TIMEOUT = 300.0
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.1


def _http_post(url: str, headers: dict, body: dict, timeout: float = DEFAULT_TIMEOUT) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _call_llm(
    cpg_text: str,
    cpg_name: str,
    endpoint: str,
    model: str,
    api_key: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """Generic OpenAI-compatible chat-completions call."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(cpg_text, cpg_name)},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    return _http_post(endpoint, headers, body)


def _process_one_cpg(
    p: Path,
    raw_dir: Path,
    endpoint: str,
    model: str,
    api_key: str,
    force: bool,
) -> tuple[str, dict]:
    """Process a single CPG. Thread-safe (no shared mutable state besides FS writes)."""
    cpg = p.stem.replace(".parsed", "")
    out_path = raw_dir / f"{cpg}.json"
    if out_path.exists() and not force:
        prior = json.loads(out_path.read_text())
        return cpg, {"n_constraints": len(prior.get("constraints") or []), "source": "cached"}
    text, _ = _parse_parsed_json(p)
    t0 = time.time()
    try:
        resp = _call_llm(text, cpg, endpoint, model, api_key)
        constraints = _extract_constraint_list(resp)
    except Exception as e:
        return cpg, {"error": f"{type(e).__name__}: {e}"}
    elapsed = time.time() - t0
    out = {
        "cpg": cpg,
        "model": model,
        "constraints": constraints,
        "elapsed_s": round(elapsed, 2),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    return cpg, {
        "n_constraints": len(constraints),
        "elapsed_s": round(elapsed, 2),
        "source": "fresh",
    }


def run_extraction(
    raw_dir: Path,
    summary_path: Path,
    endpoint: str,
    model: str,
    api_key: str,
    limit: int | None,
    force: bool,
    workers: int = 1,
) -> dict:
    raw_dir.mkdir(parents=True, exist_ok=True)
    inputs = sorted(RAG_CORPUS.glob("*.parsed.json"))
    if limit is not None:
        inputs = inputs[:limit]
    print(f"Processing {len(inputs)} CPGs (workers={workers}, force={force}, endpoint={endpoint}, model={model})")

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "endpoint": endpoint,
        "model": model,
        "n_cpgs": len(inputs),
        "workers": workers,
        "per_cpg": {},
    }
    print_lock = threading.Lock()

    def _process_and_log(p: Path) -> tuple[str, dict]:
        cpg, rec = _process_one_cpg(p, raw_dir, endpoint, model, api_key, force)
        with print_lock:
            if "error" in rec:
                print(f"  [error]  {cpg}: {rec['error']}")
            elif rec.get("source") == "cached":
                print(f"  [cache]  {cpg}: {rec['n_constraints']} constraints")
            else:
                print(f"  [fresh]  {cpg}: {rec['n_constraints']} constraints in {rec['elapsed_s']}s")
        return cpg, rec

    if workers <= 1:
        for p in inputs:
            cpg, rec = _process_and_log(p)
            summary["per_cpg"][cpg] = rec
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_process_and_log, p) for p in inputs]
            for fut in as_completed(futures):
                cpg, rec = fut.result()
                summary["per_cpg"][cpg] = rec

    summary["total_constraints"] = sum(v.get("n_constraints", 0) for v in summary["per_cpg"].values())
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_compare(raw_dir: Path, output_suffix: str) -> dict:
    """Diff LLM extraction (raw_dir) against CDE engine_audit."""
    cde = json.loads(ENGINE_AUDIT_PATH.read_text())
    cde_by_type = cde["constraint_type_distribution"]
    cde_total = cde["n_total_constraints"]

    llm_by_type: dict[str, int] = defaultdict(int)
    llm_total = 0
    per_cpg: dict[str, dict] = {}
    for p in sorted(raw_dir.glob("*.json")):
        cpg = p.stem
        out = json.loads(p.read_text())
        cs_raw = out.get("constraints") or []
        # Defensive: cached files from reasoning models (R1) may store
        # `constraints` as a single dict or contain string elements.
        if isinstance(cs_raw, list):
            cs = [c for c in cs_raw if isinstance(c, dict)]
        else:
            cs = []
        llm_total += len(cs)
        type_counts: defaultdict[str, int] = defaultdict(int)
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
        "output_suffix": output_suffix,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (OUT_DIR / f"compare_summary_{output_suffix}.json").write_text(json.dumps(res, indent=2) + "\n")

    macros = [
        f"% Auto-generated by exp_cde_vs_llm_v3.py (suffix={output_suffix})",
        f"\\providecommand{{\\cdeVsLlm{output_suffix.capitalize()}CdeTotal}}{{{cde_total}}}",
        f"\\providecommand{{\\cdeVsLlm{output_suffix.capitalize()}LlmTotal}}{{{llm_total}}}",
        f"\\providecommand{{\\cdeVsLlm{output_suffix.capitalize()}Ratio}}{{{res['ratio_cde_over_llm']:.2f}}}",
    ]
    (OUT_DIR / f"macros_{output_suffix}.tex").write_text("\n".join(macros) + "\n")

    print(f"\nCDE total   : {cde_total:>5d}  {cde_by_type}")
    print(f"LLM total   : {llm_total:>5d}  {dict(llm_by_type)}")
    print(f"Ratio       : {res['ratio_cde_over_llm']:.2f}× (CDE / LLM)")
    return res


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        type=str,
        default=None,
        help="OpenAI-compatible chat-completions URL. If omitted, dry-run prints config and exits.",
    )
    parser.add_argument("--model", type=str, default=None, help="Model identifier string passed to the endpoint.")
    parser.add_argument(
        "--output-suffix",
        type=str,
        default="v3",
        help="Output file suffix: llm_raw_<suffix>/, llm_summary_<suffix>.json, etc.",
    )
    parser.add_argument("--api-key", type=str, default=DEFAULT_API_KEY)
    parser.add_argument("--limit", type=int, default=None, help="Smoke test on first N CPGs.")
    parser.add_argument("--force", action="store_true", help="Re-extract even if cached.")
    parser.add_argument("--compare", action="store_true", help="Skip extraction, just diff vs CDE.")
    parser.add_argument(
        "--workers",
        type=int,
        default=25,
        help="Concurrent threads for CPG extraction (default 25 = all CPGs in parallel; vllm queues internally beyond max-num-seqs).",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_dir = OUT_DIR / f"llm_raw_{args.output_suffix}"
    summary_path = OUT_DIR / f"llm_summary_{args.output_suffix}.json"

    if args.compare:
        if not raw_dir.exists():
            print(f"ERROR: {raw_dir} does not exist; run extraction first.", file=sys.stderr)
            return 2
        run_compare(raw_dir, args.output_suffix)
        return 0

    if not args.endpoint or not args.model:
        print("=== DRY RUN (--endpoint and --model required for live extraction) ===")
        print(f"  output suffix : {args.output_suffix}")
        print(f"  raw dir       : {raw_dir}")
        print(f"  summary       : {summary_path}")
        print(f"  RAG corpus    : {RAG_CORPUS}  ({len(list(RAG_CORPUS.glob('*.parsed.json')))} CPGs)")
        print("  Provide --endpoint and --model to run extraction.")
        return 0

    run_extraction(raw_dir, summary_path, args.endpoint, args.model, args.api_key, args.limit, args.force, args.workers)
    if any(raw_dir.glob("*.json")):
        run_compare(raw_dir, args.output_suffix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
