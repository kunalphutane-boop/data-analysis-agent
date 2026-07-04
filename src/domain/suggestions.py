"""Starter-question suggestions for a loaded dataset.

Best-effort: one cheap LLM call over the schema + a compact sample produces
dataset-tailored questions; on any failure we fall back to deterministic,
column-driven heuristics so the UI always has something useful to show.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from db.models import DatasetRow
from db.session import create_db_session
from llm.client import LLMClient

_PROMPTS = Path(__file__).parent.parent / "prompts"
_SAMPLE_CELL_MAX_CHARS = 160
_MAX_SUGGESTIONS = 5


class NotFoundError(Exception):
    pass


def _is_numeric(dtype: str) -> bool:
    return any(t in (dtype or "").lower() for t in ("int", "float", "number", "double"))


def _columns(profile: dict) -> list[dict]:
    return profile.get("columns", []) or []


def _compact_sample(sample: list) -> list:
    out: list = []
    for row in sample[:3]:
        if isinstance(row, dict):
            out.append(
                {
                    k: (v[:_SAMPLE_CELL_MAX_CHARS] + "…")
                    if isinstance(v, str) and len(v) > _SAMPLE_CELL_MAX_CHARS
                    else v
                    for k, v in row.items()
                }
            )
        else:
            out.append(row)
    return out


def _heuristic(profile: dict) -> list[str]:
    cols = _columns(profile)
    numeric = [c["name"] for c in cols if _is_numeric(c.get("dtype", ""))]
    categorical = [c["name"] for c in cols if not _is_numeric(c.get("dtype", ""))]
    out: list[str] = []
    if numeric and categorical:
        out.append(f"What is the total {numeric[0]} by {categorical[0]}?")
        out.append(f"Which {categorical[0]} has the highest {numeric[0]}?")
        if len(numeric) > 1:
            out.append(f"What is the average {numeric[1]} by {categorical[0]}?")
    if categorical:
        out.append(f"How many rows are there per {categorical[0]}?")
    if numeric:
        out.append(f"What is the distribution of {numeric[0]}?")
    if not out:
        out.append("How many rows and columns does this dataset have?")
    # de-dup, preserve order
    seen: set[str] = set()
    unique = [q for q in out if not (q in seen or seen.add(q))]
    return unique[:_MAX_SUGGESTIONS]


def _llm_suggestions(profile: dict) -> list[str]:
    schema = {c["name"]: c.get("dtype", "") for c in _columns(profile)}
    sample = _compact_sample(profile.get("sample", []))
    user = (
        f"Schema (column: dtype):\n{json.dumps(schema, indent=2)}\n\n"
        f"Sample rows:\n{json.dumps(sample, indent=2)}"
    )
    system = (_PROMPTS / "suggest_questions.md").read_text(encoding="utf-8").strip()
    text, _it, _ot = LLMClient().call_with_usage(user, system=system)
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    data = json.loads(match.group(0) if match else cleaned)
    questions = [str(q).strip() for q in data if str(q).strip()]
    return questions[:_MAX_SUGGESTIONS]


def get_suggestions(dataset_id: str) -> dict:
    """Return `{suggestions: [str]}` for the dataset. Never raises past NotFound."""
    with create_db_session() as session:
        row = session.get(DatasetRow, dataset_id)
        if row is None:
            raise NotFoundError(f"Dataset {dataset_id} not found.")
        profile = json.loads(row.profile_json)

    try:
        suggestions = _llm_suggestions(profile)
        if suggestions:
            return {"suggestions": suggestions}
    except Exception:
        pass  # fall back to deterministic heuristics
    return {"suggestions": _heuristic(profile)}
