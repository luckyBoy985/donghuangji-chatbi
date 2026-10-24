from backend.app.services.data.gate import assess_sufficiency
from backend.app.services.data.models import Evidence


def test_gate_rejects_weak_hit_without_keyword_coverage():
    hits = [Evidence("x", "无关内容", "东煌纪", "资讯", score=0.12)]

    verdict = assess_sufficiency(
        "灵兽属性克制",
        hits,
        strong=0.60,
        minimum=0.30,
        overlap=0.20,
    )

    assert verdict.sufficient is False
    assert verdict.best_score == 0.12


def test_gate_accepts_strong_rerank_score():
    hits = [
        Evidence(
            "x",
            "灵兽分为十八种属性，存在克制关系。",
            "东煌纪",
            "产品资料",
            score=0.72,
        )
    ]

    verdict = assess_sufficiency(
        "灵兽属性克制",
        hits,
        strong=0.60,
        minimum=0.30,
        overlap=0.20,
    )

    assert verdict.sufficient is True


def test_gate_rejects_no_hits():
    verdict = assess_sufficiency(
        "未知内容",
        [],
        strong=0.60,
        minimum=0.30,
        overlap=0.20,
    )

    assert verdict.sufficient is False
    assert "没有命中" in verdict.reason
