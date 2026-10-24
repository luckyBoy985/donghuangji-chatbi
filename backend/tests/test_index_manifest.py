import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
import pytest

from backend.app.models.ingestion import DataChunk, DataDocument
from backend.app.services.data.repository import DataRepository
from backend.app.services.ingestion.indexer import rebuild_platform_index


class FixedEmbedder:
    def encode_documents(self, texts):
        return np.tile(
            np.array([1.0, 0.0], dtype=np.float32),
            (len(texts), 1),
        )


def test_rebuild_writes_generation_manifest(session_factory, tmp_path):
    db = session_factory()
    db.add(
        DataDocument(
            doc_id="manifest-doc",
            product="东煌纪",
            source_type="internal",
            section="产品资料",
            title="Manifest 资料",
            content_hash="content-hash",
        )
    )
    db.add(
        DataChunk(
            chunk_id="manifest-doc::000",
            doc_id="manifest-doc",
            ordinal=0,
            text="需要写入索引的正文",
        )
    )
    db.commit()
    output = tmp_path / "platform.pkl"
    manifest_path = tmp_path / "platform.manifest.json"

    result = rebuild_platform_index(
        db,
        source_index=tmp_path / "missing.pkl",
        output_path=output,
        manifest_path=manifest_path,
        embedder=FixedEmbedder(),
        model_id="bge-m3:test",
    )
    db.close()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result.chunks == 1
    assert manifest["format_version"] == 1
    assert manifest["model_id"] == "bge-m3:test"
    assert manifest["documents"] == 1
    assert manifest["chunks"] == 1
    assert manifest["embedding_dim"] == 2
    assert manifest["index_sha256"] == hashlib.sha256(
        output.read_bytes()
    ).hexdigest()
    assert len(manifest["generation"]) == 32
    assert len(manifest["database_fingerprint"]) == 64


def test_repository_rejects_index_that_does_not_match_manifest(tmp_path):
    index_path = tmp_path / "base.pkl"
    platform_path = tmp_path / "platform.pkl"
    manifest_path = tmp_path / "platform.manifest.json"
    payload = {
        "chunks": [
            {
                "chunk_id": "a::000",
                "doc_id": "a",
                "product": "东煌纪",
                "source_type": "internal",
                "section": "产品资料",
                "title": "资料",
                "url": "",
                "published_at": "",
                "text": "正文",
            }
        ],
        "dense": np.ones((1, 1024), dtype=np.float32),
    }
    for path in (index_path, platform_path):
        with path.open("wb") as handle:
            pickle.dump(payload, handle)
    manifest = {
        "format_version": 1,
        "generation": "a" * 32,
        "created_at": "2026-10-24T00:00:00+00:00",
        "model_id": "bge-m3",
        "embedding_dim": 1024,
        "documents": 1,
        "chunks": 1,
        "database_fingerprint": "b" * 64,
        "index_sha256": hashlib.sha256(platform_path.read_bytes()).hexdigest(),
    }
    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    with platform_path.open("ab") as handle:
        handle.write(b"corruption")
    repository = DataRepository(
        index_path,
        platform_path,
        manifest_path,
    )

    with pytest.raises(ValueError, match="manifest"):
        repository.load()
