import sys
sys.path.insert(0, r'D:\NexCoder')
import json
from pathlib import Path
from nexcoder.agent.hermes_runtime import HermesAgentLoop

loop = HermesAgentLoop(project_root=Path(r"D:\NexCoder"))

# Happy path
result = json.loads(loop._load_skill({"id": "test-driven-development"}))
assert result["success"], result
print("tdd skill: ok, body length:", len(result["skill"]["body"]))

# Unknown
result = json.loads(loop._load_skill({"id": "nope"}))
assert not result["success"]
print("unknown skill: ok, error:", result["error"][:60])

# Missing id
result = json.loads(loop._load_skill({}))
assert not result["success"]
print("missing id: ok, error:", result["error"])

# Invalid id (path traversal)
result = json.loads(loop._load_skill({"id": "../etc/passwd"}))
assert not result["success"]
print("bad id: ok, error:", result["error"])
