import numpy as np

from backend.app.services.data.embedder import BgeM3Embedder
from backend.app.services.ingestion.parsers import (
    chunk_markdown,
    parse_upload,
)


def test_markdown_upload_uses_content_hash_and_keeps_product_metadata():
    content = "# 市场记录\n\n首测数据表现稳定。\n\n## 运营节奏\n\n每周一次版本更新。".encode()

    first = parse_upload(
        content,
        filename="市场记录.md",
        product="东煌纪",
        section="产品资料",
        title="九月市场记录",
    )
    second = parse_upload(
        content,
        filename="另一个名字.md",
        product="东煌纪",
        section="产品资料",
    )

    assert first.doc_id.startswith("upload_")
    assert first.doc_id == second.doc_id
    assert first.title == "九月市场记录"
    assert first.product == "东煌纪"
    assert first.section == "产品资料"
    assert "首测数据表现稳定" in first.body
    assert first.content_hash == second.content_hash


def test_csv_upload_is_converted_to_searchable_markdown_table():
    content = "区域,收入\n华东,120\n华南,90\n".encode()

    parsed = parse_upload(
        content,
        filename="收入.csv",
        product="东煌纪",
        section="经营数据",
    )

    assert "| 区域 | 收入 |" in parsed.body
    assert "| 华东 | 120 |" in parsed.body
    assert parsed.title == "收入"


def test_same_file_can_be_uploaded_to_different_products():
    content = "# 通用资料\n\n同一条竞品观察，可用于两个产品的对比。".encode()

    first = parse_upload(
        content,
        filename="观察.md",
        product="东煌纪",
        section="产品资料",
    )
    second = parse_upload(
        content,
        filename="观察.md",
        product="乐趣萌宠",
        section="产品资料",
    )

    assert first.doc_id != second.doc_id
    assert first.content_hash == second.content_hash


def test_chunk_markdown_prefers_headings_and_preserves_overlap():
    body = "# 总览\n\n" + "甲" * 12 + "\n\n## 数据\n\n" + "乙" * 12

    chunks = chunk_markdown(body, chunk_size=18, overlap=4)

    assert chunks[0].startswith("# 总览")
    assert any(chunk.startswith("## 数据") for chunk in chunks)
    assert "".join(chunks).count("甲") >= 12


def test_document_embedding_batches_and_normalizes_vectors():
    class FakeModel:
        def encode(self, texts, **_kwargs):
            return {
                "dense_vecs": np.array(
                    [[3.0, 4.0], [0.0, 2.0]],
                    dtype=np.float32,
                )[: len(texts)]
            }

    embedder = BgeM3Embedder()
    embedder._model = FakeModel()

    vectors = embedder.encode_documents(["甲", "乙"])

    assert vectors.shape == (2, 2)
    assert np.allclose(vectors[0], [0.6, 0.8])
    assert np.allclose(vectors[1], [0.0, 1.0])
