"""
Report generation for multi-model comparison.

Generates Markdown and LaTeX comparison tables from PairwiseComparison results.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import logging

from cga_bench.eval_harness.comparison import PairwiseComparison

logger = logging.getLogger(__name__)


class ComparisonReportGenerator:
    """Generate comparison reports in Markdown and LaTeX."""

    def __init__(self, comparisons: List[PairwiseComparison]):
        self.comparisons = comparisons

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def generate_markdown_table(self) -> str:
        lines = [
            "# Multi-Agent Comparison Results",
            "",
            "## Pairwise Statistical Comparisons",
            "",
            "| Agent 1 | Agent 2 | Scenario | N | Mean Diff | 95% CI | p-value | Effect Size | Winner |",
            "|---------|---------|----------|---|-----------|--------|---------|-------------|--------|",
        ]
        for c in self.comparisons:
            t = c.tests[0] if c.tests else None
            es = c.effect_sizes[0] if c.effect_sizes else None
            p_str = f"{t.p_value:.4f}" if t else "—"
            sig = "***" if (t and t.significant) else ""
            es_str = f"{es.value:.3f} ({es.interpretation})" if es else "—"
            winner = c.winner or "—"
            lines.append(
                f"| {c.agent1} | {c.agent2} | {c.scenario} | {c.n_samples} | "
                f"{c.mean_diff:+.4f} | [{c.ci_lower:.4f}, {c.ci_upper:.4f}] | "
                f"{p_str}{sig} | {es_str} | {winner} |"
            )
        lines.extend([
            "",
            "> *** p < 0.05 (Bonferroni corrected)",
            "",
        ])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LaTeX
    # ------------------------------------------------------------------

    def generate_latex_table(self) -> str:
        lines = [
            r"\begin{table}[h]",
            r"\centering",
            r"\caption{Multi-Agent Performance Comparison}",
            r"\label{tab:agent_comparison}",
            r"\begin{tabular}{llrrrr}",
            r"\toprule",
            r"Agent 1 & Agent 2 & $\Delta$ Mean & 95\% CI & $p$ & Cohen's $d$ \\",
            r"\midrule",
        ]
        for c in self.comparisons:
            t = c.tests[0] if c.tests else None
            es = c.effect_sizes[0] if c.effect_sizes else None
            sig = r"$^{***}$" if (t and t.significant) else ""
            p_str = f"{t.p_value:.4f}" if t else "—"
            es_str = f"{es.value:.3f}" if es else "—"
            lines.append(
                f"{c.agent1} & {c.agent2} & "
                f"{c.mean_diff:+.4f} & "
                f"[{c.ci_lower:.4f}, {c.ci_upper:.4f}] & "
                f"{p_str}{sig} & "
                f"{es_str} \\\\"
            )
        lines.extend([
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------

    def generate_summary_statistics(self, summary_data: Dict[str, Any]) -> str:
        stats = summary_data.get("statistics", {})
        if not stats:
            return "## Summary Statistics\n\nNo statistics available.\n"

        lines = [
            "## Summary Statistics",
            "",
            "| Agent | Overall Mean | Overall Std | Scenarios |",
            "|-------|-------------|-------------|-----------|",
        ]
        for agent, s in stats.items():
            mean = s.get("overall_mean", 0)
            std = s.get("overall_std", 0)
            n_scenarios = len(s.get("by_scenario", {}))
            lines.append(f"| {agent} | {mean:.4f} | {std:.4f} | {n_scenarios} |")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Token efficiency
    # ------------------------------------------------------------------

    def generate_token_efficiency(self, summary_data: Dict[str, Any]) -> str:
        results = summary_data.get("results", [])
        eff: Dict[str, List[float]] = {}
        for r in results:
            tokens = r.get("total_tokens", 0)
            if tokens > 0:
                score = r.get("compliance_score", 0)
                agent = r.get("agent_id") or r.get("baseline_id", "unknown")
                eff.setdefault(agent, []).append(score / tokens)

        if not eff:
            return "## Token Efficiency\n\nNo token usage data available.\n"

        try:
            import numpy as _np
        except ImportError:
            return "## Token Efficiency\n\nnumpy required for efficiency analysis.\n"

        lines = [
            "## Token Efficiency (Score / Token)",
            "",
            "| Agent | Mean Efficiency | Std |",
            "|-------|----------------|-----|",
        ]
        for agent, vals in sorted(eff.items()):
            lines.append(f"| {agent} | {_np.mean(vals):.8f} | {_np.std(vals):.8f} |")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_report(
        self,
        output_path: Path,
        summary_path: Optional[Path] = None,
    ) -> None:
        """Save complete report as .md and .tex files."""
        summary_data: Dict[str, Any] = {}
        if summary_path and summary_path.exists():
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)

        parts = [
            self.generate_summary_statistics(summary_data),
            self.generate_markdown_table(),
            self.generate_token_efficiency(summary_data),
        ]
        md_content = "\n".join(parts)

        md_path = output_path.with_suffix(".md")
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        tex_path = output_path.with_suffix(".tex")
        tex_path.write_text(self.generate_latex_table(), encoding="utf-8")

        logger.info(f"Reports saved: {md_path}, {tex_path}")
        print(f"Reports saved:\n  - {md_path}\n  - {tex_path}")
