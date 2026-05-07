"""Severity-conditional FA macros on Phase B (76,464 episodes).

Mirrors exp_e24_fa_severity.py but reads from results/full_v6b and
verdict_matrix_v6_full.json. Computes:
  - Consensus FA severity buckets (Critical/High/Medium/Low)
  - Strict 3-way FA severity (ASC ∩ PAF ∩ CwT)
  - Median violations per FA episode

Severity classification:
  critical: any COMMISSION (FORBIDDEN) violation
  high:     any TIMING margin > 60 min
  medium:   TIMING margin 5-60 min (or unknown margin)
  low:      SEQUENCE only

Output:
  evidence_pack/analysis/v6_full_severity.json
  evidence_pack/tables/v6_full_severity.tex   (\\vSixFull*Critical/High/Medium/Low macros)
"""

from __future__ import annotations

import argparse
from collections import Counter
import glob
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
HARD_VIOL_TYPES = frozenset({"commission", "timing", "sequence"})


def classify_severity(ep: dict) -> str:
    """Worst-violation severity tier."""
    has_commission = False
    max_timing_margin = -1.0
    has_timing = False
    has_sequence = False
    for v in ep.get("violation_events", []):
        vt = str(v.get("violation_type", v.get("type", ""))).lower().strip()
        if "commission" in vt:
            has_commission = True
        elif "timing" in vt:
            has_timing = True
            deadline = v.get("expected_deadline")
            actual = v.get("actual_time") or v.get("timestamp_minutes")
            if deadline is not None and actual is not None:
                try:
                    margin = float(actual) - float(deadline)
                    if margin > max_timing_margin:
                        max_timing_margin = margin
                except (TypeError, ValueError):
                    pass
        elif "sequence" in vt:
            has_sequence = True
    if has_commission:
        return "critical"
    if has_timing:
        return "high" if max_timing_margin > 60 else "medium"
    if has_sequence:
        return "low"
    return "low"


def load_episodes_with_severity(phase_b_dir: str) -> dict:
    """Index episodes by (sid, ri, model_dir) → {severity, n_viols_hard}."""
    out = {}
    for m in sorted(os.listdir(phase_b_dir)):
        md = os.path.join(phase_b_dir, m)
        if not os.path.isdir(md) or m.startswith("_"):
            continue
        for f in glob.glob(os.path.join(md, "*.json")):
            base = os.path.basename(f)
            if base.startswith(("checkpoint", ".claim", "model_summary", "log_")):
                continue
            try:
                d = json.load(open(f))
            except Exception:
                continue
            sid = d.get("scenario_id")
            ri = d.get("run_index")
            if sid is None or ri is None:
                continue
            severity = classify_severity(d)
            n_hard = sum(
                1
                for v in d.get("violation_events", [])
                if any(t in str(v.get("violation_type", v.get("type", ""))).lower() for t in HARD_VIOL_TYPES)
            )
            out[(sid, ri, m)] = {"severity": severity, "n_hard": n_hard}
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vmatrix", default="evidence_pack/analysis/verdict_matrix_v6_full.json")
    p.add_argument("--vmatrix-typed", default="evidence_pack/analysis/verdict_matrix_v6_full_typed.json")
    p.add_argument("--phase-b-dir", default="results/full_v6b")
    p.add_argument("--out-json", default="evidence_pack/analysis/v6_full_severity.json")
    p.add_argument("--out-tex", default="evidence_pack/tables/v6_full_severity.tex")
    args = p.parse_args()

    print(f"[{time.strftime('%H:%M:%S')}] loading Phase B episodes for severity...")
    sev_idx = load_episodes_with_severity(args.phase_b_dir)
    print(f"  indexed: {len(sev_idx)}")

    print("loading verdict matrices...")
    pe = json.load(open(args.vmatrix))["per_episode"]
    pet = json.load(open(args.vmatrix_typed))["per_episode"]
    print(f"  Phase B orig: {len(pe)}, typed: {len(pet)}")

    def analyze(pe_in, c2_field, label):
        n = len(pe_in)
        # Consensus FA = ASC ∩ CwT pass + TCC fail (paper definition)
        consensus_fa = []
        # Strict 3-way FA = ASC ∩ PAF ∩ CwT pass + TCC fail
        strict_fa = []
        for ep in pe_in:
            key = (ep["scenario_id"], ep["run_index"], ep["model_dir"])
            sev_info = sev_idx.get(key)
            if sev_info is None:
                continue
            sev = sev_info["severity"]
            n_hard = sev_info["n_hard"]
            if ep["dxem"] and ep["ac_proxy"] and ep[c2_field] and ep["v4_hard"]:
                consensus_fa.append({"severity": sev, "n_hard": n_hard})
            if ep["ac_proxy"] and ep["mab_proxy"] and ep[c2_field] and ep["v4_hard"]:
                strict_fa.append({"severity": sev, "n_hard": n_hard})

        consensus_sev = Counter(x["severity"] for x in consensus_fa)
        strict_sev = Counter(x["severity"] for x in strict_fa)
        consensus_med = sorted(x["n_hard"] for x in consensus_fa)
        strict_med = sorted(x["n_hard"] for x in strict_fa)
        c_med = consensus_med[len(consensus_med) // 2] if consensus_med else 0
        s_med = strict_med[len(strict_med) // 2] if strict_med else 0
        cn = len(consensus_fa)
        sn = len(strict_fa)

        print(f"\n=== {label} ===")
        print(f"  Consensus FA (TOM∩ASC∩CwT, fail TCC): n={cn}")
        for k in ("critical", "high", "medium", "low"):
            v = consensus_sev.get(k, 0)
            print(f"    {k}: {v} ({100 * v / max(cn, 1):.2f}%)")
        print(f"  Median hard viols/consensus FA: {c_med}")
        print(f"  Strict 3-way FA: n={sn}")
        for k in ("critical", "high", "medium", "low"):
            v = strict_sev.get(k, 0)
            print(f"    {k}: {v} ({100 * v / max(sn, 1):.2f}%)")
        print(f"  Median hard viols/strict FA: {s_med}")

        return {
            "n_episodes": n,
            "consensus_fa": {
                "n": cn,
                "by_severity": dict(consensus_sev),
                "by_severity_pct": {
                    k: round(100 * consensus_sev.get(k, 0) / max(cn, 1), 2)
                    for k in ("critical", "high", "medium", "low")
                },
                "median_n_hard": c_med,
            },
            "strict_3way_fa": {
                "n": sn,
                "by_severity": dict(strict_sev),
                "by_severity_pct": {
                    k: round(100 * strict_sev.get(k, 0) / max(sn, 1), 2) for k in ("critical", "high", "medium", "low")
                },
                "median_n_hard": s_med,
            },
        }

    out_orig = analyze(pe, "c2_pass", "Phase B original")
    out_typed = analyze(pet, "c2_pass_typed", "Phase B typed")

    # Save
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(
        json.dumps({"phase_b_original": out_orig, "phase_b_typed": out_typed}, indent=2, default=str)
    )
    print(f"\nSaved → {args.out_json}")

    # LaTeX macros
    o = out_orig["consensus_fa"]
    s = out_orig["strict_3way_fa"]
    t = out_typed["consensus_fa"]
    ts = out_typed["strict_3way_fa"]
    L = [
        r"% v6 Full Phase B severity macros — auto-generated from recompute_v6_full_severity.py",
        "",
        r"% Consensus FA (TOM∩ASC∩CwT, fail TCC) — paper's hero severity buckets",
        rf"\providecommand{{\vSixFullConsensusFACritical}}{{{o['by_severity'].get('critical', 0)}}}",
        rf"\providecommand{{\vSixFullConsensusFACriticalPct}}{{{o['by_severity_pct']['critical']:.2f}}}",
        rf"\providecommand{{\vSixFullConsensusFAHigh}}{{{o['by_severity'].get('high', 0)}}}",
        rf"\providecommand{{\vSixFullConsensusFAMedium}}{{{o['by_severity'].get('medium', 0)}}}",
        rf"\providecommand{{\vSixFullConsensusFALow}}{{{o['by_severity'].get('low', 0)}}}",
        rf"\providecommand{{\vSixFullConsensusFAMedianViols}}{{{o['median_n_hard']}}}",
        "",
        r"% Strict 3-way FA (ASC∩PAF∩CwT, fail TCC)",
        rf"\providecommand{{\vSixFullStrictFACritical}}{{{s['by_severity'].get('critical', 0)}}}",
        rf"\providecommand{{\vSixFullStrictFACriticalPct}}{{{s['by_severity_pct']['critical']:.2f}}}",
        rf"\providecommand{{\vSixFullStrictFAHigh}}{{{s['by_severity'].get('high', 0)}}}",
        rf"\providecommand{{\vSixFullStrictFAMedium}}{{{s['by_severity'].get('medium', 0)}}}",
        rf"\providecommand{{\vSixFullStrictFALow}}{{{s['by_severity'].get('low', 0)}}}",
        rf"\providecommand{{\vSixFullStrictFAMedianViols}}{{{s['median_n_hard']}}}",
        "",
        r"% Phase B typed",
        rf"\providecommand{{\vSixFullTypedConsensusFACritical}}{{{t['by_severity'].get('critical', 0)}}}",
        rf"\providecommand{{\vSixFullTypedConsensusFACriticalPct}}{{{t['by_severity_pct']['critical']:.2f}}}",
        rf"\providecommand{{\vSixFullTypedStrictFACritical}}{{{ts['by_severity'].get('critical', 0)}}}",
        rf"\providecommand{{\vSixFullTypedStrictFACriticalPct}}{{{ts['by_severity_pct']['critical']:.2f}}}",
    ]
    Path(args.out_tex).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_tex).write_text("\n".join(L) + "\n")
    print(f"Saved → {args.out_tex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
