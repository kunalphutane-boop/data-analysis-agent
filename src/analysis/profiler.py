"""Compute a column-level profile of a DataFrame.

The profile is the ONLY dataset-derived metadata persisted and (schema + sample)
the only row-level data ever sent to the LLM. Raw rows never leave the machine.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _json_safe(value: Any) -> Any:
    """Convert numpy / pandas scalars and NaN into JSON-serialisable Python values."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if math.isnan(f) else f
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.ndarray,)):
        return [_json_safe(v) for v in value.tolist()]
    if pd.isna(value) if np.isscalar(value) else False:
        return None
    return value


def build_profile(df: pd.DataFrame, sample_rows: int = 5) -> dict:
    """Return the full profile dict matching the api.md upload shape."""
    row_count = int(df.shape[0])
    col_count = int(df.shape[1])

    columns: list[dict] = []
    for name in df.columns:
        series = df[name]
        non_null = int(series.notna().sum())
        missing = row_count - non_null
        missing_pct = round((missing / row_count) * 100, 2) if row_count else 0.0

        col_min: Any = None
        col_max: Any = None
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            if non_null > 0:
                col_min = _json_safe(series.min())
                col_max = _json_safe(series.max())

        columns.append(
            {
                "name": str(name),
                "dtype": str(series.dtype),
                "non_null": non_null,
                "missing_pct": missing_pct,
                "min": col_min,
                "max": col_max,
            }
        )

    sample_df = df.head(max(0, sample_rows))
    sample = [
        {str(k): _json_safe(v) for k, v in record.items()}
        for record in sample_df.to_dict(orient="records")
    ]

    return {
        "row_count": row_count,
        "col_count": col_count,
        "columns": columns,
        "sample": sample,
    }


def schema_from_profile(profile: dict) -> dict:
    """{column: dtype} map used to build the privacy-bounded LLM context."""
    return {c["name"]: c["dtype"] for c in profile.get("columns", [])}
