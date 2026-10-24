import json
import pickle
from pathlib import Path

import numpy as np

from backend.scripts.import_data import import_dataset


def test_import_copies_index_and_builds_catalog(tmp_path: Path):
    source = tmp_path / "source"
    corpus = source / "corpus" / "东煌纪" / "产品资料"
    corpus.mkdir(parents=True)
    (corpus / "doc.md").write_text(
        "---\n"
        "doc_id: doc1\n"
        "product: 东煌纪\n"
        "section: 产品资料\n"
        "title: 测试\n"
        "---\n"
        "正文",
        encoding="utf-8",
    )
    (source / "index").mkdir()
    payload = {
        "chunks": [
            {
                "chunk_id": "doc1::000",
                "doc_id": "doc1",
                "product": "东煌纪",
                "source_type": "internal",
                "section": "产品资料",
                "title": "测试",
                "url": "",
                "published_at": "",
                "text": "正文",
            }
        ],
        "dense": np.ones((1, 1024), dtype=np.float32),
    }
    with (source / "index" / "local_index.pkl").open("wb") as handle:
        pickle.dump(payload, handle)
    (source / "gold_set.jsonl").write_text("{}\n", encoding="utf-8")

    result = import_dataset(source, tmp_path / "runtime")

    assert result["documents"] == 1
    assert result["chunks"] == 1
    catalog = json.loads(
        (tmp_path / "runtime" / "catalog.json").read_text(encoding="utf-8")
    )
    assert catalog["products"][0]["name"] == "东煌纪"
    assert (tmp_path / "runtime" / "index" / "local_index.pkl").exists()
