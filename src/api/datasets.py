from fastapi import APIRouter, File, Form, UploadFile

from api._common import ok, api_error
from domain import dataset as dataset_domain
from domain import suggestions as suggestions_domain

router = APIRouter()


@router.post("/datasets/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
) -> dict:
    content = await file.read()
    filename = file.filename or "upload.csv"
    try:
        data = dataset_domain.upload_dataset(filename, content, session_id)
    except dataset_domain.FileTooLargeError as exc:
        raise api_error("file_too_large", str(exc), 413)
    except dataset_domain.BadFileError as exc:
        raise api_error("bad_file", str(exc), 400)
    except Exception as exc:
        raise api_error("server_error", f"Upload failed: {exc}", 500)
    return ok(data)


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
    try:
        data = dataset_domain.get_dataset(dataset_id)
    except dataset_domain.NotFoundError as exc:
        raise api_error("not_found", str(exc), 404)
    return ok(data)


@router.get("/datasets/{dataset_id}/suggestions")
def get_suggestions(dataset_id: str) -> dict:
    try:
        data = suggestions_domain.get_suggestions(dataset_id)
    except suggestions_domain.NotFoundError as exc:
        raise api_error("not_found", str(exc), 404)
    return ok(data)
