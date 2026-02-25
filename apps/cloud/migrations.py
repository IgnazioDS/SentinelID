"""Alembic migration helpers for cloud service startup and tests."""
from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config


_CLOUD_DIR = Path(__file__).resolve().parent


def build_alembic_config(database_url: str | None = None) -> Config:
    """Build an Alembic config pointing at cloud migration scripts."""
    config = Config(str(_CLOUD_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_CLOUD_DIR / "alembic"))

    resolved_url = database_url or os.environ.get("DATABASE_URL")
    if resolved_url:
        config.set_main_option("sqlalchemy.url", resolved_url)

    return config


def run_migrations(database_url: str | None = None) -> None:
    """Apply all pending migrations and fail fast on migration errors."""
    command.upgrade(build_alembic_config(database_url=database_url), "head")
