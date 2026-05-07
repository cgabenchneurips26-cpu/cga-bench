"""LLM-catalogue analogues of ASC / CwT / PAF for main-finding replication.

Paper §5 headline: on CDE-hard episodes the three-way consensus
ASC ∩ CwT ∩ PAF passes 6.6% (strictFAThree). To test whether this
consensus false-accept rate is catalogue-conditional, we build
LLM-catalogue analogues of each evaluator family using the same
constraint catalogue already loaded by LLMCatalogueShim
(evidence_pack/constraint_comparison/llm_raw/<CPG>.json).

Shim           Paper family        Rule
-------------  ------------------  ---------------------------------------
LlmAscShim     ASC (action-set)    coverage over LLM MUST ≥ 0.8
LlmCwtShim     CwT (CPG-with-      every MUST covered ∧ no FORBIDDEN hit
                   timing)         (timing axes WITHIN/BEFORE deferred —
                                    see Docstring note)
LlmPafShim     PAF (plausible      F1(performed, LLM-MUST) ≥ 0.5
                   action F1)

Notes
-----
1. Thresholds mirror the CDE wrappers (`ActionCoverageEvaluator`,
   `C2ScoreEvaluator`, `MABF1Evaluator`) so the per-family comparison
   is unit-consistent.
2. WITHIN / BEFORE axes are intentionally ignored — the LLM
   catalogue returns them as prose deadlines (e.g. "administer within
   60 minutes") that do not cleanly align with trajectory timestamps
   without another extraction pass. The same limitation exists for
   the paper's CwT when run against LLM catalogues; we document this
   in Directive and re-examine at camera-ready.
3. All three shims short-circuit to PASS when the scenario has no
   LLM catalogue (e.g. scenario prefix has no CPG mapping or
   extraction file is missing). This avoids pessimistic-fail
   inflation that was flagged in the Y.3 threshold sweep.
"""

from __future__ import annotations

from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims import llm_catalogue_shim as lcs
from audit.shims._trajectory_cache import load_trajectory


def _performed_set(traj: dict) -> set[str]:
    return {
        a.get("action_id")
        for a in (traj.get("actions") or [])
        if a.get("action_id")
    }


def _catalogue_for(traj: dict) -> dict[str, list[str]] | None:
    cpg = lcs._resolve_cpg_name(traj.get("scenario_id", ""))
    if cpg is None:
        return None
    cat = lcs._load_catalogue(cpg)
    if not cat["MUST"] and not cat["FORBIDDEN"]:
        return None
    return cat


class LlmAscShim(Evaluator):
    """Action-set coverage ≥ 0.8 on LLM MUST list."""

    meta = EvaluatorMeta(
        name="LlmAsc",
        family="llm_catalogue_asc",
        source="llm_raw/*.json MUST",
    )

    THRESHOLD = 0.8

    def verdict(self, ep: dict[str, Any]) -> bool:
        traj = load_trajectory(ep["episode_id"])
        if traj is None:
            return False
        cat = _catalogue_for(traj)
        if cat is None:
            return True
        if not cat["MUST"]:
            return True
        performed = _performed_set(traj)
        hits = sum(1 for m in cat["MUST"] if lcs._fuzzy_hit(m, performed))
        return hits / len(cat["MUST"]) >= self.THRESHOLD

    def observed_features(self) -> frozenset[str]:
        return frozenset({"actions[*].action_id", "scenario_id"})


class LlmCwtShim(Evaluator):
    """Every MUST covered AND no FORBIDDEN performed (LLM catalogue)."""

    meta = EvaluatorMeta(
        name="LlmCwt",
        family="llm_catalogue_cwt",
        source="llm_raw/*.json MUST+FORBIDDEN",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        traj = load_trajectory(ep["episode_id"])
        if traj is None:
            return False
        cat = _catalogue_for(traj)
        if cat is None:
            return True
        performed = _performed_set(traj)
        for f in cat["FORBIDDEN"]:
            if lcs._fuzzy_hit(f, performed):
                return False
        for m in cat["MUST"]:
            if not lcs._fuzzy_hit(m, performed):
                return False
        return True

    def observed_features(self) -> frozenset[str]:
        return frozenset({"actions[*].action_id", "scenario_id"})


class LlmPafShim(Evaluator):
    """F1(performed, LLM MUST) ≥ 0.5 (PAF analogue)."""

    meta = EvaluatorMeta(
        name="LlmPaf",
        family="llm_catalogue_paf",
        source="llm_raw/*.json MUST",
    )

    THRESHOLD = 0.5

    def _f1(self, performed: set[str], musts: list[str]) -> float:
        if not musts:
            return 1.0
        # precision: fraction of performed that hit a MUST (treat
        # fuzzy-hitting any MUST as a true positive)
        tp_performed = sum(
            1
            for p in performed
            if any(lcs._fuzzy_hit(m, {p}) for m in musts)
        )
        # recall: fraction of MUSTs that are covered
        tp_musts = sum(1 for m in musts if lcs._fuzzy_hit(m, performed))
        p = tp_performed / len(performed) if performed else 0.0
        r = tp_musts / len(musts)
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)

    def verdict(self, ep: dict[str, Any]) -> bool:
        traj = load_trajectory(ep["episode_id"])
        if traj is None:
            return False
        cat = _catalogue_for(traj)
        if cat is None:
            return True
        performed = _performed_set(traj)
        return self._f1(performed, cat["MUST"]) >= self.THRESHOLD

    def observed_features(self) -> frozenset[str]:
        return frozenset({"actions[*].action_id", "scenario_id"})
