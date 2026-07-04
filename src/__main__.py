"""Entry point.

`python -m src`         → start the API server on :8001.
`python -m src --run`   → run migrations, build the frontend (if present), then start.
"""
import subprocess
import sys
from pathlib import Path

import uvicorn

_SRC_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SRC_DIR.parent

# Make top-level modules (api, db, graph, ...) importable when run as `python -m src`.
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _run_migrations() -> None:
    print("[run] applying database migrations...", flush=True)
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=_REPO_ROOT, check=True)


def _build_frontend() -> None:
    frontend = _REPO_ROOT / "frontend"
    if not (frontend / "package.json").exists():
        print("[run] no frontend/ found — starting API-only.", flush=True)
        return
    try:
        print("[run] building frontend (pnpm build)...", flush=True)
        subprocess.run(["pnpm", "install"], cwd=frontend, check=True)
        subprocess.run(["pnpm", "build"], cwd=frontend, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        # Guard: server must still start if pnpm/frontend is unavailable.
        print(f"[run] frontend build skipped ({exc}) — starting API-only.", flush=True)


def main() -> None:
    if "--run" in sys.argv[1:]:
        _run_migrations()
        _build_frontend()
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=False)


if __name__ == "__main__":
    main()
