"""Robust file loader for CSV, XLSX, XLS, Parquet, and JSON.

Contract
--------
- The DataFrame stored in ``LoadResult.df`` is the raw, unmodified output of pandas.
  No column is renamed, no value is cast, no row is dropped silently.
- Any non-fatal issue is surfaced through ``LoadResult.warnings``; the caller
  decides what to communicate to the user.
- ``reload_sheet`` accepts the same raw bytes stored by the caller, so the user
  can switch Excel sheets without re-uploading.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Union

import pandas as pd

from app.utils.validators import validate_upload, validate_dataframe

logger = logging.getLogger(__name__)


class _FakeUpload:
    """Minimal duck-type for Streamlit's UploadedFile.

    Lets callers that already have ``raw_bytes`` avoid a second ``.read()`` call
    after the stream has been consumed.
    """
    def __init__(self, name: str, size: int, raw: bytes) -> None:
        self.name = name
        self.size = size
        self._raw = raw

    def read(self) -> bytes:
        return self._raw

_ENCODINGS_TO_TRY = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "utf-16"]
_SNIFF_BYTES = 16_384  # 16 KB is enough to sniff delimiter reliably


# ── Public data class ────────────────────────────────────────────────────────

@dataclass
class LoadResult:
    df: pd.DataFrame
    filename: str
    file_type: str                       # "csv" | "xlsx" | "xls" | "parquet" | "json"
    sheet_names: list[str]               # populated for Excel; empty otherwise
    active_sheet: str                    # populated for Excel; empty otherwise
    encoding: str                        # detected/used encoding
    rows: int
    columns: int
    warnings: list[str] = field(default_factory=list)


# ── Public API ───────────────────────────────────────────────────────────────

def load_from_upload(uploaded_file, sheet_name: Union[str, int] = 0) -> LoadResult:
    """Load a Streamlit UploadedFile.  Returns a LoadResult; never mutates ``uploaded_file``."""
    validate_upload(uploaded_file.name, uploaded_file.size)
    raw: bytes = uploaded_file.read()
    ext = _extension(uploaded_file.name)

    dispatch = {
        "csv":     lambda: _load_csv(raw, uploaded_file.name, ext),
        "xlsx":    lambda: _load_excel(raw, uploaded_file.name, ext, sheet_name),
        "xls":     lambda: _load_excel(raw, uploaded_file.name, ext, sheet_name),
        "parquet": lambda: _load_parquet(raw, uploaded_file.name, ext),
        "json":    lambda: _load_json(raw, uploaded_file.name, ext),
    }
    loader = dispatch.get(ext)
    if loader is None:
        raise ValueError(f"Unsupported file type: .{ext}")
    return loader()


def reload_sheet(raw_bytes: bytes, filename: str, sheet_name: Union[str, int]) -> LoadResult:
    """Re-parse an Excel file with a different sheet without re-uploading."""
    ext = _extension(filename)
    if ext not in ("xlsx", "xls"):
        raise ValueError("Sheet selection only applies to Excel files (.xlsx / .xls).")
    return _load_excel(raw_bytes, filename, ext, sheet_name)


# ── CSV ──────────────────────────────────────────────────────────────────────

def _load_csv(raw: bytes, filename: str, ext: str) -> LoadResult:
    warnings: list[str] = []

    encoding, enc_warn = _detect_encoding(raw)
    if enc_warn:
        warnings.append(enc_warn)

    sep = _sniff_separator(raw, encoding)
    if sep != ",":
        sep_display = {"\\t": "tab", "\t": "tab"}.get(sep, repr(sep))
        warnings.append(f"Auto-detected delimiter: {sep_display}. If incorrect, the preview may look wrong.")

    try:
        df = pd.read_csv(
            io.BytesIO(raw),
            encoding=encoding,
            sep=sep,
            on_bad_lines="warn",
            low_memory=False,
            dtype_backend="numpy_nullable",
        )
    except UnicodeDecodeError:
        encoding = "latin-1"
        warnings.append("UTF-8 decode failed; re-reading with latin-1. Some special characters may appear incorrectly.")
        df = pd.read_csv(
            io.BytesIO(raw),
            encoding=encoding,
            sep=sep,
            on_bad_lines="warn",
            low_memory=False,
            dtype_backend="numpy_nullable",
        )
    except pd.errors.ParserError as exc:
        raise ValueError(f"CSV parse error: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Could not read CSV file: {exc}") from exc

    validate_dataframe(df)
    warnings += _warn_unnamed_columns(df)
    return LoadResult(df=df, filename=filename, file_type=ext,
                      sheet_names=[], active_sheet="", encoding=encoding,
                      rows=len(df), columns=len(df.columns), warnings=warnings)


# ── Excel ────────────────────────────────────────────────────────────────────

def _load_excel(raw: bytes, filename: str, ext: str, sheet_name: Union[str, int] = 0) -> LoadResult:
    warnings: list[str] = []

    try:
        xl = pd.ExcelFile(io.BytesIO(raw))
    except Exception as exc:
        raise ValueError(f"Cannot open Excel file: {exc}") from exc

    sheet_names: list[str] = xl.sheet_names
    if not sheet_names:
        raise ValueError("Excel file contains no sheets.")

    # Resolve the requested sheet
    active = _resolve_sheet(sheet_names, sheet_name, warnings)

    try:
        df = xl.parse(active, dtype_backend="numpy_nullable")
    except Exception as exc:
        raise ValueError(f"Cannot parse sheet '{active}': {exc}") from exc

    validate_dataframe(df)

    if len(sheet_names) > 1:
        warnings.append(
            f"This file contains {len(sheet_names)} sheets. "
            f"Currently showing '{active}'. Use the sheet selector to switch."
        )
    warnings += _warn_unnamed_columns(df)

    return LoadResult(df=df, filename=filename, file_type=ext,
                      sheet_names=sheet_names, active_sheet=active,
                      encoding="n/a (binary)",
                      rows=len(df), columns=len(df.columns), warnings=warnings)


def _resolve_sheet(sheet_names: list[str], requested: Union[str, int],
                   warnings: list[str]) -> str:
    if isinstance(requested, int):
        if 0 <= requested < len(sheet_names):
            return sheet_names[requested]
        warnings.append(f"Sheet index {requested} is out of range; loading the first sheet.")
        return sheet_names[0]
    if requested in sheet_names:
        return requested
    warnings.append(f"Sheet '{requested}' not found; loading the first sheet.")
    return sheet_names[0]


# ── Parquet ──────────────────────────────────────────────────────────────────

def _load_parquet(raw: bytes, filename: str, ext: str) -> LoadResult:
    try:
        df = pd.read_parquet(io.BytesIO(raw))
    except Exception as exc:
        raise ValueError(f"Could not read Parquet file: {exc}") from exc
    validate_dataframe(df)
    return LoadResult(df=df, filename=filename, file_type=ext,
                      sheet_names=[], active_sheet="", encoding="binary",
                      rows=len(df), columns=len(df.columns))


# ── JSON ─────────────────────────────────────────────────────────────────────

def _load_json(raw: bytes, filename: str, ext: str) -> LoadResult:
    warnings: list[str] = []
    encoding, enc_warn = _detect_encoding(raw)
    if enc_warn:
        warnings.append(enc_warn)

    try:
        df = pd.read_json(io.BytesIO(raw), encoding=encoding, dtype_backend="numpy_nullable")
    except ValueError:
        try:
            df = pd.read_json(io.BytesIO(raw), encoding=encoding, lines=True, dtype_backend="numpy_nullable")
            warnings.append("Parsed as JSON Lines (one JSON object per line).")
        except Exception as exc:
            raise ValueError(f"Could not parse JSON file: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Could not read JSON file: {exc}") from exc

    validate_dataframe(df)
    return LoadResult(df=df, filename=filename, file_type=ext,
                      sheet_names=[], active_sheet="", encoding=encoding,
                      rows=len(df), columns=len(df.columns), warnings=warnings)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _detect_encoding(raw: bytes) -> tuple[str, str]:
    """Return (encoding, warning).  Warning is empty on clean detection."""
    if raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig", ""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16", ""
    for enc in _ENCODINGS_TO_TRY:
        try:
            raw.decode(enc)
            return enc, ""
        except (UnicodeDecodeError, LookupError):
            continue
    return "latin-1", (
        "Could not confidently detect file encoding; falling back to latin-1. "
        "Special characters (accents, symbols) may appear incorrectly."
    )


def _sniff_separator(raw: bytes, encoding: str) -> str:
    try:
        sample = raw[:_SNIFF_BYTES].decode(encoding, errors="replace")
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _warn_unnamed_columns(df: pd.DataFrame) -> list[str]:
    unnamed = [str(c) for c in df.columns if str(c).startswith("Unnamed:")]
    if not unnamed:
        return []
    names = ", ".join(f"'{c}'" for c in unnamed[:5])
    suffix = f" (+{len(unnamed)-5} more)" if len(unnamed) > 5 else ""
    return [
        f"Found {len(unnamed)} unnamed column(s): {names}{suffix}. "
        "These typically come from an extra index column in the source file."
    ]
