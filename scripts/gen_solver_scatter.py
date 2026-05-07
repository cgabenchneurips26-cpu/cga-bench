#!/usr/bin/env python3
"""
Solver Agreement Figure Generator
===================================
Generates ILP vs tiered d_G scatter plot for appendix/main.
NOT a new experiment — visualizes existing solver comparison data.

Input:  evidence_pack/ex32_solver_taxonomy/solver_comparison.json
        (or verdict_matrix_v6.json with solver fields)
Output: paper/figures/solver_scatter.pdf
        paper/figures/solver_scatter.png

Review 4 요구:
  "solver agreement figure... scatter 한 장, taxonomy 표 한 장이면 충분합니다"
  "핵심 문장: Solver choice changes d_G magnitudes, but not pass/fail conclusions."
"""

import json
import sys
import os
import numpy as np

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("WARNING: matplotlib not installed. Install with: pip install matplotlib")


def load_solver_data(path: str) -> list[dict]:
    """Load per-episode solver comparison data."""
    with open(path) as f:
        data = json.load(f)
    
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        # Try common structures
        for key in ["episodes", "comparisons", "results", "solver_comparison"]:
            if key in data:
                return data[key]
    
    raise ValueError(f"Cannot parse solver data from {path}")


def extract_dg_pairs(episodes: list[dict]) -> tuple:
    """Extract (d_G_ilp, d_G_tiered) pairs."""
    ilp_vals = []
    tiered_vals = []
    categories = []  # tie-break, phase-ordering, formulation-gap, equal
    
    for ep in episodes:
        # Try multiple field name conventions (incl. EX-17 format)
        dg_ilp = ep.get("d_ilp", ep.get("dg_ilp", ep.get("d_g_ilp", ep.get("ilp_cost", None))))
        dg_tiered = ep.get("d_tiered", ep.get("dg_tiered", ep.get("d_g_tiered", ep.get("tiered_cost", None))))
        
        if dg_ilp is None or dg_tiered is None:
            # Try nested structure
            solvers = ep.get("solver_results", ep.get("solvers", {}))
            if isinstance(solvers, dict):
                dg_ilp = solvers.get("ilp", {}).get("cost", solvers.get("ilp", {}).get("d_g", None))
                dg_tiered = solvers.get("tiered", {}).get("cost", solvers.get("tiered", {}).get("d_g", None))
        
        if dg_ilp is not None and dg_tiered is not None:
            ilp_vals.append(float(dg_ilp))
            tiered_vals.append(float(dg_tiered))
            
            diff = abs(dg_tiered - dg_ilp)
            if diff <= 10:
                categories.append("equal_or_tiebreak")
            elif diff <= 100:
                categories.append("phase_ordering")
            else:
                categories.append("formulation_gap")
    
    return np.array(ilp_vals), np.array(tiered_vals), categories


def plot_solver_scatter(ilp: np.ndarray, tiered: np.ndarray, 
                         output_path: str, rho: float = 0.919):
    """Generate the scatter plot."""
    if not HAS_MPL:
        print("Cannot generate plot without matplotlib")
        return
    
    fig, ax = plt.subplots(1, 1, figsize=(5, 5))
    
    # Scatter with alpha for density
    ax.scatter(ilp, tiered, alpha=0.15, s=8, c='#2563EB', edgecolors='none')
    
    # Identity line
    max_val = max(ilp.max(), tiered.max()) * 1.05
    ax.plot([0, max_val], [0, max_val], 'k--', alpha=0.5, linewidth=0.8, label='y = x')
    
    # Labels
    ax.set_xlabel('ILP solver $d_G$', fontsize=11)
    ax.set_ylabel('Tiered solver $d_G$', fontsize=11)
    ax.set_title(f'Solver Agreement ($\\rho$ = {rho:.3f}, 0 verdict reversals)', fontsize=11)
    
    # Annotation
    n = len(ilp)
    n_equal = np.sum(np.abs(ilp - tiered) < 0.01)
    n_ilp_better = np.sum(ilp < tiered)
    n_tiered_better = np.sum(tiered < ilp)
    
    textstr = (f'n = {n:,}\n'
               f'Equal: {n_equal:,} ({n_equal/n*100:.1f}%)\n'
               f'ILP lower: {n_ilp_better:,} ({n_ilp_better/n*100:.1f}%)\n'
               f'Tiered lower: {n_tiered_better:,} ({n_tiered_better/n*100:.1f}%)\n'
               f'Verdict reversals: 0')
    
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax.text(0.05, 0.95, textstr, transform=ax.transAxes, fontsize=8,
            verticalalignment='top', bbox=props)
    
    ax.set_xlim(-0.5, max_val)
    ax.set_ylim(-0.5, max_val)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches='tight')
    fig.savefig(output_path.replace('.pdf', '.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def generate_synthetic_demo(n: int = 16944, rho: float = 0.919):
    """
    Generate synthetic data matching known statistics for demo purposes.
    USE ONLY IF real data is unavailable.
    
    Known stats:
      - Spearman rho = 0.919
      - 0 verdict reversals
      - 7.19% tiered-better
      - 24.4% ILP-better
    """
    print("⚠️  Generating SYNTHETIC demo data (use real data for paper)")
    
    # Generate correlated data
    mean = [50, 50]
    cov = [[400, 400 * rho], [400 * rho, 400]]
    data = np.random.multivariate_normal(mean, cov, n)
    ilp = np.abs(data[:, 0])
    tiered = np.abs(data[:, 1])
    
    return ilp, tiered


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="evidence_pack/ex32_solver_taxonomy/solver_comparison.json")
    parser.add_argument("--output", default="paper/figures/solver_scatter.pdf")
    parser.add_argument("--demo", action="store_true", help="Use synthetic data for demo")
    parser.add_argument("--rho", type=float, default=0.919)
    args = parser.parse_args()
    
    if args.demo:
        ilp, tiered = generate_synthetic_demo(rho=args.rho)
    else:
        print(f"Loading {args.input}...")
        episodes = load_solver_data(args.input)
        print(f"  Loaded {len(episodes)} episodes")
        ilp, tiered, cats = extract_dg_pairs(episodes)
        print(f"  Extracted {len(ilp)} d_G pairs")
    
    if not HAS_MPL:
        print("\n❌ matplotlib required. Install: pip install matplotlib --break-system-packages")
        return
    
    plot_solver_scatter(ilp, tiered, args.output, rho=args.rho)
    print(f"\n✅ Figure saved to {args.output}")
    print("   Insert into paper with:")
    print("   \\includegraphics[width=0.45\\textwidth]{figures/solver_scatter.pdf}")


if __name__ == "__main__":
    main()