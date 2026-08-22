"""Embedding abstraction for V1.1.

The default hashing embedder is deterministic and dependency-free. It is not a
replacement for production embeddings; it preserves the retrieval contract so
Qdrant/pgvector can be introduced without changing the RCA layer.
"""
from __future__ import annotations
import hashlib
import math
import re
from typing import List


class EmbeddingProvider:
    dimensions: int = 128
    def embed(self, text: str) -> List[float]:
        raise NotImplementedError


class HashingEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = 128):
        self.dimensions = max(32, int(dimensions))

    @staticmethod
    def _tokens(text: str):
        latin = re.findall(r"[a-zA-Z0-9_]+", (text or "").lower())
        chinese = [c for c in (text or "") if "\u4e00" <= c <= "\u9fff"]
        return latin + chinese

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
