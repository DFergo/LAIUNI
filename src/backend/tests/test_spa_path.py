"""The admin SPA fallback is reachable without logging in: it must never serve files outside
the SPA folder (it once served /app/data/.jwt_secret)."""

import tempfile
import unittest
from pathlib import Path

from src.core.spa import resolve_spa_file


class SpaPathTraversalTest(unittest.TestCase):
    def test_only_files_inside_the_root(self):
        base = Path(tempfile.mkdtemp())
        root = base / "dist"
        (root / "assets").mkdir(parents=True)
        (root / "index.html").write_text("<html>")
        (root / "assets" / "app.js").write_text("js")
        (base / "secret.txt").write_text("top secret")
        (base / "dist-evil").mkdir()
        (base / "dist-evil" / "x.txt").write_text("sibling with the same prefix")
        (root / "link").symlink_to(base / "secret.txt")

        self.assertEqual(resolve_spa_file(root, "index.html"), (root / "index.html").resolve())
        self.assertEqual(resolve_spa_file(root, "assets/app.js"), (root / "assets" / "app.js").resolve())
        for attack in ("../secret.txt", "assets/../../secret.txt", "../dist-evil/x.txt",
                       str(base / "secret.txt"), "link", "../../../../etc/passwd"):
            self.assertIsNone(resolve_spa_file(root, attack), attack)
        self.assertIsNone(resolve_spa_file(root, "nope.html"))
        self.assertIsNone(resolve_spa_file(root, "assets"))  # a directory is not a file


if __name__ == "__main__":
    unittest.main()
