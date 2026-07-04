"""Guard the answer-JSON parsing (insight + follow-ups) and suggestion heuristics.
Network-free: both helpers are pure. The real-LLM paths are covered end-to-end.
"""
from __future__ import annotations

from domain import suggestions
from graph.nodes import _parse_answer_json


def test_parse_answer_json_valid():
    a, k, f = _parse_answer_json(
        '{"answer": "West leads.", "key_insight": "West is 44% of total.", '
        '"follow_ups": ["By month?", "By product?", "Top region?", "extra?"]}'
    )
    assert a == "West leads."
    assert k == "West is 44% of total."
    assert f == ["By month?", "By product?", "Top region?"]  # capped at 3


def test_parse_answer_json_fenced_and_partial():
    # Code-fenced JSON with a missing key still parses; follow_ups defaults to [].
    a, k, f = _parse_answer_json('```json\n{"answer": "42", "key_insight": "big"}\n```')
    assert a == "42" and k == "big" and f == []


def test_parse_answer_json_plain_prose_fallback():
    # Non-JSON prose becomes the answer; no insight/follow-ups, never raises.
    a, k, f = _parse_answer_json("Just a plain answer.")
    assert a == "Just a plain answer." and k == "" and f == []


def test_suggestions_heuristic_uses_real_columns():
    profile = {
        "columns": [
            {"name": "region", "dtype": "str"},
            {"name": "revenue", "dtype": "int64"},
        ]
    }
    out = suggestions._heuristic(profile)
    assert out and all(isinstance(q, str) and q for q in out)
    assert any("region" in q and "revenue" in q for q in out)
    assert len(out) == len(set(out))  # de-duped


def test_suggestions_heuristic_always_nonempty():
    assert suggestions._heuristic({"columns": []})  # falls back to a generic question
