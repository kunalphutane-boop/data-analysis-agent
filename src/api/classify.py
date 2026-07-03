"""Conversation Intelligence endpoints (Phase 4). See spec/api.md."""
from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from api._common import ok, api_error
from domain import classify as classify_domain

router = APIRouter()


class ClassifyRequest(BaseModel):
    text_column: str


@router.post("/datasets/{dataset_id}/classify")
def start_classify(dataset_id: str, req: ClassifyRequest) -> dict:
    if not req.text_column.strip():
        raise api_error("bad_column", "text_column must not be empty", 400)
    try:
        data = classify_domain.start_job(dataset_id, req.text_column)
    except classify_domain.NotFoundError as exc:
        raise api_error("not_found", str(exc), 404)
    except classify_domain.BadColumnError as exc:
        raise api_error("bad_column", str(exc), 400)
    except Exception as exc:
        raise api_error("server_error", f"Could not start classify job: {exc}", 500)
    return ok(data)


@router.get("/classify/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        data = classify_domain.get_progress(job_id)
    except classify_domain.NotFoundError as exc:
        raise api_error("not_found", str(exc), 404)
    return ok(data)


@router.get("/classify/jobs/{job_id}/results")
def get_job_results(job_id: str) -> dict:
    try:
        data = classify_domain.get_results(job_id)
    except classify_domain.NotFoundError as exc:
        raise api_error("not_found", str(exc), 404)
    return ok(data)


@router.get("/classify/jobs/{job_id}/labelled.csv")
def download_labelled_csv(job_id: str) -> Response:
    try:
        csv_text, filename = classify_domain.export_labelled_csv(job_id)
    except classify_domain.NotFoundError as exc:
        raise api_error("not_found", str(exc), 404)
    except classify_domain.NotReadyError as exc:
        raise api_error("not_ready", str(exc), 409)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
