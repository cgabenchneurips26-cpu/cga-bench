"""Hard Negative Mining for Domain-Specific Entity Linking Fine-tuning.

Generates training data with hard negatives for improving entity linking:
1. DHNS-style: Dynamic Hard Negative Sampling from model's top-K errors
2. Confusable pairs: Surface-form similar but semantically different
3. Type traps: Same surface form, different semantic type (lactate vs lactated_ringers)

References:
- kNN-BioEL (2024): Dynamic Hard Negative Sampling
- ANGEL (ACL 2025): Negative-aware training for generative EL
- BioSyn (2020): Synonym marginalization with hard negatives
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class NegativeType(str, Enum):
    """Type of hard negative."""
    MODEL_CONFUSION = "model_confusion"     # Model's top-K errors (DHNS)
    SURFACE_SIMILAR = "surface_similar"     # Lexically similar, different meaning
    TYPE_TRAP = "type_trap"                 # Same surface, different semantic type
    SIBLING = "sibling"                     # Same parent in ontology
    BRAND_GENERIC = "brand_generic"         # Brand name vs generic class
    ABBREVIATION = "abbreviation"           # Abbreviation vs full form confusion


@dataclass
class HardNegative:
    """A single hard negative example.

    Attributes:
        query: Original query text
        gold_concept_id: Correct concept
        negative_concept_id: Hard negative concept
        negative_type: Type of confusion
        model_score: Model's score for the negative (if applicable)
        gold_score: Model's score for the gold (if applicable)
        surface_similarity: Lexical similarity between gold and negative
        notes: Human-readable explanation
    """
    query: str
    gold_concept_id: str
    negative_concept_id: str
    negative_type: NegativeType
    model_score: float = 0.0
    gold_score: float = 0.0
    surface_similarity: float = 0.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "gold_concept_id": self.gold_concept_id,
            "negative_concept_id": self.negative_concept_id,
            "negative_type": self.negative_type.value,
            "model_score": self.model_score,
            "gold_score": self.gold_score,
            "surface_similarity": self.surface_similarity,
            "notes": self.notes,
        }


@dataclass
class TrainingTriple:
    """Training triple for contrastive learning.

    Format: (query, positive, negative)
    Used for margin-based or InfoNCE loss.
    """
    query: str
    positive_id: str
    positive_text: str
    negative_id: str
    negative_text: str
    negative_type: NegativeType
    margin: float = 0.3  # Desired margin between positive and negative

    def to_contrastive_format(self) -> Dict[str, Any]:
        """Format for sentence-transformers contrastive training."""
        return {
            "query": self.query,
            "positive": self.positive_text,
            "negative": self.negative_text,
            "label": 1,  # Positive should rank higher
        }

    def to_triplet_format(self) -> Tuple[str, str, str]:
        """Format for triplet loss: (anchor, positive, negative)."""
        return (self.query, self.positive_text, self.negative_text)


@dataclass
class MiningConfig:
    """Configuration for hard negative mining.

    Attributes:
        top_k_negatives: Number of negatives to mine per query
        min_surface_similarity: Minimum lexical similarity for surface-similar negatives
        max_surface_similarity: Maximum similarity (avoid near-duplicates)
        include_model_errors: Mine from model's top-K errors
        include_type_traps: Mine type confusion cases
        include_siblings: Mine sibling concepts from ontology
        model_error_threshold: Score threshold for model errors
    """
    top_k_negatives: int = 5
    min_surface_similarity: float = 0.3
    max_surface_similarity: float = 0.9
    include_model_errors: bool = True
    include_type_traps: bool = True
    include_siblings: bool = True
    model_error_threshold: float = 0.5


class HardNegativeMiner:
    """Mine hard negatives from gold set and model predictions.

    Strategy:
    1. Run model on gold set queries
    2. Collect top-K predictions that are NOT the gold
    3. Filter by negative type (model confusion, type trap, sibling)
    4. Output training data for fine-tuning

    Usage:
        miner = HardNegativeMiner(embedder, ontology, config)

        # Mine from gold set
        negatives = miner.mine_from_gold_set(gold_set)

        # Export for training
        miner.export_training_data(negatives, Path("train_negatives.jsonl"))
    """

    def __init__(
        self,
        embedder: Any,  # NeuralEmbedder
        ontology: Optional[Any] = None,  # ClinicalOntology for sibling detection
        config: Optional[MiningConfig] = None,
    ):
        self._embedder = embedder
        self._ontology = ontology
        self._config = config or MiningConfig()
        self._concept_texts: Dict[str, str] = {}
        self._concept_types: Dict[str, str] = {}

    def set_concept_metadata(
        self,
        concepts: List[Tuple[str, str, str]],  # (id, display, type)
    ) -> None:
        """Set concept metadata for text lookup."""
        for cid, display, ctype in concepts:
            self._concept_texts[cid] = display
            self._concept_types[cid] = ctype

    def mine_from_gold_set(
        self,
        gold_set: List[Tuple[str, str]],  # (query, gold_concept_id)
    ) -> List[HardNegative]:
        """Mine hard negatives from gold set.

        For each gold instance:
        1. Run model to get top-K predictions
        2. Collect non-gold predictions as potential negatives
        3. Classify negative type
        4. Filter by configuration

        Args:
            gold_set: List of (query, gold_concept_id) pairs

        Returns:
            List of HardNegative instances.
        """
        all_negatives: List[HardNegative] = []

        for query, gold_cid in gold_set:
            # Get model predictions
            matches = self._embedder.find_similar(
                query,
                top_k=self._config.top_k_negatives + 5,
                log_execution=False,
            )

            # Find gold rank and score
            gold_score = 0.0
            gold_rank = -1
            for i, m in enumerate(matches):
                if m.concept_id == gold_cid:
                    gold_score = m.similarity
                    gold_rank = i
                    break

            # Collect negatives (non-gold predictions above threshold)
            for match in matches:
                if match.concept_id == gold_cid:
                    continue

                # Determine negative type
                neg_type = self._classify_negative(
                    query, gold_cid, match.concept_id, match.similarity
                )

                if neg_type is None:
                    continue

                # Calculate surface similarity
                gold_text = self._concept_texts.get(gold_cid, gold_cid)
                neg_text = self._concept_texts.get(match.concept_id, match.concept_id)
                surface_sim = self._jaccard_similarity(gold_text, neg_text)

                # Filter by surface similarity bounds
                if not (self._config.min_surface_similarity <= surface_sim <= self._config.max_surface_similarity):
                    if neg_type != NegativeType.MODEL_CONFUSION:
                        continue

                negative = HardNegative(
                    query=query,
                    gold_concept_id=gold_cid,
                    negative_concept_id=match.concept_id,
                    negative_type=neg_type,
                    model_score=match.similarity,
                    gold_score=gold_score,
                    surface_similarity=surface_sim,
                    notes=self._generate_notes(neg_type, gold_cid, match.concept_id),
                )
                all_negatives.append(negative)

                # Limit negatives per query
                query_negatives = [n for n in all_negatives if n.query == query]
                if len(query_negatives) >= self._config.top_k_negatives:
                    break

        logger.info(f"Mined {len(all_negatives)} hard negatives from {len(gold_set)} gold instances")
        return all_negatives

    def mine_type_traps(
        self,
        trap_definitions: List[Dict[str, Any]],
    ) -> List[HardNegative]:
        """Mine type trap cases from predefined confusable pairs.

        Type traps are cases where surface forms are similar but semantic
        types differ (e.g., "lactate" as LAB vs "lactated ringers" as FLUID).

        Args:
            trap_definitions: List of dicts with:
                - query: confusable surface form
                - gold_concept_id: correct concept
                - trap_concept_id: confusable concept (wrong type)
                - gold_type: correct semantic type
                - trap_type: wrong semantic type

        Returns:
            List of HardNegative instances.
        """
        negatives = []

        for trap in trap_definitions:
            query = trap["query"]
            gold_cid = trap["gold_concept_id"]
            trap_cid = trap["trap_concept_id"]

            # Get model scores
            matches = self._embedder.find_similar(query, top_k=10, log_execution=False)

            gold_score = 0.0
            trap_score = 0.0
            for m in matches:
                if m.concept_id == gold_cid:
                    gold_score = m.similarity
                elif m.concept_id == trap_cid:
                    trap_score = m.similarity

            gold_text = self._concept_texts.get(gold_cid, gold_cid)
            trap_text = self._concept_texts.get(trap_cid, trap_cid)

            negative = HardNegative(
                query=query,
                gold_concept_id=gold_cid,
                negative_concept_id=trap_cid,
                negative_type=NegativeType.TYPE_TRAP,
                model_score=trap_score,
                gold_score=gold_score,
                surface_similarity=self._jaccard_similarity(gold_text, trap_text),
                notes=f"Type trap: {trap.get('gold_type', '')} vs {trap.get('trap_type', '')}",
            )
            negatives.append(negative)

        logger.info(f"Generated {len(negatives)} type trap negatives")
        return negatives

    def mine_brand_generic_pairs(
        self,
        brand_mappings: List[Dict[str, str]],
    ) -> List[HardNegative]:
        """Mine brand name to generic class confusions.

        Args:
            brand_mappings: List of dicts with:
                - brand: brand name query
                - generic_class: correct generic concept
                - confusion: commonly confused concept

        Returns:
            List of HardNegative instances.
        """
        negatives = []

        for mapping in brand_mappings:
            brand = mapping["brand"]
            generic_cid = mapping["generic_class"]
            confusion_cid = mapping.get("confusion", "")

            if not confusion_cid:
                continue

            # Get model predictions
            matches = self._embedder.find_similar(brand, top_k=10, log_execution=False)

            gold_score = 0.0
            conf_score = 0.0
            for m in matches:
                if m.concept_id == generic_cid:
                    gold_score = m.similarity
                elif m.concept_id == confusion_cid:
                    conf_score = m.similarity

            negative = HardNegative(
                query=brand,
                gold_concept_id=generic_cid,
                negative_concept_id=confusion_cid,
                negative_type=NegativeType.BRAND_GENERIC,
                model_score=conf_score,
                gold_score=gold_score,
                surface_similarity=0.0,
                notes=f"Brand→Generic: {brand} should map to {generic_cid}, not {confusion_cid}",
            )
            negatives.append(negative)

        return negatives

    def _classify_negative(
        self,
        query: str,
        gold_cid: str,
        neg_cid: str,
        neg_score: float,
    ) -> Optional[NegativeType]:
        """Classify the type of negative example.

        Returns None if the negative should be filtered out.
        """
        # Model confusion: high-scoring non-gold prediction
        if self._config.include_model_errors and neg_score >= self._config.model_error_threshold:
            return NegativeType.MODEL_CONFUSION

        # Type trap: same surface form, different type
        if self._config.include_type_traps:
            gold_type = self._concept_types.get(gold_cid, "")
            neg_type = self._concept_types.get(neg_cid, "")
            if gold_type and neg_type and gold_type != neg_type:
                gold_text = self._concept_texts.get(gold_cid, "").lower()
                neg_text = self._concept_texts.get(neg_cid, "").lower()
                # Check if surface forms overlap significantly
                if self._jaccard_similarity(gold_text, neg_text) > 0.3:
                    return NegativeType.TYPE_TRAP

        # Sibling: same parent in ontology
        if self._config.include_siblings and self._ontology:
            gold_parents = self._ontology.direct_parents(gold_cid)
            neg_parents = self._ontology.direct_parents(neg_cid)
            if gold_parents & neg_parents:
                return NegativeType.SIBLING

        # Surface similar: lexically similar but different concept
        gold_text = self._concept_texts.get(gold_cid, gold_cid)
        neg_text = self._concept_texts.get(neg_cid, neg_cid)
        sim = self._jaccard_similarity(gold_text, neg_text)
        if self._config.min_surface_similarity <= sim <= self._config.max_surface_similarity:
            return NegativeType.SURFACE_SIMILAR

        return None

    def _generate_notes(
        self,
        neg_type: NegativeType,
        gold_cid: str,
        neg_cid: str,
    ) -> str:
        """Generate human-readable notes for negative."""
        gold_text = self._concept_texts.get(gold_cid, gold_cid)
        neg_text = self._concept_texts.get(neg_cid, neg_cid)

        if neg_type == NegativeType.MODEL_CONFUSION:
            return f"Model confused '{gold_text}' with '{neg_text}'"
        elif neg_type == NegativeType.TYPE_TRAP:
            gold_type = self._concept_types.get(gold_cid, "?")
            neg_type_str = self._concept_types.get(neg_cid, "?")
            return f"Type confusion: {gold_type} vs {neg_type_str}"
        elif neg_type == NegativeType.SIBLING:
            return f"Sibling concepts: '{gold_text}' and '{neg_text}'"
        elif neg_type == NegativeType.SURFACE_SIMILAR:
            return f"Surface similar: '{gold_text}' vs '{neg_text}'"
        else:
            return ""

    @staticmethod
    def _jaccard_similarity(text_a: str, text_b: str) -> float:
        """Compute Jaccard similarity between tokenized texts."""
        tokens_a = set(text_a.lower().replace("_", " ").split())
        tokens_b = set(text_b.lower().replace("_", " ").split())
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

    def to_training_triples(
        self,
        negatives: List[HardNegative],
    ) -> List[TrainingTriple]:
        """Convert hard negatives to training triples.

        Args:
            negatives: List of HardNegative instances

        Returns:
            List of TrainingTriple for contrastive learning.
        """
        triples = []

        for neg in negatives:
            positive_text = self._concept_texts.get(neg.gold_concept_id, neg.gold_concept_id)
            negative_text = self._concept_texts.get(neg.negative_concept_id, neg.negative_concept_id)

            triple = TrainingTriple(
                query=neg.query,
                positive_id=neg.gold_concept_id,
                positive_text=positive_text,
                negative_id=neg.negative_concept_id,
                negative_text=negative_text,
                negative_type=neg.negative_type,
            )
            triples.append(triple)

        return triples

    def export_training_data(
        self,
        negatives: List[HardNegative],
        output_path: Path,
        format: str = "jsonl",
    ) -> None:
        """Export hard negatives for training.

        Args:
            negatives: List of HardNegative instances
            output_path: Output file path
            format: Output format ("jsonl", "triplet", "contrastive")
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        triples = self.to_training_triples(negatives)

        with open(output_path, "w") as f:
            for triple in triples:
                if format == "triplet":
                    line = json.dumps(triple.to_triplet_format())
                elif format == "contrastive":
                    line = json.dumps(triple.to_contrastive_format())
                else:  # jsonl
                    line = json.dumps({
                        "query": triple.query,
                        "positive_id": triple.positive_id,
                        "positive_text": triple.positive_text,
                        "negative_id": triple.negative_id,
                        "negative_text": triple.negative_text,
                        "negative_type": triple.negative_type.value,
                    })
                f.write(line + "\n")

        logger.info(f"Exported {len(triples)} training examples to {output_path}")

    def generate_analysis_report(
        self,
        negatives: List[HardNegative],
    ) -> str:
        """Generate analysis report for mined negatives."""
        lines = [
            "# Hard Negative Mining Report",
            "",
            f"**Total negatives mined**: {len(negatives)}",
            "",
            "## Distribution by Type",
            "",
        ]

        # Count by type
        type_counts = defaultdict(int)
        for neg in negatives:
            type_counts[neg.negative_type.value] += 1

        for neg_type, count in sorted(type_counts.items()):
            pct = count / len(negatives) * 100 if negatives else 0
            lines.append(f"- **{neg_type}**: {count} ({pct:.1f}%)")

        lines.extend([
            "",
            "## Score Distribution",
            "",
        ])

        # Score analysis
        if negatives:
            model_scores = [n.model_score for n in negatives]
            gold_scores = [n.gold_score for n in negatives]

            lines.extend([
                f"- Model score (negatives): mean={sum(model_scores)/len(model_scores):.3f}",
                f"- Gold score: mean={sum(gold_scores)/len(gold_scores):.3f}",
            ])

            # Cases where negative scored higher than gold
            higher_neg = sum(1 for n in negatives if n.model_score > n.gold_score)
            lines.append(f"- Negatives scoring higher than gold: {higher_neg} ({higher_neg/len(negatives)*100:.1f}%)")

        lines.extend([
            "",
            "## Example Cases",
            "",
            "| Query | Gold | Negative | Type | Neg Score | Gold Score |",
            "|-------|------|----------|------|-----------|------------|",
        ])

        # Top examples by score difference
        sorted_negs = sorted(negatives, key=lambda n: n.model_score - n.gold_score, reverse=True)
        for neg in sorted_negs[:10]:
            lines.append(
                f"| {neg.query[:20]} | {neg.gold_concept_id[:15]} | "
                f"{neg.negative_concept_id[:15]} | {neg.negative_type.value} | "
                f"{neg.model_score:.3f} | {neg.gold_score:.3f} |"
            )

        return "\n".join(lines)


# ============================================================
# Predefined Type Traps (CGA-Bench specific)
# ============================================================

CGA_TYPE_TRAPS = [
    {
        "query": "lactate",
        "gold_concept_id": "order_lab_lactate",
        "trap_concept_id": "give_lactated_ringers",
        "gold_type": "LAB",
        "trap_type": "FLUID",
        "notes": "Lactate (lab test) vs Lactated Ringers (IV fluid)",
    },
    {
        "query": "culture",
        "gold_concept_id": "order_lab_blood_culture",
        "trap_concept_id": "culture_result",
        "gold_type": "LAB",
        "trap_type": "PROCEDURE",
        "notes": "Blood culture order vs culture result review",
    },
    {
        "query": "troponin",
        "gold_concept_id": "order_lab_troponin",
        "trap_concept_id": "order_bnp",
        "gold_type": "LAB",
        "trap_type": "LAB",
        "notes": "Cardiac biomarker confusion (sibling)",
    },
    {
        "query": "pressors",
        "gold_concept_id": "start_vasopressor_norepinephrine",
        "trap_concept_id": "start_vasopressor_vasopressin",
        "gold_type": "DRUG",
        "trap_type": "DRUG",
        "notes": "Vasopressor sibling confusion",
    },
]

CGA_BRAND_MAPPINGS = [
    {
        "brand": "levophed",
        "generic_class": "start_vasopressor_norepinephrine",
        "confusion": "start_vasopressor_dopamine",
    },
    {
        "brand": "entresto",
        "generic_class": "initiate_ace_or_arb_or_arni",
        "confusion": "initiate_ace_inhibitor",
    },
    {
        "brand": "tPA",
        "generic_class": "give_alteplase_0.9mg_kg",
        "confusion": "give_tenecteplase",
    },
    {
        "brand": "lasix",
        "generic_class": "give_furosemide",
        "confusion": "give_bumetanide",
    },
]


def create_cga_hard_negatives(
    embedder: Any,
    gold_set: List[Tuple[str, str]],
    output_dir: Path,
) -> Dict[str, Any]:
    """Create complete hard negative dataset for CGA-Bench.

    Args:
        embedder: NeuralEmbedder instance
        gold_set: List of (query, gold_concept_id) pairs
        output_dir: Output directory for training data

    Returns:
        Statistics dict.
    """
    miner = HardNegativeMiner(embedder, config=MiningConfig(
        top_k_negatives=5,
        include_model_errors=True,
        include_type_traps=True,
    ))

    # Mine from gold set (DHNS-style)
    gold_negatives = miner.mine_from_gold_set(gold_set)

    # Mine type traps
    type_trap_negatives = miner.mine_type_traps(CGA_TYPE_TRAPS)

    # Mine brand-generic confusions
    brand_negatives = miner.mine_brand_generic_pairs(CGA_BRAND_MAPPINGS)

    # Combine all negatives
    all_negatives = gold_negatives + type_trap_negatives + brand_negatives

    # Export
    output_dir.mkdir(parents=True, exist_ok=True)
    miner.export_training_data(all_negatives, output_dir / "hard_negatives.jsonl")
    miner.export_training_data(all_negatives, output_dir / "hard_negatives_triplet.jsonl", format="triplet")

    # Generate report
    report = miner.generate_analysis_report(all_negatives)
    with open(output_dir / "hard_negative_report.md", "w") as f:
        f.write(report)

    return {
        "total_negatives": len(all_negatives),
        "from_gold_set": len(gold_negatives),
        "from_type_traps": len(type_trap_negatives),
        "from_brand_mappings": len(brand_negatives),
        "output_dir": str(output_dir),
    }
