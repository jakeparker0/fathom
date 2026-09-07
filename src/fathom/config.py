"""Application configuration.

Every environment-dependent value and secret Fathom needs is declared here as a
single typed settings object. Call sites depend only on :func:`get_settings` and
never read ``os.environ`` directly.

That indirection is the point. In Sprint 6 (PL-13) the source of these values
moves from a local ``.env`` file to OCI Vault; when it does, the change is
confined to :meth:`Settings.settings_customise_sources` below and no caller
changes at all.

Usage::

    from fathom.config import get_settings

    settings = get_settings()
    token = settings.up_api_token.get_secret_value()
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

# Repo root, so the .env file is found regardless of the working directory the
# app or a test happens to be launched from. src/fathom/config.py -> repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Environment(StrEnum):
    """Where the app is running. Drives nothing yet; read by logging and, in
    Sprint 6, by the choice of secrets source."""

    LOCAL = "local"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """The one typed view of Fathom's configuration.

    Secrets are typed as :class:`~pydantic.SecretStr` so they are masked in
    reprs, logs and tracebacks. Reach the raw value deliberately with
    ``.get_secret_value()``.
    """

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # --- Runtime ---------------------------------------------------------
    environment: Environment = Environment.LOCAL
    debug: bool = False
    log_level: LogLevel = LogLevel.INFO

    # --- Up Bank ---------------------------------------------------------
    up_api_token: SecretStr = Field(
        description="Up personal access token, from https://api.up.com.au",
    )
    up_api_base_url: str = "https://api.up.com.au/api/v1"

    # --- Database --------------------------------------------------------
    # Component parts rather than one URL, so docker-compose.yml (S1-03) can
    # read the same .env for POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB.
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "fathom"
    postgres_user: str = "fathom"
    postgres_password: SecretStr = Field(
        description="Password for the local Postgres role.",
    )
    # TODO:Driver is configurable because the backend framework choice (ADR-002) is
    # not yet made; psycopg3 sync is the safe default. 
    postgres_driver: str = "postgresql+psycopg"

    @field_validator("up_api_token", "postgres_password")
    @classmethod
    def _reject_blank_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw.strip():
            msg = "must not be empty"
            raise ValueError(msg)
        if raw != raw.strip():
            msg = "has leading or trailing whitespace - check for a stray paste"
            raise ValueError(msg)
        return value

    @field_validator("up_api_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def database_url(self) -> str:
        """SQLAlchemy-style DSN, password included.

        A plain property rather than a computed field on purpose: this must not
        appear in ``model_dump()`` output, which is the sort of thing that ends
        up in a log line. Use :attr:`safe_database_url` for anything printed.
        """
        password = self.postgres_password.get_secret_value()
        return (
            f"{self.postgres_driver}://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def safe_database_url(self) -> str:
        """The DSN with the password masked. Safe to log."""
        return (
            f"{self.postgres_driver}://{self.postgres_user}:***"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Sequence[PydanticBaseSettingsSource]:
        """Resolution order, highest precedence first.

        This is the seam for PL-13. In Sprint 6 an ``OCIVaultSettingsSource``
        is inserted ahead of ``dotenv_settings`` (or in place of it when
        ``ENVIRONMENT=production``) and nothing else in the codebase moves.
        """
        return (
            init_settings,  # explicit kwargs - used by tests
            env_settings,  # real environment variables
            dotenv_settings,  # .env file
            file_secret_settings,  # /run/secrets style mounts
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, loading them on first call.

    Cached so the .env file is read once. Tests that need a different
    configuration should call ``get_settings.cache_clear()`` first, or build a
    ``Settings(...)`` instance directly.
    """
    return Settings()  # type: ignore[call-arg]  # values come from the sources above