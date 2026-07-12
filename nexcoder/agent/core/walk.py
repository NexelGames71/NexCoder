"""Bounded project tree walker.

Path.rglob descends into every directory and filters afterwards, which
freezes the app on dataset-heavy projects (a Qt UI shares the GIL with
worker threads). This walker prunes skipped directories *before*
descending and hard-caps the number of entries visited.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from nexcoder.agent.path_filters import should_skip_dir

MAX_WALK_ENTRIES = 50000


def iter_project_files(root: str | Path, *, max_entries: int = MAX_WALK_ENTRIES) -> Iterator[Path]:
    """Yield files under root, pruning skipped dirs, visiting at most max_entries."""
    root = Path(root)
    visited = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames
                       if not should_skip_dir(name, skip_hidden=False)]
        dirnames.sort()
        for name in sorted(filenames):
            visited += 1
            if visited > max_entries:
                return
            yield Path(dirpath) / name
        visited += len(dirnames)
        if visited > max_entries:
            return
