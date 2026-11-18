# Tests

Phase 1 backend tests live next to the backend code in
[`backend/tests/`](../backend/tests/) and use Pytest.

This root directory is reserved for cross-system tests introduced later:

- API integration tests against a real PostgreSQL container
- pipeline contract tests over a small, documented data sample
- end-to-end frontend/API flows

Avoid committing full datasets to make tests pass. Use small, clearly labelled
fixtures with documented provenance, or run tests against the downloaded local
dataset.
