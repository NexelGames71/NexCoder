"""LspManager — one lazily-started language server per language family.

Resolution order for server binaries: NexCoder's self-contained
``language-servers/node_modules`` (installed via npm into the repo /
install dir), then PATH. Missing servers degrade gracefully: the
language reports ``unavailable`` and every request returns empty.
"""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from nexcoder.lsp.client import LspClient, LspError

logger = logging.getLogger(__name__)

# Language id (Monaco) -> server family.
LANGUAGE_FAMILIES = {
    "python": "python",
    "typescript": "typescript",
    "javascript": "typescript",
    "typescriptreact": "typescript",
    "javascriptreact": "typescript",
    "html": "html",
    "css": "css",
    "json": "json",
}

# family -> (script relative to language-servers/node_modules, PATH fallback)
_NODE_SERVERS = {
    "python": ("pyright/langserver.index.js", "pyright-langserver"),
    "typescript": ("typescript-language-server/lib/cli.mjs",
                   "typescript-language-server"),
    "html": ("vscode-langservers-extracted/bin/vscode-html-language-server",
             "vscode-html-language-server"),
    "css": ("vscode-langservers-extracted/bin/vscode-css-language-server",
            "vscode-css-language-server"),
    "json": ("vscode-langservers-extracted/bin/vscode-json-language-server",
             "vscode-json-language-server"),
}


def _servers_root() -> Path:
    return Path(__file__).resolve().parents[2] / "language-servers"


def resolve_server_command(family: str) -> list[str] | None:
    """Return the launch command for a server family, or None."""
    entry = _NODE_SERVERS.get(family)
    if entry is None:
        return None
    script_rel, path_fallback = entry
    node = shutil.which("node")
    script = _servers_root() / "node_modules" / script_rel
    if node and script.is_file():
        return [node, str(script), "--stdio"]
    binary = shutil.which(path_fallback)
    if binary:
        return [binary, "--stdio"]
    return None


def apply_text_edits(text: str, edits: list[dict]) -> str:
    """Apply LSP TextEdits (line/character ranges) to a document."""
    lines = text.splitlines(keepends=True)

    def offset(position: dict) -> int:
        line = max(0, int(position.get("line") or 0))
        character = max(0, int(position.get("character") or 0))
        if line >= len(lines):
            return len(text)
        return sum(len(item) for item in lines[:line]) + min(
            character, len(lines[line]))

    ordered = sorted(
        (edit for edit in edits if isinstance(edit, dict)),
        key=lambda e: offset((e.get("range") or {}).get("start") or {}),
        reverse=True)
    for edit in ordered:
        rng = edit.get("range") or {}
        start = offset(rng.get("start") or {})
        end = offset(rng.get("end") or {})
        text = text[:start] + str(edit.get("newText") or "") + text[end:]
        lines = text.splitlines(keepends=True)
    return text


def path_to_uri(path: str | Path) -> str:
    return Path(path).resolve().as_uri()


def uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    return str(Path(url2pathname(unquote(parsed.path))))


class LspManager:
    def __init__(self, on_diagnostics: Callable[[str, list[dict]], None]
                 | None = None) -> None:
        self._on_diagnostics = on_diagnostics
        self._project_root: Path | None = None
        self._clients: dict[str, LspClient] = {}
        self._failed: set[str] = set()
        self._open_docs: dict[str, dict[str, Any]] = {}  # path -> meta
        self._lock = threading.Lock()

    # ── Project lifecycle ────────────────────────────────────────────

    def set_project(self, root: str | Path) -> None:
        root = Path(root)
        if self._project_root == root:
            return
        self.shutdown()
        self._project_root = root

    def shutdown(self) -> None:
        with self._lock:
            clients, self._clients = self._clients, {}
            self._failed.clear()
            self._open_docs.clear()
        for client in clients.values():
            try:
                client.shutdown()
            except Exception:
                pass

    def status(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for family in _NODE_SERVERS:
            if family in self._clients and self._clients[family].alive():
                out[family] = "running"
            elif family in self._failed:
                out[family] = "failed"
            elif resolve_server_command(family) is None:
                out[family] = "not_installed"
            else:
                out[family] = "available"
        return out

    # ── Server acquisition ───────────────────────────────────────────

    def _client_for(self, language: str) -> LspClient | None:
        family = LANGUAGE_FAMILIES.get(language)
        if family is None or self._project_root is None:
            return None
        with self._lock:
            client = self._clients.get(family)
            if client is not None and client.alive():
                return client
            if family in self._failed:
                return None
        command = resolve_server_command(family)
        if command is None:
            return None
        init_options: dict[str, Any] = {}
        if family == "typescript":
            tsdk = _servers_root() / "node_modules" / "typescript" / "lib"
            if tsdk.is_dir():
                init_options = {"tsserver": {"path": str(tsdk)}}
        client = LspClient(command, self._project_root,
                           on_notification=self._handle_notification,
                           initialization_options=init_options)
        try:
            client.start()
        except Exception:
            logger.warning("Language server failed to start: %s", family,
                           exc_info=True)
            with self._lock:
                self._failed.add(family)
            return None
        with self._lock:
            self._clients[family] = client
        # Replay documents already open for this family so a lazily
        # started server has full context.
        for path, meta in list(self._open_docs.items()):
            if LANGUAGE_FAMILIES.get(meta["language"]) == family:
                client.notify("textDocument/didOpen", {"textDocument": {
                    "uri": path_to_uri(path), "languageId": meta["language"],
                    "version": meta["version"], "text": meta["text"]}})
        return client

    def _handle_notification(self, method: str, params: dict) -> None:
        if method == "textDocument/publishDiagnostics":
            uri = str(params.get("uri") or "")
            if not uri:
                return
            diagnostics = params.get("diagnostics") or []
            if self._on_diagnostics is not None:
                self._on_diagnostics(uri_to_path(uri), diagnostics)

    # ── Document sync ────────────────────────────────────────────────

    def did_open(self, path: str, language: str, text: str) -> None:
        family = LANGUAGE_FAMILIES.get(language)
        with self._lock:
            was_running = (family in self._clients
                           and self._clients[family].alive())
        self._open_docs[path] = {"language": language, "text": text,
                                 "version": 1}
        client = self._client_for(language)
        if client is None:
            return
        # A freshly started server already replayed every open doc
        # (including this one); only notify servers that were running.
        if was_running:
            client.notify("textDocument/didOpen", {"textDocument": {
                "uri": path_to_uri(path), "languageId": language,
                "version": 1, "text": text}})

    def did_change(self, path: str, text: str) -> None:
        meta = self._open_docs.get(path)
        if meta is None:
            return
        meta["version"] += 1
        meta["text"] = text
        client = self._client_for(meta["language"])
        if client is None:
            return
        client.notify("textDocument/didChange", {
            "textDocument": {"uri": path_to_uri(path),
                             "version": meta["version"]},
            "contentChanges": [{"text": text}]})

    def did_close(self, path: str) -> None:
        meta = self._open_docs.pop(path, None)
        if meta is None:
            return
        client = self._client_for(meta["language"])
        if client is not None:
            client.notify("textDocument/didClose", {"textDocument": {
                "uri": path_to_uri(path)}})

    # ── Requests ─────────────────────────────────────────────────────

    def _doc_position(self, path: str, line: int, character: int) -> dict:
        return {"textDocument": {"uri": path_to_uri(path)},
                "position": {"line": line, "character": character}}

    def _request(self, path: str, method: str, params: dict) -> Any:
        meta = self._open_docs.get(path)
        if meta is None:
            return None
        client = self._client_for(meta["language"])
        if client is None:
            return None
        try:
            return client.request(method, params)
        except LspError as exc:
            logger.debug("LSP request failed (%s): %s", method, exc)
            return None

    def completion(self, path: str, line: int, character: int) -> list[dict]:
        result = self._request(path, "textDocument/completion",
                               self._doc_position(path, line, character))
        if result is None:
            return []
        items = result.get("items") if isinstance(result, dict) else result
        out = []
        for item in (items or [])[:100]:
            out.append({
                "label": str(item.get("label") or ""),
                "kind": int(item.get("kind") or 1),
                "detail": str(item.get("detail") or ""),
                "insertText": str(item.get("insertText")
                                  or item.get("label") or ""),
                "sortText": str(item.get("sortText") or ""),
            })
        return out

    def hover(self, path: str, line: int, character: int) -> str:
        result = self._request(path, "textDocument/hover",
                               self._doc_position(path, line, character))
        if not result:
            return ""
        contents = result.get("contents")
        if isinstance(contents, dict):
            return str(contents.get("value") or "")
        if isinstance(contents, list):
            parts = []
            for part in contents:
                parts.append(str(part.get("value")) if isinstance(part, dict)
                             else str(part))
            return "\n\n".join(p for p in parts if p)
        return str(contents or "")

    def _locations(self, result: Any) -> list[dict]:
        if result is None:
            return []
        if isinstance(result, dict):
            result = [result]
        out = []
        for loc in result[:200]:
            uri = loc.get("uri") or loc.get("targetUri")
            rng = loc.get("range") or loc.get("targetSelectionRange") or {}
            if not uri:
                continue
            out.append({"path": uri_to_path(str(uri)), "range": rng})
        return out

    def definition(self, path: str, line: int, character: int) -> list[dict]:
        return self._locations(self._request(
            path, "textDocument/definition",
            self._doc_position(path, line, character)))

    def references(self, path: str, line: int, character: int) -> list[dict]:
        params = self._doc_position(path, line, character)
        params["context"] = {"includeDeclaration": True}
        return self._locations(self._request(
            path, "textDocument/references", params))

    def rename(self, path: str, line: int, character: int,
               new_name: str) -> dict[str, list[dict]]:
        params = self._doc_position(path, line, character)
        params["newName"] = new_name
        result = self._request(path, "textDocument/rename", params)
        if not result:
            return {}
        edits_by_path: dict[str, list[dict]] = {}
        for uri, edits in (result.get("changes") or {}).items():
            edits_by_path[uri_to_path(uri)] = list(edits or [])
        for change in (result.get("documentChanges") or []):
            doc = (change or {}).get("textDocument") or {}
            uri = doc.get("uri")
            if uri:
                edits_by_path.setdefault(uri_to_path(str(uri)), []).extend(
                    change.get("edits") or [])
        return edits_by_path
