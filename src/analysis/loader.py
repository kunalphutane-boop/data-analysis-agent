"""Read an uploaded file into a pandas DataFrame. Phase 1: CSV only."""
from __future__ import annotations

import csv
import io
from collections import Counter
from pathlib import Path

import pandas as pd

# How many bytes / lines to probe when sniffing for a leading junk/title line.
_PROBE_BYTES = 65536
_PROBE_LINES = 10


class BadFileError(Exception):
    """Raised when a file cannot be parsed into a non-empty DataFrame."""


def _field_count(line: str) -> int:
    """Number of CSV fields in a single physical line (quoting-aware)."""
    if line.strip() == "":
        return 0
    try:
        return len(next(csv.reader([line])))
    except Exception:
        return 1


def _detect_skiprows(head_text: str) -> int:
    """Detect leading junk/title lines to skip before the real header.

    A malformed export can prepend a title line (e.g. ``Table 1``) before the
    real header. Such a line has drastically fewer delimiters (a single token)
    than the structured rows that follow. We compute the modal field count of
    the probed body lines; if a well-formed CSV already starts with its header
    (first line matches the modal shape) we skip nothing.
    """
    lines = head_text.splitlines()[:_PROBE_LINES]
    counts = [_field_count(line) for line in lines]
    if len(counts) < 2:
        return 0

    # Modal field count of the lines AFTER the first — the plausible table body.
    body = [c for c in counts[1:] if c > 0]
    if not body:
        return 0
    modal = Counter(body).most_common(1)[0][0]
    if modal <= 1:
        # Genuinely single-column data — nothing structural to detect.
        return 0

    # Skip only leading single-token lines that are drastically thinner than
    # the modal shape. Stop at the first line that looks like the real header.
    skip = 0
    for c in counts:
        if c <= 1 and c < modal:
            skip += 1
        else:
            break
    return skip


def _read_csv_with_header_sniff(source, head_text: str) -> pd.DataFrame:
    """Parse ``source`` as CSV, skipping any detected leading junk line(s)."""
    skiprows = _detect_skiprows(head_text)
    try:
        return pd.read_csv(source, skiprows=skiprows)
    except pd.errors.EmptyDataError as exc:
        raise BadFileError("The file is empty or has no columns.") from exc
    except Exception as exc:  # parser errors, encoding, etc.
        raise BadFileError(f"Could not parse the file as CSV: {exc}") from exc


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    if df.shape[0] == 0 or df.shape[1] == 0:
        raise BadFileError("The file contains no data rows.")
    return df


def load_dataframe(filepath: str | Path) -> pd.DataFrame:
    """Load a CSV from disk into a DataFrame. Raises BadFileError on empty/unparseable."""
    path = Path(filepath)
    try:
        with open(path, "rb") as fh:
            head = fh.read(_PROBE_BYTES)
    except OSError as exc:
        raise BadFileError(f"Could not read the file: {exc}") from exc
    head_text = head.decode("utf-8", errors="replace")
    df = _read_csv_with_header_sniff(path, head_text)
    return _validate(df)


def load_dataframe_from_bytes(content: bytes) -> pd.DataFrame:
    """Parse CSV bytes into a DataFrame (used to validate before persisting)."""
    head_text = content[:_PROBE_BYTES].decode("utf-8", errors="replace")
    df = _read_csv_with_header_sniff(io.BytesIO(content), head_text)
    return _validate(df)
