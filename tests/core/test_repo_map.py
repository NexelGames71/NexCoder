from nexcoder.agent.core.repo_map import (
    build_repo_map, load_repo_map, render_repo_map, save_repo_map,
)


def seed(tmp_path):
    (tmp_path / "app.py").write_text(
        "class Server:\n    def start(self):\n        pass\n\n"
        "def helper():\n    pass\n", encoding="utf-8")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "main.ts").write_text(
        "export function boot() {}\nexport class App {}\nconst x = 1\n",
        encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.py").write_text("def hidden(): pass", encoding="utf-8")


def test_build_extracts_symbols_and_skips_filtered(tmp_path):
    seed(tmp_path)
    repo_map = build_repo_map(tmp_path)
    paths = {f["path"]: f["symbols"] for f in repo_map["files"]}
    assert "app.py" in paths and "web/main.ts" in paths
    assert "node_modules/dep.py" not in paths
    assert "class Server" in paths["app.py"] and "def helper" in paths["app.py"]
    assert "function boot" in paths["web/main.ts"] and "class App" in paths["web/main.ts"]


def test_save_and_load_roundtrip(tmp_path):
    seed(tmp_path)
    repo_map = build_repo_map(tmp_path)
    save_repo_map(tmp_path, repo_map)
    loaded = load_repo_map(tmp_path)
    assert loaded == repo_map
    assert load_repo_map(tmp_path / "nowhere") is None


def test_render_respects_budget(tmp_path):
    seed(tmp_path)
    text = render_repo_map(build_repo_map(tmp_path), token_budget=50)
    assert len(text) <= 50 * 3 + 40  # small tolerance for truncation marker
    assert "app.py" in text
