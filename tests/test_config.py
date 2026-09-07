"""Tests for the typed settings object (S1-04)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from fathom.config import Environment, LogLevel, Settings, get_settings

REQUIRED = {
    "UP_API_TOKEN": "up:yeah:test-token",
    "POSTGRES_PASSWORD": "test-password",
}


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear any real config so tests never depend on a developer's .env."""
    for key in (
        "ENVIRONMENT",
        "DEBUG",
        "LOG_LEVEL",
        "UP_API_TOKEN",
        "UP_API_BASE_URL",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DRIVER",
    ):
        monkeypatch.delenv(key, raising=False)
    # Ignore any real .env in the repo root so a developer's local secrets
    # cannot make these tests pass or fail by accident.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(**overrides: str) -> Settings:
    """Build Settings from explicit values, bypassing the environment.

    Init kwargs take field names, not env var names, so the keys are lowered
    here to keep the tests readable in terms of the .env keys.
    """
    values = {**REQUIRED, **overrides}
    return Settings(**{key.lower(): value for key, value in values.items()})  # type: ignore[arg-type]


def test_defaults_applied_when_only_required_keys_present() -> None:
    settings = _settings()

    assert settings.environment is Environment.LOCAL
    assert settings.debug is False
    assert settings.log_level is LogLevel.INFO
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432


def test_missing_required_keys_fail_loudly() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings()  # type: ignore[call-arg]

    missing = {error["loc"][0] for error in exc_info.value.errors()}
    assert {"up_api_token", "postgres_password"} <= missing


def test_secrets_are_masked_in_repr() -> None:
    settings = _settings()

    assert "up:yeah:test-token" not in repr(settings)
    assert "test-password" not in repr(settings)
    assert settings.up_api_token.get_secret_value() == "up:yeah:test-token"


def test_blank_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(UP_API_TOKEN="   ")


def test_whitespace_padded_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(POSTGRES_PASSWORD="hunter2\n")


def test_database_url_is_assembled_from_components() -> None:
    settings = _settings(
        POSTGRES_HOST="db",
        POSTGRES_PORT="6543",
        POSTGRES_DB="fathom_test",
        POSTGRES_USER="tester",
    )

    assert settings.database_url == (
        "postgresql+psycopg://tester:test-password@db:6543/fathom_test"
    )


def test_safe_database_url_masks_the_password() -> None:
    settings = _settings()

    assert "test-password" not in settings.safe_database_url
    assert settings.safe_database_url.endswith("@localhost:5432/fathom")


def test_model_dump_does_not_leak_the_database_url() -> None:
    # database_url is a plain property, not a computed field, precisely so a
    # careless model_dump() into a log line cannot expose the password.
    assert "database_url" not in _settings().model_dump()


def test_base_url_trailing_slash_is_normalised() -> None:
    settings = _settings(UP_API_BASE_URL="https://api.up.com.au/api/v1/")

    assert settings.up_api_base_url == "https://api.up.com.au/api/v1"


def test_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ENVIRONMENT", "production")

    settings = get_settings()

    assert settings.is_production is True
    assert settings.up_api_token.get_secret_value() == REQUIRED["UP_API_TOKEN"]


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)

    assert get_settings() is get_settings()


def test_settings_are_immutable() -> None:
    settings = _settings()

    with pytest.raises(ValidationError):
        settings.postgres_host = "somewhere-else"  # type: ignore[misc]


def test_values_are_read_from_a_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "UP_API_TOKEN=up:yeah:from-file\n"
        "POSTGRES_PASSWORD=from-file\n"
        "POSTGRES_DB=fathom_from_file\n"
    )
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)

    settings = Settings()  # type: ignore[call-arg]

    assert settings.up_api_token.get_secret_value() == "up:yeah:from-file"
    assert settings.postgres_db == "fathom_from_file"


def test_environment_variable_beats_the_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("UP_API_TOKEN=up:yeah:from-file\nPOSTGRES_PASSWORD=from-file\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    monkeypatch.setenv("UP_API_TOKEN", "up:yeah:from-environ")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.up_api_token.get_secret_value() == "up:yeah:from-environ"