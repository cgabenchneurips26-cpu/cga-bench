#!/usr/bin/env python3
"""γ-2 helper: generate temperature-variant agent configs.

Creates 8 configs (Qwen397B + Gemma31B at T ∈ {0.0, 0.3, 0.7, 1.0})
mirroring the existing single-T configs.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs" / "agents"

VARIANTS = [
    # (base_id, label_prefix, llm_model, base_url)
    (
        "qwen397b",
        "Qwen3.5-397B",
        "Qwen/Qwen3.5-397B-A17B-FP8",
        "http://localhost:8013/v1",
    ),
    (
        "gemma31b",
        "Gemma4-31B-IT",
        "google/gemma-4-31b-it",
        "http://localhost:8013/v1",
    ),
]
TEMPS = [0.0, 0.3, 0.7, 1.0]


def main() -> int:
    written = []
    for base_id, label_prefix, llm_model, base_url in VARIANTS:
        for t in TEMPS:
            tag = f"temp{int(round(t * 10)):02d}"
            agent_id_full = f"{base_id}_{tag}"
            cfg_path = CONFIGS / f"clean_slate_{agent_id_full}.yaml"
            content = f"""# Clean Slate: {label_prefix} @ T={t} (γ-2 temp sensitivity sweep)
agent:
  type: "rag"
  agent_id: "rag_{agent_id_full}"
  llm_backend: "vllm"
  llm_model: "{llm_model}"
  temperature: {t}
  use_llm: true
  base_url: "{base_url}"
  api_key: "sk-no-key-required"
  top_k: 5
  use_bm25: true
  cpg_sources_path: null
  max_actions_per_step: 3
  budget_limit_tokens: 100000
  budget_limit_tool_calls: 50
"""
            cfg_path.write_text(content)
            written.append(cfg_path.name)
            print(f"wrote {cfg_path}")
    print(f"\nTotal: {len(written)} configs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
