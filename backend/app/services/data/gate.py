from __future__ import annotations

import re

import jieba

from backend.app.services.data.models import Evidence, GateVerdict

_STOPWORDS = {
    "什么",
    "怎么",
    "怎样",
    "如何",
    "是否",
    "哪些",
    "多少",
    "请问",
    "介绍",
    "说明",
    "以及",
    "和",
    "的",
}


def question_keywords(question: str, limit: int = 8) -> list[str]:
    words: list[str] = []
    for token in jieba.cut(question):
        token = token.strip()
        if len(token) < 2 or token in _STOPWORDS:
            continue
        if re.fullmatch(r"[\W_]+", token):
            continue
        if token not in words:
            words.append(token)
    words.sort(key=len, reverse=True)
    return words[:limit]


def keyword_overlap(question: str, hits: list[Evidence], top_n: int = 3) -> float:
    keywords = question_keywords(question)
    if not keywords or not hits:
        return 0.0
    text = " ".join(
        f"{hit.title} {hit.section} {hit.text}" for hit in hits[:top_n]
    )
    matched = sum(1 for keyword in keywords if keyword in text)
    return round(matched / len(keywords), 4)


def assess_sufficiency(
    question: str,
    hits: list[Evidence],
    *,
    strong: float,
    minimum: float,
    overlap: float,
) -> GateVerdict:
    if not hits:
        return GateVerdict(False, "检索没有命中任何资料", 0.0, 0.0)
    best = max(float(hit.score) for hit in hits)
    covered = keyword_overlap(question, hits)
    sufficient = best >= strong or (best >= minimum and covered >= overlap)
    reason = (
        f"最高相关度 {best:.2f}，关键词覆盖率 {covered:.0%}，证据充分"
        if sufficient
        else f"最高相关度 {best:.2f}，关键词覆盖率 {covered:.0%}，证据不足"
    )
    return GateVerdict(sufficient, reason, round(best, 4), covered)
