import tempfile
import unittest
from pathlib import Path

from nexcoder.agent.codebase_scanner import CodebaseScanner


class CodebaseScannerTests(unittest.TestCase):
    def test_static_site_is_detected_from_source_files_without_package_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets" / "css").mkdir(parents=True)
            (root / "index.html").write_text(
                '<!doctype html><link rel="stylesheet" href="assets/css/styles.css">',
                encoding="utf-8",
            )
            (root / "assets" / "css" / "styles.css").write_text(
                "body { color: white; }",
                encoding="utf-8",
            )
            (root / "script.js").write_text("console.log('ready');", encoding="utf-8")
            (root / "README.md").write_text("# Product\n\nA static product page.", encoding="utf-8")

            result = CodebaseScanner().run(tmp)

        project_map = result["project_map"]
        detected = project_map["detected"]
        self.assertEqual(detected["language"], "HTML/CSS/JavaScript")
        self.assertEqual(detected["framework"], "Static site")
        self.assertEqual(detected["source_directory"], ".")
        self.assertIn("index.html", detected["entry_points"])
        self.assertNotIn("documentation files only", " ".join(project_map["warnings"]))
        self.assertIn("index.html", project_map["important_files"])
        self.assertIn("script.js", project_map["important_files"])
        self.assertIn("assets/css/styles.css", project_map["important_files"])

    def test_documentation_only_warning_still_applies_to_markdown_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "README.md").write_text("# Notes", encoding="utf-8")

            result = CodebaseScanner().run(tmp)

        self.assertIn(
            "documentation files only",
            " ".join(result["project_map"]["warnings"]),
        )


if __name__ == "__main__":
    unittest.main()
