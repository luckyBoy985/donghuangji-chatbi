import json
from collections.abc import AsyncIterator

from backend.app.models.entities import Conversation, Message
from backend.app.models.identity import User
from backend.app.services.data.models import Evidence
from backend.app.services.reports.service import ReportService, get_report_service


class FakeReportRetrieval:
    def search(self, _query, *, products=None, sections=None, limit=8):
        return [
            Evidence(
                "chunk-r1",
                "东煌纪采用进化路线与升星，竞品强调等级进化。",
                "东煌纪",
                "产品资料",
                0.91,
                doc_id="doc-r1",
                title="竞品功能对照表",
                source_type="internal",
            )
        ]


class FakeReportLLM:
    async def complete(self, _question, _hits, _history):
        return (
            "## 摘要\n东煌纪采用升星与进化并行的养成路线[S1]。\n\n"
            "## 产品概况\n当前资料覆盖有限[S1]。\n\n"
            "## 系统与玩法对比\n竞品更强调等级进化[S1]。\n\n"
            "## 版本运营节奏\n当前资料未覆盖稳定节奏[S1]。\n\n"
            "## 机会与风险\n资料显示仍需补充商业化信息[S1]。\n\n"
            "<script>alert(1)</script>"
        )


def _seed_conversation(session_factory) -> str:
    session = session_factory()
    owner = session.query(User).first()
    assert owner is not None
    conversation = Conversation(title="东煌纪竞品分析", owner_user_id=owner.id)
    session.add(conversation)
    session.flush()
    session.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content="比较东煌纪和竞品的养成体系",
            filters_json=json.dumps({"products": ["东煌纪"], "sections": []}),
        )
    )
    session.commit()
    return conversation.id


def test_report_persists_six_sections_and_safe_html(
    auth_client, app, session_factory
):
    conversation_id = _seed_conversation(session_factory)
    app.dependency_overrides[get_report_service] = lambda: ReportService(
        retrieval=FakeReportRetrieval(),
        llm=FakeReportLLM(),
    )

    response = auth_client.post(
        f"/api/conversations/{conversation_id}/reports",
        json={},
    )

    assert response.status_code == 201
    report = response.json()
    for heading in (
        "## 摘要",
        "## 产品概况",
        "## 系统与玩法对比",
        "## 版本运营节奏",
        "## 机会与风险",
        "## 证据清单",
    ):
        assert heading in report["markdown"]
    assert "<script>" not in report["html"]
    assert "&lt;script&gt;" in report["html"]

    download = auth_client.get(f"/api/reports/{report['id']}/download.md")
    assert download.status_code == 200
    assert "## 证据清单" in download.text


def test_report_list_and_detail(auth_client, app, session_factory):
    conversation_id = _seed_conversation(session_factory)
    app.dependency_overrides[get_report_service] = lambda: ReportService(
        retrieval=FakeReportRetrieval(),
        llm=FakeReportLLM(),
    )
    created = auth_client.post(
        f"/api/conversations/{conversation_id}/reports",
        json={},
    ).json()

    assert auth_client.get("/api/reports").json()[0]["id"] == created["id"]
    assert auth_client.get(f"/api/reports/{created['id']}").json()["title"]
