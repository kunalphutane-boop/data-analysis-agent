"""Routing/edge logic — deterministic, no LLM key required."""
from graph.edges import after_inspect, after_plan, after_load_context, after_answer


def test_load_context_error_routes_to_handler():
    assert after_load_context({"error": "boom"}) == "handle_error"
    assert after_load_context({}) == "plan"


def test_plan_clarify_branch():
    assert after_plan({"needs_clarification": True}) == "clarify"
    assert after_plan({"error": "x"}) == "handle_error"
    assert after_plan({}) == "generate_code"


def test_inspect_retries_while_budget_remains():
    # error + retry_count < max_retries -> loop back
    assert after_inspect({"execution_error": "e", "retry_count": 1, "max_retries": 3}) == "generate_code"
    # error but retries exhausted -> proceed to answer (explains failure)
    assert after_inspect({"execution_error": "e", "retry_count": 3, "max_retries": 3}) == "answer"
    # success -> answer
    assert after_inspect({"execution_error": None, "retry_count": 0, "max_retries": 3}) == "answer"


def test_answer_routes_to_enrich_when_answer_present():
    assert after_answer({"answer": "ok"}) == "enrich"
    # answer LLM failed with no text -> handle_error
    assert after_answer({"error": "llm down", "answer": None}) == "handle_error"
    # grounded failure answer (execution error) still flows to enrich
    assert after_answer({"answer": "could not compute", "error": "KeyError"}) == "enrich"
