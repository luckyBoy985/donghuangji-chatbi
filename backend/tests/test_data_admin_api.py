from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.security import hash_password
from backend.app.models.identity import User

PASSWORD = "CorrectHorseBatteryStaple"


def _seed_user(session_factory, username: str = "member") -> str:
    db = session_factory()
    user = User(
        username=username,
        display_name="普通成员",
        password_hash=hash_password(PASSWORD),
        platform_role="user",
    )
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()
    return user_id


def _member_client(app) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"username": "member", "password": PASSWORD},
    )
    assert response.status_code == 200
    return client


def test_non_admin_cannot_upload_documents(app, session_factory):
    _seed_user(session_factory)
    member = _member_client(app)

    response = member.post(
        "/api/admin/data/uploads",
        data={"product": "东煌纪", "section": "产品资料"},
        files={"file": ("市场记录.md", "# 市场记录\n\n测试资料", "text/markdown")},
    )

    assert response.status_code == 403


def test_admin_upload_creates_queued_job(
    auth_client, session_factory, monkeypatch
):
    from backend.app.api import data_admin

    queued: list[str] = []
    monkeypatch.setattr(data_admin, "_store_upload", lambda *args: "uploads/test.md")
    monkeypatch.setattr(data_admin, "_enqueue_job", queued.append)

    response = auth_client.post(
        "/api/admin/data/uploads",
        data={"product": "东煌纪", "section": "产品资料", "title": "市场记录"},
        files={"file": ("市场记录.md", "# 市场记录\n\n测试资料", "text/markdown")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["kind"] == "upload"
    assert payload["status"] == "queued"
    assert payload["product"] == "东煌纪"
    assert payload["original_name"] == "市场记录.md"
    assert queued == [payload["id"]]

    from backend.app.models.ingestion import IngestJob

    db = session_factory()
    job = db.scalar(select(IngestJob).where(IngestJob.id == payload["id"]))
    assert job is not None
    assert job.object_key == "uploads/test.md"
    assert job.created_by is not None
    db.close()


def test_upload_rejects_unsupported_file_before_creating_job(auth_client):
    response = auth_client.post(
        "/api/admin/data/uploads",
        data={"product": "东煌纪", "section": "产品资料"},
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
    )

    assert response.status_code == 422


def test_data_admin_overview_requires_platform_admin(app, session_factory):
    _seed_user(session_factory)
    member = _member_client(app)

    response = member.get("/api/admin/data/overview")

    assert response.status_code == 403


def test_documents_list_filters_active_document_and_counts_chunks(
    auth_client, session_factory
):
    from backend.app.models.ingestion import DataChunk, DataDocument

    db = session_factory()
    db.add_all(
        [
            DataDocument(
                doc_id="doc-active",
                product="东煌纪",
                source_type="internal",
                section="产品资料",
                title="灵兽系统说明",
                content_hash="active",
                chars=20,
            ),
            DataDocument(
                doc_id="doc-old",
                product="东煌纪",
                source_type="internal",
                section="产品资料",
                title="旧灵兽系统",
                content_hash="old",
                chars=10,
                status="archived",
            ),
            DataDocument(
                doc_id="doc-other",
                product="乐趣萌宠",
                source_type="official",
                section="玩法特色",
                title="宠物养成",
                content_hash="other",
                chars=30,
            ),
        ]
    )
    db.add_all(
        [
            DataChunk(
                chunk_id="doc-active::000",
                doc_id="doc-active",
                ordinal=0,
                text="灵兽系统说明",
            ),
            DataChunk(
                chunk_id="doc-active::001",
                doc_id="doc-active",
                ordinal=1,
                text="属性与进化",
            ),
        ]
    )
    db.commit()
    db.close()

    response = auth_client.get(
        "/api/admin/data/documents",
        params={
            "product": "东煌纪",
            "q": "灵兽",
            "status": "active",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["doc_id"] == "doc-active"
    assert payload["items"][0]["chunk_count"] == 2


def test_archiving_document_queues_index_rebuild(
    auth_client, session_factory, monkeypatch
):
    from backend.app.api import data_admin
    from backend.app.models.ingestion import DataDocument, IngestJob

    queued: list[str] = []
    monkeypatch.setattr(data_admin, "_enqueue_job", queued.append)
    db = session_factory()
    db.add(
        DataDocument(
            doc_id="doc-archive",
            product="东煌纪",
            source_type="internal",
            section="产品资料",
            title="待归档",
            content_hash="hash",
        )
    )
    db.commit()
    db.close()

    response = auth_client.patch(
        "/api/admin/data/documents/doc-archive",
        json={"status": "archived"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    assert len(queued) == 1
    db = session_factory()
    assert db.get(DataDocument, "doc-archive").status == "archived"
    job = db.scalar(select(IngestJob).where(IngestJob.id == queued[0]))
    assert job is not None
    assert job.kind == "reindex"
    db.close()


def test_crawler_sources_are_seeded_and_run_creates_job(
    auth_client, session_factory, monkeypatch
):
    from backend.app.api import data_admin
    from backend.app.models.ingestion import DataSource, IngestJob

    queued: list[str] = []
    monkeypatch.setattr(data_admin, "_enqueue_job", queued.append)

    sources = auth_client.get("/api/admin/data/sources")
    assert sources.status_code == 200
    assert {item["crawler_key"] for item in sources.json()} == {
        "donghuangji",
        "lqmc",
        "pkmbattle",
        "pokemon_sv",
    }

    response = auth_client.post(
        "/api/admin/data/sources/crawler_lqmc/run",
        json={"max_pages": 8},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["kind"] == "crawl"
    assert payload["source_id"] == "crawler_lqmc"
    assert queued == [payload["id"]]
    db = session_factory()
    source = db.get(DataSource, "crawler_lqmc")
    assert '"last_max_pages": 8' in source.config_json
    job = db.get(IngestJob, payload["id"])
    assert job.status == "queued"
    db.close()


def test_manual_index_rebuild_creates_reindex_job(
    auth_client, monkeypatch
):
    from backend.app.api import data_admin

    queued: list[str] = []
    monkeypatch.setattr(data_admin, "_enqueue_job", queued.append)

    response = auth_client.post("/api/admin/data/index/rebuild")

    assert response.status_code == 202
    assert response.json()["kind"] == "reindex"
    assert queued == [response.json()["id"]]


def test_catalog_is_derived_from_active_managed_documents(
    auth_client, session_factory
):
    from backend.app.models.ingestion import DataChunk, DataDocument

    db = session_factory()
    db.add_all(
        [
            DataDocument(
                doc_id="product-a",
                product="东煌纪",
                source_type="internal",
                section="产品资料",
                title="资料 A",
                content_hash="a",
            ),
            DataDocument(
                doc_id="product-b",
                product="乐趣萌宠",
                source_type="official",
                section="玩法特色",
                title="资料 B",
                content_hash="b",
            ),
            DataDocument(
                doc_id="hidden",
                product="东煌纪",
                source_type="internal",
                section="产品资料",
                title="归档资料",
                content_hash="c",
                status="archived",
            ),
        ]
    )
    db.add_all(
        [
            DataChunk(
                chunk_id="product-a::000",
                doc_id="product-a",
                ordinal=0,
                text="A1",
            ),
            DataChunk(
                chunk_id="product-a::001",
                doc_id="product-a",
                ordinal=1,
                text="A2",
            ),
            DataChunk(
                chunk_id="product-b::000",
                doc_id="product-b",
                ordinal=0,
                text="B1",
            ),
            DataChunk(
                chunk_id="hidden::000",
                doc_id="hidden",
                ordinal=0,
                text="隐藏",
            ),
        ]
    )
    db.commit()
    db.close()

    response = auth_client.get("/api/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"] == 2
    assert payload["chunks"] == 3
    products = {item["name"]: item for item in payload["products"]}
    assert products["东煌纪"]["documents"] == 1
    assert products["东煌纪"]["chunks"] == 2
    assert products["乐趣萌宠"]["sections"] == ["玩法特色"]


def test_catalog_stays_empty_when_every_document_is_archived(
    auth_client, session_factory
):
    from backend.app.models.ingestion import DataChunk, DataDocument

    db = session_factory()
    db.add(
        DataDocument(
            doc_id="archived-only",
            product="东煌纪",
            source_type="internal",
            section="产品资料",
            title="全部归档",
            content_hash="archived",
            status="archived",
        )
    )
    db.add(
        DataChunk(
            chunk_id="archived-only::000",
            doc_id="archived-only",
            ordinal=0,
            text="归档正文",
        )
    )
    db.commit()
    db.close()

    response = auth_client.get("/api/catalog")

    assert response.status_code == 200
    assert response.json()["documents"] == 0
    assert response.json()["chunks"] == 0
    assert response.json()["products"] == []
