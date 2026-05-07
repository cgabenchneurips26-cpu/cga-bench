#!/usr/bin/env python3
"""Classify v6-only actions (kdigo_contrast_aki) into:
  - source-explicit  : action verb_noun is literally present in corpus
  - source-implicit  : action is a clinical paraphrase of corpus content
  - author-injection : action has no support in corpus

Uses Qwen3.5-397B-A17B-FP8 (highest-capability available LLM) at 144:30001
as judge. Corpus = data_release/v5.0/rag_corpus/KDIGO-2012-Contrast-AKI.parsed.json.

Output: reports/path_d_day1/v6_only_action_classification.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO.parent))

V6_ONLY = REPO / "reports" / "path_d_day1" / "_kdigo_v6_only_actions.json"
CORPUS = REPO / "data_release" / "v5.0" / "rag_corpus" / "KDIGO-2012-Contrast-AKI.parsed.json"
REPORT = REPO / "reports" / "path_d_day1" / "v6_only_action_classification.md"

ENDPOINT = "http://localhost:8013/v1"
MODEL = "Qwen/Qwen3.5-397B-A17B-FP8"

CLASSIFY_SYSTEM = """\
You are a clinical-guideline analyst auditing whether candidate actions are grounded in a source guideline document.

For each action, classify it as one of:
- source-explicit   : the action verb+object phrase appears verbatim or near-verbatim in the source corpus.
- source-implicit   : the action is a reasonable paraphrase or operationalization of an explicit corpus statement (e.g., "monitor_scr_48_72h" derives from "measure serum creatinine at 48-72 hours").
- author-injection  : the action has no support in the corpus — neither literal nor implicit. It was added by a benchmark author.

Output a JSON array of objects, one per action, in input order, with fields:
  action_id      : the input id (snake_case)
  classification : one of the three labels above
  rationale      : ≤ 25 words explaining the call (cite a corpus phrase if explicit/implicit)
"""


def call_llm(actions: list[str], corpus_text: str) -> list[dict]:
    """Single batched LLM call to classify a chunk of actions."""
    from cga_bench.agent_runner.llm_provider import VLLMProvider, LLMConfig, LLMBackend, LLMMessage

    cfg = LLMConfig(
        backend=LLMBackend.VLLM, model=MODEL, base_url=ENDPOINT,
        api_key="sk-no-key-required", temperature=0.0, max_tokens=4096, timeout=180.0,
    )
    prov = VLLMProvider(cfg)
    user = (
        f"SOURCE CORPUS (KDIGO 2012 Clinical Practice Guideline for Acute Kidney Injury, contrast-induced section):\n\n{corpus_text}\n\n"
        f"---\n\nACTIONS TO CLASSIFY (snake_case, output array in same order):\n"
        + "\n".join(f"- {a}" for a in actions)
        + "\n\nReturn JSON array only, no prose."
    )
    msgs = [LLMMessage(role="system", content=CLASSIFY_SYSTEM), LLMMessage(role="user", content=user)]
    resp = prov.complete(msgs)
    txt = resp.content.strip()
    # strip code-fence
    txt = re.sub(r"```(?:json)?\s*\n?", "", txt).rstrip("`").strip()
    # find array
    m = re.search(r"\[\s*\{", txt)
    if m:
        end = txt.rfind("]")
        if end > m.start():
            txt = txt[m.start():end + 1]
    try:
        data = json.loads(txt)
    except json.JSONDecodeError as e:
        print(f"  WARN: parse fail: {e}; raw[:200]={resp.content[:200]!r}")
        return []
    return data if isinstance(data, list) else []


def main() -> int:
    actions = json.loads(V6_ONLY.read_text())
    print(f"Classifying {len(actions)} v6-only actions")

    corpus_data = json.loads(CORPUS.read_text())
    recs = corpus_data.get("recommendations", [])
    corpus_text = "\n\n".join(
        f"[{r.get('recommendation_id', f'R{i+1}')}] {r.get('text','')}" for i, r in enumerate(recs)
    )
    print(f"Corpus length: {len(corpus_text)} chars, {len(recs)} recommendations")

    chunk_size = 12
    all_results: list[dict] = []
    for ci in range(0, len(actions), chunk_size):
        chunk = actions[ci:ci + chunk_size]
        print(f"  Chunk {ci // chunk_size + 1}: {len(chunk)} actions ...")
        out = call_llm(chunk, corpus_text)
        if not out:
            print(f"    EMPTY result — fallback unknown")
            for a in chunk:
                all_results.append({"action_id": a, "classification": "unknown", "rationale": "LLM parse fail"})
            continue
        if len(out) != len(chunk):
            print(f"    size mismatch: got {len(out)}, expected {len(chunk)} — pad")
            ids_seen = {r.get("action_id") for r in out}
            for a in chunk:
                if a not in ids_seen:
                    out.append({"action_id": a, "classification": "unknown", "rationale": "missing in LLM output"})
        all_results.extend(out)

    # Tally
    counts: dict[str, int] = {}
    for r in all_results:
        c = r.get("classification", "unknown")
        counts[c] = counts.get(c, 0) + 1
    total = len(all_results)
    print(f"\nClassification counts:")
    for k, v in counts.items():
        print(f"  {k}: {v} ({100*v/max(total,1):.1f}%)")

    # Save markdown
    lines: list[str] = []
    lines.append("# v6-only Actions Classification — kdigo_contrast_aki\n")
    lines.append("**Source CPG**: KDIGO 2012 Clinical Practice Guideline for Acute Kidney Injury (contrast-induced section)")
    lines.append("**Judge LLM**: Qwen3.5-397B-A17B-FP8 @ T=0.0")
    lines.append(f"**v6-only candidate set**: {len(actions)} actions (67 v6 vocab − v7 union, post-ActionNormalizer)\n")

    lines.append("## Aggregate Counts\n")
    lines.append("| Classification | n | % |")
    lines.append("|---|---|---|")
    for k in ("source-explicit", "source-implicit", "author-injection", "unknown"):
        v = counts.get(k, 0)
        lines.append(f"| {k} | {v} | {100*v/max(total,1):.1f}% |")
    lines.append(f"| **TOTAL** | {total} | 100.0% |")

    lines.append("\n## Per-Action Verdicts\n")
    lines.append("| Action ID | Classification | Rationale |")
    lines.append("|---|---|---|")
    for r in all_results:
        rid = r.get("action_id", "?")
        cls = r.get("classification", "unknown")
        rat = (r.get("rationale", "") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{rid}` | {cls} | {rat[:150]} |")

    lines.append("\n## Decision-Relevant Implication\n")
    inj_pct = 100 * counts.get("author-injection", 0) / max(total, 1)
    lines.append(f"- author-injection rate = **{inj_pct:.1f}%**")
    if inj_pct > 50:
        lines.append("  - >50% indicates v6 vocabulary largely author-injected → CGA-Bench v6 corpus has serious source-fidelity weakness.")
    elif inj_pct > 20:
        lines.append("  - 20-50% range suggests significant author-injection — disclose in paper App AY/AZ as a known limitation.")
    else:
        lines.append("  - ≤20% suggests v6 vocabulary is mostly source-grounded; v6-vs-v7 gap is mostly canonical_id naming, not authorial drift.")

    REPORT.write_text("\n".join(lines))
    Path(str(REPORT).replace(".md", ".json")).write_text(json.dumps(all_results, indent=2))
    print(f"\nReport: {REPORT}")
    print(f"JSON  : {str(REPORT).replace('.md','.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
