"""Application configuration."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatabaseConfig:
    """MariaDB connection configuration."""

    host: str = field(default_factory=lambda: os.getenv("ORKP_DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("ORKP_DB_PORT", "3306")))
    user: str = field(default_factory=lambda: os.getenv("ORKP_DB_USER", "orkp"))
    password: str = field(default_factory=lambda: os.getenv("ORKP_DB_PASSWORD", "orkp"))
    database: str = field(default_factory=lambda: os.getenv("ORKP_DB_NAME", "orkp"))

    @property
    def connection_url(self) -> str:
        return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class AppConfig:
    """Top-level application configuration."""

    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    debug: bool = field(default_factory=lambda: os.getenv("ORKP_DEBUG", "false").lower() == "true")
    testing: bool = False


def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    return AppConfig()