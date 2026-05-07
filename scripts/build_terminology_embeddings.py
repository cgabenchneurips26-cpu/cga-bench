#!/usr/bin/env python3
"""
Pre-compute SapBERT embeddings for expanded terminology codes.

Generates .npy embedding files and metadata JSON for the neural
terminology grounding backend.

Usage:
    python scripts/build_terminology_embeddings.py
    python scripts/build_terminology_embeddings.py --model cambridgeltl/SapBERT-from-PubMedBERT-fulltext
    python scripts/build_terminology_embeddings.py --output-dir ./semantic_layer/terminology/embeddings
    python scripts/build_terminology_embeddings.py --no-gpu
    python scripts/build_terminology_embeddings.py --verify-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).parent
_TERMINOLOGY_DIR = _SCRIPT_DIR.parent / "semantic_layer" / "terminology"
_DEFAULT_CODES_PATH = _TERMINOLOGY_DIR / "expanded_codes.yaml"
_DEFAULT_OUTPUT_DIR = _TERMINOLOGY_DIR / "embeddings"


def load_expanded_codes(yaml_path: Path) -> List[Dict[str, Any]]:
    """Load expanded_codes.yaml and flatten to embedding-ready records.

    Each synonym + display name becomes a separate embedding row,
    all pointing to the same code/internal_code.

    Returns:
        List of dicts: {code, internal_code, display, system, domain, source_text}
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    records = []
    seen_keys = set()

    for system in ("loinc", "snomed", "rxnorm"):
        entries = data.get(system, [])
        for entry in entries:
            code = str(entry["code"])
            internal_code = entry["internal_code"]
            display = entry["display"]
            domain = entry.get("domain", "general")
            synonyms = entry.get("synonyms", [])

            # Add display name as primary embedding
            key = f"{system}:{code}:{display.lower()}"
            if key not in seen_keys:
                seen_keys.add(key)
                records.append({
                    "code": code,
                    "internal_code": internal_code,
                    "display": display,
                    "system": system,
                    "domain": domain,
                    "source_text": display,
                })

            # Add each synonym as separate embedding row
            for syn in synonyms:
                syn_key = f"{system}:{code}:{syn.lower()}"
                if syn_key not in seen_keys:
                    seen_keys.add(syn_key)
                    records.append({
                        "code": code,
                        "internal_code": internal_code,
                        "display": display,
                        "system": system,
                        "domain": domain,
                        "source_text": syn,
                    })

    logger.info(f"Loaded {len(records)} embedding records from {yaml_path}")
    return records


def encode_terms_transformers(
    terms: List[str],
    model_name: str,
    batch_size: int = 32,
    use_gpu: bool = True,
    use_fp16: bool = True,
) -> np.ndarray:
    """Encode terms using HuggingFace transformers (SapBERT path).

    Returns (N, D) L2-normalized float32 array.
    """
    import torch
    from transformers import AutoModel, AutoTokenizer

    logger.info(f"Loading model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)

    device = "cpu"
    if use_gpu and torch.cuda.is_available():
        device = "cuda"
        if use_fp16:
            model = model.half()
        logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")

    model = model.to(device)
    model.eval()

    all_embeddings = []
    for i in range(0, len(terms), batch_size):
        batch = terms[i:i + batch_size]
        inputs = tokenizer(
            batch,
            return_tensors="pt",
            max_length=128,
            truncation=True,
            padding=True,
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            # [CLS] token embedding
            embeddings = outputs.last_hidden_state[:, 0, :].cpu().float().numpy()

        all_embeddings.append(embeddings)

        if (i // batch_size) % 10 == 0:
            logger.info(f"  Encoded {min(i + batch_size, len(terms))}/{len(terms)} terms")

    result = np.vstack(all_embeddings).astype(np.float32)

    # L2 normalize
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    result = result / norms

    return result


def encode_terms_sentence_transformers(
    terms: List[str],
    model_name: str,
    batch_size: int = 32,
    use_gpu: bool = True,
) -> np.ndarray:
    """Encode terms using sentence-transformers (BGE-M3 path).

    Returns (N, D) L2-normalized float32 array.
    """
    from sentence_transformers import SentenceTransformer

    device = "cpu"
    if use_gpu:
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
        except ImportError:
            pass

    logger.info(f"Loading model: {model_name} (device={device})")
    model = SentenceTransformer(model_name, device=device)

    embeddings = model.encode(
        terms,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    return embeddings.astype(np.float32)


def encode_terms(
    terms: List[str],
    model_name: str,
    batch_size: int = 32,
    use_gpu: bool = True,
    use_fp16: bool = True,
) -> np.ndarray:
    """Encode terms, trying transformers first then sentence-transformers."""
    try:
        return encode_terms_transformers(terms, model_name, batch_size, use_gpu, use_fp16)
    except Exception as e:
        logger.warning(f"transformers encoding failed ({e}), trying sentence-transformers")
        try:
            return encode_terms_sentence_transformers(terms, model_name, batch_size, use_gpu)
        except Exception as e2:
            logger.error(f"Both encoding methods failed: {e2}")
            raise


def build_and_save(
    expanded_codes_path: Path,
    output_dir: Path,
    model_name: str = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
    batch_size: int = 32,
    use_gpu: bool = True,
    use_fp16: bool = True,
) -> None:
    """Main build pipeline: load codes -> encode -> save .npy + metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load and flatten codes
    records = load_expanded_codes(expanded_codes_path)
    terms = [r["source_text"] for r in records]

    logger.info(f"Encoding {len(terms)} terms with {model_name}...")
    start_time = time.time()

    embeddings = encode_terms(terms, model_name, batch_size, use_gpu, use_fp16)

    elapsed = time.time() - start_time
    logger.info(f"Encoding completed in {elapsed:.1f}s")
    logger.info(f"Embedding shape: {embeddings.shape}")

    # Save embeddings
    emb_path = output_dir / "terminology_embeddings.npy"
    np.save(str(emb_path), embeddings)
    logger.info(f"Saved embeddings to {emb_path} ({emb_path.stat().st_size / 1024:.1f} KB)")

    # Save metadata
    meta_path = output_dir / "terminology_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=None)
    logger.info(f"Saved metadata to {meta_path}")

    # Save build info
    with open(expanded_codes_path, "rb") as f:
        yaml_hash = hashlib.sha256(f.read()).hexdigest()[:16]

    build_info = {
        "model_name": model_name,
        "embedding_dim": int(embeddings.shape[1]),
        "num_entries": len(records),
        "num_unique_codes": len({f"{r['system']}:{r['code']}" for r in records}),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_yaml_hash": yaml_hash,
        "elapsed_seconds": round(elapsed, 1),
    }
    info_path = output_dir / "build_info.json"
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(build_info, f, indent=2)
    logger.info(f"Saved build info to {info_path}")

    # Verify
    loaded = np.load(str(emb_path))
    assert loaded.shape == embeddings.shape, "Verification failed: shape mismatch"
    logger.info("Verification passed: embeddings round-trip OK")


def verify_existing(output_dir: Path) -> bool:
    """Verify existing embeddings are valid."""
    emb_path = output_dir / "terminology_embeddings.npy"
    meta_path = output_dir / "terminology_metadata.json"
    info_path = output_dir / "build_info.json"

    for p in (emb_path, meta_path, info_path):
        if not p.exists():
            logger.error(f"Missing: {p}")
            return False

    embeddings = np.load(str(emb_path))
    with open(meta_path, "r") as f:
        metadata = json.load(f)
    with open(info_path, "r") as f:
        info = json.load(f)

    if len(embeddings) != len(metadata):
        logger.error(f"Size mismatch: {len(embeddings)} embeddings vs {len(metadata)} metadata")
        return False

    if embeddings.shape[1] != info["embedding_dim"]:
        logger.error(f"Dim mismatch: {embeddings.shape[1]} vs {info['embedding_dim']}")
        return False

    # Check normalization
    norms = np.linalg.norm(embeddings, axis=1)
    if not np.allclose(norms, 1.0, atol=0.01):
        logger.warning("Some embeddings are not L2-normalized")

    logger.info(f"Verification passed:")
    logger.info(f"  Model: {info['model_name']}")
    logger.info(f"  Entries: {info['num_entries']}")
    logger.info(f"  Unique codes: {info['num_unique_codes']}")
    logger.info(f"  Embedding dim: {info['embedding_dim']}")
    logger.info(f"  Built: {info['timestamp']}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Build terminology embeddings for neural grounding"
    )
    parser.add_argument(
        "--model",
        default="cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
        help="Embedding model name (default: SapBERT)",
    )
    parser.add_argument(
        "--codes-path",
        type=Path,
        default=_DEFAULT_CODES_PATH,
        help="Path to expanded_codes.yaml",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help="Output directory for .npy and metadata files",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for encoding",
    )
    parser.add_argument(
        "--no-gpu",
        action="store_true",
        help="Disable GPU (CPU only)",
    )
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Disable half-precision",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing embeddings, don't rebuild",
    )
    args = parser.parse_args()

    if args.verify_only:
        success = verify_existing(args.output_dir)
        sys.exit(0 if success else 1)

    if not args.codes_path.exists():
        logger.error(f"Codes file not found: {args.codes_path}")
        sys.exit(1)

    build_and_save(
        expanded_codes_path=args.codes_path,
        output_dir=args.output_dir,
        model_name=args.model,
        batch_size=args.batch_size,
        use_gpu=not args.no_gpu,
        use_fp16=not args.no_fp16,
    )


if __name__ == "__main__":
    main()
