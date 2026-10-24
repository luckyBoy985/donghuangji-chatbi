# Contributing

## Development

1. Copy `.env.example` to `.env` and replace every placeholder.
2. Install Python 3.12 and Node.js 20.
3. Install backend test dependencies with `pip install -e "backend[test]"`.
4. Install frontend dependencies with `npm ci` inside `frontend`.
5. Run `scripts/test.ps1 -SkipEval` before opening a pull request.

The full retrieval evaluation requires local BGE-M3 and BGE-Reranker model
directories. Run `scripts/test.ps1` only after configuring those paths.

## Pull requests

- Keep changes focused and explain the user-visible behavior.
- Add a regression test before changing authentication, permissions, ingestion,
  retrieval, or index behavior.
- Do not add scraped datasets, personal data, model weights, credentials, or
  production exports to the repository.
- Update documentation when configuration or deployment behavior changes.

By contributing, you agree that your source-code contribution is licensed under
the repository's MIT license. Third-party data remains subject to its own terms.
