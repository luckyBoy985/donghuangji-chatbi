from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def database_fingerprint(chunks: list[dict]) -> str:
    payload = [
        [
            chunk["chunk_id"],
            chunk["doc_id"],
            chunk["product"],
            chunk["section"],
            chunk["title"],
            chunk["text"],
        ]
        for chunk in chunks
    ]
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def write_index_manifest(
    manifest_path: Path,
    *,
    index_path: Path,
    chunks: list[dict],
    embedding_dim: int,
    model_id: str,
) -> dict:
    manifest = {
        "format_version": 1,
        "generation": uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "embedding_dim": embedding_dim,
        "documents": len({chunk["doc_id"] for chunk in chunks}),
        "chunks": len(chunks),
        "database_fingerprint": database_fingerprint(chunks),
        "index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, manifest_path)
    return manifest


def validate_index_manifest(
    index_path: Path,
    manifest_path: Path,
) -> dict:
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("索引 manifest 无法读取") from error
    if manifest.get("format_version") != 1:
        raise ValueError("索引 manifest 版本不支持")
    expected = str(manifest.get("index_sha256", ""))
    actual = hashlib.sha256(index_path.read_bytes()).hexdigest()
    if not expected or expected != actual:
        raise ValueError("索引与 manifest 校验和不一致")
    return manifest
