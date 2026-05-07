"""End-to-end SGSC pipeline orchestration.

15-step pipeline: corpus -> atoms -> verification -> compile -> optimize -> audit.
LLM is used only in steps 2, 4, 6. Steps 7-15 are fully deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any

from sgsc.audit.coverage_reporter import write_coverage_report
from sgsc.audit.leakage_scanner import scan_public_scenarios, scan_scenarios
from sgsc.audit.source_fidelity import compute_source_fidelity
from sgsc.compilers.constraint_compiler import atoms_to_derived_constraints
from sgsc.compilers.counterfactual_compiler import compile_families
from sgsc.compilers.graph_compiler import GraphCompiler
from sgsc.compilers.mutation_compiler import compile_all_mutations
from sgsc.compilers.scenario_compiler import (
    compile_seeds,
    seeds_to_scenario_yaml,
    seeds_to_split_scenario_yaml,
)
from sgsc.extraction.atom_proposer import AtomProposerConfig, propose_atoms
from sgsc.extraction.schema_validator import validate_atoms
from sgsc.optimizer.scenario_selector import select_scenarios
from sgsc.schemas.atom import RecommendationAtom
from sgsc.verification.entailment_checker import check_atoms_entailment
from sgsc.verification.quote_verifier import verify_atom_quotes

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Pipeline configuration
# ------------------------------------------------------------------


@dataclass
class PipelineConfig:
    """Configuration for the full SGSC pipeline."""

    guideline_id: str
    guideline_name: str
    output_dir: str
    llm_config: AtomProposerConfig | None = None
    enable_multi_model: bool = False
    entailment_mode: str = "rule_based"
    grounding_threshold: float = 0.6
    max_scenarios: int = 500


# ------------------------------------------------------------------
# Pipeline result
# ------------------------------------------------------------------


@dataclass
class PipelineResult:
    """Result of the full pipeline run.

    Atom buckets after step-6 entailment:
        ``atoms``                  — accepted (passed grounding + entailment)
        ``rejected_atoms``         — NOT_ENTAILED in at least one field
                                     (firm rejection per Gate 2)
        ``review_required_atoms``  — grounding failure or PARTIAL evidence
                                     under strict mode (needs human triage)
    """

    atoms: list[RecommendationAtom] = field(default_factory=list)
    rejected_atoms: list[RecommendationAtom] = field(default_factory=list)
    review_required_atoms: list[RecommendationAtom] = field(default_factory=list)
    graph: dict[str, Any] = field(default_factory=dict)
    scenarios: dict[str, dict[str, Any]] = field(default_factory=dict)
    scenarios_public: dict[str, dict[str, Any]] = field(default_factory=dict)
    scenarios_private: dict[str, dict[str, Any]] = field(default_factory=dict)
    coverage_paths: dict[str, str] = field(default_factory=dict)
    hallucination_rate: float = 0.0
    leakage_passed: bool = True
    total_seeds: int = 0
    total_families: int = 0
    total_mutations: int = 0


# ------------------------------------------------------------------
# Pipeline
# ------------------------------------------------------------------


def _normalize_atom_actions(atoms: list[RecommendationAtom]) -> list[RecommendationAtom]:
    """Normalize atom action IDs through ActionNormalizer (post-LLM, pre-entailment).

    Uses lazy import with graceful fallback so SGSC can run standalone
    when cga_bench package path isn't configured.
    """
    try:
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer
    except ImportError:
        logger.warning("ActionNormalizer not available — skipping action normalization")
        return atoms

    normalizer = ActionNormalizer()
    n_changed = 0
    for atom in atoms:
        original = atom.action.canonical_id
        normalized = normalizer.normalize(original)
        if normalized != original:
            logger.info("Normalized action: %s -> %s (atom %s)", original, normalized, atom.atom_id)
            # AtomAction is frozen — use model_copy; RecommendationAtom is mutable
            atom.action = atom.action.model_copy(update={"canonical_id": normalized})
            n_changed += 1

        # Also normalize sequence references (required_prior, before)
        # AtomSequence is frozen — rebuild via model_copy
        seq_updates: dict[str, list[str]] = {}
        if atom.sequence.required_prior:
            seq_updates["required_prior"] = [normalizer.normalize(a) for a in atom.sequence.required_prior]
        if atom.sequence.before:
            seq_updates["before"] = [normalizer.normalize(a) for a in atom.sequence.before]
        if seq_updates:
            atom.sequence = atom.sequence.model_copy(update=seq_updates)

    if n_changed:
        logger.info("Step 2b: Normalized %d / %d atom action IDs", n_changed, len(atoms))
    else:
        logger.info("Step 2b: All %d atom action IDs already canonical", len(atoms))
    return atoms


def run_pipeline(
    config: PipelineConfig,
    corpus_full_text: str,
    recommendations: list[dict[str, Any]],
    precomputed_atoms: list[RecommendationAtom] | None = None,
) -> PipelineResult:
    """Run the full 15-step SGSC pipeline.

    Steps:
    1. Load recommendations (already provided)
    2. LLM proposes atoms (or use precomputed)
    3. Schema validation
    4. [Optional] Multi-model agreement
    5. 3-tier quote grounding
    6. Field-level entailment (mandatory)
    7. Deterministic graph compiler
    8. Deterministic scenario seed compiler
    9. Deterministic counterfactual family compiler
    10. Mutation trace compiler
    11. Extract coverage items
    12. Set-cover optimizer
    13. Generate scenario YAML files (full + public/private split)
    14. Leakage audit (full scenarios + public-only scan)
    15. Coverage report

    Args:
        config: Pipeline configuration.
        corpus_full_text: Full text of the RAG corpus.
        recommendations: List of recommendation dicts.
        precomputed_atoms: Skip LLM step if atoms are pre-provided.

    Returns:
        PipelineResult with all outputs.
    """
    result = PipelineResult()
    output = Path(config.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # Step 1-2: Get atoms
    if precomputed_atoms:
        atoms = list(precomputed_atoms)
        logger.info("Using %d precomputed atoms", len(atoms))
    elif config.llm_config:
        logger.info("Step 2: Proposing atoms via LLM...")
        atoms = propose_atoms(config.llm_config, config.guideline_id, recommendations, corpus_full_text)
        logger.info("Proposed %d atoms", len(atoms))
    else:
        logger.warning("No LLM config and no precomputed atoms — empty pipeline")
        return result

    # Step 2b: Normalize action IDs through ActionNormalizer
    atoms = _normalize_atom_actions(atoms)

    # Step 3: Schema validation
    logger.info("Step 3: Schema validation...")
    validation = validate_atoms(atoms)
    atoms = validation.valid_atoms
    if validation.rejected_atoms:
        logger.warning("Rejected %d atoms with validation errors", len(validation.rejected_atoms))

    # Step 4: Multi-model agreement (optional, skip for now)
    if config.enable_multi_model:
        logger.info("Step 4: Multi-model agreement (skipped — single model)")

    # Step 5: Quote grounding
    logger.info("Step 5: Quote grounding...")
    verification_results = verify_atom_quotes(atoms, corpus_full_text, recommendations, config.grounding_threshold)
    # Filter to VERIFIED or GROUNDED
    verified_ids = {r.atom_id for r in verification_results if r.status in ("VERIFIED", "GROUNDED")}
    grounding_failures = [a for a in atoms if a.atom_id not in verified_ids]
    grounded_atoms = [a for a in atoms if a.atom_id in verified_ids]
    for a in grounded_atoms:
        a.entailment_status = "grounded"
    logger.info("Grounded %d / %d atoms", len(grounded_atoms), len(atoms))
    atoms = grounded_atoms

    # Step 6: Field-level entailment (mandatory)
    logger.info("Step 6: Field-level entailment (%s mode)...", config.entailment_mode)
    entailment_reports = check_atoms_entailment(
        atoms,
        mode=config.entailment_mode,
        action_threshold=config.grounding_threshold,
        guard_threshold=config.grounding_threshold,
    )

    # Strict mode (Gate 2 mandatory): PARTIAL counts as failure.
    strict_mode = config.entailment_mode == "llm_strict"

    passing_atom_ids: set[str] = set()
    rejected_atom_ids: set[str] = set()
    partial_atom_ids: set[str] = set()
    for report in entailment_reports:
        is_passing = report.strict_passed if strict_mode else report.all_passed
        if is_passing:
            passing_atom_ids.add(report.atom_id)
        elif report.failed_fields:
            # Firm rejection: at least one field is NOT_ENTAILED.
            rejected_atom_ids.add(report.atom_id)
            logger.warning(
                "Atom %s rejected (NOT_ENTAILED): %s",
                report.atom_id,
                ", ".join(report.failed_fields),
            )
        else:
            # Lenient mode reaches here only when an atom has PARTIAL fields
            # and no NOT_ENTAILED — strict mode flagged it for human triage.
            partial_atom_ids.add(report.atom_id)
            logger.info(
                "Atom %s flagged for review (PARTIAL): %s",
                report.atom_id,
                ", ".join(report.partial_fields),
            )

    pre_entailment_count = len(atoms)
    rejected_atoms = [a for a in atoms if a.atom_id in rejected_atom_ids]
    review_required = grounding_failures + [a for a in atoms if a.atom_id in partial_atom_ids]
    atoms = [a for a in atoms if a.atom_id in passing_atom_ids]
    for a in atoms:
        a.entailment_status = "entailed"
    for a in rejected_atoms:
        a.entailment_status = "rejected"
    logger.info(
        "Entailment: %d / %d atoms passed (%d rejected, %d review_required)",
        len(atoms),
        pre_entailment_count,
        len(rejected_atoms),
        len(review_required),
    )

    result.rejected_atoms = rejected_atoms
    result.review_required_atoms = review_required

    # Collect first-field verdicts for source fidelity downstream
    entailment_verdicts = [
        r.field_results[0].verdict if r.field_results else "NOT_ENTAILED" for r in entailment_reports
    ]

    # Step 7: Graph compiler
    logger.info("Step 7: Compiling graph...")
    compiler = GraphCompiler()
    graph = compiler.compile(atoms, config.guideline_id, config.guideline_name)
    result.graph = graph

    # Save graph
    graph_path = output / f"{config.guideline_id}_graph.json"
    graph_path.write_text(json.dumps(graph, indent=2))

    # Step 8: Scenario seeds
    logger.info("Step 8: Compiling scenario seeds...")
    seeds = compile_seeds(atoms, config.guideline_id)
    result.total_seeds = len(seeds)

    # Step 9: Counterfactual families
    logger.info("Step 9: Compiling counterfactual families...")
    families = compile_families(atoms)
    result.total_families = len(families)

    # Step 10: Mutation traces
    logger.info("Step 10: Compiling mutation traces...")
    mutations = compile_all_mutations(seeds, atoms)
    result.total_mutations = len(mutations)

    # Steps 11-12: Coverage optimization
    logger.info("Steps 11-12: Coverage optimization...")
    selection = select_scenarios(atoms, seeds, families)

    # Step 13: Generate scenario YAML
    logger.info("Step 13: Generating scenario YAML...")
    selected_seed_set = set(selection.selected_seed_ids)
    selected_seeds = [s for s in seeds if s.seed_id in selected_seed_set]
    # Track-4-2: feed compiled-graph forbidden_actions into scenario YAML
    graph_nodes = graph.get("nodes")
    scenarios = seeds_to_scenario_yaml(
        selected_seeds, config.guideline_id, atoms, graph_nodes=graph_nodes
    )
    result.scenarios = scenarios

    # Save full scenarios
    scenarios_path = output / f"{config.guideline_id}_scenarios.json"
    scenarios_path.write_text(json.dumps(scenarios, indent=2))

    # Also generate public/private split
    scenarios_public, scenarios_private = seeds_to_split_scenario_yaml(
        selected_seeds, config.guideline_id, atoms, graph_nodes=graph_nodes
    )
    result.scenarios_public = scenarios_public
    result.scenarios_private = scenarios_private

    # Save split files
    public_path = output / f"{config.guideline_id}_scenarios_public.json"
    public_path.write_text(json.dumps(scenarios_public, indent=2))
    private_path = output / f"{config.guideline_id}_scenarios_private.json"
    private_path.write_text(json.dumps(scenarios_private, indent=2))

    # Step 14: Leakage audit
    logger.info("Step 14: Leakage audit...")
    leakage = scan_scenarios(scenarios)
    if not leakage.passed:
        logger.warning("Leakage detected: %d leaks", len(leakage.leaks))

    public_leakage = scan_public_scenarios(scenarios_public)
    if not public_leakage.passed:
        logger.warning("Public scenario leakage: %d leaks", len(public_leakage.leaks))

    result.leakage_passed = leakage.passed and public_leakage.passed

    # Step 15: Coverage report
    logger.info("Step 15: Coverage report...")
    result.coverage_paths = write_coverage_report(selection.coverage_report, str(output), config.guideline_id)

    # Source fidelity
    fidelity = compute_source_fidelity(verification_results, entailment_verdicts)
    result.hallucination_rate = fidelity.hallucination_report.hallucination_rate
    result.atoms = atoms

    # Save atoms for manifest builder and downstream tooling
    atoms_path = output / "atoms_smoke.json"
    atoms_path.write_text(json.dumps([a.model_dump(mode="json") for a in atoms], indent=2))

    # Save constraints
    constraints = atoms_to_derived_constraints(atoms)
    constraints_data = [
        {"constraint_type": c.constraint_type, "actions": c.actions, "severity": c.severity} for c in constraints
    ]
    constraints_path = output / f"{config.guideline_id}_constraints.json"
    constraints_path.write_text(json.dumps(constraints_data, indent=2))

    logger.info(
        "Pipeline complete: %d atoms, %d seeds, %d families, %d mutations, %d scenarios",
        len(atoms),
        len(seeds),
        len(families),
        len(mutations),
        len(scenarios),
    )

    return result
