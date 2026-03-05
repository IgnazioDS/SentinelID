"""
Edge test configuration.

Provides shared fixtures and ensures the sentinelid_edge package is
importable from the tests directory without installation.
"""
import os
import sys

import pytest

# Ensure sentinelid_edge is importable
_edge_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _edge_src not in sys.path:
    sys.path.insert(0, _edge_src)


@pytest.fixture(autouse=True)
def reset_module_singletons(tmp_path):
    """
    Reset module-level singletons before every test so that each test
    gets a clean slate regardless of execution order.

    This prevents singleton state (DB connection, encryption key cache)
    from leaking between tests that use different temporary paths.
    """
    import sentinelid_edge.services.security.encryption as enc
    import sentinelid_edge.services.security.rate_limit as rate_limit_mod
    import sentinelid_edge.services.storage.db as db_mod
    from sentinelid_edge.core.config import settings

    old_enc = enc._provider
    old_db = db_mod._db_instance
    old_rate_limiter = rate_limit_mod._rate_limiter
    old_lockout_state_path = settings.LOCKOUT_STATE_PATH
    enc._provider = None
    db_mod._db_instance = None
    rate_limit_mod._rate_limiter = None
    settings.LOCKOUT_STATE_PATH = str(tmp_path / "lockout_state.json")

    yield

    # Restore original state (usually None at test start)
    enc._provider = old_enc
    db_mod._db_instance = old_db
    rate_limit_mod._rate_limiter = old_rate_limiter
    settings.LOCKOUT_STATE_PATH = old_lockout_state_path
