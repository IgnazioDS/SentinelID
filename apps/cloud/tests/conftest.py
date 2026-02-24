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
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_cloud_dir / 'test_cloud.db'}")
