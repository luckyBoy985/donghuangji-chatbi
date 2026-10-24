from __future__ import annotations

import math
import re
from collections import Counter

import jieba
import numpy as np

_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    tokens = [
        token.strip().lower()
        for token in jieba.lcut(text or "")
        if token.strip() and _TOKEN_RE.search(token)
    ]
    return tokens


class BM25Index:
    def __init__(self, documents: list[str]) -> None:
        self.counts = [Counter(tokenize(text)) for text in documents]
        self.lengths = np.asarray(
            [sum(count.values()) for count in self.counts], dtype=np.float32
        )
        self.average_length = float(self.lengths.mean()) if len(self.lengths) else 0.0
        document_frequency: Counter[str] = Counter()
        for count in self.counts:
            document_frequency.update(count.keys())
        self.document_frequency = document_frequency

    def scores(self, query: str) -> np.ndarray:
        terms = tokenize(query)
        result = np.zeros(len(self.counts), dtype=np.float32)
        count_total = max(len(self.counts), 1)
        k1, b = 1.5, 0.75
        for term in terms:
            df = self.document_frequency.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (count_total - df + 0.5) / (df + 0.5))
            for index, count in enumerate(self.counts):
                frequency = count.get(term, 0)
                if frequency == 0:
                    continue
                denominator = frequency + k1 * (
                    1 - b + b * float(self.lengths[index]) / max(self.average_length, 1e-6)
                )
                result[index] += idf * frequency * (k1 + 1) / denominator
        return result
