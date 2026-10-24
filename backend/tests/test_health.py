import pickle

import numpy as np

from backend.app.core.config import settings
from backend.app.models.ingestion import DataChunk, DataDocument
from backend.app.services.data.index_manifest import write_index_manifest


def _write_index(path):
    chunks = [
        {
            "chunk_id": "health-doc::000",
            "doc_id": "health-doc",
            "product": "东煌纪",
            "source_type": "internal",
            "section": "产品资料",
            "title": "健康检查",
            "url": "",
            "published_at": "",
            "text": "索引正文",
        }
    ]
    with path.open("wb") as handle:
        pickle.dump(
            {
                "chunks": chunks,
                "dense": np.ones((1, 1024), dtype=np.float32),
            },
            handle,
        )
    return chunks


def test_health_verifies_manifest_against_database(
    client, session_factory, tmp_path, monkeypatch
):
    (tmp_path / "index").mkdir()
    index_path = tmp_path / "index" / "local_index.pkl"
    platform_path = tmp_path / "index" / "platform_index.pkl"
    manifest_path = tmp_path / "index" / "platform_index.manifest.json"
    _write_index(platform_path)
    write_index_manifest(
        manifest_path,
        index_path=platform_path,
        chunks=_write_index(platform_path),
        embedding_dim=1024,
        model_id="bge-m3",
    )
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    db = session_factory()
    db.add(
        DataDocument(
            doc_id="health-doc",
            product="东煌纪",
            source_type="internal",
            section="产品资料",
            title="健康检查",
            content_hash="health",
        )
    )
    db.add(
        DataChunk(
            chunk_id="health-doc::000",
            doc_id="health-doc",
            ordinal=0,
            text="索引正文",
        )
    )
    db.commit()
    db.close()

    response = client.get("/api/health")

    assert response.status_code == 200
    index = response.json()["index"]
    assert index["status"] == "ready"
    assert index["manifest_status"] == "verified"
    assert index["documents"] == 1
    assert index["chunks"] == 1


def test_health_detects_corrupt_platform_manifest(
    client, tmp_path, monkeypatch
):
    (tmp_path / "index").mkdir()
    index_path = tmp_path / "index" / "local_index.pkl"
    platform_path = tmp_path / "index" / "platform_index.pkl"
    manifest_path = tmp_path / "index" / "platform_index.manifest.json"
    _write_index(index_path)
    _write_index(platform_path)
    manifest_path.write_text('{"format_version": 1}', encoding="utf-8")
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["index"]["status"] == "unavailable"
    assert response.json()["status"] == "degraded"
