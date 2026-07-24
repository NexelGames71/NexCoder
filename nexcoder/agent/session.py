"""AgentSession — persistent per-project conversation history.

The agent runtime used to keep ``_conversation_history`` in memory; closing
the app lost every prior conversation. This module gives the runtime a
real on-disk store so users can:

- Resume a session after restarting NexCoder
- Switch between concurrent sessions
- Inspect and share past runs

Storage layout (per project)::

    {project_root}/.nexcoder/sessions/
        index.json                          # summary of all sessions
        {session_id}/
            session.json                    # metadata (title, mode, dates)
            messages.jsonl                  # one JSON object per line

JSONL is the on-disk format for messages because:

- Append-only writes are O(1) and safe under partial-failure crashes.
- Line-delimited JSON is trivial to inspect with shell tools
  (``Get-Content -Tail 5``, ``jq -c``, etc.).
- Resumability only needs the last few messages; the file can be
  truncated without rewriting.

The index file is rewritten on every session create/close. It is small
(``O(sessions)``) so the cost is negligible.

This module is intentionally side-effect-free at import time. Callers
instantiate :class:`AgentSessionStore` once per project and reuse it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Optional

logger = logging.getLogger(__name__)


# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class SessionMessage:
    """A single message in a session.

    The shape mirrors what the runtime already appends to
    ``_conversation_history`` (``role`` + ``content``) plus optional
    structured metadata for assistant turns that produced a
    ``final_answer`` card, a diff, or a tool timeline.
    """

    role: str
    content: str
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMessage":
        return cls(
            role=str(data.get("role", "")),
            content=str(data.get("content", "")),
            created_at=str(data.get("created_at", "")),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class SessionMetadata:
    """Top-level session info shown in the UI history sidebar."""

    session_id: str
    title: str
    mode: str
    project_path: str
    created_at: str
    updated_at: str
    message_count: int
    status: str = "active"  # "active" | "complete" | "cancelled" | "error"
    tags: list[str] = field(default_factory=list)
    archived: bool = False
    plan_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMetadata":
        return cls(
            session_id=str(data.get("session_id", "")),
            title=str(data.get("title", "Untitled")),
            mode=str(data.get("mode", "ask")),
            project_path=str(data.get("project_path", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            message_count=int(data.get("message_count", 0)),
            status=str(data.get("status", "active")),
            tags=list(data.get("tags") or []),
            archived=bool(data.get("archived", False)),
            plan_id=str(data.get("plan_id", "")),
        )


# ── Store ────────────────────────────────────────────────────────────


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AgentSessionStore:
    """Disk-backed session store for one project.

    All public methods are thread-safe — the runtime may be appending
    to a session from a background thread while the UI reads the index
    from the main thread.
    """

    SESSIONS_DIRNAME = "sessions"
    INDEX_FILENAME = "index.json"

    def __init__(self, project_root: str) -> None:
        self._root = os.path.abspath(project_root)
        self._lock = threading.RLock()
        self._sessions_dir = os.path.join(
            self._root, ".nexcoder", self.SESSIONS_DIRNAME
        )
        os.makedirs(self._sessions_dir, exist_ok=True)

    # ── Paths ────────────────────────────────────────────────────────

    def _session_dir(self, session_id: str) -> str:
        if not _SAFE_ID.match(session_id):
            raise ValueError(f"Invalid session id: {session_id!r}")
        return os.path.join(self._sessions_dir, session_id)

    def _meta_path(self, session_id: str) -> str:
        return os.path.join(self._session_dir(session_id), "session.json")

    def _messages_path(self, session_id: str) -> str:
        return os.path.join(self._session_dir(session_id), "messages.jsonl")

    def _index_path(self) -> str:
        return os.path.join(self._sessions_dir, self.INDEX_FILENAME)

    # ── Sessions ─────────────────────────────────────────────────────

    def create_session(
        self,
        *,
        title: str = "New session",
        mode: str = "ask",
        session_id: Optional[str] = None,
    ) -> SessionMetadata:
        """Create a new session. Returns its metadata."""
        with self._lock:
            sid = session_id or self._new_session_id()
            if not _SAFE_ID.match(sid):
                raise ValueError(f"Invalid session id: {sid!r}")
            session_dir = self._session_dir(sid)
            if os.path.exists(session_dir):
                raise FileExistsError(f"Session already exists: {sid}")
            os.makedirs(session_dir, exist_ok=True)
            now = _utcnow()
            meta = SessionMetadata(
                session_id=sid,
                title=title,
                mode=mode,
                project_path=self._root,
                created_at=now,
                updated_at=now,
                message_count=0,
                status="active",
            )
            self._write_meta(meta)
            # Empty messages file (touch)
            open(self._messages_path(sid), "ab").close()
            self._update_index(meta, add=True)
            return meta

    def load_session(self, session_id: str) -> tuple[SessionMetadata, list[SessionMessage]]:
        """Return (metadata, messages) for *session_id*.

        Raises ``FileNotFoundError`` if the session does not exist,
        ``ValueError`` if the metadata is corrupt (caller decides how
        to recover — usually by treating it as a deleted session).
        """
        with self._lock:
            meta = self._read_meta(session_id)
            messages = list(self._iter_messages(session_id))
            return meta, messages

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and remove it from the index. Returns
        ``True`` if the session existed and was removed.
        """
        import shutil

        with self._lock:
            session_dir = self._session_dir(session_id)
            if not os.path.isdir(session_dir):
                return False
            shutil.rmtree(session_dir, ignore_errors=True)
            self._update_index_remove(session_id)
            return True

    def archive_session(self, session_id: str, archived: bool = True) -> SessionMetadata:
        """Mark a session archived/unarchived without deleting it."""
        with self._lock:
            meta = self._read_meta(session_id)
            meta.archived = bool(archived)
            meta.updated_at = _utcnow()
            self._write_meta(meta)
            self._update_index(meta, add=False)
            return meta

    def list_sessions(self) -> list[SessionMetadata]:
        """Return all sessions for the project, newest-first."""
        with self._lock:
            return self._read_index()

    # ── Messages ─────────────────────────────────────────────────────

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SessionMessage:
        """Append a message to the session and update the index.

        The append is atomic for the message file (write to a temp
        file, then rename is overkill for JSONL since each line is
        self-contained; we use ``append + flush`` instead, which is
        safe because JSONL is line-oriented and each line is its own
        record).
        """
        with self._lock:
            meta = self._read_meta(session_id)
            msg = SessionMessage(
                role=role,
                content=content,
                created_at=_utcnow(),
                metadata=dict(metadata or {}),
            )
            line = json.dumps(msg.to_dict(), ensure_ascii=False)
            # Append with newline; newline-delimited JSON.
            with open(self._messages_path(session_id), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass  # not all filesystems support fsync
            meta.message_count += 1
            meta.updated_at = msg.created_at
            # Update the title to the first user prompt, but only if
            # the session is still using the default title.
            if meta.title == "New session" and role == "user" and content:
                meta.title = _truncate_title(content)
            self._write_meta(meta)
            self._update_index(meta, add=False)
            return msg

    def append_messages(
        self,
        session_id: str,
        messages: Iterable[tuple[str, str]],
    ) -> int:
        """Bulk-append ``(role, content)`` tuples. Returns count added."""
        added = 0
        for role, content in messages:
            self.append_message(session_id, role, content)
            added += 1
        return added

    def iter_messages(self, session_id: str) -> Iterator[SessionMessage]:
        """Stream messages one at a time. Useful for large sessions."""
        return self._iter_messages(session_id)

    def truncate_messages(
        self,
        session_id: str,
        keep_count: int,
    ) -> list[SessionMessage]:
        """Atomically keep only the first *keep_count* messages.

        Prompt edit/resend uses this after file checkpoints have been restored.
        Rewriting the short JSONL file avoids leaving the abandoned branch in
        future model context while preserving every turn before the target.
        """
        with self._lock:
            meta = self._read_meta(session_id)
            messages = list(self._iter_messages(session_id))
            if keep_count < 0 or keep_count > len(messages):
                raise ValueError(
                    f"Invalid message boundary {keep_count}; "
                    f"session contains {len(messages)} messages")
            retained = messages[:keep_count]
            destination = self._messages_path(session_id)
            fd, temporary = tempfile.mkstemp(
                prefix="messages-", suffix=".jsonl.tmp",
                dir=self._session_dir(session_id))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    for message in retained:
                        fh.write(json.dumps(
                            message.to_dict(), ensure_ascii=False) + "\n")
                    fh.flush()
                    try:
                        os.fsync(fh.fileno())
                    except OSError:
                        pass
                os.replace(temporary, destination)
            except Exception:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                raise

            meta.message_count = len(retained)
            meta.updated_at = retained[-1].created_at if retained else _utcnow()
            meta.status = "active"
            if not retained:
                # Allows the replacement first prompt to become the title.
                meta.title = "New session"
            self._write_meta(meta)
            self._update_index(meta, add=False)
            return retained

    # ── Status ───────────────────────────────────────────────────────

    def set_status(self, session_id: str, status: str) -> None:
        """Update the session status (active / complete / cancelled / error)."""
        if status not in {"active", "complete", "cancelled", "error"}:
            raise ValueError(f"Invalid status: {status!r}")
        with self._lock:
            meta = self._read_meta(session_id)
            meta.status = status
            meta.updated_at = _utcnow()
            self._write_meta(meta)
            self._update_index(meta, add=False)

    def set_plan(self, session_id: str, plan_id: str) -> None:
        """Associate the conversation with its active implementation plan."""
        with self._lock:
            meta = self._read_meta(session_id)
            meta.plan_id = str(plan_id or "")
            meta.updated_at = _utcnow()
            self._write_meta(meta)
            self._update_index(meta, add=False)

    # ── Helpers ──────────────────────────────────────────────────────

    def _new_session_id(self) -> str:
        # 12-char URL-safe id with a millisecond prefix so the sort
        # order in the index matches the creation order.
        return f"{int(time.time() * 1000):x}-{uuid.uuid4().hex[:6]}"

    def _write_meta(self, meta: SessionMetadata) -> None:
        path = self._meta_path(meta.session_id)
        _atomic_write_json(path, meta.to_dict())

    def _read_meta(self, session_id: str) -> SessionMetadata:
        path = self._meta_path(session_id)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Session not found: {session_id}")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return SessionMetadata.from_dict(json.load(fh))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt session metadata: {session_id}") from exc

    def _iter_messages(self, session_id: str) -> Iterator[SessionMessage]:
        path = self._messages_path(session_id)
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    yield SessionMessage.from_dict(json.loads(line))
                except json.JSONDecodeError:
                    # Skip corrupt lines — the rest of the session is
                    # still usable. We log so the user can see the
                    # damage in the IDE log.
                    logger.warning(
                        "Skipping corrupt message line in session %s", session_id
                    )

    def _read_index(self) -> list[SessionMetadata]:
        path = self._index_path()
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(raw, list):
            return []
        out: list[SessionMetadata] = []
        for entry in raw:
            if isinstance(entry, dict):
                out.append(SessionMetadata.from_dict(entry))
        out.sort(key=lambda m: m.updated_at, reverse=True)
        return out

    def _update_index(self, meta: SessionMetadata, *, add: bool) -> None:
        sessions = self._read_index()
        if add:
            sessions.insert(0, meta)
        else:
            for i, existing in enumerate(sessions):
                if existing.session_id == meta.session_id:
                    sessions[i] = meta
                    break
            else:
                sessions.insert(0, meta)
        sessions.sort(key=lambda m: m.updated_at, reverse=True)
        _atomic_write_json(
            self._index_path(),
            [m.to_dict() for m in sessions],
        )

    def _update_index_remove(self, session_id: str) -> None:
        sessions = [m for m in self._read_index() if m.session_id != session_id]
        _atomic_write_json(
            self._index_path(),
            [m.to_dict() for m in sessions],
        )


# ── Free helpers ─────────────────────────────────────────────────────


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_title(text: str, limit: int = 64) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _atomic_write_json(path: str, payload: Any) -> None:
    """Write JSON to *path* atomically (write to temp + rename).

    On Windows, ``os.replace`` is atomic when the destination already
    exists. The temp file lives in the same directory as the target
    so the rename is on the same volume.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        # Best-effort cleanup; never leave the temp file dangling.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


__all__ = [
    "AgentSessionStore",
    "SessionMessage",
    "SessionMetadata",
]
