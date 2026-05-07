"""Patient Realism Report Generator (Defense against Attack A.2)

Analyzes generated patient profiles for clinical realism:
demographics, lab distributions, and unrealistic combinations.

Usage:
    PYTHONPATH=. python scripts/generate_patient_realism_report.py
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cga_bench.eval_harness.scenario_loader import ScenarioLoader

BASE_DIR = Path(__file__).parent.parent
MD_OUTPUT = BASE_DIR / "evidence_pack" / "analysis" / "patient_realism_report.md"
JSON_OUTPUT = BASE_DIR / "evidence_pack" / "analysis" / "patient_realism_report.json"


def safe_median(values: list[float]) -> float:
    """Compute median from a sorted list."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def analyze_patients() -> dict:
    """Load all scenarios and analyze patient realism.

    Returns:
        Analysis results dict.
    """
    loader = ScenarioLoader()
    # Some scenarios may have schema issues (e.g. string instead of list);
    # load individually and skip broken ones.
    scenarios = {}
    load_errors: list[str] = []
    scenarios_dir = loader.scenarios_dir
    for file_path in sorted(scenarios_dir.glob("*_scenarios.yaml")):
        try:
            loader._load_scenarios_from_file(file_path)
        except Exception as e:
            load_errors.append(f"{file_path.name}: {e}")
    scenarios = dict(loader._scenarios_cache)

    ages: list[int] = []
    sexes: list[str] = []
    weights: list[float] = []
    potassiums: list[float] = []
    glucoses: list[float] = []
    phs: list[float] = []
    lactates: list[float] = []
    creatinines: list[float] = []
    issues: list[str] = []
    domains: list[str] = []
    allergy_counts: list[int] = []
    comorbidity_counts: list[int] = []

    for scenario_id, scenario in scenarios.items():
        patient = scenario.patient

        # Demographics
        age = patient.age
        if age is not None:
            ages.append(age)
            if age < 0 or age > 100:
                issues.append(f"{scenario_id}: age={age} (out of range)")

        sex = patient.sex
        if sex:
            sexes.append(sex)

        weight = patient.weight_kg
        if weight is not None:
            weights.append(weight)
            if weight < 20 or weight > 300:
                issues.append(f"{scenario_id}: weight={weight}kg (extreme)")

        # Comorbidities & allergies
        comorbidities = patient.comorbidities or []
        allergies = patient.allergies or []
        comorbidity_counts.append(len(comorbidities))
        allergy_counts.append(len(allergies))

        # Labs from vitals (PatientState doesn't have labs directly,
        # but ground_truth may have initial_labs)
        gt = scenario.ground_truth or {}
        labs = gt.get("initial_labs", {})

        if "potassium" in labs:
            val = labs["potassium"]
            potassiums.append(val)
            if val < 1.5 or val > 8.0:
                issues.append(f"{scenario_id}: potassium={val} (extreme)")

        if "glucose" in labs:
            val = labs["glucose"]
            glucoses.append(val)

        if "ph" in labs:
            val = labs["ph"]
            phs.append(val)
            if val < 6.8 or val > 7.8:
                issues.append(f"{scenario_id}: pH={val} (incompatible with life)")

        if "lactate" in labs:
            lactates.append(labs["lactate"])

        if "creatinine" in labs:
            creatinines.append(labs["creatinine"])

        # Unrealistic combination detection
        if "pregnancy" in comorbidities and sex == "M":
            issues.append(f"{scenario_id}: male + pregnancy")
        if age is not None and age < 10 and "type_2_diabetes" in comorbidities:
            issues.append(f"{scenario_id}: age {age} + T2DM (unlikely)")
        if age is not None and age > 80 and "pregnancy" in comorbidities:
            issues.append(f"{scenario_id}: age {age} + pregnancy (unlikely)")
        if age is not None and age < 5 and "copd" in comorbidities:
            issues.append(f"{scenario_id}: age {age} + COPD (pediatric, unlikely)")

        # Domain tracking
        domains.append(scenario.guideline_graph or "unknown")

    # Include load errors as issues
    for err in load_errors:
        issues.append(f"LOAD_ERROR: {err}")

    return {
        "total_scenarios": len(scenarios),
        "load_errors": len(load_errors),
        "demographics": {
            "ages": ages,
            "sexes": dict(Counter(sexes)),
            "weights": weights,
        },
        "labs": {
            "potassiums": potassiums,
            "glucoses": glucoses,
            "phs": phs,
            "lactates": lactates,
            "creatinines": creatinines,
        },
        "complexity": {
            "allergy_counts": allergy_counts,
            "comorbidity_counts": comorbidity_counts,
        },
        "domains": dict(Counter(domains)),
        "issues": issues,
    }


def format_stat(values: list[float], label: str) -> str:
    """Format basic statistics for a list of values."""
    if not values:
        return f"  {label}: no data"
    return (
        f"  {label} ({len(values)} values): "
        f"min={min(values):.1f}, max={max(values):.1f}, "
        f"mean={sum(values) / len(values):.1f}, median={safe_median(values):.1f}"
    )


def generate_markdown_report(analysis: dict) -> str:
    """Generate markdown report from analysis results."""
    lines = ["# Patient Realism Report\n"]

    total = analysis["total_scenarios"]
    lines.append(f"**Total scenarios analyzed**: {total}\n")

    # Demographics
    demo = analysis["demographics"]
    ages = demo["ages"]
    lines.append("## Demographics\n")
    if ages:
        lines.append(
            f"- **Age**: min={min(ages)}, max={max(ages)}, "
            f"mean={sum(ages) / len(ages):.0f}, median={safe_median(ages):.0f}"
        )
    lines.append(f"- **Sex distribution**: {demo['sexes']}")
    weights = demo["weights"]
    if weights:
        lines.append(
            f"- **Weight**: min={min(weights):.0f}kg, max={max(weights):.0f}kg, "
            f"mean={sum(weights) / len(weights):.0f}kg"
        )

    # Lab distributions
    labs = analysis["labs"]
    lines.append("\n## Lab Distributions\n")
    for lab_name, values in [
        ("Potassium (mEq/L)", labs["potassiums"]),
        ("Glucose (mg/dL)", labs["glucoses"]),
        ("pH", labs["phs"]),
        ("Lactate (mmol/L)", labs["lactates"]),
        ("Creatinine (mg/dL)", labs["creatinines"]),
    ]:
        if values:
            lines.append(
                f"- **{lab_name}** ({len(values)} values): "
                f"{min(values):.2f} - {max(values):.2f}, "
                f"mean={sum(values) / len(values):.2f}"
            )
        else:
            lines.append(f"- **{lab_name}**: no data in ground_truth")

    # Complexity
    comp = analysis["complexity"]
    lines.append("\n## Patient Complexity\n")
    ac = comp["allergy_counts"]
    cc = comp["comorbidity_counts"]
    if ac:
        lines.append(f"- **Allergies per patient**: mean={sum(ac) / len(ac):.1f}, max={max(ac)}")
    if cc:
        lines.append(f"- **Comorbidities per patient**: mean={sum(cc) / len(cc):.1f}, max={max(cc)}")

    # Domain distribution
    lines.append("\n## Domain Distribution\n")
    lines.append("| Domain | Count |")
    lines.append("|--------|-------|")
    for domain, count in sorted(analysis["domains"].items(), key=lambda x: -x[1]):
        lines.append(f"| {domain} | {count} |")

    # Issues
    issues = analysis["issues"]
    lines.append(f"\n## Realism Issues Found: {len(issues)}\n")
    if issues:
        for issue in issues:
            lines.append(f"- {issue}")
    else:
        lines.append("No unrealistic patient profiles detected.")

    return "\n".join(lines)


def main() -> None:
    """Generate patient realism analysis report."""
    analysis = analyze_patients()

    # Print summary
    ages = analysis["demographics"]["ages"]
    issues = analysis["issues"]

    print(f"""
=== Patient Realism Report ===

Total scenarios: {analysis["total_scenarios"]}

Demographics:
  Age: min={min(ages)}, max={max(ages)}, mean={sum(ages) / len(ages):.0f}
  Sex: {analysis["demographics"]["sexes"]}
""")

    labs = analysis["labs"]
    for lab_name, values in [
        ("Potassium", labs["potassiums"]),
        ("Glucose", labs["glucoses"]),
        ("pH", labs["phs"]),
    ]:
        if values:
            print(format_stat(values, lab_name))

    print(f"\nIssues found: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")

    # Save outputs
    MD_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    md_report = generate_markdown_report(analysis)
    with open(MD_OUTPUT, "w") as f:
        f.write(md_report)
    print(f"\nMarkdown report saved to {MD_OUTPUT}")

    # JSON (without large arrays for readability)
    json_data = {
        "total_scenarios": analysis["total_scenarios"],
        "demographics": {
            "age_min": min(ages) if ages else None,
            "age_max": max(ages) if ages else None,
            "age_mean": round(sum(ages) / len(ages), 1) if ages else None,
            "age_median": safe_median(ages),
            "sex_distribution": analysis["demographics"]["sexes"],
        },
        "labs": {},
        "complexity": {
            "mean_allergies": round(
                sum(analysis["complexity"]["allergy_counts"]) / len(analysis["complexity"]["allergy_counts"]),
                2,
            )
            if analysis["complexity"]["allergy_counts"]
            else 0,
            "mean_comorbidities": round(
                sum(analysis["complexity"]["comorbidity_counts"]) / len(analysis["complexity"]["comorbidity_counts"]),
                2,
            )
            if analysis["complexity"]["comorbidity_counts"]
            else 0,
        },
        "domains": analysis["domains"],
        "issues": issues,
        "issues_count": len(issues),
    }

    for lab_name, values in labs.items():
        if values:
            json_data["labs"][lab_name] = {
                "count": len(values),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "mean": round(sum(values) / len(values), 2),
            }

    with open(JSON_OUTPUT, "w") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"JSON data saved to {JSON_OUTPUT}")


if __name__ == "__main__":
    main()
