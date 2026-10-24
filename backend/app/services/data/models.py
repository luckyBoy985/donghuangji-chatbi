from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Evidence:
    chunk_id: str
    text: str
    product: str
    section: str
    score: float = 0.0
    doc_id: str = ""
    source_type: str = ""
    title: str = ""
    url: str = ""
    published_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GateVerdict:
    sufficient: bool
    reason: str
    best_score: float
    overlap: float
