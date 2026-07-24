import unittest

from nexcoder.agent.path_filters import should_skip_dir


class PathFilterTests(unittest.TestCase):
    def test_timestamped_build_dirs_are_skipped(self):
        self.assertTrue(should_skip_dir("dist_20260709_095730"))
        self.assertTrue(should_skip_dir("dist-20260709-095730"))
        self.assertTrue(should_skip_dir("build_20260709"))
        self.assertFalse(should_skip_dir("src"))


if __name__ == "__main__":
    unittest.main()
