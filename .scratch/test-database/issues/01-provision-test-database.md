# 01 - Provision the test database

Status: ready-for-agent
Blocked by: none

## What

- Add `sqlalchemy` to runtime dependencies (`uv add sqlalchemy`; commit `uv.lock`).
- In `tests/conftest.py`, add a session-scoped fixture that:
  - builds connection details from `get_settings()` with the database name
    overridden to `<postgres_db>_test`;
  - asserts the name ends in `_test` before any destructive statement;
  - connects to the maintenance database in autocommit, drops and recreates
    `<db>_test`;
  - on connection failure, raises an error whose message says to run
    `docker compose up -d`;
  - yields a SQLAlchemy `Engine` for the test database.
- Never print or log the password; use `safe_database_url` for any message.

## Acceptance

- Fixture creates the database and the engine can `SELECT 1`.
- The guard refuses a non-`_test` name (test it by passing a bad name to the
  helper that does the check, not by running a real drop).
- With Postgres stopped, a test requesting the fixture fails with the
  `docker compose up -d` message; tests not requesting it still pass.
- Type-annotated, no `Any`, no `os.environ` (AGENTS.md).

## Comments
