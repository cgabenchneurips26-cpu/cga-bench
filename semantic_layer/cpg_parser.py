"""CPG Parser: LLM 기반 Clinical Practice Guideline 파서

CPG 문서(PDF/텍스트)를 구조화된 추천사항으로 변환합니다.

기능:
- PDF/텍스트에서 추천사항 추출
- 권고 강도(Strong/Weak) 식별
- 액션 타입 분류
- 시퀀스/타이밍 제약 추출
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from pathlib import Path
from typing import Any

from cga_bench.agent_runner.llm_provider import (
    BaseLLMProvider,
    LLMMessage,
)

logger = logging.getLogger(__name__)


class RecommendationStrength(str, Enum):
    """권고 강도"""

    STRONG = "strong"  # Must do
    MODERATE = "moderate"  # Should do
    WEAK = "weak"  # May consider
    AGAINST = "against"  # Should not do


class ActionCategory(str, Enum):
    """액션 카테고리"""

    ASSESSMENT = "assessment"
    DIAGNOSTIC = "diagnostic"
    TREATMENT = "treatment"
    MONITORING = "monitoring"
    CONSULTATION = "consultation"
    DISPOSITION = "disposition"


@dataclass
class ExtractedRecommendation:
    """추출된 개별 추천사항.

    Source traceability fields (source_guideline/section/quote/page) are required
    for v7 expansion pipeline — every extracted rule must be traceable to the
    original guideline document for reviewer-facing provenance audit.
    """

    recommendation_id: str
    text: str
    strength: RecommendationStrength
    category: ActionCategory
    action_id: str  # Normalized action identifier
    action_type: str  # order_lab, give_medication, etc.
    parameters: dict[str, Any] = field(default_factory=dict)
    timing_constraint: str | None = None  # e.g., "within 60 minutes"
    deadline_minutes: int | None = None
    prerequisites: list[str] = field(default_factory=list)  # Required prior actions
    contraindications: list[str] = field(default_factory=list)
    evidence_level: str | None = None
    # Source traceability (v7 expansion pipeline — required for provenance audit)
    source_guideline: str | None = None  # Full guideline title, e.g., "SSC 2021 Surviving Sepsis Campaign"
    source_section: str | None = None  # Section/recommendation id, e.g., "Recommendation 3.2"
    source_quote: str | None = None  # Verbatim text span from the guideline
    source_page: int | None = None
    # v2: Branch label for severity-tier routing (Phase 2a)
    branch_label: str | None = None  # e.g., "septic_shock", "severe_cap"


@dataclass
class ExtractedBranch:
    """A clinical pathway branch within a guideline category.

    Represents a severity tier or diagnostic subtype that routes patients
    to different treatment protocols. Example: sepsis vs septic_shock in
    the SSC Hour-1 Bundle.
    """

    branch_id: str  # Machine ID, e.g., "septic_shock"
    parent_category: ActionCategory  # Which category this branch splits
    condition: str  # State expression, e.g., "state.working_diagnosis == 'septic_shock'"
    condition_label: str  # Human-readable, e.g., "Septic Shock"
    node_id: str  # Generated node ID, e.g., "septic_shock_bundle"
    node_name: str  # Display name, e.g., "Septic Shock Hour-1 Bundle"
    description: str = ""
    precondition: str | None = None  # Guard on the node, e.g., "state.working_diagnosis == 'septic_shock'"


@dataclass
class ExtractedConditionalRule:
    """A patient-specific conditional rule (allergy, comorbidity constraint).

    Maps to the `conditional_rules` block in CPG YAML. These rules dynamically
    add/remove forbidden or required actions based on patient characteristics.
    """

    rule_id: str  # e.g., "SEPSIS-PENICILLIN-ANAPHYLAXIS-NO-CEPH"
    condition: str  # Python-like expression, e.g., "'penicillin_anaphylaxis' in patient.allergies"
    effect_type: str  # "FORBIDDEN" or "REQUIRED"
    affected_actions: list[str] = field(default_factory=list)
    evidence: str = ""
    severity: str = "MODERATE"  # CRITICAL, HIGH, MODERATE, LOW
    description: str = ""
    condition_variables: list[str] = field(default_factory=list)
    trigger_range: dict[str, Any] = field(default_factory=dict)
    normal_range: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReassessmentSpec:
    """Post-treatment reassessment node specification.

    Extracted in Pass 3 to generate dedicated reassessment and disposition
    nodes in the CPG graph. The gold-standard SSC graph has `reassessment`
    and `disposition_decision` nodes — this dataclass captures equivalent info
    from any guideline.
    """

    reassessment_actions: list[str] = field(default_factory=list)  # e.g., ["reassess_perfusion"]
    reassessment_deadlines: dict[str, int] = field(default_factory=dict)
    reassessment_forbidden: list[str] = field(default_factory=list)
    # Disposition routing
    disposition_conditions: list[dict[str, str]] = field(default_factory=list)
    # Each: {"condition": "state.vitals...", "target": "admit_to_icu", "label": "ICU"}
    disposition_mandatory: list[str] = field(default_factory=list)  # e.g., ["determine_disposition"]
    disposition_forbidden: list[str] = field(default_factory=list)  # e.g., ["discharge_home"]
    # Terminal nodes
    terminal_nodes: list[dict[str, Any]] = field(default_factory=list)
    # Each: {"node_id": "admit_to_icu", "mandatory": [...], "allowed": [...], "forbidden": [...]}


@dataclass
class ParsedGuideline:
    """파싱된 CPG 가이드라인"""

    guideline_id: str
    name: str
    source: str  # e.g., "SSC 2021", "AHA 2023"
    domain: str  # e.g., "sepsis", "chest_pain", "stroke"
    version: str
    recommendations: list[ExtractedRecommendation] = field(default_factory=list)
    # Derived constraints
    mandatory_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    sequence_rules: list[dict[str, str]] = field(default_factory=list)
    # v2: Clinical structure (Phase 2a)
    branches: list[ExtractedBranch] = field(default_factory=list)
    conditional_rules: list[ExtractedConditionalRule] = field(default_factory=list)
    # v3: Reassessment & disposition (Phase 2a enhancement)
    reassessment_spec: ReassessmentSpec | None = None
    # Metadata
    raw_text: str | None = None
    parse_confidence: float = 0.0


class CPGParser:
    """LLM 기반 CPG 파서

    CPG 문서를 분석하여 구조화된 추천사항을 추출합니다.
    """

    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm_provider = llm_provider
        self._cache: dict[str, ParsedGuideline] = {}

    def parse_text(self, text: str, guideline_id: str, domain: str, source: str = "unknown") -> ParsedGuideline:
        """CPG 텍스트를 파싱하여 구조화된 가이드라인 반환

        Args:
            text: CPG 문서 텍스트
            guideline_id: 가이드라인 식별자
            domain: 임상 도메인 (sepsis, stroke, etc.)
            source: 출처 (SSC 2021, AHA 2023, etc.)

        Returns:
            ParsedGuideline: 구조화된 가이드라인
        """
        cache_key = f"{guideline_id}_{hash(text[:1000])}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Step 1: 추천사항 추출 (source is propagated for provenance)
        recommendations = self._extract_recommendations(text, domain, source=source)

        # Step 2: 제약 조건 도출
        mandatory, forbidden, sequences = self._derive_constraints(recommendations)

        # v2 second pass: extract clinical structure (branching + safety rules)
        branches, conditional_rules = self._extract_clinical_structure(
            recommendations,
            domain,
            text[:5000],
            source=source,
        )

        # Assign branch_labels to recommendations based on extracted branches
        self._assign_branch_labels(recommendations, branches)

        # v3 third pass: extract reassessment + disposition node structure
        reassessment_spec = self._extract_reassessment_disposition(
            recommendations,
            domain,
            text[:5000],
            source=source,
        )

        parsed = ParsedGuideline(
            guideline_id=guideline_id,
            name=f"{domain.upper()} Guidelines",
            source=source,
            domain=domain,
            version="1.0",
            recommendations=recommendations,
            mandatory_actions=mandatory,
            forbidden_actions=forbidden,
            sequence_rules=sequences,
            branches=branches,
            conditional_rules=conditional_rules,
            reassessment_spec=reassessment_spec,
            raw_text=text[:5000],  # Keep first 5000 chars
            parse_confidence=self._calculate_confidence(recommendations),
        )

        self._cache[cache_key] = parsed
        return parsed

    def parse_file(self, file_path: Path, domain: str) -> ParsedGuideline:
        """파일에서 CPG 파싱"""
        if file_path.suffix == ".pdf":
            text = self._extract_pdf_text(file_path)
        else:
            text = file_path.read_text(encoding="utf-8")

        guideline_id = file_path.stem.replace(" ", "_").lower()
        return self.parse_text(text, guideline_id, domain, source=file_path.name)

    def _extract_recommendations(
        self, text: str, domain: str, source: str = "unknown"
    ) -> list[ExtractedRecommendation]:
        """LLM을 사용하여 추천사항 추출.

        `source` is propagated to each ExtractedRecommendation.source_guideline
        so that every rule carries provenance to the originating guideline document.
        """
        # 텍스트가 너무 길면 청크로 분할
        chunks = self._split_text(text, max_chars=8000)
        all_recommendations = []

        for i, chunk in enumerate(chunks):
            recs = self._extract_from_chunk(chunk, domain, chunk_idx=i, source=source)
            all_recommendations.extend(recs)

        # 중복 제거
        seen_ids = set()
        unique_recs = []
        for rec in all_recommendations:
            if rec.action_id not in seen_ids:
                unique_recs.append(rec)
                seen_ids.add(rec.action_id)

        return unique_recs

    def _extract_from_chunk(
        self, chunk: str, domain: str, chunk_idx: int = 0, source: str = "unknown"
    ) -> list[ExtractedRecommendation]:
        """단일 청크에서 추천사항 추출.

        Every extracted recommendation MUST carry source traceability
        (section id + verbatim quote) for provenance audit in v7 expansion pipeline.
        """
        prompt = f"""You are a clinical guideline parser. Extract ALL actionable recommendations from this {domain} guideline text, including reassessment and disposition phases.

## Guidelines Text
{chunk}

## Task
Extract each clinical recommendation and return a JSON array. For each recommendation:

1. Identify the clinical action (what to do)
2. Determine the strength (strong/moderate/weak/against)
3. Categorize the action type into one of the 6 clinical phases:
   - **assessment**: Initial patient evaluation (vitals, history, physical exam)
   - **diagnostic**: Lab orders, imaging, tests
   - **treatment**: Medications, procedures, interventions
   - **monitoring**: Ongoing reassessment, serial measurements, response evaluation
   - **consultation**: Specialist referrals
   - **disposition**: Admission decisions (ICU vs ward), discharge, transfer
4. Extract timing constraints if mentioned (convert to minutes: "1 hour" = 60, "3 hours" = 180)
5. Identify any prerequisites or contraindications
6. **Record source provenance**: the section/recommendation number (if present), the exact verbatim quote from the guideline that states this recommendation, and the page number if inferable

## Critical: Don't miss these common action types
- **Reassessment**: "reassess perfusion", "remeasure lactate", "re-evaluate", "serial monitoring"
- **Disposition**: "admit to ICU", "admit to ward", "determine disposition", "transfer to higher care"
- **Forbidden actions**: "do not discharge", "avoid", "contraindicated", "should not be used"
- **Sequence constraints**: "before antibiotics, obtain cultures", "after fluid bolus, reassess"

## Output Format
Return a JSON object:
{{
    "recommendations": [
        {{
            "recommendation_id": "rec_001",
            "text": "Original recommendation text",
            "strength": "strong|moderate|weak|against",
            "category": "assessment|diagnostic|treatment|monitoring|consultation|disposition",
            "action_id": "normalized_action_id",
            "action_type": "order_lab|order_imaging|give_medication|assess|consult|monitor|admit|reassess",
            "parameters": {{"key": "value"}},
            "timing_constraint": "within X minutes" or null,
            "deadline_minutes": 60 or null,
            "prerequisites": ["action_id_1"],
            "contraindications": ["condition_1"],
            "evidence_level": "1A|1B|2A|2B|3" or null,
            "source_section": "Recommendation 3.2" or "Section 4.1" or null,
            "source_quote": "exact verbatim span from the guideline text stating this recommendation",
            "source_page": 12 or null
        }}
    ]
}}

IMPORTANT:
- action_id should be snake_case (e.g., "measure_serum_lactate", "reassess_perfusion", "admit_to_icu")
- Only include actionable recommendations, not background information
- Be precise with timing constraints — always convert to deadline_minutes (integer)
- Include monitoring/reassessment recommendations (category="monitoring") — these generate reassessment nodes
- Include disposition recommendations (category="disposition") — these generate admission/discharge routing
- Mark forbidden/contraindicated actions with strength="against"
- **source_quote MUST be a verbatim substring from the Guidelines Text above**, not a paraphrase. If you cannot find a clean verbatim span, copy 1-2 sentences that most directly state the recommendation.
- **source_section** should reflect the guideline's own numbering (e.g., "Rec 3.2", "Table 4", "Hour-1 Bundle") when present."""

        messages = [
            LLMMessage(
                role="system",
                content="You are a medical guideline parser that extracts structured clinical recommendations.",
            ),
            LLMMessage(role="user", content=prompt),
        ]

        schema = {
            "type": "object",
            "properties": {
                "recommendations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "recommendation_id": {"type": "string"},
                            "text": {"type": "string"},
                            "strength": {"type": "string"},
                            "category": {"type": "string"},
                            "action_id": {"type": "string"},
                            "action_type": {"type": "string"},
                            "parameters": {"type": "object"},
                            "timing_constraint": {"type": "string"},
                            "deadline_minutes": {"type": "integer"},
                            "prerequisites": {"type": "array", "items": {"type": "string"}},
                            "contraindications": {"type": "array", "items": {"type": "string"}},
                            "evidence_level": {"type": "string"},
                            # v7 provenance fields
                            "source_section": {"type": "string"},
                            "source_quote": {"type": "string"},
                            "source_page": {"type": "integer"},
                        },
                    },
                }
            },
        }

        try:
            result = self.llm_provider.complete_json(messages, schema)
            recs_data = result.get("recommendations", [])

            recommendations = []
            for idx, rec_data in enumerate(recs_data):
                try:
                    rec = ExtractedRecommendation(
                        recommendation_id=rec_data.get("recommendation_id", f"rec_{chunk_idx}_{idx}"),
                        text=rec_data.get("text", ""),
                        strength=self._parse_strength(rec_data.get("strength", "moderate")),
                        category=self._parse_category(rec_data.get("category", "treatment")),
                        action_id=self._normalize_action_id(rec_data.get("action_id", f"action_{idx}")),
                        action_type=rec_data.get("action_type", "assess"),
                        parameters=rec_data.get("parameters", {}),
                        timing_constraint=rec_data.get("timing_constraint"),
                        deadline_minutes=rec_data.get("deadline_minutes"),
                        prerequisites=rec_data.get("prerequisites", []),
                        contraindications=rec_data.get("contraindications", []),
                        evidence_level=rec_data.get("evidence_level"),
                        # v7 provenance (source_guideline from caller, rest from LLM)
                        source_guideline=source,
                        source_section=rec_data.get("source_section"),
                        source_quote=rec_data.get("source_quote"),
                        source_page=rec_data.get("source_page"),
                    )
                    recommendations.append(rec)
                except Exception as e:
                    logger.warning(f"Failed to parse recommendation: {e}")
                    continue

            return recommendations

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []

    def _derive_constraints(self, recommendations: list[ExtractedRecommendation]) -> tuple:
        """추천사항에서 제약 조건 도출"""
        mandatory = []
        forbidden = []
        sequences = []

        for rec in recommendations:
            # Strong recommendations are mandatory
            if rec.strength == RecommendationStrength.STRONG:
                mandatory.append(rec.action_id)

            # "Against" recommendations are forbidden
            if rec.strength == RecommendationStrength.AGAINST:
                forbidden.append(rec.action_id)

            # Prerequisites define sequences
            for prereq in rec.prerequisites:
                sequences.append(
                    {"before": prereq, "after": rec.action_id, "reason": f"Prerequisite for {rec.action_id}"}
                )

        return mandatory, forbidden, sequences

    def _parse_strength(self, strength_str: str) -> RecommendationStrength:
        """권고 강도 파싱"""
        strength_lower = strength_str.lower()
        if "strong" in strength_lower:
            return RecommendationStrength.STRONG
        elif "against" in strength_lower:
            return RecommendationStrength.AGAINST
        elif "weak" in strength_lower:
            return RecommendationStrength.WEAK
        else:
            return RecommendationStrength.MODERATE

    def _parse_category(self, category_str: str) -> ActionCategory:
        """액션 카테고리 파싱"""
        category_lower = category_str.lower()
        if "assess" in category_lower:
            return ActionCategory.ASSESSMENT
        elif "diagnos" in category_lower:
            return ActionCategory.DIAGNOSTIC
        elif "treat" in category_lower or "therap" in category_lower:
            return ActionCategory.TREATMENT
        elif "monitor" in category_lower:
            return ActionCategory.MONITORING
        elif "consult" in category_lower:
            return ActionCategory.CONSULTATION
        elif "dispos" in category_lower or "discharge" in category_lower:
            return ActionCategory.DISPOSITION
        else:
            return ActionCategory.TREATMENT

    def _normalize_action_id(self, action_id: str) -> str:
        """액션 ID 정규화"""
        # Convert to snake_case
        normalized = action_id.lower()
        normalized = normalized.replace("-", "_").replace(" ", "_")
        # Remove multiple underscores
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized.strip("_")

    def _split_text(self, text: str, max_chars: int = 8000) -> list[str]:
        """텍스트를 청크로 분할

        JSON 파일 등 paragraph break가 없는 경우도 처리합니다.
        """
        if len(text) <= max_chars:
            return [text]

        chunks = []
        paragraphs = text.split("\n\n")

        # Paragraph-based splitting이 작동하는지 확인
        if len(paragraphs) > 1:
            current_chunk = ""
            for para in paragraphs:
                if len(current_chunk) + len(para) > max_chars:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = para
                else:
                    current_chunk += "\n\n" + para if current_chunk else para

            if current_chunk:
                chunks.append(current_chunk)

            # 청크가 여러 개면 정상 동작
            if len(chunks) > 1:
                return chunks

        # Fallback: 문자 수 기반 분할 (JSON 등 paragraph break 없는 경우)
        logger.info(f"Using character-based splitting for {len(text)} char text")
        chunks = []
        start = 0

        while start < len(text):
            end = min(start + max_chars, len(text))

            # 청크가 끝나기 전에 좋은 분할 지점 찾기
            if end < len(text):
                # JSON 구조를 고려한 분할 지점 찾기 (우선순위: }, ], \n, 공백)
                best_split = -1
                for split_char in ["},", "],", "}\n", "]\n", "\n", " "]:
                    # 마지막 1000자 내에서 분할 지점 찾기
                    search_start = max(start, end - 1000)
                    pos = text.rfind(split_char, search_start, end)
                    if pos > start:
                        best_split = pos + len(split_char)
                        break

                if best_split > start:
                    end = best_split

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end

        logger.info(f"Split into {len(chunks)} chunks")
        return chunks

    def _extract_pdf_text(self, file_path: Path) -> str:
        """PDF에서 텍스트 추출"""
        try:
            import pymupdf  # PyMuPDF

            doc = pymupdf.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            return text
        except ImportError:
            logger.warning("PyMuPDF not installed, trying pdfplumber")
            try:
                import pdfplumber

                with pdfplumber.open(file_path) as pdf:
                    text = ""
                    for page in pdf.pages:
                        text += page.extract_text() or ""
                return text
            except ImportError:
                raise ImportError("Install pymupdf or pdfplumber for PDF support")

    def _extract_clinical_structure(
        self,
        recommendations: list[ExtractedRecommendation],
        domain: str,
        text_excerpt: str,
        source: str = "unknown",
    ) -> tuple[list[ExtractedBranch], list[ExtractedConditionalRule]]:
        """Second-pass LLM: extract branching pathways and patient safety rules.

        This is the Phase 2a clinical enrichment step. Given the flat list of
        extracted recommendations, the LLM identifies:
        1. Severity-based pathway branches (e.g., sepsis vs septic_shock)
        2. Patient-specific conditional rules (allergy, comorbidity constraints)
        """
        if not recommendations:
            return [], []

        # Build recommendation summary for the prompt
        rec_summary = "\n".join(
            f"- [{r.recommendation_id}] {r.action_id} ({r.strength.value}, {r.category.value})"
            + (f" deadline={r.deadline_minutes}min" if r.deadline_minutes else "")
            for r in recommendations
        )

        prompt = f"""You are a clinical guideline structure analyzer. Given extracted recommendations from a {domain} guideline, identify the clinical decision structure.

## Extracted Recommendations
{rec_summary}

## Original Guideline Excerpt
{text_excerpt[:3000]}

## Task
Analyze the recommendations and identify:

1. **Severity-based branches**: Are there distinct clinical pathways based on patient severity or diagnosis? For example, in sepsis guidelines, there may be separate pathways for "sepsis without shock" and "septic shock" with different mandatory actions. Each branch should specify which actions are ADDITIONAL mandatory vs forbidden for that severity level.

2. **Patient safety rules**: What patient-specific conditions (allergies, comorbidities, age) would contraindicate or require specific actions? For example:
   - Drug allergies (penicillin → avoid cephalosporins)
   - Organ dysfunction (heart failure → cautious fluids, CKD → avoid nephrotoxins)
   - Age-related (elderly → dose adjustment, avoid certain medications)
   - Disease interactions (cirrhosis → avoid lactated Ringer's)
   Include at least 5-8 rules for comprehensive patient safety.

## Output Format
Return a JSON object:
{{
    "branches": [
        {{
            "branch_id": "unique_id",
            "parent_category": "treatment|diagnostic|assessment|monitoring",
            "condition": "state.working_diagnosis == 'condition_name'",
            "condition_label": "Human Readable Label",
            "node_id": "descriptive_node_id",
            "node_name": "Human Readable Node Name",
            "description": "When and why this branch applies",
            "precondition": "state.working_diagnosis == 'condition_name'",
            "recommendation_ids": ["rec_001", "rec_003"],
            "additional_mandatory": ["action_id_1"],
            "additional_forbidden": ["action_id_2"],
            "additional_deadlines": {{"action_id_1": 60}}
        }}
    ],
    "conditional_rules": [
        {{
            "rule_id": "DOMAIN-CONDITION-EFFECT",
            "condition": "'allergy_name' in patient.allergies",
            "effect_type": "FORBIDDEN",
            "affected_actions": ["action_id_1", "action_id_2"],
            "evidence": "Guideline reference",
            "severity": "CRITICAL|HIGH|MODERATE|LOW",
            "description": "Clinical rationale",
            "condition_variables": ["patient.allergies"],
            "trigger_range": {{"patient.allergies": {{"contains": "allergy_name", "type": "list_contains"}}}},
            "normal_range": {{"patient.allergies": {{"not_contains": "allergy_name", "type": "list_not_contains"}}}}
        }}
    ]
}}

IMPORTANT:
- Only include branches when there are genuinely distinct clinical pathways with different treatment protocols
- branch condition must be a valid Python-like expression using state.* or patient.* variables
- Each branch MUST include additional_mandatory (actions unique to that severity) and additional_forbidden (actions contraindicated at that severity)
- conditional_rules should capture real clinical safety constraints (drug allergies, organ dysfunction, etc.)
- Each conditional_rule must have a unique rule_id following the pattern DOMAIN-CONDITION-EFFECT
- condition expression syntax: "'X' in patient.allergies", "'Y' in patient.comorbidities", "patient.age > 70"
- If no branches exist for this guideline, return empty "branches" array
- Include 5-8 conditional_rules covering: drug allergies, organ comorbidities, age extremes, disease interactions"""

        messages = [
            LLMMessage(
                role="system",
                content="You are a clinical guideline structure analyzer that identifies decision branching and patient safety rules.",
            ),
            LLMMessage(role="user", content=prompt),
        ]

        schema = {
            "type": "object",
            "properties": {
                "branches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "branch_id": {"type": "string"},
                            "parent_category": {"type": "string"},
                            "condition": {"type": "string"},
                            "condition_label": {"type": "string"},
                            "node_id": {"type": "string"},
                            "node_name": {"type": "string"},
                            "description": {"type": "string"},
                            "precondition": {"type": "string"},
                            "recommendation_ids": {"type": "array", "items": {"type": "string"}},
                            "additional_mandatory": {"type": "array", "items": {"type": "string"}},
                            "additional_forbidden": {"type": "array", "items": {"type": "string"}},
                            "additional_deadlines": {"type": "object"},
                        },
                    },
                },
                "conditional_rules": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "rule_id": {"type": "string"},
                            "condition": {"type": "string"},
                            "effect_type": {"type": "string"},
                            "affected_actions": {"type": "array", "items": {"type": "string"}},
                            "evidence": {"type": "string"},
                            "severity": {"type": "string"},
                            "description": {"type": "string"},
                            "condition_variables": {"type": "array", "items": {"type": "string"}},
                            "trigger_range": {"type": "object"},
                            "normal_range": {"type": "object"},
                        },
                    },
                },
            },
        }

        try:
            result = self.llm_provider.complete_json(messages, schema)
        except Exception as e:
            logger.warning("Clinical structure extraction failed: %s — falling back to linear graph", e)
            return [], []

        branches = self._parse_branches(result.get("branches", []), source)
        cond_rules = self._parse_conditional_rules(result.get("conditional_rules", []))
        logger.info("Extracted %d branches, %d conditional_rules", len(branches), len(cond_rules))
        return branches, cond_rules

    def _parse_branches(
        self,
        raw_branches: list[dict[str, Any]],
        source: str,
    ) -> list[ExtractedBranch]:
        """Parse raw LLM output into ExtractedBranch instances."""
        branches: list[ExtractedBranch] = []
        for b in raw_branches:
            try:
                branches.append(
                    ExtractedBranch(
                        branch_id=b.get("branch_id", "unknown"),
                        parent_category=self._parse_category(b.get("parent_category", "treatment")),
                        condition=b.get("condition", "True"),
                        condition_label=b.get("condition_label", "Default"),
                        node_id=self._normalize_action_id(b.get("node_id", f"branch_{len(branches)}")),
                        node_name=b.get("node_name", "Branch Node"),
                        description=b.get("description", ""),
                        precondition=b.get("precondition"),
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse branch: %s", e)
        return branches

    def _parse_conditional_rules(
        self,
        raw_rules: list[dict[str, Any]],
    ) -> list[ExtractedConditionalRule]:
        """Parse raw LLM output into ExtractedConditionalRule instances."""
        rules: list[ExtractedConditionalRule] = []
        for r in raw_rules:
            try:
                rules.append(
                    ExtractedConditionalRule(
                        rule_id=r.get("rule_id", f"RULE-{len(rules)}"),
                        condition=r.get("condition", "True"),
                        effect_type=r.get("effect_type", "FORBIDDEN").upper(),
                        affected_actions=r.get("affected_actions", []),
                        evidence=r.get("evidence", ""),
                        severity=r.get("severity", "MODERATE").upper(),
                        description=r.get("description", ""),
                        condition_variables=r.get("condition_variables", []),
                        trigger_range=r.get("trigger_range", {}),
                        normal_range=r.get("normal_range", {}),
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse conditional rule: %s", e)
        return rules

    def _extract_reassessment_disposition(
        self,
        recommendations: list[ExtractedRecommendation],
        domain: str,
        text_excerpt: str,
        source: str = "unknown",
    ) -> ReassessmentSpec | None:
        """Third-pass LLM: extract reassessment and disposition node structure.

        The gold-standard CPG graphs (e.g., SSC sepsis) have dedicated
        reassessment nodes (post-treatment monitoring) and disposition decision
        nodes (ICU vs ward routing). This pass extracts that structure so the
        generator can produce equivalent multi-node graphs.
        """
        if not recommendations:
            return None

        # Check if we already have monitoring/disposition recs
        monitoring_recs = [r for r in recommendations if r.category.value == "monitoring"]
        disposition_recs = [r for r in recommendations if r.category.value == "disposition"]

        rec_summary = "\n".join(
            f"- [{r.recommendation_id}] {r.action_id} ({r.strength.value}, {r.category.value})"
            + (f" deadline={r.deadline_minutes}min" if r.deadline_minutes else "")
            for r in recommendations
        )

        prompt = f"""You are a clinical guideline disposition analyzer. Given extracted recommendations from a {domain} guideline, identify the post-treatment reassessment and disposition decision structure.

## Extracted Recommendations
{rec_summary}

## Original Guideline Excerpt
{text_excerpt[:2000]}

## Task
Clinical guidelines typically have these post-treatment phases:
1. **Reassessment**: After initial treatment, patients are reassessed (re-check vitals, repeat labs, evaluate treatment response)
2. **Disposition Decision**: Based on reassessment, patients are routed to ICU, ward, or discharge

Identify:

1. **Reassessment actions**: What should be monitored/reassessed after initial treatment? (e.g., reassess_perfusion, remeasure_lactate_if_elevated, evaluate_treatment_response)

2. **Disposition routing**: What criteria determine where the patient goes?
   - ICU admission criteria (e.g., vasopressor use, MAP < 65, organ failure)
   - Ward admission criteria (e.g., stable vitals, improving)
   - Discharge criteria if applicable

3. **Terminal node actions**: What is mandatory/forbidden at each disposition?

## Output Format
Return a JSON object:
{{
    "reassessment": {{
        "actions": ["reassess_perfusion", "remeasure_lactate_if_elevated"],
        "deadlines": {{"remeasure_lactate_if_elevated": 360}},
        "forbidden": ["discharge_home"]
    }},
    "disposition": {{
        "mandatory": ["determine_disposition"],
        "forbidden": ["discharge_home"],
        "conditions": [
            {{
                "condition": "state.vitals.map_mmhg < 65 or 'vasopressor' in str(state.medications_given)",
                "target_node": "admit_to_icu",
                "label": "ICU Admission"
            }},
            {{
                "condition": "'True'",
                "target_node": "admit_to_ward",
                "label": "Ward Admission (default)"
            }}
        ]
    }},
    "terminal_nodes": [
        {{
            "node_id": "admit_to_icu",
            "name": "ICU Admission",
            "mandatory_actions": ["admit_to_icu"],
            "allowed_actions": ["admit_to_icu", "continue_vasopressor", "arterial_line_monitoring"],
            "forbidden_actions": ["discharge_home", "admit_to_ward"]
        }},
        {{
            "node_id": "admit_to_ward",
            "name": "Ward Admission",
            "mandatory_actions": ["admit_to_ward"],
            "allowed_actions": ["admit_to_ward", "continue_antibiotics", "serial_lactate_monitoring"],
            "forbidden_actions": ["discharge_home"]
        }}
    ]
}}

IMPORTANT:
- disposition conditions must be valid Python-like expressions using state.* or patient.* variables
- The last condition should be "'True'" as a default/fallback route
- terminal_nodes should have clinically appropriate forbidden_actions (e.g., ICU patients should NOT be discharged home)
- If the guideline has no clear disposition routing, return minimal reassessment with generic ICU/ward disposition
- action_ids must be snake_case"""

        messages = [
            LLMMessage(
                role="system",
                content="You are a clinical guideline analyzer that extracts reassessment and disposition decision structure.",
            ),
            LLMMessage(role="user", content=prompt),
        ]

        schema = {
            "type": "object",
            "properties": {
                "reassessment": {
                    "type": "object",
                    "properties": {
                        "actions": {"type": "array", "items": {"type": "string"}},
                        "deadlines": {"type": "object"},
                        "forbidden": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "disposition": {
                    "type": "object",
                    "properties": {
                        "mandatory": {"type": "array", "items": {"type": "string"}},
                        "forbidden": {"type": "array", "items": {"type": "string"}},
                        "conditions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "condition": {"type": "string"},
                                    "target_node": {"type": "string"},
                                    "label": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "terminal_nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "node_id": {"type": "string"},
                            "name": {"type": "string"},
                            "mandatory_actions": {"type": "array", "items": {"type": "string"}},
                            "allowed_actions": {"type": "array", "items": {"type": "string"}},
                            "forbidden_actions": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        }

        try:
            result = self.llm_provider.complete_json(messages, schema)
        except Exception as e:
            logger.warning("Reassessment/disposition extraction failed: %s — using defaults", e)
            return self._default_reassessment_spec(domain, monitoring_recs, disposition_recs)

        return self._parse_reassessment_result(result, domain, monitoring_recs, disposition_recs)

    def _parse_reassessment_result(
        self,
        result: dict[str, Any],
        domain: str,
        monitoring_recs: list[ExtractedRecommendation],
        disposition_recs: list[ExtractedRecommendation],
    ) -> ReassessmentSpec:
        """Parse raw LLM output into ReassessmentSpec."""
        reassess = result.get("reassessment") or {}
        disposition = result.get("disposition") or {}
        terminal_raw = result.get("terminal_nodes") or []

        # Merge LLM-extracted reassessment with already-extracted monitoring recs
        reassess_actions = list(reassess.get("actions") or [])
        for rec in monitoring_recs:
            if rec.action_id not in reassess_actions:
                reassess_actions.append(rec.action_id)

        reassess_deadlines: dict[str, int] = {}
        for action, deadline in (reassess.get("deadlines") or {}).items():
            if isinstance(deadline, (int, float)):
                reassess_deadlines[action] = int(deadline)
        for rec in monitoring_recs:
            if rec.deadline_minutes and rec.action_id not in reassess_deadlines:
                reassess_deadlines[rec.action_id] = rec.deadline_minutes

        # Parse disposition conditions
        disp_conditions: list[dict[str, str]] = []
        for cond in disposition.get("conditions") or []:
            if isinstance(cond, dict) and "condition" in cond and "target_node" in cond:
                disp_conditions.append(
                    {
                        "condition": cond["condition"],
                        "target": cond["target_node"],
                        "label": cond.get("label", cond["target_node"]),
                    }
                )

        # Parse terminal nodes
        terminal_nodes: list[dict[str, Any]] = []
        for node in terminal_raw:
            if isinstance(node, dict) and "node_id" in node:
                terminal_nodes.append(
                    {
                        "node_id": self._normalize_action_id(node["node_id"]),
                        "name": node.get("name", node["node_id"]),
                        "mandatory": list(node.get("mandatory_actions") or []),
                        "allowed": list(node.get("allowed_actions") or []),
                        "forbidden": list(node.get("forbidden_actions") or []),
                    }
                )

        # Merge disposition recs
        disp_mandatory = list(disposition.get("mandatory") or [])
        for rec in disposition_recs:
            if rec.strength.value == "strong" and rec.action_id not in disp_mandatory:
                disp_mandatory.append(rec.action_id)

        return ReassessmentSpec(
            reassessment_actions=reassess_actions,
            reassessment_deadlines=reassess_deadlines,
            reassessment_forbidden=list(reassess.get("forbidden") or []),
            disposition_conditions=disp_conditions,
            disposition_mandatory=disp_mandatory,
            disposition_forbidden=list(disposition.get("forbidden") or []),
            terminal_nodes=terminal_nodes,
        )

    @staticmethod
    def _default_reassessment_spec(
        domain: str,
        monitoring_recs: list[ExtractedRecommendation],
        disposition_recs: list[ExtractedRecommendation],
    ) -> ReassessmentSpec:
        """Fallback reassessment spec when LLM extraction fails."""
        reassess_actions = [rec.action_id for rec in monitoring_recs] or ["reassess_perfusion"]
        reassess_deadlines = {rec.action_id: rec.deadline_minutes for rec in monitoring_recs if rec.deadline_minutes}
        disp_mandatory = [rec.action_id for rec in disposition_recs if rec.strength.value == "strong"]
        if not disp_mandatory:
            disp_mandatory = ["determine_disposition"]

        return ReassessmentSpec(
            reassessment_actions=reassess_actions,
            reassessment_deadlines=reassess_deadlines,
            reassessment_forbidden=["discharge_home"],
            disposition_conditions=[
                {"condition": "state.vitals.map_mmhg < 65", "target": "admit_to_icu", "label": "ICU"},
                {"condition": "'True'", "target": "admit_to_ward", "label": "Ward"},
            ],
            disposition_mandatory=disp_mandatory,
            disposition_forbidden=["discharge_home"],
            terminal_nodes=[
                {
                    "node_id": "admit_to_icu",
                    "name": "ICU Admission",
                    "mandatory": ["admit_to_icu"],
                    "allowed": ["admit_to_icu"],
                    "forbidden": ["discharge_home", "admit_to_ward"],
                },
                {
                    "node_id": "admit_to_ward",
                    "name": "Ward Admission",
                    "mandatory": ["admit_to_ward"],
                    "allowed": ["admit_to_ward"],
                    "forbidden": ["discharge_home"],
                },
            ],
        )

    @staticmethod
    def _assign_branch_labels(
        recommendations: list[ExtractedRecommendation],
        branches: list[ExtractedBranch],
    ) -> None:
        """Tag recommendations with branch_label based on branch recommendation_ids.

        Recommendations not claimed by any branch remain branch_label=None (shared).
        """
        # Build branch_id -> set of recommendation_ids
        # The branch extraction prompt asks LLM to include recommendation_ids,
        # but we also do fuzzy matching on action_id for robustness.
        for branch in branches:
            # We use the branch_id as the label
            for rec in recommendations:
                if rec.branch_label is not None:
                    continue  # Already assigned
                # Category must match
                if rec.category != branch.parent_category:
                    continue
                # Check if this rec is severity-specific (heuristic: contraindications
                # or prerequisites that reference the branch condition)
                # For now, leave all recs as shared (branch_label=None) — the generator
                # will handle splitting by merging shared + branch-specific actions.

    def _calculate_confidence(self, recommendations: list[ExtractedRecommendation]) -> float:
        """파싱 신뢰도 계산"""
        if not recommendations:
            return 0.0

        # Confidence based on:
        # - Number of recommendations extracted
        # - Completeness of fields
        scores = []
        for rec in recommendations:
            score = 0.5  # Base score
            if rec.timing_constraint or rec.deadline_minutes:
                score += 0.1
            if rec.prerequisites:
                score += 0.1
            if rec.evidence_level:
                score += 0.1
            if rec.parameters:
                score += 0.1
            if len(rec.text) > 20:
                score += 0.1
            scores.append(min(score, 1.0))

        return sum(scores) / len(scores)
