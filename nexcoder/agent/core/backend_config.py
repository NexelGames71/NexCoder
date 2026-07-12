"""The migration seam: one config object describes any OpenAI-compatible backend."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class BackendConfig:
    base_url: str
    model: str
    api_key: str
    adapter: str  # "xml" | "native"
    context_window: int


def load_backend_config() -> BackendConfig:
    return BackendConfig(
        base_url=os.getenv("NEXA_API_URL", "http://127.0.0.1:8001"),
        model=os.getenv("NEXA_MODEL", "default"),
        api_key=os.getenv("NEXA_API_KEY", ""),
        adapter=os.getenv("NEXCODER_ADAPTER", "xml"),
        context_window=max(2048, int(os.getenv("NEXA_CONTEXT_WINDOW", "8192"))),
    )
