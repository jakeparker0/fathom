# Spec: Test database (S1-06)

Branch: `feature/s1-06-test-database` (ADR-001). Commits: `S1-06: …`.

## Goal

pytest with a passing example test and an isolated test database fixture, so
repository and service tests (S1-25 onwards) can hit real Postgres without ever
touching the development database.

## Decisions (from grilling)

1. **Isolation**: a dedicated `<postgres_db>_test` database on the existing
   docker-compose Postgres. Per-test isolation by an outer transaction rolled
   back at test end. Rejected: per-test template databases, testcontainers.
2. **Fixture yields a SQLAlchemy `Session`** bound to a connection in an outer
   transaction, `join_transaction_mode="create_savepoint"`, so a `commit()` in
   code under test still rolls back. `sqlalchemy` becomes a runtime dependency
   (already decided in ADR-002).
3. **Safety guard**: connection details come from `get_settings()` only (no
   `os.environ`). The database name is `<postgres_db>_test`. The fixture asserts
   the resolved name ends in `_test` before any `DROP` / `CREATE`.
4. **Postgres down**: fail loudly with a message pointing at
   `docker compose up -d`. No skip. The fixture is lazy, so tests that do not
   request it (domain tests, `test_config.py`) never need Postgres.
5. **Empty schema**: no models or migrations exist yet (S1-21, S1-25). The
   fixture creates an empty database and marks where `alembic upgrade head`
   slots in at S1-25. Example tests use a throwaway table created inside the
   test transaction (Postgres DDL is transactional). The schema and data model
   are not touched (hand-written area).
6. **Lifecycle**: drop and recreate `<db>_test` at session start; leave it in
   place at session end for inspection.
7. **ADR-010** "Test database isolation" records 1-6 using `000-template.md`.
8. **Fixtures**: `tests/fixtures/` is untracked (real data, public repo, to be
   masked) and excluded locally via `.git/info/exclude`. Never staged, never read.

## Out of scope

- Schema, models, Alembic (S1-21, S1-25).
- CI wiring (S1-29).
- Masking or committing `tests/fixtures/up/`.
- Parallel test execution (xdist).

## Done when

- `uv run pytest` green with Postgres up.
- `uv run pytest` with the container stopped fails with a readable message
  (only for tests that request the DB fixture).
- `uv run ruff check` and `uv run ruff format --check` clean; pre-commit passes
  without `--no-verify`.
- A fresh sub-agent reviews the diff against `docs/agents/review-checklist.md`.
- S1-06 ticked in the vault `Fathom.md` with a dated "(AI)" log line.
