from hashlib import sha256
from math import sqrt
from typing import Protocol


class EmbeddingProvider(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicEmbedding:
    """Stable local vectors for development and CI; replace in production."""

    dimension = 32

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = sha256(text.encode("utf-8")).digest()
            vector = [((byte / 255.0) * 2.0) - 1.0 for byte in digest[: self.dimension]]
            norm = sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors
