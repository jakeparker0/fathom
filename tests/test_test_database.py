"""Tests for the test database provisioning (S1-06)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from fathom.config import Settings
from testdb import (
    DatabaseUnavailableError,
    UnsafeTestDatabaseError,
    assert_is_test_database,
    describe_connection_failure,
    provision_test_database,
    settings_for_test_database,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine

PASSWORD = "s3cret-pw"  # noqa: S105  # fixture value, not a real secret


def _settings(**overrides: str | int) -> Settings:
    values: dict[str, str | int] = {
        "up_api_token": "up:yeah:test-token",
        "postgres_password": PASSWORD,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]  # pydantic-settings init kwargs are typed loosely


def test_database_name_gets_the_test_suffix() -> None:
    settings = settings_for_test_database(_settings(postgres_db="fathom"))

    assert settings.postgres_db == "fathom_test"


def test_guard_refuses_a_name_without_the_test_suffix() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_is_test_database("fathom")


def test_guard_accepts_a_test_database_name() -> None:
    assert_is_test_database("fathom_test")


def test_unreachable_postgres_says_to_run_docker_compose_up() -> None:
    # Port 1 refuses connections immediately; no Postgres needed.
    settings = _settings(postgres_host="127.0.0.1", postgres_port=1)

    with pytest.raises(DatabaseUnavailableError) as exc_info:
        provision_test_database(settings)

    assert "docker compose up -d" in str(exc_info.value)
    assert PASSWORD not in str(exc_info.value)


class _ServerRejected(Exception):  # noqa: N818  # stand-in for a psycopg error
    sqlstate = "28P01"


def test_rejected_credentials_do_not_suggest_starting_the_container() -> None:
    exc = OperationalError("SELECT 1", {}, _ServerRejected("auth failed"))

    message = describe_connection_failure(_settings(), exc)

    assert "docker compose up" not in message
    assert "POSTGRES_PASSWORD" in message
    assert PASSWORD not in message


def test_unreachable_server_error_names_the_safe_url() -> None:
    exc = OperationalError("SELECT 1", {}, ConnectionRefusedError("refused"))

    message = describe_connection_failure(_settings(), exc)

    assert "docker compose up -d" in message
    assert "***" in message
    assert PASSWORD not in message


def test_engine_for_the_test_database_can_select_one(test_engine: Engine) -> None:
    with test_engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1


def test_engine_points_at_the_test_database(test_engine: Engine) -> None:
    with test_engine.connect() as conn:
        name = conn.execute(text("SELECT current_database()")).scalar_one()

    assert name.endswith("_test")
