"""Ask use-case: validate session/dataset, then run the graph."""
from __future__ import annotations

from db.models import DatasetRow, SessionRow
from db.session import create_db_session
from graph.runner import run_ask as _run_ask


class NotFoundError(Exception):
    pass


def run_ask(session_id: str, dataset_id: str, question: str) -> dict:
    with create_db_session() as session:
        if session.get(SessionRow, session_id) is None:
            raise NotFoundError(f"Session {session_id} not found.")
        dataset = session.get(DatasetRow, dataset_id)
        if dataset is None or dataset.session_id != session_id:
            raise NotFoundError(f"Dataset {dataset_id} not found for this session.")
    return _run_ask(session_id, dataset_id, question)
