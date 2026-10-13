# 02 - Per-test rollback Session, example tests, ADR-010

Status: ready-for-agent
Blocked by: 01

## What

- Function-scoped `db_session` fixture in `tests/conftest.py`: opens a
  connection from the 01 engine, begins an outer transaction, binds a `Session`
  with `join_transaction_mode="create_savepoint"`, rolls back and closes at
  teardown. Leave a marked placeholder for `alembic upgrade head` in the
  session fixture (S1-25).
- Example tests (name for behaviour, e.g.
  `test_rows_written_in_one_test_are_gone_in_the_next`):
  - one creates a throwaway table, inserts a row, reads it back, and `commit()`s;
  - one asserts that table does not exist.
  The second must not depend on running after the first (use a fixed table name
  and make the assertion order-independent: the table is absent at test start in
  both).
- Write `docs/adr/010-test-database-isolation.md` from `000-template.md`,
  recording spec decisions 1-6 and the rejected options.
- Add a short "Running tests" section to README: `docker compose up -d`,
  `uv run pytest`, and the `_test` database convention.

## Acceptance

- `uv run pytest` green; the two example tests pass in either order
  (`-p no:randomly` and reversed via `pytest tests/test_db.py::b tests/test_db.py::a`).
- A `commit()` inside a test does not persist after it.
- Ruff and pre-commit clean.

## Comments
