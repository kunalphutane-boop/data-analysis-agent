"""LangGraph nodes for the analytical-QA loop.

Topology + field contract are defined in spec/agent.md. Every LLM call goes through
LLMClient.call_with_usage so tokens accumulate into the state for cost computation.
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis import loader, sandbox
from analysis.profiler import schema_from_profile
from config.settings import get_settings
from graph.state import AgentState
from llm import pricing
from llm.client import LLMClient
from observability.events import get_logger

_PROMPTS = Path(__file__).parent.parent / "prompts"
_log = get_logger("graph")

# Canonical step numbers shown in the UI (see api.md).
_STEP_PLAN = (1, "Plan")
_STEP_GEN = (2, "Generate code")
_STEP_EXEC = (3, "Execute")
_STEP_ANSWER = (4, "Answer")

# Long free-text cells (e.g. call transcripts) are truncated before being embedded
# in the plan/generate_code prompts: the model only needs a preview to write pandas,
# and the sandbox still runs on the full real DataFrame. This keeps those two prompts
# small (a few hundred tokens vs. ~9k for transcript data) — the main latency win.
_SAMPLE_CELL_MAX_CHARS = 200


def _compact_sample(sample: list) -> list:
    """Trim long string cells in the LLM-facing sample preview. Non-string cells and
    short strings pass through unchanged. Does not affect execution (full data)."""
    compact: list = []
    for row in sample:
        if isinstance(row, dict):
            compact.append(
                {
                    k: (v[:_SAMPLE_CELL_MAX_CHARS] + "…")
                    if isinstance(v, str) and len(v) > _SAMPLE_CELL_MAX_CHARS
                    else v
                    for k, v in row.items()
                }
            )
        else:
            compact.append(row)
    return compact


def _prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


def _set_step(state: AgentState, step: int, label: str, status: str) -> list:
    steps = [dict(s) for s in state.get("steps", [])]
    for s in steps:
        if s["step"] == step:
            s["status"] = status
            s["label"] = label
            return steps
    steps.append({"step": step, "label": label, "status": status})
    steps.sort(key=lambda s: s["step"])
    return steps


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```[a-zA-Z0-9]*\n(.*)\n```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # Loose fences without trailing newline
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _parse_plan_json(text: str) -> dict:
    cleaned = _strip_code_fences(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))
    return data


def _accumulate(state: AgentState, it: int, ot: int) -> dict:
    return {
        "input_tokens": state.get("input_tokens", 0) + it,
        "output_tokens": state.get("output_tokens", 0) + ot,
    }


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #

def load_context(state: AgentState) -> AgentState:
    """Load the DataFrame from disk and build the privacy-bounded context. No LLM."""
    try:
        settings = get_settings()
        df = loader.load_dataframe(state["filepath"])
        profile = state.get("profile") or {}
        schema = schema_from_profile(profile)
        sample = profile.get("sample", [])[: settings.sample_rows]
        _log.info("load_context", run_id=state.get("run_id"), rows=int(df.shape[0]))
        return {
            "dataframe": df,
            "schema": schema,
            "sample": sample,
            "profile": profile,
            "messages": [],
            "retry_count": 0,
            "input_tokens": state.get("input_tokens", 0),
            "output_tokens": state.get("output_tokens", 0),
        }
    except Exception as exc:
        _log.error("load_context_error", error=str(exc))
        return {"error": f"Failed to load dataset: {exc}"}


def plan(state: AgentState) -> AgentState:
    """Decide the approach; flag ambiguity. LLM (Gemini)."""
    started = time.time()
    try:
        context = {
            "question": state["question"],
            "schema": state.get("schema", {}),
            "profile_columns": state.get("profile", {}).get("columns", []),
            "sample": _compact_sample(state.get("sample", [])),
        }
        user = (
            f"Question: {state['question']}\n\n"
            f"Schema (column: dtype):\n{json.dumps(context['schema'], indent=2)}\n\n"
            f"Column profile:\n{json.dumps(context['profile_columns'], indent=2)}\n\n"
            f"Sample rows (first {len(context['sample'])}):\n"
            f"{json.dumps(context['sample'], indent=2)}"
        )
        text, it, ot = LLMClient().call_with_usage(user, system=_prompt("plan"))
        data = _parse_plan_json(text)
        needs = bool(data.get("needs_clarification", False))
        _log.info(
            "plan", run_id=state.get("run_id"), needs_clarification=needs,
            latency_ms=int((time.time() - started) * 1000), input_tokens=it, output_tokens=ot,
        )
        return {
            "plan": str(data.get("plan", "")),
            "needs_clarification": needs,
            "clarify_question": data.get("clarify_question"),
            "steps": _set_step(state, *_STEP_PLAN, "done"),
            **_accumulate(state, it, ot),
        }
    except Exception as exc:
        _log.error("plan_error", error=str(exc))
        return {"error": f"Planning failed: {exc}", "steps": _set_step(state, *_STEP_PLAN, "failed")}


def generate_code(state: AgentState) -> AgentState:
    """Emit pandas assigning `result`. On retry, include prior code + error. LLM."""
    started = time.time()
    try:
        parts = [
            f"Question: {state['question']}",
            f"Plan: {state.get('plan', '')}",
            f"Schema (column: dtype):\n{json.dumps(state.get('schema', {}), indent=2)}",
            f"Sample rows:\n{json.dumps(_compact_sample(state.get('sample', [])), indent=2)}",
        ]
        prior_error = state.get("execution_error")
        if prior_error and state.get("generated_code"):
            parts.append(
                "Your previous code FAILED. Fix it.\n"
                f"Previous code:\n{state['generated_code']}\n\n"
                f"Execution error:\n{prior_error}"
            )
        user = "\n\n".join(parts)
        text, it, ot = LLMClient().call_with_usage(user, system=_prompt("generate_code"))
        code = _strip_code_fences(text)
        _log.info(
            "generate_code", run_id=state.get("run_id"), retry_count=state.get("retry_count", 0),
            latency_ms=int((time.time() - started) * 1000), input_tokens=it, output_tokens=ot,
        )
        return {
            "generated_code": code,
            "steps": _set_step(state, *_STEP_GEN, "done"),
            **_accumulate(state, it, ot),
        }
    except Exception as exc:
        _log.error("generate_code_error", error=str(exc))
        return {"error": f"Code generation failed: {exc}", "steps": _set_step(state, *_STEP_GEN, "failed")}


def execute_code(state: AgentState) -> AgentState:
    """Run generated code in the local sandbox. Never raises out. No LLM."""
    settings = get_settings()
    started = time.time()
    outcome = sandbox.run_code(
        state.get("generated_code", ""),
        state["dataframe"],
        timeout=settings.sandbox_timeout_seconds,
    )
    _log.info(
        "execute_code", run_id=state.get("run_id"), ok=outcome["ok"],
        retry_count=state.get("retry_count", 0),
        latency_ms=int((time.time() - started) * 1000),
        error=outcome["error"],
    )
    status = "done" if outcome["ok"] else "retrying"
    return {
        "execution_result": outcome["result"],
        "execution_result_repr": outcome["result_repr"],
        "execution_stdout": outcome["stdout"],
        "execution_error": outcome["error"],
        "steps": _set_step(state, *_STEP_EXEC, status),
    }


def inspect(state: AgentState) -> AgentState:
    """Router state prep: increment retry_count on error. No LLM."""
    if state.get("execution_error"):
        new_count = state.get("retry_count", 0) + 1
        return {"retry_count": new_count}
    return {"steps": _set_step(state, *_STEP_EXEC, "done")}


def answer(state: AgentState) -> AgentState:
    """Plain-language answer grounded strictly in the real result. LLM (Gemini)."""
    started = time.time()
    try:
        if state.get("execution_error"):
            user = (
                f"Question: {state['question']}\n\n"
                f"The analysis could not be completed after {state.get('retry_count', 0)} "
                f"attempts. Final execution error:\n{state['execution_error']}"
            )
        else:
            user = (
                f"Question: {state['question']}\n\n"
                f"Plan: {state.get('plan', '')}\n\n"
                f"Computed result (from real pandas execution):\n"
                f"{state.get('execution_result_repr', '')}\n\n"
                f"Captured stdout:\n{state.get('execution_stdout', '')}"
            )
        text, it, ot = LLMClient().call_with_usage(user, system=_prompt("answer"))
        _log.info(
            "answer", run_id=state.get("run_id"),
            latency_ms=int((time.time() - started) * 1000), input_tokens=it, output_tokens=ot,
        )
        result: dict[str, Any] = {
            "answer": text.strip(),
            "steps": _set_step(state, *_STEP_ANSWER, "done"),
            **_accumulate(state, it, ot),
        }
        if state.get("execution_error"):
            result["error"] = state["execution_error"]
        return result
    except Exception as exc:
        _log.error("answer_error", error=str(exc))
        return {"error": f"Answer generation failed: {exc}", "steps": _set_step(state, *_STEP_ANSWER, "failed")}


# Caps so a huge result never bloats the /ask payload or the UI table.
_TABLE_MAX_ROWS = 50
_TABLE_MAX_COLS = 20


def _cell(v: Any) -> Any:
    """Coerce one value to a JSON-safe scalar (NaN → None, numpy/Timestamp → native)."""
    if v is None:
        return None
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float):
        return None if math.isnan(v) else v
    if isinstance(v, (int, str, bool)):
        return v
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return str(v)


def _result_table(result: Any) -> dict | None:
    """Best-effort structured table from an executed pandas result — no LLM.

    Returns `{columns, rows, row_count, truncated}` (rows/cols capped) or None when
    the result isn't tabular-ish. Never raises: a bad shape just yields no table.
    """
    try:
        if isinstance(result, pd.DataFrame):
            total_rows, total_cols = result.shape
            body = result.iloc[:_TABLE_MAX_ROWS, :_TABLE_MAX_COLS]
            include_index = not isinstance(result.index, pd.RangeIndex)
            columns = ([str(body.index.name or "index")] if include_index else []) + [
                str(c) for c in body.columns
            ]
            rows = []
            for idx, values in zip(body.index, body.itertuples(index=False, name=None)):
                cells = ([_cell(idx)] if include_index else []) + [_cell(v) for v in values]
                rows.append(cells)
            return {
                "columns": columns,
                "rows": rows,
                "row_count": int(total_rows),
                "truncated": bool(total_rows > _TABLE_MAX_ROWS or total_cols > _TABLE_MAX_COLS),
            }
        if isinstance(result, pd.Series):
            total = len(result)
            body = result.head(_TABLE_MAX_ROWS)
            key = str(result.index.name or "key")
            val = str(result.name or "value")
            rows = [[_cell(i), _cell(v)] for i, v in body.items()]
            return {
                "columns": [key, val],
                "rows": rows,
                "row_count": int(total),
                "truncated": total > _TABLE_MAX_ROWS,
            }
        if isinstance(result, dict):
            items = list(result.items())
            rows = [[_cell(k), _cell(v)] for k, v in items[:_TABLE_MAX_ROWS]]
            return {
                "columns": ["key", "value"],
                "rows": rows,
                "row_count": len(items),
                "truncated": len(items) > _TABLE_MAX_ROWS,
            }
        if isinstance(result, (list, tuple)):
            seq = list(result)
            if seq and all(isinstance(x, dict) for x in seq):
                cols: list[str] = []
                for d in seq[:_TABLE_MAX_ROWS]:
                    for k in d:
                        if str(k) not in cols:
                            cols.append(str(k))
                cols = cols[:_TABLE_MAX_COLS]
                rows = [[_cell(d.get(c)) for c in cols] for d in seq[:_TABLE_MAX_ROWS]]
                return {
                    "columns": cols,
                    "rows": rows,
                    "row_count": len(seq),
                    "truncated": len(seq) > _TABLE_MAX_ROWS,
                }
            rows = [[_cell(x)] for x in seq[:_TABLE_MAX_ROWS]]
            return {
                "columns": ["value"],
                "rows": rows,
                "row_count": len(seq),
                "truncated": len(seq) > _TABLE_MAX_ROWS,
            }
        if isinstance(result, (int, float, str, bool, np.generic)):
            return {"columns": ["value"], "rows": [[_cell(result)]], "row_count": 1, "truncated": False}
    except Exception:  # never let table-building break the answer
        return None
    return None


def enrich(state: AgentState) -> AgentState:
    """Best-effort structured table from the executed result (P2 visual outputs).

    Frontend-first, no LLM: the raw pandas `result` is serialised to a capped,
    JSON-safe table the UI renders and auto-charts. Never blocks the core answer —
    on an execution error or a non-tabular result there is simply no table.
    """
    if state.get("execution_error"):
        return {}
    table = _result_table(state.get("execution_result"))
    return {"table": table} if table else {}


def finalize(state: AgentState) -> AgentState:
    """Compute cost from accumulated tokens; mark steps complete. No LLM."""
    settings = get_settings()
    model = settings.llm_model or "gemini-2.5-flash"
    cost = pricing.cost_usd(
        model, state.get("input_tokens", 0), state.get("output_tokens", 0)
    )
    _log.info(
        "finalize", run_id=state.get("run_id"),
        input_tokens=state.get("input_tokens", 0),
        output_tokens=state.get("output_tokens", 0), cost_usd=cost,
        error=state.get("error"),
    )
    return {"cost_usd": cost}


def clarify(state: AgentState) -> AgentState:
    """Ambiguous question: surface the clarifying question instead of an answer. No LLM."""
    template = _prompt("clarify")
    question = state.get("clarify_question") or "Could you clarify your question?"
    answer_text = template.format(clarify_question=question)
    return {
        "answer": answer_text,
        "needs_clarification": True,
        "generated_code": "",
        "steps": _set_step(state, *_STEP_PLAN, "done"),
    }


def handle_error(state: AgentState) -> AgentState:
    """Fatal (non-code) error: return a clear failure answer. No LLM."""
    err = state.get("error") or "The analysis could not be completed."
    return {
        "answer": f"Sorry, the analysis could not be completed: {err}",
        "error": err,
    }
