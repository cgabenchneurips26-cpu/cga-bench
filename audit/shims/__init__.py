"""Pre-built evaluator shims backed by verdict_matrix_v6.json.

Each shim wraps a frozen cache of one evaluator's outputs on the
14,826-episode W8-filtered corpus. verdict() is O(1) by episode_id.
"""

from audit.shims.ac_proxy import ACProxyShim
from audit.shims.acov_shim import ACovShim
from audit.shims.active_agent_shim import ActiveAgentShim
from audit.shims.c2_shim import C2Shim
from audit.shims.dxem import DxEMShim
from audit.shims.llm_catalogue_shim import LLMCatalogueShim
from audit.shims.llm_judge_shim import LLMJudgeEvaluator
from audit.shims.mab_proxy import MABProxyShim
from audit.shims.pi_nord_shim import PiNordShim
from audit.shims.v4_hard import V4HardShim
from audit.shims.violation_count_shim import ViolationCountEvaluator
from audit.wrappers import WRAPPER_REGISTRY
from audit.wrappers.metric_evaluators import (
    ActionCoverageEvaluator,
    AlwaysTrueEvaluator,
    C2ScoreEvaluator,
    MABF1Evaluator,
)

__all__ = [
    "ACProxyShim",
    "ACovShim",
    "ActionCoverageEvaluator",
    "ActiveAgentShim",
    "AlwaysTrueEvaluator",
    "C2ScoreEvaluator",
    "C2Shim",
    "DxEMShim",
    "LLMJudgeEvaluator",
    "MABF1Evaluator",
    "MABProxyShim",
    "PiNordShim",
    "V4HardShim",
    "ViolationCountEvaluator",
]

SHIM_REGISTRY: dict[str, type] = {
    "dxem": DxEMShim,
    "ac_proxy": ACProxyShim,
    "mab_proxy": MABProxyShim,
    "c2_shim": C2Shim,
    "acov_shim": ACovShim,
    "v4_hard": V4HardShim,
    "viol_count": ViolationCountEvaluator,
    "llm_judge": LLMJudgeEvaluator,
    "active_agent": ActiveAgentShim,
    "pi_nord_witness": PiNordShim,
    "llm_catalogue": LLMCatalogueShim,
    # Option C alternative evaluators
    **WRAPPER_REGISTRY,
}
