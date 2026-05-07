
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""WS-5: Contamination Probe for CGA-Bench.

Evaluates whether LLMs have memorised clinical guideline text used in
CGA-Bench graphs, which could inflate benchmark scores.

Four probe types:
  1. Verbatim Recall  -- sentence-completion overlap
  2. Constraint Recall -- FORBIDDEN action recall from patient context only
  3. Novel Constraint  -- fabricated constraint detection
  4. Held-out Domain   -- performance gap between known vs held-out graphs

Usage:
    cd ${CGA_BENCH_ROOT}/cga_bench
    PYTHONPATH=. python scripts/experiments/ws5_contamination_probe.py --probe all --mock-llm
    PYTHONPATH=. python scripts/experiments/ws5_contamination_probe.py --probe verbatim \
        --backend vllm --endpoint http://localhost:8013/v1 --model Qwen/Qwen3-30B
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import random
import re
import sys
import time
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = ROOT / "configs"
PROBES_FILE = CONFIGS_DIR / "contamination_probes.json"
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"
RESULTS_DIR = ROOT / "results" / "clean_slate_rescored"
EVIDENCE_DIR = ROOT / "evidence_pack"
TABLES_DIR = EVIDENCE_DIR / "tables"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

try:
    from agent_runner.llm_provider import (
        BaseLLMProvider,
        LLMBackend,
        LLMConfig,
        LLMMessage,
        LLMProviderFactory,
    )
except (ImportError, ModuleNotFoundError):
    BaseLLMProvider = None  # type: ignore[assignment,misc]
    LLMBackend = None  # type: ignore[assignment,misc]
    LLMConfig = None  # type: ignore[assignment,misc]
    LLMMessage = None  # type: ignore[assignment,misc]
    LLMProviderFactory = None  # type: ignore[assignment,misc]
from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
from scripts.experiments._common import (
    HELD_OUT_GRAPH_IDS,
    bootstrap_ci,
    fmt_f,
    fmt_p,
    save_json,
    save_latex_table,
    save_markdown,
)

logger = logging.getLogger(__name__)

SEED = 42
PROBE_TYPES = ("verbatim", "recall", "novel", "heldout")

# Graphs used in CGA-Bench (non-held-out)
KNOWN_GRAPH_STEMS = [
    "ssc_sepsis_hour1",
    "aha_chest_pain",
    "ada_dka_management",
    "aha_stroke",
    "aha_heart_failure",
    "kdigo_aki_full",
]

# Patient contexts for constraint recall probes (Probe 2)
PROBE_PATIENTS: dict[str, dict[str, Any]] = {
    "ssc_sepsis_hour1": {
        "age": 67,
        "sex": "M",
        "chief_complaint": "fever, hypotension, altered mental status",
        "comorbidities": ["diabetes", "chronic_kidney_disease"],
        "allergies": ["penicillin"],
        "vitals": {"sbp": 78, "dbp": 45, "map_mmhg": 56, "hr": 118, "temp": 39.2},
        "labs": {"lactate": 5.1, "wbc": 18.4, "creatinine": 2.8},
        "medications": [],
    },
    "aha_chest_pain": {
        "age": 55,
        "sex": "M",
        "chief_complaint": "crushing substernal chest pain radiating to left arm",
        "comorbidities": ["hypertension", "rv_infarction_suspected"],
        "allergies": [],
        "vitals": {"sbp": 88, "dbp": 55, "hr": 105, "spo2": 94},
        "labs": {"troponin": 2.4},
        "medications": [],
    },
    "ada_dka_management": {
        "age": 28,
        "sex": "F",
        "chief_complaint": "nausea, vomiting, abdominal pain, polyuria",
        "comorbidities": ["type_1_diabetes"],
        "allergies": [],
        "vitals": {"sbp": 105, "dbp": 60, "hr": 112, "rr": 28},
        "labs": {"glucose": 480, "ph": 7.1, "bicarbonate": 8, "potassium": 2.9, "anion_gap": 24},
        "medications": [],
    },
    "aha_stroke": {
        "age": 72,
        "sex": "F",
        "chief_complaint": "acute onset left-sided weakness, slurred speech",
        "comorbidities": ["atrial_fibrillation", "ischemic_stroke"],
        "allergies": [],
        "vitals": {"sbp": 192, "dbp": 115, "hr": 88},
        "labs": {"glucose": 145, "inr": 1.1},
        "medications": [],
        "history": [],
        "presentation": [],
    },
    "aha_heart_failure": {
        "age": 63,
        "sex": "M",
        "chief_complaint": "progressive dyspnea, orthopnea, lower extremity edema",
        "comorbidities": ["hfref", "ef_below_40", "type_2_diabetes"],
        "allergies": [],
        "vitals": {"sbp": 100, "dbp": 62, "hr": 95, "spo2": 90},
        "labs": {"bnp": 1200, "creatinine": 1.6},
        "medications": [],
    },
}


# ===================================================================
# Helpers
# ===================================================================


def _unigram_overlap(reference: str, hypothesis: str) -> float:
    """Compute unigram overlap ratio (simple BLEU-1 proxy).

    Returns the fraction of reference unigrams present in the hypothesis.
    """
    ref_tokens = _tokenise(reference)
    hyp_tokens = _tokenise(hypothesis)
    if not ref_tokens:
        return 0.0
    ref_set = set(ref_tokens)
    hyp_set = set(hyp_tokens)
    overlap = ref_set & hyp_set
    return len(overlap) / len(ref_set)


def _char_overlap(reference: str, hypothesis: str) -> float:
    """Character-level overlap ratio."""
    ref_clean = re.sub(r"\s+", " ", reference.lower().strip())
    hyp_clean = re.sub(r"\s+", " ", hypothesis.lower().strip())
    if not ref_clean:
        return 0.0
    common_len = 0
    hyp_remaining = hyp_clean
    for char in ref_clean:
        idx = hyp_remaining.find(char)
        if idx != -1:
            common_len += 1
            hyp_remaining = hyp_remaining[:idx] + hyp_remaining[idx + 1 :]
    return common_len / len(ref_clean)


def _tokenise(text: str) -> list[str]:
    """Lowercase whitespace tokeniser with punctuation stripping."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _load_probes() -> dict[str, Any]:
    """Load the contamination probes configuration."""
    with open(PROBES_FILE) as f:
        return json.load(f)


def _build_provider(args: argparse.Namespace) -> BaseLLMProvider:
    """Build LLM provider from CLI arguments."""
    if args.mock_llm:
        config = LLMConfig(backend=LLMBackend.MOCK, model="mock")
        return LLMProviderFactory.create(config)

    backend = LLMBackend(args.backend)
    config = LLMConfig(
        backend=backend,
        model=args.model,
        temperature=0.0,
        max_tokens=512,
    )
    if args.endpoint:
        config.base_url = args.endpoint
    return LLMProviderFactory.create(config)


def _llm_complete(provider: BaseLLMProvider, system: str, user: str) -> str:
    """Single-turn LLM call."""
    messages = [
        LLMMessage(role="system", content=system),
        LLMMessage(role="user", content=user),
    ]
    response = provider.complete(messages)
    return response.content


# ===================================================================
# Probe 1: Verbatim Recall Test
# ===================================================================


@dataclass
class VerbatimResult:
    """Result for a single verbatim probe."""

    probe_id: str
    graph: str
    guideline: str
    prefix: str
    expected: str
    model_completion: str
    char_overlap: float
    unigram_overlap: float


def run_verbatim_probe(
    provider: BaseLLMProvider,
    probes: dict[str, Any],
    mock_mode: bool = False,
) -> list[VerbatimResult]:
    """Probe 1: Complete the guideline sentence."""
    results: list[VerbatimResult] = []
    system_prompt = (
        "You are a medical knowledge assistant. Complete the following "
        "clinical guideline sentence. Provide ONLY the completion text, "
        "nothing else. Do not repeat the prefix."
    )

    graphs_data = probes.get("graphs", {})
    for graph_key, graph_info in graphs_data.items():
        guideline_name = graph_info.get("guideline", graph_key)
        for sentence in graph_info.get("sentences", []):
            prefix = sentence["prefix"]
            expected = sentence["completion"]
            probe_id = sentence["id"]

            if mock_mode:
                rng = random.Random(hash(probe_id))
                words = _tokenise(expected)
                n_overlap = max(1, len(words) // 3)
                sampled = rng.sample(words, min(n_overlap, len(words)))
                extra = rng.sample(
                    ["clinical", "patient", "therapy", "recommended", "protocol"],
                    k=2,
                )
                model_completion = " ".join(sampled + extra) + "."
            else:
                user_prompt = f'Complete this clinical guideline sentence:\n\n"{prefix}"'
                model_completion = _llm_complete(provider, system_prompt, user_prompt)

            results.append(
                VerbatimResult(
                    probe_id=probe_id,
                    graph=graph_key,
                    guideline=guideline_name,
                    prefix=prefix,
                    expected=expected,
                    model_completion=model_completion.strip(),
                    char_overlap=_char_overlap(expected, model_completion),
                    unigram_overlap=_unigram_overlap(expected, model_completion),
                )
            )
    return results


# ===================================================================
# Probe 2: Constraint Recall Without Context
# ===================================================================


@dataclass
class ConstraintRecallResult:
    """Result for a single constraint recall probe."""

    graph: str
    expected_forbidden: list[str]
    model_forbidden: list[str]
    recall: float
    precision: float
    f1: float


def run_constraint_recall_probe(
    provider: BaseLLMProvider,
    mock_mode: bool = False,
) -> list[ConstraintRecallResult]:
    """Probe 2: Recall forbidden actions from patient context alone."""
    engine = ConstraintDerivationEngine()
    results: list[ConstraintRecallResult] = []

    system_prompt = (
        "You are a clinical safety advisor. Given only a patient description, "
        "list ALL contraindicated medications and procedures. "
        "Output a JSON array of strings, each a short action identifier. "
        'Example: ["give_nitroglycerin", "discharge_home"]\n'
        "Output ONLY the JSON array."
    )

    for graph_stem, patient in PROBE_PATIENTS.items():
        graph_path = GRAPHS_DIR / f"{graph_stem}.yaml"
        if not graph_path.exists():
            continue
        graph = load_graph(graph_path)
        constraint_set = engine.derive(graph, patient, scenario_id=f"ws5_{graph_stem}")

        expected_forbidden = []
        for c in constraint_set.forbidden:
            expected_forbidden.extend(c.actions)
        expected_forbidden = sorted(set(expected_forbidden))

        if not expected_forbidden:
            continue

        patient_desc = (
            f"Patient: {patient['age']}yo {patient['sex']}\n"
            f"Chief complaint: {patient['chief_complaint']}\n"
            f"Comorbidities: {', '.join(patient.get('comorbidities', []))}\n"
            f"Allergies: {', '.join(patient.get('allergies', [])) or 'None'}\n"
            f"Vitals: {json.dumps(patient.get('vitals', {}))}\n"
            f"Labs: {json.dumps(patient.get('labs', {}))}"
        )

        if mock_mode:
            rng = random.Random(hash(graph_stem))
            n_recall = max(1, len(expected_forbidden) // 2)
            model_forbidden = rng.sample(
                expected_forbidden,
                min(n_recall, len(expected_forbidden)),
            )
            model_forbidden += [f"mock_action_{rng.randint(1, 99)}"]
        else:
            user_prompt = f"Given this patient, list all contraindicated medications and procedures:\n\n{patient_desc}"
            raw = _llm_complete(provider, system_prompt, user_prompt)
            try:
                model_forbidden = json.loads(raw)
                if not isinstance(model_forbidden, list):
                    model_forbidden = []
            except json.JSONDecodeError:
                model_forbidden = _extract_action_ids(raw)

        model_set = set(model_forbidden)
        expected_set = set(expected_forbidden)

        tp = len(model_set & expected_set)
        recall = tp / len(expected_set) if expected_set else 0.0
        precision = tp / len(model_set) if model_set else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        results.append(
            ConstraintRecallResult(
                graph=graph_stem,
                expected_forbidden=expected_forbidden,
                model_forbidden=list(model_forbidden),
                recall=recall,
                precision=precision,
                f1=f1,
            )
        )
    return results


def _extract_action_ids(text: str) -> list[str]:
    """Heuristic extraction of action-like identifiers from free text."""
    pattern = re.compile(r"[a-z][a-z0-9_]+(?:_[a-z0-9]+)+")
    return list(set(pattern.findall(text.lower())))


# ===================================================================
# Probe 3: Novel Constraint Test
# ===================================================================


@dataclass
class NovelConstraintResult:
    """Result for a single novel constraint probe."""

    constraint_id: str
    description: str
    domain: str
    is_real: bool
    model_says_real: bool
    model_explanation: str
    correct: bool


def run_novel_constraint_probe(
    provider: BaseLLMProvider,
    probes: dict[str, Any],
    mock_mode: bool = False,
) -> list[NovelConstraintResult]:
    """Probe 3: Can the model identify fabricated constraints?"""
    results: list[NovelConstraintResult] = []
    system_prompt = (
        "You are a clinical guideline expert. Evaluate whether the following "
        "statement is a REAL clinical guideline recommendation or a FABRICATED one. "
        'Respond in JSON format: {"verdict": "real" or "fabricated", "explanation": "..."}'
    )

    novel_constraints = probes.get("novel_constraints", [])
    for constraint in novel_constraints:
        cid = constraint["id"]
        desc = constraint["description"]
        is_real = constraint.get("is_real", False)
        domain = constraint.get("domain", "unknown")

        if mock_mode:
            rng = random.Random(hash(cid))
            model_says_real = rng.random() < 0.3
            explanation = (
                "This appears to reference a real guideline."
                if model_says_real
                else "This medication/protocol does not appear in published guidelines."
            )
        else:
            user_prompt = (
                f"Is this a valid clinical guideline recommendation?\n\n"
                f'"{desc}"\n\n'
                f'Respond with JSON: {{"verdict": "real" or "fabricated", "explanation": "..."}}'
            )
            raw = _llm_complete(provider, system_prompt, user_prompt)
            try:
                parsed = json.loads(raw)
                verdict = parsed.get("verdict", "").lower()
                model_says_real = verdict == "real"
                explanation = parsed.get("explanation", "")
            except json.JSONDecodeError:
                model_says_real = "real" in raw.lower() and "fabricated" not in raw.lower()
                explanation = raw[:200]

        correct = model_says_real == is_real
        results.append(
            NovelConstraintResult(
                constraint_id=cid,
                description=desc,
                domain=domain,
                is_real=is_real,
                model_says_real=model_says_real,
                model_explanation=explanation,
                correct=correct,
            )
        )
    return results


# ===================================================================
# Probe 4: Held-out Domain Advantage
# ===================================================================


@dataclass
class HeldOutResult:
    """Result for held-out domain advantage analysis."""

    known_scores: list[float]
    heldout_scores: list[float]
    known_mean: float
    heldout_mean: float
    known_ci: tuple[float, float]
    heldout_ci: tuple[float, float]
    u_statistic: float
    p_value: float
    effect_significant: bool
    data_source: str


def run_heldout_probe() -> HeldOutResult:
    """Probe 4: Compare performance on known vs held-out domains.

    Uses existing episode results from results/ if available, otherwise
    generates synthetic data to demonstrate the analysis framework.
    """
    known_scores: list[float] = []
    heldout_scores: list[float] = []
    data_source = "synthetic"

    result_files = sorted(RESULTS_DIR.glob("*.json")) if RESULTS_DIR.exists() else []

    if result_files:
        for rf in result_files:
            try:
                with open(rf) as f:
                    episode = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            graph_id = episode.get("graph_id", episode.get("guideline_graph", ""))
            score = episode.get("cga_score", {})
            compliance = score.get("compliance_score")
            if compliance is None:
                continue

            if graph_id in HELD_OUT_GRAPH_IDS:
                heldout_scores.append(float(compliance))
            else:
                known_scores.append(float(compliance))

        if known_scores and heldout_scores:
            data_source = "episode_results"

    # Fall back to synthetic data if no episode results
    if not known_scores or not heldout_scores:
        rng = np.random.default_rng(SEED)
        # Known domains: models tend to score higher if contaminated
        known_scores = list(rng.beta(6, 3, size=30))
        # Held-out domains: slightly lower if contamination helps
        heldout_scores = list(rng.beta(5, 4, size=15))
        data_source = "synthetic"

    known_arr = np.array(known_scores)
    heldout_arr = np.array(heldout_scores)

    known_mean = float(np.mean(known_arr))
    heldout_mean = float(np.mean(heldout_arr))
    known_ci = bootstrap_ci(known_arr, np.mean)
    heldout_ci = bootstrap_ci(heldout_arr, np.mean)

    try:
        from scipy.stats import mannwhitneyu

        stat, p_val = mannwhitneyu(known_arr, heldout_arr, alternative="greater")
    except ImportError:
        stat, p_val = _simple_mann_whitney(known_arr, heldout_arr)

    return HeldOutResult(
        known_scores=known_scores,
        heldout_scores=heldout_scores,
        known_mean=known_mean,
        heldout_mean=heldout_mean,
        known_ci=known_ci,
        heldout_ci=heldout_ci,
        u_statistic=float(stat),
        p_value=float(p_val),
        effect_significant=p_val < 0.05,
        data_source=data_source,
    )


def _simple_mann_whitney(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Minimal Mann-Whitney U fallback when scipy is unavailable."""
    nx, ny = len(x), len(y)
    u_stat = 0.0
    for xi in x:
        for yj in y:
            if xi > yj:
                u_stat += 1.0
            elif xi == yj:
                u_stat += 0.5
    mu = nx * ny / 2
    sigma = np.sqrt(nx * ny * (nx + ny + 1) / 12)
    if sigma == 0:
        return u_stat, 1.0
    z = (u_stat - mu) / sigma
    # One-sided p-value approximation via normal CDF
    p_val = 0.5 * (1.0 - np.tanh(0.7 * z))  # rough sigmoid approx
    return u_stat, float(np.clip(p_val, 0.0, 1.0))


# ===================================================================
# Report Generation
# ===================================================================


def _build_json_report(
    verbatim: list[VerbatimResult] | None,
    constraint: list[ConstraintRecallResult] | None,
    novel: list[NovelConstraintResult] | None,
    heldout: HeldOutResult | None,
    elapsed_seconds: float,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Build structured JSON evidence pack."""
    report: dict[str, Any] = {
        "experiment": "WS-5 Contamination Probe",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": {
            "backend": args.backend if not args.mock_llm else "mock",
            "model": args.model if not args.mock_llm else "mock",
            "mock_mode": args.mock_llm,
            "probes_requested": args.probe,
        },
        "elapsed_seconds": round(elapsed_seconds, 2),
    }

    if verbatim is not None:
        by_graph: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for v in verbatim:
            by_graph[v.graph].append(
                {
                    "probe_id": v.probe_id,
                    "char_overlap": round(v.char_overlap, 4),
                    "unigram_overlap": round(v.unigram_overlap, 4),
                    "model_completion": v.model_completion[:200],
                }
            )

        char_overlaps = [v.char_overlap for v in verbatim]
        uni_overlaps = [v.unigram_overlap for v in verbatim]
        report["probe_1_verbatim"] = {
            "n_probes": len(verbatim),
            "mean_char_overlap": round(float(np.mean(char_overlaps)), 4),
            "mean_unigram_overlap": round(float(np.mean(uni_overlaps)), 4),
            "std_char_overlap": round(float(np.std(char_overlaps)), 4),
            "std_unigram_overlap": round(float(np.std(uni_overlaps)), 4),
            "by_graph": dict(by_graph),
        }

    if constraint is not None:
        report["probe_2_constraint_recall"] = {
            "n_graphs": len(constraint),
            "mean_recall": round(float(np.mean([c.recall for c in constraint])), 4),
            "mean_precision": round(float(np.mean([c.precision for c in constraint])), 4),
            "mean_f1": round(float(np.mean([c.f1 for c in constraint])), 4),
            "by_graph": {
                c.graph: {
                    "recall": round(c.recall, 4),
                    "precision": round(c.precision, 4),
                    "f1": round(c.f1, 4),
                    "n_expected": len(c.expected_forbidden),
                    "n_predicted": len(c.model_forbidden),
                }
                for c in constraint
            },
        }

    if novel is not None:
        n_correct = sum(1 for n in novel if n.correct)
        report["probe_3_novel_constraint"] = {
            "n_probes": len(novel),
            "accuracy": round(n_correct / len(novel), 4) if novel else 0.0,
            "fabricated_detected": sum(1 for n in novel if not n.is_real and not n.model_says_real),
            "fabricated_missed": sum(1 for n in novel if not n.is_real and n.model_says_real),
            "details": [
                {
                    "id": n.constraint_id,
                    "domain": n.domain,
                    "is_real": n.is_real,
                    "model_says_real": n.model_says_real,
                    "correct": n.correct,
                    "explanation_snippet": n.model_explanation[:150],
                }
                for n in novel
            ],
        }

    if heldout is not None:
        report["probe_4_heldout_domain"] = {
            "data_source": heldout.data_source,
            "known_n": len(heldout.known_scores),
            "heldout_n": len(heldout.heldout_scores),
            "known_mean": round(heldout.known_mean, 4),
            "heldout_mean": round(heldout.heldout_mean, 4),
            "known_ci_95": [round(heldout.known_ci[0], 4), round(heldout.known_ci[1], 4)],
            "heldout_ci_95": [round(heldout.heldout_ci[0], 4), round(heldout.heldout_ci[1], 4)],
            "mann_whitney_u": round(heldout.u_statistic, 2),
            "p_value": float(fmt_p(heldout.p_value)) if heldout.p_value >= 0.001 else heldout.p_value,
            "significant_at_005": heldout.effect_significant,
        }

    return report


def _build_markdown_report(report: dict[str, Any]) -> str:
    """Generate markdown summary from JSON report."""
    lines = [
        "# WS-5: Contamination Probe Results",
        "",
        f"**Timestamp**: {report.get('timestamp', 'N/A')}",
        f"**Backend**: {report['config']['backend']}",
        f"**Model**: {report['config']['model']}",
        f"**Mock mode**: {report['config']['mock_mode']}",
        f"**Elapsed**: {report.get('elapsed_seconds', 0):.1f}s",
        "",
    ]

    p1 = report.get("probe_1_verbatim")
    if p1:
        lines += [
            "## Probe 1: Verbatim Recall",
            "",
            f"- **N probes**: {p1['n_probes']}",
            f"- **Mean char overlap**: {p1['mean_char_overlap']:.4f} +/- {p1['std_char_overlap']:.4f}",
            f"- **Mean unigram overlap**: {p1['mean_unigram_overlap']:.4f} +/- {p1['std_unigram_overlap']:.4f}",
            "",
            "| Graph | Probe | Char Overlap | Unigram Overlap |",
            "|-------|-------|-------------|-----------------|",
        ]
        for graph_key, probes_list in p1["by_graph"].items():
            for p in probes_list:
                lines.append(
                    f"| {graph_key} | {p['probe_id']} | {p['char_overlap']:.4f} | {p['unigram_overlap']:.4f} |"
                )
        lines.append("")

    p2 = report.get("probe_2_constraint_recall")
    if p2:
        lines += [
            "## Probe 2: Constraint Recall (No CPG Context)",
            "",
            f"- **Mean recall**: {p2['mean_recall']:.4f}",
            f"- **Mean precision**: {p2['mean_precision']:.4f}",
            f"- **Mean F1**: {p2['mean_f1']:.4f}",
            "",
            "| Graph | Recall | Precision | F1 | Expected | Predicted |",
            "|-------|--------|-----------|-----|----------|-----------|",
        ]
        for g, info in p2["by_graph"].items():
            lines.append(
                f"| {g} | {info['recall']:.4f} | {info['precision']:.4f} | {info['f1']:.4f} | {info['n_expected']} | {info['n_predicted']} |"
            )
        lines.append("")

    p3 = report.get("probe_3_novel_constraint")
    if p3:
        lines += [
            "## Probe 3: Novel Constraint Detection",
            "",
            f"- **Accuracy**: {p3['accuracy']:.4f}",
            f"- **Fabricated detected**: {p3['fabricated_detected']}/{p3['fabricated_detected'] + p3['fabricated_missed']}",
            f"- **Fabricated missed (concerning)**: {p3['fabricated_missed']}",
            "",
            "| ID | Domain | Real? | Model Says | Correct |",
            "|----|--------|-------|------------|---------|",
        ]
        for d in p3["details"]:
            lines.append(f"| {d['id']} | {d['domain']} | {d['is_real']} | {d['model_says_real']} | {d['correct']} |")
        lines.append("")

    p4 = report.get("probe_4_heldout_domain")
    if p4:
        sig_marker = "YES" if p4["significant_at_005"] else "no"
        lines += [
            "## Probe 4: Held-out Domain Advantage",
            "",
            f"- **Data source**: {p4['data_source']}",
            f"- **Known domains**: mean={p4['known_mean']:.4f}, 95% CI [{p4['known_ci_95'][0]:.4f}, {p4['known_ci_95'][1]:.4f}], n={p4['known_n']}",
            f"- **Held-out domains**: mean={p4['heldout_mean']:.4f}, 95% CI [{p4['heldout_ci_95'][0]:.4f}, {p4['heldout_ci_95'][1]:.4f}], n={p4['heldout_n']}",
            f"- **Mann-Whitney U**: {p4['mann_whitney_u']:.2f}, p={fmt_p(p4['p_value'])}",
            f"- **Significant at 0.05**: {sig_marker}",
            "",
        ]

    lines += [
        "---",
        "*Generated by `ws5_contamination_probe.py`*",
    ]
    return "\n".join(lines)


def _build_latex_tables(report: dict[str, Any], output_dir: Path) -> None:
    """Generate LaTeX booktabs tables."""
    p1 = report.get("probe_1_verbatim")
    if p1:
        rows = []
        for graph_key, probes_list in p1["by_graph"].items():
            for p in probes_list:
                rows.append(
                    [
                        graph_key.replace("_", r"\_"),
                        p["probe_id"],
                        fmt_f(p["char_overlap"]),
                        fmt_f(p["unigram_overlap"]),
                    ]
                )
        # Summary row
        rows.append(
            [
                r"\textbf{Mean}",
                "",
                fmt_f(p1["mean_char_overlap"]),
                fmt_f(p1["mean_unigram_overlap"]),
            ]
        )
        save_latex_table(
            rows,
            headers=["Graph", "Probe", "Char Overlap", "Unigram Overlap"],
            path=output_dir / "ws5_verbatim.tex",
            caption="WS-5 Probe 1: Verbatim recall overlap scores",
            label="tab:ws5-verbatim",
        )

    p2 = report.get("probe_2_constraint_recall")
    if p2:
        rows = []
        for g, info in p2["by_graph"].items():
            rows.append(
                [
                    g.replace("_", r"\_"),
                    fmt_f(info["recall"]),
                    fmt_f(info["precision"]),
                    fmt_f(info["f1"]),
                    str(info["n_expected"]),
                ]
            )
        rows.append(
            [
                r"\textbf{Mean}",
                fmt_f(p2["mean_recall"]),
                fmt_f(p2["mean_precision"]),
                fmt_f(p2["mean_f1"]),
                "",
            ]
        )
        save_latex_table(
            rows,
            headers=["Graph", "Recall", "Precision", "F1", "|Expected|"],
            path=output_dir / "ws5_constraint_recall.tex",
            caption="WS-5 Probe 2: Constraint recall without CPG context",
            label="tab:ws5-constraint-recall",
        )

    p4 = report.get("probe_4_heldout_domain")
    if p4:
        rows = [
            [
                "Known domains",
                str(p4["known_n"]),
                fmt_f(p4["known_mean"]),
                f"[{fmt_f(p4['known_ci_95'][0])}, {fmt_f(p4['known_ci_95'][1])}]",
            ],
            [
                "Held-out domains",
                str(p4["heldout_n"]),
                fmt_f(p4["heldout_mean"]),
                f"[{fmt_f(p4['heldout_ci_95'][0])}, {fmt_f(p4['heldout_ci_95'][1])}]",
            ],
            [
                r"\textbf{Mann-Whitney U}",
                "",
                f"U={p4['mann_whitney_u']:.1f}",
                f"p={fmt_p(p4['p_value'])}",
            ],
        ]
        save_latex_table(
            rows,
            headers=["Group", "N", "Mean Compliance", "95\\% CI"],
            path=output_dir / "ws5_heldout.tex",
            caption="WS-5 Probe 4: Known vs held-out domain compliance scores",
            label="tab:ws5-heldout",
        )


# ===================================================================
# Main
# ===================================================================


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="WS-5: Contamination Probe for CGA-Bench")
    parser.add_argument(
        "--probe",
        choices=["verbatim", "recall", "novel", "heldout", "all"],
        default="all",
        help="Which probe type to run (default: all)",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM for testing (no API calls)",
    )
    parser.add_argument(
        "--backend",
        choices=["openai", "vllm", "anthropic", "mock"],
        default="openai",
        help="LLM backend (default: openai)",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=None,
        help="Custom endpoint URL (for vLLM)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4",
        help="Model name (default: gpt-4)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: evidence_pack/)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    output_dir = Path(args.output_dir) if args.output_dir else EVIDENCE_DIR
    tables_dir = output_dir / "tables"

    probes = _load_probes()
    provider = _build_provider(args)

    run_probes = set()
    if args.probe == "all":
        run_probes = set(PROBE_TYPES)
    else:
        run_probes.add(args.probe)

    start_time = time.time()

    verbatim_results = None
    constraint_results = None
    novel_results = None
    heldout_result = None

    if "verbatim" in run_probes:
        logger.info("Running Probe 1: Verbatim Recall...")
        verbatim_results = run_verbatim_probe(provider, probes, mock_mode=args.mock_llm)
        logger.info(
            "  -> %d probes, mean char overlap: %.4f",
            len(verbatim_results),
            float(np.mean([v.char_overlap for v in verbatim_results])),
        )

    if "recall" in run_probes:
        logger.info("Running Probe 2: Constraint Recall...")
        constraint_results = run_constraint_recall_probe(provider, mock_mode=args.mock_llm)
        logger.info(
            "  -> %d graphs, mean F1: %.4f",
            len(constraint_results),
            float(np.mean([c.f1 for c in constraint_results])),
        )

    if "novel" in run_probes:
        logger.info("Running Probe 3: Novel Constraint Detection...")
        novel_results = run_novel_constraint_probe(provider, probes, mock_mode=args.mock_llm)
        n_correct = sum(1 for n in novel_results if n.correct)
        logger.info(
            "  -> %d probes, accuracy: %.4f",
            len(novel_results),
            n_correct / len(novel_results) if novel_results else 0.0,
        )

    if "heldout" in run_probes:
        logger.info("Running Probe 4: Held-out Domain Advantage...")
        heldout_result = run_heldout_probe()
        logger.info(
            "  -> known=%.4f, heldout=%.4f, p=%.4f (%s)",
            heldout_result.known_mean,
            heldout_result.heldout_mean,
            heldout_result.p_value,
            heldout_result.data_source,
        )

    elapsed = time.time() - start_time

    # Build reports
    json_report = _build_json_report(
        verbatim_results,
        constraint_results,
        novel_results,
        heldout_result,
        elapsed,
        args,
    )
    md_report = _build_markdown_report(json_report)

    # Save outputs
    save_json(json_report, output_dir / "ws5_contamination.json")
    save_markdown(md_report, output_dir / "ws5_contamination.md")
    _build_latex_tables(json_report, tables_dir)

    logger.info("WS-5 Contamination Probe complete (%.1fs)", elapsed)


if __name__ == "__main__":
    main()
