"""Cloud test configuration."""
import os
import sys
from pathlib import Path

# Ensure local module imports work in pytest.
_cloud_dir = Path(__file__).resolve().parents[1]
_repo_root = _cloud_dir.parents[1]
_edge_dir = _repo_root / "apps" / "edge"

for path in (_cloud_dir, _edge_dir):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

# Test-safe defaults.
os.environ.setdefault("ADMIN_API_TOKEN", "dev-admin-token")
_test_db_path = _cloud_dir / "test_cloud.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_test_db_path}")


def _reset_test_db_file() -> None:
    if _test_db_path.exists():
        _test_db_path.unlink()


def pytest_sessionstart(session) -> None:
    """Bootstrap schema through Alembic, never through create_all."""
    _reset_test_db_file()
    from migrations import run_migrations

    run_migrations(database_url=os.environ["DATABASE_URL"])


def pytest_sessionfinish(session, exitstatus) -> None:
    _reset_test_db_file()
