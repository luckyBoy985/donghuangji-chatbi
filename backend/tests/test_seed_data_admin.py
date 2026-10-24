import pickle

import numpy as np
from sqlalchemy import func, select

from backend.app.models.ingestion import DataChunk, DataDocument
from backend.scripts.seed_data_admin import seed_index_documents


def test_seed_index_documents_is_idempotent(session_factory, tmp_path):
    index_path = tmp_path / "local_index.pkl"
    chunks = [
        {
            "chunk_id": "doc1::000",
            "doc_id": "doc1",
            "product": "东煌纪",
            "source_type": "internal",
            "section": "产品资料",
            "title": "资料一",
            "url": "",
            "published_at": "",
            "text": "第一段",
        },
        {
            "chunk_id": "doc1::001",
            "doc_id": "doc1",
            "product": "东煌纪",
            "source_type": "internal",
            "section": "产品资料",
            "title": "资料一",
            "url": "",
            "published_at": "",
            "text": "第二段",
        },
    ]
    with index_path.open("wb") as handle:
        pickle.dump(
            {
                "chunks": chunks,
                "dense": np.ones((2, 1024), dtype=np.float32),
            },
            handle,
        )
    db = session_factory()

    first = seed_index_documents(db, index_path=index_path)
    second = seed_index_documents(db, index_path=index_path)

    assert first == {"documents": 1, "chunks": 2}
    assert second == {"documents": 1, "chunks": 2}
    assert db.scalar(select(func.count()).select_from(DataDocument)) == 1
    assert db.scalar(select(func.count()).select_from(DataChunk)) == 2
    document = db.get(DataDocument, "doc1")
    assert document.title == "资料一"
    assert document.status == "active"
    db.close()

def test_seed_does_not_restore_stale_chunks_to_existing_document(
    session_factory, tmp_path
):
    index_path = tmp_path / "local_index.pkl"
    with index_path.open("wb") as handle:
        pickle.dump(
            {
                "chunks": [
                    {
                        "chunk_id": "managed::000",
                        "doc_id": "managed",
                        "product": "乐趣萌宠",
                        "source_type": "official",
                        "section": "官网资讯",
                        "title": "旧页面",
                        "url": "",
                        "published_at": "",
                        "text": "基线旧正文",
                    }
                ],
                "dense": np.ones((1, 1024), dtype=np.float32),
            },
            handle,
        )
    db = session_factory()
    seed_index_documents(db, index_path=index_path)
    document = db.get(DataDocument, "managed")
    document.title = "新页面"
    for chunk in list(document.chunks):
        db.delete(chunk)
    db.flush()
    db.add(
        DataChunk(
            chunk_id="managed::new",
            doc_id="managed",
            ordinal=0,
            text="重抓后的新正文",
        )
    )
    db.commit()

    seed_index_documents(db, index_path=index_path)

    chunks = list(
        db.scalars(
            select(DataChunk).where(DataChunk.doc_id == "managed")
        ).all()
    )
    assert [chunk.text for chunk in chunks] == ["重抓后的新正文"]
    assert db.get(DataDocument, "managed").title == "新页面"
    db.close()
