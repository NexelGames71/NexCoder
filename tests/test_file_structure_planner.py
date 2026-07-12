import tempfile
import unittest
from pathlib import Path

from nexcoder.agent.file_structure_planner import FileMove, plan_file_moves


class FileStructurePlannerTests(unittest.TestCase):
    def test_extracts_explicit_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            moves = plan_file_moves(
                "Move styles.css to assets/css/styles.css. "
                "Move script.js to assets/js/script.js.",
                tmp,
            )
        self.assertEqual(moves, [
            FileMove("styles.css", "assets/css/styles.css"),
            FileMove("script.js", "assets/js/script.js"),
        ])

    def test_generic_organization_only_moves_conventional_root_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("index.html", "README.md", "styles.css", "script.js", "vite.config.js"):
                (root / name).write_text(name, encoding="utf-8")
            moves = plan_file_moves("Organize the files into their respective folders", root)

        self.assertEqual(moves, [
            FileMove("script.js", "assets/js/script.js"),
            FileMove("styles.css", "assets/css/styles.css"),
        ])

    def test_generic_organization_includes_staged_new_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            moves = plan_file_moves(
                "Structure the files",
                tmp,
                [{"file": "theme.css", "action": "create", "content": "body {}"}],
            )
        self.assertEqual(moves, [FileMove("theme.css", "assets/css/theme.css")])

    def test_put_named_file_into_folder_resolves_unambiguous_disk_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<!doctype html>", encoding="utf-8")
            moves = plan_file_moves("Put the index file into a src folder", root)

        self.assertEqual(moves, [FileMove("index.html", "src/index.html")])

    def test_put_named_file_into_folder_resolves_pending_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            moves = plan_file_moves(
                "put the index file into the src directory",
                tmp,
                [{"file": "index.html", "action": "create", "content": "<!doctype html>"}],
            )

        self.assertEqual(moves, [FileMove("index.html", "src/index.html")])

    def test_natural_reference_is_not_guessed_when_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("html", encoding="utf-8")
            (root / "index.js").write_text("js", encoding="utf-8")
            moves = plan_file_moves("put the index file into a src folder", root)

        self.assertEqual(moves, [])


if __name__ == "__main__":
    unittest.main()
