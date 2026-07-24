import os
import sys
from pathlib import Path

from nexcoder.lsp import manager


def test_frozen_servers_root_uses_pyinstaller_bundle(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    assert manager._servers_root() == (
        tmp_path / "_internal" / "language-servers").resolve()


def test_resolve_server_prefers_bundled_node(monkeypatch, tmp_path: Path):
    servers = tmp_path / "language-servers"
    script = servers / "node_modules" / "pyright" / "langserver.index.js"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    node = servers / ("node.exe" if os.name == "nt" else "node")
    node.write_text("", encoding="utf-8")

    monkeypatch.setattr(manager, "_servers_root", lambda: servers)
    monkeypatch.setattr(manager.shutil, "which", lambda _name: None)

    command = manager.resolve_server_command("python")
    assert command == [str(node), str(script), "--stdio"]


def test_resolve_server_falls_back_to_path_binary(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(manager, "_servers_root", lambda: tmp_path)
    monkeypatch.setattr(
        manager.shutil, "which",
        lambda name: "C:/tools/pyright-langserver.cmd"
        if name == "pyright-langserver" else None,
    )

    assert manager.resolve_server_command("python") == [
        "C:/tools/pyright-langserver.cmd", "--stdio"]
