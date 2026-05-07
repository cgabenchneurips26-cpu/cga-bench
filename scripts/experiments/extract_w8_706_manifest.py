#!/usr/bin/env python3
"""Extract the canonical 706-scenario v6 manifest for the v8 frontier expansion.

The v6 typed verdict matrix at ``evidence_pack/analysis/verdict_matrix_v6_typed.json``
covers 19,062 episodes = 9 models × 706 scenarios × 3 runs. This script extracts
the deterministic 706-scenario list, attaches per-scenario CPG-domain and
violation-profile metadata, and saves it as a hash-frozen manifest used by:

  * Stage S1-S4 frontier runs (frontier_spot_check.py) — every frontier model
    visits exactly these 706 scenarios.
  * v8 corpus builder — the 706-set is later unioned with the v7 expansion
    236-set to produce the 942-scenario v8 corpus.

Run:
    PYTHONPATH=. python scripts/experiments/extract_w8_706_manifest.py \\
        --output evidence_pack/frontier/w8_706_manifest.json
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_VERDICT_MATRIX = "evidence_pack/analysis/verdict_matrix_v6_typed.json"
DEFAULT_OUTPUT = "evidence_pack/frontier/w8_706_manifest.json"


# Domain prefix map — derived from existing
# scripts/experiments/exp_d_disagreement_quantification.py:81-111. Pulled in
# here as a stand-alone copy so the manifest extraction has zero hidden
# dependencies on the analysis pipeline. Add new prefixes here if v8 adds
# new CPGs.
_DOMAIN_PREFIX_MAP: dict[str, str] = {
    "ssc_": "sepsis",
    "sepsis": "sepsis",
    "septic": "sepsis",
    "aha_chest": "chest_pain",
    "chest_pain": "chest_pain",
    "stemi": "chest_pain",
    "nstemi": "chest_pain",
    "aha_stroke": "stroke",
    "stroke": "stroke",
    "tpa": "stroke",
    "ada_dka": "dka",
    "dka_": "dka",
    "kdigo_aki": "aki",
    "aki_": "aki",
    "contrast_aki": "aki",
    "aha_heart": "heart_failure",
    "heart_failure": "heart_failure",
    "hf_": "heart_failure",
    "atrial_fib": "atrial_fibrillation",
    "af_": "atrial_fibrillation",
    "cap_": "pneumonia",
    "pneumonia": "pneumonia",
    "copd": "copd",
    "gi_bleeding": "gi_bleeding",
    "gi_": "gi_bleeding",
    "hypertensive": "hypertensive_emergency",
    "pulmonary_embolism": "pulmonary_embolism",
    "pe_": "pulmonary_embolism",
    "acls": "cardiac_arrest",
    "cardiac_arrest": "cardiac_arrest",
    "anaphylaxis": "anaphylaxis",
    "aabb": "transfusion",
    "asthma": "asthma",
    "gina_asthma": "asthma",
    "meningitis": "meningitis",
    "idsa_meningitis": "meningitis",
    "status_epi": "status_epilepticus",
    "aba_burn": "burn",
    "burn": "burn",
    "acog": "obstetric_hemorrhage",
    "apa_agit": "agitation",
    "pals": "pediatric_emergency",
    "tox_": "toxicology",
    "toxicology": "toxicology",
    "anticoagulant": "anticoagulation",
}


def _detect_domain(scenario_id: str) -> str:
    sid = scenario_id.lower()
    for prefix, domain in _DOMAIN_PREFIX_MAP.items():
        if sid.startswith(prefix):
            return domain
    # Fallback: use first underscore-delimited segment as domain.
    return sid.split("_", 1)[0]


def _primary_violation_type(episode_record: dict[str, Any]) -> str:
    """Pick the dominant violation type from a single episode's record."""
    viol_types = episode_record.get("viol_types", "")
    if not viol_types or viol_types in ("none", "[]"):
        return "none"
    if isinstance(viol_types, list):
        types = viol_types
    else:
        types = [t.strip() for t in str(viol_types).split(",") if t.strip()]
    if not types:
        return "none"
    # Priority: commission > timing > sequence > omission > deviation
    priority = ["commission", "timing", "sequence", "omission", "deviation"]
    for p in priority:
        for t in types:
            if p in t.lower():
                return p
    return types[0]


@dataclass
class ScenarioRecord:
    scenario_id: str
    cpg_domain: str
    violation_profile: list[str]   # union of primary types observed across models
    n_episodes: int                 # count in v6 (should be 27 = 9 models × 3 runs)
    fa_quartile: int                # 1 = easiest (most pass), 4 = hardest

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "cpg_domain": self.cpg_domain,
            "violation_profile": sorted(self.violation_profile),
            "n_episodes": self.n_episodes,
            "fa_quartile": self.fa_quartile,
        }


def extract(verdict_matrix_path: Path) -> list[ScenarioRecord]:
    with verdict_matrix_path.open("r", encoding="utf-8") as fh:
        matrix = json.load(fh)
    episodes = matrix.get("per_episode", [])
    if not episodes:
        raise ValueError(
            f"verdict matrix at {verdict_matrix_path} has no per_episode list"
        )

    by_scenario: dict[str, list[dict[str, Any]]] = {}
    for ep in episodes:
        sid = ep.get("scenario_id")
        if not sid:
            continue
        by_scenario.setdefault(sid, []).append(ep)

    if len(by_scenario) != 706:
        # Soft warning — proceed but flag in metadata.
        print(
            f"[warn] expected 706 unique scenarios in v6, got {len(by_scenario)}. "
            f"Continuing — manifest will reflect actual count."
        )

    # Fail-rate (v4_hard True == has violations) per scenario for FA quartile.
    fa_rates: dict[str, float] = {}
    for sid, eps in by_scenario.items():
        n_fail = sum(1 for e in eps if e.get("v4_hard"))
        fa_rates[sid] = n_fail / max(len(eps), 1)

    # Quartile boundaries.
    sorted_rates = sorted(fa_rates.values())
    n = len(sorted_rates)
    q_thresholds = [
        sorted_rates[n // 4],
        sorted_rates[n // 2],
        sorted_rates[(3 * n) // 4],
    ] if n >= 4 else [0.25, 0.5, 0.75]

    def fa_quartile(rate: float) -> int:
        if rate <= q_thresholds[0]:
            return 1
        if rate <= q_thresholds[1]:
            return 2
        if rate <= q_thresholds[2]:
            return 3
        return 4

    records: list[ScenarioRecord] = []
    for sid, eps in sorted(by_scenario.items()):
        viol_set = {_primary_violation_type(e) for e in eps if e.get("v4_hard")}
        if not viol_set:
            viol_set = {"none"}
        records.append(
            ScenarioRecord(
                scenario_id=sid,
                cpg_domain=_detect_domain(sid),
                violation_profile=list(viol_set),
                n_episodes=len(eps),
                fa_quartile=fa_quartile(fa_rates[sid]),
            )
        )
    return records


def _hash_records(records: list[ScenarioRecord]) -> str:
    """SHA-256 over the canonical (sorted scenario_id) list — manifest fingerprint."""
    canonical = json.dumps([r.scenario_id for r in records], sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _summary(records: list[ScenarioRecord]) -> dict[str, Any]:
    domains = Counter(r.cpg_domain for r in records)
    quartiles = Counter(r.fa_quartile for r in records)
    return {
        "n_scenarios": len(records),
        "n_domains": len(domains),
        "domain_counts": dict(sorted(domains.items(), key=lambda x: -x[1])),
        "fa_quartile_counts": dict(sorted(quartiles.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verdict-matrix", default=DEFAULT_VERDICT_MATRIX)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    src = Path(args.verdict_matrix)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    records = extract(src)
    summary = _summary(records)
    fingerprint = _hash_records(records)

    payload = {
        "metadata": {
            "source": str(src),
            "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
            "fingerprint_sha256": fingerprint,
            "n_scenarios": len(records),
            "summary": summary,
            "purpose": "Canonical 706-scenario v6 manifest for v8 frontier expansion.",
        },
        "scenarios": [r.to_dict() for r in records],
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    print(f"[ok] wrote {out}")
    print(f"  n_scenarios = {len(records)}")
    print(f"  n_domains   = {summary['n_domains']}")
    print(f"  fingerprint = {fingerprint[:16]}…")
    print(f"  domain_counts (top 10):")
    for k, v in list(summary["domain_counts"].items())[:10]:
        print(f"    {v:4d}  {k}")
    print(f"  fa_quartile_counts:")
    for k, v in summary["fa_quartile_counts"].items():
        print(f"    Q{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
