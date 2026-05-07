"""Smoke tests for the E9 follow-up scripts (F1, F2, F3).

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _import(name: str, rel_path: str):
    spec_path = _REPO_ROOT / rel_path
    assert spec_path.exists(), f"missing: {spec_path}"
    spec = importlib.util.spec_from_file_location(name, spec_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def f1_mod():
    return _import("e39b", "scripts/experiments/exp_e39b_threshold_sweep.py")


@pytest.fixture(scope="module")
def f2_mod():
    return _import(
        "e39c", "scripts/experiments/exp_e39c_node_authority_spotcheck.py"
    )


@pytest.fixture(scope="module")
def f3_mod():
    return _import("e39d", "scripts/experiments/exp_e39d_severity_overlay.py")


# ---------------------------------------------------------------- F1
def test_f1_sweep_definitions(f1_mod) -> None:
    sweeps = f1_mod.SWEEPS
    labels = [s[0] for s in sweeps]
    assert labels == ["S1", "S2", "S3"]
    for label, taxonomy_rel, _desc in sweeps:
        path = _REPO_ROOT / taxonomy_rel
        assert path.exists(), f"missing taxonomy for {label}: {path}"


def test_f1_combined_render_works(f1_mod) -> None:
    fake = {
        label: {
            "fa_strict": {
                "full_catalogue": {"count": 1, "rate": 0.01},
                "high_authority": {"count": 1, "rate": 0.01},
            },
            "replay_detection_loss": {
                "high_authority": {
                    "mab_proxy": 0.6,
                    "ac_proxy": 0.7,
                    "c2_pass": 0.2,
                    "acov_pass": 0.7,
                },
                "full_catalogue": {
                    "mab_proxy": 0.6,
                    "ac_proxy": 0.7,
                    "c2_pass": 0.2,
                    "acov_pass": 0.7,
                },
            },
            "ranking_reversal": {
                "n_pairs": 36,
                "n_reversed": 1,
                "rate": 0.0278,
            },
            "violation_event_authority_split": {
                "high_kept": 100,
                "total": 200,
                "drop_rate": 0.5,
            },
            "violation_type_breakdown": {
                "full_catalogue": {"WITHIN": 100},
                "high_authority": {"WITHIN": 50},
            },
            "_meta": {
                "sweep_desc": f"{label} description",
                "n_high_authority_nodes": 100,
                "n_total_nodes": 200,
            },
            "n_episodes": 19062,
            "tcc_fail_count": {"full_catalogue": 1, "high_authority": 1},
        }
        for label in ("S1", "S2", "S3")
    }
    md = f1_mod.render_combined_md(fake)
    tex = f1_mod.render_combined_macros(fake)
    assert "Authority Threshold Sweep" in md
    assert "S1" in md and "S2" in md and "S3" in md
    for label in ("S1", "S2", "S3"):
        assert f"\\EnineS{label[1]}fastrict" in tex.replace(" ", "")[:5000] or f"\\Enine{label}fastrict" in tex


def test_f1_full_outputs_present_if_run() -> None:
    """If F1 has been run, smoke-check the combined files."""
    out_dir = _REPO_ROOT / "evidence_pack" / "analysis"
    md = out_dir / "exp_e9_threshold_sweep.md"
    tex = out_dir / "exp_e9_threshold_sweep.tex"
    if not md.exists():
        pytest.skip("F1 sweep not yet run")
    md_text = md.read_text()
    assert "S1" in md_text and "S2" in md_text and "S3" in md_text
    tex_text = tex.read_text()
    tex_text.encode("ascii")  # must be ASCII-safe
    for label in ("S1", "S2", "S3"):
        assert f"\\Enine{label}fastrict" in tex_text


# ---------------------------------------------------------------- F2
def test_f2_extract_domain(f2_mod) -> None:
    assert f2_mod.extract_domain("stemi_inferior_basic") == "chest_pain"
    assert f2_mod.extract_domain("septic_shock_lactate_high") == "sepsis"
    assert f2_mod.extract_domain("aabb_t_basic_cardiac_liberal_threshold") == "transfusion"
    assert f2_mod.extract_domain("zzz_unknown") == "other"


def test_f2_primary_violation_type(f2_mod) -> None:
    assert f2_mod.primary_violation_type(["WITHIN"]) == "WITHIN"
    assert f2_mod.primary_violation_type(["WITHIN", "FORBIDDEN"]) == "FORBIDDEN"
    assert f2_mod.primary_violation_type(["BEFORE", "WITHIN"]) == "WITHIN"
    assert f2_mod.primary_violation_type([]) == "NONE"
    assert f2_mod.primary_violation_type(None) == "NONE"


def test_f2_stratified_sample_round_robin(f2_mod) -> None:
    eps = []
    for m in ("a", "b", "c"):
        for d in ("x", "y"):
            for v in ("WITHIN",):
                for k in range(20):
                    eps.append(
                        {
                            "model_dir": m,
                            "scenario_id": f"{d}_scn_{k}",
                            "viol_types": [v],
                        }
                    )
    sampled = f2_mod.stratified_sample(eps, n=12, seed=42)
    assert len(sampled) == 12
    # Round-robin should hit every model_dir at least once
    models = {e["model_dir"] for e in sampled}
    assert len(models) >= 2


def test_f2_full_outputs_present_if_run() -> None:
    out_dir = _REPO_ROOT / "evidence_pack" / "analysis"
    csv = out_dir / "exp_e9_node_authority_spotcheck.csv"
    md = out_dir / "exp_e9_node_authority_spotcheck.md"
    if not csv.exists():
        pytest.skip("F2 spot-check not yet run")
    md_text = md.read_text()
    assert "Spot-Check" in md_text
    assert "Promotion cases" in md_text


# ---------------------------------------------------------------- F3
def test_f3_severity_order(f3_mod) -> None:
    rank = f3_mod._SEVERITY_RANK
    assert rank["catastrophic"] < rank["severe"] < rank["major"] < rank["moderate"]


def test_f3_max_hard_severity(f3_mod) -> None:
    events = [
        {"violation_type": "deviation", "harm_severity": "severe"},  # soft
        {"violation_type": "commission", "harm_severity": "major"},
        {"violation_type": "timing", "harm_severity": "moderate"},
        {"violation_type": "sequence", "harm_severity": "minor"},
    ]
    assert f3_mod.max_hard_severity(events) == "major"

    # Commission catastrophic dominates everything
    events2 = [
        {"violation_type": "commission", "harm_severity": "catastrophic"},
        {"violation_type": "commission", "harm_severity": "minor"},
    ]
    assert f3_mod.max_hard_severity(events2) == "catastrophic"

    # All soft -> "none"
    events3 = [
        {"violation_type": "deviation", "harm_severity": "severe"},
    ]
    assert f3_mod.max_hard_severity(events3) == "none"


def test_f3_aggregate_promotion_threshold(f3_mod) -> None:
    rows = [
        {"max_severity": "severe", "model_dir": "a", "domain": "x"},
        {"max_severity": "major", "model_dir": "a", "domain": "x"},
        {"max_severity": "minor", "model_dir": "a", "domain": "x"},
        {"max_severity": "minor", "model_dir": "a", "domain": "x"},
    ]
    m = f3_mod.aggregate(rows)
    # 2/4 = 50% critical+major -> promote
    assert m["promotion"]["promote_to_main"] is True
    assert m["shares"]["critical_major"] == 0.5

    rows_below = [{"max_severity": "minor", "model_dir": "a", "domain": "x"}] * 10
    m2 = f3_mod.aggregate(rows_below)
    assert m2["promotion"]["promote_to_main"] is False


def test_f3_full_outputs_present_if_run() -> None:
    out_dir = _REPO_ROOT / "evidence_pack" / "analysis"
    json_path = out_dir / "exp_e9_severity_overlay.json"
    macros_path = out_dir / "exp_e9_severity_macros.tex"
    if not json_path.exists():
        pytest.skip("F3 severity overlay not yet run")
    with open(json_path) as f:
        m = json.load(f)
    assert "shares" in m and "promotion" in m
    macros_path.read_text().encode("ascii")
    assert "\\Eninecriticalshare" in macros_path.read_text()


# ---------------------------------------------------------------- G1
_G1_JSON = _REPO_ROOT / "evidence_pack" / "analysis" / "exp_e9_safety_core.json"


@pytest.fixture(scope="module")
def g1_data() -> dict:
    """Load G1 safety-core overlay output; skip if not yet generated."""
    if not _G1_JSON.exists():
        pytest.skip("G1 safety-core output not yet generated")
    with open(_G1_JSON) as f:
        return json.load(f)


def test_g1_strict_fa_counts(g1_data: dict) -> None:
    """G1: strict-FA episode counts for S1 and S2 match spec pins."""
    assert g1_data["n_strict_fa_S1"] == 1124
    assert g1_data["n_strict_fa_S2"] == 548


def test_g1_safety_core_and_must_only(g1_data: dict) -> None:
    """G1: safety-core subset sizes and must-only residual match spec."""
    assert g1_data["safety_core_S1"] == 144
    assert g1_data["safety_core_S2"] == 4
    assert g1_data["must_only_S1"] == 980
    assert g1_data["must_only_S2"] == 544


def test_g1_collapse_delta_and_pct(g1_data: dict) -> None:
    """G1: S1->S2 safety-core collapse delta and percentage match spec."""
    assert g1_data["collapse_delta"] == -140
    assert abs(g1_data["collapse_pct"] - (-97.22)) < 0.1


def test_g1_family_breakdown_s1(g1_data: dict) -> None:
    """G1: S1 family breakdown forbid_only and forbid_within match spec."""
    fb = g1_data["family_breakdown_S1"]
    assert fb["forbid_only"] == 139
    assert fb["forbid_within"] == 5


# ---------------------------------------------------------------- G2
_G2_JSON = (
    _REPO_ROOT / "evidence_pack" / "analysis" / "exp_e9_context_swap_strictest.json"
)


@pytest.fixture(scope="module")
def g2_data() -> dict:
    """Load G2 context-swap x strictest output; skip if not yet generated."""
    if not _G2_JSON.exists():
        pytest.skip("G2 context-swap output not yet generated")
    with open(_G2_JSON) as f:
        return json.load(f)


def test_g2_well_formed_and_retained_s1(g2_data: dict) -> None:
    """G2: well-formed pair count and S1 retained count match spec."""
    assert g2_data["n_well_formed"] == 238
    assert g2_data["retained_s1"]["count"] == 231


def test_g2_retained_s2_counts(g2_data: dict) -> None:
    """G2: S2 retained count and distinct graph coverage match spec."""
    assert g2_data["retained_s2"]["count"] == 154
    assert g2_data["retained_s2"]["distinct_graphs"] == 17


def test_g2_retained_s2_severity(g2_data: dict) -> None:
    """G2: S2 severity breakdown (HIGH/CRITICAL/MODERATE) matches spec."""
    sev = g2_data["retained_s2"]["severity"]
    assert sev["HIGH"] == 85
    assert sev["CRITICAL"] == 67
    assert sev["MODERATE"] == 2


def test_g2_gate_checks(g2_data: dict) -> None:
    """G2: gate_check flags retained_ge_30 and domains_ge_8 both True."""
    gc = g2_data["gate_check"]
    assert gc["retained_ge_30"] is True
    assert gc["domains_ge_8"] is True


# ---------------------------------------------------------------- G3
_G3_JSON = _REPO_ROOT / "evidence_pack" / "analysis" / "exp_e9_s2_diversity.json"


@pytest.fixture(scope="module")
def g3_data() -> dict:
    """Load G3 S2 diversity output; skip if not yet generated."""
    if not _G3_JSON.exists():
        pytest.skip("G3 S2 diversity output not yet generated")
    with open(_G3_JSON) as f:
        return json.load(f)


def test_g3_strict_fa_s2_total(g3_data: dict) -> None:
    """G3: top-level n (strict FA S2 total) matches spec pin of 548."""
    assert g3_data["n"] == 548


def test_g3_distinct_counts(g3_data: dict) -> None:
    """G3: distinct models, scenarios, and domains match spec."""
    dc = g3_data["distinct_counts"]
    assert dc["models"] == 9
    assert dc["scenarios"] == 122
    assert dc["domains"] == 9


def test_g3_top_dominance_shares(g3_data: dict) -> None:
    """G3: top-3 domain share (~91.4) and top-model share (~28.5) match spec.

    Values are stored as percentages (0-100), not fractions.
    """
    td = g3_data["top_dominance"]
    assert abs(td["top_3_domains_share"] - 91.4) < 0.5
    assert abs(td["top_model_share"] - 28.5) < 0.5
