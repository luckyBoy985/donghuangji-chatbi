import pickle

import numpy as np

from backend.app.models.ingestion import DataChunk, DataDocument
from backend.app.services.ingestion.indexer import rebuild_platform_index


class FixedDocumentEmbedder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        self.calls.append(texts)
        return np.tile(
            np.array([0.0, 1.0], dtype=np.float32),
            (len(texts), 1),
        )


def test_rebuild_reuses_unchanged_vectors_and_excludes_archived_documents(
    session_factory, tmp_path
):
    db = session_factory()
    db.add_all(
        [
            DataDocument(
                doc_id="doc-a",
                product="东煌纪",
                source_type="internal",
                section="产品资料",
                title="已存在",
                content_hash="a",
            ),
            DataDocument(
                doc_id="doc-b",
                product="东煌纪",
                source_type="internal",
                section="产品资料",
                title="已归档",
                content_hash="b",
                status="archived",
            ),
            DataDocument(
                doc_id="doc-c",
                product="东煌纪",
                source_type="internal",
                section="产品资料",
                title="新资料",
                content_hash="c",
            ),
        ]
    )
    db.add_all(
        [
            DataChunk(
                chunk_id="a::000",
                doc_id="doc-a",
                ordinal=0,
                text="未变化正文",
            ),
            DataChunk(
                chunk_id="b::000",
                doc_id="doc-b",
                ordinal=0,
                text="归档正文",
            ),
            DataChunk(
                chunk_id="c::000",
                doc_id="doc-c",
                ordinal=0,
                text="新增正文",
            ),
        ]
    )
    db.commit()

    source_path = tmp_path / "base.pkl"
    source_chunks = [
        {
            "chunk_id": "a::000",
            "doc_id": "doc-a",
            "product": "东煌纪",
            "section": "产品资料",
            "title": "已存在",
            "source_type": "internal",
            "url": "",
            "published_at": "",
            "text": "未变化正文",
        },
        {
            "chunk_id": "b::000",
            "doc_id": "doc-b",
            "product": "东煌纪",
            "section": "产品资料",
            "title": "已归档",
            "source_type": "internal",
            "url": "",
            "published_at": "",
            "text": "归档正文",
        },
    ]
    with source_path.open("wb") as handle:
        pickle.dump(
            {
                "chunks": source_chunks,
                "dense": np.array(
                    [[1.0, 0.0], [0.0, 1.0]],
                    dtype=np.float32,
                ),
            },
            handle,
        )
    output_path = tmp_path / "platform.pkl"
    embedder = FixedDocumentEmbedder()

    result = rebuild_platform_index(
        db,
        source_index=source_path,
        output_path=output_path,
        embedder=embedder,
    )
    db.close()

    with output_path.open("rb") as handle:
        payload = pickle.load(handle)
    assert result.chunks == 2
    assert result.embedded == 1
    assert [chunk["chunk_id"] for chunk in payload["chunks"]] == [
        "a::000",
        "c::000",
    ]
    assert payload["dense"][0].tolist() == [1.0, 0.0]
    assert payload["dense"][1].tolist() == [0.0, 1.0]
    assert embedder.calls == [["新增正文"]]
