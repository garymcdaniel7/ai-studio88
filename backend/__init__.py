"""AI Studio backend package.

The repository currently supports two import styles:
- ``backend.main`` for local/deployment entrypoints run from the repo root.
- ``app.*`` for the installable backend package rooted at ``backend/app``.

When ``backend.main`` is imported directly, make ``backend/app`` importable as
``app`` so existing package-internal imports resolve without requiring callers
to set ``PYTHONPATH=backend`` manually.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
_BACKEND_DIR_STR = str(_BACKEND_DIR)

if _BACKEND_DIR_STR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR_STR)
