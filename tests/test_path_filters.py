import os
import tempfile
import unittest
from pathlib import Path

from nexcoder.agent.codebase_scanner import CodebaseScanner
from nexcoder.agent.hermes_runtime import HermesAgentLoop
from nexcoder.agent.path_filters import should_skip_dir
from nexcoder.agent.tool_registry import ToolRegistry


class PathFilterTests(unittest.TestCase):
    def test_timestamped_build_dirs_are_skipped(self):
        self.assertTrue(should_skip_dir("dist_20260709_095730"))
        self.assertTrue(should_skip_dir("dist-20260709-095730"))
        self.assertTrue(should_skip_dir("build_20260709"))
        self.assertFalse(should_skip_dir("src"))

    def test_scanners_ignore_generated_output_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("print('real')", encoding="utf-8")
            generated = root / "dist_20260709_095730" / "NexCoder" / "_internal"
            generated.mkdir(parents=True)
            (generated / "fake.py").write_text("print('generated')", encoding="utf-8")

            scanner = CodebaseScanner()
            files = scanner._list_project_files(root)
            rel_files = [path.relative_to(root).as_posix() for path in files]

            self.assertIn("src/app.py", rel_files)
            self.assertNotIn("dist_20260709_095730/NexCoder/_internal/fake.py", rel_files)

            loop_files = HermesAgentLoop(root)._safe_list_project_files(root, limit=20)
            self.assertIn(os.path.join("src", "app.py"), loop_files)
            self.assertFalse(any("dist_20260709_095730" in path for path in loop_files))

    def test_tool_search_ignores_generated_output_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "real.py").write_text("needle", encoding="utf-8")
            generated = root / "build_20260709_095730"
            generated.mkdir()
            (generated / "fake.py").write_text("needle", encoding="utf-8")

            result = ToolRegistry(root).search_grep({"query": "needle"})

            self.assertTrue(result["success"])
            self.assertEqual([item["file"] for item in result["results"]], ["src/real.py"])


if __name__ == "__main__":
    unittest.main()
