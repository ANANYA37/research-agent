"""Lightweight embedding utilities for semantic research-history cache lookup."""

import hashlib
import math
import re


EMBEDDING_DIMENSIONS = 384
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "and", "are", "for", "in", "into", "of", "on", "or", "the", "to", "with",
}
SYNONYMS = {
    "medicine": ["healthcare", "medical", "health"],
    "medical": ["healthcare", "medicine", "health"],
    "healthcare": ["medicine", "medical", "health"],
    "health": ["healthcare", "medicine", "medical"],
    "impact": ["effect", "effects", "influence"],
    "effects": ["impact", "effect", "influence"],
    "effect": ["impact", "effects", "influence"],
    "ai": ["artificial", "intelligence"],
    "artificial": ["ai", "intelligence"],
    "intelligence": ["ai", "artificial"],
}


def embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Return a deterministic hashed bag-of-words embedding.

    This keeps semantic cache lookup local and dependency-free. It is intentionally
    swappable: replace this function with provider embeddings if desired.
    """
    vector = [0.0] * dimensions
    base_tokens = [token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS]
    tokens = []
    for token in base_tokens:
        tokens.append(token)
        tokens.extend(SYNONYMS.get(token, []))
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        vector[bucket] += 1.0

    length = math.sqrt(sum(value * value for value in vector))
    if length == 0:
        return vector
    return [value / length for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
