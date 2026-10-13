"""Shared fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.orm import Session

from fathom.config import get_settings
from testdb import provision_test_database

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Engine


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Engine for a freshly created ``<postgres_db>_test`` database.

    Lazy: tests that do not request it never need Postgres. The database is
    left in place at session end for inspection and dropped on the next run.
    """
    engine = provision_test_database(get_settings())
    # S1-25: run `alembic upgrade head` against `engine` here.
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[Session]:
    """Session whose writes, including ``commit()``, are rolled back at teardown.

    The session joins an outer transaction through a SAVEPOINT, so a
    ``commit()`` in the code under test only releases the savepoint.
    """
    connection = test_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
