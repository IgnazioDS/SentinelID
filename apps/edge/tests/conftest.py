"""
Edge test configuration.

Provides shared fixtures and ensures the sentinelid_edge package is
importable from the tests directory without installation.
"""
import os
import sys

# Ensure sentinelid_edge is importable
_edge_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _edge_src not in sys.path:
    sys.path.insert(0, _edge_src)
