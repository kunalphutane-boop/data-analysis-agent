"""Profiler tests — no LLM key required."""
import numpy as np
import pandas as pd

from analysis.profiler import build_profile, schema_from_profile


def _frame():
    return pd.DataFrame(
        {
            "region": ["West", "East", "West", None],
            "revenue": [100.0, 200.0, np.nan, 50.0],
            "qty": [1, 2, 3, 4],
        }
    )


def test_counts_and_types():
    p = build_profile(_frame(), sample_rows=2)
    assert p["row_count"] == 4
    assert p["col_count"] == 3
    frame = _frame()
    cols = {c["name"]: c for c in p["columns"]}
    # dtype string is whatever pandas reports for this version (object/str).
    assert cols["region"]["dtype"] == str(frame["region"].dtype)
    assert cols["revenue"]["dtype"] == "float64"


def test_missing_pct():
    p = build_profile(_frame())
    cols = {c["name"]: c for c in p["columns"]}
    assert cols["revenue"]["non_null"] == 3
    assert cols["revenue"]["missing_pct"] == 25.0
    assert cols["region"]["non_null"] == 3
    assert cols["region"]["missing_pct"] == 25.0


def test_numeric_min_max_and_non_numeric_null():
    p = build_profile(_frame())
    cols = {c["name"]: c for c in p["columns"]}
    assert cols["revenue"]["min"] == 50.0
    assert cols["revenue"]["max"] == 200.0
    assert cols["qty"]["min"] == 1
    assert cols["qty"]["max"] == 4
    assert cols["region"]["min"] is None
    assert cols["region"]["max"] is None


def test_sample_respects_limit_and_is_json_safe():
    import json

    p = build_profile(_frame(), sample_rows=2)
    assert len(p["sample"]) == 2
    # NaN must be None, not float('nan') — must be JSON serialisable.
    json.dumps(p)
    assert p["sample"][2 - 1]["revenue"] == 200.0


def test_schema_from_profile():
    frame = _frame()
    p = build_profile(frame)
    schema = schema_from_profile(p)
    assert schema["region"] == str(frame["region"].dtype)
    assert schema["revenue"] == "float64"
