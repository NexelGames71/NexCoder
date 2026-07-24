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
    reserve_output: int
    temperature: float
    max_turns_override: int  # 0 = use the mode profile's budget
    disabled_tools: tuple[str, ...]
    memory_enabled: bool


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_backend_config() -> BackendConfig:
    disabled = tuple(
        name.strip() for name in
        os.getenv("NEXCODER_DISABLED_TOOLS", "").split(",") if name.strip())
    return BackendConfig(
        base_url=os.getenv(
            "NEXA_API_URL", "https://integrate.api.nvidia.com/v1"
        ),
        model=os.getenv("NEXA_MODEL", "default"),
        api_key=os.getenv("NEXA_API_KEY", ""),
        adapter=os.getenv("NEXCODER_ADAPTER", "xml"),
        context_window=max(2048, _int_env("NEXA_CONTEXT_WINDOW", 32768)),
        reserve_output=max(1024, _int_env("NEXCODER_RESERVE_OUTPUT", 6144)),
        temperature=min(2.0, max(0.0, _float_env("NEXCODER_TEMPERATURE", 0.2))),
        max_turns_override=max(0, _int_env("NEXCODER_MAX_TURNS", 0)),
        disabled_tools=disabled,
        memory_enabled=os.getenv("NEXCODER_MEMORY", "1") != "0",
    )
