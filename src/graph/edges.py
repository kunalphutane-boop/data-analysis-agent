"""Conditional-edge routing functions for the analysis graph (see spec/agent.md)."""
from graph.state import AgentState


def after_load_context(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "plan"


def after_plan(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    if state.get("needs_clarification"):
        return "clarify"
    return "generate_code"


def after_inspect(state: AgentState) -> str:
    if state.get("execution_error") and state.get("retry_count", 0) < state.get("max_retries", 3):
        return "generate_code"
    return "answer"


def after_answer(state: AgentState) -> str:
    # answer node may set a fatal error only if the LLM answer call itself failed.
    return "handle_error" if state.get("error") and not state.get("answer") else "enrich"
