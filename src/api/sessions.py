from fastapi import APIRouter
from pydantic import BaseModel

from api._common import ok, api_error
from domain import session as session_domain

router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: str | None = None


@router.post("/sessions")
def create_session(req: CreateSessionRequest) -> dict:
    try:
        data = session_domain.create_session(req.title)
    except Exception as exc:  # DB failure
        raise api_error("server_error", f"Could not create session: {exc}", 500)
    return ok(data)
