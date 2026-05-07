"""
ArchEHR-QA Adapter
EHR Sentence-level Evidence Alignment + Clinician-generated Answers

Data Source: PhysioNet (Credentialed Access Required)
URL: https://physionet.org/content/archehr-qa-bionlp-task-2025/1.3/

ArchEHR-QA Structure:
- Patient narrative question (from health forums)
- Clinician-interpreted question
- Clinical note excerpts (from MIMIC-III/IV)
- Sentence-level annotations: essential, supplementary, not-relevant
- Clinician-authored reference answers with citations

Episode Structure:
- episode = 1 QA case
- event = ASK(patient_question) → RETRIEVE(ehr_evidence) → DOCUMENT(answer)
- state = selected EHR sentence set as state_delta

CPG Compliance Relevance:
- Evidence-based reasoning evaluation
- Grounding accuracy (correct sentence selection)
- Answer quality with proper citations
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum
import logging
import json
import xml.etree.ElementTree as ET

from cga_bench.env.adapters.base_adapter import (
    BaseAdapter,
    AdaptedEpisode,
    AdaptedAction,
)
from cga_bench.env.core.state import PatientState2
from cga_bench.env.core.actions import (
    Action2,
    ActionType2,
    ActionStatus,
)

logger = logging.getLogger(__name__)


class EvidenceRelevance(Enum):
    """ArchEHR-QA evidence relevance levels"""
    ESSENTIAL = "essential"           # Required for answering
    SUPPLEMENTARY = "supplementary"   # Helpful but not required
    NOT_RELEVANT = "not-relevant"     # Not needed


@dataclass
class EHRSentence:
    """Single EHR sentence with annotation"""
    sentence_id: str
    text: str
    relevance: EvidenceRelevance
    note_id: Optional[str] = None
    section: Optional[str] = None


@dataclass
class ArchEHRCase:
    """Single ArchEHR-QA case"""
    case_id: str
    patient_question: str
    clinician_question: str
    clinical_notes: List[EHRSentence] = field(default_factory=list)
    clinician_answer: Optional[str] = None
    answer_citations: List[str] = field(default_factory=list)

    # Statistics
    total_sentences: int = 0
    essential_count: int = 0
    supplementary_count: int = 0
    not_relevant_count: int = 0


class ArchEHRQAAdapter(BaseAdapter):
    """
    ArchEHR-QA Adapter for Evidence-grounded Clinical QA

    IMPORTANT: This dataset requires PhysioNet credentialed access.
    Before using this adapter:
    1. Create a PhysioNet account at https://physionet.org/register/
    2. Complete CITI training for "Data or Specimens Only Research"
    3. Sign the Data Use Agreement
    4. Download from: https://physionet.org/content/archehr-qa-bionlp-task-2025/1.3/

    Data Files:
    - archehr-qa.xml: Main dataset with cases and annotations
    - archehr-qa_key.json: Answer key with clinician answers
    - archehr-qa_mapping.json: ID mappings to MIMIC databases
    """

    ACCESS_REQUIREMENTS = """
    ╔══════════════════════════════════════════════════════════════════╗
    ║  ArchEHR-QA Dataset - Credentialed Access Required               ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║  This is a PhysioNet credentialed-access resource.               ║
    ║                                                                   ║
    ║  Requirements:                                                    ║
    ║  1. PhysioNet credentialed user status                           ║
    ║  2. CITI "Data or Specimens Only Research" training              ║
    ║  3. Signed Data Use Agreement                                    ║
    ║                                                                   ║
    ║  Download: https://physionet.org/content/archehr-qa-bionlp-task-2025/1.3/
    ╚══════════════════════════════════════════════════════════════════╝
    """

    def __init__(self):
        super().__init__("ArchEHR-QA")
        self.cases: Dict[str, ArchEHRCase] = {}
        self.data_loaded = False

    def check_data_available(self, data_dir: Path) -> bool:
        """Check if ArchEHR-QA data files exist"""
        data_dir = Path(data_dir)
        required_files = [
            'archehr-qa.xml',
            'archehr-qa_key.json',
        ]

        for f in required_files:
            if not (data_dir / f).exists():
                return False
        return True

    def load_data(self, data_dir: Path) -> int:
        """
        Load ArchEHR-QA dataset from downloaded files

        Args:
            data_dir: Directory containing archehr-qa.xml and archehr-qa_key.json

        Returns:
            Number of cases loaded
        """
        data_dir = Path(data_dir)

        if not self.check_data_available(data_dir):
            logger.warning(self.ACCESS_REQUIREMENTS)
            raise FileNotFoundError(
                f"ArchEHR-QA data not found in {data_dir}. "
                "Please download from PhysioNet (credentialed access required)."
            )

        # Parse XML data
        xml_path = data_dir / 'archehr-qa.xml'
        self._parse_xml(xml_path)

        # Load answer key
        key_path = data_dir / 'archehr-qa_key.json'
        self._load_answer_key(key_path)

        self.data_loaded = True
        logger.info(f"Loaded {len(self.cases)} ArchEHR-QA cases")
        return len(self.cases)

    def _parse_xml(self, xml_path: Path):
        """Parse ArchEHR-QA XML file"""
        tree = ET.parse(xml_path)
        root = tree.getroot()

        for case_elem in root.findall('.//case'):
            case_id = case_elem.get('id', '')

            # Parse questions
            patient_q = case_elem.findtext('.//patient_question', '')
            clinician_q = case_elem.findtext('.//clinician_question', '')

            # Parse clinical notes with sentence annotations
            sentences = []
            for sent_elem in case_elem.findall('.//sentence'):
                sent_id = sent_elem.get('id', '')
                text = sent_elem.text or ''
                relevance_str = sent_elem.get('relevance', 'not-relevant')

                try:
                    relevance = EvidenceRelevance(relevance_str)
                except ValueError:
                    relevance = EvidenceRelevance.NOT_RELEVANT

                sentences.append(EHRSentence(
                    sentence_id=sent_id,
                    text=text,
                    relevance=relevance,
                    note_id=sent_elem.get('note_id'),
                    section=sent_elem.get('section'),
                ))

            # Create case
            case = ArchEHRCase(
                case_id=case_id,
                patient_question=patient_q,
                clinician_question=clinician_q,
                clinical_notes=sentences,
                total_sentences=len(sentences),
                essential_count=sum(1 for s in sentences if s.relevance == EvidenceRelevance.ESSENTIAL),
                supplementary_count=sum(1 for s in sentences if s.relevance == EvidenceRelevance.SUPPLEMENTARY),
                not_relevant_count=sum(1 for s in sentences if s.relevance == EvidenceRelevance.NOT_RELEVANT),
            )

            self.cases[case_id] = case

    def _load_answer_key(self, key_path: Path):
        """Load answer key JSON"""
        with open(key_path, 'r', encoding='utf-8') as f:
            key_data = json.load(f)

        for case_id, answer_data in key_data.items():
            if case_id in self.cases:
                self.cases[case_id].clinician_answer = answer_data.get('answer', '')
                self.cases[case_id].answer_citations = answer_data.get('citations', [])

    def load_patient(self, case_data: ArchEHRCase) -> PatientState2:
        """Create minimal patient state from ArchEHR-QA case"""
        state = PatientState2(state_id=f"archehr_{case_data.case_id}")
        state.chief_complaint = case_data.patient_question
        return state

    def convert_to_actions(self, case: ArchEHRCase) -> List[AdaptedAction]:
        """
        Convert ArchEHR-QA case to actions

        Event flow: ASK → RETRIEVE → DOCUMENT
        """
        actions = []

        # Action 1: ASK (patient question)
        ask_action = Action2(
            action_type=ActionType2.QUERY,
            action_id=f"ask_{hash(case.patient_question) % 10000}",
            target="patient_question",
            parameters={
                'patient_question': case.patient_question,
                'clinician_interpretation': case.clinician_question,
            },
            timestamp_minutes=0,
            status=ActionStatus.COMPLETED,
        )
        actions.append(AdaptedAction(
            original_action={'event': 'ASK', 'question': case.patient_question},
            cga_action=ask_action,
            mapping_confidence=0.95,
        ))

        # Action 2: RETRIEVE (evidence selection)
        essential_evidence = [s for s in case.clinical_notes if s.relevance == EvidenceRelevance.ESSENTIAL]
        supplementary_evidence = [s for s in case.clinical_notes if s.relevance == EvidenceRelevance.SUPPLEMENTARY]

        retrieve_action = Action2(
            action_type=ActionType2.RETRIEVE,
            action_id=f"retrieve_{case.case_id}",
            target="ehr_evidence",
            parameters={
                'total_sentences': case.total_sentences,
                'essential_count': len(essential_evidence),
                'supplementary_count': len(supplementary_evidence),
                'essential_sentences': [s.text for s in essential_evidence[:5]],  # Sample
            },
            timestamp_minutes=5,
            status=ActionStatus.COMPLETED,
        )
        actions.append(AdaptedAction(
            original_action={'event': 'RETRIEVE', 'evidence': essential_evidence},
            cga_action=retrieve_action,
            mapping_confidence=0.9,
        ))

        # Action 3: DOCUMENT (answer generation)
        if case.clinician_answer:
            doc_action = Action2(
                action_type=ActionType2.DOCUMENT,
                action_id=f"doc_{case.case_id}",
                target="clinical_answer",
                parameters={
                    'answer': case.clinician_answer,
                    'citations': case.answer_citations,
                },
                timestamp_minutes=10,
                status=ActionStatus.COMPLETED,
            )
            actions.append(AdaptedAction(
                original_action={'event': 'DOCUMENT', 'answer': case.clinician_answer},
                cga_action=doc_action,
                mapping_confidence=0.9,
            ))

        return actions

    def adapt_episode(self, case: ArchEHRCase) -> AdaptedEpisode:
        """Convert ArchEHR-QA case to AdaptedEpisode"""
        initial_state = self.load_patient(case)
        actions = self.convert_to_actions(case)

        # Evidence grounding success = essential sentences identified
        task_success = case.essential_count > 0 and case.clinician_answer is not None

        episode = AdaptedEpisode(
            episode_id=f"archehr_{case.case_id}",
            source_benchmark="ArchEHR-QA",
            original_task_id=case.case_id,
            initial_state=initial_state,
            actions=actions,
            guideline_id="cpg/runtime_dsl/archehr/evidence_grounding.yaml",
            task_success=task_success,
            original_metrics={
                'total_sentences': case.total_sentences,
                'essential_count': case.essential_count,
                'supplementary_count': case.supplementary_count,
                'not_relevant_count': case.not_relevant_count,
                'essential_ratio': case.essential_count / max(1, case.total_sentences),
            },
        )

        episode.adaptation_warnings = self.validate_adaptation(episode)
        return episode

    def convert_action(self, action_data: Dict) -> Optional[AdaptedAction]:
        """Not used for ArchEHR-QA"""
        return None

    def convert_action_log(self, action_log: List[Dict]) -> List[AdaptedAction]:
        """Not used for ArchEHR-QA"""
        return []

    def load_from_directory(self, data_dir: Path) -> List[AdaptedEpisode]:
        """Load all episodes from ArchEHR-QA data directory"""
        self.load_data(data_dir)

        episodes = []
        for case_id, case in self.cases.items():
            try:
                episode = self.adapt_episode(case)
                episodes.append(episode)
            except Exception as e:
                logger.warning(f"Failed to adapt case {case_id}: {e}")

        return episodes

    def get_statistics(self) -> Dict[str, Any]:
        """Get ArchEHR-QA dataset statistics"""
        if not self.cases:
            return {'error': 'No data loaded', 'access_info': self.ACCESS_REQUIREMENTS}

        total_sentences = sum(c.total_sentences for c in self.cases.values())
        total_essential = sum(c.essential_count for c in self.cases.values())
        total_supplementary = sum(c.supplementary_count for c in self.cases.values())
        total_not_relevant = sum(c.not_relevant_count for c in self.cases.values())

        return {
            'total_cases': len(self.cases),
            'total_sentences': total_sentences,
            'avg_sentences_per_case': total_sentences / max(1, len(self.cases)),
            'relevance_distribution': {
                'essential': total_essential,
                'supplementary': total_supplementary,
                'not_relevant': total_not_relevant,
            },
            'essential_ratio': total_essential / max(1, total_sentences),
            'supplementary_ratio': total_supplementary / max(1, total_sentences),
        }

    def evaluate_evidence_selection(
        self,
        selected_sentences: List[str],
        case: ArchEHRCase
    ) -> Dict[str, float]:
        """
        Evaluate evidence selection against ground truth

        Args:
            selected_sentences: Agent's selected sentence IDs
            case: Ground truth case

        Returns:
            Metrics: precision, recall, f1 for essential evidence
        """
        essential_ids = {s.sentence_id for s in case.clinical_notes
                        if s.relevance == EvidenceRelevance.ESSENTIAL}

        selected_set = set(selected_sentences)

        # Calculate metrics
        true_positives = len(selected_set & essential_ids)
        precision = true_positives / max(1, len(selected_set))
        recall = true_positives / max(1, len(essential_ids))
        f1 = 2 * precision * recall / max(0.001, precision + recall)

        return {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'essential_selected': true_positives,
            'total_selected': len(selected_set),
            'total_essential': len(essential_ids),
        }
