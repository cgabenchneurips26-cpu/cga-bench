"""Tests for scripts/experiments/v6_v7_transition_audit.py (TG-V4 generator).

Verifies that the four marginal attribution rows sum to the direct
v6 -> v7_final delta, and that the Markdown output reports both sums.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="module")
def audit_module() -> Any:
    """Load the script as a module and register it in sys.modules.

    Required for @dataclass forward-reference resolution.
    """
    import sys

    name = "v6_v7_transition_audit"
    repo_root = Path(__file__).resolve().parent.parent.parent
    script_path = repo_root / "scripts" / "experiments" / "v6_v7_transition_audit.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _arm(label: str, fa: float, comp: float, viol: float, conflict: int) -> dict[str, Any]:
    return {
        "label": label,
        "n_scenarios": 100,
        "headline_fa": fa,
        "mean_compliance": comp,
        "mean_violations_per_episode": viol,
        "n_conflict_events": conflict,
    }


def _write(tmp_path: Path, name: str, payload: dict[str, Any]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload))
    return p


class TestLoadArm:
    def test_missing_keys_raise(self, audit_module: Any, tmp_path: Path) -> None:
        bad = _write(tmp_path, "bad.json", {"n_scenarios": 100})
        with pytest.raises(ValueError, match="missing keys"):
            audit_module.load_arm(bad, "x")

    def test_loads_well_formed_arm(self, audit_module: Any, tmp_path: Path) -> None:
        path = _write(tmp_path, "ok.json", _arm("v6", 0.50, 0.60, 1.0, 5))
        snap = audit_module.load_arm(path, "v6")
        assert snap.label == "v6"
        assert snap.headline_fa == 0.50


class TestAttribute:
    def test_marginals_sum_to_direct_delta(
        self, audit_module: Any, tmp_path: Path
    ) -> None:
        v6 = audit_module.load_arm(
            _write(tmp_path, "v6.json", _arm("v6", 0.50, 0.60, 1.00, 0)),
            "v6",
        )
        v7_corpus_only = audit_module.load_arm(
            _write(tmp_path, "v7co.json", _arm("v7_co", 0.55, 0.62, 1.10, 0)),
            "v7_corpus_only",
        )
        v7_cds_flip = audit_module.load_arm(
            _write(tmp_path, "v7cds.json", _arm("v7_cds", 0.48, 0.55, 1.30, 0)),
            "v7_cds_flip",
        )
        v7_alternative = audit_module.load_arm(
            _write(tmp_path, "v7alt.json", _arm("v7_alt", 0.46, 0.54, 1.45, 0)),
            "v7_alternative",
        )
        v7_final = audit_module.load_arm(
            _write(tmp_path, "v7f.json", _arm("v7_final", 0.45, 0.53, 1.50, 12)),
            "v7_final",
        )

        rows = audit_module.attribute(
            v6, v7_corpus_only, v7_cds_flip, v7_alternative, v7_final
        )
        assert len(rows) == 4

        # Marginal sums == direct deltas (within float epsilon)
        sum_fa = sum(r.delta_headline_fa for r in rows)
        sum_comp = sum(r.delta_mean_compliance for r in rows)
        sum_viol = sum(r.delta_violations_per_episode for r in rows)
        sum_conflict = sum(r.delta_conflict_events for r in rows)

        assert abs(sum_fa - (v7_final.headline_fa - v6.headline_fa)) < 1e-9
        assert abs(sum_comp - (v7_final.mean_compliance - v6.mean_compliance)) < 1e-9
        assert abs(
            sum_viol
            - (v7_final.mean_violations_per_episode - v6.mean_violations_per_episode)
        ) < 1e-9
        assert sum_conflict == v7_final.n_conflict_events - v6.n_conflict_events

    def test_dimension_order_is_canonical(
        self, audit_module: Any, tmp_path: Path
    ) -> None:
        """Rows must always be in the documented order for paper inclusion."""
        snaps = []
        for label, fa in [("v6", 0.5), ("v7_co", 0.55), ("v7_cds", 0.48),
                          ("v7_alt", 0.46), ("v7_final", 0.45)]:
            path = _write(tmp_path, f"{label}.json", _arm(label, fa, 0.6, 1.0, 0))
            snaps.append(audit_module.load_arm(path, label))
        rows = audit_module.attribute(*snaps)
        dims = [r.dimension for r in rows]
        assert dims == [
            "corpus_change_25_to_14_cpgs",
            "cds_default_true_to_false",
            "alternative_coverage_reserved_to_active",
            "cde_coupling_added",
        ]


class TestRenderAuditMd:
    def test_md_contains_summary_lines(self, audit_module: Any, tmp_path: Path) -> None:
        snaps = []
        for label, fa, conf in [
            ("v6", 0.50, 0),
            ("v7_co", 0.55, 0),
            ("v7_cds", 0.48, 0),
            ("v7_alt", 0.46, 0),
            ("v7_final", 0.45, 12),
        ]:
            path = _write(tmp_path, f"{label}.json", _arm(label, fa, 0.6, 1.0, conf))
            snaps.append(audit_module.load_arm(path, label))
        rows = audit_module.attribute(*snaps)
        md = audit_module.render_audit_md(snaps[0], snaps[-1], rows)

        # Must mention the four dimension names in canonical order
        for token in (
            "corpus_change_25_to_14_cpgs",
            "cds_default_true_to_false",
            "alternative_coverage_reserved_to_active",
            "cde_coupling_added",
        ):
            assert token in md

        # Must include both the marginal sum and the direct delta rows
        assert "Sum (marginals)" in md
        assert "Direct delta" in md
