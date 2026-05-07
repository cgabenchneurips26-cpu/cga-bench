"""Generate paper/appendix_figures.tex from evidence_pack/figures/ contents."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

FIGURES_DIR = Path(__file__).parent.parent / "evidence_pack" / "figures"
OUTPUT_FILE = Path(__file__).parent.parent / "paper" / "appendix_figures.tex"

# Map filename prefixes to section titles
PREFIX_SECTIONS: dict[str, str] = {
    "exp_a": "Experiment A: Scenario Equivalence",
    "exp_b": "Experiment B: Derivation Ablation",
    "exp_c": "Experiment C: Generalizability",
    "exp_d": "Experiment D: Disagreement Quantification",
    "exp_e": "Experiment E: Difficulty Equivalence",
    "exp_f": "Experiment F: Evidence Pack",
    "ws4": "Run Variance Analysis",
    "ws5": "Contamination Probe",
    "ws6": "Error Taxonomy",
    "bsr": "BSR Perturbation Analysis",
    "activity": "Activity Analysis",
}


def humanize_filename(stem: str) -> str:
    """Convert filename stem to a human-readable caption."""
    # Remove common prefixes
    for prefix in PREFIX_SECTIONS:
        if stem.startswith(prefix + "_"):
            stem = stem[len(prefix) + 1 :]
            break

    return stem.replace("_", " ").title()


def get_section(filename: str) -> str:
    """Determine which section a figure belongs to."""
    for prefix, section in PREFIX_SECTIONS.items():
        if filename.startswith(prefix):
            return section
    return "Miscellaneous"


def main() -> None:
    if not FIGURES_DIR.exists():
        print(f"No figures directory at {FIGURES_DIR}")
        return

    figures = sorted(p for p in FIGURES_DIR.iterdir() if p.suffix.lower() in (".png", ".pdf", ".jpg", ".jpeg"))

    if not figures:
        print("No figures found.")
        return

    # Group by section
    sections: dict[str, list[Path]] = {}
    for fig in figures:
        section = get_section(fig.stem)
        sections.setdefault(section, []).append(fig)

    lines: list[str] = [
        "% Auto-generated from evidence_pack/figures/",
        "% Regenerate with: python scripts/generate_appendix_figures_tex.py",
        "",
    ]

    for section_name, section_figs in sections.items():
        lines.append(f"\\subsection{{{section_name}}}")
        lines.append("")

        for fig in section_figs:
            rel_path = f"evidence_pack/figures/{fig.name}"
            caption = humanize_filename(fig.stem)
            label = f"fig:app_{fig.stem}"

            lines.append("\\begin{figure}[h]")
            lines.append("\\centering")
            lines.append(f"\\includegraphics[width=0.9\\textwidth]{{{rel_path}}}")
            lines.append(f"\\caption{{{caption}}}")
            lines.append(f"\\label{{{label}}}")
            lines.append("\\end{figure}")
            lines.append("")

    OUTPUT_FILE.write_text("\n".join(lines))
    print(f"Generated {OUTPUT_FILE} with {len(figures)} figures in {len(sections)} sections.")


if __name__ == "__main__":
    main()
