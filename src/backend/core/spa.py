"""Safe file lookup for the admin SPA fallback route.

The route ``/{full_path:path}`` is reachable without logging in, so the request path is
untrusted: it must never resolve to a file outside the SPA folder (``..`` segments, encoded
``%2e%2e%2f``, absolute paths, symlinks). Before this check the route served any file in the
container, including ``/app/data/.jwt_secret``.
"""

from __future__ import annotations

from pathlib import Path


def resolve_spa_file(root: Path, full_path: str) -> Path | None:
    """The file under ``root`` that ``full_path`` names, or None."""
    root = root.resolve()
    candidate = (root / full_path).resolve()
    return candidate if candidate.is_file() and candidate.is_relative_to(root) else None
