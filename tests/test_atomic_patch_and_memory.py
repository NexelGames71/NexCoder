import os
import tempfile
from nexcoder.agent.patch_generator import PatchGenerator


def test_apply_patchset():
    with tempfile.TemporaryDirectory() as tmp:
        project_root = tmp
        # create an original file
        file_path = os.path.join(tmp, "foo.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("line1\nline2\nline3\n")

        # create patches: modify foo.txt and add bar.txt
        patches = [
            {
                "file": "foo.txt",
                "action": "modify",
                "diff": "--- a/foo.txt\n+++ b/foo.txt\n@@ -1,3 +1,3 @@\n line1\n-line2\n+LINE2_MODIFIED\n line3\n",
                "language": "diff",
            },
            {
                "file": "bar.txt",
                "action": "create",
                "content": "new file content\n",
                "language": "text",
            },
        ]

        pg = PatchGenerator(project_root)
        pg.apply_patchset(patches)

        # verify modifications
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "LINE2_MODIFIED" in content

        bar_path = os.path.join(tmp, "bar.txt")
        assert os.path.isfile(bar_path)


if __name__ == '__main__':
    test_apply_patchset()
    print('OK')
