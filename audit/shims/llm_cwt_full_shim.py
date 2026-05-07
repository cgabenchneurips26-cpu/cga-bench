"""LlmCwt extended with WITHIN and BEFORE axes.

Previous LlmCwt (audit/shims/llm_family_shims.py::LlmCwtShim) only
checks MUST coverage and FORBIDDEN avoidance; the LLM catalogue's
WITHIN (deadline_minutes) and BEFORE (before_action) fields were
intentionally deferred because trajectory timestamps were not being
reconciled against LLM-phrase matching.

This shim folds WITHIN and BEFORE in. On the 14,826-episode W8
corpus, the LlmCwtFullShim verdict is:

    pass iff  (no FORBIDDEN phrase hit)  AND
              (every MUST phrase hit)    AND
              (for every WITHIN with a matching performed action,
               the first matching timestamp ≤ deadline_minutes)  AND
              (for every BEFORE(subj, bef) where both are performed,
               ts(subj) < ts(bef))

A missing action (subject not performed) is a vacuous pass for
WITHIN and BEFORE; MUST catches omissions separately. Catalogues
without WITHIN/BEFORE entries (truncated gpt-oss v2 extractions)
degrade gracefully — the corresponding checks pass trivially.
"""

from __future__ import annotations

from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims import llm_catalogue_shim as lcs
from audit.shims._trajectory_cache import load_trajectory
from audit.shims.llm_family_shims import _catalogue_for, _performed_set


def _load_full_catalogue(cpg: str) -> dict[str, list]:
    """Like _load_catalogue but also carries WITHIN / BEFORE entries."""
    from pathlib import Path
    import json

    path = lcs._LLM_CATALOGUE_DIR / f"{cpg}.json"
    out: dict[str, list] = {"MUST": [], "FORBIDDEN": [], "WITHIN": [], "BEFORE": []}
    if not path.exists():
        return out
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return out
    for c in data.get("constraints", []) or []:
        t = str(c.get("type", "")).upper()
        action = str(c.get("action", "")).strip()
        if not action:
            continue
        if t == "MUST":
            out["MUST"].append(action)
        elif t == "FORBIDDEN":
            out["FORBIDDEN"].append(action)
        elif t == "WITHIN":
            dl = c.get("deadline_minutes")
            if dl is not None:
                out["WITHIN"].append({"action": action, "deadline_minutes": float(dl)})
        elif t == "BEFORE":
            bef = (c.get("before_action") or "").strip()
            if bef:
                out["BEFORE"].append({"action": action, "before_action": bef})
    return out


def _first_match_ts(phrase: str, events: list[dict]) -> float | None:
    """Return first timestamp_minutes where event.action_id tokens overlap phrase tokens."""
    target = lcs._tokens(phrase)
    if not target:
        return None
    for ev in events:
        aid = ev.get("action_id") or ""
        if not aid:
            continue
        if target & lcs._tokens(aid):
            ts = ev.get("timestamp_minutes")
            if ts is not None:
                return float(ts)
    return None


class LlmCwtFullShim(Evaluator):
    """LlmCwt + WITHIN deadlines + BEFORE ordering."""

    meta = EvaluatorMeta(
        name="LlmCwtFull",
        family="llm_catalogue_cwt_full",
        source="llm_raw*/*.json MUST+FORBIDDEN+WITHIN+BEFORE",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        traj = load_trajectory(ep["episode_id"])
        if traj is None:
            return False
        cat_min = _catalogue_for(traj)
        if cat_min is None:
            # Scenario has no LLM catalogue → vacuous pass (same policy
            # as the rest of the family for principled invariance).
            return True
        # Reload full catalogue (adds WITHIN/BEFORE)
        import json
        from pathlib import Path

        cpg = lcs._resolve_cpg_name(traj.get("scenario_id", ""))
        if cpg is None:
            return True
        cat = _load_full_catalogue(cpg)

        performed = _performed_set(traj)
        events = traj.get("actions") or []

        # 1. FORBIDDEN
        for f in cat["FORBIDDEN"]:
            if lcs._fuzzy_hit(f, performed):
                return False
        # 2. MUST all
        for m in cat["MUST"]:
            if not lcs._fuzzy_hit(m, performed):
                return False
        # 3. WITHIN deadlines
        for w in cat["WITHIN"]:
            ts = _first_match_ts(w["action"], events)
            if ts is not None and ts > w["deadline_minutes"]:
                return False
        # 4. BEFORE ordering
        for b in cat["BEFORE"]:
            ts_subj = _first_match_ts(b["action"], events)
            ts_bef = _first_match_ts(b["before_action"], events)
            if ts_subj is not None and ts_bef is not None and ts_subj >= ts_bef:
                return False
        return True

    def observed_features(self) -> frozenset[str]:
        return frozenset(
            {"actions[*].action_id", "actions[*].timestamp_minutes", "scenario_id"}
        )
