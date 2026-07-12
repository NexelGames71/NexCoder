import json
import os

from nexcoder.services.checkpoint import CheckpointManager


def test_add_file_snapshots_and_restores(tmp_path):
    (tmp_path / "a.txt").write_text("A1", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B1", encoding="utf-8")
    manager = CheckpointManager(str(tmp_path))
    cp_id = manager.create([str(tmp_path / "a.txt")], label="run")
    manager.add_file(cp_id, str(tmp_path / "b.txt"))
    (tmp_path / "a.txt").write_text("A2", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B2", encoding="utf-8")
    manager.restore(cp_id)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "A1"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "B1"


def test_add_file_missing_file_marks_not_existed_and_restore_deletes(tmp_path):
    (tmp_path / "a.txt").write_text("A1", encoding="utf-8")
    manager = CheckpointManager(str(tmp_path))
    cp_id = manager.create([str(tmp_path / "a.txt")], label="run")
    manager.add_file(cp_id, str(tmp_path / "new.txt"))  # does not exist yet
    (tmp_path / "new.txt").write_text("created later", encoding="utf-8")
    manager.restore(cp_id)
    assert not (tmp_path / "new.txt").exists()


def test_add_file_is_idempotent(tmp_path):
    (tmp_path / "a.txt").write_text("A1", encoding="utf-8")
    manager = CheckpointManager(str(tmp_path))
    cp_id = manager.create([str(tmp_path / "a.txt")], label="run")
    manager.add_file(cp_id, str(tmp_path / "a.txt"))
    cp_dir = os.path.join(str(tmp_path), ".nexcoder", "checkpoints", cp_id)
    with open(os.path.join(cp_dir, "manifest.json")) as fh:
        manifest = json.load(fh)
    assert len(manifest["files"]) == 1
