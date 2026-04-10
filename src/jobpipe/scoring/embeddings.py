from __future__ import annotations

import importlib

import numpy as np


class LocalEmbedder:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model

        try:
            module = importlib.import_module("sentence_transformers")
            sentence_transformer = getattr(module, "SentenceTransformer")
        except (ImportError, ModuleNotFoundError, AttributeError) as exc:
            raise RuntimeError(
                "sentence-transformers is required for local embeddings. "
                "Install dependencies before running scoring."
            ) from exc

        self._model = sentence_transformer(self._model_name)
        return self._model

    def embed_text(self, text: str) -> np.ndarray:
        model = self._ensure_model()
        vector = model.encode([text], normalize_embeddings=True)[0]
        return np.asarray(vector, dtype=float)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / denominator)


def relevance_score(job_text: str, cv_text: str, embedder: LocalEmbedder) -> float:
    job_vec = embedder.embed_text(job_text)
    cv_vec = embedder.embed_text(cv_text)
    similarity = cosine_similarity(job_vec, cv_vec)

    # Numerical clipping for stability.
    similarity = max(-1.0, min(1.0, similarity))
    return (similarity + 1.0) / 2.0
