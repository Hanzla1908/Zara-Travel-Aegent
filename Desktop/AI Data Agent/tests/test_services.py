"""Service tests — Claude calls are mocked to avoid API charges."""

import io
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from app.services.data_loader import load_from_upload
from app.services.export_service import to_csv_bytes, to_excel_bytes


class FakeUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self.size = len(data)
        self._data = data

    def read(self) -> bytes:
        return self._data


def test_load_csv():
    csv_bytes = b"a,b\n1,2\n3,4"
    f = FakeUpload("data.csv", csv_bytes)
    df = load_from_upload(f)
    assert len(df) == 2


def test_export_csv_roundtrip():
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    csv = to_csv_bytes(df)
    result = pd.read_csv(io.BytesIO(csv))
    assert list(result.columns) == ["x", "y"]


def test_export_excel_roundtrip():
    df = pd.DataFrame({"x": [1, 2]})
    xlsx = to_excel_bytes(df)
    result = pd.read_excel(io.BytesIO(xlsx))
    assert "x" in result.columns
