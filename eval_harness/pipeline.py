"""
Post-Scoring Pipeline: integrates XES export, LTL/CTL verification,
LLM-Judge severity, and pathway mining into the evaluation runner.

All features are opt-in via PipelineConfig. When disabled, the pipeline
is a no-op and runner behavior is unchanged.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from cga_bench.cpg_model.schemas.base import CGAScore, ViolationEvent
from cga_bench.semantic_layer.conformance.activity import (
    ActivityEvent,
    extract_activity_events,
)

logger = logging.getLogger(__name__)


# ============================================
# Configuration
# ============================================

@dataclass
class PipelineConfig:
    """Configuration for the post-scoring analysis pipeline.

    All features are disabled by default for backward compatibility.
    """
    # XES Export (per-episode)
    enable_xes_export: bool = False
    xes_output_dir: Optional[str] = None
    xes_enable_outcome: bool = True
    xes_enable_violation_overlay: bool = True

    # LTL Verification (per-episode)
    enable_ltl_verification: bool = False
    ltl_properties_file: Optional[str] = None
    # Ontology-based subsumption for LTL atom matching
    ontology_domain: Optional[str] = None  # e.g., "sepsis", "chest_pain", None=unified

    # LLM Judge (per-episode)
    enable_llm_judge: bool = False
    llm_judge_backend: str = "mock"
    llm_judge_model: str = "gpt-4"
    llm_judge_api_key: Optional[str] = None

    # Pathway Mining (batch-level, after all episodes)
    enable_pathway_mining: bool = False
    mining_ged_threshold: float = 3.0
    mining_min_cluster_size: int = 2


# ============================================
# Pipeline Results
# ============================================

@dataclass
class EpisodePipelineResult:
    """Results from the per-episode pipeline."""
    episode_id: str
    xes_path: Optional[str] = None
    ltl_satisfied: Optional[int] = None
    ltl_violated: Optional[int] = None
    ltl_violations: List[str] = field(default_factory=list)
    llm_judge_applied: bool = False
    severity_changes: int = 0


@dataclass
class BatchPipelineResult:
    """Results from the batch-level pipeline (pathway mining)."""
    total_pathways: int = 0
    num_clusters: int = 0
    high_performing: List[str] = field(default_factory=list)
    low_performing: List[str] = field(default_factory=list)
    significant_correlations: List[Dict[str, Any]] = field(default_factory=list)


# ============================================
# Post-Scoring Pipeline
# ============================================

class PostScoringPipeline:
    """Orchestrates post-scoring analysis for episodes and batches.

    Integration points:
    - Per-episode: called after run_episode() produces a score
    - Batch-level: called after all episodes in an experiment complete

    Usage:
        pipeline = PostScoringPipeline(config)
        # Per-episode
        ep_result = pipeline.process_episode(episode_id, events, score, violations)
        # Batch-level
        batch_result = pipeline.process_batch(all_pathways, all_scores)
    """

    def __init__(self, config: PipelineConfig):
        self._config = config
        self._xes_exporter = None
        self._ltl_verifier = None
        self._ltl_properties = None
        self._llm_judge = None
        self._miner = None
        self._init_components()

    def process_episode(
        self,
        episode_id: str,
        raw_events: List[Dict[str, Any]],
        score: CGAScore,
        violations: List[ViolationEvent],
        patient_context: Optional[str] = None,
    ) -> EpisodePipelineResult:
        """Run per-episode pipeline: XES export, LTL verify, LLM judge.

        Args:
            episode_id: Unique episode identifier
            raw_events: Raw tool call events from the episode log
            score: Computed CGAScore
            violations: Extracted violations
            patient_context: Optional clinical context for LLM judge

        Returns:
            EpisodePipelineResult with paths and summaries
        """
        result = EpisodePipelineResult(episode_id=episode_id)

        # Extract activity events from raw events
        activity_events = self._extract_activities(raw_events)

        # 1. XES Export
        if self._config.enable_xes_export and self._xes_exporter:
            result.xes_path = self._export_xes(
                episode_id, activity_events, score, violations
            )

        # 2. LTL Verification
        if self._config.enable_ltl_verification and self._ltl_verifier:
            satisfied, violated, violation_names = self._verify_ltl(activity_events)
            result.ltl_satisfied = satisfied
            result.ltl_violated = violated
            result.ltl_violations = violation_names

        # 3. LLM Judge
        if self._config.enable_llm_judge and self._llm_judge:
            changes = self._apply_llm_judge(violations, patient_context)
            result.llm_judge_applied = True
            result.severity_changes = changes

        return result

    def process_batch(
        self,
        episode_data: List[Dict[str, Any]],
    ) -> BatchPipelineResult:
        """Run batch-level pipeline: pathway mining and outcome correlation.

        Args:
            episode_data: List of dicts with keys:
                - episode_id: str
                - raw_events: List[Dict]
                - score: CGAScore

        Returns:
            BatchPipelineResult with mining insights
        """
        if not self._config.enable_pathway_mining or not self._miner:
            return BatchPipelineResult()

        from cga_bench.semantic_layer.mining.pathway_miner import Pathway

        pathways: List[Pathway] = []
        scores: List[CGAScore] = []

        for ep in episode_data:
            activities = self._extract_activities(ep.get("raw_events", []))
            if activities:
                pw = self._miner.extract_pathway(ep["episode_id"], activities)
                pathways.append(pw)
                if ep.get("score"):
                    scores.append(ep["score"])

        if not pathways:
            return BatchPipelineResult()

        mining_result = self._miner.mine(pathways, scores if scores else None)

        # Extract significant correlations
        sig_corr = [
            {
                "feature": c.feature_name,
                "dimension": c.score_dimension,
                "correlation": round(c.correlation, 3),
                "p_value": round(c.p_value, 4),
            }
            for c in mining_result.correlations
            if abs(c.correlation) > 0.5 and c.p_value < 0.05
        ]

        return BatchPipelineResult(
            total_pathways=len(mining_result.pathways),
            num_clusters=len(mining_result.clusters),
            high_performing=mining_result.high_performing_pathways,
            low_performing=mining_result.low_performing_pathways,
            significant_correlations=sig_corr,
        )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_components(self):
        """Initialize pipeline components based on config."""
        if self._config.enable_xes_export:
            self._init_xes()
        if self._config.enable_ltl_verification:
            self._init_ltl()
        if self._config.enable_llm_judge:
            self._init_llm_judge()
        if self._config.enable_pathway_mining:
            self._init_miner()

    def _init_xes(self):
        """Initialize XES exporter."""
        try:
            from cga_bench.semantic_layer.export.xes_exporter import (
                XESExporter,
                XESExportConfig,
                XESPerspectiveConfig,
            )
            perspective = XESPerspectiveConfig(
                enable_outcome_perspective=self._config.xes_enable_outcome,
                enable_violation_overlay=self._config.xes_enable_violation_overlay,
            )
            config = XESExportConfig(perspective_config=perspective)
            self._xes_exporter = XESExporter(config)

            if self._config.xes_output_dir:
                Path(self._config.xes_output_dir).mkdir(parents=True, exist_ok=True)

            logger.info("XES exporter initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize XES exporter: {e}")

    def _init_ltl(self):
        """Initialize LTL verifier and load properties."""
        try:
            from cga_bench.semantic_layer.export.temporal_logic_verifier import (
                LTLVerifier,
                PropertySpec,
            )
            # Create ontology matcher if domain specified
            ontology_matcher = None
            if self._config.ontology_domain is not None:
                try:
                    from cga_bench.semantic_layer.ontology.domain_hierarchies import (
                        get_ontology_matcher,
                        get_unified_matcher,
                    )
                    if self._config.ontology_domain:
                        ontology_matcher = get_ontology_matcher(self._config.ontology_domain)
                    else:
                        ontology_matcher = get_unified_matcher()
                    logger.info(f"Ontology matcher initialized (domain={self._config.ontology_domain or 'unified'})")
                except Exception as e:
                    logger.warning(f"Failed to initialize ontology matcher: {e}")

            self._ltl_verifier = LTLVerifier(ontology_matcher=ontology_matcher)

            if self._config.ltl_properties_file:
                self._ltl_properties = self._load_ltl_properties(
                    self._config.ltl_properties_file
                )
                logger.info(
                    f"LTL verifier initialized with {len(self._ltl_properties)} properties"
                )
            else:
                self._ltl_properties = []
                logger.info("LTL verifier initialized (no properties file)")
        except Exception as e:
            logger.warning(f"Failed to initialize LTL verifier: {e}")

    def _init_llm_judge(self):
        """Initialize LLM severity judge."""
        try:
            from cga_bench.semantic_layer.conformance.llm_severity_judge import (
                LLMJudgeConfig,
                LLMSeverityJudge,
            )
            config = LLMJudgeConfig(
                backend=self._config.llm_judge_backend,
                model=self._config.llm_judge_model,
                api_key=self._config.llm_judge_api_key,
            )
            self._llm_judge = LLMSeverityJudge(config)
            logger.info(f"LLM Judge initialized (backend={self._config.llm_judge_backend})")
        except Exception as e:
            logger.warning(f"Failed to initialize LLM judge: {e}")

    def _init_miner(self):
        """Initialize pathway miner."""
        try:
            from cga_bench.semantic_layer.mining.pathway_miner import (
                MiningConfig,
                PathwayMiner,
            )
            config = MiningConfig(
                ged_threshold=self._config.mining_ged_threshold,
                min_cluster_size=self._config.mining_min_cluster_size,
            )
            self._miner = PathwayMiner(config)
            logger.info("Pathway miner initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize pathway miner: {e}")

    # ------------------------------------------------------------------
    # Per-episode handlers
    # ------------------------------------------------------------------

    def _extract_activities(
        self, raw_events: List[Dict[str, Any]]
    ) -> List[ActivityEvent]:
        """Extract ActivityEvents from raw tool call events."""
        try:
            result = extract_activity_events(raw_events)
            # extract_activity_events returns (events, unrecognized) tuple
            if isinstance(result, tuple):
                return result[0]
            return result
        except Exception as e:
            logger.debug(f"Activity extraction failed: {e}")
            return []

    def _export_xes(
        self,
        episode_id: str,
        events: List[ActivityEvent],
        score: CGAScore,
        violations: List[ViolationEvent],
    ) -> Optional[str]:
        """Export episode to XES with outcome annotations."""
        try:
            xml = self._xes_exporter.export_with_outcomes(
                episode_id=episode_id,
                events=events,
                score=score,
                violations=violations,
            )
            if self._config.xes_output_dir:
                out_path = Path(self._config.xes_output_dir) / f"{episode_id}.xes"
                out_path.write_text(xml, encoding="utf-8")
                return str(out_path)
            return None
        except Exception as e:
            logger.warning(f"XES export failed for {episode_id}: {e}")
            return None

    def _verify_ltl(
        self, events: List[ActivityEvent]
    ) -> tuple:
        """Verify LTL properties against the trace."""
        if not self._ltl_properties:
            return 0, 0, []

        try:
            report = self._ltl_verifier.verify_properties(
                events, self._ltl_properties
            )
            violation_names = []
            for i, result in enumerate(report.results):
                if not result.satisfied and i < len(self._ltl_properties):
                    violation_names.append(self._ltl_properties[i].name)
            return report.satisfied, report.violated, violation_names
        except Exception as e:
            logger.warning(f"LTL verification failed: {e}")
            return 0, 0, []

    def _apply_llm_judge(
        self,
        violations: List[ViolationEvent],
        patient_context: Optional[str],
    ) -> int:
        """Apply LLM judge to re-assess violation severities."""
        if not violations:
            return 0

        try:
            result = self._llm_judge.judge_violations(violations, patient_context)
            changes = sum(1 for jv in result.judged_violations if jv.severity_changed)
            return changes
        except Exception as e:
            logger.warning(f"LLM judge failed: {e}")
            return 0

    # ------------------------------------------------------------------
    # Property loading
    # ------------------------------------------------------------------

    def _load_ltl_properties(self, path: str) -> List:
        """Load LTL properties from a YAML file.

        Expected YAML format:
            properties:
              - name: "response_culture_to_abx"
                type: "response"
                trigger: "ORDER_BLOOD_CULTURE"
                response: "GIVE_ANTIBIOTICS"
                category: "safety"
              - name: "absence_nitrates"
                type: "absence"
                forbidden: "GIVE_NITRATES"
                category: "safety"
              - name: "precedence_assess_before_treat"
                type: "precedence"
                prerequisite: "ASSESS_VITALS"
                action: "GIVE_MEDICATION"
                category: "safety"
              - name: "existence_vitals"
                type: "existence"
                required: "ASSESS_VITALS"
                category: "liveness"
              - name: "not_succession_rv_nitrates"
                type: "not_succession"
                a: "DIAGNOSE_RV_INFARCT"
                b: "GIVE_NITRATES"
                category: "safety"
        """
        import yaml

        from cga_bench.semantic_layer.export.temporal_logic_verifier import (
            absence_property,
            existence_property,
            not_succession_property,
            precedence_property,
            response_property,
            # MTL bounded properties
            response_within_property,
            existence_within_property,
            absence_after_property,
            bounded_response_chain_property,
        )

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load LTL properties from {path}: {e}")
            return []

        properties = []
        for entry in data.get("properties", []):
            prop_type = entry.get("type", "")
            try:
                if prop_type == "response":
                    properties.append(response_property(
                        entry["trigger"], entry["response"]
                    ))
                elif prop_type == "absence":
                    properties.append(absence_property(entry["forbidden"]))
                elif prop_type == "precedence":
                    properties.append(precedence_property(
                        entry["prerequisite"], entry["action"]
                    ))
                elif prop_type == "existence":
                    properties.append(existence_property(entry["required"]))
                elif prop_type == "not_succession":
                    properties.append(not_succession_property(
                        entry["a"], entry["b"]
                    ))
                # MTL bounded types
                elif prop_type == "response_within":
                    properties.append(response_within_property(
                        entry["trigger"], entry["response"],
                        entry["max_minutes"],
                    ))
                elif prop_type == "existence_within":
                    properties.append(existence_within_property(
                        entry["required"], entry["max_minutes"],
                    ))
                elif prop_type == "absence_after":
                    properties.append(absence_after_property(
                        entry["trigger"], entry["forbidden"],
                        entry["window_minutes"],
                    ))
                elif prop_type == "bounded_response_chain":
                    properties.append(bounded_response_chain_property(
                        entry["a"], entry["b"], entry["c"],
                        entry["ab_max_minutes"], entry["bc_max_minutes"],
                    ))
                else:
                    logger.warning(f"Unknown LTL property type: {prop_type}")
            except KeyError as ke:
                logger.warning(f"Missing field in LTL property: {ke}")

        return properties
