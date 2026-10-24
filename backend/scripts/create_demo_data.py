"""Create a small synthetic dataset for local demos and CI."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import random
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]

PRODUCTS = (
    ("示例产品 A", "图鉴", "青羽兽", "风属性，擅长高速群体攻击"),
    ("示例产品 B", "玩法", "赤焰兽", "火属性，核心玩法是进化与升星"),
    ("示例产品 C", "运营", "潮汐兽", "水属性，采用双周版本更新"),
    ("示例产品 D", "世界观", "岩甲兽", "土属性，强调大地图探索"),
)


def build_demo(runtime: Path) -> dict:
    corpus = runtime / "corpus"
    index_dir = runtime / "index"
    corpus.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[dict] = []
    catalog_products: list[dict] = []
    gold_rows: list[dict] = []

    for position, (product, section, creature, fact) in enumerate(PRODUCTS, start=1):
        doc_id = f"demo_{position}"
        title = f"{creature}演示档案"
        body = f"{creature}是 {product} 的示例灵兽。{fact}。"
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        document_dir = corpus / product / section
        document_dir.mkdir(parents=True, exist_ok=True)
        (document_dir / f"{doc_id}.md").write_text(
            "\n".join(
                [
                    "---",
                    f"doc_id: {doc_id}",
                    f"product: {product}",
                    "source_type: official",
                    f"section: {section}",
                    f"title: {title}",
                    "url: https://example.com/demo",
                    "published_at: 2026-01-01",
                    "---",
                    "",
                    f"# {title}",
                    "",
                    body,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        chunk = {
            "chunk_id": f"{doc_id}::000",
            "doc_id": doc_id,
            "product": product,
            "source_type": "official",
            "section": section,
            "title": title,
            "url": "https://example.com/demo",
            "published_at": "2026-01-01",
            "text": body,
        }
        chunks.append(chunk)
        catalog_products.append(
            {
                "name": product,
                "documents": 1,
                "chunks": 1,
                "sections": [section],
            }
        )
        gold_rows.append(
            {
                "id": f"demo-{position}",
                "question": f"{creature}是什么属性或玩法？",
                "dimension": section,
                "products": [product],
                "expected_doc_ids": [doc_id],
                "answer_points": fact,
                "expect_gap": False,
            }
        )

    generator = random.Random(20261024)
    dense = np.asarray(
        [
            [generator.uniform(-1.0, 1.0) for _ in range(1024)]
            for _ in chunks
        ],
        dtype=np.float32,
    )
    dense /= np.clip(np.linalg.norm(dense, axis=1, keepdims=True), 1e-8, None)
    with (index_dir / "local_index.pkl").open("wb") as handle:
        pickle.dump({"chunks": chunks, "dense": dense}, handle)

    catalog = {
        "documents": len(chunks),
        "chunks": len(chunks),
        "embedding_dim": 1024,
        "products": catalog_products,
    }
    (runtime / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runtime / "gold_set.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in gold_rows) + "\n",
        encoding="utf-8",
    )
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Create synthetic demo data")
    parser.add_argument(
        "--runtime",
        type=Path,
        default=ROOT / "data" / "runtime",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if (args.runtime / "index" / "local_index.pkl").exists() and not args.force:
        raise SystemExit("Runtime data exists; pass --force to replace demo files")
    print(json.dumps(build_demo(args.runtime), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
