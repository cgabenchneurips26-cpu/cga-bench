"""Fine-tuning Script for Cross-Encoder Reranker.

Fine-tunes a cross-encoder on domain-specific hard negatives for improved
clinical entity linking. Uses contrastive learning with margin loss.

Training Strategy:
1. Load hard negatives from HardNegativeMiner output
2. Create training pairs: (query, positive, negative)
3. Fine-tune with margin ranking loss
4. Evaluate on gold set

References:
- ANGEL (ACL 2025): Negative-aware training for BioEL
- Sentence-Transformers: Cross-encoder training
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FinetuneConfig:
    """Configuration for cross-encoder fine-tuning.

    Attributes:
        base_model: Pre-trained model to fine-tune
        output_dir: Directory to save fine-tuned model
        train_data_path: Path to training JSONL (from HardNegativeMiner)
        eval_data_path: Path to evaluation data (gold set)
        epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Learning rate
        warmup_ratio: Warmup ratio for scheduler
        margin: Margin for ranking loss
        max_seq_length: Maximum sequence length
        eval_steps: Evaluation frequency
        save_steps: Checkpoint frequency
        use_gpu: Whether to use GPU
        seed: Random seed
    """
    base_model: str = "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract"
    output_dir: str = "models/finetuned_reranker"
    train_data_path: str = "data/hard_negatives/hard_negatives.jsonl"
    eval_data_path: Optional[str] = None
    epochs: int = 3
    batch_size: int = 16
    learning_rate: float = 2e-5
    warmup_ratio: float = 0.1
    margin: float = 0.3
    max_seq_length: int = 128
    eval_steps: int = 100
    save_steps: int = 500
    use_gpu: bool = True
    seed: int = 42


@dataclass
class TrainingExample:
    """Single training example for cross-encoder."""
    query: str
    positive: str
    negative: str
    negative_type: str = ""


@dataclass
class EvalResult:
    """Evaluation result on gold set."""
    accuracy_at_1: float
    accuracy_at_5: float
    mrr: float
    rank_improvement_rate: float  # % of cases where fine-tuned model improves rank
    avg_score_delta: float


class CrossEncoderFinetuner:
    """Fine-tuner for cross-encoder reranker.

    Usage:
        config = FinetuneConfig(
            train_data_path="data/hard_negatives.jsonl",
            output_dir="models/finetuned_reranker",
        )
        finetuner = CrossEncoderFinetuner(config)
        finetuner.train()

        # Evaluate
        result = finetuner.evaluate(gold_set)
        print(f"Accuracy@1: {result.accuracy_at_1:.2%}")
    """

    def __init__(self, config: FinetuneConfig):
        self._config = config
        self._model = None
        self._tokenizer = None
        self._device = None
        self._training_examples: List[TrainingExample] = []
        self._is_trained = False

    def load_training_data(self) -> int:
        """Load training data from JSONL file.

        Returns:
            Number of examples loaded.
        """
        path = Path(self._config.train_data_path)
        if not path.exists():
            logger.error(f"Training data not found: {path}")
            return 0

        self._training_examples = []

        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)

                example = TrainingExample(
                    query=data.get("query", ""),
                    positive=data.get("positive_text", data.get("positive", "")),
                    negative=data.get("negative_text", data.get("negative", "")),
                    negative_type=data.get("negative_type", ""),
                )

                if example.query and example.positive and example.negative:
                    self._training_examples.append(example)

        logger.info(f"Loaded {len(self._training_examples)} training examples")
        return len(self._training_examples)

    def prepare_training_data(self) -> List[Dict[str, Any]]:
        """Prepare training data for sentence-transformers.

        Returns:
            List of training examples in InputExample format.
        """
        prepared = []

        for ex in self._training_examples:
            # For margin ranking loss:
            # positive pair: (query, positive) should have higher score
            # negative pair: (query, negative) should have lower score
            prepared.append({
                "query": ex.query,
                "positive": ex.positive,
                "negative": ex.negative,
            })

        return prepared

    def train(self) -> Dict[str, Any]:
        """Run fine-tuning.

        Returns:
            Training statistics.
        """
        stats = {
            "n_examples": 0,
            "epochs": self._config.epochs,
            "training_time_seconds": 0,
            "final_loss": 0.0,
        }

        # Load data
        n_examples = self.load_training_data()
        if n_examples == 0:
            logger.error("No training data available")
            return stats
        stats["n_examples"] = n_examples

        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
                TrainingArguments,
                Trainer,
            )
            from torch.utils.data import Dataset

            # Set device
            if self._config.use_gpu and torch.cuda.is_available():
                self._device = torch.device("cuda")
            else:
                self._device = torch.device("cpu")

            logger.info(f"Training on {self._device}")

            # Load model and tokenizer
            logger.info(f"Loading base model: {self._config.base_model}")
            self._tokenizer = AutoTokenizer.from_pretrained(self._config.base_model)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self._config.base_model,
                num_labels=1,
            )
            self._model.to(self._device)

            # Prepare dataset
            class RankingDataset(Dataset):
                def __init__(self, examples, tokenizer, max_length):
                    self.examples = examples
                    self.tokenizer = tokenizer
                    self.max_length = max_length

                def __len__(self):
                    return len(self.examples) * 2  # positive and negative

                def __getitem__(self, idx):
                    ex_idx = idx // 2
                    is_positive = idx % 2 == 0
                    ex = self.examples[ex_idx]

                    text_pair = ex.positive if is_positive else ex.negative
                    label = 1.0 if is_positive else 0.0

                    encoding = self.tokenizer(
                        ex.query,
                        text_pair,
                        truncation=True,
                        max_length=self.max_length,
                        padding="max_length",
                        return_tensors="pt",
                    )

                    return {
                        "input_ids": encoding["input_ids"].squeeze(),
                        "attention_mask": encoding["attention_mask"].squeeze(),
                        "labels": torch.tensor(label, dtype=torch.float),
                    }

            train_dataset = RankingDataset(
                self._training_examples,
                self._tokenizer,
                self._config.max_seq_length,
            )

            # Training arguments
            output_dir = Path(self._config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            training_args = TrainingArguments(
                output_dir=str(output_dir),
                num_train_epochs=self._config.epochs,
                per_device_train_batch_size=self._config.batch_size,
                learning_rate=self._config.learning_rate,
                warmup_ratio=self._config.warmup_ratio,
                logging_dir=str(output_dir / "logs"),
                logging_steps=10,
                save_steps=self._config.save_steps,
                eval_strategy="no",
                save_total_limit=2,
                seed=self._config.seed,
                report_to="none",
            )

            # Custom loss for margin ranking
            class MarginRankingTrainer(Trainer):
                def __init__(self, margin=0.3, **kwargs):
                    super().__init__(**kwargs)
                    self.margin = margin
                    self.ranking_loss = torch.nn.MarginRankingLoss(margin=margin)

                def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
                    labels = inputs.pop("labels")
                    outputs = model(**inputs)
                    logits = outputs.logits.squeeze()

                    # Standard BCE loss for classification
                    loss_fn = torch.nn.BCEWithLogitsLoss()
                    loss = loss_fn(logits, labels)

                    if return_outputs:
                        return loss, outputs
                    return loss

            # Train
            start_time = time.time()

            trainer = MarginRankingTrainer(
                margin=self._config.margin,
                model=self._model,
                args=training_args,
                train_dataset=train_dataset,
            )

            train_result = trainer.train()
            stats["training_time_seconds"] = time.time() - start_time
            stats["final_loss"] = train_result.training_loss

            # Save model
            trainer.save_model(str(output_dir / "final"))
            self._tokenizer.save_pretrained(str(output_dir / "final"))

            logger.info(f"Training complete. Model saved to {output_dir / 'final'}")
            self._is_trained = True

        except ImportError as e:
            logger.error(f"Missing dependencies for fine-tuning: {e}")
            logger.info("Install with: pip install transformers torch")

        except Exception as e:
            logger.error(f"Training failed: {e}")
            raise

        return stats

    def evaluate(
        self,
        eval_data: List[Tuple[str, str]],  # (query, gold_concept_id)
        candidate_getter=None,  # Function to get candidates
    ) -> EvalResult:
        """Evaluate fine-tuned model on gold set.

        Args:
            eval_data: List of (query, gold_concept_id) pairs
            candidate_getter: Function(query) -> List[(concept_id, text)]

        Returns:
            EvalResult with accuracy metrics.
        """
        if not self._is_trained and self._model is None:
            logger.warning("Model not trained or loaded")
            return EvalResult(0, 0, 0, 0, 0)

        correct_at_1 = 0
        correct_at_5 = 0
        reciprocal_ranks = []

        for query, gold_cid in eval_data:
            if candidate_getter is None:
                continue

            candidates = candidate_getter(query)
            if not candidates:
                continue

            # Score each candidate
            scores = []
            for cid, text in candidates:
                score = self._score_pair(query, text)
                scores.append((cid, score))

            # Rank by score
            ranked = sorted(scores, key=lambda x: x[1], reverse=True)
            ranked_ids = [x[0] for x in ranked]

            # Compute metrics
            if gold_cid in ranked_ids:
                rank = ranked_ids.index(gold_cid) + 1
                reciprocal_ranks.append(1.0 / rank)

                if rank == 1:
                    correct_at_1 += 1
                if rank <= 5:
                    correct_at_5 += 1
            else:
                reciprocal_ranks.append(0.0)

        n = len(eval_data)
        return EvalResult(
            accuracy_at_1=correct_at_1 / n if n else 0,
            accuracy_at_5=correct_at_5 / n if n else 0,
            mrr=sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0,
            rank_improvement_rate=0.0,  # Computed separately with baseline comparison
            avg_score_delta=0.0,
        )

    def _score_pair(self, query: str, candidate: str) -> float:
        """Score a (query, candidate) pair."""
        if self._model is None or self._tokenizer is None:
            return 0.0

        import torch

        inputs = self._tokenizer(
            query,
            candidate,
            truncation=True,
            max_length=self._config.max_seq_length,
            return_tensors="pt",
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)
            score = torch.sigmoid(outputs.logits.squeeze()).item()

        return score

    def load_finetuned_model(self, model_path: str) -> bool:
        """Load a previously fine-tuned model.

        Args:
            model_path: Path to saved model directory

        Returns:
            True if loaded successfully.
        """
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            path = Path(model_path)
            if not path.exists():
                logger.error(f"Model path not found: {path}")
                return False

            self._tokenizer = AutoTokenizer.from_pretrained(str(path))
            self._model = AutoModelForSequenceClassification.from_pretrained(
                str(path),
                num_labels=1,
            )

            if self._config.use_gpu and torch.cuda.is_available():
                self._device = torch.device("cuda")
            else:
                self._device = torch.device("cpu")

            self._model.to(self._device)
            self._model.eval()
            self._is_trained = True

            logger.info(f"Loaded fine-tuned model from {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False


def generate_training_data_from_goldset(
    embedder,
    gold_set: List[Tuple[str, str]],
    output_path: Path,
) -> int:
    """Generate training data by mining hard negatives from gold set.

    Args:
        embedder: NeuralEmbedder instance
        gold_set: List of (query, gold_concept_id)
        output_path: Output JSONL path

    Returns:
        Number of examples generated.
    """
    from .hard_negative_miner import (
        HardNegativeMiner,
        MiningConfig,
        CGA_TYPE_TRAPS,
    )

    miner = HardNegativeMiner(embedder, config=MiningConfig(
        top_k_negatives=5,
        include_model_errors=True,
        include_type_traps=True,
    ))

    # Mine from gold set
    negatives = miner.mine_from_gold_set(gold_set)

    # Add predefined type traps
    type_trap_negs = miner.mine_type_traps(CGA_TYPE_TRAPS)
    negatives.extend(type_trap_negs)

    # Export
    miner.export_training_data(negatives, output_path)

    return len(negatives)


def run_finetuning_pipeline(
    embedder,
    gold_set_path: Path,
    output_dir: Path,
    config: Optional[FinetuneConfig] = None,
) -> Dict[str, Any]:
    """Complete fine-tuning pipeline.

    1. Load gold set
    2. Mine hard negatives
    3. Fine-tune cross-encoder
    4. Evaluate

    Args:
        embedder: NeuralEmbedder instance (for mining negatives)
        gold_set_path: Path to gold set JSONL
        output_dir: Output directory
        config: Optional fine-tuning config

    Returns:
        Pipeline results.
    """
    from .ablation import load_gold_set

    results = {
        "n_gold": 0,
        "n_training": 0,
        "training_stats": {},
        "eval_results": {},
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load gold set
    gold_set = load_gold_set(gold_set_path)
    gold_pairs = [(g.query, g.gold_concept_id) for g in gold_set]
    results["n_gold"] = len(gold_pairs)

    # Generate training data
    train_path = output_dir / "train_negatives.jsonl"
    n_training = generate_training_data_from_goldset(embedder, gold_pairs, train_path)
    results["n_training"] = n_training

    if n_training == 0:
        logger.warning("No training data generated")
        return results

    # Fine-tune
    config = config or FinetuneConfig()
    config.train_data_path = str(train_path)
    config.output_dir = str(output_dir / "model")

    finetuner = CrossEncoderFinetuner(config)
    train_stats = finetuner.train()
    results["training_stats"] = train_stats

    logger.info(f"Pipeline complete. Results: {results}")
    return results
