"""Action Normalizer: Agent 생성 Action ID를 CPG 표준 형식으로 정규화

문제:
- RAG agent가 생성하는 action_id가 CPG의 allowed_actions와 형식이 다름
- 예: order_blood_culture vs order_lab_blood_culture

해결:
- 패턴 매칭 및 매핑 규칙으로 action_id를 CPG 표준 형식으로 변환
"""

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re

from cga_bench.cpg_model.schemas.base import Action

logger = logging.getLogger(__name__)


@dataclass
class NormalizationRule:
    """정규화 규칙"""

    pattern: str  # 정규식 패턴
    replacement: str  # 대체 문자열 (그룹 참조 가능: \\1, \\2)
    description: str = ""
    priority: int = 0  # 높을수록 먼저 적용


@dataclass
class ActionNormalizerConfig:
    """ActionNormalizer 설정"""

    # 직접 매핑 (정확히 일치하는 경우)
    direct_mappings: dict[str, str] = field(default_factory=dict)

    # 도메인별 직접 매핑 (cpg_id 기반 - 범용 매핑보다 우선)
    domain_specific_mappings: dict[str, dict[str, str]] = field(default_factory=dict)

    # 패턴 기반 규칙 (정규식)
    pattern_rules: list[NormalizationRule] = field(default_factory=list)

    # 동의어 그룹 (같은 의미의 다른 표현들)
    synonym_groups: dict[str, list[str]] = field(default_factory=dict)

    # CPG별 허용 action 목록 (검증용)
    cpg_allowed_actions: dict[str, set[str]] = field(default_factory=dict)


class ActionNormalizer:
    """Action ID 정규화기

    Agent가 생성한 action_id를 CPG 표준 형식으로 변환합니다.
    """

    # Clinical abbreviation expansion table
    ABBREVIATION_MAP: dict[str, str] = {
        "cbc": "complete_blood_count",
        "bmp": "basic_metabolic_panel",
        "cmp": "comprehensive_metabolic_panel",
        "abg": "arterial_blood_gas",
        "cxr": "chest_xray",
        "ct": "computed_tomography",
        "mri": "magnetic_resonance_imaging",
        "ecg": "electrocardiogram",
        "ekg": "electrocardiogram",
        "bnp": "brain_natriuretic_peptide",
        "tsh": "thyroid_stimulating_hormone",
        "ptt": "partial_thromboplastin_time",
        "inr": "international_normalized_ratio",
        "pt": "prothrombin_time",
        "ua": "urinalysis",
        "hba1c": "hemoglobin_a1c",
        "hgb": "hemoglobin",
        "hct": "hematocrit",
        "plt": "platelet_count",
        "wbc": "white_blood_cell_count",
        "rbc": "red_blood_cell_count",
        "ldh": "lactate_dehydrogenase",
        "ck": "creatine_kinase",
        "ast": "aspartate_aminotransferase",
        "alt": "alanine_aminotransferase",
        "gfr": "glomerular_filtration_rate",
        "egfr": "estimated_glomerular_filtration_rate",
        "scr": "serum_creatinine",
        "bun": "blood_urea_nitrogen",
        "sbp": "systolic_blood_pressure",
        "dbp": "diastolic_blood_pressure",
        "map": "mean_arterial_pressure",
        "hr": "heart_rate",
        "rr": "respiratory_rate",
        "spo2": "oxygen_saturation",
        "tpa": "alteplase",
        "ns": "normal_saline",
        "lr": "lactated_ringers",
        "ngt": "nasogastric_tube",
    }

    def __init__(self, config: ActionNormalizerConfig | None = None):
        """Args:
        config: 정규화 설정. None이면 기본 설정 사용
        """
        using_default = config is None
        self.config = config or self._create_default_config()
        # CAV overlay: only extend the default config with external vocabulary.
        # Custom configs (e.g. from tests) are left untouched.
        if using_default:
            self._load_cav_overlay()
        else:
            self._cav_loaded = False
        self._compiled_patterns: list[tuple[re.Pattern, str, int]] = []
        self._compile_patterns()
        # Determinism cache: input → output mapping
        self._cache: dict[str, str] = {}
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        # Track unmapped actions for diagnostics
        self._unmapped_actions: set[str] = set()

    def _load_cav_overlay(self) -> None:
        """Load CAV (Clinical Action Vocabulary) entries as additional
        direct_mappings.  Uses ``CAV_PATH`` env-var or falls back to
        ``cav_v0_6/cav_v0_6.json`` relative to the repo root.

        Existing v6 mappings are preserved via ``setdefault``.
        """
        cav_path_str = os.environ.get("CAV_PATH", "")
        if not cav_path_str:
            repo_root = Path(__file__).resolve().parent.parent
            cav_path = repo_root / "cav_v0_6" / "cav_v0_6.json"
        else:
            cav_path = Path(cav_path_str)

        if not cav_path.is_file():
            logger.debug("CAV overlay not found at %s - skipping", cav_path)
            self._cav_loaded = False
            return

        try:
            cav_data = json.loads(cav_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load CAV overlay from %s: %s", cav_path, exc)
            self._cav_loaded = False
            return

        entries = cav_data.get("entries", {})
        added = 0
        for entry_id, entry in entries.items():
            canonical = entry_id.lower()
            # Register entry key as known canonical (identity mapping)
            if self.config.direct_mappings.setdefault(canonical, canonical) == canonical:
                added += 1
            # Register each raw_form as alias -> canonical
            for raw_form in entry.get("raw_forms", []):
                rf_lower = raw_form.lower().strip()
                if rf_lower and rf_lower != canonical:
                    self.config.direct_mappings.setdefault(rf_lower, canonical)
                    added += 1

        self._cav_loaded = True
        self._cav_entries_count = len(entries)
        self._cav_added_mappings = added
        logger.info(
            "CAV overlay loaded: %d entries, %d new mappings from %s",
            len(entries),
            added,
            cav_path,
        )

    def _compile_patterns(self):
        """패턴 규칙 컴파일"""
        self._compiled_patterns = []
        for rule in sorted(self.config.pattern_rules, key=lambda r: -r.priority):
            try:
                compiled = re.compile(rule.pattern, re.IGNORECASE)
                self._compiled_patterns.append((compiled, rule.replacement, rule.priority))
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{rule.pattern}': {e}")

    def normalize(self, action_id: str, cpg_id: str | None = None) -> str:
        """Action ID 정규화

        Args:
            action_id: 원본 action ID
            cpg_id: CPG 식별자 (도메인별 매핑 우선 적용)

        Returns:
            정규화된 action ID
        """
        if not action_id:
            return action_id

        # Determinism cache lookup
        cache_key = f"{action_id}||{cpg_id or ''}"
        if cache_key in self._cache:
            self._cache_hits += 1
            return self._cache[cache_key]
        self._cache_misses += 1

        normalized = action_id.lower().strip()

        # 0. 도메인별 매핑 우선 체크 (H3 Fix: 도메인 간 충돌 방지)
        if cpg_id and cpg_id in self.config.domain_specific_mappings:
            domain_map = self.config.domain_specific_mappings[cpg_id]
            if normalized in domain_map:
                result = domain_map[normalized]
                logger.debug(f"Domain-specific mapping [{cpg_id}]: {action_id} -> {result}")
                self._cache[cache_key] = result
                return result

        # 1. 범용 직접 매핑 체크
        if normalized in self.config.direct_mappings:
            result = self.config.direct_mappings[normalized]
            logger.debug(f"Direct mapping: {action_id} -> {result}")
            self._cache[cache_key] = result
            return result

        # 1a. Abbreviation expansion (AFTER direct/domain mappings to preserve existing rules)
        normalized = self._expand_abbreviations(normalized)

        # Re-check direct mappings after expansion
        if normalized in self.config.direct_mappings:
            result = self.config.direct_mappings[normalized]
            logger.debug(f"Direct mapping (post-abbrev): {action_id} -> {result}")
            self._cache[cache_key] = result
            return result

        # 2. 동의어 그룹 체크
        for canonical, synonyms in self.config.synonym_groups.items():
            if normalized in [s.lower() for s in synonyms]:
                logger.debug(f"Synonym mapping: {action_id} -> {canonical}")
                self._cache[cache_key] = canonical
                return canonical

        # 3. 패턴 매칭
        for pattern, replacement, _ in self._compiled_patterns:
            if pattern.match(normalized):
                result = pattern.sub(replacement, normalized)
                if result != normalized:
                    logger.debug(f"Pattern mapping: {action_id} -> {result}")
                    self._cache[cache_key] = result
                    return result

        # 4. CPG 허용 목록에서 유사도 기반 매칭
        if cpg_id and cpg_id in self.config.cpg_allowed_actions:
            allowed = self.config.cpg_allowed_actions[cpg_id]
            best_match = self._find_best_match(normalized, allowed)
            if best_match:
                logger.debug(f"Fuzzy mapping: {action_id} -> {best_match}")
                self._cache[cache_key] = best_match
                return best_match

        # No mapping found — track as unmapped for diagnostics
        # but return the normalized form (without prefix) so downstream
        # components (ViolationExtractor, CPGEngine) can still compare
        # against mandatory/forbidden/allowed action sets.
        self._unmapped_actions.add(normalized)
        logger.debug(f"No mapping found (unmapped): {action_id} -> {normalized}")
        self._cache[cache_key] = normalized
        return normalized

    def _expand_abbreviations(self, text: str) -> str:
        """Expand clinical abbreviations in action text.

        Replaces known abbreviations with full forms.
        E.g., "order_lab_cbc" → "order_lab_complete_blood_count"
        """
        parts = text.split("_")
        expanded = []
        for part in parts:
            if part in self.ABBREVIATION_MAP:
                expanded.append(self.ABBREVIATION_MAP[part])
            else:
                expanded.append(part)
        result = "_".join(expanded)
        if result != text:
            logger.debug(f"Abbreviation expansion: {text} -> {result}")
        return result

    def decompose_composite(self, text: str) -> list[str]:
        """Decompose composite actions into individual canonical actions.

        E.g., "order cbc and bmp" → ["order_lab_complete_blood_count", "order_lab_basic_metabolic_panel"]
        """
        # Normalize separators
        cleaned = text.lower().strip()
        cleaned = re.sub(r"\s+", "_", cleaned)

        # Split on "_and_" or "_&_"
        parts = re.split(r"_(?:and|&)_", cleaned)
        if len(parts) <= 1:
            return [self.normalize(text)]

        # Infer prefix from first part
        prefix = ""
        first = parts[0]
        if first.startswith("order_"):
            prefix = "order_"
            parts[0] = first[len("order_") :]

        results = []
        for part in parts:
            action = f"{prefix}{part}" if prefix and not part.startswith(prefix) else part
            results.append(self.normalize(action))
        return results

    def get_diagnostics(self) -> dict[str, any]:
        """Return cache diagnostics for monitoring.

        Returns:
            dict with cache_size, hits, misses, hit_rate.
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0
        return {
            "cache_size": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
            "unmapped_count": len(self._unmapped_actions),
            "unmapped_actions": sorted(self._unmapped_actions),
        }

    def normalize_action(self, action: Action, cpg_id: str | None = None) -> Action:
        """Action 객체의 action_id 정규화

        Args:
            action: 원본 Action
            cpg_id: CPG 식별자

        Returns:
            정규화된 action_id를 가진 새 Action
        """
        normalized_id = self.normalize(action.action_id, cpg_id)

        # action_id가 변경되지 않았으면 원본 반환
        if normalized_id == action.action_id:
            return action

        # 새 Action 생성 (불변성 유지)
        return Action(
            type=action.type,
            action_id=normalized_id,
            args=action.args.copy(),
            timestamp_minutes=action.timestamp_minutes,
            justification=action.justification,
        )

    def normalize_actions(self, actions: list[Action], cpg_id: str | None = None) -> list[Action]:
        """Action 목록 정규화

        Args:
            actions: 원본 Action 목록
            cpg_id: CPG 식별자

        Returns:
            정규화된 Action 목록
        """
        return [self.normalize_action(a, cpg_id) for a in actions]

    def _find_best_match(self, action_id: str, allowed_actions: set[str], threshold: float = 0.7) -> str | None:
        """허용된 action 중 가장 유사한 것 찾기 (Jaccard 유사도)

        Args:
            action_id: 찾을 action ID
            allowed_actions: 허용된 action 집합
            threshold: 최소 유사도 임계값

        Returns:
            가장 유사한 action ID 또는 None
        """

        def tokenize(s: str) -> set[str]:
            return set(re.split(r"[_\s-]+", s.lower()))

        query_tokens = tokenize(action_id)
        best_match = None
        best_score = threshold

        for allowed in allowed_actions:
            allowed_tokens = tokenize(allowed)

            # Jaccard 유사도
            intersection = len(query_tokens & allowed_tokens)
            union = len(query_tokens | allowed_tokens)
            if union == 0:
                continue
            score = intersection / union

            if score > best_score:
                best_score = score
                best_match = allowed

        return best_match

    def are_aliases(self, action_a: str, action_b: str, cpg_id: str | None = None) -> bool:
        """Check if two action IDs resolve to the same canonical form.

        Both sides are normalized through the full pipeline (domain-specific,
        direct mappings, abbreviation expansion, synonyms, patterns).
        Returns True only when canonical forms are identical.
        """
        norm_a = self.normalize(action_a, cpg_id)
        norm_b = self.normalize(action_b, cpg_id)
        return norm_a == norm_b

    @staticmethod
    def _create_default_config() -> ActionNormalizerConfig:
        """기본 정규화 설정 생성"""
        return ActionNormalizerConfig(
            direct_mappings=_DEFAULT_DIRECT_MAPPINGS,
            domain_specific_mappings=_DEFAULT_DOMAIN_SPECIFIC_MAPPINGS,
            pattern_rules=_DEFAULT_PATTERN_RULES,
            synonym_groups=_DEFAULT_SYNONYM_GROUPS,
            cpg_allowed_actions=_DEFAULT_CPG_ALLOWED_ACTIONS,
        )


# ============================================
# 기본 정규화 규칙 정의
# ============================================

_DEFAULT_DIRECT_MAPPINGS: dict[str, str] = {
    # Lab orders - blood culture variations
    "order_blood_culture": "order_lab_blood_culture",
    "blood_culture": "order_lab_blood_culture",
    "get_blood_culture": "order_lab_blood_culture",
    "draw_blood_culture": "order_lab_blood_culture",
    "obtain_blood_cultures": "order_lab_blood_culture",
    "order_blood_cultures": "order_lab_blood_culture",
    "blood_culture_before_antibiotics": "order_lab_blood_culture",  # Sepsis Decision Table 매핑
    # Lab orders - lactate variations
    "order_lactate": "order_lab_lactate",
    "lactate": "order_lab_lactate",
    "get_lactate": "order_lab_lactate",
    "check_lactate": "order_lab_lactate",
    "serum_lactate": "order_lab_lactate",
    "measure_lactate": "order_lab_lactate",  # Sepsis Decision Table 매핑
    # Lab orders - troponin variations
    "order_troponin": "order_lab_troponin",
    "troponin": "order_lab_troponin",
    "check_troponin": "order_lab_troponin",
    "cardiac_enzymes": "order_lab_troponin",
    # Lab orders - CBC variations
    "order_cbc": "order_lab_cbc",
    "cbc": "order_lab_cbc",
    "complete_blood_count": "order_lab_cbc",
    "order_lab_complete_blood_count": "order_lab_cbc",
    "order_complete_blood_count": "order_lab_cbc",
    # Lab orders - BMP/metabolic variations
    "order_bmp": "order_lab_bmp",
    "bmp": "order_lab_bmp",
    "basic_metabolic_panel": "order_lab_bmp",
    "order_lab_basic_metabolic_panel": "order_lab_bmp",
    "order_basic_metabolic_panel": "order_lab_bmp",
    "order_metabolic_panel": "order_lab_bmp",
    "order_chem7": "order_lab_bmp",
    "order_lab_comprehensive_metabolic_panel": "order_lab_cmp",
    "order_lab_cmp": "order_lab_cmp",
    "comprehensive_metabolic_panel": "order_lab_cmp",
    # Lab orders - coagulation
    "order_coagulation": "order_lab_coagulation",
    "order_coags": "order_lab_coagulation",
    "order_pt_inr": "order_lab_coagulation",
    "coagulation_studies": "order_lab_coagulation",
    "order_lab_prothrombin_time": "order_lab_coagulation",
    "order_lab_pt_inr": "order_lab_coagulation",
    # Lab orders - procalcitonin
    "order_procalcitonin": "order_lab_procalcitonin",
    "procalcitonin": "order_lab_procalcitonin",
    "order_pct": "order_lab_procalcitonin",
    # Lab orders - urine
    "order_lab_urine_culture": "order_lab_urine_culture",
    "urine_culture": "order_lab_urine_culture",
    "order_urine_culture": "order_lab_urine_culture",
    "order_lab_urine_analysis": "order_lab_urinalysis",
    "order_lab_urinalysis": "order_lab_urinalysis",
    "order_urinalysis": "order_lab_urinalysis",
    # Lab orders - blood gas (canonical: order_lab_abg)
    "order_lab_blood_gas": "order_lab_abg",
    "order_lab_arterial_blood_gas": "order_lab_abg",
    "order_lab_abg": "order_lab_abg",  # Identity
    "arterial_blood_gas": "order_lab_abg",
    "order_abg": "order_lab_abg",
    # Lab orders - BNP
    "order_lab_brain_natriuretic_peptide": "order_lab_bnp",
    "order_lab_nt_probnp": "order_lab_bnp",
    "brain_natriuretic_peptide": "order_lab_bnp",
    # Lab orders - liver/kidney
    "order_lab_liver_function": "order_lab_liver_function_tests",
    "order_lab_lft": "order_lab_liver_function_tests",
    "order_lab_renal_function": "order_lab_bmp",
    "order_lab_electrolytes": "order_lab_bmp",
    # Fluid resuscitation variations
    "initiate_iv_fluid_resuscitation": "give_crystalloid_30ml_kg",
    "iv_fluid_resuscitation": "give_crystalloid_30ml_kg",
    "fluid_resuscitation": "give_crystalloid_30ml_kg",
    "give_iv_fluids": "give_crystalloid_fluid",
    "administer_fluids": "give_crystalloid_fluid",
    "bolus_fluids": "give_crystalloid_30ml_kg",
    "fluid_bolus": "give_crystalloid_30ml_kg",
    "give_fluid_bolus": "give_crystalloid_30ml_kg",
    "crystalloid_bolus": "give_crystalloid_30ml_kg",
    "crystalloid_30ml_kg": "give_crystalloid_30ml_kg",  # Sepsis Decision Table 매핑
    "give_normal_saline": "give_crystalloid_fluid",
    "give_lactated_ringers": "give_crystalloid_fluid",
    "give_ns_bolus": "give_crystalloid_30ml_kg",
    "give_lr_bolus": "give_crystalloid_30ml_kg",
    "start_iv_fluid_bolus": "give_crystalloid_30ml_kg",  # RV trap scenario 매핑
    "iv_fluid_bolus": "give_crystalloid_30ml_kg",
    "give_iv_fluid_bolus": "start_iv_fluid_normal_saline",  # DKA uses NS specifically
    "start_iv_fluid": "start_iv_fluid_normal_saline",
    "start_normal_saline": "start_iv_fluid_normal_saline",
    "start_iv_hydration": "start_iv_fluid_normal_saline",
    "start_iv_fluid_ns": "start_iv_fluid_normal_saline",  # Abbreviation canonical
    # Vasopressor variations - norepinephrine
    "start_norepinephrine": "start_vasopressor_norepinephrine",
    "norepinephrine": "start_vasopressor_norepinephrine",
    "give_norepinephrine": "start_vasopressor_norepinephrine",
    "initiate_norepinephrine": "start_vasopressor_norepinephrine",
    "levophed": "start_vasopressor_norepinephrine",
    "start_levophed": "start_vasopressor_norepinephrine",
    "start_norepi": "start_vasopressor_norepinephrine",
    # Vasopressor variations - vasopressin
    "start_vasopressin": "start_vasopressor_vasopressin",
    "vasopressin": "start_vasopressor_vasopressin",
    "give_vasopressin": "start_vasopressor_vasopressin",
    # Vasopressor variations - general
    "start_vasopressors": "start_vasopressor_norepinephrine",
    "initiate_vasopressors": "start_vasopressor_norepinephrine",
    "give_vasopressors": "start_vasopressor_norepinephrine",
    # Antibiotics variations
    "give_antibiotics": "give_broad_spectrum_antibiotics",
    "administer_antibiotics": "give_broad_spectrum_antibiotics",
    "start_antibiotics": "give_broad_spectrum_antibiotics",
    "empiric_antibiotics": "give_broad_spectrum_antibiotics",
    "broad_spectrum_antibiotics": "give_broad_spectrum_antibiotics",
    "iv_antibiotics": "give_broad_spectrum_antibiotics",
    # ECG variations
    "get_ecg": "obtain_12_lead_ecg",
    "order_ecg": "obtain_12_lead_ecg",
    # N5 fix: order_imaging_ecg (graph 5x) -> order_ecg (graph 30x) -> obtain_12_lead_ecg.
    # The downstream resolution chain to obtain_12_lead_ecg is intentional (clinical canonical).
    "order_imaging_ecg": "order_ecg",
    "obtain_ecg": "obtain_12_lead_ecg",  # Oracle Decision Table 매핑
    "12_lead_ecg": "obtain_12_lead_ecg",
    "ecg": "obtain_12_lead_ecg",
    "ekg": "obtain_12_lead_ecg",
    "order_ekg": "obtain_12_lead_ecg",
    "stat_ecg": "obtain_12_lead_ecg",
    # ECG interpretation
    "interpret_ecg": "obtain_12_lead_ecg",
    "interpret_electrocardiogram": "obtain_12_lead_ecg",
    "read_ecg": "obtain_12_lead_ecg",
    "obtain_prior_electrocardiogram_comparison": "obtain_12_lead_ecg",
    # Right-sided ECG (V4R) variations - RV infarct detection
    "v4r_ecg": "obtain_right_sided_ecg_v4r",
    "right_sided_ecg": "obtain_right_sided_ecg_v4r",
    "order_v4r": "obtain_right_sided_ecg_v4r",
    "obtain_v4r_ecg": "obtain_right_sided_ecg_v4r",
    "rv_ecg": "obtain_right_sided_ecg_v4r",
    "obtain_right_sided_electrocardiogram_v4r": "obtain_right_sided_ecg_v4r",
    "right_sided_electrocardiogram": "obtain_right_sided_ecg_v4r",
    # Cath lab variations
    "call_cath_lab": "activate_cath_lab",
    "cath_lab_activation": "activate_cath_lab",
    "activate_cardiac_cath_lab": "activate_cath_lab",
    "emergent_pci": "activate_cath_lab",
    "stat_cath_lab": "activate_cath_lab",
    # Nitroglycerin / Nitrate variations
    "give_nitroglycerin": "give_nitrates_if_indicated",
    "nitroglycerin": "give_nitrates_if_indicated",
    "give_ntg": "give_nitrates_if_indicated",
    "give_nitrate": "give_nitrates_if_indicated",
    "give_nitrates": "give_nitrates_if_indicated",
    "sublingual_nitroglycerin": "give_nitrates_if_indicated",
    "ntg_sublingual": "give_nitrates_if_indicated",
    # Aspirin variations
    "give_aspirin": "give_aspirin_loading",
    "aspirin": "give_aspirin_loading",
    "aspirin_loading": "give_aspirin_loading",  # Oracle Decision Table 매핑
    "aspirin_loading_dose": "give_aspirin_loading",
    "asa": "give_aspirin_loading",
    "give_asa": "give_aspirin_loading",
    "chewable_aspirin": "give_aspirin_loading",
    # P2Y12 inhibitor variations
    "give_clopidogrel": "give_p2y12_inhibitor",
    "give_plavix": "give_p2y12_inhibitor",
    "clopidogrel": "give_p2y12_inhibitor",
    "plavix": "give_p2y12_inhibitor",
    "give_ticagrelor": "give_p2y12_inhibitor",
    "ticagrelor": "give_p2y12_inhibitor",
    "brilinta": "give_p2y12_inhibitor",
    "give_prasugrel": "give_p2y12_inhibitor",
    "prasugrel": "give_p2y12_inhibitor",
    "dual_antiplatelet": "give_p2y12_inhibitor",
    "p2y12_loading": "give_p2y12_inhibitor",  # Oracle Decision Table 매핑
    "p2y12": "give_p2y12_inhibitor",
    # Anticoagulation variations
    "give_heparin": "give_anticoagulation",
    "heparin": "give_anticoagulation",
    "start_heparin": "give_anticoagulation",
    "heparin_bolus": "give_anticoagulation",
    "give_enoxaparin": "give_anticoagulation",
    "lovenox": "give_anticoagulation",
    "anticoagulation": "give_anticoagulation",
    # Assessment variations
    "check_vital_signs": "assess_vital_signs",
    "vitals": "assess_vital_signs",
    "vital_signs": "assess_vital_signs",
    "get_vitals": "assess_vital_signs",
    "monitor_vitals": "assess_vital_signs",
    # Infection source assessment
    "evaluate_infection": "assess_infection_source",
    "infection_source": "assess_infection_source",
    "find_infection_source": "assess_infection_source",
    "identify_infection": "assess_infection_source",
    "source_control": "assess_infection_source",
    # Organ dysfunction assessment
    "evaluate_organ_function": "assess_organ_dysfunction",
    "organ_dysfunction": "assess_organ_dysfunction",
    "check_organ_function": "assess_organ_dysfunction",
    "sofa_score": "assess_organ_dysfunction",
    "calculate_sofa": "assess_organ_dysfunction",
    # Imaging variations
    "chest_xray": "order_imaging_chest_xray",
    "order_chest_xray": "order_imaging_chest_xray",
    "cxr": "order_imaging_chest_xray",
    "order_cxr": "order_imaging_chest_xray",
    "order_imaging_computed_tomography": "order_imaging_ct",
    "order_imaging_ct_scan": "order_imaging_ct",
    "order_imaging_abdominal_computed_tomography": "order_imaging_ct_abdomen",
    "order_imaging_ct_abdomen_pelvis": "order_imaging_ct_abdomen",
    "order_imaging_head_computed_tomography": "order_stat_ct_head",
    "order_imaging_ct_head": "order_stat_ct_head",
    "order_imaging_chest_computed_tomography": "order_imaging_ct_chest",
    "order_imaging_ct_chest": "order_imaging_ct_chest",
    "order_imaging_ct_angiography": "order_imaging_cta",
    "order_imaging_cta": "order_imaging_cta",
    "order_imaging_ct_angiography_chest": "order_imaging_cta_chest",
    "order_imaging_ct_angiography_head": "order_imaging_cta_head",
    "order_imaging_computed_tomography_abdomen": "order_imaging_ct_abdomen",
    "order_imaging_computed_tomography_chest": "order_imaging_ct_chest",
    "order_imaging_computed_tomography_head": "order_stat_ct_head",
    "order_imaging_abdominal_ultrasound": "order_imaging_ultrasound_abdomen",
    "order_imaging_renal_ultrasound": "order_imaging_ultrasound_renal",
    "order_imaging_mri_brain": "order_imaging_mri_brain",
    "order_imaging_ultrasound": "order_imaging_ultrasound",
    "order_imaging_echocardiogram": "order_echocardiogram",
    "order_imaging_echo": "order_echocardiogram",
    # Consultation variations
    "consult": "request_consultation",
    "consult_specialist": "request_consultation",
    "request_consult": "request_consultation",
    "consult_icu": "request_consultation",
    "consult_cardiology": "request_consultation",
    "consult_nephrology": "consult_nephrology",
    "consult_neurology": "request_consultation",
    "consult_surgery": "request_consultation",
    "consult_infectious_disease": "request_consultation",
    "consult_endocrinology": "consult_endocrinology",
    # N3 fix: word-order alias. Canonical = consult_endocrinology (matches consult_<specialty> family).
    "endocrinology_consult": "consult_endocrinology",
    # Line placement
    "central_line": "place_central_line",
    "insert_central_line": "place_central_line",
    "cvc": "place_central_line",
    "arterial_line": "place_arterial_line",
    "insert_arterial_line": "place_arterial_line",
    "a_line": "place_arterial_line",
    # Reassessment
    "reassess": "reassess_perfusion",
    "reassess_patient": "reassess_perfusion",
    "check_response": "reassess_perfusion",
    "evaluate_response": "reassess_perfusion",
    "remeasure_lactate": "remeasure_lactate_if_elevated",  # Sepsis Decision Table 매핑
    # AKI-specific mappings
    # N4 fix: canonical = order_lab_creatinine (graph occurrences 19 vs 3 for order_creatinine).
    # Prior reverse mapping ("order_lab_creatinine": "order_creatinine") removed.
    # Note: line ~798 still maps order_creatinine -> check_baseline_egfr unconditionally for the
    # Contrast-AKI domain — that's a flat-dict cross-domain leak (TODO move to DOMAIN_SPECIFIC).
    "check_creatinine": "order_lab_creatinine",
    "assess_urine_output": "monitor_urine_output",
    "check_urine_output": "monitor_urine_output",
    "order_lab_urine_output": "monitor_urine_output",
    "review_nephrotoxic_medications": "check_current_medications",
    "check_current_medications": "check_current_medications",
    "discontinue_nephrotoxins": "discontinue_nephrotoxic_agents",
    "hold_nephrotoxic_medications": "discontinue_nephrotoxic_agents",
    "stop_nephrotoxic_medications": "discontinue_nephrotoxic_agents",
    "order_imaging_ultrasound_renal": "order_renal_ultrasound",
    "renal_ultrasound": "order_renal_ultrasound",
    "kidney_ultrasound": "order_renal_ultrasound",
    "optimize_fluid_status": "give_crystalloid_fluid",
    "assess_fluid_status": "assess_hydration_status",
    "order_lab_coagulation_profile": "order_lab_coagulation",
    "order_lab_electrocardiogram_12lead": "obtain_12_lead_ecg",
    "nephrology_consult": "consult_nephrology",
    "consult_nephrology_if_needed": "consult_nephrology",
    "urgent_nephrology_consult": "consult_nephrology",
    "order_lab_serum_lactate": "order_lab_lactate",
    # Urine studies → urinalysis (grouped)
    "order_lab_urine_electrolytes": "order_urinalysis",
    "order_lab_urine_osmolality": "order_urinalysis",
    "order_lab_urine_specific_gravity": "order_urinalysis",
    "order_lab_urine_sediment": "order_urinalysis",
    "order_lab_urine_protein": "order_urinalysis",
    "order_lab_urine_microalbumin": "order_urinalysis",
    "order_lab_urine_albumin_to_creatinine_ratio": "order_urinalysis",
    "order_lab_urine_eosinophils": "order_urinalysis",
    "order_lab_urine_sodium": "order_urinalysis",
    "order_lab_urine_creatinine": "order_urinalysis",
    # AKI specific labs
    "order_lab_fena": "order_lab_fena",
    "order_lab_autoimmune_panel": "order_lab_autoimmune_panel",
    # Procedures
    "order_lab_procedure_hemodialysis": "initiate_rrt_immediately",
    "order_lab_procedure_renal_biopsy": "order_renal_biopsy",
    # Medications
    "give_medication_furosemide": "give_medication_furosemide",
    "give_anticoagulation": "give_anticoagulation",
    # Contrast AKI specific
    "order_lab_d_dimer": "order_lab_d_dimer",
    "order_lab_fibrinogen": "order_lab_fibrinogen",
    "order_lab_partial_thromboplastin_time": "order_lab_coagulation",
    "order_lab_hemoglobin": "order_lab_cbc",
    "order_lab_platelet": "order_lab_cbc",
    "order_lab_international_normalized_ratio": "order_lab_coagulation",
    "order_lab_troponin_repeat": "order_lab_troponin",
    "order_imaging_echo_transthoracic": "order_echocardiogram",
    "order_imaging_lower_extremity_ultrasound": "order_imaging_ultrasound",
    "order_imaging_computed_tomography_pe_contrast": "order_imaging_cta_chest",
    "order_imaging_computed_tomography_aorta": "order_imaging_cta",
    "give_medication_oxygen": "give_supplemental_oxygen",
    "order_lab_medication_rivaroxaban": "give_anticoagulation",
    "order_lab_medication_aspirin": "give_aspirin_loading",
    "order_lab_medication_morphine": "give_analgesic",
    "order_lab_medication_thrombolysis": "give_thrombolytic",
    "order_lab_medication_warfarin": "give_anticoagulation",
    "order_lab_medication_low_molecular_weight_heparin": "give_anticoagulation",
    # ── Normalizer Gap Fix (evidence: quantify_normalizer_gap_v2.py) ──
    # Monitoring frequency subsumption: more frequent satisfies less frequent
    "monitor_creatinine_q6h": "monitor_creatinine",
    "monitor_creatinine_q12h": "monitor_creatinine",
    "monitor_creatinine_daily": "monitor_creatinine",
    "monitor_creatinine_q4h": "monitor_creatinine",
    "monitor_potassium_q2h": "monitor_potassium",
    "monitor_potassium_q4h": "monitor_potassium",
    "monitor_potassium_q6h": "monitor_potassium",
    # Serial creatinine monitoring synonyms (contrast AKI follow-up)
    "assess_serum_creatinine_at_72h": "monitor_serum_creatinine_48_72h",
    "assess_serum_creatinine_at_48h": "monitor_serum_creatinine_48_72h",
    "post_procedure_creatinine_48_72h": "monitor_serum_creatinine_48_72h",
    "check_scr_at_72h": "monitor_serum_creatinine_48_72h",
    # Steroid class: specific drug satisfies general class
    "give_hydrocortisone_iv": "give_systemic_corticosteroid",
    "give_methylprednisolone_iv": "give_systemic_corticosteroid",
    "give_dexamethasone_iv": "give_systemic_corticosteroid",
    "prescribe_oral_corticosteroid_5_day": "give_systemic_corticosteroid",
    "give_systemic_corticosteroid_iv": "give_systemic_corticosteroid",
    # Contrast volume minimization synonyms
    "calculate_contrast_volume_limit": "use_minimum_contrast_volume",
    "use_lowest_contrast_volume": "use_minimum_contrast_volume",
    "use_low_osmolar_contrast": "use_minimum_contrast_volume",
    # Access/procedure variants (general satisfies specific)
    "establish_large_bore_iv_access": "establish_iv_access",
    "give_iv_crystalloid_bolus": "give_crystalloid_fluid",
    # Bronchodilator class
    "give_bronchodilator": "give_short_acting_bronchodilator",
    # CSF studies
    "order_lab_csf_culture": "order_lab_csf_analysis",
    # CT PA shortening
    "order_imaging_computed_tomography_pa": "order_imaging_computed_tomography_pulmonary_angiography",
    # ECG variants
    "order_lab_serial_electrocardiogram": "serial_electrocardiogram",
    "order_serial_ecg": "serial_electrocardiogram",
    "electrocardiogram_for_hyperkalemia": "order_lab_electrocardiogram_stat",
    "order_ecg_stat": "order_lab_electrocardiogram_stat",
    # Observation duration (longer satisfies shorter)
    "observe_minimum_24_hours": "observe_minimum_4_hours",
    "observe_minimum_12_hours": "observe_minimum_4_hours",
    # Anticoagulation verb variants
    "initiate_anticoagulation": "give_anticoagulation",
    # Stroke admission
    "admit_to_icu_or_stroke_unit": "admit_to_stroke_unit",
    # Epinephrine dose/timing variants (same drug, same route)
    "give_epinephrine_repeat_3_5min": "give_epinephrine_1mg_iv",
    # Urine output monitoring variants
    "monitor_urine_output_target_200ml_h": "monitor_urine_output",
    "monitor_urine_output_target_0_5_ml_kg_h": "monitor_urine_output",
    # Fluid status
    "optimize_fluid_status": "optimize_volume_status",
    # Medication review variants
    "review_nephrotoxic_medications": "check_current_medications",
    "avoid_additional_nephrotoxins": "avoid_nephrotoxins",
    # ── End Normalizer Gap Fix ──
    # DKA-specific mappings
    "monitor_potassium": "monitor_potassium",
    "check_potassium": "monitor_potassium",
    "reassess_anion_gap": "order_lab_anion_gap",
    "check_anion_gap": "order_lab_anion_gap",
    "monitor_glucose_hourly": "monitor_glucose_hourly",
    "monitor_fluid_balance": "monitor_fluid_balance",
    # DKA - Insulin mappings (D1-c fix)
    "insulin_drip": "start_insulin_infusion",
    "insulin_infusion": "start_insulin_infusion",
    "begin_insulin_infusion": "start_insulin_infusion",
    "initiate_insulin_infusion": "start_insulin_infusion",
    "start_insulin_drip": "start_insulin_infusion",
    "iv_insulin": "start_insulin_infusion",
    "iv_insulin_infusion": "start_insulin_infusion",
    "give_insulin_infusion": "start_insulin_infusion",
    "regular_insulin_infusion": "start_insulin_infusion",
    "regular_insulin_drip": "start_insulin_infusion",
    # DKA - Hold insulin (hypokalemia trap)
    "delay_insulin": "hold_insulin_until_k_above_3.3",
    "withhold_insulin": "hold_insulin_until_k_above_3.3",
    "hold_insulin": "hold_insulin_until_k_above_3.3",
    "defer_insulin": "hold_insulin_until_k_above_3.3",
    # DKA - Potassium replacement
    "potassium_replacement": "give_potassium_iv",
    "give_potassium_replacement": "give_potassium_iv",
    "replace_potassium": "give_potassium_iv",
    "potassium_repletion": "give_potassium_iv",
    "iv_potassium": "give_potassium_iv",
    "kcl_iv": "give_potassium_iv",
    "potassium_chloride_iv": "give_potassium_iv",
    # DKA - Recheck potassium
    "recheck_potassium": "recheck_potassium_in_1h",
    "repeat_potassium": "recheck_potassium_in_1h",
    "follow_up_potassium": "recheck_potassium_in_1h",
    # DKA - Cardiac monitoring
    "cardiac_monitoring": "continuous_cardiac_monitoring",
    "telemetry": "continuous_cardiac_monitoring",
    "cardiac_telemetry": "continuous_cardiac_monitoring",
    "ecg_monitoring": "continuous_cardiac_monitoring",
    "continuous_monitoring": "continuous_cardiac_monitoring",
    # DKA - Potassium monitoring interval
    "monitor_potassium_q2h": "monitor_potassium_q2h",
    "check_potassium_q2h": "monitor_potassium_q2h",
    "potassium_q2h": "monitor_potassium_q2h",
    # PCI/reperfusion
    "pci": "arrange_pci",
    "percutaneous_intervention": "arrange_pci",
    "cardiac_catheterization": "arrange_pci",
    "primary_pci": "arrange_pci",
    "coronary_intervention": "arrange_pci",
    # Disposition
    "admit_icu": "admit_to_icu",
    "icu_admission": "admit_to_icu",
    "transfer_to_icu": "admit_to_icu",
    "admit_ward": "admit_to_ward",
    "ward_admission": "admit_to_ward",
    # Risk score
    "heart_score": "calculate_risk_score",
    "timi_score": "calculate_risk_score",
    "grace_score": "calculate_risk_score",
    "risk_stratification": "calculate_risk_score",
    # ========================================
    # AKI / Contrast-AKI Mappings (KDIGO 2024)
    # ========================================
    # Creatinine/eGFR assessment - AKI Decision Table → CPG Graph
    "order_creatinine": "check_baseline_egfr",
    "check_creatinine": "check_baseline_egfr",
    "measure_creatinine": "check_baseline_egfr",
    "serum_creatinine": "check_baseline_egfr",
    "baseline_creatinine": "check_baseline_egfr",
    "check_egfr": "check_baseline_egfr",
    "assess_renal_function": "check_baseline_egfr",
    "renal_function": "check_baseline_egfr",
    # Urine output monitoring
    # N1 fix: canonical form is monitor_urine_output (graph occurrences 26 vs 4 for assess_*).
    # Prior reverse mapping ("monitor_urine_output": "assess_urine_output") removed to break cycle.
    "urine_output": "monitor_urine_output",
    "check_urine_output": "monitor_urine_output",
    "measure_urine_output": "monitor_urine_output",
    "urine_monitoring": "monitor_urine_output",
    # Nephrotoxin management
    "discontinue_nephrotoxins": "hold_nephrotoxic_medications",
    "stop_nephrotoxins": "hold_nephrotoxic_medications",
    "hold_nephrotoxins": "hold_nephrotoxic_medications",
    "avoid_nephrotoxins": "hold_nephrotoxic_medications",
    "discontinue_nephrotoxic_medications": "hold_nephrotoxic_medications",
    "review_nephrotoxic_drugs": "hold_nephrotoxic_medications",
    # Volume/Hydration status assessment
    "optimize_volume_status": "assess_hydration_status",
    "assess_volume_status": "assess_hydration_status",
    "check_volume_status": "assess_hydration_status",
    "volume_assessment": "assess_hydration_status",
    "fluid_status": "assess_hydration_status",
    "hydration_assessment": "assess_hydration_status",
    # Nephrology consult (canonical: consult_nephrology — matches CPG expected actions)
    "nephrology_consultation": "consult_nephrology",
    "renal_consult": "consult_nephrology",
    "consult_renal": "consult_nephrology",
    "kidney_consult": "consult_nephrology",
    # IV Hydration (pre/post contrast)
    "iv_hydration": "iv_hydration_pre_contrast",
    "pre_hydration": "iv_hydration_pre_contrast",
    "hydrate_before_contrast": "iv_hydration_pre_contrast",
    "saline_hydration": "iv_hydration_pre_contrast",
    "post_hydration": "iv_hydration_post_contrast",
    "hydrate_after_contrast": "iv_hydration_post_contrast",
    # Contrast volume minimization
    "minimize_contrast": "use_minimum_contrast_volume",
    "low_contrast_volume": "use_minimum_contrast_volume",
    "reduce_contrast_dose": "use_minimum_contrast_volume",
    # SCr monitoring post-contrast
    "monitor_creatinine_48h": "monitor_scr_48_72h",
    "check_creatinine_48h": "monitor_scr_48_72h",
    "serial_creatinine": "monitor_scr_48_72h",
    "follow_up_creatinine": "monitor_scr_48_72h",
    "check_scr_48h": "check_scr_at_48h",
    "scr_at_48h": "check_scr_at_48h",
    # Metformin hold
    "hold_metformin": "hold_metformin_if_applicable",
    "stop_metformin": "hold_metformin_if_applicable",
    "discontinue_metformin": "hold_metformin_if_applicable",
    # Risk factor review
    "aki_risk_assessment": "review_risk_factors",
    "assess_aki_risk": "review_risk_factors",
    "check_risk_factors": "review_risk_factors",
    # CI-AKI Prevention specific (AKI Decision Table → CPG Graph)
    "assess_ci_aki_risk": "review_risk_factors",
    "order_baseline_creatinine": "check_baseline_egfr",
    "iv_hydration_if_proceeding": "iv_hydration_pre_contrast",
    "minimize_contrast_volume": "use_minimum_contrast_volume",
    "use_iso_osmolar_contrast": "use_iso_osmolar_contrast",  # Same
    "consider_alternative_imaging": "consider_alternative_imaging",  # Same
    # ========================================
    # Heart Failure Mappings (AHA/ACC/HFSA 2022)
    # ========================================
    # BNP/NT-proBNP ordering
    "order_bnp_or_ntprobnp": "order_bnp_or_ntprobnp",  # Identity - prevent pattern rule transformation
    "order_bnp": "order_bnp_or_ntprobnp",
    "order_ntprobnp": "order_bnp_or_ntprobnp",
    "order_nt_probnp": "order_bnp_or_ntprobnp",
    "bnp": "order_bnp_or_ntprobnp",
    "ntprobnp": "order_bnp_or_ntprobnp",
    "check_bnp": "order_bnp_or_ntprobnp",
    "measure_bnp": "order_bnp_or_ntprobnp",
    "order_natriuretic_peptides": "order_bnp_or_ntprobnp",
    # Echocardiogram
    "order_echocardiogram": "order_echocardiogram",  # Identity - prevent pattern rule transformation
    "order_echo": "order_echocardiogram",
    "echo": "order_echocardiogram",
    "get_echo": "order_echocardiogram",
    "transthoracic_echo": "order_echocardiogram",
    "tte": "order_echocardiogram",
    "order_tte": "order_echocardiogram",
    # LVEF assessment
    "check_lvef": "assess_lvef",
    "measure_lvef": "assess_lvef",
    "evaluate_lvef": "assess_lvef",
    "lvef_assessment": "assess_lvef",
    "ejection_fraction": "assess_lvef",
    # GDMT - ACEi/ARB/ARNI
    "start_ace_inhibitor": "initiate_ace_or_arb_or_arni",
    "start_acei": "initiate_ace_or_arb_or_arni",
    "give_ace_inhibitor": "initiate_ace_or_arb_or_arni",
    "initiate_acei": "initiate_ace_or_arb_or_arni",
    "start_arb": "initiate_ace_or_arb_or_arni",
    "give_arb": "initiate_ace_or_arb_or_arni",
    "initiate_arb": "initiate_ace_or_arb_or_arni",
    "start_arni": "initiate_ace_or_arb_or_arni",
    "give_arni": "initiate_ace_or_arb_or_arni",
    "initiate_arni": "initiate_ace_or_arb_or_arni",
    "start_sacubitril_valsartan": "initiate_ace_or_arb_or_arni",
    "entresto": "initiate_ace_or_arb_or_arni",
    "give_entresto": "initiate_ace_or_arb_or_arni",
    "start_lisinopril": "initiate_ace_or_arb_or_arni",
    "start_enalapril": "initiate_ace_or_arb_or_arni",
    "start_losartan": "initiate_ace_or_arb_or_arni",
    "start_valsartan": "initiate_ace_or_arb_or_arni",
    "raas_inhibitor": "initiate_ace_or_arb_or_arni",
    "consider_ace_or_arb_or_arni": "initiate_ace_or_arb_or_arni",
    # GDMT - Beta-blockers
    "start_beta_blocker": "initiate_beta_blocker",
    "give_beta_blocker": "initiate_beta_blocker",
    "initiate_bb": "initiate_beta_blocker",
    "start_carvedilol": "initiate_beta_blocker",
    "give_carvedilol": "initiate_beta_blocker",
    "start_metoprolol_succinate": "initiate_beta_blocker",
    "give_metoprolol": "initiate_beta_blocker",
    "start_bisoprolol": "initiate_beta_blocker",
    "give_bisoprolol": "initiate_beta_blocker",
    "bb_for_hf": "initiate_beta_blocker",
    "consider_beta_blocker": "initiate_beta_blocker",
    # GDMT - MRA
    "start_mra": "initiate_mra",
    "give_mra": "initiate_mra",
    "start_spironolactone": "initiate_mra",
    "give_spironolactone": "initiate_mra",
    "start_eplerenone": "initiate_mra",
    "give_eplerenone": "initiate_mra",
    "aldosterone_antagonist": "initiate_mra",
    "mineralocorticoid_antagonist": "initiate_mra",
    "consider_mra": "initiate_mra",
    # GDMT - SGLT2i
    "start_sglt2i": "initiate_sglt2i",
    "give_sglt2i": "initiate_sglt2i",
    "start_sglt2_inhibitor": "initiate_sglt2i",
    "give_sglt2_inhibitor": "initiate_sglt2i",
    "start_dapagliflozin": "initiate_sglt2i",
    "give_dapagliflozin": "initiate_sglt2i",
    "farxiga": "initiate_sglt2i",
    "start_empagliflozin": "initiate_sglt2i",
    "give_empagliflozin": "initiate_sglt2i",
    "jardiance": "initiate_sglt2i",
    "sglt2_inhibitor": "initiate_sglt2i",
    # ADHF - IV Diuretics
    "give_iv_diuretics": "iv_diuretics",
    "give_iv_furosemide": "iv_diuretics",
    "iv_furosemide": "iv_diuretics",
    "iv_lasix": "iv_diuretics",
    "lasix_iv": "iv_diuretics",
    "give_iv_lasix": "iv_diuretics",
    "give_loop_diuretic": "iv_diuretics",
    "iv_loop_diuretic": "iv_diuretics",
    "start_iv_diuretics": "iv_diuretics",
    "diuretic_therapy": "iv_diuretics",
    "diuretics_for_congestion": "iv_diuretics",
    "add_diuretic_for_congestion": "iv_diuretics",
    "give_iv_diuretics_furosemide": "iv_diuretics",
    "administer_iv_furosemide": "iv_diuretics",
    "furosemide_iv_push": "iv_diuretics",
    # ADHF - Fluid restriction
    "fluid_restriction": "fluid_restrict",
    "restrict_fluids": "fluid_restrict",
    "limit_fluids": "fluid_restrict",
    "order_fluid_restriction": "fluid_restrict",
    # ADHF - Daily weights
    "order_daily_weights": "daily_weights",
    "monitor_weight": "daily_weights",
    "daily_weight_monitoring": "daily_weights",
    "check_daily_weight": "daily_weights",
    # ADHF - Electrolyte monitoring
    "order_electrolytes": "monitor_electrolytes",
    "check_electrolytes": "monitor_electrolytes",
    "electrolyte_panel": "monitor_electrolytes",
    "serial_electrolytes": "monitor_electrolytes",
    # ADHF - Hemodynamic assessment
    "assess_hemodynamics": "assess_hemodynamic_profile",
    "hemodynamic_assessment": "assess_hemodynamic_profile",
    "evaluate_hemodynamics": "assess_hemodynamic_profile",
    "check_hemodynamic_profile": "assess_hemodynamic_profile",
    "perfusion_assessment": "assess_hemodynamic_profile",
    # ADHF - Inotropes
    "start_inotrope": "consider_inotropes",
    "give_inotrope": "consider_inotropes",
    "start_dobutamine": "consider_inotropes",
    "give_dobutamine": "consider_inotropes",
    "dobutamine": "consider_inotropes",
    "start_milrinone": "consider_inotropes",
    "give_milrinone": "consider_inotropes",
    "milrinone": "consider_inotropes",
    "inotropic_support": "consider_inotropes",
    "inotrope_support": "consider_inotropes",
    # ADHF - Vasodilators
    "give_vasodilator": "consider_vasodilators",
    "start_vasodilator": "consider_vasodilators",
    "nitroprusside": "consider_vasodilators",
    "give_nitroprusside": "consider_vasodilators",
    "nesiritide": "consider_vasodilators",
    "give_nesiritide": "consider_vasodilators",
    "add_vasodilator_if_hypertensive": "consider_vasodilators",
    # ADHF - Hemodynamic monitoring
    "invasive_monitoring": "hemodynamic_monitoring",
    "swan_ganz": "hemodynamic_monitoring",
    "pa_catheter": "hemodynamic_monitoring",
    "pulmonary_artery_catheter": "hemodynamic_monitoring",
    "place_pa_catheter": "hemodynamic_monitoring",
    "invasive_hemodynamic_monitoring": "hemodynamic_monitoring",
    # Cardiogenic shock - ICU admission
    "transfer_icu": "admit_to_icu",
    "admit_icu_cardiogenic": "admit_to_icu",
    "ccu_admission": "admit_to_icu",
    "admit_to_ccu": "admit_to_icu",
    # Cardiogenic shock - Vasopressors (HF-specific)
    "start_vasopressor_for_shock": "vasopressor_support",
    "initiate_vasopressors": "vasopressor_support",
    "pressor_support": "vasopressor_support",
    "hemodynamic_support": "vasopressor_support",
    # Cardiogenic shock - MCS evaluation
    "evaluate_mcs": "mechanical_circulatory_support_evaluation",
    "mcs_evaluation": "mechanical_circulatory_support_evaluation",
    "consider_mcs": "mechanical_circulatory_support_evaluation",
    "assess_for_mcs": "mechanical_circulatory_support_evaluation",
    "iabp_evaluation": "mechanical_circulatory_support_evaluation",
    "impella_evaluation": "mechanical_circulatory_support_evaluation",
    "ecmo_evaluation": "mechanical_circulatory_support_evaluation",
    # Device therapy
    "evaluate_icd": "assess_icd_indication",
    "icd_evaluation": "assess_icd_indication",
    "check_icd_indication": "assess_icd_indication",
    "evaluate_crt": "assess_crt_indication",
    "crt_evaluation": "assess_crt_indication",
    "check_crt_indication": "assess_crt_indication",
    # NYHA class assessment
    "assess_nyha": "assess_nyha_class",
    "check_nyha_class": "assess_nyha_class",
    "evaluate_functional_status": "assess_nyha_class",
    "functional_class_assessment": "assess_nyha_class",
    # Precipitating factors
    "identify_precipitant": "identify_precipitating_factors",
    "find_precipitant": "identify_precipitating_factors",
    "evaluate_triggers": "identify_precipitating_factors",
    "assess_triggers": "identify_precipitating_factors",
    "decompensation_trigger": "identify_precipitating_factors",
    # Cold-dry specific - Fluid challenge
    "give_fluid_challenge": "careful_fluid_challenge",
    "cautious_fluid_bolus": "careful_fluid_challenge",
    "small_fluid_bolus": "careful_fluid_challenge",
    "250ml_fluid_challenge": "careful_fluid_challenge",
    # Comorbidity management (HFpEF)
    "treat_comorbidities": "manage_comorbidities",
    "address_comorbidities": "manage_comorbidities",
    "comorbidity_optimization": "manage_comorbidities",
    # Volume management (HFpEF)
    "volume_management": "manage_volume_status",
    "euvolemia_management": "manage_volume_status",
    "diuresis_management": "manage_volume_status",
    # Alternative RAAS therapy
    "hydralazine_isdn": "add_hydralazine_isdn_if_intolerant",
    "give_hydralazine_isdn": "add_hydralazine_isdn_if_intolerant",
    "start_hydralazine_isdn": "add_hydralazine_isdn_if_intolerant",
    "bidil": "add_hydralazine_isdn_if_intolerant",
    # Ivabradine
    "start_ivabradine": "add_ivabradine_if_indicated",
    "give_ivabradine": "add_ivabradine_if_indicated",
    "ivabradine": "add_ivabradine_if_indicated",
    "corlanor": "add_ivabradine_if_indicated",
    # Additional drug name -> action mappings for HF
    "carvedilol": "initiate_beta_blocker",
    "metoprolol": "initiate_beta_blocker",
    "bisoprolol": "initiate_beta_blocker",
    "lisinopril": "initiate_ace_or_arb_or_arni",
    "enalapril": "initiate_ace_or_arb_or_arni",
    "ramipril": "initiate_ace_or_arb_or_arni",
    "losartan": "initiate_ace_or_arb_or_arni",
    "valsartan": "initiate_ace_or_arb_or_arni",
    "candesartan": "initiate_ace_or_arb_or_arni",
    "sacubitril_valsartan": "initiate_ace_or_arb_or_arni",
    "spironolactone": "initiate_mra",
    "eplerenone": "initiate_mra",
    "dapagliflozin": "initiate_sglt2i",
    "empagliflozin": "initiate_sglt2i",
    "furosemide": "iv_diuretics",
    "lasix": "iv_diuretics",
    "bumetanide": "iv_diuretics",
    "torsemide": "iv_diuretics",
    # ========================================
    # Stroke Mappings (AHA/ASA 2019)
    # ========================================
    # Identity mappings for stroke CPG actions (prevent pattern rule transformation)
    "activate_stroke_team": "activate_stroke_team",
    "obtain_last_known_well_time": "obtain_last_known_well_time",
    "perform_nihss": "perform_nihss",
    "check_glucose": "check_glucose",
    "establish_iv_access": "establish_iv_access",
    "order_stat_ct_head": "order_stat_ct_head",
    "order_cbc_bmp_coag": "order_cbc_bmp_coag",
    "obtain_12_lead_ecg": "obtain_12_lead_ecg",
    "review_inclusion_criteria": "review_inclusion_criteria",
    "review_exclusion_criteria": "review_exclusion_criteria",
    "obtain_informed_consent": "obtain_informed_consent",
    "give_alteplase_0.9mg_kg": "give_alteplase_0.9mg_kg",
    "confirm_lvo_on_imaging": "confirm_lvo_on_imaging",
    "assess_aspects_score": "assess_aspects_score",
    "assess_prestroke_mrs": "assess_prestroke_mrs",
    "activate_neurointerventional_team": "activate_neurointerventional_team",
    "perform_thrombectomy_procedure": "perform_thrombectomy_procedure",
    "confirm_favorable_perfusion_imaging": "confirm_favorable_perfusion_imaging",
    "icu_admission": "admit_to_icu",
    "bp_reduction_target_140": "bp_reduction_target_140",
    "reverse_anticoagulation_if_applicable": "reverse_anticoagulation_if_applicable",
    "neurosurgery_consult": "neurosurgery_consult",
    "admit_to_icu_or_stroke_unit": "admit_to_icu_or_stroke_unit",
    "obtain_ct_angiography": "obtain_ct_angiography",
    "obtain_ct_perfusion": "obtain_ct_perfusion",
    # CODE STROKE activation
    "code_stroke": "activate_stroke_team",
    "stroke_code": "activate_stroke_team",
    "call_stroke_team": "activate_stroke_team",
    "stroke_alert": "activate_stroke_team",
    "activate_stroke_code": "activate_stroke_team",
    # Last known well time
    "get_last_known_well": "obtain_last_known_well_time",
    "check_symptom_onset": "obtain_last_known_well_time",
    "symptom_onset_time": "obtain_last_known_well_time",
    "time_of_onset": "obtain_last_known_well_time",
    "when_last_normal": "obtain_last_known_well_time",
    # NIHSS assessment
    "nihss": "perform_nihss",
    "check_nihss": "perform_nihss",
    "nihss_score": "perform_nihss",
    "calculate_nihss": "perform_nihss",
    "nih_stroke_scale": "perform_nihss",
    "repeat_nihss": "perform_nihss",
    # CT Head
    "ct_head": "order_stat_ct_head",
    "head_ct": "order_stat_ct_head",
    "stat_ct": "order_stat_ct_head",
    "noncontrast_ct": "order_stat_ct_head",
    "ct_brain": "order_stat_ct_head",
    "order_ct_head": "order_stat_ct_head",
    "stat_ct_head": "order_stat_ct_head",
    # CT Angiography
    "cta_head_neck": "obtain_ct_angiography",
    "ct_angiography": "obtain_ct_angiography",
    "cta": "obtain_ct_angiography",
    "order_cta": "obtain_ct_angiography",
    "ct_angio": "obtain_ct_angiography",
    # CT Perfusion
    "ct_perfusion": "obtain_ct_perfusion",
    "ctp": "obtain_ct_perfusion",
    "perfusion_imaging": "obtain_ct_perfusion",
    "order_ct_perfusion": "obtain_ct_perfusion",
    # tPA/Alteplase
    "give_tpa": "give_alteplase_0.9mg_kg",
    "tpa": "give_alteplase_0.9mg_kg",
    "alteplase": "give_alteplase_0.9mg_kg",
    "give_alteplase": "give_alteplase_0.9mg_kg",
    "administer_tpa": "give_alteplase_0.9mg_kg",
    "administer_alteplase": "give_alteplase_0.9mg_kg",
    "thrombolysis": "give_alteplase_0.9mg_kg",
    "iv_thrombolysis": "give_alteplase_0.9mg_kg",
    "activase": "give_alteplase_0.9mg_kg",
    # tPA Eligibility
    "check_tpa_eligibility": "review_inclusion_criteria",
    "tpa_screening": "review_inclusion_criteria",
    "assess_tpa_eligibility": "review_inclusion_criteria",
    "check_contraindications": "review_exclusion_criteria",
    "tpa_contraindications": "review_exclusion_criteria",
    # LVO assessment
    "check_lvo": "confirm_lvo_on_imaging",
    "lvo_assessment": "confirm_lvo_on_imaging",
    "large_vessel_occlusion": "confirm_lvo_on_imaging",
    "assess_lvo": "confirm_lvo_on_imaging",
    # ASPECTS score
    "aspects": "assess_aspects_score",
    "check_aspects": "assess_aspects_score",
    "calculate_aspects": "assess_aspects_score",
    "aspects_score": "assess_aspects_score",
    # Thrombectomy
    "thrombectomy": "perform_thrombectomy_procedure",
    "mechanical_thrombectomy": "perform_thrombectomy_procedure",
    "endovascular_therapy": "perform_thrombectomy_procedure",
    "evt": "perform_thrombectomy_procedure",
    "clot_retrieval": "perform_thrombectomy_procedure",
    # Neurointerventional team
    "call_neurointerventional": "activate_neurointerventional_team",
    "neurointerventional_consult": "activate_neurointerventional_team",
    "activate_ir": "activate_neurointerventional_team",
    "call_interventional_neuro": "activate_neurointerventional_team",
    # BP management for stroke
    "lower_bp_for_tpa": "reduce_bp_to_below_185_110_before_tpa",
    "bp_management_tpa": "reduce_bp_to_below_185_110_before_tpa",
    "control_bp_pre_tpa": "reduce_bp_to_below_185_110_before_tpa",
    "give_labetalol": "use_iv_labetalol_or_nicardipine",
    "give_nicardipine": "use_iv_labetalol_or_nicardipine",
    "labetalol": "use_iv_labetalol_or_nicardipine",
    "nicardipine": "use_iv_labetalol_or_nicardipine",
    "iv_antihypertensive": "use_iv_labetalol_or_nicardipine",
    # ICH-specific BP
    "lower_bp_ich": "bp_reduction_target_140",
    "sbp_target_140": "bp_reduction_target_140",
    "intensive_bp_lowering": "bp_reduction_target_140",
    # Anticoagulation reversal
    "reverse_warfarin": "reverse_anticoagulation_if_applicable",
    "give_pcc": "reverse_anticoagulation_if_applicable",
    "give_vitamin_k": "reverse_anticoagulation_if_applicable",
    "give_idarucizumab": "reverse_anticoagulation_if_applicable",
    "give_andexanet": "reverse_anticoagulation_if_applicable",
    "reversal_agent": "reverse_anticoagulation_if_applicable",
    # Neurosurgery
    "neurosurgery_eval": "neurosurgery_consult",
    "call_neurosurgery": "neurosurgery_consult",
    "nsgy_consult": "neurosurgery_consult",
    # Post-tPA monitoring
    "neuro_checks": "neurological_checks_q15min",
    "neurological_monitoring": "neurological_checks_q15min",
    "serial_neuro_exams": "neurological_checks_q15min",
    "bp_monitoring_post_tpa": "monitor_bp_q15min_x2h_then_q30min_x6h",
    # Stop tPA
    "stop_tpa": "stop_tpa_infusion",
    "discontinue_tpa": "stop_tpa_infusion",
    "hold_tpa": "stop_tpa_infusion",
    # Hemorrhage workup
    "stat_coags": "stat_coagulation_panel",
    "stat_pt_inr": "stat_coagulation_panel",
    "coagulation_panel": "stat_coagulation_panel",
    # Hemorrhage treatment
    "cryoprecipitate": "give_cryoprecipitate",
    "give_cryo": "give_cryoprecipitate",
    "txa": "give_tranexamic_acid",
    "tranexamic_acid": "give_tranexamic_acid",
    # Stroke unit admission
    "admit_stroke_unit": "admit_to_stroke_unit",
    "stroke_unit": "admit_to_stroke_unit",
    "transfer_stroke_unit": "admit_to_stroke_unit",
    # DVT prophylaxis
    "dvt_prevention": "dvt_prophylaxis",
    "vte_prophylaxis": "dvt_prophylaxis",
    "compression_stockings": "dvt_prophylaxis",
    "scds": "dvt_prophylaxis",
    # Swallow assessment
    "swallow_evaluation": "swallow_screen",
    "dysphagia_screen": "swallow_screen",
    "swallow_assessment": "swallow_screen",
    "npo_until_swallow": "swallow_screen",
    # Mobilization
    "pt_evaluation": "early_mobilization",
    # N1 Fix: "physical_therapy" moved to domain-specific (aha_stroke → early_mobilization)
    "get_patient_up": "early_mobilization",
    "mobilize_patient": "early_mobilization",
    # Secondary prevention
    "start_aspirin": "antiplatelet_therapy",
    "aspirin_secondary_prevention": "antiplatelet_therapy",
    "give_statin": "statin_therapy",
    "start_statin": "statin_therapy",
    "high_intensity_statin": "statin_therapy",
    "atorvastatin": "statin_therapy",
    "rosuvastatin": "statin_therapy",
    # Cardiac monitoring (AF-specific only; do NOT remap continuous_cardiac_monitoring here)
    "holter_monitor": "cardiac_monitoring_for_afib",
    "afib_monitoring": "cardiac_monitoring_for_afib",
    # NOTE: "telemetry" and "continuous_cardiac_monitoring" removed — they are
    # domain-generic terms mapped in DKA/ADHF sections to their canonical forms.
    # Carotid evaluation
    "carotid_ultrasound": "carotid_evaluation",
    "carotid_duplex": "carotid_evaluation",
    "carotid_imaging": "carotid_evaluation",
    # DOAC for Afib
    "start_anticoagulation_afib": "start_doac_preferred",
    "apixaban": "start_doac_preferred",
    "rivaroxaban": "start_doac_preferred",
    "dabigatran": "start_doac_preferred",
    "edoxaban": "start_doac_preferred",
    "doac": "start_doac_preferred",
    "noac": "start_doac_preferred",
    # CHA2DS2-VASc
    "chads_vasc": "calculate_chadsvasc",
    "stroke_risk_score": "calculate_chadsvasc",
    "afib_stroke_risk": "calculate_chadsvasc",
    # HAS-BLED
    "has_bled": "calculate_hasbled",
    "bleeding_risk_score": "calculate_hasbled",
    # ========================================
    # Additional Heart Failure Mappings (Gap Fix)
    # ========================================
    # Initial Assessment - History & Physical
    "obtain_history": "obtain_history",  # Identity mapping
    "take_history": "obtain_history",
    "get_history": "obtain_history",
    "history_and_physical": "obtain_history",
    "hpi": "obtain_history",
    "physical_examination": "physical_examination",  # Identity mapping
    "physical_exam": "physical_examination",
    "examine_patient": "physical_examination",
    "pe": "physical_examination",
    # Initial Assessment - Labs (Identity mappings to prevent pattern rule transformation)
    # N1 Fix: Conflicting entries moved to _DEFAULT_DOMAIN_SPECIFIC_MAPPINGS["aha_heart_failure"]
    # Kept: unique keys only (no conflict with earlier generic mappings)
    "order_basic_metabolic_panel": "order_basic_metabolic_panel",  # Identity (unique key)
    "basic_metabolic": "order_basic_metabolic_panel",  # Unique key
    "order_tsh": "order_tsh",  # Identity
    "tsh": "order_tsh",
    "thyroid_function": "order_tsh",
    "check_thyroid": "order_tsh",
    "order_iron_studies": "order_iron_studies",  # Identity
    "order_lipid_panel": "order_lipid_panel",  # Identity
    "order_hba1c": "order_hba1c",  # Identity
    # ADHF - Urine output monitoring
    # N1 Fix: "urine_output", "check_urine_output" moved to domain-specific (conflict with AKI section)
    "foley_output": "monitor_urine_output",
    "i_o_monitoring": "monitor_urine_output",
    "ins_and_outs": "monitor_urine_output",
    # ADHF - Continuous monitoring
    "continuous_monitoring": "continuous_monitoring",  # Identity
    # NOTE: "telemetry_monitoring" and "cardiac_monitoring" moved to
    # domain-specific aha_heart_failure (conflict with DKA continuous_cardiac_monitoring)
    # Structural abnormalities
    "assess_structural_abnormalities": "assess_structural_abnormalities",  # Identity
    "structural_assessment": "assess_structural_abnormalities",
    "assess_valves": "assess_structural_abnormalities",
    # HF Classification documentation
    "document_hfref_diagnosis": "document_hfref_diagnosis",  # Identity
    "document_hfref": "document_hfref_diagnosis",
    "document_hfmref_diagnosis": "document_hfmref_diagnosis",  # Identity
    "document_hfmref": "document_hfmref_diagnosis",
    "document_hfpef_diagnosis": "document_hfpef_diagnosis",  # Identity
    "document_hfpef": "document_hfpef_diagnosis",
    # Etiology identification
    "identify_etiology": "identify_etiology",  # Identity
    "determine_etiology": "identify_etiology",
    "etiology_workup": "identify_etiology",
    "hf_etiology": "identify_etiology",
    # Diastolic function (HFpEF)
    "evaluate_diastolic_function": "evaluate_diastolic_function",  # Identity
    "diastolic_assessment": "evaluate_diastolic_function",
    "assess_diastolic": "evaluate_diastolic_function",
    # GDMT optimization
    "optimize_gdmt_titration": "optimize_gdmt_titration",  # Identity
    "titrate_gdmt": "optimize_gdmt_titration",
    "uptitrate_medications": "optimize_gdmt_titration",
    # Follow-up
    "regular_follow_up": "regular_follow_up",  # Identity
    "schedule_followup": "regular_follow_up",
    "outpatient_followup": "regular_follow_up",
    # Deterioration monitoring
    "monitor_for_deterioration": "monitor_for_deterioration",  # Identity
    "watch_for_worsening": "monitor_for_deterioration",
    "decompensation_monitoring": "monitor_for_deterioration",
    # Patient education
    "patient_education": "patient_education",  # Identity
    "educate_patient": "patient_education",
    "hf_education": "patient_education",
    # Cardiac rehab
    "cardiac_rehabilitation": "cardiac_rehabilitation",  # Identity
    "cardiac_rehab": "cardiac_rehabilitation",
    "cr_referral": "cardiac_rehabilitation",
    # Sodium restriction
    "sodium_restriction": "sodium_restriction",  # Identity
    "low_sodium_diet": "sodium_restriction",
    "salt_restriction": "sodium_restriction",
    # Fluid restriction
    "fluid_restriction_if_needed": "fluid_restriction_if_needed",  # Identity
    "conditional_fluid_restriction": "fluid_restriction_if_needed",
    # Vaccinations
    "vaccinations": "vaccinations",  # Identity
    "flu_vaccine": "vaccinations",
    "pneumonia_vaccine": "vaccinations",
    "immunizations": "vaccinations",
    # GDMT duration check
    "check_optimal_gdmt_duration": "check_optimal_gdmt_duration",  # Identity
    "gdmt_duration_check": "check_optimal_gdmt_duration",
    "3_months_gdmt": "check_optimal_gdmt_duration",
    # ICD/CRT procedures
    "implant_icd": "implant_icd",  # Identity
    "icd_implant": "implant_icd",
    "place_icd": "implant_icd",
    "implant_crt": "implant_crt",  # Identity
    "crt_implant": "implant_crt",
    "place_crt": "implant_crt",
    "biventricular_pacing": "implant_crt",
    # Informed consent
    "discuss_risks_benefits": "discuss_risks_benefits",  # Identity
    "risks_benefits_discussion": "discuss_risks_benefits",
    "obtain_informed_consent": "obtain_informed_consent",  # Identity
    "informed_consent": "obtain_informed_consent",
    "consent": "obtain_informed_consent",
    # Diuretic resistance
    "increase_diuretic_dose": "increase_diuretic_dose",  # Identity
    "uptitrate_diuretic": "increase_diuretic_dose",
    "double_diuretic": "increase_diuretic_dose",
    "consider_combination_diuretics": "consider_combination_diuretics",  # Identity
    "combination_diuretics": "consider_combination_diuretics",
    "add_thiazide_metolazone": "add_thiazide_metolazone",  # Identity
    "add_metolazone": "add_thiazide_metolazone",
    "metolazone": "add_thiazide_metolazone",
    "continuous_diuretic_infusion": "continuous_diuretic_infusion",  # Identity
    "lasix_drip": "continuous_diuretic_infusion",
    "furosemide_infusion": "continuous_diuretic_infusion",
    "consider_ultrafiltration": "consider_ultrafiltration",  # Identity
    "ultrafiltration": "consider_ultrafiltration",
    "uf": "consider_ultrafiltration",
    # MCS specific
    "select_mcs_device": "select_mcs_device",  # Identity
    "mcs_selection": "select_mcs_device",
    "multidisciplinary_team_evaluation": "multidisciplinary_team_evaluation",  # Identity
    "mdt_evaluation": "multidisciplinary_team_evaluation",
    "iabp": "iabp",  # Identity
    "intra_aortic_balloon_pump": "iabp",
    "balloon_pump": "iabp",
    "impella": "impella",  # Identity
    "impella_cp": "impella",
    "impella_5": "impella",
    "ecmo": "ecmo",  # Identity
    "va_ecmo": "ecmo",
    "veno_arterial_ecmo": "ecmo",
    "lvad_evaluation": "lvad_evaluation",  # Identity
    "evaluate_lvad": "lvad_evaluation",
    "lvad_workup": "lvad_workup",  # Identity
    # Advanced HF
    "confirm_optimal_gdmt": "confirm_optimal_gdmt",  # Identity
    "verify_optimal_gdmt": "confirm_optimal_gdmt",
    "assess_candidacy_for_advanced_therapies": "assess_candidacy_for_advanced_therapies",  # Identity
    "advanced_therapy_evaluation": "assess_candidacy_for_advanced_therapies",
    "palliative_care_discussion": "palliative_care_discussion",  # Identity
    "goals_of_care": "palliative_care_discussion",
    "discuss_goals_of_care": "palliative_care_discussion",
    "comprehensive_transplant_workup": "comprehensive_transplant_workup",  # Identity
    "transplant_workup": "comprehensive_transplant_workup",
    "psychosocial_evaluation": "psychosocial_evaluation",  # Identity
    "psych_evaluation": "psychosocial_evaluation",
    "list_if_appropriate": "list_if_appropriate",  # Identity
    "transplant_listing": "list_if_appropriate",
    "lvad_as_bridge_to_transplant": "lvad_as_bridge_to_transplant",  # Identity
    "btt": "lvad_as_bridge_to_transplant",
    "lvad_as_destination_therapy": "lvad_as_destination_therapy",  # Identity
    "dt": "lvad_as_destination_therapy",
    "destination_therapy": "lvad_as_destination_therapy",
    # Palliative
    "symptom_management": "symptom_management",  # Identity
    "symptomatic_treatment": "symptom_management",
    "discuss_advance_directives": "discuss_advance_directives",  # Identity
    "advance_directives": "discuss_advance_directives",
    "code_status": "discuss_advance_directives",
    "hospice_referral_if_appropriate": "hospice_referral_if_appropriate",  # Identity
    "hospice_referral": "hospice_referral_if_appropriate",
    "comfort_care": "hospice_referral_if_appropriate",
    # ========================================
    # Additional Stroke Mappings (Gap Fix)
    # ========================================
    # Glucose check variations
    "glucose_check": "check_glucose",
    "blood_glucose": "check_glucose",
    "finger_stick": "check_glucose",
    "accucheck": "check_glucose",
    "glucose_poc": "check_glucose",
    "point_of_care_glucose": "check_glucose",
    # IV access
    "establish_iv_access": "establish_iv_access",  # Identity
    "iv_access": "establish_iv_access",
    "start_iv": "establish_iv_access",
    "peripheral_iv": "establish_iv_access",
    "two_large_bore_ivs": "establish_iv_access",
    # Stroke labs
    "order_cbc_bmp_coag": "order_cbc_bmp_coag",  # Identity
    "stroke_labs": "order_cbc_bmp_coag",
    "stroke_panel": "order_cbc_bmp_coag",
    "stat_labs": "order_cbc_bmp_coag",
    # ECG variations
    "obtain_12_lead_ecg": "obtain_12_lead_ecg",  # Identity
    "12_lead_ecg": "obtain_12_lead_ecg",
    "ecg_12_lead": "obtain_12_lead_ecg",
    "stat_ecg": "obtain_12_lead_ecg",
    # Time calculation
    "calculate_time_from_onset": "calculate_time_from_onset",  # Identity
    "time_from_onset": "calculate_time_from_onset",
    "onset_to_door_time": "calculate_time_from_onset",
    # Anticoagulation status
    "review_anticoagulation_status": "review_anticoagulation_status",  # Identity
    "anticoagulation_history": "review_anticoagulation_status",
    "check_anticoagulation": "review_anticoagulation_status",
    # Stroke unit admission
    "admit_to_icu_or_stroke_unit": "admit_to_icu_or_stroke_unit",  # Identity
    "stroke_icu_admission": "admit_to_icu_or_stroke_unit",
    "neuro_icu": "admit_to_icu_or_stroke_unit",
    # Hold antiplatelets post-tPA
    "hold_antiplatelet_anticoagulation_24h": "hold_antiplatelet_anticoagulation_24h",  # Identity
    "hold_antiplatelets_24h": "hold_antiplatelet_anticoagulation_24h",
    "no_antiplatelets_24h": "hold_antiplatelet_anticoagulation_24h",
    # Pre-stroke mRS
    "assess_prestroke_mrs": "assess_prestroke_mrs",  # Identity
    "prestroke_mrs": "assess_prestroke_mrs",
    "baseline_mrs": "assess_prestroke_mrs",
    "premorbid_function": "assess_prestroke_mrs",
    # TICI score
    "achieve_tici_2b_or_better": "achieve_tici_2b_or_better",  # Identity
    "tici_score": "achieve_tici_2b_or_better",
    "successful_recanalization": "achieve_tici_2b_or_better",
    # Perfusion imaging
    "confirm_favorable_perfusion_imaging": "confirm_favorable_perfusion_imaging",  # Identity
    "perfusion_mismatch": "confirm_favorable_perfusion_imaging",
    "dawn_defuse_criteria": "confirm_favorable_perfusion_imaging",
    # Post-thrombectomy care
    "groin_site_monitoring": "groin_site_monitoring",  # Identity
    "puncture_site_check": "groin_site_monitoring",
    "groin_check": "groin_site_monitoring",
    "follow_up_imaging": "follow_up_imaging",  # Identity
    "post_procedure_ct": "follow_up_imaging",
    # Non-reperfusion
    "aspirin_within_24_48h": "aspirin_within_24_48h",  # Identity
    "start_aspirin_24h": "aspirin_within_24_48h",
    "aspirin_for_stroke": "aspirin_within_24_48h",
    "dual_antiplatelet_for_minor_stroke_tia": "dual_antiplatelet_for_minor_stroke_tia",  # Identity
    "dapt_minor_stroke": "dual_antiplatelet_for_minor_stroke_tia",
    "aspirin_clopidogrel": "dual_antiplatelet_for_minor_stroke_tia",
    # Repeat CT
    "repeat_ct_24h": "repeat_ct_24h",  # Identity
    "24h_ct": "repeat_ct_24h",
    "followup_ct": "repeat_ct_24h",
    "repeat_ct_6h_or_if_deterioration": "repeat_ct_6h_or_if_deterioration",  # Identity
    "repeat_ct_ich": "repeat_ct_6h_or_if_deterioration",
    "6h_ct": "repeat_ct_6h_or_if_deterioration",
    # BP targets
    "bp_management_target_180_105": "bp_management_target_180_105",  # Identity
    "maintain_bp_180_105": "bp_management_target_180_105",
    "post_tpa_bp_target": "bp_management_target_180_105",
    "maintain_bp_below_180_105_post_tpa": "maintain_bp_below_180_105_post_tpa",  # Identity
    # Secondary prevention start
    "start_antiplatelet_after_24h_if_no_hemorrhage": "start_antiplatelet_after_24h_if_no_hemorrhage",  # Identity
    "resume_antiplatelets": "start_antiplatelet_after_24h_if_no_hemorrhage",
    # Hemorrhagic transformation
    "hemorrhagic_transformation_management": "hemorrhagic_transformation_management",  # Identity
    "sICH_management": "hemorrhagic_transformation_management",
    # Type and screen
    "type_and_screen": "type_and_screen",  # Identity
    "t_and_s": "type_and_screen",
    "blood_bank": "type_and_screen",
    # Coagulopathy reversal
    "reverse_coagulopathy": "reverse_coagulopathy",  # Identity
    "correct_coagulopathy": "reverse_coagulopathy",
    "normalize_inr": "reverse_coagulopathy",
    # ICU management
    "icu_management": "icu_management",  # Identity
    "icu_care": "icu_management",
    "intensive_care": "icu_management",
    # Deterioration evaluation
    "evaluate_for_recurrent_stroke": "evaluate_for_recurrent_stroke",  # Identity
    "recurrent_stroke_workup": "evaluate_for_recurrent_stroke",
    "evaluate_for_hemorrhage": "evaluate_for_hemorrhage",  # Identity
    "hemorrhage_workup": "evaluate_for_hemorrhage",
    "evaluate_for_edema": "evaluate_for_edema",  # Identity
    "edema_assessment": "evaluate_for_edema",
    # Malignant edema
    "elevate_head_of_bed": "elevate_head_of_bed",  # Identity
    "head_elevation": "elevate_head_of_bed",
    "hob_30": "elevate_head_of_bed",
    "avoid_hyperthermia": "avoid_hyperthermia",  # Identity
    "temperature_management": "avoid_hyperthermia",
    "fever_prevention": "avoid_hyperthermia",
    "avoid_hyperglycemia": "avoid_hyperglycemia",  # Identity
    "glucose_control": "avoid_hyperglycemia",
    "neurosurgery_consult_for_decompressive_craniectomy": "neurosurgery_consult_for_decompressive_craniectomy",  # Identity
    "craniectomy_consult": "neurosurgery_consult_for_decompressive_craniectomy",
    "decompressive_surgery": "neurosurgery_consult_for_decompressive_craniectomy",
    "osmotic_therapy": "osmotic_therapy",  # Identity
    "mannitol": "osmotic_therapy",
    "hypertonic_saline": "osmotic_therapy",
    "hyperventilation_temporizing": "hyperventilation_temporizing",  # Identity
    "hyperventilation": "hyperventilation_temporizing",
    # ICH specific
    "evd_for_hydrocephalus": "evd_for_hydrocephalus",  # Identity
    "evd_placement": "evd_for_hydrocephalus",
    "external_ventricular_drain": "evd_for_hydrocephalus",
    "consider_evacuation_if_indicated": "consider_evacuation_if_indicated",  # Identity
    "hematoma_evacuation": "consider_evacuation_if_indicated",
    "clot_evacuation": "consider_evacuation_if_indicated",
    "icp_monitoring_if_indicated": "icp_monitoring_if_indicated",  # Identity
    "icp_monitoring": "icp_monitoring_if_indicated",
    "icp_monitor": "icp_monitoring_if_indicated",
    "seizure_prophylaxis_consideration": "seizure_prophylaxis_consideration",  # Identity
    "seizure_prophylaxis": "seizure_prophylaxis_consideration",
    "levetiracetam": "seizure_prophylaxis_consideration",
    "dvt_prophylaxis_mechanical": "dvt_prophylaxis_mechanical",  # Identity
    "scds_for_dvt": "dvt_prophylaxis_mechanical",
    "mechanical_dvt_prophylaxis": "dvt_prophylaxis_mechanical",
    # Secondary prevention - BP
    "bp_management_long_term": "bp_management_long_term",  # Identity
    "chronic_bp_management": "bp_management_long_term",
    "antihypertensive_therapy": "bp_management_long_term",
    # Secondary prevention - Diabetes
    "diabetes_management": "diabetes_management",  # Identity
    "glycemic_control": "diabetes_management",
    "manage_diabetes": "diabetes_management",
    # Secondary prevention - Smoking
    "smoking_cessation": "smoking_cessation",  # Identity
    "stop_smoking": "smoking_cessation",
    "tobacco_cessation": "smoking_cessation",
    # Afib anticoagulation
    "anticoagulation_if_afib": "anticoagulation_if_afib",  # Identity
    "afib_anticoagulation": "anticoagulation_if_afib",
    "start_anticoagulation_before_24h_post_tpa": "start_anticoagulation_before_24h_post_tpa",  # Identity (forbidden)
    "warfarin_if_doac_contraindicated": "warfarin_if_doac_contraindicated",  # Identity
    "warfarin": "warfarin_if_doac_contraindicated",
    "left_atrial_appendage_closure_consideration": "left_atrial_appendage_closure_consideration",  # Identity
    "laa_closure": "left_atrial_appendage_closure_consideration",
    "watchman": "left_atrial_appendage_closure_consideration",
    # Carotid intervention
    "confirm_stenosis_degree": "confirm_stenosis_degree",  # Identity
    "stenosis_measurement": "confirm_stenosis_degree",
    "assess_surgical_risk": "assess_surgical_risk",  # Identity
    "surgical_risk_assessment": "assess_surgical_risk",
    "surgical_planning": "surgical_planning",  # Identity
    "perform_cea_within_2_weeks": "perform_cea_within_2_weeks",  # Identity
    "cea": "perform_cea_within_2_weeks",
    "carotid_endarterectomy": "perform_cea_within_2_weeks",
    "dual_antiplatelet_before_procedure": "dual_antiplatelet_before_procedure",  # Identity
    "dapt_before_cas": "dual_antiplatelet_before_procedure",
    "perform_cas": "perform_cas",  # Identity
    "carotid_stent": "perform_cas",
    "carotid_stenting": "perform_cas",
    "carotid_intervention_if_indicated": "carotid_intervention_if_indicated",  # Identity
    "carotid_revascularization": "carotid_intervention_if_indicated",
    # Rehabilitation
    "early_rehabilitation_assessment": "early_rehabilitation_assessment",  # Identity
    "rehab_assessment": "early_rehabilitation_assessment",
    # N1 Fix: "physical_therapy" removed (domain-specific handles stroke→early_mobilization)
    "pt": "physical_therapy",
    "occupational_therapy": "occupational_therapy",  # Identity
    "ot": "occupational_therapy",
    "speech_therapy_if_needed": "speech_therapy_if_needed",  # Identity
    "slp": "speech_therapy_if_needed",
    "speech_therapy": "speech_therapy_if_needed",
    "discharge_planning": "discharge_planning",  # Identity
    "disposition_planning": "discharge_planning",
    "inpatient_rehabilitation": "inpatient_rehabilitation",  # Identity
    "irf": "inpatient_rehabilitation",
    "acute_rehab": "inpatient_rehabilitation",
    "outpatient_rehabilitation": "outpatient_rehabilitation",  # Identity
    "home_pt": "outpatient_rehabilitation",
    # Shared decision making (stroke)
    "discuss_with_patient_family": "discuss_with_patient_family",  # Identity
    "shared_decision": "discuss_with_patient_family",
    "family_discussion": "discuss_with_patient_family",
    "document_shared_decision": "document_shared_decision",  # Identity
    # Alternative action names for forbiddens
    "give_antiplatelet_within_24h": "give_antiplatelet_within_24h",  # Identity (forbidden)
    "give_anticoagulation_within_24h": "give_anticoagulation_within_24h",  # Identity (forbidden)
    "give_heparin_within_24h": "give_heparin_within_24h",  # Identity (forbidden)
    "place_foley_within_30min": "place_foley_within_30min",  # Identity (forbidden)
    "place_ng_tube_within_30min": "place_ng_tube_within_30min",  # Identity (forbidden)
    "place_arterial_line_within_30min": "place_arterial_line_within_30min",  # Identity (forbidden)
    "give_antiplatelet_before_24h": "give_antiplatelet_before_24h",  # Identity (forbidden)
    "give_anticoagulation_before_24h": "give_anticoagulation_before_24h",  # Identity (forbidden)
    "give_tpa_if_bp_uncontrolled": "give_tpa_if_bp_uncontrolled",  # Identity (forbidden)
    "give_anticoagulation_for_stroke_prevention_in_first_24h": "give_anticoagulation_for_stroke_prevention_in_first_24h",  # Identity (forbidden)
    "treat_if_bp_above_220_120": "treat_if_bp_above_220_120",  # Identity
    "goal_reduction_15_percent": "goal_reduction_15_percent",  # Identity
    "permissive_hypertension_below_220_120": "permissive_hypertension_below_220_120",  # Identity
    # ================================================================
    # Expansion Domain Mappings (AF, GI, HTN, PE, COPD, HF, Stroke)
    # ================================================================
    # Atrial Fibrillation (including route-specific variants)
    "give_medication_diltiazem": "give_calcium_channel_blocker",
    "give_medication_diltiazem_iv": "give_calcium_channel_blocker",
    "give_medication_diltiazem_oral": "give_calcium_channel_blocker",
    "give_medication_beta_blocker": "give_beta_blocker",
    "give_medication_metoprolol_iv": "give_beta_blocker",
    "give_medication_metoprolol_oral": "give_beta_blocker",
    "give_medication_amiodarone": "give_iv_amiodarone",
    "give_medication_amiodarone_iv": "give_iv_amiodarone",
    "give_medication_apixaban": "give_anticoagulation",
    "give_medication_apixaban_oral": "give_anticoagulation",
    "give_medication_rivaroxaban_oral": "give_anticoagulation",
    "give_medication_heparin": "give_heparin",
    "give_medication_heparin_iv": "give_heparin",
    "give_medication_heparin_subq": "give_heparin",
    "give_medication_normal_saline_iv": "give_iv_fluids",
    "order_ecg_12lead": "order_ecg",
    "order_ecg_continuous_monitoring": "continuous_monitoring",
    "order_imaging_echo_transthoracic": "order_echocardiogram",
    "order_imaging_tee": "order_echocardiogram",
    "order_procedure_cardioversion": "perform_cardioversion",
    "order_procedure_sedation": "perform_cardioversion",
    "order_lab_pt": "order_lab_coagulation",
    "consult_electrophysiology": "consult_electrophysiology",
    # GI Bleeding
    "give_medication_iv_pantoprazole": "give_iv_ppi",
    "give_medication_iv_pantoprazole_continuous": "give_iv_ppi",
    "give_medication_oral_pantoprazole": "give_iv_ppi",
    "give_medication_iv_octreotide": "give_octreotide",
    "give_medication_iv_erythromycin": "give_prokinetic",
    "give_medication_iv_fluids": "give_iv_crystalloid_bolus",
    "order_blood_product_prbc": "give_packed_rbc_if_hgb_below_7",
    "order_procedure_egd": "perform_endoscopy",
    "perform_procedure_egd": "perform_endoscopy",
    "order_procedure_angiography": "perform_angiography",
    "perform_procedure_angiography": "perform_angiography",
    "consult_gastroenterology": "consult_gi",
    "order_lab_coag": "order_lab_coagulation",
    "order_lab_type_and_screen": "order_type_and_crossmatch",
    "order_lab_hgb_repeat": "repeat_cbc",
    "order_lab_lactate_repeat": "repeat_lactate",
    # HTN Emergency
    "give_medication_labetalol": "give_iv_labetalol",
    "give_medication_nicardipine": "give_iv_nicardipine",
    "give_medication_nitroprusside": "give_iv_nitroprusside",
    "give_medication_clevidipine": "give_iv_antihypertensive",
    "assess_neurologic_status": "assess_neurological_status",
    # N2 fix: canonical form is assess_neurological_status (graph occurrences 18 vs 2 for monitor_*).
    "monitor_neurological_status": "assess_neurological_status",
    "assess_cardiac_status": "assess_end_organ_damage",
    "assess_urine_output": "monitor_urine_output",
    "order_lab_renal": "order_lab_bmp",
    "order_lab_eGFR": "order_lab_bmp",
    "order_lab_urine_output": "monitor_urine_output",
    "order_lab_urine_microalbumin": "order_lab_urinalysis",
    "order_lab_urine_protein": "order_lab_urinalysis",
    "order_lab_urine_sodium": "order_lab_urinalysis",
    "order_lab_urine_specific_gravity": "order_lab_urinalysis",
    "order_fluid_normal_saline": "give_iv_fluids",
    # Pulmonary Embolism
    "give_medication_heparin_continuous_infusion": "give_heparin",
    "give_medication_enoxaparin": "give_lmwh",
    "give_medication_oxygen": "give_supplemental_oxygen",
    "order_medication_rivaroxaban": "give_anticoagulation",
    "order_imaging_ct_pe": "order_imaging_ct_pa",
    "order_imaging_echo_transthoracic": "order_echocardiogram",
    "order_imaging_ultrasound_lower_extremity": "order_imaging_lower_extremity_doppler",
    "order_lab_arterial_blood_gas": "order_lab_abg",
    # COPD
    "give_medication_albuterol": "give_bronchodilator",
    "give_medication_ipratropium": "give_bronchodilator",
    "give_medication_steroids": "give_systemic_corticosteroid",
    "give_medication_antibiotics": "give_antibiotics",
    "order_procedure_niv": "initiate_niv",
    "order_procedure_intubation": "intubate_if_niv_fails",
    "consult_respiratory": "consult_pulmonology",
    "order_medication_furosemide": "give_diuretic",
    "order_medication_normal_saline_30mlkg": "give_iv_fluids",
    "order_medication_vasopressor_norepinephrine": "give_vasopressor",
    # Heart Failure
    "assess_volume_status": "assess_hemodynamic_profile",
    "assess_perfusion_status": "assess_hemodynamic_profile",
    "give_iv_diuretic": "iv_diuretics",
    "give_vasodilator": "add_vasodilator_if_hypertensive",
    "order_imaging_cxr": "order_imaging_chest_xray",
    "order_imaging_echo": "order_echocardiogram",
    "order_lab_bnp": "order_bnp_or_ntprobnp",
    "order_lab_ntproBNP": "order_bnp_or_ntprobnp",
    # Hemorrhagic Stroke
    "assess_airway": "assess_vital_signs",
    "give_medication_labetalol_iv": "bp_reduction_target_140",
    "give_medication_nicardipine_iv": "bp_reduction_target_140",
    "give_medication_mannitol": "give_osmotic_therapy",
    "give_medication_levetiracetam": "give_antiseizure_prophylaxis",
    "give_medication_prothrombin_complex_concentrate": "reverse_anticoagulation_if_applicable",
    "order_imaging_ct_head_noncontrast": "stat_ct_head",
    "order_imaging_ct_head_angiography": "order_ct_angiography",
    "order_imaging_ct_head_repeat": "repeat_ct_head",
    "place_external_ventricular_drain": "place_evd_if_hydrocephalus",
    "order_lab_fibrinogen": "order_lab_coagulation",
    "order_lab_serum_sodium": "order_lab_bmp",
    # Common cross-domain
    "consult_intensive_care": "admit_to_icu",
    "consult_pulmonology": "consult_pulmonology",
    "order_lab_inr": "order_lab_coagulation",
    "order_lab_hgb": "order_lab_cbc",
    # N4 fix: cross-domain override removed (was: "order_lab_creatinine": "order_lab_bmp").
    # AKI graphs reference order_lab_creatinine directly (19 occurrences); the BMP collapse
    # silently broke AKI matching. If a future CPG genuinely needs BMP-collapse, scope it via
    # _DEFAULT_DOMAIN_SPECIFIC_MAPPINGS, not flat DIRECT_MAPPINGS.
    # ========================================
    # Hemorrhagic Stroke Mappings
    # ========================================
    "order_imaging_head_ct": "order_stat_ct_head",
    "consult_neurosurgery": "neurosurgery_consult",
    "give_medication_antihypertensive": "bp_reduction_target_140",
    "give_medication_bp_control": "bp_reduction_target_140",
    "give_medication_labetalol": "bp_reduction_target_140",
    "give_medication_nicardipine": "bp_reduction_target_140",
    "give_medication_tranexamic_acid": "reverse_anticoagulation_if_applicable",
    # ========================================
    # NOTE: v6 normalizer expansion attempted in commit cc02ed76 (2026-04-25),
    # then REVERTED — see docs/critical_review/normalizer_v6_revert.md.
    # Reason: aliases were over-aggressive (e.g. reassess_perfusion →
    # reassess_vital_signs is a clinical-concept collapse, not a synonym).
    # The runtime fuzzy/pattern matching was already handling these correctly;
    # explicit direct_mappings overrode and *broke* working cases.
    # Future v2 benchmark work should redesign aliases from pre-validated
    # CPG corpus rather than ad-hoc collection.
    # ========================================
}

_DEFAULT_PATTERN_RULES: list[NormalizationRule] = [
    # order_X → order_lab_X (검사 주문)
    NormalizationRule(
        pattern=r"^order_(?!lab_|imaging_)(\w+)$",
        replacement=r"order_lab_\1",
        description="Add 'lab_' prefix to lab orders",
        priority=100,
    ),
    # give_vasopressor_X 또는 start_X (승압제)
    NormalizationRule(
        pattern=r"^(?:give_|administer_|initiate_)(norepinephrine|vasopressin|epinephrine|dopamine|phenylephrine)$",
        replacement=r"start_vasopressor_\1",
        description="Standardize vasopressor start actions",
        priority=90,
    ),
    # start_X → start_vasopressor_X (승압제)
    NormalizationRule(
        pattern=r"^start_(?!vasopressor_)(norepinephrine|vasopressin|epinephrine|dopamine|phenylephrine)$",
        replacement=r"start_vasopressor_\1",
        description="Add 'vasopressor_' prefix",
        priority=85,
    ),
    # fluid → crystalloid
    NormalizationRule(
        pattern=r"^(?:give_|administer_)?(?:iv_)?fluid(?:s)?(?:_resuscitation)?$",
        replacement="give_crystalloid_fluid",
        description="Standardize fluid orders",
        priority=80,
    ),
    # bolus → 30ml_kg
    NormalizationRule(
        pattern=r"^(?:give_|administer_)?(?:fluid_)?bolus$",
        replacement="give_crystalloid_30ml_kg",
        description="Standardize fluid bolus",
        priority=75,
    ),
    # check_X → assess_X
    NormalizationRule(
        pattern=r"^check_(.+)$", replacement=r"assess_\1", description="Standardize assessment actions", priority=50
    ),
    # get_X → obtain_X (ECG 등)
    NormalizationRule(
        pattern=r"^get_(ecg|ekg|12_lead|blood|vitals)$",
        replacement=r"obtain_\1",
        description="Standardize obtain actions",
        priority=45,
    ),
    # administer_X → give_X
    NormalizationRule(
        pattern=r"^administer_(.+)$",
        replacement=r"give_\1",
        description="Standardize medication administration",
        priority=40,
    ),
]

_DEFAULT_SYNONYM_GROUPS: dict[str, list[str]] = {
    "give_broad_spectrum_antibiotics": [
        "antibiotics",
        "abx",
        "empiric_abx",
        "iv_antibiotics",
        "broad_spectrum_abx",
        "sepsis_antibiotics",
    ],
    "give_crystalloid_30ml_kg": ["30ml_kg_bolus", "resuscitation_fluids", "sepsis_fluids"],
    "start_vasopressor_norepinephrine": ["norepi", "levo", "levophed", "pressor"],
    "order_lab_blood_culture": ["bc", "bld_cx", "blood_cx"],
    "obtain_12_lead_ecg": ["12lead", "12-lead", "ecg_12lead"],
    # Normalizer Gap Fix: monitoring frequency subsumption
    "monitor_creatinine": [
        "monitor_creatinine_daily",
        "monitor_creatinine_q12h",
        "monitor_creatinine_q6h",
        "monitor_creatinine_q4h",
        "monitor_serum_creatinine_48_72h",
    ],
    "monitor_potassium": [
        "monitor_potassium_q6h",
        "monitor_potassium_q4h",
        "monitor_potassium_q2h",
    ],
    "give_systemic_corticosteroid": [
        "give_systemic_corticosteroid_iv",
        "give_hydrocortisone_iv",
        "give_methylprednisolone_iv",
        "give_dexamethasone_iv",
        "prescribe_oral_corticosteroid_5_day",
    ],
    "consult_nephrology": [
        "nephrology_consult",
        "consult_nephrology_if_needed",
        "urgent_nephrology_consult",
        "renal_consult",
    ],
    "monitor_serum_creatinine_48_72h": [
        "assess_serum_creatinine_at_48h",
        "assess_serum_creatinine_at_72h",
        "post_procedure_creatinine_48_72h",
        "check_scr_at_72h",
        "check_scr_at_48h",
    ],
}

# ============================================
# 도메인별 매핑 오버라이드 (H3 Fix: 도메인 간 충돌 방지)
# cpg_id가 제공되면 이 매핑이 범용 매핑보다 우선합니다.
# ============================================
_DEFAULT_DOMAIN_SPECIFIC_MAPPINGS: dict[str, dict[str, str]] = {
    "aha_stroke": {
        # Stroke에서 aspirin은 antiplatelet_therapy로 매핑
        "aspirin": "antiplatelet_therapy",
        "give_aspirin": "antiplatelet_therapy",
        "start_aspirin": "antiplatelet_therapy",
        # Stroke에서 physical_therapy는 early_mobilization
        "physical_therapy": "early_mobilization",
        "pt": "early_mobilization",
        "rehabilitation": "early_mobilization",
        # Stroke에서 tPA는 alteplase
        "tpa": "give_alteplase_0.9mg_kg",
        "alteplase": "give_alteplase_0.9mg_kg",
        "thrombolytic": "give_alteplase_0.9mg_kg",
    },
    "aha_chest_pain": {
        # Chest pain에서 aspirin은 loading dose
        "aspirin": "give_aspirin_loading",
        "give_aspirin": "give_aspirin_loading",
        "start_aspirin": "give_aspirin_loading",
        # Chest pain에서 physical_therapy는 그대로
        "physical_therapy": "physical_therapy",
    },
    "aha_heart_failure": {
        # Heart failure에서 aspirin은 특정 용법
        "aspirin": "give_aspirin",
        # Heart failure에서 diuretic은 loop diuretic
        "diuretic": "give_iv_furosemide",
        "furosemide": "give_iv_furosemide",
        "lasix": "give_iv_furosemide",
        # N1 Fix: HF CPG uses different lab/imaging action IDs than sepsis
        "order_bmp": "order_basic_metabolic_panel",
        "bmp": "order_basic_metabolic_panel",
        "order_cbc": "order_cbc",
        "cbc": "order_cbc",
        "complete_blood_count": "order_cbc",
        "order_ecg": "order_ecg",
        "order_chest_xray": "order_chest_xray",
        # N1 Fix: HF uses monitor_urine_output (vs AKI's assess_urine_output)
        "urine_output": "monitor_urine_output",
        "check_urine_output": "monitor_urine_output",
        # P6 Fix: Identity mappings for domain targets to prevent generic remapping.
        # Without these, mandatory action IDs like "give_iv_furosemide" would
        # fall through to generic mappings (→ "iv_diuretics"), causing mismatch
        # when comparing normalized performed actions vs normalized mandatory actions.
        "give_iv_furosemide": "give_iv_furosemide",
        "give_aspirin": "give_aspirin",
        "monitor_urine_output": "monitor_urine_output",
        # Moved from generic: HF uses continuous_monitoring (not continuous_cardiac_monitoring)
        "cardiac_monitoring": "continuous_monitoring",
        "telemetry_monitoring": "continuous_monitoring",
    },
    "ssc_sepsis_hour1_bundle": {
        # Sepsis에서 fluid는 30ml/kg crystalloid
        "fluid": "give_crystalloid_30ml_kg",
        "fluids": "give_crystalloid_30ml_kg",
        "iv_fluid": "give_crystalloid_30ml_kg",
        "bolus": "give_crystalloid_30ml_kg",
    },
}

_DEFAULT_CPG_ALLOWED_ACTIONS: dict[str, set[str]] = {
    "ssc_sepsis_hour1_bundle": {
        # initial_recognition
        "assess_infection_source",
        "assess_organ_dysfunction",
        "order_lab_lactate",
        "order_lab_blood_culture",
        # sepsis_bundle
        "give_broad_spectrum_antibiotics",
        "give_crystalloid_fluid",
        "order_lab_cbc",
        "order_lab_bmp",
        "order_lab_coagulation",
        "order_imaging_chest_xray",
        "reassess_perfusion",
        # septic_shock_bundle
        "give_crystalloid_30ml_kg",
        "start_vasopressor_norepinephrine",
        "start_vasopressor_vasopressin",
        "order_lab_procalcitonin",
        "place_central_line",
        "place_arterial_line",
        # reassessment
        "remeasure_lactate_if_elevated",
        "adjust_vasopressor",
        "additional_fluid_bolus",
        "order_echocardiogram",
        "escalate_to_icu",
        # disposition
        "admit_to_icu",
        "admit_to_ward",
        "transfer_to_higher_care",
        "continue_vasopressor",
        "arterial_line_monitoring",
        "central_line_access",
        "continue_antibiotics",
        "serial_lactate_monitoring",
    },
    "aha_chest_pain_evaluation": {
        # initial_assessment
        "obtain_12_lead_ecg",
        "assess_vital_signs",
        "obtain_chest_pain_history",
        "establish_iv_access",
        "order_lab_troponin",
        "administer_oxygen_if_hypoxic",
        # ecg_interpretation
        "interpret_ecg",
        "obtain_prior_ecg_comparison",
        "request_cardiology_consult",
        # stemi_pathway
        "activate_cath_lab",
        "give_aspirin_loading",
        "give_p2y12_inhibitor",
        "give_anticoagulation",
        "give_nitrates_if_indicated",
        "give_morphine_if_needed",
        "give_beta_blocker_if_stable",
        "arrange_pci",
        "consider_fibrinolysis_if_pci_delayed",
        # nste_acs_pathway
        "calculate_risk_score",
        "order_echocardiogram",
        # risk_stratification
        "order_serial_ecg",
        "order_chest_xray",
        "obtain_detailed_history",
        # observation_pathway
        "serial_troponin",
        "serial_ecg",
        "stress_testing_or_cta",
        "admit_to_observation",
        # low_risk_pathway
        "document_risk_assessment",
        "provide_discharge_instructions",
        "schedule_outpatient_followup",
        "consider_outpatient_stress_test",
        # post_pci_care
        "admit_to_ccu",
        "continue_dual_antiplatelet",
        "initiate_secondary_prevention",
        "echocardiogram_post_mi",
        "cardiac_rehabilitation_referral",
        # admit_to_cardiology
        "admit_to_cardiology_service",
        "continue_medical_therapy",
        "schedule_catheterization",
        # disposition
        "admit_to_hospital",
        "discharge_with_followup",
        "transfer_to_higher_care",
        "assess_for_early_invasive",
        "determine_disposition",
    },
}


_DEFAULT_NORMALIZER: ActionNormalizer | None = None
_NORMALIZER_LOCK = __import__("threading").Lock()


def get_default_normalizer() -> ActionNormalizer:
    """기본 설정의 ActionNormalizer 싱글톤 반환 (모듈 수준 캐싱, thread-safe)"""
    global _DEFAULT_NORMALIZER
    if _DEFAULT_NORMALIZER is None:
        with _NORMALIZER_LOCK:
            # Double-checked locking
            if _DEFAULT_NORMALIZER is None:
                _DEFAULT_NORMALIZER = ActionNormalizer()
    return _DEFAULT_NORMALIZER


def create_default_normalizer() -> ActionNormalizer:
    """기본 설정의 ActionNormalizer 생성 (하위 호환성)"""
    return get_default_normalizer()


def normalize_action_id(action_id: str, cpg_id: str | None = None) -> str:
    """간편 함수: Action ID 정규화 (싱글톤 사용)

    Args:
        action_id: 원본 action ID
        cpg_id: CPG 식별자 (선택)

    Returns:
        정규화된 action ID
    """
    return get_default_normalizer().normalize(action_id, cpg_id)
