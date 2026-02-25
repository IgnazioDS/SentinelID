"""Tests for cloud migration bootstrapping and startup behavior."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from migrations import run_migrations


def test_startup_does_not_use_create_all(monkeypatch) -> None:
    from models import Base

    def _raise_if_called(*args, **kwargs):
        raise AssertionError("Base.metadata.create_all must not be called at startup")

    monkeypatch.setattr(Base.metadata, "create_all", _raise_if_called)

    from main import app

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_run_migrations_bootstraps_fresh_sqlite_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh_cloud.db"
    database_url = f"sqlite:///{db_path}"

    run_migrations(database_url=database_url)
    # Idempotency: applying head again should succeed.
    run_migrations(database_url=database_url)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    assert "alembic_version" in tables
    assert "devices" in tables
    assert "telemetry_events" in tables
