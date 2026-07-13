from nexcoder.agent.core.backend_config import load_backend_config


def test_defaults(monkeypatch):
    for var in ("NEXA_API_URL", "NEXA_MODEL", "NEXA_API_KEY",
                "NEXCODER_ADAPTER", "NEXA_CONTEXT_WINDOW"):
        monkeypatch.delenv(var, raising=False)
    config = load_backend_config()
    assert config.base_url == "http://127.0.0.1:8002"
    assert config.adapter == "xml"
    assert config.context_window == 32768


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("NEXA_API_URL", "http://gpu-server:8000")
    monkeypatch.setenv("NEXCODER_ADAPTER", "native")
    monkeypatch.setenv("NEXA_CONTEXT_WINDOW", "32768")
    config = load_backend_config()
    assert config.base_url == "http://gpu-server:8000"
    assert config.adapter == "native"
    assert config.context_window == 32768
