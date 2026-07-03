"""Session use-cases: create a workspace."""
from __future__ import annotations

from db.models import SessionRow
from db.session import create_db_session


def _serialize(row: SessionRow) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def create_session(title: str | None = None) -> dict:
    with create_db_session() as session:
        row = SessionRow(title=(title or "Untitled analysis"))
        session.add(row)
        session.flush()
        data = _serialize(row)
    return data


def ensure_session(session_id: str | None) -> str:
    """Return an existing session id, or create one if absent/unknown."""
    if session_id:
        with create_db_session() as session:
            row = session.get(SessionRow, session_id)
            if row is not None:
                return row.id
    return create_session()["id"]


class NotFoundError(Exception):
    pass


def get_business_context(session_id: str) -> str:
    """Return the session's saved free-text business context ("" if unset)."""
    with create_db_session() as session:
        row = session.get(SessionRow, session_id)
        if row is None:
            raise NotFoundError(f"Session {session_id} not found.")
        return row.business_context or ""


def set_business_context(session_id: str, business_context: str) -> str:
    """Persist a new business context for the session. Returns the stored value."""
    value = (business_context or "").strip()
    with create_db_session() as session:
        row = session.get(SessionRow, session_id)
        if row is None:
            raise NotFoundError(f"Session {session_id} not found.")
        row.business_context = value
        return value
