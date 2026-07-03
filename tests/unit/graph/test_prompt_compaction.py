"""Guard the plan/generate_code prompt optimization: long free-text cells (e.g. call
transcripts) are truncated in the LLM-facing sample so those prompts stay small.
"""
from __future__ import annotations

from graph.nodes import _SAMPLE_CELL_MAX_CHARS, _compact_sample


def test_long_string_cells_truncated():
    big = "x" * 6000
    out = _compact_sample([{"call_id": "C1", "log": big}])
    assert len(out[0]["log"]) == _SAMPLE_CELL_MAX_CHARS + 1  # +1 for the ellipsis
    assert out[0]["log"].endswith("…")
    assert out[0]["call_id"] == "C1"  # short cells untouched


def test_non_string_and_short_pass_through():
    out = _compact_sample([{"n": 5, "s": "short", "f": 1.5}])
    assert out == [{"n": 5, "s": "short", "f": 1.5}]


def test_non_dict_rows_pass_through():
    assert _compact_sample([[1, 2, 3]]) == [[1, 2, 3]]
