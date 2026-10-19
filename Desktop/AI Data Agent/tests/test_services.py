"""Service tests — Claude calls are mocked to avoid API charges."""

import io
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from app.services.data_loader import load_from_upload, reload_sheet
from app.services.export_service import to_csv_bytes, to_excel_bytes, get_filtered_view


class FakeUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self.size = len(data)
        self._data = data

    def read(self) -> bytes:
        return self._data


# ── data loader ───────────────────────────────────────────────────────────────

def test_load_csv_returns_loadresult():
    csv_bytes = b"a,b\n1,2\n3,4"
    f = FakeUpload("data.csv", csv_bytes)
    result = load_from_upload(f)
    assert result.df is not None
    assert len(result.df) == 2
    assert result.rows == 2
    assert result.columns == 2
    assert result.filename == "data.csv"
    assert result.file_type == "csv"


def test_load_csv_with_missing_values():
    csv_bytes = b"name,age\nAlice,30\nBob,\nCarol,25"
    f = FakeUpload("data.csv", csv_bytes)
    result = load_from_upload(f)
    assert result.df["age"].isna().sum() == 1


def test_load_csv_tab_delimited():
    csv_bytes = b"a\tb\n1\t2\n3\t4"
    f = FakeUpload("data.csv", csv_bytes)
    result = load_from_upload(f)
    assert list(result.df.columns) == ["a", "b"]


def test_load_invalid_extension_raises():
    with pytest.raises(ValueError, match="not supported"):
        f = FakeUpload("data.txt", b"hello")
        load_from_upload(f)


def test_load_zero_byte_raises():
    with pytest.raises(ValueError, match="empty"):
        f = FakeUpload("data.csv", b"")
        load_from_upload(f)


def test_load_excel_basic():
    buf = io.BytesIO()
    df_orig = pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_orig.to_excel(writer, index=False)
    raw = buf.getvalue()
    f = FakeUpload("data.xlsx", raw)
    result = load_from_upload(f)
    assert list(result.df.columns) == ["x", "y"]
    assert result.file_type == "xlsx"


def test_load_excel_multi_sheet():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Sheet1", index=False)
        pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="Sheet2", index=False)
    raw = buf.getvalue()
    f = FakeUpload("data.xlsx", raw)
    result = load_from_upload(f)
    assert len(result.sheet_names) == 2
    # switching sheets
    result2 = reload_sheet(raw, "data.xlsx", "Sheet2")
    assert "b" in result2.df.columns


# ── export service ────────────────────────────────────────────────────────────

def test_export_csv_roundtrip():
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    csv = to_csv_bytes(df)
    result = pd.read_csv(io.BytesIO(csv))
    assert list(result.columns) == ["x", "y"]


def test_export_csv_preserves_values():
    df = pd.DataFrame({"name": ["Alice", "Bob"], "score": [9.5, 8.0]})
    csv = to_csv_bytes(df)
    result = pd.read_csv(io.BytesIO(csv))
    assert result["name"].tolist() == ["Alice", "Bob"]
    assert result["score"].tolist() == [9.5, 8.0]


def test_export_excel_roundtrip():
    df = pd.DataFrame({"x": [1, 2]})
    xlsx = to_excel_bytes(df)
    result = pd.read_excel(io.BytesIO(xlsx))
    assert "x" in result.columns


def test_export_excel_preserves_nulls():
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    xlsx = to_excel_bytes(df)
    result = pd.read_excel(io.BytesIO(xlsx))
    assert result["a"].isna().sum() == 1


def test_get_filtered_view_no_filter():
    """get_filtered_view falls back to full df when no session state is available."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    view = get_filtered_view(df)
    assert len(view) == len(df)
    assert list(view.columns) == list(df.columns)
