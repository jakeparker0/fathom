"""Tests for per-test rollback isolation of ``db_session`` (S1-06)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.orm import Session

# Both tests use the same name: each must find it absent at the start.
THROWAWAY_TABLE = "throwaway_isolation_check"


def _table_exists(session: Session) -> bool:
    found = session.execute(
        text("SELECT to_regclass(:name)"), {"name": THROWAWAY_TABLE}
    ).scalar_one()
    return found is not None


def test_commit_inside_the_test_does_not_reach_other_connections(
    db_session: Session, test_engine: Engine
) -> None:
    assert not _table_exists(db_session)

    db_session.execute(text("CREATE TABLE throwaway_isolation_check (id integer)"))
    db_session.execute(text("INSERT INTO throwaway_isolation_check VALUES (1)"))
    db_session.commit()

    rows = db_session.execute(
        text("SELECT id FROM throwaway_isolation_check")
    ).scalars()
    assert list(rows) == [1]
    with test_engine.connect() as other:
        found = other.execute(
            text("SELECT to_regclass(:name)"), {"name": THROWAWAY_TABLE}
        ).scalar_one()
    assert found is None


def test_a_table_created_by_another_test_does_not_exist(db_session: Session) -> None:
    assert not _table_exists(db_session)
