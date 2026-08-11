"""Fixtures for repository unit tests.

Ensures the app package is importable with the correct path resolution
before any test modules are collected.
"""

from __future__ import annotations

import os
import sys

# Ensure backend directory is at the front of sys.path so that
# `app.*` imports resolve correctly when run alongside other test
# modules that use `backend.app.*` imports.
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_backend_dir = os.path.abspath(_backend_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
