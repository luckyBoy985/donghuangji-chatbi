import subprocess
import sys
from pathlib import Path

from backend.scripts.evaluate_retrieval import retrieval_metrics

PYTHON = sys.executable
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_retrieval_metrics_use_expected_document_set():
    metrics = retrieval_metrics(["a", "c", "b"], ["a", "b"])

    assert metrics == {
        "hit": 1.0,
        "precision": 0.6667,
        "recall": 1.0,
        "mrr": 1.0,
    }


def test_retrieval_metrics_return_zero_without_relevant_document():
    metrics = retrieval_metrics(["c", "d"], ["a", "b"])

    assert metrics == {
        "hit": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "mrr": 0.0,
    }


def test_evaluate_script_can_run_as_a_file():
    result = subprocess.run(
        [PYTHON, "backend/scripts/evaluate_retrieval.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--output" in result.stdout
