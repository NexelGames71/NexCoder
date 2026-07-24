import sys
import threading
import time
from pathlib import Path

import pytest

from nexcoder.lsp.client import LspClient, LspError

FAKE_SERVER = Path(__file__).parent / "fake_server.py"


def make_client(tmp_path, notifications=None):
    client = LspClient(
        [sys.executable, str(FAKE_SERVER)], tmp_path,
        on_notification=(lambda method, params:
                         notifications.append((method, params)))
        if notifications is not None else None)
    client.start()
    return client


def test_initialize_handshake_and_request_roundtrip(tmp_path):
    client = make_client(tmp_path)
    try:
        assert client.initialized
        result = client.request("test/echo", {"value": 42}, timeout=5.0)
        assert result == {"value": 42}
    finally:
        client.shutdown()


def test_server_error_raises(tmp_path):
    client = make_client(tmp_path)
    try:
        with pytest.raises(LspError, match="deliberate failure"):
            client.request("test/error", {}, timeout=5.0)
    finally:
        client.shutdown()


def test_notifications_are_delivered(tmp_path):
    notifications = []
    client = make_client(tmp_path, notifications)
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if any(m == "textDocument/publishDiagnostics"
                   for m, _ in notifications):
                break
            time.sleep(0.05)
        methods = [m for m, _ in notifications]
        assert "textDocument/publishDiagnostics" in methods
    finally:
        client.shutdown()


def test_concurrent_requests_correlate_by_id(tmp_path):
    client = make_client(tmp_path)
    results = {}

    def call(n):
        results[n] = client.request("test/echo", {"n": n}, timeout=5.0)

    try:
        threads = [threading.Thread(target=call, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert results == {i: {"n": i} for i in range(5)}
    finally:
        client.shutdown()
