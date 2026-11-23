"""Validated startup configuration. Secret values are excluded from repr."""

import os
from dataclasses import dataclass
from pathlib import Path

from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict


@dataclass(frozen=True, repr=False)
class DatabaseConfig:
    """PostgreSQL connection settings; production verifies server identity."""

    url: str
    environment: str = "development"
    ca_file: str = ""

    def __post_init__(self):
        try:
            values = conninfo_to_dict(self.url)
        except ProgrammingError:
            raise ValueError("Invalid DATABASE_URL") from None
        if not values.get("dbname") or not values.get("host"):
            raise ValueError("DATABASE_URL must name a host and database")
        if self.environment not in ("development", "production"):
            raise ValueError("Invalid database environment")
        if self.environment == "development" and values["host"] not in (
            "localhost",
            "127.0.0.1",
            "::1",
        ):
            raise ValueError(
                "Remote databases require APP_ENV=production and verified TLS"
            )
        if self.environment == "production" and (
            not self.ca_file or not Path(self.ca_file).is_file()
        ):
            raise ValueError("Production requires an existing DATABASE_CA_FILE")

    def connection_kwargs(self) -> dict:
        """Override DSN transport/timeouts so a URL cannot weaken production TLS."""
        return {
            "sslmode": "verify-full" if self.environment == "production" else "prefer",
            **({"sslrootcert": self.ca_file} if self.ca_file else {}),
            "connect_timeout": 5,
            "options": "-c statement_timeout=5000 -c lock_timeout=2000",
        }

    @classmethod
    def from_environment(cls, variable="DATABASE_URL"):
        url = os.environ.get(variable)
        if not url:
            raise ValueError(f"Missing required configuration: {variable}")
        return cls(
            url,
            os.environ.get("APP_ENV", "development"),
            os.environ.get("DATABASE_CA_FILE", ""),
        )


@dataclass(frozen=True, repr=False)
class Settings:
    verify_token: str
    app_secret: str
    api_token: str
    phone_id: str
    access_token: str
    environment: str = "development"
    database: DatabaseConfig | None = None

    def __post_init__(self) -> None:
        if self.environment not in ("development", "production"):
            raise ValueError("APP_ENV must be development or production")
        if self.environment == "production" and (
            self.database is None or self.database.environment != "production"
        ):
            raise ValueError("Production requires PostgreSQL with verified TLS")
        for name in ("verify_token", "app_secret", "api_token", "access_token"):
            value = getattr(self, name)
            if len(value.strip()) < 32 or value != value.strip():
                raise ValueError(
                    f"{name} must contain at least 32 characters without surrounding whitespace"
                )
        if not self.phone_id.isascii() or not self.phone_id.isdecimal():
            raise ValueError("phone_id must be a numeric Meta phone-number ID")
        if self.api_token == self.verify_token:
            raise ValueError("API_TOKEN and WHATSAPP_VERIFY_TOKEN must differ")

    @classmethod
    def from_environment(cls) -> "Settings":
        """Fail before serving requests if required configuration is absent."""
        names = (
            "WHATSAPP_VERIFY_TOKEN",
            "WHATSAPP_APP_SECRET",
            "API_TOKEN",
            "WHATSAPP_PHONE_ID",
            "WHATSAPP_ACCESS_TOKEN",
        )
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise ValueError("Missing required configuration: " + ", ".join(missing))
        return cls(
            *(os.environ[name] for name in names),
            environment=os.environ.get("APP_ENV", "development"),
            database=DatabaseConfig.from_environment()
            if os.environ.get("DATABASE_URL")
            else None,
        )
