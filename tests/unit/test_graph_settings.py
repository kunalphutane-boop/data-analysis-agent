"""Graph compilation + settings/state shape — no LLM key required."""
from graph.agent import agentic_ai
from graph.state import AgentState


def test_graph_compiles():
    assert agentic_ai is not None


def test_graph_has_all_nodes():
    node_names = set(agentic_ai.get_graph().nodes.keys())
    for expected in [
        "load_context", "plan", "generate_code", "execute_code", "inspect",
        "answer", "enrich", "clarify", "finalize", "handle_error",
    ]:
        assert expected in node_names


def test_new_settings_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import config.settings as m
    m._settings = None
    s = m.get_settings()
    assert s.sample_rows == 5
    assert s.sandbox_timeout_seconds == 15
    assert s.max_retries == 3


def test_state_is_typeddict():
    st: AgentState = {"question": "x"}
    assert st["question"] == "x"
