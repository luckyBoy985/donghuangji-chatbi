from backend.app.services.qa.citations import validate_citations


def test_validate_removes_unknown_citation_and_keeps_known():
    answer = "火克草[S1]，水系资料见[S9]。"

    cleaned, used = validate_citations(answer, {"S1", "S2"})

    assert cleaned == "火克草[S1]，水系资料见S9。"
    assert used == {"S1"}


def test_validate_accepts_multiple_known_citations():
    cleaned, used = validate_citations("结论[S1]，补充[S2]。", {"S1", "S2"})

    assert cleaned == "结论[S1]，补充[S2]。"
    assert used == {"S1", "S2"}
