"""Invoke the compiled graph for one ask and persist the resulting `messages` row."""
from __future__ import annotations

import json

from config.settings import get_settings
from db.models import DatasetRow, MessageRow, SessionRow
from db.session import create_db_session
from graph.agent import agentic_ai
from graph.state import AgentState
from observability.events import get_logger

_log = get_logger("runner")


def run_ask(session_id: str, dataset_id: str, question: str) -> dict:
    """Create the message row, run the graph, persist results, return the /ask payload."""
    settings = get_settings()

    # Load dataset + create the pending message row (run_id == message id).
    with create_db_session() as session:
        dataset = session.get(DatasetRow, dataset_id)
        filepath = dataset.filepath
        profile = json.loads(dataset.profile_json)

        msg = MessageRow(
            session_id=session_id,
            dataset_id=dataset_id,
            role="turn",
            question=question,
        )
        session.add(msg)
        session.flush()
        run_id = msg.id

    initial: AgentState = {
        "run_id": run_id,
        "session_id": session_id,
        "dataset_id": dataset_id,
        "question": question,
        "filepath": filepath,
        "profile": profile,
        "messages": [],
        "retry_count": 0,
        "max_retries": settings.max_retries,
        "input_tokens": 0,
        "output_tokens": 0,
        "error": None,
    }

    _log.info("ask_start", run_id=run_id, question=question[:120])
    final = agentic_ai.invoke(initial)

    answer_text = final.get("answer")
    generated_code = final.get("generated_code") or None
    steps = final.get("steps", [])
    input_tokens = final.get("input_tokens", 0)
    output_tokens = final.get("output_tokens", 0)
    cost_usd = final.get("cost_usd", 0.0)
    error = final.get("error")
    needs_clarification = bool(final.get("needs_clarification", False))
    clarify_question = final.get("clarify_question")

    with create_db_session() as session:
        msg = session.get(MessageRow, run_id)
        msg.generated_code = generated_code
        msg.answer_text = answer_text
        msg.steps_json = json.dumps(steps)
        msg.input_tokens = input_tokens
        msg.output_tokens = output_tokens
        msg.cost_usd = cost_usd
        msg.error = error
        sess = session.get(SessionRow, session_id)
        if sess is not None:
            from datetime import datetime, timezone
            sess.updated_at = datetime.now(timezone.utc)

    _log.info(
        "ask_done", run_id=run_id, cost_usd=cost_usd,
        input_tokens=input_tokens, output_tokens=output_tokens, error=error,
    )

    return {
        "message_id": run_id,
        "answer": answer_text,
        "generated_code": generated_code if not needs_clarification else "",
        "steps": steps,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "needs_clarification": needs_clarification,
        "clarify_question": clarify_question,
        "table": final.get("table"),
        "error": error,
    }
