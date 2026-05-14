from __future__ import annotations

import importlib
import threading
from typing import Sequence

import numpy as np


_MODEL_CACHE: dict[str, object] = {}
_MODEL_LOCK = threading.Lock()


class LocalEmbedder:
    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self._model_name = model_name
        self._batch_size = max(1, batch_size)
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

                cached = sentence_transformer(self._model_name)
                _MODEL_CACHE[self._model_name] = cached

        self._model = cached
        return self._model

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=float)

        model = self._ensure_model()
        vectors = model.encode(
            list(texts),
            normalize_embeddings=True,
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=float)

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
