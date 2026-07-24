from nexcoder.agent.core.walk import iter_project_files


def test_walk_prunes_skipped_dirs_without_descending(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "index.js").write_text("y", encoding="utf-8")
    files = [p.name for p in iter_project_files(tmp_path)]
    assert "app.py" in files
    assert "index.js" not in files


def test_walk_respects_max_entries(tmp_path):
    for i in range(50):
        (tmp_path / f"f{i:03}.txt").write_text("x", encoding="utf-8")
    capped = list(iter_project_files(tmp_path, max_entries=10))
    assert len(capped) == 10
