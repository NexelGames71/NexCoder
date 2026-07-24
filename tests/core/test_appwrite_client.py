import sys
from types import ModuleType

from nexcoder.services.appwrite_client import AppwriteClient


def test_desktop_appwrite_client_never_uses_server_api_key(monkeypatch):
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def set_endpoint(self, value):
            calls.append(("endpoint", value))
            return self

        def set_project(self, value):
            calls.append(("project", value))
            return self

        def set_key(self, value):
            calls.append(("key", value))
            return self

    class FakeService:
        def __init__(self, _client):
            pass

    client_module = ModuleType("appwrite.client")
    client_module.Client = FakeClient
    databases_module = ModuleType("appwrite.services.databases")
    databases_module.Databases = FakeService
    account_module = ModuleType("appwrite.services.account")
    account_module.Account = FakeService
    monkeypatch.setitem(sys.modules, "appwrite.client", client_module)
    monkeypatch.setitem(sys.modules, "appwrite.services.databases", databases_module)
    monkeypatch.setitem(sys.modules, "appwrite.services.account", account_module)
    monkeypatch.setenv("APPWRITE_ENDPOINT", "https://example.invalid/v1")
    monkeypatch.setenv("APPWRITE_PROJECT_ID", "project")
    monkeypatch.setenv("APPWRITE_DATABASE_ID", "database")
    monkeypatch.setenv("APPWRITE_API_KEY", "must-not-be-used")

    client = AppwriteClient()

    assert client.is_available
    assert ("endpoint", "https://example.invalid/v1") in calls
    assert ("project", "project") in calls
    assert not any(name == "key" for name, _ in calls)
