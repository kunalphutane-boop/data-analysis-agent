"""Sandbox security + behaviour tests — no LLM key required."""
import pandas as pd

from analysis.sandbox import run_code


def _df():
    return pd.DataFrame({"region": ["W", "E", "W"], "revenue": [100.0, 200.0, 50.0]})


def test_happy_path_groupby():
    out = run_code("result = df.groupby('region')['revenue'].sum()", _df())
    assert out["ok"] is True
    assert out["error"] is None
    assert out["result"]["W"] == 150.0
    assert out["result"]["E"] == 200.0
    assert "W" in out["result_repr"]


def test_captures_stdout():
    out = run_code("print('hello sandbox')\nresult = 1 + 1", _df())
    assert out["ok"] is True
    assert out["result"] == 2
    assert "hello sandbox" in out["stdout"]


def test_missing_result_is_error():
    out = run_code("x = df['revenue'].sum()", _df())
    assert out["ok"] is False
    assert "result" in out["error"]


def test_runtime_error_captured_not_raised():
    out = run_code("result = df['does_not_exist'].sum()", _df())
    assert out["ok"] is False
    assert out["result"] is None
    assert "KeyError" in out["error"] or "does_not_exist" in out["error"]


def test_open_is_blocked():
    out = run_code("result = open('/etc/passwd').read()", _df())
    assert out["ok"] is False
    assert "open" in out["error"] or "NameError" in out["error"]


def test_import_is_blocked():
    out = run_code("import os\nresult = os.getcwd()", _df())
    assert out["ok"] is False
    assert "error" in out and out["error"]


def test_dunder_import_is_blocked():
    out = run_code("result = __import__('os').getcwd()", _df())
    assert out["ok"] is False
    assert out["error"]


def test_eval_is_blocked():
    out = run_code("result = eval('1+1')", _df())
    assert out["ok"] is False
    assert out["error"]


def test_timeout_enforced():
    out = run_code("result = 0\nwhile True:\n    result += 1", _df(), timeout=1)
    assert out["ok"] is False
    assert "timed out" in out["error"]


def test_safe_builtins_available():
    out = run_code("result = sum([len(str(x)) for x in range(3)])", _df())
    assert out["ok"] is True
    assert out["result"] == 3
