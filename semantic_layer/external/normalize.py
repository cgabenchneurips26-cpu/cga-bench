import importlib
from typing import Any, Dict, Optional

from .agentclinic import normalize_agentclinic_case
from .medagentbench import normalize_medagentbench_task
from .medchain import normalize_medchain_case
from .pipeline import process_case
from .registry import REGISTRY


def normalize_external_case(
    source: str,
    raw_case: Dict[str, Any],
    case_id: Optional[str] = None,
) -> Any:
    source_lower = source.lower()
    if source_lower == "medagentbench":
        return normalize_medagentbench_task(raw_case)
    if source_lower == "medchain":
        resolved_case_id: str = str(case_id or raw_case.get("id", "unknown"))
        return normalize_medchain_case(resolved_case_id, raw_case)
    if source_lower == "agentclinic":
        if "OSCE_Examination" in raw_case:
            converter_module = importlib.import_module("scripts.load_external_benchmarks")
            raw_case = converter_module.convert_agentclinic_case(raw_case, 0)
        return normalize_agentclinic_case(raw_case)

    if source_lower == "healthbench":
        from .healthbench import parse_eval_row, parse_meta_eval_row

        if "rubrics" in raw_case and isinstance(raw_case.get("rubrics"), list):
            raw_case = parse_eval_row(raw_case)
        elif "rubric" in raw_case and isinstance(raw_case.get("rubric"), str):
            raw_case = parse_meta_eval_row(raw_case)
        manifest = REGISTRY["healthbench"]
        return process_case(raw_case, manifest)

    # Universal pipeline for registered datasets
    if source_lower in REGISTRY:
        manifest = REGISTRY[source_lower]
        return process_case(raw_case, manifest)

    raise ValueError(f"Unsupported source: {source}")
