from fastapi import APIRouter
from pydantic import BaseModel

from api._common import ok, api_error
from domain import ask as ask_domain

router = APIRouter()


class AskRequest(BaseModel):
    session_id: str
    dataset_id: str
    question: str


@router.post("/ask")
def ask(req: AskRequest) -> dict:
    if not req.question.strip():
        raise api_error("bad_request", "question must not be empty", 400)
    try:
        data = ask_domain.run_ask(req.session_id, req.dataset_id, req.question)
    except ask_domain.NotFoundError as exc:
        raise api_error("not_found", str(exc), 404)
    except Exception as exc:
        raise api_error("server_error", f"Ask failed: {exc}", 500)
    return ok(data)
