"""Tests for sgsc.compilers.graph_compiler."""

from __future__ import annotations

from sgsc.compilers.graph_compiler import (
    GraphCompiler,
    GraphCompilerConfig,
)
from sgsc.schemas.atom import (
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    AtomSequence,
    PopulationCriteria,
    RecommendationAtom,
    ScenarioHooks,
    SourceReference,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_atom(
    section: str = "Hour-1 Bundle",
    action_id: str = "give_abx",
    constraint_type: str = "REQUIRED",
    deadline: int | None = None,
    required_prior: list[str] | None = None,
    before: list[str] | None = None,
    atom_id: str | None = None,
) -> RecommendationAtom:
    return RecommendationAtom(
        atom_id=atom_id or f"atom_{action_id}",
        source=SourceReference(
            guideline_id="ssc_2021",
            section=section,
            page="10",
            quote=f"Do {action_id}.",
        ),
        population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
        action=AtomAction(canonical_id=action_id, action_type="medication"),
        constraint=AtomConstraint(
            type=constraint_type,
            deadline_minutes=deadline,
        ),
        sequence=AtomSequence(
            required_prior=required_prior or [],
            before=before or [],
        ),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="A"),
        scenario_hooks=ScenarioHooks(),
    )


# ------------------------------------------------------------------
# Basic compilation
# ------------------------------------------------------------------


class TestGraphCompilerBasic:
    def test_empty_atoms(self) -> None:
        compiler = GraphCompiler()
        graph = compiler.compile([], "test_id", "Test Guideline")
        assert graph["graph_id"] == "test_id"
        assert graph["nodes"] == {}
        assert graph["entry_node"] == ""

    def test_single_atom(self) -> None:
        atoms = [_make_atom()]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        assert graph["graph_id"] == "ssc"
        assert graph["guideline_name"] == "SSC 2021"
        assert len(graph["nodes"]) == 1
        assert graph["entry_node"] != ""

    def test_node_has_required_fields(self) -> None:
        atoms = [_make_atom()]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        node = list(graph["nodes"].values())[0]
        required_keys = {
            "node_id",
            "node_type",
            "name",
            "description",
            "mandatory_actions",
            "allowed_actions",
            "forbidden_actions",
            "deadlines",
            "next_nodes",
        }
        assert required_keys.issubset(set(node.keys()))

    def test_version_present(self) -> None:
        atoms = [_make_atom()]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        assert graph["version"] == "sgsc-0.1.0"

    def test_generation_pipeline_metadata(self) -> None:
        atoms = [_make_atom(), _make_atom(action_id="order_lactate", atom_id="atom_lactate")]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        meta = graph["_generation_pipeline"]
        assert meta["method"] == "sgsc"
        assert meta["atom_count"] == 2


# ------------------------------------------------------------------
# Node grouping
# ------------------------------------------------------------------


class TestNodeGrouping:
    def test_same_section_grouped(self) -> None:
        atoms = [
            _make_atom(section="Assessment", action_id="a1", atom_id="atom_a1"),
            _make_atom(section="Assessment", action_id="a2", atom_id="atom_a2"),
        ]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        assert len(graph["nodes"]) == 1

    def test_different_sections_separate(self) -> None:
        atoms = [
            _make_atom(section="Assessment", action_id="a1", atom_id="atom_a1"),
            _make_atom(section="Treatment", action_id="a2", atom_id="atom_a2"),
        ]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        assert len(graph["nodes"]) == 2


# ------------------------------------------------------------------
# Action classification
# ------------------------------------------------------------------


class TestActionClassification:
    def test_required_in_mandatory(self) -> None:
        atoms = [_make_atom(constraint_type="REQUIRED")]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        node = list(graph["nodes"].values())[0]
        assert "give_abx" in node["mandatory_actions"]

    def test_forbidden_in_forbidden(self) -> None:
        atoms = [_make_atom(constraint_type="FORBIDDEN", action_id="give_nitro")]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        node = list(graph["nodes"].values())[0]
        assert "give_nitro" in node["forbidden_actions"]
        assert "give_nitro" not in node["mandatory_actions"]

    def test_within_has_deadline(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        node = list(graph["nodes"].values())[0]
        assert node["deadlines"]["give_abx"] == 60


# ------------------------------------------------------------------
# Edge wiring
# ------------------------------------------------------------------


class TestEdgeWiring:
    def test_before_constraint_creates_edge(self) -> None:
        atoms = [
            _make_atom(
                section="Blood Cultures",
                action_id="order_blood_culture",
                constraint_type="BEFORE",
                before=["give_abx"],
            ),
            _make_atom(section="Antibiotics", action_id="give_abx"),
        ]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        # Find node with blood culture
        for node in graph["nodes"].values():
            if "order_blood_culture" in node.get("allowed_actions", []):
                assert len(node["next_nodes"]) > 0
                break

    def test_linear_chain_fallback(self) -> None:
        atoms = [
            _make_atom(section="Step 1", action_id="a1", atom_id="atom_a1"),
            _make_atom(section="Step 2", action_id="a2", atom_id="atom_a2"),
            _make_atom(section="Step 3", action_id="a3", atom_id="atom_a3"),
        ]
        compiler = GraphCompiler()
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        # Without explicit sequence constraints, should get linear chain
        node_ids = list(graph["nodes"].keys())
        assert len(node_ids) == 3
        # First node should point to second
        first_node = graph["nodes"][node_ids[0]]
        assert node_ids[1] in first_node["next_nodes"]


# ------------------------------------------------------------------
# Max nodes enforcement
# ------------------------------------------------------------------


class TestMaxNodes:
    def test_merge_when_exceeds_max(self) -> None:
        atoms = [_make_atom(section=f"Section {i}", action_id=f"a{i}", atom_id=f"atom_a{i}") for i in range(10)]
        compiler = GraphCompiler(GraphCompilerConfig(max_nodes=5))
        graph = compiler.compile(atoms, "ssc", "SSC 2021")
        assert len(graph["nodes"]) <= 5


# ------------------------------------------------------------------
# β-5: Defensive action normalization in graph output
# ------------------------------------------------------------------


class TestDefensiveNormalization:
    """Verify compiled graph action IDs are canonicalized by ActionNormalizer."""

    def test_forbidden_actions_normalized_in_graph(self) -> None:
        """A FORBIDDEN atom with a raw alias should appear in canonical form in graph output."""
        atom = _make_atom(
            section="Contraindications",
            action_id="broad_spectrum_antibiotics",  # raw alias
            constraint_type="FORBIDDEN",
            atom_id="atom_forbidden_raw",
        )
        compiler = GraphCompiler()
        graph = compiler.compile([atom], "test", "Test")

        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            normalizer = ActionNormalizer()
            expected = normalizer.normalize("broad_spectrum_antibiotics")
        except ImportError:
            expected = "broad_spectrum_antibiotics"

        node = list(graph["nodes"].values())[0]
        assert expected in node["forbidden_actions"], (
            f"Expected canonical '{expected}' in forbidden_actions, got {node['forbidden_actions']}"
        )

    def test_mandatory_actions_normalized_in_graph(self) -> None:
        """REQUIRED atoms with raw aliases emerge canonical in mandatory_actions."""
        atom = _make_atom(
            section="Hour-1",
            action_id="blood_culture_before_antibiotics",  # known alias
            constraint_type="REQUIRED",
            atom_id="atom_mand_raw",
        )
        compiler = GraphCompiler()
        graph = compiler.compile([atom], "test", "Test")

        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            normalizer = ActionNormalizer()
            expected = normalizer.normalize("blood_culture_before_antibiotics")
        except ImportError:
            expected = "blood_culture_before_antibiotics"

        node = list(graph["nodes"].values())[0]
        assert expected in node["mandatory_actions"]
        assert expected in node["allowed_actions"]

    def test_required_prior_actions_normalized(self) -> None:
        """required_prior_actions keys and values are also canonicalized."""
        atom = _make_atom(
            section="Hour-1",
            action_id="give_abx",
            constraint_type="REQUIRED",
            required_prior=["blood_culture_before_antibiotics"],
            atom_id="atom_seq_raw",
        )
        compiler = GraphCompiler()
        graph = compiler.compile([atom], "test", "Test")

        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            normalizer = ActionNormalizer()
            expected_prior = normalizer.normalize("blood_culture_before_antibiotics")
        except ImportError:
            expected_prior = "blood_culture_before_antibiotics"

        node = list(graph["nodes"].values())[0]
        rpa = node.get("required_prior_actions", {})
        # The prior list for give_abx should contain the canonical form
        all_priors = [p for priors in rpa.values() for p in priors]
        assert expected_prior in all_priors, f"Expected '{expected_prior}' in priors, got {rpa}"
