from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.data.repository import get_repository
from backend.app.services.data.retrieval import RetrievalEngine


def retrieval_metrics(
    retrieved: list[str], expected: list[str]
) -> dict[str, float]:
    expected_set = set(expected)
    retrieved_set = set(retrieved)
    matches = expected_set & retrieved_set
    mrr = 0.0
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in expected_set:
            mrr = 1.0 / rank
            break
    return {
        "hit": 1.0 if matches else 0.0,
        "precision": round(len(matches) / max(len(retrieved_set), 1), 4),
        "recall": round(len(matches) / max(len(expected_set), 1), 4),
        "mrr": round(mrr, 4),
    }


def _unique_documents(hits: list, limit: int = 5) -> list[str]:
    result: list[str] = []
    for hit in hits:
        if hit.doc_id not in result:
            result.append(hit.doc_id)
        if len(result) >= limit:
            break
    return result


def evaluate(gold_path: Path) -> dict:
    questions = [
        json.loads(line)
        for line in gold_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    engine = RetrievalEngine(get_repository())
    rows: list[dict] = []
    started = time.time()
    for question in questions:
        expected = question.get("expected_doc_ids") or []
        if not expected:
            rows.append(
                {
                    "id": question["id"],
                    "question": question["question"],
                    "expected": expected,
                    "retrieved": [],
                    "retrieval_evaluated": False,
                }
            )
            continue
        hits = engine.search(
            question["question"],
            products=question.get("products") or [],
            limit=20,
        )
        retrieved = _unique_documents(hits, 5)
        rows.append(
            {
                "id": question["id"],
                "question": question["question"],
                "products": question.get("products") or [],
                "expected": expected,
                "retrieved": retrieved,
                "scores": [round(hit.score, 4) for hit in hits[:5]],
                "retrieval_evaluated": True,
                **retrieval_metrics(retrieved, expected),
            }
        )

    scored = [row for row in rows if row["retrieval_evaluated"]]
    divisor = max(len(scored), 1)
    summary = {
        "questions": len(rows),
        "retrieval_questions": len(scored),
        "hit@5": round(sum(row["hit"] for row in scored) / divisor, 4),
        "precision@5": round(
            sum(row["precision"] for row in scored) / divisor, 4
        ),
        "recall@5": round(sum(row["recall"] for row in scored) / divisor, 4),
        "mrr": round(sum(row["mrr"] for row in scored) / divisor, 4),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    return {"summary": summary, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="评测混合检索 Hit@5")
    parser.add_argument("--gold", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    repository = get_repository()
    gold_path = args.gold or repository.index_path.parents[1] / "gold_set.jsonl"
    result = evaluate(gold_path)
    output = args.output or gold_path.parent / "eval_results.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result["summary"]["hit@5"] >= 0.8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
