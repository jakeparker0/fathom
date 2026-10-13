"""Helpers that provision the isolated test database (S1-06).

Kept out of ``conftest.py`` so the safety guard and the failure path can be
tested directly, without a running Postgres.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import OperationalError

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from fathom.config import Settings

TEST_DATABASE_SUFFIX = "_test"
# Always present in the postgres image; used only to issue DROP / CREATE.
MAINTENANCE_DATABASE = "postgres"


class UnsafeTestDatabaseError(RuntimeError):
    """The resolved database name is not a ``_test`` database."""


class DatabaseUnavailableError(RuntimeError):
    """Postgres could not be reached to provision the test database."""


def settings_for_test_database(settings: Settings) -> Settings:
    """Return ``settings`` with the database name set to ``<postgres_db>_test``."""
    name = f"{settings.postgres_db}{TEST_DATABASE_SUFFIX}"
    return settings.model_copy(update={"postgres_db": name})


def assert_is_test_database(name: str) -> None:
    """Refuse any name that does not end in ``_test``.

    Called before every destructive statement; this is the only thing between
    the fixture and the development database.
    """
    if not name.endswith(TEST_DATABASE_SUFFIX):
        msg = (
            f"refusing to drop or create {name!r}: "
            f"name must end in {TEST_DATABASE_SUFFIX!r}"
        )
        raise UnsafeTestDatabaseError(msg)


def _url(settings: Settings, database: str) -> URL:
    # URL.create escapes the password, unlike string-building settings.database_url.
    return URL.create(
        settings.postgres_driver,
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=database,
    )


def describe_connection_failure(settings: Settings, exc: OperationalError) -> str:
    """Explain why provisioning could not reach or use Postgres.

    A failure with no SQLSTATE never reached a server (refused, DNS, timeout), so
    "start the container" is the right advice. Once the server has answered with a
    SQLSTATE (bad password, missing role), that advice would be misleading.
    """
    url = settings.safe_database_url
    if getattr(exc.orig, "sqlstate", None) is None:
        return (
            f"Could not connect to Postgres at {url} to provision the test "
            "database. Is it running? Start it with `docker compose up -d`. "
            f"Driver error: {exc.orig}"
        )
    return (
        f"Postgres at {url} rejected the connection while provisioning the test "
        "database. Check POSTGRES_USER and POSTGRES_PASSWORD in .env match the "
        f"running database. Driver error: {exc.orig}"
    )


def provision_test_database(settings: Settings) -> Engine:
    """Drop and recreate ``<postgres_db>_test`` and return an engine for it."""
    test_settings = settings_for_test_database(settings)
    name = test_settings.postgres_db
    assert_is_test_database(name)

    admin = create_engine(
        _url(test_settings, MAINTENANCE_DATABASE), isolation_level="AUTOCOMMIT"
    )
    quoted = admin.dialect.identifier_preparer.quote(name)
    try:
        with admin.connect() as conn:
            # WITH (FORCE) so a stale connection from a previous run cannot block it.
            conn.execute(
                text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)")
            )  # identifier is quoted and guarded by assert_is_test_database
            conn.execute(text(f"CREATE DATABASE {quoted}"))
    except OperationalError as exc:
        raise DatabaseUnavailableError(
            describe_connection_failure(test_settings, exc)
        ) from exc
    finally:
        admin.dispose()

    return create_engine(_url(test_settings, name))
