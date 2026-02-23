"""
Cloud test configuration.

Stubs out database dependencies so Pydantic model tests run without PostgreSQL.
This conftest must run before any test module imports cloud package modules.
"""
import os
import sys
import types

# Add the cloud directory to sys.path so imports like `from api.ingest_router`
# resolve to apps/cloud/api/ingest_router.py
_cloud_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _cloud_dir not in sys.path:
    sys.path.insert(0, _cloud_dir)

# Stub psycopg2 before any SQLAlchemy code runs
if "psycopg2" not in sys.modules:
    _psycopg2 = types.ModuleType("psycopg2")
    sys.modules["psycopg2"] = _psycopg2
    sys.modules["psycopg2.extras"] = types.ModuleType("psycopg2.extras")
    sys.modules["psycopg2.extensions"] = types.ModuleType("psycopg2.extensions")

# Stub 'models' so ingest_router.py can be imported without a real DB
if "models" not in sys.modules:
    _models = types.ModuleType("models")

    class _FakeBase:
        pass

    def _fake_get_db():
        class _FakeSession:
            pass
        yield _FakeSession()

    _models.get_db = _fake_get_db
    _models.Device = type("Device", (), {})
    _models.TelemetryEvent = type("TelemetryEvent", (), {})
    _models.init_db = lambda: None
    sys.modules["models"] = _models

# Stub signature_verifier so ingest_router import succeeds
_api_pkg = types.ModuleType("api")
_api_pkg.__path__ = [os.path.join(_cloud_dir, "api")]
_api_pkg.__package__ = "api"
sys.modules.setdefault("api", _api_pkg)

_sv = types.ModuleType("api.signature_verifier")


class _SigVerifier:
    @staticmethod
    def verify_batch(*a, **kw):
        return True

    @staticmethod
    def verify_event(*a, **kw):
        return True


_sv.SignatureVerifier = _SigVerifier
sys.modules.setdefault("api.signature_verifier", _sv)
