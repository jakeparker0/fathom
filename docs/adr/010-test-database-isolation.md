# ADR-010: Test database isolation

**Status:** Accepted
**Date:** 2026-10-12

## Context

Repository and service tests (S1-25 onwards) need real Postgres: the money, period and Spend rules depend on SQL behaviour that a fake would not reproduce. Those tests must never touch the development database, must not leak rows into each other, and must stay fast enough to run constantly. Only a local docker-compose Postgres exists (ADR-004), and there are no models or migrations yet (S1-21, S1-25).

## Options Considered

### Option A: Dedicated `<postgres_db>_test` database, per-test rollback
- Pros: reuses the existing container; a rolled-back transaction is the cheapest reset; Postgres DDL is transactional, so tests can create tables too.
- Cons: code under test that opens its own connection or relies on a real commit is not covered; the guard against hitting the wrong database must be explicit.

### Option B: Per-test template databases
- Pros: full isolation, including real commits and multiple connections.
- Cons: `CREATE DATABASE ... TEMPLATE` per test is slow and grows with the schema.

### Option C: testcontainers
- Pros: no shared state with the developer's Postgres at all.
- Cons: another dependency and a container start-up cost for a single-user project that already runs compose.

## Decision

Option A. The decisions that make it work:

1. **Isolation:** a `<postgres_db>_test` database on the compose Postgres. Each test runs inside an outer transaction that is rolled back at teardown.
2. **Session:** the `db_session` fixture yields a SQLAlchemy `Session` bound to a connection in that outer transaction with `join_transaction_mode="create_savepoint"`, so a `commit()` in code under test releases a savepoint and still rolls back. `sqlalchemy` is a runtime dependency (ADR-002).
3. **Safety guard:** connection details come from `get_settings()` only. The name is `<postgres_db>_test`, and the fixture asserts it ends in `_test` before any `DROP` or `CREATE`.
4. **Postgres down:** fail loudly with a message pointing at `docker compose up -d`; no skip. The fixture is lazy, so tests that do not request it never need Postgres.
5. **Empty schema:** the database is created empty. `alembic upgrade head` slots into the session fixture at S1-25 (marked in `tests/conftest.py`). Until then tests create throwaway tables inside the test transaction.
6. **Lifecycle:** drop and recreate the database at session start; leave it in place at session end for inspection.

## Consequences

- Tests that use `db_session` are fast and cannot leak state into each other. Code under test that opens its own engine is not covered.
- A test that needs a real commit, or a second connection seeing committed data, cannot use `db_session`; it would need its own fixture and an ADR amendment.
- Parallel runs (xdist) would collide on the one database; out of scope until needed.
- A failed run leaves `<db>_test` behind; it is dropped with `WITH (FORCE)` on the next run.
- S1-25 must add the migration step to the session fixture so every test sees the real schema.

## Notes

- `DROP DATABASE ... WITH (FORCE)` needs Postgres 13 or later; the compose image is 18.
- Revisit if tests need committed data across connections (Option B) or CI wiring (S1-29) prefers a service container (Option C).
