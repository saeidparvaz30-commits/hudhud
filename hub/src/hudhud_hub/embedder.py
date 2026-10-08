# SPDX-License-Identifier: AGPL-3.0-or-later
"""Text embedders. Every vector is L2-normalised, so a dot product is the cosine."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    model: str

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return (vectors / np.where(norms == 0, 1, norms)).astype(np.float32)


class FastEmbedder:
    """A local ONNX model via fastembed. Downloads the model once into `cache_dir`."""

    def __init__(self, model: str, cache_dir: Path | None = None):
        # Windows without Developer Mode has no symlinks; the cache copes, quietly.
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        from fastembed import TextEmbedding

        self.model = model
        self._model = TextEmbedding(model_name=model,
                                    cache_dir=str(cache_dir) if cache_dir else None)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        # passage_embed/query_embed add the prefixes models such as e5 expect.
        return _normalise(np.array(list(self._model.passage_embed(texts)), dtype=np.float32))

    def embed_query(self, text: str) -> np.ndarray:
        return _normalise(np.array(next(iter(self._model.query_embed([text]))), dtype=np.float32))


class HashEmbedder:
    """Bag-of-words hashing. Deterministic and instant, for tests only."""

    DIM = 256

    def __init__(self, model: str = "hash", cache_dir: Path | None = None):
        self.model = model

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.DIM, dtype=np.float32)
        for word in re.findall(r"\w+", text.lower()):
            if len(word) > 2:
                index = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM
                vector[index] += 1
        return vector

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.DIM), dtype=np.float32)
        return _normalise(np.stack([self._vector(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return _normalise(self._vector(text))
