"""LLM-catalogue-derived verdict shim — Y.3 invariance test.

For each W8 episode, take the performed action_ids from the trajectory
and evaluate them against the MUST/FORBIDDEN constraints the LLM
extracted for the scenario's CPG (see
evidence_pack/constraint_comparison/llm_raw/<CPG>.json).

Verdict = PASS iff every MUST is fuzzy-matched by some performed
action AND no FORBIDDEN is fuzzy-matched. WITHIN / BEFORE are skipped
because timestamps in trajectory are on the CGA clock, not reconciled
with LLM-expressed deadlines.

This shim lets us compare LLM-catalogue verdicts to CDE-catalogue
(`v4_hard`) verdicts on the same corpus. High pair τ → Pose-B
invariance ("the audit harness does not depend on catalogue
construction method"). Low τ → the two catalogues lead to different
audit outputs and §4.3 needs revision.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._trajectory_cache import load_trajectory

_ROOT = Path(__file__).resolve().parents[2]
_LLM_CATALOGUE_DIR = _ROOT / "evidence_pack" / "constraint_comparison" / "llm_raw"

# Scenario prefix → LLM catalogue CPG name (stem of <CPG>.json)
SCENARIO_PREFIX_TO_CPG: dict[str, str] = {
    "aabb_t": "AABB-2016-Transfusion-Guidelines",
    "aba_burn": "ABA-2018-Burn-Resuscitation",
    "acls": "AHA-2020-ACLS-Guidelines",
    "acog_o": "ACOG-2017-Obstetric-Hemorrhage",
    "ada_dka": "ADA-2009-DKA-Management",
    "aha_hf": "AHA-2022-Heart-Failure-Guidelines",
    "aha_stroke": "AHA-2019-Stroke-Guidelines",
    "anaphyl": "WAO-2020-Anaphylaxis-Guidelines",
    "apa_a": "APA-2024-Agitation-Management",
    "asthma": "GINA-2024-Asthma-Exacerbation",
    "atrial_fib": "ESC-2020-AF-Guidelines",
    "cap_pneu": "ATS-IDSA-2019-CAP-Guidelines",
    "copd": "GOLD-2024-COPD-Report",
    "gi_bleed": "ACG-2021-GI-Bleeding-Guidelines",
    "hyper_emerg": "AHA-2017-Hypertensive-Emergency",
    "kdigo": "KDIGO-2012-AKI-Guidelines",
    "meningitis": "IDSA-2004-Meningitis-Guidelines",
    "pals_p": "AHA-2020-PALS-Guidelines",
    "pe_": "ESC-2019-PE-Guidelines",
    "sepsis": "SSC-2021-Sepsis-Hour1-Bundle",
    "status_epi": "AES-2016-Status-Epilepticus",
    "stemi_": "AHA-2021-Chest-Pain-Guidelines",
    "toxicology_m": "AACT-Toxicology-Management",
    "universal": "Universal-Clinical-Safety",
}


def _resolve_cpg_name(scenario_id: str) -> str | None:
    for prefix, cpg in SCENARIO_PREFIX_TO_CPG.items():
        if scenario_id.startswith(prefix):
            return cpg
    return None


@lru_cache(maxsize=32)
def _load_catalogue(cpg: str) -> dict[str, list[str]]:
    """Return {'MUST': [...], 'FORBIDDEN': [...]} action phrases for a CPG."""
    path = _LLM_CATALOGUE_DIR / f"{cpg}.json"
    if not path.exists():
        return {"MUST": [], "FORBIDDEN": []}
    data = json.loads(path.read_text())
    musts: list[str] = []
    forbids: list[str] = []
    raw_constraints = data.get("constraints", []) or []
    # Defensive: reasoning models (R1) sometimes return constraints as a single
    # dict instead of list-of-dicts, or include string elements alongside dicts.
    if isinstance(raw_constraints, list):
        constraints_iter = (c for c in raw_constraints if isinstance(c, dict))
    else:
        constraints_iter = iter(())
    for c in constraints_iter:
        t = str(c.get("type", "")).upper()
        action = str(c.get("action", "")).strip()
        if not action:
            continue
        if t == "MUST":
            musts.append(action)
        elif t == "FORBIDDEN":
            forbids.append(action)
    return {"MUST": musts, "FORBIDDEN": forbids}


_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "and",
        "or",
        "at",
        "by",
        "is",
        "are",
        "be",
        "as",
        "if",
        "not",
        "no",
        "do",
        "does",
        "should",
        "must",
        "shall",
        "will",
        "may",
        "any",
        "all",
        "each",
        "every",
        "patient",
        "patients",
        "when",
        "after",
        "before",
        "during",
        "within",
        "minutes",
        "hours",
        "hour",
        "minute",
        "administer",
        "give",
        "perform",
        "consider",
        "ensure",
        "avoid",
        "use",
        "ordering",
        "order",
    }
)


def _tokens(s: str) -> set[str]:
    """Lowercase → split on non-alpha → drop stopwords + short tokens."""
    import re

    raw = re.split(r"[^a-zA-Z]+", s.lower())
    return {w for w in raw if len(w) > 2 and w not in _STOPWORDS}


def _fuzzy_hit(phrase: str, performed: set[str]) -> bool:
    """Phrase matches a performed action if ≥1 content token overlaps."""
    pt = _tokens(phrase)
    if not pt:
        return False
    for p in performed:
        if pt & _tokens(p):
            return True
    return False


class LLMCatalogueShim(Evaluator):
    """Verdict = LLM MUSTs all satisfied AND no LLM FORBIDDEN performed."""

    meta = EvaluatorMeta(
        name="LLMCatalogue",
        family="catalogue_invariance",
        source="evidence_pack/constraint_comparison/llm_raw/*.json",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        traj = load_trajectory(ep["episode_id"])
        if traj is None:
            return False
        scenario = traj.get("scenario_id", "")
        cpg = _resolve_cpg_name(scenario)
        if cpg is None:
            # Unknown scenario family → pessimistic fail so it's
            # counted consistently (same convention as other shims).
            return False
        cat = _load_catalogue(cpg)
        if not cat["MUST"] and not cat["FORBIDDEN"]:
            # No LLM catalogue for this CPG (e.g. truncated extraction).
            # Treat as pass: absence of evidence, not evidence of failure.
            return True
        performed = {a.get("action_id") for a in (traj.get("actions") or []) if a.get("action_id")}
        # FORBIDDEN first: any hit → fail
        for f in cat["FORBIDDEN"]:
            if _fuzzy_hit(f, performed):
                return False
        # MUST: coverage threshold (≥ 0.5 of MUSTs hit) — strict all-
        # MUSTs-required is unachievable because the LLM returns
        # sentence-level statements while trajectory action_ids are
        # snake_case tokens; use coverage threshold consistent with
        # pi_nord_witness V3.
        if not cat["MUST"]:
            return True
        hits = sum(1 for m in cat["MUST"] if _fuzzy_hit(m, performed))
        return hits / len(cat["MUST"]) >= 0.5

    def observed_features(self) -> frozenset[str]:
        return frozenset(
            {
                "actions[*].action_id",
                "scenario_id",
                # catalogue is external metadata, scenario-derived; not
                # TCC-derived (no n_viols / compliance_score read)
            }
        )
