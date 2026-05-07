"""
Process mining module: Outcome-Driven Pathway Mining.

Provides pathway extraction, Graph Edit Distance (GED) computation,
similarity clustering, and outcome correlation analysis.
"""
from .pathway_miner import (
    CorrelationResult,
    MiningConfig,
    MiningResult,
    Pathway,
    PathwayCluster,
    PathwayMiner,
)

__all__ = [
    "CorrelationResult",
    "MiningConfig",
    "MiningResult",
    "Pathway",
    "PathwayCluster",
    "PathwayMiner",
]
