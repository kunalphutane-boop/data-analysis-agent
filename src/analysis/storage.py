"""Local raw-file storage under data/uploads/. Files stay on disk, never in the DB."""
from __future__ import annotations

from pathlib import Path

# Repo root = src/analysis/storage.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
UPLOADS_DIR = _REPO_ROOT / "data" / "uploads"


def uploads_dir() -> Path:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADS_DIR


def save_upload(dataset_id: str, filename: str, content: bytes) -> str:
    """Write raw bytes to data/uploads/<dataset_id>/<filename>. Returns the path."""
    safe_name = Path(filename).name or "upload.csv"
    target_dir = uploads_dir() / dataset_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    target.write_bytes(content)
    return str(target)


def delete_upload(dataset_id: str) -> None:
    """Best-effort cleanup of a partial upload directory."""
    import shutil

    target_dir = UPLOADS_DIR / dataset_id
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
