import tempfile
import unittest
from pathlib import Path

from nexcoder.cli import safe_apply_diffs


class CliPatchApplyTests(unittest.TestCase):
    def test_safe_apply_diffs_writes_inside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            applied = safe_apply_diffs(root, [{"file": "src/app.txt", "content": "hello"}])
            self.assertEqual([path.relative_to(root).as_posix() for path in applied], ["src/app.txt"])
            self.assertEqual((root / "src" / "app.txt").read_text(encoding="utf-8"), "hello")

    def test_safe_apply_diffs_blocks_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            outside = root.parent / "outside-nexcoder-cli-test.txt"
            if outside.exists():
                outside.unlink()
            applied = safe_apply_diffs(root, [{"file": "../outside-nexcoder-cli-test.txt", "content": "bad"}])
            self.assertEqual(applied, [])
            self.assertFalse(outside.exists())

    def test_safe_apply_diffs_moves_files_and_removes_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "styles.css").write_text("body {}", encoding="utf-8")
            applied = safe_apply_diffs(root, [
                {"file": "assets/css", "action": "mkdir"},
                {
                    "file": "assets/css/styles.css",
                    "source": "styles.css",
                    "action": "move",
                    "operation": "move",
                    "content": "body {}",
                },
            ])
            self.assertEqual(
                [path.relative_to(root).as_posix() for path in applied],
                ["assets/css/styles.css"],
            )
            self.assertFalse((root / "styles.css").exists())
            self.assertEqual(
                (root / "assets" / "css" / "styles.css").read_text(encoding="utf-8"),
                "body {}",
            )


if __name__ == "__main__":
    unittest.main()
