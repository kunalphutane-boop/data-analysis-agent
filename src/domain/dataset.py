"""Dataset use-cases: upload + profile, fetch."""
from __future__ import annotations

import json
from uuid import uuid4

from analysis import loader, storage
from analysis.profiler import build_profile
from config.settings import get_settings
from db.models import DatasetRow
from db.session import create_db_session
from domain.session import ensure_session

MAX_BYTES = 100 * 1024 * 1024  # ~100 MB


class BadFileError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


class NotFoundError(Exception):
    pass


def _serialize(row: DatasetRow) -> dict:
    profile = json.loads(row.profile_json)
    return {
        "id": row.id,
        "session_id": row.session_id,
        "filename": row.filename,
        "row_count": row.row_count,
        "col_count": row.col_count,
        "profile": profile,
    }


def upload_dataset(filename: str, content: bytes, session_id: str | None = None) -> dict:
    if len(content) > MAX_BYTES:
        raise FileTooLargeError("File exceeds the ~100 MB limit.")
    if not filename.lower().endswith(".csv"):
        raise BadFileError("Only CSV files are supported in Phase 1.")

    # Parse + profile before persisting anything.
    try:
        df = loader.load_dataframe_from_bytes(content)
    except loader.BadFileError as exc:
        raise BadFileError(str(exc)) from exc

    settings = get_settings()
    profile = build_profile(df, sample_rows=settings.sample_rows)

    sid = ensure_session(session_id)
    dataset_id = str(uuid4())

    filepath = storage.save_upload(dataset_id, filename, content)
    try:
        with create_db_session() as session:
            row = DatasetRow(
                id=dataset_id,
                session_id=sid,
                filename=filename,
                filepath=filepath,
                row_count=int(df.shape[0]),
                col_count=int(df.shape[1]),
                profile_json=json.dumps(profile),
            )
            session.add(row)
            session.flush()
            data = _serialize(row)
    except Exception:
        storage.delete_upload(dataset_id)
        raise
    return data


def get_dataset(dataset_id: str) -> dict:
    with create_db_session() as session:
        row = session.get(DatasetRow, dataset_id)
        if row is None:
            raise NotFoundError(f"Dataset {dataset_id} not found.")
        return _serialize(row)
