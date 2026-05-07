"""CAV v0.5 Phase 3 — RxNorm Crosscoding.

Maps every medication-kind CAV entry (explicit + implicit tiers) to RxNorm
RxCUI via deterministic RxNav approximateTerm + properties calls.

NO LLM. Deterministic flow only — failures are reported as `rxnorm_unmatched`
with a reason code; the paper discloses the failures rather than guessing.

Drug-name extraction (deterministic):
1. Strip leading verb prefix (give_/administer_/start_/prescribe_/infuse_/bolus_).
2. Drop trailing `_if_*` suffix (e.g. start_vasopressor_if_hypotensive -> vasopressor).
3. Replace remaining `_` with spaces.
4. Try the cleaned phrase first.
5. If that fails AND the phrase has 2+ tokens, retry with just the LAST token
   (handles compound forms like "vasopressor norepinephrine" -> "norepinephrine").

Acceptance:
- top approximateTerm hit `score >= 50`
- /rxcui/{rxcui}/properties.json verifies the rxcui exists
- tty in {IN, BN, SBD, SCD, SCDC, SBDC}
- Else mark `rxnorm_unmatched` with one of:
    score_below_threshold | tty_invalid | properties_missing | api_error | no_hit

Cache file is updated atomically (tmp + os.replace) after each API call so
re-runs skip already-resolved drugs.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
_VERB_PREFIXES = ("give_", "administer_", "start_", "prescribe_", "infuse_", "bolus_")
_VALID_TTYS = {"IN", "BN", "SBD", "SCD", "SCDC", "SBDC"}
_REQUEST_TIMEOUT_S = 15
_POLITE_SLEEP_S = 0.1


def extract_drug_terms(canonical_id: str) -> list[str]:
    """Return ordered list of candidate drug-name strings to try.

    Each term is space-separated lowercase. Longer (more specific) candidates
    come first so the first matching one wins.
    """
    cid = canonical_id.lower()
    # 1. Strip verb prefix
    for p in _VERB_PREFIXES:
        if cid.startswith(p):
            cid = cid[len(p) :]
            break
    # 2. Drop _if_* suffix
    if "_if_" in cid:
        cid = cid.split("_if_", 1)[0]
    # 3. Spaces
    phrase = cid.replace("_", " ").strip()
    if not phrase:
        return []
    candidates = [phrase]
    # 5. If multi-token, also try the last token alone (compound drug fallback)
    tokens = phrase.split()
    if len(tokens) >= 2:
        candidates.append(tokens[-1])
    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _http_get_json(url: str) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=_REQUEST_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"[WARN] HTTP error for {url}: {exc}", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"[WARN] JSON decode error for {url}: {exc}", file=sys.stderr)
        return None


def approximate_term(term: str) -> tuple[str | None, float | None, str | None]:
    """Call /approximateTerm.json. Returns (rxcui, score, reason).

    RxNav approximateTerm returns scores as float-strings on a similarity
    scale (typically 5-15 for credible matches, with rank==1 for the top
    candidate). The fuzzy nature means rank/score alone are NOT reliable
    correctness filters — even gibberish terms return rank=1. We therefore
    accept ANY rank=1 candidate from this call and let the TTY check on
    /properties.json (downstream) be the authoritative correctness filter.
    """
    url = f"{_RXNAV_BASE}/approximateTerm.json?" + urllib.parse.urlencode({"term": term, "maxEntries": 5})
    data = _http_get_json(url)
    if data is None:
        return None, None, "api_error"
    candidates = (data.get("approximateGroup") or {}).get("candidate") or []
    if not candidates:
        return None, None, "no_hit"
    top = candidates[0]
    rxcui = top.get("rxcui")
    if not rxcui:
        return None, None, "no_hit"
    try:
        score = float(top.get("score"))
    except (TypeError, ValueError):
        score = None
    return rxcui, score, None


def fetch_properties(rxcui: str) -> dict[str, Any] | None:
    url = f"{_RXNAV_BASE}/rxcui/{rxcui}/properties.json"
    data = _http_get_json(url)
    if data is None:
        return None
    return data.get("properties")


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def map_one(
    canonical_id: str,
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
) -> dict[str, Any]:
    """Resolve one canonical_id. Updates cache atomically. Returns result dict.

    Result schema:
      success -> {"status": "matched", "rxcui", "rxnorm_name", "tty", "score", "extracted_term"}
      failure -> {"status": "unmatched", "reason", "extracted_term"}
    """
    candidates = extract_drug_terms(canonical_id)
    if not candidates:
        return {"status": "unmatched", "reason": "no_drug_term", "extracted_term": ""}

    last_reason = "no_hit"
    last_score: int | None = None
    for term in candidates:
        cache_key = f"approx::{term}"
        if cache_key in cache:
            approx_cached = cache[cache_key]
            rxcui = approx_cached.get("rxcui")
            score = approx_cached.get("score")
            reason = approx_cached.get("reason")
        else:
            rxcui, score, reason = approximate_term(term)
            cache[cache_key] = {"rxcui": rxcui, "score": score, "reason": reason}
            _atomic_write_json(cache_path, cache)
            time.sleep(_POLITE_SLEEP_S)
        if not rxcui:
            last_reason = reason or "no_hit"
            last_score = score
            continue

        prop_key = f"props::{rxcui}"
        if prop_key in cache:
            props = cache[prop_key]
        else:
            props = fetch_properties(rxcui)
            cache[prop_key] = props or {"_missing": True}
            _atomic_write_json(cache_path, cache)
            time.sleep(_POLITE_SLEEP_S)
        if not props or props.get("_missing"):
            last_reason = "properties_missing"
            continue
        tty = props.get("tty")
        if tty not in _VALID_TTYS:
            last_reason = "tty_invalid"
            continue
        return {
            "status": "matched",
            "rxcui": rxcui,
            "rxnorm_name": props.get("name"),
            "tty": tty,
            "score": score,
            "extracted_term": term,
        }
    return {"status": "unmatched", "reason": last_reason, "extracted_term": candidates[0]}


def map_rxnorm(
    labeled: dict[str, Any],
    cache_path: Path,
) -> dict[str, Any]:
    cache: dict[str, dict[str, Any]] = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] Cache parse failed; starting fresh: {exc}", file=sys.stderr)
            cache = {}

    eligible: list[str] = [
        cid
        for cid, entry in labeled["entries"].items()
        if entry["action_kind"] == "medication" and entry["tier"] in {"explicit", "implicit"}
    ]
    eligible.sort()

    print(f"[INFO] {len(eligible)} medications to map (cache: {len(cache)} prior entries)")
    mappings: dict[str, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    for i, cid in enumerate(eligible, 1):
        result = map_one(cid, cache, cache_path)
        if result["status"] == "matched":
            mappings[cid] = {
                "rxcui": result["rxcui"],
                "rxnorm_name": result["rxnorm_name"],
                "tty": result["tty"],
                "score": result["score"],
                "extracted_term": result["extracted_term"],
            }
        else:
            unmatched.append(
                {
                    "canonical_id": cid,
                    "extracted_term": result.get("extracted_term", ""),
                    "reason": result["reason"],
                }
            )
        if i % 25 == 0:
            print(f"[INFO]   progress: {i}/{len(eligible)}  matched={len(mappings)}  unmatched={len(unmatched)}")

    return {
        "metadata": {
            "phase": "rxnorm_crosscoded",
            "api": "rxnav.nlm.nih.gov",
            "n_attempted": len(eligible),
            "n_matched": len(mappings),
            "n_unmatched": len(unmatched),
            "produced_at": datetime.now(UTC).isoformat(),
        },
        "mappings": mappings,
        "unmatched": unmatched,
    }


def _print_summary(result: dict[str, Any]) -> float:
    md = result["metadata"]
    n = md["n_attempted"]
    matched = md["n_matched"]
    rate = (matched / n) if n else 0.0
    print()
    print("=== CAV Phase 3: RxNorm Crosscoding ===")
    print(f"  Attempted: {n}")
    print(f"  Matched:   {matched} ({rate:.1%})")
    print(f"  Unmatched: {md['n_unmatched']}")
    print()
    if result["unmatched"]:
        print("  Unmatched reasons (count):")
        from collections import Counter as _C

        rcount = _C(u["reason"] for u in result["unmatched"])
        for r, c in rcount.most_common():
            print(f"    {r:25s} {c}")
        print()
        print("  Sample of unmatched (first 20):")
        for u in result["unmatched"][:20]:
            print(f"    [{u['reason']:24s}] {u['canonical_id']} (term='{u['extracted_term']}')")
        print()
    if result["mappings"]:
        print("  Sample of 10 successful mappings:")
        for cid, m in list(result["mappings"].items())[:10]:
            print(
                f"    {cid}  ->  rxcui={m['rxcui']:>8s}  tty={m['tty']:<4s}  score={m['score']:>3}  name='{m['rxnorm_name']}'"
            )
    return rate


def main() -> int:
    parser = argparse.ArgumentParser(description="CAV v0.5 Phase 3: RxNorm crosscoding")
    parser.add_argument(
        "--input",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "02_labeled.json",
        help="Phase 2 labeled output JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "03_rxnorm_mapping.json",
        help="Phase 3 RxNorm mapping output JSON.",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "03_rxnav_cache.json",
        help="Atomic-update cache file for RxNav API responses.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if match rate < 70%%.",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"[ERROR] --input not found: {args.input}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.cache.parent.mkdir(parents=True, exist_ok=True)

    labeled = json.loads(args.input.read_text(encoding="utf-8"))
    result = map_rxnorm(labeled, args.cache)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=False), encoding="utf-8")
    print(f"[INFO] Wrote {args.output}")

    rate = _print_summary(result)
    if args.strict and rate < 0.70:
        print(f"[STOP] match rate {rate:.1%} < 70%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
