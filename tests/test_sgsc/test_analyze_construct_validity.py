"""Tests for scripts/sgsc/analyze_construct_validity.py (P2-2).

Covers H1-H5 hypothesis computations, JSON contract shape, LaTeX macro
generation, edge cases (empty dirs, missing files), and the hypothesis
filter (--hypotheses flag).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sgsc" / "analyze_construct_validity.py"


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_module():
    spec = importlib.util.spec_from_file_location("analyze_construct_validity", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_registry(tmp_path: Path, guidelines: list[dict]) -> Path:
    data = {"version": "sgsc_pilot_v1", "guidelines": guidelines}
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(data))
    return p


def _guideline_entry(gid: str, domain: str = "sepsis") -> dict:
    return {
        "guideline_id": gid,
        "guideline_name": gid,
        "corpus_file": "x.json",
        "graph_file": "x.yaml",
        "category": "breadth",
        "conflict_pattern": None,
        "tier": None,
        "held_out": False,
        "domain": domain,
    }


def _make_atom(
    atom_id: str,
    canonical_id: str,
    constraint_type: str = "REQUIRED",
    deadline_minutes: int | None = None,
    exclusion: list[str] | None = None,
    required_prior: list[str] | None = None,
) -> dict:
    return {
        "atom_id": atom_id,
        "source": {"guideline_id": "test_guideline", "quote": "test"},
        "population": {
            "inclusion": ["adults"],
            "exclusion": exclusion or [],
        },
        "action": {"canonical_id": canonical_id, "action_type": "lab"},
        "constraint": {
            "type": constraint_type,
            "activation_event": "test",
            "deadline_minutes": deadline_minutes,
        },
        "sequence": {
            "before": [],
            "required_prior": required_prior or [],
        },
        "evidence": {"system": "TEST", "recommendation_class": "strong", "level": "high"},
        "scenario_hooks": {
            "boundary_variables": [],
            "counterfactual_pairs": [],
            "auto_transitions": [],
        },
    }


def _make_scenario(
    scenario_id: str,
    mutations: list[dict] | None = None,
) -> dict:
    scen: dict = {
        "scenario_id": scenario_id,
        "description": f"Test scenario {scenario_id}",
        "guideline_graph": "test",
        "patient": {"age": 55, "sex": "M"},
        "expected_actions": ["act_a"],
        "forbidden_actions": [],
        "optional_actions": [],
        "max_duration_minutes": 120,
        "passing_compliance_threshold": 0.7,
        "_sgsc_metadata": {
            "seed_id": scenario_id,
            "source_atoms": ["atom_a"],
            "coverage_targets": {},
        },
    }
    if mutations is not None:
        scen["mutations"] = mutations
        scen["_sgsc_metadata"]["mutations"] = mutations
    return scen


def _write_atoms(gdir: Path, atoms: list[dict]) -> None:
    (gdir / "atoms_smoke.json").write_text(json.dumps(atoms))


def _write_scenarios(gdir: Path, gid: str, scenarios: dict) -> None:
    (gdir / f"{gid}_scenarios.json").write_text(json.dumps(scenarios))


# ---------------------------------------------------------------------------
# H1 — Mutation Kill-Rate
# ---------------------------------------------------------------------------


class TestH1MutationKillRate:
    def test_h1_kill_rate_all_mutations_have_violations(self, mod, tmp_path: Path) -> None:
        """3 atoms each producing 1 mutation -> kill_rate = 1.0."""
        gid = "test_sepsis"
        gdir = tmp_path / gid
        gdir.mkdir()
        atoms = [
            _make_atom("a1", "give_abx", constraint_type="REQUIRED"),
            _make_atom("a2", "order_lactate", constraint_type="REQUIRED"),
            _make_atom("a3", "give_fluids", constraint_type="REQUIRED"),
        ]
        _write_atoms(gdir, atoms)

        result = mod.compute_h1_mutation_kill_rate([_guideline_entry(gid)], tmp_path)

        assert result["total_mutations"] == 3
        assert result["mutations_with_violation"] == 3
        assert result["kill_rate"] == pytest.approx(1.0)

    def test_h1_kill_rate_partial(self, mod, tmp_path: Path) -> None:
        """2 REQUIRED atoms + 1 FORBIDDEN atom (no mutations) -> kill_rate = 1.0 for 2/2."""
        gid = "test_partial"
        gdir = tmp_path / gid
        gdir.mkdir()
        # FORBIDDEN atoms are skipped by _infer_mutations_from_atom (no template generated)
        # Two REQUIRED → 2 omit mutations, both have violation → 2/2 = 1.0
        atoms = [
            _make_atom("a1", "act_a", constraint_type="REQUIRED"),
            _make_atom("a2", "act_b", constraint_type="REQUIRED"),
        ]
        _write_atoms(gdir, atoms)

        result = mod.compute_h1_mutation_kill_rate([_guideline_entry(gid)], tmp_path)

        assert result["total_mutations"] == 2
        assert result["mutations_with_violation"] == 2
        assert result["kill_rate"] == pytest.approx(1.0)

    def test_h1_breakdown_by_type(self, mod, tmp_path: Path) -> None:
        """Omit + delay + sequence_break -> by_type has OMISSION=1, TIMING=1, SEQUENCE=1."""
        gid = "test_breakdown"
        gdir = tmp_path / gid
        gdir.mkdir()
        atoms = [
            # REQUIRED -> omit (OMISSION)
            _make_atom("a1", "act_required", constraint_type="REQUIRED"),
            # WITHIN with deadline -> omit (OMISSION) + delay (TIMING)
            _make_atom("a2", "act_within", constraint_type="WITHIN", deadline_minutes=60),
            # BEFORE with required_prior -> sequence_break (SEQUENCE)
            _make_atom(
                "a3",
                "act_before",
                constraint_type="BEFORE",
                required_prior=["act_required"],
            ),
        ]
        _write_atoms(gdir, atoms)

        result = mod.compute_h1_mutation_kill_rate([_guideline_entry(gid)], tmp_path)

        # a1 → 1 omit; a2 → 1 omit + 1 delay; a3 → 1 sequence_break = 4 total
        assert result["total_mutations"] == 4
        assert result["by_type"]["OMISSION"] == 2  # a1 + a2
        assert result["by_type"]["TIMING"] == 1  # a2 delay
        assert result["by_type"]["SEQUENCE"] == 1  # a3
        assert result["kill_rate"] == pytest.approx(1.0)

    def test_h1_no_atoms_file_graceful(self, mod, tmp_path: Path) -> None:
        """Missing atoms file -> 0 mutations, kill_rate = 1.0 (vacuous)."""
        gid = "test_no_atoms"
        gdir = tmp_path / gid
        gdir.mkdir()
        # No atoms_smoke.json written

        result = mod.compute_h1_mutation_kill_rate([_guideline_entry(gid)], tmp_path)

        assert result["total_mutations"] == 0
        assert result["kill_rate"] == pytest.approx(1.0)
        assert result["guidelines_scanned"] == 0


# ---------------------------------------------------------------------------
# H2 — Null Control Rate
# ---------------------------------------------------------------------------


class TestH2NullControlRate:
    def test_h2_all_conformant(self, mod, tmp_path: Path) -> None:
        """5 base scenarios (no mutations) -> null_control_rate = 1.0."""
        gid = "test_h2_all"
        gdir = tmp_path / gid
        gdir.mkdir()
        scenarios = {f"scen_{i:03d}": _make_scenario(f"scen_{i:03d}") for i in range(5)}
        _write_scenarios(gdir, gid, scenarios)

        result = mod.compute_h2_null_control_rate([_guideline_entry(gid)], tmp_path)

        assert result["total_base_scenarios"] == 5
        assert result["conformant_base_scenarios"] == 5
        assert result["null_control_rate"] == pytest.approx(1.0)

    def test_h2_mixed_mutated_and_base(self, mod, tmp_path: Path) -> None:
        """3 base + 2 mutated scenarios -> base=3, null_control_rate=1.0."""
        gid = "test_h2_mixed"
        gdir = tmp_path / gid
        gdir.mkdir()
        scenarios: dict = {}
        # 3 base scenarios
        for i in range(3):
            sid = f"scen_{i:03d}_seed"
            scenarios[sid] = _make_scenario(sid)
        # 2 mutated scenarios (have mutations in metadata)
        for i in range(2):
            sid = f"scen_mut_{i:03d}_seed__omit_act_a"
            scenarios[sid] = _make_scenario(
                sid,
                mutations=[{"mutation_type": "omit", "target_action": "act_a"}],
            )
        _write_scenarios(gdir, gid, scenarios)

        result = mod.compute_h2_null_control_rate([_guideline_entry(gid)], tmp_path)

        assert result["total_base_scenarios"] == 3
        assert result["conformant_base_scenarios"] == 3
        assert result["null_control_rate"] == pytest.approx(1.0)

    def test_h2_empty_scenarios_file(self, mod, tmp_path: Path) -> None:
        """Empty scenarios dict -> 0 base, null_control_rate = 1.0 (vacuous)."""
        gid = "test_h2_empty"
        gdir = tmp_path / gid
        gdir.mkdir()
        _write_scenarios(gdir, gid, {})

        result = mod.compute_h2_null_control_rate([_guideline_entry(gid)], tmp_path)

        assert result["total_base_scenarios"] == 0
        assert result["null_control_rate"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# H3 — Counterfactual Sensitivity
# ---------------------------------------------------------------------------


class TestH3CounterfactualSensitivity:
    def test_h3_exclusion_families_flip(self, mod, tmp_path: Path) -> None:
        """Atom with exclusion -> 1 exclusion family with 2 verdicts -> flip=1."""
        gid = "test_h3_exclusion"
        gdir = tmp_path / gid
        gdir.mkdir()
        atoms = [
            _make_atom(
                "a1",
                "give_nitrates",
                constraint_type="REQUIRED",
                exclusion=["right_ventricular_infarct"],
            )
        ]
        _write_atoms(gdir, atoms)

        result = mod.compute_h3_counterfactual_sensitivity([_guideline_entry(gid)], tmp_path)

        assert result["total_families"] == 1
        assert result["families_with_flip"] == 1
        assert result["sensitivity"] == pytest.approx(1.0)
        assert result["by_type"]["exclusion"] == 1

    def test_h3_timing_families_flip(self, mod, tmp_path: Path) -> None:
        """Atom with WITHIN + deadline -> 1 timing family with 2 verdicts -> flip=1."""
        gid = "test_h3_timing"
        gdir = tmp_path / gid
        gdir.mkdir()
        atoms = [
            _make_atom(
                "a1",
                "administer_thrombolytics",
                constraint_type="WITHIN",
                deadline_minutes=60,
            )
        ]
        _write_atoms(gdir, atoms)

        result = mod.compute_h3_counterfactual_sensitivity([_guideline_entry(gid)], tmp_path)

        assert result["total_families"] >= 1
        assert result["families_with_flip"] >= 1
        assert result["by_type"]["timing"] >= 1

    def test_h3_no_families_vacuous(self, mod, tmp_path: Path) -> None:
        """0 families -> sensitivity = 1.0 (vacuous truth)."""
        gid = "test_h3_empty"
        gdir = tmp_path / gid
        gdir.mkdir()
        # REQUIRED atoms with no exclusion/deadline/sequence = no families
        atoms = [_make_atom("a1", "order_cbc", constraint_type="REQUIRED")]
        _write_atoms(gdir, atoms)

        result = mod.compute_h3_counterfactual_sensitivity([_guideline_entry(gid)], tmp_path)

        assert result["total_families"] == 0
        assert result["sensitivity"] == pytest.approx(1.0)

    def test_h3_sequence_families_flip(self, mod, tmp_path: Path) -> None:
        """Atom with BEFORE + required_prior -> sequence family with flip."""
        gid = "test_h3_sequence"
        gdir = tmp_path / gid
        gdir.mkdir()
        atoms = [
            _make_atom(
                "a1",
                "give_antibiotics",
                constraint_type="BEFORE",
                required_prior=["order_blood_culture"],
            )
        ]
        _write_atoms(gdir, atoms)

        result = mod.compute_h3_counterfactual_sensitivity([_guideline_entry(gid)], tmp_path)

        assert result["total_families"] == 1
        assert result["families_with_flip"] == 1
        assert result["by_type"]["sequence"] == 1


# ---------------------------------------------------------------------------
# H4 — Clinician Agreement (deferred)
# ---------------------------------------------------------------------------


class TestH4ClinicianAgreement:
    def test_h4_deferred_when_no_validation_packet_dir(self, mod, tmp_path: Path) -> None:
        """No validation_packet dir -> status = deferred."""
        sgsc_dir = tmp_path / "sgsc_out"
        sgsc_dir.mkdir()

        result = mod.compute_h4_clinician_agreement(sgsc_dir)

        assert result["status"] == "deferred"
        assert "reason" in result

    def test_h4_deferred_when_no_review_files(self, mod, tmp_path: Path) -> None:
        """validation_packet dir exists but is empty -> status = deferred."""
        sgsc_dir = tmp_path / "sgsc_out"
        sgsc_dir.mkdir()
        packet_dir = sgsc_dir / "validation_packet"
        packet_dir.mkdir()
        # No JSON files written

        result = mod.compute_h4_clinician_agreement(sgsc_dir)

        assert result["status"] == "deferred"


# ---------------------------------------------------------------------------
# H5 — MIMIC Calibration (deferred)
# ---------------------------------------------------------------------------


class TestH5MimicCalibration:
    def test_h5_deferred_when_no_mimic_file(self, mod, tmp_path: Path) -> None:
        """No mimic_calibration.json -> status = deferred."""
        # monkeypatch REPO_ROOT to point at tmp_path so it doesn't find the real file
        original_repo_root = mod.REPO_ROOT
        mod.REPO_ROOT = tmp_path
        try:
            result = mod.compute_h5_mimic_calibration()
        finally:
            mod.REPO_ROOT = original_repo_root

        assert result["status"] == "deferred"
        assert "P2-3" in result["reason"]


# ---------------------------------------------------------------------------
# JSON contract schema
# ---------------------------------------------------------------------------


class TestJsonContractSchema:
    def test_json_contract_schema(self, mod, tmp_path: Path) -> None:
        """Output report has all required top-level keys."""
        gid = "test_schema"
        sgsc_dir = tmp_path / "sgsc_out"
        sgsc_dir.mkdir()
        gdir = sgsc_dir / gid
        gdir.mkdir()
        _write_atoms(gdir, [_make_atom("a1", "act_a")])
        _write_scenarios(gdir, gid, {"s1": _make_scenario("s1")})

        registry = _make_registry(tmp_path, [_guideline_entry(gid)])
        out_dir = tmp_path / "out"

        report = mod.run_analysis(registry, out_dir, sgsc_dir)

        required_keys = {
            "check_name",
            "status",
            "commit",
            "input_hash",
            "output_hash",
            "metrics",
            "failures",
        }
        assert required_keys.issubset(report.keys())
        assert report["check_name"] == "construct_validity"
        assert report["status"] in ("pass", "warn", "fail")

        metrics = report["metrics"]
        assert "H1_mutation_kill_rate" in metrics
        assert "H2_null_control_rate" in metrics
        assert "H3_counterfactual_sensitivity" in metrics
        assert "H4_clinician_agreement" in metrics
        assert "H5_mimic_calibration" in metrics

    def test_output_hash_is_sha256(self, mod, tmp_path: Path) -> None:
        """output_hash is a 64-character hex SHA-256."""
        gid = "test_hash"
        sgsc_dir = tmp_path / "sgsc_out"
        sgsc_dir.mkdir()
        gdir = sgsc_dir / gid
        gdir.mkdir()
        _write_atoms(gdir, [_make_atom("a1", "act_a")])
        _write_scenarios(gdir, gid, {"s1": _make_scenario("s1")})

        registry = _make_registry(tmp_path, [_guideline_entry(gid)])
        out_dir = tmp_path / "out"

        report = mod.run_analysis(registry, out_dir, sgsc_dir)
        h = report["output_hash"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# LaTeX macros
# ---------------------------------------------------------------------------


class TestLatexMacros:
    def test_latex_macros_generated(self, mod, tmp_path: Path) -> None:
        """_build_macros produces all 7 required macro commands."""
        metrics = {
            "H1_mutation_kill_rate": {
                "total_mutations": 10,
                "mutations_with_violation": 9,
                "kill_rate": 0.9,
                "by_type": {"OMISSION": 5, "TIMING": 3, "COMMISSION": 0, "SEQUENCE": 1},
                "guidelines_scanned": 4,
            },
            "H2_null_control_rate": {
                "total_base_scenarios": 20,
                "conformant_base_scenarios": 20,
                "null_control_rate": 1.0,
                "per_guideline": [],
            },
            "H3_counterfactual_sensitivity": {
                "total_families": 6,
                "families_with_flip": 6,
                "sensitivity": 1.0,
                "by_type": {"exclusion": 2, "timing": 2, "sequence": 2},
            },
        }
        macros = mod._build_macros(metrics)
        macro_text = "\n".join(macros)

        assert "\\sgscMutationKillRate" in macro_text
        assert "\\sgscNullControlRate" in macro_text
        assert "\\sgscCounterfactualSensitivity" in macro_text
        assert "\\sgscTotalMutations" in macro_text
        assert "\\sgscTotalFamilies" in macro_text
        assert "\\sgscTotalBaseScenarios" in macro_text
        assert "\\sgscGuidelinesWithMutations" in macro_text
        assert "\\providecommand" in macro_text

    def test_latex_macros_written_to_file(self, mod, tmp_path: Path) -> None:
        """_append_macros writes the block to the tex file when not already present."""
        tex_path = tmp_path / "auto_numbers_sgsc.tex"
        macros = [
            "\\providecommand{\\sgscMutationKillRate}{90.0\\%}",
            "\\providecommand{\\sgscTotalMutations}{10}",
        ]
        mod._append_macros(tex_path, macros)

        content = tex_path.read_text(encoding="utf-8")
        assert "\\sgscMutationKillRate" in content
        assert "\\sgscTotalMutations" in content

    def test_latex_macros_idempotent(self, mod, tmp_path: Path) -> None:
        """_append_macros does not duplicate block when called twice."""
        tex_path = tmp_path / "auto_numbers_sgsc.tex"
        macros = ["\\providecommand{\\sgscMutationKillRate}{90.0\\%}"]
        mod._append_macros(tex_path, macros)
        mod._append_macros(tex_path, macros)

        content = tex_path.read_text(encoding="utf-8")
        count = content.count("\\sgscMutationKillRate")
        assert count == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_sgsc_output_graceful(self, mod, tmp_path: Path) -> None:
        """Empty sgsc_output dir -> warn status, 0 mutations."""
        gid = "test_empty"
        sgsc_dir = tmp_path / "sgsc_out"
        sgsc_dir.mkdir()
        # Guideline dir exists but is empty
        (sgsc_dir / gid).mkdir()

        registry = _make_registry(tmp_path, [_guideline_entry(gid)])
        out_dir = tmp_path / "out"

        report = mod.run_analysis(registry, out_dir, sgsc_dir)

        assert report["check_name"] == "construct_validity"
        assert report["status"] in ("pass", "warn", "fail")
        h1 = report["metrics"]["H1_mutation_kill_rate"]
        assert h1["total_mutations"] == 0

    def test_per_guideline_breakdown(self, mod, tmp_path: Path) -> None:
        """2 guidelines -> 2 entries in H2 per_guideline list."""
        sgsc_dir = tmp_path / "sgsc_out"
        sgsc_dir.mkdir()
        guidelines = []
        for gid in ["g_sepsis", "g_aki"]:
            gdir = sgsc_dir / gid
            gdir.mkdir()
            _write_atoms(gdir, [_make_atom("a1", "act_a")])
            scenarios = {f"{gid}_s1_seed": _make_scenario(f"{gid}_s1_seed")}
            _write_scenarios(gdir, gid, scenarios)
            guidelines.append(_guideline_entry(gid))

        result = mod.compute_h2_null_control_rate(guidelines, sgsc_dir)

        assert len(result["per_guideline"]) == 2
        ids = {e["id"] for e in result["per_guideline"]}
        assert ids == {"g_sepsis", "g_aki"}

    def test_hypothesis_filter(self, mod, tmp_path: Path) -> None:
        """--hypotheses H1,H2 -> only H1 and H2 keys in metrics."""
        gid = "test_filter"
        sgsc_dir = tmp_path / "sgsc_out"
        sgsc_dir.mkdir()
        gdir = sgsc_dir / gid
        gdir.mkdir()
        _write_atoms(gdir, [_make_atom("a1", "act_a")])
        _write_scenarios(gdir, gid, {"s1": _make_scenario("s1")})

        registry = _make_registry(tmp_path, [_guideline_entry(gid)])
        out_dir = tmp_path / "out"

        report = mod.run_analysis(registry, out_dir, sgsc_dir, hypotheses=["H1", "H2"])

        assert "H1_mutation_kill_rate" in report["metrics"]
        assert "H2_null_control_rate" in report["metrics"]
        assert "H3_counterfactual_sensitivity" not in report["metrics"]
        assert "H4_clinician_agreement" not in report["metrics"]
        assert "H5_mimic_calibration" not in report["metrics"]

    def test_status_pass_when_kill_rate_high(self, mod, tmp_path: Path) -> None:
        """kill_rate >= 0.9 with conformant base -> status = pass."""
        gid = "test_pass_status"
        sgsc_dir = tmp_path / "sgsc_out"
        sgsc_dir.mkdir()
        gdir = sgsc_dir / gid
        gdir.mkdir()
        # REQUIRED atoms -> omit mutations, all have OMISSION violation type
        atoms = [_make_atom(f"a{i}", f"act_{i}") for i in range(5)]
        _write_atoms(gdir, atoms)
        scenarios = {f"s{i}_seed": _make_scenario(f"s{i}_seed") for i in range(5)}
        _write_scenarios(gdir, gid, scenarios)

        registry = _make_registry(tmp_path, [_guideline_entry(gid)])
        out_dir = tmp_path / "out"

        report = mod.run_analysis(registry, out_dir, sgsc_dir)

        assert report["status"] == "pass"
        h1 = report["metrics"]["H1_mutation_kill_rate"]
        assert h1["kill_rate"] >= 0.9
