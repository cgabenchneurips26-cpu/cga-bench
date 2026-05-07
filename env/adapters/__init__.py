"""
Legacy adapter layer (env/adapters/).

CANONICAL PATH: semantic_layer/external/

This module contains early-stage adapters for MedAgentBench, MedChain,
AgentClinic, and ArchEHR-QA. The canonical adapter interface is now in
semantic_layer/external/ which provides:
- UniversalExternalAdapter (unified interface)
- DatasetManifest (registry)
- 4-stage pipeline (Parse→Normalize→Evaluate→Report)

New dataset integrations should use semantic_layer/external/.
This module is maintained for backward compatibility only.
"""
from cga_bench.env.adapters.base_adapter import (
    BaseAdapter,
    AdaptedEpisode,
    AdaptedAction,
)
from cga_bench.env.adapters.medagentbench_adapter import (
    MedAgentBenchAdapter,
    FHIRResourceMapper,
)
from cga_bench.env.adapters.agentclinic_adapter import (
    AgentClinicAdapter,
)

__all__ = [
    "BaseAdapter",
    "AdaptedEpisode",
    "AdaptedAction",
    "MedAgentBenchAdapter",
    "FHIRResourceMapper",
    "AgentClinicAdapter",
]
