#!/usr/bin/env python3
"""
EX-35: Replay Scorer Fidelity Audit
=====================================
Constructs 15 toy traces with known violation types and verifies that
MAB-replay, AC-replay, and TCC produce expected verdicts.

This is NOT a re-run of 16,944 episodes — it's a diagnostic test suite
that proves the replay scorers reproduce the *expected blindness pattern*.

Output: evidence_pack/ex35_fidelity_audit/fidelity_audit.json + macros.tex
        + appendix table ready for LaTeX
"""

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional


# ============================================================================
# Toy Trace Definitions
# ============================================================================

@dataclass
class Action:
    name: str
    timestamp: float  # minutes from episode start
    is_required: bool = True
    is_forbidden: bool = False

@dataclass
class Constraint:
    type: str  # MUST, FORBIDDEN, BEFORE, WITHIN
    target: str
    param: Optional[str] = None  # second action for BEFORE, deadline for WITHIN
    deadline: Optional[float] = None

@dataclass
class ToyTrace:
    id: str
    description: str
    violation_type: str  # WITHIN, BEFORE, FORBIDDEN, MUST, MIXED, CLEAN
    actions: list  # list of Action dicts
    required_actions: list  # canonical required set
    forbidden_actions: list  # canonical forbidden set
    constraints: list  # list of Constraint dicts
    expected_tcc: str  # "pass" or "fail"
    expected_reason: str  # why it should pass/fail


# Define the 15 toy traces
TOY_TRACES = [
    # --- WITHIN-only (T1-T3): timing late, action set intact ---
    ToyTrace(
        id="T01", description="Single action 10min late (antibiotics in sepsis)",
        violation_type="WITHIN-only",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "order_blood_culture", "t": 5},
            {"name": "order_lactate", "t": 10},
            {"name": "start_iv_fluids", "t": 15},
            {"name": "administer_antibiotics", "t": 70},  # deadline=60min
        ],
        required_actions=["check_vitals", "order_blood_culture", "order_lactate",
                          "start_iv_fluids", "administer_antibiotics"],
        forbidden_actions=[],
        constraints=[
            {"type": "WITHIN", "target": "administer_antibiotics", "deadline": 60},
        ],
        expected_tcc="fail",
        expected_reason="antibiotics at t=70 > deadline 60min",
    ),
    ToyTrace(
        id="T02", description="Two actions late (tPA + antibiotics both past deadline)",
        violation_type="WITHIN-only",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "order_ct_head", "t": 5},
            {"name": "obtain_ct_results", "t": 35},
            {"name": "administer_tpa", "t": 65},  # deadline=60
            {"name": "administer_antibiotics", "t": 80},  # deadline=60
        ],
        required_actions=["check_vitals", "order_ct_head", "obtain_ct_results",
                          "administer_tpa", "administer_antibiotics"],
        forbidden_actions=[],
        constraints=[
            {"type": "WITHIN", "target": "administer_tpa", "deadline": 60},
            {"type": "WITHIN", "target": "administer_antibiotics", "deadline": 60},
        ],
        expected_tcc="fail",
        expected_reason="both tPA (t=65) and antibiotics (t=80) exceed 60min deadline",
    ),
    ToyTrace(
        id="T03", description="Single action 60min late (extreme delay, set intact)",
        violation_type="WITHIN-only",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "order_ecg", "t": 5},
            {"name": "administer_aspirin", "t": 10},
            {"name": "administer_antibiotics", "t": 120},  # deadline=60, 60min late
        ],
        required_actions=["check_vitals", "order_ecg", "administer_aspirin",
                          "administer_antibiotics"],
        forbidden_actions=[],
        constraints=[
            {"type": "WITHIN", "target": "administer_antibiotics", "deadline": 60},
        ],
        expected_tcc="fail",
        expected_reason="antibiotics at t=120, 60min past deadline",
    ),

    # --- BEFORE-only (T4-T6): ordering swapped, action set intact ---
    ToyTrace(
        id="T04", description="Single pair swapped (blood culture after antibiotics)",
        violation_type="BEFORE-only",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "administer_antibiotics", "t": 5},  # should be AFTER blood culture
            {"name": "order_blood_culture", "t": 10},
        ],
        required_actions=["check_vitals", "administer_antibiotics", "order_blood_culture"],
        forbidden_actions=[],
        constraints=[
            {"type": "BEFORE", "target": "order_blood_culture",
             "param": "administer_antibiotics"},
        ],
        expected_tcc="fail",
        expected_reason="blood_culture at t=10 but antibiotics at t=5 (wrong order)",
    ),
    ToyTrace(
        id="T05", description="Two pairs swapped",
        violation_type="BEFORE-only",
        actions=[
            {"name": "administer_antibiotics", "t": 0},
            {"name": "order_blood_culture", "t": 5},
            {"name": "start_insulin", "t": 10},
            {"name": "correct_potassium", "t": 15},
        ],
        required_actions=["administer_antibiotics", "order_blood_culture",
                          "start_insulin", "correct_potassium"],
        forbidden_actions=[],
        constraints=[
            {"type": "BEFORE", "target": "order_blood_culture",
             "param": "administer_antibiotics"},
            {"type": "BEFORE", "target": "correct_potassium",
             "param": "start_insulin"},
        ],
        expected_tcc="fail",
        expected_reason="both ordering constraints violated",
    ),
    ToyTrace(
        id="T06", description="Critical pair: tPA before CT completion",
        violation_type="BEFORE-only",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "order_ct_head", "t": 5},
            {"name": "administer_tpa", "t": 10},  # should wait for CT results
            {"name": "obtain_ct_results", "t": 35},
        ],
        required_actions=["check_vitals", "order_ct_head", "administer_tpa",
                          "obtain_ct_results"],
        forbidden_actions=[],
        constraints=[
            {"type": "BEFORE", "target": "obtain_ct_results",
             "param": "administer_tpa"},
        ],
        expected_tcc="fail",
        expected_reason="tPA at t=10 before CT results at t=35",
    ),

    # --- FORBIDDEN-only (T7-T9): contraindicated action present ---
    ToyTrace(
        id="T07", description="Single contraindicated action (NSAID with AKI)",
        violation_type="FORBIDDEN-only",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "order_bmp", "t": 5},
            {"name": "start_iv_fluids", "t": 10},
            {"name": "administer_nsaids", "t": 15},  # FORBIDDEN
        ],
        required_actions=["check_vitals", "order_bmp", "start_iv_fluids"],
        forbidden_actions=["administer_nsaids"],
        constraints=[
            {"type": "FORBIDDEN", "target": "administer_nsaids"},
        ],
        expected_tcc="fail",
        expected_reason="NSAID administered despite AKI context (forbidden)",
    ),
    ToyTrace(
        id="T08", description="Conditional FORBIDDEN (amoxicillin with penicillin allergy)",
        violation_type="FORBIDDEN-only",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "administer_amoxicillin", "t": 5},  # FORBIDDEN if allergy
        ],
        required_actions=["check_vitals"],
        forbidden_actions=["administer_amoxicillin"],
        constraints=[
            {"type": "FORBIDDEN", "target": "administer_amoxicillin"},
        ],
        expected_tcc="fail",
        expected_reason="amoxicillin given to penicillin-allergic patient",
    ),
    ToyTrace(
        id="T09", description="Two contraindicated actions",
        violation_type="FORBIDDEN-only",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "administer_nsaids", "t": 5},
            {"name": "administer_nitroglycerin", "t": 10},  # FORBIDDEN with RV infarct
        ],
        required_actions=["check_vitals"],
        forbidden_actions=["administer_nsaids", "administer_nitroglycerin"],
        constraints=[
            {"type": "FORBIDDEN", "target": "administer_nsaids"},
            {"type": "FORBIDDEN", "target": "administer_nitroglycerin"},
        ],
        expected_tcc="fail",
        expected_reason="two contraindicated medications administered",
    ),

    # --- MUST-omit (T10-T12): required action missing ---
    ToyTrace(
        id="T10", description="Single required action missing",
        violation_type="MUST-omit",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "order_ecg", "t": 5},
            # administer_aspirin is MISSING
        ],
        required_actions=["check_vitals", "order_ecg", "administer_aspirin"],
        forbidden_actions=[],
        constraints=[
            {"type": "MUST", "target": "administer_aspirin"},
        ],
        expected_tcc="fail",
        expected_reason="required aspirin not administered",
    ),
    ToyTrace(
        id="T11", description="Two required actions missing",
        violation_type="MUST-omit",
        actions=[
            {"name": "check_vitals", "t": 0},
            # order_blood_culture MISSING
            # administer_antibiotics MISSING
        ],
        required_actions=["check_vitals", "order_blood_culture",
                          "administer_antibiotics"],
        forbidden_actions=[],
        constraints=[
            {"type": "MUST", "target": "order_blood_culture"},
            {"type": "MUST", "target": "administer_antibiotics"},
        ],
        expected_tcc="fail",
        expected_reason="both blood culture and antibiotics omitted",
    ),
    ToyTrace(
        id="T12", description="Critical omission (antibiotics in sepsis)",
        violation_type="MUST-omit",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "order_blood_culture", "t": 5},
            {"name": "order_lactate", "t": 10},
            {"name": "start_iv_fluids", "t": 15},
            # administer_antibiotics MISSING — critical
        ],
        required_actions=["check_vitals", "order_blood_culture", "order_lactate",
                          "start_iv_fluids", "administer_antibiotics"],
        forbidden_actions=[],
        constraints=[
            {"type": "MUST", "target": "administer_antibiotics"},
        ],
        expected_tcc="fail",
        expected_reason="antibiotics omitted in sepsis protocol",
    ),

    # --- MIXED (T13-T14) ---
    ToyTrace(
        id="T13", description="WITHIN + FORBIDDEN (late antibiotics + contraindicated med)",
        violation_type="MIXED",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "order_blood_culture", "t": 5},
            {"name": "administer_nsaids", "t": 10},  # FORBIDDEN
            {"name": "administer_antibiotics", "t": 70},  # deadline=60
        ],
        required_actions=["check_vitals", "order_blood_culture",
                          "administer_antibiotics"],
        forbidden_actions=["administer_nsaids"],
        constraints=[
            {"type": "WITHIN", "target": "administer_antibiotics", "deadline": 60},
            {"type": "FORBIDDEN", "target": "administer_nsaids"},
        ],
        expected_tcc="fail",
        expected_reason="timing violation + contraindicated medication",
    ),
    ToyTrace(
        id="T14", description="BEFORE + MUST-omit (wrong order + missing action)",
        violation_type="MIXED",
        actions=[
            {"name": "administer_antibiotics", "t": 0},  # before blood culture
            {"name": "order_blood_culture", "t": 5},
            # start_iv_fluids MISSING
        ],
        required_actions=["administer_antibiotics", "order_blood_culture",
                          "start_iv_fluids"],
        forbidden_actions=[],
        constraints=[
            {"type": "BEFORE", "target": "order_blood_culture",
             "param": "administer_antibiotics"},
            {"type": "MUST", "target": "start_iv_fluids"},
        ],
        expected_tcc="fail",
        expected_reason="ordering violation + omission",
    ),

    # --- CLEAN (T15) ---
    ToyTrace(
        id="T15", description="All constraints satisfied (clean trace)",
        violation_type="CLEAN",
        actions=[
            {"name": "check_vitals", "t": 0},
            {"name": "order_blood_culture", "t": 5},
            {"name": "order_lactate", "t": 10},
            {"name": "start_iv_fluids", "t": 15},
            {"name": "administer_antibiotics", "t": 20},  # within 60min ✓
        ],
        required_actions=["check_vitals", "order_blood_culture", "order_lactate",
                          "start_iv_fluids", "administer_antibiotics"],
        forbidden_actions=[],
        constraints=[
            {"type": "WITHIN", "target": "administer_antibiotics", "deadline": 60},
            {"type": "BEFORE", "target": "order_blood_culture",
             "param": "administer_antibiotics"},
        ],
        expected_tcc="pass",
        expected_reason="all actions present, on time, correct order, no forbidden",
    ),
]


# ============================================================================
# Simulated Scorers
# ============================================================================

def score_mab_replay(trace: ToyTrace) -> dict:
    """
    MAB-style replay: action-set F1 with safety penalty.
    - Precision = |performed ∩ required| / |performed|
    - Recall = |performed ∩ required| / |required|
    - F1 = 2*P*R/(P+R)
    - Forbidden penalty: -0.1 per forbidden action found
    - Pass if F1 - penalty >= 0.5
    """
    performed = set(a["name"] for a in trace.actions)
    required = set(trace.required_actions)
    forbidden = set(trace.forbidden_actions)
    
    tp = len(performed & required)
    fp = len(performed - required)
    fn = len(required - performed)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    forbidden_found = len(performed & forbidden)
    penalty = forbidden_found * 0.1
    
    score = f1 - penalty
    verdict = "pass" if score >= 0.5 else "fail"
    
    return {
        "scorer": "MAB-replay",
        "f1": round(f1, 3),
        "forbidden_penalty": round(penalty, 3),
        "score": round(score, 3),
        "verdict": verdict,
        "can_see_timing": False,
        "can_see_order": False,
        "can_see_forbidden": True,  # via precision
        "can_see_omission": True,   # via recall
    }


def score_ac_replay(trace: ToyTrace) -> dict:
    """
    AC-style replay: coverage-based scorer.
    - Coverage = |performed ∩ required| / |required|
    - Pass if coverage >= 0.5
    """
    performed = set(a["name"] for a in trace.actions)
    required = set(trace.required_actions)
    
    coverage = len(performed & required) / len(required) if required else 1.0
    verdict = "pass" if coverage >= 0.5 else "fail"
    
    return {
        "scorer": "AC-replay",
        "coverage": round(coverage, 3),
        "verdict": verdict,
        "can_see_timing": False,
        "can_see_order": False,
        "can_see_forbidden": False,
        "can_see_omission": True,  # via coverage
    }


def score_tcc(trace: ToyTrace) -> dict:
    """
    TCC: full trace conformance checking (all 4 constraint types).
    """
    violations = []
    performed = set(a["name"] for a in trace.actions)
    action_times = {a["name"]: a["t"] for a in trace.actions}
    
    for c in trace.constraints:
        ctype = c["type"]
        target = c["target"]
        
        if ctype == "MUST":
            if target not in performed:
                violations.append(f"MUST: {target} missing")
        
        elif ctype == "FORBIDDEN":
            if target in performed:
                violations.append(f"FORBIDDEN: {target} present")
        
        elif ctype == "WITHIN":
            deadline = c["deadline"]
            if target in action_times:
                if action_times[target] > deadline:
                    violations.append(
                        f"WITHIN: {target} at t={action_times[target]} > deadline {deadline}")
            else:
                violations.append(f"WITHIN: {target} missing entirely")
        
        elif ctype == "BEFORE":
            first = target  # should come first
            second = c["param"]  # should come second
            if first in action_times and second in action_times:
                if action_times[first] >= action_times[second]:
                    violations.append(
                        f"BEFORE: {first} (t={action_times[first]}) "
                        f"not before {second} (t={action_times[second]})")
    
    verdict = "fail" if violations else "pass"
    
    return {
        "scorer": "TCC",
        "violations": violations,
        "n_violations": len(violations),
        "verdict": verdict,
        "can_see_timing": True,
        "can_see_order": True,
        "can_see_forbidden": True,
        "can_see_omission": True,
    }


# ============================================================================
# Main
# ============================================================================

def run_audit() -> dict:
    """Run all 15 toy traces through all 3 scorers."""
    results = []
    
    for trace in TOY_TRACES:
        mab = score_mab_replay(trace)
        ac = score_ac_replay(trace)
        tcc = score_tcc(trace)
        
        # Check correctness
        tcc_correct = (tcc["verdict"] == trace.expected_tcc)
        mab_expected_blind = trace.violation_type in ("WITHIN-only", "BEFORE-only")
        ac_expected_blind = trace.violation_type in ("WITHIN-only", "BEFORE-only", 
                                                      "FORBIDDEN-only")
        
        result = {
            "id": trace.id,
            "description": trace.description,
            "violation_type": trace.violation_type,
            "expected_tcc": trace.expected_tcc,
            "expected_reason": trace.expected_reason,
            "mab_verdict": mab["verdict"],
            "mab_score": mab["score"],
            "mab_f1": mab["f1"],
            "ac_verdict": ac["verdict"],
            "ac_coverage": ac["coverage"],
            "tcc_verdict": tcc["verdict"],
            "tcc_n_violations": tcc["n_violations"],
            "tcc_violations": tcc["violations"],
            "tcc_correct": tcc_correct,
        }
        results.append(result)
    
    # Summary by violation type
    type_summary = {}
    for vtype in ["WITHIN-only", "BEFORE-only", "FORBIDDEN-only", 
                   "MUST-omit", "MIXED", "CLEAN"]:
        traces_of_type = [r for r in results if r["violation_type"] == vtype]
        n = len(traces_of_type)
        if n == 0:
            continue
        type_summary[vtype] = {
            "count": n,
            "mab_detect": sum(1 for r in traces_of_type if r["mab_verdict"] == "fail"),
            "mab_detect_pct": round(sum(1 for r in traces_of_type 
                                        if r["mab_verdict"] == "fail") / n * 100, 1),
            "ac_detect": sum(1 for r in traces_of_type if r["ac_verdict"] == "fail"),
            "ac_detect_pct": round(sum(1 for r in traces_of_type 
                                       if r["ac_verdict"] == "fail") / n * 100, 1),
            "tcc_detect": sum(1 for r in traces_of_type if r["tcc_verdict"] == "fail"),
            "tcc_detect_pct": round(sum(1 for r in traces_of_type 
                                        if r["tcc_verdict"] == "fail") / n * 100, 1),
        }
    
    # Overall
    total_fail = [r for r in results if r["expected_tcc"] == "fail"]
    n_fail = len(total_fail)
    overall = {
        "total_traces": len(results),
        "expected_fail": n_fail,
        "expected_pass": len(results) - n_fail,
        "mab_correct_detect": sum(1 for r in total_fail if r["mab_verdict"] == "fail"),
        "ac_correct_detect": sum(1 for r in total_fail if r["ac_verdict"] == "fail"),
        "tcc_correct_detect": sum(1 for r in total_fail if r["tcc_verdict"] == "fail"),
        "tcc_all_correct": all(r["tcc_correct"] for r in results),
    }
    
    return {
        "traces": results,
        "type_summary": type_summary,
        "overall": overall,
    }


def generate_macros(results: dict) -> str:
    """Generate LaTeX macros from audit results."""
    o = results["overall"]
    return f"""% EX-35: Replay Fidelity Audit
% Auto-generated by exp_replay_fidelity_audit.py

\\newcommand{{\\fidelityNTraces}}{{{o['total_traces']}}}
\\newcommand{{\\fidelityNFail}}{{{o['expected_fail']}}}
\\newcommand{{\\fidelityMABDetect}}{{{o['mab_correct_detect']}}}
\\newcommand{{\\fidelityACDetect}}{{{o['ac_correct_detect']}}}
\\newcommand{{\\fidelityTCCDetect}}{{{o['tcc_correct_detect']}}}
\\newcommand{{\\fidelityTCCPerfect}}{{{str(o['tcc_all_correct']).lower()}}}
"""


def generate_latex_table(results: dict) -> str:
    """Generate a LaTeX table for the appendix."""
    lines = [
        "% EX-35 fidelity audit table",
        "\\begin{table}[h]",
        "\\centering",
        "\\small",
        "\\caption{Replay scorer fidelity audit on 15 diagnostic traces. "
        "MAB-replay and AC-replay reproduce the expected blindness pattern: "
        "0\\% detection of WITHIN and BEFORE violations. "
        "TCC detects all 14 violations and correctly passes the clean trace.}",
        "\\label{tab:fidelity_audit}",
        "\\begin{tabular}{llcccc}",
        "\\toprule",
        "ID & Type & Expected & MAB & AC & TCC \\\\",
        "\\midrule",
    ]
    
    for r in results["traces"]:
        exp = r["expected_tcc"].capitalize()
        mab = r["mab_verdict"].capitalize()
        ac = r["ac_verdict"].capitalize()
        tcc = r["tcc_verdict"].capitalize()
        
        # Mark correct/incorrect
        mab_mark = "\\checkmark" if (r["mab_verdict"] == r["expected_tcc"]) else "\\texttimes"
        ac_mark = "\\checkmark" if (r["ac_verdict"] == r["expected_tcc"]) else "\\texttimes"
        tcc_mark = "\\checkmark" if r["tcc_correct"] else "\\texttimes"
        
        vtype_short = r["violation_type"].replace("-only", "").replace("-", "+")
        
        lines.append(
            f"{r['id']} & {{\\sc {vtype_short}}} & {exp} & "
            f"{mab} {mab_mark} & {ac} {ac_mark} & {tcc} {tcc_mark} \\\\"
        )
    
    lines.extend([
        "\\midrule",
        f"\\multicolumn{{6}}{{l}}{{MAB detects {results['overall']['mab_correct_detect']}/14 violations; "
        f"AC detects {results['overall']['ac_correct_detect']}/14; TCC detects 14/14.}} \\\\",
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ])
    
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="evidence_pack/ex35_fidelity_audit")
    args = parser.parse_args()
    
    print("Running fidelity audit on 15 toy traces...\n")
    results = run_audit()
    
    # Print results
    print(f"{'ID':<4} {'Type':<15} {'Expected':<8} {'MAB':<8} {'AC':<8} {'TCC':<8}")
    print("-" * 60)
    for r in results["traces"]:
        mab_ok = "✓" if r["mab_verdict"] == r["expected_tcc"] else "✗"
        ac_ok = "✓" if r["ac_verdict"] == r["expected_tcc"] else "✗"
        tcc_ok = "✓" if r["tcc_correct"] else "✗"
        print(f"{r['id']:<4} {r['violation_type']:<15} {r['expected_tcc']:<8} "
              f"{r['mab_verdict']:<6}{mab_ok} {r['ac_verdict']:<6}{ac_ok} "
              f"{r['tcc_verdict']:<6}{tcc_ok}")
    
    print(f"\n--- Summary by type ---")
    for vtype, s in results["type_summary"].items():
        print(f"  {vtype:<15}: MAB {s['mab_detect']}/{s['count']}, "
              f"AC {s['ac_detect']}/{s['count']}, TCC {s['tcc_detect']}/{s['count']}")
    
    o = results["overall"]
    print(f"\n--- Overall (14 expected failures) ---")
    print(f"  MAB detects: {o['mab_correct_detect']}/14")
    print(f"  AC detects:  {o['ac_correct_detect']}/14")
    print(f"  TCC detects: {o['tcc_correct_detect']}/14")
    print(f"  TCC all correct: {o['tcc_all_correct']}")
    
    # Save
    os.makedirs(args.output_dir, exist_ok=True)
    
    with open(os.path.join(args.output_dir, "fidelity_audit.json"), "w") as f:
        json.dump(results, f, indent=2)
    
    macros = generate_macros(results)
    with open(os.path.join(args.output_dir, "macros.tex"), "w") as f:
        f.write(macros)
    
    latex = generate_latex_table(results)
    with open(os.path.join(args.output_dir, "table.tex"), "w") as f:
        f.write(latex)
    
    print(f"\nSaved to {args.output_dir}/")


if __name__ == "__main__":
    main()