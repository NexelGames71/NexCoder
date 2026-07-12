"""AgentMemory — simple persistent key/value memory for agent runs.

Stored per-project under `.nexcoder/agent_memory.json` so the agent can
remember previous decisions, notes, or short-term context between runs.
"""
import json
import os
from typing import Any


class AgentMemory:
    def __init__(self, project_root: str | None = None) -> None:
        self._root = os.path.abspath(project_root) if project_root else None
        self._data: dict[str, Any] = {}
        self._loaded = False

    def _memory_path(self) -> str:
        if not self._root:
            raise ValueError("No project root set for AgentMemory")
        d = os.path.join(self._root, ".nexcoder")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "agent_memory.json")

    def load(self) -> None:
        path = self._memory_path()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                # Corrupt file — start fresh
                self._data = {}
        else:
            self._data = {}
        self._loaded = True

    def save(self) -> None:
        path = self._memory_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        if not self._loaded:
            self.load()
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if not self._loaded:
            self.load()
        self._data[key] = value
        self.save()

    def append(self, key: str, value: Any) -> None:
        if not self._loaded:
            self.load()
        lst = self._data.get(key)
        if not isinstance(lst, list):
            lst = []
        lst.append(value)
        self._data[key] = lst
        self.save()

    def clear(self) -> None:
        self._data = {}
        self.save()
