"""FileIndex — SQLite-based file indexing with full-text search."""

import os
import sqlite3
import hashlib
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class FileIndex:
    """SQLite-based file index with FTS5 full-text search."""

    def __init__(self, project_root: str) -> None:
        self._root = os.path.abspath(project_root)
        db_dir = os.path.join(self._root, ".nexcoder")
        os.makedirs(db_dir, exist_ok=True)

        self._db_path = os.path.join(db_dir, "index.db")
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database and tables."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    extension TEXT,
                    size INTEGER,
                    modified REAL,
                    content_hash TEXT
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
                    path, name, content,
                    content_rowid='rowid'
                );

                CREATE TABLE IF NOT EXISTS file_contents (
                    path TEXT PRIMARY KEY,
                    content TEXT,
                    FOREIGN KEY (path) REFERENCES files(path) ON DELETE CASCADE
                );
            """)

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-safe connection."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def index_file(self, file_path: str) -> None:
        """Index a single file."""
        abs_path = os.path.abspath(file_path)
        if not os.path.isfile(abs_path):
            return

        try:
            stat = os.stat(abs_path)
            name = os.path.basename(abs_path)
            ext = os.path.splitext(name)[1].lower()

            # Skip large files and binary files
            if stat.st_size > 1_000_000:  # 1MB
                return

            binary_exts = {
                ".png", ".jpg", ".gif", ".ico", ".exe", ".dll",
                ".zip", ".tar", ".gz", ".pdf", ".pyc", ".wasm",
                ".ttf", ".woff", ".woff2", ".mp3", ".mp4",
            }
            if ext in binary_exts:
                return

            # Read content
            content = ""
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                return

            content_hash = hashlib.md5(content.encode()).hexdigest()

            with self._lock:
                with self._get_conn() as conn:
                    # Check if file has changed
                    existing = conn.execute(
                        "SELECT content_hash FROM files WHERE path = ?", (abs_path,)
                    ).fetchone()

                    if existing and existing[0] == content_hash:
                        return  # No change

                    # Upsert file metadata
                    conn.execute("""
                        INSERT OR REPLACE INTO files (path, name, extension, size, modified, content_hash)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (abs_path, name, ext, stat.st_size, stat.st_mtime, content_hash))

                    # Upsert content
                    conn.execute("""
                        INSERT OR REPLACE INTO file_contents (path, content)
                        VALUES (?, ?)
                    """, (abs_path, content[:50000]))  # Cap at 50K chars

                    # Update FTS
                    conn.execute("DELETE FROM files_fts WHERE path = ?", (abs_path,))
                    conn.execute("""
                        INSERT INTO files_fts (path, name, content)
                        VALUES (?, ?, ?)
                    """, (abs_path, name, content[:10000]))

        except Exception as e:
            logger.debug(f"Error indexing file {file_path}: {e}")

    def index_directory(self, root: str | None = None) -> int:
        """Index all files in a directory. Returns count of indexed files."""
        target = root or self._root
        count = 0

        skip_dirs = {
            "node_modules", ".git", "__pycache__", "venv", ".venv",
            "dist", "build", ".nexcoder", ".next", "target",
        }

        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]

            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                self.index_file(filepath)
                count += 1

        logger.info(f"Indexed {count} files in {target}")
        return count

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Full-text search across indexed files."""
        results: list[dict[str, Any]] = []

        with self._lock:
            with self._get_conn() as conn:
                try:
                    cursor = conn.execute("""
                        SELECT path, name, snippet(files_fts, 2, '>>>', '<<<', '...', 40) as snippet,
                               rank
                        FROM files_fts
                        WHERE files_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    """, (query, limit))

                    for row in cursor:
                        results.append({
                            "path": row[0],
                            "name": row[1],
                            "snippet": row[2],
                            "score": row[3],
                        })
                except sqlite3.OperationalError as e:
                    logger.debug(f"FTS search error: {e}")
                    # Fallback to LIKE search
                    cursor = conn.execute("""
                        SELECT path, name FROM files
                        WHERE name LIKE ? OR path LIKE ?
                        LIMIT ?
                    """, (f"%{query}%", f"%{query}%", limit))

                    for row in cursor:
                        results.append({"path": row[0], "name": row[1]})

        return results

    def remove_file(self, file_path: str) -> None:
        """Remove a file from the index."""
        abs_path = os.path.abspath(file_path)
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM files WHERE path = ?", (abs_path,))
                conn.execute("DELETE FROM file_contents WHERE path = ?", (abs_path,))
                conn.execute("DELETE FROM files_fts WHERE path = ?", (abs_path,))

    def clear(self) -> None:
        """Clear the entire index."""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM files")
                conn.execute("DELETE FROM file_contents")
                conn.execute("DELETE FROM files_fts")
