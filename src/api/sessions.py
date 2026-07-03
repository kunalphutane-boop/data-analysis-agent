from fastapi import APIRouter
from pydantic import BaseModel

from api._common import ok, api_error
from domain import session as session_domain

router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: str | None = None


class BusinessContextRequest(BaseModel):
    business_context: str = ""


@router.post("/sessions")
def create_session(req: CreateSessionRequest) -> dict:
    try:
        data = session_domain.create_session(req.title)
    except Exception as exc:  # DB failure
        raise api_error("server_error", f"Could not create session: {exc}", 500)
    return ok(data)


@router.get("/sessions/{session_id}/business_context")
def get_business_context(session_id: str) -> dict:
    try:
        value = session_domain.get_business_context(session_id)
    except session_domain.NotFoundError as exc:
        raise api_error("not_found", str(exc), 404)
    return ok({"session_id": session_id, "business_context": value})


@router.put("/sessions/{session_id}/business_context")
def put_business_context(session_id: str, req: BusinessContextRequest) -> dict:
    try:
        value = session_domain.set_business_context(session_id, req.business_context)
    except session_domain.NotFoundError as exc:
        raise api_error("not_found", str(exc), 404)
    except Exception as exc:  # DB failure
        raise api_error("server_error", f"Could not save business context: {exc}", 500)
    return ok({"session_id": session_id, "business_context": value})
