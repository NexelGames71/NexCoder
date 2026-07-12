from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.session_store import SessionStore
from nexcoder.agent.core.transport import XmlAdapter


class OneShotModel:
    def complete(self, messages, *, extras, on_delta=None):
        return {"role": "assistant", "content": "all done"}


def test_store_save_load_list(tmp_path):
    store = SessionStore(tmp_path)
    store.save("run_a", {"task": "t1"})
    store.save("run_b", {"task": "t2"})
    assert store.load("run_a") == {"task": "t1"}
    assert store.load("missing") is None
    assert set(store.list_runs()) == {"run_a", "run_b"}


def test_loop_persists_session(tmp_path):
    store = SessionStore(tmp_path)
    loop = AgentLoop(
        project_root=tmp_path, model=OneShotModel(), adapter=XmlAdapter(),
        belt=build_default_belt(), system_prompt="sys", session_store=store)
    result = loop.run("say done")
    saved = store.load(result["run_id"])
    assert saved is not None
    assert saved["status"] == "completed"
    assert saved["task"] == "say done"
    assert any(m["role"] == "assistant" for m in saved["messages"])
