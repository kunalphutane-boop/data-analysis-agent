"""Unit tests for the P2 visual-outputs table serializer (`enrich` node).

Network-free: `_result_table` is pure serialization of an executed pandas result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from graph.nodes import _result_table, enrich


def test_dataframe_to_table_caps_and_nan():
    df = pd.DataFrame({"a": [1, 2], "b": [3.5, float("nan")]})
    t = _result_table(df)
    assert t["columns"] == ["a", "b"]
    assert t["rows"] == [[1, 3.5], [2, None]]  # NaN -> None
    assert t["row_count"] == 2
    assert t["truncated"] is False


def test_groupby_series_to_table():
    df = pd.DataFrame({"region": ["W", "E", "W"], "rev": [10, 20, 5]})
    t = _result_table(df.groupby("region")["rev"].sum())
    assert t["columns"] == ["region", "rev"]
    assert dict(t["rows"]) == {"E": 20, "W": 15}
    assert t["row_count"] == 2


def test_scalar_and_dict_and_nontabular():
    assert _result_table(42) == {
        "columns": ["value"],
        "rows": [[42]],
        "row_count": 1,
        "truncated": False,
    }
    assert _result_table({"x": 1, "y": 2})["columns"] == ["key", "value"]
    # numpy scalar coerces to a native cell
    assert _result_table(np.int64(7))["rows"] == [[7]]
    # non-tabular / unusable -> None
    assert _result_table(object()) is None


def test_row_cap_marks_truncated():
    df = pd.DataFrame({"n": list(range(120))})
    t = _result_table(df)
    assert len(t["rows"]) == 50
    assert t["row_count"] == 120
    assert t["truncated"] is True


def test_enrich_skips_on_execution_error():
    assert enrich({"execution_error": "boom", "execution_result": 5}) == {}
    assert enrich({"execution_result": 5}) == {"table": _result_table(5)}
