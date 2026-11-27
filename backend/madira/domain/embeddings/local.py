"""Deterministic hashed embeddings. No network, same text, same vector."""

from __future__ import annotations

import hashlib
import math
import re

LOCAL_MODEL = "madira-local-embed-v1"
LOCAL_DIM = 64

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN.findall((text or "").casefold()) if len(token) >= 2]


def embed(text: str) -> list[float]:
    vector = [0.0] * LOCAL_DIM
    tokens = tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % LOCAL_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    return normalize(vector)


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return [0.0] * len(vector)
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(a * b for a, b in zip(left, right)))
