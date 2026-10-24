from __future__ import annotations

import argparse
import json
import pickle
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


def _read_index(index_file: Path) -> tuple[list[dict[str, Any]], np.ndarray]:
    with index_file.open("rb") as handle:
        payload = pickle.load(handle)
    chunks = payload.get("chunks")
    dense = np.asarray(payload.get("dense"))
    if not isinstance(chunks, list) or dense.ndim != 2:
        raise ValueError("索引文件格式无效")
    if dense.shape != (len(chunks), 1024):
        raise ValueError(
            f"索引维度不一致：chunks={len(chunks)}, dense={dense.shape}"
        )
    return chunks, dense


def _build_catalog(chunks: list[dict[str, Any]], embedding_dim: int) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        grouped[str(chunk.get("product", ""))].append(chunk)

    products = [
        {
            "name": product,
            "documents": len({str(chunk.get("doc_id", "")) for chunk in product_chunks}),
            "chunks": len(product_chunks),
            "sections": sorted(
                {str(chunk.get("section", "")) for chunk in product_chunks}
            ),
        }
        for product, product_chunks in sorted(
            grouped.items(), key=lambda item: (-len(item[1]), item[0])
        )
    ]
    return {
        "documents": len({str(chunk.get("doc_id", "")) for chunk in chunks}),
        "chunks": len(chunks),
        "embedding_dim": embedding_dim,
        "products": products,
    }


def import_dataset(source: Path, destination: Path) -> dict[str, Any]:
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    index_file = source / "index" / "local_index.pkl"
    corpus_dir = source / "corpus"
    gold_set = source / "gold_set.jsonl"
    for required in (index_file, corpus_dir, gold_set):
        if not required.exists():
            raise FileNotFoundError(f"数据基线缺失：{required}")

    chunks, dense = _read_index(index_file)
    empty_chunks = sum(not str(chunk.get("text", "")).strip() for chunk in chunks)
    if empty_chunks:
        raise ValueError(f"索引包含 {empty_chunks} 个空正文分块")

    (destination / "index").mkdir(parents=True, exist_ok=True)
    shutil.copy2(index_file, destination / "index" / "local_index.pkl")
    shutil.copytree(corpus_dir, destination / "corpus", dirs_exist_ok=True)
    shutil.copy2(gold_set, destination / "gold_set.jsonl")

    catalog = _build_catalog(chunks, int(dense.shape[1]))
    (destination / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="导入东煌纪竞品情报数据基线")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = import_dataset(args.source, args.destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
