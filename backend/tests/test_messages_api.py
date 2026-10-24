from collections.abc import AsyncIterator

from backend.app.services.data.models import Evidence
from backend.app.services.qa.service import QAService, get_qa_service


class FakeRetrieval:
    def __init__(self, hits):
        self.hits = hits

    def search(self, _query, *, products=None, sections=None, limit=8):
        return self.hits[:limit]


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def stream(self, _question, _hits, history) -> AsyncIterator[str]:
        self.calls += 1
        yield "根据资料，火克草，草克水，水克火[S1]。"


def _install_service(app, hits, llm=None):
    retrieval = FakeRetrieval(hits)
    fake_llm = llm or FakeLLM()
    app.dependency_overrides[get_qa_service] = lambda: QAService(
        retrieval=retrieval,
        llm=fake_llm,
    )
    return fake_llm


def test_stream_persists_answer_and_candidates(auth_client, app):
    conversation = auth_client.post("/api/conversations", json={}).json()
    llm = _install_service(
        app,
        [
            Evidence(
                "chunk-1",
                "火克草，草克水，水克火",
                "东煌纪",
                "产品资料",
                0.91,
                doc_id="doc-1",
                title="灵兽系统说明",
                source_type="internal",
            )
        ],
    )

    response = auth_client.post(
        f"/api/conversations/{conversation['id']}/messages/stream",
        json={
            "content": "东煌纪的灵兽属性克制关系是什么？",
            "products": ["东煌纪"],
            "sections": [],
        },
    )

    assert response.status_code == 200
    assert "event: stage" in response.text
    assert "event: token" in response.text
    assert "event: citations" in response.text
    assert "event: done" in response.text
    assert "[S1]" in response.text
    assert llm.calls == 1

    detail = auth_client.get(f"/api/conversations/{conversation['id']}").json()
    assert [item["role"] for item in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["citations"][0]["citation_key"] == "S1"
    assert detail["messages"][1]["citations"][0]["used_in_answer"] is True


def test_low_confidence_question_refuses_without_calling_llm(auth_client, app):
    conversation = auth_client.post("/api/conversations", json={}).json()
    llm = _install_service(
        app,
        [
            Evidence(
                "chunk-2",
                "完全无关",
                "东煌纪",
                "官方资讯",
                0.05,
                doc_id="doc-2",
                title="普通公告",
            )
        ],
    )

    response = auth_client.post(
        f"/api/conversations/{conversation['id']}/messages/stream",
        json={
            "content": "某个知识库完全没有的内容？",
            "products": ["东煌纪"],
            "sections": [],
        },
    )

    assert "资料不足" in response.text or "没有命中" in response.text
    assert llm.calls == 0
    detail = auth_client.get(f"/api/conversations/{conversation['id']}").json()
    assert detail["messages"][-1]["status"] == "refused"


def test_stream_rejects_user_after_daily_quota(auth_client, app, monkeypatch):
    from backend.app.core.config import settings

    conversation = auth_client.post("/api/conversations", json={}).json()
    _install_service(app, [])
    monkeypatch.setattr(settings, "qa_daily_limit_per_user", 0)

    response = auth_client.post(
        f"/api/conversations/{conversation['id']}/messages/stream",
        json={
            "content": "东煌纪的灵兽属性克制关系是什么？",
            "products": ["东煌纪"],
            "sections": [],
        },
    )

    assert response.status_code == 429
