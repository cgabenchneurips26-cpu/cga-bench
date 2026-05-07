r"""Engine-vs-manual constraint match audit per type.

Compares constraints derived from CPG YAML graphs (engine) against
constraints explicitly authored in scenario YAMLs (manual).

For each constraint type {FORBIDDEN, REQUIRED, BEFORE, WITHIN}:
  Engine set: union over CPG YAMLs (cpg_model/graphs/, /auto/, /auto_v2/)
              extracts forbidden_actions, mandatory_actions, sequence rules,
              and timing deadlines from each node.
  Manual set: union over configs/scenarios/*.yaml constraint blocks
              (forbidden_actions, expected_actions, etc).
  Precision = |engine ∩ manual| / |engine|
  (per main_final_v17:337: "manual-overlap fraction" — agreement with manual
   practice rather than precision against held-out truth).

Output:
  evidence_pack/analysis/constraint_precision.json
  evidence_pack/tables/constraint_precision.tex   (\precForbidden, etc.)
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import glob
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def normalize(aid: str) -> str:
    return aid.strip().lower().replace("-", "_").replace(" ", "_")


def extract_engine_constraints(cpg_root: str) -> dict[str, set[tuple]]:
    """Extract per-type constraint sets from CPG graph YAMLs.

    Constraint identifier scheme:
      FORBIDDEN: (cpg_id, "FORBIDDEN", normalized_action)
      REQUIRED:  (cpg_id, "REQUIRED",  normalized_action)
      BEFORE:    (cpg_id, "BEFORE",    normalized_pre, normalized_post)
      WITHIN:    (cpg_id, "WITHIN",    normalized_action, deadline_minutes)
    """
    constraints: dict[str, set] = defaultdict(set)
    yaml_files = []
    for sub in ("graphs", "graphs/auto", "graphs/auto_v2"):
        d = Path(cpg_root) / sub
        if d.exists():
            yaml_files.extend(sorted(d.glob("*.yaml")))

    for yf in yaml_files:
        try:
            data = yaml.safe_load(yf.read_text())
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        cpg_id = data.get("graph_id") or yf.stem

        # Iterate nodes
        nodes = data.get("nodes") or {}
        if isinstance(nodes, dict):
            node_iter = nodes.items()
        elif isinstance(nodes, list):
            node_iter = ((n.get("id") or n.get("node_id") or "", n) for n in nodes)
        else:
            continue

        for node_id, node in node_iter:
            if not isinstance(node, dict):
                continue
            for fa in node.get("forbidden_actions") or []:
                aid = fa if isinstance(fa, str) else (fa.get("action_id") if isinstance(fa, dict) else "")
                if aid:
                    constraints["FORBIDDEN"].add((cpg_id, "FORBIDDEN", normalize(aid)))
            for ma in node.get("mandatory_actions") or node.get("expected_actions") or []:
                if isinstance(ma, dict):
                    aid = ma.get("action_id", "")
                    deadline = ma.get("deadline_minutes")
                else:
                    aid, deadline = str(ma), None
                if aid:
                    constraints["REQUIRED"].add((cpg_id, "REQUIRED", normalize(aid)))
                    if deadline is not None:
                        try:
                            constraints["WITHIN"].add((cpg_id, "WITHIN", normalize(aid), float(deadline)))
                        except (TypeError, ValueError):
                            pass
            for seq in node.get("sequence_constraints") or []:
                if isinstance(seq, dict):
                    pre = seq.get("before") or seq.get("pre")
                    post = seq.get("after") or seq.get("post")
                    if pre and post:
                        constraints["BEFORE"].add((cpg_id, "BEFORE", normalize(pre), normalize(post)))
            for d in node.get("deadlines") or []:
                if isinstance(d, dict):
                    aid = d.get("action_id", "")
                    dl = d.get("deadline_minutes")
                    if aid and dl is not None:
                        try:
                            constraints["WITHIN"].add((cpg_id, "WITHIN", normalize(aid), float(dl)))
                        except (TypeError, ValueError):
                            pass
        # graph-level forbidden / required
        for fa in data.get("forbidden_actions") or []:
            aid = fa if isinstance(fa, str) else (fa.get("action_id") if isinstance(fa, dict) else "")
            if aid:
                constraints["FORBIDDEN"].add((cpg_id, "FORBIDDEN", normalize(aid)))

    return constraints


def extract_manual_constraints(scenarios_root: str) -> dict[str, set[tuple]]:
    """Extract per-type manual constraint sets from scenario YAMLs.

    Maps scenario.guideline_graph → cpg_id when available; falls back to
    filename-derived id.
    """
    constraints: dict[str, set] = defaultdict(set)
    yaml_files = (
        sorted(glob.glob(f"{scenarios_root}/*.yaml"))
        + sorted(glob.glob(f"{scenarios_root}/auto/*.yaml"))
        + sorted(glob.glob(f"{scenarios_root}/auto_v2/*.yaml"))
    )

    for yf in yaml_files:
        try:
            data = yaml.safe_load(open(yf))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        scenarios = data.get("scenarios") or {}

        # Normalize: scenarios may be dict (sid → sc_dict) or list of sc_dicts
        if isinstance(scenarios, dict):
            sc_iter = scenarios.values()
        elif isinstance(scenarios, list):
            sc_iter = scenarios
        else:
            continue

        for sc in sc_iter:
            if not isinstance(sc, dict):
                continue
            cpg_id = sc.get("guideline_graph") or sc.get("cpg_id") or Path(yf).stem.replace("_scenarios", "")
            for fa in sc.get("forbidden_actions") or []:
                aid = fa if isinstance(fa, str) else (fa.get("action_id") if isinstance(fa, dict) else "")
                if aid:
                    constraints["FORBIDDEN"].add((cpg_id, "FORBIDDEN", normalize(aid)))
            for ea in sc.get("expected_actions") or []:
                if isinstance(ea, dict):
                    aid = ea.get("action_id", "")
                    deadline = ea.get("deadline_minutes")
                else:
                    aid, deadline = str(ea), None
                if aid:
                    constraints["REQUIRED"].add((cpg_id, "REQUIRED", normalize(aid)))
                    if deadline is not None:
                        try:
                            constraints["WITHIN"].add((cpg_id, "WITHIN", normalize(aid), float(deadline)))
                        except (TypeError, ValueError):
                            pass
            for seq in sc.get("sequence_constraints") or []:
                if isinstance(seq, dict):
                    pre = seq.get("before") or seq.get("pre")
                    post = seq.get("after") or seq.get("post")
                    if pre and post:
                        constraints["BEFORE"].add((cpg_id, "BEFORE", normalize(pre), normalize(post)))
    return constraints


def compute_overlap(engine: dict, manual: dict) -> dict:
    """Per-type Jaccard, precision (engine ∩ manual / engine), recall."""
    out = {}
    all_engine = set()
    all_manual = set()
    for t in ("FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN"):
        e = engine.get(t, set())
        m = manual.get(t, set())
        # For precision/recall, ignore the cpg_id prefix in WITHIN's deadline
        # (compare action+type only) since manual specifies different deadlines
        e_keys = {(c[1], c[2]) for c in e}  # (type, action) ignoring cpg+deadline
        m_keys = {(c[1], c[2]) for c in m}
        inter = e_keys & m_keys
        prec = len(inter) / len(e_keys) if e_keys else 0.0
        rec = len(inter) / len(m_keys) if m_keys else 0.0
        jacc = len(inter) / len(e_keys | m_keys) if (e_keys | m_keys) else 0.0
        out[t] = {
            "n_engine": len(e_keys),
            "n_manual": len(m_keys),
            "n_intersection": len(inter),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "jaccard": round(jacc, 4),
        }
        all_engine |= e_keys
        all_manual |= m_keys

    # All combined
    inter_all = all_engine & all_manual
    out["ALL"] = {
        "n_engine": len(all_engine),
        "n_manual": len(all_manual),
        "n_intersection": len(inter_all),
        "precision": round(len(inter_all) / len(all_engine), 4) if all_engine else 0.0,
        "recall": round(len(inter_all) / len(all_manual), 4) if all_manual else 0.0,
        "jaccard": round(len(inter_all) / len(all_engine | all_manual), 4) if (all_engine | all_manual) else 0.0,
    }
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cpg-root", default="cpg_model")
    p.add_argument("--scenarios-root", default="configs/scenarios")
    p.add_argument("--out-json", default="evidence_pack/analysis/constraint_precision.json")
    p.add_argument("--out-tex", default="evidence_pack/tables/constraint_precision.tex")
    args = p.parse_args()

    print(f"Extracting engine constraints from {args.cpg_root}...")
    engine = extract_engine_constraints(args.cpg_root)
    for t in ("FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN"):
        print(f"  {t}: {len(engine.get(t, set()))}")

    print(f"\nExtracting manual constraints from {args.scenarios_root}...")
    manual = extract_manual_constraints(args.scenarios_root)
    for t in ("FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN"):
        print(f"  {t}: {len(manual.get(t, set()))}")

    print("\nComputing per-type precision/recall/Jaccard...")
    overlap = compute_overlap(engine, manual)
    for t, stats in overlap.items():
        print(
            f"  {t}: prec={stats['precision'] * 100:.2f}%, rec={stats['recall'] * 100:.2f}%, "
            f"jacc={stats['jaccard'] * 100:.2f}% (engine={stats['n_engine']}, manual={stats['n_manual']}, ∩={stats['n_intersection']})"
        )

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(overlap, indent=2))
    print(f"\nSaved → {args.out_json}")

    def pct(x):
        return f"{x * 100:.2f}\\%"

    L = [
        r"% Constraint-type precision (engine vs manual) — auto-generated by audit_constraint_precision.py",
        "",
        rf"\renewcommand{{\precForbidden}}{{{pct(overlap['FORBIDDEN']['precision'])}}}",
        rf"\renewcommand{{\precRequired}}{{{pct(overlap['REQUIRED']['precision'])}}}",
        rf"\renewcommand{{\precBefore}}{{{pct(overlap['BEFORE']['precision'])}}}",
        rf"\renewcommand{{\precWithin}}{{{pct(overlap['WITHIN']['precision'])}}}",
        rf"\renewcommand{{\precAll}}{{{pct(overlap['ALL']['precision'])}}}",
        "",
        r"% Recall variants",
        rf"\providecommand{{\recForbidden}}{{{pct(overlap['FORBIDDEN']['recall'])}}}",
        rf"\providecommand{{\recRequired}}{{{pct(overlap['REQUIRED']['recall'])}}}",
        rf"\providecommand{{\recBefore}}{{{pct(overlap['BEFORE']['recall'])}}}",
        rf"\providecommand{{\recWithin}}{{{pct(overlap['WITHIN']['recall'])}}}",
        rf"\providecommand{{\recAll}}{{{pct(overlap['ALL']['recall'])}}}",
        "",
        r"% Engine and manual counts (used in appendix table)",
        rf"\providecommand{{\nEngineForbidden}}{{{overlap['FORBIDDEN']['n_engine']}}}",
        rf"\providecommand{{\nEngineRequired}}{{{overlap['REQUIRED']['n_engine']}}}",
        rf"\providecommand{{\nEngineBefore}}{{{overlap['BEFORE']['n_engine']}}}",
        rf"\providecommand{{\nEngineWithin}}{{{overlap['WITHIN']['n_engine']}}}",
        rf"\providecommand{{\nEngineAll}}{{{overlap['ALL']['n_engine']}}}",
    ]
    Path(args.out_tex).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_tex).write_text("\n".join(L) + "\n")
    print(f"Saved → {args.out_tex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
