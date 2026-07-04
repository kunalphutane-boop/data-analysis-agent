from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    load_context, plan, generate_code, execute_code, inspect,
    answer, enrich, clarify, finalize, handle_error,
)
from graph.edges import (
    after_load_context, after_plan, after_inspect, after_answer,
)


def _build_graph():
    g = StateGraph(AgentState)

    for name, fn in [
        ("load_context", load_context), ("plan", plan),
        ("generate_code", generate_code), ("execute_code", execute_code),
        ("inspect", inspect), ("answer", answer), ("enrich", enrich),
        ("clarify", clarify), ("finalize", finalize), ("handle_error", handle_error),
    ]:
        g.add_node(name, fn)

    g.set_entry_point("load_context")

    g.add_conditional_edges(
        "load_context", after_load_context,
        {"handle_error": "handle_error", "plan": "plan"},
    )
    g.add_conditional_edges(
        "plan", after_plan,
        {"handle_error": "handle_error", "clarify": "clarify", "generate_code": "generate_code"},
    )
    g.add_edge("generate_code", "execute_code")
    g.add_edge("execute_code", "inspect")
    g.add_conditional_edges(
        "inspect", after_inspect,
        {"generate_code": "generate_code", "answer": "answer"},
    )
    g.add_conditional_edges(
        "answer", after_answer,
        {"handle_error": "handle_error", "enrich": "enrich"},
    )
    g.add_edge("enrich", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("clarify", END)
    g.add_edge("handle_error", END)

    return g.compile()


agentic_ai = _build_graph()
