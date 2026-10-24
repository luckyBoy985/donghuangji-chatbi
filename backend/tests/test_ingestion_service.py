import pytest
from sqlalchemy import func, select

from backend.app.models.ingestion import DataChunk, DataDocument, DataSource
from backend.app.services.ingestion.service import (
    IngestDocument,
    TransientIngestError,
    archive_missing_documents,
    process_crawl,
    upsert_document,
)
from backend.app.services.ingestion.crawlers import CrawlDocument
from backend.app.models.ingestion import IngestJob


def _document(body: str, *, digest: str = "hash-one") -> IngestDocument:
    return IngestDocument(
        doc_id="crawl_stable",
        product="东煌纪",
        source_type="internal",
        section="官方资讯",
        title="版本公告",
        url="https://example.test/news/1",
        published_at="2026-10-24",
        body=body,
        content_hash=digest,
        original_name="",
        object_key="",
    )


def test_upsert_is_idempotent_and_replaces_chunks_when_body_changes(
    session_factory,
):
    db = session_factory()
    first = upsert_document(
        db,
        _document("# 版本公告\n\n第一版内容足够长，可以建立索引分块。"),
        origin="crawler",
    )
    db.commit()
    second = upsert_document(
        db,
        _document("# 版本公告\n\n第一版内容足够长，可以建立索引分块。"),
        origin="crawler",
    )
    db.commit()

    assert first["inserted"] is True
    assert second["changed"] is False
    assert second["chunks"] == first["chunks"]

    upsert_document(
        db,
        _document(
            "# 版本公告\n\n第二版内容已经变化，需要替换全部分块。",
            digest="hash-two",
        ),
        origin="crawler",
    )
    db.commit()

    assert db.scalar(select(func.count()).select_from(DataDocument)) == 1
    chunks = list(
        db.scalars(
            select(DataChunk).where(DataChunk.doc_id == "crawl_stable")
        ).all()
    )
    assert chunks
    assert all("第二版" in chunk.text for chunk in chunks)
    document = db.get(DataDocument, "crawl_stable")
    assert document is not None
    assert document.content_hash == "hash-two"
    db.close()

def test_upsert_reactivates_previously_archived_document(session_factory):
    db = session_factory()
    upsert_document(
        db,
        _document("# 版本公告\n\n旧内容足够长，可以建立索引分块。"),
        origin="crawler",
    )
    document = db.get(DataDocument, "crawl_stable")
    document.status = "archived"
    db.commit()

    result = upsert_document(
        db,
        _document("# 版本公告\n\n重新上线内容足够长，可以建立索引分块。", digest="new"),
        origin="crawler",
    )
    db.commit()

    assert result["changed"] is True
    assert db.get(DataDocument, "crawl_stable").status == "active"
    db.close()


def test_upsert_updates_source_metadata_when_content_is_unchanged(
    session_factory,
):
    db = session_factory()
    db.add(
        DataSource(
            id="source-1",
            name="测试源",
            kind="crawler",
            crawler_key="test",
            product="东煌纪",
        )
    )
    db.commit()
    original = _document("# 版本公告\n\n正文内容足够长，可以建立索引分块。")
    upsert_document(db, original, origin="baseline")
    db.commit()
    refreshed = _document("# 版本公告\n\n正文内容足够长，可以建立索引分块。")
    refreshed.title = "版本公告（新标题）"
    refreshed.url = "https://example.test/news/updated"

    result = upsert_document(
        db,
        refreshed,
        origin="crawler",
        source_id="source-1",
    )
    db.commit()

    assert result["changed"] is False
    row = db.get(DataDocument, "crawl_stable")
    assert row.title == "版本公告（新标题）"
    assert row.url == "https://example.test/news/updated"
    assert row.origin == "crawler"
    assert row.source_id == "source-1"
    db.close()


def test_archive_guard_skips_suspicious_low_coverage_crawl(session_factory):
    db = session_factory()
    db.add(
        DataSource(
            id="source-guard",
            name="抓取保护测试",
            kind="crawler",
            crawler_key="guard",
            product="东煌纪",
        )
    )
    db.flush()
    for index in range(5):
        db.add(
            DataDocument(
                doc_id=f"guard-{index}",
                product="东煌纪",
                source_type="internal",
                section="官方资讯",
                title=f"资料 {index}",
                content_hash=str(index),
                source_id="source-guard",
            )
        )
    db.commit()

    suspicious = archive_missing_documents(
        db,
        source_id="source-guard",
        seen_doc_ids={"guard-0", "guard-1"},
    )
    db.commit()

    assert suspicious == 0
    assert all(
        row.status == "active"
        for row in db.scalars(
            select(DataDocument).where(
                DataDocument.source_id == "source-guard"
            )
        ).all()
    )

    healthy = archive_missing_documents(
        db,
        source_id="source-guard",
        seen_doc_ids={"guard-0", "guard-1", "guard-2", "guard-3"},
    )
    db.commit()

    assert healthy == 1
    assert db.get(DataDocument, "guard-4").status == "archived"
    db.close()


def test_upsert_repairs_chunk_layout_when_content_hash_matches(
    session_factory,
):
    db = session_factory()
    expected = _document("# 版本公告\n\n正文足够长，可以形成正确分块。")
    upsert_document(db, expected, origin="crawler")
    db.commit()
    for chunk in list(
        db.scalars(
            select(DataChunk).where(DataChunk.doc_id == "crawl_stable")
        ).all()
    ):
        db.delete(chunk)
    db.flush()
    db.add(
        DataChunk(
            chunk_id="crawl_stable::stale",
            doc_id="crawl_stable",
            ordinal=0,
            text="错误分块",
        )
    )
    db.commit()

    result = upsert_document(db, expected, origin="crawler")
    db.commit()

    chunks = list(
        db.scalars(
            select(DataChunk)
            .where(DataChunk.doc_id == "crawl_stable")
            .order_by(DataChunk.ordinal)
        ).all()
    )
    assert result["changed"] is True
    assert chunks[0].chunk_id == "crawl_stable::000"
    assert all(chunk.text != "错误分块" for chunk in chunks)
    db.close()


def test_crawl_job_stores_content_versioned_raw_snapshot(
    session_factory, monkeypatch
):
    from backend.app.services.ingestion import service

    db = session_factory()
    source = DataSource(
        id="crawler_snapshot",
        name="快照测试",
        kind="crawler",
        crawler_key="lqmc",
        product="乐趣萌宠",
        config_json='{"last_max_pages": 6}',
    )
    job = IngestJob(
        kind="crawl",
        product="乐趣萌宠",
        source_id=source.id,
    )
    db.add_all([source, job])
    db.commit()
    captured = {}

    def fake_put_bytes(key, content, content_type):
        captured.update(
            key=key,
            content=content.decode(),
            content_type=content_type,
        )
        return key

    monkeypatch.setattr(
        service,
        "crawl",
        lambda _key, _pages: [
            CrawlDocument(
                doc_id="snapshot-doc",
                product="乐趣萌宠",
                source_type="official",
                section="官网资讯",
                title="快照文章",
                url="https://lqmc.net/10.html",
                published_at="",
                body="解析后的正文足够建立索引。",
                content_hash="abcdef1234567890",
                raw_content="<html>原始页面</html>",
                raw_extension="html",
            )
        ],
    )
    monkeypatch.setattr(service, "put_bytes", fake_put_bytes)
    monkeypatch.setattr(
        service,
        "rebuild_index",
        lambda _db: {"chunks": 1, "embedded": 1, "reused": 0},
    )

    stats = process_crawl(db, job)

    assert captured["key"] == (
        "snapshots/crawler_snapshot/abcdef1234567890/snapshot-doc.html"
    )
    assert captured["content"] == "<html>原始页面</html>"
    assert captured["content_type"] == "text/html; charset=utf-8"
    document = db.get(DataDocument, "snapshot-doc")
    assert document.object_key == captured["key"]
    assert stats["snapshot_count"] == 1
    db.close()


def test_empty_crawl_is_transient_so_celery_can_retry(
    session_factory, monkeypatch
):
    from backend.app.services.ingestion import service

    db = session_factory()
    source = DataSource(
        id="crawler_transient",
        name="临时失败测试",
        kind="crawler",
        crawler_key="lqmc",
        product="乐趣萌宠",
    )
    job = IngestJob(
        kind="crawl",
        product="乐趣萌宠",
        source_id=source.id,
    )
    db.add_all([source, job])
    db.commit()
    monkeypatch.setattr(service, "crawl", lambda _key, _pages: [])

    with pytest.raises(TransientIngestError):
        process_crawl(db, job)
    db.close()
