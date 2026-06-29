from __future__ import annotations

import hashlib
import importlib
import logging
import os
import threading
from typing import Sequence

try:
    import torch
except ImportError:
    torch = None

import numpy as np

# Force offline mode to prevent any HuggingFace Hub API calls
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

LOGGER = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, object] = {}
_MODEL_LOCK = threading.Lock()
_EMBEDDING_CACHE: dict[str, np.ndarray] = {}
_EMBEDDING_CACHE_LOCK = threading.Lock()


def _hash_text(text: str) -> str:
    """Create a hash for text caching."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def clear_embedding_cache() -> None:
    """Clear the embedding cache (useful for testing or memory management)."""
    with _EMBEDDING_CACHE_LOCK:
        _EMBEDDING_CACHE.clear()
        LOGGER.info("Embedding cache cleared")


class LocalEmbedder:
    def __init__(self, model_name: str, batch_size: int = 32, quantize: bool = False) -> None:
        self._model_name = model_name
        self._batch_size = max(1, batch_size)
        self._quantize = quantize
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model

        with _MODEL_LOCK:
            cached = _MODEL_CACHE.get(self._model_name)
            if cached is None:
                try:
                    module = importlib.import_module("sentence_transformers")
                    sentence_transformer = getattr(module, "SentenceTransformer")
                except (ImportError, ModuleNotFoundError, AttributeError) as exc:
                    raise RuntimeError(
                        "sentence-transformers is required for local embeddings. "
                        "Install dependencies before running scoring."
                    ) from exc

                # Load from local cache to avoid HuggingFace API checks
                # In offline mode (HF_HUB_OFFLINE=1), only load from cache
                offline_mode = os.environ.get("HF_HUB_OFFLINE", "0") == "1"

                try:
                    # Try to load from cache first
                    cached = sentence_transformer(
                        self._model_name,
                        local_files_only=True,
                    )
                    LOGGER.info("Embedding model loaded from local cache")
                except Exception as exc:
                    if offline_mode:
                        # In offline mode, don't fall back to online loading
                        raise RuntimeError(
                            f"Cannot load model '{self._model_name}' in offline mode. "
                            f"Run 'python scripts/download_embedding_model.py' while online "
                            f"to cache the model locally."
                        ) from exc
                    else:
                        LOGGER.warning("Failed to load from cache, trying without cache: %s", exc)
                        cached = sentence_transformer(self._model_name)
                        LOGGER.info("Embedding model loaded without cache")

                # Apply quantization if requested
                if self._quantize:
                    if torch is not None:
                        try:
                            # Use dynamic quantization for faster CPU inference
                            cached = torch.quantization.quantize_dynamic(
                                cached, {torch.nn.Linear}, dtype=torch.qint8
                            )
                            LOGGER.info("Model quantized for faster inference")
                        except Exception as qe:
                            LOGGER.warning("Failed to quantize model: %s", qe)
                    else:
                        LOGGER.warning("torch not available, skipping quantization")

                _MODEL_CACHE[self._model_name] = cached

        self._model = cached
        return self._model

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=float)
        
        import time
        start_time = time.time()

        # Check cache first
        cached_results = []
        texts_to_embed = []
        text_indices = []
        
        with _EMBEDDING_CACHE_LOCK:
            for idx, text in enumerate(texts):
                text_hash = _hash_text(text)
                if text_hash in _EMBEDDING_CACHE:
                    cached_results.append((idx, _EMBEDDING_CACHE[text_hash]))
                else:
                    texts_to_embed.append(text)
                    text_indices.append(idx)
        
        cache_hit_rate = len(cached_results) / len(texts) * 100 if texts else 0
        
        # Embed only uncached texts
        if texts_to_embed:
            model = self._ensure_model()
            encode_start = time.time()
            new_vectors = model.encode(
                texts_to_embed,
                normalize_embeddings=True,
                batch_size=self._batch_size,
                show_progress_bar=False,
            )
            encode_time = time.time() - encode_start
            new_vectors = np.asarray(new_vectors, dtype=float)
            
            # Cache new embeddings
            with _EMBEDDING_CACHE_LOCK:
                for i, idx in enumerate(text_indices):
                    text_hash = _hash_text(texts[idx])
                    _EMBEDDING_CACHE[text_hash] = new_vectors[i]
            
            LOGGER.info(
                "Embedded %d new texts (%.2fs), cache hit rate: %.1f%%",
                len(texts_to_embed), encode_time, cache_hit_rate
            )
        else:
            new_vectors = np.zeros((0, len(cached_results[0][1]) if cached_results else 0), dtype=float)
            LOGGER.info("All %d texts served from cache (%.1f%% hit rate)", len(texts), cache_hit_rate)
        
        # Combine cached and new results in correct order
        all_vectors = np.zeros((len(texts), new_vectors.shape[1] if new_vectors.shape[0] > 0 else 
                                  (cached_results[0][1].shape[0] if cached_results else 0)), dtype=float)
        
        # Fill in cached results
        for idx, vector in cached_results:
            all_vectors[idx] = vector
        
        # Fill in new results
        new_idx = 0
        for i in range(len(texts)):
            if i not in [idx for idx, _ in cached_results]:
                all_vectors[i] = new_vectors[new_idx]
                new_idx += 1
        
        total_time = time.time() - start_time
        LOGGER.debug(
            "Total embed_texts time: %.2fs for %d texts (%.1f%% cache hit)",
            total_time, len(texts), cache_hit_rate
        )
        
        return all_vectors

    def embed_text(self, text: str) -> np.ndarray:
        vectors = self.embed_texts([text])
        return vectors[0]


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / denominator)


def relevance_scores(
    job_texts: Sequence[str],
    cv_vector: np.ndarray,
    embedder: LocalEmbedder,
) -> list[float]:
    if not job_texts:
        return []

    job_vectors = embedder.embed_texts(job_texts)
    cv_vec = np.asarray(cv_vector, dtype=float).reshape(-1)
    similarities = np.dot(job_vectors, cv_vec)
    similarities = np.clip(similarities, -1.0, 1.0)
    return ((similarities + 1.0) / 2.0).tolist()


def relevance_score(job_text: str, cv_text: str, embedder: LocalEmbedder) -> float:
    cv_vec = embedder.embed_text(cv_text)
    scores = relevance_scores([job_text], cv_vec, embedder)
    return scores[0] if scores else 0.0
