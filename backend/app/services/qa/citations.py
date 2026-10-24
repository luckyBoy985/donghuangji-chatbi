from __future__ import annotations

import re

_CITATION = re.compile(r"\[(S\d+)\]")


def validate_citations(
    answer: str, valid_keys: set[str]
) -> tuple[str, set[str]]:
    used = {
        match.group(1)
        for match in _CITATION.finditer(answer)
        if match.group(1) in valid_keys
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return match.group(0) if key in valid_keys else key

    return _CITATION.sub(replace, answer), used
