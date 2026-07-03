"""Loader tests — CSV header sniffing and missing-value tolerance. No LLM key required."""
import io

import pandas as pd
import pytest

from analysis.loader import (
    BadFileError,
    load_dataframe,
    load_dataframe_from_bytes,
)
from analysis.profiler import build_profile

NORMAL_CSV = (
    "call_id,start_time,end_time,dead_air,dialled_number,note\n"
    "1,09:00,09:05,0,555,hi\n"
    "2,09:10,09:12,1,556,bye\n"
)

JUNK_HEADER_CSV = "Table 1\n" + NORMAL_CSV


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# --- happy path: junk leading line is skipped -----------------------------
def test_junk_first_line_skipped_from_path(tmp_path):
    df = load_dataframe(_write(tmp_path, "junk.csv", JUNK_HEADER_CSV))
    assert df.shape[1] == 6
    assert list(df.columns) == [
        "call_id",
        "start_time",
        "end_time",
        "dead_air",
        "dialled_number",
        "note",
    ]
    assert df.shape[0] == 2


def test_junk_first_line_skipped_from_bytes():
    df = load_dataframe_from_bytes(JUNK_HEADER_CSV.encode("utf-8"))
    assert df.shape[1] == 6
    assert "Table 1" not in df.columns


# --- unaffected: a well-formed CSV is read unchanged -----------------------
def test_normal_csv_unaffected_from_path(tmp_path):
    df = load_dataframe(_write(tmp_path, "ok.csv", NORMAL_CSV))
    assert df.shape == (2, 6)
    assert list(df.columns)[0] == "call_id"


def test_normal_csv_unaffected_from_bytes():
    df = load_dataframe_from_bytes(NORMAL_CSV.encode("utf-8"))
    assert df.shape == (2, 6)


def test_single_column_csv_unaffected():
    """A genuine single-column dataset must not be mistaken for junk."""
    single = "value\n1\n2\n3\n"
    df = load_dataframe_from_bytes(single.encode("utf-8"))
    assert df.shape == (3, 1)
    assert list(df.columns) == ["value"]


# --- edge / error paths ----------------------------------------------------
def test_empty_file_raises():
    with pytest.raises(BadFileError):
        load_dataframe_from_bytes(b"")


# --- missing values: profiler tolerates blanks after header sniff ----------
def test_missing_values_profile_after_junk_header():
    text = (
        "Table 1\n"
        "id,start_time,note\n"
        "1,,hello\n"
        "2,,\n"
        "3,09:00,world\n"
        "4,,\n"
    )
    df = load_dataframe_from_bytes(text.encode("utf-8"))
    assert df.shape == (4, 3)
    profile = build_profile(df)
    cols = {c["name"]: c for c in profile["columns"]}
    # start_time: 3 of 4 blank -> 1 non-null, 75% missing
    assert cols["start_time"]["non_null"] == 1
    assert cols["start_time"]["missing_pct"] == 75.0
    # note: 2 of 4 blank -> 2 non-null, 50% missing
    assert cols["note"]["non_null"] == 2
    assert cols["note"]["missing_pct"] == 50.0
    assert cols["id"]["non_null"] == 4
