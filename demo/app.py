"""Gradio demo for the CGA-Bench evaluator audit harness.

A zero-install reviewer experience: select any registered shim (built-in
or external) from a dropdown, click "Run audit", see π-class, BSR,
Bayes floor, red-cell count, and the top-K false-accept witnesses.

Usage:
    pip install gradio
    PYTHONPATH=. python demo/app.py
    # opens http://localhost:7860

Deployment: see demo/README.md for HuggingFace Spaces hand-off.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gradio as gr  # noqa: E402

from audit.shims import SHIM_REGISTRY  # noqa: E402
from scripts.audit.evaluator_audit import run_audit  # noqa: E402

SHIM_CHOICES = sorted(SHIM_REGISTRY.keys())
DEFAULT_SHIM = "v4_hard" if "v4_hard" in SHIM_CHOICES else SHIM_CHOICES[0]


def _format_report_markdown(report: dict) -> str:
    """Pretty-print the core audit fields as Markdown."""
    s1 = report.get("step1_pi_class", {})
    s2 = report.get("step2_bsr", {})
    s3 = report.get("step3_bayes_floor", {})
    s6 = report.get("step6_blindspot_grid", {}) or {}
    ev = report.get("evaluator", {})

    lines = [
        f"# Audit report: `{ev.get('name', '?')}` ({ev.get('family', '?')})",
        "",
        "## Summary",
        f"- **π-class:** `{s1.get('pi_class', '?')}`",
        f"- **BSR:** {s2.get('bsr', 0):.4f} ({s2.get('n_disagree', 0):,}/{s2.get('n_total', 0):,})",
        f"- **False accepts:** {s2.get('n_false_accept', 0):,}",
        f"- **Bayes floor (ε\\*):** {s3.get('epsilon_star', 0):.3f}",
        f"- **Red cells:** {s6.get('n_red_cells', '?')}/{s6.get('n_cells', '?')}",
        "",
    ]

    if s6.get("marginal_bsr") is not None:
        lines.append(f"- **Marginal BSR (domain×viol):** {s6['marginal_bsr']:.4f}")
        lines.append("")

    s4 = report.get("step4_witnesses") or {}
    top_k = s4.get("top_k") or []
    if top_k:
        lines.append("## Top-K false-accept witnesses")
        for w in top_k[:5]:
            lines.append(
                f"- `{w.get('episode_id', '?')}` — scenario: `{w.get('scenario_id', '?')}`"
            )
    elif s4.get("total_false_accepts", 0) == 0:
        lines.append("_No false-accept witnesses (evaluator has zero false-accepts on the corpus)._")

    return "\n".join(lines)


def run_audit_for_shim(shim_key: str, top_k: int) -> tuple[str, str, str]:
    """Run an audit on the given shim and return (markdown, summary, json)."""
    if shim_key not in SHIM_REGISTRY:
        return f"Unknown shim: `{shim_key}`", "", ""

    evaluator = SHIM_REGISTRY[shim_key]()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        report = run_audit(evaluator, out_dir=out_dir, top_k=int(top_k))
        md = _format_report_markdown(report)
        ev = report.get("evaluator", {})
        s2 = report.get("step2_bsr", {})
        s3 = report.get("step3_bayes_floor", {})
        summary = (
            f"{ev.get('name', '?')} — π={report['step1_pi_class']['pi_class']} — "
            f"BSR={s2.get('bsr', 0):.4f} — ε*={s3.get('epsilon_star', 0):.3f}"
        )
        return md, summary, json.dumps(report, indent=2)


def list_shims_markdown() -> str:
    rows = ["| shim | family |", "|---|---|"]
    for key in SHIM_CHOICES:
        cls = SHIM_REGISTRY[key]
        try:
            family = getattr(cls, "meta", None).family if getattr(cls, "meta", None) else ""
        except Exception:
            family = ""
        rows.append(f"| `{key}` | {family} |")
    return "\n".join(rows)


def build_app() -> gr.Blocks:
    with gr.Blocks(title="CGA-Bench Audit") as app:
        gr.Markdown(
            "# CGA-Bench Evaluator Audit Harness\n"
            "Pick a registered evaluator shim, run the audit, and see which "
            "π-equivalence class it factors through, its Blind-Spot Rate, "
            "Bayes-error floor, and top-K false-accept witnesses. Built-in + "
            "external-benchmark shims are unified under `SHIM_REGISTRY`."
        )
        with gr.Tab("Run audit"):
            shim_dropdown = gr.Dropdown(
                choices=SHIM_CHOICES,
                value=DEFAULT_SHIM,
                label="Shim (evaluator to audit)",
            )
            topk_slider = gr.Slider(
                minimum=0, maximum=10, step=1, value=3, label="Top-K witnesses"
            )
            run_btn = gr.Button("Run audit", variant="primary")
            summary_out = gr.Textbox(label="Summary", interactive=False)
            md_out = gr.Markdown(label="Report")
            json_out = gr.Code(language="json", label="Raw report JSON")
            run_btn.click(
                run_audit_for_shim,
                inputs=[shim_dropdown, topk_slider],
                outputs=[md_out, summary_out, json_out],
            )
        with gr.Tab("Registry"):
            gr.Markdown(
                "Current `SHIM_REGISTRY` contents. Externally-registered "
                "benchmarks appear with the `ext_` prefix."
            )
            gr.Markdown(list_shims_markdown())
    return app


if __name__ == "__main__":
    app = build_app()
    app.launch(server_name="0.0.0.0", server_port=7860)
