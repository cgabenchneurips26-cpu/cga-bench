"""
Explainability module for CGA-Bench eval harness.
Provides template-based clinical explanation generation for violations.
"""

from cga_bench.eval_harness.explainability.violation_explainer import ViolationExplainer
from cga_bench.eval_harness.explainability.narrative_generator import EpisodeNarrativeGenerator
from cga_bench.eval_harness.explainability.radar_chart import RadarChartGenerator

__all__ = ["ViolationExplainer", "EpisodeNarrativeGenerator", "RadarChartGenerator"]
