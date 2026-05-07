#!/usr/bin/env python3
"""YAML CPG 그래프에서 RAG parsed.json 파일 생성.

각 그래프의 노드 정보(mandatory_actions, forbidden_actions, deadlines,
source_quote, description, conditional_rules)를 추출하여
CPGDocumentStore가 인덱싱할 수 있는 parsed.json 형식으로 변환한다.

Usage:
    PYTHONPATH=. python scripts/generate_rag_from_graphs.py
"""

import json
from pathlib import Path
from typing import Any

import yaml

GRAPH_DIR = Path("cpg_model/graphs")
OUTPUT_DIR = Path("cpg_sources")

# graph_id → parsed.json 파일명 매핑
GRAPH_TO_FILENAME: dict[str, str] = {
    "ssc_sepsis_hour1_bundle": "SSC-2021-Sepsis-Hour1-Bundle.parsed.json",
    "aha_chest_pain_evaluation": "AHA-2021-Chest-Pain-Guidelines.parsed.json",
    "kdigo_aki_full": "KDIGO-2012-AKI-Guidelines.parsed.json",
    "aha_heart_failure_2022": "AHA-2022-Heart-Failure-Guidelines.parsed.json",
    "aha_stroke_2019": "AHA-2019-Stroke-Guidelines.parsed.json",
    "ada_dka_management": "ADA-2009-DKA-Management.parsed.json",
    "atrial_fibrillation": "ESC-2020-AF-Guidelines.parsed.json",
    "cap_pneumonia": "ATS-IDSA-2019-CAP-Guidelines.parsed.json",
    "copd_exacerbation": "GOLD-2024-COPD-Report.parsed.json",
    "gi_bleeding": "ACG-2021-GI-Bleeding-Guidelines.parsed.json",
    "hypertensive_emergency": "AHA-2017-Hypertensive-Emergency.parsed.json",
    "kdigo_contrast_aki": "KDIGO-2012-Contrast-AKI.parsed.json",
    "pulmonary_embolism": "ESC-2019-PE-Guidelines.parsed.json",
    "anaphylaxis_management": "WAO-2020-Anaphylaxis-Guidelines.parsed.json",
    "acls_cardiac_arrest": "AHA-2020-ACLS-Guidelines.parsed.json",
    "status_epilepticus": "AES-2016-Status-Epilepticus.parsed.json",
    "gina_asthma_exacerbation": "GINA-2024-Asthma-Exacerbation.parsed.json",
    "idsa_meningitis": "IDSA-2004-Meningitis-Guidelines.parsed.json",
    "toxicology_management": "AACT-Toxicology-Management.parsed.json",
    "aba_burn_resuscitation": "ABA-2018-Burn-Resuscitation.parsed.json",
    "aabb_transfusion": "AABB-2016-Transfusion-Guidelines.parsed.json",
    "acog_obstetric_hemorrhage": "ACOG-2017-Obstetric-Hemorrhage.parsed.json",
    "pals_pediatric_emergency": "AHA-2020-PALS-Guidelines.parsed.json",
    "apa_agitation_management": "APA-2024-Agitation-Management.parsed.json",
    "universal_clinical_safety": "Universal-Clinical-Safety.parsed.json",
}

# 기존 parsed.json 보존 목록 (수동 작성된 고품질 파일)
PRESERVE_EXISTING = {
    "SSC-2021-Sepsis-Hour1-Bundle.parsed.json",
    "AHA-2021-Chest-Pain-Guidelines.parsed.json",
    "KDIGO-2012-AKI-Guidelines.parsed.json",
}


def load_graph(yaml_path: Path) -> dict[str, Any]:
    """YAML 그래프 파일 로드."""
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_metadata(graph: dict[str, Any]) -> dict[str, str]:
    """그래프 메타데이터 추출."""
    meta = graph.get("metadata", {})
    primary = meta.get("primary_source", {})
    return {
        "guideline_name": graph.get("guideline_name", ""),
        "graph_id": graph.get("graph_id", ""),
        "version": graph.get("version", ""),
        "source": meta.get("source", ""),
        "description": meta.get("description", ""),
        "doi": meta.get("doi", primary.get("doi", "")),
        "key_evidence": meta.get("key_evidence", ""),
        "key_recommendation": meta.get("key_recommendation", ""),
    }


def extract_recommendations(graph: dict[str, Any]) -> list[dict[str, str]]:
    """그래프 노드에서 recommendations 추출."""
    recommendations: list[dict[str, str]] = []
    nodes = graph.get("nodes", {})
    if isinstance(nodes, dict):
        nodes = nodes.values()

    graph_id = graph.get("graph_id", "UNKNOWN")
    prefix = graph_id.upper().replace("_", "")[:8]
    rec_idx = 0

    for node in nodes:
        if not isinstance(node, dict):
            continue

        # source_quote가 있으면 최우선 사용 (원문 인용)
        source_quote = node.get("source_quote", "")
        description = node.get("description", "")
        rec_class = node.get("recommendation_class", "")
        evidence = node.get("evidence_level", "")
        source_gl = node.get("source_guideline", "")
        source_sec = node.get("source_section", "")

        # 1) source_quote 기반 recommendation
        if source_quote and len(source_quote) > 20:
            rec_idx += 1
            strength = _classify_strength(rec_class, source_quote)
            recommendations.append(
                {
                    "recommendation_id": f"{prefix}_R{rec_idx}",
                    "text": source_quote.strip(),
                    "strength": strength,
                    "page": node.get("source_page", ""),
                    "source_section": source_sec,
                    "source_guideline": source_gl,
                    "evidence_level": f"Class {rec_class}, Level {evidence}",
                }
            )

        # 2) mandatory actions 기반 recommendation
        mandatory = node.get("mandatory_actions", [])
        deadlines = node.get("deadlines", {})
        if mandatory:
            rec_idx += 1
            action_text = _actions_to_text(mandatory, deadlines, node.get("name", ""))
            recommendations.append(
                {
                    "recommendation_id": f"{prefix}_R{rec_idx}",
                    "text": action_text,
                    "strength": _classify_strength(rec_class, ""),
                    "page": node.get("source_page", ""),
                    "source_section": source_sec,
                    "source_guideline": source_gl,
                    "evidence_level": f"Class {rec_class}, Level {evidence}",
                }
            )

        # 3) forbidden actions 기반 recommendation
        forbidden = node.get("forbidden_actions", [])
        if forbidden:
            rec_idx += 1
            forbidden_text = _forbidden_to_text(forbidden, node.get("name", ""))
            recommendations.append(
                {
                    "recommendation_id": f"{prefix}_R{rec_idx}",
                    "text": forbidden_text,
                    "strength": "strong",
                    "page": node.get("source_page", ""),
                    "source_section": source_sec,
                    "source_guideline": source_gl,
                }
            )

        # 4) conditional rules 기반 recommendations
        for rule in node.get("conditional_rules", []) or []:
            if not isinstance(rule, dict):
                continue
            rule_desc = rule.get("description", "")
            if rule_desc and len(rule_desc) > 15:
                rec_idx += 1
                effect = rule.get("effect", {})
                effect_type = effect.get("type", "")
                effect_actions = effect.get("actions", [])
                severity = rule.get("severity", "")

                rule_text = f"{rule_desc} [{effect_type}: {', '.join(effect_actions)}] (Severity: {severity})"
                recommendations.append(
                    {
                        "recommendation_id": f"{prefix}_R{rec_idx}",
                        "text": rule_text.strip(),
                        "strength": "strong" if severity in ("CRITICAL", "HIGH") else "conditional",
                        "page": "",
                        "source_guideline": rule.get("evidence", source_gl),
                    }
                )

    return recommendations


def extract_tables(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """그래프에서 테이블 데이터 추출 (deadlines, action summaries)."""
    tables: list[dict[str, Any]] = []
    nodes = graph.get("nodes", {})
    if isinstance(nodes, dict):
        nodes_list = list(nodes.values())
    else:
        nodes_list = list(nodes)

    graph_id = graph.get("graph_id", "UNKNOWN")
    prefix = graph_id.upper().replace("_", "")[:8]

    # Table 1: Mandatory Actions with Deadlines
    deadline_rows = [["Node", "Action", "Deadline (minutes)"]]
    for node in nodes_list:
        if not isinstance(node, dict):
            continue
        deadlines = node.get("deadlines", {})
        if not deadlines:
            continue
        node_name = node.get("name", node.get("node_id", ""))
        for action, minutes in deadlines.items():
            deadline_rows.append([node_name, action, str(minutes)])

    if len(deadline_rows) > 1:
        tables.append(
            {
                "table_id": f"{prefix}_T1",
                "title": "Time-Critical Actions and Deadlines",
                "data": deadline_rows,
                "page": "",
            }
        )

    # Table 2: Forbidden Actions Summary
    forbidden_rows = [["Node", "Forbidden Action", "Rationale"]]
    for node in nodes_list:
        if not isinstance(node, dict):
            continue
        forbidden = node.get("forbidden_actions", [])
        if not forbidden:
            continue
        node_name = node.get("name", node.get("node_id", ""))
        for action in forbidden:
            forbidden_rows.append([node_name, action, "Contraindicated per guideline"])

    if len(forbidden_rows) > 1:
        tables.append(
            {
                "table_id": f"{prefix}_T2",
                "title": "Forbidden/Contraindicated Actions",
                "data": forbidden_rows,
                "page": "",
            }
        )

    # Table 3: Sequence Requirements
    seq_rows = [["Node", "Must Precede", "Must Follow"]]
    for node in nodes_list:
        if not isinstance(node, dict):
            continue
        seq_rules = node.get("sequence_rules", [])
        req_prior = node.get("required_prior_actions", {})

        for seq in seq_rules or []:
            if isinstance(seq, list) and len(seq) >= 2:
                seq_rows.append([node.get("name", ""), seq[0], seq[1]])

        if isinstance(req_prior, dict):
            for action, priors in req_prior.items():
                if isinstance(priors, list):
                    for prior in priors:
                        seq_rows.append([node.get("name", ""), prior, action])

    if len(seq_rows) > 1:
        tables.append(
            {
                "table_id": f"{prefix}_T3",
                "title": "Required Action Sequences",
                "data": seq_rows,
                "page": "",
            }
        )

    return tables


def extract_key_sections(graph: dict[str, Any]) -> dict[str, str]:
    """그래프 노드 설명에서 key_sections 생성."""
    sections: dict[str, str] = {}
    meta = graph.get("metadata", {})
    nodes = graph.get("nodes", {})
    if isinstance(nodes, dict):
        nodes_list = list(nodes.values())
    else:
        nodes_list = list(nodes)

    # Section 1: Overview (metadata)
    overview_parts = []
    if meta.get("description"):
        overview_parts.append(meta["description"])
    if meta.get("key_evidence"):
        overview_parts.append(f"Key evidence: {meta['key_evidence']}")
    if meta.get("key_recommendation"):
        overview_parts.append(f"Key recommendation: {meta['key_recommendation']}")
    if overview_parts:
        sections["overview"] = " ".join(overview_parts)[:2000]

    # Sections from nodes (group by node)
    for node in nodes_list:
        if not isinstance(node, dict):
            continue
        node_name = node.get("name", node.get("node_id", ""))
        section_key = node_name.lower().replace(" ", "_").replace("-", "_")[:40]

        parts = []
        if node.get("description"):
            parts.append(node["description"])
        if node.get("source_quote"):
            parts.append(f"Guideline states: {node['source_quote']}")

        # Mandatory actions summary
        mandatory = node.get("mandatory_actions", [])
        if mandatory:
            parts.append(f"Required actions: {', '.join(mandatory)}")

        # Forbidden actions summary
        forbidden = node.get("forbidden_actions", [])
        if forbidden:
            parts.append(f"Contraindicated: {', '.join(forbidden)}")

        # Conditional rules summary
        for rule in node.get("conditional_rules", []) or []:
            if isinstance(rule, dict) and rule.get("description"):
                parts.append(rule["description"])

        if parts:
            sections[section_key] = " ".join(parts)[:2000]

    return sections


def _classify_strength(rec_class: str, text: str) -> str:
    """Recommendation class → strength 변환."""
    rc = str(rec_class).strip().upper()
    if rc in ("I", "1"):
        return "strong"
    elif rc in ("IIA", "2A", "IIB", "2B", "II"):
        return "moderate"
    elif rc in ("III", "3"):
        return "weak"
    # 텍스트 기반 분류 fallback
    text_lower = text.lower()
    if "recommend" in text_lower or "should" in text_lower or "must" in text_lower:
        return "strong"
    if "suggest" in text_lower or "consider" in text_lower or "may" in text_lower:
        return "weak"
    return "strong"


def _actions_to_text(actions: list[str], deadlines: dict[str, int], node_name: str) -> str:
    """Mandatory action 리스트를 자연어 recommendation 텍스트로 변환."""
    parts = [f"For {node_name}, the following actions are mandatory:"]
    for action in actions:
        action_readable = action.replace("_", " ")
        dl = deadlines.get(action)
        if dl:
            parts.append(f"- {action_readable} (within {dl} minutes)")
        else:
            parts.append(f"- {action_readable}")
    return " ".join(parts)


def _forbidden_to_text(forbidden: list[str], node_name: str) -> str:
    """Forbidden action 리스트를 자연어 텍스트로 변환."""
    actions_text = ", ".join(a.replace("_", " ") for a in forbidden)
    return f"During {node_name}, the following actions are contraindicated and must NOT be performed: {actions_text}."


def generate_parsed_json(graph: dict[str, Any]) -> dict[str, Any]:
    """단일 YAML 그래프를 parsed.json으로 변환."""
    meta = extract_metadata(graph)
    recommendations = extract_recommendations(graph)
    tables = extract_tables(graph)
    key_sections = extract_key_sections(graph)

    return {
        "guideline_name": meta["guideline_name"],
        "graph_id": meta["graph_id"],
        "source": meta["source"],
        "doi": meta["doi"],
        "recommendations": recommendations,
        "tables": tables,
        "key_sections": key_sections,
    }


def main() -> None:
    """전체 그래프를 parsed.json으로 변환."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    yaml_files = sorted(GRAPH_DIR.glob("*.yaml"))
    print(f"Found {len(yaml_files)} YAML graph files")

    generated = 0
    skipped = 0
    errors = 0

    for yaml_file in yaml_files:
        graph = load_graph(yaml_file)
        graph_id = graph.get("graph_id", yaml_file.stem)
        filename = GRAPH_TO_FILENAME.get(graph_id)

        if filename is None:
            print(f"  WARN: No filename mapping for {graph_id} — using default")
            filename = f"{graph_id}.parsed.json"

        output_path = OUTPUT_DIR / filename

        # 기존 수동 작성 파일은 보존
        if filename in PRESERVE_EXISTING and output_path.exists():
            print(f"  PRESERVE: {filename} (manually curated)")
            skipped += 1
            continue

        try:
            parsed = generate_parsed_json(graph)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=2, ensure_ascii=False)

            n_recs = len(parsed["recommendations"])
            n_tables = len(parsed["tables"])
            n_sections = len(parsed["key_sections"])
            print(f"  OK: {filename} — {n_recs} recs, {n_tables} tables, {n_sections} sections")
            generated += 1

        except Exception as e:
            print(f"  ERROR: {graph_id} — {e}")
            errors += 1

    print("\n" + "=" * 60)
    print("GENERATION SUMMARY")
    print("=" * 60)
    print(f"Generated: {generated}")
    print(f"Preserved: {skipped}")
    print(f"Errors:    {errors}")
    print(f"Total parsed.json files: {len(list(OUTPUT_DIR.glob('*.parsed.json')))}")


if __name__ == "__main__":
    main()
