"""Local, restricted code-execution sandbox for LLM-generated pandas.

Generated code is never trusted. It runs in a curated namespace with no ambient
capabilities (no open/eval/exec/compile/__import__/input), against the full `df`,
under a wall-clock timeout enforced by a worker thread. Every outcome is a
structured dict; the sandbox never raises out.
"""
from __future__ import annotations

import io
import threading
import traceback
from contextlib import redirect_stdout
from typing import Any

import numpy as np
import pandas as pd

# Curated builtins allow-list — safe, pure helpers only. No file/network/import/eval.
_SAFE_BUILTINS = {
    name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)
    for name in (
        "len", "range", "min", "max", "sum", "sorted", "abs", "round",
        "enumerate", "zip", "list", "dict", "set", "tuple", "str", "int",
        "float", "bool", "print", "reversed", "map", "filter", "any", "all",
        "divmod", "pow", "isinstance", "type", "repr", "format",
    )
}

_MAX_REPR_LEN = 4000


def _safe_repr(value: Any) -> str:
    try:
        text = repr(value)
    except Exception:  # pragma: no cover - repr should not fail for pandas objects
        text = f"<unrepresentable {type(value).__name__}>"
    if len(text) > _MAX_REPR_LEN:
        text = text[:_MAX_REPR_LEN] + "\n... [truncated]"
    return text


def run_code(code: str, df: pd.DataFrame, timeout: int = 15) -> dict:
    """Execute `code` against `df`. Returns {ok, result, result_repr, stdout, error}."""
    namespace: dict[str, Any] = {
        "pd": pd,
        "np": np,
        "df": df,
        "__builtins__": _SAFE_BUILTINS,
    }
    stdout_buffer = io.StringIO()
    outcome: dict[str, Any] = {"error": None, "raised": None}

    def _target() -> None:
        try:
            with redirect_stdout(stdout_buffer):
                exec(code, namespace)  # noqa: S102 - restricted namespace by design
        except Exception as exc:  # captured, never propagated
            tb = traceback.format_exc(limit=3)
            outcome["error"] = f"{type(exc).__name__}: {exc}\n{tb}".strip()
            outcome["raised"] = exc

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout)

    if worker.is_alive():
        # Thread cannot be force-killed; it is abandoned as a daemon.
        return {
            "ok": False,
            "result": None,
            "result_repr": "",
            "stdout": stdout_buffer.getvalue(),
            "error": f"execution timed out after {timeout}s",
        }

    stdout = stdout_buffer.getvalue()

    if outcome["error"] is not None:
        return {
            "ok": False,
            "result": None,
            "result_repr": "",
            "stdout": stdout,
            "error": outcome["error"],
        }

    if "result" not in namespace:
        return {
            "ok": False,
            "result": None,
            "result_repr": "",
            "stdout": stdout,
            "error": "code did not assign a `result` variable",
        }

    result = namespace["result"]
    return {
        "ok": True,
        "result": result,
        "result_repr": _safe_repr(result),
        "stdout": stdout,
        "error": None,
    }
