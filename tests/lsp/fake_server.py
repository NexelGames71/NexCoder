"""A minimal fake LSP server for protocol tests (stdio, one session)."""
import json
import sys


def read_message(stream):
    length = 0
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":")[1])
    body = stream.read(length)
    return json.loads(body.decode("utf-8"))


def send(payload):
    body = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n%b" % (len(body), body))
    sys.stdout.buffer.flush()


def main():
    stdin = sys.stdin.buffer
    while True:
        message = read_message(stdin)
        if message is None:
            return
        method = message.get("method")
        msg_id = message.get("id")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "capabilities": {},
                "serverInfo": {"name": "fake-server"}}})
        elif method == "initialized":
            # Push a diagnostics notification unprompted.
            send({"jsonrpc": "2.0",
                  "method": "textDocument/publishDiagnostics",
                  "params": {"uri": "file:///C:/tmp/x.py",
                             "diagnostics": [{"message": "fake problem"}]}})
        elif method == "test/echo":
            send({"jsonrpc": "2.0", "id": msg_id,
                  "result": message.get("params")})
        elif method == "test/error":
            send({"jsonrpc": "2.0", "id": msg_id,
                  "error": {"code": -1, "message": "deliberate failure"}})
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": msg_id, "result": None})
        elif method == "exit":
            return


if __name__ == "__main__":
    main()
