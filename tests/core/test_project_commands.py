import json

from nexcoder.agent.core.project_commands import (
    detect_project_commands, render_project_commands,
)


def test_empty_project_detects_nothing(tmp_path):
    assert detect_project_commands(tmp_path) == []
    assert render_project_commands([]) == ""


def test_package_json_scripts(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"build": "vite build", "test": "vitest",
                    "obscure": "x"},
    }), encoding="utf-8")
    commands = dict(detect_project_commands(tmp_path))
    assert commands["npm build"] == "npm run build"
    assert commands["npm test"] == "npm run test"
    assert "obscure" not in str(commands)


def test_pyproject_pytest_and_ruff(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n[tool.ruff]\n", encoding="utf-8")
    commands = dict(detect_project_commands(tmp_path))
    assert commands["python tests"] == "python -m pytest tests -q"
    assert "ruff" in commands["lint"]


def test_cargo_and_go(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")
    commands = dict(detect_project_commands(tmp_path))
    assert commands["rust tests"] == "cargo test"
    assert commands["go tests"] == "go test ./..."


def test_makefile_targets(tmp_path):
    (tmp_path / "Makefile").write_text(
        "build:\n\techo b\n\ntest: build\n\techo t\n.PHONY: x\n",
        encoding="utf-8")
    commands = dict(detect_project_commands(tmp_path))
    assert commands["make build"] == "make build"
    assert commands["make test"] == "make test"
    assert "make .PHONY" not in commands


def test_render_mentions_verification():
    out = render_project_commands([("tests", "pytest -q")])
    assert "verify" in out.lower()
    assert "`pytest -q`" in out


def test_user_overrides_come_first(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXCODER_CMD_TEST", "pytest -x tests/unit")
    (tmp_path / "Cargo.toml").write_text("[package]", encoding="utf-8")
    commands = detect_project_commands(tmp_path)
    assert commands[0] == ("test", "pytest -x tests/unit")


def test_broken_package_json_is_ignored(tmp_path):
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    assert detect_project_commands(tmp_path) == []
